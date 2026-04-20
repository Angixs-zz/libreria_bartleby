from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Permite hacer {{ dict|get_item:key }} en templates Django."""
    return dictionary.get(key)
