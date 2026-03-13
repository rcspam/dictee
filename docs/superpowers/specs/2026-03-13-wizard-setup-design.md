# Wizard de configuration — dictee v1.1.0

## Résumé

Ajouter un assistant de configuration pas-à-pas (wizard) à `dictee-setup.py` pour guider les nouveaux utilisateurs. Le wizard se déclenche au premier lancement (absence de `~/.config/dictee.conf`) et reste accessible via un bouton "Assistant de configuration" dans le formulaire classique, ou via `dictee --setup --wizard`.

## Architecture

### Approche : QStackedWidget dans DicteeSetupDialog

Un `QStackedWidget` avec 5 pages est ajouté dans le dialog existant. Le mode (wizard ou classique) est déterminé **une seule fois au démarrage** dans `__init__()`.

```
DicteeSetupDialog
├── self.wizard_mode: bool
├── self.stack: QStackedWidget (5 pages)  ← mode wizard
├── self.scroll: QScrollArea              ← mode classique (existant)
└── Barre de navigation: Précédent | (n/5) | Suivant/Terminer
```

### Détection du mode

```python
wizard_mode = True si:
  - ~/.config/dictee.conf n'existe pas (premier lancement)
  - argument --wizard passé en ligne de commande
  - bouton "Assistant de configuration" cliqué → ferme et relance en mode wizard
```

### Construction conditionnelle (pas de re-parenting)

Les widgets sont créés une seule fois dans `__init__()` et placés **directement** dans le bon conteneur selon `self.wizard_mode` :

- **Mode wizard** → les widgets sont ajoutés dans les pages du `QStackedWidget`
- **Mode classique** → les widgets sont ajoutés dans le `QScrollArea` (comme actuellement)

Il n'y a **pas de déplacement dynamique** de widgets entre les modes. Le bouton "Assistant de configuration" en mode classique **ferme le dialog et relance** `dictee-setup.py --wizard` (nouveau processus).

### Radio buttons visuels vs ComboBox

Le **mode wizard** utilise des radio buttons visuels (blocs cliquables) pour ASR et traduction — plus guidé, plus clair pour un premier contact.

Le **mode classique** conserve les `QComboBox` existantes — compact, familier pour les utilisateurs récurrents.

Les deux modes utilisent la même variable interne (`self.asr_backend`, `self.trans_backend`). Les radio buttons et la ComboBox sont créés de manière conditionnelle :

```python
if self.wizard_mode:
    self._build_asr_radio_buttons()   # crée des QFrame cliquables
else:
    self._build_asr_combobox()        # QComboBox existante
```

## Pages du wizard

### Page 1 — Bienvenue + Backend ASR

**Contenu :**
- Message de bienvenue
- Choix du backend ASR via **radio buttons visuels** (blocs cliquables) :
  - Parakeet-TDT 0.6B (recommandé) — 25 langues, ~2,5 Go, ~0,8s
  - Vosk (léger) — 9+ langues, ~50 Mo, ~1,5s
  - faster-whisper (99 langues) — ~500 Mo–3 Go, ~0,3s
- Statut d'installation des modèles (✓ installé / ⚠ bouton Télécharger)
- Sous-options conditionnelles : langue Vosk, modèle Whisper (apparaissent sous le choix sélectionné)

**Validation avant "Suivant" :**
- Le modèle principal du backend sélectionné doit être installé (ou téléchargement en cours)

### Page 2 — Raccourcis clavier

**Contenu :**
- Environnement détecté (KDE Plasma / GNOME / tiling WM)
- Deux `ShortcutButton` pour capturer les raccourcis :
  - Dictée vocale (défaut : F9)
  - Dictée + Traduction (défaut : Alt+F9)
- Détection de conflit en temps réel :
  - **KDE** : via `check_kde_conflict()` existant (kglobalshortcutsrc)
  - **GNOME** : hors-scope v1.1.0 (pas de détection de conflit, juste écriture gsettings)
- Message d'avertissement si conflit détecté (KDE uniquement)

**Cas particulier WM tiling :**
- Pas de boutons de capture
- Affiche les commandes à ajouter manuellement à la config Sway/i3/Hyprland

**Validation :** aucune — les raccourcis par défaut sont toujours valides.

### Page 3 — Traduction

**Contenu :**
- Langues source/cible côte à côte (pré-remplies depuis la locale système)
- Choix du backend via radio buttons visuels, **locaux en premier** :
  1. **ollama** (100% local, meilleure qualité) — 2,3–3,4s
  2. **LibreTranslate** (100% local) — Docker ~2 Go, 0,1–0,3s
  3. **Google Translate** (en ligne, rapide) — 0,2–0,7s
  4. **Bing** (en ligne) — 1,7–2,2s
- Sous-options conditionnelles : modèle ollama, port LibreTranslate, téléchargement
- Détection automatique des dépendances (ollama installé ? Docker accessible ? translate-shell ?)

**Pas de toggle d'activation** — la traduction est optionnelle par nature (raccourci dédié).

**Validation :** aucune — la configuration de traduction est toujours valide.

### Page 4 — Microphone, interface visuelle et services

**Contenu :**

#### Microphone
- **Sélection de la source audio** — ComboBox listant les sources PipeWire/PulseAudio détectées
- **Slider volume micro** — contrôle via `wpctl set-volume` ou `pactl set-source-volume`
- **Indicateur de niveau temps réel** — `QProgressBar` mis à jour par un `QThread` qui lit `parec` (PulseAudio) ou `pw-record` (PipeWire) via un pipe, calcule le RMS sur des blocs de 100ms, émet un signal `level(int)`. Rafraîchissement ~10 Hz.
- Détection et proposition de démuter si le micro est muté
- **Si aucun micro détecté** : message d'avertissement non-bloquant "Aucun microphone détecté. Vérifiez votre connexion audio." Le wizard continue normalement.

