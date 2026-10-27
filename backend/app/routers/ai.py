from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..models import Connection, User
from ..services import ai_assistant as assistant
from ..services.limits import bump_usage, check_chat_quota, get_user_plan
from ..services.llm import LLMProvider
from ..services.platform_ai import AIUnavailable, platform_guard
from ..services.ratelimit import ai_chat_limiter
from ..services.runner import load_connections

router = APIRouter(prefix="/ai", tags=["ai"])


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=4000)


class ChatIn(BaseModel):
    messages: List[ChatMessage] = Field(min_length=1, max_length=50)
    workflow: Optional[Dict[str, Any]] = None
    connection_id: Optional[int] = None       # свой AI-ключ пользователя вместо ключа платформы
    model: Optional[str] = Field(default=None, max_length=120)


@router.post("/chat")
async def chat(data: ChatIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    ai_chat_limiter.check(str(user.id), "Слишком часто, подождите немного")
    if data.messages[-1].role != "user":
        raise HTTPException(400, detail={"code": "bad_request", "message": "Последнее сообщение должно быть от пользователя"})
    plan = await get_user_plan(db, user)
    await check_chat_quota(db, user, plan)

    rows = (await db.execute(select(Connection).where(Connection.user_id == user.id))).scalars().all()
    public = [{"id": c.id, "provider": c.provider, "name": c.name} for c in rows]
    connections = await load_connections(db, user.id)

    system = assistant.build_system_prompt(data.workflow, public)
    history = [{"role": m.role, "content": m.content} for m in data.messages[-assistant.MAX_HISTORY:]]
    llm = LLMProvider(connections=connections, guard=platform_guard)
    try:
        message = await llm.chat(
            [{"role": "system", "content": system}, *history], model=data.model, temperature=0.2,
            mode=settings.default_llm_mode if not data.connection_id else "cloud",
            connection_id=data.connection_id, json_mode=True,
        )
    except AIUnavailable as e:
        raise HTTPException(503, detail={"code": "ai_unavailable", "message": str(e)})
    except Exception as e:
        raise HTTPException(502, detail={"code": "llm_error", "message": f"Ошибка языковой модели: {e}"})

    await bump_usage(db, user.id, "ai_chat")
    text = message.get("content") or ""
    parsed = assistant.extract_json(text)
    if parsed is None:
        return {"reply": text.strip() or "Модель вернула пустой ответ", "workflow": None}
    workflow = assistant.sanitize_workflow(parsed.get("workflow"), data.workflow, public)
    reply = parsed.get("reply") if isinstance(parsed.get("reply"), str) else ""
    if parsed.get("workflow") and workflow is None:
        reply = (reply + "\n\n" if reply else "") + "Не удалось построить корректный граф — попробуйте сформулировать запрос подробнее."
    return {"reply": reply or "Готово", "workflow": workflow}
