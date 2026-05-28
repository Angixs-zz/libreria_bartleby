# ──────────────────────────────────────────────────────────────────────────────
# Email Service — Librería Bartleby
#
# MODO ACTUAL: Simulación por consola (desarrollo)
#   Los correos se imprimen en la terminal del servidor Django.
#   Para activar el envío real con Resend:
#     1. Descomenta la sección "INTEGRACIÓN RESEND" de abajo.
#     2. Comenta/elimina la función enviar_correo actual.
#     3. Descomenta RESEND_API_KEY y RESEND_FROM_EMAIL en el archivo .env
# ──────────────────────────────────────────────────────────────────────────────

# import requests                          # ← necesario para Resend
from django.conf import settings
from django.core.mail import send_mail


# ── INTEGRACIÓN RESEND (desactivada por ahora) ────────────────────────────────
#
# RESEND_API_URL = 'https://api.resend.com/emails'
#
# def _enviar_con_resend(destinatario, asunto, html, texto):
#     if not settings.RESEND_API_KEY:
#         raise RuntimeError('RESEND_API_KEY no está configurada.')
#     response = requests.post(
#         RESEND_API_URL,
#         headers={
#             'Authorization': f'Bearer {settings.RESEND_API_KEY}',
#             'Content-Type': 'application/json',
#         },
#         json={
#             'from': settings.RESEND_FROM_EMAIL,
#             'to': [destinatario],
#             'subject': asunto,
#             'html': html,
#             'text': texto,
#         },
#         timeout=15,
#     )
#     if response.status_code >= 400:
#         detalle = response.text.strip() or 'Respuesta inválida de Resend.'
#         raise RuntimeError(f'No se pudo enviar el correo de verificación. {detalle}')
#     return response.json()
#
# ─────────────────────────────────────────────────────────────────────────────


def enviar_correo(destinatario, asunto, html, texto):
    """
    Envía un correo usando el EMAIL_BACKEND configurado en settings.

    En desarrollo (EMAIL_BACKEND = console.EmailBackend) el correo
    se imprime en la terminal — NO se envía ningún correo real.
    """
    send_mail(
        asunto,
        texto,
        getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bartleby.dev'),
        [destinatario],
        fail_silently=False,
        html_message=html,
    )
    return {'modo': 'django_email'}


def enviar_codigo_verificacion_email(user, codigo):
    print("\n\n\n" + "*" * 60)
    print(f"      CÓDIGO DE ACTIVACIÓN: >>> {codigo} <<<")
    print(f"      (Para: {user.email})")
    print("*" * 60 + "\n\n\n")
    asunto = 'Codigo de verificacion - Libreria Bartleby'
    texto = (
        f'Hola {user.first_name or user.username},\n\n'
        f'Tu codigo de verificacion es: {codigo}\n\n'
        'Ingresa este codigo en la pantalla de verificacion para activar tu cuenta.'
    )
    html = f"""
    <div style="font-family: Georgia, serif; background: #faf9f5; padding: 32px; color: #1b1c1a;">
        <div style="max-width: 560px; margin: 0 auto; background: #ffffff; border: 1px solid #d8dccf; border-radius: 18px; padding: 32px;">
            <p style="font-size: 12px; letter-spacing: 0.24em; text-transform: uppercase; color: #6b705f; margin-bottom: 12px;">
                Libreria Bartleby
            </p>
            <h1 style="font-size: 32px; font-style: italic; color: #3e5219; margin: 0 0 16px 0;">
                Confirma tu cuenta
            </h1>
            <p style="font-family: Arial, sans-serif; font-size: 15px; line-height: 1.7; color: #404437;">
                Hola {user.first_name or user.username}, tu codigo de verificacion es:
            </p>
            <div style="margin: 28px 0; padding: 18px 20px; background: #f4f4f0; border-radius: 14px; text-align: center; font-size: 34px; letter-spacing: 0.35em; color: #3e5219; font-weight: 700;">
                {codigo}
            </div>
            <p style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.7; color: #5a5f52; margin-bottom: 0;">
                Ingresa este codigo en la pantalla de verificacion para activar tu cuenta.
            </p>
        </div>
    </div>
    """
    return enviar_correo(user.email, asunto, html, texto)


