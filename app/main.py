# ============================================================
# main.py —— FastAPI 应用入口
# 功能：
#   1. 启动时自动建表（开发环境）
#   2. 创建 FastAPI 应用实例
#   3. 配置跨域中间件（CORS）
#   4. 注册全局异常处理器
#   5. 挂载所有业务路由
#   6. 提供健康检测接口
# 启动方式：python -m app.main
# ============================================================

from fastapi import FastAPI, HTTPException
from prometheus_client import make_asgi_app
from requests import RequestException
from starlette.middleware.cors import CORSMiddleware

from app.api._init_ import api_router
from app.common.exception_handler import global_exception_handler
from app.config import settings
from app.database import Base, engine
from app.db_migrations import ensure_order_agent_draft_id_column
# Register before create_all so the new table is created at startup.
from app.models.ai_chat_session import AIChatSession  # noqa: F401
from app.metrics import record_http_request, request_start_time

# ---------- 1. 自动建表 ----------
# 开发环境下，首次启动时会自动在数据库中创建所有表
# 生产环境建议使用 Alembic 等迁移工具管理表结构
Base.metadata.create_all(bind=engine)
# create_all 只会新建表，不会给已有 orders 表补列；开发环境启动时安全补上本次新增列。
ensure_order_agent_draft_id_column()

# ---------- 2. 创建 FastAPI 应用实例 ----------
# title/description/version 会显示在 Swagger 文档（/docs）页面
app = FastAPI(
    title="购物系统API",
    description="购物系统API",
    version="1.0.0"
)

# ---------- 3. 配置跨域中间件（CORS）----------
# 跨域：浏览器中，前端（localhost:5173）调用后端（localhost:8000）
#       由于端口不同，属于跨域请求，默认会被浏览器拦截
# 这里设置 allow_origins=["*"] 允许任何来源的请求
# 生产环境应该限制具体的域名
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # 允许所有来源
    allow_credentials=True,     # 允许携带 Cookie 等凭证
    allow_methods=["*"],        # 允许所有 HTTP 方法（GET/POST/PUT/DELETE 等）
    allow_headers=["*"]         # 允许所有请求头
)

# ---------- HTTP 指标中间件 ----------
# 每个请求结束后记录次数、响应状态和耗时；/metrics 本身不计入业务指标。
@app.middleware("http")
async def collect_http_metrics(request, call_next):
    started_at = request_start_time()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        if not request.url.path.startswith("/metrics"):
            record_http_request(request, status_code, started_at)
# ---------- 4. 注册全局异常处理器 ----------
# 当路由抛出异常时，会被这里统一捕获并返回规范的错误响应
# 注册了三类异常：
#   - HTTPException：FastAPI 主动抛出的业务异常
#   - RequestException：第三方请求库的异常
#   - Exception：所有未捕获的其他异常
app.add_exception_handler(HTTPException, global_exception_handler)
app.add_exception_handler(RequestException, global_exception_handler)
app.add_exception_handler(Exception, global_exception_handler)

# ---------- 5. 挂载业务路由 ----------
# api_router 是在 api/_init_.py 中组装好的总路由
# 前缀为 /api，所以所有接口地址都是 /api/xxx
app.include_router(api_router)

# ---------- Prometheus 指标端点 ----------
# Prometheus 容器会定期访问 /metrics，读取上述中间件记录的指标。
app.mount("/metrics", make_asgi_app())
# ---------- 6. 健康检测接口 ----------
# 用于运维监控，检查服务是否正常运行
# 访问 http://localhost:8000/health 返回 {"status":"ok","msg":"服务正常"}
@app.get("/health", summary="健康检测")
def health():
    return {"status": "ok", "msg": "服务正常"}


# ---------- 7. 直接运行时启动服务 ----------
# 如果执行 python -m app.main，则会启动 Uvicorn 服务器
# reload=True 表示代码修改后自动重启（开发模式）
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app",
                host=settings.HOST,     # 监听地址，从配置读取
                port=settings.PORT,     # 端口号，从配置读取
                reload=True,            # 自动重启
                )
