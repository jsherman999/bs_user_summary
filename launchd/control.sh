#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This script only supports macOS launchd." >&2
  exit 1
fi

SERVICE_NAME="com.jay.bs-user-summary"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKDIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PLIST_TEMPLATE="${SCRIPT_DIR}/${SERVICE_NAME}.plist.template"
PLIST_PATH="${HOME}/Library/LaunchAgents/${SERVICE_NAME}.plist"
LOG_DIR="${WORKDIR}/logs"
STDOUT_LOG="${LOG_DIR}/bs-user-summary.out.log"
STDERR_LOG="${LOG_DIR}/bs-user-summary.err.log"
if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="${PYTHON_BIN}"
else
  PYTHON_BIN="$(command -v python3)"
fi
HOST="${BS_APP_HOST:-0.0.0.0}"
PORT="${BS_APP_PORT:-8080}"
UID_NUM="$(id -u)"
TARGET="gui/${UID_NUM}/${SERVICE_NAME}"

render_plist() {
  mkdir -p "${HOME}/Library/LaunchAgents" "${LOG_DIR}"

  sed \
    -e "s|__WORKDIR__|${WORKDIR}|g" \
    -e "s|__PYTHON_BIN__|${PYTHON_BIN}|g" \
    -e "s|__HOST__|${HOST}|g" \
    -e "s|__PORT__|${PORT}|g" \
    -e "s|__STDOUT_LOG__|${STDOUT_LOG}|g" \
    -e "s|__STDERR_LOG__|${STDERR_LOG}|g" \
    "${PLIST_TEMPLATE}" > "${PLIST_PATH}"
}

ensure_loaded() {
  if ! launchctl print "${TARGET}" >/dev/null 2>&1; then
    echo "Service is not loaded. Run: $0 install" >&2
    exit 1
  fi
}

check_python_version() {
  if ! "${PYTHON_BIN}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
    echo "Python 3.11+ is required. Current interpreter: ${PYTHON_BIN}" >&2
    echo "Set PYTHON_BIN to a 3.11+ interpreter and run install again." >&2
    exit 1
  fi
}

cmd_install() {
  check_python_version
  render_plist
  launchctl bootout "${TARGET}" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/${UID_NUM}" "${PLIST_PATH}"
  launchctl enable "${TARGET}"
  launchctl kickstart -k "${TARGET}"
  echo "Installed and started ${SERVICE_NAME}"
  echo "URL: http://${HOST}:${PORT}"
}

cmd_start() {
  ensure_loaded
  launchctl kickstart -k "${TARGET}"
  echo "Started ${SERVICE_NAME}"
}

cmd_stop() {
  launchctl bootout "${TARGET}" >/dev/null 2>&1 || true
  echo "Stopped ${SERVICE_NAME}"
}

cmd_restart() {
  if launchctl print "${TARGET}" >/dev/null 2>&1; then
    launchctl kickstart -k "${TARGET}"
  else
    cmd_install
    return
  fi
  echo "Restarted ${SERVICE_NAME}"
}

cmd_status() {
  if launchctl print "${TARGET}" >/dev/null 2>&1; then
    launchctl print "${TARGET}" | rg "state =|pid =|last exit code =|path ="
  else
    echo "${SERVICE_NAME} is not loaded"
    exit 1
  fi
}

cmd_logs() {
  mkdir -p "${LOG_DIR}"
  echo "== stdout (${STDOUT_LOG}) =="
  tail -n 80 "${STDOUT_LOG}" 2>/dev/null || true
  echo
  echo "== stderr (${STDERR_LOG}) =="
  tail -n 80 "${STDERR_LOG}" 2>/dev/null || true
}

cmd_uninstall() {
  launchctl bootout "${TARGET}" >/dev/null 2>&1 || true
  rm -f "${PLIST_PATH}"
  echo "Uninstalled ${SERVICE_NAME}"
}

usage() {
  cat <<USAGE
Usage: $0 <install|start|stop|restart|status|logs|uninstall>

Environment overrides:
  BS_APP_HOST   (default: 0.0.0.0)
  BS_APP_PORT   (default: 8080)
  PYTHON_BIN    (default: /usr/bin/python3)
USAGE
}

case "${1:-}" in
  install) cmd_install ;;
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_restart ;;
  status) cmd_status ;;
  logs) cmd_logs ;;
  uninstall) cmd_uninstall ;;
  *) usage; exit 1 ;;
esac
