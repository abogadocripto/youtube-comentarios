# 12 — Plan de desarrollo

## 1. Principios de ejecución

- **Primero el Daily, con fuentes licencia-limpias** (escenario A). Es el producto diario que crea hábito y el que más ejercita la arquitectura. Las fuentes que dependen de licencias o permisos se enchufan después sin tocar el núcleo, porque el filtro de licencias ya está en el diseño.
- **Todo conector nace con fixtures.** Cada conector trae una respuesta real grabada y una prueba de contrato. El desarrollo y la CI no dependen de la red. Las pruebas en vivo se ejecutan desde el VPS, porque el entorno de desarrollo en la nube bloquea estas APIs.
- **Modo sombra antes de publicar:** al menos **14 días** publicando en un canal privado con los criterios de aceptación cumplidos.
- **Cada fase termina con algo que funciona de principio a fin.**

## 2. Fases

| Fase | Contenido | Entregable verificable | Criterio de aceptación |
|---|---|---|---|
| **0 · Cimientos** | Estructura del repositorio (doc 01 §10); `pyproject` (pip o uv); carga y validación de `metrics.yaml`, `rules.yaml` y `news_sources.yaml`; migración inicial desde `schema.sql`; clase base `Connector`; registro de licencias; CLI `bp`; CI (lint, tests) | `bp doctor` valida la configuración y el esquema; tests en verde en CI | Los 91 IDs de métricas cargan; `schema.sql` se aplica limpio; 0 errores de lint |
| **1 · Datos núcleo** | Conectores: CoinGecko, CoinMarketCap (contraste), alternative.me, mempool.space / Blockstream, Tesoro de EE. UU. (curvas), Fed de Nueva York (EFFR, ON RRP), Fiscal Data (TGA), Reserva Federal (H.4.1, H.6, H.10, calendario), BCE (tipos, M2), BoE (M4), PBoC (HTML), BoJ (si hay permiso); calendario (BEA, BLS en YAML, BCE en YAML, festivos NYSE, vencimientos Deribit) | `bp ingest-daily --date …` rellena `metric_observations` con procedencia completa | Frescura, rangos y contraste de precio aplicados; `bp smoke` en verde **desde el VPS** |
| **2 · Análisis y selección** | Estadísticos, reglas por familia, ejes, pistas, *salience*, "Hoy vigilaría…", fact sheet validado contra el esquema | `bp build-daily --date …` genera el fact sheet | Tests unitarios de cada regla (histéresis, percentiles, rachas); backtest de frecuencias de estados (doc 04 §8) |
| **3 · LLM, validación, renderizado y Telegram** | Cliente de Claude (salida estructurada, fallback del servidor, rechazos, costes); validadores V-* e I-*; verificador; lectura de respaldo por plantillas; renderizador es-ES + plantillas Telegram; publicador idempotente; bot de edición básico (previsualización, retener, corregir); temporizadores de systemd; Healthchecks | **Modo sombra**: Daily a las 09:00 en el canal privado | 14 días seguidos a las 09:00 ±1 min; 0 fallos bloqueantes no detectados; batería adversarial 100 % rechazada; valoración del editor ≥ 4/5 |
| **4 · On-chain propio** | Servidor del nodo: Bitcoin Core + BRK (versión fijada); conector BRK; MVRV, MVRV-Z, SOPR, LTH, suministro en beneficio, precio realizado | Bloque on-chain en el Daily | Contraste con una segunda fuente dentro de las tolerancias del doc 04 (precio realizado ±3 %, MVRV ±0,05) |
| **5 · ETF, derivados y exchanges** (según licencias) | SoSoValue y/o CoinGlass; Coinalyze; CryptoQuant; conciliación y versionado de ETF; agregación de funding y OI | Bloques ETF, derivados y exchanges | Conciliación CONSISTENTE ≥ 95 % de las sesiones; completitud a las 08:30 medida durante 20 sesiones |
| **6 · Noticias y alertas** | Recolectores (RSS/API/diff/IMAP), prefiltro, deduplicación, agrupación, clasificación por lotes, scoring, borradores de alerta, flujo de aprobación, alertas de mercado | Alertas en el grupo de edición | Precisión del scoring revisada por el editor en 4 semanas; 0 alertas desde fuentes T3 |
| **7 · Weekly y newsletter** | Agregación semanal, selección, prompt del Weekly, V-QUOTE, V-LEGAL, V-JUR y V-DATE, plantilla MJML, Brevo, archivo web estático, aprobación con hash | Weekly en borrador el sábado y enviado el domingo tras la aprobación | 4 semanas en sombra con lista de prueba; 0 citas inventadas; revisión sustantiva registrada |
| **8 · Endurecimiento y lanzamiento** | Conjunto de evaluación, panel, guías de operación, copias y restauración, revisión de seguridad, página de metodología | Lanzamiento público | Criterios de las fases 3–7 + visto bueno jurídico del doc 11 |

