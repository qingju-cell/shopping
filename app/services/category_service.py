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
import time
import random

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

        缓存穿透防护：
        1. 缓存空对象：空列表也写缓存，60秒过期
        缓存击穿防护：
        2. 互斥锁自旋：分类列表是典型热点，缓存过期时只有一个请求查DB
        """
        cache_key = f"categories:list"
        lock_key = f"lock:{cache_key}"
        lock_expire = 3

        # ========== 先查 Redis 缓存 + 互斥锁，Redis 挂了就跳过 ==========
        if redis_available():
            try:
                cache = redis_client.get(cache_key)
                if cache is not None:
                    cached_data = json.loads(cache)
                    return cached_data

                # 【缓存没命中 → 加互斥锁，防止击穿】
                for _ in range(5):
                    locked = redis_client.set(lock_key, 1, nx=True, ex=lock_expire)
                    if locked:
                        try:
                            # 拿到锁 → 查DB + 写缓存
                            result = db.query(Category).order_by(Category.sort.asc()).all()
                            list_as_dict = [category.to_dict() for category in result]
                            # 写缓存：空列表也写，防穿透
                            expire = (
                                settings.REDIS_NULL_CACHE_EXPIRE
                                if len(list_as_dict) == 0
                                else settings.REDIS_CACHE_EXPIRE
                            )
                            redis_client.setex(cache_key, expire, json.dumps(list_as_dict))
                            return list_as_dict
                        finally:
                            redis_client.delete(lock_key)
                    else:
                        # 没拿到锁，等50ms后重试查缓存
                        time.sleep(0.05)
                        cache = redis_client.get(cache_key)
                        if cache is not None:
                            return json.loads(cache)
            except redis.ConnectionError:
                pass  # Redis 挂了，降级走兜底 DB 查询

        # ========== 兜底：Redis 不可用 / 5次重试都没等到，直接查DB ==========
        result = db.query(Category).order_by(Category.sort.asc()).all()
        list_as_dict = [category.to_dict() for category in result]

        # 兜底查询也顺便写缓存（Redis 挂了就跳过）
        if redis_available():
            try:
                expire = (
                    settings.REDIS_NULL_CACHE_EXPIRE
                    if len(list_as_dict) == 0
                    else settings.REDIS_CACHE_EXPIRE
                )
                redis_client.setex(cache_key, expire, json.dumps(list_as_dict))
            except redis.ConnectionError:
                pass

        return list_as_dict

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
        返回 None 表示不存在（保持返回 ORM 对象，供 update/delete 内部使用）

        缓存穿透防护：
        1. 参数校验：ID 必须大于 0，不合法直接拦截
        2. 缓存空对象：查不到时写入 "__NULL__"，60 秒内同样的请求不会再打到 DB
        缓存击穿防护：
        3. 互斥锁自旋：热点分类缓存过期时，只有一个请求查DB
        """
        # ========== 第一道防线：参数校验 ==========
        if category_id is None or category_id <= 0:
            return None

        cache_key = f"categories:detail:{category_id}"
        lock_key = f"lock:{cache_key}"
        lock_expire = 3

        # ========== 先查 Redis 缓存 + 互斥锁，Redis 挂了就跳过 ==========
        if redis_available():
            try:
                cache = redis_client.get(cache_key)
                if cache is not None:
                    # ========== 命中空对象缓存，直接返回 None ==========
                    if cache == "__NULL__":
                        return None
                    cached_dict = json.loads(cache)
                    category = Category()
                    for k, v in cached_dict.items():
                        setattr(category, k, v)
                    return category

                # 【缓存没命中 → 加互斥锁，防止击穿】
                for _ in range(5):
                    locked = redis_client.set(lock_key, 1, nx=True, ex=lock_expire)
                    if locked:
                        try:
                            # 拿到锁 → 查DB + 写缓存
                            category = db.query(Category).filter(
                                Category.id == category_id
                            ).first()
                            if category is None:
                                redis_client.setex(
                                    cache_key,
                                    settings.REDIS_NULL_CACHE_EXPIRE,
                                    "__NULL__",
                                )
                            else:
                                redis_client.setex(
                                    cache_key,
                                    settings.REDIS_CACHE_EXPIRE + random.randint(-300, 300),
                                    json.dumps(category.to_dict()),
                                )
                            return category
                        finally:
                            redis_client.delete(lock_key)
                    else:
                        # 没拿到锁，等50ms后重试查缓存
                        time.sleep(0.05)
                        cache = redis_client.get(cache_key)
                        if cache is not None:
                            if cache == "__NULL__":
                                return None
                            cached_dict = json.loads(cache)
                            category = Category()
                            for k, v in cached_dict.items():
                                setattr(category, k, v)
                            return category
            except redis.ConnectionError:
                pass  # Redis 挂了，降级走兜底 DB 查询

        # ========== 兜底：Redis 不可用 / 5次重试都没等到，直接查DB ==========
        category = db.query(Category).filter(Category.id == category_id).first()

        # 兜底查询也顺便写缓存（Redis 挂了就跳过）
        if redis_available():
            try:
                if category is None:
                    redis_client.setex(
                        cache_key,
                        settings.REDIS_NULL_CACHE_EXPIRE,
                        "__NULL__",
                    )
                else:
                    redis_client.setex(
                        cache_key,
                        settings.REDIS_CACHE_EXPIRE + random.randint(-300, 300),
                        json.dumps(category.to_dict()),
                    )
            except redis.ConnectionError:
                pass

        return category

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

        # ========== 新增：清除分类列表缓存 + 分类详情缓存 ==========
        _delete_category_cache()
        _delete_category_detail_cache(category_id)
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

        # ========== 新增：清除分类列表缓存 + 分类详情缓存 ==========
        _delete_category_cache()
        _delete_category_detail_cache(category_id)



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


def _delete_category_detail_cache(category_id: int):
    """
    删除指定分类的详情缓存
    Redis 挂了就跳过，不影响业务
    """
    if redis_available():
        try:
            redis_client.delete(f"categories:detail:{category_id}")
        except redis.ConnectionError:
            pass