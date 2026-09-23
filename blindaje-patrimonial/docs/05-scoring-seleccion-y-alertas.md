# 05 — Noticias, scoring, selección del Weekly y alertas

> Registro de fuentes: `config/news_sources.yaml`. Calendario fiscal y regulatorio: `config/calendar/regulatory.yaml`. La selección de **métricas** del Daily está en el doc 04 §5; este documento trata las **noticias**.

## 1. Conclusión

- Todo lo necesario para los frentes fiscal, regulatorio y de protección se puede obtener **gratis de fuentes primarias**:
  - boletines oficiales: BOE, BOPA, Diario Oficial de la UE (DOUE);
  - reguladores: CNMV, ESMA, EBA, SEC;
  - registros: MiCA de ESMA, listas OFAC;
  - fabricantes de wallets;
  - organismos internacionales: OECD, FATF, BIS.
- Los agregadores de pago (CryptoPanic, NewsAPI, CoinDesk Data) se descartan. Los medios cripto se usan **solo para descubrir** asuntos (titular + enlace), nunca como fuente publicable de hechos jurídicos.
- La doctrina administrativa (DGT, TEAC) no tiene API. Se consulta semanalmente, con moderación.
- **CENDOJ no se automatiza:** sus términos prohíben el uso comercial y la descarga masiva.
- El scoring es **código**: el LLM solo aporta rasgos (0–5) con justificación. La decisión de alertar la toma una fórmula con suelos y techos explícitos, y la confirma un editor humano.

## 2. Canal de noticias

```
fetch (RSS/API/HTML/CSV-diff/IMAP) ──► normalizar ──► prefiltro determinista ──► deduplicar ──► agrupar en eventos
      │                                                    (tier, palabras clave,     (IDs nativos,       (event_key_hint +
      │                                                     departamento, idioma)      hash de URL)         simhash, 72 h)
      ▼                                                                                                        │
raw_payloads                                                                            clasificar (LLM, batch) ◄┘
                                                                                                │
                                                                        scoring determinista ◄──┘
                                                                                │
                                   ≥ 80 ──► borrador de ALERTA ──► aprobación del editor ──► Telegram (+ email)
                                   50–79 ─► candidato del WEEKLY
                                   35–49 ─► "radar" (solo si hay hueco; nunca en 60 s)
                                   < 35 ──► archivo
```

### 2.1 Niveles de fuente y regla de publicación

| Nivel | Qué incluye | Uso |
|---|---|---|
| **T1** oficial o primaria | BOE, BOPA, DOUE / Cellar, Comisión, Consejo, Parlamento Europeo, ESMA, EBA, AMLA, BCE, OECD, FATF, FSB, BIS, CNMV, Banco de España, AEAT, DGT, TEAC, AFA, Govern d'Andorra, SEC, CFTC, Reserva Federal, Tesoro/OFAC, IRS, Congress.gov, Federal Register, Bitcoin Core, fabricantes de wallets **sobre sus propios productos**, Europol, INCIBE | Fuente citable para hechos jurídicos y regulatorios |
| **T2** especializada fiable | rekt.news, SlowMist, CertiK, Chainalysis, Elliptic, TRM Labs, Bitcoin Optech | Citable para incidentes de seguridad, con la fórmula "según…" |
| **T3** medios y agregadores | CoinDesk, The Block, Decrypt, Blockworks, Bitcoin Magazine, GDELT, prensa general | **Solo descubrimiento**: titular + enlace, sin almacenar ni republicar el cuerpo del artículo |

**Regla:** un asunto jurídico o regulatorio solo se publica con una fuente T1. Un incidente de seguridad exige una T1 (el propio protocolo, exchange o fabricante) o **dos T2 independientes**. Un asunto solo T3 puede alimentar el borrador del Weekly como `pendiente_confirmacion`, pero **nunca dispara una alerta**.

### 2.2 Métodos de acceso (resumen; detalle en `news_sources.yaml`)

