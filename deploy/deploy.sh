#!/usr/bin/env bash
# Fast-forward update of the currently checked-out branch, with a DB/config backup.
set -Eeuo pipefail
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/lib.sh"
if [[ "${1:-}" == --help ]]; then
    printf 'Usage: sudo bash deploy/deploy.sh\nDeploys origin/<current branch>.\n'
    exit 0
fi
[[ $# == 0 ]] || die 'Unknown argument; see --help.'
require_root
umask 077
lock_deployment
cd "$APP_DIR"
[[ -f "$ATTENDANCE_CONFIG" && -f "$ATTENDANCE_ENV" ]] || die 'Run install.sh first.'
[[ -z "$(git status --porcelain)" ]] || die 'Checkout is not clean. Commit/stash changes before deploying.'
branch="$(git symbolic-ref --quiet --short HEAD)" || die 'Detached HEAD; switch to the deployment branch.'
git fetch origin "$branch"
target="$(git rev-parse FETCH_HEAD)"
git merge-base --is-ancestor HEAD "$target" || die 'Update is not a fast-forward.'
create_backup
printf '%s\n' "$target" > "$BACKUP_DIR/target.txt"
trap 'printf "Deployment failed. Backup: %s. Inspect journalctl -u %s and README recovery instructions.\n" "$BACKUP_DIR" "$SERVICE_NAME" >&2' ERR
# Stop before replacing Python files/dependencies to avoid a mixed running version.
systemctl stop "$SERVICE_NAME"
git merge --ff-only "$target"
(umask 022; install_dependencies)
log 'Database migrations: reviewing pending changes'
run_app status
run_app migrate
run_app check
install_service
systemctl reset-failed "$SERVICE_NAME"
systemctl start "$SERVICE_NAME"
check_service
trap - ERR
log "Deployment complete. Backup: $BACKUP_DIR"
