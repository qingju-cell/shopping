# ============================================================
# order_service.py —— 订单业务逻辑层
# 功能：
#   1. 生成订单编号（时间戳 + 随机数）
#   2. 创建订单（核心：扣库存、写订单主表、写订单明细）
#   3. 查询用户的订单列表
#   4. 查询订单详情
# 关键技术：
#   - with_for_update(): 行锁，防止并发扣库存导致超卖
#   - with db.begin_nested(): 事务嵌套，任何步骤失败都会回滚
#   - joinedload(): 预加载订单明细，解决 SQLAlchemy 懒加载问题
# ============================================================

import random
import time
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models.order import Order, OrderItem
from app.models.product import Product
from app.schemas.order import OrderCreate


class OrderService:
    PENDING_PAYMENT = 0
    PAID = 1
    SHIPPED = 2
    COMPLETED = 3
    CANCELLED = 4

    # ---------- 生成订单编号 ----------
    @staticmethod
    def generate_order_no():
        """
        生成唯一的订单编号
        格式：时间戳（秒）+ 4位随机数
        例如：17000000001234
        """
        timestamp = str(int(time.time()))          # 当前时间戳（秒）
        random_num = str(random.randint(1000, 9999))  # 4 位随机数
        return f"{timestamp}{random_num}"

    # ---------- 创建订单（核心方法）----------
    @staticmethod
    def create_order(
        db: Session,
        user_id: int,
        order_in: OrderCreate,
        agent_draft_id: str | None = None,
    ):
        """
        创建订单：整个过程在一个事务中，任何步骤失败都会全部回滚
        
        流程：
        1. 开启事务（begin_nested）
        2. 创建订单主记录（先占位，总金额先填 0）
        3. 遍历每个商品：
           - 检查商品是否存在、是否上架
           - 检查库存是否充足
           - 扣减库存（with_for_update 加行锁，防止并发超卖）
           - 计算小计金额，累加总金额
           - 创建订单明细记录
        4. 更新订单总金额
        5. 提交事务
        6. 重新查询订单（预加载明细）并返回
        
        with_for_update() 的作用：
        - 锁住查询到的商品行，直到事务提交
        - 防止多个请求同时扣减同一商品的库存（超卖问题）
        """
        # AI 的网络重试先按草稿编号找旧订单；普通页面下单没有该编号，不受影响。
        if agent_draft_id:
            existing = db.query(Order).filter(Order.agent_draft_id == agent_draft_id).first()
            if existing:
                return db.query(Order).options(
                    joinedload(Order.order_items)
                ).filter(Order.id == existing.id).first()

        total_amount = Decimal("0")
        try:
            # begin_nested 开启一个嵌套事务；中途失败则库存和订单一起回滚。
            with db.begin_nested():
                db_order = Order(
                    order_no=OrderService.generate_order_no(),
                    agent_draft_id=agent_draft_id,
                    user_id=user_id,
                    total_amount=Decimal("0"),
                    receiver_name=order_in.receiver_name,
                    receiver_phone=order_in.receiver_phone,
                    receiver_address=order_in.receiver_address,
                    remark=order_in.remark,
                )
                db.add(db_order)
                # flush 让数据库生成自增 ID，这样后面的 OrderItem 才能引用 order_id。
                db.flush()

                for item in order_in.items:
                    product = db.query(Product).filter(
                        Product.id == item.product_id,
                        Product.status == 1,
                    ).with_for_update().first()
                    if not product:
                        raise HTTPException(status_code=404, detail="商品不存在或已下架")
                    if product.stock < item.quantity:
                        raise HTTPException(status_code=400, detail="商品库存不足")

                    product.stock -= item.quantity
                    subtotal = Decimal(product.price) * item.quantity
                    total_amount += subtotal
                    db.add(OrderItem(
                        order_id=db_order.id,
                        product_id=product.id,
                        product_name=product.name,
                        product_price=product.price,
                        quantity=item.quantity,
                        subtotal=subtotal,
                    ))

                db_order.total_amount = total_amount

            # 所有操作一次性生效。
            db.commit()
        except IntegrityError:
            # 两个请求同时确认同一 draft_id 时，唯一约束只允许一个创建；另一个取回原订单。
            db.rollback()
            if agent_draft_id:
                existing = db.query(Order).filter(Order.agent_draft_id == agent_draft_id).first()
                if existing:
                    return db.query(Order).options(
                        joinedload(Order.order_items)
                    ).filter(Order.id == existing.id).first()
            raise
        except Exception:
            db.rollback()
            raise

        # 6. 重新查询订单，并预加载订单明细
        # joinedload 解决 SQLAlchemy 懒加载问题
        # 如果不使用 joinedload，在序列化 Order 时 order_items 可能为空
        db_order = db.query(Order).options(
            joinedload(Order.order_items)
        ).filter(Order.id == db_order.id).first()

        return db_order

    # ---------- 查询用户的订单列表 ----------
    @staticmethod
    def get_user_order(db: Session, user_id: int):
        """
        获取指定用户的所有订单，按订单 ID 倒序排列（最新的在前）
        使用 joinedload 预加载订单明细，避免懒加载问题
        """
        orders = db.query(Order).options(
            joinedload(Order.order_items)
        ).filter(Order.user_id == user_id).order_by(Order.id.desc()).all()
        return orders

    # ---------- 查询订单详情 ----------
    @staticmethod
    def get_order_detail(db: Session, user_id: int, order_id: int):
        """
        获取单个订单的详细信息
        需要验证该订单是否属于当前用户（防止越权访问）
        """
        order = db.query(Order).options(
            joinedload(Order.order_items)
        ).filter(Order.user_id == user_id).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="订单不存在")
        return order

    # ---------- 模拟支付 ----------
    @staticmethod
    def pay_order(db: Session, user_id: int, order_id: int):
        """将待支付订单更新为已支付。

        库存在 create_order() 中已通过同一笔下单事务扣减；这里绝不能再次扣库存。
        with_for_update() 会在支付状态切换期间锁住订单行，避免同一订单被两个请求同时支付。
        """
        try:
            with db.begin_nested():
                order = db.query(Order).filter(
                    Order.id == order_id,
                    Order.user_id == user_id,
                ).with_for_update().first()

                if not order:
                    raise HTTPException(status_code=404, detail="订单不存在")

                # 网络重试或用户连点时，已支付订单直接返回，保证接口幂等。
                if order.status == OrderService.PAID:
                    pass
                elif order.status == OrderService.PENDING_PAYMENT:
                    order.status = OrderService.PAID
                else:
                    raise HTTPException(status_code=400, detail="当前订单状态不能支付")

            db.commit()
        except Exception:
            db.rollback()
            raise

        return db.query(Order).options(
            joinedload(Order.order_items)
        ).filter(Order.id == order_id).first()
