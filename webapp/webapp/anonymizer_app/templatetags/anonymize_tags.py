from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe
import re

register = template.Library()

@register.filter(is_safe=True)
def highlight_anonymized(text, restore_map):
    """Wrap anonymized labels in spans so they are colored in the rendered output."""
    if not text or not restore_map:
        return escape(text)

    escaped_text = escape(text)
    labels = sorted(restore_map.keys(), key=len, reverse=True)
    for label in labels:
        escaped_label = escape(label)
        escaped_text = re.sub(
            rf"\b{re.escape(escaped_label)}\b",
            f"<span class=\"anonymized-label\">{escaped_label}</span>",
            escaped_text,
        )
    return mark_safe(escaped_text)
