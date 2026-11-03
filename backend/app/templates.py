"""Готовые сценарии. Telegram/Sheets-ноды без connection_id — подключение выбирается в панели ноды."""


def _llm(node_id: str, prompt: str, x: int, y: int, temperature: float = 0.4) -> dict:
    return {"id": node_id, "type": "llm", "position": {"x": x, "y": y},
            "config": {"model": "", "prompt": prompt, "temperature": temperature, "mode": "cloud"}}


def _telegram_trigger(x: int, y: int, test_input: str) -> dict:
    return {"id": "trigger", "type": "telegram_trigger", "position": {"x": x, "y": y},
            "config": {"allowed_chat_ids": "", "only_commands": False, "test_input": test_input, "test_chat_id": ""}}


def _send(node_id: str, message: str, x: int, y: int) -> dict:
    return {"id": node_id, "type": "telegram_send", "position": {"x": x, "y": y},
            "config": {"chat_id": "", "message": message}}


def _sheets(node_id: str, values: str, x: int, y: int) -> dict:
    return {"id": node_id, "type": "google_sheets_append", "position": {"x": x, "y": y},
            "config": {"spreadsheet_id": "", "range": "A1", "values": values}}


def _edge(source: str, target: str, condition: str | None = None) -> dict:
    edge = {"id": f"{source}__{target}", "from_node": source, "to_node": target, "type": "next"}
    if condition:
        edge["condition"] = condition
    return edge


EXTRACT_RULES = "Ответь ТОЛЬКО JSON-объектом без пояснений и markdown. Значения без запятых; если данных нет — пустая строка."

