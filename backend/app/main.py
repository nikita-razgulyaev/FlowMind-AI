import traceback

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any

from .database import get_db, engine, Base
from .models import Workflow, Execution, Connection
from .schemas import WorkflowCreate, WorkflowResponse, ExecutionResponse, ConnectionCreate, ConnectionResponse
from .templates import TEMPLATES
from .worker import WorkflowEngine

app = FastAPI(title="FlowMind AI Lite")

SECRET_KEYS = {"api_key", "bot_token", "token", "password", "secret"}

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
    connections = {
        c.id: {"provider": c.provider, "config": c.config}
        for c in conn_result.scalars().all()
    }

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