"""Почта: пресеты популярных сервисов, отправка (SMTP), чтение новых писем (IMAP), проверка доступа."""
import asyncio
import imaplib
import smtplib
import ssl
from email import message_from_bytes
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime

from .textops import clean_email_text

PRESETS = {
    "gmail": {"label": "Gmail", "imap_host": "imap.gmail.com", "imap_port": 993, "smtp_host": "smtp.gmail.com", "smtp_port": 465,
              "help": "Включите двухэтапную аутентификацию в аккаунте Google и создайте «пароль приложения» — обычный пароль не подойдёт."},
    "mailru": {"label": "Почта Mail.ru", "imap_host": "imap.mail.ru", "imap_port": 993, "smtp_host": "smtp.mail.ru", "smtp_port": 465,
               "help": "В настройках Mail.ru откройте «Пароли для внешних приложений» и создайте пароль для почтовых программ."},
    "yandex": {"label": "Яндекс Почта", "imap_host": "imap.yandex.ru", "imap_port": 993, "smtp_host": "smtp.yandex.ru", "smtp_port": 465,
               "help": "В настройках Яндекс Почты включите доступ по IMAP и создайте пароль приложения."},
    "outlook": {"label": "Outlook / Microsoft 365", "imap_host": "outlook.office365.com", "imap_port": 993, "smtp_host": "smtp.office365.com", "smtp_port": 587,
                "help": "Для рабочих аккаунтов Microsoft 365 администратор должен разрешить доступ по IMAP/SMTP."},
    "custom": {"label": "Другая почта (корпоративная)", "imap_host": "", "imap_port": 993, "smtp_host": "", "smtp_port": 465,
               "help": "Адреса серверов и порты можно узнать у вашего хостинга или IT-специалиста."},
}


# Серверы почтовых сервисов, подключённых через OAuth (вход по XOAUTH2, пароль не нужен)
OAUTH_HOSTS = {
    "google_gmail": {"imap_host": "imap.gmail.com", "imap_port": 993, "smtp_host": "smtp.gmail.com", "smtp_port": 465},
    "yandex_mail": {"imap_host": "imap.yandex.ru", "imap_port": 993, "smtp_host": "smtp.yandex.ru", "smtp_port": 465},
    "mailru_mail": {"imap_host": "imap.mail.ru", "imap_port": 993, "smtp_host": "smtp.mail.ru", "smtp_port": 465},
}


def with_provider(connection: dict) -> dict:
    """Конфиг подключения вместе с типом: по нему выбирается способ входа (пароль приложения или OAuth)."""
    return {**connection["config"], "_provider": connection["provider"]}


def _xoauth2(s: dict) -> str:
    return f"user={s['email']}\x01auth=Bearer {s['access_token']}\x01\x01"


def resolve_settings(cfg: dict) -> dict:
    """Объединяет пресет и ручные значения (ручные важнее). Для OAuth-почты берутся фиксированные серверы и токен вместо пароля."""
    oauth_hosts = OAUTH_HOSTS.get(cfg.get("_provider", ""))
    if oauth_hosts:
        return {"email": str(cfg.get("email", "")).strip(), "password": "", "access_token": cfg.get("access_token", ""), **oauth_hosts}
    preset = PRESETS.get(cfg.get("preset") or "custom", PRESETS["custom"])
    return {
        "email": str(cfg.get("email", "")).strip(),
        "password": cfg.get("password", ""),
        "imap_host": (cfg.get("imap_host") or preset["imap_host"]).strip(),
        "imap_port": int(cfg.get("imap_port") or preset["imap_port"]),
        "smtp_host": (cfg.get("smtp_host") or preset["smtp_host"]).strip(),
        "smtp_port": int(cfg.get("smtp_port") or preset["smtp_port"]),
    }


def _send_sync(s: dict, to: str, subject: str, body: str, reply_to_id: str = "") -> None:
    msg = EmailMessage()
    msg["From"] = s["email"]
    msg["To"] = to
    msg["Subject"] = subject
    if reply_to_id:
        msg["In-Reply-To"] = reply_to_id
        msg["References"] = reply_to_id
    msg.set_content(body)
    context = ssl.create_default_context()

    def login(smtp):
        if s.get("access_token"):
            smtp.auth("XOAUTH2", lambda challenge=None: _xoauth2(s), initial_response_ok=True)
        else:
            smtp.login(s["email"], s["password"])

    if s["smtp_port"] == 465:
        with smtplib.SMTP_SSL(s["smtp_host"], s["smtp_port"], timeout=20, context=context) as smtp:
            login(smtp)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(s["smtp_host"], s["smtp_port"], timeout=20) as smtp:
            smtp.starttls(context=context)
            login(smtp)
            smtp.send_message(msg)


async def send_message(cfg: dict, to: str, subject: str, body: str, reply_to_id: str = "") -> None:
    await asyncio.to_thread(_send_sync, resolve_settings(cfg), to, subject, body, reply_to_id)


def _decode(value) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return str(value or "")


def _body_text(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(part.get("Content-Disposition", "")):
                payload = part.get_payload(decode=True) or b""
                return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        return ""
    payload = msg.get_payload(decode=True) or b""
    return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")


def _imap_connect(s: dict) -> imaplib.IMAP4_SSL:
    box = imaplib.IMAP4_SSL(s["imap_host"], s["imap_port"], timeout=20)
    if s.get("access_token"):
        box.authenticate("XOAUTH2", lambda _: _xoauth2(s).encode())
    else:
        box.login(s["email"], s["password"])
    return box


def _check_sync(s: dict) -> None:
    box = _imap_connect(s)
    try:
        box.select("INBOX", readonly=True)
    finally:
        box.logout()


async def check_credentials(cfg: dict) -> None:
    """Бросает исключение, если войти в ящик не удалось."""
    await asyncio.to_thread(_check_sync, resolve_settings(cfg))


def _fetch_new_sync(s: dict, last_uid: int | None, limit: int) -> tuple[int, list[dict]]:
    """Письма с UID больше last_uid. Первый вызов (last_uid=None) только запоминает позицию и ничего не возвращает."""
    box = _imap_connect(s)
    try:
        box.select("INBOX", readonly=True)
        status, data = box.uid("search", None, "ALL")
        uids = [int(x) for x in (data[0] or b"").split()] if status == "OK" else []
        top = max(uids) if uids else 0
        if last_uid is None:
            return top, []
        fresh = [u for u in uids if u > last_uid][:limit]
        result = []
        for uid in fresh:
            status, parts = box.uid("fetch", str(uid), "(RFC822)")
            if status != "OK" or not parts or not isinstance(parts[0], tuple):
                continue
            msg = message_from_bytes(parts[0][1])
            name, address = parseaddr(_decode(msg.get("From")))
            try:
                date = parsedate_to_datetime(msg.get("Date")).isoformat()
            except Exception:
                date = ""
            body = _body_text(msg)
            result.append({
                "uid": uid, "from": address, "from_name": name, "subject": _decode(msg.get("Subject")),
                "body": clean_email_text(body)[:20000], "date": date, "message_id": msg.get("Message-ID", ""),
            })
        new_top = max(fresh) if fresh else last_uid
        return max(new_top, last_uid), result
    finally:
        box.logout()


async def fetch_new(cfg: dict, last_uid: int | None, limit: int = 5) -> tuple[int, list[dict]]:
    return await asyncio.to_thread(_fetch_new_sync, resolve_settings(cfg), last_uid, limit)
