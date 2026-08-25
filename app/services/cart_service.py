# ============================================================
# cart_service.py —— 购物车业务逻辑层
# 功能：
#   1. 查询用户购物车列表（关联商品信息）
#   2. 添加商品到购物车（检查库存、已存在则累加数量）
#   3. 更新购物车商品数量
#   4. 删除购物车商品
# 核心逻辑：加购时需要检查商品状态、库存、是否已在购物车中
# ============================================================

from fastapi import HTTPException
from sqlalchemy.orm import Session
import redis

from app.models.cart import CartItem
from app.models.product import Product
from app.schemas.cart import CartAdd, CartUpdateQuantity
from app.redis_client import redis_client, redis_available
from app.config import settings

class CartService:

    # ---------- 查询用户购物车列表 ----------
    @staticmethod
    def get_cart_list(db: Session, user_id: int):

        """
        查询用户购物车列表（Redis Hash 版本）
        1. 确保 Redis 里有数据（没有就从 MySQL 同步，兜底）
        2. HGETALL 一次取出所有 product_id → quantity
        3. 逐个查商品表拿到名称/价格/图片（还是要查 MySQL，但只查商品表，不查 cart 表了）
        """
        # ========== 1. 兜底：确保 Redis 有数据 ==========
        _ensure_cart_in_redis(db, user_id)

        key = _cart_key(user_id)

        # ========== 2. HGETALL 一次取出所有 product_id → quantity ==========
        cart_dict = redis_client.hgetall(key)

        result = []

        for product_id,quantity in cart_dict.items():
            product_id=int(product_id)
            quantity=int(quantity)

            # ========== 3. 查商品详情（关联商品表，和原来一样）==========
            product = db.query(Product).filter(Product.id == product_id).first()
            if not product or product.status != 1:
                # 商品不存在/下架了 → 顺便把购物车中这一项清理掉（Redis + MySQL 都清）
                redis_client.hdel(key,product_id)
                db.query(CartItem).filter(
                    CartItem.user_id == user_id,
                    CartItem.product_id == product_id
                ).delete()
                db.commit()
                continue

            #计算价格
            price=float(product.price)
            subtotal=round(quantity*price,2)

            # 组装返回数据
            # ⚠️ 注意：下面的字段名必须和前端 CartItem / OrderConfirm.vue 里读的完全一致
            # 前端要 item.product.name, item.product.price, item.product.image_url
            # 所以这里必须嵌套一个 product 对象！否则前端读到 undefined，显示 ¥0.00
            result.append({
                "id": product_id,
                "product_id": product_id,
                # --- 下面 3 个是为了兼容老代码（购物车列表页可能在直接读 product_name）---
                "product_name": product.name,
                "product_price": price,
                "product_image": product.image_url,
                # --- ⭐ 关键：加 product 嵌套对象，让 OrderConfirm.vue 的 item.product?.name 能读到 ---
                "product": {
                    "id": product.id,
                    "name": product.name,
                    "price": price,
                    "image_url": product.image_url,
                    "description": product.description or "",
                    "stock": product.stock,
                    "category_id": product.category_id,
                    "status": product.status,
                },
                "quantity": quantity,
                "subtotal": subtotal,
                "created_at": None,
            })
        return result

    # ---------- 添加商品到购物车 ----------
    @staticmethod
    def add_cart(db: Session, user_id: int, cart_in: CartAdd):
        """
        添加商品到购物车
        流程：
        1. 检查商品是否存在、上架、库存是否充足（这一步还是必须查 MySQL 商品表，库存不能缓存）
        2. HINCRBY 一步完成：没有这个商品就加进去，有就自动累加数量（原子操作，不会并发问题）
        3. 双写：同步写入 MySQL 兜底
        4. 重置 Redis key 过期时间（用户活跃就延长）
        """

        _ensure_cart_in_redis(db, user_id)

        key = _cart_key(user_id)
        product_id = cart_in.product_id
        add_quantity = cart_in.quantity

        # ========== 1. 校验商品（和原来一样，必须查 MySQL，不能缓存库存）==========
        product = db.query(Product).filter(Product.id == cart_in.product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="商品不存在")
        if product.status != 1:
            raise HTTPException(status_code=400, detail="该商品已下架,无法加入购物车")
        if product.stock < cart_in.quantity:
            raise HTTPException(status_code=400, detail=f"库存不足,当前仅剩 {product.stock} 件")

        # ========== 2. 检查购物车中是否已存在该商品==========
        existing_qty_str = redis_client.hget(key, str(product_id))

        existing_qty = int(existing_qty_str)+add_quantity

        # ========== 3. 校验加购后是否超出库存==========
        if product.stock < existing_qty:
            raise HTTPException(status_code=400, detail=f"加购后超出库存,当前仅剩 {product.stock} 件")

        # ========== 3. Redis 写操作：HINCRBY 原子加数量 ==========
        # HINCRBY key field increment
        # - 如果 field 不存在，先默认设为 0 再加 increment
        # - 如果存在，就在原有值基础上加
        # - 返回值：加完之后的新数量
        final_qty=redis_client.hincrby(key, str(product_id), add_quantity)



        # ========== 4. 双写：MySQL 也同步写一份（兜底）==========
        existing_item = db.query(CartItem).filter(
            CartItem.user_id == user_id,
            CartItem.product_id == cart_in.product_id
        ).first()

        if existing_item:
            # 已存在：累加数量
            existing_item.quantity = final_qty
            db.commit()
            db.refresh(existing_item)

            redis_client.expire(key, 7 * 24 * 60 * 60)

            return {"id": existing_item.id, "quantity": final_qty}

        # 不存在：新增购物车项
        new_item = CartItem(
            user_id=user_id,
            product_id=cart_in.product_id,
            quantity=final_qty,
        )
        db.add(new_item)
        db.commit()
        redis_client.expire(key, 7 * 24 * 60 * 60)
        db.refresh(new_item)
        return {"id": new_item.id, "quantity": new_item.quantity}

    # ---------- 更新购物车商品数量 ----------
    @staticmethod
    def update_quantity(db: Session, user_id: int, product_id: int,
                        quantity_in: CartUpdateQuantity):
        """
        更新购物车中某商品的数量（Redis Hash 版本）
        注意：现在用 product_id 定位商品，不再用 cart_item_id
        """

        _ensure_cart_in_redis(db, user_id)

        key = _cart_key(user_id)
        product_id = product_id
        quantity = quantity_in.quantity

        # ========== 1. 校验：购物车里必须有这个商品 ==========
        existing_qty_str = redis_client.hget(key, str(product_id))
        if not existing_qty_str:
            raise HTTPException(status_code=404, detail="购物车商品不存在")
        existing_qty = int(existing_qty_str)

        product=db.query(Product).filter(Product.id == product_id).first()
        if quantity>product.stock:
            raise HTTPException(status_code=400, detail=f"库存不足,当前仅剩 {product.stock} 件")

        # ========== 2. 更新 Redis 内容 ==========
        redis_client.hset(key,str(product_id),str(quantity))

        # ========== 3. 双写：MySQL 也同步写一份（兜底）==========
        item=db.query(CartItem).filter(
            CartItem.user_id == user_id,
            CartItem.product_id == product_id
        ).first()
        if item:
            item.quantity = quantity
            db.commit()
            db.refresh(item)

        # ========== 5. 续期 ==========
        redis_client.expire(key, 7 * 24 * 60 * 60)



    # ---------- 删除购物车商品 ----------
    @staticmethod
    def delete_cart(db: Session, user_id: int, product_id: int):
        """
        删除购物车中的某商品
        需要验证该购物车项是否属于当前用户
        """
        _ensure_cart_in_redis(db, user_id)

        key = _cart_key(user_id)
        # ========== 1. 校验：购物车里必须有这个商品 ==========
        existing_product=redis_client.hdel(key,str(product_id))
        if not existing_product:
            raise HTTPException(status_code=404, detail="购物车商品不存在")

        redis_client.hdel(key,str(product_id))

        # ========== 2. 双写：MySQL 也同步写一份（兜底）==========
        item=db.query(CartItem).filter(
            CartItem.user_id == user_id,
            CartItem.product_id == product_id
        ).first()
        if item:
            db.delete(item)
            db.commit()

        redis_client.expire(key, 7 * 24 * 60 * 60)
        return None









