# 11 — Cumplimiento normativo y riesgos del propio producto

> Documento de trabajo para revisión de ABAST.
> - **Cómo se verificaron los textos:** los artículos se contrastaron con réplicas en GitHub de los diarios oficiales, actualizadas a 23 sep 2026 (legalize-eu, legalize-es, legalize-ad y boletines-md-corpus), porque EUR-Lex, BOE y BOPA no eran accesibles desde el entorno de diseño.
> - **Marcas:** **[VERIFICAR]** señala lo que debe confirmarse con la fuente oficial antes de apoyarse en ello en un dictamen.
> - **Alcance:** es orientación de diseño, no un dictamen.

## 1. Conclusión

El producto es viable si se respetan seis líneas. Dos de ellas obligan a cambios concretos en el diseño.

1. **Información general, nunca recomendación personalizada ni específica.**
   - En MiCA, el asesoramiento exige **recomendaciones personalizadas** (art. 3.1.24).
   - En Andorra la definición es **más amplia**: "recomanacions personalitzades **o específiques**" (Llei 24/2022). Esto obliga a evitar también cualquier recomendación específica sobre activos o servicios, aunque se dirija al público en general.
2. **Integridad del mercado**, que afecta a cualquiera, esté o no autorizado:
   - MiCA art. 91.2.c) prohíbe difundir señales falsas o engañosas, incluso por negligencia ("debiera haber sabido");
   - MiCA art. 91.3.c) prohíbe el *scalping*: opinar teniendo posiciones sin revelarlo.

   Por eso las capas de validación del doc 08 son **un control jurídico, no solo de calidad**, y hace falta una **declaración de intereses** pública.
3. **Transparencia sobre la IA (art. 50.4 del Reglamento de IA, aplicable desde el 2 ago 2026 y sin cambios tras el Digital Omnibus).**
   - El Daily se publica sin revisión humana sustantiva, así que lleva **etiqueta de IA visible al principio del mensaje**, no solo en el pie. **Cambio de diseño aplicado.**
   - El Weekly y las alertas pueden acogerse a la excepción si hay **revisión humana sustantiva** (verificación de hechos), **responsable editorial identificado públicamente** y **congelación del contenido tras la aprobación**. **Cambio de diseño aplicado.**
4. **Licencias de datos y propiedad intelectual:** registro de licencias con bloqueo de publicación (doc 02, doc 05, V-LIC).
5. **Protección de datos y comunicaciones comerciales:**
   - consentimiento demostrable;
   - sin píxeles de seguimiento sin consentimiento;
   - identificación LSSI completa en la newsletter;
   - proveedor de email en la UE.
6. **Deontología:**
   - EGAE (RD 135/2021) art. 20.2;
   - Llei andorrana 48/2014, art. 17 (redacción de la Llei 10/2023);
   - secreto profesional;
   - nada de clientes;
   - ninguna promesa de resultados.

## 2. Perímetro regulatorio del contenido

### 2.1 MiCA: asesoramiento sobre criptoactivos (Reglamento (UE) 2023/1114)

- **Norma.**
  - Art. 3.1.24: "prestación de asesoramiento sobre criptoactivos" es ofrecer, dar o acordar dar **recomendaciones personalizadas** a un cliente, a petición de este o por iniciativa del CASP, sobre operaciones con criptoactivos o sobre el uso de servicios de criptoactivos.
  - Es un servicio que exige autorización (art. 59) y conlleva obligaciones de idoneidad (art. 81).
- **Interpretación.**
  - El comentario impersonal difundido al público queda, con alta probabilidad, fuera del régimen de autorización.
  - Apoya esta lectura la analogía con MiFID II: según el Reglamento Delegado (UE) 2017/565, art. 9, una recomendación no es personal si se emite exclusivamente al público. Pero es una **analogía**, no texto de MiCA.
  - MiCA no contiene un régimen equivalente al art. 20 de MAR para las recomendaciones.
