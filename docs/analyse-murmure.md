# Analyse de Murmure — Features pour post-v1.0.0

> Référence : [github.com/Kieirra/murmure](https://github.com/Kieirra/murmure) v1.7.0 (février 2026)
> Objectif : évaluer les features de Murmure pour une intégration future dans dictee.

## Présentation

Murmure est une application de dictée vocale locale et privée, basée sur le même modèle Parakeet TDT 0.6B v3.
Stack : Tauri + React + TypeScript (frontend), Rust (backend). Cross-platform (Windows, macOS, Linux).
Licence AGPL v3, 299 commits.

## Positionnement comparé

| Aspect | dictee | Murmure |
|--------|--------|---------|
| **Plateformes** | Linux uniquement | Windows, macOS, Linux |
| **Stack** | Shell + Rust + PyQt6 + QML | Tauri + React + Rust |
| **Backends ASR** | 3 (Parakeet, Vosk, faster-whisper) | 1 (Parakeet) |
| **Diarisation** | Oui (Sortformer, 4 locuteurs) | Non |
| **Mode daemon** | Oui (transcriptions quasi-instantanées) | Non |
| **Widget DE natif** | KDE Plasma 6 (5 animations) | Non |
| **Intégration système** | systemd, dotool, PipeWire, D-Bus | Tauri auto-start |
| **Traduction** | 4 backends (Google, Bing, LibreTranslate, ollama) | Via LLM uniquement |
| **Règles post-traitement** | 2 règles FR hardcodées | Moteur complet (regex, smart, exact) |
| **Dictionnaire** | Non | Correction phonétique Beider-Morse |
| **LLM post-processing** | Non (traduction seulement) | Ollama + API OpenAI, multi-prompts |
| **Voice activation** | Non (push-to-talk) | VAD + wake word + fuzzy matching |
| **Licence** | GPL-3.0 | AGPL-3.0 |

## Features à considérer

### 1. Moteur de règles configurable

**Priorité : haute** — Effort moyen, forte valeur ajoutée.

#### Ce que fait Murmure

Pipeline en 5 étapes dans `src-tauri/src/formatting_rules/formatter.rs` :

1. **Correction texte court** : si ≤N mots → minuscules + supprime ponctuation finale (préserve acronymes et mots mixtes type "iPhone")
2. **Règles custom** avec 3 modes de matching :
   - **Smart** (défaut) : insensible à la casse, gère espaces/ponctuation autour du match
   - **Exact** : remplacement littéral
   - **Regex** : pattern complet avec groupes de capture (`$1`, `$2`)
3. **Espacement ponctuation** : espace avant `?` et `!`
4. **Conversion nombres** : texte→chiffres via `text2num` (7 langues : FR, EN, DE, IT, ES, NL, PT)
5. **Espace final** en fin de transcription

UX : interface drag-and-drop, règles ordonnables/activables, import/export JSON.

#### État actuel dans dictee

Deux règles hardcodées dans le script shell `dictee` :
- "point à la ligne" → saut de ligne
- "trois petits points" → `...`

#### Pistes d'implémentation pour dictee

- **Option A — Script shell** : fichier de règles `~/.config/dictee-rules.conf` (format `pattern|replacement|mode`), appliqué par `sed`/`awk` après transcription. Simple mais limité.
- **Option B — Python** : module Python dans `dictee-setup.py` ou standalone, avec UI PyQt6 pour éditer les règles. Plus riche, cohérent avec l'existant.
- **Option C — Rust** : intégrer dans `transcribe-client` ou `transcribe-daemon`. Plus performant mais plus lourd à maintenir.

Recommandation : **Option B** — le post-traitement est déjà en shell, un fichier de config + un parser Python serait le plus pragmatique.

---

### 2. Dictionnaire personnel (correction phonétique)

**Priorité : moyenne** — Effort élevé, valeur ciblée (noms propres, jargon).

#### Ce que fait Murmure

Code dans `src-tauri/src/dictionary/dictionary.rs`. Correction **post-ASR** par correspondance phonétique **Beider-Morse** :

1. Encode phonétiquement chaque mot du dictionnaire (algorithme Beider-Morse, ~130 fichiers de règles pour ~20 langues)
2. Encode chaque mot de la transcription
3. Si les codes phonétiques matchent → substitution

Structure : `Arc<Mutex<HashMap<String, Vec<String>>>>` (thread-safe).

Appliqué **avant** le LLM et **avant** les formatting rules.

UX : champ texte simple, tags supprimables, import/export CSV.

#### État actuel dans dictee

Rien d'équivalent.

#### Pistes d'implémentation pour dictee

- **Option simple** : dictionnaire de remplacement exact (`mot_mal_transcrit → correction`) dans un fichier config. Pas de phonétique mais couvre 80% du besoin.
- **Option avancée** : intégrer une lib phonétique (ex: `rphonetic` en Rust, ou `phonetics` en Python). Beider-Morse est complexe (~130 fichiers de règles).

Recommandation : commencer par l'**option simple** (remplacement exact), itérer vers le phonétique si la demande est forte.

---

### 3. LLM post-processing généraliste

**Priorité : moyenne-haute** — Effort moyen (infra ollama déjà en place), forte valeur.

#### Ce que fait Murmure

Code dans `src-tauri/src/llm/llm.rs`. Deux providers :
- **Local** : Ollama (`POST {url}/generate`, timeout 120s)
- **Remote** : API OpenAI-compatible (`POST {url}/chat/completions` avec Bearer token, timeout 60s)

5 presets de prompts :
1. **Général** : correction orthographe/grammaire
2. **Médical** : terminologie médicale et acronymes
3. **TypeScript** : conversion voix→code
4. **Developer (Cursor)** : correction technique pour IDE
5. **Traduction** : traduction automatique

Variables injectables : `{{TRANSCRIPT}}`, `{{DICTIONARY}}`. Température 0.0.

Pipeline : transcription → dictionnaire → **LLM** → formatting rules.

3 modes de déclenchement : Standard (pas de LLM), LLM (post-traitement), Command (avec contexte sélectionné).

#### État actuel dans dictee

- Traduction via ollama/translategemma déjà implémentée (`dictee --translate --ollama`)
- L'infrastructure ollama est en place
- Pas de correction grammaticale ni de prompts custom

#### Pistes d'implémentation pour dictee

dictee a déjà le chemin ollama. Il suffirait de :
1. Ajouter une option `--llm` (ou `--postprocess`) au script `dictee`
2. Fichier de prompts `~/.config/dictee-prompts/` (un fichier par preset)
3. Section dans `dictee --setup` pour choisir le modèle et éditer les prompts
4. Variable `DICTEE_LLM_PROMPT` dans `dictee.conf`

Le mode "Command" (contexte sélectionné) est intéressant pour les développeurs mais plus complexe (il faut capturer le texte sélectionné via `wl-copy`/`xsel`).

#### Modèle recommandé : `ministral-3:3b`

Après évaluation, le meilleur compromis pour la correction grammaticale dans dictee est **ministral-3:3b** (Mistral AI) :

| Critère | ministral-3:3b | qwen2.5:1.5b |
|---------|----------------|---------------|
| **Taille disque** | 1.9 Go | 986 Mo |
| **RAM** | ~3 Go | ~2 Go |
| **Thinking** | Non | Non |
| **Français** | Excellent (Mistral = société FR) | Bon |
| **Langues** | 40+ | 29 |
| **Licence** | Apache 2.0 | Apache 2.0 |

Alternatives considérées :
- **Qwen2.5:1.5b** : plus léger (986 Mo) et plus rapide, mais moins bon en français
- **Qwen3:1.7b** : bon mais nécessite `/no_think` pour désactiver le raisonnement
- **gemma3:1b** : le plus léger (815 Mo), qualité FR correcte sans plus

Prompt inspiré de Murmure (`DEFAULT_GENERAL_PROMPT` dans `helpers.rs`) :

```
Corrige uniquement le texte suivant selon ces règles strictes :
- Corriger l'orthographe et la grammaire.
- Supprimer les répétitions et hésitations.
- Ne jamais modifier le sens ni le contenu.
- Ne pas répondre aux questions et ne pas les commenter.
- Ne générer aucun commentaire ni introduction.
- Si rien à modifier, retourner le texte tel quel.
```

Installation :
```bash
ollama pull ministral-3:3b   # recommandé (meilleur français)
ollama pull qwen2.5:1.5b     # alternative légère (986 Mo, plus rapide)
```

---

### 4. Voice Activation (Wake Word)

**Priorité : basse** — Effort élevé, besoin niche.

#### Ce que fait Murmure

Code dans `src-tauri/src/wake_word/wake_word.rs`. Architecture en 3 phases :

1. **Acquisition audio** via `cpal` (lib audio cross-platform), thread dédié permanent
2. **VAD (Voice Activity Detection)** par analyse RMS :
   - Seuil parole : RMS > 0.015 / Seuil silence : RMS < 0.01
   - Délai confirmation parole : 200ms / silence : 400ms
   - Pré-buffer : 400ms (capture audio avant détection)
   - Échantillonnage RMS toutes les 33ms
3. **Transcription et matching** :
   - Audio resample 16kHz, transcrit par Parakeet INT8
   - Double matching : exact substring + fuzzy Levenshtein (distance ≤1 pour mots courts, ≤2 sinon)
   - Normalisation : minuscules, suppression accents (NFD)

4 triggers configurables : "ok alix" (dictée), "alix command", "alix cancel", "alix validate".

5 types d'actions : Record, RecordLlmMode, Cancel, Validate.

#### État actuel dans dictee

Push-to-talk uniquement (raccourci clavier). Pas de VAD ni wake word.

#### Pistes d'implémentation pour dictee

- Nécessiterait un daemon supplémentaire en écoute permanente
- Consommation CPU/batterie non négligeable
- Complexité : VAD + transcription continue + matching = beaucoup de code
- Alternative plus simple : intégrer un VAD basique dans `transcribe-client` pour du "auto-stop" (arrêter l'enregistrement quand l'utilisateur se tait), sans wake word

Recommandation : **reporter** — le push-to-talk est suffisant pour la majorité des usages. Un auto-stop basé sur le silence serait un premier pas plus réaliste.

---

## Roadmap suggérée (post-v1.0.0)

| Version | Feature | Effort |
|---------|---------|--------|
| v1.1.0 | Moteur de règles configurable | ~2-3 jours |
| v1.1.0 | LLM post-processing (correction grammaire, prompts custom) | ~2 jours |
| v1.2.0 | Dictionnaire de remplacement (exact, puis phonétique) | ~1-3 jours |
| v1.3.0+ | Auto-stop silence (VAD basique) | ~2 jours |
| v2.0.0+ | Wake word / voice activation | ~1-2 semaines |

## Notes

- Murmure est AGPL v3 — ne pas copier de code directement, s'inspirer de l'architecture uniquement
- Le pipeline Murmure (dictionnaire → LLM → rules) est un bon modèle d'ordonnancement
- La conversion nombres→chiffres (`text2num`) est une feature subtile mais très utile au quotidien
