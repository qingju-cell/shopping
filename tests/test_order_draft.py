import pytest

from app.AI.order_draft import (
    build_order_draft_confirmation,
    fill_pending_order_receiver,
    start_pending_order,
)


def test_pending_order_collects_receiver_information_before_confirmation():
    memory = start_pending_order(
        {"topic_keywords": ["笔记本"]},
        {"id": 501, "name": "轻薄笔记本", "price": 3999.0},
        quantity=2,
    )

    draft = memory["pending_order"]
    assert draft["status"] == "collecting_receiver"
    assert draft["items"][0]["subtotal"] == 7998.0
    assert memory["topic_keywords"] == ["笔记本"]

    memory = fill_pending_order_receiver(
        memory,
        receiver_name="小杨",
        receiver_phone="13800138000",
        receiver_address="成都市高新区测试路 1 号",
    )

    draft = memory["pending_order"]
    assert draft["status"] == "ready_for_confirmation"
    assert draft["missing_receiver_fields"] == []
    assert draft["receiver_name"] == "小杨"


def test_pending_order_rejects_invalid_quantity_and_missing_draft():
    with pytest.raises(ValueError, match="数量"):
        start_pending_order({"x": 1}, {"id": 501, "price": 1}, quantity=0)

    with pytest.raises(ValueError, match="没有待确认订单"):
        fill_pending_order_receiver({}, receiver_name="小杨")


def test_confirmation_is_only_built_after_receiver_information_is_complete():
    memory = start_pending_order(
        {}, {"id": 501, "name": "轻薄笔记本", "price": 3999.0}, quantity=1,
    )
    assert build_order_draft_confirmation(memory) is None

    memory = fill_pending_order_receiver(
        memory,
        receiver_name="小杨",
        receiver_phone="13800138000",
        receiver_address="成都市高新区测试路 1 号",
    )
    confirmation = build_order_draft_confirmation(memory)

    assert confirmation == {
        "status": "ready_for_confirmation",
        "items": [{
            "product_id": 501,
            "product_code": "PR501",
            "product_name": "轻薄笔记本",
            "quantity": 1,
            "unit_price": 3999.0,
            "subtotal": 3999.0,
        }],
        "total_amount": 3999.0,
        "receiver_name": "小杨",
        "receiver_phone": "13800138000",
        "receiver_address": "成都市高新区测试路 1 号",
        "remark": "",
        "can_confirm": True,
    }