- **Diseño:**

| Requisito | Dónde se aplica |
|---|---|
| Ningún texto dice al lector qué hacer con sus criptoactivos (imperativos de compra, venta o mantenimiento) | prompts (doc 07); V-LEX; verificador (`investment_advice`, `personalised_advice`) |
| Semáforo por ejes con etiquetas de condiciones; ningún indicador de "compra/venta" | doc 04 §4 |
| "Qué deberías vigilar" = qué seguir y qué plazos existen | prompts del Weekly y de las alertas |
| **Sin canal de interacción personalizada:** canal sin comentarios; mensajes directos contestados con una plantilla que remite a un encargo profesional (identificación del cliente, conflictos, hoja de encargo). **El LLM nunca responde a usuarios** | doc 09 §5 y §8 |
| La segmentación por residencia solo adapta la relevancia, nunca se segmenta por nivel de patrimonio ni se dan indicaciones individuales | doc 10 §5 |

### 2.2 Andorra: Llei 24/2022 y Llei 7/2013

- **Norma.**
  - **Llei 24/2022:** el asesoramiento financiero sobre activos digitales ("recomanacions personalitzades o específiques a un tercer" sobre adquisición, venta o uso de servicios) requiere autorización previa de la AFA. Su redacción, más amplia que la de MiCA, reproduce la propuesta de MiCA de 2020.
  - **Llei 7/2013:** considera el asesoramiento en inversiones sobre instrumentos financieros un servicio de inversión, y los "informes d'inversions i anàlisis financeres o altres formes de recomanació general", un servicio auxiliar.
- **Interpretación.** Una lectura literal de "específiques" podría alcanzar recomendaciones no personalizadas pero concretas sobre un activo ("conviene tener BTC en autocustodia en la wallet X"). La postura prudente es que el producto **no contenga recomendaciones de ningún tipo**, tampoco específicas.
  - Sí caben hechos ("la AFA ha autorizado a X") y riesgos descritos ("los hackeos de exchanges afectan a los saldos en custodia de terceros").
  - No caben indicaciones ("mueve tus fondos a…").
- **[VERIFICAR]** con abogado andorrano o con la AFA:
  - si el comentario público e impersonal queda fuera de "específiques";
  - si la "recomanació general" sobre instrumentos financieros es actividad reservada a efectos prácticos.
- **Diseño:** V-LEX incluye imperativos y recomendaciones sobre productos o servicios concretos (autocustodia en X, exchange Y). El verificador marca `investment_advice` también para las recomendaciones específicas no personalizadas.

### 2.3 MiCA: abuso de mercado (título VI)

- **Norma.**
  - Art. 91.2.c): es manipulación de mercado difundir, por los medios o por internet, información que dé o pueda dar señales falsas o engañosas sobre la oferta, la demanda o el precio, incluidos los rumores, cuando se sabía o se **debería haber sabido** que era falsa o engañosa.
  - Art. 91.3.c) (numeración del apartado inferida de la estructura **[VERIFICAR]**): aprovechar el acceso a los medios para opinar sobre un criptoactivo tras haber tomado posiciones y beneficiarse del efecto en el precio, **sin revelar simultáneamente el conflicto al público de forma adecuada y efectiva**.
- **Interpretación.**
  - El volumen de bitcoin hace improbable un impacto en el precio, pero la negligencia basta para el art. 91.2.c).
  - Las alucinaciones del LLM, los flujos de ETF mal fechados o las noticias sin verificar en alertas son los vectores de riesgo reales.
