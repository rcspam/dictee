# Plan B — Cheatsheet UI flottant + packaging

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Spec de référence :** `docs/superpowers/specs/2026-04-25-voice-commands-cheatsheet-design.md`. Toutes les sections numérotées (§N) renvoient à ce document. **Relire le spec entre tâches** pour les détails de code.
>
> **Prérequis recommandé :** Plan A (page wiki Voice-Commands) shippé d'abord.

**Goal:** Implémenter le script `dictee-cheatsheet` (carte flottante PyQt6 montrant les commandes vocales pendant la dictée), l'intégrer aux 4 triggers (plasmoid, tray, raccourci global, auto-show 1ère install), et l'ajouter aux 3 formats de packaging (deb, rpm, PKGBUILD).

**Architecture:** Script Python autonome avec PyQt6, singleton via QLocalServer, fenêtre frameless toujours-au-dessus, contenu hardcodé `COMMAND_TABLE` + valeurs dynamiques (SUFFIX, mot continuation) avec `QFileSystemWatcher` live update. Persistance via QSettings.

**Tech Stack:** Python 3, PyQt6 (déjà dans deps), QLocalServer/Socket pour IPC, QFileSystemWatcher, QSettings. KDE kglobalaccel via D-Bus pour le raccourci global.

---

## File Structure

| Fichier | Type | Rôle |
|---|---|---|
| `dictee-cheatsheet` | **création** | Script Python (~250 lignes) |
| `dictee-tray.py` | modif | Entrée menu + auto-show 1ère install |
| `plasmoid/package/contents/ui/FullRepresentation.qml` | modif | Bouton ToolButton |
| `plasmoid/package/contents/ui/main.qml` | modif | Switch case |
| `dictee-setup.py` | modif | Onglet Raccourcis : nouveau champ |
| `build-deb.sh` | modif | Install dans .deb (cpu + cuda) |
| `build-rpm.sh` | modif | Install dans .rpm (cpu + cuda) |
| `PKGBUILD` | modif | Install dans Arch package |

---

## Task 1: Skeleton — singleton + fenêtre vide + IPC

**Files:**
- Create: `dictee-cheatsheet`

- [ ] **Step 1: Créer le script avec entête + parsing args + singleton**

Voir spec §2 « Architecture globale » et §3 « Structure interne du script ». Le squelette doit :
- Parser `--toggle`, `--close`, `--first-run`, défaut `open`
- Tenter une connexion `QLocalSocket` au server `dictee-cheatsheet-${UID}`
- Si une instance existe → écrire la commande au socket et sortir
- Sinon → créer le `QLocalServer`, instancier la fenêtre vide (`Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool`), afficher
- Listener IPC : sur `newConnection` → lire la commande → toggle/close/open/first-run

- [ ] **Step 2: Rendre le script exécutable**

```bash
chmod +x /home/rapha/SOURCES/RAPHA_STT/dictee/dictee-cheatsheet
```

- [ ] **Step 3: Test manuel**

```bash
/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-cheatsheet &
```

Expected : petite fenêtre frameless apparaît, reste au-dessus.

```bash
/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-cheatsheet --toggle
```

Expected : la fenêtre se ferme. Re-toggle → réapparaît.

```bash
pkill -f dictee-cheatsheet
```

- [ ] **Step 4: Commit**

```bash
git add dictee-cheatsheet
git commit -m "feat(cheatsheet): skeleton — frameless window + IPC singleton"
```

---

## Task 2: COMMAND_TABLE pour les 7 langues

**Files:**
- Modify: `dictee-cheatsheet`

- [ ] **Step 1: Constantes globales**

Ajouter au top du module :
- `CATEGORY_ORDER` : 7 catégories ordonnées (`continuation_reset`, `sauts_de_ligne`, `ponctuation`, `brackets`, `markdown`, `caracteres_speciaux`, `hotkeys`)
- `DEFAULT_EXPANDED` : set des 4 premières
- `CATEGORY_LABELS` : dict langue → catégorie → label localisé
- `TITLE_BY_LANG` : dict langue → titre fenêtre
- `COMMAND_TABLE` : dict langue → catégorie → liste de tuples `(template_command, result_label)`

Templates : `{cont}` (mot continuation), `{suffix}` (SUFFIX_<LANG>). Voir spec §3 et la page wiki Voice-Commands (Plan A) pour le contenu exact.

