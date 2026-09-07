#!/usr/bin/env bash
# One-time Debian/Ubuntu installation with local MariaDB and systemd.
set -Eeuo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
SKIP_PACKAGES=false
CREATE_DATABASE=false
for argument in "$@"; do
    case "$argument" in
        --skip-packages) SKIP_PACKAGES=true ;;
        --create-database) CREATE_DATABASE=true ;;
        --help) printf 'Usage: sudo bash deploy/install.sh [--skip-packages] [--create-database]\n'; exit 0 ;;
        *) die "Unknown option: $argument" ;;
    esac
done
require_root
umask 077
lock_deployment
[[ "$APP_DIR" != /root/* && "$APP_DIR" != /home/* ]] || die 'Place the repository under /opt or /srv (ProtectHome is enabled).'
if ! $SKIP_PACKAGES; then
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv mariadb-server mariadb-client git locales
fi
for command in python3 mariadb mariadb-dump systemctl runuser; do
    command -v "$command" >/dev/null || die "Missing command: $command"
done
if command -v locale-gen >/dev/null; then
    sed -i 's/^# *cs_CZ.UTF-8 UTF-8/cs_CZ.UTF-8 UTF-8/' /etc/locale.gen
    locale-gen
fi
id "$SERVICE_USER" >/dev/null 2>&1 || useradd --system --home-dir "$STATE_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
install -d -m 750 -o "$SERVICE_USER" -g "$SERVICE_USER" "$STATE_DIR"
install -d -m 755 /opt/slack-attendance
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    (umask 022; python3 -m venv "$VENV_DIR")
fi
(umask 022; install_dependencies)
if [[ ! -f "$ATTENDANCE_ENV" ]]; then
    cp "$APP_DIR/.env.example" "$ATTENDANCE_ENV"
fi
if [[ ! -f "$ATTENDANCE_CONFIG" ]]; then
    cp "$APP_DIR/config.ini.example" "$ATTENDANCE_CONFIG"
fi
chown "$SERVICE_USER:$SERVICE_USER" "$ATTENDANCE_CONFIG" "$ATTENDANCE_ENV"
chmod 600 "$ATTENDANCE_CONFIG" "$ATTENDANCE_ENV"
# First run prepares the files. After editing them, rerun the same command.
if grep -qE 'replace-me|REPLACE_' "$ATTENDANCE_CONFIG" "$ATTENDANCE_ENV"; then
    printf '\nFill in %s and %s, then rerun this script.\n' "$ATTENDANCE_CONFIG" "$ATTENDANCE_ENV"
    printf 'Create the MariaDB database/user as described in README.md (or use an existing database).\n'
    exit 0
fi
runuser -u "$SERVICE_USER" -- test -r "$APP_DIR/bot.py" || die 'Service user cannot read the repository. Grant read/traverse access.'
systemctl start mariadb
if $CREATE_DATABASE; then
    "$VENV_DIR/bin/python" "$APP_DIR/manage.py" provision
fi
create_backup
systemctl stop "$SERVICE_NAME" 2>/dev/null || true
log 'Database migrations: reviewing pending changes'
run_app status
run_app migrate
run_app check
install_service
systemctl reset-failed "$SERVICE_NAME"
systemctl enable --now "$SERVICE_NAME"
check_service || die "Startup failed; inspect journalctl -u $SERVICE_NAME. Backup: $BACKUP_DIR"
log 'Installation completed. Verify the Home tab and Socket Mode connection in the service logs.'
