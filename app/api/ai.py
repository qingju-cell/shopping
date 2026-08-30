# ============================================================
# ai.py —— AI 智能客服模块路由
# 功能：提供前端调用 AI 客服的 HTTP 接口
# 接口列表：
#   - POST  /api/ai/chat        发送消息给 AI，获取回答
# 核心逻辑：导入阶段四写好的 LangChain RAG 机器人
# ============================================================

import os
import sys
import threading
import importlib.util
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.common.response import ApiResponse

# ---------- 定位项目根目录和 AI 目录（绝对路径，100% 不迷路）----------
# 当前文件：D:/python/project/shopping/app/api/ai.py
# 往上跳 2 级：    D:/python/project/shopping/       ← 项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
# AI 模块目录：    D:/python/project/shopping/app/AI/ ← langchain 代码在哪
_AI_MODULE_DIR = _PROJECT_ROOT / "app" / "AI"


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


# ---------- 创建路由 ----------
router = APIRouter(prefix="/ai", tags=["AI 智能客服"])


# ---------- 全局单例：LangChain RAG 组件 + 已加载的阶段四模块 ----------
# 说明：这些都是重量级对象，启动时初始化一次就行，不要每次请求都新建
_init_lock = threading.Lock()  # 防止并发重复初始化，确保只初始化一次
_rag_ready = False
_vectorstore = None
_llm = None
_chat_chain = None
_product_chain = None
_classify_fn = None
_langchain_module = None   # AI 核心模块（合并版 ai_core.py）
_memory_formatter = None   # 把历史对话格式化成 Prompt 能用的文本


def _load_module_by_path(module_name: str, file_name: str):
    """
    ⭐ 通用工具函数：用 importlib 动态加载一个 .py 文件
    好处：不依赖 sys.path 和包结构，只要文件路径对就能加载
    :param module_name: 给模块起的别名（随便写，不重名就行）
    :param file_name:   app/AI/ 目录下的文件名（比如 "step5_rag_chatbot_langchain.py"）
    :return:            加载后的模块对象
    """
    module_file = _AI_MODULE_DIR / file_name
    if not module_file.exists():
        raise FileNotFoundError(
            f"找不到模块文件：{module_file}\n"
            f"请确认阶段四的 {file_name} 文件存在！"
        )

    # importlib 固定三件套：spec_from_file_location → module_from_spec → spec.loader.exec_module
    spec = importlib.util.spec_from_file_location(module_name, str(module_file))
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载模块：{module_file}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module        # 注册到 sys.modules，避免重复加载
    spec.loader.exec_module(module)        # 执行模块代码
    return module


def _load_ai_modules():
    """
    加载 AI 核心模块（合并版）
    ai_core.py 包含了所有 AI 代码：嵌入函数、LangChain RAG、LangGraph Agent
    """
    ai_core = _load_module_by_path("ai_core", "ai_core.py")
    return ai_core


def _init_rag():
    """
    懒加载初始化 LangChain RAG 系统
    第一次请求时才初始化，避免服务启动慢
    """
    global _rag_ready, _vectorstore, _llm, _chat_chain, _product_chain, _classify_fn

    # 第一重检查：不加锁，快速判断（99% 的请求走这里，直接返回，不阻塞）
    if _rag_ready:
        return

    # 第二重检查：加锁，确保只有一个线程进去初始化
    # 如果两个请求同时到达，线程1先拿到锁，线程2在外面排队等待
    # 线程1初始化完把 _rag_ready 设为 True，线程2拿到锁后看到 True 直接返回
    with _init_lock:
        if _rag_ready:
            return

        print("\n🤖 正在初始化 LangChain RAG 系统（首次请求，可能较慢）...")

        # 1. 加载环境变量（找 app/AI/.env）
        from dotenv import load_dotenv
        env_path = _AI_MODULE_DIR / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=str(env_path))
            print(f"  ✅ 已加载环境变量：{env_path}")
        else:
            print(f"  ⚠️  未找到 .env 文件：{env_path}，使用系统环境变量")

        # 2. ⭐ 动态加载 AI 核心模块（合并版 ai_core.py）
        global _langchain_module, _memory_formatter
        _langchain_module = _load_ai_modules()
        get_llm                     = _langchain_module.get_llm
        get_vectorstore             = _langchain_module.get_vectorstore
        build_chat_chain            = _langchain_module.build_chat_chain
        build_product_chain         = _langchain_module.build_product_chain
        classify_intent_and_expand  = _langchain_module.classify_intent_and_expand
        _memory_formatter           = _langchain_module.format_memory_for_prompt
        print("  ✅ AI 核心模块加载成功（合并版 ai_core.py）")

        # 3. 依次初始化
        _llm = get_llm()
        print("  ✅ LLM 初始化完成")

        _vectorstore = get_vectorstore()
        print("  ✅ 向量库连接完成")

        _chat_chain = build_chat_chain(_llm)
        print("  ✅ 聊天 Chain 构建完成")

        _product_chain = build_product_chain(_vectorstore, _llm)
        print("  ✅ 商品 RAG Chain 构建完成")

        # 意图分类 + 搜索关键词提取：合并为一次 LLM 调用，省一半时间
        _classify_fn = classify_intent_and_expand
        print("  ✅ 意图分类+查询扩展合并器加载完成")

        _rag_ready = True
        print("🤖 LangChain RAG 系统初始化完毕！\n")


# ---------- 主接口：POST /api/ai/chat ----------
@router.post("/chat", summary="AI 聊天接口")
def ai_chat(req: ChatRequest):
    """
    前端调用格式：
    POST /api/ai/chat
    Body: {
        "question": "你们有什么便宜的手机？",
        "history": [{"role": "user", "content": "xxx"}, {"role": "assistant", "content": "yyy"}],
        "user_id": 1
    }
    返回：{"code": 200, "data": {"answer": "...", "intent": "product"}}
    """
    question = req.question.strip()
    if not question:
        return ApiResponse.error(msg="问题不能为空")

    # 1. 初始化 RAG（仅第一次会慢）
    _init_rag()



    # 3. 把前端传来的历史对话，格式化成 Prompt 能读懂的字符串
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
    history_text = _memory_formatter(history_raw) if history_raw else ""
    if history_text:
        print(f"💾 本轮携带历史记忆：{len(history_raw)} 轮对话")

    # 2. 意图分类 + 搜索关键词提取（合并为一次 LLM 调用，无论有无历史都执行）
    intent, search_keywords = _classify_fn(question, _llm, history_text)
    print(f"\n🙋 用户：{question}")
    print(f"🧠 识别意图：{intent}")
    if search_keywords:
        print(f"🔑 搜索关键词：{search_keywords}")

    # 4. 调用 LangGraph Agent，传入 user_id 自动入库
    from app.AI.ai_core import run_agent

    try:
        result = run_agent(question, history_text,
                           user_id=req.user_id,
                           session_id=getattr(req, "session_id", None))
        answer = result["answer"]
        intent = result["intent"]
    except Exception as e:
        import traceback
        traceback.print_exc()
        answer = "抱歉，我刚才开小差了~"
        intent = "unknown"

    print(f"🤖 AI：{answer[:80]}{'...' if len(answer) > 80 else ''}")

    # 5. 返回规范的 ApiResponse
    return ApiResponse.success(
        data=ChatResponse(answer=answer, intent=intent)
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