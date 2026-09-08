# ============================================================
# order.py —— 订单表 & 订单明细表 ORM 模型
# 功能：映射数据库中的 orders 表和 order_items 表
# 设计说明：
#   - Order（订单主表）：存储订单的整体信息
#   - OrderItem（订单明细表）：存储订单中每个商品的快照信息
#   - 一对多关系：一个订单可以有多个订单明细
# 对应数据库表：orders, order_items
# ============================================================

from sqlalchemy import Column, Integer, String, DECIMAL, DateTime, SmallInteger, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


# ==================== 订单主表 ====================
class Order(Base):
    """
    订单主表：存储订单的整体信息
    一个订单由多个 OrderItem（订单明细）组成
    """
    __tablename__ = "orders"

    # ---------- 主键 ----------
    id = Column(Integer, primary_key=True, autoincrement=True, comment="订单ID")

    # ---------- 订单基本信息 ----------
    # order_no 是业务编号，唯一，用于展示给用户（不同于自增 ID）
    order_no = Column(String(32), unique=True, nullable=False, comment="订单编号")
    user_id = Column(Integer, nullable=False, comment="用户ID")
    # total_amount 是订单总金额（所有明细的小计之和）
    total_amount = Column(DECIMAL(10, 2), nullable=False, comment="订单总金额")

    # ---------- 订单状态 ----------
    # 订单状态在后端和前端共用同一套编号，不能各自定义：
    # 0: 待支付 -> 1: 已支付 -> 2: 已发货 -> 3: 已完成；4: 已取消
    status = Column(SmallInteger, default=0, comment="订单状态：0待支付 1已支付 2已发货 3已完成 4已取消")

    # ---------- 收货信息 ----------
    receiver_name = Column(String(50), comment="收货人姓名")
    receiver_phone = Column(String(20), comment="收货人电话")
    receiver_address = Column(String(500), comment="收货地址")
    remark = Column(String(500), comment="订单备注")

    # ---------- 时间戳 ----------
    created_at = Column(DateTime, server_default=func.now(), comment="下单时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    # ---------- 关联关系（一对多）----------
    # relationship 告诉 SQLAlchemy：Order 和 OrderItem 之间是一对多关系
    # back_populates 让 OrderItem 也能反向访问到所属的 Order
    # 这样在查询订单时，可以通过 order.order_items 获取所有明细
    order_items = relationship("OrderItem", back_populates="order")

    def to_dict(self):
        return{
            "id":self.id,
            "order_no":self.order_no,
            "user_id":self.user_id,
            "total_amount":float(self.total_amount),
            "status":self.status,
            "receiver_name":self.receiver_name,
            "receiver_phone":self.receiver_phone,
            "receiver_address":self.receiver_address,
            "remark":self.remark,
            "created_at":self.created_at.isoformat(),
            "updated_at":self.updated_at.isoformat(),
        }




# ==================== 订单明细表 ====================
class OrderItem(Base):
    """
    订单明细表：存储订单中每个商品的快照信息
    
    注意：这里的商品信息是"快照"，即下单时的商品名称、价格
    即使后来商品信息变了，订单中的记录也不会变（符合业务需求）
    """
    __tablename__ = "order_items"

    # ---------- 主键 ----------
    id = Column(Integer, primary_key=True, autoincrement=True, comment="明细ID")

    # ---------- 关联订单 ----------
    # ForeignKey 定义外键，关联到 orders 表的 id 字段
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, comment="订单ID")

    # ---------- 商品快照信息 ----------
    # 下单时的商品 ID
    product_id = Column(Integer, nullable=False, comment="商品ID")
    # 下单时的商品名称（快照，不随商品修改而变化）
    product_name = Column(String(200), nullable=False, comment="商品名称快照")
    # 下单时的商品单价（快照）
    product_price = Column(DECIMAL(10, 2), nullable=False, comment="商品单价快照")

    # ---------- 数量与金额 ----------
    quantity = Column(Integer, nullable=False, comment="购买数量")
    # 小计金额 = product_price × quantity
    subtotal = Column(DECIMAL(10, 2), nullable=False, comment="小计金额")

    # ---------- 反向关联 ----------
    # 让 OrderItem 可以通过 item.order 访问所属的订单
    order = relationship("Order", back_populates="order_items")

    def to_dict(self):
        return{
            "id":self.id,
            "order_id":self.order_id,
            "product_id":self.product_id,
            "product_name":self.product_name,
            "product_price":float(self.product_price),
            "quantity":self.quantity,
            "subtotal":float(self.subtotal),
        }
