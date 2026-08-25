# ============================================================
# user.py —— 用户模块的数据校验与序列化
# 功能：
#   1. 定义用户注册/登录时的请求参数校验规则
#   2. 定义返回给前端的用户数据结构
# 技术栈：Pydantic（数据校验库）
# 说明：Schema 是 "数据契约"，定义了前后端交互的数据格式
# ============================================================

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------- 用户注册请求 ----------
# 当前端调用 /api/user/register 时，需要发送这样的 JSON 数据
# Pydantic 会自动校验数据是否符合要求
class UserRegister(BaseModel):
    # Field 的参数说明：
    #   - description: 字段说明（会出现在 Swagger 文档中）
    #   - min_length/max_length: 字符串长度限制
    username: str = Field(description="用户名", min_length=3, max_length=10)
    password: str = Field(description="密码", min_length=6, max_length=20)
    # Optional[str] 表示可以为空（前端可以不传这个字段）
    email: Optional[str] = Field(None, description="邮箱")
    phone: Optional[str] = Field(None, description="手机号")


# ---------- 用户登录请求 ----------
# 登录时只需要用户名和密码
class UserLogin(BaseModel):
    username: str = Field(description="用户名")
    password: str = Field(description="密码")


# ---------- 用户信息响应 ----------
# 查询用户信息时，返回这样的结构给前端
# class Config + from_attributes = True 表示可以直接从 ORM 模型转换
class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str]
    phone: Optional[str]
    role: str
    created_at: datetime

    # 允许从 ORM 对象直接创建 Pydantic 模型
    # 用法：UserResponse.model_validate(user_orm_object)
    model_config = {"from_attributes": True}