#### Retour visuel
- **Multi-sélection** (checkboxes, pas radio — on peut combiner) :
  - Widget KDE Plasma (recommandé si KDE détecté)
  - animation-speech (overlay plein écran, Wayland)
  - Icône de notification (dictee-tray, pour non-KDE)
- Détection environnement → pré-coche intelligente :
  - KDE → plasmoid coché
  - GNOME/Xfce/Sway → tray coché
- Bouton "Installer" intégré si animation-speech ou plasmoid manquant

#### Services au démarrage
- Toggle : démarrer le daemon de transcription au login (ON par défaut)
- Toggle : copier la transcription dans le presse-papiers (OFF par défaut)

**Validation :** aucune.

### Page 5 — Test

**Contenu :**

#### Vérifications automatiques
Lancées dès l'arrivée sur la page :
- Daemon ASR actif (systemctl --user is-active)
- Modèle installé
- Raccourci enregistré (kglobalshortcutsrc / gsettings)
- Audio détecté (PipeWire/PulseAudio)
- dotool fonctionnel

Chaque check : ✓ vert si OK, ✗ rouge + bouton "Réparer" qui retourne à la page concernée.

#### Test de dictée
- Bouton "Tester la dictée" — appelle directement `transcribe-client` en sous-processus (le binaire Rust qui enregistre le micro et envoie au daemon via socket Unix). Capture stdout (le texte transcrit) et l'affiche dans un `QTextEdit` en lecture seule.
- Pas besoin de `dotool` ni de mode `--test` dans le script `dictee` — on court-circuite la chaîne.
- Timeout de 10 secondes. Le bouton passe en "Arrêter" pendant l'enregistrement.
- **Optionnel** — "Terminer" est toujours cliquable sans avoir testé

#### Message final
- "Tout est prêt !" avec rappel du raccourci configuré

**Bouton "Terminer"** (vert) → appelle `_on_apply()`, sauvegarde config, ferme le wizard.

## Navigation

```
[Précédent]  Étape n sur 5  [Suivant →]     (pages 1-4)
[Précédent]  Étape 5 sur 5  [✓ Terminer]    (page 5)
```

- "Précédent" désactivé sur la page 1
- "Suivant" valide la page courante avant d'avancer
- "Terminer" appelle `_on_apply()` (même fonction que le formulaire classique)
- Indicateur de progression textuel "Étape n sur 5"

## Mode classique — modifications

- Ajout d'un bouton **"Assistant de configuration"** en bas à gauche (à côté de Cancel)
- Cliquer dessus **ferme le dialog et relance** `dictee-setup --wizard`
- Ajout de la section **Microphone** (source, volume, niveau) dans le formulaire classique aussi
- Tout le reste du formulaire classique reste identique

## Argument CLI

```bash
dictee --setup           # classique si config existe, wizard sinon
dictee --setup --wizard  # force le mode wizard
```

Le script `dictee` transmet `--wizard` à `dictee-setup` si présent.

## Nouvelles clés de configuration

```bash
# Ajoutées à ~/.config/dictee.conf
DICTEE_AUDIO_SOURCE=alsa_input.pci-0000_00_1f.3.analog-stereo  # ID source PipeWire/PA
```

Le volume micro n'est **pas persisté** dans dictee.conf — il est appliqué immédiatement via `wpctl`/`pactl` et le système audio le retient. La source audio est persistée pour pouvoir la restaurer.

## Détection des sources audio

```python
def list_audio_sources():
    """Liste les sources micro via wpctl ou pactl."""
    # 1. Essayer wpctl status → parser les Sources (section Audio/Sources)
    # 2. Fallback pactl list sources short
    # Retourne: [(id, name, description), ...]
    # Retourne [] si aucun outil disponible

class AudioLevelThread(QThread):
    """Lit le micro en continu, émet le niveau RMS."""
    level = Signal(int)  # 0-100

    def run(self):
        # Lance parec (PA) ou pw-record (PipeWire) en subprocess
        # Lit des blocs de 1600 échantillons (100ms à 16kHz, mono, s16le)
        # Calcule RMS → normalise 0-100 → émet signal level
        # Se termine proprement quand self._running = False
```

## Fichiers modifiés

| Fichier | Modification |
|---------|-------------|
| `dictee-setup.py` | QStackedWidget, 5 pages wizard, section micro, AudioLevelThread, radio buttons visuels, bouton assistant |
| `dictee` (script shell) | Transmission de `--wizard` à `dictee-setup` |
| `po/dictee.pot` | Nouvelles chaînes wizard (~30 chaînes) |
| `po/{fr,de,es,it,uk,pt}.po` | Traductions des nouvelles chaînes |

**Estimation :** ~500-600 lignes ajoutées à `dictee-setup.py` (1945 → ~2500-2550 lignes).

## Ce qui ne change pas

- `_on_apply()` — inchangé (le wizard appelle la même fonction)
- Threads de téléchargement (ModelDownloadThread, VenvInstallThread, etc.) — inchangés
- Gestion des raccourcis KDE/GNOME — inchangée
- Format général de `~/.config/dictee.conf` — étendu (nouvelle clé `DICTEE_AUDIO_SOURCE`)

## Hors-scope v1.1.0

- Détection de conflit raccourci GNOME
- Support aarch64 pré-compilé (compilation depuis les sources uniquement)
- Mode `dictee --test` dans le script shell
