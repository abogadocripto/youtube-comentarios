# Imagen de la aplicación (los temporizadores de systemd la invocan con `docker compose run --rm app bp <orden>`).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 TZ=UTC
WORKDIR /app

RUN useradd --system --uid 10001 --home /app bp
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip && pip install .

# Configuración, esquemas y prompts: se leen de BP_ROOT (versionados junto al código)
COPY config ./config
COPY schema ./schema
COPY prompts ./prompts
ENV BP_ROOT=/app

USER bp
ENTRYPOINT ["bp"]
CMD ["doctor"]