| Método | Fuentes | Notas |
|---|---|---|
| API oficial | BOE (sumario diario JSON, sin clave), Cellar SPARQL (DOUE), Federal Register, Congress.gov (clave gratuita), NVD 2.0, Congreso de los Diputados (datos abiertos) | La vía preferida |
| RSS / Atom | CNMV, Banco de España, SEPBLAC, Hacienda, INCIBE, Comisión, Consejo, Parlamento Europeo, BCE, EBA, ESMA, BIS, FSB, SEC, CFTC, Reserva Federal, Europol, rekt.news, Bitcoin Core, releases de GitHub de firmwares, medios T3 | GET condicional (ETag / If-Modified-Since) |
| Diff de fichero | Registro provisional MiCA de ESMA (5 CSV), lista CASP de la CNMV (PDF), compromisos CARF de la OECD (PDF), OFAC (Sanctions List Service: ficheros y deltas; **OFAC retiró su RSS el 31 ene 2025**) | Se guarda la instantánea y se emiten diferencias **semánticas** (entidad añadida o retirada), no "el fichero cambió" |
| HTML con diff | AMLA, FATF, IOSCO, OECD Global Forum, Govern d'Andorra, AFA, UIFAND, Consell General, reguladores de EAU (VARA, DFSA, CBUAE, ADGM, FTA), páginas de seguridad de fabricantes | Hash de la lista normalizada de enlaces; alarma si hay cero elementos o cambia la estructura |
| API no documentada + respaldo | **BOPA** (Azure Functions `GetNewPaginatedNewsletter` → `GetDocumentsByBOPA`) | Prueba de contrato diaria; respaldo con las **alertas gratuitas por email** de BOPA leídas por IMAP |
| Consulta semanal | DGT (Petete), TEAC (DYCTEA), consultas vinculantes del Departament de Tributs d'Andorra | Palabras clave: monedas virtuales, criptoactivos, Andorra, Emiratos, residencia fiscal; 1 petición por segundo como máximo |
| Descubrimiento con IA (opcional) | Una pasada diaria a las 07:45 y otra semanal con la búsqueda web de la API de Claude (`web_search_20260209`), con `allowed_domains` limitado a los dominios T1 | 10 $ por cada 1.000 búsquedas; unos 600 al mes, ≈ 6 $ más tokens. **Solo propone URLs**: cada una vuelve a pasar por el recolector normal antes de almacenarse. El texto de la búsqueda nunca es fuente |

**Higiene HTTP:**
- *User-Agent* identificado con email de contacto;
- respeto de `robots.txt`;
- límites por dominio (SEC ≤ 10 peticiones/s; NVD 50 cada 30 s con clave; Congress.gov 5.000/h);
- backoff exponencial;
- nunca se eluden protecciones anti-bot.

**Salud de cada fuente:**
- cero elementos durante N días según su cadencia;
- 404;
- cambio de esquema.

Cualquiera de estas situaciones genera un aviso de operaciones. Hay precedentes: OFAC retiró su RSS y está prevista la migración del registro MiCA de ESMA.

### 2.3 Prefiltro determinista (antes del LLM, para ahorrar coste y ruido)

1. **Por fuente:**
   - BOE: secciones I, II‑B y III, y departamentos Hacienda, Economía, CNMV, Banco de España y Jefatura del Estado;
   - BOPA: todo;
   - DOUE: sector CELEX 3 con materias o palabras clave (MiCA `32023R1114`, TFR `32023R1113`, AMLR `32024R1624`, AMLA `32024R1620`, DAC8 `32023L2226`).
