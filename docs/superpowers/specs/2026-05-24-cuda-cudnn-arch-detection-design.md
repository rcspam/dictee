# Spec — cuDNN par détection d'archi GPU + fallback CPU gracieux (dictee-cuda)

**Date :** 2026-05-24
**Cibles :** v1.3 (release/1.3) **et** v1.4 (master) — bugs frappant les utilisateurs actuels.
**Statut :** design validé, à implémenter.

> **🎯 v1.3.5 = release de CORRECTION, réputation-critique. ZÉRO régression, ZÉRO bug ajouté.**
> Discipline imposée : patch minimal (pas de refacto opportuniste), **TDD** (test avant fix), **règle d'or
> packaging** (les modifs touchent les cibles SIMULTANÉMENT), vérif post-build (3 libs ORT), et **validation
> sur GPU réels** (GTX 1060 Pascal + RTX 4070 Ada) AVANT tag. Rien ne part sans preuve d'exécution.

Deux composants complémentaires :
- **A. Détection d'archi → bonne cuDNN** (install-time) = *optimisation* : chaque GPU reçoit la cuDNN qui marche → accélération GPU de Maxwell à Blackwell.
- **B. Fallback CPU gracieux** (runtime, daemon) = *filet de sécurité* : si l'init CUDA échoue malgré tout, le daemon bascule CPU au lieu de crash-loop. **Personne ne reste bloqué.**

A optimise, B garantit. B est indispensable car A a des cas de défaillance (détection ratée, multi-GPU mixte, bump ORT) — voir §7 Robustesse.

> **Différence 1.3 ↔ 1.4 = INT8 uniquement.** INT8 est une feature **v1.4** (livrée sur master, absente de
> release/1.3). Donc le fallback B va vers **INT8 en 1.4**, vers **FP32 CPU en 1.3**. **Tout le reste**
> (détection A + chaîne de fallback B hors choix du modèle) est **identique** entre les deux versions.

## 1. Problème

Aujourd'hui dictee-cuda **ne décide rien** sur cuDNN : les 4 cibles d'install
(`pkg/dictee/DEBIAN/postinst`, `build-rpm.sh` %post, `dictee-cuda.install`, `install.sh` mode_tarball) font
toutes `pip install nvidia-cudnn-cu12` (+ autres) **sans contrainte de version** → pip prend **la dernière du
jour**. Non déterministe, aveugle au GPU, cible mouvante.

Et le daemon, sur échec d'init CUDA, **`exit 1` → crash-loop systemd** (F9 muet, aucune explication).

**Symptôme** (GTX 1060 6 Go, Pascal sm_61, driver 570/CUDA 12.8) : cuDNN 9.22 a abandonné Pascal →
`CUDNN_STATUS_EXECUTION_FAILED` à `cudnnSetDropoutDescriptor` (op RNN du LSTM Parakeet) → crash-loop. Les
GTX 10xx (Pascal) = famille très répandue → flux d'issues.

## 2. Objectif

1. Sélection **déterministe** de cuDNN selon l'archi GPU réelle → tout GPU de Maxwell (cc 5.0) à Blackwell
   (cc 12.0) a une cuDNN qui marche.
2. **Aucun crash-loop** quel que soit le cas : échec d'init CUDA → bascule CPU automatique + notification.

## 3. Correspondances vérifiées (matrices officielles NVIDIA)

| compute_cap | GPU | cuDNN **9.0.0** | cuDNN **latest (9.22)** |
|---|---|---|---|
| 5.0 | Maxwell | ✅ | ❌ |
| 6.0 / 6.1 | Pascal (GTX 10xx) | ✅ | ❌ |
| 7.0 | Volta | ✅ | ❌ |
| 7.5 | Turing (RTX 20xx, GTX 16xx) | ✅ | ✅ |
| 8.0–8.9 | Ampere / Ada | ✅ | ✅ |
| 9.0 | Hopper | ✅ | ✅ |
| 10.0 / 12.0 | Blackwell (RTX 50xx) | ❌ | ✅ |

