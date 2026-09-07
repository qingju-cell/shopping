# ============================================================
# ai.py —— AI 智能客服模块路由
# 功能：提供前端调用 AI 客服的 HTTP 接口
# 接口列表：
#   - POST  /api/ai/chat        发送消息给 AI，获取回答
# 核心逻辑：导入阶段四写好的 LangChain RAG 机器人
# ============================================================

from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.common.response import ApiResponse
from app.AI.ai_core import format_memory_for_prompt, run_agent


# ---------- 请求/响应的 Pydantic 模型 ----------
class ChatMessage(BaseModel):
    """单条聊天消息结构"""
    role: str = Field(..., description="角色：user=用户, assistant=AI")
    content: str = Field(..., description="消息内容")


class ChatRequest(BaseModel):
    """AI 聊天请求体"""
    question: str = Field(..., description="用户当前问的问题", min_length=1)
    history: Optional[List[ChatMessage]] = Field(default=None, description="最近的聊天历史（可选）")
    user_id: Optional[int] = Field(default=None, description="用户ID（可选，暂未使用）")
    session_id: Optional[str] = Field(default=None, description="会话ID（可选，传入则复用同一个会话）")


class ChatResponse(BaseModel):
    """AI 聊天响应体"""
    answer: str = Field(..., description="AI 的回答")
    intent: str = Field(default="unknown", description="识别到的意图：product/chat/service/abuse")
    session_id: Optional[str] = Field(default=None, description="本次消息所属会话ID；登录用户可用于续聊")


# ---------- 创建路由 ----------
router = APIRouter(prefix="/ai", tags=["AI 智能客服"])


# ---------- 主接口：POST /api/ai/chat ----------
@router.post("/chat", summary="AI 聊天接口")
def ai_chat(req: ChatRequest):
    """
    前端调用格式：
    POST /api/ai/chat
    Body: {
        "question": "你们有什么便宜的手机？",
        "history": [{"role": "user", "content": "xxx"}, {"role": "assistant", "content": "yyy"}],
        "user_id": 1,
        "session_id": "上一次响应返回的会话ID（首次可不传）"
    }
    返回：{"code": 200, "data": {"answer": "...", "intent": "product", "session_id": "..."}}
    """
    question = req.question.strip()
    if not question:
        return ApiResponse.error(msg="问题不能为空")

    # 1. 把前端传来的历史对话，格式化成 Prompt 能读懂的字符串。
    # Agent 会在首次 run_agent() 时完成唯一一次初始化。



    #    知识点：这样 AI 就能记住「我刚才说我要手机 → 现在说太贵了 → 推荐更便宜的手机」这种上下文
    #    注意：前端传的 role 是 assistant，但阶段四的记忆里 AI 那边存的是 ai，
    #          这里把 assistant 转成 ai，让格式化函数认出来
    history_raw = []
    if req.history:
        for msg in req.history[-10:]:   # 只保留最近 10 轮，省 token + 速度快
            role = msg.role
            if role == "assistant":
                role = "ai"
            history_raw.append({"role": role, "content": msg.content})
    history_text = format_memory_for_prompt(history_raw) if history_raw else ""
    if history_text:
        print(f"💾 本轮携带历史记忆：{len(history_raw)} 轮对话")

    # 2. 调用唯一的 LangGraph Agent。它内部只做一次意图分类，再按结果路由。
    session_id = None
    try:
        result = run_agent(question, history_text,
                           user_id=req.user_id,
                           session_id=getattr(req, "session_id", None))
        answer = result["answer"]
        intent = result["intent"]
        session_id = result.get("session_id")
    except Exception as e:
        import traceback
        traceback.print_exc()
        answer = "抱歉，我刚才开小差了~"
        intent = "unknown"

    print(f"🤖 AI：{answer[:80]}{'...' if len(answer) > 80 else ''}")

    # 3. 返回规范的 ApiResponse
    return ApiResponse.success(
        data=ChatResponse(answer=answer, intent=intent, session_id=session_id)
    )


# ---------- 获取历史消息接口：GET /api/ai/history ----------
@router.get("/history", summary="获取 AI 聊天历史")
def get_history(user_id: int, session_id: str = None,
                limit: int = 20, offset: int = 0):
    """
    GET /api/ai/history?user_id=1&session_id=abc123&limit=20&offset=0
    返回该用户的历史消息列表（分页）
    """
    from app.AI.ai_core import load_history_from_db
    messages = load_history_from_db(user_id, session_id, limit=limit)
    return ApiResponse.success(data={
        "user_id": user_id,
        "session_id": session_id,
        "total": len(messages),
        "messages": messages,
    })