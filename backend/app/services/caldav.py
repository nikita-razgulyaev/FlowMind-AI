"""Яндекс Календарь по CalDAV: вход по логину и паролю приложения (пароль нужно создать в Яндекс ID для типа «Календарь»)."""
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib.parse import quote, urljoin

import httpx

BASE = "https://caldav.yandex.ru"
NS = {"d": "DAV:", "c": "urn:ietf:params:xml:ns:caldav"}

PROPFIND_HOME = '<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><c:calendar-home-set/></d:prop></d:propfind>'
PROPFIND_CALENDARS = ('<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop>'
                      '<d:resourcetype/><d:displayname/><c:supported-calendar-component-set/></d:prop></d:propfind>')


class CalDAVError(Exception):
    """Ошибка с понятным пользователю текстом."""


def _client(email: str, password: str) -> httpx.AsyncClient:      # точка подмены в тестах
    return httpx.AsyncClient(auth=(email, password), timeout=30.0, follow_redirects=False)


def _check(response: httpx.Response, what: str) -> None:
    if response.status_code == 401:
        raise CalDAVError("Яндекс Календарь не принял логин или пароль. Нужен пароль приложения для типа «Календарь»; новый пароль может начать действовать через 2–3 часа")
    if response.status_code >= 400:
        raise CalDAVError(f"Яндекс Календарь: {what} не удалось (код {response.status_code})")


async def _propfind(client: httpx.AsyncClient, url: str, body: str, depth: str) -> ET.Element:
    r = await client.request("PROPFIND", url, content=body, headers={"Depth": depth, "Content-Type": "application/xml; charset=utf-8"})
    _check(r, "получить список календарей")
    try:
        return ET.fromstring(r.content)
    except ET.ParseError:
        raise CalDAVError("Яндекс Календарь вернул непонятный ответ")


async def discover_calendar(client: httpx.AsyncClient, email: str, calendar_name: str = "") -> str:
    """Находит адрес календаря для событий: по названию, иначе первый календарь, поддерживающий события."""
    principal = f"{BASE}/principals/users/{quote(email)}/"
    root = await _propfind(client, principal, PROPFIND_HOME, "0")
    href = root.find(".//c:calendar-home-set/d:href", NS)
    home = urljoin(BASE, href.text.strip()) if href is not None and href.text else f"{BASE}/calendars/{quote(email)}/"
    listing = await _propfind(client, home, PROPFIND_CALENDARS, "1")
    found = []
    for response in listing.findall("d:response", NS):
        if response.find(".//d:resourcetype/c:calendar", NS) is None:
            continue
        components = [c.get("name") for c in response.findall(".//c:supported-calendar-component-set/c:comp", NS)]
        if components and "VEVENT" not in components:
            continue
        link = response.find("d:href", NS)
        name = response.find(".//d:displayname", NS)
        if link is not None and link.text:
            found.append((urljoin(BASE, link.text.strip()), (name.text or "") if name is not None else ""))
    if not found:
        raise CalDAVError("В Яндекс Календаре не найден календарь для событий")
    if calendar_name:
        for url, name in found:
            if name.strip().lower() == calendar_name.strip().lower():
                return url
        raise CalDAVError(f"Календарь «{calendar_name}» не найден. Оставьте поле пустым, чтобы использовать основной")
    return found[0][0]


async def check_credentials(email: str, password: str) -> None:
    async with _client(email, password) as client:
        await discover_calendar(client, email)


def _ics_time(value: str) -> str:
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise CalDAVError(f"Не удалось разобрать дату «{value}». Нужен формат 2026-11-12T16:00:00+03:00")
    if moment.tzinfo is None:
        raise CalDAVError(f"В дате «{value}» не указан часовой пояс. Пример: 2026-11-12T16:00:00+03:00")
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def build_ics(summary: str, description: str, start: str, end: str, uid: str | None = None) -> tuple[str, str]:
    uid = uid or f"{uuid.uuid4()}@flowmind"
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//FlowMind//RU", "BEGIN:VEVENT", f"UID:{uid}",
             f"DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}", f"DTSTART:{_ics_time(start)}", f"DTEND:{_ics_time(end)}",
             f"SUMMARY:{_escape(summary)}"]
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return uid, "\r\n".join(lines) + "\r\n"


async def create_event(email: str, password: str, summary: str, description: str, start: str, end: str, calendar_name: str = "") -> dict:
    if not summary.strip():
        raise CalDAVError("Не заполнено название события")
    uid, ics = build_ics(summary, description, start, end)
    async with _client(email, password) as client:
        calendar = await discover_calendar(client, email, calendar_name)
        r = await client.put(f"{calendar.rstrip('/')}/{quote(uid)}.ics", content=ics.encode(),
                             headers={"Content-Type": "text/calendar; charset=utf-8", "If-None-Match": "*"})
        _check(r, "создать событие")
    return {"status": "created", "uid": uid, "calendar": calendar}