- cuDNN **9.0.0** : compute **5.0 → 9.0**. cuDNN **9.22** : compute **7.5 → 12.0**.
- **Union = 5.0 → 12.0 sans trou.** Seuil **7.5** = plancher de latest ; recouvrement (7.5→9.0) → on prend latest.
- Aucun **cuDNN unique** ne couvre Pascal (6.x) ET Blackwell (12.0) → d'où la détection (A) + le filet (B).

## 4. Composant A — détection d'archi (install-time)

### 4.1 Détection
1. `nvidia-smi --query-gpu=compute_cap --format=csv,noheader` → `6.1`, `8.9`, `12.0`…
2. Si ça échoue/vide → **installer latest** + warning clair, en comptant sur le **fallback B** au runtime.
- Plusieurs GPU NVIDIA : prendre le **minimum** des compute_cap (la cuDNN doit marcher sur tous présents) —
  **sauf** si l'écart dépasse une seule cuDNN (Pascal+Blackwell) → cas non servable par A, rattrapé par B (§7.2).
- Comparaison : `"X.Y"` → entier `X*10+Y`, comparer à **75**. Arithmétique entière, locale-safe (pas de `bc`).
- **DESCOPÉ (décision 2026-05-24)** : PAS de fallback par nom GPU (`nvidia-smi -L` → table nom→cc).
  `compute_cap` existe depuis driver R460 ; dictee-cuda exige CUDA 12 → driver ≥ R525 → `compute_cap`
  toujours disponible sur tout matériel capable de faire tourner dictee-cuda. Une table nom→cc serait
  fragile (gold-plating). Le cas « détection KO » est couvert par le fallback B.

### 4.2 Mapping (2 paliers)
| compute_cap | cuDNN |
|---|---|
| **< 7.5** (Maxwell/Pascal/Volta) | **`nvidia-cudnn-cu12==9.0.0.312`** (pin strict) |
| **≥ 7.5** (Turing → Blackwell) | **latest** (non pinné = comportement actuel) |

- **Pin strict `==9.0.0.312`** = seule version prouvée Pascal. Tests session 1060 : 9.22 ❌, 9.11.1.4 ❌,
  **9.0.0.312 ✅**. **Ne PAS** ranger `<9.1` ni viser 9.1–9.10 (non testées ; 9.11 casse déjà).
- **Seul `nvidia-cudnn-cu12`** contraint ; les autres `nvidia-*-cu12` restent latest (validé 1060 : 9.0.0 +
  cublas 12.9 marche).

### 4.3 Où vit la logique — script partagé unique
`pkg/dictee/usr/lib/dictee/setup-cuda-venv.sh` — emplacement **canonique** (décision 2026-05-24) : un seul
fichier, qui reflète le chemin d'install `/usr/lib/dictee/`. Pas de copie racine (donc **pas de dérive
root↔pkg**, contrairement à `dictee_models.py` qui existe en double). Ce n'est pas un artefact régénéré : il
EST la source. Inclus dans le .deb via `cp -a pkg/dictee` ; copié explicitement par build-rpm.sh /
build-tar.sh / PKGBUILD-cuda. Les 4 cibles d'install **appellent ce script** au lieu de dupliquer le bloc
pip inline. Source unique de vérité, testable isolément.

Le script (reproduit le mécanisme actuel + détection + robustesse) :
```
1. guard : /usr/lib/dictee/libonnxruntime_providers_cuda.so présent (= variante CUDA)
2. créer/réutiliser /opt/dictee/cuda-venv + upgrade pip
3. détecter compute_cap (§4.1) → choisir contrainte cuDNN (§4.2)
4. pip install nvidia-*-cu12 (cuDNN contraint, autres latest) — idempotent, échec géré (§7.3)
5. nettoyer symlinks périmés de /usr/lib/dictee/ pointant vers le venv, puis re-symlink lib*.so* du venv (§7.5)
6. ldconfig (via /etc/ld.so.conf.d/dictee.conf existant)
7. afficher la cuDNN choisie + le compute_cap détecté ; exit code propre
```

