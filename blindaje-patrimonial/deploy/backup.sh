#!/usr/bin/env bash
# Copia diaria cifrada: pg_dump → age (clave pública del despacho) → almacenamiento de objetos UE (rclone).
# Requiere: age, rclone configurado con el remoto $BP_BACKUP_REMOTE, y la clave pública en $BP_BACKUP_AGE_RECIPIENT.
set -euo pipefail
cd /opt/blindaje
: "${BP_BACKUP_REMOTE:?define BP_BACKUP_REMOTE (p. ej. hetzner:blindaje-backups)}"
: "${BP_BACKUP_AGE_RECIPIENT:?define BP_BACKUP_AGE_RECIPIENT (age1…)}"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
out="/var/backups/blindaje/bp-${stamp}.sql.gz.age"
mkdir -p /var/backups/blindaje
docker compose exec -T postgres pg_dump -U bp -d bp --format=plain --no-owner | gzip -9 | age -r "$BP_BACKUP_AGE_RECIPIENT" > "$out"
rclone copy "$out" "$BP_BACKUP_REMOTE/" --immutable
find /var/backups/blindaje -name 'bp-*.sql.gz.age' -mtime +7 -delete
[ -n "${HC_BACKUP:-}" ] && curl -fsS -m 10 --retry 3 "$HC_BACKUP" >/dev/null || true
