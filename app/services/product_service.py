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
        """

        # ==============================================
        # 【第一步】先查 Redis 缓存
        # ==============================================

        # 1.1 生成缓存 key —— 用所有查询参数拼一个唯一的 key
        # 不同参数对应不同缓存，不会互相覆盖
        cache_key = f"products:page:{page}:size:{page_size}:cat:{category_id}:kw:{keyword}"

        # ========== 尝试读缓存，Redis 挂了就跳过 ==========
        if redis_available():
            try:
                cache = redis_client.get(cache_key)
                if cache:
                    return json.loads(cache)
            except redis.ConnectionError:
                pass

        # ==============================================
        # 【第二步】缓存没命中，走原来的数据库查询
        # ==============================================

        # 基础查询：只查询上架商品（status == 1）
        query = db.query(Product).filter(Product.status == 1)
        
        # 如果传了分类 ID，添加分类筛选条件
        if category_id:
            query = query.filter(Product.category_id == category_id)
        
        # 如果传了关键词，添加模糊搜索条件
        # like '%关键词%' 表示包含关键词的任何位置都匹配
        if keyword:
            query = query.filter(Product.name.like(f"%{keyword}%"))
        
        # 获取符合条件的商品总数（用于前端分页计算）
        total = query.count()
        
        # 分页查询：按 ID 倒序（新的在前），跳过前面的页，取当前页的数据
        products = query.order_by(Product.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

        # ==============================================
        # 【第三步】统一用 to_dict() 处理，然后同时用于"返回"和"写缓存"
        # ==============================================

        # 把 ORM 对象数组转成字典数组
        list_as_dict = [p.to_dict() for p in products]

        # 统一的结果对象：返回给前端 和 写入缓存 都用它，保证一致
        result = {
            "list": list_as_dict,
            "total": total,
            "page": page,
            "page_size": page_size
        }

        # ========== 尝试写缓存，Redis 挂了就跳过 ==========
        if redis_available():
            try:
                redis_client.setex(
                    cache_key,
                    settings.REDIS_CACHE_EXPIRE,
                    json.dumps(result)
                )
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
        """
        # 1. 从 Redis 查有没有这个 key
        id_key = f"products:detail:{product_id}"

        # ========== 尝试读缓存，Redis 挂了就跳过 ==========
        if redis_available():
            try:
                cache = redis_client.get(id_key)
                if cache:
                    return json.loads(cache)
            except redis.ConnectionError:
                pass


        #2 从数据库查询
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="商品不存在")

        # ========== 尝试写缓存，Redis 挂了就跳过 ==========
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
        1. 查找商品是否存在
        2. 只更新前端传入的字段
        """
        product = ProductService.get_product_detail(db, id)
        updated_data = product_in.model_dump(exclude_unset=True)

        for key, value in updated_data.items():
            setattr(product, key, value)

        db.commit()
        db.refresh(product)

        # ========== 更新：清除商品列表缓存 ==========
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
        product = ProductService.get_product_detail(db, id)
        product.status = 0

        db.commit()
        # ========== 新增：清除商品列表缓存 ==========
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