### 4.4 Plomberie ONNX↔cuDNN — NE PAS toucher (cf. feedback-cuda-build-flags)
- Les **3 `.so` ORT bundlés** (`libonnxruntime.so` + `libonnxruntime_providers_cuda.so` +
  `libonnxruntime_providers_shared.so`) restent copiés au **build**. Garde-fou « 3 libs » inchangé.
- Le symlink `libcudnn.so.9` → venv (version-agnostic) : pin 9.0.0 = juste un contenu différent dans le venv.
- `ORT_DYLIB_PATH` services : inchangé.

## 5. Composant B — fallback CPU gracieux (runtime, daemon Rust)

**Aujourd'hui** : `src/execution.rs::best_provider()` renvoie Cuda si GPU présent ; la session ORT est créée
avec ce provider, et si l'init CUDA échoue → exception → `exit 1` → crash-loop.

**Cible** : envelopper la création de session.
```
1. provider = best_provider()  (Cuda si GPU dispo, sauf DICTEE_FORCE_CPU)
2. si Cuda : tenter de créer la session ONNX avec CUDA EP
3. sur ÉCHEC (toute exception d'init CUDA/cuDNN) :
   a. logguer l'erreur (1 ligne claire)
   b. recréer la session en CPU EP :
      → **v1.4** : charger le modèle INT8 si présent (Parakeet INT8 / DICTEE_PARAKEET_QUANT ;
        Whisper compute_type int8_float32), SINON FP32 (dégradation robuste).
      → **v1.3** : FP32 CPU directement — **INT8 n'existe pas en 1.3** (= LA seule différence 1.3/1.4 du fix).
   c. notifier (« GPU indisponible — bascule sur CPU », respecte DICTEE_NOTIFICATIONS) — DÉCISION 2026-05-24 :
      → **master (v1.4)** : écrire /dev/shm/.dictee_provider = **"cpu-fallback"** (NOUVELLE valeur ≠
        cuda/cpu/cpu-forced/cpu-only) ; dictee-tray (déjà QFileSystemWatcher) fire le notify-send + badge.
      → **1.3** : **notify-send DIRECT depuis le daemon** (~5-10 lignes). Le mécanisme provider N'EXISTE PAS
        en 1.3 et **n'est PAS backporté** (patch minimal/robuste pour une release de correction).
4. le daemon continue sur CPU — PAS de exit 1, PAS de crash-loop
```
- INT8 : pré-requis = modèle INT8 présent ; sinon FP32 CPU (toujours fonctionnel). Réf
  parakeet-int8 (−34 % vs FP32) et whisper-bench (int8_float32).
- Couvre TOUS les `*-daemon` ASR (Parakeet/Canary/…) — auditer chaque chemin de chargement de modèle.

