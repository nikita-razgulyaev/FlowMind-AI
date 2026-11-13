"""Движок: ветвление Condition/Switch, пути {node.field}, Set, тестовые данные триггера, шаблоны."""
import asyncio

from app.templates import TEMPLATES
from app.worker import WorkflowEngine


class FakeLLM:
    def __init__(self, answers: dict):
        self.answers = answers

    async def generate(self, prompt, *args, **kwargs):
        for marker, answer in self.answers.items():
            if marker in prompt:
                return answer
        return "ok"


def run(workflow: dict, answers: dict | None = None, trigger: dict | None = None) -> WorkflowEngine:
    engine = WorkflowEngine(workflow, 1)
    engine.llm = FakeLLM(answers or {})
    asyncio.run(engine.execute(trigger if trigger is not None else {"input": "привет"}))
    return engine


def edge(a, b, condition=None):
    return {"id": f"{a}-{b}", "from_node": a, "to_node": b, **({"condition": condition} if condition else {})}


def test_condition_runs_only_selected_branch():
    wf = {"nodes": [
        {"id": "t", "type": "manual", "config": {}},
        {"id": "c", "type": "condition", "config": {"expression": "len(input) > 3"}},
        {"id": "yes", "type": "print", "config": {"value": "Y"}},
        {"id": "no", "type": "print", "config": {"value": "N"}},
        {"id": "end", "type": "print", "config": {"value": "{yes}{no}"}},
    ], "edges": [edge("t", "c"), edge("c", "yes", "true"), edge("c", "no", "false"), edge("yes", "end"), edge("no", "end")]}
    ctx = run(wf).context
    assert (ctx["yes"], ctx["no"], ctx["end"]) == ("Y", "", "Y")
    assert run(wf, trigger={"input": "ab"}).context["end"] == "N"


def test_switch_routes_by_llm_answer_and_default():
    wf = {"nodes": [
        {"id": "t", "type": "manual", "config": {}},
        {"id": "cls", "type": "llm", "config": {"prompt": "classify {input}"}},
        {"id": "sw", "type": "switch", "config": {"value": "{cls}", "cases": "support, sales"}},
        {"id": "a", "type": "print", "config": {"value": "A"}},
        {"id": "b", "type": "print", "config": {"value": "B"}},
        {"id": "d", "type": "print", "config": {"value": "D"}},
    ], "edges": [edge("t", "cls"), edge("cls", "sw"), edge("sw", "a", "support"), edge("sw", "b", "sales"), edge("sw", "d", "default")]}
    assert run(wf, {"classify": "Sales."}).context["b"] == "B"
    assert run(wf, {"classify": "support"}).context["a"] == "A"
    ctx = run(wf, {"classify": "other"}).context
    assert (ctx["a"], ctx["b"], ctx["d"]) == ("", "", "D")


def test_legacy_condition_edges_without_label_still_run_everything():
    wf = {"nodes": [{"id": "t", "type": "manual", "config": {}}, {"id": "c", "type": "condition", "config": {"expression": "False"}},
                    {"id": "p", "type": "print", "config": {"value": "ran"}}], "edges": [edge("t", "c"), edge("c", "p")]}
    assert run(wf).context["p"] == "ran"


def test_json_paths_and_set_node():
    wf = {"nodes": [
        {"id": "t", "type": "manual", "config": {}},
        {"id": "ex", "type": "llm", "config": {"prompt": "extract"}},
        {"id": "s", "type": "set", "config": {"values": "who={ex.name}\nscore={ex.score}"}},
        {"id": "c", "type": "condition", "config": {"expression": "{ex.score} >= 7"}},
        {"id": "p", "type": "print", "config": {"value": "{s.who}:{s.score}:{ex.missing}"}},
    ], "edges": [edge("t", "ex"), edge("ex", "s"), edge("s", "c"), edge("c", "p", "true")]}
    ctx = run(wf, {"extract": 'Вот JSON: {"name": "Анна", "score": 8}'}).context
    assert ctx["s"] == {"who": "Анна", "score": "8"} and ctx["p"] == "Анна:8:{ex.missing}"


