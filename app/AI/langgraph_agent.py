# ============================================================
# langgraph_agent.py —— LangGraph 多 Agent 架构
# 与手写版（ai.py + step5_rag_chatbot_langchain.py）的对比：
#   手写版：if-elif-else 路由 + 手动传参
#   LangGraph版：StateGraph 状态图 + 自动状态传递 + 条件路由
# ============================================================


import os
import sys
from typing import TypedDict, Annotated
from operator import add

from langgraph.graph import StateGraph, END

# ---------- 定义 State（工作流的数据载体）----------
class AgentState(TypedDict):
    """
    这是整个工作流共享的状态对象。
    每个节点函数读取它，返回部分更新，LangGraph 自动合并。

    对比手写版：手写版的数据分散在 ai.py 的变量里，
    这里统一放在一个 TypedDict 里，结构化、可追溯、可调试。
    """
    question:str      # 用户问题
    history_text:str  # 历史对话文本
    intent:str        # 意图分类
    search_keyword:str # 搜索关键词
    answer:str        # 回答文本


# ---------- 节点 1：意图分类 ----------
def classify_intent_node(state:AgentState)->dict:
    """
        对应手写版 ai.py 里的：
            intent, search_keywords = _classify_fn(question, _llm, history_text)

        区别：
            手写版：返回两个值，调用方手动拆包
            LangGraph版：返回 dict，框架自动合并到 State
    """
    from app.AI.step5_rag_chatbot_langchain import classify_intent_and_expand
    intent, search_keywords = classify_intent_and_expand(state["question"], state["history_text"])
    print (f"意图分类结果：{intent}, 搜索关键词：{search_keywords}")
    return {"intent": intent, "search_keyword": search_keywords}

# ---------- 节点 2：商品推荐（RAG）----------
def product_node(state:AgentState)->dict:
    """
       对应手写版 ai.py 里的：
           answer = _langchain_module.product_channel(
               _product_chain, question, history_text, search_keywords
           )

       区别：
           手写版：需要手动传 4 个参数
           LangGraph版：从 State 里取，不需要考虑参数顺序
       """
    from app.AI.step5_rag_chatbot_langchain import product_channel
    answer=product_channel(
        state["question"],
        state["history_text"],
        state["search_keyword"],
    )
    print (f"商品推荐结果：{answer}")
    return {"answer": answer}


# ---------- 节点 3：闲聊 ----------

def chat_node(state: AgentState) -> dict:
    """
    对应手写版：chat_channel(_chat_chain, question, history_text)
    """
    from app.AI.step5_rag_chatbot_langchain import chat_channel

    answer=chat_channel(state["question"], state["history_text"])
    print (f"闲聊结果：{answer}")
    return {"answer": answer}


# ---------- 节点 4：售后 ----------
def service_node(state: AgentState) -> dict:
    """
    对应手写版：service_channel(question)
    """
    from app.AI.step5_rag_chatbot_langchain import service_channel

    answer = service_channel(state["question"])
    print (f"售后结果：{answer}")
    return {"answer": answer}


# ---------- 节点 5：恶意拒绝 ----------
def abuse_node(state: AgentState) -> dict:
    """
    对应手写版：abuse_channel(question)
    """
    from app.AI.step5_rag_chatbot_langchain import abuse_channel

    answer = abuse_channel(state["question"])
    print (f"恶意拒绝结果：{answer}")
    return {"answer": answer}

# ---------- 节点 6：路由 ----------
def route_by_intent(state: AgentState) -> str:
    intent = state.get("intent", "product")
    return intent  # 返回 product / chat / service / abuse


# ---------- 构建 StateGraph ----------
def build_graph():
    """
    这是 LangGraph 的"装配车间"。
    把节点和边按顺序组装成一张有向图。

    手写版：ai.py 里的流程是隐式的，只能通过读代码理解
     LangGraph 版：图结构是显式的，甚至可以用 .get_graph().draw_mermaid() 可视化
    """
    # 1. 创建图，指定 State 类型
    workflow=StateGraph(AgentState)

    # 2. 添加节点（给每个节点起个名字，和图里的方块对应）
    workflow.add_node("classify_intent_node", classify_intent_node)
    workflow.add_node("product_node", product_node)
    workflow.add_node("chat_node", chat_node)
    workflow.add_node("service_node", service_node)
    workflow.add_node("abuse_node", abuse_node)

    # 3. 设置入口节点（图从哪个节点开始执行）
    workflow.set_entry_point("classify_intent_node")
    # 4. 添加条件边：从 classify_intent 出发，根据意图路由到不同节点
    workflow.add_edges("classify_intent_node",   # 从哪个节点出发
                       route_by_intent,          # 路由函数：返回下一个节点名
                       {
                           "product": "product_node",
                           "chat": "chat_node",
                           "service": "service_node",
                           "abuse": "abuse_node",
                       }
                       )
    # 5. 所有通道节点执行完后，结束
    workflow.add_edge("product_node", END)
    workflow.add_edge("chat_node", END)
    workflow.add_edge("service_node", END)
    workflow.add_edge("abuse_node", END)

    # 6. 编译图（把声明式的图结构编译成可执行的 Runnable）
    return workflow.compile()

# ---------- 全局单例：和图相关的初始化 ----------
_graph = None
_llm = None
_chat_chain = None
_product_chain = None
_initialized = False

def init_langgraph():
    """
    初始化 LLM、Chain、Graph（和手写版 ai.py 的 _init_rag() 对应）
    """
    global _graph, _llm, _chat_chain, _product_chain, _initialized
    if _initialized:
        return

    from app.AI.step5_rag_chatbot_langchain import (
        get_llm, get_vectorstore, build_chat_chain, build_product_chain,
    )

    _llm = get_llm()
    _chat_chain = build_chat_chain(_llm)
    vectorstore = get_vectorstore()
    _product_chain = build_product_chain(vectorstore, _llm)

    _graph = build_graph()
    _initialized = True
    print("✅ LangGraph 工作流初始化完成")



def run_agent(question: str, history_text: str = "") -> dict:
    """
    执行 LangGraph 工作流，返回最终 State

    手写版（ai.py）：
        intent, keywords = _classify_fn(question, _llm, history_text)
        if intent == "abuse": ...
        elif intent == "service": ...
        ...

    LangGraph 版：
        graph.invoke(initial_state) → 一行代码搞定整个流程
    """
    init_langgraph()

    initial_state: AgentState = {
        "question": question,
        "history_text": history_text,
        "intent": "",
        "search_keyword": "",
        "answer": "",
    }

    result = _graph.invoke(initial_state)
    return result