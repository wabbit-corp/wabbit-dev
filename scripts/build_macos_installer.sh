#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Build an installable macOS package for wabbit-dev.

Usage:
  scripts/build_macos_installer.sh [--version <semver>] [--app-name <name>] [--python <path>] [--skip-sign] [--skip-notarize]

Options:
  --version <semver>   Package version (default: $VERSION or 0.1.0)
  --app-name <name>    CLI/binary name (default: $APP_NAME or wabbit-dev)
  --python <path>      Python interpreter used to run scripts/build_executable.py
  --skip-sign          Skip productsign step even when INSTALLER_SIGN_IDENTITY is set
  --skip-notarize      Skip notarization/stapling even when credentials are set
  -h, --help           Show this help

Environment hooks:
  VERSION                     Same as --version
  APP_NAME                    Same as --app-name
  PYTHON_BIN                  Same as --python
  PKG_IDENTIFIER              Installer package identifier (default: com.wabbit.<app-name>)
  INSTALLER_SIGN_IDENTITY     Developer ID Installer identity for productsign
  NOTARYTOOL_PROFILE          Keychain profile for xcrun notarytool submit --keychain-profile
  NOTARYTOOL_APPLE_ID         Apple ID for xcrun notarytool submit
  NOTARYTOOL_PASSWORD         App-specific password for xcrun notarytool submit
  NOTARYTOOL_TEAM_ID          Apple Team ID for xcrun notarytool submit

Notes:
  - Produces dist/<app>-<version>.pkg and dist/<app>-<version>.dmg
  - Installs binary at /usr/local/lib/<app>/<app>
  - Installs symlink command at /usr/local/bin/<app>
EOF
}

log() {
  printf '[build-macos-installer] %s\n' "$*"
}

