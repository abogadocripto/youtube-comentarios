# 10 — Newsletter (Informe semanal) y envío de email

## 1. Conclusión

- **Proveedor recomendado para arrancar: Brevo.**
  - Empresa de la UE con alojamiento en Alemania y Francia y DPA en autoservicio.
  - API disponible en todos los planes para crear y programar campañas con HTML propio (`POST /v3/emailCampaigns` con `htmlContent` y `scheduledAt`).
  - Precio por volumen de envío: unos 9 $/mes por 5.000 emails y unos 19 $/mes por 20.000 **[VERIFICAR en su web de precios]**.
- **Opción a escala: Listmonk** autoalojado (código abierto, AGPLv3) en el mismo VPS, enviando por Amazon SES en región UE o por Scaleway TEM, que es 100 % UE.
  - Coste de envío de 0,10–0,25 $ por cada 1.000 emails.
  - Trae de serie doble opt-in, archivo público y la cabecera de baja en un clic (RFC 8058).
  - Contrapartida: la entregabilidad pasa a ser responsabilidad propia.
  - Migrar a partir de ~5–10k suscriptores o cuando Brevo supere ~50 $/mes.
- **Descartados:**
  - beehiiv: su API de creación de posts es beta y solo para Enterprise;
  - MailerLite: el plan gratuito no permite enviar por API y el HTML propio por API depende del plan;
  - Mailchimp: caro y alojado en EE. UU.;
  - Resend Marketing: sin doble opt-in ni archivo;
  - Postmark: sin gestión de listas.
- **Kit** (gratis hasta 10.000 suscriptores, API completa) sería la opción más barata, pero **aloja los datos en EE. UU.** bajo el Marco de Privacidad de Datos UE-EE. UU., hoy recurrido (C-703/25 P). Para un despacho que asesora en protección de datos, es un riesgo de coherencia y de reputación. **No se recomienda.**
- **El archivo web se publica en el dominio propio** del despacho, como páginas estáticas generadas por el sistema. Así el archivo no depende del proveedor de email (migrar de Brevo a Listmonk no rompe enlaces) y cada número se convierte en contenido para posicionamiento web.

## 2. Flujo de envío

```
sáb 10:20  render: plantilla Jinja2 + MJML → HTML (≤ 90 KB) + texto plano + página del archivo web (borrador, no publicada)
sáb 10:22  ESP: crear campaña como BORRADOR (sin programar) → id de campaña en weekly_reports.esp_campaign_id
sáb 10:25  ESP: enviar email de prueba a los editores + previsualización en el grupo de edición (doc 09 §5)
sáb–dom    revisión SUSTANTIVA por el abogado responsable editorial (lista de verificación por asunto; doc 08 §8, doc 11 §3.2)
           [Aprobar envío] → se registran el revisor, la hora y el SHA-256 del HTML y del texto → el sistema programa la campaña
                             (scheduledAt = dom 18:00 Europe/Madrid)
           [Editar] → cambios → nueva validación (doc 08) → nuevo borrador, nuevo email de prueba y NUEVA aprobación
dom 17:55  V-HASH: el contenido de la campaña en el ESP coincide con el hash aprobado; si no, se cancela el envío y se avisa
dom 18:00  el ESP envía · el sistema publica la página del archivo web · aviso en Telegram con los 3 puntos (doc 09 §2.3)
dom 18:15  comprobación: estado de la campaña en el ESP = enviada; si no lo está, aviso al operador
```

Sin aprobación antes del domingo a las 17:00 no se envía nada. El editor recibe un recordatorio el domingo a las 12:00 y, si no aprueba, un aviso de "no enviado". **Nunca hay un envío automático sin revisión humana.**

## 3. Estructura del email

