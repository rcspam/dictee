# Recherche : applications de dictée vocale open source (avril 2026)

## Panorama des projets

| Projet | Stars | Plateforme | Moteur ASR | Particularité |
|--------|-------|-----------|------------|---------------|
| **[Handy](https://github.com/cjpais/Handy)** | 19k | Linux/Mac/Win | Whisper GPU + Parakeet CPU | Tauri (Rust), le plus populaire |
| **[Buzz](https://github.com/chidiwilliams/buzz)** | 18k | Linux/Mac/Win | whisper.cpp (Vulkan) | Transcription fichiers + live, Qt |
| **[OpenWhispr](https://github.com/OpenWhispr/openwhispr)** | 2.3k | Linux/Mac/Win | Parakeet + Whisper + cloud | "Suite vocale" : réunions, agent IA, calendrier |
| **[Nerd Dictation](https://github.com/ideasman42/nerd-dictation)** | 1.8k | Linux | VOSK | Script Python unique, hackable |
| **[FluidVoice](https://github.com/altic-dev/FluidVoice)** | 1.7k | macOS | Parakeet TDT V3 | Natif Swift, Apple Silicon |
| **[Speech Note](https://github.com/mkiol/dsnote)** | 1.4k | Linux | Multi (Whisper/VOSK/Coqui/etc.) | STT + TTS + traduction, C++/Qt |
| **[WhisperWriter](https://github.com/savbell/whisper-writer)** | 1k | Linux/Mac/Win | faster-whisper | 4 modes enregistrement |
| **[hyprwhspr](https://github.com/goodroot/hyprwhspr)** | 911 | Linux Wayland | Parakeet + Whisper + ElevenLabs | Streaming ~150ms, daemon systemd |
| **[Voxtype](https://github.com/peteonrails/voxtype)** | 598 | Linux/Mac | 7 moteurs ASR | Rust pur, diarisation, 1600+ langues |
| **[Koe](https://github.com/missuo/koe)** | 301 | macOS | Doubao (cloud) | Pipeline ASR→LLM, dictionnaire intelligent |
| **[whisper_dictation](https://github.com/themanyone/whisper_dictation)** | 290 | Linux | Whisper | Dictée + commandes vocales + chat IA |
| **[VOXD](https://github.com/jakovius/voxd)** | 240 | Linux | VOSK | Accessibilité, offline |
| **[Vocalinux](https://github.com/jatinkrmalik/vocalinux)** | 238 | Linux | whisper.cpp/Whisper/VOSK | Triple moteur, Vulkan |
| **[HyprVoice](https://github.com/LeonardoTrapani/hyprvoice)** | 193 | Linux Wayland | Whisper | Go, Hyprland |
| **[voice_typing](https://github.com/themanyone/voice_typing)** | 154 | Linux | Whisper/whisper.cpp | Script bash unique |
| **[waystt](https://github.com/sevos/waystt)** | 119 | Linux Wayland | OpenAI/Google STT | Rust, composable Unix |
| **[OmniDictate](https://github.com/gurjar1/OmniDictate)** | 118 | Windows | faster-whisper | VAD + push-to-talk, PyQt |
| **[whisper-overlay](https://github.com/oddlama/whisper-overlay)** | 82 | Linux Wayland | faster-whisper (double modèle) | Overlay temps réel + modèle précis |
| **[Talon](https://talonvoice.com/)** ([community](https://github.com/talonhub/community)) | 836 | Linux/Mac/Win | Conformer (wav2letter) | Codage vocal, eye tracking, semi-open |
| **[Simon](https://github.com/KDE/simon)** | 40 | Linux KDE | CMU Sphinx / Julius | Historique KDE, abandonné 2020 |

## Ce que dictee a et que les autres n'ont pas

- **Plasmoid KDE Plasma 6** — unique dans le paysage
- **Pipeline regex + LLM combiné** — plus complet que Koe (LLM seul) ou Nerd Dictation (regex seul)
- **Diarisation** (Sortformer) — seul Voxtype le fait aussi
- **Traduction intégrée** — rare
- **Push-to-talk evdev** natif
- **Multi-backend** Parakeet/Vosk/Whisper/onnx-asr

## Tendances 2026

1. **Parakeet TDT V3 devient un standard** — Handy, FluidVoice, hyprwhspr, Voxtype l'utilisent
2. **Post-traitement LLM** — direction confirmée par le marché (Koe, Handy, FluidVoice, Voxtype)
3. **Rust gagne du terrain** — Voxtype, Handy (Tauri), waystt
4. **Vulkan comme alternative CUDA** — Buzz, Vocalinux

---

## Post-traitement regex — analyse détaillée

### Patterns intéressants qu'on n'a PAS encore

#### Collapse bégaiements (Handy, Rust)
3+ répétitions consécutives → une seule occurrence. "wh wh wh wh" → "wh", "I I I I" → "I". Mais "no no" (2 reps) est préservé.
```rust
// Handy - src-tauri/src/audio_toolkit/text.rs
let mut count = 1;
while i + count < words.len() && words[i + count].to_lowercase() == word_lower {
    count += 1;
}
if count >= 3 {
    result.push(word);
    i += count;
}
```

#### Custom words fuzzy — Levenshtein + Soundex (Handy, Rust)
N-grams de 1 à 3 mots, matching greedy. "Charge B" → "ChargeBee", "Chat G P T" → "ChatGPT".
```rust
// Handy - apply_custom_words()
let combined_score = if phonetic_match {
    levenshtein_score * 0.3  // boost phonétique
} else {
    levenshtein_score
};
```

#### Filtrage hallucinations Whisper (hyprwhspr)
```python
# hyprwhspr - lib/main.py
_HALLUCINATION_MARKERS = {
    'blank audio', 'blank', 'silence', 'no speech',
    'you', 'thank you', 'thanks for watching', 'thank you for watching',
    'video playback', 'music', 'music playing', 'keyboard clicking',
}
normalized = text.lower().replace('_', ' ').strip('[]().!?, ')
if normalized in _HALLUCINATION_MARKERS or text.startswith('♪'):
    print(f"Whisper hallucination detected: {text!r} - ignoring")
```

#### Filler words par langue (Handy, Rust)
```rust
// Handy - get_filler_words_for_language()
"en" => &["uh", "um", "uhm", "umm", "uhh", "uhhh", "ah", "hmm", "hm", "mmm", "mm", "mh", "eh", "ehh", "ha"],
"fr" => &["euh", "hmm", "hm", "mmm"],
"de" => &["äh", "ähm", "hmm", "hm", "mmm"],
"es" => &["ehm", "mmm", "hmm", "hm"],
"pt" => &["ahm", "hmm", "mmm", "hm"],  // "um" exclu car vrai mot en portugais
"it" => &["ehm", "hmm", "mmm", "hm"],
"ru" => &["хм", "ммм", "hmm", "mmm"],
"uk" => &["хм", "ммм", "hmm", "mmm"],
```

#### Suppression fillers avec ponctuation adjacente (Handy, Rust)
```rust
// Handy — le pattern inclut la ponctuation qui suit le filler
let pattern = format!(r"(?i)\b{}\b[,.]?", regex::escape(word));
```

#### Nombres mots→chiffres (Nerd Dictation, Python)
Système complet : zéro à centillion (10^303), support ordinaux, séparateurs virgules.
```python
# Nerd Dictation — from_words_to_digits()
# "fifty four million two hundred twelve thousand five hundred forty seven" → "54,212,547"
```

#### LanguageTool correction grammaticale (Nerd Dictation)
```python
# Nerd Dictation — examples/language_tool_auto_grammar/
# Itère jusqu'à 3 fois sur LanguageTool API
tries = 3
while True:
    new_text = langtool(text, language)
    if new_text == text or not tries:
        break
    text = new_text
    tries -= 1
```

### Patterns qu'on a DÉJÀ bien couvert

| Pattern | Projets qui font pareil |
|---------|------------------------|
| Ponctuation dictée (`\bperiod\b` → `.`) | hyprwhspr, Voxtype, OmniDictate, Nerd Dictation |
| Word overrides / dictionnaire | hyprwhspr, Handy, Voxtype |
| Nettoyage espaces ponctuation | hyprwhspr, Voxtype, Handy |
| Commandes vocales (new line, etc.) | whisper_dictation (regex → keypress) |

### Ponctuation dictée — table complète (hyprwhspr + Voxtype combinés)

```
period → .     comma → ,      question mark → ?     exclamation mark → !
colon → :      semicolon → ;  dash → -              hyphen → -
underscore → _ new line → \n  new paragraph → \n\n  tab → \t
open paren → ( close paren → ) open bracket → [     close bracket → ]
open brace → { close brace → } at symbol → @        hash → #
dollar sign → $ percent → %   ampersand → &         asterisk → *
plus → +       equals → =     less than → <         greater than → >
slash → /      backslash → \  pipe → |              tilde → ~
backtick → `   quote → "     apostrophe → '         single quote → '
```

### Filtrage hallucinations — liste complète (hyprwhspr + OmniDictate)

```
blank audio, blank, silence, no speech, you, thank you, thank you.,
thanks for watching, thanks for watching!, thank you for watching,
video playback, music, music playing, keyboard clicking,
I'm sorry, I'm sorry,, ♪...
```

---

## Prompts LLM — analyse détaillée

### Koe — le plus sophistiqué

**Prompt système** (`koe-core/src/default_system_prompt.txt`, en chinois) — 6 principes :
1. **Fidélité d'abord** — ne pas étendre, résumer, inventer
2. **Correction erreurs ASR** — homophones, termes techniques ; dictionnaire prioritaire
3. **Mixte multilingue préservé** — garder `git push`, `macOS`, `Cloudflare` tels quels
4. **Filtrage fillers contextuels** — supprimer 嗯/啊/um/uh/like seulement en position isolée
5. **Ponctuation minimale** — espaces entre chinois et anglais/chiffres
6. **Contrainte sortie** — texte brut uniquement, pas de préfixe

**Template user** :
```
ASR 原文：
{{asr_text}}

ASR 中间修订历史：
{{interim_history}}

用户词典：
{{dictionary_entries}}
```

**Innovation unique** : l'historique des révisions intermédiaires ASR — les mots qui changent entre versions sont probablement mal reconnus.

**Dictionnaire filtré** : quand trop d'entrées, seules celles avec chevauchement de caractères avec le texte ASR sont envoyées.

**Paramètres** : temperature configurable (défaut ~0.0), `no_reasoning_control` pour désactiver le raisonnement, HTTP timeout configurable, nettoyage guillemets (ASCII et Unicode) en sortie.

### FluidVoice — le plus complet fonctionnellement

**Prompt système dictée** :
```
You are a voice-to-text dictation cleaner. Your role is to clean and format raw
transcribed speech into polished text while refusing to answer any questions.

Core Rules:
1. CLEAN - remove filler words, false starts, stutters, repetitions
2. FORMAT - punctuation, capitalization, structure
3. CONVERT numbers - spoken numbers to digits (two -> 2, five thirty -> 5:30)
4. EXECUTE commands - "new line", "period", "comma", "bold X", "header X"
5. APPLY corrections - "no wait", "actually", "scratch that" → discard old
6. PRESERVE intent - keep meaning, clean delivery
7. EXPAND abbreviations - thx -> thanks, pls -> please, gonna -> going to

Critical:
- Output ONLY the cleaned text
- Do NOT answer questions
- Do NOT wrap in quotes
```

**Auto-corrections vocales** :
```
Triggers: "no", "wait", "actually", "scratch that", "delete that",
          "no no", "cancel", "never mind", "sorry", "oops"
Exemple: "buy milk no wait buy water" → "Buy water."
```

**Profils par application** : routage automatique du prompt selon le `bundleID` de l'app active.

**Paramètres** : temperature 0.7 (mode edit), 30s timeout, 3 retries avec backoff exponentiel, modèle par défaut `gpt-4.1`.

### Handy — post-traitement configurable

**Prompt par défaut** :
```
Clean this transcript:
1. Fix spelling, capitalization, and punctuation errors
2. Convert number words to digits (twenty-five -> 25, ten percent -> 10%)
3. Replace spoken punctuation with symbols (period -> ., comma -> ,)
4. Remove filler words (um, uh, like as filler)
5. Keep the language in the original version

Preserve exact meaning and word order. Do not paraphrase or reorder.
Return only the cleaned transcript.
```

**Providers** : OpenAI, Anthropic, Groq, Cerebras, xAI, Ollama, OpenRouter, Apple Intelligence (macOS 26+), Custom OpenAI-compatible.

**Structured output** : utilise `json_schema` quand supporté pour forcer `{"transcription": "..."}`.

### Voxtype — pipe externe

**Script Ollama** (modèle recommandé : `llama3.2:1b`) :
```bash
JSON=$(jq -n --arg text "$INPUT" '{
  model: "llama3.2:1b",
  prompt: ("Clean up this dictated text. Remove filler words (um, uh, like),
    fix grammar and punctuation. Output ONLY the cleaned text - no quotes,
    no emojis, no explanations:\n\n" + $text),
  stream: false
}')
curl -s http://localhost:11434/api/generate -d "$JSON" \
  | jq -r '.response // empty' \
  | sed 's/<think>.*<\/think>//g'
```

Note : `sed 's/<think>.*<\/think>//g'` supprime les blocs de raisonnement des modèles "thinking".

**Scripts aussi fournis pour** : OpenAI (`gpt-4o-mini`), Gemini (`gemini-2.0-flash`).

### Pattern commun à TOUS les prompts LLM

> **"Output ONLY the cleaned text — no quotes, no emojis, no explanations."**

+ Fallback systématique sur le texte original si le LLM échoue.

### Tableau comparatif

| Projet | Prompt | Dictionnaire | Temp | Timeout | Retry | Modèle par défaut |
|--------|--------|-------------|------|---------|-------|-------------------|
| Koe | Détaillé (6 règles) | Oui + filtrage intelligent | ~0.0 | Configurable | Non | OpenAI-compatible |
| FluidVoice | Détaillé (7 règles + corrections) | Non | 0.7 (edit) | 30s | 3× expo | gpt-4.1 |
| Handy | Court (5 règles) | Non | Non envoyé | Implicite | Structured→legacy | Multi-provider |
| Voxtype | Minimaliste | Non | Dépend du script | 30s | Non | llama3.2:1b |

---

## Backends Voxtype — architecture détaillée

### Les 7 moteurs ASR

| Moteur | Langues | Architecture | Intégration | Source |
|--------|---------|-------------|-------------|--------|
| **Whisper** | 99 | Encoder-decoder autoregressif | whisper.cpp via `whisper-rs` (FFI) | OpenAI |
| **Parakeet TDT** | EN (25 langues v3) | FastConformer + TDT decoder | `parakeet-rs` crate (notre upstream !) | NVIDIA |
| **Moonshine** | EN | Encoder-decoder + KV cache | ONNX natif via `ort` | Useful Sensors |
| **SenseVoice** | zh/en/ja/ko/yue | CTC encoder-only | ONNX natif via `ort` | Alibaba FunASR |
| **Paraformer** | zh+en, zh+yue+en | Non-autoregressif | ONNX natif via `ort` | Alibaba FunASR |
| **Dolphin** | 40 langues (PAS EN) | CTC E-Branchformer | ONNX natif via `ort` | DataoceanAI |
| **Omnilingual** | 1600+ | wav2vec2 CTC | ONNX natif via `ort` | Meta MMS |

### Abstraction Rust

```rust
// Trait unique — chaque backend l'implémente
pub trait Transcriber: Send + Sync {
    fn transcribe(&self, samples: &[f32]) -> Result<String, TranscribeError>;
    fn prepare(&self) {}  // optionnel, précharge pendant l'enregistrement
}
```

Factory `create_transcriber(config)` avec `match` sur `TranscriptionEngine` + `#[cfg(feature)]`.
Aussi : `SubprocessTranscriber` (isolation GPU), `RemoteTranscriber` (API HTTP), `CliTranscriber`.

### Fichiers modèles par backend

| Backend | ONNX | Tokenizer | Autres |
|---------|------|-----------|--------|
| Whisper | `ggml-*.bin` (whisper.cpp) | Intégré | — |
| Parakeet TDT | `encoder-model.onnx`, `decoder_joint-model.onnx` | `vocab.txt` | `config.json` |
| Moonshine | `encoder_model.onnx`, `decoder_model_merged.onnx` | `tokenizer.json` (BPE) | — |
| SenseVoice | `model.int8.onnx` | `tokens.txt` | CMVN dans metadata |
| Paraformer | `model.int8.onnx` | `tokens.txt` | `am.mvn` (CMVN Kaldi) |
| Dolphin | `model.int8.onnx` | `tokens.txt` | CMVN dans metadata |
| Omnilingual | `model.int8.onnx` | `tokens.txt` (9812 symboles) | — |

### Code partagé entre backends ONNX

- `fbank.rs` : extraction Fbank 80-dim (FFT 512, hop 160, win 400, Hamming, preemphasis 0.97)
- `ctc.rs` : décodage CTC greedy (argmax, collapse doublons, suppression blancs)
- SenseVoice + Paraformer : LFR (Low Frame Rate) — empilement 7 frames, stride 6 → 560-dim
- Normalisation CMVN (stats depuis metadata ONNX ou fichier `am.mvn` Kaldi)
- Moonshine + Omnilingual : waveform brute (pas de Fbank)

### Accélération GPU

| Backend | CPU | Vulkan | CUDA | TensorRT | ROCm | Metal |
|---------|-----|--------|------|----------|------|-------|
| Whisper | ✓ | ✓ | ✓ | — | ✓ | ✓ |
| Parakeet | ✓ | — | ✓ | ✓ | ✓ | — |
| Moonshine | ✓ | — | ✓ | ✓ | — | — |
| SenseVoice | ✓ | — | ✓ | ✓ | — | — |
| Paraformer | ✓ | — | ✓ | ✓ | — | — |
| Dolphin | ✓ | — | ✓ | ✓ | — | — |
| Omnilingual | ✓ | — | ✓ | ✓ | — | — |

### Features Cargo

```toml
default = []
# Whisper GPU (via whisper.cpp)
gpu-vulkan = ["whisper-rs/vulkan"]
gpu-cuda = ["whisper-rs/cuda"]
gpu-metal = ["whisper-rs/metal"]
gpu-hipblas = ["whisper-rs/hipblas"]
# Parakeet (via parakeet-rs)
parakeet = ["dep:parakeet-rs"]
parakeet-cuda = ["parakeet", "parakeet-rs/cuda"]
parakeet-tensorrt = ["parakeet", "parakeet-rs/tensorrt"]
parakeet-rocm = ["parakeet", "parakeet-rs/rocm"]
# Couche ONNX partagée
onnx-common = ["dep:ort", "dep:ndarray", "dep:rustfft"]
# Backends ONNX
moonshine = ["onnx-common", "dep:tokenizers"]
sensevoice = ["onnx-common"]
paraformer = ["onnx-common"]
dolphin = ["onnx-common"]
omnilingual = ["onnx-common"]
# + variantes -cuda et -tensorrt pour chacun
```

### Comparaison avec dictee

| Aspect | Voxtype | dictee |
|--------|---------|--------|
| Parakeet TDT | Via `parakeet-rs 0.3` (crate) | Implémentation native dans `src/` |
| Whisper | whisper.cpp via whisper-rs (FFI) | Python : faster-whisper / openai-whisper / onnx-asr |
| Moonshine | ONNX natif Rust | Non (prévu post-v1) |
| SenseVoice | ONNX natif Rust | Non |
| Vosk | Non | Oui (Python) |
| ORT version | `2.0.0-rc.11` | `2.0.0-rc.11` |
| Plasmoid KDE | Non | Oui |
| Traduction | Non | Oui |
| Diarisation | Oui | Oui (Sortformer) |
| Post-traitement | Pipe externe | regex + LLM intégré |

---

## Idées à considérer pour dictee (post-v1.3)

### Priorité haute
- **Collapse bégaiements** (Handy) — simple, utile
- **Strip `<think>...</think>`** des réponses LLM (Voxtype) — trivial
- **Filtrage hallucinations Whisper** (hyprwhspr) — set de phrases connues

### Priorité moyenne
- **Custom words fuzzy** Levenshtein + Soundex (Handy) — meilleur que le matching exact
- **Filler words par langue** (Handy) — enrichir notre liste française
- **Auto-corrections vocales** "non attends" → discard (FluidVoice)
- **Historique révisions intermédiaires ASR** envoyé au LLM (Koe) — innovant

### Priorité basse / exploratoire
- **Moonshine backend** Rust natif (Voxtype) — candidat CPU léger
- **Nombres mots→chiffres** (Nerd Dictation) — complexe à faire en français
- **LanguageTool** comme alternative/complément LLM (Nerd Dictation)
- **Profils de prompts par application** (FluidVoice) — selon la fenêtre active
- **Structured output JSON** pour forcer le format LLM (Handy)
