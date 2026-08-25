# ============================================================
# category_service.py —— 商品分类业务逻辑层
# 功能：
#   1. 获取所有分类列表
#   2. 新增分类
#   3. 根据 ID 查询分类
#   4. 修改分类
#   5. 删除分类
# ============================================================
import json

import redis
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.config import settings
from app.redis_client import redis_client, redis_available
from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryUpdate


class CategoryService:

    # ---------- 获取所有分类 ----------
    @staticmethod
    def get_categories_list(db: Session) -> list[Category]:
        """
        获取所有分类，按 sort 字段升序排列
        数字越小的分类越靠前
        """
        cache_key = f"categories:list"

        # ========== 尝试读缓存，Redis 挂了就跳过 ==========
        if redis_available():
            try:
                cache = redis_client.get(cache_key)
                if cache:
                    return json.loads(cache)
            except redis.ConnectionError:
                pass

        # ========== 查数据库（永远能执行）==========
        result = db.query(Category).order_by(Category.sort.asc()).all()

        # ========== 尝试写缓存，Redis 挂了就跳过 ==========
        if redis_available():
            try:
                redis_client.setex(
                    cache_key,
                    settings.REDIS_CACHE_EXPIRE,
                    json.dumps([category.to_dict() for category in result])
                )
            except redis.ConnectionError:
                pass

        return [category.to_dict() for category in result]

    # ---------- 新增分类 ----------
    @staticmethod
    def create_category(db: Session, category_in: CategoryCreate) -> Category:
        """
        新增分类
        直接将前端传来的数据映射为 ORM 对象并保存
        """
        db_category = Category(
            name=category_in.name,
            parent_id=category_in.parent_id,
            sort=category_in.sort,
        )
        db.add(db_category)
        db.commit()
        db.refresh(db_category)

        # ========== 新增：清除分类列表缓存 ==========
        _delete_category_cache()
        return db_category

    # ---------- 根据 ID 查询分类 ----------
    @staticmethod
    def get_category_by_id(db: Session, category_id: int) -> Category | None:
        """
        根据分类 ID 获取分类信息
        返回 None 表示不存在
        """
        return db.query(Category).filter(Category.id == category_id).first()

    # ---------- 修改分类 ----------
    @staticmethod
    def update_category(db: Session, category_id: int, category_in: CategoryUpdate) -> Category:
        """
        修改分类信息
        流程：
        1. 根据 ID 查找分类是否存在
        2. 将传入的字段（只包含有值的字段）更新到 ORM 对象
        3. 提交到数据库
        
        model_dump(exclude_unset=True) 的作用：
        - 只返回前端实际传入的字段
        - 如果前端只传了 name，就只更新 name，不动其他字段
        """
        db_category = CategoryService.get_category_by_id(db, category_id)
        if not db_category:
            raise HTTPException(status_code=404, detail="分类不存在")
        
        # 获取需要更新的字段（排除未设置的字段）
        update_data = category_in.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(db_category, key, value)  # 动态设置属性值
        
        db.commit()
        db.refresh(db_category)

        # ========== 新增：清除分类列表缓存 ==========
        _delete_category_cache()
        return db_category

    # ---------- 删除分类 ----------
    @staticmethod
    def delete_category(db: Session, category_id: int) -> None:
        """
        删除分类（物理删除，从数据库中彻底移除）
        """
        db_category = CategoryService.get_category_by_id(db, category_id)
        if not db_category:
            raise HTTPException(status_code=404, detail="分类不存在")
        db.delete(db_category)
        db.commit()

        # ========== 新增：清除分类列表缓存 ==========
        _delete_category_cache()



        # 4. 从 Redis 中删除缓存
def _delete_category_cache():
    """
    删除所有分类缓存
    Redis 挂了就跳过，不影响业务
    """
    if redis_available():
        try:
            redis_client.delete("categories:list")
        except redis.ConnectionError:
            pass