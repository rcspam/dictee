# Wizard de configuration dictee v1.1.0 — Plan d'implémentation

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un assistant de configuration pas-à-pas (wizard) à `dictee-setup.py` avec 5 pages, radio buttons visuels, test micro temps réel, et test de dictée.

**Architecture:** QStackedWidget avec 5 pages dans DicteeSetupDialog. Construction conditionnelle : les widgets sont créés une seule fois dans `__init__()` et placés directement dans le bon conteneur (stack ou scroll) selon `self.wizard_mode`. Pas de re-parenting dynamique.

**Tech Stack:** PyQt6/PySide6, QStackedWidget, QThread (AudioLevelThread), parec/pw-record, wpctl/pactl, gettext i18n

**Spec:** `docs/superpowers/specs/2026-03-13-wizard-setup-design.md`

---

## Chunk 1 : Infrastructure

### Task 1 : Argument --wizard dans le script shell

**Files:**
- Modify: `dictee:83-85` (bloc `--setup)`)
- Modify: `dictee:10` (commentaire Usage)

- [ ] **Step 1: Ajouter --wizard au script dictee**

Dans `dictee`, modifier le bloc `--setup)` et ajouter `--wizard)` :

```bash
    --setup)
        shift
        exec dictee-setup "$@"
        ;;
    --wizard)
        exec dictee-setup --wizard
        ;;
```

Et mettre à jour le commentaire Usage ligne 10 :
```bash
# Usage: dictee [--translate] [--ollama] [--cancel] [--setup [--wizard]]
```

- [ ] **Step 2: Ajouter le parsing --wizard dans dictee-setup.py**

Dans `dictee-setup.py`, modifier `main()` (ligne 1937) pour parser `--wizard` :

```python
def main():
    import sys
    wizard_flag = "--wizard" in sys.argv
    app = QApplication([])
    app.setApplicationName("dictee-setup")
    dialog = DicteeSetupDialog(wizard=wizard_flag)
    dialog.exec()
```

- [ ] **Step 3: Tester manuellement**

```bash
dictee-setup --wizard  # doit s'ouvrir sans erreur
dictee --setup --wizard  # idem via le script shell
```

- [ ] **Step 4: Commit**

```bash
git add dictee dictee-setup.py
git commit -m "feat: ajouter argument --wizard à dictee et dictee-setup"
```

---

### Task 2 : QStackedWidget + barre de navigation

**Files:**
- Modify: `dictee-setup.py:953-960` (DicteeSetupDialog.__init__)

- [ ] **Step 1: Ajouter wizard_mode et QStackedWidget dans __init__**

Modifier `DicteeSetupDialog.__init__` pour accepter `wizard=False`. Avant la construction des widgets existants, ajouter :

```python
class DicteeSetupDialog(QDialog):
    def __init__(self, wizard=False):
        super().__init__()
        self.wizard_mode = wizard or not os.path.exists(CONF_PATH)
        # ... (code existant de détection DE, lecture config, etc.)
```

- [ ] **Step 2: Créer la structure wizard si wizard_mode**

Après la lecture de config et avant la construction des sections, ajouter la branche conditionnelle :

```python
if self.wizard_mode:
    self._build_wizard_ui()
else:
    self._build_classic_ui()
```

Extraire le code existant de construction UI dans `_build_classic_ui()`. Créer `_build_wizard_ui()` qui crée le QStackedWidget avec 5 pages vides + barre de navigation.

- [ ] **Step 3: Implémenter _build_wizard_ui avec navigation**

```python
from PyQt6.QtWidgets import QStackedWidget  # ajouter à l'import

def _build_wizard_ui(self):
    main_layout = QVBoxLayout(self)
    self.stack = QStackedWidget()

    # 5 pages (vides pour l'instant)
    self.wizard_pages = []
    for i in range(5):
        page = QWidget()
        page.setLayout(QVBoxLayout())
        self.stack.addWidget(page)
        self.wizard_pages.append(page)

    main_layout.addWidget(self.stack)

    # Barre de navigation
    nav = QHBoxLayout()
    self.btn_prev = QPushButton(_("← Previous"))
    self.btn_prev.clicked.connect(self._wizard_prev)
    self.lbl_step = QLabel()
    self.lbl_step.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.btn_next = QPushButton(_("Next →"))
    self.btn_next.clicked.connect(self._wizard_next)

    nav.addWidget(self.btn_prev)
    nav.addStretch()
    nav.addWidget(self.lbl_step)
    nav.addStretch()
    nav.addWidget(self.btn_next)
    main_layout.addLayout(nav)

    self._update_wizard_nav()
    self.setWindowTitle(_("dictee — Setup wizard"))
    self.resize(600, 500)
```

- [ ] **Step 4: Implémenter les méthodes de navigation**

```python
def _wizard_prev(self):
    idx = self.stack.currentIndex()
    if idx > 0:
        self.stack.setCurrentIndex(idx - 1)
        self._update_wizard_nav()

def _wizard_next(self):
    idx = self.stack.currentIndex()
    if idx == 4:  # dernière page → Terminer
        self._on_wizard_finish()
        return
    if not self._validate_wizard_page(idx):
        return
    self.stack.setCurrentIndex(idx + 1)
    if idx + 1 == 4:  # arrivée sur page 5 → lancer checks
        self._run_wizard_checks()
    self._update_wizard_nav()

def _update_wizard_nav(self):
    idx = self.stack.currentIndex()
    self.btn_prev.setEnabled(idx > 0)
    self.lbl_step.setText(_("Step {n} of 5").format(n=idx + 1))
    if idx == 4:
        self.btn_next.setText(_("✓ Finish"))
        self.btn_next.setStyleSheet("background: #4a4; color: white; font-weight: bold; padding: 8px 20px;")
    else:
        self.btn_next.setText(_("Next →"))
        self.btn_next.setStyleSheet("")

def _validate_wizard_page(self, idx):
    """Valide la page courante. Retourne True si OK."""
    if idx == 0:  # Page ASR : vérifier que le modèle est installé
        return self._validate_asr_model()
    return True  # pages 1-3 : pas de validation

def _on_wizard_finish(self):
    self._on_apply()
    self.accept()
```

