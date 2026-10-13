"""Filtros e tags de apresentação."""
import re

from django import template
from django.utils.html import conditional_escape, format_html, format_html_join
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def difficulty_dots(level):
    level = int(level or 0)
    dots = "".join('<i class="on"></i>' if i <= level else "<i></i>" for i in range(1, 6))
    return mark_safe(f'<span class="dots" role="img" aria-label="Dificuldade {level} de 5">{dots}</span>')


@register.simple_tag
def meter(value, small=False):
    try:
        v = max(0.0, min(100.0, float(value or 0)))
    except (TypeError, ValueError):
        v = 0.0
    cls = "meter small" if small else "meter"
    return format_html('<div class="{}" role="meter" aria-valuemin="0" aria-valuemax="100" aria-valuenow="{}">'
                       '<span style="width:{}%"></span></div>', cls, round(v), round(v, 1))


@register.filter
def pct(value):
    if value is None:
        return "—"
    return f"{round(float(value))}%"


@register.filter
def score_pct(value):
    if value is None:
        return "—"
    return f"{round(float(value) * 100)}%"


@register.filter
def result_mark(result):
    return {"correct": "✓", "incorrect": "✗", "partial": "½", "pending": "…"}.get(result, "·")


@register.filter
def dialogue(text):
    """Renderiza texto com linhas 'Nome : fala' destacando o falante; parágrafos por linha em branco."""
    out = []
    for para in re.split(r"\n\s*\n", text or ""):
        lines = []
        for line in para.strip().splitlines():
            m = re.match(r"^([^:\n]{1,30}) : (.*)$", line)
            if m:
                lines.append(format_html('<span class="dialogue-line"><b>{}</b> : {}</span>', m.group(1), m.group(2)))
            else:
                lines.append(conditional_escape(line))
        if lines:
            out.append("<p>" + "<br>".join(lines) + "</p>")
    return mark_safe("".join(out))


@register.filter
def get_item(d, key):
    try:
        return d.get(key)
    except AttributeError:
        return None


@register.filter
def minutes(total):
    total = int(total or 0)
    if total < 60:
        return f"{total} min"
    return f"{total // 60} h {total % 60:02d} min"
