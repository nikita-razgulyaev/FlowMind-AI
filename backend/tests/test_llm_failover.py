"""Встроенная облачная модель: автоматическое переключение на запасную модель другого провайдера."""
import asyncio
import json

import httpx
import pytest

from app.config import settings
from app.services import llm
from app.services.llm import LLMProvider
from app.services.platform_ai import AIUnavailable

CHAIN = json.dumps([
    {"name": "primary", "base_url": "https://primary.test/v1", "api_key": "KEY-PRIMARY", "model": "big-model"},
    {"name": "groq", "base_url": "https://groq.test/v1", "api_key": "KEY-GROQ", "model": "llama-3"},
    {"name": "together", "base_url": "https://together.test/v1", "api_key": "KEY-TOGETHER", "model": "qwen"},
])


@pytest.fixture(autouse=True)
def platform(monkeypatch):
    monkeypatch.setattr(settings, "platform_llm_providers_raw", CHAIN)
    monkeypatch.setattr(settings, "platform_llm_cooldown_seconds", 60)
    llm._health.clear()
    yield
    llm._health.clear()


class Net:
    """Поведение провайдеров по хосту: код ответа, либо исключение сети; журнал обращений."""

    def __init__(self, monkeypatch, behaviour: dict):
        self.behaviour = behaviour
        self.calls: list[tuple[str, dict]] = []
        monkeypatch.setattr(llm, "_client", lambda timeout: httpx.AsyncClient(transport=httpx.MockTransport(self.handler), timeout=timeout))

    def handler(self, request: httpx.Request):
        host = request.url.host.split(".")[0]
        body = json.loads(request.content)
        self.calls.append((host, body))
        action = self.behaviour.get(host, 200)
        if isinstance(action, Exception):
            raise action
        if action == 200:
            return httpx.Response(200, json={"choices": [{"message": {"content": f"ответ от {host}", "tool_calls": [
                {"function": {"name": "t", "arguments": "{\"a\": 1}"}}]}}]})
        if action == "garbage":
            return httpx.Response(200, json={"unexpected": True})
        return httpx.Response(action, text=f"error {action} KEY-PRIMARY")

    @property
    def hosts(self):
        return [h for h, _ in self.calls]


def ask(provider=None, **kw):
    provider = provider or LLMProvider()
    return asyncio.run(provider.generate("привет", mode="cloud", **kw)), provider


def test_one_list_first_is_main_and_invalid_entries_skipped(monkeypatch):
    assert [p["name"] for p in settings.platform_llm_providers] == ["primary", "groq", "together"]
    monkeypatch.setattr(settings, "platform_llm_providers_raw", json.dumps([
        {"name": "ok", "base_url": "https://a.test/v1", "api_key": "k", "model": "m"},
        {"name": "http", "base_url": "http://insecure.test/v1", "api_key": "k", "model": "m"},     # не https
        {"name": "nokey", "base_url": "https://b.test/v1", "model": "m"},
        "мусор", {"name": "nomodel", "base_url": "https://c.test/v1", "api_key": "k"}]))
    assert [p["name"] for p in settings.platform_llm_providers] == ["ok"]


def test_default_main_model_is_routerai_qwen_with_key_from_env(monkeypatch):
    monkeypatch.setattr(settings, "platform_llm_providers_raw", "")
    monkeypatch.delenv("ROUTERAI_API_KEY", raising=False)
    monkeypatch.setattr("app.config._dotenv", lambda: {})
    assert settings.platform_llm_providers == [] and not settings.platform_llm_configured       # без ключа основная модель не работает
    monkeypatch.setenv("ROUTERAI_API_KEY", "routerai-key")
    main = settings.platform_llm_providers[0]
    assert (main["name"], main["base_url"], main["model"], main["api_key"]) == (
        "routerai", "https://routerai.ru/api/v1", "qwen/qwen3.8-27b", "routerai-key")


