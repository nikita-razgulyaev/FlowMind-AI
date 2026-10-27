"""Локальный режим (DEPLOYMENT_MODE=local): без входа, без лимитов, Ollama по умолчанию."""
import json
import os

import pytest

from tests.conftest import TEST_MODE, ai_workflow, simple_workflow

pytestmark = pytest.mark.skipif(TEST_MODE != "local", reason="local only")
API = "/api"


def test_config_reports_local(client):
    cfg = client.get(f"{API}/config").json()
    assert cfg["deployment_mode"] == "local" and cfg["auth_required"] is False
    assert cfg["default_llm_mode"] == "local" and cfg["telegram_mode"] == "polling"


def test_no_login_needed_and_unlimited_plan(client):
    me = client.get(f"{API}/me").json()
    assert me["user"]["is_local"] is True and me["plan"]["code"] == "local"
    assert all(v is None for v in me["plan"]["limits"].values())          # ни одного ограничения
    for i in range(8):                                                     # больше, чем разрешено на Free (5)
        assert client.post(f"{API}/workflows/", json=ai_workflow(f"ai{i}", mode="local")).status_code == 200
    assert client.get(f"{API}/me").json()["workflows"]["ai_workflows"] >= 8


def test_billing_disabled_locally(client):
    assert client.post(f"{API}/billing/checkout", json={"plan_code": "pro", "period": "month"}).status_code == 400
    assert client.request("DELETE", f"{API}/me", json={"password": "x"}).status_code == 400


def test_ollama_generation(client, fake_net):
    wid = client.post(f"{API}/workflows/", json=ai_workflow(mode="local")).json()["id"]
    out = client.post(f"{API}/workflows/{wid}/execute", json={"input": "мир"}).json()
    assert out["status"] == "success"
    assert out["result"]["l"].startswith("ollama:qwen2.5:Скажи: мир")      # модель по умолчанию из OLLAMA_MODEL
    assert not [r for r in fake_net.requests if r.url.host == "router.huggingface.co"]


def test_templates_switch_to_ollama(client):
    templates = client.get(f"{API}/templates").json()
    for key in templates:
        wf = client.post(f"{API}/workflows/from-template/{key}").json()
        for node in wf["nodes"]:
            if node["type"] in ("llm", "agent") and not node["config"].get("connection_id"):
                assert node["config"]["mode"] == "local" and node["config"]["model"] == "qwen2.5"


def test_ai_chat_uses_ollama(client, fake_net):
    fake_net.llm_queue.append(json.dumps({"reply": "ок", "workflow": {
        "nodes": [{"id": "a", "type": "manual"}, {"id": "b", "type": "llm", "config": {"prompt": "hi"}}],
        "edges": [{"from_node": "a", "to_node": "b"}]}}))
    r = client.post(f"{API}/ai/chat", json={"messages": [{"role": "user", "content": "собери"}]}).json()
    assert fake_net.ollama_chat_payloads and fake_net.ollama_chat_payloads[0]["format"] == "json"
    llm = [n for n in r["workflow"]["nodes"] if n["id"] == "b"][0]
    assert llm["config"]["mode"] == "local" and llm["config"]["model"] == "qwen2.5"


def test_http_node_may_reach_localhost_locally(client):
    wf = simple_workflow("h", [{"id": "h", "type": "http", "config": {"method": "GET", "url": "http://localhost:9/x"}}],
                         [{"id": "e2", "from_node": "p", "to_node": "h", "type": "next"}])
    wid = client.post(f"{API}/workflows/", json=wf).json()["id"]
    out = client.post(f"{API}/workflows/{wid}/execute", json={}).json()["result"]["h"]
    assert "внутреннюю сеть" not in str(out)


def test_secrets_are_encrypted_locally_too(client):
    r = client.post(f"{API}/connections", json={"category": "ai_api", "provider": "openai_compatible", "name": "k",
                                                 "config": {"base_url": "http://localhost:1234/v1", "api_key": "sk-local-1111"}})
    assert r.status_code == 200 and r.json()["config"]["api_key"].endswith("1111") and "sk-local" not in r.text


@pytest.mark.skipif(not os.environ.get("LEGACY_DB"), reason="нужна БД старой версии")
def test_legacy_data_adopted_by_local_user(client):
    wfs = client.get(f"{API}/workflows/").json()
    assert [w["name"] for w in wfs if w["name"] == "old"] == ["old"]
    old = [w for w in wfs if w["name"] == "old"][0]
    assert old["is_ai"] is True                                            # признак пересчитан миграцией
    assert any(e["workflow_id"] == old["id"] for e in client.get(f"{API}/executions").json())
    conns = client.get(f"{API}/connections").json()
    assert conns and conns[0]["provider"] == "telegram_bot"
    assert conns[0]["config"]["bot_token"].startswith("••••")              # старый открытый токен маскируется в ответах


def test_telegram_long_polling(client, fake_net):
    import asyncio
    from app.services.telegram_service import poller

    token = "987654321:AAPollingTokenForTestsOnly_abcdefg"
    cid = client.post(f"{API}/connections", json={"category": "tool", "provider": "telegram_bot", "name": "poll",
                                                    "config": {"bot_token": token}}).json()["id"]
    wf = {"name": "poll", "description": "", "is_active": True,
          "nodes": [{"id": "trg", "type": "telegram_trigger", "config": {"connection_id": cid}},
                    {"id": "say", "type": "telegram_send", "config": {"connection_id": cid, "message": "эхо: {input}"}}],
          "edges": [{"id": "e", "from_node": "trg", "to_node": "say", "type": "next"}]}
    assert client.post(f"{API}/workflows/", json=wf).status_code == 200
    assert not fake_net.telegram_calls                                    # в локальном режиме вебхуки не регистрируются
    fake_net.tg_updates.append({"update_id": 777001, "message": {"message_id": 1, "text": "ping", "chat": {"id": 42},
                                                                  "from": {"id": 42, "username": "u"}}})

    async def poll_a_bit():
        assert await poller._wanted() >= {cid}
        task = asyncio.create_task(poller._poll(cid))
        await asyncio.sleep(1.0)
        task.cancel()
    client.portal.call(poll_a_bit)

    methods = [m for m, _ in fake_net.telegram_calls]
    assert "deleteWebhook" in methods and "getUpdates" in methods
    sent = [p for m, p in fake_net.telegram_calls if m == "sendMessage"]
    assert sent and sent[0]["text"] == "эхо: ping" and sent[0]["chat_id"] == "42"
    assert any(e["source"] == "telegram" for e in client.get(f"{API}/executions").json())
