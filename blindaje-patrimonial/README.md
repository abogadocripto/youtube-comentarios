# Blindaje Patrimonial — Sistema automático de inteligencia patrimonial

Sistema que publica cada mañana a las 09:00 (Europe/Madrid) un **Daily Bitcoin** en Telegram, elabora un **Informe semanal de Blindaje Patrimonial** por email y emite **Alertas patrimoniales** cuando ocurre algo relevante en los frentes financiero, fiscal, regulatorio o de protección.

> **Empieza por [`docs/00-resumen-ejecutivo.md`](docs/00-resumen-ejecutivo.md).**

## Principios

- Datos → filtro → contexto → impacto patrimonial. Sin predicciones, sin señales, sin análisis técnico.
- El LLM **nunca** aporta cifras: escribe marcadores que el sistema sustituye por datos trazables.
- Solo se publican datos con licencia de difusión pública (filtro de licencias en código).
- El Daily sale siempre a las 09:00 si hay datos núcleo; si no, no sale y se avisa.
- El Weekly y las alertas requieren revisión humana sustantiva.

## Estructura

```
docs/        Diseño (00 resumen · 01 arquitectura · 02 métricas y fuentes · 03 modelo de datos ·
             04 reglas · 05 noticias y alertas · 06 contrato LLM · 07 prompts · 08 validación ·
             09 Telegram · 10 newsletter · 11 cumplimiento · 12 plan)
config/      metrics.yaml · rules.yaml · news_sources.yaml · calendar/ · editorial.yaml · fomc.yaml
schema/      schema.sql (PostgreSQL 16) · llm/*.schema.json · examples/
prompts/     daily · weekly · alert · classify · verify
src/bp/      Código de la aplicación (en desarrollo; ver estado abajo)
tests/       Pruebas unitarias, de contrato (fixtures), golden y adversariales
deploy/      Docker y temporizadores de systemd
```

## Estado

| Fase (doc 12) | Estado |
|---|---|
| Diseño (docs 00–12, configuración, esquemas) | ✔ completo |
| 0 · Cimientos | en desarrollo |
| 1–8 | pendiente |
