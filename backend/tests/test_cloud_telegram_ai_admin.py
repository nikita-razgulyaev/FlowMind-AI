import json
import time

import pytest

from app.services import telegram_service as tg
from tests.conftest import TEST_MODE, ai_workflow, register, run, simple_workflow

pytestmark = pytest.mark.skipif(TEST_MODE != "cloud", reason="cloud only")

BOT_TOKEN = "123456789:AAFakeTokenForTestsOnly_abcdefghijk"


def bot_connection(s, name="bot"):
    r = s.post("/connections", json={"category": "tool", "provider": "telegram_bot", "name": name, "config": {"bot_token": BOT_TOKEN}})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def telegram_workflow(conn_id, name="tg", extra_cfg=None):
    return {"name": name, "description": "", "is_active": True,
            "nodes": [{"id": "trg", "type": "telegram_trigger", "config": {"connection_id": conn_id, **(extra_cfg or {})}},
                      {"id": "say", "type": "telegram_send", "config": {"connection_id": conn_id, "chat_id": "", "message": "Вы написали: {input} от {telegram_username}"}}],
            "edges": [{"id": "e1", "from_node": "trg", "to_node": "say", "type": "next"}]}


_BASE = {"n": 0}


@pytest.fixture(autouse=True)
def _fresh_update_ids():
    _BASE["n"] += 1000          # update_id уникален для бота; тесты используют один и тот же токен
    yield


def update(update_id, text="Привет", chat_id=555, username="ivan"):
    return {"update_id": _BASE["n"] + update_id, "message": {"message_id": 1, "text": text, "chat": {"id": chat_id},
                                                  "from": {"id": chat_id, "username": username, "first_name": "Иван"}}}


