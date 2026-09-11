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
from app.AI.agent_tools import (
    _fill_order_draft_receiver,
    _confirm_pending_order,
    _read_product_for_order,
    _start_order_draft,
)


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


def test_order_agent_product_check_reads_live_stock_without_writing(db_session):
    """Agent 的查询工具只能读取实时状态，不能在预览阶段扣库存。"""
    product = Product(name="工具测试笔记本", price=Decimal("3999.00"), stock=2, status=1)
    db_session.add(product)
    db_session.commit()

    available = _read_product_for_order(product.id, quantity=2, db=db_session)
    insufficient = _read_product_for_order(product.id, quantity=3, db=db_session)

    assert available["ok"] is True
    assert available["product"]["price"] == 3999.0
    assert insufficient["code"] == "INSUFFICIENT_STOCK"
    assert insufficient["available_stock"] == 2
    assert db_session.get(Product, product.id).stock == 2


def test_order_agent_draft_saves_selected_item_without_creating_an_order(db_session):
    """草稿只保存会话内的待确认信息，不能改变商品库存或写入订单表。"""
    product = Product(name="草稿测试手机", price=Decimal("2999.00"), stock=3, status=1)
    db_session.add(product)
    db_session.commit()

    result, memory = _start_order_draft(
        product.id,
        quantity=2,
        user_id=7,
        session_id="draft-session",
        memory={"topic_keywords": ["手机"]},
        db=db_session,
    )

    assert result["code"] == "DRAFT_CREATED"
    assert memory["pending_order"]["items"][0]["product_id"] == product.id
    assert memory["pending_order"]["items"][0]["subtotal"] == 5998.0
    assert db_session.get(Product, product.id).stock == 3
    assert db_session.query(Order).count() == 0


def test_order_agent_draft_requires_logged_in_session(db_session):
    result, memory = _start_order_draft(
        product_id=501,
        quantity=1,
        user_id=None,
        session_id=None,
        memory={},
        db=db_session,
    )

    assert result["code"] == "LOGIN_REQUIRED"
    assert memory is None


def test_order_agent_receiver_tool_fills_draft_without_creating_order(db_session):
    """用户资料只能补进草稿；资料齐全时仍不能写 orders 表或扣库存。"""
    product = Product(name="收货信息测试耳机", price=Decimal("199.00"), stock=4, status=1)
    db_session.add(product)
    db_session.commit()
    _, draft_memory = _start_order_draft(
        product.id,
        quantity=1,
        user_id=7,
        session_id="receiver-session",
        memory={},
        db=db_session,
    )

    result, updated_memory = _fill_order_draft_receiver(
        user_id=7,
        session_id="receiver-session",
        memory=draft_memory,
        receiver_name="小杨",
        receiver_phone="13800138000",
        receiver_address="成都市高新区测试路 1 号",
    )

    assert result["code"] == "DRAFT_READY_FOR_CONFIRMATION"
    assert result["pending_order"]["missing_receiver_fields"] == []
    assert "13800138000" not in str(result)  # 工具结果不重复把电话交给模型。
    assert updated_memory["pending_order"]["receiver_address"] == "成都市高新区测试路 1 号"
    assert db_session.get(Product, product.id).stock == 4
    assert db_session.query(Order).count() == 0


def test_order_agent_receiver_tool_rejects_empty_fields_or_missing_draft(db_session):
    empty_result, _ = _fill_order_draft_receiver(
        user_id=7,
        session_id="receiver-session",
        memory={"pending_order": {"status": "collecting_receiver"}},
    )
    missing_result, _ = _fill_order_draft_receiver(
        user_id=7,
        session_id="receiver-session",
        memory={},
        receiver_name="小杨",
    )

    assert empty_result["code"] == "NO_RECEIVER_FIELDS"
    assert missing_result["code"] == "NO_PENDING_ORDER"


def test_order_agent_explicit_confirmation_creates_one_pending_payment_order(db_session):
    """只有确认提交才创建订单；重复确认必须复用同一订单，不能再扣库存。"""
    product = Product(name="确认测试手机", price=Decimal("2999.00"), stock=2, status=1)
    db_session.add(product)
    db_session.commit()
    _, memory = _start_order_draft(product.id, 1, 7, "confirm-session", {}, db=db_session)
    _, memory = _fill_order_draft_receiver(
        7, "confirm-session", memory,
        receiver_name="小杨", receiver_phone="13800138000", receiver_address="测试地址",
    )

    result, submitted_memory = _confirm_pending_order(7, "confirm-session", memory, db=db_session)

    db_session.refresh(product)
    assert result["code"] == "ORDER_CREATED"
    assert result["order"]["status"] == "pending_payment"
    assert product.stock == 1
    assert db_session.query(Order).count() == 1
    assert "pending_order" not in submitted_memory

    # 模拟两个请求几乎同时读到同一份“等待确认”草稿；数据库 draft_id 必须防止第二张订单。
    retried, retried_memory = _confirm_pending_order(7, "confirm-session", memory, db=db_session)
    db_session.refresh(product)
    assert retried["code"] == "ORDER_CREATED"
    assert "pending_order" not in retried_memory
    assert retried["order"]["id"] == result["order"]["id"]
    assert product.stock == 1
    assert db_session.query(Order).count() == 1


def test_order_agent_cannot_submit_a_draft_with_missing_receiver_fields(db_session):
    product = Product(name="未完善草稿测试", price=Decimal("99.00"), stock=1, status=1)
    db_session.add(product)
    db_session.commit()
    _, memory = _start_order_draft(product.id, 1, 7, "incomplete-session", {}, db=db_session)

    result, updated_memory = _confirm_pending_order(7, "incomplete-session", memory, db=db_session)

    assert result["code"] == "DRAFT_NOT_READY"
    assert updated_memory is None
    assert db_session.get(Product, product.id).stock == 1
    assert db_session.query(Order).count() == 0


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
