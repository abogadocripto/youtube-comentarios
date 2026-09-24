# Despliegue (VPS de la UE)

Resumen de docs/01 §5–6. Todo en hora UTC salvo los temporizadores, que se expresan en `Europe/Madrid` (los cambios
de hora de marzo y octubre no desplazan la publicación).

## Primera instalación

```bash
# 1. Código en /opt/blindaje (este directorio blindaje-patrimonial/)
sudo mkdir -p /opt/blindaje && sudo chown $USER /opt/blindaje
git clone <repo> /tmp/repo && cp -r /tmp/repo/blindaje-patrimonial/. /opt/blindaje/
cd /opt/blindaje

# 2. Secretos
mkdir -p secrets && openssl rand -base64 32 > secrets/pg_password.txt && chmod 600 secrets/pg_password.txt
cp .env.example .env && chmod 600 .env      # completar; BP_DATABASE_URL con la misma contraseña

# 3. Imagen, base de datos y comprobaciones
docker compose build app
docker compose up -d postgres
docker compose --profile jobs run --rm app db-init
docker compose --profile jobs run --rm app doctor
docker compose --profile jobs run --rm app smoke            # conectores en vivo (red real)
docker compose --profile jobs run --rm app smoke --record   # opcional: graba fixtures reales para las pruebas

# 4. Temporizadores
sudo cp deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now bp-ingest-daily.timer bp-build-daily.timer bp-publish-daily.timer \
    bp-publish-daily-fallback.timer bp-backup.timer
systemctl list-timers 'bp-*'
```

## Calendario diario (Europe/Madrid)

| Hora | Unidad | Orden |
|---|---|---|
| 08:30 | `bp-ingest-daily.timer` | `ingest-daily` (se recupera tras un apagado: `Persistent=true`) |
| 08:45 | `bp-build-daily.timer` | `build-daily` → borrador `validated` (LLM) o `fallback` (plantillas) |
| 09:00 | `bp-publish-daily.timer` | `publish-daily` (si no hay borrador, genera el respaldo y publica) |
| 09:07 | `bp-publish-daily-fallback.timer` | `publish-daily --only-if-missing` |
| 03:30 | `bp-backup.timer` | copia cifrada de PostgreSQL |

Después de las 10:30 la aplicación se niega a publicar sin `--force` (confirmación humana).

## Modo sombra (2–3 semanas antes del lanzamiento)

`TELEGRAM_CHANNEL_ID` apunta a un canal privado de pruebas. Criterios de paso a producción: docs/12.

## Operación manual

```bash
docker compose --profile jobs run --rm app build-daily --out /tmp/out       # reconstruir el borrador de hoy
docker compose --profile jobs run --rm app publish-daily --dry-run          # ver lo que se publicaría
docker compose --profile jobs run --rm app publish-daily --force            # publicar pasadas las 10:30
journalctl -u 'bp-job@*' --since today                                      # registros
```

## Vigilancia

- Healthchecks.io: una comprobación por job (`HC_DAILY_INGEST`, `HC_DAILY_BUILD`, `HC_DAILY_PUBLISH`, `HC_BACKUP`).
  La de publicación con plazo 09:00 + 2 min: si no llega, SMS o email al operador.
- El respaldo de las 09:07 corre en el mismo VPS: cubre un fallo del job, no una caída del servidor. Para una caída del
  VPS el mecanismo es la alerta de Healthchecks al operador (publicar exige la base de datos).