```
[Preheader oculto: {{ preheader }}]
BLINDAJE PATRIMONIAL · Informe semanal · Semana {{ n }} · {{ periodo }}
─────────────────────────────────────
LA SEMANA EN 60 SEGUNDOS
 1. …  2. …  3. …
─────────────────────────────────────
TERMÓMETRO DE LA SEMANA        Liquidez 🟢→🟢 · Macro 🟡→🔴 · Demanda 🟢→🟡 · Apalancamiento 🟡→🟡 · Sentimiento 🔴→🟡
─────────────────────────────────────
1 · FRENTE FINANCIERO
 Lectura semanal (3–6 frases) + tabla mínima de 5–6 datos (inicio → fin de semana)
 [asuntos, si los hay]
2 · FRENTE FISCAL             ← "Sin cambios relevantes esta semana." si procede
 Por asunto:  QUÉ HA PASADO · POR QUÉ IMPORTA · A QUIÉN AFECTA · QUÉ DEBERÍAS VIGILAR
              Estado: {{ estado jurídico }} · Fuente: {{ enlace T1 }}
3 · FRENTE REGULATORIO
4 · FRENTE PROTECCIÓN
─────────────────────────────────────
EN EL RADAR (opcional; una línea por asunto)
AGENDA DE LA PRÓXIMA SEMANA (macro, bancos centrales, vencimientos, plazos fiscales y regulatorios)
─────────────────────────────────────
Sobre este informe · Metodología · Fuentes y atribuciones · Declaración de intereses
"Elaborado con asistencia de IA y revisado y validado por [Nombre Apellido], abogado ([Colegio], n.º [●]), responsable editorial, [email]"
Aviso legal (información general; sin asesoramiento personalizado; frase de riesgo — doc 11 §7)
[Contacto con ABAST: bloque fijo revisado por el despacho, separado del contenido; no lo genera la IA]
Identificación LSSI (art. 10.1.d): razón social, NIF, domicilio, email, colegio y número de colegiado, título
"Recibes este email porque te suscribiste el [fecha] en [formulario]" · Gestionar preferencias · Darte de baja
(enlace visible + cabecera en un clic + email de revocación, art. 22.1 LSSI) · Política de privacidad
Contenido cerrado el [fecha, hora]
```

## 4. Plantilla y renderizado

- **Jinja2 + MJML** (`mjml-python` 1.4.x o el CLI de MJML) para obtener HTML compatible con Outlook y Gmail. Estilos en línea con `premailer` si hace falta.
- **Límites:**
  - HTML ≤ 90 KB (Gmail recorta a partir de ~102 KB; V-HTML);
  - imágenes alojadas fuera del mensaje y con `alt`;
  - siempre una **parte en texto plano**.
- **Accesibilidad y modo oscuro:** contraste suficiente, sin información transmitida solo por color. Los semáforos llevan también su etiqueta textual (doc 04). Hay que probar el modo oscuro de Gmail, que ignora `prefers-color-scheme`.
- **Identidad visual** de ABAST: aplicar la guía de marca del despacho (logotipo, paleta, tipografía) en la plantilla MJML. Se hará en la Fase 6 con los materiales oficiales.
- **Enlaces:** a la fuente T1 original y a la página del número en el archivo web. Sin acortadores de terceros.

## 5. Captación de suscriptores y consentimiento

| Elemento | Diseño |
|---|---|
| Formulario | En la web del despacho (formulario del ESP insertado o formulario propio contra la API): email + nombre (opcional) + casillas **separadas y no premarcadas**: (a) informe semanal; (b) alertas patrimoniales por email (opcional); (c) comunicaciones comerciales del despacho (opcional y aparte) |
| Doble opt-in | Obligatorio. Email de confirmación con enlace; sin confirmación no hay alta |
| Prueba del consentimiento | El ESP guarda la fecha y hora, la IP, el formulario y la versión del texto aceptado. Se exporta mensualmente al archivo de cumplimiento |
| Información al interesado | Aviso de privacidad en capas: responsable (**sociedad concreta de ABAST por confirmar**), finalidad, base jurídica (consentimiento), encargado (ESP), plazo de conservación, derechos |
| Segmentos | `weekly` (todos), `alertas_email` (opt-in adicional), `residencia` (ES/AD/otros, opcional y declarada por el usuario; permite adaptar ejemplos en el futuro sin personalizar el asesoramiento) |
| Baja | Enlace visible + cabeceras `List-Unsubscribe` (HTTPS) y `List-Unsubscribe-Post: List-Unsubscribe=One-Click` firmadas por DKIM; baja efectiva en menos de 48 h |
| Captación desde Telegram | Mensaje fijado en el canal con el enlace al formulario; aviso semanal del Weekly con enlace |

