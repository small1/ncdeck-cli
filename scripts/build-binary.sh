#!/usr/bin/env bash
# Build a standalone ncdeck binary with PyInstaller.
#
# Why: a single-file executable lets people install ncdeck without Python or
# pip. The build is isolated in a venv so it never touches the system Python.
#
# Env overrides (mainly for local testing):
#   NCDECK_BUILD_VENV  - venv location (default: ./.build-venv)
#   NCDECK_OUT         - output directory (default: ./dist)
#   NCDECK_WORK        - PyInstaller work/spec directory (default: ./build/pyinstaller)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# python3 on Unix, python on Windows (GitHub Actions Git Bash).
if command -v python3 >/dev/null 2>&1; then
    PY=python3
else
    PY=python
fi

VENV="${NCDECK_BUILD_VENV:-$ROOT/.build-venv}"
DIST="${NCDECK_OUT:-$ROOT/dist}"
WORK="${NCDECK_WORK:-$ROOT/build/pyinstaller}"

if [[ ! -x "$VENV/bin/python" && ! -x "$VENV/Scripts/python.exe" ]]; then
    "$PY" -m venv "$VENV"
fi

if [[ -x "$VENV/bin/python" ]]; then
    VPY="$VENV/bin/python"
else
    VPY="$VENV/Scripts/python.exe"
fi

"$VPY" -m pip install --upgrade pip
"$VPY" -m pip install -r requirements-build.txt

"$VPY" -m PyInstaller --onefile --clean --noconfirm \
    --name ncdeck \
    --paths "$ROOT/src" \
    --distpath "$DIST" \
    --workpath "$WORK" \
    --specpath "$WORK" \
    "$ROOT/scripts/binary_entry.py"

if [[ -f "$DIST/ncdeck.exe" ]]; then
    echo "Built: $DIST/ncdeck.exe"
else
    chmod +x "$DIST/ncdeck"
    echo "Built: $DIST/ncdeck"
fi
