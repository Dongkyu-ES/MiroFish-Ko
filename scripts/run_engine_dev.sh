#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${ROOT_DIR}/.venv-engine"
STAMP_FILE="${VENV_DIR}/.requirements.sha256"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required to run the parity engine dev server." >&2
  exit 1
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

CURRENT_HASH="$(shasum "${ROOT_DIR}/requirements.txt" | awk '{print $1}')"

source "${VENV_DIR}/bin/activate"

if [[ ! -f "${STAMP_FILE}" ]] || [[ "$(cat "${STAMP_FILE}")" != "${CURRENT_HASH}" ]]; then
  python -m pip install --upgrade pip
  python -m pip install -r "${ROOT_DIR}/requirements.txt"
  printf '%s' "${CURRENT_HASH}" > "${STAMP_FILE}"
fi

cd "${ROOT_DIR}"
exec python app.py
