#!/bin/bash
# build-common.sh — shared scaffolding for build-deb.sh / build-rpm.sh / build-tar.sh
#
# Sourced (not executed) by the build scripts. Each caller must set:
#   - VERSION    (e.g. "1.3.0")
#   - PKG_DIR    (default: pkg/dictee)
#   - DIST_DIR   (default: .dev/dist)
#
# Provides:
#   - dict_prepare_pkg_dir   populates $PKG_DIR with all .py wrappers,
#                            shell scripts, default configs, assets,
#                            compiled .mo locales and a VERSION file.
#                            Idempotent — safe to re-run.

dict_prepare_pkg_dir() {
    : "${PKG_DIR:?PKG_DIR must be set before sourcing build-common}"
    : "${VERSION:?VERSION must be set before sourcing build-common}"

    mkdir -p "$PKG_DIR/usr/bin"
    mkdir -p "$PKG_DIR/usr/lib/dictee"
    mkdir -p "$PKG_DIR/usr/share/dictee/assets"

    # Wrappers Python / shell. Source-of-truth files are at the repo root
    # (NOT pkg/) — see CLAUDE.md project conventions.
    cp ./dictee                  "$PKG_DIR/usr/bin/dictee"
    cp ./dictee-setup.py         "$PKG_DIR/usr/bin/dictee-setup"
    cp ./dictee-tray.py          "$PKG_DIR/usr/bin/dictee-tray"
    cp ./dictee-ptt.py           "$PKG_DIR/usr/bin/dictee-ptt"
    cp ./dictee-postprocess.py   "$PKG_DIR/usr/bin/dictee-postprocess"
    cp ./dictee-diarize-llm.py   "$PKG_DIR/usr/bin/dictee-diarize-llm"
    cp ./dictee-switch-backend   "$PKG_DIR/usr/bin/dictee-switch-backend"
    cp ./dictee-test-rules       "$PKG_DIR/usr/bin/dictee-test-rules"
    cp ./dictee-transcribe.py    "$PKG_DIR/usr/bin/dictee-transcribe"
    cp ./dictee-reset            "$PKG_DIR/usr/bin/dictee-reset"
    cp ./dictee-translate-langs  "$PKG_DIR/usr/bin/dictee-translate-langs"
    cp ./dictee-audio-sources    "$PKG_DIR/usr/bin/dictee-audio-sources"
    cp ./dictee-cheatsheet       "$PKG_DIR/usr/bin/dictee-cheatsheet"
    cp ./dictee-common.sh        "$PKG_DIR/usr/lib/dictee/dictee-common.sh"
    cp ./dictee_models.py        "$PKG_DIR/usr/lib/dictee/dictee_models.py"

    chmod 755 \
        "$PKG_DIR/usr/bin/dictee" \
        "$PKG_DIR/usr/bin/dictee-setup" \
        "$PKG_DIR/usr/bin/dictee-tray" \
        "$PKG_DIR/usr/bin/dictee-ptt" \
        "$PKG_DIR/usr/bin/dictee-postprocess" \
        "$PKG_DIR/usr/bin/dictee-diarize-llm" \
        "$PKG_DIR/usr/bin/dictee-switch-backend" \
        "$PKG_DIR/usr/bin/dictee-test-rules" \
        "$PKG_DIR/usr/bin/dictee-transcribe" \
        "$PKG_DIR/usr/bin/dictee-reset" \
        "$PKG_DIR/usr/bin/dictee-translate-langs" \
        "$PKG_DIR/usr/bin/dictee-audio-sources" \
        "$PKG_DIR/usr/bin/dictee-cheatsheet"

    # Default config files (post-processing / dictionary / continuation /
    # short-text keepcaps / dictee.conf example).
    cp ./rules.conf.default                  "$PKG_DIR/usr/share/dictee/rules.conf.default"
    cp ./dictionary.conf.default             "$PKG_DIR/usr/share/dictee/dictionary.conf.default"
    cp ./continuation.conf.default           "$PKG_DIR/usr/share/dictee/continuation.conf.default"
    cp ./short_text_keepcaps.conf.default    "$PKG_DIR/usr/share/dictee/short_text_keepcaps.conf.default"
    cp ./dictee.conf.example                 "$PKG_DIR/usr/share/dictee/dictee.conf.example"

    # VERSION file (git short hash if available, else "unknown")
    local build_hash
    build_hash=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
    echo "$VERSION build $build_hash" > "$PKG_DIR/usr/share/dictee/VERSION"

    # SVG assets (banners + logos + icons)
    cp ./assets/banner-dark.svg ./assets/banner-light.svg \
        "$PKG_DIR/usr/share/dictee/assets/"
    if [ -d "./assets/logos" ]; then
        mkdir -p "$PKG_DIR/usr/share/dictee/assets/logos"
        cp ./assets/logos/*.svg "$PKG_DIR/usr/share/dictee/assets/logos/"
    fi
    if [ -d "./assets/icons" ]; then
        mkdir -p "$PKG_DIR/usr/share/dictee/assets/icons"
        cp ./assets/icons/*.svg "$PKG_DIR/usr/share/dictee/assets/icons/"
    fi

    # Compiled .mo locales (also duplicated under /usr/share/dictee/locale/
    # so postinst can restore them after `dpkg -r`).
    for lang in fr de es it uk pt; do
        msgfmt -o "po/$lang.mo" "po/$lang.po" 2>/dev/null || true
        mkdir -p "$PKG_DIR/usr/share/locale/$lang/LC_MESSAGES"
        cp "po/$lang.mo" "$PKG_DIR/usr/share/locale/$lang/LC_MESSAGES/dictee.mo"
        mkdir -p "$PKG_DIR/usr/share/dictee/locale/$lang/LC_MESSAGES"
        cp "po/$lang.mo" "$PKG_DIR/usr/share/dictee/locale/$lang/LC_MESSAGES/dictee.mo"
    done
}