### 5.1 Implémentation — repérage Rust (investigué 2026-05-24, prêt à coder)
**Lieu unique : `src/bin/transcribe_daemon.rs` ~143-152** (chargement du modèle). Ce binaire charge **Parakeet ET Canary** (branche `if use_canary`), donc **un seul wrap couvre les deux**. Vosk/Whisper = daemons Python/CT2 → hors scope ORT-CUDA.
```rust
// AUJOURD'HUI (le `?` sur échec d'init CUDA → exit 1 → crash-loop) :
let config = ExecutionConfig::new().with_execution_provider(best_provider()); // Cuda si GPU
let mut backend = if use_canary {
    AsrBackend::Canary(Canary::from_pretrained(&model_dir, Some(config), &source_lang, &target_lang)?)
} else {
    AsrBackend::Parakeet(ParakeetTDT::from_pretrained(&model_dir, Some(config))?)
};
```
- **Le crash CUDA est à `commit_from_file`** (init de session, cf. les loaders model_tdt.rs/model.rs/model_canary.rs : `Session::builder()? → apply_to_session_builder → commit_from_file`), **PAS** à l'enregistrement de l'EP. Donc le fallback CPU natif d'ORT (liste d'EP dans `execution.rs:139-142`) **ne le capte pas** → d'où le wrap au niveau **daemon/modèle**.
- **Fallback au niveau MODÈLE (all-or-nothing)**, pas par session : recharger TOUT le modèle en CPU (évite un mix encoder-GPU + decoder-CPU). `from_pretrained` renvoie `Err` si une session échoue → le daemon catch → reload Cpu.
- **Patron** : extraire le chargement en closure `load(cfg) -> Result<AsrBackend>` (testable) ; capturer `was_cuda = best_provider()==Cuda` ;
  `match load(config) { Ok=>b, Err(e) if was_cuda => { log + notify + load(cpu_config)? }, Err(e)=>return Err(e) }`.
- **1.3** : `cpu_config = ExecutionConfig::new().with_execution_provider(ExecutionProvider::Cpu)` (garder intra/inter threads) → MÊME modèle en CPU (FP32, pas de changement de model-path) ; **`notify-send` direct** depuis le daemon (shell-out, respecte `DICTEE_NOTIFICATIONS` lu via conf/env). `ExecutionProvider::Cpu` existe déjà (execution.rs:136).
- **master** : en plus → modèle INT8 si présent (model-path int8) + écrire `/dev/shm/.dictee_provider = cpu-fallback`.
- **Tests** : TDD = mock du `load` qui échoue → assert retry CPU + 1 seul notify. **E2E** (point dur) = forcer un échec CUDA : 1060 remise en cuDNN **latest** (état cassé) + daemon rebuildé → vérifier bascule CPU **sans crash-loop** + notif. (Défait temporairement le fix A sur la machine de test.)
- **Branche** : nouvelle branche `fix/cuda-graceful-fallback` depuis release/1.3 (A est indépendant, sur `fix/cuda-cudnn-arch-detection`).

## 6. ⚠ Caveat — dépendance à la version d'ORT (atténué par B)

Support **Pascal-GPU lié à ORT 1.23** (`src/onnxruntime-linux-x64-gpu-1.23.0/`).
- **Vérifié** : ORT exige cuDNN **major 9.x** (doc officielle ; 8.x↔9.x incompatibles). 9.0.0 satisfait ça,
  **prouvé sur ORT 1.23 + 1060**.
- **Risque non chiffré** : un bump ORT pourrait exiger des symboles cuDNN 9.x plus récents absents de 9.0.0
  (classe `cublasLtCreate`). La valeur « cuDNN ≥ 9.20 » (mémoire interne) **n'est PAS dans la doc officielle ORT**
  → risque, pas fait.
- **Si un bump ORT casse Pascal** (cuDNN ≥ 9.12 a viré Pascal) : grâce à **B**, Pascal **bascule CPU
  automatiquement** au lieu de crash-loop. Re-tester le palier legacy au moindre bump ORT.

## 7. Robustesse (les 5 points durs)

1. **Détection ratée ne casse plus rien** : si `nvidia-smi` KO → A installe latest, mais **B** capte le crash
   au runtime et bascule CPU. Le trou du happy-path est colmaté par B (la détection par nom est descopée, §4.1).
2. **Multi-GPU mixte (Pascal+Blackwell)** : A prend le min → 9.0.0 → Blackwell non couvert → **B** le rattrape
   (bascule CPU pour ce cas). Documenter : un mix Pascal+Blackwell ne peut pas avoir les DEUX en GPU. (Option
   future : détecter le GPU réellement utilisé via `CUDA_VISIBLE_DEVICES` plutôt que le min.)