2. **Palabras clave por frente**, en castellano, catalán, inglés y francés (`config/news_keywords.yaml`). Ejemplos: criptoactivo, moneda virtual, bitcoin, stablecoin, MiCA, DAC8, CARF, CRS, Modelo 721, Modelo 172, patrimonio, grandes fortunas, residencia fiscal, *exit tax*, autocustodia, hackeo, *phishing*, blanqueo, KYC, sanciones.
3. **Deduplicación exacta** por identificador nativo: CELEX/ELI, número de documento del Federal Register, número de *release* de la SEC, CVE, publicación de OFAC, fila del registro, *guid* del RSS. Si no hay identificador nativo, se usa el hash de la URL canónica (sin `utm_*`, `fbclid`, fragmentos ni barra final).

Solo lo que supera el prefiltro va al clasificador. Se estima una reducción de 3 a 5 veces (doc 06 §7).

### 2.4 Agrupación en eventos

- Un **evento** es un hecho del mundo; varios documentos lo describen.
- **Clave:** la `event_key_hint` del clasificador (p. ej. `es-modelo-721-plazo`) más la similitud de título y resumen (simhash o *embeddings*), en una ventana de 72 h.
- **Documento principal:** el de mejor nivel (T1 antes que T2 y T3) y, a igualdad, el más antiguo.
- `corroboration` = número de editores **independientes** (se excluyen reproducciones del mismo teletipo).
- Si llegan documentos nuevos de un evento ya alertado o publicado, pasan a "seguimiento" (`open_followups` del Weekly) y no generan una alerta nueva, salvo un cambio material (p. ej. de propuesta a publicada en el BOE).

## 3. Clasificación (LLM)

Salida: `news_classification.schema.json`, generada con el prompt `prompts/classify.system.md`. Por cada documento el modelo aporta:
- frentes;
- jurisdicciones;
- tipo de documento;
- **estado jurídico**;
- perfiles afectados;
- **seis rasgos 0–5 con justificación**: impacto económico, población afectada, fuerza jurídica, urgencia, novedad y encaje con el público;
- fechas clave con cita literal;
- resumen;
- clave del hecho;
- sospecha de inyección de instrucciones.

**Modo de ejecución:**
- **Batch API** (−50 % de coste) en ciclos de 2 h;
- **síncrono** para fuentes T1 en horario de 07:00 a 22:00, para que las alertas no esperen al lote.

El campo `legal_value` de cada documento es determinista, según su fuente y su sección:

| `legal_value` | Significado |
|---|---|
| `official_journal` | boletín oficial |
| `parliamentary_bulletin` | boletín parlamentario |
| `regulator_register` | registro de un regulador |
| `regulator_notice_or_warning` | aviso o advertencia de un regulador |
| `binding_admin_doctrine` | doctrina administrativa vinculante |
| `draft_norm` | borrador de norma |
| `press_release` | nota de prensa |
| `secondary_media` | medio secundario |

## 4. Scoring de impacto (0–100)

### 4.1 Fórmula

```
base  = 100 × (0,20·E + 0,15·P + 0,20·L + 0,15·U + 0,10·N + 0,20·I) / 5
        E = impacto económico, P = población afectada, L = fuerza jurídica,
        U = urgencia, N = novedad, I = encaje con el público (ES/AD con cripto)

fiab  = T1: 1,00 · dos T2 independientes: 0,90 · una T2: 0,80 · solo T3: 0,50
juris = ES o AD directa: 1,00 · UE aplicable en ES: 1,00 · EE. UU./internacional con efecto indirecto: 0,80 · otras: 0,50

score = min(techo, max(suelo, base × fiab × juris))
```

### 4.2 Suelos: hechos que deben llegar al editor aunque la fórmula dé menos

