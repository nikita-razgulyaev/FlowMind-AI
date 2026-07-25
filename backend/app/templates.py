TEMPLATES = {
    "email_responder": {
        "name": "AI Email Responder",
        "description": "Автоматические ответы на письма",
        "nodes": [
            {"id": "trigger_1", "type": "manual", "config": {}},
            {"id": "llm_1", "type": "llm", "config": {
                "model": "Qwen/Qwen2.5-1.5B-Instruct",
                "prompt": "Ты — поддержка компании. Ответь кратко и вежливо на:\n\n{input}",
                "temperature": 0.5,
                "mode": "cloud"
            }},
            {"id": "output_1", "type": "print", "config": {"value": "Ответ: {llm_1}"}}
        ],
        "edges": [
            {"id": "edge_1", "from_node": "trigger_1", "to_node": "llm_1"},
            {"id": "edge_2", "from_node": "llm_1", "to_node": "output_1"}
        ],
        "is_active": True
    },

    "news_summarizer": {
        "name": "Саммари новостей",
        "description": "Получает URL, возвращает краткое содержание",
        "nodes": [
            {"id": "trigger_1", "type": "manual", "config": {}},
            {"id": "http_1", "type": "http", "config": {
                "method": "GET",
                "url": "{input}"
            }},
            {"id": "llm_1", "type": "llm", "config": {
                "model": "Qwen/Qwen2.5-1.5B-Instruct",
                "prompt": "Сделай краткое саммари (3 предложения):\n\n{http_1}",
                "temperature": 0.3,
                "mode": "cloud"
            }},
            {"id": "output_1", "type": "print", "config": {"value": "{llm_1}"}}
        ],
        "edges": [
            {"id": "edge_1", "from_node": "trigger_1", "to_node": "http_1"},
            {"id": "edge_2", "from_node": "http_1", "to_node": "llm_1"},
            {"id": "edge_3", "from_node": "llm_1", "to_node": "output_1"}
        ],
        "is_active": True
    },

    "weather_advisor": {
        "name": "Погодный советник",
        "description": "Получает погоду, даёт совет по одежде",
        "nodes": [
            {"id": "trigger_1", "type": "manual", "config": {}},
            {"id": "http_1", "type": "http", "config": {
                "method": "GET",
                "url": "https://api.open-meteo.com/v1/forecast?latitude=55.75&longitude=37.62&current=temperature"
            }},
            {"id": "llm_1", "type": "llm", "config": {
                "model": "Qwen/Qwen2.5-1.5B-Instruct",
                "prompt": "Температура: {http_1}. Что надеть? Ответь в 1 предложении.",
                "temperature": 0.8,
                "mode": "cloud"
            }},
            {"id": "output_1", "type": "print", "config": {"value": "{llm_1}"}}
        ],
        "edges": [
            {"id": "edge_1", "from_node": "trigger_1", "to_node": "http_1"},
            {"id": "edge_2", "from_node": "http_1", "to_node": "llm_1"},
            {"id": "edge_3", "from_node": "llm_1", "to_node": "output_1"}
        ],
        "is_active": True
    }
}