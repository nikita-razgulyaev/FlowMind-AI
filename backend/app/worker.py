import asyncio
import json
import httpx
import os


class LLMProvider:
    """Выбирает LLM-провайдер в зависимости от настроек узла"""

    def __init__(self, connections: dict = None):
        self.mode = os.getenv("LLM_MODE", "local")
        self.ollama_url = os.getenv("OLLAMA_URL", "http://ollama:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5")
        self.hf_token = os.getenv("HF_TOKEN")
        self.hf_model = os.getenv("HF_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
        self.cloud_provider = os.getenv("CLOUD_PROVIDER", "huggingface")
        # connection_id -> {"provider": ..., "config": {...}} — реальные (не замаскированные)
        # данные подключений, подгружаются из БД в main.py перед выполнением workflow.
        self.connections = connections or {}

    def _resolve_connection(self, connection_id):
        if connection_id is None:
            return None
        return self.connections.get(connection_id)

    async def generate(self, prompt: str, model: str = None, temperature: float = 0.7,
                        mode: str = None, connection_id=None) -> str:
        effective_mode = mode or self.mode

        if effective_mode == "local":
            return await self._ollama_generate(prompt, model or self.ollama_model, temperature)
        elif effective_mode == "cloud":
            connection = self._resolve_connection(connection_id)
            if connection:
                return await self._cloud_generate_via_connection(prompt, model, temperature, connection)
            # Обратная совместимость: старый путь через .env (HF_TOKEN)
            return await self._cloud_generate(prompt, model or self.hf_model, temperature)
        else:
            raise ValueError(f"Unknown LLM_MODE: {effective_mode}")

    async def _cloud_generate_via_connection(self, prompt: str, model: str, temperature: float, connection: dict) -> str:
        provider = connection["provider"]
        cfg = connection["config"]
        if provider == "huggingface":
            return await self._hf_generate(prompt, model or self.hf_model, temperature, api_key=cfg.get("api_key"))
        elif provider == "openai_compatible":
            return await self._openai_generate(
                prompt, model, temperature,
                api_key=cfg.get("api_key"), base_url=cfg.get("base_url", "https://api.openai.com/v1"),
            )
        else:
            raise ValueError(f"Подключение с provider='{provider}' не поддерживает генерацию текста")

    async def _cloud_generate(self, prompt: str, model: str, temperature: float) -> str:
        if self.cloud_provider == "huggingface":
            return await self._hf_generate(prompt, model, temperature)
        else:
            raise ValueError(f"Unknown CLOUD_PROVIDER: {self.cloud_provider}")

    async def _ollama_generate(self, prompt: str, model: str, temperature: float) -> str:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": temperature}
                }
            )
            data = response.json()
            return data.get("response", "")

    async def _hf_generate(self, prompt: str, model: str, temperature: float, api_key: str = None) -> str:
        token = api_key or self.hf_token
        if not token:
            raise ValueError("HF_TOKEN not set (ни в .env, ни в подключении)")

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"https://api-inference.huggingface.co/models/{model}",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "inputs": prompt,
                    "parameters": {
                        "max_new_tokens": 500,
                        "temperature": temperature,
                        "return_full_text": False
                    }
                }
            )

            if response.status_code == 503:
                print("Model loading, waiting 20s...")
                await asyncio.sleep(20)
                return await self._hf_generate(prompt, model, temperature, api_key=api_key)

            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                return data[0].get("generated_text", "").strip()

            return str(data)

    async def _openai_generate(self, prompt: str, model: str, temperature: float, api_key: str, base_url: str) -> str:
        if not api_key:
            raise ValueError("У подключения не задан API Key")

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"].get("content", "")

    async def chat(self, messages: list, model: str = None, tools: list = None, temperature: float = 0.7,
                    mode: str = None, connection_id=None) -> dict:
        """Чат-эндпоинт с поддержкой tool calling: local (Ollama) или cloud через openai-совместимое подключение."""
        effective_mode = mode or self.mode

        if effective_mode == "local":
            return await self._ollama_chat(messages, model or self.ollama_model, tools, temperature)

        if effective_mode == "cloud":
            connection = self._resolve_connection(connection_id)
            if not connection:
                raise ValueError(
                    "Agent-нода в mode='cloud' требует connection_id, указывающий на подключение "
                    "с провайдером 'openai_compatible' (только он поддерживает tool calling в облаке)."
                )
            if connection["provider"] != "openai_compatible":
                raise ValueError(
                    f"Подключение с provider='{connection['provider']}' не поддерживает tool calling. "
                    f"Используй подключение с provider='openai_compatible' (OpenAI/OpenRouter/Groq)."
                )
            cfg = connection["config"]
            return await self._openai_chat(
                messages, model, tools, temperature,
                api_key=cfg.get("api_key"), base_url=cfg.get("base_url", "https://api.openai.com/v1"),
            )

        raise ValueError(f"Unknown mode: {effective_mode}")

    async def _ollama_chat(self, messages: list, model: str, tools: list, temperature: float) -> dict:
        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature}
            }
            if tools:
                payload["tools"] = tools

            response = await client.post(f"{self.ollama_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("message", {})

    async def _openai_chat(self, messages: list, model: str, tools: list, temperature: float,
                            api_key: str, base_url: str) -> dict:
        if not api_key:
            raise ValueError("У подключения не задан API Key")

        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {"model": model, "messages": messages, "temperature": temperature}
            if tools:
                payload["tools"] = tools

            response = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            message = data["choices"][0]["message"]

            # OpenAI отдаёт tool_calls[].function.arguments строкой JSON —
            # приводим к тому же формату (dict), который уже понимает agent-loop
            # после ответа Ollama, чтобы не дублировать логику ниже.
            for call in message.get("tool_calls") or []:
                fn = call.get("function", {})
                args = fn.get("arguments")
                if isinstance(args, str):
                    try:
                        fn["arguments"] = json.loads(args)
                    except json.JSONDecodeError:
                        fn["arguments"] = {}

            return message


class WorkflowEngine:
    def __init__(self, workflow, execution_id, connections: dict = None):
        self.workflow = workflow
        self.execution_id = execution_id
        self.context = {}
        self.logs = []
        # connection_id -> {"provider": ..., "config": {...}}
        self.connections = connections or {}
        self.llm = LLMProvider(connections=self.connections)
        # Быстрый доступ к нодам по id — нужен агенту для поиска tool-нод
        self.nodes_by_id = {n["id"]: n for n in workflow.get("nodes", [])}
        self._current_agent_id = None

    def _get_connection(self, connection_id):
        if connection_id is None:
            return None
        return self.connections.get(connection_id)

    def _topological_order(self):
        """
        Порядок выполнения определяется реальными связями графа ("next"-рёбрами),
        а не порядком нод в массиве — React Flow может тасовать порядок массива
        (например, при клике по ноде), поэтому полагаться на него нельзя.
        """
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

        # Ноды вне графа связей (изолированные, либо цикл) — добавляем в исходном порядке
        for nid in node_ids:
            if nid not in visited:
                visited.append(nid)

        return [self.nodes_by_id[nid] for nid in visited]

    async def execute(self, trigger_data=None):
        trigger_data = trigger_data or {}
        # Если trigger_data — словарь вида {"input": "..."}, подставляем в шаблоны
        # чистое значение, а не весь словарь целиком (иначе {input} превращается
        # в "{'input': '...'}", что сбивает модель с толку).
        if isinstance(trigger_data, dict) and "input" in trigger_data:
            self.context["input"] = trigger_data["input"]
        else:
            self.context["input"] = trigger_data

        # Ноды, привязанные к какому-либо agent-у как инструмент, не выполняются
        # в обычном последовательном проходе — их вызывает сам агент по необходимости.
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
                "timestamp": str(asyncio.get_event_loop().time())
            })
        return self.context

    def _get_handler(self, node_type):
        """Единая точка сопоставления типа ноды с её обработчиком — используется
        и обычным исполнением графа, и агентом при вызове ноды как инструмента."""
        handlers = {
            "manual": self._handle_manual,
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
        model = config.get("model")
        temperature = config.get("temperature", 0.7)
        mode = config.get("mode", "cloud")  # ← "cloud" по умолчанию
        connection_id = config.get("connection_id")

        try:
            return await self.llm.generate(prompt, model, temperature, mode, connection_id=connection_id)
        except Exception as e:
            return f"LLM Error: {str(e)}"

    async def _handle_http(self, config, td, extra_vars=None):
        async with httpx.AsyncClient() as client:
            try:
                method = config.get("method", "GET").upper()
                url = self._render_template(config.get("url", ""), extra_vars)

                if not url or not url.startswith(("http://", "https://")):
                    return f"HTTP Error: Invalid URL after template rendering: '{url}'. Make sure to provide a valid URL or trigger data."

                if method == "GET":
                    response = await client.get(url)
                else:
                    response = await client.post(url)
                return {
                    "status_code": response.status_code,
                    "body": response.text[:1000]
                }
            except Exception as e:
                return f"HTTP Error: {str(e)}"

    async def _handle_telegram_send(self, config, td, extra_vars=None):
        """
        Отправка сообщения через Telegram Bot API, используя bot_token
        из подключения (Connections → Инструменты → Telegram Bot).
        """
        connection = self._get_connection(config.get("connection_id"))
        if not connection or connection.get("provider") != "telegram_bot":
            return "Telegram Error: не выбрано подключение Telegram Bot (Connections → Инструменты)"

        bot_token = connection["config"].get("bot_token")
        if not bot_token:
            return "Telegram Error: у подключения не задан bot_token"

        chat_id = self._render_template(str(config.get("chat_id", "")), extra_vars)
        text = self._render_template(config.get("message", ""), extra_vars)

        if not chat_id:
            return "Telegram Error: не указан chat_id"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={"chat_id": chat_id, "text": text},
                )
                return {"status_code": response.status_code, "body": response.text[:500]}
        except Exception as e:
            return f"Telegram Error: {str(e)}"

    async def _handle_google_sheets_append(self, config, td, extra_vars=None):
        """
        Добавляет строку в Google Таблицу. config.values — строка с разделителем-запятой,
        например "{client_name}, {phone}, {date}" — каждый {placeholder} подставляется
        из контекста выполнения или аргументов агента (extra_vars).
        """
        connection = self._get_connection(config.get("connection_id"))
        if not connection or connection.get("provider") != "google_sheets":
            return "Google Sheets Error: не выбрано подключение Google Таблицы (Connections → Инструменты)"

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
        """
        Создаёт событие в Google Календаре. start_datetime/end_datetime — ISO 8601
        (например 2026-08-01T15:00:00+03:00), можно с {placeholder} для подстановки.
        """
        connection = self._get_connection(config.get("connection_id"))
        if not connection or connection.get("provider") != "google_calendar":
            return "Google Calendar Error: не выбрано подключение Google Календарь (Connections → Инструменты)"

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
        try:
            result = eval(expression, {"__builtins__": {}}, self.context)
            return result
        except:
            return False

    async def _handle_print(self, config, td, extra_vars=None):
        value = self._render_template(config.get("value", "{last_result}"), extra_vars)
        print(f"[FlowMind] {value}")
        return value

    async def _handle_agent(self, config, td, extra_vars=None):
        """
        Agent-loop: LLM (Ollama локально, либо openai-совместимое облачное подключение)
        сам решает, вызывать ли инструмент и когда остановиться и дать финальный ответ.

        Инструментом может стать НОДА ЛЮБОГО ТИПА (http, telegram_send, llm, condition, print,
        в будущем — что угодно ещё) — единственное условие: у неё в конфиге заполнено
        tool_name/tool_description. Так новые типы нод автоматически становятся доступны
        агенту без правок в этом методе.
        """
        system_prompt = config.get("system_prompt", "Ты — полезный ассистент.")
        model = config.get("model", "qwen2.5")
        mode = config.get("mode", "local")
        max_iterations = config.get("max_iterations", 5)
        temperature = config.get("temperature", 0.3)  # ниже, чем у обычной llm-ноды — стабильнее tool calling
        connection_id = config.get("connection_id")

        # Инструменты определяются рёбрами графа (agent --tool--> node),
        # плюс поддержка старого формата config.tools для обратной совместимости.
        tool_node_ids = set(config.get("tools", []))
        agent_node_id = self._current_agent_id
        for edge in self.workflow.get("edges", []):
            if edge.get("type") == "tool" and edge.get("from_node") == agent_node_id and edge.get("to_node") != agent_node_id:
                tool_node_ids.add(edge["to_node"])

        # Собираем схемы инструментов из указанных tool-нод. Нода годится в инструменты,
        # если у неё есть обработчик и явно размечены tool_name/tool_description —
        # тип ноды при этом не имеет значения.
        tool_nodes = {}
        tool_schemas = []
        for node_id in tool_node_ids:
            tool_node = self.nodes_by_id.get(node_id)
            if not tool_node:
                continue
            tconf = tool_node.get("config", {})
            if not (tconf.get("tool_name") or tconf.get("tool_description")):
                continue  # нода не размечена как инструмент — пропускаем
            if not self._get_handler(tool_node["type"]):
                continue  # неизвестный тип ноды — нечем выполнить
            tool_name = tconf.get("tool_name", node_id)
            tool_nodes[tool_name] = tool_node
            tool_schemas.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tconf.get("tool_description", f"Инструмент {tool_name}"),
                    "parameters": tconf.get("tool_parameters", {
                        "type": "object", "properties": {}, "required": []
                    }),
                }
            })

        user_input = self._render_template(config.get("prompt", "{input}"))
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input},
        ]

        trace = []  # для отладки — весь диалог с инструментами

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
                    return {
                        "answer": message.get("content", ""),
                        "trace": trace,
                    }

                for call in tool_calls:
                    fn = call.get("function", {})
                    name = fn.get("name")
                    args = fn.get("arguments", {}) or {}

                    tool_node = tool_nodes.get(name)
                    if not tool_node:
                        tool_result = f"Unknown tool: {name}"
                    else:
                        tool_handler = self._get_handler(tool_node["type"])
                        tool_result = await tool_handler(tool_node.get("config", {}), td, extra_vars=args)

                    tool_message = {
                        "role": "tool",
                        "tool_name": name,
                        "content": json.dumps(tool_result, ensure_ascii=False) if not isinstance(tool_result, str) else tool_result,
                    }
                    messages.append(tool_message)
                    trace.append(tool_message)

            return {
                "answer": "Достигнут лимит итераций агента без финального ответа",
                "trace": trace,
            }
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