- **Diseño:**
  1. **Declaración de intereses** en la página de metodología, con enlace desde el pie:
     - si ABAST, sus socios o sus editores tienen BTC o ETF/ETP de BTC;
     - que no se recibe remuneración de emisores, CASP ni exchanges (o, si se recibe, cuál);
     - cómo se gestionan los conflictos.
  2. **Política interna de operaciones personales**, que es una decisión de diseño y no una exigencia legal expresa:
     - quien redacta o aprueba no opera en BTC ni en ETP de BTC desde 24 h antes hasta 24 h después de un Daily o una alerta que haya aprobado;
     - declaración trimestral.
  3. **Las alertas solo se disparan con fuentes primarias públicas** (T1, o dos T2 para incidentes de seguridad). Nunca con rumores ni redes sociales (doc 05).
  4. **Corrección pública** de errores materiales (doc 09 §4).

### 2.4 MAR: recomendaciones de inversión (Reglamento (UE) 596/2014)

- **Norma.**
  - Art. 3.1.35: "recomendaciones de inversión" es información que recomienda o sugiere una estrategia de inversión sobre **instrumentos financieros**, incluida cualquier opinión sobre su valor presente o futuro.
  - Art. 3.1.34.ii): un no profesional solo queda comprendido si **propone directamente una decisión de inversión concreta**.
  - Art. 20 y Reglamento Delegado (UE) 2016/958: presentación objetiva y revelación de conflictos. El Reglamento Delegado define al "experto" como quien propone de forma reiterada decisiones de inversión y se presenta como experto.
  - Se aplica a instrumentos financieros (ETP de BTC cotizados en la UE y posiblemente los ETF), no a bitcoin.
- **Diseño:**
  - los flujos de ETF se describen como dato neutro;
  - prohibido valorar, comparar como inversión o sugerir un ETF o ETP concreto ("IBIT es mejor", "infravalorado");
  - si alguna vez se menciona un ETP de la UE, se indican fecha, hora y fuentes y se separan hechos e interpretación.

### 2.5 España: publicidad de criptoactivos y personas influyentes

- **La Circular 1/2022 de la CNMV fue derogada** por la Circular 1/2024, de 17 dic 2024 (BOE-A-2024-27149, BOE de 27 dic 2024, en vigor el 28 dic 2024; confirmado en boe.es), porque MiCA regula las comunicaciones publicitarias.
  - La competencia de la CNMV sobre la publicidad de criptoactivos se apoya ahora en la Ley 6/2023, art. 247.
  - Las comunicaciones publicitarias de MiCA (arts. 7, 29 y 53) afectan a oferentes, emisores y CASP, no a un comentarista independiente.
- **Diseño:**
  - sin patrocinios, enlaces de afiliación ni referidos de exchanges o emisores;
  - cualquier contenido pagado futuro irá identificado como "Publicidad" y se revisará antes conforme a MiCA.
- **RD 444/2024** (usuarios de especial relevancia): solo cubre plataformas de intercambio de vídeos, con ingresos brutos ≥ 300.000 €, ≥ 1 M de seguidores en una plataforma o ≥ 2 M en conjunto, y ≥ 24 vídeos al año. **No se aplica** al canal de Telegram ni a la newsletter. Si procede, se revisará por separado la actividad en YouTube.

### 2.6 Otras jurisdicciones

- **EAU:** el producto no se dirige activamente a sus residentes. Si se captan lectores de EAU (ABAST MENA Advisors), habría que revisar las licencias de *finfluencer* de la SCA y los permisos del UAE Media Council **[VERIFICAR]**.
- **Reglamento de IA:** alcanza también a responsables del despliegue de terceros países cuya salida se usa en la UE (art. 2.1.c) **[VERIFICAR]**).

## 3. Reglamento de IA: transparencia (Reglamento (UE) 2024/1689)

### 3.1 Norma y estado a 23 sep 2026