- [ ] **Step 5: Tester**

```bash
dictee-setup --wizard  # doit afficher 5 pages vides avec navigation fonctionnelle
```

- [ ] **Step 6: Commit**

```bash
git add dictee-setup.py
git commit -m "feat: QStackedWidget + navigation wizard dans dictee-setup"
```

---

### Task 3 : Bouton "Assistant de configuration" en mode classique

**Files:**
- Modify: `dictee-setup.py` — fin de `_build_classic_ui()` (barre de boutons)

- [ ] **Step 1: Ajouter le bouton dans la barre existante**

Dans `_build_classic_ui()`, dans la barre de boutons en bas (à côté de Cancel), ajouter :

```python
btn_wizard = QPushButton(_("Setup wizard"))
btn_wizard.clicked.connect(self._launch_wizard)
button_layout.insertWidget(0, btn_wizard)  # à gauche
```

- [ ] **Step 2: Implémenter _launch_wizard**

```python
def _launch_wizard(self):
    """Ferme le dialog et relance en mode wizard."""
    self.reject()
    subprocess.Popen([sys.executable, __file__, "--wizard"])
```

Note : import `sys` déjà ajouté dans Task 1.

- [ ] **Step 3: Tester**

```bash
dictee-setup  # mode classique, vérifier le bouton "Assistant" en bas à gauche
# Cliquer → doit fermer et rouvrir en mode wizard
```

- [ ] **Step 4: Commit**

```bash
git add dictee-setup.py
git commit -m "feat: bouton 'Assistant de configuration' en mode classique"
```

---

## Chunk 2 : Pages 1 et 2

### Task 4 : Page 1 — Bienvenue + Backend ASR (radio buttons visuels)

**Files:**
- Modify: `dictee-setup.py` — `_build_wizard_ui()` + nouvelles méthodes

- [ ] **Step 1: Créer _build_wizard_page_asr()**

Méthode qui construit la page 1 avec radio buttons visuels (blocs QFrame cliquables) :

```python
def _build_wizard_page_asr(self):
    page = self.wizard_pages[0]
    lay = page.layout()

    # Titre
    title = QLabel(_("Welcome to dictee!"))
    title.setStyleSheet("font-size: 20px; font-weight: bold;")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(title)

    subtitle = QLabel(_("Choose your speech recognition engine."))
    subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
    subtitle.setStyleSheet("color: #888;")
    lay.addWidget(subtitle)

    # Radio buttons visuels
    self.asr_radio_group = QButtonGroup(self)
    backends = [
        ("parakeet", "Parakeet-TDT 0.6B", _("Recommended"), _("25 languages, ~2.5 GB, ~0.8s")),
        ("vosk", "Vosk", _("Lightweight"), _("9+ languages, ~50 MB, ~1.5s")),
        ("whisper", "faster-whisper", _("99 languages"), _("~500 MB–3 GB, ~0.3s")),
    ]
    self._asr_radio_frames = {}
    for i, (key, name, badge, desc) in enumerate(backends):
        frame = self._make_radio_card(name, badge, desc)
        radio = QRadioButton()
        radio.setFixedSize(0, 0)  # caché, contrôle logique uniquement
        self.asr_radio_group.addButton(radio, i)
        frame.mousePressEvent = lambda e, r=radio, k=key: self._select_asr_radio(r, k)
        lay.addWidget(frame)
        self._asr_radio_frames[key] = (frame, radio)

    # Sélection par défaut
    self._select_asr_radio(
        self._asr_radio_frames.get(self._current_asr, self._asr_radio_frames["parakeet"])[1],
        self._current_asr if self._current_asr in self._asr_radio_frames else "parakeet"
    )

    # Sous-options conditionnelles (langue Vosk, modèle Whisper)
    self._build_asr_sub_options(lay)

    # Statut d'installation + bouton télécharger
    self._build_asr_model_status(lay)

    lay.addStretch()
```

- [ ] **Step 2: Créer _make_radio_card()**

Widget réutilisable pour les radio buttons visuels :

```python
def _make_radio_card(self, title, badge, description, selected=False):
    frame = QFrame()
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    frame.setCursor(Qt.CursorShape.PointingHandCursor)
    frame.setStyleSheet(self._card_style(selected))
    frame.setFixedHeight(70)

    lay = QVBoxLayout(frame)
    lay.setContentsMargins(12, 8, 12, 8)

    top = QHBoxLayout()
    lbl_title = QLabel(f"<b>{title}</b>")
    top.addWidget(lbl_title)
    if badge:
        lbl_badge = QLabel(badge)
        lbl_badge.setStyleSheet("background: #233; color: #6a6; padding: 2px 8px; border-radius: 10px; font-size: 11px;")
        top.addWidget(lbl_badge)
    top.addStretch()
    lay.addLayout(top)

    lbl_desc = QLabel(description)
    lbl_desc.setStyleSheet("color: #888; font-size: 12px;")
    lay.addWidget(lbl_desc)

    return frame

def _card_style(self, selected):
    border = "2px solid #5566ff" if selected else "1px solid #444"
    bg = "#252545" if selected else "#1e1e2e"
    return f"QFrame {{ background: {bg}; border: {border}; border-radius: 8px; }}"
```

