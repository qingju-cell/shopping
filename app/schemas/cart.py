# ============================================================
# cart.py —— 购物车模块的数据校验与序列化
# 功能：
#   1. 定义添加购物车/修改数量的请求参数校验规则
#   2. 定义返回给前端的购物车数据结构
# ============================================================

from pydantic import BaseModel, Field
from datetime import datetime
from decimal import Decimal


# ---------- 添加购物车请求 ----------
class CartAdd(BaseModel):
    # gt=0 表示商品 ID 必须大于 0
    product_id: int = Field(description="商品ID", gt=0)
    # gt=0 表示数量必须大于 0
    quantity: int = Field(1, description="数量", gt=0)


# ---------- 修改购物车商品数量请求 ----------
class CartUpdateQuantity(BaseModel):
    quantity: int = Field(description="数量", gt=0)


# ---------- 购物车项信息响应 ----------
# 查询购物车列表时，返回这样的结构
# 包含商品的详细信息（名称、价格、图片等）
class CartItemResponse(BaseModel):
    id: int                     # 购物车项ID
    product_id: int             # 商品ID
    product_name: str           # 商品名称
    product_price: Decimal      # 商品单价
    product_image: str | None   # 商品图片（可为空）
    quantity: int               # 购买数量
    subtotal: Decimal           # 小计金额 = 单价 × 数量
    created_at: datetime        # 添加时间

    # 允许从 ORM 对象直接创建
    class Config:
        from_attributes = True