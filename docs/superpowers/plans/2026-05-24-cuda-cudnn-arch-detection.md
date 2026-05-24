# cuDNN Arch-Detection (Component A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** À l'installation de dictee-cuda, détecter le compute capability du GPU et installer la cuDNN qui le supporte (cc < 7.5 → `nvidia-cudnn-cu12==9.0.0.312`, ≥ 7.5 → latest), au lieu de prendre aveuglément la dernière du jour qui casse Pascal.

**Architecture :** Un script shell partagé unique `setup-cuda-venv.sh` (livré dans `/usr/lib/dictee/`) contient toute la mise en place CUDA (détection + venv + pip + symlinks + ldconfig). Les 4 cibles d'installation (deb postinst, rpm %post, Arch .install, install.sh mode_tarball) l'appellent au lieu de dupliquer le bloc pip inline. Logique de mapping/détection isolée en fonctions pures, testables sans GPU.

**Tech Stack :** bash, pip (venv `/opt/dictee/cuda-venv`), nvidia-smi, ldconfig.

**Spec :** `docs/superpowers/specs/2026-05-24-cuda-cudnn-arch-detection-design.md`

**Branche :** `fix/cuda-cudnn-arch-detection` (depuis `release/1.3`). Cible v1.3.5.

---

## SCOPE DE CE PLAN