- [ ] **Step 3: Créer _select_asr_radio()**

```python
def _select_asr_radio(self, radio, key):
    radio.setChecked(True)
    self._current_asr = key
    # Mettre à jour les styles
    for k, (frame, _) in self._asr_radio_frames.items():
        frame.setStyleSheet(self._card_style(k == key))
    # Afficher/masquer sous-options
    self._update_asr_sub_options(key)
```

- [ ] **Step 4: Implémenter _build_asr_sub_options() et _build_asr_model_status()**

Sous-options conditionnelles (langue Vosk, modèle Whisper) + statut d'installation avec bouton Télécharger. Réutiliser la logique existante des ComboBox Vosk/Whisper (lignes 1125-1180) mais dans le layout wizard.

- [ ] **Step 5: Implémenter _validate_asr_model()**

```python
def _validate_asr_model(self):
    """Vérifie que le modèle ASR sélectionné est installé."""
    key = self._current_asr
    if key == "parakeet":
        installed = self._check_parakeet_installed()
    elif key == "vosk":
        installed = self._check_vosk_model_installed()
    elif key == "whisper":
        installed = self._check_whisper_venv()
    else:
        installed = True

    if not installed:
        QMessageBox.warning(self, _("Model required"),
            _("Please download the model before continuing."))
    return installed
```

- [ ] **Step 6: Connecter la page dans _build_wizard_ui()**

Appeler `self._build_wizard_page_asr()` après la création des pages.

- [ ] **Step 7: Tester**

```bash
dictee-setup --wizard  # Page 1 : radio buttons, sélection, sous-options, statut modèle
```

- [ ] **Step 8: Commit**

```bash
git add dictee-setup.py
git commit -m "feat: page 1 wizard — backend ASR avec radio buttons visuels"
```

---

### Task 5 : Page 2 — Raccourcis clavier

**Files:**
- Modify: `dictee-setup.py` — nouvelle méthode `_build_wizard_page_shortcuts()`

- [ ] **Step 1: Créer _build_wizard_page_shortcuts()**

Réutilise `ShortcutButton` existant (ligne 905), adapté au layout wizard :

```python
def _build_wizard_page_shortcuts(self):
    page = self.wizard_pages[1]
    lay = page.layout()

    title = QLabel(_("Keyboard shortcuts"))
    title.setStyleSheet("font-size: 20px; font-weight: bold;")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(title)

    # Environnement détecté
    env_label = QLabel(_("Detected: {env}").format(env=self.de_name))
    env_label.setStyleSheet("color: #8a8;")
    env_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(env_label)

    if self.de_type == "unsupported":
        # WM tiling : afficher les commandes manuelles
        self._build_tiling_wm_instructions(lay)
    else:
        # KDE / GNOME : boutons de capture
        form = QFormLayout()

        self.btn_capture = ShortcutButton(QKeySequence("F9"))
        self.btn_capture.shortcut_captured.connect(self._on_shortcut_captured)
        form.addRow(_("Voice dictation:"), self.btn_capture)

        self.btn_capture_translate = ShortcutButton(QKeySequence("Alt+F9"))
        self.btn_capture_translate.shortcut_captured.connect(self._on_shortcut_translate_captured)
        form.addRow(_("Dictation + Translation:"), self.btn_capture_translate)

        lay.addLayout(form)

        # Détection de conflit (KDE uniquement)
        if self.de_type == "kde":
            self.lbl_conflict = QLabel()
            lay.addWidget(self.lbl_conflict)
            self.btn_capture.shortcut_captured.connect(
                lambda seq: self._check_shortcut_conflict(seq, self.lbl_conflict))

    lay.addStretch()
```

- [ ] **Step 2: Implémenter _build_tiling_wm_instructions()**

```python
def _build_tiling_wm_instructions(self, layout):
    info = QLabel(_("Manual shortcut configuration required for your WM."))
    info.setStyleSheet("color: #ca6;")
    layout.addWidget(info)

    cmds = QLabel(
        "Sway/i3:\n"
        "  bindsym F9 exec dictee\n"
        "  bindsym Alt+F9 exec dictee --translate\n\n"
        "Hyprland:\n"
        "  bind = , F9, exec, dictee\n"
        "  bind = ALT, F9, exec, dictee --translate"
    )
    cmds.setStyleSheet("font-family: monospace; background: #1a1a2e; padding: 12px; border-radius: 6px;")
    cmds.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    layout.addWidget(cmds)
```

- [ ] **Step 3: Implémenter _check_shortcut_conflict()**

```python
def _check_shortcut_conflict(self, seq, label):
    """Vérifie les conflits de raccourci KDE et affiche dans label."""
    accel = qt_key_to_kde(seq)
    conflict = check_kde_conflict(accel)
    if conflict:
        label.setText(_("⚠ Conflict: {app}").format(app=conflict))
        label.setStyleSheet("color: #ca6;")
    else:
        label.setText(_("✓ No conflict"))
        label.setStyleSheet("color: #6a6;")
```

- [ ] **Step 4: Connecter dans _build_wizard_ui()**

- [ ] **Step 5: Tester**

