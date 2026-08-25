# ============================================================
# category.py —— 商品分类模块路由
# 功能：定义商品分类相关的 HTTP 接口
# 接口列表：
#   - GET    /api/category/        获取分类列表
#   - POST   /api/category/        新增分类
#   - PUT    /api/category/{id}     修改分类
#   - DELETE /api/category/{id}    删除分类
# ============================================================

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.common.response import ApiResponse
from app.database import get_db
from app.schemas.category import CategoryResponse, CategoryCreate, CategoryUpdate
from app.services.category_service import CategoryService

# 创建分类模块路由
router = APIRouter(prefix="/category", tags=["物品分类"])


# ---------- 获取分类列表 ----------
@router.get("/", summary="获取物品分类列表")
def get_categories(db: Session = Depends(get_db)):
    """
    获取所有商品分类，按排序权重升序排列
    """
    categories = CategoryService.get_categories_list(db)
    # 列表推导式：将每个 ORM 对象转换为响应模型
    return ApiResponse.success(data=[CategoryResponse.model_validate(c) for c in categories])


# ---------- 新增分类 ----------
@router.post("", summary="新增分类")
def create_category(category_in: CategoryCreate, db: Session = Depends(get_db)):
    """
    新增商品分类
    """
    category = CategoryService.create_category(db, category_in)
    return ApiResponse.success(data=CategoryResponse.model_validate(category), msg="创建成功")


# ---------- 修改分类 ----------
@router.put("/{category_id}", summary="修改分类")
def update_category(category_id: int, category_in: CategoryUpdate, 
                    db: Session = Depends(get_db)):
    """
    修改指定分类的信息（支持部分更新）
    """
    category = CategoryService.update_category(db, category_id, category_in)
    return ApiResponse.success(data=CategoryResponse.model_validate(category), msg="更新成功")


# ---------- 删除分类 ----------
@router.delete("/{category_id}", summary="删除分类")
def delete_category(category_id: int, db: Session = Depends(get_db)):
    """
    删除指定分类（物理删除）
    """
    CategoryService.delete_category(db, category_id)
    return ApiResponse.success(msg="删除成功")