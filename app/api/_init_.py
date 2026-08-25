# ============================================================
# _init_.py —— API 路由注册中心
# 功能：将所有模块的路由组装到一个总路由（api_router）
#       然后在 main.py 中统一挂载
# 路由前缀：/api
# 最终接口地址：/api/user/login, /api/products, /api/orders 等
# ============================================================

from fastapi import APIRouter
from app.api.user import router as user_router
from app.api.category import router as category_router
from app.api.product import router as product_router
from app.api.cart import router as cart_router
from app.api.order import router as order_router
from app.api.ai import router as ai_router

# 创建总路由，前缀为 /api
# 所有注册到这个路由的接口地址都会加上 /api 前缀
api_router = APIRouter(prefix="/api")

# 将各模块路由注册到总路由
# 例如 user_router 的前缀是 /user，所以用户接口地址为 /api/user/xxx
api_router.include_router(user_router)
api_router.include_router(category_router)
api_router.include_router(product_router)
api_router.include_router(cart_router)
api_router.include_router(order_router)
api_router.include_router(ai_router)