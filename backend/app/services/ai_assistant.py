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
condition — условие с двумя ветками. Предпочтительно без кода: config: {"mode": "rules", "match": "all|any", "rules": [{"value": "{input}", "operator": "contains|not_contains|equals|not_equals|starts_with|ends_with|empty|not_empty|gt|gte|lt|lte|regex", "expected": "слово"}]}. Для сложных случаев: config: {"expression": "python-выражение, можно {node.field}, например {extract.score} >= 7"}. Исходящие рёбра обязаны иметь "condition": "true" или "false" — выполнится только выбранная ветка.
switch — выбор ветки по значению. config: {"value": "{classify}", "cases": "support, sales, complaint"}. Рёбра имеют "condition" = одно из значений cases или "default".
keyword_switch — классификация по ключевым словам без нейросети: подходит, когда достаточно простых слов, и не тратит лимит нейросети. config: {"value": "{input}", "rules": "доставка: где заказ, трек\nоплата: оплата, счёт", "default_label": "другое"}. Рёбра имеют "condition" = название категории из rules или default_label.
text_assemble — собрать текст из шаблона с данными других шагов без нейросети. config: {"template": "Здравствуйте! Ваш заказ {text_1}"}; результат доступен как {id_ноды}.
text_input — готовый текст (вставленный или из файла). config: {"text": "..."}; доступен как {id_ноды}.
set — именованные значения. config: {"values": "key=значение (по строке на ключ)"}; доступны как {set_1.key}.
webhook — запуск внешним HTTP-вызовом (триггер). config: {}; тело запроса: {webhook.body.поле}.
schedule — запуск по интервалу (триггер). config: {"interval_minutes": 60}.
print — вывод результата. config: {"value": "{id_ноды}"}
telegram_send — отправка сообщения в Telegram. config: {"connection_id": <id>, "chat_id": "" (пусто = ответ в чат триггера), "message": "текст"}
google_sheets_append — добавить строку в Google Таблицу. config: {"connection_id": <id>, "spreadsheet_id": "", "range": "A1", "values": "a, b, c"}
email_trigger — запуск входящим письмом (триггер). config: {"connection_id": <id подключения email>, "interval_minutes": 5}; доступны {email_from}, {email_subject}, {email_body}.
text_transform — обработка текста без нейросети. config: {"operation": "extract_email|extract_phone|extract_order|extract_date|extract_amount|extract_url|extract_regex|normalize|clean_email|first_line|truncate|lower|upper|trim|replace|capitalize|title_case|extract_number|one_line|today|now", "value": "{input}", "pattern": "", "replacement": "", "max_chars": 500}. pattern — что искать (extract_regex, replace), replacement — на что заменить (replace). Результат — строка (пустая, если не найдено).
email_send — отправить письмо. config: {"connection_id": <id подключения email>, "to": "{email_from}", "subject": "", "body": "", "as_reply": false}
google_calendar_create_event — создать событие. config: {"connection_id": <id>, "calendar_id": "primary", "summary": "", "description": "", "start_datetime": "", "end_datetime": ""}"""

ALLOWED_TYPES = {
    "manual", "telegram_trigger", "llm", "agent", "http", "condition", "print", "telegram_send",
    "google_sheets_append", "google_calendar_create_event", "switch", "set", "webhook", "schedule", "text_input",
    "email_trigger", "text_transform", "email_send", "keyword_switch", "text_assemble",
}
TRIGGERS = {"manual", "telegram_trigger", "webhook", "schedule", "email_trigger"}
MAX_HISTORY = 10
MIN_REPLY_TOKENS = 4000     # граф в JSON длинный, а модели-«рассуждатели» тратят часть лимита на размышления


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
- Значения нод доступны как {{id_ноды}} и по JSON-пути {{id_ноды.поле}}. В фигурных скобках ВСЕГДА пиши id ноды БУКВА В БУКВУ так, как он указан в поле "id" этой ноды в твоём JSON: не меняй регистр, не добавляй и не убирай символы (например, нельзя превращать id "abc1" в "abc_1" и наоборот). Ссылаться можно только на ноды, которые есть в этом же графе. Перед ответом сверь каждую {{ссылку}} в config со списком id нод. Чтобы LLM-нода вернула поля, проси её ответить JSON-объектом.
- Начинай граф с триггера (manual, telegram_trigger, webhook или schedule). id нод — короткие латинские, например "trigger_1", "agent_1".
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
    edges = [{"from_node": e.get("from_node"), "to_node": e.get("to_node"), "type": e.get("type", "next"),
              **({"condition": e["condition"]} if e.get("condition") else {})}
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
        edge = {"id": str(e.get("id") or f"edge_{i + 1}"), "from_node": src, "to_node": dst, "type": kind}
        if e.get("condition") and kind == "next":
            edge["condition"] = str(e["condition"])
        edges.append(edge)

    for e in edges:                                     # ноды-инструменты должны быть описаны для модели
        if e["type"] == "tool":
            cfg = by_id[e["to_node"]]["config"]
            cfg.setdefault("tool_name", re.sub(r"\W", "_", e["to_node"]).lower())
            cfg.setdefault("tool_description", f"Инструмент {e['to_node']}")
    _fix_references(nodes)
    _layout(nodes, edges)
    return {"nodes": nodes, "edges": edges}


_REF_RE = re.compile(r"\{([A-Za-z_][\w\-]*)((?:\.[\w\-]+|\[\d+\])*)\}")
# переменные, которые существуют помимо id нод (данные триггеров и вход)
_BUILTIN_VARS = {"input", "email_from", "email_subject", "email_body", "webhook", "telegram_message", "telegram_text", "telegram_chat_id", "telegram_username", "telegram_first_name", "email_from_name", "email_message_id", "last_result"}


def _fix_references(nodes: list[dict]) -> None:
    """Приводит {ссылки} в config к реальным id нод графа (если модель исказила регистр или подчёркивания в id)."""
    canon = {re.sub(r"[_\-]", "", n["id"]).lower(): n["id"] for n in nodes}
    ids = set(canon.values())

    def fix(text: str) -> str:
        def repl(m):
            name = m.group(1)
            if name in ids or name in _BUILTIN_VARS:
                return m.group(0)
            target = canon.get(re.sub(r"[_\-]", "", name).lower())
            return "{" + target + m.group(2) + "}" if target else m.group(0)
        return _REF_RE.sub(repl, text)

    def walk(value):
        if isinstance(value, str):
            return fix(value) if "{" in value else value
        if isinstance(value, list):
            return [walk(v) for v in value]
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        return value

    for n in nodes:
        n["config"] = walk(n["config"])


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