def wait_for(fn, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        value = fn()
        if value:
            return value
        time.sleep(0.05)
    return None


def hook(client, conn_id, upd, secret=None):
    return client.post(f"/api/telegram/webhook/{conn_id}", json=upd,
                       headers={"X-Telegram-Bot-Api-Secret-Token": secret if secret is not None else tg.webhook_secret(conn_id)})


def test_telegram_webhook_registration_and_trigger(client, fake_net):
    s = register(client)
    cid = bot_connection(s)
    assert fake_net.telegram_calls == []                           # вебхук без активных воркфлоу не нужен
    wf = s.post("/workflows/", json=telegram_workflow(cid)).json()
    assert wf["has_telegram_trigger"] is True and wf["is_ai"] is False

    method, payload = fake_net.telegram_calls[-1]
    assert method == "setWebhook"
    assert payload["url"] == f"https://flowmind.test/api/telegram/webhook/{cid}"
    assert payload["secret_token"] == tg.webhook_secret(cid) and payload["allowed_updates"] == ["message"]
    assert s.get("/telegram/status").json()["connections"][0]["webhook_registered"] is True

    assert hook(client, cid, update(1), secret="wrong").status_code == 403
    assert client.post(f"/api/telegram/webhook/{cid}", json=update(1)).status_code == 403    # без заголовка

    assert hook(client, cid, update(10, "Как дела?")).status_code == 200
    execs = wait_for(lambda: s.get("/executions").json())
    assert execs and execs[0]["source"] == "telegram" and execs[0]["status"] == "success"
    sent = [(m, p) for m, p in fake_net.telegram_calls if m == "sendMessage"]
    assert sent and sent[0][1]["chat_id"] == "555" and sent[0][1]["text"] == "Вы написали: Как дела? от ivan"

    # повторная доставка того же update_id не запускает воркфлоу второй раз
    hook(client, cid, update(10, "Как дела?"))
    time.sleep(0.4)
    assert len(s.get("/executions").json()) == 1


def test_telegram_filters_and_deactivation(client, fake_net):
    s = register(client)
    cid = bot_connection(s)
    wf = s.post("/workflows/", json=telegram_workflow(cid, extra_cfg={"allowed_chat_ids": "777", "only_commands": True})).json()
    hook(client, cid, update(1, "/start", chat_id=555))            # чужой чат
    hook(client, cid, update(2, "просто текст", chat_id=777))       # не команда
    time.sleep(0.5)
    assert s.get("/executions").json() == []
    hook(client, cid, update(3, "/start", chat_id=777))
    assert wait_for(lambda: s.get("/executions").json())

    body = telegram_workflow(cid)
    body["is_active"] = False
    s.put(f"/workflows/{wf['id']}", json=body)
    assert fake_net.telegram_calls[-1][0] == "deleteWebhook"
    n = len(s.get("/executions").json())
    hook(client, cid, update(4, "/start", chat_id=777))
    time.sleep(0.4)
    assert len(s.get("/executions").json()) == n


def test_telegram_trigger_quota_per_plan(client):
    s = register(client)
    cid = bot_connection(s)
    assert s.post("/workflows/", json=telegram_workflow(cid, "one")).status_code == 200
    r = s.post("/workflows/", json=telegram_workflow(cid, "two"))
    assert r.status_code == 402 and r.json()["detail"]["kind"] == "telegram_triggers"
    inactive = telegram_workflow(cid, "three")
    inactive["is_active"] = False
    assert s.post("/workflows/", json=inactive).status_code == 200      # неактивные не считаются


def test_telegram_run_limit_notifies_chat(client, fake_net, admin):
    s = register(client)
    cid = bot_connection(s)
    s.post("/workflows/", json=telegram_workflow(cid))
    admin.put("/admin/plans/free", json={"limits": {"regular_run": 0}})
    try:
        hook(client, cid, update(1))
        assert wait_for(lambda: [p for m, p in fake_net.telegram_calls if m == "sendMessage"])
        assert "лимит" in [p for m, p in fake_net.telegram_calls if m == "sendMessage"][0]["text"].lower()
    finally:
        admin.put("/admin/plans/free", json={"limits": {"regular_run": 3000}})


def test_deleting_connection_removes_webhook(client, fake_net):
    s = register(client)
    cid = bot_connection(s)
    s.post("/workflows/", json=telegram_workflow(cid))
    assert s.delete(f"/connections/{cid}").status_code == 200
    assert fake_net.telegram_calls[-1][0] == "deleteWebhook"


# ───────── AI-чат ─────────

def chat(s, text="Собери агента", workflow=None, **kw):
    return s.post("/ai/chat", json={"messages": [{"role": "user", "content": text}], "workflow": workflow, **kw})


def test_ai_chat_builds_graph(client, fake_net):
    s = register(client)
    conn = s.post("/connections", json={"category": "tool", "provider": "telegram_bot", "name": "b", "config": {"bot_token": BOT_TOKEN}}).json()["id"]
    model_answer = {"reply": "Собрал бота-помощника", "workflow": {
        "nodes": [
            {"id": "trg", "type": "telegram_trigger", "config": {"connection_id": conn}},
            {"id": "bot", "type": "agent", "config": {"system_prompt": "Ты помощник", "connection_id": 99999}},
            {"id": "tool1", "type": "http", "config": {"method": "GET", "url": "https://api.example.com/{order_id}"}},
            {"id": "send", "type": "telegram_send", "config": {"connection_id": conn, "message": "{bot}"}},
            {"id": "evil", "type": "shell_exec", "config": {"cmd": "rm -rf /"}},
        ],
        "edges": [
            {"from_node": "trg", "to_node": "bot", "type": "next"},
            {"from_node": "bot", "to_node": "tool1", "type": "tool"},
            {"from_node": "bot", "to_node": "send", "type": "next"},
            {"from_node": "bot", "to_node": "ghost", "type": "next"},
            {"from_node": "send", "to_node": "send", "type": "next"},
            {"from_node": "send", "to_node": "trg", "type": "tool"},
        ]}}
    fake_net.llm_queue.append(json.dumps(model_answer, ensure_ascii=False))
    r = chat(s)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["reply"] == "Собрал бота-помощника"
    wf = data["workflow"]
    types = {n["id"]: n for n in wf["nodes"]}
    assert set(types) == {"trg", "bot", "tool1", "send"}                   # неизвестный тип отброшен
    assert "connection_id" not in types["bot"]["config"]                   # чужой/несуществующий id удалён
    assert types["trg"]["config"]["connection_id"] == conn                  # свой — оставлен
    assert types["bot"]["config"]["mode"] == "cloud"                        # режим по умолчанию для облака
    assert types["tool1"]["config"]["tool_name"] and types["tool1"]["config"]["tool_description"]
    assert {(e["from_node"], e["to_node"], e["type"]) for e in wf["edges"]} == {
        ("trg", "bot", "next"), ("bot", "tool1", "tool"), ("bot", "send", "next")}
    assert all(n["position"] and "x" in n["position"] for n in wf["nodes"])
    assert types["trg"]["position"]["x"] < types["bot"]["position"]["x"] < types["send"]["position"]["x"]
    assert types["tool1"]["position"]["y"] > types["bot"]["position"]["y"]   # инструмент под агентом

    # результат можно сохранить как воркфлоу
    saved = s.post("/workflows/", json={"name": "from chat", "description": "", **wf, "is_active": False})
    assert saved.status_code == 200 and saved.json()["is_ai"] is True


def test_ai_chat_preserves_positions_and_handles_plain_text(client, fake_net):
    s = register(client)
    current = {"nodes": [{"id": "a", "type": "manual", "config": {}, "position": {"x": 500, "y": 40}}], "edges": []}
    fake_net.llm_queue.append('```json\n{"reply": "ок", "workflow": {"nodes": [{"id": "a", "type": "manual", "config": {}}, {"id": "b", "type": "print", "config": {}}], "edges": [{"from_node": "a", "to_node": "b"}]}}\n```')
    wf = chat(s, "добавь вывод", current).json()["workflow"]
    assert wf["nodes"][0]["position"] == {"x": 500, "y": 40}
    fake_net.llm_queue.append("Это просто текст, а не JSON")
    r = chat(s, "что такое агент?").json()
    assert r["workflow"] is None and "просто текст" in r["reply"]
    fake_net.llm_queue.append(json.dumps({"reply": "Агент — нода с инструментами", "workflow": None}, ensure_ascii=False))
    assert chat(s, "что такое агент?").json() == {"reply": "Агент — нода с инструментами", "workflow": None}
    fake_net.llm_queue.append(json.dumps({"reply": "готово", "workflow": {"nodes": [{"id": "x", "type": "nope"}], "edges": []}}))
    assert "Не удалось построить" in chat(s).json()["reply"]


def test_ai_chat_quota_and_validation(client, fake_net, admin):
    s = register(client)
    assert s.post("/ai/chat", json={"messages": [{"role": "assistant", "content": "x"}]}).status_code == 400
    assert s.post("/ai/chat", json={"messages": []}).status_code == 422
    admin.put("/admin/plans/free", json={"limits": {"ai_chat": 2}})
    try:
        for _ in range(2):
            fake_net.llm_queue.append(json.dumps({"reply": "ok", "workflow": None}))
            assert chat(s).status_code == 200
        r = chat(s)
        assert r.status_code == 402 and r.json()["detail"]["kind"] == "ai_chat"
        assert s.get("/me").json()["usage"]["ai_chat"] == 2
    finally:
        admin.put("/admin/plans/free", json={"limits": {"ai_chat": 100}})


def test_ai_chat_unavailable_when_switched_off(client, admin):
    s = register(client)
    admin.put("/admin/settings", json={"ai_enabled": False})
    try:
        r = chat(s)
        assert r.status_code == 503 and r.json()["detail"]["code"] == "ai_unavailable"
        assert s.get("/me").json()["usage"]["ai_chat"] == 0             # неудачный запрос не списывается
    finally:
        admin.put("/admin/settings", json={"ai_enabled": True})


# ───────── админка ─────────

def test_admin_access_control(client, user, admin):
    for url in ("/admin/stats", "/admin/users", "/admin/plans", "/admin/payments", "/admin/settings", "/admin/audit"):
        assert user.get(url).status_code == 403, url
        assert admin.get(url).status_code == 200, url
    assert user.put("/admin/plans/free", json={"name": "hack"}).status_code == 403
    assert user.patch("/admin/users/1", json={"role": "admin"}).status_code == 403


def test_admin_users_grant_and_audit(client, admin):
    target = register(client)
    uid = target.get("/me").json()["user"]["id"]
    users = admin.get("/admin/users", params={"q": target.email[:12]}).json()
    assert any(u["email"] == target.email and u["plan"] == "free" for u in users["items"])

    g = admin.post(f"/admin/users/{uid}/grant", json={"plan_code": "business", "period": "year"})
    assert g.status_code == 200 and g.json()["provider"] == "manual"
    assert target.get("/me").json()["plan"]["code"] == "business"
    detail = admin.get(f"/admin/users/{uid}").json()
    assert detail["plan"]["code"] == "business" and detail["subscription"]["plan_code"] == "business"

    assert admin.post(f"/admin/users/{uid}/grant", json={"plan_code": "nope"}).status_code == 400
    assert admin.post(f"/admin/users/{uid}/grant", json={"plan_code": "free"}).status_code == 200
    assert target.get("/me").json()["plan"]["code"] == "free"

    assert any(a["action"] == "subscription.grant" and a["target"] == target.email for a in admin.get("/admin/audit").json())
    me_id = admin.get("/me").json()["user"]["id"]
    assert admin.patch(f"/admin/users/{me_id}", json={"is_active": False}).status_code == 400       # нельзя заблокировать себя


def test_admin_edit_plan_and_stats(client, admin):
    r = admin.put("/admin/plans/pro", json={"price_month": 123000, "limits": {"ai_workflows": None, "ai_run": 4000}})
    try:
        assert r.status_code == 200
        pro = {p["code"]: p for p in client.get("/api/plans").json()}["pro"]
        assert pro["price_month"] == 123000 and pro["limits"]["ai_workflows"] is None and pro["limits"]["ai_run"] == 4000
        assert admin.put("/admin/plans/pro", json={"limits": {"ai_run": -5}}).status_code == 400
        assert admin.put("/admin/plans/ghost", json={"name": "x"}).status_code == 404
    finally:
        admin.put("/admin/plans/pro", json={"price_month": 99000, "limits": {"ai_workflows": 25, "ai_run": 3000}})

    stats = admin.get("/admin/stats").json()
    assert stats["users_total"] >= 1 and len(stats["runs_by_day"]) == 14
    assert {"mrr", "revenue_total", "revenue_30d", "ai", "paid_subscriptions"} <= set(stats)
    assert stats["ai"]["key_configured"] is True