| Punto | Estado |
|---|---|
| Art. 50.4, párrafo segundo | Los responsables del despliegue de un sistema de IA que genere texto publicado para informar al público sobre asuntos de interés público deben revelar que es generado por IA |
| Excepción | Contenido sometido a **revisión humana o control editorial**, con una persona física o jurídica que tenga la **responsabilidad editorial** |
| Forma (art. 50.5) | Clara y distinguible, a más tardar en la primera exposición |
| ¿Quién es el responsable del despliegue? | ABAST, que usa Claude por API (art. 3.4) |
| Aplicación | **Desde el 2 ago 2026** |
| Digital Omnibus (Reglamento (UE) 2026/1744, en vigor desde el 27 jul 2026) | **No modificó el art. 50.1–50.6**. Solo sustituyó el art. 50.7 y dio a los **proveedores** un periodo de gracia hasta el 2 dic 2026 para el art. 50.2 (confirmado en alertas de Goodwin y Morgan Lewis de agosto de 2026) |

**Directrices de la Comisión sobre el art. 50 (jul 2026; numeración de párrafos [VERIFICAR]):**
- **Interés público:** incluye cualquier desarrollo económico o financiero relevante para el debate público. "Publicado" significa accesible a un número indeterminado de lectores.
- **Revisión humana válida:** el mínimo es verificar los hechos.
  - **No valen:** la corrección ortográfica, tener una política editorial, que una IA revise a otra IA ni una aprobación superficial.
  - **Cualquier intervención sustantiva de la IA después de la revisión anula la excepción.**
  - La identidad y el contacto del responsable editorial deben ser públicos y fáciles de encontrar.

**Código de buenas prácticas final (10 jun 2026):** en textos, la etiqueta va **al principio o junto al titular**.

**Sanciones** (art. 99.4): hasta 15 M € o el 3 % del volumen de negocio mundial; para pymes, la cifra menor.

**En España**, la autoridad y el régimen sancionador dependen del Proyecto de Ley Orgánica de IA (expediente 121/000096, en tramitación desde el 26 may 2026) **[VERIFICAR estado]**.

### 3.2 Diseño resultante (aplicado en los docs 08, 09 y 10)

| Producto | Postura | Implementación |
|---|---|---|
| **Daily** con lectura del LLM | Sin revisión humana previa → **etiqueta obligatoria arriba** | La cabecera incluye "🤖 Lectura elaborada con IA". El pie añade: "Texto interpretativo generado por IA a partir de los datos citados; las cifras se insertan automáticamente desde las fuentes; sin revisión humana previa." Validador **V-AILABEL** |
| **Daily** de respaldo (lectura por plantillas, sin LLM) | No hay texto generado por IA | La cabecera dice "Lectura automática por plantillas" |
| Daily revisado por un abogado antes de las 09:00 (opcional) | Excepción posible | "Redactado con asistencia de IA · revisado por [Nombre], abogado", solo si hubo verificación de hechos registrada |
| **Weekly** | Revisión **sustantiva** obligatoria por abogado | **Verificación de hechos**: cada afirmación contrastada con su cita (`evidence_quote`). Se registran quién revisó, cuándo, los cambios y el **SHA-256 del HTML y del texto aprobados**. El envío se **bloquea si cambia el hash**; cualquier regeneración por el LLM (asunto, preheader incluidos) obliga a reaprobar. Responsable editorial **identificado públicamente** en cada número y en la web. Se mantiene igualmente la línea "Elaborado con asistencia de IA y revisado y validado por…" |
| **Alertas por noticia** | Aprobación humana sustantiva, con los mismos registros y hash | Si alguna vez se publicara sin revisión, etiqueta arriba: "⚠️ ALERTA AUTOMÁTICA · texto generado con IA · sin revisión humana" |
| **Alertas de mercado** | Plantilla determinista, sin LLM | Sin etiqueta de IA |

**Alfabetización en IA** (art. 4, en la redacción del Omnibus: "adoptar medidas para apoyar"): breve formación documentada para editores y revisores sobre límites del LLM, validadores y el protocolo de corrección.

## 4. Protección de datos y comunicaciones electrónicas

