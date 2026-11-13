"""Запуск workflow: проверка лимитов тарифа, загрузка подключений пользователя, выполнение, сохранение."""
import asyncio
import traceback
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import async_session
from ..models import Connection, Execution, User, Workflow
from ..security import decrypt_config
from ..worker import WorkflowEngine, is_error_output
from .google import GOOGLE_PROVIDERS, refresh_if_needed
from .limits import check_and_count_run, get_user_plan
from .platform_ai import platform_guard

_running: dict[int, int] = defaultdict(int)

# Прогресс запусков для индикатора на холсте. В памяти процесса: после завершения хранится ещё MAX_TRACKED запусков,
# для остальных статус восстанавливается из сохранённых логов.
MAX_TRACKED = 200
_progress: "OrderedDict[int, dict[str, dict]]" = OrderedDict()
_background_tasks: set = set()
_tasks_by_execution: dict[int, asyncio.Task] = {}


def record_progress(execution_id: int, node_id: str, status: str, duration_ms: Optional[int] = None) -> None:
    nodes = _progress.setdefault(execution_id, {})
    nodes[node_id] = {"status": status, "ms": duration_ms}
    while len(_progress) > MAX_TRACKED:
        _progress.popitem(last=False)


def get_progress(execution: Execution) -> dict[str, dict]:
    if execution.id in _progress:
        return _progress[execution.id]
    return {
        entry["node_id"]: {"status": "failed" if is_error_output(entry.get("output")) else "done", "ms": None}
        for entry in (execution.logs or []) if entry.get("node_id")
    }


async def load_connections(db: AsyncSession, user_id: int) -> dict:
    rows = (await db.execute(select(Connection).where(Connection.user_id == user_id))).scalars().all()
    result = {}
    for c in rows:
        cfg = await refresh_if_needed(c, db) if c.provider in GOOGLE_PROVIDERS else decrypt_config(c.config)
        result[c.id] = {"provider": c.provider, "config": cfg}
    return result


async def create_execution(
    db: AsyncSession, user: User, workflow: Workflow, trigger_data: Optional[dict[str, Any]] = None,
    source: str = "manual",
) -> Execution:
    """Проверка лимитов и создание записи запуска (статус running)."""
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
    return execution


async def execute_execution(
    db: AsyncSession, user: User, workflow: Workflow, execution: Execution, trigger_data: Optional[dict[str, Any]] = None,
) -> Execution:
    connections = await load_connections(db, user.id)
    engine = WorkflowEngine(
        {"name": workflow.name, "nodes": workflow.nodes, "edges": workflow.edges},
        execution.id, connections=connections, llm_guard=platform_guard,
        on_progress=lambda node_id, status, ms: record_progress(execution.id, node_id, status, ms),
    )

    _running[user.id] += 1
    try:
        result = await asyncio.wait_for(engine.execute(trigger_data), timeout=settings.max_execution_seconds)
        # Ошибки нод (LLM Error, HTTP Error и т.п.) не бросают исключение — движок продолжает.
        # Если хотя бы один шаг упал, сценарий считаем неуспешным (красный статус в истории).
        error_outputs = [
            entry.get("output")
            for entry in engine.logs
            if is_error_output(entry.get("output"))
        ]
        progress_nodes = _progress.get(execution.id, {})
        has_failed_progress = any(s.get("status") == "failed" for s in progress_nodes.values())
        if error_outputs or has_failed_progress:
            execution.status = "failed"
            payload = result if isinstance(result, dict) else {"result": result}
            if isinstance(payload, dict) and "error" not in payload:
                payload = {**payload, "error": error_outputs[0] if error_outputs else "Один или несколько шагов завершились с ошибкой"}
            execution.result = _jsonable(payload)
        else:
            execution.status = "success"
            execution.result = _jsonable(result)
    except asyncio.CancelledError:                 # кнопка «Стоп»
        execution.status = "cancelled"
        execution.result = {"error": "Остановлено пользователем"}
        for state in _progress.get(execution.id, {}).values():
            if state["status"] == "running":
                state["status"] = "stopped"
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


async def run_workflow(
    db: AsyncSession, user: User, workflow: Workflow, trigger_data: Optional[dict[str, Any]] = None,
    source: str = "manual",
) -> Execution:
    execution = await create_execution(db, user, workflow, trigger_data, source)
    return await execute_execution(db, user, workflow, execution, trigger_data)


def start_in_background(execution_id: int, user_id: int, workflow_id: int, trigger_data: Optional[dict[str, Any]]) -> None:
    """Выполняет уже созданный запуск в фоне (своя сессия БД): ответ клиенту уходит сразу, прогресс читается опросом."""
    async def job():
        async with async_session() as db:
            execution = await db.get(Execution, execution_id)
            workflow = await db.get(Workflow, workflow_id)
            user = await db.get(User, user_id)
            if not (execution and workflow and user):
                return
            try:
                await execute_execution(db, user, workflow, execution, trigger_data)
            except Exception:
                traceback.print_exc()
                execution.status = "failed"
                execution.result = {"error": "Внутренняя ошибка запуска"}
                execution.finished_at = datetime.now(timezone.utc)
                await db.commit()

    task = asyncio.create_task(job())
    _background_tasks.add(task)
    _tasks_by_execution[execution_id] = task
    task.add_done_callback(lambda t: (_background_tasks.discard(t), _tasks_by_execution.pop(execution_id, None)))


def cancel_task(execution_id: int) -> bool:
    """Останавливает выполняющийся запуск. False — живой задачи нет."""
    task = _tasks_by_execution.get(execution_id)
    if not task or task.done():
        return False
    task.cancel()
    return True


def _jsonable(value):
    import json
    return json.loads(json.dumps(value, default=str, ensure_ascii=False))
