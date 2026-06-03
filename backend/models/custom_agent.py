from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON
from backend.db.database import Base

class CustomAgent(Base):
    __tablename__ = 'custom_agents'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False, unique=True)
    agent_id = Column(String, nullable=False, unique=True)
    system_prompt = Column(String, nullable=False)
    llm_adapter = Column(String, default="tongyi")
    tools = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)