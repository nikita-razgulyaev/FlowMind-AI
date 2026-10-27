"""Общие фикстуры. Режим выбирается переменной TEST_MODE (cloud | local) — тесты запускаются отдельными прогонами."""
import json
import os
import tempfile
import uuid
from pathlib import Path

TEST_MODE = os.environ.get("TEST_MODE", "cloud")
_tmp = tempfile.mkdtemp(prefix="flowmind-test-")
os.environ.setdefault("DATABASE_URL", f"sqlite+aiosqlite:///{_tmp}/test.db")
os.environ["DEPLOYMENT_MODE"] = TEST_MODE
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only-0123456789"
os.environ["ADMIN_EMAIL"] = "boss@example.com"
os.environ["DEMO_MODE"] = "true"
os.environ["PLATFORM_LLM_API_KEY"] = "test-platform-key"
os.environ["PAYMENT_PROVIDER"] = "mock"
os.environ["PUBLIC_BASE_URL"] = "https://flowmind.test" if TEST_MODE == "cloud" else ""
os.environ.pop("AUTH_ENABLED", None)

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import ratelimit  # noqa: E402

REAL_ASYNC_CLIENT = httpx.AsyncClient


class FakeNet:
    """Перехватывает все исходящие HTTP-запросы приложения и отвечает заготовками."""

    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.llm_queue: list = []                # очередь ответов LLM (строка content или dict message)
        self.telegram_calls: list[tuple[str, dict]] = []
        self.ollama_chat_payloads: list[dict] = []
        self.tg_updates: list[dict] = []
        self.yookassa_payments: dict[str, dict] = {}
        self.yookassa_status = "pending"

    def reset(self):
        self.__init__()

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        host, path = request.url.host, request.url.path
        body = json.loads(request.content) if request.content and request.headers.get("content-type", "").startswith("application/json") else {}
        if host == "router.huggingface.co" or path.endswith("/chat/completions"):
            item = self.llm_queue.pop(0) if self.llm_queue else "Привет из мока"
            message = item if isinstance(item, dict) else {"role": "assistant", "content": item}
            return httpx.Response(200, json={"choices": [{"message": message}]})
        if request.url.port == 11434:                  # Ollama
            if path.endswith("/api/generate"):
                return httpx.Response(200, json={"response": f"ollama:{body.get('model')}:{body.get('prompt')}"})
            item = self.llm_queue.pop(0) if self.llm_queue else "ollama-chat"
            message = item if isinstance(item, dict) else {"role": "assistant", "content": item}
            self.ollama_chat_payloads.append(body)
            return httpx.Response(200, json={"message": message})
        if host == "api.telegram.org":
            method = path.rsplit("/", 1)[-1]
            self.telegram_calls.append((method, body))
            if method == "getUpdates" and body.get("offset") != -1 and self.tg_updates:
                return httpx.Response(200, json={"ok": True, "result": [self.tg_updates.pop(0)]})
            return httpx.Response(200, json={"ok": True, "result": []})
        if host == "api.yookassa.ru":
            if request.method == "POST":
                pid = f"yk_{uuid.uuid4().hex[:10]}"
                payment = {"id": pid, "status": "pending", "amount": body.get("amount"),
                           "confirmation": {"type": "redirect", "confirmation_url": f"https://yookassa.test/pay/{pid}"}
                           if "confirmation" in body else None,
                           "payment_method": {"id": "pm_saved_1", "saved": True, "type": "bank_card",
                                              "card": {"last4": "4477", "card_type": "MasterCard"}},
                           "request": body, "idempotence": request.headers.get("Idempotence-Key")}
                if "payment_method_id" in body:         # автоплатёж
                    payment["status"] = "succeeded" if self.yookassa_status != "canceled" else "canceled"
                    payment["cancellation_details"] = {"reason": "insufficient_funds"}
                self.yookassa_payments[pid] = payment
                return httpx.Response(200, json=payment)
            pid = path.rsplit("/", 1)[-1]
            payment = dict(self.yookassa_payments.get(pid, {"id": pid}))
            payment["status"] = self.yookassa_status if payment.get("status") == "pending" else payment.get("status")
            return httpx.Response(200, json=payment)
        return httpx.Response(200, text="ok", headers={"content-type": "text/plain"})


