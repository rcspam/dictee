# Example LLM profiles

Ready-to-import profiles for the LLM analysis pass in `dictee-transcribe`.
They are examples, not built-ins: nothing here is installed or loaded
automatically. Import the ones you want, edit them, delete the rest.

## Importing

In `dictee-setup`, sidebar → **LLM Diarization** → *Manage profiles…* →
**Import**, pick a `.json` file, then **Save**. The profile lands in
`~/.config/dictee/llm-profiles.json` as a user profile, so you can edit or
remove it later from the same dialog.

`dictee-diarize-llm --list-profiles` shows what is registered.

## Providers and models

Every example ships with `default_provider_id` and `default_model` empty.
Provider ids are local to your machine, and there are no built-in providers
any more, so a hardcoded id would just fail to resolve on someone else's
install. Pick both in the combos before running, or set them once by editing
the profile after import.

No example contains an API key. Keys live in `llm-providers.json`, a separate
file, and are never part of a profile.

## Diarized vs plain

Each profile declares a transcript type, and `dictee-transcribe` only offers
the profiles matching the active tab:

- no `format` key: diarized transcripts. The prompt receives
  `[Speaker N] (HH:MM:SS → HH:MM:SS): text` lines.
- `"format": "plain"`: transcripts produced without diarization. The prompt
  receives the raw text, no labels, no timestamps.

That is why some profiles come in two variants. Importing only one is fine if
you only ever work with one kind of transcript.

## Available profiles

| File | Type | Mode | What it does |
|---|---|---|---|
| `pkm-frontmatter.json` | diarized | global | Generates YAML frontmatter (title, tags, aliases, summary) for a markdown notes vault such as Obsidian or Logseq. |
| `pkm-frontmatter-plain.json` | plain | global | Same, for transcripts without speaker labels. |

The frontmatter prompts are adapted from the [Fabric](https://github.com/danielmiessler/fabric)
`generate_frontmatter` pattern (MIT). Two changes were needed for dictee: the
prompt cannot ask for "today's date" because only `{TRANSCRIPT}`,
`{PREVIOUS_SEGMENT}` and `{DICTIONARY}` are substituted, so a model asked for
the current date will invent one; and the diarized variant tells the model
that the `[Speaker N]` prefixes are structure rather than content.

Smaller models still fill an occasional field with an empty string instead of
dropping the line. Worth a look before pasting the block into a note.

## Writing your own

Start from an example, or from *New* in the profiles dialog. The shape:

```json
{
  "profiles": [
    {
      "id": "my-profile",
      "name": "Shown in the combo",
      "mode": "global",
      "format": "plain",
      "default_provider_id": "",
      "default_model": "",
      "prompt": "<role>...</role>\n<instructions>...</instructions>\n<input>\n{TRANSCRIPT}\n</input>\n"
    }
  ]
}
```

- `mode`: `global` sends the whole transcript in one call. `per-segment`
  calls the model once per segment and gives the prompt the previous
  segment's result through `{PREVIOUS_SEGMENT}`, which suits rewriting
  passes like ASR correction.
- `format`: omit it for diarized, `"plain"` otherwise.
- `prompt`: `{TRANSCRIPT}` is required. `{DICTIONARY}` receives the user
  dictionary and `{PREVIOUS_SEGMENT}` only means something in `per-segment`
  mode; both render as `(none)` when empty.
- `id` must be unique. On import, a colliding id is suffixed (`-2`, `-3`),
  it does not overwrite anything.

Contributions welcome: drop a `.json` here plus a row in the table above.
