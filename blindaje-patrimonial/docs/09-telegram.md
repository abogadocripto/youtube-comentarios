# 09 — Telegram: canal público y bot de edición

> Estado de la Bot API a 23 sep 2026: versión **10.3** (24 ago 2026). La verificación se hizo con copias oficiales de la especificación en GitHub (tdlib, especificación de aiogram) porque core.telegram.org no era accesible desde el entorno de diseño. Se confirmará en la Fase 0.

## 1. Piezas

| Pieza | Qué es | Permisos |
|---|---|---|
| **Canal público** "Blindaje Patrimonial · Daily Bitcoin" (nombre por decidir) | Donde se publican el Daily, las alertas y el aviso del Weekly | Propietario: cuenta de Telegram del despacho con 2FA |
| **Bot publicador** (`@…_publisher_bot`) | Solo publica, edita y fija en el canal | Administrador del canal con `can_post_messages`, `can_edit_messages` (necesario también para fijar) y `can_delete_messages`. Nada más |
| **Bot de edición** (`@…_editor_bot`, *adminbot*) | Interfaz del equipo: previsualizaciones, aprobaciones, correcciones, estado | Solo responde a una lista cerrada de IDs de usuario; opera en un **grupo privado de editores** |
| **Canal privado de pruebas** | Modo sombra y ensayo en seco diario a las 08:50 | Mismo bot publicador |
| **Grupo de comentarios** (opcional) | Si se quieren comentarios bajo los posts | Moderado; decisión editorial pendiente (§8) |

Son dos bots separados para que el compromiso de uno no afecte al otro. Se direccionan por **ID numérico** (`-100…`), no por @alias.

## 2. Formato del mensaje

- **`parse_mode=HTML`**, no MarkdownV2. MarkdownV2 exige escapar `_*[]()~\`>#+-=|{}.!`, y cifras como "+2,5 %" o "−$420 M" rompen el mensaje entero con un error 400.
- **Escapado:** todo valor dinámico, incluido el texto del LLM, pasa por `html.escape(v, quote=False)` antes de entrar en la plantilla. Solo la plantilla aporta etiquetas.
- **Etiquetas permitidas** (V-HTML, doc 08): `<b>`, `<i>`, `<u>`, `<s>`, `<a href>`, `<code>`, `<pre>`, `<blockquote>`.
- **Longitud:** objetivo de 1.200–2.000 caracteres visibles; máximo duro de 3.500, frente a los 4.096 que admite Telegram, que se cuentan tras interpretar las entidades. Si se supera, el renderizador retira bloques opcionales por orden de *salience* ascendente.
- **Vista previa de enlaces** desactivada por defecto (`link_preview_options.is_disabled=true`). Si en el futuro se añade un gráfico:
  - **opción A:** `link_preview_options` con la URL de la imagen, `prefer_large_media=true`, `show_above_text=true` y un parámetro de fecha para evitar la caché;
  - **opción B:** `sendPhoto` (pie ≤ 1.024 caracteres) seguido del texto en un mensaje silencioso.

  Recomendación: la opción A, porque mantiene un único mensaje.
- **`protect_content=false`:** se quiere que la comunidad reenvíe los mensajes.
- **Notificaciones:**
  - Daily de las 09:00 y alertas: **con sonido**;
  - mensajes accesorios (correcciones, gráfico, fe de erratas): `disable_notification=true`;
  - fijar mensajes en un canal siempre es silencioso;
  - nunca `allow_paid_broadcast`.

### 2.1 Plantilla del Daily (`editorial/templates/daily_telegram.html.j2`)

```
☀️ <b>BITCOIN MORNING BRIEF</b> · {{ weekday }}, {{ date_es }} · {{ ai_label }}
   ← ai_label = "🤖 Lectura elaborada con IA" (hay texto del LLM) | "Lectura automática por plantillas" (respaldo)
     | "Redactado con asistencia de IA · revisado por [Nombre], abogado" (solo si hubo revisión sustantiva registrada)
     Obligatoria en la PRIMERA línea (art. 50.4-50.5 del Reglamento de IA; doc 11 §3). Validador V-AILABEL.

₿ <b>Bitcoin</b>
{{ btc_usd }} · {{ btc_eur }}
24 h: {{ chg_24h }} · 7 d: {{ chg_7d }}{% if eur_hint %} (en euros: {{ chg_7d_eur }}){% endif %}
Máximo histórico: {{ ath_usd }} ({{ ath_date }}) · {{ drawdown }} · {{ days_since_ath }} días
{% for block in blocks %}                         ← solo bloques seleccionados (doc 04 §5.2), en orden fijo
{{ block.emoji }} <b>{{ block.title }}</b>{% if block.as_of_label %} · {{ block.as_of_label }}{% endif %}
{{ block.data_line }}                              ← línea(s) determinista(s) con los hechos seleccionados
{% if block.comment %}{{ block.comment }}{% endif %}  ← comentario del LLM (escapado)
{% endfor %}
{% if axes|length >= 2 %}🌡️ {{ axes_line }}{% endif %}

🧭 <b>La lectura</b>
{{ lectura }}

👀 <b>Hoy vigilaría…</b>
{{ vigilar }}

<i>{{ footer_legal }} Datos a {{ data_timestamp }}: {{ attributions }}.</i> <a href="{{ methodology_url }}">Metodología, aviso legal y declaración de intereses</a>
```

