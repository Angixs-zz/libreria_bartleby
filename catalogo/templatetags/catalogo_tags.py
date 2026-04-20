from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Permite hacer {{ dict|get_item:key }} en templates Django."""
    try:
        return dictionary.get(key)
    except AttributeError:
        # Si no es un dict (por ejemplo un string accidental), evitamos romper la plantilla.
        try:
            return dictionary[key]
        except Exception:
            return None
