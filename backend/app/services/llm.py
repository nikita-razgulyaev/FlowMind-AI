"""Единый слой доступа к LLM: Ollama (локально), OpenAI-совместимые API, Hugging Face router, ключ платформы."""
from __future__ import annotations

import json
import logging
import time
from typing import Awaitable, Callable, Optional

import httpx

from ..config import settings
from .platform_ai import AIUnavailable
from .ssrf import assert_public_url

DEFAULT_OPENAI_URL = "https://api.openai.com/v1"
HF_ROUTER_URL = "https://router.huggingface.co/v1"        # подключение пользователя «Hugging Face»
HF_DEFAULT_MODEL = "openai/gpt-oss-120b:groq"
log = logging.getLogger(__name__)

# Ответы провайдера, при которых имеет смысл переключиться на запасную модель: проблема на его стороне (ключ, оплата, лимит, сбой),
# а не в запросе. 400/413/422 означают ошибку самого запроса: другая модель её не исправит.
FAILOVER_STATUSES = {401, 402, 403, 404, 408, 409, 425, 429}

# Состояние провайдеров платформы: имя -> {"fails": подряд сбоев, "until": время (monotonic), до которого его пропускаем}
_health: dict[str, dict] = {}


def _client(timeout: httpx.Timeout) -> httpx.AsyncClient:    # точка подмены в тестах
    return httpx.AsyncClient(timeout=timeout)


class ProviderHTTPError(ValueError):
    def __init__(self, status: int, text: str):
        super().__init__(f"LLM API вернул {status}: {text[:200]}")
        self.status = status


def _should_failover(exc: Exception) -> bool:
    if isinstance(exc, ProviderHTTPError):
        return exc.status in FAILOVER_STATUSES or exc.status >= 500
    # сеть, таймауты, нечитаемый или неполный ответ провайдера
    return isinstance(exc, (httpx.TransportError, json.JSONDecodeError, KeyError, IndexError, TypeError))


def _mark_failed(name: str) -> None:
    entry = _health.setdefault(name, {"fails": 0, "until": 0.0})
    entry["fails"] += 1
    delay = min(settings.platform_llm_cooldown_seconds * (2 ** (entry["fails"] - 1)), 600)
    entry["until"] = time.monotonic() + delay


def _mark_ok(name: str) -> None:
    _health.pop(name, None)


def _order(providers: list[dict]) -> list[dict]:
    """Сначала провайдеры без «охлаждения» в заданном порядке, затем отложенные (на случай, если все сбоят)."""
    now = time.monotonic()
    ready = [p for p in providers if _health.get(p["name"], {}).get("until", 0.0) <= now]
    cooling = [p for p in providers if p not in ready]
    return ready + cooling


