# Maintainer: rcspam <rcspams@gmail.com>
pkgname=dictee
pkgver=1.3.0.beta4
pkgrel=1
_tag=1.3.0-beta4
pkgdesc="Fast push-to-talk voice dictation for Linux with NVIDIA Parakeet, Vosk and faster-whisper"
arch=('x86_64' 'aarch64')
url="https://github.com/rcspam/dictee"
license=('GPL-3.0-or-later')
depends=(
    'python'
    'pipewire'
    'dotool'
    'libnotify'
    'libpulse'
    'python-pyqt6'
    'qt6-multimedia'
    'qt6-svg'
    'sox'
)
optdepends=(
    'python-evdev: dictee-ptt key grab (recommended)'
    'wl-clipboard: clipboard copy (Wayland)'
    'xclip: clipboard copy (X11)'
    'curl: LibreTranslate translation'
    'translate-shell: translation via Google/Bing'
    'python-numpy: plasmoid audio visualization'
    'ollama: 100% local translation'
    'docker: LibreTranslate local translation'
    'libayatana-appindicator: GNOME tray icon support'
    'cuda: NVIDIA GPU acceleration'
    'cudnn: NVIDIA cuDNN for GPU acceleration'
)
makedepends=('rust' 'cargo' 'gettext' 'git')
install=dictee.install
source=("$pkgname-$_tag.tar.gz::https://github.com/rcspam/dictee/archive/v$_tag.tar.gz")
sha256sums=('SKIP')

build() {
    cd "$pkgname-$_tag"

    # Build Rust binaries
    cargo build --release --features sortformer \
        --bin transcribe \
        --bin transcribe-daemon \
        --bin transcribe-client \
        --bin transcribe-diarize \
        --bin transcribe-stream-diarize

    # Compile locales from .po sources
    for lang in fr de es it pt uk; do
        if [ -f "po/$lang.po" ]; then
            msgfmt -o "po/$lang.mo" "po/$lang.po"
        fi
    done

    # Build plasmoid
    if [ -d "plasmoid/package" ]; then
        (cd plasmoid/package && zip -r "../../dictee.plasmoid" metadata.json contents/)
    fi
}

package() {
    cd "$pkgname-$_tag"

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
    install -Dm755 dictee-switch-backend "$pkgdir/usr/bin/dictee-switch-backend"
    install -Dm755 dictee-postprocess.py "$pkgdir/usr/bin/dictee-postprocess"
    install -Dm755 dictee-test-rules "$pkgdir/usr/bin/dictee-test-rules"
    install -Dm755 dictee-transcribe.py "$pkgdir/usr/bin/dictee-transcribe"
    install -Dm755 dictee-reset "$pkgdir/usr/bin/dictee-reset"
    install -Dm755 dictee-translate-langs "$pkgdir/usr/bin/dictee-translate-langs"
    install -Dm755 pkg/dictee/usr/bin/dictee-audio-sources "$pkgdir/usr/bin/dictee-audio-sources"
    install -Dm755 pkg/dictee/usr/bin/dictee-plasmoid-level "$pkgdir/usr/bin/dictee-plasmoid-level"
    install -Dm755 pkg/dictee/usr/bin/dictee-plasmoid-level-daemon "$pkgdir/usr/bin/dictee-plasmoid-level-daemon"
    install -Dm755 pkg/dictee/usr/bin/dictee-plasmoid-level-fft "$pkgdir/usr/bin/dictee-plasmoid-level-fft"
    install -Dm755 pkg/dictee/usr/bin/transcribe-daemon-vosk "$pkgdir/usr/bin/transcribe-daemon-vosk"
    install -Dm755 pkg/dictee/usr/bin/transcribe-daemon-whisper "$pkgdir/usr/bin/transcribe-daemon-whisper"

    # Systemd services
    install -Dm644 pkg/dictee/usr/lib/systemd/user/dictee.service "$pkgdir/usr/lib/systemd/user/dictee.service"
    install -Dm644 pkg/dictee/usr/lib/systemd/user/dictee-tray.service "$pkgdir/usr/lib/systemd/user/dictee-tray.service"
    install -Dm644 pkg/dictee/usr/lib/systemd/user/dictee-ptt.service "$pkgdir/usr/lib/systemd/user/dictee-ptt.service"
    install -Dm644 pkg/dictee/usr/lib/systemd/user/dictee-vosk.service "$pkgdir/usr/lib/systemd/user/dictee-vosk.service"
    install -Dm644 pkg/dictee/usr/lib/systemd/user/dictee-whisper.service "$pkgdir/usr/lib/systemd/user/dictee-whisper.service"
    install -Dm644 pkg/dictee/usr/lib/systemd/user/dictee-canary.service "$pkgdir/usr/lib/systemd/user/dictee-canary.service"
    install -Dm644 pkg/dictee/usr/lib/systemd/user/dotoold.service "$pkgdir/usr/lib/systemd/user/dotoold.service"
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

    # Assets (wizard banners + logos)
    install -d "$pkgdir/usr/share/dictee/assets"
    install -Dm644 assets/banner-dark.svg "$pkgdir/usr/share/dictee/assets/banner-dark.svg"
    install -Dm644 assets/banner-light.svg "$pkgdir/usr/share/dictee/assets/banner-light.svg"
    if [ -d assets/logos ]; then
        install -d "$pkgdir/usr/share/dictee/assets/logos"
        for f in assets/logos/*.svg; do
            [ -f "$f" ] && install -Dm644 "$f" "$pkgdir/usr/share/dictee/assets/logos/$(basename "$f")"
        done
    fi
    if [ -d assets/icons ]; then
        install -d "$pkgdir/usr/share/dictee/assets/icons"
        for f in assets/icons/*.svg; do
            [ -f "$f" ] && install -Dm644 "$f" "$pkgdir/usr/share/dictee/assets/icons/$(basename "$f")"
        done
    fi

    # Locales (compiled in build())
    for lang in fr de es it pt uk; do
        if [ -f "po/$lang.mo" ]; then
            install -Dm644 "po/$lang.mo" "$pkgdir/usr/share/locale/$lang/LC_MESSAGES/dictee.mo"
        fi
    done

    # Desktop entries
    install -Dm644 pkg/dictee/usr/share/applications/dictee-setup.desktop "$pkgdir/usr/share/applications/dictee-setup.desktop"
    install -Dm644 pkg/dictee/usr/share/applications/dictee-tray.desktop "$pkgdir/usr/share/applications/dictee-tray.desktop"

    # Plasmoid
    if [ -f "dictee.plasmoid" ]; then
        install -Dm644 dictee.plasmoid "$pkgdir/usr/share/dictee/dictee.plasmoid"
    fi

    # Shared libraries
    install -Dm644 dictee-common.sh "$pkgdir/usr/lib/dictee/dictee-common.sh"
    install -Dm644 dictee_models.py "$pkgdir/usr/lib/dictee/dictee_models.py"

    # Default config files
    install -Dm644 dictee.conf.example "$pkgdir/usr/share/dictee/dictee.conf.example"
    install -Dm644 rules.conf.default "$pkgdir/usr/share/dictee/rules.conf.default"
    install -Dm644 dictionary.conf.default "$pkgdir/usr/share/dictee/dictionary.conf.default"
    install -Dm644 continuation.conf.default "$pkgdir/usr/share/dictee/continuation.conf.default"

    # VERSION file (generated at build time)
    echo "$pkgver build $(git rev-parse --short HEAD 2>/dev/null || echo unknown)" \
        > "$pkgdir/usr/share/dictee/VERSION"
    chmod 644 "$pkgdir/usr/share/dictee/VERSION"
}
