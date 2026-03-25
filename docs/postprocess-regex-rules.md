# Post-processing — Regex rules tab

## Overview

The **Regex rules** tab configures regex substitution rules applied to ASR-transcribed text. Rules are executed sequentially, in file order.

## Configuration files

- **User**: `~/.config/dictee/rules.conf`
- **System (default)**: `/usr/share/dictee/rules.conf.default`
- User rules are applied **after** system rules
- Environment variable: `DICTEE_PP_RULES=true|false`

## Rule format

```
[lang] /PATTERN/REPLACEMENT/FLAGS
```

- **lang**: ISO 639-1 code (`fr`, `en`, `de`, `es`, `it`, `pt`, `uk`) or `*` (all languages)
- **PATTERN**: Python regular expression
- **REPLACEMENT**: replacement text (`\n` = newline, `\t` = tab, `\1` = captured group)
- **FLAGS**:
  - `i` — case-insensitive
  - `g` — global (all occurrences)
  - `m` — multiline (`^` and `$` match start/end of each line)

## Sections (STEPs)

Rules are organized in sections executed in order:

### STEP 1 — Non-speech annotations

Removes non-speech annotations added by Whisper/Parakeet.

```
[*] /\([^)]*\)//g        # (applause), (music), etc.
[*] /\[[^\]]*\]//g       # [music], [laughter], etc.
```

### STEP 2 — Filler words / hesitations

Removes filler words detected by the ASR.

```
[fr] /[,.\s]*\b(euh|euhm?|hum|hmm|ben|bah|hein)\b[,.\s]*/ /ig
[en] /[,.\s]*\b(uh|um|hmm|mm|mhm|mmm)\b[,.\s]*/ /ig
```

Each language has its own filler words.

### STEP 3 — Voice commands

Voice commands transformed into control characters or punctuation. This is the most important section.

**Language sub-sections**: each language has its own sub-section (`# ── French ──`, `# ── English ──`, etc.).

**`[*]` rules are forbidden** in this section — voice commands are language-specific.

French examples:
```
[fr] /[,.\s]*point à la ligne[,.\s]*/.\n/ig
[fr] /[,.\s]*virgule[,.\s]*/, /ig
[fr] /[,.\s]*nouveau paragraphe[,.\s]*/\n\n/ig
```

**Common patterns**:
- `[,.\s]*` — absorbs punctuation and spaces the ASR adds around commands
- `^[,.\s]*...[,.\s]*` with `m` flag — matches at line start (e.g., standalone "à la ligne")
- `(?:a|b|c)` — non-capturing alternations

**Cyrillic handling**: Parakeet sometimes confuses French commands with Cyrillic on short audio clips. Rules like `^[,.\s]*[А-Яа-я]...` catch these misdetections.

### STEP 4 — Word deduplication

Fixes a known Parakeet bug that duplicates words.

```
[*] /\b(\w+)\s+\1\b/\1/ig    # "je je" → "je"
```

### STEP 5 — Punctuation cleanup

Deduplicates punctuation (ASR + voice commands can double up).

```
[*] /\.{3,}/…/g    # ... → …
[*] /\?+/?/g       # ?? → ?
[*] /!+/!/g        # !! → !
```

### STEP 6 — Final cleanup

Final typographic cleanup.

```
[*] /([.!?…»\)])([A-Za-zÀ-ÿ])/\1 \2/g    # Space after glued punctuation
[*] /(\S)«/\1 «/g                          # Space before opening quote
```

## User interface

### "Add a rule" form

- **Language**: combo with all languages + `*`
- **Pattern**: what the ASR says
- **Replacement**: desired replacement
- **Flags**: `ig` by default
- **Insert in**: combo with STEP sections + "At cursor" (default) + "End of file"
- **Position**: "at end" or "at beginning" of section (grayed out if "At cursor")
- **Record**: records audio, transcribes, and fills the pattern field. Automatic Cyrillic detection.

### Smart insertion

- Rules are inserted in the matching **language sub-section** (`# ── French ──`)
- If the sub-section doesn't exist, it is created automatically
- `[*]` rules are inserted directly (no sub-section)
- `[*]` rules are **forbidden** in STEP 3 (Voice commands)

### Search (Ctrl+F)

- Search bar with theme magnifier icon, ▲/▼ navigation, occurrence counter
- Circular search (wraps around)
- Dark yellow selection highlight during search
- Escape or second click closes the bar

### "↓ Test" button

Sends the current line's pattern to the Test panel. The regex pattern is converted to readable text (escape sequences removed).

### Syntax highlighting

- **Gray**: comments `#`
- **Dark yellow bold**: section headers `═══`
- **Blue bold**: `[lang]`
- **Orange**: pattern
- **Green**: replacement
- **Purple**: flags

## Execution order in the pipeline

Order is critical. Rules are applied in file order:

1. Annotations removed first (otherwise they'd be treated as text)
2. Hesitations removed (otherwise "uh comma" would be interpreted as a command)
3. Voice commands converted (core processing)
4. Deduplication runs after commands (otherwise "point point" would be deduplicated before conversion)
5. Punctuation cleaned up after everything
6. Final cleanup ensures typography

## Technical notes

- French elisions (`l' arbre → l'arbre`) are handled by `fix_elisions()` in `dictee-postprocess.py`, **not** by regex rules. See the "Language rules" tab.
- French typography (non-breaking spaces) is also handled separately.
- Regex rules are reloaded on each transcription — no daemon restart needed.