```bash
dictee-setup --wizard  # Page 2 : raccourcis, capture, détection conflit
```

- [ ] **Step 6: Commit**

```bash
git add dictee-setup.py
git commit -m "feat: page 2 wizard — raccourcis clavier avec détection conflit"
```

---

## Chunk 3 : Pages 3 et 4

### Task 6 : Page 3 — Traduction

**Files:**
- Modify: `dictee-setup.py` — nouvelle méthode `_build_wizard_page_translation()`

- [ ] **Step 1: Créer _build_wizard_page_translation()**

Radio buttons visuels pour les backends de traduction, locaux en premier :

```python
def _build_wizard_page_translation(self):
    page = self.wizard_pages[2]
    lay = page.layout()

    title = QLabel(_("Translation"))
    title.setStyleSheet("font-size: 20px; font-weight: bold;")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(title)

    subtitle = QLabel(_("Dictate in one language, get text in another. Optional."))
    subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
    subtitle.setStyleSheet("color: #888;")
    lay.addWidget(subtitle)

    # Langues source / cible
    lang_row = QHBoxLayout()
    src_lay = QVBoxLayout()
    src_lay.addWidget(QLabel(_("Source language")))
    self.combo_src = QComboBox()
    for code, name in LANGUAGES:
        self.combo_src.addItem(f"{name} ({code})", code)
    self._set_combo_by_data(self.combo_src, self._current_src_lang, 0)
    src_lay.addWidget(self.combo_src)
    lang_row.addLayout(src_lay)

    arrow = QLabel("→")
    arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lang_row.addWidget(arrow)

    tgt_lay = QVBoxLayout()
    tgt_lay.addWidget(QLabel(_("Target language")))
    self.combo_tgt = QComboBox()
    for code, name in LANGUAGES:
        self.combo_tgt.addItem(f"{name} ({code})", code)
    self._set_combo_by_data(self.combo_tgt, self._current_tgt_lang, 1)
    tgt_lay.addWidget(self.combo_tgt)
    lang_row.addLayout(tgt_lay)
    lay.addLayout(lang_row)

    # Radio buttons visuels — locaux en premier
    self.trans_radio_group = QButtonGroup(self)
    backends = [
        ("ollama", "ollama", _("100% local — Best quality"), _("translategemma — 2.3–3.4s")),
        ("libretranslate", "LibreTranslate", _("100% local"), _("Docker ~2 GB — 0.1–0.3s")),
        ("trans:google", "Google Translate", _("Online — Fast"), _("0.2–0.7s — translate-shell")),
        ("trans:bing", "Bing", _("Online"), _("1.7–2.2s — translate-shell")),
    ]
    self._trans_radio_frames = {}
    for i, (key, name, badge, desc) in enumerate(backends):
        frame = self._make_radio_card(name, badge, desc)
        radio = QRadioButton()
        radio.setFixedSize(0, 0)
        self.trans_radio_group.addButton(radio, i)
        frame.mousePressEvent = lambda e, r=radio, k=key: self._select_trans_radio(r, k)
        lay.addWidget(frame)
        self._trans_radio_frames[key] = (frame, radio)

    # Sélection par défaut
    default_trans = self._current_trans_backend or "trans:google"
    if default_trans in self._trans_radio_frames:
        self._select_trans_radio(self._trans_radio_frames[default_trans][1], default_trans)

    # Sous-options conditionnelles (modèle ollama, port LT)
    self._build_trans_sub_options_wizard(lay)

    # Statut dépendances
    self._build_trans_deps_status(lay)

    lay.addStretch()
```

- [ ] **Step 2: Créer _select_trans_radio()**

```python
def _select_trans_radio(self, radio, key):
    radio.setChecked(True)
    self._current_trans_backend = key
    for k, (frame, _) in self._trans_radio_frames.items():
        frame.setStyleSheet(self._card_style(k == key))
    self._update_trans_sub_options_wizard(key)
```

- [ ] **Step 3: Implémenter sous-options et détection dépendances**

Sous-options ollama (modèle, téléchargement) et LibreTranslate (port, Docker) qui apparaissent conditionnellement. Détection automatique : `shutil.which("trans")`, `shutil.which("ollama")`, `shutil.which("docker")`.

- [ ] **Step 4: Connecter dans _build_wizard_ui()**

- [ ] **Step 5: Tester**

```bash
dictee-setup --wizard  # Page 3 : traduction, radio buttons, sous-options
```

- [ ] **Step 6: Commit**

```bash
git add dictee-setup.py
git commit -m "feat: page 3 wizard — traduction avec backends locaux en premier"
```

---

### Task 7 : AudioLevelThread + list_audio_sources()

**Files:**
- Modify: `dictee-setup.py` — nouvelles classes/fonctions avant DicteeSetupDialog

- [ ] **Step 1: Implémenter list_audio_sources()**

```python
def list_audio_sources():
    """Liste les sources micro via pactl ou wpctl.
    Retourne [(id, description), ...] ou [] si rien détecté.
    """
    sources = []
    try:
        out = subprocess.run(
            ["pactl", "list", "sources", "short"],
            capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0:
            for line in out.stdout.strip().splitlines():
                parts = line.split("\t")
                if len(parts) >= 2 and "monitor" not in parts[1].lower():
                    source_id = parts[1]
                    desc = parts[1].replace(".", " ").replace("_", " ")
                    sources.append((source_id, desc))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    if not sources:
        # Fallback wpctl
        try:
            out = subprocess.run(
                ["wpctl", "status"],
                capture_output=True, text=True, timeout=5
            )
            if out.returncode == 0:
                in_sources = False
                for line in out.stdout.splitlines():
                    if "Sources:" in line:
                        in_sources = True
                        continue
                    if in_sources and line.strip() == "":
                        break
                    if in_sources and "│" in line:
                        # Parse "│  * 47. source_name [vol: ...]"
                        m = re.search(r'(\d+)\.\s+(.+?)(?:\s+\[|$)', line)
                        if m:
                            sources.append((m.group(1), m.group(2).strip()))
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    return sources
```

