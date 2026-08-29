# ============================================================
# cart_service.py —— 购物车业务逻辑层
# 功能：
#   1. 查询用户购物车列表（关联商品信息）
#   2. 添加商品到购物车（检查库存、已存在则累加数量）
#   3. 更新购物车商品数量
#   4. 删除购物车商品
# 核心：Redis 可用时走 Redis Hash（快，原子操作）
#       Redis 挂了自动降级走 MySQL（兜底，保证业务不中断）
# ============================================================

from fastapi import HTTPException
from sqlalchemy.orm import Session
import redis

from app.models.cart import CartItem
from app.models.product import Product
from app.schemas.cart import CartAdd, CartUpdateQuantity
from app.redis_client import redis_client, redis_available
from app.config import settings


def _build_cart_item_result(product: Product, product_id: int, quantity: int):
    """
    组装购物车单项的返回格式（统一的工厂函数，避免 Redis/MySQL 两条路径写两份）
    """
    price = float(product.price)
    subtotal = round(quantity * price, 2)
    return {
        "id": product_id,
        "product_id": product_id,
        "product_name": product.name,
        "product_price": price,
        "product_image": product.image_url,
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
    }


class CartService:

    # ---------- 查询用户购物车列表 ----------
    @staticmethod
    def get_cart_list(db: Session, user_id: int):
        """
        查询用户购物车列表
        - Redis 可用 → 从 Redis Hash 读（快）
        - Redis 不可用 → 直接查 MySQL 关联查询（兜底）
        """
        # ========== 路径 1：Redis 可用，走 Redis ==========
        if redis_available():
            try:
                _ensure_cart_in_redis(db, user_id)
                key = _cart_key(user_id)
                cart_dict = redis_client.hgetall(key)

                result = []
                for product_id_str, qty_str in cart_dict.items():
                    product_id = int(product_id_str)
                    quantity = int(qty_str)

                    product = db.query(Product).filter(Product.id == product_id).first()
                    if not product or product.status != 1:
                        # 下架了，双端清理
                        try:
                            redis_client.hdel(key, str(product_id))
                        except redis.ConnectionError:
                            pass
                        db.query(CartItem).filter(
                            CartItem.user_id == user_id,
                            CartItem.product_id == product_id
                        ).delete()
                        db.commit()
                        continue

                    result.append(_build_cart_item_result(product, product_id, quantity))
                return result
            except redis.ConnectionError:
                pass  # Redis 突然挂了，走下面 MySQL 降级

        # ========== 路径 2：Redis 不可用，走 MySQL ==========
        mysql_items = db.query(CartItem).filter(CartItem.user_id == user_id).all()
        result = []
        for item in mysql_items:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if not product or product.status != 1:
                # 下架了，从 MySQL 清掉
                db.delete(item)
                db.commit()
                continue
            result.append(_build_cart_item_result(product, item.product_id, item.quantity))
        return result

    # ---------- 添加商品到购物车 ----------
    @staticmethod
    def add_cart(db: Session, user_id: int, cart_in: CartAdd):
        """
        添加商品到购物车
        - Redis 可用 → HINCRBY 原子累加，双写 MySQL
        - Redis 不可用 → 直接操作 MySQL
        """
        product_id = cart_in.product_id
        add_quantity = cart_in.quantity

        # ========== 1. 校验商品（必须查 MySQL，库存不能缓存）==========
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="商品不存在")
        if product.status != 1:
            raise HTTPException(status_code=400, detail="该商品已下架,无法加入购物车")
        if product.stock < add_quantity:
            raise HTTPException(status_code=400, detail=f"库存不足,当前仅剩 {product.stock} 件")

        key = _cart_key(user_id)

        # ========== 路径 1：Redis 可用 ==========
        if redis_available():
            try:
                _ensure_cart_in_redis(db, user_id)

                # 先读当前数量，校验库存
                existing_qty_str = redis_client.hget(key, str(product_id)) or "0"
                existing_qty = int(existing_qty_str) + add_quantity
                if product.stock < existing_qty:
                    raise HTTPException(status_code=400, detail=f"加购后超出库存,当前仅剩 {product.stock} 件")

                # HINCRBY 原子加
                final_qty = redis_client.hincrby(key, str(product_id), add_quantity)

                # 双写 MySQL
                existing_item = db.query(CartItem).filter(
                    CartItem.user_id == user_id,
                    CartItem.product_id == product_id
                ).first()

                if existing_item:
                    existing_item.quantity = final_qty
                    db.commit()
                    db.refresh(existing_item)
                    ret_id = existing_item.id
                else:
                    new_item = CartItem(
                        user_id=user_id,
                        product_id=product_id,
                        quantity=final_qty,
                    )
                    db.add(new_item)
                    db.commit()
                    db.refresh(new_item)
                    ret_id = new_item.id

                # 续期
                try:
                    redis_client.expire(key, 7 * 24 * 60 * 60)
                except redis.ConnectionError:
                    pass

                return {"id": ret_id, "quantity": final_qty}
            except redis.ConnectionError:
                pass  # Redis 中途挂了，走 MySQL 降级

        # ========== 路径 2：Redis 不可用，直接走 MySQL ==========
        existing_item = db.query(CartItem).filter(
            CartItem.user_id == user_id,
            CartItem.product_id == product_id
        ).first()

        if existing_item:
            new_qty = existing_item.quantity + add_quantity
            if product.stock < new_qty:
                raise HTTPException(status_code=400, detail=f"加购后超出库存,当前仅剩 {product.stock} 件")
            existing_item.quantity = new_qty
            db.commit()
            db.refresh(existing_item)
            return {"id": existing_item.id, "quantity": new_qty}
        else:
            new_item = CartItem(
                user_id=user_id,
                product_id=product_id,
                quantity=add_quantity,
            )
            db.add(new_item)
            db.commit()
            db.refresh(new_item)
            return {"id": new_item.id, "quantity": new_item.quantity}

    # ---------- 更新购物车商品数量 ----------
    @staticmethod
    def update_quantity(db: Session, user_id: int, product_id: int,
                        quantity_in: CartUpdateQuantity):
        """
        更新购物车中某商品的数量
        - Redis 可用 → HSET，双写 MySQL
        - Redis 不可用 → 直接操作 MySQL
        """
        quantity = quantity_in.quantity
        key = _cart_key(user_id)

        # ========== 1. 查库存 ==========
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product or product.status != 1:
            raise HTTPException(status_code=404, detail="商品不存在或已下架")
        if quantity > product.stock:
            raise HTTPException(status_code=400, detail=f"库存不足,当前仅剩 {product.stock} 件")

        # ========== 路径 1：Redis 可用 ==========
        if redis_available():
            try:
                _ensure_cart_in_redis(db, user_id)

                # 校验购物车里必须有这个商品
                existing_qty_str = redis_client.hget(key, str(product_id))
                if not existing_qty_str:
                    raise HTTPException(status_code=404, detail="购物车商品不存在")

                redis_client.hset(key, str(product_id), str(quantity))

                # 双写 MySQL
                item = db.query(CartItem).filter(
                    CartItem.user_id == user_id,
                    CartItem.product_id == product_id
                ).first()
                if item:
                    item.quantity = quantity
                    db.commit()
                    db.refresh(item)

                # 续期
                try:
                    redis_client.expire(key, 7 * 24 * 60 * 60)
                except redis.ConnectionError:
                    pass
                return
            except redis.ConnectionError:
                pass  # Redis 中途挂了，走 MySQL 降级

        # ========== 路径 2：Redis 不可用，走 MySQL ==========
        item = db.query(CartItem).filter(
            CartItem.user_id == user_id,
            CartItem.product_id == product_id
        ).first()
        if not item:
            raise HTTPException(status_code=404, detail="购物车商品不存在")
        item.quantity = quantity
        db.commit()
        db.refresh(item)

    # ---------- 删除购物车商品 ----------
    @staticmethod
    def delete_cart(db: Session, user_id: int, product_id: int):
        """
        删除购物车中的某商品
        - Redis 可用 → HDEL，双写 MySQL
        - Redis 不可用 → 直接操作 MySQL
        """
        key = _cart_key(user_id)
        deleted = False

        # ========== 路径 1：Redis 可用 ==========
        if redis_available():
            try:
                _ensure_cart_in_redis(db, user_id)

                existing = redis_client.hget(key, str(product_id))
                if not existing:
                    raise HTTPException(status_code=404, detail="购物车商品不存在")

                redis_client.hdel(key, str(product_id))
                deleted = True

                # 续期
                try:
                    redis_client.expire(key, 7 * 24 * 60 * 60)
                except redis.ConnectionError:
                    pass
            except HTTPException:
                raise
            except redis.ConnectionError:
                pass  # Redis 中途挂了，走 MySQL 降级

        # ========== MySQL 双写/降级 ==========
        item = db.query(CartItem).filter(
            CartItem.user_id == user_id,
            CartItem.product_id == product_id
        ).first()
        if item:
            db.delete(item)
            db.commit()
            deleted = True

        if not deleted:
            raise HTTPException(status_code=404, detail="购物车商品不存在")
        return None


