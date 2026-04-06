# Analyse des issues GitHub de Handy (cjpais/Handy) — avril 2026

Handy : application STT open-source (Rust/Tauri v2), 19 304 étoiles, multiplateforme, offline. ~100 issues ouvertes.

## Idées à récupérer pour dictee

### Haute priorité

#### Rejet audio silencieux (#1229)
Seuil RMS energy (0.005) + durée minimum (100ms) pour éviter les hallucinations Whisper/Parakeet. Simple et directement applicable à tous les backends de dictee.

#### Contexte LLM enrichi (#704, 2 reactions)
3 nouvelles variables pour le post-traitement LLM :
- `$current_app` : identifie l'appli active (via `xdotool getactivewindow getwindowpid` ou D-Bus KDE) pour contextualiser le LLM
- `$short_prev_transcript` : 200 derniers mots de la même appli, expire après 5 min
- `$time_local` : heure locale

Permet au LLM d'adapter sa correction selon le contexte (email vs terminal vs code).

#### Transcription hook (#930, 5 reactions)
Exécuter un script/commande après chaque transcription. Utile pour :
- Logging/stats
- Intégrations externes (Slack, notes, etc.)
- Post-traitement custom

### Moyenne priorité

#### Text replacements GUI (#455, 15 reactions, 25 comments)
Feature la plus votée après la transcription de fichiers. Équivalent de notre `rules.conf` mais avec une interface graphique dédiée. On a déjà l'éditeur avancé dans setup — mais on pourrait améliorer l'UX.

#### Chunking/streaming revisité (#1173, 4 reactions)
Le mainteneur explore le même sujet que notre `post-v1-chunking-streaming.md`. Confirme la pertinence.

#### Auto-tune threads ORT (#1120)
Réglage automatique du nombre de threads ORT + benchmark. Pertinent pour optimiser les performances.

#### Custom transcription prompt (#1227)
Prompt initial pour guider Whisper (noms propres, vocabulaire technique). Applicable si on ajoute un backend Whisper avec `initial_prompt`.

#### Reasoning effort passthrough (#1221)
Éviter la latence du mode "thinking" sur les modèles locaux. Pertinent pour notre intégration Ollama — on pourrait passer `--think=false` ou `num_predict` limité.

### Basse priorité / exploratoire

- **Wake-word** (#618, 2 reactions) : mot-clé vocal pour déclencher la dictée sans raccourci
- **Suivre la langue d'entrée de l'OS** (#559, 4 reactions) : auto-détection de la langue du clavier
- **Pause-while-recording** (#1028) : pause/reprise pendant l'enregistrement
- **Liste priorisée de microphones** (#1070) : au lieu d'un seul sélecteur
- **Flatpak packaging** (#548, 8 reactions)
- **Qwen3-ASR** (#957) et **FireRedASR-AED** (#1141) comme moteurs alternatifs
- **Serveur API local style OpenAI** (#509, 3 reactions) : dictee a déjà le daemon socket Unix

---

## Issues les plus discutées / critiques

| # | Titre | Comments | Reactions |
|---|-------|----------|-----------|
| 96 | Changement de raccourci ne fonctionne pas | 61 | 5 |
| 455 | Text replacements feature | 25 | 15 |
| 381 | Transcription de fichiers locaux | 25 | 21 |
| 502 | Colle le clipboard au lieu du texte dicté | 38 | 0 |
| 261 | Whisper models crash | 41 | 0 |
| 429 | Premier caractère manquant (GNOME/Wayland) | 36 | 9 |
| 102 | Raccourci clavier Ubuntu 22.04 | 38 | 11 |
| 548 | Flatpak packaging | 18 | 8 |

---

## Bugs qu'on évite déjà

### Clipboard écrasé (#502, 38 comments, critique)
Handy utilise copier-coller pour insérer le texte → le clipboard est écrasé. Dictee utilise `dotool`/`wtype` direct → pas ce problème.

### Raccourcis clavier cassés (#96, #102, #844, #1019, #1105)
99 comments cumulés. Multi-DE (GNOME, KDE, Sway) × multi-protocole (X11, Wayland). Notre approche `/dev/input` + KDE global shortcuts est plus robuste.

### Fenêtre cible pas focusée (#315)
Identique à notre `project-dotool-safety.md`. Handy a le même problème.

### Premier caractère manquant (#429, 36 comments)
Direct paste sur GNOME/Wayland perd le premier caractère. Notre approche `wtype` avec délai initial évite ça.

### wtype failures silencieuses (#522, 2 reactions)
Dictee utilise aussi wtype — on doit surveiller ce problème.

---

## Confirmation de nos choix techniques

1. **Parakeet + ORT CUDA** (#1165, #1203) : Handy a exactement les mêmes problèmes que nous. Le mainteneur explore ORT CUDA en ce moment.
2. **Le clipboard est un piège universel** : 5 issues critiques chez Handy. Notre `dotool`/`wtype` est validé.
3. **Chunking/streaming** (#1173) : sujet actif chez Handy, confirme `post-v1-chunking-streaming.md`.
4. **Text replacements** (#455, 15 reactions) = feature la plus votée. On a déjà `rules.conf` + éditeur avancé.
5. **Chemins cyrilliques** (#574, #1187) : Handy a le même bug que notre `project-cyrillic-misdetection.md`.

---

## Bugs Parakeet/ORT partagés

- **#1165** (22 comments) : Parakeet Transcription Failures depuis v0.8. Échecs fréquents. Même stack que dictee.
- **#1203** : Le mainteneur explore ORT avec CUDA.
- **#574** : Parakeet échoue avec chemins Unicode/cyrilliques.
- **#1187** (3 reactions) : Fix chemins cyrilliques en cours.

## Bugs Linux/KDE spécifiques

- **#1121** (18 comments) : Overlay cassé sur KDE Linux.
- **#1042** (26 comments) : Titlebar controls Wayland.
- **#689** (21 comments, 4 reactions) : Remote desktop direct mode Wayland.
- **#806** : Pop!_OS PipeWire — cpal sonde OSS mais échoue avec ALSA input.