- [ ] **Step 2: Implémenter AudioLevelThread**

```python
class AudioLevelThread(QThread):
    """Lit le micro en continu, émet le niveau RMS (0-100)."""
    level = Signal(int)

    def __init__(self, source_id=None):
        super().__init__()
        self._running = True
        self._source_id = source_id
        self._process = None

    def run(self):
        import struct, math
        cmd = self._build_record_cmd()
        if not cmd:
            return
        try:
            self._process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
            while self._running and self._process.poll() is None:
                # 100ms de s16le mono 16kHz = 3200 octets = 1600 samples
                data = self._process.stdout.read(3200)
                if len(data) < 3200:
                    break
                samples = struct.unpack(f"<{len(data)//2}h", data)
                rms = math.sqrt(sum(s*s for s in samples) / len(samples))
                normalized = min(100, int(rms / 327.67))  # 32767 → 100
                self.level.emit(normalized)
        except Exception:
            pass
        finally:
            self.stop()

    def _build_record_cmd(self):
        """Construit la commande parec ou pw-record."""
        if shutil.which("parec"):
            cmd = ["parec", "--format=s16le", "--rate=16000", "--channels=1"]
            if self._source_id:
                cmd.extend(["--device", self._source_id])
            return cmd
        elif shutil.which("pw-record"):
            cmd = ["pw-record", "--format=s16", "--rate=16000", "--channels=1", "-"]
            return cmd
        return None

    def stop(self):
        self._running = False
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
```

- [ ] **Step 3: Tester unitairement**

```python
# Test rapide dans un terminal Python
from dictee_setup import list_audio_sources
print(list_audio_sources())  # doit lister les micros
```

- [ ] **Step 4: Commit**

```bash
git add dictee-setup.py
git commit -m "feat: AudioLevelThread et list_audio_sources() pour monitoring micro"
```

---

### Task 8 : Page 4 — Micro, interface visuelle, services

**Files:**
- Modify: `dictee-setup.py` — nouvelle méthode `_build_wizard_page_visual()`

- [ ] **Step 1: Créer _build_wizard_page_visual() — section Microphone**

```python
def _build_wizard_page_visual(self):
    page = self.wizard_pages[3]
    lay = page.layout()

    # Utiliser un QScrollArea car cette page est dense
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    content_lay = QVBoxLayout(content)

    title = QLabel(_("Microphone, visual feedback & services"))
    title.setStyleSheet("font-size: 20px; font-weight: bold;")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    content_lay.addWidget(title)

    # === Microphone ===
    mic_group = QGroupBox(_("Microphone"))
    mic_lay = QVBoxLayout(mic_group)

    # Source audio
    sources = list_audio_sources()
    self.cmb_audio_source = QComboBox()
    if sources:
        for src_id, desc in sources:
            self.cmb_audio_source.addItem(desc, src_id)
    else:
        self.cmb_audio_source.addItem(_("No microphone detected"), "")
        self.cmb_audio_source.setEnabled(False)

    mic_lay.addWidget(QLabel(_("Audio source:")))
    mic_lay.addWidget(self.cmb_audio_source)

    # Volume slider
    from PyQt6.QtWidgets import QSlider
    vol_row = QHBoxLayout()
    vol_row.addWidget(QLabel(_("Volume:")))
    self.slider_volume = QSlider(Qt.Orientation.Horizontal)
    self.slider_volume.setRange(0, 150)
    self.slider_volume.setValue(100)
    self.slider_volume.valueChanged.connect(self._on_volume_changed)
    vol_row.addWidget(self.slider_volume)
    self.lbl_volume = QLabel("100%")
    vol_row.addWidget(self.lbl_volume)
    mic_lay.addLayout(vol_row)

    # Indicateur de niveau
    self.bar_mic_level = QProgressBar()
    self.bar_mic_level.setRange(0, 100)
    self.bar_mic_level.setTextVisible(False)
    self.bar_mic_level.setFixedHeight(12)
    mic_lay.addWidget(self.bar_mic_level)

    # Avertissement si pas de micro
    if not sources:
        warn = QLabel(_("⚠ No microphone detected. Check your audio connection."))
        warn.setStyleSheet("color: #ca6;")
        mic_lay.addWidget(warn)

    content_lay.addWidget(mic_group)
```

- [ ] **Step 2: Section retour visuel (checkboxes)**