- [ ] **Step 2: Vérification syntaxique**

```bash
python3 -c "import ast; ast.parse(open('/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-cheatsheet').read()); print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add dictee-cheatsheet
git commit -m "feat(cheatsheet): COMMAND_TABLE for 7 languages × 7 categories"
```

---

## Task 3: Header avec drag + boutons

**Files:**
- Modify: `dictee-cheatsheet`

- [ ] **Step 1: Refactorer `__init__` avec un header**

`QHBoxLayout` contenant :
- Label titre (« 🎤 Commandes vocales (FR) »)
- Bouton `−` (zoom out, connecté en Task 7)
- Bouton `+` (zoom in, connecté en Task 7)
- Bouton `×` (close, connecté à `self.hide`)

Le tout dans un `QVBoxLayout` racine (header / body / footer).

- [ ] **Step 2: Events drag**

`mousePressEvent` : démarre le drag si bouton gauche ET clic non sur bouton/titre catégorie.
`mouseMoveEvent` : applique le delta de position.
`mouseReleaseEvent` : reset le drag state.

Voir spec §7 « Drag » pour le code complet.

- [ ] **Step 3: Stylesheet sombre semi-transparent**

`_apply_stylesheet()` : fond sombre `rgba(28, 30, 35, 235)`, border-radius 8px, header plus clair, hover sur boutons. Voir spec §7 « Apparence générale ».

- [ ] **Step 4: Test manuel**

Drag depuis le fond → fenêtre suit. Click × → ferme.

- [ ] **Step 5: Commit**

```bash
git add dictee-cheatsheet
git commit -m "feat(cheatsheet): header with drag + close button"
```

---

## Task 4: Rendu des catégories avec expand/collapse

**Files:**
- Modify: `dictee-cheatsheet`

- [ ] **Step 1: Ajouter `_render_body()`**

Pour chaque catégorie de `CATEGORY_ORDER` :
- Bouton titre cliquable (couleur accent bleu `#8ec5ff`, sans border)
- Si dépliée : `QGridLayout` 2 colonnes (commande | résultat), spacing 4×8px
- Si repliée : juste le titre

Click sur titre → toggle `self._cat_state[cat]` + re-render.

Lang temporairement hardcoded à `"fr"`, cont_word à `"minuscule"`, suffix à `"final"` — remplacés en Task 5.

- [ ] **Step 2: Style commande/résultat**

`#cmd` : opacité 0.85
`#result` : monospace, opacité 0.5

- [ ] **Step 3: Test manuel**

7 titres visibles. 4 dépliées avec leurs commandes, 3 repliées. Click toggle.

- [ ] **Step 4: Commit**

```bash
git add dictee-cheatsheet
git commit -m "feat(cheatsheet): render categories with expand/collapse"
```

---

## Task 5: Lecture configs + résolution dynamique des templates

**Files:**
- Modify: `dictee-cheatsheet`

- [ ] **Step 1: Helper functions au top du module**

- `_read_kv_file(path)` : parse fichier `KEY=VALUE` en dict, ignore lignes vides et commentaires
- `_detect_lang()` : lit `DICTEE_LANG_SOURCE` depuis `~/.config/dictee.conf`, fallback locale système, fallback `"en"`
- `_read_suffix(lang)` : lit `SUFFIX_<LANG>` depuis dictee.conf, fallback hardcoded (fr=`final`, en=`stop`, de=`Ende`, es=`final`, it=`finale`, pt=`final`)
- `_read_continuation_word(lang)` : lit `CONTINUATION_WORDS_<LANG>` depuis `~/.config/dictee/continuation.conf`, prend le premier alias

- [ ] **Step 2: Modifier `_render_body` pour utiliser les valeurs lues**

Remplacer les hardcoded `lang`, `cont_word`, `suffix` par les appels aux helpers. Update aussi le titre de la fenêtre via `self._title.setText(...)` avec `TITLE_BY_LANG[lang]`.

- [ ] **Step 3: Test manuel**

Avec config FR : titre « Commandes vocales (FR) ». Commandes affichées avec le bon SUFFIX.

- [ ] **Step 4: Commit**

```bash
git add dictee-cheatsheet
git commit -m "feat(cheatsheet): read DICTEE_LANG_SOURCE + SUFFIX + continuation word from configs"
```

---

## Task 6: Live update via QFileSystemWatcher

