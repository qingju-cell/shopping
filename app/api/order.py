# ============================================================
# order.py —— 订单模块路由
# 功能：定义订单相关的 HTTP 接口
# 接口列表：
#   - POST   /api/orders            创建订单（下单）
#   - GET    /api/orders            查询当前用户的订单列表
#   - GET    /api/orders/{id}       查询订单详情
#   - POST   /api/orders/{id}/pay   模拟支付待支付订单
# 注意：目前 user_id 暂用固定值 1，后期接入登录认证后改为从 token 获取
# ============================================================

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.order import OrderCreate, OrderResponse
from app.services.order_service import OrderService
from app.common.response import ApiResponse

# 创建订单模块路由
router = APIRouter(prefix="/orders", tags=["订单模块"])


# ---------- 创建订单（下单）----------
@router.post("", summary="创建订单")
def create_order(order_in: OrderCreate, user_id: int = 1, 
                  db: Session = Depends(get_db)):
    """
    创建新订单
    - order_in: 包含商品列表、收货人信息、备注等
    - 核心逻辑：扣减库存、生成订单号、写入订单主表和明细表
    """
    order = OrderService.create_order(db, user_id, order_in)
    return ApiResponse.success(data=OrderResponse.model_validate(order), msg="下单成功")


# ---------- 模拟支付 ----------
@router.post("/{order_id}/pay", summary="模拟支付订单")
def pay_order(order_id: int, user_id: int = 1,
              db: Session = Depends(get_db)):
    """支付已创建的待支付订单；库存已在创建订单时扣减，不会重复扣减。"""
    order = OrderService.pay_order(db, user_id, order_id)
    return ApiResponse.success(data=OrderResponse.model_validate(order), msg="支付成功")


# ---------- 查询我的订单列表 ----------
@router.get("", summary="查询我的订单列表")
def get_my_orders(user_id: int = 1, db: Session = Depends(get_db)):
    """
    获取当前用户的所有订单
    按订单 ID 倒序排列（最新下单的在前）
    """
    orders = OrderService.get_user_order(db, user_id)
    # 列表推导式：将每个订单 ORM 对象转换为响应模型
    return ApiResponse.success(
        data=[OrderResponse.model_validate(o) for o in orders]
    )


# ---------- 查询订单详情 ----------
@router.get("/{order_id}", summary="查询订单详情")
def get_order_detail(order_id: int, user_id: int = 1, 
                     db: Session = Depends(get_db)):
    """
    查询单个订单的详细信息（包括所有订单明细）
    需要验证订单是否属于当前用户
    """
    order = OrderService.get_order_detail(db, user_id, order_id)
    return ApiResponse.success(data=OrderResponse.model_validate(order))
