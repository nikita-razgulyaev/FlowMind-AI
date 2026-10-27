"""AI-ассистент редактора: по текстовому описанию собирает/изменяет граф воркфлоу."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any, Optional

from ..config import settings

NODE_CATALOG = """\
manual — ручной запуск (триггер). config: {}
telegram_trigger — запуск входящим сообщением в Telegram (триггер). config: {"connection_id": <id подключения telegram_bot>, "allowed_chat_ids": "", "only_commands": false}
llm — один запрос к языковой модели. config: {"mode": "cloud|local", "model": "", "prompt": "текст, можно {input} и {id_другой_ноды}", "temperature": 0.7, "connection_id": null}
agent — AI-агент с инструментами. config: {"mode": "cloud|local", "model": "", "system_prompt": "...", "prompt": "{input}", "max_iterations": 5, "temperature": 0.3, "connection_id": null}
http — HTTP-запрос. config: {"method": "GET|POST", "url": "https://... (можно {input})"}
condition — условие. config: {"expression": "python-выражение, например len(input) > 5"}
print — вывод результата. config: {"value": "{id_ноды}"}
telegram_send — отправка сообщения в Telegram. config: {"connection_id": <id>, "chat_id": "" (пусто = ответ в чат триггера), "message": "текст"}
google_sheets_append — добавить строку в Google Таблицу. config: {"connection_id": <id>, "spreadsheet_id": "", "range": "A1", "values": "a, b, c"}
google_calendar_create_event — создать событие. config: {"connection_id": <id>, "calendar_id": "primary", "summary": "", "description": "", "start_datetime": "", "end_datetime": ""}"""

ALLOWED_TYPES = {
    "manual", "telegram_trigger", "llm", "agent", "http", "condition", "print", "telegram_send",
    "google_sheets_append", "google_calendar_create_event",
}
TRIGGERS = {"manual", "telegram_trigger"}
MAX_HISTORY = 10


def build_system_prompt(current: Optional[dict], connections: list[dict]) -> str:
    default_mode = settings.default_llm_mode
    conn_lines = "\n".join(f'- id={c["id"]}, тип={c["provider"]}, название="{c["name"]}"' for c in connections) or "(нет подключений)"
    graph = json.dumps(_compact(current), ensure_ascii=False) if current and current.get("nodes") else "(холст пуст)"
    return f"""Ты — ассистент визуального конструктора AI-воркфлоу FlowMind. Помогаешь собирать граф из нод и отвечаешь на вопросы по работе сервиса. Отвечай по-русски, кратко.

Доступные типы нод:
{NODE_CATALOG}

Правила графа:
- Рёбра типа "next" задают порядок выполнения слева направо: {{"id":"e1","from_node":"a","to_node":"b","type":"next"}}.
- У агента (agent) инструменты подключаются рёбрами типа "tool" ОТ агента К ноде-инструменту. Ноде-инструменту добавь в config: "tool_name" (латиница, snake_case), "tool_description" и "tool_parameters" (JSON Schema: {{"type":"object","properties":{{...}},"required":[...]}}).
- Ноды-инструменты не соединяй рёбрами "next".
- Начинай граф с триггера (manual или telegram_trigger). id нод — короткие латинские, например "trigger_1", "agent_1".
- Для AI-нод (llm, agent) ставь "mode": "{default_mode}", поле "model" оставляй пустой строкой.
- connection_id указывай ТОЛЬКО из списка подключений пользователя; если подходящего нет — null и сообщи об этом в reply.

Подключения пользователя:
{conn_lines}

Текущий граф на холсте:
{graph}

