# app/services/email_service.py
#
# Envío de emails vía Resend (https://resend.com) -- API HTTP simple,
# sin lidiar con SMTP. Tier gratis: 3000 emails/mes, 100/día, alcanza
# de sobra para recuperación de contraseña en un proyecto de este tamaño.

import httpx
from app.config.config import RESEND_API_KEY, EMAIL_FROM, FRONTEND_URL
from app.core.logging_config import get_logger

logger = get_logger(__name__)


async def send_password_reset_email(to_email: str, raw_token: str) -> bool:
    reset_link = f"{FRONTEND_URL}/reset-password?token={raw_token}"

    html_body = f"""
    <p>Recibimos un pedido para restablecer tu contraseña.</p>
    <p><a href="{reset_link}">Hacé click acá para elegir una nueva contraseña</a></p>
    <p>Este link vence en 30 minutos. Si no pediste esto, podés ignorar
    este email -- tu contraseña no va a cambiar.</p>
    """

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
                json={
                    "from": EMAIL_FROM,
                    "to": [to_email],
                    "subject": "Restablecer tu contraseña",
                    "html": html_body,
                },
            )
        return response.status_code < 300

    except (httpx.TimeoutException, httpx.HTTPError) as e:
        logger.warning(f"Error enviando email de reseteo: {e!r}")
        return False