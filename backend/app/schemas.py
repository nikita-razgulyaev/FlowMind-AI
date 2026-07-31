from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

class WorkflowNode(BaseModel):
    id: str
    type: str
    config: Dict[str, Any] = {}
    position: Optional[Dict[str, float]] = None

class WorkflowEdge(BaseModel):
    id: str
    from_node: str
    to_node: str
    condition: Optional[str] = None
    type: Optional[str] = "next"  # "next" (обычный порядок) | "tool" (доступен агенту как инструмент)

class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    nodes: List[WorkflowNode]
    edges: List[WorkflowEdge]
    is_active: bool = True

class WorkflowResponse(WorkflowCreate):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class ExecutionResponse(BaseModel):
    id: int
    workflow_id: int
    status: str
    trigger_data: Optional[Dict[str, Any]]
    result: Optional[Dict[str, Any]]
    logs: List[Dict[str, Any]]
    started_at: datetime
    finished_at: Optional[datetime]
    
class Config:
    from_attributes = True

class ConnectionCreate(BaseModel):
    category: str          # "ai_api" | "tool"
    provider: str          # "huggingface" | "openai_compatible" | "telegram_bot" | "google_sheets" | "google_calendar"
    name: str
    config: Dict[str, Any] = {}

class ConnectionResponse(BaseModel):
    id: int
    category: str
    provider: str
    name: str
    config: Dict[str, Any]
    created_at: datetime

class Config:
    from_attributes = True