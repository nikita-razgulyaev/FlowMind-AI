"""Единый источник тарифов (app/plans_config.py): документация, база и синхронизация при старте."""
import asyncio
import copy

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models import AppSetting, Base, Plan
from app.plans_config import AI_DAILY_CAP, PLANS, plan_rows
from app.plans_docs import ROOT, TARGETS, render_text
from app.seed import PLANS_SNAPSHOT_KEY, sync_plans
from tests.conftest import TEST_MODE


def test_docs_are_in_sync_with_config():
    """Таблицы в README и документации совпадают с plans_config.py (обновить: python -m app.plans_docs)."""
    checked = 0
    for rel in TARGETS:
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        assert render_text(text) == text, f"{rel} устарел: выполните `python -m app.plans_docs` в папке backend"
        checked += 1
    if not checked:
        pytest.skip("документация не найдена")


def test_features_are_built_from_limits():
    rows = {r["code"]: r for r in plan_rows()}
    pro = PLANS["pro"]
    assert f"{pro['max_ai_workflows']} ИИ-сценариев и {pro['max_regular_workflows']} обычных" in rows["pro"]["features"]
    assert f"{pro['ai_runs_month']:,}".replace(",", " ") + " ИИ-запусков в месяц" in rows["pro"]["features"]
    assert rows["business"]["features"][0].endswith("обычные без ограничений")      # None = без ограничений


@pytest.mark.skipif(TEST_MODE != "cloud", reason="cloud only")
def test_database_plans_match_config(client):
    by = {p["code"]: p for p in client.get("/api/plans").json()}
    for row in plan_rows():
        if row["is_public"]:
            assert by[row["code"]]["features"] == row["features"]
            assert by[row["code"]]["price_month"] == row["price_month"]


@pytest.mark.skipif(TEST_MODE != "cloud", reason="cloud only")
def test_daily_cap_default_comes_from_config(client, admin):
    assert admin.get("/admin/settings").json()["ai_daily_cap"] == AI_DAILY_CAP


def _scenario(tmp_path):
    async def go():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/plans.db")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session = async_sessionmaker(engine, expire_on_commit=False)

        async def plan(code):
            async with session() as db:
                return (await db.execute(select(Plan).where(Plan.code == code))).scalar_one()

        v1 = copy.deepcopy(plan_rows())
        async with session() as db:
            await sync_plans(db, v1, force=False)                        # первый старт: тарифы созданы
        assert (await plan("pro")).ai_runs_month == PLANS["pro"]["ai_runs_month"]

        async with session() as db:                                      # администратор правит бизнес-тариф вручную
            (await db.execute(select(Plan).where(Plan.code == "business"))).scalar_one().ai_runs_month = 5000
            await db.commit()

        v2 = copy.deepcopy(v1)                                           # правка в коде: меняем Про и Бизнес
        for r in v2:
            if r["code"] == "pro":
                r["ai_runs_month"], r["features"] = 777, ["новая строка"]
            if r["code"] == "business":
                r["ai_runs_month"] = 888
        async with session() as db:
            await sync_plans(db, v2, force=False)
        pro, business = await plan("pro"), await plan("business")
        assert pro.ai_runs_month == 777 and pro.features == ["новая строка"]      # из кода применилось
        assert business.ai_runs_month == 5000                                      # ручная правка не затёрта

        v3 = copy.deepcopy(v2)
        for r in v3:
            if r["code"] == "pro":
                r["ai_runs_month"] = 999
        async with session() as db:                                      # нет снимка прошлых значений: ничего не трогаем
            row = (await db.execute(select(AppSetting).where(AppSetting.key == PLANS_SNAPSHOT_KEY))).scalar_one()
            await db.delete(row)
            await db.commit()
        async with session() as db:
            await sync_plans(db, v3, force=False)
        assert (await plan("pro")).ai_runs_month == 777

        async with session() as db:                                      # принудительная синхронизация перезаписывает всё
            await sync_plans(db, v3, force=True)
        assert (await plan("pro")).ai_runs_month == 999 and (await plan("business")).ai_runs_month == 888
        await engine.dispose()
    asyncio.run(go())


def test_sync_updates_defaults_but_keeps_admin_edits(tmp_path):
    _scenario(tmp_path)


def _numbers_from_card(features: list[str]) -> dict:
    """Достаёт числа из строк карточки тарифа, чтобы сверить их с лимитами, которые реально действуют."""
    import re
    n = lambda s: int(s.replace(" ", ""))          # noqa: E731
    out, text = {}, "\n".join(features)
    m = re.search(r"^([\d ]+) ИИ-сценариев(?: и ([\d ]+) обычных|, обычные без ограничений)", text, re.M)
    out["ai_workflows"], out["regular_workflows"] = n(m.group(1)), (n(m.group(2)) if m.group(2) else None)
    out["ai_run"] = n(re.search(r"^([\d ]+) ИИ-запусков в месяц", text, re.M).group(1))
    out["regular_run"] = n(re.search(r"^([\d ]+) обычных запусков", text, re.M).group(1))
    out["ai_chat"] = n(re.search(r"^([\d ]+) сообщен\S* ИИ-помощника", text, re.M).group(1))
    out["telegram_triggers"] = n(re.search(r"^([\d ]+) Telegram-триггер", text, re.M).group(1))
    out["history_days"] = n(re.search(r"^История выполнений за ([\d ]+) ", text, re.M).group(1))
    return out


@pytest.mark.skipif(TEST_MODE != "cloud", reason="cloud only")
def test_cards_match_enforced_limits(client):
    """Числа в карточках тарифов = лимиты, по которым сервис реально отказывает (поля тарифа в базе)."""
    plans = client.get("/api/plans").json()
    assert [p["code"] for p in plans] == list(PLANS)
    for p in plans:
        assert _numbers_from_card(p["features"]) == p["limits"], p["code"]
        spec = PLANS[p["code"]]
        assert p["limits"] == {
            "ai_workflows": spec["max_ai_workflows"], "regular_workflows": spec["max_regular_workflows"],
            "ai_run": spec["ai_runs_month"], "regular_run": spec["regular_runs_month"],
            "telegram_triggers": spec["telegram_triggers"], "history_days": spec["history_days"],
            "ai_chat": spec["ai_chat_messages_month"]}, p["code"]
