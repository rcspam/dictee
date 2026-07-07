# Matrice DER — benchmark diarisation

## collar 0 + overlap (DIHARD) — mode auto (DER %, plus bas = mieux)

| candidat | _val | aishellsub | voxsub |
|---|---|---|---|
| community1-onnx-th0.5 | — | 42.8 | 35.3 |
| diarizen | — | 6.7 | 11.8 |
| pyannote-speaker-diarization-community-1 | — | 7.9 | 13.2 |
| sherpa-3dspeaker_speech_campplus_sv_en_voxceleb_16k-th0.6 | — | 34.0 | 21.0 |
| sherpa-3dspeaker_speech_eres2net_sv_en_voxceleb_16k-th0.6 | 19.8 | 33.2 | 23.3 |
| sherpa-wespeaker_en_voxceleb_resnet34_LM-th0.6 | — | 38.4 | 37.2 |
| sortformer | 19.1 | 27.4 | 26.5 |
| speakrs-th0.6 | — | 7.9 | 13.2 |

## collar 0 + overlap (DIHARD) — mode oracle (DER %, plus bas = mieux)

| candidat | _val | aishellsub | voxsub |
|---|---|---|---|
| community1-onnx-oracle | — | 51.9 | 36.4 |
| pyannote-speaker-diarization-community-1 | — | 7.9 | 21.1 |
| sherpa-3dspeaker_speech_campplus_sv_en_voxceleb_16k-oracle | — | 26.6 | 27.7 |
| sherpa-3dspeaker_speech_eres2net_sv_en_voxceleb_16k-oracle | 14.9 | 27.3 | 17.4 |
| sherpa-wespeaker_en_voxceleb_resnet34_LM-oracle | — | 37.9 | 30.7 |
| speakrs-oracle | — | 31.2 | 14.2 |

## collar 0.25 sans overlap (AMI/CALLHOME) — mode auto (DER %, plus bas = mieux)

| candidat | _val | aishellsub | voxsub |
|---|---|---|---|
| community1-onnx-th0.5 | — | 36.5 | 27.2 |
| diarizen | — | 1.7 | 6.3 |
| pyannote-speaker-diarization-community-1 | — | 1.9 | 7.1 |
| sherpa-3dspeaker_speech_campplus_sv_en_voxceleb_16k-th0.6 | — | 26.5 | 13.2 |
| sherpa-3dspeaker_speech_eres2net_sv_en_voxceleb_16k-th0.6 | 15.7 | 25.3 | 15.9 |
| sherpa-wespeaker_en_voxceleb_resnet34_LM-th0.6 | — | 32.4 | 32.0 |
| sortformer | 15.3 | 22.9 | 20.3 |
| speakrs-th0.6 | — | 1.9 | 7.0 |

## collar 0.25 sans overlap (AMI/CALLHOME) — mode oracle (DER %, plus bas = mieux)

| candidat | _val | aishellsub | voxsub |
|---|---|---|---|
| community1-onnx-oracle | — | 47.2 | 28.7 |
| pyannote-speaker-diarization-community-1 | — | 1.9 | 15.6 |
| sherpa-3dspeaker_speech_campplus_sv_en_voxceleb_16k-oracle | — | 21.6 | 21.8 |
| sherpa-3dspeaker_speech_eres2net_sv_en_voxceleb_16k-oracle | 11.2 | 22.4 | 11.0 |
| sherpa-wespeaker_en_voxceleb_resnet34_LM-oracle | — | 32.2 | 24.6 |
| speakrs-oracle | — | 26.1 | 8.1 |
