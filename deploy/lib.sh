#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_NAME=slack-attendance
SERVICE_USER=slack-attendance
STATE_DIR=/var/lib/slack-attendance
VENV_DIR=/opt/slack-attendance/venv
BACKUP_ROOT=/var/backups/slack-attendance
export ATTENDANCE_CONFIG="$STATE_DIR/config.ini"
export ATTENDANCE_ENV="$STATE_DIR/.env"
export TZ=Europe/Prague
export PYTHONDONTWRITEBYTECODE=1

die() { printf '%s\n' "$*" >&2; exit 1; }
log() { printf '\n%s\n' "$*"; }
require_root() { [[ $EUID -eq 0 ]] || die 'Run this script with sudo.'; }
lock_deployment() {
    exec 9>/run/lock/slack-attendance-deploy.lock
    flock -n 9 || die 'Another installation or deployment is running.'
}
install_dependencies() {
    "$VENV_DIR/bin/python" -m pip install -r "$APP_DIR/requirements.txt"
    "$VENV_DIR/bin/python" -m pip check
}
run_app() {
    runuser -u "$SERVICE_USER" -- env ATTENDANCE_CONFIG="$ATTENDANCE_CONFIG" \
        ATTENDANCE_ENV="$ATTENDANCE_ENV" TZ="$TZ" PYTHONDONTWRITEBYTECODE=1 \
        "$VENV_DIR/bin/python" "$APP_DIR/manage.py" "$@"
}
create_backup() {
    mkdir -p "$BACKUP_ROOT"
    chmod 700 "$BACKUP_ROOT"
    BACKUP_DIR="$(mktemp -d "$BACKUP_ROOT/$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
    cp "$ATTENDANCE_CONFIG" "$ATTENDANCE_ENV" "$BACKUP_DIR/"
    git -C "$APP_DIR" rev-parse HEAD > "$BACKUP_DIR/commit.txt"
    "$VENV_DIR/bin/python" -m pip freeze > "$BACKUP_DIR/requirements.txt"
    "$VENV_DIR/bin/python" "$APP_DIR/manage.py" backup --output "$BACKUP_DIR/database.sql"
    log "Backup: $BACKUP_DIR"
}
install_service() {
    # systemd paths are deliberately restricted to avoid quoting ambiguities.
    [[ "$APP_DIR" =~ ^/[a-zA-Z0-9_./-]+$ ]] || die 'Repository path must not contain spaces or special characters.'
    sed "s|@APP_DIR@|$APP_DIR|g" "$APP_DIR/deploy/slack-attendance.service" \
        > /etc/systemd/system/slack-attendance.service
    systemctl daemon-reload
}
check_service() {
    local attempt
    for attempt in {1..10}; do
        sleep 2
        systemctl is-active --quiet "$SERVICE_NAME" || return 1
    done
    # This only verifies process stability; Socket Mode has no HTTP health endpoint.
    [[ "$(systemctl show "$SERVICE_NAME" -p NRestarts --value)" == 0 ]]
}
