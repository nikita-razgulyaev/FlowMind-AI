"""OAuth-вход (Google, Яндекс), обновление токенов, почта и Telegram."""
import asyncio
import hashlib
import base64
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models import Connection
from app.security import decrypt_config
from app.services import oauth
from app.worker import WorkflowEngine


@pytest.fixture(autouse=True)
def keys(monkeypatch):
    for name in ("google_client_id", "google_client_secret", "yandex_client_id", "yandex_client_secret"):
        monkeypatch.setattr(settings, name, f"test-{name}")


def mock_net(monkeypatch, module, handler):
    monkeypatch.setattr(module, "_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def start(user, provider, name="Тест", **extra):
    r = user.get("/oauth/start", params={"provider": provider, "name": name, **extra})
    assert r.status_code == 200, r.text
    url = urlparse(r.json()["auth_url"])
    return url, {k: v[0] for k, v in parse_qs(url.query).items()}


def callback(user, family, **params):
    return user.client.get(f"/api/oauth/{family}/callback", params=params, follow_redirects=False)


def stored(provider):
    async def go():
        async with async_session() as db:
            rows = (await db.execute(select(Connection).where(Connection.provider == provider).order_by(Connection.id.desc()))).scalars().all()
            return rows[0]
    return asyncio.run(go())


def latest(user, provider):
    """Последнее подключение сервиса (в локальном режиме все тесты работают под одним пользователем)."""
    rows = [c for c in user.get("/connections").json() if c["provider"] == provider]
    return max(rows, key=lambda c: c["id"])


def google_handler(scope="https://mail.google.com/", email="anna@gmail.com", calls=None):
    def handler(request: httpx.Request):
        if calls is not None:
            calls.append((request.method, str(request.url), request.content.decode()))
        if request.url.path == "/token":
            return httpx.Response(200, json={"access_token": "ya29.access", "refresh_token": "1//refresh", "expires_in": 3600, "scope": scope})
        if "userinfo" in request.url.path:
            return httpx.Response(200, json={"email": email})
        return httpx.Response(200, json={})
    return handler


def test_status_and_unconfigured(user, monkeypatch):
    assert user.get("/oauth/status").json()["yandex"] is True
    monkeypatch.setattr(settings, "yandex_client_id", "")
    assert user.get("/oauth/status").json()["yandex"] is False
    r = user.get("/oauth/start", params={"provider": "yandex_mail", "name": "x"})
    assert r.status_code == 500 and r.json()["detail"]["code"] == "oauth_not_configured"
    assert user.get("/oauth/start", params={"provider": "bogus", "name": "x"}).status_code == 400


def test_pkce_is_s256_and_verifier_never_in_url(user):
    url, q = start(user, "google_gmail")
    assert q["code_challenge_method"] == "S256" and q["scope"] == "https://mail.google.com/"
    assert q["access_type"] == "offline" and q["include_granted_scopes"] == "false"
    state = oauth.read_state(q["state"])
    verifier = oauth.pkce_verifier(state["r"])
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    assert q["code_challenge"] == expected and verifier not in url.query
    with pytest.raises(Exception):
        oauth.read_state(q["state"][:-2] + "00")           # подделка state отвергается


def test_google_flow_creates_encrypted_connection_with_account(user, monkeypatch):
    calls = []
    mock_net(monkeypatch, oauth, google_handler(calls=calls))
    _, q = start(user, "google_gmail", "Рабочая почта")
    r = callback(user, "google", code="abc", state=q["state"])
    assert r.status_code in (302, 307) and "connected=1" in r.headers["location"] and "provider=google_gmail" in r.headers["location"]
    token_call = next(c for c in calls if c[1].endswith("/token"))
    assert "code_verifier=" in token_call[2]                # PKCE-проверка передана при обмене кода

    row = stored("google_gmail")
    assert str(row.config["access_token"]).startswith("enc:") or row.config["access_token"] != "ya29.access"
    assert decrypt_config(row.config)["access_token"] == "ya29.access"
    dto = latest(user, "google_gmail")
    assert dto["oauth"] is True and dto["account"] == "anna@gmail.com" and dto["needs_reauth"] is False
    assert "ya29.access" not in json.dumps(dto)


def test_denied_and_missing_scope_and_foreign_state(user, monkeypatch):
    _, q = start(user, "google_sheets")
    r = callback(user, "google", error="access_denied", state=q["state"])
    assert "error=oauth_denied" in r.headers["location"]

    revoked = []
    def handler(request):
        if request.url.path == "/revoke":
            revoked.append(request.content.decode())
        return google_handler(scope="openid email")(request)   # пользователь снял галочку с нужного права
    mock_net(monkeypatch, oauth, handler)
    _, q = start(user, "google_sheets")
    r = callback(user, "google", code="abc", state=q["state"])
    assert "error=missing_scope" in r.headers["location"] and revoked              # доступ сразу отзывается

    _, q = start(user, "google_sheets")
    assert "error=oauth_failed" in callback(user, "yandex", code="x", state=q["state"]).headers["location"]   # state от другого сервиса


def test_reconnect_updates_same_connection_and_clears_flag(user, monkeypatch):
    mock_net(monkeypatch, oauth, google_handler(scope="https://www.googleapis.com/auth/spreadsheets"))
    _, q = start(user, "google_sheets", "Таблицы")
    callback(user, "google", code="a", state=q["state"])
    conn = latest(user, "google_sheets")
    before = len([c for c in user.get("/connections").json() if c["provider"] == "google_sheets"])
    _, q2 = start(user, "google_sheets", "Таблицы", reconnect_id=conn["id"])
    callback(user, "google", code="b", state=q2["state"])
    after = [c for c in user.get("/connections").json() if c["provider"] == "google_sheets"]
    assert len(after) == before and latest(user, "google_sheets")["id"] == conn["id"]
    assert user.get("/oauth/start", params={"provider": "google_sheets", "name": "x", "reconnect_id": 999999}).status_code == 404


def test_yandex_mail_connection_has_email(user, monkeypatch):
    def handler(request):
        if request.url.path == "/token":
            assert request.headers["authorization"].startswith("Basic ")       # ключи приложения передаются в заголовке
            return httpx.Response(200, json={"access_token": "y0_a", "refresh_token": "1:r", "expires_in": 3600})
        if "login.yandex.ru" in request.url.host:
            return httpx.Response(200, json={"default_email": "shop@yandex.ru", "login": "shop"})
        return httpx.Response(404)
    mock_net(monkeypatch, oauth, handler)
    _, q = start(user, "yandex_mail", "Яндекс")
    assert q["scope"] == "mail:imap_ro mail:smtp login:email"
    r = callback(user, "yandex", code="c", state=q["state"])
    assert "connected=1" in r.headers["location"]
    assert decrypt_config(stored("yandex_mail").config)["email"] == "shop@yandex.ru"


def test_refresh_success_and_revoked_marks_needs_reauth(user, monkeypatch):
    from app.services.google import refresh_if_needed
    mock_net(monkeypatch, oauth, google_handler(scope="https://www.googleapis.com/auth/spreadsheets"))
    _, q = start(user, "google_sheets")
    callback(user, "google", code="a", state=q["state"])

    async def expire_and_refresh(handler):
        mock_net(monkeypatch, oauth, handler)
        async with async_session() as db:
            conn = (await db.execute(select(Connection).where(Connection.provider == "google_sheets").order_by(Connection.id.desc()))).scalars().first()
            conn.config = {**conn.config, "obtained_at": "2000-01-01T00:00:00+00:00"}
            db.add(conn); await db.commit()
            cfg = await refresh_if_needed(conn, db)
            return cfg, dict(conn.config)

    cfg, saved = asyncio.run(expire_and_refresh(lambda r: httpx.Response(200, json={"access_token": "ya29.new", "expires_in": 3600})))
    assert cfg["access_token"] == "ya29.new" and saved["needs_reauth"] is False and saved["access_token"] != "ya29.new"

    cfg, saved = asyncio.run(expire_and_refresh(lambda r: httpx.Response(400, json={"error": "invalid_grant"})))
    assert saved["needs_reauth"] is True
    assert latest(user, "google_sheets")["needs_reauth"] is True

    cfg, saved = asyncio.run(expire_and_refresh(lambda r: httpx.Response(200, json={"access_token": "ya29.again", "expires_in": 3600})))
    assert saved["needs_reauth"] is False                                           # после успешного обновления флаг снимается

    mock_net(monkeypatch, oauth, lambda r: httpx.Response(503))                     # сбой сервиса — не повод просить войти заново
    cfg, saved = asyncio.run(expire_and_refresh(lambda r: httpx.Response(503)))
    assert saved["needs_reauth"] is False


def test_delete_oauth_connection_revokes_google_access(user, monkeypatch):
    revoked = []
    def handler(request):
        if request.url.path == "/revoke":
            revoked.append(request.content.decode())
        return google_handler(scope="https://www.googleapis.com/auth/calendar")(request)
    mock_net(monkeypatch, oauth, handler)
    _, q = start(user, "google_calendar")
    callback(user, "google", code="a", state=q["state"])
    conn = latest(user, "google_calendar")
    assert user.delete(f"/connections/{conn['id']}").status_code == 200
    assert revoked and "token=" in revoked[0]


def test_oauth_provider_cannot_be_created_by_password(user):
    r = user.post("/connections", json={"category": "tool", "provider": "google_gmail", "name": "x", "config": {"access_token": "stolen"}})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "use_oauth"


def engine(nodes, connections=None):
    wf = {"nodes": [{"id": "t", "type": "manual", "config": {}}] + nodes,
          "edges": [{"id": f"e{i}", "from_node": a["id"], "to_node": b["id"], "type": "next"} for i, (a, b) in enumerate(zip([{"id": "t"}] + nodes, nodes))]}
    e = WorkflowEngine(wf, 1, connections=connections or {})
    asyncio.run(e.execute({"input": "Новый ролик"}))
    return e


def test_oauth_mail_connection_works_for_email_nodes(monkeypatch):
    from app.services import email_service
    s = email_service.resolve_settings({"_provider": "google_gmail", "email": "a@gmail.com", "access_token": "tok"})
    assert s["imap_host"] == "imap.gmail.com" and s["smtp_port"] == 465 and s["access_token"] == "tok"
    assert email_service._xoauth2(s) == "user=a@gmail.com\x01auth=Bearer tok\x01\x01"
    sent = []

    async def fake_send(cfg, to, subject, body, reply=""):
        sent.append(cfg["_provider"])

    monkeypatch.setattr(email_service, "send_message", fake_send)
    e = engine([{"id": "m", "type": "email_send", "config": {"connection_id": 5, "to": "x@y.ru", "subject": "s", "body": "b"}}],
               {5: {"provider": "yandex_mail", "config": {"email": "me@yandex.ru", "access_token": "t"}}})
    assert e.context["m"]["status"] == "sent" and sent == ["yandex_mail"]


# ───────── Telegram ─────────

def test_telegram_connection_is_verified_and_shows_bot_name(user, fake_net):
    r = user.post("/connections", json={"category": "tool", "provider": "telegram_bot", "name": "Бот",
                                        "config": {"bot_token": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ"}})
    assert r.status_code == 200 and r.json()["account"] == "@test_bot"
    assert any(m == "getMe" for m, _ in fake_net.telegram_calls)
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ" not in json.dumps(r.json())


def test_telegram_send_photo_to_channel_and_readable_errors(monkeypatch):
    sent = []

    def handler(request):
        method = request.url.path.rsplit("/", 1)[-1]
        body = json.loads(request.content)
        sent.append((method, body))
        if body.get("chat_id") == "@nochannel":
            return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})
        return httpx.Response(200, json={"ok": True, "result": {}})

    factory = httpx.AsyncClient          # уже подменённый общей фикстурой клиент, принимает свой transport
    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: factory(transport=httpx.MockTransport(handler)))
    conns = {1: {"provider": "telegram_bot", "config": {"bot_token": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ"}}}

    e = engine([{"id": "s", "type": "telegram_send", "config": {"connection_id": 1, "chat_id": "https://t.me/myblog", "message": "Пост: {input}", "photo_url": "https://img.test/a.png"}}], conns)
    assert sent[0][0] == "sendPhoto" and sent[0][1]["chat_id"] == "@myblog" and sent[0][1]["caption"] == "Пост: Новый ролик"

    sent.clear()
    long_text = "я" * 1500
    engine([{"id": "s", "type": "telegram_send", "config": {"connection_id": 1, "chat_id": "@blog", "message": long_text, "photo_url": "https://img.test/a.png"}}], conns)
    assert [m for m, _ in sent] == ["sendPhoto", "sendMessage"] and sent[0][1]["caption"] == ""     # длинный текст — отдельным сообщением

    e = engine([{"id": "s", "type": "telegram_send", "config": {"connection_id": 1, "chat_id": "@nochannel", "message": "x"}}], conns)
    assert e.context["s"].startswith("Telegram Error") and "добавьте бота администратором" in e.context["s"]


def test_email_leads_template_extracts_and_replies(monkeypatch):
    from app.services import email_service
    import copy
    from app.templates import TEMPLATES
    sent = []

    async def fake_send(cfg, to, subject, body, reply=""):
        sent.append((to, subject, reply))

    monkeypatch.setattr(email_service, "send_message", fake_send)
    tpl = copy.deepcopy(TEMPLATES["email_leads"])
    for n in tpl["nodes"]:
        if n["type"] in ("email_send", "email_trigger"):
            n["config"]["connection_id"] = 9
    e = WorkflowEngine({"nodes": tpl["nodes"], "edges": tpl["edges"]}, 1, connections={9: {"provider": "google_gmail", "config": {"email": "me@gmail.com", "access_token": "t"}}})
    asyncio.run(e.execute({"input": "Где заказ 5521? Тел 8 900 111-22-33", "email": {"from": "c@x.ru", "subject": "Заказ", "body": "", "message_id": "<1@x>"}}))
    assert e.context["phone"] == "+79001112233" and e.context["order_number"] == "5521"
    assert sent == [("c@x.ru", "Re: Заказ", "<1@x>")]