```python
    # === Retour visuel ===
    vis_group = QGroupBox(_("Visual feedback during recording"))
    vis_lay = QVBoxLayout(vis_group)

    self.chk_plasmoid = QCheckBox(_("KDE Plasma widget"))
    self.chk_anim_speech = QCheckBox(_("animation-speech (fullscreen overlay, Wayland)"))
    self.chk_tray = QCheckBox(_("Notification icon (dictee-tray)"))

    # Pré-coche intelligente
    if self.de_type == "kde":
        self.chk_plasmoid.setChecked(True)
    else:
        self.chk_tray.setChecked(True)

    # Statut installation
    for chk, check_fn, name in [
        (self.chk_plasmoid, self._check_plasmoid_installed, "plasmoid"),
        (self.chk_anim_speech, lambda: bool(shutil.which(ANIMATION_SPEECH_BIN)), "animation-speech"),
    ]:
        if check_fn():
            chk.setToolTip(_("✓ Installed"))
        else:
            chk.setToolTip(_("Not installed"))

    vis_lay.addWidget(self.chk_plasmoid)
    vis_lay.addWidget(self.chk_anim_speech)
    vis_lay.addWidget(self.chk_tray)
    content_lay.addWidget(vis_group)
```

- [ ] **Step 3: Section services au démarrage**

```python
    # === Services ===
    svc_group = QGroupBox(_("Startup services"))
    svc_lay = QVBoxLayout(svc_group)

    self.chk_daemon = QCheckBox(_("Start transcription daemon at login"))
    self.chk_daemon.setChecked(True)
    svc_lay.addWidget(self.chk_daemon)

    self.chk_clipboard = QCheckBox(_("Copy transcription to clipboard"))
    self.chk_clipboard.setChecked(False)
    svc_lay.addWidget(self.chk_clipboard)

    content_lay.addWidget(svc_group)

    content_lay.addStretch()
    scroll.setWidget(content)
    lay.addWidget(scroll)
```

- [ ] **Step 4: Implémenter _on_volume_changed()**

```python
def _on_volume_changed(self, value):
    self.lbl_volume.setText(f"{value}%")
    vol = value / 100.0
    source = self.cmb_audio_source.currentData()
    if shutil.which("wpctl") and source:
        subprocess.Popen(["wpctl", "set-volume", source, f"{vol:.2f}"])
    elif shutil.which("pactl") and source:
        subprocess.Popen(["pactl", "set-source-volume", source, f"{value}%"])
```

- [ ] **Step 5: Démarrer/arrêter AudioLevelThread**

Démarrer le thread quand on arrive sur la page 4, l'arrêter quand on quitte :

```python
def _start_audio_level(self):
    source = self.cmb_audio_source.currentData() if hasattr(self, 'cmb_audio_source') else None
    if source:
        self._audio_thread = AudioLevelThread(source)
        self._audio_thread.level.connect(self.bar_mic_level.setValue)
        self._audio_thread.start()

def _stop_audio_level(self):
    if hasattr(self, '_audio_thread') and self._audio_thread.isRunning():
        self._audio_thread.stop()
        self._audio_thread.wait(2000)
```

Modifier `_wizard_next()` et `_wizard_prev()` pour appeler `_start_audio_level()` à l'entrée sur page 4 et `_stop_audio_level()` en sortie.

- [ ] **Step 6: Connecter dans _build_wizard_ui()**

- [ ] **Step 7: Tester**

```bash
dictee-setup --wizard  # Page 4 : micro avec niveau, visual, services
```

- [ ] **Step 8: Commit**

```bash
git add dictee-setup.py
git commit -m "feat: page 4 wizard — micro, retour visuel, services au démarrage"
```

---

## Chunk 4 : Page 5, intégration, i18n, finitions

### Task 9 : Page 5 — Test

**Files:**
- Modify: `dictee-setup.py` — nouvelle méthode `_build_wizard_page_test()`

- [ ] **Step 1: Créer _build_wizard_page_test()**

```python
def _build_wizard_page_test(self):
    page = self.wizard_pages[4]
    lay = page.layout()

    title = QLabel(_("Let's test!"))
    title.setStyleSheet("font-size: 20px; font-weight: bold;")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lay.addWidget(title)

    subtitle = QLabel(_("Let's verify everything works correctly."))
    subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
    subtitle.setStyleSheet("color: #888;")
    lay.addWidget(subtitle)

    # Vérifications automatiques
    checks_group = QGroupBox(_("Automatic checks"))
    checks_lay = QVBoxLayout(checks_group)
    self._check_labels = {}
    check_items = [
        ("daemon", _("ASR Daemon")),
        ("model", _("Model installed")),
        ("shortcut", _("Shortcut registered")),
        ("audio", _("Audio (PipeWire/PulseAudio)")),
        ("dotool", _("dotool")),
    ]
    for key, label_text in check_items:
        row = QHBoxLayout()
        icon = QLabel("⏳")
        icon.setFixedWidth(24)
        lbl = QLabel(label_text)
        btn_fix = QPushButton(_("Fix"))
        btn_fix.setFixedWidth(60)
        btn_fix.hide()
        row.addWidget(icon)
        row.addWidget(lbl)
        row.addStretch()
        row.addWidget(btn_fix)
        checks_lay.addLayout(row)
        self._check_labels[key] = (icon, lbl, btn_fix)

    lay.addWidget(checks_group)

    # Test de dictée
    test_group = QGroupBox(_("Dictation test"))
    test_lay = QVBoxLayout(test_group)
    test_lay.addWidget(QLabel(_("Click the button below and speak for a few seconds.")))

    self.btn_test_dictee = QPushButton(_("🎤 Test dictation"))
    self.btn_test_dictee.setStyleSheet("padding: 12px 24px; font-size: 14px;")
    self.btn_test_dictee.clicked.connect(self._on_test_dictee)
    test_lay.addWidget(self.btn_test_dictee)

    from PyQt6.QtWidgets import QTextEdit
    self.txt_test_result = QTextEdit()
    self.txt_test_result.setReadOnly(True)
    self.txt_test_result.setMaximumHeight(80)
    self.txt_test_result.setPlaceholderText(_("Result will appear here..."))
    test_lay.addWidget(self.txt_test_result)

    lay.addWidget(test_group)

    # Message final
    self.lbl_ready = QLabel(_("🎉 All set! Press your shortcut anytime to dictate."))
    self.lbl_ready.setStyleSheet("color: #afa; font-size: 16px; font-weight: bold;")
    self.lbl_ready.setAlignment(Qt.AlignmentFlag.AlignCenter)
    self.lbl_ready.hide()
    lay.addWidget(self.lbl_ready)

    lay.addStretch()
```

