"""每段 AI 会话的一行结构化购物记忆。"""
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from app.database import Base

class AIChatSession(Base):
    __tablename__ = "ai_chat_sessions"
    __table_args__ = (UniqueConstraint("user_id", "session_id", name="uq_ai_chat_session_user_session"),)
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(String(50), nullable=False, index=True)
    memory_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)