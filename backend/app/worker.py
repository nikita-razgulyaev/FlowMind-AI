"""Движок выполнения workflow: топологический порядок, agent-loop с tool calling, обработчики нод."""
import asyncio
import json
import re
import time
from datetime import datetime, timezone

import httpx

from .config import settings
from .services import caldav, email_service, oauth, textops
from .services.llm import LLMProvider
from .services.safe_eval import safe_eval
from .services.ssrf import assert_public_url

MAX_HTTP_REDIRECTS = 3
MAX_RENDER_CHARS = 20000                    # длина одного подставляемого значения {node}
MAX_HTTP_JSON_CHARS = 20000                 # ответ HTTP разбирается в json, только если он не больше
TRIGGER_TYPES = ("manual", "telegram_trigger", "webhook", "schedule", "email_trigger")
BRANCH_TRIGGER_KEYS = ("telegram", "webhook", "schedule", "email")     # признаки «боевого» запуска (не кнопка Run)

# {name}, {name.field}, {name.items[0].title} — путь по JSON-выводу ноды
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][\w\-]*)((?:\.[\w\-]+|\[\d+\])*)\}")
PATH_PART_RE = re.compile(r"\.([\w\-]+)|\[(\d+)\]")


def loose_json(value):
    """Достаёт JSON-объект из значения: dict как есть, из строки — первый блок {...} (LLM любят оборачивать JSON в текст)."""
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    start, end = value.find("{"), value.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(value[start:end + 1])
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def resolve_path(value, path: str):
    """Идёт по пути .a.b[0]. Возвращает (найдено, значение)."""
    for key, index in PATH_PART_RE.findall(path):
        if index:
            if not isinstance(value, list) or int(index) >= len(value):
                return False, None
            value = value[int(index)]
            continue
        container = value if isinstance(value, (dict, list)) else loose_json(value)
        if isinstance(container, dict) and key in container:
            value = container[key]
        elif isinstance(container, list) and key.isdigit() and int(key) < len(container):
            value = container[int(key)]
        else:
            return False, None
    return True, value


def render_value(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str) \
        if isinstance(value, (dict, list)) else str(value)
    return text[:MAX_RENDER_CHARS]


ERROR_OUTPUT_RE = re.compile(r"^[A-Za-z ]{2,30} Error\b")


def is_error_output(result) -> bool:
    """Обработчики нод возвращают сбой строкой «LLM Error: ...», «HTTP Error: ...» — помечаем такую ноду как failed."""
    return isinstance(result, str) and bool(ERROR_OUTPUT_RE.match(result))


def telegram_error_hint(body: str) -> str:
    """Понятное объяснение типичных отказов Telegram."""
    low = body.lower()
    if "chat not found" in low:
        return "чат или канал не найден. Для канала укажите @имя_канала и добавьте бота администратором"
    if "not enough rights" in low or "have no rights" in low or "need administrator" in low:
        return "у бота нет прав публиковать в этом канале. Назначьте его администратором с правом публикации сообщений"
    if "bot was blocked" in low or "bot was kicked" in low:
        return "бот заблокирован пользователем или удалён из чата"
    if "wrong file identifier" in low or "failed to get http url content" in low or "wrong type of the web page content" in low:
        return "Telegram не смог скачать картинку по ссылке. Нужна прямая ссылка на изображение, открытая без входа"
    return body[:200]


def prepare_tool_schema(schema) -> dict:
    """Схема параметров инструмента для модели. Примеры значений (`examples`) переносятся в описание поля:
    так их видят все провайдеры, и модель понимает, как искать значение в сообщении клиента."""
    if not isinstance(schema, dict) or not isinstance(schema.get("properties"), dict):
        return {"type": "object", "properties": {}, "required": []}
    props = {}
    for name, prop in schema["properties"].items():
        if not isinstance(prop, dict):
            props[name] = {"type": "string"}
            continue
        prop = dict(prop)
        examples = prop.pop("examples", None)
        if isinstance(examples, list) and examples:
            sample = "; ".join(f"«{e}»" for e in examples[:5])
            prop["description"] = f"{prop.get('description', '')} Примеры в сообщениях клиентов: {sample}".strip()
        props[name] = prop
    return {**schema, "properties": props, "required": [r for r in schema.get("required", []) if r in props]}


