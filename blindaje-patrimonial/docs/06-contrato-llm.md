# 06 — Contrato con el LLM (formato JSON de entrada y salida)

> Esquemas JSON (draft 2020-12, validados): `schema/llm/*.schema.json`.
> Ejemplo completo validado: `schema/examples/daily_input.example.json` → `daily_output.example.json` → `daily_rendered.example.html`.

## 1. Principio

El LLM **no recupera ni recuerda datos**. Recibe un JSON cerrado con hechos ya validados y devuelve otro JSON cerrado. En la salida:
- **no escribe cifras**, sino marcadores que el renderizador sustituye;
- declara en qué hechos o documentos se apoya cada frase;
- en los textos basados en documentos, aporta **citas literales** que el sistema comprueba.

Así la alucinación numérica queda eliminada por construcción. La alucinación conceptual (relaciones, predicciones, estado jurídico) se ataca con los validadores y el verificador del doc 08.

## 2. Llamadas al modelo

| Propósito | Prompt (`prompts/`) | Esquema de salida | `effort` | Modo | Frecuencia |
|---|---|---|---|---|---|
| Redacción del Daily | `daily.system.md` + `daily.user.md` | `daily_output.schema.json` | `high` | síncrono, streaming | 1–2/día |
| Verificación del Daily | `verify.system.md` | `verifier_output.schema.json` | `high` | síncrono | 1–2/día |
| Clasificación de noticias | `classify.system.md` | `news_classification.schema.json` | `low` | **Batch API** (−50 %) si no es urgente; síncrono para fuentes T1 en horario de alertas | 20–150/día |
| Borrador de alerta | `alert.system.md` | `alert_output.schema.json` | `high` | síncrono | ≤ 2/semana |
| Redacción del Weekly | `weekly.system.md` + `weekly.user.md` | `weekly_output.schema.json` | `high` | síncrono, streaming | 1/semana (+ reintentos) |
| Verificación de Weekly y alertas | `verify.system.md` | `verifier_output.schema.json` | `high` | síncrono | 1–3/semana |

**Parámetros comunes** (SDK oficial `anthropic` para Python):
- **Modelo:** `claude-opus-5` en todas las llamadas, configurable en `config/llm.yaml`. Pasar la clasificación a un modelo más económico (`claude-sonnet-5` o `claude-haiku-4-5`) reduciría su coste unas 2,5–5 veces; es **decisión del usuario** y no se aplica por defecto.
- **Pensamiento adaptativo:** `thinking: {type: "adaptive"}`. La profundidad se controla con `output_config.effort`.
- **Salida estructurada:** `client.messages.parse()` con modelos Pydantic que reflejan los esquemas. Las restricciones que la API no admite (longitudes, número de elementos) se validan en cliente y en V-LEN.
- **Fallback del servidor:** `fallbacks: "default"` con el beta `server-side-fallback-2026-07-01`. Si el modelo rechaza la petición por sus clasificadores de seguridad, la API la reintenta en otro modelo dentro de la misma llamada. Se registra `served_model`.
  - No aplica a la Batch API: allí, un rechazo se reintenta en síncrono.
  - Es poco probable en este dominio, pero evita que un falso positivo tumbe la publicación.
- **Rechazos:** comprobar siempre `stop_reason == "refusal"` antes de leer el contenido. Si todo falla, se pasa a la versión "solo datos" (doc 01 §4.2).
- **Caché de prompts:** los prompts de sistema son estables y llevan `cache_control`. El contenido variable va siempre en el mensaje de usuario, después del bloque cacheado. Nunca se interpola la fecha ni la hora en el prompt de sistema.
- **Límites de tokens:** Daily y alertas, `max_tokens` ≈ 16.000; Weekly, en streaming, ≈ 64.000.
- **Tiempos:** timeout de 240 s por llamada en el Daily. El reloj de la publicación manda (doc 01 §5).
- **Sin herramientas:** no se declara ninguna *tool* (ni búsqueda web, ni ejecución de código). El modelo no puede actuar ni salir a internet.
- **Auditoría:** cada llamada se registra en `llm_calls`: modelo solicitado y servido, versión del prompt, petición sin secretos, respuesta, `stop_reason`, tokens y coste.

## 3. Gramática de marcadores

| Marcador | Se sustituye por | Uso |
|---|---|---|
| `{{f:<fact_id>}}` | `display` del hecho, con signo si procede: "−$420 M", "+7,1 %", "58" | citar el dato tal cual |
| `{{fa:<fact_id>}}` | `display_abs`, sin signo: "$420 M", "7,1 %" | tras verbos de dirección ("sube un {{fa:oi_chg_24h_pct}}"); el validador V-DIR comprueba que el verbo concuerda con el signo real |
| `{{h:<hint_id>}}` | el texto completo de una pista verificada, con sus propios marcadores ya resueltos | citar una pista entera; si queda redundante, mejor parafrasear sin cifras |

