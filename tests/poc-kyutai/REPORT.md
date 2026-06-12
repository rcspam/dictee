# POC Kyutai STT-1B en_fr — rapport

Date : 2026-06-12
Objectif : évaluer `kyutai/stt-1b-en_fr-candle` comme candidat remplaçant du live
Nemotron (FR jugé mauvais à l'usage — FLEURS FR : Nemotron 9,03 % WER vs Parakeet 5,15 %).

## TL;DR (provisoire)

| Critère | Résultat |
|---|---|
| Qualité FR | ✅ Excellente à l'oreille du POC (ponctuation, caps, noms propres quasi tous justes sur C dans l'air 4 min) |
| Timestamps mots | ✅ Natifs (`--timestamps`, [start-stop] par mot) |
| VAD sémantique | ✅ 4 têtes (horizons 0,5/1/2/3 s), probabilité `endofturn` par pas de 80 ms |
| Streaming | ✅ Vrai streaming : `step_pcm()` par frames de 80 ms, délai texte fixe 0,48 s (`asr_delay_in_tokens=6`) |
| RTF GPU (RTX 4070 Laptop) | ≈ 0,78 (4 min TV news, bf16) — temps réel OK, peu de marge |
| RTF CPU (f32) | ❌ **≈ 3,2** (mesure différentielle propre) — PAS temps réel ; pas de GGUF quantisé publié pour candle → live Kyutai = GPU-only en l'état |
| VRAM | ≈ 2,6 Go (avec daemon dictee Nemotron chargé à côté : pic total 6,1/8 Go) |
| RAM CPU | ≈ 5,8 Go RSS (conversion bf16→f32 du 1B params) |
| Daemon résident | ✅ Faisable : API `moshi::asr::State` = load once + `step_pcm` + `reset()` (asr.rs:113), mode batché dispo |
| Licence | ✅ CC-BY-4.0 (modèle), code Apache-2.0/MIT |

## Setup

- Repo : `github.com/kyutai-labs/delayed-streams-modeling` (exemple `stt-rs`, ~260 lignes)
- Crates : candle 0.9.1, moshi 0.6.1, sentencepiece, kaudio (resample auto 16 k→24 k)
- Modèle : `kyutai/stt-1b-en_fr-candle` — `model.safetensors` (~2 Go bf16) + mimi (codec audio) + tokenizer SP 8000
- Build CPU : `cargo build --profile release-no-debug` — direct, 1 min 33
- Build CUDA : voir « gotcha nvcc » ci-dessous

### 🔧 Gotcha build CUDA (host TUXEDO, driver 595.71 = CUDA 13.2, toolkit installé = 13.3)

1. `cudarc 0.16.x` (pin de candle 0.9.1) ne connaît pas CUDA 13.3 → panic build.rs.
   Contournement : `CUDARC_CUDA_VERSION=12090` (force les bindings 12.9, dynamic-loading OK).
2. Les kernels candle compilés par nvcc 13.3 émettent du PTX ISA 9.3 → rejeté par le
   driver 13.2 (`CUDA_ERROR_UNSUPPORTED_PTX_VERSION`).
   Contournement : nvcc 12.8 extrait localement SANS root (`apt download cuda-nvcc-12-8
   cuda-crt-12-8 cuda-nvvm-12-8 cuda-cudart-dev-12-8 cuda-cudart-12-8 cuda-cccl-12-8`
   + `dpkg -x` dans `cuda-12.8-local/`) → PTX ISA 8.7, accepté.
3. ⚠️ `cargo clean -p candle-kernels` ne purge PAS le profil custom `release-no-debug`
   → `rm -rf target/<profil>/build/candle-kernels-* target/<profil>/.fingerprint/candle-kernels-*`.
   Vérif : `grep '^.version' target/.../out/affine.ptx` → 8.7 = OK, 9.3 = KO.

Build final :
```bash
CUDA_LOCAL=$PWD/../cuda-12.8-local/usr/local/cuda-12.8
CUDARC_CUDA_VERSION=12090 PATH=$CUDA_LOCAL/bin:$PATH CUDA_ROOT=$CUDA_LOCAL \
  CUDA_COMPUTE_CAP=89 cargo build --profile release-no-debug --features cuda
```

## Résultats

### Qualité FR (ref-fr.wav, 3,7 s TTS)