| Tratamiento o requisito | Norma | Diseño |
|---|---|---|
| Consentimiento para la newsletter | RGPD arts. 6.1.a) y 7.1 (hay que poder demostrarlo); LSSI art. 21.1 (prohibidas las comunicaciones promocionales no solicitadas ni autorizadas expresamente). La LSSI incluye la **promoción indirecta de la imagen o los servicios del profesional** en el concepto de comunicación comercial (anexo, letra f), así que una newsletter de despacho lo es | Casilla sin premarcar y consentimientos separados: informe, alertas por email, analítica opcional. **Doble opt-in**: no lo exige la ley, pero es la mejor prueba. Registro de consentimiento (hash del email, fecha y hora, IP, URL y versión del formulario, versión del texto, confirmación) exportado y respaldado |
| Andorra | Llei 20/2014 (consentimiento previo para comunicaciones comerciales electrónicas); Llei 29/2021 (modificada por la Llei 12/2024); decisión de adecuación de la UE 2010/625/UE | El mismo estándar cubre ambas jurisdicciones |
| Revocación y oposición | LSSI art. 22.1 (dirección válida para revocar en cada envío); RGPD art. 21.2–21.3 | Baja en un clic + email de contacto en el pie |
| Identificación del remitente | LSSI art. 20.1 (comunicación y remitente identificables) y **art. 10.1.d)** (profesión regulada: colegio y número de colegiado, título) | Pie del Weekly con razón social, NIF, domicilio, email, colegio y número, y título profesional |
| Píxeles de seguimiento | LSSI art. 22.2; Directrices EDPB 2/2023 (los píxeles y las URL de seguimiento entran en el ámbito del art. 5.3 de ePrivacy) | **Seguimiento de aperturas desactivado** y sin seguimiento de clics por destinatario. Solo métricas agregadas no identificativas o con consentimiento específico. Se anota en el registro de actividades de tratamiento |
| Encargado del tratamiento | RGPD art. 28 | Proveedor de email de la UE con DPA (Brevo) o autoalojado (doc 10) |
| Datos personales en noticias | Minimización | No publicar nombres de personas físicas (doc 05 §8) |
| Responsable del tratamiento | — | **[DECIDIR]** sociedad del grupo; condiciona la normativa aplicable (LOPDGDD o Llei 29/2021), el aviso de privacidad y el DPA |

## 5. Deontología profesional

- **España.** EGAE (RD 135/2021), art. 20.2: prohíbe en la publicidad de los abogados:
  - a) revelar hechos amparados por el secreto profesional;
  - b) incitar al pleito;
  - c) ofrecer servicios a víctimas de accidentes o catástrofes (durante 45 días);
  - d) prometer resultados que no dependan exclusivamente del abogado;
  - e) referirse a clientes sin autorización;
  - f) usar emblemas institucionales o colegiales;
  - g) mencionar actividades incompatibles.

  **[VERIFICAR]** el art. 6 del Código Deontológico de 2019 y las normas del colegio correspondiente sobre redes sociales y newsletters.
- **Andorra.** Llei 48/2014, art. 17 (Llei 10/2023): la publicidad debe respetar la independencia y el honor, ser digna, fiel, veraz y leal, y respetar el secreto profesional.
- **Diseño:**
  1. **Nunca** se usa información de clientes ni de asuntos. Los datos del sistema son exclusivamente públicos.
  2. Si un asunto afecta a un cliente, el editor puede excluirlo o tratarlo con especial neutralidad, con registro.
  3. El bloque comercial es **fijo, separado del contenido de datos y nunca dentro de "La lectura"**. Sin promesas, sin incitar a reclamar, sin nombres de clientes, sin emblemas colegiales.
  4. Se aclara que la lectura no crea una relación profesional.
  5. Contenidos atribuidos a la sociedad correcta del grupo **[DECIDIR]**.
  6. V-LEX incluye las fórmulas prohibidas por deontología: "te garantizamos", "ganaremos", "reclama ya"…