TEMPLATES = {
    "telegram_support": {
        "name": "Telegram-бот поддержки",
        "description": "Отвечает клиентам в Telegram вежливо и по делу на каждое сообщение боту",
        "nodes": [
            _telegram_trigger(80, 140, "Здравствуйте! Как оформить возврат товара?"),
            _llm("reply", "Ты — вежливая служба поддержки компании. Ответь кратко (до 5 предложений) на языке клиента.\n\nСообщение клиента:\n{input}", 400, 140),
            _send("send_reply", "{reply}", 720, 140),
        ],
        "edges": [_edge("trigger", "reply"), _edge("reply", "send_reply")],
        "is_active": True,
    },

    "lead_to_sheets": {
        "name": "Запись лида в Google Sheets",
        "description": "Достаёт имя, контакт и потребность из сообщения, добавляет строку в таблицу и подтверждает клиенту",
        "nodes": [
            _telegram_trigger(80, 140, "Привет, я Анна, мой телефон +7 900 111-22-33. Нужен сайт для кофейни."),
            _llm("extract", f'Из сообщения клиента извлеки данные. {EXTRACT_RULES}\nФормат: {{"name": "", "contact": "", "need": ""}}\n\nСообщение:\n{{input}}', 400, 140, 0.1),
            _sheets("save_lead", "{extract.name}, {extract.contact}, {extract.need}", 720, 140),
            _send("send_reply", "Спасибо! Мы получили вашу заявку и скоро свяжемся.", 1040, 140),
        ],
        "edges": [_edge("trigger", "extract"), _edge("extract", "save_lead"), _edge("save_lead", "send_reply")],
        "is_active": True,
    },

    "meeting_summary": {
        "name": "Саммари встречи + action items",
        "description": "Ручной запуск: вставьте текст встречи в Manual Trigger (поле «Тестовые данные») и нажмите Run",
        "nodes": [
            {"id": "trigger", "type": "manual", "position": {"x": 80, "y": 140}, "config": {
                "test_input": "Иван: релиз переносим на пятницу. Мария: тогда я до среды подготовлю тексты для рассылки. "
                              "Иван: договор с подрядчиком нужно отправить юристам до вторника. Пётр: возьму на себя тесты."}},
            _llm("summary", "Сделай саммари встречи (3–5 предложений), затем список action items в формате «Ответственный — задача — срок».\n\nТекст встречи:\n{input}", 400, 140, 0.3),
            {"id": "output", "type": "print", "position": {"x": 720, "y": 140}, "config": {"value": "{summary}"}},
        ],
        "edges": [_edge("trigger", "summary"), _edge("summary", "output")],
        "is_active": True,
    },

    "lead_qualification": {
        "name": "Квалификация лида",
        "description": "Извлекает данные и оценивает лид 1–10, пишет в Sheets; горячим и тёплым лидам — разные ответы (ветвление)",
        "nodes": [
            _telegram_trigger(80, 220, "Мы IT-компания, 50 человек, бюджет 500 тысяч, нужна CRM на этой неделе. Пишет Олег."),
            _llm("extract", f'Проанализируй обращение. {EXTRACT_RULES}\nФормат: {{"name": "", "company": "", "budget": "", "urgency": "", "score": 1}}\n'
                            "score — целое от 1 до 10: насколько лид готов купить (бюджет, срочность, конкретность).\n\nОбращение:\n{input}", 400, 220, 0.1),
            _sheets("save_lead", "{extract.name}, {extract.company}, {extract.budget}, {extract.urgency}, {extract.score}", 720, 220),
            {"id": "is_hot", "type": "condition", "position": {"x": 1040, "y": 220}, "config": {"expression": "{extract.score} >= 7"}},
            _llm("reply_hot", "Клиент — горячий лид ({extract.name}, {extract.company}). Напиши короткий ответ: поблагодари, предложи созвониться сегодня и спроси удобное время.\n\nОбращение:\n{input}", 1360, 100),
            _llm("reply_warm", "Клиент — тёплый лид. Напиши короткий ответ: поблагодари, задай 1–2 уточняющих вопроса о задаче и сроках.\n\nОбращение:\n{input}", 1360, 340),
            _send("send_reply", "{reply_hot}{reply_warm}", 1680, 220),
        ],
        "edges": [
            _edge("trigger", "extract"), _edge("extract", "save_lead"), _edge("save_lead", "is_hot"),
            _edge("is_hot", "reply_hot", "true"), _edge("is_hot", "reply_warm", "false"),
            _edge("reply_hot", "send_reply"), _edge("reply_warm", "send_reply"),
        ],
        "is_active": True,
    },

    "request_router": {
        "name": "Классификатор обращений",
        "description": "Определяет тип обращения (поддержка / продажа / жалоба / другое), отвечает по типу и ведёт лог в Sheets",
        "nodes": [
            _telegram_trigger(80, 280, "Заказ №4512 пришёл с браком, верните деньги!"),
            _llm("classify", "Определи тип обращения. Ответь ОДНИМ словом из списка: support, sales, complaint, other.\n\nОбращение:\n{input}", 400, 280, 0.0),
            {"id": "route", "type": "switch", "position": {"x": 720, "y": 280}, "config": {"value": "{classify}", "cases": "support, sales, complaint"}},
            _llm("reply_support", "Ты — поддержка. Дай полезный краткий ответ на вопрос клиента.\n\n{input}", 1040, 40),
            _llm("reply_sales", "Ты — менеджер по продажам. Ответь дружелюбно, расскажи, чем можешь помочь, и предложи следующий шаг.\n\n{input}", 1040, 220),
            _llm("reply_complaint", "Ты — менеджер по работе с жалобами. Извинись, покажи, что понял проблему, пообещай разобраться и вернуться в течение суток.\n\n{input}", 1040, 400),
            _llm("reply_other", "Вежливо ответь на сообщение и уточни, чем можешь помочь.\n\n{input}", 1040, 580),
            _send("send_reply", "{reply_support}{reply_sales}{reply_complaint}{reply_other}", 1360, 280),
            _sheets("log_request", "{classify}, {telegram_username}, {input}", 1680, 280),
        ],
        "edges": [
            _edge("trigger", "classify"), _edge("classify", "route"),
            _edge("route", "reply_support", "support"), _edge("route", "reply_sales", "sales"),
            _edge("route", "reply_complaint", "complaint"), _edge("route", "reply_other", "default"),
            _edge("reply_support", "send_reply"), _edge("reply_sales", "send_reply"),
            _edge("reply_complaint", "send_reply"), _edge("reply_other", "send_reply"),
            _edge("send_reply", "log_request"),
        ],
        "is_active": True,
    },
}
