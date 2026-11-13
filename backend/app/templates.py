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


def _transform(node_id: str, operation: str, x: int, y: int, value: str = "{input}") -> dict:
    return {"id": node_id, "type": "text_transform", "position": {"x": x, "y": y},
            "config": {"operation": operation, "value": value, "pattern": "", "max_chars": 500}}







def _edge(source: str, target: str, condition: str | None = None) -> dict:
    edge = {"id": f"{source}__{target}" + (f"__{condition}" if condition else ""), "from_node": source, "to_node": target, "type": "next"}
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
        "is_active": False,
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
        "is_active": False,
    },

    "meeting_summary": {
        "name": "Саммари встречи + action items",
        "description": "Ручной запуск: вставьте текст встречи (или загрузите файл) в ноду «Текст» и нажмите Run",
        "nodes": [
            {"id": "trigger", "type": "manual", "position": {"x": 80, "y": 140}, "config": {}},
            {"id": "meeting_text", "type": "text_input", "position": {"x": 400, "y": 140}, "config": {
                "file_name": "",
                "text": "Иван: релиз переносим на пятницу. Мария: тогда я до среды подготовлю тексты для рассылки. "
                        "Иван: договор с подрядчиком нужно отправить юристам до вторника. Пётр: возьму на себя тесты."}},
            _llm("summary", "Сделай саммари встречи (3–5 предложений), затем список action items в формате «Ответственный — задача — срок».\n\nТекст встречи:\n{meeting_text}", 720, 140, 0.3),
            {"id": "output", "type": "print", "position": {"x": 1040, "y": 140}, "config": {"value": "{summary}"}},
        ],
        "edges": [_edge("trigger", "meeting_text"), _edge("meeting_text", "summary"), _edge("summary", "output")],
        "is_active": False,
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
        "is_active": False,
    },

    "request_router": {
        "name": "Классификатор обращений",
        "description": "Определяет тип обращения (поддержка / продажа / жалоба / другое), отвечает по типу и ведёт журнал обращений в Google Таблице",
        "nodes": [
            _telegram_trigger(80, 280, "Заказ №4512 пришёл с браком, верните деньги!"),
            _llm("classify", "Определи тип обращения. Ответь ОДНИМ словом из списка: support, sales, complaint, other. Слово other — для всего, что не подходит под остальные типы.\n\nОбращение:\n{input}", 400, 280, 0.0),
            {"id": "route", "type": "switch", "position": {"x": 720, "y": 280}, "config": {"value": "{classify}", "cases": "support, sales, complaint, other"}},
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
            _edge("route", "reply_complaint", "complaint"), _edge("route", "reply_other", "other"), _edge("route", "reply_other", "default"),   # default — страховка, если модель ответила не по списку
            _edge("reply_support", "send_reply"), _edge("reply_sales", "send_reply"),
            _edge("reply_complaint", "send_reply"), _edge("reply_other", "send_reply"),
            _edge("send_reply", "log_request"),
        ],
        "is_active": False,
    },

    "faq_bot": {
        "name": "Ответы на частые вопросы",
        "description": "Бот в Telegram отвечает клиентам строго по вашей базе знаний (график работы, цены, доставка). Замените текст в шаге «База знаний» на свой",
        "nodes": [
            _telegram_trigger(80, 140, "Во сколько вы работаете в субботу?"),
            {"id": "knowledge", "type": "text_input", "position": {"x": 400, "y": 140}, "config": {
                "file_name": "",
                "text": "График работы: пн–пт с 9:00 до 19:00, сб с 10:00 до 16:00, воскресенье — выходной.\n"
                        "Доставка по городу — 300 ₽, бесплатно от 5000 ₽. Оплата картой или наличными.\n"
                        "Возврат возможен в течение 14 дней при сохранении товарного вида."}},
            _llm("answer", "Вы — помощник компании. Отвечайте вежливо и кратко, ТОЛЬКО на основе базы знаний. "
                           "Если ответа в базе нет, скажите, что передадите вопрос менеджеру.\n\nБаза знаний:\n{knowledge}\n\nВопрос клиента:\n{input}", 720, 140, 0.2),
            _send("send_reply", "{answer}", 1040, 140),
        ],
        "edges": [_edge("trigger", "knowledge"), _edge("knowledge", "answer"), _edge("answer", "send_reply")],
        "is_active": False,
    },

    "order_request": {
        "name": "Приём обращений по заказу",
        "description": "Находит в сообщении номер заказа и телефон без нейросети, записывает обращение в Google Таблицу и подтверждает клиенту",
        "nodes": [
            _telegram_trigger(80, 140, "Где мой заказ? Номер 1234, звоните на 8 900 111-22-33"),
            _transform("order_number", "extract_order", 400, 140),
            _transform("phone", "extract_phone", 720, 140),
            _sheets("save_request", "{order_number}, {phone}, {telegram_username}, {input}", 1040, 140),
            _send("send_reply", "Спасибо! Обращение по заказу {order_number} принято, менеджер свяжется с Вами.", 1360, 140),
        ],
        "edges": [_edge("trigger", "order_number"), _edge("order_number", "phone"), _edge("phone", "save_request"), _edge("save_request", "send_reply")],
        "is_active": False,
    },

    "email_support": {
        "name": "Ответы на входящие письма",
        "description": "Читает новые письма в подключённой почте, готовит вежливый ответ и отправляет его отправителю. Нужна подключённая почта",
        "nodes": [
            {"id": "trigger", "type": "email_trigger", "position": {"x": 80, "y": 140}, "config": {
                "connection_id": None, "interval_minutes": 5,
                "test_input": "Добрый день! Подскажите, можно ли изменить адрес доставки заказа 5521?", "test_from": "client@example.com", "test_subject": "Вопрос по заказу"}},
            _llm("reply", "Вы — служба поддержки компании. Напишите деловой, вежливый и краткий ответ на письмо клиента на языке письма. Без темы и подписи.\n\nТема: {email_subject}\n\nПисьмо:\n{input}", 400, 140, 0.3),
            {"id": "send_mail", "type": "email_send", "position": {"x": 720, "y": 140}, "config": {
                "connection_id": None, "to": "{email_from}", "subject": "Re: {email_subject}", "body": "{reply}\n\nС уважением, служба поддержки", "as_reply": True}},
        ],
        "edges": [_edge("trigger", "reply"), _edge("reply", "send_mail")],
        "is_active": False,
    },

    # ───────── почта ─────────

    "email_leads": {
        "name": "Заявки с почты: в таблицу и автоответ",
        "description": "Новое письмо → находит телефон и номер заказа без нейросети → строка в Google Таблице → автоответ клиенту. Нужны подключения: почта и Google Таблицы",
        "nodes": [
            {"id": "trigger", "type": "email_trigger", "position": {"x": 80, "y": 140}, "config": {
                "connection_id": None, "interval_minutes": 5, "test_from": "client@example.com", "test_subject": "Вопрос по заказу",
                "test_input": "Добрый день! Где мой заказ 5521? Мой телефон 8 900 111-22-33."}},
            _transform("phone", "extract_phone", 400, 140),
            _transform("order_number", "extract_order", 720, 140),
            _sheets("save_request", "{email_from}, {email_subject}, {phone}, {order_number}", 1040, 140),
            {"id": "autoreply", "type": "email_send", "position": {"x": 1360, "y": 140}, "config": {
                "connection_id": None, "to": "{email_from}", "subject": "Re: {email_subject}", "as_reply": True,
                "body": "Здравствуйте! Мы получили Ваше обращение и ответим в ближайшее время.\n\nС уважением, команда поддержки"}},
        ],
        "edges": [_edge("trigger", "phone"), _edge("phone", "order_number"), _edge("order_number", "save_request"), _edge("save_request", "autoreply")],
        "is_active": False,
    },

    "email_router": {
        "name": "Сортировка писем по темам",
        "description": "Определяет тему письма (поддержка, продажи, жалоба, другое), готовит ответ нужного тона и отправляет его. Нужна подключённая почта",
        "nodes": [
            {"id": "trigger", "type": "email_trigger", "position": {"x": 80, "y": 280}, "config": {
                "connection_id": None, "interval_minutes": 5, "test_from": "client@example.com", "test_subject": "Заказ с браком",
                "test_input": "Заказ №4512 пришёл с браком. Верните деньги."}},
            _llm("classify", "Определите тип письма. Ответьте ОДНИМ словом из списка: support, sales, complaint, other. Слово other — для всего остального.\n\nПисьмо:\n{input}", 400, 280, 0.0),
            {"id": "route", "type": "switch", "position": {"x": 720, "y": 280}, "config": {"value": "{classify}", "cases": "support, sales, complaint, other"}},
            _llm("reply_support", "Вы — служба поддержки. Напишите деловой, вежливый и краткий ответ с решением вопроса. Без темы и подписи.\n\nПисьмо:\n{input}", 1040, 100),
            _llm("reply_sales", "Вы — менеджер по продажам. Поблагодарите за интерес, ответьте по существу и предложите следующий шаг. Без темы и подписи.\n\nПисьмо:\n{input}", 1040, 240),
            _llm("reply_complaint", "Вы — менеджер по работе с жалобами. Извинитесь, покажите, что понимаете проблему, и предложите решение. Без темы и подписи.\n\nПисьмо:\n{input}", 1040, 380),
            _llm("reply_other", "Вежливо ответьте на письмо и уточните, чем можете помочь. Без темы и подписи.\n\nПисьмо:\n{input}", 1040, 520),
            {"id": "send_mail", "type": "email_send", "position": {"x": 1360, "y": 280}, "config": {
                "connection_id": None, "to": "{email_from}", "subject": "Re: {email_subject}", "as_reply": True,
                "body": "{reply_support}{reply_sales}{reply_complaint}{reply_other}\n\nС уважением, команда компании"}},
        ],
        "edges": [
            _edge("trigger", "classify"), _edge("classify", "route"),
            _edge("route", "reply_support", "support"), _edge("route", "reply_sales", "sales"), _edge("route", "reply_complaint", "complaint"),
            _edge("route", "reply_other", "other"), _edge("route", "reply_other", "default"),
            _edge("reply_support", "send_mail"), _edge("reply_sales", "send_mail"), _edge("reply_complaint", "send_mail"), _edge("reply_other", "send_mail"),
        ],
        "is_active": False,
    },
}
