from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, func
from app.database import Base

class AIChatMessage(Base):
    __tablename__ = 'ai_chat_messages'
    id = Column(Integer, primary_key=True, autoincrement=True, comment='消息ID')
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True, comment='用户ID')
    session_id = Column(String(50), nullable=False, index=True, comment='会话ID')
    role = Column(String(10), nullable=False, comment='角色：user/ai')
    content = Column(Text, nullable=False, comment='消息内容')
    intent = Column(String(20), comment='意图分类：product/chat/service/abuse')
    created_at = Column(DateTime, server_default=func.now(), comment='创建时间')

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'session_id': self.session_id,
            'role': self.role,
            'content': self.content,
            'intent': self.intent,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
