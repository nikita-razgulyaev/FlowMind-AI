import traceback
import os
import json
from datetime import datetime, timedelta
from urllib.parse import urlencode

from dotenv import load_dotenv
load_dotenv()

import httpx
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any

from .database import get_db, engine, Base
from .models import Workflow, Execution, Connection
from .schemas import WorkflowCreate, WorkflowResponse, ExecutionResponse, ConnectionCreate, ConnectionResponse
from .templates import TEMPLATES
from .worker import WorkflowEngine

app = FastAPI(title="FlowMind AI Lite")

# Данные OAuth-приложения — заводятся в Google Cloud Console (см. инструкцию),
# сюда попадают только через .env, в БД никогда не хранятся.
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/oauth/google/callback")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
# Параметризовано ради тестируемости (в тестах подменяются на локальный мок-сервер)
GOOGLE_AUTH_URL = os.getenv("GOOGLE_AUTH_URL", "https://accounts.google.com/o/oauth2/v2/auth")
GOOGLE_TOKEN_URL = os.getenv("GOOGLE_TOKEN_URL", "https://oauth2.googleapis.com/token")

GOOGLE_SCOPES = {
    "google_sheets": "https://www.googleapis.com/auth/spreadsheets",
    "google_calendar": "https://www.googleapis.com/auth/calendar",
}

SECRET_KEYS = {"api_key", "bot_token", "token", "password", "secret", "access_token", "refresh_token"}

def _mask_connection(conn: Connection) -> dict:
    masked_config = {}
    for k, v in (conn.config or {}).items():
        if k in SECRET_KEYS and isinstance(v, str) and len(v) > 4:
            masked_config[k] = "••••••" + v[-4:]
        else:
            masked_config[k] = v
    return {
        "id": conn.id,
        "category": conn.category,
        "provider": conn.provider,
        "name": conn.name,
        "config": masked_config,
        "created_at": conn.created_at,
    }

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/workflows/", response_model=List[WorkflowResponse])
async def get_workflows(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow))
    workflows = result.scalars().all()
    return workflows

@app.post("/workflows/", response_model=WorkflowResponse)
async def create_workflow(data: WorkflowCreate, db: AsyncSession = Depends(get_db)):
    workflow = Workflow(
        name=data.name,
        description=data.description,
        nodes=[n.model_dump() for n in data.nodes],
        edges=[e.model_dump() for e in data.edges],
        is_active=data.is_active
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)
    return workflow

@app.put("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow(workflow_id: int, data: WorkflowCreate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(404, "Workflow not found")

    workflow.name = data.name
    workflow.description = data.description
    workflow.nodes = [n.model_dump() for n in data.nodes]
    workflow.edges = [e.model_dump() for e in data.edges]
    workflow.is_active = data.is_active

    await db.commit()
    await db.refresh(workflow)
    return workflow

@app.delete("/workflows/{workflow_id}")
async def delete_workflow(workflow_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(404, "Workflow not found")
    await db.delete(workflow)
    await db.commit()
    return {"deleted": workflow_id}

@app.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(404, "Workflow not found")
    return workflow

@app.post("/workflows/{workflow_id}/execute")
async def execute_workflow(workflow_id: int, trigger_data: Dict[str, Any] = None, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
    workflow = result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(404, "Workflow not found")
    
    # Создаём execution со статусом running
    execution = Execution(
        workflow_id=workflow_id,
        status="running",
        trigger_data=trigger_data
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)
    
    # Синхронное выполнение (без Celery)
    workflow_dict = {
        "name": workflow.name,
        "nodes": workflow.nodes,
        "edges": workflow.edges
    }

    # Подключения нужны движку в реальном (немаскированном) виде — в отличие от
    # /connections/, этот эндпоинт никогда не отдаёт данные наружу, а использует
    # их только внутри процесса выполнения.
    conn_result = await db.execute(select(Connection))
    all_connections = conn_result.scalars().all()
    connections = {}
    for c in all_connections:
        cfg = c.config
        if c.provider in GOOGLE_SCOPES:
            cfg = await _refresh_google_connection_if_needed(c, db)
        connections[c.id] = {"provider": c.provider, "config": cfg}

    engine_obj = WorkflowEngine(workflow_dict, execution.id, connections=connections)
    
    try:
        result = await engine_obj.execute(trigger_data)
        
        execution.status = "success"
        execution.result = result
        execution.logs = engine_obj.logs
        
    except Exception as e:
        traceback.print_exc()
        execution.status = "failed"
        execution.result = {"error": str(e)}
        execution.logs = engine_obj.logs
    
    await db.commit()
    
    return {"execution_id": execution.id, "status": execution.status}

@app.get("/executions/")
async def get_executions(workflow_id: int = None, db: AsyncSession = Depends(get_db)):
    query = select(Execution)
    if workflow_id:
        query = query.where(Execution.workflow_id == workflow_id)
    query = query.order_by(Execution.started_at.desc())
    result = await db.execute(query)
    return result.scalars().all()

@app.get("/executions/{execution_id}", response_model=ExecutionResponse)
async def get_execution(execution_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Execution).where(Execution.id == execution_id))
    execution = result.scalar_one_or_none()
    if not execution:
        raise HTTPException(404, "Execution not found")
    return execution

@app.get("/templates/")
async def get_templates():
    return TEMPLATES

@app.post("/workflows/from-template/{template_name}")
async def create_from_template(template_name: str, db: AsyncSession = Depends(get_db)):
    template = TEMPLATES.get(template_name)
    if not template:
        raise HTTPException(404, "Template not found")
    
    workflow = Workflow(
        name=template["name"],
        description=template["description"],
        nodes=template["nodes"],
        edges=template["edges"],
        is_active=template["is_active"]
    )
    db.add(workflow)
    await db.commit()
    await db.refresh(workflow)
    return {"id": workflow.id, "template": template_name}

@app.get("/connections/")
async def get_connections(category: str = None, db: AsyncSession = Depends(get_db)):
    query = select(Connection)
    if category:
        query = query.where(Connection.category == category)
    result = await db.execute(query)
    return [_mask_connection(c) for c in result.scalars().all()]

@app.post("/connections/")
async def create_connection(data: ConnectionCreate, db: AsyncSession = Depends(get_db)):
    conn = Connection(category=data.category, provider=data.provider, name=data.name, config=data.config)
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return _mask_connection(conn)

@app.delete("/connections/{connection_id}")
async def delete_connection(connection_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Connection).where(Connection.id == connection_id))
    conn = result.scalar_one_or_none()
    if not conn:
        raise HTTPException(404, "Connection not found")
    await db.delete(conn)
    await db.commit()
    return {"deleted": connection_id}


@app.get("/oauth/google/start")
async def google_oauth_start(provider: str, name: str):
    """Возвращает ссылку на экран согласия Google — фронтенд делает на неё редирект."""
    if provider not in GOOGLE_SCOPES:
        raise HTTPException(400, f"Unknown Google provider: {provider}")
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            500,
            "GOOGLE_CLIENT_ID не задан в .env — сначала заведи OAuth-приложение в Google Cloud Console",
        )

    state = json.dumps({"provider": provider, "name": name})
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GOOGLE_SCOPES[provider],
        "access_type": "offline",   # ← без этого Google не выдаст refresh_token
        "prompt": "consent",        # ← иначе refresh_token придёт только при первом согласии
        "state": state,
    }
    return {"auth_url": f"{GOOGLE_AUTH_URL}?{urlencode(params)}"}


