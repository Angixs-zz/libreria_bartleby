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

import requests
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
    En producción en Render (Free Tier), si se configuran credenciales de Brevo,
    se enviará automáticamente usando la API HTTP de Brevo en el puerto 443 (HTTPS)
    para evitar el bloqueo que hace Render en el puerto SMTP 587.
    """
    api_key = getattr(settings, 'EMAIL_HOST_PASSWORD', '')
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@bartleby.dev')
    email_host = getattr(settings, 'EMAIL_HOST', '')
    email_backend = getattr(settings, 'EMAIL_BACKEND', '')

    # Si detectamos Brevo y no estamos usando la consola de desarrollo, intentamos enviar vía API HTTPS (puerto 443)
    if api_key and ('xsmtpsib-' in api_key or 'smtp-relay.brevo.com' in email_host) and 'console.EmailBackend' not in email_backend:
        url = "https://api.brevo.com/v3/smtp/email"
        headers = {
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json"
        }
        payload = {
            "sender": {"email": from_email, "name": "Libreria Bartleby"},
            "to": [{"email": destinatario}],
            "subject": asunto,
            "htmlContent": html,
            "textContent": texto
        }
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=5)
            if response.status_code in [200, 201, 202]:
                return {'modo': 'brevo_api_http', 'status': 'success'}
            else:
                # Si la API da error, hacemos fallback al envío SMTP tradicional
                print(f"[Brevo API Error]: HTTP {response.status_code} - {response.text}")
        except Exception as err:
            print(f"[Brevo API Connection Error]: {err}")

    # Fallback o envío predeterminado (SMTP o Consola)
    send_mail(
        asunto,
        texto,
        from_email,
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
