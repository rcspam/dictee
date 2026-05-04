#!/bin/bash
# build-tar.sh — build the universal CUDA tarball, standalone.
#
# Previously bundled inside build-deb.sh's build_tarball() — that
# coupled the tarball to the .deb pipeline AND silently shipped CPU
# binaries (incident 2026-05-02): build-deb.sh's CPU step overwrote
# target/release/ before the tarball was assembled, so the "universal"
# archive contained CPU-only Rust binaries.
#
# This script does its own CUDA build (with the strict flags) and
# never touches CPU binaries, so the result is always GPU-capable.
set -e

cd "$(dirname "$0")"

VERSION="1.3.1"
PKG_DIR="pkg/dictee"
DIST_DIR=".dev/dist"
mkdir -p "$DIST_DIR"

# shellcheck disable=SC1091
source ./build-common.sh

echo "========================================"
echo "  Building dictee tarball $VERSION (CUDA)"
echo "========================================"

# 1. Wrappers Python / shell, locales, configs, assets
echo ""
echo "=== [TAR.GZ] Scaffolding pkg dir ==="
dict_prepare_pkg_dir

# 2. Plasmoid + extra binaries / configs that build-deb.sh layers on top.
#    Re-pulled here because the tarball doesn't go through build-deb.sh
#    anymore. Idempotent — fine to overwrite.
mkdir -p "$PKG_DIR/usr/lib/systemd/user" \
         "$PKG_DIR/usr/lib/systemd/user-preset" \
         "$PKG_DIR/usr/share/man/man1" \
         "$PKG_DIR/usr/share/man/fr/man1" \
         "$PKG_DIR/usr/share/icons/hicolor/scalable/apps" \
         "$PKG_DIR/usr/share/applications" \
         "$PKG_DIR/etc/udev/rules.d"

# Audio level helpers (ship-as-is)
[ -f ./dictee-plasmoid-level ]         && cp ./dictee-plasmoid-level         "$PKG_DIR/usr/bin/"
[ -f ./dictee-plasmoid-level-daemon ]  && cp ./dictee-plasmoid-level-daemon  "$PKG_DIR/usr/bin/"
[ -f ./dictee-plasmoid-level-fft ]     && cp ./dictee-plasmoid-level-fft     "$PKG_DIR/usr/bin/"

