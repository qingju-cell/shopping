"""AI 下单前的订单草稿数据规则。

草稿不是 Order 数据库记录：它只暂存用户已选商品和收货信息，
在用户明确确认前绝不创建订单、绝不扣减库存。
"""

from datetime import datetime
from typing import Any
from uuid import uuid4


_RECEIVER_FIELDS = ("receiver_name", "receiver_phone", "receiver_address")


def _copy_memory(memory: dict | None) -> dict:
    """复制会话记忆，避免在原字典上直接修改。"""
    return dict(memory or {})


def _missing_receiver_fields(draft: dict[str, Any]) -> list[str]:
    """返回尚未收集到的必填收货字段名。"""
    return [field for field in _RECEIVER_FIELDS if not str(draft.get(field, "")).strip()]


def start_pending_order(memory: dict | None, product: dict[str, Any], quantity: int) -> dict:
    """依据已经查验成功的商品结果创建待确认草稿，不写订单表。"""
    if isinstance(quantity, bool) or quantity < 1:
        raise ValueError("购买数量必须是大于 0 的整数")

    product_id = product.get("id")
    if not isinstance(product_id, int) or product_id < 1:
        raise ValueError("商品草稿必须包含有效的商品 ID")

    updated = _copy_memory(memory)
    unit_price = float(product["price"])
    updated["pending_order"] = {
        # 草稿编号只属于这一笔 AI 下单任务；订单表用它做唯一约束，防并发重复下单。
        "draft_id": str(uuid4()),
        "status": "collecting_receiver",
        "items": [{
            "product_id": product_id,
            "product_code": str(product.get("product_code") or f"PR{product_id}"),
            "product_name": str(product.get("name", "")),
            "quantity": quantity,
            "unit_price": unit_price,
            "subtotal": unit_price * quantity,
        }],
        "receiver_name": "",
        "receiver_phone": "",
        "receiver_address": "",
        "remark": "",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    return updated


def fill_pending_order_receiver(memory: dict | None, **receiver_fields: str) -> dict:
    """把本轮已识别出的收货信息填进草稿，并标出是否可请求用户确认。"""
    updated = _copy_memory(memory)
    draft = dict(updated.get("pending_order") or {})
    if not draft:
        raise ValueError("当前会话没有待确认订单草稿")

    for field in (*_RECEIVER_FIELDS, "remark"):
        value = receiver_fields.get(field)
        if isinstance(value, str) and value.strip():
            draft[field] = value.strip()

    missing_fields = _missing_receiver_fields(draft)
    draft["status"] = "ready_for_confirmation" if not missing_fields else "collecting_receiver"
    draft["missing_receiver_fields"] = missing_fields
    draft["updated_at"] = datetime.now().isoformat(timespec="seconds")
    updated["pending_order"] = draft
    return updated


def build_order_draft_confirmation(memory: dict | None) -> dict[str, Any] | None:
    """把收货信息齐全的草稿转换成可安全展示给当前用户的确认单。

    这一步仍然只是“展示给用户核对”，不是创建 Order，也不会扣减库存。
    """
    draft = dict((memory or {}).get("pending_order") or {})
    if draft.get("status") != "ready_for_confirmation":
        return None

    items = [
        {
            "product_id": item.get("product_id"),
            "product_code": str(item.get("product_code") or f"PR{item.get('product_id', '')}"),
            "product_name": str(item.get("product_name", "")),
            "quantity": int(item.get("quantity", 0)),
            "unit_price": float(item.get("unit_price", 0)),
            "subtotal": float(item.get("subtotal", 0)),
        }
        for item in draft.get("items", [])
        if isinstance(item, dict)
    ]
    if not items:
        return None

    return {
        "status": "ready_for_confirmation",
        "items": items,
        "total_amount": sum(item["subtotal"] for item in items),
        "receiver_name": str(draft.get("receiver_name", "")),
        "receiver_phone": str(draft.get("receiver_phone", "")),
        "receiver_address": str(draft.get("receiver_address", "")),
        "remark": str(draft.get("remark", "")),
        "can_confirm": True,
    }
