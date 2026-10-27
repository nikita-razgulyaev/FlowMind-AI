"""Движок выполнения workflow: топологический порядок, agent-loop с tool calling, обработчики нод."""
import asyncio
import json
from datetime import datetime, timezone

import httpx

from .config import settings
from .services.llm import LLMProvider
from .services.safe_eval import safe_eval
from .services.ssrf import assert_public_url

MAX_HTTP_REDIRECTS = 3


class WorkflowEngine:
    def __init__(self, workflow, execution_id, connections: dict = None, llm_guard=None):
        self.workflow = workflow
        self.execution_id = execution_id
        self.context = {}
        self.logs = []
        # connection_id -> {"provider": ..., "config": {...расшифрованный...}}
        self.connections = connections or {}
        self.llm = LLMProvider(connections=self.connections, guard=llm_guard)
        self.nodes_by_id = {n["id"]: n for n in workflow.get("nodes", [])}
        self._current_agent_id = None

    def _get_connection(self, connection_id):
        if connection_id is None:
            return None
        return self.connections.get(connection_id)

    def _topological_order(self):
        """Порядок выполнения определяется связями графа, а не порядком нод в массиве."""
        nodes = self.workflow["nodes"]
        node_ids = [n["id"] for n in nodes]
        order_index = {nid: i for i, nid in enumerate(node_ids)}

        next_edges = [e for e in self.workflow.get("edges", []) if e.get("type") != "tool"]
        incoming = {nid: 0 for nid in node_ids}
        outgoing = {nid: [] for nid in node_ids}
        for e in next_edges:
            if e.get("from_node") in outgoing and e.get("to_node") in incoming:
                outgoing[e["from_node"]].append(e["to_node"])
                incoming[e["to_node"]] += 1

        queue = sorted([nid for nid in node_ids if incoming[nid] == 0], key=lambda x: order_index[x])
        visited = []
        while queue:
            queue.sort(key=lambda x: order_index[x])
            current = queue.pop(0)
            if current in visited:
                continue
            visited.append(current)
            for nxt in outgoing[current]:
                incoming[nxt] -= 1
                if incoming[nxt] <= 0 and nxt not in visited:
                    queue.append(nxt)

        for nid in node_ids:
            if nid not in visited:
                visited.append(nid)
        return [self.nodes_by_id[nid] for nid in visited]

    async def execute(self, trigger_data=None):
        trigger_data = trigger_data or {}
        if isinstance(trigger_data, dict) and "input" in trigger_data:
            self.context["input"] = trigger_data["input"]
        else:
            self.context["input"] = trigger_data

        tg = trigger_data.get("telegram") if isinstance(trigger_data, dict) else None
        if isinstance(tg, dict):
            self.context["telegram_chat_id"] = tg.get("chat_id", "")
            self.context["telegram_text"] = tg.get("text", "")
            self.context["telegram_username"] = tg.get("username", "")
            self.context["telegram_first_name"] = tg.get("first_name", "")

        # Ноды, привязанные к агенту как инструменты, вызывает сам агент.
        tool_ids = set()
        for node in self.workflow["nodes"]:
            if node["type"] == "agent":
                tool_ids.update(node.get("config", {}).get("tools", []))
        for edge in self.workflow.get("edges", []):
            if edge.get("type") == "tool" and edge.get("from_node") != edge.get("to_node"):
                tool_ids.add(edge["to_node"])

        for node in self._topological_order():
            if node["id"] in tool_ids:
                continue
            result = await self._execute_node(node, trigger_data)
            self.context[node["id"]] = result
            self.logs.append({
                "node_id": node["id"],
                "type": node["type"],
                "input": node.get("config", {}),
                "output": result,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        return self.context

    def _get_handler(self, node_type):
        handlers = {
            "manual": self._handle_manual,
            "telegram_trigger": self._handle_manual,
            "llm": self._handle_llm,
            "http": self._handle_http,
            "condition": self._handle_condition,
            "print": self._handle_print,
            "agent": self._handle_agent,
            "telegram_send": self._handle_telegram_send,
            "google_sheets_append": self._handle_google_sheets_append,
            "google_calendar_create_event": self._handle_google_calendar_create_event,
        }
        return handlers.get(node_type)

    async def _execute_node(self, node, trigger_data):
        handler = self._get_handler(node["type"])
        if not handler:
            return f"Unknown node type: {node['type']}"
        self._current_agent_id = node["id"]
        return await handler(node.get("config", {}), trigger_data)

    async def _handle_manual(self, config, trigger_data, extra_vars=None):
        return trigger_data or {}

    async def _handle_llm(self, config, td, extra_vars=None):
        prompt = self._render_template(config.get("prompt", ""), extra_vars)
        try:
            return await self.llm.generate(
                prompt, config.get("model"), config.get("temperature", 0.7),
                config.get("mode", "cloud"), connection_id=config.get("connection_id"),
            )
        except Exception as e:
            return f"LLM Error: {str(e)}"

    async def _handle_http(self, config, td, extra_vars=None):
        try:
            method = config.get("method", "GET").upper()
            url = self._render_template(config.get("url", ""), extra_vars)
            if not url or not url.startswith(("http://", "https://")):
                return f"HTTP Error: Invalid URL after template rendering: '{url}'. Make sure to provide a valid URL or trigger data."

            async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
                for _ in range(MAX_HTTP_REDIRECTS + 1):
                    await assert_public_url(url)
                    response = await client.request("GET" if method == "GET" else "POST", url)
                    if response.is_redirect and response.headers.get("location"):
                        url = str(response.url.join(response.headers["location"]))
                        continue
                    break
            return {"status_code": response.status_code, "body": response.text[:1000]}
        except Exception as e:
            return f"HTTP Error: {str(e)}"

    async def _handle_telegram_send(self, config, td, extra_vars=None):
        connection = self._get_connection(config.get("connection_id"))
        if not connection or connection.get("provider") != "telegram_bot":
            return "Telegram Error: не выбрано подключение Telegram Bot (Подключения → Инструменты)"

        bot_token = connection["config"].get("bot_token")
        if not bot_token:
            return "Telegram Error: у подключения не задан bot_token"

        chat_id = self._render_template(str(config.get("chat_id", "")), extra_vars)
        if not chat_id and self.context.get("telegram_chat_id"):
            chat_id = str(self.context["telegram_chat_id"])      # ответ в чат, откуда пришёл триггер
        text = self._render_template(config.get("message", ""), extra_vars)

        if not chat_id:
            return "Telegram Error: не указан chat_id"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": text[:4096]},
                )
                return {"status_code": response.status_code, "body": response.text[:500]}
        except Exception as e:
            return f"Telegram Error: {str(e).replace(bot_token, '***')}"

    async def _handle_google_sheets_append(self, config, td, extra_vars=None):
        connection = self._get_connection(config.get("connection_id"))
        if not connection or connection.get("provider") != "google_sheets":
            return "Google Sheets Error: не выбрано подключение Google Таблицы (Подключения → Инструменты)"

        access_token = connection["config"].get("access_token")
        if not access_token:
            return "Google Sheets Error: нет access_token — переподключи аккаунт на странице Подключения"

        spreadsheet_id = self._render_template(config.get("spreadsheet_id", ""), extra_vars)
        sheet_range = config.get("range", "A1")
        raw_values = self._render_template(config.get("values", ""), extra_vars)
        row = [v.strip() for v in raw_values.split(",")] if raw_values else []

        if not spreadsheet_id:
            return "Google Sheets Error: не указан spreadsheet_id"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{sheet_range}:append",
                    params={"valueInputOption": "USER_ENTERED"},
                    headers={"Authorization": f"Bearer {access_token}"},
                    json={"values": [row]},
                )
                return {"status_code": response.status_code, "body": response.text[:500]}
        except Exception as e:
            return f"Google Sheets Error: {str(e)}"

    async def _handle_google_calendar_create_event(self, config, td, extra_vars=None):
        connection = self._get_connection(config.get("connection_id"))
        if not connection or connection.get("provider") != "google_calendar":
            return "Google Calendar Error: не выбрано подключение Google Календарь (Подключения → Инструменты)"

        access_token = connection["config"].get("access_token")
        if not access_token:
            return "Google Calendar Error: нет access_token — переподключи аккаунт на странице Подключения"

        calendar_id = config.get("calendar_id") or "primary"
        summary = self._render_template(config.get("summary", ""), extra_vars)
        description = self._render_template(config.get("description", ""), extra_vars)
        start_dt = self._render_template(config.get("start_datetime", ""), extra_vars)
        end_dt = self._render_template(config.get("end_datetime", ""), extra_vars)

        if not (start_dt and end_dt):
            return "Google Calendar Error: не указаны start_datetime/end_datetime"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
                    headers={"Authorization": f"Bearer {access_token}"},
                    json={
                        "summary": summary,
                        "description": description,
                        "start": {"dateTime": start_dt},
                        "end": {"dateTime": end_dt},
                    },
                )
                return {"status_code": response.status_code, "body": response.text[:500]}
        except Exception as e:
            return f"Google Calendar Error: {str(e)}"

    async def _handle_condition(self, config, td, extra_vars=None):
        expression = self._render_template(config.get("expression", "True"), extra_vars)
        names = dict(self.context)
        if extra_vars:
            names.update(extra_vars)
        try:
            return safe_eval(expression, names)
        except Exception:
            return False

    async def _handle_print(self, config, td, extra_vars=None):
        return self._render_template(config.get("value", "{last_result}"), extra_vars)

    async def _handle_agent(self, config, td, extra_vars=None):
        """
        Agent-loop: LLM сам решает, вызывать ли инструмент и когда дать финальный ответ.
        Инструментом может стать нода любого типа с заполненными tool_name/tool_description.
        """
        system_prompt = config.get("system_prompt", "Ты — полезный ассистент.")
        model = config.get("model") or None
        mode = config.get("mode", settings.default_llm_mode)
        max_iterations = max(1, min(int(config.get("max_iterations", 5) or 5), 10))
        temperature = config.get("temperature", 0.3)
        connection_id = config.get("connection_id")

        tool_node_ids = set(config.get("tools", []))
        agent_node_id = self._current_agent_id
        for edge in self.workflow.get("edges", []):
            if edge.get("type") == "tool" and edge.get("from_node") == agent_node_id and edge.get("to_node") != agent_node_id:
                tool_node_ids.add(edge["to_node"])

        tool_nodes = {}
        tool_schemas = []
        for node_id in tool_node_ids:
            tool_node = self.nodes_by_id.get(node_id)
            if not tool_node:
                continue
            tconf = tool_node.get("config", {})
            if not (tconf.get("tool_name") or tconf.get("tool_description")):
                continue
            if not self._get_handler(tool_node["type"]):
                continue
            tool_name = tconf.get("tool_name", node_id)
            tool_nodes[tool_name] = tool_node
            tool_schemas.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tconf.get("tool_description", f"Инструмент {tool_name}"),
                    "parameters": tconf.get("tool_parameters", {"type": "object", "properties": {}, "required": []}),
                },
            })

        user_input = self._render_template(config.get("prompt", "{input}"))
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]
        trace = []

        try:
            for _ in range(max_iterations):
                message = await self.llm.chat(
                    messages, model=model, tools=tool_schemas or None,
                    temperature=temperature, mode=mode, connection_id=connection_id,
                )
                messages.append(message)
                trace.append(message)

                tool_calls = message.get("tool_calls") or []
                if not tool_calls:
                    return {"answer": message.get("content") or "", "trace": trace}

                for call in tool_calls:
                    fn = call.get("function", {})
                    name = fn.get("name")
                    args = fn.get("arguments", {}) or {}

                    tool_node = tool_nodes.get(name)
                    if not tool_node:
                        tool_result = f"Unknown tool: {name}"
                    else:
                        try:
                            handler = self._get_handler(tool_node["type"])
                            tool_result = await handler(tool_node.get("config", {}), td, extra_vars=args)
                        except Exception as e:
                            tool_result = f"Tool Error: {str(e)}"

                    tool_message = {
                        "role": "tool",
                        "tool_name": name,
                        "content": json.dumps(tool_result, ensure_ascii=False) if not isinstance(tool_result, str) else tool_result,
                    }
                    if call.get("id"):
                        tool_message["tool_call_id"] = call["id"]
                    messages.append(tool_message)
                    trace.append(tool_message)

            return {"answer": "Достигнут лимит итераций агента без финального ответа", "trace": trace}
        except Exception as e:
            return {"answer": f"Agent Error: {str(e)}", "trace": trace}

    def _render_template(self, template, extra_vars=None):
        result = template
        variables = dict(self.context)
        if extra_vars:
            variables.update(extra_vars)
        for key, value in variables.items():
            placeholder = f"{{{key}}}"
            if placeholder in result:
                result = result.replace(placeholder, str(value)[:500])
        return result
