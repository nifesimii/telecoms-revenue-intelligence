#!/usr/bin/env sh
# Scheduled pg_dump of the dedicated FBB audit Postgres.
#
# DATA SAFETY: the audit trail is an audit artifact that must survive
# container recreation. The named volume protects against `docker compose
# down` / container restarts, but NOT against `docker volume rm` /
# `down -v` / disk loss. This dump writes a compressed snapshot to a
# HOST-mounted directory (./backups, outside the container) so a wiped
# volume can be restored.
#
# Runs inside the fbb-postgres-backup sidecar on a loop (see docker-compose).
# Keeps the last RETENTION dumps and prunes older ones.
#
# Restore with:
#   gunzip -c backups/fbb_audit_YYYYMMDDTHHMMSSZ.sql.gz \
#     | docker exec -i fbb_audit_postgres psql -U fbb_audit -d fbb_audit

set -eu

: "${PGHOST:=fbb-postgres}"
: "${PGPORT:=5432}"
: "${PGDATABASE:=fbb_audit}"
: "${PGUSER:=fbb_audit}"
: "${PGPASSWORD:?PGPASSWORD must be set}"
: "${BACKUP_DIR:=/backups}"
: "${BACKUP_INTERVAL_SECONDS:=86400}"   # daily
: "${BACKUP_RETENTION:=14}"             # keep last 14 dumps

export PGPASSWORD

mkdir -p "$BACKUP_DIR"

echo "[backup] FBB audit backup sidecar starting."
echo "[backup]   target: ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE}"
echo "[backup]   dir=${BACKUP_DIR} interval=${BACKUP_INTERVAL_SECONDS}s retention=${BACKUP_RETENTION}"

# Wait for Postgres to accept connections before the first dump.
until pg_isready -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" >/dev/null 2>&1; do
  echo "[backup] waiting for postgres…"
  sleep 3
done

while true; do
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  out="${BACKUP_DIR}/fbb_audit_${stamp}.sql.gz"
  echo "[backup] $(date -u) → dumping to ${out}"
  if pg_dump -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" \
       | gzip -c > "${out}.tmp"; then
    mv "${out}.tmp" "$out"
    echo "[backup] wrote ${out}"
  else
    echo "[backup] ERROR: pg_dump failed; leaving previous backups intact"
    rm -f "${out}.tmp"
  fi

  # Prune: keep the newest $BACKUP_RETENTION dumps.
  ls -1t "${BACKUP_DIR}"/fbb_audit_*.sql.gz 2>/dev/null \
    | tail -n +"$((BACKUP_RETENTION + 1))" \
    | while read -r old; do
        echo "[backup] pruning old dump ${old}"
        rm -f "$old"
      done

  sleep "$BACKUP_INTERVAL_SECONDS"
done
