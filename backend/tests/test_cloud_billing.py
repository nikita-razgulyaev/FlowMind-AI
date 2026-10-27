from datetime import timedelta

import pytest

from app.models import utcnow
from tests.conftest import TEST_MODE, register, run, simple_workflow

pytestmark = pytest.mark.skipif(TEST_MODE != "cloud", reason="cloud only")

GOOD = {"number": "4242 4242 4242 4242", "exp_month": 12, "exp_year": 2035, "cvc": "123", "holder": "TEST USER"}


def pay(s, plan="pro", period="month", card=GOOD):
    checkout = s.post("/billing/checkout", json={"plan_code": plan, "period": period}).json()
    assert checkout["action"] == "pay", checkout
    p = checkout["payment"]
    assert p["status"] == "pending" and p["provider"] == "mock"
    return s.post(f"/billing/mock/{p['id']}/pay", json=card)


def test_plans_public(client):
    plans = client.get("/api/plans").json()
    assert [p["code"] for p in plans] == ["free", "pro", "business"]
    by = {p["code"]: p for p in plans}
    assert by["pro"]["price_month"] == 99000 and by["pro"]["price_year"] == 950400
    assert by["business"]["price_month"] == 299000 and by["business"]["price_year"] == 2870400
    for code in ("pro", "business"):                    # годовая цена = 12 месяцев со скидкой 20%
        assert by[code]["price_year"] == by[code]["price_month"] * 12 * 80 // 100


def test_successful_payment_activates_plan(client):
    s = register(client)
    r = pay(s)
    assert r.status_code == 200 and r.json()["status"] == "succeeded" and r.json()["card"]["last4"] == "4242"
    me = s.get("/me").json()
    assert me["plan"]["code"] == "pro" and me["subscription"]["period"] == "month"
    assert me["subscription"]["payment_method_label"] == "Visa •••• 4242"
    start, end = (me["subscription"][k] for k in ("current_period_start", "current_period_end"))
    assert 28 <= (_dt(end) - _dt(start)).days <= 31
    pays = s.get("/billing/payments").json()
    assert pays[0]["amount"] == 99000 and pays[0]["status"] == "succeeded"
    # повторная оплата того же платежа невозможна
    assert s.post(f"/billing/mock/{pays[0]['id']}/pay", json=GOOD).status_code == 400


def _dt(value):
    from datetime import datetime
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_yearly_payment(client):
    s = register(client)
    checkout = s.post("/billing/checkout", json={"plan_code": "business", "period": "year"}).json()["payment"]
    assert checkout["amount"] == 2870400
    s.post(f"/billing/mock/{checkout['id']}/pay", json=GOOD)
    sub = s.get("/me").json()["subscription"]
    assert sub["period"] == "year" and 364 <= (_dt(sub["current_period_end"]) - _dt(sub["current_period_start"])).days <= 366


def test_declined_and_insufficient_cards(client):
    s = register(client)
    r = pay(s, card={**GOOD, "number": "4000000000000002"})
    assert r.json()["status"] == "failed" and "отклонил" in r.json()["failure_reason"]
    r = pay(s, card={**GOOD, "number": "4000000000009995"})
    assert r.json()["status"] == "failed" and "Недостаточно" in r.json()["failure_reason"]
    assert s.get("/me").json()["plan"]["code"] == "free"          # тариф не изменился


def test_card_validation(client):
    s = register(client)
    assert pay(s, card={**GOOD, "number": "1234 5678 9012 3456"}).status_code == 422       # Luhn
    assert pay(s, card={**GOOD, "exp_year": 2020}).status_code == 422
    assert pay(s, card={**GOOD, "cvc": "12"}).status_code == 422
    assert pay(s, card={**GOOD, "exp_month": 13}).status_code == 422
    assert s.get("/me").json()["plan"]["code"] == "free"


def test_3ds_flow(client):
    s = register(client)
    r = pay(s, card={**GOOD, "number": "4000000000003220"})
    assert r.json()["status"] == "requires_action"
    pid = r.json()["id"]
    assert s.post(f"/billing/mock/{pid}/confirm-3ds", json={"approve": True}).json()["status"] == "succeeded"
    assert s.get("/me").json()["plan"]["code"] == "pro"

    s2 = register(client)
    pid = pay(s2, card={**GOOD, "number": "4000000000003220"}).json()["id"]
    r = s2.post(f"/billing/mock/{pid}/confirm-3ds", json={"approve": False}).json()
    assert r["status"] == "failed" and "3-D Secure" in r["failure_reason"]


