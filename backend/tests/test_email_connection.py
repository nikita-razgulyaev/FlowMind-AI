"""Почтовое подключение: пресеты, проверка входа, маскировка пароля."""
from app.services import email_service


def test_email_presets_and_connection_flow(user, monkeypatch):
    presets = {p["id"] for p in user.get("/connections/email-presets").json()}
    assert {"gmail", "mailru", "yandex", "outlook", "custom"} <= presets

    checked = []

    async def ok(cfg):
        checked.append(email_service.resolve_settings(cfg))

    monkeypatch.setattr(email_service, "check_credentials", ok)
    body = {"category": "tool", "provider": "email", "name": "Почта магазина",
            "config": {"preset": "mailru", "email": "shop@mail.ru", "password": "app-password"}}
    r = user.post("/connections", json=body)
    assert r.status_code == 200, r.text
    assert checked[0]["imap_host"] == "imap.mail.ru" and checked[0]["smtp_port"] == 465
    assert "app-password" not in r.text                     # пароль в ответе замаскирован

    async def fail(cfg):
        raise OSError("auth failed")

    monkeypatch.setattr(email_service, "check_credentials", fail)
    r = user.post("/connections", json=body)
    assert r.status_code == 400 and r.json()["detail"]["code"] == "email_login_failed"

    bad = dict(body, config={"preset": "mailru", "email": "not-an-email", "password": "x"})
    assert user.post("/connections", json=bad).json()["detail"]["code"] == "bad_email"
