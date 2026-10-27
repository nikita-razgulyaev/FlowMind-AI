from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


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
    type: Optional[str] = "next"      # "next" (порядок выполнения) | "tool" (инструмент агента)


class WorkflowCreate(BaseModel):
    name: str = Field(max_length=200)
    description: str = Field("", max_length=1000)
    nodes: List[WorkflowNode]
    edges: List[WorkflowEdge]
    is_active: bool = True


class WorkflowResponse(WorkflowCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    is_ai: bool = False
    has_telegram_trigger: bool = False
    created_at: datetime


class ConnectionCreate(BaseModel):
    category: str
    provider: str
    name: str = Field(max_length=120)
    config: Dict[str, Any] = {}


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field("", max_length=120)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)