**Files:**
- Modify: `dictee-cheatsheet`

- [ ] **Step 1: Watcher dans `__init__`**

```python
from PyQt6.QtCore import QFileSystemWatcher
self._watcher = QFileSystemWatcher(self)
for path in (DICTEE_CONF, CONTINUATION_CONF):
    if path.exists():
        self._watcher.addPath(str(path))
self._watcher.fileChanged.connect(self._on_config_changed)
```

`_on_config_changed(path)` : appelle `_render_body()` puis re-add le path si retiré (rename atomique).

- [ ] **Step 2: Test manuel**

Avec carte ouverte : modifier `SUFFIX_FR` dans `~/.config/dictee.conf` (par sed pour tester rapidement). La carte met à jour la commande « point finale → . » immédiatement. Restaurer après test.

- [ ] **Step 3: Commit**

```bash
git add dictee-cheatsheet
git commit -m "feat(cheatsheet): live update via QFileSystemWatcher on config changes"
```

---

## Task 7: Zoom — buttons + raccourcis clavier + auto-resize

**Files:**
- Modify: `dictee-cheatsheet`

- [ ] **Step 1: Constantes zoom**

```python
DEFAULT_ZOOM_PT = 12.0
MIN_ZOOM_PT = 9.0
MAX_ZOOM_PT = 22.0
ZOOM_STEP = 0.5
```

- [ ] **Step 2: Méthodes zoom**

`zoom_in()` / `zoom_out()` / `zoom_reset()` modifient `self._zoom_pt` puis appellent `_apply_zoom()`.

`_apply_zoom()` : applique stylesheet, re-render body, recalcule `sizeHint`, resize cappé à `screen.availableGeometry() - 32px`. Voir spec §8 pour le détail.

- [ ] **Step 3: Connecter boutons header + raccourcis clavier**

`_zoom_in_btn.clicked.connect(self.zoom_in)` etc.

Raccourcis via `QShortcut` :
- `Ctrl++` / `Ctrl+=` → zoom_in
- `Ctrl+-` → zoom_out
- `Ctrl+0` → zoom_reset
- `Ctrl+W` / `Escape` → hide

`setFocusPolicy(Qt.FocusPolicy.StrongFocus)` pour recevoir le focus clavier.

- [ ] **Step 4: Test manuel**

Click + → texte plus gros, fenêtre s'agrandit. Click − → l'inverse. Ctrl+0 → reset.

- [ ] **Step 5: Commit**

```bash
git add dictee-cheatsheet
git commit -m "feat(cheatsheet): zoom feature (0.5pt step, auto-resize, shortcuts)"
```

---

## Task 8: Persistance — geometry + zoom + categories states

**Files:**
- Modify: `dictee-cheatsheet`

- [ ] **Step 1: `closeEvent` et `_save_state`**

`_save_state()` : utilise `QSettings("dictee", "cheatsheet")` pour sauvegarder x, y, width, height, zoom_pt, et la liste des catégories dépliées.

`closeEvent` et `hideEvent` appellent `_save_state()`.

- [ ] **Step 2: `_restore_state` appelé dans `__init__`**

Avant le premier `_render_body()`, restaurer :
- Zoom (clamp à `[MIN, MAX]`)
- Categories states
- Geometry : restore x, y, w, h. Si position hors écran → recenter top-right primary screen avec marge 16px.

- [ ] **Step 3: Test manuel**

Move + resize + zoom + plier 2 catégories + fermer → réouvrir : tout restauré identiquement.

- [ ] **Step 4: Commit**

```bash
git add dictee-cheatsheet
git commit -m "feat(cheatsheet): persist geometry + zoom + category states across sessions"
```

---

## Task 9: First-run banner + marker filesystem

**Files:**
- Modify: `dictee-cheatsheet`

- [ ] **Step 1: Constante du marker**

```python
FIRSTRUN_MARKER = Path.home() / ".local/state/dictee/cheatsheet-firstrun.done"
```

- [ ] **Step 2: Méthode `show_firstrun_banner`**

Insère un `QFrame` avec texte d'onboarding au début du body layout. Style bleu transparent (voir spec §7).

Contenu : « Bienvenue. Cette aide reste accessible via Ctrl+Alt+H ou le menu tray. Glisser pour déplacer. »

- [ ] **Step 3: Créer le marker au close si banner affiché**