| Regla | Suelo |
|---|---|
| BOE sección I (ley, real decreto-ley, real decreto, orden) con palabras clave cripto o tributarias del frente fiscal | 85 |
| BOPA: ley o decreto que cite la Llei 24/2022, el IRPF andorrano o la normativa de prevención del blanqueo con criptoactivos | 85 |
| Vulnerabilidad **confirmada por el fabricante** que afecte a semillas o claves de una wallet hardware o software de uso amplio | 85 |
| Exchange o custodio con retirada de fondos suspendida o insolvencia, con usuarios en la UE (T1 o 2×T2) | 85 |
| Sanción de OFAC o de la UE con direcciones XBT de un servicio usado por residentes de la UE | 80 |
| Advertencia de la CNMV, o baja o alta en el registro MiCA, de una plataforma relevante para residentes en España | 80 |
| Cambio en las listas del FATF que afecte a ES, AD o EAU | 75 |
| Plazo del `regulatory.yaml` que vence en ≤ 7 días con novedad normativa asociada | 70 |

### 4.3 Techos

| Situación | Techo |
|---|---|
| Solo fuentes T3 | 60 (no alerta) |
| `injection_suspected` | 50 hasta revisión humana |
| `legal_status = declaracion_o_anuncio` | 75, salvo U = 5 |
| Evento ya alertado, sin cambio material | 49 |

Umbrales y pesos en `config/rules.yaml → news` (versionados, igual que las reglas de métricas).

### 4.4 Ejemplos de calibración (provisionales; se ajustarán en el modo sombra)

| Asunto (ilustrativo) | E | P | L | U | N | I | Nivel | Resultado |
|---|---|---|---|---|---|---|---|---|
| Orden ministerial en el BOE que crea un nuevo modelo informativo sobre criptoactivos con plazo en enero | 3 | 5 | 5 | 3 | 4 | 5 | T1 | base 84 → **84**, alerta |
| Nota de prensa del Gobierno anunciando que estudiará gravar más las plusvalías cripto | 4 | 5 | 1 | 1 | 4 | 5 | T1 | base 66 (bajo el techo de declaración, 75) → **66**, Weekly |
| Hackeo de 30 M $ en un protocolo DeFi poco usado en España, informado por rekt.news | 2 | 1 | 0 | 2 | 4 | 1 | T2 | base 29 × 0,8 = **23**, archivo |
| Fabricante de wallet hardware confirma una vulnerabilidad de semillas en un modelo concreto | 4 | 3 | 0 | 5 | 5 | 4 | T1 | base 66 → suelo **85**, alerta |
| ESMA publica unas Q&A de MiCA sobre el servicio de custodia | 1 | 2 | 3 | 1 | 3 | 3 | T1 | base 43 → **43**, radar |

## 5. Selección del Weekly

1. **Candidatos:** eventos de la semana (sábado a viernes) con score ≥ 50, más `open_followups` con documentos nuevos.
2. **Por frente:** hasta 3 asuntos (fiscal, regulatorio, protección) y hasta 2 en el financiero, además de la lectura semanal de datos, ordenados por score.
   - Un frente sin candidatos ≥ 50 → **"Sin cambios relevantes esta semana."**
3. **"La semana en 60 segundos":**
   - los 3 asuntos de mayor score, sea cual sea su frente;
   - prioridad a los que tienen fuente T1;
   - como máximo 2 del mismo frente.
4. **Radar** (35–49): puede aparecer al final como "En el radar", una línea por asunto, sin análisis y solo si el informe tiene menos de 6 asuntos.
5. **Topes de extensión:** el email renderizado no debe superar ~1.800 palabras (lectura de 6–8 minutos) ni 100 KB de HTML.
6. El editor puede **excluir** asuntos o **forzar su inclusión** desde la previsualización. Se registra en `editor_actions` y sirve para calibrar el scoring.

## 6. Alertas

### 6.1 Disparadores

