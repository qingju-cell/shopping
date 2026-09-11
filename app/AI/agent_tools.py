"""ReAct Agent 可调用的受控业务工具。

模型只能调用这里公开的工具，不能直接连接数据库或执行 SQL。
当前工具只允许查库存、创建订单草稿、补全收货信息；只有用户明确确认后才能创建真实订单。
"""

# json：把工具返回的 Python 字典转为模型可阅读的 JSON 文本。
import json
from uuid import uuid4
# 类型注解：描述参数类型；不改变运行逻辑。
from typing import Annotated, Any, Optional

# @tool 将安全的 Python 函数注册为模型可申请调用的工具。
from langchain_core.tools import tool
# InjectedState 让 ToolNode 注入后端状态，避免模型伪造 user_id/session_id。
from langgraph.prebuilt import InjectedState
# Session 是 SQLAlchemy 数据库会话的类型；SessionLocal 用于创建真实会话。
from sqlalchemy.orm import Session

# 订单草稿的数据结构和字段完整性规则。
from app.AI.order_draft import fill_pending_order_receiver, start_pending_order
from app.database import SessionLocal
# Product 是 products 表的 ORM 模型，用于查询实时价格、状态与库存。
from app.models.product import Product
# OrderCreate 是复用原有下单服务所需的“订单输入单”；OrderService 负责事务、行锁和扣库存。
from app.schemas.order import OrderCreate
from app.services.order_service import OrderService


def _read_product_for_order(
    product_id: int, quantity: int = 1, db: Optional[Session] = None
) -> dict:
    """读取下单前必须确认的实时商品状态；供 Tool 与单元测试共同复用。"""
    if isinstance(quantity, bool) or quantity < 1:
        return {
            "ok": False,
            "code": "INVALID_QUANTITY",
            "message": "购买数量必须是大于 0 的整数。",
        }

    own_session = db is None
    db = db or SessionLocal()
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if product is None:
            return {
                "ok": False,
                "code": "PRODUCT_NOT_FOUND",
                "message": "商品不存在。",
            }
        if product.status != 1:
            return {
                "ok": False,
                "code": "PRODUCT_OFF_SHELF",
                "message": "商品已下架，不能下单。",
            }
        if product.stock < quantity:
            return {
                "ok": False,
                "code": "INSUFFICIENT_STOCK",
                "message": "商品库存不足。",
                "available_stock": product.stock,
            }

        return {
            "ok": True,
            "requested_quantity": quantity,
            "product": {
                "id": product.id,
                "product_code": product.product_code,
                "name": product.name,
                "price": float(product.price),
                "stock": product.stock,
                "image_url": product.image_url or "",
            },
        }
    finally:
        if own_session:
            db.close()


@tool
def check_product_for_order(product_id: int, quantity: int = 1) -> str:
    """查询某件商品是否可按指定数量下单，并返回实时价格和库存。

    仅在已经明确商品 ID 时调用。此工具只读数据库，不创建订单、不扣减库存。
    """
    result = _read_product_for_order(product_id, quantity)
    return json.dumps(result, ensure_ascii=False)


def _start_order_draft(
    product_id: int,
    quantity: int,
    user_id: int | None,
    session_id: str | None,
    memory: dict | None,
    db: Optional[Session] = None,
) -> tuple[dict[str, Any], dict | None]:
    """创建草稿的可测试业务部分；不负责读取或写入会话记忆。"""
    if not user_id or not session_id:
        return {
            "ok": False,
            "code": "LOGIN_REQUIRED",
            "message": "请先登录后再通过 AI 创建订单草稿。",
        }, None

    checked = _read_product_for_order(product_id, quantity, db=db)
    if not checked["ok"]:
        return checked, None

    updated_memory = start_pending_order(memory, checked["product"], quantity)
    draft = updated_memory["pending_order"]
    return {
        "ok": True,
        "code": "DRAFT_CREATED",
        "message": "订单草稿已创建；请继续收集收货人姓名、电话和地址，不能直接创建订单。",
        "pending_order": {
            "status": draft["status"],
            "items": draft["items"],
            "missing_receiver_fields": ["receiver_name", "receiver_phone", "receiver_address"],
        },
    }, updated_memory


