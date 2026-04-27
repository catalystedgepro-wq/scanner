#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${WORKSPACE_ROOT}/.venv-graphify"
PYTHON_BIN="${VENV_DIR}/bin/python"
GRAPHIFY_BIN="${VENV_DIR}/bin/graphify"
SITE_DIR="${WORKSPACE_ROOT}/.graphify-site"

run_with_site() {
  PYTHONPATH="${SITE_DIR}${PYTHONPATH:+:${PYTHONPATH}}" \
    python3 -m graphify "$@"
}

ensure_graphify() {
  if python3 -m venv "${VENV_DIR}" >/dev/null 2>&1; then
    if ! "${PYTHON_BIN}" -c "import graphify" >/dev/null 2>&1; then
      "${PYTHON_BIN}" -m pip install --upgrade pip >/dev/null
      "${PYTHON_BIN}" -m pip install -e "${WORKSPACE_ROOT}/vendor/graphify[all]"
    fi
    return 0
  fi

  mkdir -p "${SITE_DIR}"
  if ! PYTHONPATH="${SITE_DIR}${PYTHONPATH:+:${PYTHONPATH}}" python3 -c "import graphify" >/dev/null 2>&1; then
    python3 -m pip install --upgrade pip --break-system-packages >/dev/null
    python3 -m pip install --target "${SITE_DIR}" --upgrade --break-system-packages "${WORKSPACE_ROOT}/vendor/graphify[all]"
  fi
}

ensure_graphify

cd "${WORKSPACE_ROOT}"

if [ "$#" -eq 0 ]; then
  if [ -x "${GRAPHIFY_BIN}" ]; then
    exec "${GRAPHIFY_BIN}" "${WORKSPACE_ROOT}" --update
  fi
  run_with_site "${WORKSPACE_ROOT}" --update
  exit 0
fi

if [ -x "${GRAPHIFY_BIN}" ]; then
  exec "${GRAPHIFY_BIN}" "$@"
fi

run_with_site "$@"