def test_api_key_env_is_read_from_environment_or_dotenv_and_broken_json_falls_back(monkeypatch):
    monkeypatch.setattr(settings, "platform_llm_providers_raw", json.dumps([
        {"name": "a", "base_url": "https://a.test/v1", "model": "m", "api_key_env": "KEY_A"},
        {"name": "b", "base_url": "https://b.test/v1", "model": "m", "api_key_env": "KEY_B"}]))
    monkeypatch.setenv("KEY_A", "from-env")
    monkeypatch.delenv("KEY_B", raising=False)
    monkeypatch.setattr("app.config._dotenv", lambda: {"KEY_B": "from-dotenv"})
    assert [(p["name"], p["api_key"]) for p in settings.platform_llm_providers] == [("a", "from-env"), ("b", "from-dotenv")]
    monkeypatch.setattr(settings, "platform_llm_providers_raw", "{не json")
    monkeypatch.setenv("ROUTERAI_API_KEY", "routerai-key")
    assert [p["name"] for p in settings.platform_llm_providers] == ["routerai"]


def test_platform_unavailable_without_any_key(monkeypatch):
    monkeypatch.setattr(settings, "platform_llm_providers_raw", "")
    monkeypatch.delenv("ROUTERAI_API_KEY", raising=False)
    monkeypatch.setattr("app.config._dotenv", lambda: {})
    with pytest.raises(AIUnavailable):
        ask()


def test_provider_status_lists_models_without_keys(monkeypatch):
    llm._mark_failed("groq")
    status = llm.provider_status()
    assert [(s["name"], s["main"], s["state"]) for s in status] == [("primary", True, "ok"), ("groq", False, "cooling"), ("together", False, "ok")]
    assert status[0]["model"] == "big-model" and status[0]["host"] == "primary.test" and "KEY" not in json.dumps(status)


def test_healthy_primary_is_used_without_fallback(monkeypatch):
    net = Net(monkeypatch, {})
    text, provider = ask()
    assert text == "ответ от primary" and net.hosts == ["primary"] and provider.last_provider == "primary"


@pytest.mark.parametrize("failure", [503, 500, 429, 401, 402, 403, 404, 408, "garbage", httpx.ConnectTimeout("t"), httpx.ReadError("r")])
def test_provider_side_failures_switch_to_next_model(monkeypatch, failure):
    net = Net(monkeypatch, {"primary": failure})
    text, provider = ask()
    assert text == "ответ от groq" and net.hosts == ["primary", "groq"] and provider.last_provider == "groq"
    assert net.calls[1][1]["model"] == "llama-3"          # у запасного провайдера своя модель, а не модель основного


@pytest.mark.parametrize("failure", [400, 413, 422])
def test_request_errors_do_not_trigger_failover(monkeypatch, failure):
    net = Net(monkeypatch, {"primary": failure})
    with pytest.raises(ValueError, match=str(failure)):
        ask()
    assert net.hosts == ["primary"]                       # ошибку запроса другая модель не исправит


