# Multi-architecture et multi-distribution — Roadmap packaging

> Post-v1.0.0 — packaging pour d'autres architectures et distributions Linux.

## État actuel (v1.0.0)

- **Architecture** : amd64 (x86_64) uniquement
- **Formats** : .deb (Debian/Ubuntu), .tar.gz (générique)
- **Paquets** : dictee-cuda, dictee-cpu, dictee-plasmoid
- **Build** : `build-deb.sh`, compilation native

## Architectures cibles

### aarch64 (ARM64) — Priorité haute

Cible : Raspberry Pi 5, serveurs ARM (Oracle Cloud, AWS Graviton), Asahi Linux (Apple Silicon).

**Contraintes :**
- Cross-compilation Rust : bien supportée via `cross` ou `cargo-cross`
- dotool (Go) : cross-compilation native (`GOARCH=arm64`)
- ONNX Runtime (`ort`) : binaires précompilés disponibles pour aarch64
- CUDA : disponible sur aarch64 (Jetson, serveurs)
- Modèle Parakeet : identique (ONNX portable), ~2.5 Go RAM nécessaire

**Approche :**
```bash
# Via cross (Docker-based)
cargo install cross
cross build --release --target aarch64-unknown-linux-gnu

# Ou via toolchain native
rustup target add aarch64-unknown-linux-gnu
sudo apt install gcc-aarch64-linux-gnu
cargo build --release --target aarch64-unknown-linux-gnu
```

**Paquets produits :**
- `dictee-cpu_X.X.X_arm64.deb`
- `dictee-cuda_X.X.X_arm64.deb`
- `dictee-X.X.X_arm64.tar.gz`

### armv7 / riscv64 — Non prévu

- armv7 (ARM32) : RAM insuffisante pour Parakeet (2.5 Go de modèle)
- riscv64 : ONNX Runtime pas supporté

## Distributions cibles

### RPM (Fedora, openSUSE, RHEL) — Priorité haute

Deuxième plus grande base d'utilisateurs Linux après Debian/Ubuntu.

**Approche :**
- Utiliser `fpm` (Effing Package Manager) pour convertir ou générer directement
- Ou écrire un `.spec` natif pour `rpmbuild`

```bash
# Via fpm (le plus simple)
gem install fpm
fpm -s dir -t rpm -n dictee-cpu -v 1.0.0 \
    --architecture x86_64 \
    --depends pipewire --depends curl --depends ffmpeg \
    --description "Fast speech-to-text with NVIDIA Parakeet" \
    usr/=/usr/

# Ou convertir depuis le .deb
fpm -s deb -t rpm dictee-cpu_1.0.0_amd64.deb
```

**Dépendances à adapter :**
| Debian (.deb) | Fedora (.rpm) |
|---|---|
| `pipewire` | `pipewire` |
| `ffmpeg` | `ffmpeg-free` |
| `libnotify-bin` | `libnotify` |
| `python3-gi` | `python3-gobject` |
| `gir1.2-ayatanaappindicator3-0.1` | `libayatana-appindicator-gtk3` |
| `python3-numpy` | `python3-numpy` |
| `wl-clipboard` | `wl-clipboard` |

**Paquets produits :**
- `dictee-cpu-X.X.X-1.x86_64.rpm`
- `dictee-cuda-X.X.X-1.x86_64.rpm`
- `dictee-cpu-X.X.X-1.aarch64.rpm` (quand ARM64 prêt)

### AUR PKGBUILD (Arch Linux) — Priorité moyenne

Communauté active, effort faible (un seul fichier PKGBUILD).

**Approche :**
```bash
# PKGBUILD — compile depuis les sources
pkgname=dictee
pkgver=1.0.0
pkgrel=1
pkgdesc="Fast speech-to-text with NVIDIA Parakeet"
arch=('x86_64' 'aarch64')
url="https://github.com/rcspam/dictee"
license=('GPL-3.0-or-later')
depends=('pipewire' 'dotool' 'ffmpeg' 'curl')
optdepends=(
    'wl-clipboard: clipboard copy'
    'libnotify: desktop notifications'
    'python-gobject: dictee-tray'
    'python-numpy: plasmoid audio visualization'
)
makedepends=('rust' 'go' 'scdoc')
source=("$pkgname-$pkgver.tar.gz::https://github.com/rcspam/dictee/archive/v$pkgver.tar.gz")

build() {
    cd "$pkgname-$pkgver"
    cargo build --release --features sortformer
}

package() {
    cd "$pkgname-$pkgver"
    install -Dm755 target/release/transcribe "$pkgdir/usr/bin/transcribe"
    install -Dm755 target/release/transcribe-daemon "$pkgdir/usr/bin/transcribe-daemon"
    install -Dm755 target/release/transcribe-client "$pkgdir/usr/bin/transcribe-client"
    install -Dm755 target/release/transcribe-diarize "$pkgdir/usr/bin/transcribe-diarize"
    install -Dm755 target/release/transcribe-stream-diarize "$pkgdir/usr/bin/transcribe-stream-diarize"
    install -Dm755 dictee "$pkgdir/usr/bin/dictee"
    install -Dm755 dictee-setup.py "$pkgdir/usr/bin/dictee-setup"
    install -Dm755 dictee-tray.py "$pkgdir/usr/bin/dictee-tray"
    # ... man pages, services, icons, locales, plasmoid
}
```

Arch a déjà `dotool` dans les dépôts communautaires → pas besoin de le bundler.

**Publication :** soumettre sur https://aur.archlinux.org/

## Matrice de build cible

| Arch | .deb | .rpm | AUR | .tar.gz |
|------|------|------|-----|---------|
| **amd64** | CPU + CUDA | CPU + CUDA | PKGBUILD | CPU |
| **aarch64** | CPU + CUDA | CPU + CUDA | PKGBUILD | CPU |

## Automatisation CI/CD (GitHub Actions)

Pour automatiser les builds multi-arch/multi-distro :

```yaml
# .github/workflows/release.yml (esquisse)
strategy:
  matrix:
    include:
      - target: x86_64-unknown-linux-gnu
        arch: amd64
        features: "sortformer"
      - target: x86_64-unknown-linux-gnu
        arch: amd64
        features: "cuda,sortformer"
      - target: aarch64-unknown-linux-gnu
        arch: arm64
        features: "sortformer"
```

Utiliser `cross` dans le CI pour la cross-compilation ARM64.

## Roadmap

| Version | Cible | Effort |
|---------|-------|--------|
| v1.1.0 | .rpm amd64 (Fedora/openSUSE) via `fpm` | ~1 jour |
| v1.1.0 | AUR PKGBUILD (Arch) | ~0.5 jour |
| v1.2.0 | aarch64 .deb + .rpm + .tar.gz | ~2-3 jours |
| v1.2.0 | GitHub Actions CI/CD multi-arch | ~1-2 jours |
