"""Календарь: Яндекс по CalDAV и Google через один и тот же шаг."""
import asyncio
import json

import httpx
import pytest

from app.services import caldav
from app.worker import WorkflowEngine

HOME = """<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:response><d:href>/principals/users/a@yandex.ru/</d:href>
<d:propstat><d:prop><c:calendar-home-set><d:href>/calendars/a@yandex.ru/</d:href></c:calendar-home-set></d:prop></d:propstat></d:response></d:multistatus>"""
LISTING = """<?xml version="1.0"?><d:multistatus xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
<d:response><d:href>/calendars/a@yandex.ru/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat></d:response>
<d:response><d:href>/calendars/a@yandex.ru/todos-default/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/><c:calendar/></d:resourcetype><d:displayname>Задачи</d:displayname>
<c:supported-calendar-component-set><c:comp name="VTODO"/></c:supported-calendar-component-set></d:prop></d:propstat></d:response>
<d:response><d:href>/calendars/a@yandex.ru/events-default/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/><c:calendar/></d:resourcetype><d:displayname>Мои события</d:displayname>
<c:supported-calendar-component-set><c:comp name="VEVENT"/></c:supported-calendar-component-set></d:prop></d:propstat></d:response>
<d:response><d:href>/calendars/a@yandex.ru/work/</d:href><d:propstat><d:prop><d:resourcetype><d:collection/><c:calendar/></d:resourcetype><d:displayname>Работа</d:displayname>
<c:supported-calendar-component-set><c:comp name="VEVENT"/></c:supported-calendar-component-set></d:prop></d:propstat></d:response></d:multistatus>"""


def mock(monkeypatch, put_status=201, auth_ok=True):
    log = []

    def handler(request: httpx.Request):
        log.append((request.method, request.url.path, request.headers.get("authorization", ""), request.content.decode()))
        if not auth_ok:
            return httpx.Response(401)
        if request.method == "PROPFIND" and request.url.path.startswith("/principals/"):
            return httpx.Response(207, content=HOME.encode())
        if request.method == "PROPFIND":
            return httpx.Response(207, content=LISTING.encode())
        if request.method == "PUT":
            return httpx.Response(put_status)
        return httpx.Response(404)

    monkeypatch.setattr(caldav, "_client", lambda email, password: httpx.AsyncClient(
        transport=httpx.MockTransport(handler), auth=(email, password), base_url=caldav.BASE))
    return log


def test_event_is_created_in_first_event_calendar_skipping_tasks(monkeypatch):
    log = mock(monkeypatch)
    out = asyncio.run(caldav.create_event("a@yandex.ru", "pw", "Консультация, Анна", "Первичная; приём\nс 16:00", "2026-11-12T16:00:00+03:00", "2026-11-12T17:00:00+03:00"))
    method, path, auth, body = log[-1]
    assert method == "PUT" and path.startswith("/calendars/a@yandex.ru/events-default/") and path.endswith(".ics")
    assert auth.startswith("Basic ")
    assert "DTSTART:20261112T130000Z" in body and "DTEND:20261112T140000Z" in body            # время переведено в UTC
    assert "SUMMARY:Консультация\\, Анна" in body and "DESCRIPTION:Первичная\\; приём\\nс 16:00" in body
    assert out["status"] == "created" and out["calendar"].endswith("/events-default/")


def test_calendar_can_be_chosen_by_name(monkeypatch):
    log = mock(monkeypatch)
    asyncio.run(caldav.create_event("a@yandex.ru", "pw", "X", "", "2026-11-12T16:00:00Z", "2026-11-12T17:00:00Z", calendar_name="работа"))
    assert log[-1][1].startswith("/calendars/a@yandex.ru/work/")
    with pytest.raises(caldav.CalDAVError, match="не найден"):
        asyncio.run(caldav.create_event("a@yandex.ru", "pw", "X", "", "2026-11-12T16:00:00Z", "2026-11-12T17:00:00Z", calendar_name="нет такого"))