## 6. Licencias de datos y propiedad intelectual

- **Registro de licencias** (`source_licences`) con:
  - `display_allowed`, `storage_allowed` y `llm_input_allowed`;
  - el texto y la ubicación de la atribución;
  - la referencia del contrato y la evidencia archivada;
  - revisión trimestral e interruptor de desactivación por fuente.

  El validador bloquea publicar (V-LIC) y enviar al LLM (I-LIC) lo que no esté permitido.
- **Derecho *sui generis* sobre bases de datos** (Directiva 96/9/CE, art. 7; en España, arts. 133 y siguientes del TRLPI **[VERIFICAR]**): no se hace scraping de agregadores sin permiso, ni detrás de protecciones anti-bot o de un inicio de sesión.
- **Derecho de los editores de prensa** (Directiva (UE) 2019/790, art. 15): de los medios, solo titular y enlace.
- **Términos que prohíben el almacenamiento o el uso con IA:**
  - aviso de FRED de 2026 **[VERIFICAR]** (el diseño no depende de FRED);
  - Coin Metrics Community (según se informa);
  - Blockchain.com.

  Ninguno de ellos entra en la base de datos ni en el LLM.

## 7. Textos legales propuestos (borradores para revisión del despacho)

**Cabecera del Daily** (con lectura del LLM):
> ☀️ **BITCOIN MORNING BRIEF** · Miércoles, 23 sep 2026 · 🤖 Lectura elaborada con IA

**Pie del Daily y de las alertas** (plantilla, 300–400 caracteres, nunca redactado por el LLM):
> *ℹ️ Información general. No es asesoramiento financiero, fiscal ni jurídico personalizado ni una recomendación de inversión, y no tiene en cuenta tu situación. Los criptoactivos son volátiles y se puede perder todo lo invertido. Texto interpretativo generado por IA a partir de los datos citados; las cifras se insertan automáticamente desde las fuentes. ABAST y sus profesionales pueden mantener posiciones en bitcoin (declaración de intereses: [enlace]). Datos a [dd/mm hh:mm]: [atribuciones]. Metodología y aviso legal: [enlace]*

**Pie completo del Weekly:**
1. aviso de información general, sin asesoramiento personalizado, con la frase de riesgo;
2. metodología de IA + "Elaborado con asistencia de IA y revisado y validado por [Nombre Apellido], abogado ([Colegio], n.º [●]), responsable editorial, [email]";
3. conflictos de interés (posiciones, sin remuneración de emisores o CASP, o revelarla);
4. fuentes y atribuciones;
5. identificación LSSI: razón social, NIF, domicilio, email, colegio y número, título (art. 10.1.d);
6. "Recibes este email porque te suscribiste el [fecha] en [formulario]";
7. baja en un clic + dirección de email para revocar (art. 22.1);
8. política de privacidad (RGPD arts. 13 y 21);
9. fecha y hora de cierre del contenido.

**Página de metodología** (pública y versionada):
- fuentes y licencias;
- reglas de interpretación y umbrales;
- qué hace la IA y qué no hace;
- validaciones;
- procedimiento de corrección;
- declaración de intereses;
- responsable editorial y contacto.

## 8. Controles internos y conservación

| Control | Responsable | Frecuencia |
|---|---|---|
| Política editorial (tono, fuentes, cautelas, conflictos, prohibición de usar información de clientes) | Socio responsable | Anual |
| Política de operaciones personales + declaración | Socio / cumplimiento | Anual + trimestral |
| Formación en IA de editores y revisores (art. 4 del Reglamento de IA) | Socio | Al incorporarse + anual |
| Registro de licencias | Operador | Trimestral |
| Reglas y umbrales (doc 04) | Editor + operador | Trimestral |
| Muestreo del Daily | Editor | 2 días por semana |
| Revisión sustantiva y aprobación del Weekly y las alertas (con hash) | Abogado responsable editorial | Cada envío |
| Incidentes y correcciones | Editor | Continuo; revisión mensual |
| Seguimiento normativo (LO de IA española, directrices del art. 50, Omnibus RGPD/ePrivacy, directrices sobre *finfluencers* de ESMA/CNMV, Estrategia de Inversión Minorista) | Socio | Trimestral |