Dans `_save_state` :
```python
if hasattr(self, "_firstrun_banner") and self._firstrun_banner:
    FIRSTRUN_MARKER.parent.mkdir(parents=True, exist_ok=True)
    FIRSTRUN_MARKER.touch()
```

- [ ] **Step 4: Test manuel**

```bash
rm -f ~/.local/state/dictee/cheatsheet-firstrun.done
/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-cheatsheet --first-run &
```

Carte avec banner bleu en haut. Fermer → marker existe.

- [ ] **Step 5: Commit**

```bash
git add dictee-cheatsheet
git commit -m "feat(cheatsheet): --first-run banner + state marker"
```

---

## Task 10: État sync via /dev/shm

**Files:**
- Modify: `dictee-cheatsheet`

- [ ] **Step 1: Constante state file**

```python
STATE_FILE = Path(f"/dev/shm/.dictee_cheatsheet-{os.getuid()}")
```

- [ ] **Step 2: Override `showEvent` et `hideEvent`**

`showEvent` : `STATE_FILE.write_text("1\n")` puis super.
`hideEvent` : `_save_state()` + `STATE_FILE.write_text("0\n")` + super.

- [ ] **Step 3: Cleanup à l'exit propre**

Dans `main()`, après la boucle Qt main : `STATE_FILE.unlink(missing_ok=True)`.

- [ ] **Step 4: Test manuel**

```bash
/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-cheatsheet &
sleep 1
cat /dev/shm/.dictee_cheatsheet-$(id -u)   # → 1
/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-cheatsheet --toggle
sleep 0.5
cat /dev/shm/.dictee_cheatsheet-$(id -u)   # → 0
pkill -f dictee-cheatsheet
ls /dev/shm/.dictee_cheatsheet-* 2>/dev/null   # → rien
```

- [ ] **Step 5: Commit**

```bash
git add dictee-cheatsheet
git commit -m "feat(cheatsheet): sync state to /dev/shm for tray/plasmoid awareness"
```

---

## Task 11: Bouton plasmoid

**Files:**
- Modify: `plasmoid/package/contents/ui/FullRepresentation.qml`
- Modify: `plasmoid/package/contents/ui/main.qml`

- [ ] **Step 1: Bouton dans FullRepresentation.qml**

Trouver `icon.name: "edit-reset"` (autour ligne 850). Ajouter juste avant un nouveau `PlasmaComponents.ToolButton` avec `icon.name: "view-list-text"`, `onClicked: fullRep.actionRequested("cheatsheet")`, tooltip i18n. Voir spec §5 pour le code QML exact.

- [ ] **Step 2: Switch case dans main.qml**

Trouver le switch dans `actionRequested` (autour ligne 640). Ajouter avant `case "transcribe-file"` :

```qml
case "cheatsheet":
    executable.run("dictee-cheatsheet --toggle")
    break
```

- [ ] **Step 3: Reload du plasmoid + test manuel**

```bash
kpackagetool6 -t Plasma/Applet -u /home/rapha/SOURCES/RAPHA_STT/dictee/plasmoid/package
# Puis logout/login KDE OU plasmashell --replace
```

Click sur l'icône plasmoid → panneau déroulé. Nouveau bouton à côté du reset rouge. Click → carte cheatsheet toggle.

- [ ] **Step 4: Commit**

```bash
git add plasmoid/package/contents/ui/FullRepresentation.qml plasmoid/package/contents/ui/main.qml
git commit -m "feat(plasmoid): cheatsheet toggle button next to reset action"
```

---

## Task 12: Entrée menu tray

**Files:**
- Modify: `dictee-tray.py`

- [ ] **Step 1: Localiser construction du menu**

```bash
grep -n "addAction\|menu.append\b" /home/rapha/SOURCES/RAPHA_STT/dictee/dictee-tray.py | head -10
```

- [ ] **Step 2: Ajouter entrée dans version PyQt6**

