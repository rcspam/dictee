# Retired diarization engines

Kept for reference, outside the build. Last compiled at commit 5e97acd
(branch feat/nemotron3-diar, October 2026), with
`cargo build --features "sortformer,diar"`.

- **diarize-multi** (`src/diar/`, `src/bin/diarize_multi.rs`): the in-house
  multi-speaker engine, pyannote segmentation-3.0 + WeSpeaker ResNet34
  embeddings + PLDA/VBx clustering, with a live mode for the meeting window.
  Its unit tests read `tests/diar-fixtures/`.
- **Sortformer** (`src/sortformer.rs`): NVIDIA's streaming Sortformer v2,
  4 speakers at most, used by `diarize-only` (default engine),
  `transcribe-diarize` (Parakeet + Sortformer) and `transcribe-stream-diarize`
  (Nemotron + Sortformer, streamed).

Both were replaced in dictee 1.4 by Nemotron 3 Diarization (8 speakers,
`diarize-only --engine nemotron3`), which serves files and the live meeting
window alike: lower DER on French meetings (11.8 % against 20.6 % for
Sortformer on SUMM-RE) and no 4-speaker cap. MOSS remains as a one-pass
alternative.