Формат ответа — СТРОГО один JSON-объект без пояснений вне JSON:
{{"reply": "короткий ответ пользователю", "workflow": null}}
или, если нужно создать/изменить граф:
{{"reply": "что сделано", "workflow": {{"nodes": [{{"id": "...", "type": "...", "config": {{...}}}}], "edges": [...]}}}}
В "workflow" всегда возвращай ПОЛНЫЙ итоговый граф (включая прежние ноды, которые остаются), а не только изменения. Если пользователь просто задаёт вопрос — "workflow": null."""


def _compact(wf: Optional[dict]) -> dict:
    def trim(v):
        return v[:200] if isinstance(v, str) else v

    nodes = [{"id": n.get("id"), "type": n.get("type"),
              "config": {k: trim(v) for k, v in (n.get("config") or {}).items() if k != "tool_parameters"}}
             for n in (wf or {}).get("nodes", [])][:settings.max_nodes_per_workflow]
    edges = [{"from_node": e.get("from_node"), "to_node": e.get("to_node"), "type": e.get("type", "next")}
             for e in (wf or {}).get("edges", [])]
    return {"nodes": nodes, "edges": edges}


def extract_json(text: str) -> Optional[dict]:
    """Достаёт JSON-объект из ответа модели (даже если вокруг есть текст или ```-блок)."""
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.S)
    for candidate in (cleaned, cleaned[cleaned.find("{"): cleaned.rfind("}") + 1] if "{" in cleaned else ""):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def sanitize_workflow(raw: Any, existing: Optional[dict], connections: list[dict]) -> Optional[dict]:
    """Проверяет граф от модели: типы, id, рёбра, подключения; расставляет позиции."""
    if not isinstance(raw, dict) or not isinstance(raw.get("nodes"), list):
        return None
    conn_ids = {c["id"] for c in connections}
    old_positions = {n.get("id"): n.get("position") for n in (existing or {}).get("nodes", []) if n.get("position")}
    default_mode = settings.default_llm_mode

    nodes, seen = [], set()
    for i, n in enumerate(raw["nodes"][:settings.max_nodes_per_workflow]):
        if not isinstance(n, dict) or n.get("type") not in ALLOWED_TYPES:
            continue
        node_id = str(n.get("id") or f"{n['type']}_{i + 1}")
        node_id = re.sub(r"[^A-Za-z0-9_\-]", "_", node_id)[:60]
        if node_id in seen:
            node_id = f"{node_id}_{i + 1}"
        seen.add(node_id)
        config = n.get("config") if isinstance(n.get("config"), dict) else {}
        if config.get("connection_id") not in conn_ids:
            config.pop("connection_id", None)
        if n["type"] in ("llm", "agent"):
            config.setdefault("mode", default_mode)
            if config["mode"] not in ("local", "cloud"):
                config["mode"] = default_mode
            config.setdefault("model", settings.ollama_model if config["mode"] == "local" else "")
            config.setdefault("temperature", 0.3 if n["type"] == "agent" else 0.7)
        if n["type"] == "agent":
            config.setdefault("system_prompt", "Ты — полезный ассистент.")
            config.setdefault("prompt", "{input}")
            config.setdefault("max_iterations", 5)
        nodes.append({"id": node_id, "type": n["type"], "config": config, "position": old_positions.get(node_id)})
    if not nodes:
        return None

    ids = {n["id"] for n in nodes}
    by_id = {n["id"]: n for n in nodes}
    edges, pairs = [], set()
    for i, e in enumerate(raw.get("edges") or []):
        if not isinstance(e, dict):
            continue
        src, dst = e.get("from_node"), e.get("to_node")
        if src not in ids or dst not in ids or src == dst:
            continue
        if e.get("type") == "tool" and by_id[src]["type"] != "agent":
            continue                                    # инструменты бывают только у агента
        if by_id[dst]["type"] in TRIGGERS:
            continue                                    # в триггер ничего не входит
        kind = "tool" if e.get("type") == "tool" else "next"
        if (src, dst, kind) in pairs:
            continue
        pairs.add((src, dst, kind))
        edges.append({"id": str(e.get("id") or f"edge_{i + 1}"), "from_node": src, "to_node": dst, "type": kind})

    for e in edges:                                     # ноды-инструменты должны быть описаны для модели
        if e["type"] == "tool":
            cfg = by_id[e["to_node"]]["config"]
            cfg.setdefault("tool_name", re.sub(r"\W", "_", e["to_node"]).lower())
            cfg.setdefault("tool_description", f"Инструмент {e['to_node']}")
    _layout(nodes, edges)
    return {"nodes": nodes, "edges": edges}


def _layout(nodes: list[dict], edges: list[dict]) -> None:
    """Слева направо по глубине; ноды-инструменты — под своим агентом."""
    by_id = {n["id"]: n for n in nodes}
    tool_parent = {e["to_node"]: e["from_node"] for e in edges if e["type"] == "tool"}
    nxt = defaultdict(list)
    indeg = {n["id"]: 0 for n in nodes}
    for e in edges:
        if e["type"] == "next" and e["to_node"] not in tool_parent:
            nxt[e["from_node"]].append(e["to_node"])
            indeg[e["to_node"]] += 1
    depth = {nid: 0 for nid, d in indeg.items() if d == 0 and nid not in tool_parent}
    queue = list(depth)
    while queue:
        cur = queue.pop(0)
        for child in nxt[cur]:
            if depth.get(child, -1) < depth[cur] + 1:
                depth[child] = depth[cur] + 1
                queue.append(child)
    rows: dict[int, int] = defaultdict(int)
    for n in nodes:
        if n["id"] in tool_parent:
            continue
        d = depth.get(n["id"], 0)
        if not n.get("position"):
            n["position"] = {"x": 80 + d * 300, "y": 80 + rows[d] * 200}
        rows[d] += 1
    slot: dict[str, int] = defaultdict(int)
    for n in nodes:
        parent = tool_parent.get(n["id"])
        if parent and not n.get("position"):
            base = by_id[parent].get("position") or {"x": 80, "y": 80}
            n["position"] = {"x": base["x"] + slot[parent] * 300 - 150, "y": base["y"] + 220}
            slot[parent] += 1
        elif not n.get("position"):
            n["position"] = {"x": 80, "y": 80}
