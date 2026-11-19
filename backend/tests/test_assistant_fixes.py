from app.services.ai_assistant import _fix_references
from app.services.llm import _is_empty_message


def test_fix_references_matches_real_node_ids():
    nodes = [{"id": "http1", "type": "http", "config": {}},
             {"id": "switch_2", "type": "switch", "config": {}},
             {"id": "llm3", "type": "llm", "config": {
                 "prompt": "Курс {http_1.rates.RUB}, ветка {Switch2}, вход {input}, ответ {llm3}, {unknown}"}}]
    _fix_references(nodes)
    assert nodes[2]["config"]["prompt"] == "Курс {http1.rates.RUB}, ветка {switch_2}, вход {input}, ответ {llm3}, {unknown}"


def test_empty_message_detection():
    assert _is_empty_message({"content": None})
    assert _is_empty_message({"content": "  "})
    assert not _is_empty_message({"content": "ok"})
    assert not _is_empty_message({"content": None, "tool_calls": [{"id": "1"}]})


# ───────── шаги без нейросети ─────────
import asyncio

from app.services import textops
from app.worker import WorkflowEngine


def run_node(node_type, config, context=None, text="Где мой заказ 1234?"):
    step = {"id": "n1", "type": node_type, "config": config}
    engine = WorkflowEngine({"nodes": [step], "edges": []}, 0)
    engine.context = {**(context or {}), "input": text}
    output = asyncio.run(engine._execute_node(step, {"input": text}))
    engine._register_branch(step, output)
    return output, engine.branches.get("n1")


def test_condition_rules_all_and_any():
    rules = [{"value": "{input}", "operator": "contains", "expected": "заказ"},
             {"value": "{n0}", "operator": "gt", "expected": "5"}]
    assert run_node("condition", {"mode": "rules", "rules": rules}, {"n0": "7,5"})[1] == "true"
    assert run_node("condition", {"mode": "rules", "rules": rules}, {"n0": "3"})[1] == "false"
    assert run_node("condition", {"mode": "rules", "match": "any", "rules": rules}, {"n0": "3"})[1] == "true"
    assert run_node("condition", {"mode": "rules", "rules": [{"value": "{input}", "operator": "empty"}]}, text="")[1] == "true"


def test_keyword_switch_picks_first_matching_category():
    cfg = {"value": "{input}", "rules": "доставка: трек, где мой заказ\nоплата: оплата, счёт", "default_label": "другое"}
    assert run_node("keyword_switch", cfg)[0] == "доставка"
    assert run_node("keyword_switch", cfg, text="Не проходит оплата!")[0] == "оплата"
    assert run_node("keyword_switch", cfg, text="Привет")[1] == "другое"


def test_text_assemble_and_new_text_operations():
    assert run_node("text_assemble", {"template": "Заказ {n0} принят"}, {"n0": "1234"})[0] == "Заказ 1234 принят"
    assert textops.apply_operation("replace", "a-b-c", "-", 500, " ") == "a b c"
    assert textops.apply_operation("capitalize", "  привет мир") == "Привет мир"
    assert textops.apply_operation("title_case", "иван ПЕТРОВ") == "Иван Петров"
    assert textops.apply_operation("extract_number", "Итого 12 500,50 руб") == "12500.50"
    assert textops.apply_operation("one_line", "а\n  б\n\nв") == "а б в"
    assert len(textops.apply_operation("today", "")) == 10
