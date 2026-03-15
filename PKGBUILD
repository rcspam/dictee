# Maintainer: rcspam <rcspams@gmail.com>
pkgname=dictee
pkgver=1.0.0
pkgrel=1
pkgdesc="Fast push-to-talk voice dictation for Linux with NVIDIA Parakeet, Vosk and faster-whisper"
arch=('x86_64' 'aarch64')
url="https://github.com/rcspam/dictee"
license=('GPL-3.0-or-later')
depends=(
    'pipewire'
    'dotool'
    'ffmpeg'
    'curl'
    'python-pyqt6'
    'python-pyqt6-multimedia'
)
optdepends=(
    'wl-clipboard: clipboard copy'
    'libnotify: desktop notifications'
    'python-gobject: dictee-tray notification icon'
    'python-evdev: dictee-ptt key grab (recommended)'
    'python-numpy: plasmoid audio visualization'
    'pulseaudio-utils: plasmoid audio visualization (parec)'
    'translate-shell: translation via Google/Bing'
    'ollama: 100% local translation'
    'docker: LibreTranslate local translation'
)
makedepends=('rust' 'cargo' 'go' 'scdoc' 'libxkbcommon' 'git')
source=("$pkgname-$pkgver.tar.gz::https://github.com/rcspam/dictee/archive/v$pkgver.tar.gz")
sha256sums=('SKIP')

build() {
    cd "$pkgname-$pkgver"

    # Build Rust binaries
    cargo build --release --features sortformer \
        --bin transcribe \
        --bin transcribe-daemon \
        --bin transcribe-client \
        --bin transcribe-diarize \
        --bin transcribe-stream-diarize

    # Build dotool
    if [ ! -d "/tmp/dotool-build" ]; then
        git clone https://git.sr.ht/~geb/dotool /tmp/dotool-build
        (cd /tmp/dotool-build && ./build.sh)
    fi

    # Build plasmoid
    if [ -d "plasmoid/package" ]; then
        (cd plasmoid/package && zip -r "../../dictee.plasmoid" metadata.json contents/)
    fi
}

package() {
    cd "$pkgname-$pkgver"

    # Rust binaries
    install -Dm755 target/release/transcribe "$pkgdir/usr/bin/transcribe"
    install -Dm755 target/release/transcribe-daemon "$pkgdir/usr/bin/transcribe-daemon"
    install -Dm755 target/release/transcribe-client "$pkgdir/usr/bin/transcribe-client"
    install -Dm755 target/release/transcribe-diarize "$pkgdir/usr/bin/transcribe-diarize"
    install -Dm755 target/release/transcribe-stream-diarize "$pkgdir/usr/bin/transcribe-stream-diarize"

    # Scripts
    install -Dm755 dictee "$pkgdir/usr/bin/dictee"
    install -Dm755 dictee-setup.py "$pkgdir/usr/bin/dictee-setup"
    install -Dm755 dictee-tray.py "$pkgdir/usr/bin/dictee-tray"
    install -Dm755 dictee-ptt.py "$pkgdir/usr/bin/dictee-ptt"
    install -Dm755 pkg/dictee/usr/bin/dictee-plasmoid-level "$pkgdir/usr/bin/dictee-plasmoid-level"
    install -Dm755 pkg/dictee/usr/bin/dictee-plasmoid-level-daemon "$pkgdir/usr/bin/dictee-plasmoid-level-daemon"
    install -Dm755 pkg/dictee/usr/bin/dictee-plasmoid-level-fft "$pkgdir/usr/bin/dictee-plasmoid-level-fft"
    install -Dm755 pkg/dictee/usr/bin/transcribe-daemon-vosk "$pkgdir/usr/bin/transcribe-daemon-vosk"
    install -Dm755 pkg/dictee/usr/bin/transcribe-daemon-whisper "$pkgdir/usr/bin/transcribe-daemon-whisper"

    # dotool
    install -Dm755 /tmp/dotool-build/dotool "$pkgdir/usr/bin/dotool"
    install -Dm755 /tmp/dotool-build/dotoold "$pkgdir/usr/bin/dotoold"
    install -Dm644 /tmp/dotool-build/80-dotool.rules "$pkgdir/etc/udev/rules.d/80-dotool.rules"

    # Systemd services
    install -Dm644 pkg/dictee/usr/lib/systemd/user/dictee.service "$pkgdir/usr/lib/systemd/user/dictee.service"
    install -Dm644 pkg/dictee/usr/lib/systemd/user/dictee-tray.service "$pkgdir/usr/lib/systemd/user/dictee-tray.service"
    install -Dm644 pkg/dictee/usr/lib/systemd/user/dictee-ptt.service "$pkgdir/usr/lib/systemd/user/dictee-ptt.service"
    install -Dm644 pkg/dictee/usr/lib/systemd/user/dictee-vosk.service "$pkgdir/usr/lib/systemd/user/dictee-vosk.service"
    install -Dm644 pkg/dictee/usr/lib/systemd/user/dictee-whisper.service "$pkgdir/usr/lib/systemd/user/dictee-whisper.service"
    install -Dm644 pkg/dictee/usr/lib/systemd/user-preset/90-dictee.preset "$pkgdir/usr/lib/systemd/user-preset/90-dictee.preset"

    # Man pages
    for f in pkg/dictee/usr/share/man/man1/*.1; do
        install -Dm644 "$f" "$pkgdir/usr/share/man/man1/$(basename "$f")"
    done
    for f in pkg/dictee/usr/share/man/fr/man1/*.1; do
        install -Dm644 "$f" "$pkgdir/usr/share/man/fr/man1/$(basename "$f")"
    done

    # Icons
    for f in pkg/dictee/usr/share/icons/hicolor/scalable/apps/*.svg; do
        install -Dm644 "$f" "$pkgdir/usr/share/icons/hicolor/scalable/apps/$(basename "$f")"
    done

    # Locales
    for lang in fr de es it pt uk; do
        for f in pkg/dictee/usr/share/locale/$lang/LC_MESSAGES/*.mo; do
            [ -f "$f" ] && install -Dm644 "$f" "$pkgdir/usr/share/locale/$lang/LC_MESSAGES/$(basename "$f")"
        done
    done

    # Desktop entry
    install -Dm644 pkg/dictee/usr/share/applications/dictee-setup.desktop "$pkgdir/usr/share/applications/dictee-setup.desktop"
    install -Dm644 pkg/dictee/usr/share/applications/dictee-tray.desktop "$pkgdir/usr/share/applications/dictee-tray.desktop"

    # Plasmoid
    if [ -f "dictee.plasmoid" ]; then
        install -Dm644 dictee.plasmoid "$pkgdir/usr/share/dictee/dictee.plasmoid"
    fi
}
