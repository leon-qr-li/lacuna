#!/bin/sh
# LACUNA installer for macOS (and Linux). Paste into Terminal:
#   curl -fsSL https://github.com/leon-qr-li/lacuna/releases/latest/download/install.sh | bash
# Installs into ~/Library/Application Support/LACUNA (no admin rights), creates ~/Applications/LACUNA.app
# and starts LACUNA. Run it again any time to repair. The workspace (~/LACUNA_Workspace) is never touched.
# Overrides (tests / offline): LACUNA_RELEASE_BASE (URL or folder), LACUNA_ROOT, LACUNA_WORKSPACE,
# LACUNA_NO_START=1, LACUNA_NO_SHORTCUTS=1.
set -eu

UV_VERSION=0.11.32
BASE="${LACUNA_RELEASE_BASE:-https://github.com/leon-qr-li/lacuna/releases/latest/download}"

case "$(uname -s)" in
  Darwin) ROOT_DEFAULT="$HOME/Library/Application Support/LACUNA"; OS=apple-darwin ;;
  Linux)  ROOT_DEFAULT="${XDG_DATA_HOME:-$HOME/.local/share}/lacuna"; OS=unknown-linux-gnu ;;
  *) echo "LACUNA: unsupported system $(uname -s)"; exit 1 ;;
esac
case "$(uname -m)" in
  arm64|aarch64) ARCH=aarch64 ;;
  x86_64|amd64)  ARCH=x86_64 ;;
  *) echo "LACUNA: unsupported CPU $(uname -m)"; exit 1 ;;
esac
ROOT="${LACUNA_ROOT:-$ROOT_DEFAULT}"

# fetch <url-or-folder-path> <dest>
fetch() {
  case "$1" in
    http://*|https://*) curl -fsSL --retry 3 -o "$2" "$1" ;;
    file://*) cp "${1#file://}" "$2" ;;
    *) cp "$1" "$2" ;;
  esac
}

echo "==> LACUNA 安装到 $ROOT"
mkdir -p "$ROOT/bin"
if [ ! -x "$ROOT/bin/uv" ]; then
  echo "==> 下载 uv $UV_VERSION"
  TMP="$(mktemp -d)"
  T="uv-$ARCH-$OS"
  curl -fsSL --retry 3 "https://github.com/astral-sh/uv/releases/download/$UV_VERSION/$T.tar.gz" | tar -xz -C "$TMP"
  mv "$TMP/$T/uv" "$ROOT/bin/uv"
  chmod +x "$ROOT/bin/uv"
  rm -rf "$TMP"
fi

fetch "$BASE/lacuna_launcher.py" "$ROOT/lacuna_launcher.py.new"

export UV_PYTHON_INSTALL_DIR="$ROOT/python" UV_CACHE_DIR="$ROOT/cache" UV_LINK_MODE=copy PYTHONUTF8=1
unset VIRTUAL_ENV || true
STATUS=0
echo "==> 准备 Python（第一次要下载）"
# </dev/null: when piped from curl, stdin is this script
"$ROOT/bin/uv" run --no-project --python 3.12 python "$ROOT/lacuna_launcher.py.new" install --root "$ROOT" --base "$BASE" </dev/null || STATUS=$?
rm -f "$ROOT/lacuna_launcher.py.new"
exit $STATUS