Dans la zone des actions menu (Setup, Quitter, etc.), ajouter une `QAction` « Toggle voice commands cheatsheet » dont le slot `triggered` lance `dictee-cheatsheet --toggle` via `subprocess` (pattern `Popen` avec liste d'args, sécurisé). Voir spec §5 « T — Menu tray » pour le code.

- [ ] **Step 3: Idem version AppIndicator**

Dans `DicteeTrayAppIndicator`, ajouter un `Gtk.MenuItem` similaire avec callback `activate` qui lance le même process.

- [ ] **Step 4: Test manuel**

Restart tray. Click droit → entrée présente. Click → carte toggle.

- [ ] **Step 5: Commit**

```bash
git add dictee-tray.py
git commit -m "feat(tray): cheatsheet toggle entry in tray menu"
```

---

## Task 13: Raccourci global KDE

**Files:**
- Modify: `dictee-setup.py`

- [ ] **Step 1: Localiser le pattern existant**

```bash
grep -n "kglobalaccel\|register_shortcut\|F8\|F9\|DICTEE_SHORTCUT" /home/rapha/SOURCES/RAPHA_STT/dictee/dictee-setup.py | head -20
```

Identifier comment F8/F9 sont :
- Affichés dans l'onglet Raccourcis
- Capturés via widget de raccourci
- Persistés dans dictee.conf
- Enregistrés via kglobalaccel D-Bus

- [ ] **Step 2: Champ dans l'onglet Raccourcis**

Dupliquer la structure F8 → nouveau champ « Voice commands cheatsheet » avec default `Ctrl+Alt+H`, config_key `DICTEE_SHORTCUT_CHEATSHEET`.

- [ ] **Step 3: Enregistrement à l'Apply**

Réutiliser la méthode `_register_kglobalaccel` (ou équivalente) avec :
- action_id : `dictee-cheatsheet-toggle`
- description i18n : « Toggle voice commands cheatsheet »
- shortcut : valeur du champ
- command : `dictee-cheatsheet --toggle`

- [ ] **Step 4: Persistance dans dictee.conf**

Sérialiser `DICTEE_SHORTCUT_CHEATSHEET=...` à l'Apply.

- [ ] **Step 5: Test manuel**

dictee-setup → onglet Raccourcis → champ présent avec Ctrl+Alt+H. Apply. Test depuis Firefox : Ctrl+Alt+H → carte toggle.

- [ ] **Step 6: Commit**

```bash
git add dictee-setup.py
git commit -m "feat(setup): cheatsheet keyboard shortcut field + kglobalaccel registration"
```

---

## Task 14: Auto-show 1ère install

**Files:**
- Modify: `dictee-tray.py`

- [ ] **Step 1: Check dans `main()`**

Après le singleton lock et la first-run config guard, ajouter un check du marker `~/.local/state/dictee/cheatsheet-firstrun.done`. Si absent → lancer `dictee-cheatsheet --first-run` via `subprocess.Popen` (forme list-args sécurisée), avec `try/except FileNotFoundError` pour les environnements de dev sans le binaire installé.

- [ ] **Step 2: Test manuel**

```bash
rm -f ~/.local/state/dictee/cheatsheet-firstrun.done
pkill -f dictee-tray
pkill -f dictee-cheatsheet
/home/rapha/SOURCES/RAPHA_STT/dictee/dictee-tray.py &
sleep 2
```

Carte s'ouvre avec banner. Fermer la carte. Restart tray → carte ne se ré-ouvre PAS auto.

- [ ] **Step 3: Commit**

```bash
git add dictee-tray.py
git commit -m "feat(tray): auto-show cheatsheet on first install (one-shot)"
```

---

## Task 15: Packaging — build-deb.sh + build-rpm.sh + PKGBUILD

**Files:**
- Modify: `build-deb.sh`
- Modify: `build-rpm.sh`
- Modify: `PKGBUILD`

⚠ **Règle permanente** : voir `feedback-new-binary-all-distros.md` en mémoire — ne jamais oublier les 3 fichiers de build.

- [ ] **Step 1: Ajouter dictee-cheatsheet dans build-deb.sh**

```bash
grep -nE 'cp\s+dictee-setup\b' /home/rapha/SOURCES/RAPHA_STT/dictee/build-deb.sh
```

À chaque occurrence (probablement 2-3, pour cpu et cuda), ajouter :

```bash
cp dictee-cheatsheet pkg/dictee/usr/bin/
chmod +x pkg/dictee/usr/bin/dictee-cheatsheet
```

- [ ] **Step 2: Ajouter dans build-rpm.sh**

Section `%files` du SPEC : ajouter `/usr/bin/dictee-cheatsheet`.
Section `%install` : `install -Dm755 dictee-cheatsheet "$BUILDROOT/usr/bin/dictee-cheatsheet"`.

- [ ] **Step 3: Ajouter dans PKGBUILD**

Dans `package()` :

```bash
install -Dm755 "$srcdir/$_repo/dictee-cheatsheet" "$pkgdir/usr/bin/dictee-cheatsheet"
```

- [ ] **Step 4: Vérification cross-distro**

```bash
grep -n "dictee-cheatsheet" /home/rapha/SOURCES/RAPHA_STT/dictee/build-deb.sh \
                              /home/rapha/SOURCES/RAPHA_STT/dictee/build-rpm.sh \
                              /home/rapha/SOURCES/RAPHA_STT/dictee/PKGBUILD
```

Expected : matches dans les 3 fichiers.

- [ ] **Step 5: Build .deb local**

```bash
cd /home/rapha/SOURCES/RAPHA_STT/dictee
./build-deb.sh 2>&1 | tail -20
dpkg-deb -c .dev/dist/dictee-cpu_*.deb | grep cheatsheet
```

Expected : `/usr/bin/dictee-cheatsheet` dans le contenu du .deb.

- [ ] **Step 6: Commit**

```bash
git add build-deb.sh build-rpm.sh PKGBUILD
git commit -m "build: install dictee-cheatsheet in deb, rpm, and Arch packages"
```

---

## Task 16: Tests E2E + push final

**Files:** none

- [ ] **Step 1: Checklist tests E2E**

Sur la machine du dev :

- [ ] Reboot pour clean `/dev/shm`. Lancer dictee-tray. Vérifier auto-show 1ère install
- [ ] Fermer carte. Tray menu : entrée présente → toggle
- [ ] Plasmoid bouton → toggle
- [ ] Ctrl+Alt+H global (depuis Firefox) → toggle
- [ ] Drag dans le fond → carte se déplace
- [ ] Resize via coin bas-droite → change de taille
- [ ] Click sur titre catégorie → toggle expand/collapse
- [ ] Ctrl++ × 5 → zoom + grossit
- [ ] Ctrl+0 → reset
- [ ] Fermer → réouvrir : tout restauré
- [ ] dictee-setup change SUFFIX_FR → Apply → carte ouverte se met à jour
- [ ] dictee-setup change mot continuation → carte ouverte se met à jour
- [ ] Click footer « doc complète : wiki » → ouvre la page

- [ ] **Step 2: Vérifier les commits**

```bash
git log --oneline origin/master..HEAD
```

Expected : ~16 commits (Tasks 1-15 + Task 16 ne crée pas de commit).

- [ ] **Step 3: Push**

```bash
git push github master
```

- [ ] **Step 4: Mémoire — noter Plan B livré**

Créer `~/.claude/projects/-home-rapha-SOURCES-RAPHA-STT-dictee/memory/project-rc3-cheatsheet-implemented.md` résumant la livraison. Ajouter référence dans `MEMORY.md`. Mettre à jour `project-rc3-reset-context-implemented.md` pour rayer la TODO « page wiki dédiée + cheatsheet ».

---

## Spec Coverage

| Section spec | Task |
|---|---|
| §2 Architecture (singleton, CLI) | Task 1 |
| §3 Composants (script structure) | Tasks 1-10 |
| §3 COMMAND_TABLE | Task 2 |
| §4 Data flow + watcher | Tasks 5, 6 |
| §5 Triggers P (plasmoid) | Task 11 |
| §5 Triggers T (tray) | Task 12 |
| §5 Triggers K (raccourci global) | Task 13 |
| §5 Triggers A (auto-show) | Tasks 9, 14 |
| §5 Sync state | Task 10 |
| §6 Persistance | Task 8 |
| §7 Visuel (frameless, drag, etc.) | Tasks 3, 4 |
| §8 Zoom et accessibilité | Task 7 |
| §9 Wiki (référencé en footer) | (Plan A) |
| §10 Tests | Task 16 |
| §11 Risques | (vigilance pendant implémentation) |
| §12 Phase 3 packaging | Task 15 |

## Estimated Time

~4h total : Tasks 1-2 (45 min skeleton + table), Tasks 3-4 (45 min header + body), Tasks 5-6 (30 min config + watcher), Task 7 (30 min zoom), Tasks 8-9 (30 min persistance + first-run), Task 10 (10 min state file), Tasks 11-14 (45 min intégrations triggers), Task 15 (15 min packaging), Task 16 (15 min tests).
