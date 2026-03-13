# Wizard de configuration — dictee v1.1.0

## Résumé

Ajouter un assistant de configuration pas-à-pas (wizard) à `dictee-setup.py` pour guider les nouveaux utilisateurs. Le wizard se déclenche au premier lancement (absence de `~/.config/dictee.conf`) et reste accessible via un bouton "Assistant de configuration" dans le formulaire classique, ou via `dictee --setup --wizard`.

## Architecture

### Approche : QStackedWidget dans DicteeSetupDialog

Un `QStackedWidget` avec 5 pages est ajouté dans le dialog existant. Les widgets sont partagés entre les modes wizard et classique — pas de duplication de code.

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
  - bouton "Assistant de configuration" cliqué dans le mode classique
```

### Widgets partagés

Les widgets (ComboBox, ShortcutButton, checkboxes, sliders) sont créés une seule fois dans `__init__()`. En mode wizard, ils sont déplacés dans les pages du `QStackedWidget`. En mode classique, ils sont dans le `QScrollArea` comme actuellement.

## Pages du wizard

### Page 1 — Bienvenue + Backend ASR

**Contenu :**
- Message de bienvenue
- Choix du backend ASR via **radio buttons visuels** (blocs cliquables, pas ComboBox) :
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
- Détection de conflit en temps réel (kglobalshortcutsrc / gsettings)
- Message d'avertissement si conflit détecté

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

### Page 4 — Interface visuelle, micro et services

**Contenu :**

#### Microphone
- **Sélection de la source audio** — ComboBox listant les sources PipeWire/PulseAudio détectées (`wpctl status` ou `pactl list sources short`)
- **Slider volume micro** — contrôle via `wpctl set-volume` ou `pactl set-source-volume`
- **Indicateur de niveau temps réel** — barre animée (parec/pw-record) pour vérifier la capture
- Détection et proposition de démuter si le micro est muté

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
- Bouton "Tester la dictée" — lance `dictee` en mode test (enregistre quelques secondes, transcrit, affiche le résultat)
- Zone de résultat avec le texte transcrit
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
- Cliquer dessus bascule en mode wizard
- Tout le reste du formulaire classique reste identique
- Ajout de la section **Microphone** (source, volume, niveau) dans le formulaire classique aussi

## Argument CLI

```bash
dictee --setup           # classique si config existe, wizard sinon
dictee --setup --wizard  # force le mode wizard
```

## Détection des sources audio

```python
def list_audio_sources():
    """Liste les sources micro via wpctl ou pactl."""
    # 1. Essayer wpctl status → parser les Sources
    # 2. Fallback pactl list sources short
    # Retourne: [(id, name, description), ...]
```

## Fichiers modifiés

| Fichier | Modification |
|---------|-------------|
| `dictee-setup.py` | QStackedWidget, 5 pages wizard, section micro, bouton assistant |

**Estimation :** ~350-400 lignes ajoutées (1945 → ~2300-2350 lignes).

## Ce qui ne change pas

- `save_config()` / `load_config()` — inchangés
- `_on_apply()` — inchangé (le wizard appelle la même fonction)
- Threads de téléchargement — inchangés
- Gestion des raccourcis KDE/GNOME — inchangée
- Format de `~/.config/dictee.conf` — inchangé
