# ============================================================
# exception_handler.py —— 全局异常处理器
# 功能：
#   1. 捕获 FastAPI 路由抛出的所有异常
#   2. 将异常转换为统一的 JSON 响应格式
#   3. 记录服务器内部错误的日志
# 调用方式：在 main.py 中通过 app.add_exception_handler() 注册
# ============================================================

import logging
import traceback

from fastapi import Request, status, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.common.response import ApiResponse

# 获取当前模块的日志记录器，用于打印错误日志
logger = logging.getLogger(__name__)


# 全局异常处理器函数
# 当路由抛出异常时，FastAPI 会自动调用这个函数
# request: 触发异常的 HTTP 请求对象
# exc: 抛出的异常对象
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:

    # ---------- 1. 处理业务异常（HTTPException）----------
    # 业务代码中抛出的 HTTPException，例如：
    #   raise HTTPException(status_code=400, detail="用户名已存在")
    # 直接返回异常中指定的状态码和错误信息
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content=ApiResponse.error(
                code=exc.status_code,
                msg=str(exc.detail)
            ).model_dump()
        )

    # ---------- 2. 处理参数校验异常（RequestValidationError）----------
    # 当前端传的参数不符合要求时（比如用户名太短、类型不对），
    # Pydantic 会自动抛出 RequestValidationError
    # 从错误详情中提取第一个错误信息，返回给前端
    if isinstance(exc, RequestValidationError):
        error_msg = exc.errors()[0].get('msg', '参数校验失败')
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ApiResponse.error(
                code=400,
                msg=f"参数校验失败:{error_msg}"
            ).model_dump()
        )

    # ---------- 3. 处理其他未知异常 ----------
    # 代码 bug、数据库连接失败、网络错误等
    # 把完整的错误堆栈打印到日志中，方便排查问题
    logger.error("未处理异常: %s\n%s", exc, traceback.format_exc())
    # 向前端返回通用的 500 错误，避免泄露服务器内部信息
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ApiResponse.error(
            code=500,
            msg=f"服务器内部错误: {exc}"
        ).model_dump()
    )