class LLMProvider:
    def __init__(self, connections: Optional[dict] = None, guard: Optional[Callable[[], Awaitable[None]]] = None):
        # connection_id -> {"provider": ..., "config": {...расшифрованный...}}
        self.connections = connections or {}
        self.guard = guard
        self.last_provider: Optional[str] = None     # какая модель платформы ответила последней (для журнала и диагностики)

    # ───────── выбор бэкенда ─────────
    def _resolve(self, mode: Optional[str], connection_id, model: Optional[str]):
        mode = mode or settings.default_llm_mode
        if mode == "local":
            if settings.is_cloud:
                raise ValueError("Локальные модели (Ollama) недоступны в облачной версии — выберите режим Cloud.")
            return {"kind": "ollama", "model": model or settings.ollama_model}
        if mode != "cloud":
            raise ValueError(f"Неизвестный режим LLM: {mode}")

        if connection_id:
            conn = self.connections.get(connection_id)
            if not conn:
                raise ValueError("Подключение не найдено (возможно, оно удалено)")
            cfg = conn["config"]
            provider = conn["provider"]
            if provider == "huggingface":
                return {"kind": "openai", "base_url": HF_ROUTER_URL, "api_key": cfg.get("api_key"),
                        "model": model or HF_DEFAULT_MODEL, "platform": False}
            if provider == "openai_compatible":
                if not model:
                    raise ValueError("Не указана модель для OpenAI-совместимого подключения")
                return {"kind": "openai", "base_url": cfg.get("base_url") or DEFAULT_OPENAI_URL,
                        "api_key": cfg.get("api_key"), "model": model, "platform": False}
            raise ValueError(f"Подключение '{provider}' не поддерживает генерацию текста")

        if not settings.platform_llm_configured:
            raise AIUnavailable("AI платформы не настроен. Подключите свой API-ключ в разделе «Подключения».")
        return {"kind": "platform", "model": model}

    # ───────── публичный API ─────────
    async def generate(self, prompt: str, model: Optional[str] = None, temperature: float = 0.7,
                       mode: Optional[str] = None, connection_id=None) -> str:
        target = self._resolve(mode, connection_id, model)
        if target["kind"] == "ollama":
            async with httpx.AsyncClient(timeout=120.0) as client:
                r = await client.post(f"{settings.ollama_url}/api/generate", json={
                    "model": target["model"], "prompt": prompt, "stream": False,
                    "options": {"temperature": temperature}})
                self._raise_for_status(r)
                return r.json().get("response", "")
        messages = [{"role": "user", "content": prompt}]
        if target["kind"] == "platform":
            message = await self._platform_chat(messages, None, temperature, target.get("model"))
        else:
            message = await self._openai_chat(target, messages, None, temperature)
        return message.get("content") or ""

    async def chat(self, messages: list, model: Optional[str] = None, tools: Optional[list] = None,
                   temperature: float = 0.7, mode: Optional[str] = None, connection_id=None,
                   json_mode: bool = False) -> dict:
        target = self._resolve(mode, connection_id, model)
        if target["kind"] == "ollama":
            payload = {"model": target["model"], "messages": messages, "stream": False,
                       "options": {"temperature": temperature}}
            if tools:
                payload["tools"] = tools
            if json_mode:
                payload["format"] = "json"
            async with httpx.AsyncClient(timeout=180.0) as client:
                r = await client.post(f"{settings.ollama_url}/api/chat", json=payload)
                self._raise_for_status(r)
                return r.json().get("message", {})
        if target["kind"] == "platform":
            return await self._platform_chat(messages, tools, temperature, target.get("model"))
        return await self._openai_chat(target, messages, tools, temperature)

    # ───────── реализация ─────────
    @staticmethod
    def _raise_for_status(r: httpx.Response) -> None:
        if r.status_code >= 400:
            raise ProviderHTTPError(r.status_code, r.text)

    async def _platform_chat(self, messages: list, tools: Optional[list], temperature: float, preferred: Optional[str] = None) -> dict:
        """Встроенная модель платформы: основная, а при сбое на её стороне автоматически запасные от других провайдеров."""
        if self.guard:
            await self.guard()                  # суточный лимит считается один раз на запрос, а не на каждую попытку
        configured = settings.platform_llm_providers
        chain_main = configured[0]
        if preferred:                           # выбранная в шаге модель платформы пробуется первой; названия вне списка игнорируются
            configured = sorted(configured, key=lambda p: p["model"] != preferred)
        chain = _order(configured)
        failures = []
        for index, provider in enumerate(chain):
            last = index == len(chain) - 1
            timeout = httpx.Timeout(120.0 if last else 60.0, connect=10.0)     # зависшего провайдера не ждём дольше минуты, если есть запасной
            try:
                message = await self._post_chat(provider["base_url"], provider["api_key"], provider["model"], messages, tools,
                                                temperature, provider.get("max_tokens", 1500), timeout)
            except Exception as e:
                if not _should_failover(e):
                    raise
                _mark_failed(provider["name"])
                reason = self._short(e, [p["api_key"] for p in chain])
                failures.append(f"{provider['name']}: {reason}")
                log.warning("Модель платформы «%s» не ответила (%s), переключаемся на следующую", provider["name"], reason)
                continue
            _mark_ok(provider["name"])
            if provider is not chain_main:
                log.warning("Запрос выполнен запасной моделью платформы «%s»", provider["name"])
            self.last_provider = provider["name"]
            return message
        raise ValueError("AI платформы временно недоступен: не ответила ни одна модель (" + "; ".join(failures) + "). Повторите позже или подключите свой API-ключ.")

    @staticmethod
    def _short(exc: Exception, secrets: list[str]) -> str:
        text = str(exc) or exc.__class__.__name__
        for secret in secrets:
            text = text.replace(secret, "***")
        return text[:120]

    async def _openai_chat(self, target: dict, messages: list, tools: Optional[list], temperature: float) -> dict:
        """Запрос через подключение пользователя (его ключ и его провайдер): запасных моделей платформы здесь нет намеренно."""
        api_key = target.get("api_key")
        if not api_key:
            raise ValueError("У подключения не задан API Key")
        base_url = target["base_url"].rstrip("/")
        await assert_public_url(base_url)
        return await self._post_chat(base_url, api_key, target["model"], messages, tools, temperature, None, httpx.Timeout(120.0, connect=10.0))

    async def _post_chat(self, base_url: str, api_key: str, model: str, messages: list, tools: Optional[list], temperature: float,
                         max_tokens: Optional[int], timeout: httpx.Timeout) -> dict:
        payload = {"model": model, "messages": messages, "temperature": temperature}
        if tools:
            payload["tools"] = tools
        if max_tokens:
            payload["max_tokens"] = max_tokens        # ограничиваем расход общего ключа платформы
        async with _client(timeout) as client:
            r = await client.post(f"{base_url.rstrip('/')}/chat/completions", headers={"Authorization": f"Bearer {api_key}"}, json=payload)
            self._raise_for_status(r)
            data = r.json()
        message = data["choices"][0]["message"]
        for call in message.get("tool_calls") or []:
            fn = call.get("function", {})
            args = fn.get("arguments")
            if isinstance(args, str):
                try:
                    fn["arguments"] = json.loads(args)
                except json.JSONDecodeError:
                    fn["arguments"] = {}
        return message


def provider_status() -> list[dict]:
    """Модели встроенного AI по порядку со статусом (для админ-панели): ok или cooling (временно отложена после сбоя). Ключи не отдаются."""
    now = time.monotonic()
    return [{"name": p["name"], "model": p["model"], "host": p["base_url"].split("//", 1)[-1].split("/", 1)[0],
             "main": i == 0, "state": "cooling" if _health.get(p["name"], {}).get("until", 0.0) > now else "ok"}
            for i, p in enumerate(settings.platform_llm_providers)]
