# ============================================================
# order.py —— 订单模块的数据校验与序列化
# 功能：
#   1. 定义创建订单的请求参数校验规则
#   2. 定义返回给前端的订单数据结构
#   3. 处理 Decimal 类型到 float 的转换（JSON 不支持 Decimal）
#   4. 添加兼容字段（price、items）方便前端使用
# ============================================================

from pydantic import BaseModel, Field, field_serializer, computed_field
from typing import Optional, List
from datetime import datetime
from decimal import Decimal


# ---------- 订单项（商品明细）创建请求 ----------
# 创建订单时，每个商品的信息
class OrderItemCreate(BaseModel):
    product_id: int = Field(description="商品ID")
    # gt=0 表示数量必须大于 0
    quantity: int = Field(description="购买数量", gt=0)


# ---------- 创建订单请求 ----------
# 下单时前端需要发送的完整数据
class OrderCreate(BaseModel):
    # 订单可以包含多个商品，用 List 包裹
    items: List[OrderItemCreate] = Field(description="订单商品列表")
    receiver_name: str = Field(description="收货人姓名")
    receiver_phone: str = Field(description="收货人电话")
    receiver_address: str = Field(description="收货地址")
    remark: Optional[str] = Field(None, description="订单备注")


# ---------- 订单项（明细）响应 ----------
# 返回给前端的每个订单明细的信息
class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    product_price: Decimal       # 单价（Decimal 类型）
    quantity: int
    subtotal: Decimal           # 小计（Decimal 类型）

    class Config:
        from_attributes = True

    # ---------- 序列化器：Decimal → float ----------
    # JSON 标准不支持 Decimal 类型，需要转换成 float 才能正常返回
    # field_serializer 会在序列化为 JSON 时自动调用
    @field_serializer('product_price', 'subtotal')
    def decimal_to_float(self, v):
        return float(v)

    # ---------- 计算字段：兼容前端字段名 ----------
    # 前端使用 item.price 而不是 item.product_price
    # 通过 @computed_field 自动生成 price 字段
    @computed_field
    @property
    def price(self) -> float:
        return float(self.product_price)


# ---------- 订单信息响应 ----------
class OrderResponse(BaseModel):
    id: int
    order_no: str               # 订单编号
    total_amount: Decimal       # 订单总金额（Decimal 类型）
    status: int                 # 订单状态码
    receiver_name: str
    receiver_phone: str
    receiver_address: str
    remark: Optional[str]
    created_at: datetime
    # 包含订单明细列表（默认空列表）
    order_items: List[OrderItemResponse] = []

    class Config:
        from_attributes = True

    # ---------- 序列化器：Decimal → float ----------
    @field_serializer('total_amount')
    def decimal_to_float(self, v):
        return float(v)

    # ---------- 计算字段：兼容前端字段名 ----------
    # 前端使用 order.items 而不是 order.order_items
    @computed_field
    @property
    def items(self) -> List[OrderItemResponse]:
        return self.order_items