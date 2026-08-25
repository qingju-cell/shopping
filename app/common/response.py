# ============================================================
# response.py —— 统一响应封装
# 功能：定义统一的 API 响应格式，保证前端接收到的 JSON 结构一致
# 响应格式：{"code": 200, "msg": "success", "data": ...}
# 设计模式：泛型（Generic[T]），data 字段可以是任意类型
# ============================================================

from typing import TypeVar, Generic, Optional
from pydantic import BaseModel

# TypeVar 用于泛型定义，T 代表 "任意类型"
# 使用时：ApiResponse[UserResponse] 表示 data 字段是 UserResponse 类型
T = TypeVar('T')


# ApiResponse 是所有接口的统一响应体
# 继承 BaseModel 获得 Pydantic 的数据校验能力
# 继承 Generic[T] 获得泛型能力，data 字段类型由使用时指定
class ApiResponse(BaseModel, Generic[T]):
    # ---------- 三个标准字段 ----------
    code: int = 200             # 状态码：200 成功，400 客户端错误，500 服务器错误
    msg: str = 'success'        # 提示信息：告诉前端请求的结果
    data: Optional[T] = None    # 响应数据：可以是对象、列表或 null

    # ---------- 成功响应（快捷方法）----------
    # 用法：return ApiResponse.success(data=user, msg="注册成功")
    @classmethod
    def success(cls, data: T = None, msg: str = '操作成功'):
        """
        成功响应
        - data: 要返回给前端的数据
        - msg: 提示信息，默认 "操作成功"
        """
        return cls(code=200, msg=msg, data=data)

    # ---------- 失败响应（快捷方法）----------
    # 用法：return ApiResponse.error(code=400, msg="用户名已存在")
    @classmethod
    def error(cls, code: int = 400, msg: str = '操作失败'):
        """
        失败响应
        - code: 错误码，默认 400
        - msg: 错误信息，默认 "操作失败"
        """
        return cls(code=code, msg=msg, data=None)