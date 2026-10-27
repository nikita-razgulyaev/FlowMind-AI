"""Отправка писем. Без SMTP письмо просто пишется в лог (удобно для локальной разработки и демо)."""
import asyncio
import logging
import smtplib
from email.message import EmailMessage

from ..config import settings

log = logging.getLogger("flowmind.mail")


def _send_sync(to: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


async def send_email(to: str, subject: str, body: str) -> None:
    if not settings.smtp_host:
        log.warning("[EMAIL → %s] %s\n%s", to, subject, body)
        return
    try:
        await asyncio.to_thread(_send_sync, to, subject, body)
    except Exception:           # письмо не должно ронять запрос
        log.exception("Не удалось отправить письмо на %s", to)