## 3. Qué necesito del despacho y cuándo

| Cuándo | Qué | Por qué |
|---|---|---|
| Fase 0 | **Repositorio propio** para el proyecto (hoy está en `youtube-comentarios/blindaje-patrimonial`) | Separar historial, permisos y CI |
| Fase 1 | **VPS en la UE** (p. ej. Hetzner CX23) con acceso SSH; **clave de CoinGecko Basic** (L1); clave gratuita de CoinMarketCap Basic (L2) | Ingesta real y pruebas en vivo de endpoints |
| Fase 3 | **Clave de la API de Anthropic**; dos bots de Telegram (BotFather) y los dos canales (privado de pruebas y público) con el despacho como propietario; cuenta de Healthchecks.io | LLM y publicación |
| Fase 3 | **Decisiones editoriales:** nombre del canal; sociedad editora; responsable editorial; declaración de intereses; texto legal final (doc 11 §7) | Pie legal y cumplimiento |
| Fase 4 | **Servidor dedicado del nodo** (2 TB NVMe, 32 GB) o hosting gestionado de BRK | On-chain propio |
| Fase 5 | Respuestas de licencias: **SoSoValue, Coinalyze, CoinGlass, CryptoQuant** (L3–L5) | Bloques ETF, derivados y exchanges |
| Fase 7 | **Cuenta de Brevo** (o decisión por Listmonk), subdominio de envío con acceso DNS (SPF, DKIM, DMARC), formulario de alta en la web del despacho, aviso de privacidad | Newsletter |

## 4. Decisiones pendientes (resumen; detalle en cada documento)

| # | Decisión | Recomendación |
|---|---|---|
| D1 | Escenario de datos (A, B o C; doc 02 §6) | **B** si CoinGlass confirma por escrito la difusión pública; si no, **A** + permisos gratuitos |
| D2 | Nasdaq-100 (doc 02 §7, L9) | **Omitir en el MVP**; bloque "Tipos y dólar" |
| D3 | Revisión humana del Daily antes de las 09:00 | **No**: etiqueta de IA en la cabecera (doc 11 §3.2) |
| D4 | Sociedad editora y responsable editorial | Por decidir (doc 11 §10) |
| D5 | Proveedor de email | **Brevo** al inicio; Listmonk a escala |
| D6 | Hora del Weekly | **Domingo 18:00** |
| D7 | Comentarios en Telegram | **No** al inicio |
| D8 | Modelo LLM para clasificar noticias | `claude-opus-5` por defecto; valorar uno más económico si el coste lo justifica |
| D9 | Máximo de alertas públicas | **2 por semana** |
| D10 | Idiomas | Solo castellano al inicio |

## 5. Estado del desarrollo en este repositorio

El código se desarrolla en `blindaje-patrimonial/src/bp/` siguiendo estas fases. El estado real de cada fase, qué funciona y qué falta, se mantiene en `blindaje-patrimonial/README.md`.
