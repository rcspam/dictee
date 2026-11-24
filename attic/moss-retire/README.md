# MOSS (retired in dictee 1.4)

Kept for reference, outside execution: nothing installs or runs these files.
Last live at commit 53fe879a (master, November 2026).

- `dictee-moss-diarize`: the Python driver of MOSS-Transcribe-Diarize
  (OpenMOSS, 0.9B audio LLM, GGUF on the transcribe.cpp runtime) that wrote
  the transcript and the speaker labels in one pass. It cut long files into
  windows and patched the holes the model left with a secondary ASR
  (`DICTEE_MOSS_GAP_ASR`).
- `tests/test-moss-{chunked,gap-patch,driver-truncation}.py`: its tests.

Added in July 2026 (e2933063) when Sortformer stopped at 4 speakers. Retired
on 2026-11-24, replaced by Nemotron 3 Diarization (8 speakers, DER 11 % on
SUMM-RE 004c, 6.5 s on GPU and 27 s on CPU for 21 min, streamed in the
meeting window, shipped by every package) with Parakeet Ultra for the text.
MOSS skipped words (67 to 76 % coverage), lost speaker identities past
5 minutes with its 40 s windows (79.4 % against 99.0 % with 5 min windows,
never fixed), was unusable on the CPU (RTF 1.73), and depended on
transcribe.cpp, a pre-1.0 API that kept changing. No package ever shipped it.

Files a machine may still hold: the GGUF (`/usr/share/dictee/moss` or
`~/.local/share/dictee/moss`), the `moss-env` venv and the transcribe.cpp
runtime (`~/.local/share/dictee/transcribe-cpp`). The Diarization page of
dictee-setup lists them under Retired models, with a Delete button.
