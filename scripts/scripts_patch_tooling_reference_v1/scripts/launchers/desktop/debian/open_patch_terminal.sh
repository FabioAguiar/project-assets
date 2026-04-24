#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"

PROJECT_DISPLAY_NAME="${PATCH_TOOL_PROJECT_NAME:-$(basename "${REPO_ROOT}")}"
PROJECT_SLUG="${PATCH_TOOL_PROJECT_SLUG:-$(basename "${REPO_ROOT}")}"
PYTHON_ENV_VAR="${PATCH_TOOL_PYTHON_ENV_VAR:-PATCH_TOOL_PYTHON}"
PYTHON_BIN="${PATCH_TOOL_PYTHON:-python}"

if [ -n "${PYTHON_ENV_VAR}" ]; then
  PROJECT_SPECIFIC_PYTHON="${!PYTHON_ENV_VAR-}"
  if [ -n "${PROJECT_SPECIFIC_PYTHON}" ]; then
    PYTHON_BIN="${PROJECT_SPECIFIC_PYTHON}"
  fi
fi

PATCH_TOOL="${REPO_ROOT}/scripts/patch_tool.py"
PATCH_ZIP="${REPO_ROOT}/patch.zip"

echo "${PROJECT_DISPLAY_NAME} — Patch Terminal"
echo
echo "Repositório: ${REPO_ROOT}"
echo "Projeto: ${PROJECT_SLUG}"
echo "Python env var: ${PYTHON_ENV_VAR}"
echo "Python: ${PYTHON_BIN}"
echo

if [ ! -f "${PATCH_TOOL}" ]; then
  echo "ERRO: patch_tool.py não encontrado em:"
  echo "  ${PATCH_TOOL}"
  echo
  read -r -p "Pressione Enter para fechar..."
  exit 2
fi

if [ ! -f "${PATCH_ZIP}" ]; then
  echo "ERRO: patch.zip não encontrado em:"
  echo "  ${PATCH_ZIP}"
  echo
  echo "Coloque o arquivo patch.zip na raiz do repositório e tente novamente."
  echo
  read -r -p "Pressione Enter para fechar..."
  exit 3
fi

CMD=(
  "${PYTHON_BIN}"
  "${PATCH_TOOL}"
  --root "${REPO_ROOT}"
  --require-no-conflict
  --conflict-policy skip
  --backup
)

echo "Aplicando patch automaticamente..."
echo "Comando:"
printf ' %q' "${CMD[@]}"
echo
echo

set +e
"${CMD[@]}"
STATUS=$?
set -e

echo
if [ "${STATUS}" -eq 0 ]; then
  echo "Patch aplicado com sucesso."
else
  echo "Falha ao aplicar patch. Exit code: ${STATUS}"
fi

echo
read -r -p "Pressione Enter para fechar..."
exit "${STATUS}"
