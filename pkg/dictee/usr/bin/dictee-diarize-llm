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
You summarise a diarized meeting or interview transcript. You are not a conversational assistant.
</role>
<instructions>
From the transcript below (labels like [Speaker N] mark speakers), produce a structured Markdown report.

CRITICAL — Output language: write the entire report in the **same language as the transcript** (English transcript → English report; French → French; German → German; etc.). This applies to the section headings and to any literal placeholder like "_None_" / "_Aucun_" / "_Keine_".

Sections (translate each heading into the transcript's language):

## Summary
3-5 sentences summarising the exchange.

## Decisions
Explicit decisions made during the exchange.

## Action items
Format: "- [Speaker]: action (deadline if mentioned)".

## Open questions
Issues raised without resolution.

Strict rules:
- Absolute fidelity: do not invent, do not infer what is not said.
- If a section is empty, write "_None_" (in the transcript's language).
- Cite speakers by their exact label ([Speaker N], or the renamed label if any).
- Do NOT reproduce the transcript, only the synthesis.
- No preamble, no added conclusion.
</instructions>
<input>
{TRANSCRIPT}
</input>
"""

PROMPT_CHAPITRAGE = """\
<role>
You identify topic shifts in a diarized transcript and produce a navigable table of contents.
</role>
<instructions>
Split the transcript below into thematic chapters. Strict output format:

[HH:MM:SS] Short title (3-7 words)

CRITICAL — Output language: write each chapter title in the **same language as the transcript** (English transcript → English titles; French → French; etc.). Never translate.

Rules:
- New chapter only when the topic actually changes (not at every speaker turn).
- Target: 1 chapter every 2-5 minutes.
- Descriptive, neutral titles (e.g., "Q3 Roadmap", not "Discussion about the roadmap").
- Use the timestamps present in the transcript.
- Output ONLY the list, nothing else.
</instructions>
<input>
{TRANSCRIPT}
</input>
"""

PROMPT_CORRECTION_ASR = """\
<role>
Speech-recognition (ASR) error corrector. You are not a conversational assistant.
</role>
<instructions>
Fix ONLY the likely recognition errors in the segment below (output of a Parakeet ASR).

CRITICAL — Output language: reply in the **same language as the input segment**. Never translate.

DO:
- Correct homophones, misrecognised words, mangled proper nouns.
- Prefer terms from the user dictionary (when one is provided) in case of phonetic doubt.
- Preserve verbatim: correct punctuation, casing, hesitations ("uh", "um", "euh", "hum"…).

DO NOT:
- Rephrase, summarise, or complete an interrupted sentence.
- Modify correct punctuation.
- Add content not present in the segment.
- Comment, introduce, or explain.

If nothing needs correcting, return the segment unchanged, with no comment.

Context (previous segment, for coherence — DO NOT return it):
{PREVIOUS_SEGMENT}

User dictionary:
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

# No built-in providers anymore — the previous "Ollama (local)" entry was
# read-only and prevented users from setting an API key (needed for Ollama
# Cloud). Users now create their own providers from presets in the UI
# (Ollama local/cloud, LM Studio, Jan, vLLM, OpenAI, Anthropic, Groq…).
BUILTIN_PROVIDERS = []


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


class CancelledError(ProviderError):
    """Raised when the caller aborts the request mid-stream."""


class Cancellation:
    """Cooperative cancellation token for a single LLM call.

    The UI (LLMAnalysisThread) creates one and passes it down; if the
    user clicks the X on the result tab, `abort()` flips the flag and
    closes the live HTTP response so the streaming `for line in resp`
    loop in the provider call exits immediately. Without this the
    response would keep streaming in the background, burning cloud
    tokens (OpenAI / Anthropic / Groq) and pinning the GPU on Ollama.
    """
    def __init__(self):
        self.cancelled = False
        self.response = None

    def abort(self):
        self.cancelled = True
        r = self.response
        if r is not None:
            try:
                r.close()
            except Exception:
                pass

    def check(self):
        if self.cancelled:
            raise CancelledError("cancelled")


_NULL_CANCELLATION = Cancellation()  # for callers that don't pass one


_DEFAULT_USER_AGENT = "dictee/1.3 (+https://github.com/rcspam/dictee)"


def _open_stream(url, payload, headers, timeout, cancellation):
    """POST JSON, return the raw HTTPResponse for streaming. The
    response is registered on the cancellation token so an external
    abort() can close it. Caller is responsible for closing it after
    consumption."""
    data = json.dumps(payload).encode("utf-8")
    headers = dict(headers)
    headers.setdefault("User-Agent", _DEFAULT_USER_AGENT)
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise ProviderError(f"HTTP {e.code} {e.reason}: {body[:300]}") from e
    except urllib.error.URLError as e:
        raise ProviderError(f"Network error: {e.reason}") from e
    except (TimeoutError, socket.timeout) as e:
        raise ProviderError(f"Timeout after {timeout}s") from e
    except (OSError, ValueError) as e:
        raise ProviderError(f"{type(e).__name__}: {e}") from e
    cancellation.response = resp
    return resp


def _http_post_json(url, payload, headers, timeout):
    """POST JSON payload, return parsed JSON response."""
    data = json.dumps(payload).encode("utf-8")
    headers = dict(headers)
    headers.setdefault("User-Agent", _DEFAULT_USER_AGENT)
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
    headers = dict(headers)
    headers.setdefault("User-Agent", _DEFAULT_USER_AGENT)
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


def _ollama_headers(cfg):
    """Build headers for Ollama. Cloud needs `Authorization: Bearer
    <api_key>` (same header Ollama's own CLI uses against ollama.com).
    Local Ollama instances ignore it. Without this, Cloud returned
    401/empty responses while curl-from-terminal worked because the
    user had `~/.ollama/id_ed25519` configured."""
    h = {"Content-Type": "application/json"}
    if cfg.get("api_key"):
        h["Authorization"] = f"Bearer {cfg['api_key']}"
    return h


def _provider_call_ollama(cfg, model, system, prompt, timeout,
                          cancellation=_NULL_CANCELLATION):
    url = cfg["url"].rstrip("/") + "/api/generate"
    # Ollama defaults `num_ctx` to 2048 tokens. A 30-min transcript is
    # ~10-15 k tokens, so without raising the context window the model
    # only sees the first ~3 minutes and hallucinates the rest.
    options = {"num_ctx": int(cfg.get("num_ctx", 16384))}
    if isinstance(cfg.get("options"), dict):
        options.update(cfg["options"])
    payload = {
        "model": model,
        "prompt": prompt,
        # Streaming so we can interrupt mid-generation when the user
        # closes the result tab — without it the model keeps generating
        # in background, pinning GPU/CPU for nothing.
        "stream": True,
        "options": options,
        "think": bool(cfg.get("think", False)),
    }
    if system:
        payload["system"] = system
    resp = _open_stream(url, payload, _ollama_headers(cfg), timeout, cancellation)
    chunks = []
    try:
        for line in resp:
            cancellation.check()
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            piece = obj.get("response", "")
            if piece:
                chunks.append(piece)
            if obj.get("done"):
                break
    finally:
        try:
            resp.close()
        except Exception:
            pass
    return "".join(chunks).strip()


def _provider_list_models_ollama(cfg, timeout=10):
    url = cfg["url"].rstrip("/") + "/api/tags"
    data = _http_get_json(url, _ollama_headers(cfg), timeout)
    return [m.get("name", "") for m in data.get("models", []) if m.get("name")]


def _provider_call_openai(cfg, model, system, prompt, timeout,
                          cancellation=_NULL_CANCELLATION):
    url = cfg["url"].rstrip("/") + "/chat/completions"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {"model": model, "messages": messages, "stream": True}
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg.get('api_key', '')}",
    }
    resp = _open_stream(url, payload, headers, timeout, cancellation)
    chunks = []
    try:
        for line in resp:
            cancellation.check()
            line = line.strip()
            if not line.startswith(b"data: "):
                continue
            data = line[6:]
            if data == b"[DONE]":
                break
            try:
                obj = json.loads(data)
            except ValueError:
                continue
            choices = obj.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            piece = delta.get("content") or ""
            if piece:
                chunks.append(piece)
    finally:
        try:
            resp.close()
        except Exception:
            pass
    if not chunks:
        raise ProviderError("Empty stream response")
    return "".join(chunks).strip()