Reglas:
1. Fuera de los marcadores **no puede haber ningún dígito** (V-NUM). En el Weekly se admiten cifras de documentos si aparecen literalmente en la cita aportada (V-NUM-W).
2. Todo marcador debe apuntar a un hecho `selected: true` o a una pista de un hecho seleccionado (V-REF, V-SEL), y figurar en el `fact_ids` o `hint_ids` de su frase (V-DECL).
3. El renderizador es la **única** pieza que convierte valores en texto. Usa `editorial/format.py`, con formato es-ES:
   - miles con punto y decimales con coma: `$101.250`, `1,92`;
   - signo tipográfico `−`;
   - espacio fino antes de `%`;
   - importes USD con "$" delante: `$420 M`, `$84 mm`, `$6,7 bill.`.

## 4. Daily

### 4.1 Entrada (`daily_input.schema.json`)

```
meta            fecha, día de la semana, versiones de reglas y prompt, contexto de mercado
                (¿hubo sesión en EE. UU.? ¿fin de semana? ¿festivo?), bloques disponibles, límites de longitud
facts[]         objetos fact (ver abajo): TODOS los que tienen estado calculado; solo los selected=true son citables
axes[]          color y etiqueta por eje + si cambió respecto a ayer + qué hechos lo determinan
watch           candidato elegido por código para "Hoy vigilaría…" + alternativas con su peso
previous_daily  lectura y "vigilaría" de ayer (continuidad; no es fuente de datos)
```

Objeto `fact` (definición en `common.defs.schema.json`):

| Campo | Contenido | Quién lo produce |
|---|---|---|
| `id` | = `metric_id` | catálogo |
| `display`, `display_abs` | valor formateado con y sin signo | `editorial.format` |
| `value` | valor crudo, solo como contexto; el LLM no lo copia | `ingest` |
| `as_of`, `as_of_label` | a qué momento se refiere ("sesión del martes 22 sep", "M2 global a agosto") | `ingest` / `editorial` |
| `source` | nombre + URL de la fuente o de la metodología | `sources` |
| `is_provisional`, `freshness` | provisional; `fresh` / `stale_shown` / `stale` | `validation` de entrada |
| `changes` | variaciones citables (referencias a otros hechos) | `analysis` |
| `stats` | z, percentil, racha: contexto, **no citable como cifra** | `analysis` |
| `state` | eje, código, etiqueta y color (doc 04) | `analysis` |
| `salience`, `selected` | puntuación y selección (doc 04 §5) | `select` |
| `interpretation_hints` | frases derivadas ya verificadas | `analysis.hints` |
| `caveats` | cautelas obligatorias si se menciona el hecho | `metrics.yaml` / reglas |

### 4.2 Salida (`daily_output.schema.json`)

```json
{
  "lectura": [ {"text": "…{{fa:oi_chg_24h_pct}}…", "kind": "hecho|interpretacion|matiz", "fact_ids": [], "hint_ids": []} ],
  "vigilar": {"watch_id": "metric:etf_streak", "text": "…", "fact_ids": []},
  "block_comments": [ {"block": "sentimiento|liquidez|demanda_etf|exchanges|onchain|macro|derivados", "text": "…", "fact_ids": [], "hint_ids": []} ],
  "watch_override_reason": null
}
```

**Límites** (en `meta.limits`, validados por V-LEN):
- lectura: 2–4 frases y 480 caracteres renderizados como máximo;
- "vigilaría": 200 caracteres;
- comentario de bloque: 140 caracteres.

### 4.3 Qué hace el renderizador con la salida

Plantilla fija `editorial/templates/daily_telegram.html.j2` (doc 09):
- **cabecera;**
- **bloques numéricos**, deterministas, con los bloques y métricas seleccionados;
- **comentario del LLM** bajo cada bloque, si existe;
- **línea de ejes** ("termómetro");
- **"🧭 La lectura"**;
- **"👀 Hoy vigilaría…"**;
- **pie legal y atribuciones**, que salen de `source_licences` y nunca del LLM.

## 5. Weekly

### 5.1 Entrada (`weekly_input.schema.json`)

```
meta                       semana ISO, periodo, fecha de envío, versiones, perfiles de audiencia
financial                  hechos semanales (con marcadores) + ejes al inicio y al final de la semana
events[]                   asuntos seleccionados por el scoring (doc 05) con frentes, jurisdicciones, puntuación y documentos
documents[]                documentos fuente S01…Sn: editor, tier, jurisdicción, frente, tipo, ESTADO JURÍDICO, texto (≤ 6.000 caracteres)
fronts_without_candidates  frentes sin asuntos (→ "Sin cambios relevantes esta semana")
calendar_next_week[]       agenda de la semana siguiente (macro, bancos centrales, vencimientos, plazos fiscales y regulatorios)
open_followups[]           asuntos de semanas anteriores con documentos nuevos
```

