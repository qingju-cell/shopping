# ============================================================
# product.py —— 商品模块的数据校验与序列化
# 功能：
#   1. 定义新增/修改商品的请求参数校验规则
#   2. 定义返回给前端的商品数据结构
#   3. 定义分页查询的响应结构
# ============================================================

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from decimal import Decimal


# ---------- 新增商品请求 ----------
class ProductCreate(BaseModel):
    name: str = Field(description="商品名称", max_length=200)
    description: Optional[str] = Field(None, description="商品描述")
    # gt=0 表示价格必须大于 0
    price: Decimal = Field(description="商品价格", gt=0)
    # ge=0 表示库存必须大于等于 0
    stock: int = Field(0, description="库存数量", ge=0)
    category_id: Optional[int] = Field(None, description="分类ID")
    image_url: Optional[str] = Field(None, description="商品图片链接")
    status: Optional[int] = Field(1, description="商品状态：1上架 0下架")


# ---------- 修改商品请求 ----------
# 所有字段都是 Optional，支持部分更新
class ProductUpdate(BaseModel):
    name: Optional[str] = Field(None, description="商品名称")
    description: Optional[str] = Field(None, description="商品描述")
    price: Optional[Decimal] = Field(None, description="商品价格", gt=0)
    stock: Optional[int] = Field(None, description="库存数量", ge=0)
    category_id: Optional[int] = Field(None, description="分类ID")
    image_url: Optional[str] = Field(None, description="商品图片链接")
    status: Optional[int] = Field(None, description="商品状态")


# ---------- 商品信息响应 ----------
class ProductResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    price: Decimal
    stock: int
    category_id: Optional[int]
    image_url: Optional[str]
    status: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- 分页查询结果 ----------
# 分页接口返回的结构：总数、当前页、每页数量、商品列表
class ProductPageResponse(BaseModel):
    total: int              # 商品总数
    page: int               # 当前页码
    page_size: int          # 每页数量
    list: list[ProductResponse]  # 当前页的商品列表