import asyncio
import json
import httpx
import os


class LLMProvider:
    """Выбирает LLM-провайдер в зависимости от настроек узла"""

    def __init__(self):
        self.mode = os.getenv("LLM_MODE", "local")
        self.ollama_url = os.getenv("OLLAMA_URL", "http://ollama:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5")
        self.hf_token = os.getenv("HF_TOKEN")
        self.hf_model = os.getenv("HF_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
        self.cloud_provider = os.getenv("CLOUD_PROVIDER", "huggingface")

    async def generate(self, prompt: str, model: str = None, temperature: float = 0.7, mode: str = None) -> str:
        effective_mode = mode or self.mode

        if effective_mode == "local":
            return await self._ollama_generate(prompt, model or self.ollama_model, temperature)
        elif effective_mode == "cloud":
            return await self._cloud_generate(prompt, model or self.hf_model, temperature)
        else:
            raise ValueError(f"Unknown LLM_MODE: {effective_mode}")

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

    async def _hf_generate(self, prompt: str, model: str, temperature: float) -> str:
        if not self.hf_token:
            raise ValueError("HF_TOKEN not set")

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"https://api-inference.huggingface.co/models/{model}",
                headers={"Authorization": f"Bearer {self.hf_token}"},
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
                return await self._hf_generate(prompt, model, temperature)

            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                return data[0].get("generated_text", "").strip()

            return str(data)

    async def chat(self, messages: list, model: str = None, tools: list = None, temperature: float = 0.7, mode: str = None) -> dict:
        """Чат-эндпоинт с поддержкой tool calling. Пока только для local (Ollama)."""
        effective_mode = mode or self.mode

        if effective_mode == "local":
            return await self._ollama_chat(messages, model or self.ollama_model, tools, temperature)
        else:
            raise ValueError(
                f"Agent-нода пока поддерживает tool calling только в mode='local' (Ollama). "
                f"Получен mode='{effective_mode}'."
            )

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


class WorkflowEngine:
    def __init__(self, workflow, execution_id):
        self.workflow = workflow
        self.execution_id = execution_id
        self.context = {}
        self.logs = []
        self.llm = LLMProvider()
        # Быстрый доступ к нодам по id — нужен агенту для поиска tool-нод
        self.nodes_by_id = {n["id"]: n for n in workflow.get("nodes", [])}
        self._current_agent_id = None

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

    async def _execute_node(self, node, trigger_data):
        handlers = {
            "manual": self._handle_manual,
            "llm": self._handle_llm,
            "http": self._handle_http,
            "condition": self._handle_condition,
            "print": self._handle_print,
            "agent": self._handle_agent,
        }
        handler = handlers.get(node["type"])
        if not handler:
            return f"Unknown node type: {node['type']}"
        self._current_agent_id = node["id"]
        return await handler(node.get("config", {}), trigger_data)

    async def _handle_manual(self, config, trigger_data):
        return trigger_data or {}

    async def _handle_llm(self, config, td):
        prompt = self._render_template(config.get("prompt", ""))
        model = config.get("model")
        temperature = config.get("temperature", 0.7)
        mode = config.get("mode", "cloud")  # ← "cloud" по умолчанию

        try:
            return await self.llm.generate(prompt, model, temperature, mode)
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

    async def _handle_condition(self, config, td):
        expression = self._render_template(config.get("expression", "True"))
        try:
            result = eval(expression, {"__builtins__": {}}, self.context)
            return result
        except:
            return False

    async def _handle_print(self, config, td):
        value = self._render_template(config.get("value", "{last_result}"))
        print(f"[FlowMind] {value}")
        return value

    async def _handle_agent(self, config, td):
        """
        MVP agent-loop: LLM (через Ollama /api/chat + tools) сам решает,
        вызывать ли инструмент (пока поддерживается только тип "http") и когда
        остановиться и дать финальный ответ.
        """
        system_prompt = config.get("system_prompt", "Ты — полезный ассистент.")
        model = config.get("model", "qwen2.5")
        mode = config.get("mode", "local")
        max_iterations = config.get("max_iterations", 5)
        temperature = config.get("temperature", 0.3)  # ниже, чем у обычной llm-ноды — стабильнее tool calling

        # Инструменты определяются рёбрами графа (agent --tool--> node),
        # плюс поддержка старого формата config.tools для обратной совместимости.
        tool_node_ids = set(config.get("tools", []))
        agent_node_id = self._current_agent_id
        for edge in self.workflow.get("edges", []):
            if edge.get("type") == "tool" and edge.get("from_node") == agent_node_id and edge.get("to_node") != agent_node_id:
                tool_node_ids.add(edge["to_node"])

        # Собираем схемы инструментов из указанных tool-нод
        tool_nodes = {}
        tool_schemas = []
        for node_id in tool_node_ids:
            tool_node = self.nodes_by_id.get(node_id)
            if not tool_node or tool_node["type"] != "http":
                continue  # MVP: пока поддерживаем только http-ноды как инструменты
            tconf = tool_node.get("config", {})
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
                message = await self.llm.chat(messages, model=model, tools=tool_schemas or None, temperature=temperature, mode=mode)
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
                        tool_result = await self._handle_http(tool_node.get("config", {}), td, extra_vars=args)

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