**No se guarda ningún dato de suscriptores en la base de datos del sistema** (doc 03, minimización). Solo el ESP los trata, como encargado del tratamiento con DPA firmado.

## 6. Entregabilidad (requisito para cualquier proveedor)

1. **Subdominio de envío dedicado** (p. ej. `informe.<dominio-del-despacho>`), para que un incidente de reputación no afecte al correo profesional del despacho.
2. **SPF** con el `include` del proveedor; **DKIM** de 2048 bits; **DMARC** empezando en `p=none` con informes `rua` y pasando a `quarantine` tras 4–6 semanas limpias. Alineación del *From*.
3. **Baja en un clic** (RFC 8058), exigida por Gmail y Yahoo a remitentes masivos, con el enlace visible.
4. **Tasa de spam < 0,3 %** (objetivo < 0,1 %). Rebotes gestionados y limpieza de inactivos cada 6 meses (campaña de reconfirmación).
5. **Calentamiento progresivo** si se migra a Listmonk + SES (salida del modo *sandbox* de SES, avisos de rebotes y quejas).

## 7. Medición

- Se miden **clics, respuestas y bajas**. Las **aperturas no son fiables**: la protección de privacidad de Apple Mail las infla.
- Según las Directrices 2/2023 del EDPB y el art. 22.2 de la LSSI, los píxeles y las URL de seguimiento **requieren consentimiento previo**. Decisión de diseño:
  - **seguimiento de aperturas desactivado** y **sin seguimiento de clics por destinatario**;
  - si se quieren métricas, dos vías: (a) consentimiento separado y específico en el alta; (b) medidas agregadas no identificativas (enlaces de redirección no personalizados);
  - la decisión se anota en el registro de actividades de tratamiento (doc 11 §4).
- Indicadores del producto:
  - crecimiento neto de suscriptores;
  - tasa de clic en fuentes;
  - respuestas;
  - bajas por número (señal de fatiga);
  - consultas al despacho atribuibles (solo si el despacho las registra).

## 8. Costes (orientativos)

| Suscriptores (envío semanal) | Brevo | Listmonk + SES UE | Kit (no recomendado) |
|---|---|---|---|
| 1.000 (~4.300 emails/mes) | ~9 $/mes | ~0,5–0,7 $/mes (+ VPS ya pagado) | 0 $ |
| 5.000 (~21.700 emails/mes) | ~19–29 $/mes | ~2–3,5 $/mes | 0 $ |
| 25.000 (~108.000 emails/mes) | **[VERIFICAR]** ~65–110 $/mes | ~11–17 $/mes | de pago (precio sin verificar) |

## 9. Decisiones pendientes (newsletter)

1. **Responsable del tratamiento:** qué sociedad del grupo firma el aviso de privacidad y contrata el ESP (ABAST Legal, ABAST Global u otra). Condiciona el aviso de privacidad y la facturación.
2. **Proveedor:** Brevo (recomendado) frente a Listmonk desde el primer día, si se prefiere control total y coste mínimo a cambio de operar la entregabilidad.
3. **Hora de envío:** domingo a las 18:00 (recomendada) frente a lunes a las 07:30.
4. **Nombre y remitente:** p. ej. "Blindaje Patrimonial · ABAST" `<informe@…>`, con respuesta a un buzón atendido.
5. **Bloque comercial:** texto fijo sobre los servicios del despacho, revisado conforme a las normas deontológicas de publicidad (doc 11).