def test_failed_provider_is_skipped_during_cooldown_then_retried(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(llm.time, "monotonic", lambda: clock["t"])
    net = Net(monkeypatch, {"primary": 503})
    ask()
    assert net.hosts == ["primary", "groq"]
    net.calls.clear()
    ask()
    assert net.hosts == ["groq"]                          # основной «охлаждается»: не тратим время на повторный отказ
    clock["t"] += 61
    net.behaviour["primary"] = 200
    net.calls.clear()
    text, _ = ask()
    assert net.hosts == ["primary"] and text == "ответ от primary" and "primary" not in llm._health     # вернулись на основной


def test_cooldown_grows_with_repeated_failures_and_is_capped(monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(llm.time, "monotonic", lambda: clock["t"])
    for expected in (60, 120, 240, 480, 600, 600):
        llm._mark_failed("primary")
        assert llm._health["primary"]["until"] - clock["t"] == expected


def test_all_models_failing_gives_clear_error_without_leaking_keys(monkeypatch):
    net = Net(monkeypatch, {"primary": 503, "groq": 429, "together": httpx.ConnectError("down")})
    with pytest.raises(ValueError) as e:
        ask()
    message = str(e.value)
    assert net.hosts == ["primary", "groq", "together"]
    assert "не ответила ни одна модель" in message and "primary" in message and "groq" in message and "together" in message
    assert "KEY-PRIMARY" not in message and "KEY-GROQ" not in message


def test_when_everything_is_cooling_down_models_are_still_tried(monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(llm.time, "monotonic", lambda: clock["t"])
    net = Net(monkeypatch, {"primary": 503, "groq": 503, "together": 503})
    with pytest.raises(ValueError):
        ask()
    net.behaviour["together"] = 200
    net.calls.clear()
    text, _ = ask()
    assert text == "ответ от together"                    # все были отложены, но запрос всё равно прошёл


def test_daily_cap_guard_is_counted_once_per_request_not_per_attempt(monkeypatch):
    net = Net(monkeypatch, {"primary": 503, "groq": 503})
    counted = []

    async def guard():
        counted.append(1)

    text, _ = ask(LLMProvider(guard=guard))
    assert text == "ответ от together" and net.hosts == ["primary", "groq", "together"] and len(counted) == 1


def test_guard_limit_is_not_a_reason_to_failover(monkeypatch):
    net = Net(monkeypatch, {})

    async def guard():
        raise AIUnavailable("лимит исчерпан")

    with pytest.raises(AIUnavailable):
        ask(LLMProvider(guard=guard))
    assert net.calls == []


def test_users_own_connection_never_falls_back_to_platform_models(monkeypatch):
    async def public(url):
        return None

    monkeypatch.setattr(llm, "assert_public_url", public)
    net = Net(monkeypatch, {"own": 503})
    provider = LLMProvider(connections={7: {"provider": "openai_compatible", "config": {"base_url": "https://own.test/v1", "api_key": "USER-KEY"}}})
    with pytest.raises(ValueError, match="503"):
        asyncio.run(provider.generate("привет", mode="cloud", connection_id=7, model="gpt"))
    assert net.hosts == ["own"]                           # чужой ключ — чужой провайдер, платформа не подменяет его молча


def test_chat_with_tools_works_through_fallback_and_parses_arguments(monkeypatch):
    net = Net(monkeypatch, {"primary": 500})
    provider = LLMProvider()
    message = asyncio.run(provider.chat([{"role": "user", "content": "x"}], mode="cloud", tools=[{"type": "function", "function": {"name": "t"}}]))
    assert net.hosts == ["primary", "groq"] and net.calls[1][1]["tools"]
    assert message["tool_calls"][0]["function"]["arguments"] == {"a": 1}
    assert net.calls[1][1]["max_tokens"] == 1500          # ограничение расхода общего ключа действует и у запасных моделей


def test_model_chosen_in_a_step_is_tried_first_then_the_rest_of_the_chain(monkeypatch):
    net = Net(monkeypatch, {})
    text, _ = ask(model="llama-3")
    assert net.hosts == ["groq"] and text == "ответ от groq" and net.calls[0][1]["model"] == "llama-3"
    net = Net(monkeypatch, {"groq": 503})
    ask(model="llama-3")
    assert net.hosts == ["groq", "primary"]                      # выбранная недоступна: дальше обычный порядок, основная первой
    net = Net(monkeypatch, {})
    ask(model="какая-то-чужая-модель")
    assert net.hosts == ["primary"]                              # названия вне списка платформы игнорируются


def test_models_endpoint_returns_default_and_list_without_keys(user):
    r = user.get("/ai/models")
    assert r.status_code == 200
    body = r.json()
    assert body["default"] == body["models"][0]["model"] and body["models"][0]["main"] is True
    assert "key" not in json.dumps(body).lower().replace("routerai.ru", "")
