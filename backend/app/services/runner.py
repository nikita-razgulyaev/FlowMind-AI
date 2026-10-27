"""Запуск workflow: проверка лимитов тарифа, загрузка подключений пользователя, выполнение, сохранение."""
import asyncio
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Connection, Execution, User, Workflow
from ..security import decrypt_config
from ..worker import WorkflowEngine
from .google import GOOGLE_PROVIDERS, refresh_if_needed
from .limits import check_and_count_run, get_user_plan
from .platform_ai import platform_guard

_running: dict[int, int] = defaultdict(int)


async def load_connections(db: AsyncSession, user_id: int) -> dict:
    rows = (await db.execute(select(Connection).where(Connection.user_id == user_id))).scalars().all()
    result = {}
    for c in rows:
        cfg = await refresh_if_needed(c, db) if c.provider in GOOGLE_PROVIDERS else decrypt_config(c.config)
        result[c.id] = {"provider": c.provider, "config": cfg}
    return result


async def run_workflow(
    db: AsyncSession, user: User, workflow: Workflow, trigger_data: Optional[dict[str, Any]] = None,
    source: str = "manual",
) -> Execution:
    if _running[user.id] >= settings.max_parallel_executions_per_user:
        raise HTTPException(429, detail={"code": "too_many_runs", "message": "Слишком много одновременных запусков, дождитесь завершения предыдущих"})

    plan = await get_user_plan(db, user)
    await check_and_count_run(db, user, plan, workflow.is_ai)

    execution = Execution(
        user_id=user.id, workflow_id=workflow.id, status="running", source=source,
        is_ai=workflow.is_ai, trigger_data=trigger_data,
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)

    connections = await load_connections(db, user.id)
    engine = WorkflowEngine(
        {"name": workflow.name, "nodes": workflow.nodes, "edges": workflow.edges},
        execution.id, connections=connections, llm_guard=platform_guard,
    )

    _running[user.id] += 1
    try:
        result = await asyncio.wait_for(engine.execute(trigger_data), timeout=settings.max_execution_seconds)
        execution.status = "success"
        execution.result = _jsonable(result)
    except asyncio.TimeoutError:
        execution.status = "failed"
        execution.result = {"error": f"Превышено максимальное время выполнения ({settings.max_execution_seconds} с)"}
    except Exception as e:
        traceback.print_exc()
        execution.status = "failed"
        execution.result = {"error": str(e)}
    finally:
        _running[user.id] -= 1
    execution.logs = _jsonable(engine.logs)
    execution.finished_at = datetime.now(timezone.utc)
    await db.commit()
    return execution


def _jsonable(value):
    import json
    return json.loads(json.dumps(value, default=str, ensure_ascii=False))
