import pytest
from sqlalchemy import select

from tests.conftest import (TEST_MODE, ai_workflow, register, run, simple_workflow)

pytestmark = pytest.mark.skipif(TEST_MODE != "cloud", reason="cloud only")


def test_tenant_isolation(client):
    a, b = register(client), register(client)
    wf = a.post("/workflows/", json=simple_workflow("A")).json()
    assert b.get("/workflows/").json() == []
    assert b.get(f"/workflows/{wf['id']}").status_code == 404
    assert b.put(f"/workflows/{wf['id']}", json=simple_workflow("hack")).status_code == 404
    assert b.delete(f"/workflows/{wf['id']}").status_code == 404
    assert b.post(f"/workflows/{wf['id']}/execute", json={"input": "x"}).status_code == 404

    ex = a.post(f"/workflows/{wf['id']}/execute", json={"input": "привет"}).json()
    assert b.get(f"/executions/{ex['execution_id']}").status_code == 404
    assert b.get("/executions").json() == []
    assert len(a.get("/executions").json()) == 1

    conn = a.post("/connections", json={"category": "ai_api", "provider": "openai_compatible", "name": "k",
                                         "config": {"base_url": "https://api.openai.com/v1", "api_key": "sk-secret-1234"}}).json()
    assert b.get("/connections").json() == []
    assert b.delete(f"/connections/{conn['id']}").status_code == 404


def test_execute_simple_workflow(client):
    s = register(client)
    wf = s.post("/workflows/", json=simple_workflow()).json()
    assert wf["is_ai"] is False
    res = s.post(f"/workflows/{wf['id']}/execute", json={"input": "мир"}).json()
    assert res["status"] == "success" and res["result"]["p"] == "Ответ: мир"
    logs = s.get(f"/executions/{res['execution_id']}").json()["logs"]
    assert logs[-1]["node_id"] == "p" and "T" in logs[-1]["timestamp"]


def test_condition_is_sandboxed(client):
    s = register(client)
    cond = lambda expr: simple_workflow("c", [{"id": "c", "type": "condition", "config": {"expression": expr}}],
                                        [{"id": "e2", "from_node": "p", "to_node": "c", "type": "next"}])
    wf = s.post("/workflows/", json=cond("len(input) > 3 and input.startswith('при')")).json()
    assert s.post(f"/workflows/{wf['id']}/execute", json={"input": "привет"}).json()["result"]["c"] is True
    evil = s.post("/workflows/", json=cond("__import__('os').system('echo pwned')")).json()
    out = s.post(f"/workflows/{evil['id']}/execute", json={"input": "x"}).json()
    assert out["status"] == "success" and out["result"]["c"] is False
    evil2 = s.post("/workflows/", json=cond("().__class__.__bases__[0].__subclasses__()")).json()
    assert s.post(f"/workflows/{evil2['id']}/execute", json={"input": "x"}).json()["result"]["c"] is False


def test_http_node_blocks_internal_network(client):
    s = register(client)
    wf = simple_workflow("h", [{"id": "h", "type": "http", "config": {"method": "GET", "url": "http://127.0.0.1:8000/api/health"}}],
                         [{"id": "e2", "from_node": "p", "to_node": "h", "type": "next"}])
    wid = s.post("/workflows/", json=wf).json()["id"]
    out = s.post(f"/workflows/{wid}/execute", json={}).json()["result"]["h"]
    assert "внутреннюю сеть" in out
    wf["nodes"][-1]["config"]["url"] = "http://169.254.169.254/latest/meta-data"
    wid = s.post("/workflows/", json=wf).json()["id"]
    assert "внутреннюю сеть" in s.post(f"/workflows/{wid}/execute", json={}).json()["result"]["h"]
    wf["nodes"][-1]["config"]["url"] = "http://93.184.216.34/"          # публичный IP — разрешён (ответ мокнут)
    wid = s.post("/workflows/", json=wf).json()["id"]
    assert s.post(f"/workflows/{wid}/execute", json={}).json()["result"]["h"]["status_code"] == 200


def test_free_plan_workflow_limits(client):
    s = register(client)
    for i in range(5):
        assert s.post("/workflows/", json=ai_workflow(f"ai{i}")).status_code == 200
    r = s.post("/workflows/", json=ai_workflow("ai6"))
    assert r.status_code == 402 and r.json()["detail"]["code"] == "quota_exceeded" and r.json()["detail"]["kind"] == "ai_workflows"
    for i in range(20):
        assert s.post("/workflows/", json=simple_workflow(f"r{i}")).status_code == 200
    assert s.post("/workflows/", json=simple_workflow("r21")).status_code == 402
    usage = s.get("/me").json()["workflows"]
    assert usage["ai_workflows"] == 5 and usage["regular_workflows"] == 20


