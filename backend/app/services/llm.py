"""Единый слой доступа к LLM: Ollama (локально), OpenAI-совместимые API, Hugging Face router, ключ платформы."""
from __future__ import annotations

import json
from typing import Awaitable, Callable, Optional

import httpx

from ..config import settings
from .platform_ai import AIUnavailable
from .ssrf import assert_public_url

DEFAULT_OPENAI_URL = "https://api.openai.com/v1"


class LLMProvider:
    def __init__(self, connections: Optional[dict] = None, guard: Optional[Callable[[], Awaitable[None]]] = None):
        # connection_id -> {"provider": ..., "config": {...расшифрованный...}}
        self.connections = connections or {}
        self.guard = guard

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
                return {"kind": "openai", "base_url": settings.platform_llm_base_url, "api_key": cfg.get("api_key"),
                        "model": model or settings.platform_llm_model, "platform": False}
            if provider == "openai_compatible":
                if not model:
                    raise ValueError("Не указана модель для OpenAI-совместимого подключения")
                return {"kind": "openai", "base_url": cfg.get("base_url") or DEFAULT_OPENAI_URL,
                        "api_key": cfg.get("api_key"), "model": model, "platform": False}
            raise ValueError(f"Подключение '{provider}' не поддерживает генерацию текста")

        if not settings.platform_llm_api_key:
            raise AIUnavailable("AI платформы не настроен. Подключите свой API-ключ в разделе «Подключения».")
        return {"kind": "openai", "base_url": settings.platform_llm_base_url, "api_key": settings.platform_llm_api_key,
                "model": settings.platform_llm_model, "platform": True}

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
        message = await self._openai_chat(target, [{"role": "user", "content": prompt}], None, temperature)
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
        return await self._openai_chat(target, messages, tools, temperature)

    # ───────── реализация ─────────
    @staticmethod
    def _raise_for_status(r: httpx.Response) -> None:
        if r.status_code >= 400:
            raise ValueError(f"LLM API вернул {r.status_code}: {r.text[:200]}")

    async def _openai_chat(self, target: dict, messages: list, tools: Optional[list], temperature: float) -> dict:
        api_key = target.get("api_key")
        if not api_key:
            raise ValueError("У подключения не задан API Key")
        base_url = target["base_url"].rstrip("/")
        if not target.get("platform"):
            await assert_public_url(base_url)
        elif self.guard:
            await self.guard()

        payload = {"model": target["model"], "messages": messages, "temperature": temperature}
        if tools:
            payload["tools"] = tools
        if target.get("platform"):
            payload["max_tokens"] = 1500       # ограничиваем расход общего ключа

        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(f"{base_url}/chat/completions",
                                  headers={"Authorization": f"Bearer {api_key}"}, json=payload)
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