def enviar_codigo_login_email(user, codigo):
    print("\n\n\n" + "*" * 60)
    print(f"      CÓDIGO DE LOGIN: >>> {codigo} <<<")
    print(f"      (Para: {user.email})")
    print("*" * 60 + "\n\n\n")
    asunto = 'Codigo de acceso - Libreria Bartleby'
    texto = (
        f'Hola {user.first_name or user.username},\n\n'
        f'Tu codigo de acceso es: {codigo}\n\n'
        'Ingresa este codigo para iniciar sesion.'
    )
    html = f"""
    <div style="font-family: Georgia, serif; background: #faf9f5; padding: 32px; color: #1b1c1a;">
        <div style="max-width: 560px; margin: 0 auto; background: #ffffff; border: 1px solid #d8dccf; border-radius: 18px; padding: 32px;">
            <p style="font-size: 12px; letter-spacing: 0.24em; text-transform: uppercase; color: #6b705f; margin-bottom: 12px;">
                Libreria Bartleby
            </p>
            <h1 style="font-size: 32px; font-style: italic; color: #3e5219; margin: 0 0 16px 0;">
                Tu codigo de acceso
            </h1>
            <div style="margin: 28px 0; padding: 18px 20px; background: #f4f4f0; border-radius: 14px; text-align: center; font-size: 34px; letter-spacing: 0.35em; color: #3e5219; font-weight: 700;">
                {codigo}
            </div>
            <p style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.7; color: #5a5f52; margin-bottom: 0;">
                Ingresa este codigo para iniciar sesion.
            </p>
        </div>
    </div>
    """
    return enviar_correo(user.email, asunto, html, texto)


def enviar_codigo_recuperacion_email(user, codigo):
    print("\n\n\n" + "*" * 60)
    print(f"      CÓDIGO DE RECUPERACIÓN: >>> {codigo} <<<")
    print(f"      (Para: {user.email})")
    print("*" * 60 + "\n\n\n")
    asunto = 'Restablecer contrasena - Libreria Bartleby'
    texto = (
        f'Hola {user.first_name or user.username},\n\n'
        f'Tu codigo para restablecer tu contrasena es: {codigo}\n\n'
        'Ingresa este codigo en la pantalla de recuperacion para asignar una nueva contrasena.'
    )
    html = f"""
    <div style="font-family: Georgia, serif; background: #faf9f5; padding: 32px; color: #1b1c1a;">
        <div style="max-width: 560px; margin: 0 auto; background: #ffffff; border: 1px solid #d8dccf; border-radius: 18px; padding: 32px;">
            <p style="font-size: 12px; letter-spacing: 0.24em; text-transform: uppercase; color: #6b705f; margin-bottom: 12px;">
                Libreria Bartleby
            </p>
            <h1 style="font-size: 32px; font-style: italic; color: #3e5219; margin: 0 0 16px 0;">
                Recuperacion de contrasena
            </h1>
            <p style="font-family: Arial, sans-serif; font-size: 15px; line-height: 1.7; color: #404437;">
                Hola {user.first_name or user.username}, tu codigo para restablecer tu contrasena es:
            </p>
            <div style="margin: 28px 0; padding: 18px 20px; background: #f4f4f0; border-radius: 14px; text-align: center; font-size: 34px; letter-spacing: 0.35em; color: #3e5219; font-weight: 700;">
                {codigo}
            </div>
            <p style="font-family: Arial, sans-serif; font-size: 14px; line-height: 1.7; color: #5a5f52; margin-bottom: 0;">
                Ingresa este codigo en la pantalla de recuperacion para asignar una nueva contrasena. Si no solicitaste esto, puedes ignorar este correo.
            </p>
        </div>
    </div>
    """
    return enviar_correo(user.email, asunto, html, texto)
