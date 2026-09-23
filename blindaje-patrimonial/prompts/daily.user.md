<!-- prompt_id: daily.user · version: daily-v1.0 · plantilla Jinja2 -->
Fact sheet del {{ meta.weekday_es }} {{ meta.report_date }}:

<fact_sheet>
{{ fact_sheet_json }}
</fact_sheet>
{% if validation_feedback %}

Tu versión anterior no superó la validación automática por estos motivos. Corrígelos sin introducir cambios innecesarios en lo demás:

<validation_feedback>
{{ validation_feedback }}
</validation_feedback>
{% endif %}

Redacta la lectura, el "Hoy vigilaría…" y los comentarios de bloque siguiendo las reglas.
