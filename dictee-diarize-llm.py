#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dictee-diarize-llm — LLM analysis pipeline for diarized transcripts.

Pure logic module: parses dictee diarize output, dispatches to a configured
LLM provider, and returns the analysis text. No UI here — used by
dictee-transcribe (UI) and as a standalone CLI for testing.

CLI:
    dictee-diarize-llm --profile synthese --input out.txt
    dictee-diarize-llm --list-profiles
    dictee-diarize-llm --list-providers
    dictee-diarize-llm --test-provider ollama-local
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request

# ── Constants ─────────────────────────────────────────────────────────

XDG_CONFIG = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
CONFIG_DIR = os.path.join(XDG_CONFIG, "dictee")
PROVIDERS_PATH = os.path.join(CONFIG_DIR, "llm-providers.json")
PROFILES_PATH = os.path.join(CONFIG_DIR, "llm-profiles.json")

# Same regex as dictee-transcribe.py — keep in sync.
DIARIZE_RE = re.compile(
    r"\[(\d+\.?\d*)s\s*-\s*(\d+\.?\d*)s\]\s*(Speaker\s+\d+|UNKNOWN):\s*(.*)"
)

DEFAULT_TIMEOUT = 120  # seconds — LLM calls on long transcripts can take time

# ── Built-in profiles ─────────────────────────────────────────────────
#
# Modes:
#   "global"      — entire formatted transcript is sent in one LLM call.
#                   Output is whatever the LLM produced (markdown, etc.).
#   "per-segment" — one LLM call per segment, label stripped before sending
#                   and re-attached after. Speaker labels can never be
#                   corrupted by the LLM since it never sees them.

PROMPT_SYNTHESE = """\
<role>
Tu synthétises une transcription de réunion ou interview diarisée. Tu n'es pas un assistant conversationnel.
</role>
<instructions>
À partir de la transcription ci-dessous (labels [Speaker N] = locuteurs), produis un compte-rendu en Markdown structuré :

## Résumé
3-5 phrases qui résument l'échange.

## Décisions
Liste des décisions explicites prises pendant l'échange.

## Actions à faire
Format : « - [Locuteur] : action (échéance si mentionnée) »

## Questions ouvertes
Points soulevés sans résolution.

Règles strictes :
- Fidélité absolue : n'invente rien, ne déduis rien d'absent.
- Si une section est vide, écris « _Aucun_ ».
- Cite les locuteurs par leur label exact ([Speaker N]).
- Ne reproduis PAS la transcription, seulement la synthèse.
- Aucun préambule, aucune conclusion ajoutée.
</instructions>
<input>
{TRANSCRIPT}
</input>
"""

PROMPT_CHAPITRAGE = """\
<role>
Tu identifies les changements de sujet dans une transcription diarisée pour produire un sommaire navigable.
</role>
<instructions>
Découpe la transcription ci-dessous en chapitres thématiques. Format de sortie strict :

[HH:MM:SS] Titre court (3-7 mots)

Règles :
- Nouveau chapitre uniquement quand le sujet change réellement (pas à chaque tour de parole).
- Cible : 1 chapitre toutes les 2-5 minutes.
- Titres descriptifs et neutres (ex. « Roadmap Q3 », pas « Discussion sur la roadmap »).
- Utilise les timestamps présents dans la transcription.
- Ne produis QUE la liste, aucune autre sortie.
</instructions>
<input>
{TRANSCRIPT}
</input>
"""

PROMPT_CORRECTION_ASR = """\
<role>
Correcteur d'erreurs de reconnaissance vocale (ASR). Tu n'es pas un assistant conversationnel.
</role>
<instructions>
Corrige uniquement les erreurs PROBABLES de reconnaissance dans le segment ci-dessous (issu d'un ASR Parakeet).

À FAIRE :
- Corriger homophones, mots mal reconnus, noms propres déformés.
- Privilégier les termes du dictionnaire utilisateur (s'il y en a un) en cas de doute phonétique.
- Préserver à l'identique : ponctuation correcte, casse, hésitations (« euh », « hum »).

À NE PAS FAIRE :
- Reformuler, résumer, compléter une phrase coupée.
- Modifier la ponctuation correcte.
- Ajouter du contenu non présent dans le segment.
- Commenter, introduire, expliquer.

Si rien à corriger, renvoie le segment tel quel, sans commentaire.

Contexte (segment précédent, pour cohérence — NE PAS le retourner) :
{PREVIOUS_SEGMENT}

Dictionnaire utilisateur :
{DICTIONARY}
</instructions>
<input>
{TRANSCRIPT}
</input>
"""