@tool
def start_order_draft(
    product_id: int,
    quantity: int = 1,
    state: Annotated[dict, InjectedState] = None,
) -> str:
    """为已明确商品和数量的购买需求创建待确认订单草稿。

    此工具会再次读取实时库存，并把草稿绑定到当前登录用户的当前会话。
    它只保存草稿，不创建订单、不扣减库存；缺少收货信息时必须继续询问用户。
    """
    state = state or {}
    # 记忆已独立到 memory.py；工具无需再反向依赖庞大的 ai_core.py。
    from app.AI.memory import load_structured_memory, save_structured_memory

    user_id = state.get("user_id")
    session_id = state.get("session_id")
    memory = load_structured_memory(user_id, session_id) if user_id and session_id else {}
    result, updated_memory = _start_order_draft(
        product_id, quantity, user_id, session_id, memory
    )
    if updated_memory is not None:
        save_structured_memory(user_id, session_id, updated_memory)
    return json.dumps(result, ensure_ascii=False)


def _fill_order_draft_receiver(
    user_id: int | None,
    session_id: str | None,
    memory: dict | None,
    receiver_name: str = "",
    receiver_phone: str = "",
    receiver_address: str = "",
    remark: str = "",
) -> tuple[dict[str, Any], dict | None]:
    """补全草稿的可测试业务部分；不直接读取或写入数据库。"""
    if not user_id or not session_id:
        return {
            "ok": False,
            "code": "LOGIN_REQUIRED",
            "message": "请先登录后再通过 AI 补全订单草稿。",
        }, None

    provided_fields = {
        name: value.strip()
        for name, value in {
            "receiver_name": receiver_name,
            "receiver_phone": receiver_phone,
            "receiver_address": receiver_address,
            "remark": remark,
        }.items()
        if isinstance(value, str) and value.strip()
    }
    if not provided_fields:
        return {
            "ok": False,
            "code": "NO_RECEIVER_FIELDS",
            "message": "本轮没有识别到可保存的收货信息。",
        }, None

    try:
        updated_memory = fill_pending_order_receiver(memory, **provided_fields)
    except ValueError as error:
        return {
            "ok": False,
            "code": "NO_PENDING_ORDER",
            "message": str(error),
        }, None

    draft = updated_memory["pending_order"]
    missing_fields = draft["missing_receiver_fields"]
    return {
        "ok": True,
        "code": "DRAFT_READY_FOR_CONFIRMATION" if not missing_fields else "DRAFT_RECEIVER_UPDATED",
        "message": "收货信息已齐全，请向用户展示确认单并等待明确确认。" if not missing_fields
        else "收货信息已部分保存，请继续询问缺少的字段。",
        # 不把完整电话和地址回传给模型；模型只需要知道状态、商品和缺失字段。
        "pending_order": {
            "status": draft["status"],
            "items": draft["items"],
            "missing_receiver_fields": missing_fields,
        },
    }, updated_memory


@tool
def fill_order_draft_receiver(
    receiver_name: str = "",
    receiver_phone: str = "",
    receiver_address: str = "",
    remark: str = "",
    state: Annotated[dict, InjectedState] = None,
) -> str:
    """将用户本轮明确给出的收货人姓名、电话、地址或备注补充到待确认订单草稿。

    只传入本轮用户实际说出的字段；工具会保留旧字段，不会凭空补全。
    工具不会创建订单或扣减库存。资料齐全后只能展示确认单并等待用户明确确认。
    """
    state = state or {}
    from app.AI.memory import load_structured_memory, save_structured_memory

    user_id = state.get("user_id")
    session_id = state.get("session_id")
    memory = load_structured_memory(user_id, session_id) if user_id and session_id else {}
    result, updated_memory = _fill_order_draft_receiver(
        user_id,
        session_id,
        memory,
        receiver_name,
        receiver_phone,
        receiver_address,
        remark,
    )
    if updated_memory is not None:
        save_structured_memory(user_id, session_id, updated_memory)
    return json.dumps(result, ensure_ascii=False)


