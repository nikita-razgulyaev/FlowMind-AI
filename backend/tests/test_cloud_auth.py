import pytest

from tests.conftest import TEST_MODE, Session, register, run, simple_workflow, unique_email

pytestmark = pytest.mark.skipif(TEST_MODE != "cloud", reason="cloud only")


def test_config_and_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    cfg = client.get("/api/config").json()
    assert cfg["deployment_mode"] == "cloud" and cfg["auth_required"] is True
    assert cfg["payment_provider"] == "mock" and cfg["platform_ai_available"] is True


def test_requires_auth(client):
    assert client.get("/api/workflows/").status_code == 401
    assert client.get("/api/connections").status_code == 401
    assert client.get("/api/admin/stats").status_code == 401


def test_register_login_refresh_logout(client):
    email = unique_email()
    r = client.post("/api/auth/register", json={"email": email, "password": "password123", "name": "Никита"})
    assert r.status_code == 200
    data = r.json()
    assert data["user"]["email"] == email and data["user"]["role"] == "user"
    assert "fm_refresh" in r.cookies or client.cookies.get("fm_refresh")

    me = client.get("/api/me", headers={"Authorization": f"Bearer {data['access_token']}"}).json()
    assert me["plan"]["code"] == "free" and me["subscription"]["plan_code"] == "free"

    # дубликат email, слабый пароль, неверный пароль
    assert client.post("/api/auth/register", json={"email": email, "password": "password123"}).status_code == 409
    assert client.post("/api/auth/register", json={"email": unique_email(), "password": "short"}).status_code == 422
    assert client.post("/api/auth/login", json={"email": email, "password": "wrongpass1"}).status_code == 401

    r = client.post("/api/auth/login", json={"email": email.upper(), "password": "password123"})
    assert r.status_code == 200

    r = client.post("/api/auth/refresh")                 # refresh-cookie из предыдущего ответа
    assert r.status_code == 200 and r.json()["user"]["email"] == email

    assert client.post("/api/auth/logout").status_code == 200
    assert client.post("/api/auth/refresh").status_code == 401


def test_refresh_token_rotation(client):
    register(client)
    old_cookie = client.cookies.get("fm_refresh")
    assert client.post("/api/auth/refresh").status_code == 200
    assert client.cookies.get("fm_refresh") != old_cookie
    client.cookies.set("fm_refresh", old_cookie)          # повторное использование старого токена запрещено
    assert client.post("/api/auth/refresh").status_code == 401


def test_login_rate_limit(client):
    email = unique_email()
    register(client, email)
    codes = [client.post("/api/auth/login", json={"email": email, "password": "badbadbad1"}).status_code for _ in range(12)]
    assert 429 in codes


def test_password_reset_flow(client):
    email = unique_email()
    s = register(client, email)
    r = client.post("/api/auth/forgot-password", json={"email": email})
    link = r.json()["dev_link"]                          # DEMO_MODE=true отдаёт ссылку в ответе
    token = link.split("token=")[1]
    assert client.post("/api/auth/reset-password", json={"token": token, "password": "newpassword1"}).status_code == 200
    assert client.post("/api/auth/reset-password", json={"token": token, "password": "another1234"}).status_code == 400   # одноразовый
    assert client.post("/api/auth/login", json={"email": email, "password": "password123"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": email, "password": "newpassword1"}).status_code == 200
    # несуществующий email отвечает так же
    r = client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert r.status_code == 200 and r.json()["dev_link"] is None


def test_email_verification_required(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "require_email_verification", True)
    email = unique_email()
    r = client.post("/api/auth/register", json={"email": email, "password": "password123"})
    assert r.json()["verification_required"] is True and "access_token" not in r.json()
    assert client.post("/api/auth/login", json={"email": email, "password": "password123"}).status_code == 403
    token = r.json()["dev_link"].split("token=")[1]
    r = client.post("/api/auth/verify-email", json={"token": token})
    assert r.status_code == 200 and r.json()["user"]["email_verified"] is True
    assert client.post("/api/auth/login", json={"email": email, "password": "password123"}).status_code == 200


def test_change_password_and_delete_account(client):
    s = register(client)
    assert s.post("/me/password", json={"current_password": "wrong", "new_password": "newpassword1"}).status_code == 400
    assert s.post("/me/password", json={"current_password": "password123", "new_password": "newpassword1"}).status_code == 200
    s.post("/workflows/", json=simple_workflow())
    assert s.delete("/me", json={"password": "bad"}).status_code == 400
    assert s.delete("/me", json={"password": "newpassword1"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": s.email, "password": "newpassword1"}).status_code == 401


def test_user_settings_roundtrip(client):
    s = register(client)
    assert s.put("/me/settings", json={"defaultMode": "cloud", "evil": "x"}).json() == {"defaultMode": "cloud"}
    assert s.get("/me/settings").json() == {"defaultMode": "cloud"}


def test_blocked_user_rejected(client, admin):
    victim = register(client)
    uid = victim.get("/me").json()["user"]["id"]
    assert admin.patch(f"/admin/users/{uid}", json={"is_active": False}).status_code == 200
    assert victim.get("/me").status_code == 403
    assert client.post("/api/auth/login", json={"email": victim.email, "password": "password123"}).status_code == 403