def test_run_button_uses_trigger_test_input_but_real_triggers_do_not():
    wf = {"nodes": [{"id": "t", "type": "manual", "config": {"test_input": "демо"}},
                    {"id": "p", "type": "print", "config": {"value": "[{input}]"}}], "edges": [edge("t", "p")]}
    assert run(wf, trigger={"input": ""}).context["p"] == "[демо]"
    assert run(wf, trigger={"input": "", "webhook": {"body": {}}}).context["p"] == "[]"


def test_templates_are_valid_graphs():
    assert set(TEMPLATES) == {"telegram_support", "lead_to_sheets", "meeting_summary", "lead_qualification", "request_router",
                              "faq_bot", "order_request", "email_support", "email_leads", "email_router"}
    for key, tpl in TEMPLATES.items():
        ids = {n["id"] for n in tpl["nodes"]}
        assert len(ids) == len(tpl["nodes"]), key
        assert all(e["from_node"] in ids and e["to_node"] in ids for e in tpl["edges"]), key


def test_meeting_summary_template_runs_without_input():
    tpl = TEMPLATES["meeting_summary"]
    ctx = run({"nodes": tpl["nodes"], "edges": tpl["edges"]}, {"Текст встречи": "САММАРИ"}, trigger={"input": ""}).context
    assert ctx["output"] == "САММАРИ" and "релиз переносим" in ctx["meeting_text"]


def test_request_router_template_routes_complaint():
    tpl = TEMPLATES["request_router"]
    wf = {"nodes": tpl["nodes"], "edges": tpl["edges"]}
    ctx = run(wf, {"Определи тип": "complaint", "менеджер по работе с жалобами": "Извините!"},
              trigger={"input": "брак", "telegram": {"chat_id": 1, "text": "брак"}}).context
    assert ctx["reply_complaint"] == "Извините!" and ctx["reply_support"] == "" and ctx["send_reply"]


def test_progress_reports_running_done_skipped_failed():
    events = []
    wf = {"nodes": [
        {"id": "t", "type": "manual", "config": {}},
        {"id": "c", "type": "condition", "config": {"expression": "False"}},
        {"id": "yes", "type": "print", "config": {"value": "Y"}},
        {"id": "no", "type": "http", "config": {"url": "ftp://bad"}},
    ], "edges": [edge("t", "c"), edge("c", "yes", "true"), edge("c", "no", "false")]}
    engine = WorkflowEngine(wf, 1, on_progress=lambda n, st, ms: events.append((n, st)))
    asyncio.run(engine.execute({"input": "x"}))
    assert events == [("t", "running"), ("t", "done"), ("c", "running"), ("c", "done"),
                      ("yes", "skipped"), ("no", "running"), ("no", "failed")]


def test_request_router_normalizes_model_answer_and_uses_other_branch():
    tpl = TEMPLATES["request_router"]
    wf = {"nodes": tpl["nodes"], "edges": tpl["edges"]}
    trig = {"input": "привет", "telegram": {"chat_id": 1, "text": "привет"}}
    assert run(wf, {"Определи тип": "Support.", "Ты — поддержка": "Помогу"}, trigger=trig).context["reply_support"] == "Помогу"
    ctx = run(wf, {"Определи тип": "other", "Вежливо ответь": "Чем помочь?"}, trigger=trig).context
    assert ctx["reply_other"] == "Чем помочь?" and ctx["reply_support"] == ""
    ctx = run(wf, {"Определи тип": "что-то странное", "Вежливо ответь": "Чем помочь?"}, trigger=trig).context
    assert ctx["reply_other"] == "Чем помочь?"      # страховка default


def test_order_request_template_extracts_order_and_phone():
    tpl = TEMPLATES["order_request"]
    wf = {"nodes": tpl["nodes"], "edges": tpl["edges"]}
    ctx = run(wf, trigger={"input": "Где мой заказ? Номер 1234, звоните 8 900 111-22-33",
                           "telegram": {"chat_id": 1, "text": "x", "username": "anna"}}).context
    assert ctx["order_number"] == "1234" and ctx["phone"] == "+79001112233"


