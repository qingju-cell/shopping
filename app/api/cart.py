# ============================================================
# cart.py —— 购物车模块路由
# 功能：定义购物车相关的 HTTP 接口
# 接口列表：
#   - GET    /api/cart              查询购物车列表
#   - POST   /api/cart              添加商品到购物车
#   - PUT    /api/cart/{id}         修改购物车商品数量
#   - DELETE /api/cart/{id}         删除购物车商品
# 注意：目前 user_id 暂用固定值 1，后期接入登录认证后改为从 token 获取
# ============================================================

from fastapi import APIRouter, Depends, Path
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.cart import CartAdd, CartUpdateQuantity
from app.services.cart_service import CartService
from app.common.response import ApiResponse

# 创建购物车模块路由
router = APIRouter(prefix="/cart", tags=["购物车模块"])


# ---------- 查询购物车列表 ----------
@router.get("", summary="查询购物车列表")
def get_cart(user_id: int = 1, db: Session = Depends(get_db)):
    """
    查询指定用户的购物车列表
    目前 user_id 暂用固定值 1，后期接入登录后改为自动获取
    """
    cart_list = CartService.get_cart_list(db, user_id)
    return ApiResponse.success(data=cart_list)


# ---------- 添加商品到购物车 ----------
@router.post("", summary="添加商品到购物车")
def add_to_cart(cart_in: CartAdd, user_id: int = 1, db: Session = Depends(get_db)):
    """
    添加商品到购物车
    - cart_in: 包含 product_id 和 quantity
    - 如果购物车中已有该商品，会累加数量
    """
    item = CartService.add_cart(db, user_id, cart_in)
    return ApiResponse.success(msg="添加成功", data=item)


# ---------- 修改购物车商品数量 ----------
@router.put("/{product_id}", summary="修改购物车商品数量")
def update_cart_quantity(
    product_id: int,
    quantity_in: CartUpdateQuantity,
    user_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    修改购物车中某商品的数量
    - product_id: 商品 ID（路径参数）
    - quantity_in: 包含新的数量
    """
    CartService.update_quantity(db, user_id, product_id, quantity_in)
    return ApiResponse.success(msg="修改成功")


# ---------- 删除购物车商品 ----------
@router.delete("/{product_id}", summary="删除购物车商品")
def remove_cart_item(
    product_id: int = Path(description="商品ID"),
    user_id: int = 1,
    db: Session = Depends(get_db)
):
    """
    删除购物车中的某个商品
    """
    CartService.delete_cart(db, user_id, product_id)
    return ApiResponse.success(msg="删除成功")