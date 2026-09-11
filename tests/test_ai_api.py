"""AI HTTP 入口的无模型单元测试。"""

from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from app.AI import ai_core
from app.AI.ai_core import (
    align_recommended_products_to_answer,
    get_created_order_from_current_turn,
    purchase_node,
    route_purchase_after_model,
)
from app.AI.agent_tools import ORDER_AGENT_TOOLS, start_order_draft
from app.api import ai as ai_api


class ToolState(TypedDict):
    """仅用于验证 ToolNode 的隐藏状态注入。"""
    messages: Annotated[list, add_messages]
    user_id: int | None
    session_id: str | None


def test_ai_chat_enters_the_agent_once(monkeypatch):
    """接口层不应先分类一次、再让 LangGraph 分类一次。"""
    calls = []

    def fake_run_agent(question, history_text, user_id=None, session_id=None):
        calls.append((question, history_text, user_id, session_id))
        return {
            "answer": "测试回答",
            "intent": "purchase",
            "session_id": session_id or "new-session",
            "order_draft": {"can_confirm": True, "total_amount": 3999.0},
            "created_order": {"id": 88, "order_no": "202609100001", "total_amount": 3999.0, "status": "pending_payment"},
        }

    monkeypatch.setattr(ai_api, "run_agent", fake_run_agent)

    response = ai_api.ai_chat(ai_api.ChatRequest(
        question="推荐一台电脑",
        history=[ai_api.ChatMessage(role="user", content="你好")],
        user_id=7,
        session_id="computer-shopping",
    ))

    assert len(calls) == 1
    assert calls[0][0] == "推荐一台电脑"
    assert calls[0][2] == 7
    assert calls[0][3] == "computer-shopping"
    assert response.data.session_id == "computer-shopping"
    assert response.data.order_draft == {"can_confirm": True, "total_amount": 3999.0}
    assert response.data.created_order == {
        "id": 88, "order_no": "202609100001", "total_amount": 3999.0, "status": "pending_payment",
    }
    assert response.code == 200


def test_purchase_router_only_runs_tools_when_model_requested_one():
    """ReAct 只有模型明确发出 tool_calls 时才会进入工具节点。"""
    tool_request = AIMessage(
        content="",
        tool_calls=[{
            "name": "check_product_for_order",
            "args": {"product_id": 501, "quantity": 1},
            "id": "tool-call-1",
        }],
    )
    plain_answer = AIMessage(content="请告诉我商品 ID，我来查询库存。")

    assert route_purchase_after_model({"messages": [tool_request]}) == "tools"
    assert route_purchase_after_model({"messages": [plain_answer]}) == "end"


def test_created_order_card_is_emitted_only_for_the_current_confirm_tool_call():
    created = ToolMessage(
        name="confirm_order_draft",
        tool_call_id="confirm-1",
        content='{"ok": true, "code": "ORDER_CREATED", "order": {"id": 88, "status": "pending_payment"}}',
    )

    assert get_created_order_from_current_turn([AIMessage(content="订单已创建"), created]) == {
        "id": 88, "status": "pending_payment",
    }
    assert get_created_order_from_current_turn([AIMessage(content="你好，我能帮你什么？")]) is None


def test_recommended_cards_follow_answer_text_order_and_never_exceed_mentions():
    candidates = [
        {"id": 1, "name": "A 笔记本"},
        {"id": 2, "name": "B 笔记本"},
        {"id": 3, "name": "C 笔记本"},
    ]
    answer = "我更推荐【B 笔记本】，其次是【A 笔记本】。"

    cards = align_recommended_products_to_answer(answer, candidates)

    assert [card["id"] for card in cards] == [2, 1]


def test_purchase_node_lets_the_llm_decide_the_tool_call(monkeypatch):
    """购买意图不再由正则判断；模型必须看到提示词、上下文和工具白名单。"""
    received_messages = []

    class FakeOrderLLM:
        def invoke(self, messages):
            received_messages.extend(messages)
            return AIMessage(content="", tool_calls=[{
                "name": "start_order_draft",
                "args": {"product_id": 505, "quantity": 2},
                "id": "model-chose-start-draft",
            }])

    class FakeLLM:
        def bind_tools(self, tools):
            assert tools == ORDER_AGENT_TOOLS
            return FakeOrderLLM()

    monkeypatch.setattr(ai_core, "_llm", FakeLLM())
    result = purchase_node({
        "question": "我要买 PR505，买 2 件",
        "history_text": "",
        "messages": [HumanMessage(content="我要买 PR505，买 2 件")],
    })
    tool_call = result["messages"][0].tool_calls[0]
    assert tool_call["name"] == "start_order_draft"
    assert tool_call["args"] == {"product_id": 505, "quantity": 2}
    assert "自主判断" in received_messages[0].content
    assert "PR500" in received_messages[0].content


def test_tool_node_injects_session_state_without_exposing_it_to_the_model():
    """模型调用草稿工具时不能伪造 user_id；ToolNode 必须从 State 注入它。"""
    assert set(start_order_draft.args) == {"product_id", "quantity"}

    workflow = StateGraph(ToolState)
    workflow.add_node("tools", ToolNode(ORDER_AGENT_TOOLS))
    workflow.set_entry_point("tools")
    workflow.add_edge("tools", END)
    graph = workflow.compile()
    tool_call = AIMessage(content="", tool_calls=[{
        "name": "start_order_draft",
        "args": {"product_id": 501, "quantity": 1},
        "id": "draft-tool-call",
    }])

    result = graph.invoke({"messages": [tool_call], "user_id": None, "session_id": None})
    assert '"code": "LOGIN_REQUIRED"' in result["messages"][-1].content
