from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.order import Order, OrderItem
from app.models.product import Product
from app.schemas.order import OrderCreate
from app.services.order_service import OrderService


@pytest.fixture()
def db_session():
    """使用临时 SQLite 数据库测试订单流程，不触碰 Docker 中的真实商品数据。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine, tables=[Product.__table__, Order.__table__, OrderItem.__table__])
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine, tables=[OrderItem.__table__, Order.__table__, Product.__table__])


def test_create_order_deducts_stock_once_and_payment_only_changes_status(db_session):
    product = Product(name="测试耳机", price=Decimal("99.00"), stock=1, status=1)
    db_session.add(product)
    db_session.commit()

    order = OrderService.create_order(
        db_session,
        user_id=7,
        order_in=OrderCreate(
            items=[{"product_id": product.id, "quantity": 1}],
            receiver_name="小杨",
            receiver_phone="13800138000",
            receiver_address="测试地址",
        ),
    )

    db_session.refresh(product)
    assert order.status == OrderService.PENDING_PAYMENT
    assert product.stock == 0
    assert len(order.order_items) == 1

    paid_order = OrderService.pay_order(db_session, user_id=7, order_id=order.id)
    db_session.refresh(product)
    assert paid_order.status == OrderService.PAID
    assert product.stock == 0  # 支付不能再扣一次；库存已经在创建订单时从 1 变为 0。


def test_create_order_rolls_back_everything_when_one_item_is_out_of_stock(db_session):
    available = Product(name="有货商品", price=Decimal("10.00"), stock=1, status=1)
    sold_out = Product(name="缺货商品", price=Decimal("20.00"), stock=0, status=1)
    db_session.add_all([available, sold_out])
    db_session.commit()

    with pytest.raises(HTTPException, match="库存不足"):
        OrderService.create_order(
            db_session,
            user_id=7,
            order_in=OrderCreate(
                items=[
                    {"product_id": available.id, "quantity": 1},
                    {"product_id": sold_out.id, "quantity": 1},
                ],
                receiver_name="小杨",
                receiver_phone="13800138000",
                receiver_address="测试地址",
            ),
        )

    db_session.refresh(available)
    assert available.stock == 1  # 第一件商品的临时扣减已被事务回滚。
    assert db_session.query(Order).count() == 0  # 订单主表也没有留下半张订单。
