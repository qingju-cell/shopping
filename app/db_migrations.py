"""开发环境的最小表结构升级。正式生产环境应改用 Alembic 管理迁移。"""

from sqlalchemy import inspect, text

from app.database import engine


def ensure_order_agent_draft_id_column() -> None:
    """为已有 orders 表补上 AI 草稿唯一编号列；已存在时不做任何事。"""
    inspector = inspect(engine)
    if "orders" not in inspector.get_table_names():
        return
    column_names = {column["name"] for column in inspector.get_columns("orders")}
    if "agent_draft_id" in column_names:
        return
    with engine.begin() as connection:
        connection.execute(text(
            "ALTER TABLE orders ADD COLUMN agent_draft_id VARCHAR(36) NULL UNIQUE COMMENT 'AI 下单草稿唯一编号'"
        ))
