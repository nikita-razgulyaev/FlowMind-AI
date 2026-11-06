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
    assert set(TEMPLATES) == {"telegram_support", "lead_to_sheets", "meeting_summary", "lead_qualification", "request_router"}
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
