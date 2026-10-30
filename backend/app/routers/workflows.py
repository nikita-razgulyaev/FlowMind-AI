import copy
from datetime import timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Execution, User, Workflow, utcnow
from ..schemas import WorkflowCreate, WorkflowResponse
from ..services import telegram_service
from ..services.limits import QuotaError, check_workflow_quota, get_user_plan, workflow_flags
from ..services.runner import run_workflow
from ..templates import TEMPLATES

router = APIRouter(tags=["workflows"])


def _validate_graph(data: WorkflowCreate) -> None:
    if len(data.nodes) > settings.max_nodes_per_workflow:
        raise HTTPException(400, detail={"code": "too_many_nodes", "message": f"Максимум {settings.max_nodes_per_workflow} нод в воркфлоу"})
    ids = [n.id for n in data.nodes]
    if len(ids) != len(set(ids)):
        raise HTTPException(400, detail={"code": "duplicate_nodes", "message": "Идентификаторы нод должны быть уникальными"})


async def _get_own(db: AsyncSession, user: User, workflow_id: int) -> Workflow:
    wf = await db.get(Workflow, workflow_id)
    if not wf or wf.user_id != user.id:
        raise HTTPException(404, "Workflow not found")
    return wf


@router.post("/workflows/", response_model=WorkflowResponse)
async def create_workflow(data: WorkflowCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    _validate_graph(data)
    nodes = [n.model_dump() for n in data.nodes]
    is_ai, has_tg = workflow_flags(nodes)
    plan = await get_user_plan(db, user)
    await check_workflow_quota(db, user, plan, is_ai=is_ai, has_tg=has_tg, active=data.is_active)

    wf = Workflow(user_id=user.id, name=data.name, description=data.description, nodes=nodes,
                  edges=[e.model_dump() for e in data.edges], is_active=data.is_active,
                  is_ai=is_ai, has_telegram_trigger=has_tg)
    db.add(wf)
    await db.commit()
    await db.refresh(wf)
    if has_tg:
        await telegram_service.sync_user_webhooks(db, user.id)
    return wf


@router.get("/workflows/", response_model=list[WorkflowResponse])
async def list_workflows(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow).where(Workflow.user_id == user.id).order_by(Workflow.id.desc()))
    return result.scalars().all()


@router.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _get_own(db, user, workflow_id)