def test_cannot_touch_foreign_payment(client):
    a, b = register(client), register(client)
    pid = a.post("/billing/checkout", json={"plan_code": "pro", "period": "month"}).json()["payment"]["id"]
    assert b.post(f"/billing/mock/{pid}/pay", json=GOOD).status_code == 404
    assert b.get(f"/billing/payments/{pid}").status_code == 404


def test_upgrade_with_proration_and_scheduled_downgrade(client):
    s = register(client)
    pay(s, "pro", "month")
    q = s.post("/billing/quote", json={"plan_code": "business", "period": "month"}).json()
    assert q["action"] == "pay" and q["kind"] == "upgrade" and q["price"] == 299000
    assert 90000 <= q["credit"] <= 99000 and q["amount"] == q["price"] - q["credit"]
    r = pay(s, "business", "month")
    assert r.json()["amount"] == q["amount"] or abs(r.json()["amount"] - q["amount"]) < 200
    assert s.get("/me").json()["plan"]["code"] == "business"

    # понижение — применится в конце периода, платить сейчас не нужно
    r = s.post("/billing/checkout", json={"plan_code": "pro", "period": "month"}).json()
    assert r["action"] == "scheduled"
    sub = s.get("/me").json()["subscription"]
    assert sub["plan_code"] == "business" and sub["pending_plan_code"] == "pro"


def test_cancel_and_resume(client):
    s = register(client)
    pay(s)
    assert s.post("/billing/cancel").json()["action"] == "cancel"
    assert s.get("/me").json()["subscription"]["cancel_at_period_end"] is True
    assert s.get("/me").json()["plan"]["code"] == "pro"           # доступ сохраняется до конца периода
    assert s.post("/billing/checkout", json={"plan_code": "pro", "period": "month"}).json()["action"] == "resumed"
    assert s.get("/me").json()["subscription"]["cancel_at_period_end"] is False
    assert s.post("/billing/checkout", json={"plan_code": "pro", "period": "month"}).status_code == 400   # уже активен
    assert register(client).post("/billing/cancel").status_code == 400                                     # у free отменять нечего


def test_auto_renewal_and_expiry(client):
    s = register(client)
    pay(s)
    r = s.post("/billing/demo/renew-now").json()
    assert r["outcome"] == {"renewed": 1}
    kinds = [p["kind"] for p in s.get("/billing/payments").json()]
    assert kinds.count("renewal") == 1
    assert s.get("/me").json()["plan"]["code"] == "pro"

    # отмена + конец периода → автоматический возврат на Free, без списания
    s.post("/billing/cancel")
    out = s.post("/billing/demo/renew-now").json()
    assert out["outcome"] == {"downgraded": 1}
    assert s.get("/me").json()["plan"]["code"] == "free"


def test_scheduled_downgrade_applies_at_renewal(client):
    s = register(client)
    pay(s, "business", "month")
    s.post("/billing/checkout", json={"plan_code": "pro", "period": "month"})
    assert s.post("/billing/demo/renew-now").json()["outcome"] == {"renewed": 1}
    me = s.get("/me").json()
    assert me["plan"]["code"] == "pro" and me["subscription"]["pending_plan_code"] is None
    assert s.get("/billing/payments").json()[0]["amount"] == 99000       # списали цену нового тарифа


def test_failed_renewal_grace_then_downgrade(client):
    s = register(client)
    pay(s)
    s.post("/billing/demo/fail-next")
    r = s.post("/billing/demo/renew-now").json()
    assert r["outcome"] == {"failed": 1} and r["subscription"]["status"] == "past_due"
    assert s.get("/me").json()["plan"]["code"] == "pro"           # льготный период: доступ ещё есть
    s.post("/billing/demo/renew-now")
    s.post("/billing/demo/renew-now")                              # третья неудача
    assert s.get("/me").json()["plan"]["code"] == "free"


def test_plan_limits_follow_subscription(client):
    s = register(client)
    pay(s)
    assert s.get("/me").json()["plan"]["limits"]["ai_workflows"] == 25
    pay_b = s.post("/billing/checkout", json={"plan_code": "business", "period": "year"}).json()["payment"]
    s.post(f"/billing/mock/{pay_b['id']}/pay", json=GOOD)
    assert s.get("/me").json()["plan"]["limits"]["regular_workflows"] is None   # без ограничений


def test_expired_subscription_falls_back_to_free(client):
    s = register(client)
    pay(s)
    from app.database import async_session
    from app.models import Subscription
    from sqlalchemy import select

    uid = s.get("/me").json()["user"]["id"]

    async def expire_it():
        async with async_session() as db:
            sub = (await db.execute(select(Subscription).where(Subscription.user_id == uid))).scalar_one()
            sub.current_period_end = utcnow() - timedelta(days=10)
            await db.commit()
    run(client, expire_it)
    assert s.get("/me").json()["plan"]["code"] == "free"