def _provider_list_models_openai(cfg, timeout=10):
    url = cfg["url"].rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {cfg.get('api_key', '')}"}
    data = _http_get_json(url, headers, timeout)
    return [m.get("id", "") for m in data.get("data", []) if m.get("id")]


def _provider_call_anthropic(cfg, model, system, prompt, timeout,
                             cancellation=_NULL_CANCELLATION):
    url = cfg["url"].rstrip("/") + "/v1/messages"
    payload = {
        "model": model,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
    }
    if system:
        payload["system"] = system
    headers = {
        "Content-Type": "application/json",
        "x-api-key": cfg.get("api_key", ""),
        "anthropic-version": "2023-06-01",
    }
    resp = _open_stream(url, payload, headers, timeout, cancellation)
    chunks = []
    try:
        for line in resp:
            cancellation.check()
            line = line.strip()
            if not line.startswith(b"data: "):
                continue
            data = line[6:]
            try:
                obj = json.loads(data)
            except ValueError:
                continue
            etype = obj.get("type")
            if etype == "content_block_delta":
                delta = obj.get("delta") or {}
                piece = delta.get("text") or ""
                if piece:
                    chunks.append(piece)
            elif etype == "message_stop":
                break
            elif etype == "error":
                raise ProviderError(
                    f"Anthropic error: {obj.get('error', {}).get('message')}")
    finally:
        try:
            resp.close()
        except Exception:
            pass
    return "".join(chunks).strip()


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
                  timeout=DEFAULT_TIMEOUT,
                  cancellation=_NULL_CANCELLATION):
    """Dispatch a generation call to the right provider type.

    provider_cfg: provider dict from llm-providers.json (or built-in).
    cancellation: optional Cancellation token; abort() on it closes
    the live HTTP response and the streaming loop returns immediately.
    Returns the generated text (string), or raises ProviderError /
    CancelledError.
    """
    ptype = provider_cfg.get("type")
    if ptype not in PROVIDER_DISPATCH:
        raise ProviderError(f"Unknown provider type: {ptype!r}")
    call_fn, _ = PROVIDER_DISPATCH[ptype]
    return call_fn(provider_cfg, model, system, prompt, timeout, cancellation)


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
    """Return list of profiles: built-ins (with user overrides applied)
    + user-defined.

    Built-in profiles can have their default_provider_id / default_model
    overridden in `~/.config/dictee/llm-profiles.json` under the
    `builtin_overrides` key. The prompt / mode / name stay frozen.
    """
    user_profiles = []
    builtin_overrides = {}
    if os.path.isfile(PROFILES_PATH):
        try:
            with open(PROFILES_PATH, encoding="utf-8") as f:
                data = json.load(f)
            user_profiles = [p for p in data.get("profiles", [])
                             if not p.get("builtin")]
            builtin_overrides = data.get("builtin_overrides", {}) or {}
        except (OSError, ValueError) as e:
            print(f"[dictee-diarize-llm] Warning: failed to read "
                  f"{PROFILES_PATH}: {e}", file=sys.stderr)
    builtins = []
    for b in BUILTIN_PROFILES:
        b_copy = dict(b)
        ov = builtin_overrides.get(b["id"])
        if isinstance(ov, dict):
            if ov.get("default_provider_id"):
                b_copy["default_provider_id"] = ov["default_provider_id"]
            if ov.get("default_model"):
                b_copy["default_model"] = ov["default_model"]
        builtins.append(b_copy)
    return builtins + user_profiles