CPU et GPU identiques, parfait :
```
[ 0.56- 0.96] Bonjour,
[ 0.96- 1.28] ceci est
...
[ 3.52-     ] français.
```

### Qualité FR (cdanslair_attal_16k.wav, 4 min 10 s broadcast, 5 locuteurs)

Sortie GPU = sortie CPU (déterministe, température 0). Très bonne : ponctuation riche
(guillemets « », ?, virgules), majuscules, noms propres majoritairement justes
(Bardella, Attal, Retailleau, MEDEF, Patrick Martin, Odoxa, Edouard Philippe, Ebra).
Erreurs relevées : « Jérôme Jaffray » (Jaffré), « SEVIPOV » (CEVIPOF), « Frontierreur »
(Franc-Tireur), « Gaëlle Slimane » (Gaël Sliman), « beaude ruche » (baudruche),
« le droit à la paresse qui était régé » (érigé). Aucune anglicisation — contraste
net avec Parakeet-TDT en auto et Nemotron.

### Performance

| Run | Wall | Audio traité* | RTF | Mémoire |
|---|---|---|---|---|
| CPU court (à chaud) | 28,7 s | ~6,2 s | — (load domine) | RSS 5,8 Go |
| CPU long (4 min) | 1236,7 s ⚠️ | ~255 s | ⚠️ ≈ 4,8 brut — mesure CONTAMINÉE (cargo builds concurrents sur tous les cœurs) | RSS 5,9 Go |
| CPU différentiel (5 s vs 65 s, machine au repos) | 23,0 / 213,8 s | Δ = 60 s | **≈ 3,2** (net de load, mesure propre) | |
| GPU court | 13,7 s | ~6,2 s | — (load ≈ 9 s) | |
| GPU long (4 min) | 207,7 s | ~255 s | **≈ 0,78** (net de load) | VRAM +2,6 Go |

\* audio + préfixe silence + délai + 1 s de flush.

