# ============================================================
# product_service.py —— 商品业务逻辑层
# 功能：
#   1. 分页查询商品列表（支持分类筛选和关键词搜索）
#   2. 新增商品
#   3. 获取商品详情
#   4. 更新商品信息
#   5. 删除商品（软删除，将状态改为 0 下架）
# ============================================================

import json
import time
import random
from fastapi import HTTPException
from sqlalchemy.orm import Session
import redis

from app.models.product import Product
from app.schemas.product import ProductCreate, ProductUpdate
from app.redis_client import redis_client, redis_available
from app.config import settings

class ProductService:

    # ---------- 分页查询商品列表 ----------
    @staticmethod
    def get_product_page(db: Session, page: int = 1, page_size: int = 10,
                         category_id: int = None, keyword: str = None):
        """
        分页获取商品列表
        支持按分类筛选、按关键词搜索

        参数说明：
        - page: 当前页码，从 1 开始
        - page_size: 每页显示数量
        - category_id: 分类 ID，传了就只查该分类下的商品
        - keyword: 搜索关键词，传了就按商品名称模糊搜索

        返回值：字典，包含商品列表、总数、当前页、每页数量

        缓存穿透防护：
        1. 参数校验：page、page_size 必须大于 0，category_id 不合法直接拦截
        2. 缓存空对象：空列表也写缓存，防止恶意用不存在的条件反复打DB
        缓存击穿防护：
        3. 互斥锁自旋：热点查询缓存过期时，只有一个请求查DB
        """
        # ========== 第一道防线：参数校验 ==========
        if page is None or page < 1:
            raise HTTPException(status_code=400, detail="页码必须大于等于1")
        if page_size is None or page_size < 1:
            raise HTTPException(status_code=400, detail="每页数量必须大于等于1")
        if page_size > 100:
            raise HTTPException(status_code=400, detail="每页数量不能超过100")
        if category_id is not None and category_id <= 0:
            raise HTTPException(status_code=400, detail="分类ID不合法")
        if keyword is not None and len(keyword) > 100:
            raise HTTPException(status_code=400, detail="搜索关键词过长")

        # 1.1 生成缓存 key —— 用所有查询参数拼一个唯一的 key
        cache_key = f"products:page:{page}:size:{page_size}:cat:{category_id}:kw:{keyword}"
        lock_key = f"lock:{cache_key}"
        lock_expire = 5  # 分页查询比单条详情慢一点，锁5秒

        # ========== 先查 Redis 缓存 + 互斥锁，Redis 挂了就跳过 ==========
        if redis_available():
            try:
                cache = redis_client.get(cache_key)
                if cache is not None:
                    # ========== 命中空对象缓存（total=0的空列表标记）==========
                    cached_data = json.loads(cache)
                    return cached_data

                # 【缓存没命中 → 加互斥锁，防止击穿】
                for _ in range(5):
                    locked = redis_client.set(lock_key, 1, nx=True, ex=lock_expire)
                    if locked:
                        try:
                            # 拿到锁 → 查DB + 写缓存
                            query = db.query(Product).filter(Product.status == 1)
                            if category_id:
                                query = query.filter(Product.category_id == category_id)
                            if keyword:
                                query = query.filter(Product.name.like(f"%{keyword}%"))
                            total = query.count()
                            products = query.order_by(Product.id.desc()).offset(
                                (page - 1) * page_size
                            ).limit(page_size).all()

                            list_as_dict = [p.to_dict() for p in products]
                            result = {
                                "list": list_as_dict,
                                "total": total,
                                "page": page,
                                "page_size": page_size
                            }
                            # 写缓存：空列表也写，防穿透
                            expire = (
                                settings.REDIS_NULL_CACHE_EXPIRE
                                if total == 0
                                else settings.REDIS_CACHE_EXPIRE + random.randint(-300, 300)
                            )
                            redis_client.setex(cache_key, expire, json.dumps(result))
                            return result
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
        query = db.query(Product).filter(Product.status == 1)
        if category_id:
            query = query.filter(Product.category_id == category_id)
        if keyword:
            query = query.filter(Product.name.like(f"%{keyword}%"))
        total = query.count()
        products = query.order_by(Product.id.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size).all()

        list_as_dict = [p.to_dict() for p in products]
        result = {
            "list": list_as_dict,
            "total": total,
            "page": page,
            "page_size": page_size
        }

        # 兜底查询也顺便写缓存（Redis 挂了就跳过）
        if redis_available():
            try:
                expire = (
                    settings.REDIS_NULL_CACHE_EXPIRE
                    if total == 0
                    else settings.REDIS_CACHE_EXPIRE + random.randint(-300, 300)
                )
                redis_client.setex(cache_key, expire, json.dumps(result))
            except redis.ConnectionError:
                pass

        return result

    # ---------- 新增商品 ----------
    @staticmethod
    def create_product(db: Session, product_in: ProductCreate) -> Product:
        """
        新增商品
        将前端传来的数据直接映射为 ORM 对象并保存
        """
        db_product = Product(
            name=product_in.name,
            description=product_in.description,
            price=product_in.price,
            stock=product_in.stock,
            category_id=product_in.category_id,
            image_url=product_in.image_url,
            status=product_in.status,
        )
        db.add(db_product)
        db.commit()
        db.refresh(db_product)



        return db_product



    # ---------- 获取商品详情 ----------
    @staticmethod
    def get_product_detail(db: Session, product_id: int) -> Product:
        """
        根据商品 ID 获取商品详情
        如果商品不存在，抛出 404 错误

        缓存穿透防护：
        1. 参数校验：ID 必须大于 0，不合法直接拦截
        2. 缓存空对象：查不到时写入 "__NULL__"，60 秒内同样的请求不会再打到 DB
        """
        # ========== 第一道防线：参数校验 ==========
        if product_id is None or product_id <= 0:
            raise HTTPException(status_code=400, detail="商品ID不合法")

        # 1. 从 Redis 查有没有这个 key
        id_key = f"products:detail:{product_id}"
        lock_key=f"lock:{id_key}"
        lock_expire=3   # 锁过期时间，3秒内只能有一个请求访问数据库



        # ========== 尝试读缓存，Redis 挂了就跳过 ==========
        if redis_available():
            try:
                cache = redis_client.get(id_key)
                if cache is not None:
                    # ========== 命中空对象缓存，直接抛 404，不查 DB ==========
                    if cache == "__NULL__":
                        raise HTTPException(status_code=404, detail="商品不存在")
                    return json.loads(cache)

                # 【缓存没命中 → 加互斥锁，防止击穿】
                # 自旋重试：最多5次，每次等50ms
                for _ in range(5):
                    # 尝试拿锁（SETNX + 过期时间，保证原子性）
                    locked = redis_client.set(lock_key, 1, nx=True, ex=lock_expire)
                    if locked:
                        # 拿到锁 → 查DB + 写缓存
                        try:
                            product = db.query(Product).filter(Product.id == product_id).first()
                            if product is None:
                                redis_client.setex(
                                    id_key,
                                    settings.REDIS_NULL_CACHE_EXPIRE,
                                    "__NULL__"
                                )
                                raise HTTPException(status_code=404, detail="商品不存在")

                            redis_client.setex(
                                id_key,
                                settings.REDIS_CACHE_EXPIRE,
                                json.dumps(product.to_dict())
                            )
                            return product.to_dict()
                        finally:
                            # 释放锁
                            redis_client.delete(lock_key)
                    else:
                        # 没有拿到锁，等50ms后重试查缓存
                        time.sleep(0.05)
                        cache = redis_client.get(id_key)
                        if cache is not None:
                            # ========== 命中空对象缓存，直接抛 404，不查 DB ==========
                            if cache == "__NULL__":
                                raise HTTPException(status_code=404, detail="商品不存在")
                            return json.loads(cache)
            except redis.ConnectionError:
                pass  # Redis 挂了，降级走下面的兜底 DB 查询

        # ========== 兜底：5次重试都没等到 / Redis 直接挂了，直接查DB ==========
        product = db.query(Product).filter(Product.id == product_id).first()
        if product is None:
            # 兜底查询也顺便写空对象缓存，防后续穿透（Redis 挂了就跳过）
            if redis_available():
                try:
                    redis_client.setex(
                        id_key,
                        settings.REDIS_NULL_CACHE_EXPIRE,
                        "__NULL__"
                    )
                except redis.ConnectionError:
                    pass
            raise HTTPException(status_code=404, detail="商品不存在")

        # 兜底查询也顺便写正常缓存（Redis 挂了就跳过）
        if redis_available():
            try:
                redis_client.setex(
                    id_key,
                    settings.REDIS_CACHE_EXPIRE,
                    json.dumps(product.to_dict())
                )
            except redis.ConnectionError:
                pass

        return product.to_dict()


    # ---------- 更新商品信息 ----------
    @staticmethod
    def update_product(db: Session, id: int, product_in: ProductUpdate) -> Product:
        """
        更新商品信息（部分更新）
        流程与 CategoryService.update_category 相同：
        1. 查找商品是否存在（直接查 ORM，不走缓存：写操作必须拿最新的数据库对象）
        2. 只更新前端传入的字段
        """
        # 直接查 ORM 对象，不能用 get_product_detail（它返回的是 dict）
        product = db.query(Product).filter(Product.id == id).first()
        if not product:
            raise HTTPException(status_code=404, detail="商品不存在")

        updated_data = product_in.model_dump(exclude_unset=True)

        for key, value in updated_data.items():
            setattr(product, key, value)

        db.commit()
        db.refresh(product)

        # ========== 更新：清除商品列表缓存 + 详情缓存 ==========
        _clear_product_cache()
        if redis_available():
            try:
                redis_client.delete(f"products:detail:{id}")
            except redis.ConnectionError:
                pass

        return product

    # ---------- 删除商品（软删除）----------
    @staticmethod
    def delete_product(db: Session, id: int):
        """
        删除商品：采用"软删除"策略
        不是真的从数据库删除记录，而是将 status 改为 0（下架）
        好处：数据不会丢失，以后可以恢复
        """
        # 直接查 ORM 对象，不能用 get_product_detail（它返回的是 dict）
        product = db.query(Product).filter(Product.id == id).first()
        if not product:
            raise HTTPException(status_code=404, detail="商品不存在")
        product.status = 0

        db.commit()
        # ========== 新增：清除商品列表缓存 + 详情缓存 ==========
        _clear_product_cache()
        if redis_available():
            try:
                redis_client.delete(f"products:detail:{id}")
            except redis.ConnectionError:
                pass


# 清除缓存
def _clear_product_cache():
    """
    清除所有商品列表相关的缓存
    用 scan_iter 批量扫描删除，不阻塞 Redis
    Redis 挂了就跳过，不影响业务
    """
    if not redis_available():
        return
    try:
        for key in redis_client.scan_iter("products:page:*"):
            redis_client.delete(key)
    except redis.ConnectionError:
        pass