def test_errors_are_readable(monkeypatch):
    mock(monkeypatch, auth_ok=False)
    with pytest.raises(caldav.CalDAVError, match="пароль приложения для типа «Календарь»"):
        asyncio.run(caldav.check_credentials("a@yandex.ru", "bad"))
    mock(monkeypatch, put_status=409)
    with pytest.raises(caldav.CalDAVError, match="409"):
        asyncio.run(caldav.create_event("a@yandex.ru", "pw", "X", "", "2026-11-12T16:00:00Z", "2026-11-12T17:00:00Z"))
    with pytest.raises(caldav.CalDAVError, match="часовой пояс"):
        caldav.build_ics("X", "", "2026-11-12T16:00:00", "2026-11-12T17:00:00")
    with pytest.raises(caldav.CalDAVError, match="название"):
        asyncio.run(caldav.create_event("a@yandex.ru", "pw", " ", "", "2026-11-12T16:00:00Z", "2026-11-12T17:00:00Z"))


def run_node(config, connections):
    wf = {"nodes": [{"id": "t", "type": "manual", "config": {}}, {"id": "cal", "type": "google_calendar_create_event", "config": config}],
          "edges": [{"id": "e", "from_node": "t", "to_node": "cal", "type": "next"}]}
    e = WorkflowEngine(wf, 1, connections=connections)
    asyncio.run(e.execute({"input": "Анна"}))
    return e.context["cal"]


def test_calendar_step_works_with_yandex_and_reports_missing_connection(monkeypatch):
    mock(monkeypatch)
    cfg = {"connection_id": 1, "summary": "Запись: {input}", "start_datetime": "2026-11-12T16:00:00+03:00", "end_datetime": "2026-11-12T17:00:00+03:00"}
    out = run_node(cfg, {1: {"provider": "yandex_calendar", "config": {"email": "a@yandex.ru", "password": "pw"}}})
    assert out["status"] == "created"
    assert run_node({**cfg, "connection_id": None}, {}).startswith("Calendar Error")
    assert run_node(cfg, {1: {"provider": "google_calendar", "config": {"needs_reauth": True}}}).endswith("войдите заново")


def test_calendar_step_works_with_google(monkeypatch):
    seen = {}

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers=None, json=None, **k):
            seen.update(url=url, auth=headers["Authorization"], body=json)
            return httpx.Response(200, json={"id": "ev1"})

    import app.worker as worker
    monkeypatch.setattr(worker.httpx, "AsyncClient", FakeClient)
    cfg = {"connection_id": 2, "summary": "Встреча {input}", "start_datetime": "2026-11-12T16:00:00+03:00", "end_datetime": "2026-11-12T17:00:00+03:00"}
    out = run_node(cfg, {2: {"provider": "google_calendar", "config": {"access_token": "gt"}}})
    assert out["status_code"] == 200 and seen["auth"] == "Bearer gt" and seen["body"]["summary"] == "Встреча Анна"
    assert seen["url"].endswith("/calendars/primary/events")


def test_yandex_calendar_connection_is_verified_and_secret_hidden(user, monkeypatch):
    checked = []

    async def ok(email, password):
        checked.append((email, password))

    monkeypatch.setattr(caldav, "check_credentials", ok)
    body = {"category": "tool", "provider": "yandex_calendar", "name": "Мой календарь", "config": {"email": "a@yandex.ru", "password": "app-secret"}}
    r = user.post("/connections", json=body)
    assert r.status_code == 200 and r.json()["account"] == "a@yandex.ru" and "app-secret" not in json.dumps(r.json())
    assert checked == [("a@yandex.ru", "app-secret")]

    async def fail(email, password):
        raise caldav.CalDAVError("не принял логин")

    monkeypatch.setattr(caldav, "check_credentials", fail)
    r = user.post("/connections", json=body)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "calendar_login_failed"
    assert user.post("/connections", json={**body, "config": {"email": "нет", "password": "x"}}).json()["detail"]["code"] == "bad_calendar"