- Load modèle GPU ≈ 9 s (one-time pour un daemon résident).
- Pas de variante quantisée candle (.gguf) publiée par Kyutai (le support existe dans
  l'exemple `main.rs`) ; MLX q4/q8 existent mais format inexploitable. Quantiser
  nous-mêmes = piste si le CPU doit être couvert.

### VAD sémantique

`--vad` → messages `Step { prs }` à chaque frame de 80 ms ; `prs[2]` = P(pas de voix
sur l'horizon 2 s). Émis en continu → utilisable pour l'auto-stop / fin de phrase
(c'est ce qu'utilise leur produit Unmute). Sur le wav TTS court, p≈0,56-0,68 en fin
de mots — seuil 0,5 un peu sensible, à calibrer sur voix réelle.

## Faisabilité daemon résident (analyse code)

`moshi::asr::State` (crate moshi 0.6.1) :
- `State::new(batch_size, asr_delay_in_tokens, …, audio_tokenizer, lm)` — load une fois.
- `step_pcm(pcm_chunk)` → `Vec<AsrMsg>` : `Word{tokens, start_time}`, `EndWord{stop_time}`,
  `Step{prs}` — incrémental, push-driven, exactement le modèle de notre streaming F9.
- `reset()` (asr.rs:113) — réutilisation entre dictées sans recharger.
- `reset_batch_idx(idx)` — serving multi-clients batché (moshi-server fait du batch 64).
- candle = Rust pur + kernels CUDA propres → **pas de collision de symboles avec ort**
  (contrairement à sherpa-onnx) ; cohabitation même binaire a priori possible, daemon
  séparé trivialement possible (pattern transcribe-daemon existant).

## moshi-server (voie websocket officielle) — VALIDÉ end-to-end

- `cargo install --locked moshi-server --features cuda` (⚠️ sans `--locked` : E0119
  conflit de trait avec un crate `time` trop récent). Link dynamique CUDA → il a fallu
  ajouter au tree local : `libcublas{,-dev}-12-8`, `cuda-nvrtc{,-dev}-12-8`,
  `libcurand{,-dev}-12-8` + `LIBRARY_PATH` (build) et `LD_LIBRARY_PATH` (run).
- Port 8090 occupé sur le host → POC sur **8998**.
- Smoke test complet : serveur up (warmup + asr loop batch 4) + client
  `stt_from_file_rust_server.py` en simulation temps réel (rtf=1) sur ref-fr.wav →
  transcription parfaite + timestamps mots reçus en websocket. Wrapper : `run-mic-test.sh`.

## À compléter

- [x] RTF CPU : ≈ 3,2 (différentiel propre) — pas temps réel
- [ ] Test micro live (latence perçue) — PRÊT, nécessite le user :
      `./run-mic-test.sh server` (terminal 1) puis `./run-mic-test.sh mic` (terminal 2)
- [ ] Bench qualité sur la voix du user vs nemotron/parakeet/whisper-medium (protocole prêt)

## Optimisation CPU — MKL + quantisation (après-midi 2026-06-12)

Constat utilisateur confirmé : l'inférence f32 n'occupe que **185 %** d'un i7-13700H
(20 threads). Cause : décodage autorégressif batch 1 = produits matrice×vecteur,
bornés mémoire, non parallélisés par le backend gemm par défaut de candle.

| Variante | Poids | Wall slice5 / slice65 | RTF (différentiel, Δ60 s) | %CPU | RSS |
|---|---|---|---|---|---|
| f32 (gemm défaut) | ~2 Go bf16→f32 | 23,0 / 213,8 s | **3,18** | ~185 % | 5,8 Go |
| q8_0 GGUF | 1 003 Mo | 18,7 / 201,3 s | **3,04** | ~1090 % | 2,3 Go |
| q4k GGUF | 531 Mo | 11,6 / 137,5 s | **2,10** | ~950 % | 1,9 Go |
| MKL (candle/mkl) | — | ÉCHEC BUILD : `undefined reference to hgemm_` (la MKL trouvée par intel-mkl-src n'a pas les symboles half-precision attendus par candle 0.9.1) | | | |

Méthode : quantisation via `tensor-tools quantize` (repo candle 0.9.1 cloné dans le POC,
3 s pour quantiser) ; patch local de `main.rs` pour accepter un `--model-path` fichier
local (sinon `repo.get()` HF seulement). Qualité q8/q4k : spot-check OK sur slice5
(texte identique au f32) — PAS de diff complet 4 min (inutile vu le verdict).
Mesures faites serveur CPU idle à 8 % (vérifié), machine au repos sinon.

### Verdict CPU

**Le live CPU Kyutai n'est PAS viable, même quantisé** (critère : RTF < 1) :
- La quantisation réveille bien le multi-cœurs (2 → 10-11 cœurs) et divise la RAM par 3,
  mais le RTF ne descend qu'à 2,1 (q4k) — le gain ne suit pas le trafic mémoire
  (q8 = −4 % seulement, q4k = −34 %).
- Lecture : le goulot n'est pas (que) la bande passante des poids du LM — overhead
  par pas de 80 ms du framework + codec mimi resté f32 fixent un plancher ≈ 2.
- Écart avec Nemotron CPU (RTF 0,33, ONNX Runtime int8) : ~6×. Sur CPU, Nemotron reste
  le seul moteur live ; Kyutai = GPU-only pour le live (RTF 0,78).

1. « FR ≥ Whisper-medium sur sa voix » → bench voix user EN ATTENTE, mais la qualité
   FR observée (broadcast 4 min) est nettement au-dessus de Nemotron.
2. « Latence live ≤ nemotron » → architecture : délai texte fixe 0,48 s vs chunks figés
   560 ms Nemotron ; à confirmer au micro.
3. « Daemon résident faisable » → ✅ (API moshi::asr, reset(), même pattern que le F9).
4. « Licence OK » → ✅ CC-BY-4.0.

⚠️ Limite majeure découverte : **CPU pas temps réel (RTF 3,2)** → si Kyutai devient le
moteur live, les installs `dictee-cpu` gardent Nemotron (RTF 0,33) ou restent en batch.
Piste : quantisation q8 maison (le loader candle supporte les .gguf, main.rs:135-147).

## VERDICT FINAL — test micro user (2026-06-12 soir)

**« Kyutai est très bon en français ! » — GO.** Les 4 critères sont au vert :
qualité FR sur la voix du user ✓ (subjectif fort ; bench formel 4 moteurs optionnel),
latence live non critiquée ✓, daemon résident faisable ✓, licence CC-BY-4.0 ✓.
Réserve actée : **GPU-only** (CPU RTF 2,1-3,2 même quantisé — le live CPU reste
Nemotron). → Prochain chantier : intégration moteur live GPU (daemon résident
candle/moshi, socket dédié, pattern transcribe-daemon, branché sur l'orchestrateur
streaming F9 via le protocole StreamClient existant).