**Conservación** (propuesta; confirmar con el despacho):
- **5 años como mínimo** para publicaciones y registros de auditoría: texto final + SHA-256, fact sheet, observaciones con su licencia, versión del prompt y del modelo, salida del LLM, informe de validación, variante de etiqueta de IA y de aviso legal, revisor, fecha y hora, diferencias, `message_id` o id de campaña, correcciones;
- **registros de consentimiento:** mientras dure la suscripción y 3 años más.

## 9. Matriz de riesgos

| Riesgo | Probabilidad | Impacto | Mitigación principal |
|---|---|---|---|
| Error material publicado (cifra, dirección, estado jurídico) → posible "debería haber sabido" del art. 91.2.c) de MiCA | Media al inicio → baja | Alto | Slot-filling, validadores, verificador, modo sombra, corrección pública |
| Falta de etiqueta de IA o etiqueta mal ubicada | Baja (con V-AILABEL) | Alto (art. 99.4) | Etiqueta en cabecera por plantilla + validador bloqueante |
| Revisión humana "de trámite" presentada como sustantiva | Media | Alto | Lista de comprobación de verificación de hechos en el bot de edición, registro de cambios, hash congelado |
| Deriva hacia el asesoramiento (MiCA; Llei 24/2022 "específiques") | Baja | Alto | Sin interacción personalizada; léxico vetado; verificador |
| Conflicto de interés no revelado (*scalping*) | Baja | Medio-alto | Declaración de intereses + política de operaciones |
| Uso de datos sin licencia | Media si no se gestiona | Medio-alto | Registro de licencias + V-LIC + permisos escritos |
| Defectos de consentimiento o píxeles sin consentimiento | Baja | Medio | Doble opt-in, registro, seguimiento desactivado |
| Publicidad contraria a la deontología | Baja | Medio | Bloque comercial fijo y revisado; léxico vetado |
| Suplantación del canal | Media | Medio | Mensaje fijado con los canales oficiales; nunca pedir datos ni fondos |

## 10. Pendientes de verificación y decisión

1. **[DECIDIR]** Sociedad editora y responsable del despliegue de IA (española, andorrana o ambas). Condiciona:
   - las normas colegiales;
   - la exposición ante AFA y CNMV;
   - los datos de identificación LSSI;
   - el ámbito territorial del Reglamento de IA.
2. **[DECIDIR]** Responsable editorial nominativo (abogado) para el Weekly y las alertas, y si habrá revisión diaria del Daily antes de las 09:00. Si no, la etiqueta de IA es obligatoria en todos los Daily.
3. **[DECIDIR]** Contenido de la declaración de intereses: posiciones del despacho, socios y editores en BTC o ETF/ETP; relaciones comerciales con CASP o exchanges.
4. **[VERIFICAR]**
   - la numeración del art. 91.3.c) de MiCA;
   - la numeración de los párrafos de las directrices del art. 50 y el uso del art. 50.7 para respaldar el código de buenas prácticas;
   - la autoridad española competente para el art. 50.4 mientras se tramita la LO de IA.
5. **[VERIFICAR]** Con abogado andorrano o con la AFA:
   - si el comentario público impersonal queda fuera de "recomanacions específiques" (Llei 24/2022);
   - el alcance de la "recomanació general" (Llei 7/2013).
6. **[VERIFICAR]** El art. 6 del Código Deontológico de 2019 y las normas colegiales sobre newsletters y redes sociales.
7. **[VERIFICAR]** Las directrices sobre *finfluencers* de ESMA/CNMV y el estado de la Estrategia de Inversión Minorista de la UE.