@router.put("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(workflow_id: int, data: WorkflowCreate, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    wf = await _get_own(db, user, workflow_id)
    _validate_graph(data)
    nodes = [n.model_dump() for n in data.nodes]
    is_ai, has_tg = workflow_flags(nodes)

    # Лимиты проверяем только при переходе «обычный → AI» или «триггер выключен → включён»,
    # чтобы после понижения тарифа можно было редактировать уже существующие воркфлоу.
    becomes_ai = is_ai and not wf.is_ai
    becomes_regular = (not is_ai) and wf.is_ai
    becomes_tg = has_tg and data.is_active and not (wf.has_telegram_trigger and wf.is_active)
    if becomes_ai or becomes_regular or becomes_tg:
        plan = await get_user_plan(db, user)
        await _check_transition(db, user, plan, wf, is_ai, becomes_ai or becomes_regular, becomes_tg)

    had_tg = wf.has_telegram_trigger
    wf.name, wf.description = data.name, data.description
    wf.nodes, wf.edges = nodes, [e.model_dump() for e in data.edges]
    wf.is_active, wf.is_ai, wf.has_telegram_trigger = data.is_active, is_ai, has_tg
    await db.commit()
    await db.refresh(wf)
    if has_tg or had_tg:
        await telegram_service.sync_user_webhooks(db, user.id)
    return wf


async def _check_transition(db, user, plan, wf, is_ai, category_changed, tg_changed) -> None:
    """Проверяет только ту квоту, которую изменение действительно затрагивает."""
    def count(*conds):
        return select(func.count()).select_from(Workflow).where(Workflow.user_id == user.id, Workflow.id != wf.id, *conds)

    if category_changed:
        limit = plan.max_ai_workflows if is_ai else plan.max_regular_workflows
        if limit is not None:
            n = (await db.execute(count(Workflow.is_ai.is_(is_ai)))).scalar_one()
            if n + 1 > limit:
                raise QuotaError("ai_workflows" if is_ai else "regular_workflows", limit)
    if tg_changed and plan.telegram_triggers is not None:
        n = (await db.execute(count(Workflow.has_telegram_trigger.is_(True), Workflow.is_active.is_(True)))).scalar_one()
        if n + 1 > plan.telegram_triggers:
            raise QuotaError("telegram_triggers", plan.telegram_triggers,
                             "Telegram-триггеры недоступны на вашем тарифе." if plan.telegram_triggers == 0 else None)


@router.delete("/workflows/{workflow_id}")
async def delete_workflow(workflow_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    wf = await _get_own(db, user, workflow_id)
    had_tg = wf.has_telegram_trigger
    await db.execute(delete(Execution).where(Execution.workflow_id == wf.id, Execution.user_id == user.id))
    await db.delete(wf)
    await db.commit()
    if had_tg:
        await telegram_service.sync_user_webhooks(db, user.id)
    return {"message": "Workflow deleted"}


class IdsIn(BaseModel):
    ids: list[int]


@router.post("/workflows/bulk-delete")
async def bulk_delete_workflows(data: IdsIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    ids = list({int(i) for i in data.ids if i})
    if not ids:
        return {"deleted": 0}
    rows = (await db.execute(select(Workflow).where(Workflow.user_id == user.id, Workflow.id.in_(ids)))).scalars().all()
    had_tg = False
    for wf in rows:
        had_tg = had_tg or wf.has_telegram_trigger
        await db.execute(delete(Execution).where(Execution.workflow_id == wf.id, Execution.user_id == user.id))
        await db.delete(wf)
    await db.commit()
    if had_tg:
        await telegram_service.sync_user_webhooks(db, user.id)
    return {"deleted": len(rows)}


@router.post("/executions/bulk-delete")
async def bulk_delete_executions(data: IdsIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    ids = list({int(i) for i in data.ids if i})
    if not ids:
        return {"deleted": 0}
    result = await db.execute(
        delete(Execution).where(Execution.user_id == user.id, Execution.id.in_(ids))
    )
    await db.commit()
    return {"deleted": result.rowcount or 0}


@router.post("/workflows/{workflow_id}/execute")
async def execute_workflow(workflow_id: int, trigger_data: Optional[Dict[str, Any]] = None,
                           user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    wf = await _get_own(db, user, workflow_id)
    execution = await run_workflow(db, user, wf, trigger_data or {}, source="manual")
    return {"execution_id": execution.id, "status": execution.status, "result": execution.result}


# ───────── шаблоны ─────────

@router.get("/templates")
async def list_templates(user: User = Depends(get_current_user)):
    return TEMPLATES


@router.post("/workflows/from-template/{template_id}", response_model=WorkflowResponse)
async def create_from_template(template_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    template = TEMPLATES.get(template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    nodes = copy.deepcopy(template["nodes"])
    for i, node in enumerate(nodes):
        # Горизонтальная цепочка — без переноса на следующую строку
        if not node.get("position"):
            node["position"] = {"x": 80 + i * 320, "y": 120}
        cfg = node.get("config", {})
        if node["type"] in ("llm", "agent") and settings.is_local and cfg.get("mode") == "cloud" and not cfg.get("connection_id"):
            cfg["mode"], cfg["model"] = "local", settings.ollama_model     # в локальной версии шаблоны работают на Ollama
    is_ai, has_tg = workflow_flags(nodes)
    plan = await get_user_plan(db, user)
    await check_workflow_quota(db, user, plan, is_ai=is_ai, has_tg=has_tg, active=True)
    wf = Workflow(user_id=user.id, name=template["name"], description=template.get("description", ""),
                  nodes=nodes, edges=copy.deepcopy(template["edges"]), is_active=True,
                  is_ai=is_ai, has_telegram_trigger=has_tg)
    db.add(wf)
    await db.commit()
    await db.refresh(wf)
    return wf


# ───────── история выполнений ─────────

@router.get("/executions")
async def list_executions(workflow_id: Optional[int] = None, user: User = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db)):
    plan = await get_user_plan(db, user)
    q = select(Execution).where(Execution.user_id == user.id).order_by(Execution.id.desc()).limit(200)
    if workflow_id:
        q = q.where(Execution.workflow_id == workflow_id)
    if plan.history_days:
        q = q.where(Execution.started_at >= utcnow() - timedelta(days=plan.history_days))
    return [_exec_dto(e) for e in (await db.execute(q)).scalars().all()]


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    e = await db.get(Execution, execution_id)
    if not e or e.user_id != user.id:
        raise HTTPException(404, "Execution not found")
    return _exec_dto(e)


def _exec_dto(e: Execution) -> dict:
    return {"id": e.id, "workflow_id": e.workflow_id, "status": e.status, "source": e.source, "is_ai": e.is_ai,
            "trigger_data": e.trigger_data, "result": e.result, "logs": e.logs,
            "started_at": e.started_at, "finished_at": e.finished_at}
