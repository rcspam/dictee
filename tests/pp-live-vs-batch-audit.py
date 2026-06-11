#!/usr/bin/env python3
"""Differential audit: streaming-live PP vs batch PP.

For each corpus utterance and several fragmentations, the FINAL text typed
by the live path (LiveComposer + Typist + end-of-push fixup) must equal the
batch pipeline output (run_pipeline local subset is shared; short_text is
applied at end in both; LLM and bad-language rejection are out of scope).
Run on the developer machine with the real user conf (results depend on
rules.conf/dictionary.conf): diagnostic tool, not a CI test.
"""
import importlib.machinery as m
import os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ds = m.SourceFileLoader("ds", os.path.join(ROOT, "dictee-stream")).load_module()
pp = m.SourceFileLoader("pp", os.path.join(ROOT, "dictee-postprocess.py")).load_module()


def batch_final(text):
    out = pp.run_pipeline(text, local_only=False)
    return ds.Typist.sanitize(out)


def live_final(text, frags, promote_between=False):
    closed = {w.lower() for w in pp.load_continuation()}
    c = ds.LiveComposer(lambda t: pp.run_pipeline(t, local_only=True),
                        closed_words=closed,
                        fr_typography=pp._env_bool("DICTEE_PP_TYPOGRAPHY"))
    t = ds.Typist(dry_run=True)
    for i, frag in enumerate(frags):
        tgt = c.feed(frag)
        if tgt:
            t.rewrite(tgt)
        if promote_between and i < len(frags) - 1:
            c.promote()
            tgt = c.target()
            if tgt:
                t.rewrite(tgt)
    c._kw_active = False
    tgt = c.target()
    if tgt:
        t.rewrite(tgt)
    # end-of-push short_text fixup (mirror of _main, final_pass off)
    if t.typed.strip() and pp._env_bool("DICTEE_PP_SHORT_TEXT"):
        _kc_on = pp._env_bool("DICTEE_PP_KEEPCAPS")
        _kc = pp.load_keepcaps() if _kc_on else None
        _ext = pp._env_bool("DICTEE_PP_KEEPCAPS_EXTENDED") if _kc_on else False
        fixed = pp.fix_short_text(t.typed, keepcaps=_kc, extended=_ext)
        fixed = ds._with_lead_of(t.typed, t.sanitize(fixed))
        if fixed != t.typed:
            t.rewrite(fixed)
    return t.typed


def fragmentations(text):
    """ASR-like fragmentations of ' '+text (leading SentencePiece space)."""
    full = " " + text
    yield "entier", [full]
    words = full.split(" ")
    yield "par-mot", [" " + w for w in words if w]
    # pairs of words
    ws = [w for w in words if w]
    yield "par-2-mots", [" " + " ".join(ws[i:i+2]) for i in range(0, len(ws), 2)]
    # fixed-size chunks (mid-word splits, like 560ms chunks)
    n = 7
    yield "tranches-7c", [full[i:i+n] for i in range(0, len(full), n)]


CORPUS = [
    # — commandes vocales (rules) —
    "bonjour tout le monde point final",
    "bonjour virgule la suite arrive",
    "premier point à la ligne deuxième",
    "le texte tabulation la suite",
    "avant contrôle j après",
    "vraiment point d'interrogation",
    "attention point d'exclamation",
    "les courses deux points final pommes",
    "primo point virgule secundo",
    # — hésitations / dedup (rules) —
    "euh bonjour le monde",
    "le le chat dort",
    # — élisions fr —
    "je ai très faim aujourd'hui",
    "il ne est pas venu ce matin",
    # — nombres —
    "il est vingt-trois heures quinze",
    "rendez-vous le trois janvier prochain",
    "cela coûte cent cinquante euros",
    # — capitalisation multi-phrases —
    "première phrase. deuxième phrase. troisième",
    # — typographie fr (ponctuation haute) —
    "tu viens demain ? oui bien sûr !",
    # — continuation intra (mot-outil + point parasite) —
    "je vais le. faire demain",
    # — courts (short_text) —
    "une cuisine",
    "d'accord",
    "oui",
    # — mixte —
    "euh je ai vingt-trois ans virgule et toi point d'interrogation",
    # — dictionnaire perso (entrées [*] api/url) —
    "regarde la api de ce site",
    "ouvre la url dans le navigateur",
    # — commande reset-contexte (\x04) en tête —
    "nouvelle phrase on repart",
    # — guillemets / ponctuation haute en chaîne —
    "il a dit deux points magnifique point d'exclamation",
]

os.environ.setdefault("DICTEE_LANG_SOURCE", "fr")
fails = 0
for text in CORPUS:
    ref = batch_final(text)
    seen = {}
    for name, frags in fragmentations(text):
        got = live_final(text, list(frags))
        seen[name] = got
    # Passe pause (INFORMATIVE) : promote entre chaque fragment. Le gel par
    # pause fige le texte affiché ; une unité multi-mots coupée par une
    # pause de 700 ms (nombre, élision, commande en 2 mots) ne peut plus
    # être fusionnée — tradeoff assumé du mode live, pas un échec.
    frags2 = [" " + " ".join(text.split()[i:i+2]) for i in range(0, len(text.split()), 2)]
    pause_out = live_final(text, frags2, promote_between=True)
    # invariant 1: toutes les fragmentations donnent le même résultat
    uniq = set(seen.values())
    # invariant 2: égal au batch
    ok = len(uniq) == 1 and next(iter(uniq)) == ref
    if not ok:
        fails += 1
        print(f"✗ {text!r}")
        print(f"   batch        : {ref!r}")
        for name, got in seen.items():
            mark = " " if got == ref else "≠"
            print(f"   live {name:12}{mark}: {got!r}")
    elif pause_out != ref:
        print(f"ℹ pause-split divergence (tradeoff connu): {text!r}")
        print(f"   batch : {ref!r}\n   pause : {pause_out!r}")
print()
print(f"{'AUDIT VERT' if fails == 0 else f'{fails} écarts'} / {len(CORPUS)} énoncés")