# ============ 下面是模块级辅助函数（class 外面，顶格写）============

def _cart_key(user_id: int)->str:
    """
       生成某个用户购物车的 Redis key
       统一写在这里，避免各处手写 f-string 写错前缀
    """
    return f"cart:user:{user_id}"


def _sync_mysql_cart_to_redis(db: Session, user_id: int):
    """
        把 MySQL 里的购物车数据同步到 Redis（一般只在 Redis 里没数据时调用一次）
        相当于：重建 Redis 购物车缓存
    """
    if not redis_available():
        return

    key = _cart_key(user_id)

    # 2. 从 MySQL 查这个用户所有的购物车项
    mysql_items = db.query(CartItem).filter(CartItem.user_id == user_id).all()

    # 3. 如果 MySQL 里也啥都没有，就啥也不做
    if not mysql_items:
        return

    # 3. 把 MySQL 数据转成 Redis Hash 需要的格式：{product_id(str): quantity(str)}
    mapping = {}
    for item in mysql_items:
        mapping[str(item.product_id)] = str(item.quantity)

    # 4. 写入 Redis
    try:
        redis_client.hset(key, mapping=mapping)
        redis_client.expire(key, 7 * 24 * 60 * 60)
    except redis.ConnectionError:
        pass


def _ensure_cart_in_redis(db: Session, user_id: int):
    """
    确保 Redis 里有这个用户的购物车数据
    如果 Redis 是空的，就从 MySQL 同步过来
    每个读操作前先调这个函数，相当于"缓存预热"
    """
    if not redis_available():
        raise HTTPException(
            status_code=503,
            detail="购物车服务暂时不可用，请稍后重试"
        )
    key = _cart_key(user_id)
    try:
        if redis_client.hlen(key) == 0:
            _sync_mysql_cart_to_redis(db, user_id)
    except redis.ConnectionError:
        raise HTTPException(
            status_code=503,
            detail="购物车服务暂时不可用，请稍后重试"
        )