NET = FakeNet()


@pytest.fixture(autouse=True)
def fake_net(monkeypatch):
    NET.reset()

    async def fake_resolve(host, port):          # в песочнице нет DNS: публичные имена → публичный IP
        return ["127.0.0.1"] if host in ("localhost", "internal.test") else ["93.184.216.34"]

    from app.services import ssrf
    monkeypatch.setattr(ssrf, "_resolve", fake_resolve)

    def factory(*args, **kwargs):
        kwargs.setdefault("transport", httpx.MockTransport(NET.handler))
        return REAL_ASYNC_CLIENT(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)
    for limiter in (ratelimit.login_limiter, ratelimit.register_limiter, ratelimit.email_limiter,
                    ratelimit.ai_chat_limiter, ratelimit.telegram_chat_limiter):
        limiter._hits.clear()
    return NET


@pytest.fixture(scope="session")
def client():
    with TestClient(app, base_url="https://testserver" if TEST_MODE == "cloud" else "http://testserver") as c:
        yield c


_counter = {"n": 0}


def unique_email() -> str:
    _counter["n"] += 1
    return f"user{_counter['n']}-{uuid.uuid4().hex[:6]}@example.com"


class Session:
    """Пользователь с access-токеном для тестов."""

    def __init__(self, client: TestClient, email: str, token: str):
        self.client, self.email, self.token = client, email, token

    @property
    def headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, url, **kw): return self.client.get(f"/api{url}", headers=self.headers, **kw)
    def post(self, url, **kw): return self.client.post(f"/api{url}", headers=self.headers, **kw)
    def put(self, url, **kw): return self.client.put(f"/api{url}", headers=self.headers, **kw)
    def patch(self, url, **kw): return self.client.patch(f"/api{url}", headers=self.headers, **kw)
    def delete(self, url, **kw): return self.client.request("DELETE", f"/api{url}", headers=self.headers, **kw)


def register(client: TestClient, email: str = None, password: str = "password123") -> Session:
    email = email or unique_email()
    r = client.post("/api/auth/register", json={"email": email, "password": password, "name": "Тест"})
    assert r.status_code == 200, r.text
    return Session(client, email, r.json()["access_token"])


@pytest.fixture
def user(client):
    return register(client)


@pytest.fixture
def admin(client):
    email = "boss@example.com"
    r = client.post("/api/auth/login", json={"email": email, "password": "password123"})
    if r.status_code != 200:
        r = client.post("/api/auth/register", json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    return Session(client, email, r.json()["access_token"])


def simple_workflow(name="wf", extra_nodes=None, extra_edges=None, active=True):
    nodes = [{"id": "t", "type": "manual", "config": {}},
             {"id": "p", "type": "print", "config": {"value": "Ответ: {input}"}}] + (extra_nodes or [])
    edges = [{"id": "e1", "from_node": "t", "to_node": "p", "type": "next"}] + (extra_edges or [])
    return {"name": name, "description": "", "nodes": nodes, "edges": edges, "is_active": active}


def ai_workflow(name="ai", mode="cloud"):
    return {"name": name, "description": "", "is_active": True,
            "nodes": [{"id": "t", "type": "manual", "config": {}},
                      {"id": "l", "type": "llm", "config": {"mode": mode, "model": "", "prompt": "Скажи: {input}", "temperature": 0.1}}],
            "edges": [{"id": "e1", "from_node": "t", "to_node": "l", "type": "next"}]}


def run(client: TestClient, coro_fn):
    """Выполняет async-функцию в event loop приложения (для прямых проверок БД)."""
    return client.portal.call(coro_fn)
