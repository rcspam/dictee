# bench-diarize — harness de benchmark diarisation (>4 locuteurs)

But : trancher sur données solides quelle techno de diarisation dictee doit embarquer
pour dépasser le plafond 4 de Sortformer. Spec : `docs/superpowers/specs/2026-06-28-diarization-benchmark-harness-design.md`.

Métrique : **DER + JER** via **dscore** (standard DIHARD), 2 conventions.
Candidats : Sortformer, sherpa-onnx (×N embeddings), pyannote community-1, DiariZen (étalon).
Corpus libres avec RTTM : VoxConverse, AISHELL-4, MSDWild (set *many* >4), ICSI.

## ⚠️ Pérennité / licences
- **DiariZen** : poids **CC BY-NC 4.0 (non commercial)** → benchmark uniquement, **non
  embarquable** dans dictee (GPL). Sert de plafond de qualité.
- **pyannote community-1 / 3.1** : poids **gated** (token HF + acceptation conditions).
- **sherpa-onnx + Sortformer** : OK à embarquer.

## Prérequis
- Binaires dictee dans le PATH (ou via env) : `diarize-only` (Sortformer, feature
  `sortformer`) et `diarize-only-sherpa` (crate `dictee-sherpa-diarize`).
  Override : `DIARIZE_ONLY=/path/...`, `DIARIZE_ONLY_SHERPA=/path/...`.
- `ffmpeg`/`ffprobe`, `wget` (ou `aria2c`), `git`, `unzip`. `uv` pour les runners Python.
- MSDWild : `gdown` (`pip install gdown`). pyannote : `HF_TOKEN` exporté.

## Workflow
```bash
cd tests/bench-diarize

# 1. modèles sherpa (segmentation + embeddings, ~450 Mo). Dry-run d'abord :
./fetch-models.sh --dry-run
./fetch-models.sh

# 2. corpus — VOIR la liste de courses (tailles) AVANT de télécharger :
./fetch-corpora.sh --dry-run
./fetch-corpora.sh --yes voxconverse aishell4     # sous-ensemble, ou tout : --yes

# 3. lancer les candidats (idempotent ; relancer = complète seulement le manquant)
CANDIDATES="sortformer sherpa" EMBEDDINGS="eres2net campplus wespeaker titanet" ./run.sh
HF_TOKEN=hf_xxx CANDIDATES="pyannote" ./run.sh        # pyannote community-1

# 4. scorer + agréger
./score.sh
python report.py        # -> results/DER-matrix.md  +  results/DER.tsv
```

## Modes
- **auto** : nb de locuteurs libre (sherpa `--threshold`, pyannote défaut). Cas « aveugle ».
- **oracle** : nb = vérité terrain (sherpa `--num-clusters N`, pyannote `num_speakers=N`).
  Chiffre le gain d'un **champ « nombre de participants »** dans l'UI meeting.

## DiariZen (étalon, env séparé)
```bash
conda create -y -n diarizen python=3.10 && conda activate diarizen
conda install -y pytorch==2.1.1 torchaudio==2.1.1 pytorch-cuda=12.1 "mkl<2024.1" -c pytorch -c nvidia
git clone https://github.com/BUTSpeechFIT/DiariZen && cd DiariZen && pip install -r requirements.txt && pip install -e .
cd pyannote-audio && pip install -e .[dev,testing] && cd .. && git submodule update --init
# puis, pour chaque corpus :
python runners/diarizen_run.py --audio audio/16k/<corpus> --out hyp/diarizen/<corpus>/auto
```

## Disposition
```
models/ (segmentation.onnx, emb/*.onnx)   audio/16k/<corpus>/*.wav
ref_rttm/<corpus>/*.rttm   uem/<corpus>.uem
hyp/<candidate>/<corpus>/<mode>/<file-id>.rttm (+ _all.rttm)
results/raw/*.txt  results/DER-matrix.md  results/DER.tsv   logs/
.dl/ .mdir/ .tools/ .refall/  (caches, non versionnés)
```

## Notes
- Le binaire `diarize-only-sherpa` charge des noms de modèle fixes → `sherpa.sh` monte un
  models-dir par embedding via symlinks. (TODO produit : exposer `--embedding` dans la crate.)
- Tout est isolé dans ce dossier ; aucun gros artefact n'est destiné à être committé.