BUILTIN_PROFILES = [
    {
        "id": "synthese",
        "name": "Synthèse / compte-rendu",
        "prompt": PROMPT_SYNTHESE,
        "mode": "global",
        "default_provider_id": "ollama-local",
        "default_model": "gemma3:4b",
        "builtin": True,
    },
    {
        "id": "chapitrage",
        "name": "Chapitrage",
        "prompt": PROMPT_CHAPITRAGE,
        "mode": "global",
        "default_provider_id": "ollama-local",
        "default_model": "gemma3:4b",
        "builtin": True,
    },
    {
        "id": "correction-asr",
        "name": "Correction ASR contextuelle",
        "prompt": PROMPT_CORRECTION_ASR,
        "mode": "per-segment",
        "default_provider_id": "ollama-local",
        "default_model": "gemma3:4b",
        "builtin": True,
    },
]

BUILTIN_PROVIDERS = [
    {
        "id": "ollama-local",
        "name": "Ollama (local)",
        "type": "ollama",
        "url": "http://localhost:11434",
        "api_key": None,
        "builtin": True,
    },
]


# ── Diarize parsing & formatting ──────────────────────────────────────

def parse_diarize_text(text):
    """Parse dictee diarize output into a list of segments.

    Each segment is a dict: {"start": float, "end": float,
                              "speaker": str, "text": str}
    Lines that don't match the diarize format are skipped silently.
    """
    segments = []
    for line in text.splitlines():
        m = DIARIZE_RE.match(line.strip())
        if m:
            segments.append({
                "start": float(m.group(1)),
                "end": float(m.group(2)),
                "speaker": m.group(3),
                "text": m.group(4).strip(),
            })
    return segments


def _seconds_to_hms(seconds):
    """Format seconds as HH:MM:SS."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def format_segments_for_prompt(segments):
    """Format segments as a clean text block for the LLM prompt.

    Format: '[Speaker 1] (00:01:23 → 00:01:25): text\n\n...'
    Speaker labels are kept exactly as parsed so the LLM can reference them.
    """
    lines = []
    for seg in segments:
        ts = f"{_seconds_to_hms(seg['start'])} → {_seconds_to_hms(seg['end'])}"
        lines.append(f"[{seg['speaker']}] ({ts}): {seg['text']}")
    return "\n\n".join(lines)


# ── Providers ────────────────────────────────────────────────────────

class ProviderError(Exception):
    """Raised on provider call failures (network, API, parsing)."""


def _http_post_json(url, payload, headers, timeout):
    """POST JSON payload, return parsed JSON response."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise ProviderError(f"HTTP {e.code} {e.reason}: {body[:300]}") from e
    except urllib.error.URLError as e:
        raise ProviderError(f"Network error: {e.reason}") from e
    except (TimeoutError, socket.timeout) as e:
        raise ProviderError(f"Timeout after {timeout}s") from e
    except (OSError, ValueError) as e:
        raise ProviderError(f"{type(e).__name__}: {e}") from e


def _http_get_json(url, headers, timeout):
    """GET request, return parsed JSON response."""
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise ProviderError(f"HTTP {e.code} {e.reason}: {body[:300]}") from e
    except urllib.error.URLError as e:
        raise ProviderError(f"Network error: {e.reason}") from e
    except (TimeoutError, socket.timeout) as e:
        raise ProviderError(f"Timeout after {timeout}s") from e
    except (OSError, ValueError) as e:
        raise ProviderError(f"{type(e).__name__}: {e}") from e


def _provider_call_ollama(cfg, model, system, prompt, timeout):
    url = cfg["url"].rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        payload["system"] = system
    headers = {"Content-Type": "application/json"}
    data = _http_post_json(url, payload, headers, timeout)
    return data.get("response", "").strip()


