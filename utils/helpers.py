"""
Utilidades compartidas del proyecto Bartleby.
"""

import string
import re
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from django.utils.crypto import get_random_string
from django.db.models import Q


def generar_sku_mejorado():
    """
    Genera SKU único de 4 caracteres alfanuméricos.
    Usa get_random_string de Django para mayor seguridad.
    
    Returns:
        str: SKU en formato "BRT-XXXX"
    """
    codigo = get_random_string(
        4,
        allowed_chars='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    )
    return f"BRT-{codigo}"


def buscar_por_isbn(isbn_str):
    """
    Busca un libro por ISBN exacto o normalizado.
    Maneja variantes con o sin guiones.
    
    Args:
        isbn_str (str): ISBN a buscar
        
    Returns:
        Libro o None: El primer libro que coincida
    """
    from inventario.models import Libro
    
    if not isbn_str:
        return None
    
    # Normalizar ISBN removiendo espacios y guiones
    isbn_limpio = isbn_str.replace('-', '').replace(' ', '').strip()
    
    return Libro.objects.filter(
        Q(isbn=isbn_str) | Q(isbn=isbn_limpio)
    ).first()


def validar_precio(precio_str):
    """
    Valida y convierte un precio string a Decimal.
    
    Args:
        precio_str (str): Precio como string
        
    Returns:
        tuple: (Decimal, error_message) o (None, None) si es válido
        
    Raises:
        ValueError: Si el precio no es válido
    """
    try:
        precio = Decimal(precio_str)
        
        if precio <= 0:
            raise ValueError("El precio debe ser mayor a 0")
        
        if precio > Decimal('999999.99'):
            raise ValueError("El precio excede el máximo permitido")
        
        return precio, None
    
    except (InvalidOperation, ValueError) as e:
        return None, str(e)


def aplicar_precio_psicologico(precio):
    """
    Convierte precios enteros a precios psicológicos terminados en .99.

    Ejemplos:
    - 200 -> 199.99
    - 150.00 -> 149.99
    - 199.99 -> 199.99
    """
    if precio in (None, ''):
        return precio

    try:
        precio_decimal = Decimal(precio).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError, ValueError):
        return precio

    if precio_decimal <= Decimal('0.00'):
        return precio_decimal

    entero = precio_decimal.to_integral_value(rounding=ROUND_DOWN)
    if precio_decimal == entero:
        return (precio_decimal - Decimal('0.01')).quantize(Decimal('0.01'))

    return precio_decimal


def validar_isbn(isbn_str):
    """
    Valida si un ISBN tiene formato válido (ISBN-10 o ISBN-13).
    
    Args:
        isbn_str (str): ISBN a validar
        
    Returns:
        bool: True si es válido, False en caso contrario
    """
    if not isbn_str:
        return True  # ISBN es opcional
    
    # Remover guiones y espacios
    isbn_limpio = isbn_str.replace('-', '').replace(' ', '').upper()
    
    # Validar ISBN-10 o ISBN-13
    # ISBN-10: 10 dígitos o 9 dígitos + X
    # ISBN-13: 13 dígitos, comenzando con 978 o 979
    
    if len(isbn_limpio) == 10:
        return all(c.isdigit() for c in isbn_limpio[:-1]) and (isbn_limpio[-1].isdigit() or isbn_limpio[-1] == 'X')
    
    if len(isbn_limpio) == 13:
        return isbn_limpio.isdigit() and (isbn_limpio.startswith('978') or isbn_limpio.startswith('979'))
    
    return False


def validar_cantidad(cantidad_str, stock_disponible=None):
    """
    Valida cantidad de ejemplares.
    
    Args:
        cantidad_str (str): Cantidad como string
        stock_disponible (int): Stock disponible (opcional para máximo)
        
    Returns:
        tuple: (cantidad, error_message) o (None, None) si es válido
    """
    try:
        cantidad = int(cantidad_str)
        
        if cantidad <= 0:
            raise ValueError("La cantidad debe ser mayor a 0")
        
        if stock_disponible is not None and cantidad > stock_disponible:
            raise ValueError(f"No hay suficiente stock. Disponible: {stock_disponible}")
        
        return cantidad, None
    
    except (ValueError, TypeError) as e:
        return None, str(e)


def validar_nombre_humano(nombre):
    """
    Valida que un nombre o apellido humano no contenga números ni caracteres extraños.
    Permite letras (incluyendo acentuadas y eñes), espacios, guiones y apóstrofes.
    
    Args:
        nombre (str): Nombre o apellido a validar
        
    Returns:
        tuple: (bool, error_message o None)
    """
    if not nombre:
        return True, None
    
    nombre_str = str(nombre).strip()
    
    if not nombre_str:
        return True, None
        
    # Verificar si contiene dígitos
    if any(char.isdigit() for char in nombre_str):
        return False, "El nombre o apellido no puede contener números."
        
    # Expresión regular que permite letras de español, acentos, espacios, guiones y apóstrofes
    patron = r"^[a-zA-ZáéíóúÁÉÍÓÚñÑüÜ\s'\-]+$"
    if not re.match(patron, nombre_str):
        return False, "El nombre o apellido contiene caracteres no válidos (solo se permiten letras, espacios, guiones y apóstrofes)."
        
    return True, None


def validar_telefono_mexico(telefono):
    """
    Valida y normaliza un número de teléfono de México a 10 dígitos.
    Debe contener exactamente 10 dígitos (o 12 si incluye la clave de país 52).
    
    Args:
        telefono (str): Teléfono a validar
        
    Returns:
        tuple: (bool, valor_limpio o error_message)
    """
    if not telefono:
        return True, ""
        
    telefono_str = str(telefono).strip()
    if not telefono_str:
        return True, ""
        
    # Eliminar caracteres no numéricos
    digitos = re.sub(r'\D', '', telefono_str)
    
    # Manejar prefijo de país 52
    if len(digitos) == 12 and digitos.startswith('52'):
        digitos = digitos[2:]
        
    if len(digitos) != 10:
        return False, "El número de teléfono debe tener exactamente 10 dígitos (formato de México, ej: 5512345678)."
        
    if len(set(digitos)) == 1:
        return False, "El número de teléfono no es válido (todos los dígitos son iguales)."
        
    return True, digitos


def validar_email_robusto(email):
    """
    Valida de forma robusta un formato de correo electrónico.
    Debe incluir un '@', un dominio con un punto, y un TLD válido (como .com, .edu, .mx, etc.).
    
    Args:
        email (str): Correo a validar
        
    Returns:
        tuple: (bool, valor_limpio o error_message)
    """
    if not email:
        return True, ""
        
    email_limpio = str(email).strip().lower()
    if not email_limpio:
        return True, ""
        
    # Expresión regular estándar y estricta para correos
    patron = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(patron, email_limpio):
        return False, "El formato de correo no es válido. Debe tener una estructura como usuario@dominio.com."
        
    if email_limpio.count('@') != 1:
        return False, "El correo debe contener exactamente un símbolo '@'."
        
    partes = email_limpio.split('@')
    usuario = partes[0]
    dominio = partes[1]
    
    if not usuario or not dominio:
        return False, "El correo no puede tener el usuario o el dominio vacíos."
        
    if '.' not in dominio:
        return False, "El dominio del correo debe contener al menos un punto (ej: dominio.com)."
        
    partes_dominio = dominio.split('.')
    tld = partes_dominio[-1]
    
    if len(tld) < 2 or not tld.isalpha():
        return False, "El correo debe terminar en un dominio válido de al menos 2 letras (ej: .com, .edu, .mx)."
        
    return True, email_limpio
