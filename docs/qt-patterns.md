# Qt/PyQt6 Patterns réutilisables — dictee

Référence des classes et patterns Qt custom utilisés dans le projet.
Consulter avant de réinventer.

## 1. _ResizableFrame — Widget resizable par l'utilisateur (resize: both)

**Fichier** : `dictee-setup.py` (avant `DicteeSetupDialog`)

**Usage** :
```python
editor = QTextEdit()
frame = _ResizableFrame(editor, min_w=200, min_h=80, init_w=800, init_h=250)
layout.addWidget(frame)
```

**Principe** : QFrame avec `QSizePolicy.Fixed` + override `sizeHint()` retournant un `_target_size` mutable. Le `_GripHandle` (triangle 16x16 en bas à droite) modifie `_target_size` via `set_target_size()` qui appelle `updateGeometry()` + `resize()`. Auto-scroll via `ensureWidgetVisible()`.

**Pourquoi** : `resize()` seul est écrasé par le layout. `setFixedSize()` empêche de réduire. Seul l'override de `sizeHint()` force le layout à respecter la taille dans les 4 directions.

---

## 2. _CheckMarkComboBox — QComboBox avec texte coloré à l'état fermé

**Fichier** : `dictee-setup.py`

**Principe** : `setItemData(idx, QColor, ForegroundRole)` ne colore que le dropdown. Pour le combo fermé : override `paintEvent` avec `QStylePainter` + `QStyleOptionComboBox`.

---

## 3. _add_zoom_overlay — Boutons zoom flottants sur QTextEdit

**Fichier** : `dictee-setup.py` (méthode statique de `DicteeSetupDialog`)

**Usage** :
```python
self._add_zoom_overlay(my_text_edit)
```

**Principe** : QPushButton "−" et "+" positionnés en overlay (top-right) via `resizeEvent` override. Raccourcis Ctrl++/Ctrl+−.

---

## 4. _RulesHighlighter — Coloration syntaxique rules.conf

**Fichier** : `dictee-setup.py`

**Principe** : QSyntaxHighlighter custom pour le format `[lang] pattern → replacement // flags`.

---

## 5. Ollama HTTP API — appel avec system prompt séparé

**Fichier** : `dictee-postprocess.py` (`llm_postprocess()`)

**Usage** :
```python
payload = json.dumps({
    "model": model,
    "system": system_prompt,   # prompt système séparé
    "prompt": text,             # texte utilisateur
    "stream": False,
}).encode("utf-8")
req = urllib.request.Request(
    "http://localhost:11434/api/generate",
    data=payload,
    headers={"Content-Type": "application/json"})
resp = urllib.request.urlopen(req, timeout=timeout)
data = json.loads(resp.read().decode("utf-8"))
result = data.get("response", "").strip()
```

**Note** : `ollama run` CLI ne supporte PAS `--system`. Seule l'API HTTP `/api/generate` a le paramètre `system`.

---

## 6. _freeze_pp / _unfreeze_pp — Anti-artefacts repaint pour layouts complexes

**Fichier** : `dictee-setup.py` (méthodes de `DicteeSetupDialog`)

**Usage** :
```python
self._freeze_pp()
# ... changements de visibilité, taille, contenu ...
self._unfreeze_pp(delay=15)  # ms avant repaint
```

**Principe** : Quand un widget change de taille ou de visibilité dans un layout complexe (QScrollArea + QTabWidget + contraintes de hauteur), Qt peint un frame intermédiaire avec des tailles incorrectes avant que le layout se stabilise. Cela crée des "fantômes" visuels pendant ~16ms.

`_freeze_pp()` appelle `setUpdatesEnabled(False)` sur le QScrollArea parent, bloquant tout repaint. Le layout se recalcule en arrière-plan sans rien afficher. `_unfreeze_pp(delay)` réactive les repaints après `delay` ms via `QTimer.singleShot`, le temps que le layout se stabilise.

**Quand l'utiliser** : Tout changement dans la zone test PP qui modifie la géométrie — ouverture/fermeture d'accordéon, affichage/masquage des détails, changement de taille input/output, exécution du pipeline test (mise à jour output + détails).

**Piège** : Le délai doit être suffisant pour que le layout se stabilise (10-20ms typiquement). Trop court = artefact résiduel. Pas besoin de plus de 30ms.
