"""AI HTTP 入口的无模型单元测试。"""

from app.api import ai as ai_api


def test_ai_chat_enters_the_agent_once(monkeypatch):
    """接口层不应先分类一次、再让 LangGraph 分类一次。"""
    calls = []

    def fake_run_agent(question, history_text, user_id=None, session_id=None):
        calls.append((question, history_text, user_id, session_id))
        return {"answer": "测试回答", "intent": "product", "session_id": session_id or "new-session"}

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
    assert response.code == 200