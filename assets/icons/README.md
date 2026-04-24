# Icons

SVG icons used by the various dictee UIs and documentation.

## Panel / plasmoid

- **`plasmoid-panel.svg`** — *design draft, not yet wired*. Waveform-style panel icon mock-up
  intended to replace the generic `audio-input-microphone` Breeze icon referenced by
  `plasmoid/package/metadata.json` (`"Icon"` field). To enable it, copy into
  `plasmoid/package/contents/icons/` and update `metadata.json`. Note: for proper KDE
  theme integration it should be converted to monochrome with the `ColorScheme-Text`
  CSS class (see Breeze icons for reference).

## Pipeline visualization (used by `dictee-setup` + Post-Processing wiki)

- `microphone-symbolic-{dark,light,orange-dark,orange-light}.svg` — mic (input)
- `asr-symbolic-{dark,light,orange-dark,orange-light}.svg` — ASR stage
- `translate-symbolic-{dark,light,orange-dark,orange-light}.svg` — translation stage
- `workspacelistentryicon-pencilandpaper-symbolic-{dark,light,orange-dark,orange-light}.svg` — final output

All variants ship in dark + light + orange pairs for blue (normal) and orange (translation) pipeline rows.