`footer_legal` es un texto fijo versionado (`config/editorial.yaml`, doc 11 §7), de 300–400 caracteres. Nunca lo redacta el LLM. Incluye:
- aviso de información general sin asesoramiento;
- frase de riesgo;
- explicación del papel de la IA ("las cifras se insertan automáticamente desde las fuentes");
- enlace a la declaración de intereses.

Orden fijo de los bloques:
1. ₿ Bitcoin;
2. 🧠 Sentimiento;
3. 🌊 Liquidez;
4. 🏦 Demanda ETF;
5. 🔗 On-chain / Exchanges;
6. 🏛️ Tipos y dólar (o 📈 Risk-on si hay licencia del Nasdaq);
7. ⚡ Derivados.

Un orden estable crea hábito de lectura.

Ejemplo real renderizado: `schema/examples/daily_rendered.example.html` (y doc 07 §3).

### 2.2 Plantillas de alerta

**Alerta por noticia** (texto del LLM validado):
```
⚠️ <b>ALERTA PATRIMONIAL</b>
<b>{{ titular }}</b>

<b>Qué ha pasado:</b> {{ que_ha_pasado }}
<b>Por qué importa:</b> {{ por_que_importa }}
<b>A quién afecta:</b> {{ a_quien_afecta }}
<b>Qué vigilar:</b> {{ que_vigilar }}

Estado: {{ legal_status_es }} · Fuente: <a href="{{ url_T1 }}">{{ publisher }}</a>
<i>Elaborada con asistencia de IA y revisada por {{ reviewer_name }}, abogado. {{ footer_legal_alert }}</i>
```

Las alertas por noticia **solo se publican tras la revisión sustantiva del abogado** (verificación de hechos contra las fuentes), con registro de revisor, hora, diferencias y hash (doc 11 §3.2). Si algún día se habilitara la publicación sin revisión, la primera línea tendría que decir "⚠️ ALERTA AUTOMÁTICA · texto generado con IA · sin revisión humana".

**Alerta de mercado** (plantilla sin LLM). Ejemplo de depeg:
```
⚠️ <b>ALERTA PATRIMONIAL · Stablecoins</b>
USDT cotiza a {{ usdt_peg }} desde hace {{ minutos }} min (paridad de referencia: 1 $).
Qué significa: una desviación sostenida de la paridad puede afectar a quien mantiene saldos en esta stablecoin o la usa para operar.
Qué vigilar: comunicados del emisor y de los principales exchanges; evolución de la paridad en las próximas horas.
Datos: CoinGecko. <i>Información general; no es asesoramiento.</i>
```

### 2.3 Aviso del Weekly en Telegram

El domingo, una vez enviado el email, se publica un mensaje corto:
- los 3 puntos de "La semana en 60 segundos", resumidos;
- el enlace al archivo web del número.

Los informes completos solo en el email. Así Telegram también sirve para captar suscriptores de la newsletter.

## 3. Publicación: fiabilidad e idempotencia

| Situación | Comportamiento |
|---|---|
| Antes de enviar | Se inserta `publications(idempotency_key='telegram_public:daily:YYYY-MM-DD', status='pending')` |
| Respuesta `ok:true` | Se guardan `message_id` y `sent_at`; `status='sent'` |
| **429** | Se espera `retry_after` y se reintenta (la petición no se procesó) |
| **400** "can't parse entities" | Error de plantilla o de escapado → versión de respaldo en texto plano **y** aviso al editor |
| **5xx** explícito | Reintento con backoff (hasta 3) |
| **Timeout de red tras enviar la petición (ambiguo)** | **NO se reintenta automáticamente.** La Bot API no tiene clave de idempotencia y un bot no puede leer el historial del canal. Se marca `status='unknown'` y se avisa al editor, que comprueba el canal con un botón: [Se publicó] (y se registra el `message_id`) / [No se publicó → publicar ahora]. Pendiente de prueba empírica: si el bot recibe la actualización `channel_post` de sus propios mensajes, se podría conciliar automáticamente |
| Después de las 10:30 sin publicar | El job se niega a publicar solo y pide confirmación humana (evita un "Morning Brief" a mediodía sin contexto) |

**Ensayo diario:** a las 08:50 se envía el borrador al **canal privado de pruebas**. Si falla el formato, hay 10 minutos para el respaldo.