# ============ 下面是模块级辅助函数 ============

def _cart_key(user_id: int) -> str:
    """
    生成某个用户购物车的 Redis key
    统一写在这里，避免各处手写 f-string 写错前缀
    """
    return f"cart:user:{user_id}"


def _sync_mysql_cart_to_redis(db: Session, user_id: int):
    """
    把 MySQL 里的购物车数据同步到 Redis
    一般只在 Redis 里没数据时调用一次（缓存预热/恢复）
    """
    if not redis_available():
        return

    key = _cart_key(user_id)
    mysql_items = db.query(CartItem).filter(CartItem.user_id == user_id).all()

    if not mysql_items:
        return

    mapping = {}
    for item in mysql_items:
        mapping[str(item.product_id)] = str(item.quantity)

    try:
        redis_client.hset(key, mapping=mapping)
        redis_client.expire(key, 7 * 24 * 60 * 60)
    except redis.ConnectionError:
        pass


def _ensure_cart_in_redis(db: Session, user_id: int):
    """
    确保 Redis 里有这个用户的购物车数据
    如果 Redis 是空的，就从 MySQL 同步过来
    每个 Redis 操作前先调这个函数（缓存预热）
    """
    if not redis_available():
        return  # Redis 不可用，交给外层降级走 MySQL
    key = _cart_key(user_id)
    try:
        if redis_client.hlen(key) == 0:
            _sync_mysql_cart_to_redis(db, user_id)
    except redis.ConnectionError:
        return  # Redis 不可用，交给外层降级走 MySQL