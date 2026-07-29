from sqlalchemy import Column, Integer, String, DateTime, JSON, Boolean
from sqlalchemy.sql import func
from .database import Base

class Workflow(Base):
    __tablename__ = "workflows"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    description = Column(String, default="")
    nodes = Column(JSON, default=list)
    edges = Column(JSON, default=list)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Execution(Base):
    __tablename__ = "executions"
    
    id = Column(Integer, primary_key=True, index=True)
    workflow_id = Column(Integer, nullable=False)
    status = Column(String, default="pending")
    trigger_data = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    logs = Column(JSON, default=list)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)

class Connection(Base):
    __tablename__ = "connections"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String, nullable=False)   # "ai_api" | "tool"
    provider = Column(String, nullable=False)   # "huggingface" | "openai_compatible" | "telegram_bot" | "google_sheets" | "google_calendar"
    name = Column(String, nullable=False)
    config = Column(JSON, default=dict)          # секреты/параметры конкретного провайдера
    created_at = Column(DateTime(timezone=True), server_default=func.now())