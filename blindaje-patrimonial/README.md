# Blindaje Patrimonial — Sistema automático de inteligencia patrimonial

Sistema que publica cada mañana a las 09:00 (Europe/Madrid) un **Daily Bitcoin** en Telegram, elabora un **Informe semanal de Blindaje Patrimonial** por email y emite **Alertas patrimoniales** cuando ocurre algo relevante en los frentes financiero, fiscal, regulatorio o de protección.

> **Empieza por [`docs/00-resumen-ejecutivo.md`](docs/00-resumen-ejecutivo.md). Para retomar el trabajo en otra sesión: [`docs/13-traspaso.md`](docs/13-traspaso.md).**

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
             09 Telegram · 10 newsletter · 11 cumplimiento · 12 plan · 13 traspaso)
config/      metrics.yaml · rules.yaml · sources.yaml · editorial.yaml · llm.yaml · fomc.yaml ·
             news_sources.yaml · calendar/
schema/      schema.sql (PostgreSQL 16) · llm/*.schema.json · examples/
prompts/     daily · weekly · alert · classify · verify
src/bp/      ingest → analysis → select → llm → validation → editorial → distribution · orchestrator · cli
tests/       unit/ · adversarial/ (A1–A25, bloqueante en CI) · pipeline · golden · postgres · fixtures/
deploy/      temporizadores de systemd (Europe/Madrid), copias cifradas y guía de instalación
```

## Probarlo en local (sin red ni base de datos)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
bp doctor                      # configuración, esquemas, prompts y variables de entorno
bp demo                        # Daily completo con historia y fixtures SINTÉTICOS → out/demo/
bp demo --llm static           # la misma ejecución por la ruta del LLM (backend simulado + verificador)
pytest                         # 83 pruebas (+3 omitidas); con BP_TEST_DATABASE_URL, 85 (incluye PostgreSQL)
```

`bp demo` usa valores ficticios: sirve para probar la arquitectura de principio a fin, no el contenido.

## Órdenes

| Orden | Qué hace |
|---|---|
| `bp db-init` | Crea el esquema si la base está vacía y sincroniza fuentes y métricas desde la YAML |
| `bp ingest-daily` | Ingesta de las fuentes del Daily (08:30) |
| `bp build-daily` | Derivar → analizar → seleccionar → LLM → validar → borrador (08:45) |
| `bp publish-daily` | Publicación idempotente en Telegram (09:00); `--only-if-missing` para el respaldo de las 09:07 |
| `bp run-daily` | Las tres anteriores en un solo proceso |
| `bp smoke [--record]` | Prueba en vivo de los conectores desde el VPS; `--record` graba fixtures reales |

Despliegue: [`deploy/README.md`](deploy/README.md).

## Estado

| Fase (doc 12) | Estado | Detalle |
|---|---|---|
| Diseño (docs 00–12, configuración, esquemas) | ✔ | |
| 0 · Cimientos | ✔ | Configuración validada, `schema.sql` probado en PostgreSQL 16, `PostgresStore`, CLI, CI |
| 1 · Datos núcleo | ◐ | **Urgente:** el conector H.4.1 depende del *Data Download Program*, cuya opción «Build Your Package» la Fed retira la semana del 9 nov 2026; migrar al XML de la publicación. Hechos: CoinGecko, alternative.me, mempool.space, Tesoro de EE. UU., Fed de Nueva York, Fiscal Data (TGA), H.4.1, BCE (EUR/USD), calendario. **Faltan:** componentes del M2 global (BCE, BoE, PBoC, BoJ, H.6), índice amplio del dólar, contraste con CoinMarketCap. **Formatos de respuesta sin verificar en vivo** (marcados `[VERIFICAR]`): se validan con `bp smoke` desde el VPS |
| 2 · Análisis y selección | ✔ | Derivaciones, reglas por familia, ejes, saliencia, «Hoy vigilaría…», fact sheet validado contra el esquema; filtro de licencias en la selección y en la validación |
| 3 · LLM, validación, render, Telegram | ◐ | Hechos: cliente de Claude con salida estructurada, verificador independiente, 28 validadores deterministas, respaldo por plantillas, renderizador, publicación idempotente, temporizadores. **Faltan:** bot de edición (previsualizar, retener, corregir) y prueba con el modelo real |
| 4 · On-chain propio (BRK) | ☐ | Reglas y render listos; falta el conector y el servidor del nodo |
| 5 · ETF, derivados y exchanges | ◐ | Conector SoSoValue hecho; **bloqueado por licencias** (L3–L5): hoy el filtro retira esos bloques |
| 6 · Noticias y alertas | ☐ | Diseño, fuentes, prompts y esquemas listos |
| 7 · Weekly y newsletter | ◐ | Validadores del Weekly (V-QUOTE, V-LEGAL, V-JUR, V-DATE, V-EMPTY, V-HASH) hechos y probados; falta el flujo |
| 8 · Endurecimiento y lanzamiento | ☐ | |

### Qué publicaría hoy el Daily en producción

Con las fuentes ya conectadas: bloque Bitcoin (precio en USD y EUR, variaciones, máximo histórico), sentimiento,
tipos y dólar, «La lectura» y «Hoy vigilaría…». El bloque de liquidez aparecerá cuando estén los componentes del
M2 global: con solo datos de EE. UU. el sistema no rotula nada como «liquidez global».

### Bloqueos para publicar

- **URL de metodología y aviso legal** (`config/editorial.yaml`, `[●]`): mientras sea un marcador, la validación
  bloquea la publicación en producción. Es deliberado.
- Decisiones del despacho: sociedad editora y responsable editorial (D4), nombre del canal y licencias L1–L10
  (doc 12 §3–4).