@app.get("/oauth/google/callback")
async def google_oauth_callback(code: str, state: str, db: AsyncSession = Depends(get_db)):
    """Google возвращает пользователя сюда после согласия. Обмениваем code на токены и сохраняем подключение."""
    try:
        state_data = json.loads(state)
        provider = state_data["provider"]
        name = state_data["name"]
    except (json.JSONDecodeError, KeyError):
        raise HTTPException(400, "Invalid state")

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        })
        if response.status_code != 200:
            return RedirectResponse(url=f"{FRONTEND_URL}/connections?error=google_oauth_failed")
        tokens = response.json()

    conn = Connection(
        category="tool",
        provider=provider,
        name=name,
        config={
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"),
            "expires_in": tokens.get("expires_in", 3600),
            "obtained_at": datetime.utcnow().isoformat(),
        },
    )
    db.add(conn)
    await db.commit()
    return RedirectResponse(url=f"{FRONTEND_URL}/connections?connected=1")


async def _refresh_google_connection_if_needed(conn: Connection, db: AsyncSession) -> dict:
    """
    Проверяет, не истёк ли access_token (с запасом в 60 секунд), и если истёк —
    обновляет его через refresh_token, сохраняя новое значение в БД.
    Возвращает актуальный (немаскированный) config для использования движком.
    """
    cfg = dict(conn.config or {})
    obtained_at = cfg.get("obtained_at")
    expires_in = cfg.get("expires_in", 3600)
    refresh_token = cfg.get("refresh_token")

    is_expired = True
    if obtained_at:
        try:
            obtained = datetime.fromisoformat(obtained_at)
            is_expired = datetime.utcnow() >= obtained + timedelta(seconds=expires_in - 60)
        except ValueError:
            is_expired = True

    if not is_expired or not refresh_token:
        return cfg

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(GOOGLE_TOKEN_URL, data={
            "refresh_token": refresh_token,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "grant_type": "refresh_token",
        })
        if response.status_code != 200:
            # Не удалось обновить — отдаём как есть, нода сама сообщит об ошибке авторизации
            return cfg
        tokens = response.json()

    cfg["access_token"] = tokens["access_token"]
    cfg["expires_in"] = tokens.get("expires_in", expires_in)
    cfg["obtained_at"] = datetime.utcnow().isoformat()
    # refresh_token Google обычно не переотдаёт повторно — сохраняем старый
    conn.config = cfg
    db.add(conn)
    await db.commit()
    return cfg