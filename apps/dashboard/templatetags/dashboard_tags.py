from django import template

register = template.Library()


@register.filter
def percentage(value, total):
    try:
        return round((value / total) * 100, 1)
    except (ZeroDivisionError, TypeError):
        return 0