3. **pip sur réseau capricieux** (vécu : timeouts cuDNN + bug Canary) : le script est **idempotent**
   (re-run rejoue, downgrade/upgrade vers la version cible), **signale clairement l'échec** (message offline +
   commande de reprise), **ne laisse pas un venv à moitié cassé** (pip valide les wheels ; sur échec, exit code
   non-zéro, l'appelant prévient). Re-run = réparation.
4. **Parsing `compute_cap` blindé** : gérer sortie vide / `N/A` / multi-lignes / format inattendu / locale.
   Arithmétique entière. Si parsing impossible → traiter comme « détection ratée » (point 1 → latest + B).
5. **Idempotence / changement de GPU / réparation** : re-run re-détecte, corrige la version cuDNN
   (downgrade si besoin), et **nettoie les symlinks périmés** de `/usr/lib/dictee/` (lib présente en latest mais
   absente en 9.0.0 = symlink mort) avant de re-symliquer.

## 8. Cibles & fichiers (règle d'or packaging + daemon)

**Composant A (packaging) :**
- Nouveau : **`pkg/dictee/usr/lib/dictee/setup-cuda-venv.sh`** (emplacement canonique, cf. §4.3).
- Copie (4 build-scripts) : `build-deb.sh`, `build-rpm.sh`, `PKGBUILD-cuda`, `build-tar.sh` → `usr/lib/dictee/`.
- Appel (4 cibles) : `pkg/dictee/DEBIAN/postinst`, `build-rpm.sh` %post, `dictee-cuda.install`,
  `install.sh` (mode_tarball). Remplacent le bloc pip inline par l'appel au script.

**Composant B (daemon + UI) — IMPLÉMENTATION PAR BRANCHE (divergence réelle, pas de cherry-pick aveugle) :**
- `src/execution.rs` **diverge déjà 1.3↔master (~77 l)** : master a `provider_status()` +
  `ldconfig_has_cuda_libs()` + le fix `DICTEE_FORCE_CPU` truthy ; **1.3 n'a rien de ça** (encore `is_some()`).
  → écrire le fallback **sur chaque branche depuis son état réel**.
- **Cœur B** (try-CUDA → catch → CPU, zéro crash-loop) : dans le code de création de session / chargement
  modèle des `*-daemon`. Sur **les DEUX** branches.
- **Notif** : master → nouvelle valeur provider `cpu-fallback` (étend `provider_status()` + badge) +
  `dictee-tray.py` via watcher existant ; **1.3 → `notify-send` direct dans le daemon**, **PAS** de backport
  du provider (ffbaf31 ~373 l / 9 fichiers = hors scope patch).
- **INT8** sur fallback : **master uniquement** (cf. §5).

## 9. Tests / vérification
- **Mapping testable isolément** : `setup-cuda-venv.sh` avec compute_cap simulé → 61→9.0.0.312, 75→latest,
  120→latest ; vide/N/A → latest + warning.
- **Fallback testable** : forcer un échec d'init CUDA (ex. cuDNN incompatible) → vérifier bascule CPU +
  provider `cpu-fallback` + notif + PAS de crash-loop.
- **Vérif post-build (garde-fou)** : `dpkg-deb -c …deb | grep .so` / `rpm -qlp …rpm | grep .so` → 3 libs ORT.
- **E2E** : GTX 1060 (Pascal) → GPU sans crash (prouvé session, 9.0.0.312) ; RTX 4070 (Ada) → latest inchangé ;
  cas détection-KO → CPU fallback propre.

## 10. Hors scope
- Re-déclenchement du script après changement de GPU via bouton dictee-setup / CLI (le script standalone le
  rend trivial — extension naturelle, pas incluse).
- Doc wiki « support GPU par archi » : à faire mais mineure une fois A+B en place.
- Détection du GPU réellement utilisé (`CUDA_VISIBLE_DEVICES`) au lieu du min pour le cas multi-GPU mixte :
  optimisation future (B couvre déjà la sécurité).
