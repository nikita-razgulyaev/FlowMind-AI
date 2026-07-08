from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Dict, Any

from .database import get_db, engine, Base
from .models import Workflow, Execution
from .schemas import WorkflowCreate, WorkflowResponse, ExecutionResponse
from .templates import TEMPLATES
from .worker import WorkflowEngine

app = FastAPI(title="FlowMind AI Lite")

# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

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
    
    engine_obj = WorkflowEngine(workflow_dict, execution.id)
    
    try:
        result = await engine_obj.execute(trigger_data)
        
        execution.status = "success"
        execution.result = result
        execution.logs = engine_obj.logs
        
    except Exception as e:
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