**Planificación:**
- temporizador de systemd `publish-daily.timer` con `OnCalendar=*-*-* 09:00:00 Europe/Madrid`, `AccuracySec=1s` y `RandomizedDelaySec=0`;
- **dead-man switch** en Healthchecks.io: si no llega la señal de publicación antes de las 09:03, email al operador y aviso al grupo de edición;
- **respaldo externo:** a las 09:07 (Cloud Scheduler o GitHub Actions con zona horaria) se ejecuta `bp publish-daily --only-if-missing`. Nunca es el disparador principal.

## 4. Correcciones

- **`editMessageText`** sobre el `message_id` guardado. No hay límite temporal para los mensajes del propio bot en su canal.
- Si la corrección es material, se añade al final: "✏️ <i>Corregido HH:MM: {{ qué cambió }}</i>".
- Si el error ya ha circulado mucho, se publica además un mensaje breve y silencioso de fe de erratas.
- **Retirar** (`deleteMessage`) solo por riesgo legal, con registro en `editor_actions`.
- Toda corrección genera un caso nuevo en la batería adversarial (doc 08 §6) si revela un fallo sistemático.

## 5. Bot de edición (grupo privado)

Funciona con *long polling* (`getUpdates`, timeout 50 s, `allowed_updates` filtrado) como servicio del VPS. No necesita una URL pública ni webhooks.

**Mensajes automáticos:**

| Momento | Contenido | Botones |
|---|---|---|
| 08:57 diario | Previsualización del Daily + resumen de validación (avisos, métricas omitidas, fuentes caídas) | [Retener publicación] [Ver fact sheet] |
| 09:00 | Confirmación de publicación con enlace | [Corregir] [Retirar] |
| 09:05 | Informe operativo (doc 01 §7) | — |
| Alerta en borrador | Previsualización + desglose del score + fuentes + informe del verificador | [Aprobar] [Editar] [Descartar] [Aprobar + email] |
| Sábado 10:25 | Previsualización del Weekly + enlace al email de prueba + anotaciones del verificador | [Aprobar envío] [Editar] [Excluir asunto…] [Posponer] |
| Incidencias | Fuente caída más de N horas, dato congelado, timeout ambiguo, fallo del nodo | [Ver detalle] [Silenciar fuente 24 h] |

**Comandos:**

| Comando | Qué hace |
|---|---|
| `/estado` | salud del sistema |
| `/hoy` | fact sheet resumido |
| `/retener` / `/reanudar` | pausa o reanuda el Daily |
| `/publicar_ahora` | publica inmediatamente |
| `/corregir <texto>` | corrige el mensaje publicado |
| `/alertas` | alertas pendientes |
| `/coste` | coste del mes |
| `/fuentes` | estado del registro de licencias |

**Edición de un texto:** "Editar" abre un diálogo en el que el editor escribe la versión corregida. El texto editado **vuelve a pasar los validadores deterministas**, salvo V-NUM en el caso de que el editor escriba cifras a mano, lo que queda registrado como `override` en `editor_actions`. Lo que un humano cambia también queda trazado.

Seguridad:
- lista cerrada de `user_id`;
- los botones llevan un `callback_data` firmado (HMAC con caducidad);
- una segunda confirmación para acciones destructivas: retirar y publicar fuera de hora.

## 6. Métricas del canal

La Bot API **no ofrece estadísticas de canal** (visualizaciones, alcance). Solo `getChatMemberCount`, que se registra a diario.

Las estadísticas completas (visualizaciones por mensaje, crecimiento) se consultan a mano en la app de Telegram, disponibles a partir de cierto número de suscriptores. Automatizarlas exigiría una cuenta de usuario vía MTProto (Telethon `stats.getBroadcastStats`): **no se recomienda** sin revisar los términos de Telegram.

## 7. Monetización (no en el lanzamiento)

Existen dos mecanismos:
- canales privados de pago con Telegram Stars (`createChatSubscriptionInviteLink`, 1–10.000 Stars cada 30 días);
- contenido de pago puntual (`sendPaidMedia`).

**No se recomienda al inicio:**
- los Stars se cobran en TON a través de Fragment, con KYC, retención de 21 días y comisiones de las tiendas de aplicaciones, lo que tiene implicaciones contables y de IVA para un despacho;
- un canal de pago con análisis de mercado puede percibirse como venta de señales, justo el posicionamiento que se quiere evitar;
- puede acercar la actividad al perímetro regulatorio del asesoramiento (doc 11).

## 8. Decisiones pendientes (Telegram)

1. **Nombre y alias del canal**, y si se integra en la marca ABAST o en una submarca.
2. **Comentarios** (grupo de discusión): aportan comunidad, pero exigen moderación y generan riesgo de que se hagan consultas personales en público; eso acercaría el canal al asesoramiento personalizado (doc 11 §2.1–2.2). Recomendación: **sin comentarios al inicio**.
   - Los mensajes directos al bot se contestan con una plantilla fija que remite a un encargo profesional (identificación del cliente, conflictos, hoja de encargo).
   - **El LLM nunca responde a usuarios.**
3. **Idiomas:** solo castellano al inicio. El catalán, para el público andorrano, o el inglés se añadirían como canal separado en una fase posterior.
