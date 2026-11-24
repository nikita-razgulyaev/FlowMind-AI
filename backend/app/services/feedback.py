"""Обращения пользователей: отсев спама, копия в Formspree, выгрузка в CSV.

Принцип отсева: ничего не выбрасываем. Подозрительное обращение сохраняется со статусом «spam» и причиной,
в Formspree не пересылается, а администратор видит его в отдельной вкладке и может вернуть одним нажатием.
Ложное срабатывание поэтому стоит одного клика, а не потерянного отзыва.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from typing import Optional

import httpx

from ..config import settings
from ..database import async_session
from ..models import Feedback

log = logging.getLogger("flowmind.feedback")

TYPES = ("question", "bug", "idea", "payment", "other")
TYPE_LABELS = {"question": "Вопрос", "bug": "Ошибка", "idea": "Идея", "payment": "Оплата и тарифы", "other": "Другое"}
STATUSES = ("new", "in_progress", "done", "spam")

# Боты отправляют форму за единицы–сотни миллисекунд. Порог намеренно низкий: человек со скопированным заранее текстом
# тоже может уложиться в полторы секунды, а ложное срабатывание хуже пропущенного бота.
MIN_FILL_MS = 1000
# Трёх ссылок в обычном обращении (страница ошибки, скриншот, документация) бывает достаточно; спам почти всегда набит ссылками.
MAX_LINKS = 3
_LINK_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+")


def detect_spam(honeypot: str, elapsed_ms: Optional[float], message: str) -> str:
    """Возвращает причину («honeypot», «too_fast», «links») или пустую строку, если обращение нормальное.

    - honeypot: скрытое поле, которое видят и заполняют только боты. Пробелы не считаются заполнением.
    - too_fast: время от открытия формы до отправки; если клиент его не прислал (например, API-запрос) — проверка пропускается.
    - links: больше MAX_LINKS ссылок в тексте.
    """
    if (honeypot or "").strip():
        return "honeypot"
    if elapsed_ms is not None and elapsed_ms < MIN_FILL_MS:
        return "too_fast"
    if len(_LINK_RE.findall(message or "")) > MAX_LINKS:
        return "links"
    return ""


def clean_page(page: Optional[str]) -> str:
    """Только путь страницы: query и #hash могут содержать токены (например, сброса пароля) — их не сохраняем."""
    page = (page or "").split("?")[0].split("#")[0].strip()
    return page[:200] if page.startswith("/") else ""


def _payload(fb: Feedback) -> dict:
    label = TYPE_LABELS.get(fb.type, fb.type)
    snippet = " ".join((fb.message or "").split())[:60]
    payload = {
        "_subject": f"FlowMind AI · {label}: {snippet}",
        "type": label,
        "message": fb.message,
        "page": fb.page or "—",
        "account": f"user #{fb.user_id} · тариф {fb.plan or '—'}" if fb.user_id else "гость",
        "feedback_id": fb.id,
    }
    if fb.email:
        payload["email"] = fb.email          # Formspree использует это поле как адрес для ответа
    if fb.name:
        payload["name"] = fb.name
    if settings.app_url:
        payload["admin_link"] = f"{settings.app_url}/admin?tab=feedback"
    return payload


async def forward_to_formspree(feedback_id: int) -> str:
    """Отправляет копию обращения в Formspree и записывает результат в forward_status. Никогда не бросает исключений."""
    try:
        async with async_session() as db:
            fb = await db.get(Feedback, feedback_id)
            if fb is None:
                return "off"
            endpoint = settings.formspree_endpoint
            if not endpoint:
                fb.forward_status = "off"
                await db.commit()
                return "off"

            headers = {"Accept": "application/json", "User-Agent": "FlowMind-AI-feedback/1.0"}
            if settings.app_url.startswith("http"):
                headers["Origin"] = settings.app_url        # Formspree умеет ограничивать форму доменом сайта
                headers["Referer"] = settings.app_url + "/"
            status = "failed"
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                    resp = await client.post(endpoint, json=_payload(fb), headers=headers)
                try:
                    body = resp.json()
                except ValueError:
                    body = {}
                ok = resp.status_code < 300 and isinstance(body, dict) and body.get("ok", True) is not False and not body.get("errors")
                status = "sent" if ok else "failed"
                if not ok:
                    log.warning("Formspree не принял обращение #%s: HTTP %s %s", feedback_id, resp.status_code, resp.text[:200])
            except httpx.HTTPError as exc:
                log.warning("Formspree недоступен для обращения #%s: %s", feedback_id, exc)
            fb.forward_status = status
            await db.commit()
            return status
    except Exception:                                   # фоновая задача не должна падать молча и ронять что-либо ещё
        log.exception("Не удалось переслать обращение #%s", feedback_id)
        return "failed"


# ───────────── CSV ─────────────

_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def csv_cell(value) -> str:
    """Защита от CSV-инъекций: ячейка, начинающаяся с «=», «+», «-», «@», в Excel исполняется как формула."""
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(_FORMULA_START) else text


CSV_COLUMNS = ("id", "created_at", "status", "type", "name", "email", "plan", "page", "message", "admin_note", "spam_reason", "forward_status")


def feedback_csv(rows: list[Feedback]) -> bytes:
    """UTF-8 с BOM — иначе Excel показывает кириллицу кракозябрами."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for fb in rows:
        writer.writerow([csv_cell(fb.created_at.isoformat(timespec="seconds") if col == "created_at" and fb.created_at else getattr(fb, col, ""))
                         for col in CSV_COLUMNS])
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")