### 5.2 Salida (`weekly_output.schema.json`)

```
subject, preheader
semana_en_60s[≤3]          {rank, front, text, event_id, fact_ids, source_ids}
financiero                 {status, lectura_semanal[3–6 frases con fact_ids], items[]}
fiscal | regulatorio | proteccion   {status: con_novedades|sin_cambios_relevantes, intro, items[]}
   item: {event_id, titulo, jurisdictions, legal_status,
          que_ha_pasado   {text, source_ids, evidence[{source_id, quote literal}], fact_ids},
          por_que_importa {ídem},
          a_quien_afecta  {profiles[enum], text},
          que_vigilar     {text, source_ids, dates[{date, what, source_id}]},
          confidence: confirmado_fuente_primaria | confirmado_fuente_secundaria | pendiente_confirmacion}
agenda[]                   {calendar_id, text}
editor_notes[]             SOLO para el editor (no se publica)
```

Decisiones clave:
- **`evidence.quote`:** cita literal de 300 caracteres como máximo. El validador V-QUOTE comprueba de forma determinista que es subcadena, normalizada, del documento. Es el ancla anti-alucinación del Weekly.
  - No se usa la función *Citations* de la API, porque no es compatible con la salida estructurada.
  - La cita verificable ofrece la misma garantía y además es auditable.
- **`legal_status` obligatorio** por asunto, con la misma enumeración que los documentos. V-LEGAL impide que el texto sea más asertivo que la fuente.
- **`status: sin_cambios_relevantes`:** el renderizador escribe la frase fija "Sin cambios relevantes esta semana." No se deja al modelo, para que no la adorne.

## 6. Alertas, clasificación y verificación

| Esquema | Contenido | Notas |
|---|---|---|
| `alert_output.schema.json` | titular (≤ 90), estado jurídico, qué ha pasado, por qué importa, a quién afecta, qué vigilar, fuentes, notas al editor | Reutiliza `claim_text` e `item` del Weekly; mismas citas literales. Las alertas **de mercado** (depeg, ATH, flujo extremo) no usan LLM: son plantillas |
| `news_classification.schema.json` | relevancia, frentes, jurisdicciones, tipo, estado jurídico, perfiles afectados, **6 rasgos 0–5 con justificación**, fechas clave con cita, resumen, clave de agrupación, sospecha de inyección | El LLM **no** calcula la puntuación final: aporta rasgos; la fórmula es código (doc 05) |
| `verifier_output.schema.json` | por fragmento: veredicto (`supported` / `problematic` / `unsupported`), tipos de problema (14 categorías), explicación y propuesta de corrección; `overall_pass` | El verificador recibe el texto **ya renderizado** y los datos de entrada; no ve el razonamiento del redactor |

## 7. Coste estimado (tarifas de `claude-opus-5`: 5 $ por millón de tokens de entrada y 25 $ por millón de salida; Batch API al 50 %)

| Llamada | Tokens de entrada / salida (incl. pensamiento) | Coste unitario | Mensual |
|---|---|---|---|
| Daily (redacción + verificación, ~1,2 intentos) | ~10.000 / ~5.000 ×2 | ~0,30 $ | ~9 $ |
| Clasificación (50–100 noticias/día tras el prefiltro, batch, `effort` bajo) | ~2.500 / ~800 | ~0,016 $ | 25–50 $ |
| Weekly (redacción + verificación + 1 reintento) | ~70.000 / ~15.000 | ~1,5 $ | ~6 $ |
| Alertas | ~15.000 / ~4.000 ×2 | ~0,3 $ | ~2 $ |
| **Total** | | | **~40–70 $/mes** |

La partida variable es la clasificación. El **prefiltro determinista** (doc 05 §3: palabras clave, tier y deduplicación previa) reduce entre 3 y 5 veces las llamadas. Es la primera palanca de coste antes de plantear un cambio de modelo.

## 8. Versionado y cambios

- Cada prompt lleva cabecera `prompt_id · version`. La versión se guarda en `llm_calls` y en el informe.
- Cambiar un prompt o un esquema exige:
  - incrementar la versión;
  - ejecutar el conjunto de evaluación (doc 08 §7);
  - que no empeore ninguna métrica bloqueante: tasa de validación, veredictos del verificador y valoración del editor.
- Los esquemas de salida son compatibles hacia atrás mientras sea posible. Si no lo son, cambia el `$id` y la versión mayor.
