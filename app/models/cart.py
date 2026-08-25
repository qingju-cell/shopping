# ============================================================
# cart.py —— 购物车表 ORM 模型
# 功能：映射数据库中的 cart_items 表，存储用户的购物车数据
# 对应数据库表：cart_items
# 字段说明：
#   - id: 购物车项ID（主键，自增）
#   - user_id: 用户ID（关联 users 表）
#   - product_id: 商品ID（关联 products 表）
#   - quantity: 购买数量
#   - created_at: 添加时间
#   - updated_at: 更新时间
# ============================================================

from sqlalchemy import Column, Integer, DateTime
from sqlalchemy.sql import func
from app.database import Base


# CartItem 类对应数据库中的 cart_items 表
# 一个用户可以有多个购物车项，每个购物车项对应一个商品
class CartItem(Base):
    __tablename__ = "cart_items"

    # ---------- 主键 ----------
    id = Column(Integer, primary_key=True, autoincrement=True, comment="购物车项ID")

    # ---------- 关联字段 ----------
    user_id = Column(Integer, nullable=False, comment="用户ID")
    product_id = Column(Integer, nullable=False, comment="商品ID")

    # ---------- 数量 ----------
    quantity = Column(Integer, nullable=False, default=1, comment="商品数量")

    # ---------- 时间戳 ----------
    created_at = Column(DateTime, server_default=func.now(), comment="添加时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    def to_dict(self):
        return{
            "id":self.id,
            "user_id":self.user_id,
            "product_id":self.product_id,
            "quantity":self.quantity,
            "created_at":self.created_at.isoformat(),
            "updated_at":self.updated_at.isoformat(),
        }
