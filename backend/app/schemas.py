from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

class WorkflowNode(BaseModel):
    id: str
    type: str
    config: Dict[str, Any] = {}

class WorkflowEdge(BaseModel):
    id: str
    from_node: str
    to_node: str
    condition: Optional[str] = None

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