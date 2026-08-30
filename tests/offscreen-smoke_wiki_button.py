"""Headless smoke test for the Documentation button in dictee-setup.

Builds the sidebar dialog offscreen, walks every tree entry and checks
the wiki URL the button resolves to: one slug per section, the five
post-processing tabs, and the French prefix.
"""
import importlib.util
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

spec = importlib.util.spec_from_file_location(
    "dictee_setup", os.path.join(HERE, "dictee-setup.py"))
mod = importlib.util.module_from_spec(spec)
sys.modules["dictee_setup"] = mod
spec.loader.exec_module(mod)

from PyQt6.QtWidgets import QApplication, QPushButton

app = QApplication([])

# 1. Language prefix
for env, want in (("fr_FR.UTF-8", "fr-"), ("en_US.UTF-8", ""),
                  ("de_DE.UTF-8", ""), ("", "")):
    saved = {k: os.environ.get(k) for k in
             ("LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG")}
    for k in saved:
        os.environ.pop(k, None)
    if env:
        os.environ["LANG"] = env
    got = mod._wiki_lang_prefix()
    assert got == want, f"prefix for {env!r}: got {got!r}, want {want!r}"
    for k, v in saved.items():
        if v is not None:
            os.environ[k] = v
print("1. _wiki_lang_prefix OK")

# Force English for the URL checks below.
for _k in ("LANGUAGE", "LC_ALL", "LC_MESSAGES"):
    os.environ.pop(_k, None)
os.environ["LANG"] = "en_US.UTF-8"

dlg = mod.DicteeSetupDialog()
assert not dlg.wizard_mode, (
    "test needs the sidebar UI; wizard_mode kicks in when dictee.conf is "
    "missing or DICTEE_SETUP_DONE is not true")

# 2. The button exists, is centred in the bottom bar, and is unique
buttons = [b for b in dlg.findChildren(QPushButton)
           if b.text() == mod._("Documentation")]
assert len(buttons) == 1, f"expected 1 Documentation button, got {len(buttons)}"
print("2. button present and unique OK")

# 3. Every stack index resolves to a real slug
dlg._ensure_pp_built()
seen = {}
for idx in range(dlg._sidebar_stack.count()):
    dlg._sidebar_stack.setCurrentIndex(idx)
    url = dlg._wiki_url_for_current_page()
    assert url.startswith(mod.WIKI_BASE + "/"), f"index {idx}: {url}"
    seen[idx] = url.rsplit("/", 1)[-1]
    assert seen[idx], f"index {idx} resolved to an empty slug"
assert dlg._sidebar_stack.count() == len(mod.WIKI_PAGE_SLUGS), (
    f"stack has {dlg._sidebar_stack.count()} pages but WIKI_PAGE_SLUGS "
    f"maps {len(mod.WIKI_PAGE_SLUGS)}")
print(f"3. {len(seen)} stack pages -> slugs OK")

# 4. Spot-check the sections this feature was asked for
assert seen[0] == "Home", seen[0]
assert seen[9] == "LLM-Diarization", seen[9]
assert seen[3] == "Keyboard-Shortcuts", seen[3]
print("4. welcome / LLM / shortcuts slugs OK")

# 5. Post-processing follows its active tab
dlg._sidebar_stack.setCurrentIndex(8)
for tab, want in mod.WIKI_PP_TAB_SLUGS.items():
    dlg._pp_tabs.setCurrentIndex(tab)
    got = dlg._wiki_url_for_current_page().rsplit("/", 1)[-1]
    assert got == want, f"PP tab {tab}: got {got}, want {want}"
print(f"5. {len(mod.WIKI_PP_TAB_SLUGS)} post-processing tabs OK")

# 6. French prefix reaches the URL
os.environ["LANG"] = "fr_FR.UTF-8"
dlg._sidebar_stack.setCurrentIndex(9)
url = dlg._wiki_url_for_current_page()
assert url == mod.WIKI_BASE + "/fr-LLM-Diarization", url
print("6. french URL OK")

# 7. Unknown index falls back to the wiki root
dlg._sidebar_stack.setCurrentIndex(0)
saved_map = dict(mod.WIKI_PAGE_SLUGS)
mod.WIKI_PAGE_SLUGS.clear()
assert dlg._wiki_url_for_current_page() == mod.WIKI_BASE
mod.WIKI_PAGE_SLUGS.update(saved_map)
print("7. fallback to wiki root OK")

print("\nALL OK")