- [ ] **Step 2: Implémenter _run_wizard_checks()**

```python
def _run_wizard_checks(self):
    """Lance les vérifications automatiques de la page 5."""
    checks = {
        "daemon": self._check_daemon_active,
        "model": self._check_model_installed,
        "shortcut": self._check_shortcut_registered,
        "audio": self._check_audio_available,
        "dotool": lambda: bool(shutil.which("dotool")),
    }
    page_map = {"daemon": 0, "model": 0, "shortcut": 1, "audio": 3}
    all_ok = True

    for key, check_fn in checks.items():
        icon, lbl, btn_fix = self._check_labels[key]
        try:
            ok = check_fn()
        except Exception:
            ok = False

        if ok:
            icon.setText("✓")
            icon.setStyleSheet("color: #6a6; font-size: 18px;")
            btn_fix.hide()
        else:
            icon.setText("✗")
            icon.setStyleSheet("color: #a66; font-size: 18px;")
            if key in page_map:
                btn_fix.show()
                target_page = page_map[key]
                btn_fix.clicked.connect(lambda _, p=target_page: self._go_to_page(p))
            all_ok = False

    if all_ok:
        self.lbl_ready.show()

def _go_to_page(self, page_idx):
    self.stack.setCurrentIndex(page_idx)
    self._update_wizard_nav()
```

- [ ] **Step 3: Implémenter les fonctions de check individuelles**

```python
def _check_daemon_active(self):
    asr = self._current_asr
    svc = {"parakeet": "dictee", "vosk": "dictee-vosk", "whisper": "dictee-whisper"}.get(asr, "dictee")
    r = subprocess.run(["systemctl", "--user", "is-active", svc], capture_output=True, text=True)
    return r.stdout.strip() == "active"

def _check_model_installed(self):
    asr = self._current_asr
    if asr == "parakeet":
        return self._check_parakeet_installed()
    elif asr == "vosk":
        return self._check_vosk_model_installed()
    elif asr == "whisper":
        return self._check_whisper_venv()
    return True

def _check_shortcut_registered(self):
    if self.de_type == "kde":
        # Vérifier dans kglobalshortcutsrc
        rc = os.path.expanduser("~/.config/kglobalshortcutsrc")
        if os.path.isfile(rc):
            with open(rc) as f:
                return "dictee.desktop" in f.read()
    return True  # GNOME/unsupported : on suppose OK

def _check_audio_available(self):
    return bool(list_audio_sources())
```

- [ ] **Step 4: Implémenter _on_test_dictee()**

```python
def _on_test_dictee(self):
    """Lance transcribe-client en sous-processus pour test."""
    self.btn_test_dictee.setText(_("⏹ Stop"))
    self.btn_test_dictee.setEnabled(True)
    self.txt_test_result.clear()

    self._test_thread = TestDicteeThread()
    self._test_thread.result.connect(self._on_test_result)
    self._test_thread.start()

class TestDicteeThread(QThread):
    result = Signal(str)

    def run(self):
        try:
            r = subprocess.run(
                ["transcribe-client"],
                capture_output=True, text=True, timeout=10
            )
            self.result.emit(r.stdout.strip() if r.returncode == 0 else _("Error: ") + r.stderr.strip())
        except subprocess.TimeoutExpired:
            self.result.emit(_("Timeout (10s)"))
        except FileNotFoundError:
            self.result.emit(_("transcribe-client not found"))

def _on_test_result(self, text):
    self.txt_test_result.setPlainText(text)
    self.btn_test_dictee.setText(_("🎤 Test dictation"))
```

- [ ] **Step 5: Connecter dans _build_wizard_ui()**

- [ ] **Step 6: Tester**

```bash
dictee-setup --wizard  # Page 5 : checks automatiques + test de dictée
```

- [ ] **Step 7: Commit**

```bash
git add dictee-setup.py
git commit -m "feat: page 5 wizard — vérifications automatiques et test de dictée"
```

---

### Task 10 : Connecter _on_apply() au wizard

**Files:**
- Modify: `dictee-setup.py` — `_on_wizard_finish()` et `_on_apply()`

- [ ] **Step 1: Adapter _on_apply() pour supporter les deux modes**

Le mode wizard utilise `self._current_asr` et `self._current_trans_backend` (strings) au lieu de ComboBox. Modifier `_on_apply()` pour lire les bonnes sources :

```python
def _on_apply(self):
    if self.wizard_mode:
        trans_data = self._current_trans_backend
        asr_backend = self._current_asr
        # Les ComboBox langue/volume existent dans les deux modes
    else:
        trans_data = self.cmb_trans_backend.currentData()
        asr_backend = self.cmb_asr_backend.currentData() or "parakeet"

    # ... reste du code identique, utiliser trans_data et asr_backend
```

- [ ] **Step 2: Sauvegarder DICTEE_AUDIO_SOURCE**