def normalize_label(text: str) -> str:
    return re.sub(r"[^\w\s]", "", str(text).casefold()).strip()


class WorkflowEngine:
    def __init__(self, workflow, execution_id, connections: dict = None, llm_guard=None, on_progress=None):
        self.on_progress = on_progress              # (node_id, status, duration_ms|None): running | done | failed | skipped
        self.workflow = workflow
        self.execution_id = execution_id
        self.context = {}
        self.logs = []
        # connection_id -> {"provider": ..., "config": {...расшифрованный...}}
        self.connections = connections or {}
        self.llm = LLMProvider(connections=self.connections, guard=llm_guard)
        self.nodes_by_id = {n["id"]: n for n in workflow.get("nodes", [])}
        self._current_agent_id = None
        self.executed: set[str] = set()
        self.branches: dict[str, str] = {}          # id ветвящей ноды -> выбранная ветка ("true"/"false"/значение switch)
        self.incoming: dict[str, list[dict]] = {}
        for edge in workflow.get("edges", []):
            if edge.get("type") != "tool":
                self.incoming.setdefault(edge.get("to_node"), []).append(edge)

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

        mail = trigger_data.get("email") if isinstance(trigger_data, dict) else None
        if isinstance(mail, dict):
            self.context["email_from"] = mail.get("from", "")
            self.context["email_from_name"] = mail.get("from_name", "")
            self.context["email_subject"] = mail.get("subject", "")
            self.context["email_body"] = mail.get("body", "")
            self.context["email_message_id"] = mail.get("message_id", "")

        webhook = trigger_data.get("webhook") if isinstance(trigger_data, dict) else None
        if isinstance(webhook, dict):
            self.context["webhook"] = webhook
        self._apply_test_input(trigger_data)

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
            if not self._is_reachable(node["id"]):
                self.context[node["id"]] = ""      # ветка не выбрана: {node} подставляется пустым, так работает «слияние»
                self._report(node["id"], "skipped")
                continue
            self._report(node["id"], "running")
            started = time.monotonic()
            try:
                result = await self._execute_node(node, trigger_data)
            except Exception:
                self._report(node["id"], "failed", started)
                raise
            self._report(node["id"], "failed" if is_error_output(result) else "done", started)
            self.executed.add(node["id"])
            self._register_branch(node, result)
            self.context[node["id"]] = result
            self.logs.append({
                "node_id": node["id"],
                "type": node["type"],
                "input": node.get("config", {}),
                "output": result,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        return self.context

    def _report(self, node_id: str, status: str, started: float | None = None):
        """Краткий статус ноды для индикатора выполнения; сбой индикатора не должен ломать запуск."""
        if not self.on_progress:
            return
        try:
            self.on_progress(node_id, status, None if started is None else int((time.monotonic() - started) * 1000))
        except Exception:
            pass

    def _apply_test_input(self, trigger_data):
        """Кнопка Run без модалки: пустой вход заменяется тестовыми данными из настроек триггера."""
        if not isinstance(trigger_data, dict) or any(k in trigger_data for k in BRANCH_TRIGGER_KEYS):
            return
        if self.context.get("input") not in ("", {}, None):
            return
        for node in self.workflow["nodes"]:
            cfg = node.get("config") or {}
            if node["type"] not in TRIGGER_TYPES or not cfg.get("test_input"):
                continue
            text = str(cfg["test_input"])
            self.context["input"] = text
            if node["type"] == "telegram_trigger":
                self.context["telegram_text"] = text
                self.context["telegram_chat_id"] = cfg.get("test_chat_id", "")
            if node["type"] == "email_trigger":
                self.context["email_from"] = cfg.get("test_from", "client@example.com")
                self.context["email_subject"] = cfg.get("test_subject", "")
                self.context["email_body"] = text
            if node["type"] == "webhook":
                self.context["webhook"] = {"body": loose_json(text) or text, "query": {}, "method": "POST"}
            return

    def _edge_is_live(self, edge) -> bool:
        source = edge.get("from_node")
        if source not in self.executed:
            return False
        label = edge.get("condition")
        chosen = self.branches.get(source)
        return not label or chosen is None or str(chosen) == str(label)

    def _is_reachable(self, node_id) -> bool:
        """Нода выполняется, если у неё нет входов (триггер) или хотя бы один входящий путь «живой»."""
        incoming = self.incoming.get(node_id)
        return not incoming or any(self._edge_is_live(e) for e in incoming)

    def _register_branch(self, node, result):
        if node["type"] == "condition":
            self.branches[node["id"]] = "true" if result else "false"
        elif node["type"] == "switch":
            self.branches[node["id"]] = str(result)

    def _get_handler(self, node_type):
        handlers = {
            "manual": self._handle_manual,
            "telegram_trigger": self._handle_manual,
            "webhook": self._handle_manual,
            "schedule": self._handle_manual,
            "email_trigger": self._handle_manual,
            "text_transform": self._handle_text_transform,
            "email_send": self._handle_email_send,
            "text_input": self._handle_text_input,
            "switch": self._handle_switch,
            "set": self._handle_set,
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
        if isinstance(trigger_data, dict) and trigger_data.get("input") not in ("", {}, None):
            return trigger_data
        return {"input": self.context.get("input", "")}

    async def _handle_text_input(self, config, td, extra_vars=None):
        """Готовый текст (вставленный или из файла) — как есть, без подстановок."""
        return str(config.get("text", ""))

    async def _handle_text_transform(self, config, td, extra_vars=None):
        """Обработка текста без нейросети: найти email/телефон/номер заказа/дату, очистить, обрезать."""
        value = self._render_template(config.get("value") or "{input}", extra_vars)
        return textops.apply_operation(
            config.get("operation") or "trim", value, str(config.get("pattern", "")), config.get("max_chars") or 500,
        )

    async def _handle_email_send(self, config, td, extra_vars=None):
        connection = self._get_connection(config.get("connection_id"))
        if not connection or connection.get("provider") not in oauth.MAIL_PROVIDERS:
            return "Email Error: не выбрана почта. Подключите её в разделе «Подключения»"
        if connection["config"].get("needs_reauth"):
            return "Email Error: доступ к почте истёк. Откройте «Подключения» и войдите заново"
        to = self._render_template(config.get("to") or "{email_from}", extra_vars).strip()
        if not textops.EMAIL_RE.fullmatch(to):
            return f"Email Error: некорректный адрес получателя «{to}»"
        subject = self._render_template(config.get("subject", ""), extra_vars)[:300] or "Без темы"
        body = self._render_template(config.get("body", ""), extra_vars)
        reply_id = self.context.get("email_message_id", "") if config.get("as_reply") else ""
        try:
            await email_service.send_message(email_service.with_provider(connection), to, subject, body, reply_id)
        except Exception as e:
            secrets_ = [str(connection["config"].get(k, "")) for k in ("password", "access_token")]
            message = str(e)
            for secret in secrets_:
                if secret:
                    message = message.replace(secret, "***")
            return f"Email Error: {message}"
        return {"status": "sent", "to": to, "subject": subject}

    async def _handle_switch(self, config, td, extra_vars=None):
        """Выбирает ветку: совпадение значения с одним из cases (точное, затем по вхождению), иначе «default»."""
        value = normalize_label(self._render_template(config.get("value", "{input}"), extra_vars))
        cases = [c.strip() for c in re.split(r"[,\n]", str(config.get("cases", ""))) if c.strip()]
        for case in cases:
            if value == normalize_label(case):
                return case
        for case in cases:
            if normalize_label(case) and normalize_label(case) in value:
                return case
        return "default"

    async def _handle_set(self, config, td, extra_vars=None):
        """Набор именованных значений: строки key=value, доступны как {set_1.key}."""
        result = {}
        for line in str(config.get("values", "")).splitlines():
            key, separator, raw = line.partition("=")
            if separator and key.strip():
                result[key.strip()] = self._render_template(raw.strip(), extra_vars)
        return result

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

            headers = loose_json(self._render_template(str(config.get("headers", "")), extra_vars)) or {}
            body = self._render_template(str(config.get("body", "")), extra_vars)
            payload = {"json": loose_json(body)} if loose_json(body) is not None else ({"content": body} if body else {})
            origin_host = httpx.URL(url).host

            async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
                for _ in range(MAX_HTTP_REDIRECTS + 1):
                    await assert_public_url(url)
                    # заголовки (например, Authorization) не уходят на другой хост при редиректе
                    hop_headers = headers if httpx.URL(url).host == origin_host else {}
                    response = await client.request(
                        "GET" if method == "GET" else "POST", url, headers={str(k): str(v) for k, v in hop_headers.items()},
                        **({} if method == "GET" else payload),
                    )
                    if response.is_redirect and response.headers.get("location"):
                        url = str(response.url.join(response.headers["location"]))
                        continue
                    break
            result = {"status_code": response.status_code, "body": response.text[:1000]}
            if len(response.text) <= MAX_HTTP_JSON_CHARS:
                try:
                    result["json"] = response.json()      # доступно как {http_1.json.field}
                except ValueError:
                    pass
            return result
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

        photo_url = self._render_template(str(config.get("photo_url", "") or ""), extra_vars).strip()
        if chat_id.startswith("https://t.me/"):
            chat_id = "@" + chat_id.rstrip("/").rsplit("/", 1)[-1]        # ссылка на публичный канал → @имя
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if photo_url:
                    try:
                        await assert_public_url(photo_url)
                    except ValueError as e:
                        return f"Telegram Error: картинка: {e}"
                    caption = text[:1024] if len(text) <= 1024 else ""
                    response = await client.post(f"https://api.telegram.org/bot{bot_token}/sendPhoto",
                                                 json={"chat_id": chat_id, "photo": photo_url, "caption": caption})
                    if response.status_code == 200 and not caption and text:       # длинный текст уходит отдельным сообщением
                        response = await client.post(f"https://api.telegram.org/bot{bot_token}/sendMessage",
                                                     json={"chat_id": chat_id, "text": text[:4096]})
                else:
                    response = await client.post(f"https://api.telegram.org/bot{bot_token}/sendMessage",
                                                 json={"chat_id": chat_id, "text": text[:4096]})
                if response.status_code in (400, 403):
                    return f"Telegram Error: {telegram_error_hint(response.text)}"
                return {"status_code": response.status_code, "body": response.text[:500]}
        except Exception as e:
            return f"Telegram Error: {str(e).replace(bot_token, '***')}"

    async def _handle_google_sheets_append(self, config, td, extra_vars=None):
        connection = self._get_connection(config.get("connection_id"))
        provider = (connection or {}).get("provider")
        if provider not in ("google_sheets", "yandex_sheets"):
            return "Sheets Error: не выбрано подключение таблиц (Подключения → Таблицы: Google или Яндекс)"
        if connection["config"].get("needs_reauth"):
            return "Sheets Error: доступ к таблицам истёк или отозван. Откройте «Подключения» и войдите заново"

        access_token = connection["config"].get("access_token")
        if not access_token:
            return "Sheets Error: нет access_token — переподключите аккаунт на странице Подключения"

        spreadsheet_id = self._render_template(config.get("spreadsheet_id", ""), extra_vars)
        raw_values = self._render_template(config.get("values", ""), extra_vars)
        row = [v.strip() for v in raw_values.split(",")] if raw_values else []

        if not spreadsheet_id:
            return "Sheets Error: не указан ID таблицы (Google) или путь к файлу на Диске (Яндекс)"

        if provider == "yandex_sheets":
            return await self._yandex_disk_csv_append(access_token, spreadsheet_id, row)

        sheet_range = config.get("range", "A1")
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

    async def _yandex_disk_csv_append(self, access_token: str, path: str, row: list):
        """Добавить строку в CSV на Яндекс Диске (скачать → дописать → загрузить обратно)."""
        import csv
        import io

        path = path.strip()
        if not path.startswith("disk:"):
            path = "disk:/" + path.lstrip("/")
        headers = {"Authorization": f"OAuth {access_token}"}
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                meta = await client.get(
                    "https://cloud-api.yandex.net/v1/disk/resources/download",
                    params={"path": path},
                    headers=headers,
                )
                if meta.status_code == 404:
                    content = ""
                elif meta.status_code != 200:
                    return f"Yandex Tables Error: не удалось получить файл ({meta.status_code}): {meta.text[:200]}"
                else:
                    href = meta.json().get("href")
                    if not href:
                        return "Yandex Tables Error: нет ссылки на скачивание"
                    dl = await client.get(href)
                    if dl.status_code != 200:
                        return f"Yandex Tables Error: скачивание не удалось ({dl.status_code})"
                    content = dl.text

                buf = io.StringIO()
                if content and not content.endswith("\n"):
                    content += "\n"
                buf.write(content)
                writer = csv.writer(buf)
                writer.writerow(row)
                new_body = buf.getvalue().encode("utf-8")

                up = await client.get(
                    "https://cloud-api.yandex.net/v1/disk/resources/upload",
                    params={"path": path, "overwrite": "true"},
                    headers=headers,
                )
                if up.status_code != 200:
                    return f"Yandex Tables Error: не удалось получить ссылку загрузки ({up.status_code}): {up.text[:200]}"
                upload_href = up.json().get("href")
                if not upload_href:
                    return "Yandex Tables Error: нет ссылки на загрузку"

                put = await client.put(upload_href, content=new_body)
                if put.status_code not in (201, 202):
                    return f"Yandex Tables Error: загрузка не удалась ({put.status_code}): {put.text[:200]}"
                return {"status_code": put.status_code, "path": path, "rows_appended": 1}
        except Exception as e:
            return f"Yandex Tables Error: {str(e)}"

    async def _handle_google_calendar_create_event(self, config, td, extra_vars=None):
        """Событие в календаре: Google (OAuth) или Яндекс (CalDAV). Тип шага один, сервис определяется выбранным подключением."""
        connection = self._get_connection(config.get("connection_id"))
        provider = (connection or {}).get("provider")
        if provider not in ("google_calendar", "yandex_calendar"):
            return "Calendar Error: не выбрано подключение календаря. Подключите Google или Яндекс в разделе «Подключения»"
        summary = self._render_template(config.get("summary", ""), extra_vars)
        description = self._render_template(config.get("description", ""), extra_vars)
        start_dt = self._render_template(config.get("start_datetime", ""), extra_vars)
        end_dt = self._render_template(config.get("end_datetime", ""), extra_vars)
        if not (start_dt and end_dt):
            return "Calendar Error: не указаны начало и конец события"

        if provider == "yandex_calendar":
            cfg = connection["config"]
            try:
                name = self._render_template(str(config.get("calendar_id", "") or ""), extra_vars).strip()
                return await caldav.create_event(cfg.get("email", ""), cfg.get("password", ""), summary, description, start_dt, end_dt,
                                                 "" if name.lower() == "primary" else name)
            except caldav.CalDAVError as e:
                return f"Calendar Error: {e}"
            except Exception:
                return "Calendar Error: не удалось связаться с Яндекс Календарём, повторите попытку"

        if connection["config"].get("needs_reauth"):
            return "Calendar Error: доступ к Google истёк или отозван. Откройте «Подключения» и войдите заново"
        access_token = connection["config"].get("access_token")
        if not access_token:
            return "Calendar Error: нет доступа к Google. Переподключите аккаунт в разделе «Подключения»"
        calendar_id = config.get("calendar_id") or "primary"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events",
                    headers={"Authorization": f"Bearer {access_token}"},
                    json={"summary": summary, "description": description, "start": {"dateTime": start_dt}, "end": {"dateTime": end_dt}},
                )
                return {"status_code": response.status_code, "body": response.text[:500]}
        except Exception as e:
            return f"Calendar Error: {str(e)}"

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
                    "parameters": prepare_tool_schema(tconf.get("tool_parameters")),
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
        """Подставляет {name} и {name.path.to.field} за один проход; неизвестные плейсхолдеры остаются как есть."""
        variables = dict(self.context)
        if extra_vars:
            variables.update(extra_vars)

        def replace(match):
            name, path = match.group(1), match.group(2)
            if name not in variables:
                return match.group(0)
            found, value = (True, variables[name]) if not path else resolve_path(variables[name], path)
            return render_value(value) if found else match.group(0)

        return PLACEHOLDER_RE.sub(replace, template)