# ───────── ЮKassa (против поддельного API) ─────────

@pytest.fixture
def yookassa(monkeypatch, fake_net):
    from app.config import settings
    monkeypatch.setattr(settings, "payment_provider", "yookassa")
    monkeypatch.setattr(settings, "yookassa_shop_id", "shop123")
    monkeypatch.setattr(settings, "yookassa_secret_key", "secret456")
    monkeypatch.setattr(settings, "yookassa_receipts", True)
    return fake_net


def test_yookassa_payment_webhook_and_autorenewal(client, yookassa):
    s = register(client)
    r = s.post("/billing/checkout", json={"plan_code": "pro", "period": "year"}).json()
    p = r["payment"]
    assert p["provider"] == "yookassa" and p["confirmation_url"].startswith("https://yookassa.test/pay/")
    assert s.post(f"/billing/mock/{p['id']}/pay", json=GOOD).status_code == 404       # демо-эндпоинты выключены

    req = [x for x in yookassa.requests if x.url.host == "api.yookassa.ru"][0]
    assert req.headers["authorization"].startswith("Basic ") and req.headers["idempotence-key"]
    body = yookassa.yookassa_payments[next(iter(yookassa.yookassa_payments))]["request"]
    assert body["amount"] == {"value": "9504.00", "currency": "RUB"} and body["save_payment_method"] is True
    assert body["confirmation"]["return_url"].endswith(f"/billing/return?payment={p['id']}")
    assert body["receipt"]["items"][0]["payment_subject"] == "service"

    provider_id = next(iter(yookassa.yookassa_payments))
    assert s.get("/me").json()["plan"]["code"] == "free"          # пока не подтверждено — тариф не выдан

    # вебхук: подделанное уведомление не активирует, пока API не подтвердит статус
    hook = {"type": "notification", "event": "payment.succeeded", "object": {"id": provider_id, "status": "succeeded"}}
    assert client.post("/api/billing/yookassa/webhook", json=hook).status_code == 200
    assert s.get("/me").json()["plan"]["code"] == "free"

    yookassa.yookassa_status = "succeeded"
    assert client.post("/api/billing/yookassa/webhook", json=hook).status_code == 200
    me = s.get("/me").json()
    assert me["plan"]["code"] == "pro" and me["subscription"]["period"] == "year"
    assert me["subscription"]["payment_method_label"] == "MasterCard •••• 4477"
    client.post("/api/billing/yookassa/webhook", json=hook)       # повторная доставка идемпотентна
    assert len([x for x in s.get("/billing/payments").json() if x["status"] == "succeeded"]) == 1

    assert client.post("/api/billing/yookassa/webhook", json={"object": {"id": "unknown"}}).status_code == 200
    assert client.post("/api/billing/yookassa/webhook", json={"bad": 1}).status_code == 400

    # автопродление по сохранённому способу оплаты
    from app.models import Subscription
    from app.database import async_session
    from app.services import billing
    from sqlalchemy import select
    uid = me["user"]["id"]

    async def force_due():
        async with async_session() as db:
            sub = (await db.execute(select(Subscription).where(Subscription.user_id == uid))).scalar_one()
            sub.current_period_end = utcnow() - timedelta(minutes=1)
            await db.commit()
            return await billing.process_renewals(db, user_id=uid)
    assert run(client, force_due) == {"renewed": 1}
    renewal = [x for x in yookassa.yookassa_payments.values() if "payment_method_id" in x["request"]][0]
    assert renewal["request"]["payment_method_id"] == "pm_saved_1" and "confirmation" not in renewal["request"]


def test_yookassa_poll_status_when_webhook_missing(client, yookassa):
    s = register(client)
    p = s.post("/billing/checkout", json={"plan_code": "pro", "period": "month"}).json()["payment"]
    assert s.get(f"/billing/payments/{p['id']}").json()["status"] == "pending"
    yookassa.yookassa_status = "succeeded"
    assert s.get(f"/billing/payments/{p['id']}").json()["status"] == "succeeded"
    assert s.get("/me").json()["plan"]["code"] == "pro"


def test_yookassa_canceled_payment(client, yookassa):
    s = register(client)
    p = s.post("/billing/checkout", json={"plan_code": "pro", "period": "month"}).json()["payment"]
    yookassa.yookassa_status = "canceled"
    assert s.get(f"/billing/payments/{p['id']}").json()["status"] == "failed"
    assert s.get("/me").json()["plan"]["code"] == "free"