def test_editing_existing_workflow_never_blocked_by_limit(client, admin):
    s = register(client)
    wf = s.post("/workflows/", json=simple_workflow("x")).json()
    admin.put("/admin/plans/free", json={"limits": {"regular_workflows": 0}})
    try:
        body = simple_workflow("renamed")
        assert s.put(f"/workflows/{wf['id']}", json=body).status_code == 200
        assert s.post("/workflows/", json=simple_workflow("new")).status_code == 402
    finally:
        admin.put("/admin/plans/free", json={"limits": {"regular_workflows": 20}})


def test_run_quota_and_counters(client, admin):
    s = register(client)
    wid = s.post("/workflows/", json=simple_workflow()).json()["id"]
    admin.put("/admin/plans/free", json={"limits": {"regular_run": 2}})
    try:
        assert s.post(f"/workflows/{wid}/execute", json={}).status_code == 200
        assert s.post(f"/workflows/{wid}/execute", json={}).status_code == 200
        r = s.post(f"/workflows/{wid}/execute", json={})
        assert r.status_code == 402 and r.json()["detail"]["kind"] == "regular_run"
        assert s.get("/me").json()["usage"]["regular_run"] == 2
    finally:
        admin.put("/admin/plans/free", json={"limits": {"regular_run": 3000}})


def test_ai_workflow_uses_platform_key_and_guard(client, admin, fake_net):
    s = register(client)
    wid = s.post("/workflows/", json=ai_workflow()).json()["id"]
    fake_net.llm_queue.append("Привет из платформы")
    res = s.post(f"/workflows/{wid}/execute", json={"input": "мир"}).json()
    assert res["status"] == "success" and res["result"]["l"] == "Привет из платформы"
    req = [r for r in fake_net.requests if r.url.host == "router.huggingface.co"][0]
    assert req.headers["authorization"] == "Bearer test-platform-key" and req.url.path.endswith("/chat/completions")
    assert s.get("/me").json()["usage"]["ai_run"] == 1

    calls_before = admin.get("/admin/stats").json()["ai"]["calls_today"]
    assert calls_before >= 1

    admin.put("/admin/settings", json={"ai_enabled": False})                 # рубильник
    try:
        out = s.post(f"/workflows/{wid}/execute", json={}).json()["result"]["l"]
        assert "отключён" in out
        assert client.get("/api/config").json()["platform_ai_available"] is False
    finally:
        admin.put("/admin/settings", json={"ai_enabled": True})

    admin.put("/admin/settings", json={"ai_daily_cap": calls_before})        # суточный потолок
    try:
        assert "Суточный лимит" in s.post(f"/workflows/{wid}/execute", json={}).json()["result"]["l"]
    finally:
        admin.put("/admin/settings", json={"ai_daily_cap": 5000})


def test_local_mode_unavailable_in_cloud(client):
    s = register(client)
    wid = s.post("/workflows/", json=ai_workflow(mode="local")).json()["id"]
    out = s.post(f"/workflows/{wid}/execute", json={}).json()["result"]["l"]
    assert "недоступны в облачной версии" in out


def test_connection_secrets_encrypted_and_masked(client):
    s = register(client)
    r = s.post("/connections", json={"category": "ai_api", "provider": "openai_compatible", "name": "mine",
                                      "config": {"base_url": "https://api.openai.com/v1", "api_key": "sk-supersecret-9876"}})
    assert r.status_code == 200 and r.json()["config"]["api_key"] == "••••••9876"
    assert "supersecret" not in s.get("/connections").text

    from app.database import async_session
    from app.models import Connection

    async def raw():
        async with async_session() as db:
            return (await db.get(Connection, r.json()["id"])).config["api_key"]
    stored = run(client, raw)
    assert stored.startswith("enc:") and "supersecret" not in stored

    # SSRF: свой base_url не может указывать во внутреннюю сеть
    bad = s.post("/connections", json={"category": "ai_api", "provider": "openai_compatible", "name": "x",
                                        "config": {"base_url": "http://localhost:11434/v1", "api_key": "k"}})
    assert bad.status_code == 400
    # неверный токен бота
    assert s.post("/connections", json={"category": "tool", "provider": "telegram_bot", "name": "b", "config": {"bot_token": "nope"}}).status_code == 400


def test_templates(client):
    s = register(client)
    templates = s.get("/templates").json()
    assert templates
    key, tpl = next(iter(templates.items()))
    wf = s.post(f"/workflows/from-template/{key}")
    assert wf.status_code == 200 and wf.json()["name"] == tpl["name"]


def test_node_limit(client):
    s = register(client)
    big = simple_workflow()
    big["nodes"] += [{"id": f"n{i}", "type": "print", "config": {}} for i in range(70)]
    assert s.post("/workflows/", json=big).status_code == 400
    dup = simple_workflow()
    dup["nodes"].append({"id": "t", "type": "print", "config": {}})
    assert s.post("/workflows/", json=dup).status_code == 400