def save_profiles(profiles):
    """Persist user-defined profiles + builtin overrides.

    For built-in profiles, only the deltas in default_provider_id and
    default_model vs. the original BUILTIN_PROFILES are stored, in the
    `builtin_overrides` field. The frozen fields (name/mode/prompt)
    are never persisted because they cannot diverge from the source.
    """
    user = []
    builtin_overrides = {}
    for p in profiles:
        if p.get("builtin"):
            orig = next((b for b in BUILTIN_PROFILES if b["id"] == p["id"]),
                        None)
            if orig is None:
                continue
            ov = {}
            if (p.get("default_provider_id")
                    and p["default_provider_id"] != orig.get("default_provider_id")):
                ov["default_provider_id"] = p["default_provider_id"]
            if (p.get("default_model")
                    and p["default_model"] != orig.get("default_model")):
                ov["default_model"] = p["default_model"]
            if ov:
                builtin_overrides[p["id"]] = ov
        else:
            user.append(p)
    payload = {"profiles": user}
    if builtin_overrides:
        payload["builtin_overrides"] = builtin_overrides
    _atomic_write_json(PROFILES_PATH, payload)


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


def _lang_system_prompt(lang_name):
    """Build a strict 'output language' system prompt.

    The built-in prompts already ask the LLM to reply in the
    transcript's language, but in practice many models drift to
    English regardless. A system-level instruction is much more
    reliable. Returns None when no language is requested so call
    sites stay backward-compatible.
    """
    if not lang_name:
        return None
    return (
        f"You MUST write the entire response in {lang_name}. "
        f"Never reply in another language, even if the prompt is "
        f"in English or contains English instructions. All headings, "
        f"bullets, placeholders and content must be in {lang_name}."
    )