def _confirm_pending_order(
    user_id: int | None,
    session_id: str | None,
    memory: dict | None,
    db: Optional[Session] = None,
) -> tuple[dict[str, Any], dict | None]:
    """将资料齐全的草稿交给既有订单服务，创建一张待支付订单。

    订单服务会在数据库事务内重新读取库存、加行锁、扣库存、写订单和明细。
    本函数不相信草稿里的价格与库存，因为它们可能已经过期。
    """
    if not user_id or not session_id:
        return {
            "ok": False,
            "code": "LOGIN_REQUIRED",
            "message": "请先登录后再确认提交订单。",
        }, None

    updated_memory = dict(memory or {})
    draft = dict(updated_memory.get("pending_order") or {})
    if not draft:
        return {
            "ok": False,
            "code": "NO_PENDING_ORDER",
            "message": "当前会话没有可确认的订单草稿。",
        }, None

    if draft.get("status") != "ready_for_confirmation":
        return {
            "ok": False,
            "code": "DRAFT_NOT_READY",
            "message": "收货人姓名、电话和地址尚未收集完整，暂时不能提交。",
        }, None

    # 兼容本次升级前已经保存的旧草稿：首次确认时补上唯一编号。
    draft_id = draft.get("draft_id")
    if not isinstance(draft_id, str) or not draft_id:
        draft_id = str(uuid4())
        draft["draft_id"] = draft_id

    try:
        order_in = OrderCreate(
            items=[
                {"product_id": item["product_id"], "quantity": item["quantity"]}
                for item in draft.get("items", [])
            ],
            receiver_name=draft["receiver_name"],
            receiver_phone=draft["receiver_phone"],
            receiver_address=draft["receiver_address"],
            remark=draft.get("remark") or None,
        )
    except (KeyError, TypeError, ValueError) as error:
        return {
            "ok": False,
            "code": "INVALID_DRAFT",
            "message": f"订单草稿格式不完整：{error}",
        }, None

    own_session = db is None
    db = db or SessionLocal()
    try:
        # 复用普通下单入口的核心业务：这里会重新校验实时库存，绝不直接相信草稿快照。
        order = OrderService.create_order(db, user_id, order_in, agent_draft_id=draft_id)
    except Exception as error:
        # 创建失败时 OrderService 的嵌套事务会回滚；这里额外 rollback，让当前会话可安全关闭或复用。
        db.rollback()
        detail = getattr(error, "detail", None)
        return {
            "ok": False,
            "code": "ORDER_CREATE_FAILED",
            "message": str(detail or error),
        }, None
    finally:
        if own_session:
            db.close()

    # 下单任务到此结束：临时草稿立即从会话记忆移除，不会黏在后续聊天中。
    # 重复请求的防护已迁到 orders.agent_draft_id 的数据库唯一约束，不再依赖 memory_json。
    updated_memory.pop("pending_order", None)
    return {
        "ok": True,
        "code": "ORDER_CREATED",
        "message": "订单已创建，当前为待支付状态，请前往订单详情完成支付。",
        "order": {
            "id": order.id,
            "order_no": order.order_no,
            "total_amount": float(order.total_amount),
            "status": "pending_payment",
        },
    }, updated_memory


@tool
def confirm_order_draft(
    state: Annotated[dict, InjectedState] = None,
) -> str:
    """仅当用户明确说“确认提交”时，提交当前资料齐全的订单草稿。

    工具会创建一张待支付订单，并在同一笔数据库事务中重新校验库存、扣减库存。
    不能因为“我想买”或“资料填完”就调用；绝不自动支付。
    """
    state = state or {}
    from app.AI.memory import load_structured_memory, save_structured_memory

    user_id = state.get("user_id")
    session_id = state.get("session_id")
    memory = load_structured_memory(user_id, session_id) if user_id and session_id else {}
    result, updated_memory = _confirm_pending_order(user_id, session_id, memory)
    if updated_memory is not None:
        save_structured_memory(user_id, session_id, updated_memory)
    return json.dumps(result, ensure_ascii=False)


# 后续 LangGraph/ReAct 节点只从这个白名单取工具，避免模型越权调用任意函数。
ORDER_AGENT_TOOLS = [
    check_product_for_order,
    start_order_draft,
    fill_order_draft_receiver,
    confirm_order_draft,
]