# systemd user services + presets
cp -r ./systemd/user/*.service       "$PKG_DIR/usr/lib/systemd/user/"        2>/dev/null || true
cp -r ./systemd/user-preset/*.preset "$PKG_DIR/usr/lib/systemd/user-preset/" 2>/dev/null || true

# Icons + .desktop
cp ./icons/*.svg                          "$PKG_DIR/usr/share/icons/hicolor/scalable/apps/" 2>/dev/null || true
cp ./*.desktop                            "$PKG_DIR/usr/share/applications/"                2>/dev/null || true

# Udev rules (dotool)
[ -f ./80-dotool.rules ] && cp ./80-dotool.rules "$PKG_DIR/etc/udev/rules.d/"

# Build dotool / plasmoid via build-deb helpers if not already there.
# Same logic factor: we tolerate them being absent — the universal
# tarball's install.sh will degrade gracefully (no plasmoid install
# attempted if the file is missing).
if [ ! -f "$PKG_DIR/usr/bin/dotool" ] && [ -x ./build-deb.sh ]; then
    echo "Note: dotool/plasmoid not pre-staged — run ./build-deb.sh once if needed"
fi

# 3. Build Rust binaries in CUDA load-dynamic mode (the only mode that
#    actually uses the GPU at runtime). Forced rebuild — see comment on
#    build-rpm.sh:185 for why we don't trust target/release/ contents.
echo ""
echo "=== [TAR.GZ] Cargo build CUDA (forced) ==="
cargo build --release --no-default-features \
    --features "cuda,sortformer,load-dynamic" \
    --bin transcribe \
    --bin transcribe-daemon \
    --bin transcribe-client \
    --bin transcribe-diarize \
    --bin transcribe-stream-diarize \
    --bin transcribe-diarize-batch \
    --bin diarize-only

# Hard guard: only the load-dynamic CUDA build emits this provider lib.
# Without it the binaries would silently fall back to CPU at runtime.
if [ ! -f target/release/libonnxruntime_providers_cuda.so ]; then
    echo "FATAL: CUDA build failed — libonnxruntime_providers_cuda.so missing in target/release/" >&2
    exit 1
fi

# 4. Find libonnxruntime.so. With load-dynamic, ort doesn't bundle the
#    main shared lib in target/release/ — we have to source it from the
#    ONNX Runtime GPU tarball (downloaded by build-deb.sh's first run,
#    cached by ort.pyke.io).
ORT_LIB=""
for candidate in \
    "target/release/libonnxruntime.so" \
    onnxruntime-linux-x64-gpu-*/lib/libonnxruntime.so \
    "$HOME/.cache/ort.pyke.io/dfbin"/*/libonnxruntime.so; do
    # shellcheck disable=SC2086
    for f in $candidate; do
        if [ -f "$f" ]; then
            ORT_LIB="$f"
            break 2
        fi
    done
done
if [ -z "$ORT_LIB" ]; then
    echo "FATAL: libonnxruntime.so not found — run ./build-deb.sh once first to populate ort cache" >&2
    exit 1
fi
ORT_LIB_DIR="$(dirname "$ORT_LIB")"
echo "Using libonnxruntime.so from: $ORT_LIB"

# Sanity-check the two CUDA providers next to the main lib (or in
# target/release/ if cargo dropped them there).
for lib in libonnxruntime_providers_cuda.so libonnxruntime_providers_shared.so; do
    if [ ! -f "$ORT_LIB_DIR/$lib" ] && [ ! -f "target/release/$lib" ]; then
        echo "FATAL: $lib not found in $ORT_LIB_DIR/ nor target/release/" >&2
        exit 1
    fi
done

# 5. Assemble the tarball staging dir
echo ""
echo "=== [TAR.GZ] Assembling staging dir ==="
TARBALL_DIR="dictee-${VERSION}"
rm -rf "$TARBALL_DIR"
mkdir -p \
    "$TARBALL_DIR/usr/bin" \
    "$TARBALL_DIR/usr/lib/dictee" \
    "$TARBALL_DIR/usr/lib/systemd/user" \
    "$TARBALL_DIR/usr/lib/systemd/user-preset" \
    "$TARBALL_DIR/usr/share/man/man1" \
    "$TARBALL_DIR/usr/share/man/fr/man1" \
    "$TARBALL_DIR/usr/share/icons/hicolor/scalable/apps" \
    "$TARBALL_DIR/usr/share/applications" \
    "$TARBALL_DIR/usr/share/dictee/assets" \
    "$TARBALL_DIR/etc/udev/rules.d" \
    "$TARBALL_DIR/etc/modules-load.d" \
    "$TARBALL_DIR/etc/ld.so.conf.d"

for _lang in fr de es it pt uk; do
    mkdir -p "$TARBALL_DIR/usr/share/locale/$_lang/LC_MESSAGES"
done

# Rust binaries — copied straight from target/release/ (we just built
# them in CUDA mode, no risk of CPU contamination since this script
# never invokes a CPU build).
for bin in transcribe transcribe-daemon transcribe-client \
           transcribe-diarize transcribe-stream-diarize \
           transcribe-diarize-batch diarize-only; do
    cp "target/release/$bin" "$TARBALL_DIR/usr/bin/"
done

# Wrappers + scripts (from $PKG_DIR populated by dict_prepare_pkg_dir)
for f in dictee dictee-setup dictee-tray dictee-ptt dictee-postprocess \
         dictee-diarize-llm dictee-switch-backend dictee-test-rules \
         dictee-transcribe dictee-cheatsheet dictee-reset \
         dictee-translate-langs dictee-audio-sources \
         dictee-plasmoid-level dictee-plasmoid-level-daemon \
         dictee-plasmoid-level-fft; do
    [ -f "$PKG_DIR/usr/bin/$f" ] && cp "$PKG_DIR/usr/bin/$f" "$TARBALL_DIR/usr/bin/"
done

# Optional: dotool/dotoold + Vosk/Whisper daemon wrappers (only if
# build-deb.sh has previously staged them — we don't rebuild dotool
# here to keep this script light).
for f in dotool dotoold transcribe-daemon-vosk transcribe-daemon-whisper; do
    [ -f "$PKG_DIR/usr/bin/$f" ] && cp "$PKG_DIR/usr/bin/$f" "$TARBALL_DIR/usr/bin/"
done

# Shared lib helpers
cp "$PKG_DIR/usr/lib/dictee/dictee-common.sh" "$TARBALL_DIR/usr/lib/dictee/"
cp "$PKG_DIR/usr/lib/dictee/dictee_models.py" "$TARBALL_DIR/usr/lib/dictee/"

# ONNX Runtime libs — the 3 CUDA libs go into /usr/lib/dictee/, plus an
# ld.so.conf.d entry so ldconfig picks them up at install time.
cp -L "$ORT_LIB" "$TARBALL_DIR/usr/lib/dictee/"
for lib in libonnxruntime_providers_cuda.so libonnxruntime_providers_shared.so; do
    if [ -f "$ORT_LIB_DIR/$lib" ]; then
        cp -L "$ORT_LIB_DIR/$lib" "$TARBALL_DIR/usr/lib/dictee/"
    elif [ -f "target/release/$lib" ]; then
        cp -L "target/release/$lib" "$TARBALL_DIR/usr/lib/dictee/"
    fi
done
echo "/usr/lib/dictee" > "$TARBALL_DIR/etc/ld.so.conf.d/dictee.conf"

# Udev, services, presets, icons, .desktop, locales, configs, plasmoid
[ -f "$PKG_DIR/etc/udev/rules.d/80-dotool.rules" ] && \
    cp "$PKG_DIR/etc/udev/rules.d/80-dotool.rules" "$TARBALL_DIR/etc/udev/rules.d/"
[ -f "$PKG_DIR/etc/modules-load.d/dictee-uinput.conf" ] && \
    cp "$PKG_DIR/etc/modules-load.d/dictee-uinput.conf" "$TARBALL_DIR/etc/modules-load.d/"
cp "$PKG_DIR/usr/lib/systemd/user/"*.service               "$TARBALL_DIR/usr/lib/systemd/user/"        2>/dev/null || true
cp "$PKG_DIR/usr/lib/systemd/user-preset/"*.preset         "$TARBALL_DIR/usr/lib/systemd/user-preset/" 2>/dev/null || true
cp "$PKG_DIR/usr/share/man/man1/"*.1                        "$TARBALL_DIR/usr/share/man/man1/"          2>/dev/null || true
cp "$PKG_DIR/usr/share/man/fr/man1/"*.1                     "$TARBALL_DIR/usr/share/man/fr/man1/"       2>/dev/null || true
cp "$PKG_DIR/usr/share/icons/hicolor/scalable/apps/"*.svg   "$TARBALL_DIR/usr/share/icons/hicolor/scalable/apps/" 2>/dev/null || true
cp "$PKG_DIR/usr/share/applications/"*.desktop              "$TARBALL_DIR/usr/share/applications/"      2>/dev/null || true

for _lang in fr de es it pt uk; do
    cp "$PKG_DIR/usr/share/locale/$_lang/LC_MESSAGES/"*.mo \
        "$TARBALL_DIR/usr/share/locale/$_lang/LC_MESSAGES/" 2>/dev/null || true
done

# VERSION file (generated by build-common.sh's dict_prepare_pkg_dir)
cp "$PKG_DIR/usr/share/dictee/VERSION"                        "$TARBALL_DIR/usr/share/dictee/"

# Configs + plasmoid + assets
cp "$PKG_DIR/usr/share/dictee/dictee.plasmoid"                "$TARBALL_DIR/usr/share/dictee/" 2>/dev/null || true
cp "$PKG_DIR/usr/share/dictee/rules.conf.default"             "$TARBALL_DIR/usr/share/dictee/"
cp "$PKG_DIR/usr/share/dictee/dictionary.conf.default"        "$TARBALL_DIR/usr/share/dictee/"
cp "$PKG_DIR/usr/share/dictee/continuation.conf.default"      "$TARBALL_DIR/usr/share/dictee/"
cp "$PKG_DIR/usr/share/dictee/short_text_keepcaps.conf.default" "$TARBALL_DIR/usr/share/dictee/"
cp "$PKG_DIR/usr/share/dictee/dictee.conf.example"            "$TARBALL_DIR/usr/share/dictee/"
cp "$PKG_DIR/usr/share/dictee/assets/"*.svg                   "$TARBALL_DIR/usr/share/dictee/assets/"
if [ -d "$PKG_DIR/usr/share/dictee/assets/logos" ]; then
    mkdir -p "$TARBALL_DIR/usr/share/dictee/assets/logos"
    cp "$PKG_DIR/usr/share/dictee/assets/logos/"*.svg "$TARBALL_DIR/usr/share/dictee/assets/logos/"
fi
if [ -d "$PKG_DIR/usr/share/dictee/assets/icons" ]; then
    mkdir -p "$TARBALL_DIR/usr/share/dictee/assets/icons"
    cp "$PKG_DIR/usr/share/dictee/assets/icons/"*.svg "$TARBALL_DIR/usr/share/dictee/assets/icons/"
fi

# install.sh / uninstall.sh + README
cp install.sh   "$TARBALL_DIR/" 2>/dev/null || true
cp uninstall.sh "$TARBALL_DIR/" 2>/dev/null || true
[ -f README.md ] && cp README.md "$TARBALL_DIR/"

# 6. tar czf the staging dir
echo ""
echo "=== [TAR.GZ] tar czf ==="
tar czf "$DIST_DIR/dictee-${VERSION}_amd64.tar.gz" "$TARBALL_DIR"
rm -rf "$TARBALL_DIR"

# 7. Source tarball (nothing to do with CUDA — ship sources for
#    distros that prefer to recompile locally, e.g. Gentoo, Slackware).
echo "=== [TAR.GZ] Source archive ==="
git archive --format=tar.gz --prefix="dictee-${VERSION}/" \
    -o "$DIST_DIR/dictee-${VERSION}-source.tar.gz" HEAD

echo ""
echo "Built: $DIST_DIR/dictee-${VERSION}_amd64.tar.gz"
echo "Built: $DIST_DIR/dictee-${VERSION}-source.tar.gz"
