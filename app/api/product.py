# ============================================================
# product.py —— 商品模块路由
# 功能：定义商品相关的 HTTP 接口
# 接口列表：
#   - GET    /api/products          分页查询商品列表
#   - GET    /api/products/{id}     获取商品详情
#   - POST   /api/products          新增商品
#   - PUT    /api/products/{id}     更新商品
#   - DELETE /api/products/{id}     删除商品（下架）
# ============================================================

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.product import ProductCreate, ProductUpdate, ProductResponse, ProductPageResponse
from app.services.product_service import ProductService
from app.common.response import ApiResponse

# 创建商品模块路由
router = APIRouter(prefix="/products", tags=["商品模块"])


# ---------- 分页查询商品列表 ----------
@router.get("", summary="分页查询商品列表")
def get_products(
    page: int = Query(1, description="页码"),
    page_size: int = Query(10, description="每页数量"),
    category_id: int = Query(None, description="分类ID"),
    keyword: str = Query(None, description="搜索关键词"),
    db: Session = Depends(get_db)
):
    """
    获取商品分页列表
    支持按分类筛选、按关键词搜索
    
    - page: 页码，默认 1
    - page_size: 每页数量，默认 10
    - category_id: 分类 ID（可选）
    - keyword: 搜索关键词（可选）
    """
    result = ProductService.get_product_page(db, page, page_size, category_id, keyword)
    # ProductPageResponse 会将 result 字典包装成分页响应结构
    return ApiResponse.success(data=ProductPageResponse(**result))


# ---------- 获取商品详情 ----------
@router.get("/{product_id}", summary="获取商品详情")
def get_product_detail(product_id: int, db: Session = Depends(get_db)):
    """
    根据商品 ID 获取商品详细信息
    """
    product = ProductService.get_product_detail(db, product_id)
    return ApiResponse.success(data=ProductResponse.model_validate(product))


# ---------- 新增商品 ----------
@router.post("", summary="新增商品")
def create_product(product_in: ProductCreate, db: Session = Depends(get_db)):
    """
    新增商品
    """
    product = ProductService.create_product(db, product_in)
    return ApiResponse.success(data=ProductResponse.model_validate(product), msg="创建成功")


# ---------- 更新商品 ----------
@router.put("/{product_id}", summary="更新商品")
def update_product(product_id: int, product_in: ProductUpdate, 
                   db: Session = Depends(get_db)):
    """
    更新商品信息（支持部分更新）
    """
    product = ProductService.update_product(db, product_id, product_in)
    return ApiResponse.success(data=ProductResponse.model_validate(product), msg="更新成功")


# ---------- 删除商品（下架）----------
@router.delete("/{product_id}", summary="删除商品")
def delete_product(product_id: int, db: Session = Depends(get_db)):
    """
    删除商品（软删除：将状态改为 0 下架）
    """
    ProductService.delete_product(db, product_id)
    return ApiResponse.success(msg="删除成功")