def _provider_list_models_ollama(cfg, timeout=10):
    url = cfg["url"].rstrip("/") + "/api/tags"
    data = _http_get_json(url, {}, timeout)
    return [m.get("name", "") for m in data.get("models", []) if m.get("name")]


def _provider_call_openai(cfg, model, system, prompt, timeout):
    url = cfg["url"].rstrip("/") + "/chat/completions"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {"model": model, "messages": messages, "stream": False}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.get('api_key', '')}",
    }
    data = _http_post_json(url, payload, headers, timeout)
    choices = data.get("choices") or []
    if not choices:
        raise ProviderError(f"No choices in response: {str(data)[:300]}")
    return choices[0].get("message", {}).get("content", "").strip()


def _provider_list_models_openai(cfg, timeout=10):
    url = cfg["url"].rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {cfg.get('api_key', '')}"}
    data = _http_get_json(url, headers, timeout)
    return [m.get("id", "") for m in data.get("data", []) if m.get("id")]


def _provider_call_anthropic(cfg, model, system, prompt, timeout):
    url = cfg["url"].rstrip("/") + "/v1/messages"
    payload = {
        "model": model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system
    headers = {
        "Content-Type": "application/json",
        "x-api-key": cfg.get("api_key", ""),
        "anthropic-version": "2023-06-01",
    }
    data = _http_post_json(url, payload, headers, timeout)
    content = data.get("content") or []
    if not content:
        raise ProviderError(f"No content in response: {str(data)[:300]}")
    parts = [c.get("text", "") for c in content if c.get("type") == "text"]
    return "".join(parts).strip()


def _provider_list_models_anthropic(cfg, timeout=10):
    url = cfg["url"].rstrip("/") + "/v1/models"
    headers = {
        "x-api-key": cfg.get("api_key", ""),
        "anthropic-version": "2023-06-01",
    }
    data = _http_get_json(url, headers, timeout)
    return [m.get("id", "") for m in data.get("data", []) if m.get("id")]


PROVIDER_DISPATCH = {
    "ollama": (_provider_call_ollama, _provider_list_models_ollama),
    "openai": (_provider_call_openai, _provider_list_models_openai),
    "anthropic": (_provider_call_anthropic, _provider_list_models_anthropic),
}


def call_provider(provider_cfg, model, prompt, system=None,
                  timeout=DEFAULT_TIMEOUT):
    """Dispatch a generation call to the right provider type.

    provider_cfg: provider dict from llm-providers.json (or built-in).
    Returns the generated text (string), or raises ProviderError.
    """
    ptype = provider_cfg.get("type")
    if ptype not in PROVIDER_DISPATCH:
        raise ProviderError(f"Unknown provider type: {ptype!r}")
    call_fn, _ = PROVIDER_DISPATCH[ptype]
    return call_fn(provider_cfg, model, system, prompt, timeout)


def list_provider_models(provider_cfg, timeout=10):
    """List models exposed by a provider. Returns [] on failure types
    that mean 'listing not supported'."""
    ptype = provider_cfg.get("type")
    if ptype not in PROVIDER_DISPATCH:
        raise ProviderError(f"Unknown provider type: {ptype!r}")
    _, list_fn = PROVIDER_DISPATCH[ptype]
    return list_fn(provider_cfg, timeout)


# ── Persistence (providers + profiles) ───────────────────────────────

def _ensure_config_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def _atomic_write_json(path, payload, mode=0o600):
    """Write JSON atomically with restrictive permissions."""
    _ensure_config_dir()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


def load_providers():
    """Return list of providers: built-ins + user-defined.

    User file is created on first read with the built-in defaults so the
    user can edit it. Built-ins are always re-merged on top to allow
    schema upgrades — user entries with conflicting IDs are kept.
    """
    user_providers = []
    if os.path.isfile(PROVIDERS_PATH):
        try:
            with open(PROVIDERS_PATH, encoding="utf-8") as f:
                data = json.load(f)
            user_providers = [p for p in data.get("providers", [])
                              if not p.get("builtin")]
        except (OSError, ValueError) as e:
            print(f"[dictee-diarize-llm] Warning: failed to read "
                  f"{PROVIDERS_PATH}: {e}", file=sys.stderr)
    return list(BUILTIN_PROVIDERS) + user_providers


def save_providers(providers):
    """Persist user-defined providers (built-ins are not stored)."""
    user = [p for p in providers if not p.get("builtin")]
    _atomic_write_json(PROVIDERS_PATH, {"providers": user})


def load_profiles():
    """Return list of profiles: built-ins + user-defined."""
    user_profiles = []
    if os.path.isfile(PROFILES_PATH):
        try:
            with open(PROFILES_PATH, encoding="utf-8") as f:
                data = json.load(f)
            user_profiles = [p for p in data.get("profiles", [])
                             if not p.get("builtin")]
        except (OSError, ValueError) as e:
            print(f"[dictee-diarize-llm] Warning: failed to read "
                  f"{PROFILES_PATH}: {e}", file=sys.stderr)
    return list(BUILTIN_PROFILES) + user_profiles


def save_profiles(profiles):
    """Persist user-defined profiles (built-ins are not stored)."""
    user = [p for p in profiles if not p.get("builtin")]
    _atomic_write_json(PROFILES_PATH, {"profiles": user})


def find_profile(profile_id):
    for p in load_profiles():
        if p["id"] == profile_id:
            return p
    return None


def find_provider(provider_id):
    for p in load_providers():
        if p["id"] == provider_id:
            return p
    return None


# ── Analysis (the actual work) ───────────────────────────────────────

def _render_prompt(template, transcript, previous_segment="", dictionary=""):
    """Substitute variables in a prompt template."""
    return (template
            .replace("{TRANSCRIPT}", transcript)
            .replace("{PREVIOUS_SEGMENT}", previous_segment or "(none)")
            .replace("{DICTIONARY}", dictionary or "(none)"))


def analyze_global(segments, profile, provider_cfg, model, dictionary="",
                   timeout=DEFAULT_TIMEOUT):
    """Run a global-mode profile (Synthèse, Chapitrage, custom).

    Sends the full formatted transcript in one LLM call. Returns the
    raw LLM output (typically markdown).
    """
    transcript = format_segments_for_prompt(segments)
    prompt = _render_prompt(profile["prompt"], transcript,
                            dictionary=dictionary)
    return call_provider(provider_cfg, model, prompt, timeout=timeout)


def analyze_per_segment(segments, profile, provider_cfg, model,
                        dictionary="", timeout=DEFAULT_TIMEOUT,
                        progress_cb=None):
    """Run a per-segment-mode profile (Correction ASR).

    For each segment, send only the text (no speaker label) plus the
    previous segment as context. Reassemble the corrected transcript
    keeping the original DIARIZE_RE format so it stays compatible with
    dictee-transcribe parsing.

    progress_cb: optional callable(idx, total) for UI feedback.
    """
    out_lines = []
    previous = ""
    total = len(segments)
    for idx, seg in enumerate(segments):
        if progress_cb is not None:
            progress_cb(idx, total)
        prompt = _render_prompt(profile["prompt"], seg["text"],
                                previous_segment=previous,
                                dictionary=dictionary)
        try:
            corrected = call_provider(provider_cfg, model, prompt,
                                      timeout=timeout).strip()
            if not corrected:
                corrected = seg["text"]
        except ProviderError as e:
            print(f"[dictee-diarize-llm] Segment {idx + 1}/{total} failed: "
                  f"{e} — keeping original.", file=sys.stderr)
            corrected = seg["text"]
        # Reassemble in DIARIZE_RE-compatible form so the result can be
        # round-tripped back into the UI without re-parsing logic.
        out_lines.append(
            f"[{seg['start']:.2f}s - {seg['end']:.2f}s] "
            f"{seg['speaker']}: {corrected}"
        )
        previous = corrected
    if progress_cb is not None:
        progress_cb(total, total)
    return "\n".join(out_lines)


def analyze(segments, profile, provider_cfg, model=None, dictionary="",
            timeout=DEFAULT_TIMEOUT, progress_cb=None):
    """Top-level entry point. Routes to global or per-segment based on
    the profile's mode.

    model: overrides profile's default_model if given. Lets the UI
    surface a model picker without mutating the saved profile.
    """
    effective_model = model or profile.get("default_model")
    if not effective_model:
        raise ProviderError(
            f"No model specified (profile={profile['id']!r} has no default)")
    mode = profile.get("mode", "global")
    if mode == "per-segment":
        return analyze_per_segment(segments, profile, provider_cfg,
                                   effective_model, dictionary=dictionary,
                                   timeout=timeout, progress_cb=progress_cb)
    return analyze_global(segments, profile, provider_cfg, effective_model,
                          dictionary=dictionary, timeout=timeout)


# ── CLI ──────────────────────────────────────────────────────────────

def _cli_list_profiles():
    for p in load_profiles():
        flag = "[builtin]" if p.get("builtin") else "[user]"
        print(f"  {p['id']:<20} {flag:<10} {p['name']}  "
              f"(mode={p.get('mode', 'global')})")


def _cli_list_providers():
    for p in load_providers():
        flag = "[builtin]" if p.get("builtin") else "[user]"
        print(f"  {p['id']:<20} {flag:<10} {p['type']:<10} {p['url']}")


def _cli_test_provider(provider_id):
    cfg = find_provider(provider_id)
    if not cfg:
        print(f"Provider not found: {provider_id}", file=sys.stderr)
        return 2
    try:
        models = list_provider_models(cfg)
    except ProviderError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        return 1
    print(f"OK — {len(models)} model(s) available:")
    for m in models[:20]:
        print(f"  {m}")
    if len(models) > 20:
        print(f"  ... and {len(models) - 20} more")
    return 0


def _cli_run(args):
    profile = find_profile(args.profile)
    if not profile:
        print(f"Profile not found: {args.profile}", file=sys.stderr)
        return 2

    provider_id = args.provider or profile.get("default_provider_id")
    cfg = find_provider(provider_id)
    if not cfg:
        print(f"Provider not found: {provider_id}", file=sys.stderr)
        return 2

    if args.input == "-":
        text = sys.stdin.read()
    else:
        with open(args.input, encoding="utf-8") as f:
            text = f.read()

    segments = parse_diarize_text(text)
    if not segments:
        print("No diarized segments found in input.", file=sys.stderr)
        return 3

    def _progress(i, n):
        print(f"\r[{i}/{n}]", end="", file=sys.stderr, flush=True)
        if i == n:
            print("", file=sys.stderr)

    try:
        result = analyze(segments, profile, cfg, model=args.model,
                         dictionary=args.dictionary or "",
                         timeout=args.timeout,
                         progress_cb=_progress if args.verbose else None)
    except ProviderError as e:
        print(f"LLM call failed: {e}", file=sys.stderr)
        return 1

    print(result)
    return 0


def main():
    p = argparse.ArgumentParser(
        prog="dictee-diarize-llm",
        description="LLM analysis pipeline for diarized transcripts.")
    p.add_argument("--profile", help="Profile id (e.g. synthese, chapitrage).")
    p.add_argument("--provider", help="Provider id (default: profile default).")
    p.add_argument("--model", help="Model override (default: profile default).")
    p.add_argument("--input", default="-",
                   help="Input file with diarized text ('-' = stdin).")
    p.add_argument("--dictionary", default="",
                   help="Optional user dictionary (text).")
    p.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                   help=f"Per-call timeout in seconds (default {DEFAULT_TIMEOUT}).")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="Print per-segment progress to stderr.")
    p.add_argument("--list-profiles", action="store_true")
    p.add_argument("--list-providers", action="store_true")
    p.add_argument("--test-provider", metavar="ID",
                   help="Ping a provider and list its models.")

    args = p.parse_args()

    if args.list_profiles:
        _cli_list_profiles()
        return 0
    if args.list_providers:
        _cli_list_providers()
        return 0
    if args.test_provider:
        return _cli_test_provider(args.test_provider)
    if not args.profile:
        p.error("--profile is required (or use --list-profiles / "
                "--list-providers / --test-provider)")
    return _cli_run(args)


if __name__ == "__main__":
    sys.exit(main())