Ajouter dans `save_config()` :

```python
def save_config(..., audio_source=""):
    # ... lignes existantes ...
    if audio_source:
        f.write(f"DICTEE_AUDIO_SOURCE={audio_source}\n")
```

Et dans `_on_apply()` :
```python
audio_source = ""
if hasattr(self, 'cmb_audio_source'):
    audio_source = self.cmb_audio_source.currentData() or ""
```

- [ ] **Step 3: Tester le flux complet**

```bash
# Supprimer la config pour tester le premier lancement
mv ~/.config/dictee.conf ~/.config/dictee.conf.bak
dictee-setup  # doit s'ouvrir en mode wizard
# Naviguer les 5 pages → Terminer → vérifier dictee.conf créé
mv ~/.config/dictee.conf.bak ~/.config/dictee.conf
```

- [ ] **Step 4: Commit**

```bash
git add dictee-setup.py
git commit -m "feat: connecter _on_apply() au wizard + DICTEE_AUDIO_SOURCE"
```

---

### Task 11 : Section micro dans le mode classique

**Files:**
- Modify: `dictee-setup.py` — `_build_classic_ui()`

- [ ] **Step 1: Ajouter la section Microphone dans le formulaire classique**

Après la section "Interface visuelle" existante, ajouter un QGroupBox "Microphone" avec :
- ComboBox source audio
- Slider volume
- Barre de niveau (AudioLevelThread)

Réutiliser la même logique que la page 4 du wizard.

- [ ] **Step 2: Démarrer AudioLevelThread à l'ouverture en mode classique**

Dans `_build_classic_ui()`, démarrer le thread. L'arrêter dans `closeEvent()`.

- [ ] **Step 3: Tester**

```bash
dictee-setup  # mode classique, vérifier la section micro
```

- [ ] **Step 4: Commit**

```bash
git add dictee-setup.py
git commit -m "feat: section microphone dans le formulaire classique"
```

---

### Task 12 : i18n — nouvelles chaînes

**Files:**
- Modify: `po/dictee.pot`
- Modify: `po/{fr,de,es,it,uk,pt}.po`

- [ ] **Step 1: Extraire les nouvelles chaînes**

```bash
xgettext --language=Python --keyword=_ --output=po/dictee.pot \
    --package-name=dictee --package-version=1.1.0 \
    dictee-setup.py dictee-tray.py
```

- [ ] **Step 2: Mettre à jour les fichiers .po**

```bash
for lang in fr de es it uk pt; do
    msgmerge --update po/$lang.po po/dictee.pot
done
```

- [ ] **Step 3: Traduire les nouvelles chaînes (~30)**

Ouvrir chaque fichier `.po` et traduire les chaînes marquées `fuzzy` ou vides. Chaînes principales :
- "Welcome to dictee!", "Choose your speech recognition engine."
- "Keyboard shortcuts", "Previous", "Next", "Finish"
- "Translation", "Dictate in one language, get text in another."
- "Microphone", "Audio source:", "Volume:", "No microphone detected."
- "Let's test!", "Test dictation", "All set!"
- "Setup wizard", "Step {n} of 5"
- Etc.

- [ ] **Step 4: Compiler les .mo**

```bash
for lang in fr de es it uk pt; do
    msgfmt -o po/$lang.mo po/$lang.po
done
```

- [ ] **Step 5: Commit**

```bash
git add po/
git commit -m "feat: i18n wizard — 6 langues (fr, de, es, it, uk, pt)"
```

---

### Task 13 : Version bump 1.1.0

**Files:**
- Modify: `Cargo.toml` (version)
- Modify: `build-deb.sh` (×3 : version, pkg name, changelog)
- Modify: `pkg/dictee/DEBIAN/control` (version)
- Modify: `plasmoid/package/metadata.json` (version)
- Modify: `README.md`, `README.fr.md` (version badge/texte)

- [ ] **Step 1: Bumper tous les fichiers**

Suivre la checklist du MEMORY.md : Cargo.toml, build-deb.sh (×3), control, metadata.json, READMEs.

- [ ] **Step 2: Commit**

```bash
git add Cargo.toml build-deb.sh pkg/dictee/DEBIAN/control plasmoid/package/metadata.json README.md README.fr.md
git commit -m "chore: bump version 1.0.0 → 1.1.0"
```

---

### Task 14 : Test d'intégration final

- [ ] **Step 1: Test wizard premier lancement**

```bash
mv ~/.config/dictee.conf ~/.config/dictee.conf.bak
dictee-setup  # doit ouvrir en mode wizard automatiquement
# Naviguer toutes les pages, vérifier chaque section
# Terminer → vérifier dictee.conf créé avec toutes les clés
mv ~/.config/dictee.conf.bak ~/.config/dictee.conf
```

- [ ] **Step 2: Test wizard forcé**

```bash
dictee --setup --wizard  # doit ouvrir en wizard même avec config existante
dictee-setup --wizard    # idem
```

- [ ] **Step 3: Test mode classique**

```bash
dictee-setup  # mode classique (config existe)
# Vérifier : bouton "Assistant" présent, section micro présente
# Cliquer "Assistant" → doit relancer en wizard
```

- [ ] **Step 4: Test i18n**

```bash
LANGUAGE=de dictee-setup --wizard  # vérifier traduction allemande
LANGUAGE=es dictee-setup --wizard  # vérifier traduction espagnole
```

- [ ] **Step 5: Commit final si corrections**

```bash
git add -u
git commit -m "fix: corrections intégration wizard"
```
