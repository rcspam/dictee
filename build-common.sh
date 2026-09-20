#!/bin/bash
# build-common.sh — shared scaffolding for build-deb.sh / build-rpm.sh / build-tar.sh
#
# Sourced (not executed) by the build scripts. Each caller must set:
#   - VERSION    (e.g. "1.3.0")
#   - PKG_DIR    (default: pkg/dictee)
#   - DIST_DIR   (default: .dev/dist)
#
# Provides:
#   - CARGO / REL_DIR         portable cargo wrapper and its release dir
#   - dict_check_glibc        refuses binaries needing a too-recent glibc
#   - dict_prepare_pkg_dir   populates $PKG_DIR with all .py wrappers,
#                            shell scripts, default configs, assets,
#                            compiled .mo locales and a VERSION file.
#                            Idempotent — safe to re-run.

# Release binaries are compiled inside a Debian 12 container (glibc 2.36)
# so they load on every supported distro (issue #32: host-linked binaries
# imported GLIBC_2.39 and failed on Debian 12). $CARGO replaces `cargo` in
# the builders and $REL_DIR replaces target/release/ for the binaries, so
# portable builds never mix with host builds. PKGBUILD is unaffected: Arch
# compiles natively on the user's machine.
CARGO="./packaging/cargo-glibc236.sh"
REL_DIR="target/glibc236/release"

# Oldest libc among the distros we support: Ubuntu 22.04 (2.35), ahead of
# Debian 12 (2.36). KDE neon follows its Ubuntu base. Bump only when 22.04
# is dropped from the tested list in README.md.
GLIBC_MAX="2.35"

# The Rust binaries every package ships, in $REL_DIR after a build.
DICT_BINS="transcribe transcribe-daemon transcribe-client transcribe-diarize
           transcribe-stream-diarize transcribe-diarize-batch diarize-only"

# dict_check_built_bins — run dict_check_glibc over $DICT_BINS in $REL_DIR.
dict_check_built_bins() {
    local _b _paths=""
    for _b in $DICT_BINS; do _paths="$_paths $REL_DIR/$_b"; done
    # shellcheck disable=SC2086
    dict_check_glibc $_paths
}

# dict_check_glibc <binary>... — abort when a binary imports a symbol from a
# glibc newer than $GLIBC_MAX. Issue #32 shipped twice unnoticed (1.3.6 and
# 1.3.7~rc3): the binaries ran fine on the maintainer's machine and died at
# startup on Debian 12. Called right after every release cargo build.
dict_check_glibc() {
    # Refuse to pass for lack of a tool: a silent OK here is exactly how #32
    # shipped twice.
    command -v objdump >/dev/null 2>&1 || {
        echo "FATAL: objdump not found (install binutils): the glibc floor" \
             "cannot be checked, and shipping unchecked is what issue #32 was" >&2
        exit 1
    }
    local bin ver bad=""
    for bin in "$@"; do
        [ -f "$bin" ] || { echo "FATAL: $bin missing, cannot check glibc" >&2; exit 1; }
        ver=$(objdump -T "$bin" 2>/dev/null \
              | grep -o 'GLIBC_[0-9.]*' | sed 's/GLIBC_//' | sort -uV | tail -1)
        if [ -z "$ver" ]; then
            # Every binary we ship links libc dynamically, so no versioned
            # GLIBC_ symbol at all means objdump did not read this file.
            echo "FATAL: no GLIBC_ symbol in $bin — objdump could not read it," \
                 "so the glibc floor is unverified (issue #32)" >&2
            exit 1
        fi
        if [ "$(printf '%s\n%s\n' "$GLIBC_MAX" "$ver" | sort -V | tail -1)" != "$GLIBC_MAX" ]; then
            bad="$bad  $(basename "$bin") needs GLIBC_$ver\n"
        fi
    done
    if [ -n "$bad" ]; then
        echo "FATAL: binaries require a glibc newer than $GLIBC_MAX (issue #32):" >&2
        printf "%b\n" "$bad" >&2
        echo "They would not start on Debian 12. Build via \$CARGO (packaging/cargo-glibc236.sh)." >&2
        exit 1
    fi
    echo "glibc check OK (≤ $GLIBC_MAX): $# binaries"
}

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
    # cuDNN-by-GPU-arch setup script, shared by the 4 install targets (deb
    # postinst / rpm %post / Arch .install / tarball install.sh). Must be copied
    # here from the repo root because build-deb.sh rm -rf's $PKG_DIR before build.
    cp ./setup-cuda-venv.sh      "$PKG_DIR/usr/lib/dictee/setup-cuda-venv.sh"
    chmod 755                    "$PKG_DIR/usr/lib/dictee/setup-cuda-venv.sh"

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

    # KDE Plasma 6 widget — single source of truth for the .plasmoid zip.
    # Re-built every run from the up-to-date plasmoid/package/ tree so that
    # build-deb.sh / build-rpm.sh / build-tar.sh (and any caller) all embed
    # the same just-built artifact. Previously each builder re-zipped the
    # widget independently (build-deb.sh) or copied a stale pre-existing
    # zip (build-rpm.sh) — leading to silent skew when one was run before
    # the other (e.g. build-rpm.sh first → embedded plasmoid pre-dated the
    # latest QML fixes; observed 2026-05-07).
    if [ -d "./plasmoid/package" ] && command -v zip >/dev/null 2>&1; then
        # Regenerate Defaults.js from config/main.xml (source of truth for
        # kcfg defaults, used by the "Reset icon settings" button).
        if [ -x plasmoid/gen-defaults.py ]; then
            python3 plasmoid/gen-defaults.py 2>/dev/null || true
        fi
        local _abs_pkg_dir
        _abs_pkg_dir=$(cd "$PKG_DIR" && pwd)
        rm -f "$_abs_pkg_dir/usr/share/dictee/dictee.plasmoid"
        (cd ./plasmoid/package \
            && zip -rq "$_abs_pkg_dir/usr/share/dictee/dictee.plasmoid" \
                       metadata.json contents/)
    fi
}
