"""Webhook-триггер: внешний сервис вызывает URL воркфлоу и запускает его с телом запроса."""
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import User, Workflow
from ..security import constant_eq, sign
from ..services.ratelimit import client_ip, webhook_limiter
from ..services.runner import run_workflow

router = APIRouter(tags=["webhooks"])
MAX_BODY_BYTES = 100_000


def webhook_token(workflow_id: int) -> str:
    return sign(str(workflow_id), "wf-webhook")


def webhook_url(workflow_id: int) -> str:
    return f"{settings.base_url or 'http://localhost:8000'}/api/webhooks/{workflow_id}/{webhook_token(workflow_id)}"


@router.get("/workflows/{workflow_id}/webhook-url")
async def get_webhook_url(workflow_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    wf = await db.get(Workflow, workflow_id)
    if not wf or wf.user_id != user.id:
        raise HTTPException(404, "Workflow not found")
    return {"url": webhook_url(workflow_id)}


@router.api_route("/webhooks/{workflow_id}/{token}", methods=["GET", "POST"])
async def receive_webhook(workflow_id: int, token: str, request: Request, db: AsyncSession = Depends(get_db)):
    if not constant_eq(token, webhook_token(workflow_id)):
        raise HTTPException(404, "Not found")
    webhook_limiter.check(f"{workflow_id}:{client_ip(request)}")

    wf = await db.get(Workflow, workflow_id)
    if not wf or not wf.is_active or not any(n.get("type") == "webhook" for n in (wf.nodes or [])):
        raise HTTPException(404, "Not found")
    user = await db.get(User, wf.user_id)
    if not user or not user.is_active:
        raise HTTPException(404, "Not found")

    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        raise HTTPException(413, "Body too large")
    text = raw.decode("utf-8", errors="replace")
    try:
        body = json.loads(text) if text.strip() else {}
    except ValueError:
        body = text

    trigger = {
        "input": text,
        "webhook": {"body": body, "query": dict(request.query_params), "method": request.method},
    }
    execution = await run_workflow(db, user, wf, trigger, source="webhook")
    return {"execution_id": execution.id, "status": execution.status}