def test_text_transform_node_operations():
    wf = {"nodes": [
        {"id": "t", "type": "manual", "config": {}},
        {"id": "o", "type": "text_transform", "config": {"operation": "extract_order", "value": "{input}"}},
        {"id": "e", "type": "text_transform", "config": {"operation": "extract_email", "value": "{input}"}},
        {"id": "r", "type": "text_transform", "config": {"operation": "extract_regex", "value": "{input}", "pattern": r"код (\w+)"}},
        {"id": "n", "type": "text_transform", "config": {"operation": "normalize", "value": "Support."}},
        {"id": "bad", "type": "text_transform", "config": {"operation": "nope", "value": "x"}},
    ], "edges": [edge("t", "o"), edge("o", "e"), edge("e", "r"), edge("r", "n"), edge("n", "bad")]}
    ctx = run(wf, trigger={"input": "Статус заказа №1234 от 05.11.26, пишите a.b@mail.ru, код XY7"}).context
    assert (ctx["o"], ctx["e"], ctx["r"], ctx["n"]) == ("1234", "a.b@mail.ru", "XY7", "support")
    assert ctx["bad"].startswith("Text Error")


def test_email_send_node_checks_connection_and_sends(monkeypatch):
    from app.services import email_service
    sent = []

    async def fake_send(cfg, to, subject, body, reply_to_id=""):
        sent.append((cfg["email"], to, subject, body, reply_to_id))

    monkeypatch.setattr(email_service, "send_message", fake_send)
    wf = {"nodes": [
        {"id": "t", "type": "email_trigger", "config": {"test_input": "Нужна помощь", "test_from": "client@example.com", "test_subject": "Вопрос"}},
        {"id": "m", "type": "email_send", "config": {"connection_id": 7, "to": "{email_from}", "subject": "Re: {email_subject}", "body": "Ответ: {input}"}},
    ], "edges": [edge("t", "m")]}
    engine = WorkflowEngine(wf, 1, connections={7: {"provider": "email", "config": {"email": "shop@mail.ru", "password": "pw"}}})
    engine.llm = FakeLLM({})
    asyncio.run(engine.execute({"input": ""}))
    assert engine.context["m"] == {"status": "sent", "to": "client@example.com", "subject": "Re: Вопрос"}
    assert sent == [("shop@mail.ru", "client@example.com", "Re: Вопрос", "Ответ: Нужна помощь", "")]
    assert run({"nodes": [{"id": "t", "type": "manual", "config": {}}, {"id": "m", "type": "email_send", "config": {"to": "a@b.ru"}}],
                "edges": [edge("t", "m")]}).context["m"].startswith("Email Error")


def test_email_trigger_context_from_real_letter():
    wf = {"nodes": [{"id": "t", "type": "email_trigger", "config": {}},
                    {"id": "p", "type": "print", "config": {"value": "{email_from}|{email_subject}|{email_body}"}}], "edges": [edge("t", "p")]}
    letter = {"from": "x@y.ru", "from_name": "Иван", "subject": "Тема", "body": "Текст", "message_id": "<1@y>"}
    ctx = run(wf, trigger={"input": "Тема\n\nТекст", "email": letter}).context
    assert ctx["p"] == "x@y.ru|Тема|Текст"


def test_tool_schema_examples_move_into_description():
    from app.worker import prepare_tool_schema
    schema = {"type": "object", "properties": {"order_id": {"type": "string", "description": "ID заказа", "examples": ["1234", "№1234 от 05.11.26"]}},
              "required": ["order_id", "ghost"]}
    out = prepare_tool_schema(schema)
    prop = out["properties"]["order_id"]
    assert "examples" not in prop and "«1234»" in prop["description"] and "№1234 от 05.11.26" in prop["description"]
    assert out["required"] == ["order_id"]
    assert prepare_tool_schema("мусор") == {"type": "object", "properties": {}, "required": []}