def _lang_user_suffix(lang_name):
    """Trailing reinforcement for the user prompt.

    Empirically, the system prompt alone is not enough on some models
    (Groq gpt-oss, smaller open models) when the transcript itself is
    in English — they follow the content's language and ignore the
    system instruction. A short directive at the very end of the user
    prompt — the last thing the model reads before generating — fixes
    it reliably.

    Earlier versions used a longer, decorated form (with `---` and
    `IMPORTANT:`); on Gemma 3 4B the decorations triggered a token
    glitch (`<unused1630>`) and the model echoed the directive back
    instead of following it. The terse bracket form is invisible to
    the model's structure parser and behaves as a pure instruction.
    """
    if not lang_name:
        return ""
    return f"\n\n[Reply in {lang_name} only.]"


def analyze_global(segments, profile, provider_cfg, model, dictionary="",
                   timeout=DEFAULT_TIMEOUT, lang_name="",
                   cancellation=_NULL_CANCELLATION):
    """Run a global-mode profile (Synthèse, Chapitrage, custom)."""
    transcript = format_segments_for_prompt(segments)
    prompt = _render_prompt(profile["prompt"], transcript,
                            dictionary=dictionary)
    prompt += _lang_user_suffix(lang_name)
    return call_provider(provider_cfg, model, prompt,
                         system=_lang_system_prompt(lang_name),
                         timeout=timeout, cancellation=cancellation)


def analyze_per_segment(segments, profile, provider_cfg, model,
                        dictionary="", timeout=DEFAULT_TIMEOUT,
                        progress_cb=None, lang_name="",
                        cancellation=_NULL_CANCELLATION):
    """Run a per-segment-mode profile (Correction ASR).

    Cancelling between two segments stops the loop immediately;
    cancelling during a segment's HTTP stream closes that response so
    we don't waste tokens on the rest of the transcript.
    """
    out_lines = []
    previous = ""
    total = len(segments)
    for idx, seg in enumerate(segments):
        cancellation.check()
        if progress_cb is not None:
            progress_cb(idx, total)
        prompt = _render_prompt(profile["prompt"], seg["text"],
                                previous_segment=previous,
                                dictionary=dictionary)
        prompt += _lang_user_suffix(lang_name)
        try:
            corrected = call_provider(provider_cfg, model, prompt,
                                      system=_lang_system_prompt(lang_name),
                                      timeout=timeout,
                                      cancellation=cancellation).strip()
            if not corrected:
                corrected = seg["text"]
        except CancelledError:
            raise
        except ProviderError as e:
            print(f"[dictee-diarize-llm] Segment {idx + 1}/{total} failed: "
                  f"{e} — keeping original.", file=sys.stderr)
            corrected = seg["text"]
        out_lines.append(
            f"[{seg['start']:.2f}s - {seg['end']:.2f}s] "
            f"{seg['speaker']}: {corrected}"
        )
        previous = corrected
    if progress_cb is not None:
        progress_cb(total, total)
    return "\n".join(out_lines)


def analyze(segments, profile, provider_cfg, model=None, dictionary="",
            timeout=DEFAULT_TIMEOUT, progress_cb=None, lang_name="",
            cancellation=_NULL_CANCELLATION):
    """Top-level entry point. Routes to global or per-segment based on
    the profile's mode.

    cancellation: optional Cancellation token. When abort()-ed by the
    UI thread, the current HTTP stream is closed and CancelledError
    bubbles up — no more wasted tokens / GPU cycles after the user
    closes the result tab.
    """
    effective_model = model or profile.get("default_model")
    if not effective_model:
        raise ProviderError(
            f"No model specified (profile={profile['id']!r} has no default)")
    mode = profile.get("mode", "global")
    if mode == "per-segment":
        return analyze_per_segment(segments, profile, provider_cfg,
                                   effective_model, dictionary=dictionary,
                                   timeout=timeout, progress_cb=progress_cb,
                                   lang_name=lang_name,
                                   cancellation=cancellation)
    return analyze_global(segments, profile, provider_cfg, effective_model,
                          dictionary=dictionary, timeout=timeout,
                          lang_name=lang_name, cancellation=cancellation)


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
