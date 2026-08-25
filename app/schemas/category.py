# ============================================================
# category.py —— 商品分类模块的数据校验与序列化
# 功能：
#   1. 定义新增/修改分类的请求参数校验规则
#   2. 定义返回给前端的分类数据结构
# ============================================================

from typing import Optional
from pydantic import BaseModel, Field
from datetime import datetime


# ---------- 新增分类请求 ----------
class CategoryCreate(BaseModel):
    name: str = Field(description="分类名称", max_length=50)
    parent_id: int = Field(0, description="父分类ID")
    sort: int = Field(0, description="排序权重")


# ---------- 修改分类请求 ----------
# 所有字段都是 Optional，因为修改时可能只改其中一个字段
class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, description="分类名称", max_length=50)
    parent_id: Optional[int] = Field(None, description="父分类ID")
    sort: Optional[int] = Field(None, description="排序权重")


# ---------- 分类信息响应 ----------
class CategoryResponse(BaseModel):
    id: int
    name: str
    parent_id: int
    sort: int
    created_at: datetime

    model_config = {"from_attributes": True}