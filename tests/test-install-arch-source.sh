#!/usr/bin/env bash
# test-install-arch-source.sh — guard against issue #17.
#
# The online installer's Arch path clones a git ref so makepkg can read its
# PKGBUILD; makepkg then re-fetches the tagged tarball declared in the
# PKGBUILD's source=() (archive/v$_tag.tar.gz) and builds THAT. If the
# cloned ref's PKGBUILD points _tag at a version that was never tagged
# (e.g. an in-dev 1.4.0-beta on master), the download 404s and makepkg
# aborts for every Arch/CachyOS user.
#
# This test reproduces the exact chain the installer takes and asserts the
# resulting source tarball actually exists (HTTP 200). It fails on the
# broken state (clone master -> _tag=1.4.0-beta -> 404) and passes on the
# fixed state (clone the latest release tag / release branch -> 200).
#
# Usage: test-install-arch-source.sh [path-to-install.sh]
#   defaults to the install.sh at the repo root next to this test.

set -uo pipefail

REPO="rcspam/dictee"
INSTALL_SH="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/install.sh}"

fail() { echo "FAIL: $*" >&2; exit 1; }

[[ -r "$INSTALL_SH" ]] || fail "install.sh not readable: $INSTALL_SH"

# 1. Find the Arch clone line (ignore the unrelated AUR dotool clone).
clone_line="$(grep -E 'git clone .*dictee-src' "$INSTALL_SH" | grep -vE 'aur\.archlinux' | head -1)"
[[ -n "$clone_line" ]] || fail "no 'git clone ... dictee-src' line found in $INSTALL_SH"

# 2. Extract the --branch argument. It may be a literal ref (a branch like
#    release/1.3 or a tag like v1.3.5) or the $RELEASE_TAG variable. A bare
#    clone with no --branch checks out the repo's default branch (master).
ref=""
if [[ "$clone_line" =~ --branch[[:space:]]+([^[:space:]]+) ]]; then
    ref="${BASH_REMATCH[1]}"
    ref="${ref%\"}"; ref="${ref#\"}"        # strip surrounding double quotes
fi

case "$ref" in
    "")
        ref="master" ;;                      # bare clone -> default branch
    *'$RELEASE_TAG'*|*'${RELEASE_TAG}'*)
        # Installer clones the resolved latest-release tag. Resolve it the
        # same way install.sh does, so we exercise the real chain.
        ref="$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
                | grep -Po '"tag_name"\s*:\s*"\K[^"]+' | head -1)"
        [[ -n "$ref" ]] || fail "cannot resolve \$RELEASE_TAG from /releases/latest" ;;
    *'$'*)
        fail "unsupported variable in install.sh --branch argument: $ref" ;;
esac
echo "Installer resolves Arch source to ref: $ref"

# 3. Read that ref's PKGBUILD and extract _tag (the version makepkg fetches).
pkgbuild="$(curl -fsSL "https://raw.githubusercontent.com/${REPO}/${ref}/PKGBUILD")" \
    || fail "cannot fetch PKGBUILD from ref '$ref'"
tag="$(printf '%s\n' "$pkgbuild" | grep -E '^_tag=' | head -1 | cut -d= -f2)"
[[ -n "$tag" ]] || fail "no _tag= in PKGBUILD of ref '$ref'"
echo "PKGBUILD _tag: $tag"

# 4. The chain only works if archive/v$_tag.tar.gz exists (what makepkg's
#    source=() downloads). Assert HTTP 200.
url="https://github.com/${REPO}/archive/v${tag}.tar.gz"
code="$(curl -fsS -o /dev/null -w '%{http_code}' -L "$url")"
echo "Source archive $url -> HTTP $code"

[[ "$code" == "200" ]] \
    || fail "Arch installer would fetch a non-existent tarball (HTTP $code) for v$tag — see issue #17"

echo "PASS: installer's Arch source chain resolves to an existing tarball (v$tag)"