**Composant A uniquement** (détection cuDNN à l'install), pour **release/1.3**. Hors de ce plan :
- **Composant B** (fallback CPU gracieux dans le daemon Rust) → plan séparé (`...-graceful-cpu-fallback.md`).
- **Port master (v1.4)** : après validation 1.3, cherry-pick le script + adapter l'intégration (postinst master diverge).

**⚠ v1.3.5 = release de correction réputation-critique : zéro régression.** Vérif post-build obligatoire (3 libs ORT présentes) + validation sur GPU réels (GTX 1060 Pascal + RTX 4070 Ada) avant tout tag.

---

## File Structure

- **Create** `pkg/dictee/usr/lib/dictee/setup-cuda-venv.sh` — script partagé : fonctions pures (`dictee_detect_cc_int`, `dictee_cudnn_spec`) + `main` (venv + pip + symlinks + ldconfig). Inclus dans le .deb via `build-deb.sh:96` (`cp -a pkg/dictee`).
- **Create** `tests/test-cuda-cudnn-mapping.sh` — teste les fonctions pures (sans GPU, nvidia-smi mocké).
- **Modify** `pkg/dictee/DEBIAN/postinst` (~290-331) — remplacer le bloc pip inline par l'appel au script.
- **Modify** `build-rpm.sh` (%post, ~437-470) — idem + s'assurer que le script est packagé.
- **Modify** `dictee-cuda.install` (~95-125) — idem.
- **Modify** `install.sh` (`mode_tarball`, ~669-695) — installer le script + l'appeler.
- **Modify** `PKGBUILD-cuda` (~156) — `install` du script.
- **Modify** `build-tar.sh` — inclure le script dans le tarball.
- **Modify** `build-rpm.sh` (%files / install section) — packager le script.

---

## Task 1 : Fonctions pures de détection + mapping (TDD)

**Files:**
- Create: `pkg/dictee/usr/lib/dictee/setup-cuda-venv.sh`
- Test: `tests/test-cuda-cudnn-mapping.sh`

- [ ] **Step 1 : Écrire le test qui échoue**

`tests/test-cuda-cudnn-mapping.sh` :
```bash
#!/usr/bin/env bash
# Teste les fonctions pures de setup-cuda-venv.sh (sans GPU réel).
set -u
SCRIPT="$(dirname "$0")/../pkg/dictee/usr/lib/dictee/setup-cuda-venv.sh"
# shellcheck disable=SC1090
DICTEE_CUDA_LIB_SOURCED=1 source "$SCRIPT"   # source sans lancer main

fail=0
check() { # check <desc> <attendu> <obtenu>
  if [ "$2" = "$3" ]; then echo "ok   - $1"; else echo "FAIL - $1 : attendu '$2', obtenu '$3'"; fail=1; fi
}

# --- mapping cc_int -> spec cuDNN ---
check "Pascal 6.1 -> pin 9.0.0.312" "nvidia-cudnn-cu12==9.0.0.312" "$(dictee_cudnn_spec 61)"
check "Maxwell 5.0 -> pin 9.0.0.312" "nvidia-cudnn-cu12==9.0.0.312" "$(dictee_cudnn_spec 50)"
check "Volta 7.0 -> pin 9.0.0.312"   "nvidia-cudnn-cu12==9.0.0.312" "$(dictee_cudnn_spec 70)"
check "Turing 7.5 -> latest"         "nvidia-cudnn-cu12"            "$(dictee_cudnn_spec 75)"
check "Ada 8.9 -> latest"            "nvidia-cudnn-cu12"            "$(dictee_cudnn_spec 89)"
check "Blackwell 12.0 -> latest"     "nvidia-cudnn-cu12"            "$(dictee_cudnn_spec 120)"
check "cc vide (détection KO) -> latest" "nvidia-cudnn-cu12"        "$(dictee_cudnn_spec '')"

# --- parsing compute_cap via nvidia-smi mocké ---
mock_nvsmi() { # crée un faux nvidia-smi dans un PATH temporaire ; $1 = sortie
  MOCKDIR="$(mktemp -d)"; printf '#!/bin/sh\nprintf "%%s\\n" "%s"\n' "$1" > "$MOCKDIR/nvidia-smi"
  chmod +x "$MOCKDIR/nvidia-smi"; PATH="$MOCKDIR:$PATH"
}
( mock_nvsmi "6.1";        check "1 GPU 6.1 -> 61"        "61" "$(dictee_detect_cc_int)" )
( mock_nvsmi $'8.9\n6.1';  check "multi-GPU -> min (61)"  "61" "$(dictee_detect_cc_int)" )
( mock_nvsmi "12.0";       check "Blackwell -> 120"       "120" "$(dictee_detect_cc_int)" )
( mock_nvsmi "";           check "sortie vide -> rien"    ""  "$(dictee_detect_cc_int)" )
( mock_nvsmi "N/A";        check "N/A -> rien"            ""  "$(dictee_detect_cc_int)" )

exit $fail
```

- [ ] **Step 2 : Lancer le test → échoue (script absent)**

Run: `bash tests/test-cuda-cudnn-mapping.sh`
Expected: FAIL — `setup-cuda-venv.sh: No such file` (ou source échoue).

- [ ] **Step 3 : Écrire le script avec les fonctions pures + le guard de sourcing**

`pkg/dictee/usr/lib/dictee/setup-cuda-venv.sh` :
```bash
#!/usr/bin/env bash
# dictee-cuda : met en place /opt/dictee/cuda-venv avec la BONNE cuDNN selon le GPU,
# puis symlinke les libs dans /usr/lib/dictee/ (ldconfig les trouve via ld.so.conf.d/dictee.conf).
# Sélection cuDNN : compute_cap < 7.5 (Pascal/Volta/Maxwell) -> 9.0.0.312 (dernière supportant Pascal) ;
#                   >= 7.5 (Turing -> Blackwell) -> latest.
# Voir docs/superpowers/specs/2026-05-24-cuda-cudnn-arch-detection-design.md

CUDA_VENV="/opt/dictee/cuda-venv"
DICTEE_LIB_DIR="/usr/lib/dictee"
CUDNN_LEGACY_PIN="nvidia-cudnn-cu12==9.0.0.312"   # dernière cuDNN supportant Pascal (cc 6.x), prouvée GTX 1060
CUDNN_LATEST="nvidia-cudnn-cu12"
OTHER_CUDA_LIBS="nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 nvidia-cufft-cu12 nvidia-curand-cu12 nvidia-cuda-nvrtc-cu12"

# Détecte le compute_cap minimum (entier X*10+Y) des GPU NVIDIA. Echo l'entier, ou rien si indétectable.
dictee_detect_cc_int() {
    command -v nvidia-smi >/dev/null 2>&1 || return 0
    local out cc major minor v min=""
    out="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null)" || return 0
    while IFS= read -r cc; do
        cc="${cc//[[:space:]]/}"
        case "$cc" in
            [0-9]*.[0-9]*) ;;          # garde uniquement "X.Y"
            *) continue ;;
        esac
        major="${cc%%.*}"; minor="${cc##*.}"
        v=$(( major * 10 + minor ))
        if [ -z "$min" ] || [ "$v" -lt "$min" ]; then min="$v"; fi
    done <<EOF
$out
EOF
    [ -n "$min" ] && printf '%s\n' "$min"
}

# Echo la spec pip pour nvidia-cudnn-cu12 selon le cc entier. cc vide => latest (détection KO).
dictee_cudnn_spec() {
    local cc="${1:-}"
    if [ -n "$cc" ] && [ "$cc" -lt 75 ] 2>/dev/null; then
        printf '%s\n' "$CUDNN_LEGACY_PIN"
    else
        printf '%s\n' "$CUDNN_LATEST"
    fi
}

dictee_setup_cuda_venv_main() {
    # ... (Task 2) ...
    :
}

# Ne lance main que si exécuté directement (pas si sourcé par les tests).
if [ -z "${DICTEE_CUDA_LIB_SOURCED:-}" ]; then
    dictee_setup_cuda_venv_main "$@"
fi
```

- [ ] **Step 4 : Lancer le test → passe**

Run: `bash tests/test-cuda-cudnn-mapping.sh`
Expected: PASS — toutes les lignes `ok`, exit 0.

- [ ] **Step 5 : Commit**

```bash
chmod +x pkg/dictee/usr/lib/dictee/setup-cuda-venv.sh tests/test-cuda-cudnn-mapping.sh
git add pkg/dictee/usr/lib/dictee/setup-cuda-venv.sh tests/test-cuda-cudnn-mapping.sh
git commit -m "feat(cuda): GPU compute_cap detection + cuDNN version mapping (pure fns, TDD)"
```

---

## Task 2 : Corps du script (venv + pip + symlinks + ldconfig, robuste)

**Files:**
- Modify: `pkg/dictee/usr/lib/dictee/setup-cuda-venv.sh` (remplir `dictee_setup_cuda_venv_main`)

Reproduit EXACTEMENT le mécanisme du postinst actuel (créer venv → pip → symlink lib*.so* → ldconfig)
en y insérant la détection. Points de robustesse §7 du spec : idempotence, nettoyage des symlinks périmés,
échec pip géré, parsing sûr.

- [ ] **Step 1 : Implémenter `dictee_setup_cuda_venv_main`**

Remplacer le corps de la fonction (Task 1) par :
```bash
dictee_setup_cuda_venv_main() {
    # Guard : variante CUDA uniquement (provider .so présent)
    [ -f "$DICTEE_LIB_DIR/libonnxruntime_providers_cuda.so" ] || return 0
    command -v python3 >/dev/null 2>&1 || { echo "⚠ python3 absent"; return 1; }

    mkdir -p /opt/dictee
    if [ ! -x "$CUDA_VENV/bin/pip" ]; then
        python3 -m venv "$CUDA_VENV" || { echo "⚠ python3 -m venv a échoué — python3-venv installé ?"; return 1; }
        "$CUDA_VENV/bin/pip" install --quiet --upgrade pip 2>/dev/null || true
    fi

    local cc_int cudnn_spec
    cc_int="$(dictee_detect_cc_int)"
    cudnn_spec="$(dictee_cudnn_spec "$cc_int")"
    echo "→ GPU compute_cap détecté : ${cc_int:-inconnu} → cuDNN : $cudnn_spec"
    if [ -z "$cc_int" ]; then
        echo "  (détection GPU impossible — cuDNN latest par défaut ; le fallback CPU du daemon couvre les vieux GPU)"
    fi

    echo "→ Téléchargement des libs NVIDIA CUDA (≈ 1,5 Go, peut prendre plusieurs minutes)..."
    # shellcheck disable=SC2086
    if ! "$CUDA_VENV/bin/pip" install --quiet --upgrade $OTHER_CUDA_LIBS "$cudnn_spec"; then
        echo "⚠ pip install des libs NVIDIA a échoué (pas d'internet ? disque plein ?)"
        echo "  Relancer : sudo $CUDA_VENV/bin/pip install $OTHER_CUDA_LIBS $cudnn_spec && sudo ldconfig"
        return 2
    fi

    # Nettoyer les symlinks périmés de $DICTEE_LIB_DIR pointant vers le venv (cas downgrade de version)
    local _l _t
    for _l in "$DICTEE_LIB_DIR"/lib*.so*; do
        [ -L "$_l" ] || continue
        _t="$(readlink "$_l")"
        case "$_t" in "$CUDA_VENV"/*) [ -e "$_l" ] || rm -f "$_l" ;; esac
    done

    # (Re)symlink toutes les lib*.so* du venv → /usr/lib/dictee/
    local _py _root _sub _so _count=0
    _py="$(ls "$CUDA_VENV/lib/" 2>/dev/null | grep -E '^python' | head -1)"
    if [ -n "$_py" ]; then
        _root="$CUDA_VENV/lib/$_py/site-packages/nvidia"
        for _sub in "$_root"/*/lib; do
            [ -d "$_sub" ] || continue
            for _so in "$_sub"/lib*.so*; do
                [ -f "$_so" ] || continue
                ln -sf "$_so" "$DICTEE_LIB_DIR/$(basename "$_so")"
                _count=$((_count + 1))
            done
        done
        echo "✓ $_count libs NVIDIA liées dans $DICTEE_LIB_DIR/"
    fi
    ldconfig 2>/dev/null || true
    return 0
}
```

- [ ] **Step 2 : Re-lancer le test des fonctions pures (non régressé)**

Run: `bash tests/test-cuda-cudnn-mapping.sh`
Expected: PASS (le sourcing ne lance pas main, les fonctions pures inchangées).

- [ ] **Step 3 : Vérif syntaxe shell**

Run: `bash -n pkg/dictee/usr/lib/dictee/setup-cuda-venv.sh && echo "syntaxe OK"`
Expected: `syntaxe OK`. (Si `shellcheck` dispo : `shellcheck pkg/dictee/usr/lib/dictee/setup-cuda-venv.sh` — warnings tolérés, pas d'erreur.)

- [ ] **Step 4 : Commit**

```bash
git add pkg/dictee/usr/lib/dictee/setup-cuda-venv.sh
git commit -m "feat(cuda): setup-cuda-venv.sh body (venv+pip+symlinks+ldconfig, idempotent)"
```

---

## Task 3 : Brancher le postinst .deb sur le script

**Files:**
- Modify: `pkg/dictee/DEBIAN/postinst` (bloc venv/pip, repéré par `nvidia-cudnn-cu12`, ~290-331)

- [ ] **Step 1 : Remplacer le bloc inline par l'appel au script**

Dans `pkg/dictee/DEBIAN/postinst`, le bloc `elif [ -f /usr/lib/dictee/libonnxruntime_providers_cuda.so ] ... fi`
(création venv + `pip install nvidia-*-cu12` + symlinks, ~290-331) devient :
```bash
elif [ -f /usr/lib/dictee/setup-cuda-venv.sh ]; then
    bash /usr/lib/dictee/setup-cuda-venv.sh || \
        echo "⚠ Mise en place CUDA incomplète — voir les messages ci-dessus."
fi
```
(Le guard « provider_cuda.so présent » + le message offline sont désormais DANS le script.)

- [ ] **Step 2 : Vérif syntaxe**

Run: `bash -n pkg/dictee/DEBIAN/postinst && echo OK`
Expected: `OK`.

- [ ] **Step 3 : Commit**

```bash
git add pkg/dictee/DEBIAN/postinst
git commit -m "refactor(deb): postinst calls shared setup-cuda-venv.sh"
```

---

## Task 4 : Brancher rpm %post, Arch .install, install.sh + packager le script partout

**Files:**
- Modify: `build-rpm.sh` (%post ~437-470, + section %files/install pour packager le script)
- Modify: `dictee-cuda.install` (~95-125)
- Modify: `install.sh` (`mode_tarball` ~669-695)
- Modify: `PKGBUILD-cuda` (~156)
- Modify: `build-tar.sh` (inclure le script dans le tarball)

- [ ] **Step 1 : rpm %post → appel script**

Dans `build-rpm.sh`, remplacer le bloc inline `pip install nvidia-*-cu12` du %post par :
```bash
if [ -f /usr/lib/dictee/setup-cuda-venv.sh ]; then
    bash /usr/lib/dictee/setup-cuda-venv.sh || echo "⚠ Mise en place CUDA incomplète."
fi
```
Et s'assurer que `setup-cuda-venv.sh` est **packagé** dans le .rpm (section qui copie les fichiers
`usr/lib/dictee/` — suivre le pattern `dictee_models.py` / `dictee-common.sh`).

- [ ] **Step 2 : Arch .install → appel script**

Dans `dictee-cuda.install`, remplacer le bloc inline pip par :
```bash
if [ -f /usr/lib/dictee/setup-cuda-venv.sh ]; then
    bash /usr/lib/dictee/setup-cuda-venv.sh || echo "Warning: CUDA setup incomplete."
fi
```
Et dans `PKGBUILD-cuda` (après `install -d "$pkgdir/usr/lib/dictee"`, ~156) ajouter :
```bash
install -Dm755 pkg/dictee/usr/lib/dictee/setup-cuda-venv.sh "$pkgdir/usr/lib/dictee/setup-cuda-venv.sh"
```

- [ ] **Step 3 : install.sh mode_tarball → installer + appeler le script**

Dans `install.sh` `mode_tarball`, à côté de l'install de `dictee_models.py` (~673) ajouter :
```bash
    [[ -f "$SCRIPT_DIR/usr/lib/dictee/setup-cuda-venv.sh" ]] \
        && install -Dm755 "$SCRIPT_DIR/usr/lib/dictee/setup-cuda-venv.sh" /usr/lib/dictee/setup-cuda-venv.sh
```
Et remplacer le bloc inline pip (~694+) par :
```bash
    if [[ -f /usr/lib/dictee/setup-cuda-venv.sh ]]; then
        bash /usr/lib/dictee/setup-cuda-venv.sh || warn "Mise en place CUDA incomplète."
    fi
```
Et dans `build-tar.sh` : s'assurer que `setup-cuda-venv.sh` est copié dans l'arbre du tarball (suivre le
pattern `dictee_models.py` / `dictee-common.sh`).

- [ ] **Step 4 : Vérif syntaxe des 4 fichiers shell modifiés**

Run: `for f in build-rpm.sh dictee-cuda.install install.sh build-tar.sh; do bash -n "$f" && echo "$f OK"; done`
Expected: 4× `OK`.

- [ ] **Step 5 : Commit**

```bash
git add build-rpm.sh dictee-cuda.install install.sh PKGBUILD-cuda build-tar.sh
git commit -m "refactor(pkg): rpm/arch/tarball call shared setup-cuda-venv.sh (4 targets aligned)"
```

---

## Task 5 : Build + vérification garde-fou + validation GPU réels

**Files:** aucun (vérification).

- [ ] **Step 1 : Lire `feedback-cuda-build-flags` avant build** (flags cargo exacts, garde-fou 3 libs).

- [ ] **Step 2 : Build deb (CPU + CUDA)**

Run: `./build-deb.sh` (cf. CLAUDE.md). Expected: exit 0, `dictee-cpu_*.deb` + `dictee-cuda_*.deb` produits.

- [ ] **Step 3 : Garde-fou — le script EST dans le .deb + les 3 libs ORT présentes**

Run:
```bash
dpkg-deb -c .dev/dist/dictee-cuda_*.deb 2>/dev/null | grep -E "setup-cuda-venv.sh|/usr/lib/dictee/.*\.so" || \
dpkg-deb -c dictee-cuda_*.deb | grep -E "setup-cuda-venv.sh|/usr/lib/dictee/.*\.so"
```
Expected: voir `usr/lib/dictee/setup-cuda-venv.sh` **ET** les 3 libs (`libonnxruntime.so`,
`libonnxruntime_providers_cuda.so`, `libonnxruntime_providers_shared.so`). Si une manque → NE PAS releaser.

- [ ] **Step 4 : Validation E2E sur GPU réels (obligatoire avant tag)**

- **GTX 1060 (Pascal, machine sylvie via SSH)** : installer le .deb (ou copier le script + relancer le
  postinst), vérifier `pip show nvidia-cudnn-cu12` → **9.0.0.312**, puis
  `systemctl --user restart dictee.service` → `journalctl … -n 3` montre « Model loaded. Listening » (pas de
  crash-loop) + `nvidia-smi --query-compute-apps=...` montre `transcribe-daemon` sur le GPU.
- **RTX 4070 (Ada, ce host)** : vérifier que la cuDNN reste **latest** (≥ 9.12) et que le daemon charge GPU
  comme avant (non régressé).

- [ ] **Step 5 : Commit éventuel + handoff** (rien à committer si build/vérif OK ; sinon corriger).

---

## Self-Review (rempli)

- **Couverture spec §4 (détection+mapping)** : Tasks 1-2. §4.3 (script partagé) : Tasks 2-4. §4.4 (ne pas
  toucher les 3 .so ORT) : Task 5 step 3 le vérifie. §7 robustesse (parsing/idempotence/symlinks périmés/échec
  pip/multi-méthode) : couvert dans le script Task 2 + tests Task 1. §8 (8 fichiers) : Tasks 3-4.
- **Hors de CE plan (rappel)** : §5 (fallback B), §6 INT8/notif master, port master. → plans séparés.
- **Placeholders** : aucun ; tout le code des fonctions pures + corps + intégrations est fourni.
- **Cohérence noms** : `dictee_detect_cc_int`, `dictee_cudnn_spec`, `dictee_setup_cuda_venv_main`,
  `DICTEE_CUDA_LIB_SOURCED`, `setup-cuda-venv.sh` — identiques partout.
- **Gap connu** : la détection multi-méthode §4.1 (fallback `nvidia-smi -L`/nom) n'est PAS dans ce plan
  (seulement compute_cap → sinon latest + B). Acceptable : B est le vrai filet ; le parsing-nom serait du
  gold-plating. À noter si on veut le durcir plus tard.