| Tipo | Disparador | Texto |
|---|---|---|
| Noticia | score ≥ 80 **y** al menos una confirmación T1 (o dos T2 independientes para incidentes de seguridad) | LLM (`alert.system.md`) + validación (doc 08) |
| Mercado: depeg | USDT o USDC < 0,97 $ o > 1,03 $ sostenido 60 min (sondeo cada 5 min) | Plantilla fija |
| Mercado: nuevo ATH | precio > ATH almacenado, confirmado por la segunda fuente | Plantilla fija (tono sobrio: hecho + distancia recorrida desde el último ATH) |
| Mercado: flujo ETF extremo | reglas de `rules.yaml → etf.alert` (≥ 1.000 M $, ≥ 3σ, racha de 7 sesiones y ≥ 2.000 M $, o un emisor ≥ 750 M $), con conciliación CONSISTENTE | Plantilla fija |
| On-chain | **Nunca** alerta pública por sí sola; solo aviso interno para revisión humana | — |

### 6.2 Flujo y controles

1. Se crea el borrador (`alerts.status = pending_approval`) y se envía al grupo admin con la previsualización, el desglose del score, las fuentes y el informe del verificador. Botones: [Aprobar] [Editar] [Descartar].
2. **SLA:** 30 min en horario laboral. Un borrador no aprobado **caduca a las 24 h**; si el asunto sigue siendo relevante, pasa al Weekly.
3. **Antifatiga:**
   - máximo **2 alertas públicas por semana** (el editor puede forzar una tercera);
   - **72 h** de enfriamiento por `event_key`;
   - `dedup_key` único mientras la alerta está viva.
4. **Email** de la alerta: solo a suscriptores que lo hayan aceptado expresamente (segmento del proveedor de email; doc 10).
5. **Autopublicación:** solo para alertas de mercado y solo si `settings.alerts.autopublish_market_rules=true`. Por defecto está desactivada.

## 7. Calendario fiscal y regulatorio

`config/calendar/regulatory.yaml` guarda cada plazo con su jurisdicción, obligación, base jurídica y estado:

| Estado | Significado |
|---|---|
| `confirmed` | confirmado |
| `pending_norm` | pendiente de que se publique la norma |
| `inferred` | deducido |
| `unverified` | sin verificar |

Cada plazo lleva además la URL de la evidencia y la fecha de la última verificación.

- **Uso:**
  - alimenta "Hoy vigilaría…" (doc 04 §6);
  - alimenta la agenda del Weekly;
  - alimenta el suelo de scoring por plazo inminente.
- **Regla editorial:** un plazo `pending_norm` o `unverified` nunca se presenta como definitivo. Se escribe "previsto, pendiente de publicación en el BOE".
- **Revisión** mensual y cada vez que el BOE o el BOPA publiquen una orden sobre los modelos 172, 173, 175, 721, 718 o 714, o sobre la campaña de IRPF.

## 8. Cumplimiento específico de la ingesta de noticias

- **Derecho de los editores de prensa** (art. 15 de la Directiva (UE) 2019/790 y su transposición española): de los medios solo se usan el titular y el enlace. No se resumen ni se republican artículos de pago o protegidos.
- **Reutilización del sector público** con atribución:
  - BOE: "Fuente de los datos: Agencia Estatal Boletín Oficial del Estado";
  - EUR-Lex y Comisión: Decisión 2011/833/UE, CC BY 4.0;
  - OECD: CC BY 4.0 desde julio de 2024;
  - FATF: sin alterar, citando y con su aviso legal.

  Los avisos legales de CNMV, AEAT, INCIBE, AFA, BOPA y los reguladores de EAU están **pendientes de revisión manual** antes de cualquier redistribución comercial de su texto.
- **Datos personales:** las advertencias de la CNMV, las secciones III y V del BOE y las notas policiales pueden nombrar a particulares. Nunca se publica el nombre de una persona física salvo que sea imprescindible y tenga base legítima; en la práctica, se omite.
- **CENDOJ:** solo enlaces manuales, sin automatización.
- **Suplantación:** circulan "alertas de seguridad" falsas que imitan a fabricantes de wallets. Solo se ingieren avisos desde dominios oficiales y organizaciones de GitHub verificadas. **Nunca se retransmite un "actualiza tu firmware urgentemente" no verificado.**
