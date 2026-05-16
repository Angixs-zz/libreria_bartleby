"""
Decoradores personalizados para seguridad y validación.
"""

from functools import wraps
from django.contrib.auth.decorators import user_passes_test
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from django.shortcuts import redirect


def admin_required(view_func):
    """
    Decorador que requiere Director General (superusuario).
    Los cajeros NO tienen acceso a rutas protegidas con este decorador.
    
    Usage:
        @admin_required
        def mi_vista(request):
            ...
    """
    return user_passes_test(
        lambda user: user.is_authenticated and user.is_superuser,
        login_url='login'
    )(view_func)


def director_required(view_func):
    """
    Decorador que restringe el acceso al Director General (superusuario).
    Alias de admin_required, ambos exigen is_superuser.
    """
    return user_passes_test(
        lambda user: user.is_authenticated and user.is_superuser,
        login_url='login'
    )(view_func)


def cajero_required(view_func):
    """
    Decorador que permite acceso a cualquier empleado (cajero o director).
    Ideal para vistas operativas: POS, reservas, catálogo de ventas.
    
    Usage:
        @cajero_required
        def pos(request):
            ...
    """
    return user_passes_test(
        lambda user: user.is_authenticated and user.is_staff,
        login_url='login'
    )(view_func)


def cliente_requerido(view_func):
    """
    Decorador que requiere que el usuario esté autenticado como cliente.
    """
    return user_passes_test(
        lambda user: user.is_authenticated,
        login_url='login'
    )(view_func)


def api_ajax_required(view_func):
    """
    Decorador para validar que la solicitud sea AJAX.
    Devuelve JSON si no es AJAX.
    """
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse(
                {'error': 'Esta acción solo es permitida vía AJAX'},
                status=400
            )
        return view_func(request, *args, **kwargs)
    return wrapped


def json_response_handler(view_func):
    """
    Decorador que envuelve excepciones en respuestas JSON.
    
    Útil para APIs AJAX que necesitan manejo consistente de errores.
    """
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        try:
            return view_func(request, *args, **kwargs)
        except ValueError as e:
            return JsonResponse(
                {'error': str(e), 'status': 'error'},
                status=400
            )
        except Exception as e:
            return JsonResponse(
                {'error': 'Error interno del servidor', 'status': 'error'},
                status=500
            )
    return wrapped


def validar_metodo_pago(metodos_permitidos):
    """
    Decorador que valida el método de pago en POST.
    
    Usage:
        @validar_metodo_pago(['efectivo', 'tarjeta'])
        def procesar_venta(request):
            ...
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            metodo = request.POST.get('metodo_pago', '').lower()
            if metodo not in metodos_permitidos:
                return JsonResponse(
                    {
                        'error': f'Método de pago inválido. '
                                f'Permitidos: {", ".join(metodos_permitidos)}',
                        'status': 'error'
                    },
                    status=400
                )
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


# Decoradores de rate limit preconfigurados
def rate_limit_por_usuario(rate='10/h'):
    """
    Rate limit por usuario autenticado.
    
    Usage:
        @rate_limit_por_usuario('5/m')  # 5 requests por minuto
        def api_endpoint(request):
            ...
    """
    return ratelimit(key='user', rate=rate, method='GET')


def rate_limit_por_ip(rate='30/h'):
    """
    Rate limit por dirección IP (para usuarios no autenticados).
    """
    return ratelimit(key='ip', rate=rate, method='GET')
