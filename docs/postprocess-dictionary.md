# Post-processing — Dictionary tab

## Overview

The **Dictionary** tab configures a word replacement dictionary. ASR engines sometimes transcribe common words with incorrect casing or spelling — the dictionary corrects them automatically.

## Configuration files

- **User**: `~/.config/dictee/dictionary.conf`
- **System (default)**: `/usr/share/dictee/dictionary.conf.default`
- **Draft**: `~/.config/dictee/dictionary.conf.tmp` (unsaved modifications)
- Environment variables:
  - `DICTEE_PP_DICT=true|false` — enable/disable the dictionary
  - `DICTEE_PP_FUZZY_DICT=true|false` — enable/disable fuzzy matching

## File format

```
# ── Dictionary [*] ──────────────────────────────────────────────────
[*] api=API
[*] url=URL
[*] linux=Linux

# ── Dictionary [en] ─────────────────────────────────────────────────
[en] ai=AI

# ── Dictionary [fr] ─────────────────────────────────────────────────
[fr] sncf=SNCF
```

- **Section**: `# ── Dictionary [lang] ──` — one section per language
- **Entry**: `[lang] WORD=REPLACEMENT`
- **lang**: ISO 639-1 code or `*` (all languages)
- Sections are created/removed automatically based on entries

## Matching modes

### Exact (always active)

Word-boundary replacement, case-insensitive with case preservation:
- `api` → `API`
- `Api` → `API`
- `API` → `API`

### Fuzzy (jellyfish)

Uses `jaro_winkler_similarity` from the jellyfish library (threshold 0.85) to tolerate small ASR errors:
- `Gogle` → `Google` (score > 0.85)
- `Gooooogle` → no match (score < 0.85)

Requires `pip install jellyfish`. Controlled by the "Fuzzy matching (jellyfish)" checkbox.

## User interface

### Form view (default)

- **Search bar**: theme magnifier icon + language filter
- **Collapsible sections**: `▾ Dictionary [fr] (7 entries)` — click to collapse/expand
- **Inline editing**: each entry is directly editable (language, word, replacement)
- **✓ button**: appears when an existing entry is modified. Confirms and saves.
- **✕ button**: deletes the entry

### Adding entries ("+ Add" button)

- New lines appear **at the bottom of the window**, outside the scroll area, always visible
- Not affected by the search filter
- The ✓ button confirms: the entry is placed in the matching `Dictionary [lang]` section
- If the section doesn't exist, it is created
- Other in-progress new entries are not affected when confirming one
- Incomplete entries (empty word or replacement) are silently ignored

### Edit mode ("Edit mode" button)

- Monospace text editor with raw file content
- Ctrl+F search with navigation and occurrence counter
- On leaving edit mode:
  - Syntax validation
  - Automatic reorganization of orphan entries (placed in `Dictionary [lang]`)
- Changes are written to the `.tmp` draft

### Action bar

- **🔍**: search (Ctrl+F) in edit mode
- **+ Add**: add a new entry
- **Undo / Redo**: history (max 20 levels)
- **Save**: copies the `.tmp` draft to the official file
- **Revert to saved**: discards all unsaved changes
- **Factory reset**: restores the default dictionary from the system file

## Data flow

```
                    ┌─────────────────┐
                    │ dictionary.conf │ (official)
                    └────────┬────────┘
                             │ copied on open
                    ┌────────▼────────┐
                    │ dictionary.conf │.tmp (draft)
                    └────────┬────────┘
                             │ edited in UI
                             │
                    ┌────────▼────────┐
          Save ────►│ dictionary.conf │ (official updated)
                    └─────────────────┘
```

- The `.tmp` draft is created when the post-processing window opens
- All changes (add, delete, edit mode) write to the `.tmp`
- **Save** copies `.tmp` → official
- **Closing without Save**: the `.tmp` is deleted (changes lost)

## Filtering

- **Search**: filters on word AND replacement (case-insensitive)
- **Language filter**: combo with all present languages + "All languages"
- Filter stays active after confirming a new entry
- Unconfirmed new entries are not affected by the filter

## Post-processing pipeline

The dictionary is applied at step 7 of the pipeline:

1. Regex rules (`rules.conf`)
2. Bad language rejection
3. Continuation
4. Elisions (FR)
5. Numbers (text2num)
6. Typography (FR)
7. **Dictionary** ← here
8. Capitalization

Order matters: the dictionary runs after elisions and typography to avoid interfering with those transformations.

## Technical notes

- Case preservation is automatic: if the entry is `linux=Linux`, then `LINUX` → `LINUX`, `Linux` → `Linux`, `linux` → `Linux`
- The file is reloaded on each transcription — no daemon restart needed
- Fuzzy matching adds ~10ms per transcription (negligible)
- `[*]` entries apply to all languages, `[fr]` entries only when `DICTEE_LANG_SOURCE=fr`