die() {
  printf '[build-macos-installer] ERROR: %s\n' "$*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

APP_NAME="${APP_NAME:-wabbit-dev}"
VERSION="${VERSION:-0.1.0}"
PYTHON_BIN="${PYTHON_BIN:-}"
SKIP_SIGN=0
SKIP_NOTARIZE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      [[ $# -ge 2 ]] || die "--version requires a value"
      VERSION="$2"
      shift 2
      ;;
    --app-name)
      [[ $# -ge 2 ]] || die "--app-name requires a value"
      APP_NAME="$2"
      shift 2
      ;;
    --python)
      [[ $# -ge 2 ]] || die "--python requires a value"
      PYTHON_BIN="$2"
      shift 2
      ;;
    --skip-sign)
      SKIP_SIGN=1
      shift
      ;;
    --skip-notarize)
      SKIP_NOTARIZE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  die "This script only supports macOS (Darwin)."
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$REPO_ROOT/.venv/bin/python"
  else
    PYTHON_BIN="$(command -v python3 || true)"
  fi
fi
[[ -n "$PYTHON_BIN" ]] || die "Could not find Python interpreter."
[[ -x "$PYTHON_BIN" ]] || die "Python interpreter is not executable: $PYTHON_BIN"

require_cmd pkgbuild
require_cmd hdiutil

DIST_DIR="$REPO_ROOT/dist"
BUILD_DIR="$REPO_ROOT/build/macos"
PKG_ROOT="$BUILD_DIR/pkg-root"
DMG_PAYLOAD_DIR="$BUILD_DIR/dmg-payload"
PKG_IDENTIFIER="${PKG_IDENTIFIER:-com.wabbit.${APP_NAME}}"

UNSIGNED_PKG="$DIST_DIR/${APP_NAME}-${VERSION}.unsigned.pkg"
SIGNED_PKG="$DIST_DIR/${APP_NAME}-${VERSION}.pkg"
UNSIGNED_DMG="$DIST_DIR/${APP_NAME}-${VERSION}.unsigned.dmg"
FINAL_DMG="$DIST_DIR/${APP_NAME}-${VERSION}.dmg"

log "Building CLI binary with PyInstaller"
"$PYTHON_BIN" "$REPO_ROOT/scripts/build_executable.py"

BINARY_PATH="$DIST_DIR/$APP_NAME"
[[ -f "$BINARY_PATH" ]] || die "Expected binary not found: $BINARY_PATH"
[[ -x "$BINARY_PATH" ]] || die "Binary is not executable: $BINARY_PATH"

log "Staging package payload"
rm -rf "$PKG_ROOT" "$DMG_PAYLOAD_DIR"
mkdir -p "$PKG_ROOT/usr/local/lib/$APP_NAME" "$PKG_ROOT/usr/local/bin" "$DMG_PAYLOAD_DIR"
install -m 755 "$BINARY_PATH" "$PKG_ROOT/usr/local/lib/$APP_NAME/$APP_NAME"
ln -sfn "/usr/local/lib/$APP_NAME/$APP_NAME" "$PKG_ROOT/usr/local/bin/$APP_NAME"

log "Building unsigned .pkg"
pkgbuild \
  --root "$PKG_ROOT" \
  --identifier "$PKG_IDENTIFIER" \
  --version "$VERSION" \
  --install-location "/" \
  "$UNSIGNED_PKG"

PKG_FOR_DMG="$UNSIGNED_PKG"
if [[ "${INSTALLER_SIGN_IDENTITY:-}" != "" && "$SKIP_SIGN" -eq 0 ]]; then
  require_cmd productsign
  log "Signing .pkg with productsign"
  productsign \
    --sign "$INSTALLER_SIGN_IDENTITY" \
    "$UNSIGNED_PKG" \
    "$SIGNED_PKG"
  PKG_FOR_DMG="$SIGNED_PKG"
else
  log "Skipping productsign (set INSTALLER_SIGN_IDENTITY to enable)"
  cp -f "$UNSIGNED_PKG" "$SIGNED_PKG"
fi

log "Building .dmg"
cp -f "$PKG_FOR_DMG" "$DMG_PAYLOAD_DIR/"
rm -f "$UNSIGNED_DMG" "$FINAL_DMG"
hdiutil create \
  -volname "${APP_NAME} Installer" \
  -srcfolder "$DMG_PAYLOAD_DIR" \
  -ov \
  -format UDZO \
  "$UNSIGNED_DMG"
mv "$UNSIGNED_DMG" "$FINAL_DMG"

should_notarize() {
  if [[ "$SKIP_NOTARIZE" -eq 1 ]]; then
    return 1
  fi
  if [[ "${NOTARYTOOL_PROFILE:-}" != "" ]]; then
    return 0
  fi
  if [[ "${NOTARYTOOL_APPLE_ID:-}" != "" && "${NOTARYTOOL_PASSWORD:-}" != "" && "${NOTARYTOOL_TEAM_ID:-}" != "" ]]; then
    return 0
  fi
  return 1
}

if should_notarize; then
  require_cmd xcrun
  log "Submitting .dmg for notarization"
  if [[ "${NOTARYTOOL_PROFILE:-}" != "" ]]; then
    xcrun notarytool submit "$FINAL_DMG" --keychain-profile "$NOTARYTOOL_PROFILE" --wait
  else
    xcrun notarytool submit \
      "$FINAL_DMG" \
      --apple-id "$NOTARYTOOL_APPLE_ID" \
      --password "$NOTARYTOOL_PASSWORD" \
      --team-id "$NOTARYTOOL_TEAM_ID" \
      --wait
  fi
  log "Stapling notarization ticket"
  xcrun stapler staple "$FINAL_DMG"
  xcrun stapler validate "$FINAL_DMG"
else
  log "Skipping notarization (set NOTARYTOOL_PROFILE or NOTARYTOOL_APPLE_ID/PASSWORD/TEAM_ID to enable)"
fi

log "Done"
log "PKG: $SIGNED_PKG"
log "DMG: $FINAL_DMG"
