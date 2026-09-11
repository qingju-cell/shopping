# ============================================================
# ai_core.py —— AI 客服核心代码（合并版）
#
# 将原先分散在以下文件中的 AI 代码全部合并到一个文件：
#   deepseek_emb.py              → BigModelEmbeddingFunction
#   step4_semantic_search.py     → _rerank_by_intent
#   step5_rag_chatbot_langchain.py → LangChain RAG 全套
#   langgraph_agent.py           → LangGraph 多 Agent 工作流
#
# 好处：维护一个文件就行，不用在多个文件之间跳来跳去
# ============================================================

# Python 标准库：路径定位、JSON 会话记忆和偏好/预算处理。
import os
import sys
import json
from datetime import datetime
from typing import Annotated, TypedDict

# ---------- 路径设置 ----------
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 读取 .env 中的 DeepSeek/智谱 API 密钥。
from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(env_path)

# requests 调智谱 Embedding HTTP 接口；numpy 把向量转换为 API 所需格式。
import requests
import numpy as np

# ---------- LangChain 组件 ----------
# LangChain：DeepSeek 对话模型、Prompt、输出解析、可组合执行链与消息类型。
from langchain_deepseek import ChatDeepSeek
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
# Chroma：商品向量库；metrics：将实际 Token 用量写到 Prometheus。
from langchain_chroma import Chroma as LCChroma
from app.metrics import record_llm_token_usage
# Agent 可调用的业务工具白名单；模型不能直接执行任意 Python 函数。
from app.AI.agent_tools import ORDER_AGENT_TOOLS
# 订单草稿：只有收货信息完整时，才组装给当前用户核对的确认单。
from app.AI.order_draft import build_order_draft_confirmation
# 记忆模块：聊天记录、结构化偏好、会话编号和 Prompt 上下文组装。
from app.AI.memory import (
    _get_db_session,
    format_structured_memory_for_prompt,
    format_memory_for_prompt,
    generate_session_id,
    get_memory_file_path,
    load_history_from_db,
    load_memory,
    load_structured_memory,
    merge_memory_into_context,
    remove_structured_memory_from_context,
    save_memory,
    save_message_to_db,
    save_structured_memory,
    update_structured_memory,
)

# ---------- LangGraph ----------
# LangGraph：声明 Agent 流程图、消息追加规则和工具执行节点。
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode


# ============================================================
# 第一部分：BigModelEmbeddingFunction（智谱嵌入 API）
# 来源：deepseek_emb.py
# ============================================================
class BigModelEmbeddingFunction:
    """
    使用智谱AI (BigModel) Embedding API 的封装类
    兼容 Chroma 的嵌入函数接口
    """
    def __init__(self, api_key=None, model="embedding-3", dimensions=512):
        """
        :param api_key: 智谱API Key，若不传则从环境变量 BIGMODEL_API_KEY 读取
        :param model: 嵌入模型名称，默认 "embedding-3"
        :param dimensions: 输出向量维度，默认 512
        """
        self.api_key = api_key or os.getenv("BIGMODEL_API_KEY")
        if not self.api_key:
            raise ValueError("请在环境变量或代码中设置 BIGMODEL_API_KEY")
        self.model = model
        self.dimensions = dimensions
        self.base_url = "https://open.bigmodel.cn/api/paas/v4/embeddings"

    def _call_api(self, texts):
        """
        调用智谱 Embedding API
        texts: list of strings，例如 ["文本1", "文本2"]
        返回: list of vectors (list of floats)
        """
        # ====== 输入规范化：确保 texts 一定是一维字符串列表 ======
        normalized_texts = []

        def _flatten(item):
            """递归展平嵌套列表"""
            if item is None:
                return
            if isinstance(item, str):
                normalized_texts.append(item)
            elif isinstance(item, (list, tuple)):
                for sub in item:
                    _flatten(sub)
            else:
                # 其他类型转字符串
                normalized_texts.append(str(item))

        _flatten(texts)
        texts = normalized_texts

        # 过滤空字符串
        texts = [t for t in texts if t and isinstance(t, str)]
        if not texts:
            raise ValueError("嵌入失败：没有有效的输入文本")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # 智谱 embedding-3 每次最多处理 64 条文本，需要分批
        batch_size = 64
        # 单条文本字符限制（约 3072 tokens ≈ 6000-8000 中文字符，保守点用 3000）
        max_chars_per_text = 3000
        all_embeddings = []

        # 检查并截断过长的文本
        truncated_count = 0
        for i, text in enumerate(texts):
            if len(text) > max_chars_per_text:
                texts[i] = text[:max_chars_per_text]
                truncated_count += 1
        if truncated_count > 0:
            print(f"⚠️  警告: 有 {truncated_count} 条文本超过 {max_chars_per_text} 字符，已自动截断")

        for batch_start in range(0, len(texts), batch_size):
            batch_texts = texts[batch_start:batch_start + batch_size]
            print(f"📤 正在发送第 {batch_start // batch_size + 1} 批: {len(batch_texts)} 条文本到智谱 API")
            if batch_texts:
                print(f"📝 第一条文本长度: {len(batch_texts[0])} 字符，内容预览: {batch_texts[0][:50]}...")

            def _try_request(use_dimensions=True):
                """封装请求逻辑，支持重试"""
                payload = {"model": self.model, "input": batch_texts}
                if use_dimensions:
                    payload["dimensions"] = self.dimensions
                print(f"📦 Payload: model={payload['model']}" + (f", dimensions={payload['dimensions']}" if use_dimensions else ", dimensions=默认"))
                resp = requests.post(self.base_url, json=payload, headers=headers, timeout=60)
                return resp, payload

            try:
                response, payload = _try_request(use_dimensions=True)

                # 第一次失败：尝试去掉 dimensions（错误码 1210 常和参数有关）
                if response.status_code != 200:
                    try:
                        error_data = response.json()
                        print(f"⚠️  首次请求失败: HTTP {response.status_code}, 详情: {error_data}")
                    except:
                        print(f"⚠️  首次请求失败: HTTP {response.status_code}, 详情文本: {response.text}")

                    print("🔧 尝试去掉 dimensions 参数重试...")
                    response, _ = _try_request(use_dimensions=False)

                # 第二次失败：尝试单条单独发送（排查某条文本问题）
                if response.status_code != 200 and len(batch_texts) > 1:
                    try:
                        error_data = response.json()
                        print(f"⚠️  重试仍失败: {error_data}")
                    except:
                        print(f"⚠️  重试仍失败: {response.text}")
                    print("🔧 尝试逐条单独发送（定位问题文本）...")
                    batch_embeddings = []
                    for idx, single_text in enumerate(batch_texts):
                        try:
                            single_resp, _ = _try_request(use_dimensions=False)
                            if single_resp.status_code == 200:
                                single_data = single_resp.json()
                                batch_embeddings.append(single_data["data"][0]["embedding"])
                                print(f"   文本 #{idx} ✅ 成功")
                            else:
                                print(f"   文本 #{idx} ❌ 失败: {single_resp.status_code} - {single_resp.text[:200]}")
                                # 失败的文本填充零向量（避免整个批次挂掉）
                                vec_size = self.dimensions if self.dimensions else 2048
                                batch_embeddings.append([0.0] * vec_size)
                        except Exception as se:
                            print(f"   文本 #{idx} 异常: {se}")
                            vec_size = self.dimensions if self.dimensions else 2048
                            batch_embeddings.append([0.0] * vec_size)
                    all_embeddings.extend(batch_embeddings)
                    print(f"   批次处理完成，成功 {len(batch_embeddings)} 条")
                    continue

                response.raise_for_status()  # 检查HTTP错误
                data = response.json()
                # 提取嵌入向量，按输入顺序排列
                batch_embeddings = [item["embedding"] for item in data['data']]
                all_embeddings.extend(batch_embeddings)
                print(f"   ✅ 批次成功，返回 {len(batch_embeddings)} 个向量，每个向量维度: {len(batch_embeddings[0]) if batch_embeddings else 0}")
            except requests.exceptions.RequestException as e:
                print(f"❌ 智谱 API 请求失败: {e}")
                if hasattr(e, 'response') and e.response:
                    try:
                        error_data = e.response.json()
                        print(f"   错误详情 JSON: {error_data}")
                    except:
                        print(f"   错误详情文本: {e.response.text}")
                raise

        return all_embeddings

    # ---------- Chroma 所需接口 ----------
    def __call__(self, input):
        """Chroma 会调用此方法进行嵌入"""
        return self._call_api(input)

    def name(self):
        return f"bigmodel_{self.model}"

    def embed_documents(self, documents=None, input=None):
        """
        嵌入多个文档
        Chroma 传入的 input 是 list[str]
        返回: list[list[float]] 二维列表
        """
        texts = documents if documents is not None else input
        # 确保是一维列表，不是嵌套列表
        if texts and isinstance(texts[0], list):
            texts = [item for sublist in texts for item in sublist]
        return self._call_api(texts)

    def embed_query(self, query=None, input=None):
        """
        嵌入单个查询
        Chroma 传入的 input 可能是 list[str] 或 str
        返回: list[list[float]] 二维列表（Chroma 期望 embed_query 也是二维列表）
        """
        text_or_list = query if query is not None else input
        # Chroma 可能传 list[str]（如 ['查询文本']）或直接 str
        if isinstance(text_or_list, list):
            # 如果是列表，可能是 [str] 或嵌套列表，需要展开
            if text_or_list and isinstance(text_or_list[0], list):
                texts = [item for sublist in text_or_list for item in sublist]
            else:
                texts = text_or_list
        else:
            # 直接是字符串
            texts = [text_or_list]
        return self._call_api(texts)


# ============================================================
# 第二部分：_rerank_by_intent（意图重排）
# 来源：step4_semantic_search.py
# ============================================================
def _rerank_by_intent(question, results_list, n=3):
    """按用户意图重排结果：比如「最便宜」就按价格升序排"""
    q = question
    if ("最便宜" in q) or ("最低" in q) or ("最实惠" in q):
        results_list.sort(key=lambda x: x[0]["price"])
    elif ("最贵" in q) or ("最高" in q) or ("顶级" in q):
        results_list.sort(key=lambda x: x[0]["price"], reverse=True)
    return results_list[:n]


# ============================================================
# 改动 1：导入 LangChain 组件
# ============================================================



# ============================================================
# 改动 2：把自定义智谱嵌入类包装成 LangChain 接口
# ============================================================
class LangChainCompatibleEmbedding(Embeddings):
    """
    LangChain 要求嵌入类必须实现：
      - embed_documents(self, texts) -> list[list[float]]
      - embed_query(self, text) -> list[float]
    所以我们套一层壳，内部还是调用你写的 BigModelEmbeddingFunction
    """
    def __init__(self):
        self._inner = BigModelEmbeddingFunction(dimensions=512)

    def embed_documents(self, texts):
        """嵌入文档列表：给 LangChain Chroma 存数据用"""
        return self._inner(texts)

    def embed_query(self, text):
        """嵌入单个查询：给 LangChain Retriever 搜素用"""
        result = self._inner([text])
        return result[0] if result else []


# ============================================================
# 改动 3：用 LangChain 组件初始化大模型和 Prompt
# ============================================================
def get_llm():
    """原生版：from openai import OpenAI → 创建 client.chat.completions.create()
    LangChain版：直接创建 ChatDeepSeek 实例，invoke() 即可调用"""
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    llm = ChatDeepSeek(
        model="deepseek-chat",
        api_key=api_key,
        base_url=base_url,
        temperature=0.1,
    )
    print(f"✅ LangChain LLM：{base_url} / deepseek-chat")
    return llm

def get_intent_prompt_template():
    """意图分类场景的 Prompt 模板"""
    template = """你是「小购」，一个友好、专业的电商平台AI客服。
    你的任务是根据用户的问题，判断用户意图是购物类还是非购物类。
【核心规则（必须严格遵守！）】
1. **购物类**：用户问题与商品相关，例如"我想买一个手机"、"我需要一个电脑"等。
2. **日常聊天类**：用户只想与你正常聊天，例如"今天天气怎么样"、"你好呀"等。 
3. **售后类**：用户问题与售后相关，例如"我想退一个商品"、"我想换一个商品"等。
4. **恶意类**：用户问题包含恶意内容，例如"傻逼"、"垃圾"、"滚"、"废物"、"脑残"、"去死"、"操"、"草"等。
5.严格按照以上分类，不能有其他分类，不要自己编造。
   【用户问题】
   {question}
   【历史记录】
   {history_text}
   【输出格式参考】
   恶意类："abuse"
   购物类："product"
   售后类："service"
   日常聊天类："chat"
   你必须且只能输出以下字符串之一，不允许输出其他内容：abuse, product, service, chat 
      """
    return ChatPromptTemplate.from_template(template)


def get_intent_and_expand_prompt_template():
    """合并版：意图分类 + 搜索关键词提取，一次 LLM 调用完成两件事"""
    template = """你是「小购」电商平台的AI客服助手。请同时完成两项任务：

【任务1：意图分类】
判断用户意图，必须是以下之一：
- product：用户想搜索、推荐或咨询商品，但尚未进入具体下单确认
- purchase：用户明确要购买某个商品、要确认某个商品能否按指定数量下单，或正在补充待确认订单的收货信息
- chat：日常闲聊（问候、常识问答、讲笑话等）
- service：售后问题（订单、物流、退换货等）
- abuse：恶意内容（辱骂等）

【任务2：话题关系判断】（仅当意图为 product 时需要）
- continue：用户在延续刚才同一种商品或同一组条件，例如“再便宜一点”“要轻薄的”
- new：用户明确开始另一种商品需求，例如前面聊笔记本，现在问“想买拍照手机”
- purchase、chat、service、abuse 必须填写 none

【任务3：搜索关键词提取】（仅当意图为 product 时需要）
从对话上下文和当前问题中，提取用于商品搜索的核心关键词。
规则：
- 如果用户在追问之前的话题（如"有便宜的吗"），结合上下文补全关键词
- 如果用户开启了新话题，只提取当前问题的关键词，忽略历史
- 输出3-8个核心关键词，用空格分隔

【对话历史】
{history_text}

【用户当前问题】
{question}

【输出格式】
严格按以下格式输出，一行搞定：
<意图>|<话题关系>|<搜索关键词>

示例：
product|continue|笔记本 低价
product|new|手机 拍照
purchase|none|
chat|none|
service|none|
abuse|none|

现在请输出："""
    return ChatPromptTemplate.from_template(template)




def get_chat_prompt_template():
    """商品咨询场景的 Prompt 模板（V1：加上下文记忆版）"""
    template = """你是「小购」，一个友好、专业的电商平台AI客服。

【核心规则（必须严格遵守！）】
1. **诚实第一**：只能从【可推荐商品】中挑选推荐，绝对不可以编造不存在的商品。
2. **不强行推荐**：如果【可推荐商品】和用户问题不相关，直接说"抱歉，我们暂时没有这类商品哦~"，
   不要硬把不相关的商品塞给用户。
3. **不编造信息**：商品的价格、库存、分类以【可推荐商品】里写的为准，不要自己编。
4. **有货优先**：如果有多个推荐，优先推荐库存 > 0 的商品。
5. **记住上下文**：参考【历史对话】理解用户现在的问题，比如用户说"太贵了"，
   要结合刚才推荐的商品理解，不要让用户重复说一遍。
6. **卡片一致性**：最多推荐 3 款；只写入你实际推荐的商品，并保留【可推荐商品】中完全一致的商品名和排序。不要提到未推荐商品。
7. **简洁明了**：回答 3-5 句话，不要长篇大论。

【历史对话】
{history_text}

【可推荐商品】
{products_text}

【用户当前问题】
{question}

【输出格式参考】
如果有相关商品：
  "为您推荐以下几款商品哦：
   1. 【商品名】，价格 xxx 元，有货/缺货，简要说明为什么推荐
   2. ...
   还需要我帮您筛选其他条件吗~"

如果没有相关商品：
  "抱歉，我们暂时没有这类商品哦~ 您可以看看我们的手机数码、电脑办公、食品生鲜等热门品类~"

现在请回答：
"""
    return ChatPromptTemplate.from_template(template)


def get_chat_prompt_template_chat():
    """闲聊场景的 Prompt 模板（V1：加上下文记忆版）"""
    template = """你是「小购」，一个活泼、友好的电商平台AI客服。

你的任务：
  1. 用户问非购物类的问题，先简短准确地回答
  2. 回答完后，**用一句话把话题引导回购物**
  3. 记住上下文：参考【历史对话】理解用户现在的问题
  4. 回答要自然，不要生硬，1-2句话就好

【历史对话】
{history_text}

【用户当前问题】
{question}

【示例回答参考】
问：1+1等于几？
答：1+1=2哦~ 对啦，您有什么想买的商品吗？我可以帮您推荐~

问：今天天气怎么样？
答：我没法查询实时天气呢~ 对啦，您要买什么？我帮您看看有没有优惠~

问：讲个笑话
答：好呀~ 为什么程序员分不清万圣节和圣诞节？因为 Oct 31 = Dec 25~ 您要买点什么吗？

现在请回答：
"""
    return ChatPromptTemplate.from_template(template)


# ============================================================
# 改动 4：用 LangChain Chroma 连接 VectorStore + Retriever
# ============================================================
def get_vectorstore():
    """原生版：chromadb.PersistentClient() + get_collection()
    LangChain版：LangChain 封装的 Chroma(...)，返回 VectorStore
    好处：可以直接 .as_retriever() 拿到检索器，和 Chain 无缝衔接"""
    persist_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
    embedding = LangChainCompatibleEmbedding()
    vectorstore = LCChroma(
        collection_name="shopping",
        persist_directory=persist_dir,
        embedding_function=embedding,
    )
    print(f"✅ LangChain VectorStore：共 {len(vectorstore.get()['ids'])} 条商品")
    return vectorstore


# ============================================================
# 工具函数：格式化检索结果（RAG 里叫 format_docs）
# ============================================================
def format_search_results(results_with_dist):
    """把 [(meta, dist), ...] 格式化成 Prompt 里需要的文本"""
    products_text = ""
    for i, (meta, dist) in enumerate(results_with_dist, 1):
        stock_text = "有货" if meta["stock"] > 0 else "缺货"
        products_text += f"""
【商品 {i}】
  商品编号：PR{meta['product_id']}
  名称：{meta['product_name']}
  分类：{meta['category']}
  价格：{meta['price']}元
  库存状态：{stock_text}（剩余{meta['stock']}件）
  内部相似度：{dist:.4f}
"""
    return products_text


# ============================================================
# 意图分类（保持不变，关键词法简单好用，不必强行用 LangChain）
# ============================================================
def classify_intent_by_llm(question, llm,history_text):
    """用 LLM 模型分类用户意图"""
    prompt = get_intent_prompt_template()
    response = llm.invoke(prompt.format(question=question, history_text=history_text))
    record_llm_token_usage(response, "intent_classification")
    return response.content.strip().lower()


def classify_intent_and_expand(question, llm, history_text):
    """
    合并版：一次 LLM 调用同时完成意图分类 + 搜索关键词提取
    返回: (intent, topic_mode, search_keywords)
      - intent: "product" | "purchase" | "chat" | "service" | "abuse"
      - topic_mode: product 时为 "continue"（延续）或 "new"（新话题）
      - search_keywords: 搜索关键词字符串（仅 product 意图有值）
    """
    prompt = get_intent_and_expand_prompt_template()
    response = llm.invoke(prompt.format(question=question, history_text=history_text))
    record_llm_token_usage(response, "intent_classification")
    raw = response.content.strip()
    
    # 新格式："product|continue|笔记本 低价"。
    # 同时兼容旧模型可能返回的 "product|笔记本 低价"。
    parts = raw.split("|", 2)
    if len(parts) == 3:
        intent = parts[0].strip().lower()
        topic_mode = parts[1].strip().lower()
        keywords = parts[2].strip()
    elif len(parts) == 2:
        intent = parts[0].strip().lower()
        topic_mode = "continue" if intent == "product" else "none"
        keywords = parts[1].strip()
    else:
        # 兼容更旧格式：只有意图没有关键词。
        intent = raw.lower()
        topic_mode = "continue" if intent == "product" else "none"
        keywords = ""
    
    # 确保意图是有效值
    valid_intents = {"product", "purchase", "chat", "service", "abuse"}
    if intent not in valid_intents:
        intent = "chat"

    if intent != "product":
        topic_mode = "none"
    elif topic_mode not in {"continue", "new"}:
        # 模型未按格式回答时，选择保守的“延续”，避免意外丢失用户条件。
        topic_mode = "continue"
    
    return intent, topic_mode, keywords


# def classify_intent_by_keywords(question):
    q = question
    abuse_words = ["傻逼", "垃圾", "滚", "废物", "脑残", "去死", "操", "草"]
    for w in abuse_words:
        if w in q:
            return "abuse"
    service_keywords = ["订单", "下单", "付款", "支付", "发货", "物流", "快递",
        "退货", "退款", "换货", "售后", "发票"]
    for kw in service_keywords:
        if kw in q:
            return "service"
    product_keywords = ["商品", "产品", "卖", "买", "有", "推荐", "介绍",
        "手机", "电脑", "笔记本", "衣服", "鞋", "水果", "食品", "零食",
        "美妆", "护肤", "宠物", "汽车", "家电", "电器", "图书", "文具",
        "价格", "多少钱", "便宜", "贵", "性价比", "优惠", "库存", "有货",
        "品牌", "什么牌子", "哪款", "哪个好", "怎么样", "质量"]
    product_hit = sum(1 for kw in product_keywords if kw in q)
    if product_hit >= 1:
        return "product"
    return "chat"


# ============================================================
# 查询扩展（大模型版）：理解对话上下文，提取精准搜索关键词
# ============================================================
def _expand_query_by_llm(question, history_text, llm):
    """
    用大模型做查询扩展：理解完整对话上下文，提取核心搜索关键词

    相比硬编码关键词规则的巨大优势：
      - 能理解"平板电脑"这种不在规则里的新品类词
      - 能从上下文推断用户真正要搜什么（如"有便宜的吗" → "手机 便宜 低价"）
      - 不会被历史中无关话题带偏（大模型能判断用户是否开启了新话题）
      - 用户开启新话题时，自动忽略历史，只聚焦当前问题
    """
    expand_prompt = ChatPromptTemplate.from_template("""你是电商搜索助手。根据对话上下文和用户当前问题，提取用于商品搜索的核心关键词。

【规则】
1. 只提取与商品搜索直接相关的关键词（品类、属性、价格倾向、品牌等）
2. 如果用户在追问之前的话题（如"有便宜的吗"），要结合上下文补全关键词
3. 如果用户开启了新话题（话题明显变了），只提取当前问题的关键词，忽略历史
4. 输出3-8个核心关键词，用空格分隔
5. 只输出关键词，不要任何解释、标点或换行

【对话历史】
{history_text}

【用户当前问题】
{question}

搜索关键词：""")

    try:
        response = llm.invoke(expand_prompt.format(
            question=question,
            history_text=history_text if history_text else "（无历史对话）"
        ))
        record_llm_token_usage(response, "query_expansion")
        keywords = response.content.strip()
        expanded = f"{question} {keywords}"
        print(f"  🔧 大模型查询扩展：{expanded}")
        return expanded
    except Exception as e:
        print(f"  ⚠️  大模型查询扩展失败，回退到原问题：{e}")
        return question


# ============================================================
# 改动 5：用 LangChain LCEL 实现商品 RAG Chain（核心！）
# ============================================================
def build_product_chain(vectorstore, llm):
    """
    原生版：product_rag_channel() 里用 if-else 一步步写流程
    LangChain版：用 LCEL 语法 (| 运算符) 把步骤串成 Chain
    
    LCEL 语法：A | B 表示 A 的输出作为 B 的输入，依次执行
    """
    prompt = get_chat_prompt_template()

    # ---------- 第一步：自定义检索 + 三层过滤 ----------
    # RunnableLambda：把普通 Python 函数包装成 LangChain Runnable
    def custom_search_and_filter(input_dict):
        question = input_dict["question"]
        history_text = input_dict.get("history_text", "")
        search_keywords = input_dict.get("search_keywords", "")

        # 优先使用上游传来的预计算关键词（来自合并版意图分类），省一次 LLM 调用
        if search_keywords:
            expanded_q = f"{question} {search_keywords}"
            print(f"  🔧 查询扩展（复用上游）：{expanded_q}")
        else:
            # 兜底：独立调用大模型做查询扩展
            expanded_q = _expand_query_by_llm(question, history_text, llm)

        # 原生检索（保持你熟悉的 Chroma 用法）
        collection = vectorstore._collection
        # 修复：手动用 LangChain 保存的嵌入函数，把查询文本转成向量
        # 原因：_collection 是 LangChain 内部的裸对象，本身没绑定 embedding_function
        #       所以不能直接传 query_texts，必须先手动算好向量再传 query_embeddings
        query_embedding = vectorstore._embedding_function.embed_query(expanded_q)
        results = collection.query(query_embeddings=[query_embedding], n_results=10)
        candidates = list(zip(results["metadatas"][0], results["distances"][0]))
        print(f"  📊 粗筛出 {len(candidates)} 条候选")

        # 第一层：阈值过滤
        # 知识点：不同的嵌入模型，向量距离范围不同
        #   text2vec-base-chinese（本地模型）：余弦距离，0~2，1.2 是合理阈值
        #   智谱 embedding-3（API）：L2 距离，范围更大，需要放宽阈值
        THRESHOLD = 2.5
        print(f"  📏 候选距离：{[round(d, 4) for _, d in candidates]}")
        filtered = [(m, d) for (m, d) in candidates if d <= THRESHOLD]
        print(f"  🎯 阈值过滤（<={THRESHOLD}）：剩 {len(filtered)} 条")
        if len(filtered) == 0:
            return {"question": question, "products": [], "products_text": ""}

        # 意图重排
        # 商品文字和卡片最多展示 3 件，避免候选过多造成用户选择困难。
        ranked = _rerank_by_intent(question, filtered, n=3)
        print(f"  📈 意图重排后：取 {len(ranked)} 条")

        # 第二层：关键词校验
        # if not keyword_check(question, ranked):
        #     print(f"  ⚠️  关键词校验未通过 → 返回空")
        #     return {"question": question, "products": [], "products_text": ""}

        products_text = format_search_results(ranked)
        return {"question": question, "products": ranked, "products_text": products_text}

    search_step = RunnableLambda(custom_search_and_filter)

    # ---------- 第二步：如果 products 为空，直接返回默认回答，不走 LLM ----------
    def decide_skip_llm(input_dict):
        if not input_dict.get("products"):
            return "抱歉，我们暂时没有这类商品哦~ 可以看看我们的手机数码、电脑办公、食品生鲜等热门品类~"
        return None  # 返回 None 表示继续走 LLM

    skip_step = RunnableLambda(decide_skip_llm)

    # ---------- 第三步：把 products_text、question、history_text 传给 Prompt ----------
    def prepare_prompt_inputs(input_dict):
        if isinstance(input_dict, str):
            return input_dict  # 如果上一步直接返回了默认回答，直接透传
        return {
            "question": input_dict["question"],
            "products_text": input_dict["products_text"],
            "history_text": input_dict.get("history_text", "（无历史对话）"),
        }

    prepare_step = RunnableLambda(prepare_prompt_inputs)

    # ---------- 第四步：正常 LLM 生成回答 ----------
    output_parser = StrOutputParser()

    # ---------- 组装 Chain（LCEL 的 | 语法）----------
    # 原生写法：按顺序写 4 个函数
    # LangChain写法：把 4 个步骤用 | 连起来，像管道一样依次执行
    def _full_chain(input_dict):
        # Step 1：检索 + 过滤
        search_result = search_step.invoke(input_dict)
        # 新增：把上层传下来的 history_text 透传到下一步
        if "history_text" in input_dict:
            search_result["history_text"] = input_dict["history_text"]
        # Step 2：判断要不要跳过 LLM
        skip_answer = skip_step.invoke(search_result)
        if skip_answer is not None:
            # 保留结构化结果，供 API 返回给前端绘制商品卡片。
            return {"answer": skip_answer, "products": []}
        # Step 3：准备 Prompt 输入
        prompt_inputs = prepare_step.invoke(search_result)
        # Step 4：Prompt → LLM → 解析文本
        prompt_value = prompt.invoke(prompt_inputs)
        llm_result = llm.invoke(prompt_value)
        record_llm_token_usage(llm_result, "product_answer")
        answer = output_parser.invoke(llm_result)
        # products 是 Chroma 检索并排好序的商品身份证，不能只留下文字回答。
        return {"answer": answer, "products": search_result["products"]}

    return RunnableLambda(_full_chain)


# ============================================================
# 改动 6：用 LangChain LCEL 实现闲聊 Chain
# ============================================================
def build_chat_chain(llm):
    """闲聊场景 Chain（V1：加上下文记忆版）"""
    prompt = get_chat_prompt_template_chat()
    output_parser = StrOutputParser()

    def _chat_with_memory(input_dict):
        """内部包装：接收 history_text 和 question，生成回答"""
        prompt_value = prompt.invoke({
            "question": input_dict["question"],
            "history_text": input_dict.get("history_text", "（无历史对话）"),
        })
        llm_result = llm.invoke(prompt_value)
        record_llm_token_usage(llm_result, "chat_answer")
        return output_parser.invoke(llm_result)

    return RunnableLambda(_chat_with_memory)


# ============================================================
# 通道函数（V1：增加 history_text 参数）
# ============================================================
def abuse_channel(question):
    """处理辱骂等不适合继续回答的输入，返回固定且礼貌的拒绝文案。"""
    print("  ⚠️  通道：恶意问题 → 礼貌拒绝")
    answer = "请您文明用语哦~ 我是您的购物助手小购，有任何购物相关的问题，我都会尽力帮您解决的~"
    print(f"  🤖 AI：{answer}")
    return answer

def service_channel(question):
    """处理订单、物流、退换货等售后问题；当前为等待后续接入的占位回复。"""
    print("  📞 通道：订单/售后（预留接口）")
    answer = "订单/售后功能正在完善中~ 您可以在网站的「个人中心-我的订单」里查看订单状态和物流信息哦~"
    print(f"  🤖 AI：{answer}")
    return answer

def chat_channel(chat_chain, question, history_text=""):
    """执行闲聊链：将最近对话和当前问题交给 DeepSeek 生成简短客服回复。"""
    print("  💬 通道：闲聊/常识（LangChain Chat Chain）")
    print(f"  🧠 交给 DeepSeek 大模型闲聊回答...（含历史记忆）")
    answer = chat_chain.invoke({
        "question": question,
        "history_text": history_text,
    }).strip()
    print(f"  🤖 AI：{answer}")
    return answer

def _load_current_recommended_products(results_with_dist) -> list[dict]:
    """按 RAG 排序，从 MySQL 读取当前仍上架且有库存的商品卡片数据。"""
    product_ids = []
    for metadata, _distance in results_with_dist:
        try:
            product_id = int(metadata["product_id"])
        except (KeyError, TypeError, ValueError):
            continue
        if product_id not in product_ids:
            product_ids.append(product_id)

    if not product_ids:
        return []

    from app.models.product import Product

    db = _get_db_session()
    try:
        rows = db.query(Product).filter(
            Product.id.in_(product_ids), Product.status == 1, Product.stock > 0
        ).all()
        products_by_id = {row.id: row for row in rows}
        return [
            {
                "id": row.id,
                "product_code": row.product_code,
                "name": row.name,
                "price": float(row.price),
                "stock": row.stock,
                "image_url": row.image_url or "",
            }
            for product_id in product_ids
            if (row := products_by_id.get(product_id)) is not None
        ]
    finally:
        db.close()


def align_recommended_products_to_answer(answer: str, candidates: list[dict]) -> list[dict]:
    """只保留回答中实际提到的商品，并按商品名在回答中出现的顺序排列卡片。"""
    if not isinstance(answer, str):
        return []

    mentioned = []
    for original_index, product in enumerate(candidates):
        name = product.get("name")
        if not isinstance(name, str) or not name:
            continue
        position = answer.find(name)
        if position >= 0:
            mentioned.append((position, original_index, product))

    # position 让卡片跟随文字顺序；original_index 是同位置时保持 RAG 排名的稳定兜底。
    mentioned.sort(key=lambda item: (item[0], item[1]))
    return [product for _position, _index, product in mentioned[:3]]


def product_channel(product_chain, question, history_text="", search_keywords=""):
    """执行商品 RAG 链，并将向量检索结果重新从 MySQL 读取为可展示的商品卡片。"""
    print("  📦 通道：商品咨询（LangChain RAG Chain）")
    if search_keywords:
        print(f"  🔧 复用意图分类阶段的关键词：{search_keywords}")
    print(f"  🧠 交给 RAG Chain 处理...（含历史记忆）")
    chain_result = product_chain.invoke({
        "question": question,
        "history_text": history_text,
        "search_keywords": search_keywords,
    })
    answer = chain_result["answer"]
    if hasattr(answer, "strip"):
        answer = answer.strip()
    print(f"  🤖 AI：{answer}")
    cards = _load_current_recommended_products(chain_result.get("products", []))
    return {
        "answer": answer,
        # 卡片不能比回答文字多，也不能按另一套 RAG 顺序展示。
        "recommended_products": align_recommended_products_to_answer(answer, cards),
    }


# ============================================================
# AI 客服总入口（V1：加上下文记忆版）
# ============================================================
def ai_customer_service(vectorstore, llm, chat_chain, product_chain, question, history):
    """
    AI 客服总入口
    参数新增：
      history → 历史对话列表，由调用方传入和维护（list 是可变对象，直接 append 就行）
    """
    print("\n" + "=" * 60)
    print(f"🙋 用户：{question}")
    print("-" * 60)

    # Step 1：把历史对话格式化成 Prompt 能用的文本
    history_text = format_memory_for_prompt(history)

    # Step 2：意图识别（注意：意图识别本身不需要记忆，防止被历史带偏）
    intent = classify_intent_by_llm(question, llm,history_text)
    intent_map = {"chat": "闲聊/常识", "product": "商品咨询",
                  "service": "订单/售后", "abuse": "恶意问题"}
    print(f"🧭 意图识别：{intent_map.get(intent, '未知')}（{intent}）")

    # Step 3：根据意图走通道，把 history_text 传进去
    if intent == "abuse":
        answer = abuse_channel(question)
    elif intent == "chat":
        answer = chat_channel(chat_chain, question, history_text)
    elif intent == "service":
        answer = service_channel(question)
    elif intent == "product":
        answer = product_channel(product_chain, question, history_text)["answer"]
    else:
        answer = "抱歉，我没理解您的意思，可以再说一遍吗？"

    # Step 4：本轮对话结束，追加到记忆列表
    # 知识点：list 是可变对象，直接 append 就会改变调用方传进来的原对象
    history.append({"role": "user", "content": question, "time": datetime.now().isoformat(timespec="seconds")})
    history.append({"role": "ai", "content": answer, "time": datetime.now().isoformat(timespec="seconds")})

    # Step 5：保存到文件（每次都保存，防止中途崩溃丢失）
    save_memory(history)

    return answer


# ============================================================
# 第四部分：LangGraph 多 Agent 工作流（原 langgraph_agent.py）
# ============================================================
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
    topic_mode:str    # product 时是 continue（延续）或 new（新话题）
    search_keyword:str # 搜索关键词
    answer:str        # 回答文本
    recommended_products:list[dict]  # 前端商品卡片使用的实时商品数据
    # add_messages 规定：节点返回的新消息要追加到已有消息，而不是把旧消息覆盖掉。
    messages: Annotated[list, add_messages]
    # 仅由后端写入，ToolNode 会注入给需要保存会话草稿的工具；模型不能自行指定它们。
    user_id: int | None
    session_id: str | None


# ---------- 节点 1：意图分类 ----------
def classify_intent_node(state:AgentState)->dict:
    """LangGraph 首节点：一次模型调用同时得到意图、话题关系和商品检索关键词。"""
    intent, topic_mode, search_keywords = classify_intent_and_expand(
        state["question"], _llm, state["history_text"]
    )
    print(f"意图分类结果：{intent}, 话题关系：{topic_mode}, 搜索关键词：{search_keywords}")
    update = {"intent": intent, "topic_mode": topic_mode, "search_keyword": search_keywords}
    if topic_mode == "new":
        # 分类仍看过旧记忆来判断“是否换题”，但推荐回答不能再带旧条件。
        update["history_text"] = remove_structured_memory_from_context(state["history_text"])
    return update

# ---------- 节点 2：商品推荐（RAG）----------
def product_node(state:AgentState)->dict:
    """LangGraph 商品节点：运行 RAG 推荐并返回自然语言答案和商品卡片。"""
    result = product_channel(
        _product_chain,
        state["question"],
        state["history_text"],
        state["search_keyword"],
    )
    print(f"商品推荐结果：{result['answer']}")
    return result


# ---------- 节点 3：购买前的 ReAct 决策 ----------
ORDER_AGENT_SYSTEM_PROMPT = """你是电商下单助手。你可以使用工具查询实时商品状态。

规则：
1. 你必须结合用户本轮消息和最近对话，自主判断该调用哪个工具；不要让 Python 规则替你判断购买意图。
2. 商品编号的公开格式为 PR 加数字，例如 PR500 对应内部 product_id=500。调用工具时，product_id 填编号中的数字部分 500。
3. 当你理解用户明确要“买/购买/下单”，且已能确定商品编号和数量时，直接调用 start_order_draft。该工具会重新校验实时库存；绝不能先查库存后再问“是否确定购买”。数量未说时按 1 件处理。
4. 用户只问“库存/价格/能不能买”，且没有明确要下单时，调用 check_product_for_order；数量未说时按 1 件查询。
5. start_order_draft 成功后，直接告知已选商品和数量，并询问缺少的收货信息；不要重复确认用户是否要买。
6. 用户在已有待确认订单时提供姓名、电话、地址或备注，调用 fill_order_draft_receiver；只传入用户本轮明确说出的字段。
7. 工具提示资料齐全后，向用户展示商品、数量和草稿金额，并请用户明确回复“确认提交”；不要自动创建订单。
8. 只有当前草稿资料齐全、且用户本轮明确说“确认提交”或同等确认语时，才调用 confirm_order_draft。工具成功后告知订单号和“待支付”，不要说已支付。
9. 绝不因为“我想买”“可以下单吗”或“资料填好了”调用 confirm_order_draft。
10. 如果没有商品编号，礼貌请用户打开商品详情页，查看“商品编号（例如 PR500）”后告诉你；不要调用工具。
"""


def purchase_node(state: AgentState) -> dict:
    """ReAct 的思考节点：每一轮都由模型决定回答或请求调用哪个白名单工具。"""
    order_llm = _llm.bind_tools(ORDER_AGENT_TOOLS)
    system_message = SystemMessage(
        content=f"{ORDER_AGENT_SYSTEM_PROMPT}\n【最近对话】\n{state['history_text'] or '（无）'}"
    )
    response = order_llm.invoke([system_message, *state["messages"]])
    record_llm_token_usage(response, "purchase_agent")
    answer = response.content.strip() if isinstance(response.content, str) else ""
    return {"messages": [response], "answer": answer}


def route_purchase_after_model(state: AgentState) -> str:
    """模型给出 tool_calls 就去执行工具；否则它已直接回答，本轮结束。"""
    latest_message = state["messages"][-1]
    return "tools" if getattr(latest_message, "tool_calls", []) else "end"


# ---------- 节点 4：闲聊 ----------
def chat_node(state: AgentState) -> dict:
    """LangGraph 闲聊节点：不检索商品，直接调用闲聊 Chain。"""
    answer = chat_channel(_chat_chain, state["question"], state["history_text"])
    print(f"闲聊结果：{answer}")
    return {"answer": answer}


# ---------- 节点 5：售后 ----------
def service_node(state: AgentState) -> dict:
    """
    对应手写版：service_channel(question)
    """

    answer = service_channel(state["question"])
    print (f"售后结果：{answer}")
    return {"answer": answer}


# ---------- 节点 6：恶意拒绝 ----------
def abuse_node(state: AgentState) -> dict:
    """
    对应手写版：abuse_channel(question)
    """

    answer = abuse_channel(state["question"])
    print (f"恶意拒绝结果：{answer}")
    return {"answer": answer}

# ---------- 节点 7：路由 ----------
def route_by_intent(state: AgentState) -> str:
    """读取分类节点的 intent 字段，返回 LangGraph 中下一站节点的名字。"""
    intent = state.get("intent", "product")
    return intent  # 返回 product / purchase / chat / service / abuse


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
    workflow.add_node("purchase_node", purchase_node)
    workflow.add_node("purchase_tools", ToolNode(ORDER_AGENT_TOOLS))
    workflow.add_node("chat_node", chat_node)
    workflow.add_node("service_node", service_node)
    workflow.add_node("abuse_node", abuse_node)

    # 3. 设置入口节点（图从哪个节点开始执行）
    workflow.set_entry_point("classify_intent_node")
    # 4. 添加条件边：从 classify_intent 出发，根据意图路由到不同节点
    workflow.add_conditional_edges(
        "classify_intent_node",   # 从哪个节点出发
        route_by_intent,          # 路由函数：返回下一个节点名
        {
            "product": "product_node",
            "purchase": "purchase_node",
            "chat": "chat_node",
            "service": "service_node",
            "abuse": "abuse_node",
        }
    )
    # 5. 所有通道节点执行完后，结束
    workflow.add_edge("product_node", END)
    # purchase_node 先由模型决定是否要调用工具；工具执行完必须回到模型，
    # 让模型读取“观察结果”后再生成面向用户的回复。
    workflow.add_conditional_edges(
        "purchase_node",
        route_purchase_after_model,
        {"tools": "purchase_tools", "end": END},
    )
    workflow.add_edge("purchase_tools", "purchase_node")
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

    _llm = get_llm()
    _chat_chain = build_chat_chain(_llm)
    vectorstore = get_vectorstore()
    _product_chain = build_product_chain(vectorstore, _llm)

    _graph = build_graph()
    _initialized = True
    print("✅ LangGraph 工作流初始化完成")



def get_created_order_from_current_turn(messages: list) -> dict | None:
    """从本次 LangGraph 运行的工具回执中取订单摘要，不读取持久化会话记忆。"""
    for message in reversed(messages):
        if getattr(message, "name", None) != "confirm_order_draft":
            continue
        try:
            payload = json.loads(getattr(message, "content", ""))
        except (TypeError, json.JSONDecodeError):
            continue
        if payload.get("ok") and payload.get("code") == "ORDER_CREATED":
            order = payload.get("order")
            return order if isinstance(order, dict) else None
    return None


def run_agent(question: str, history_text: str = "", user_id: int = None, session_id: str = None) -> dict:
    """执行 Agent；每次仅把最近消息和会话级购物条件送入 Prompt。"""
    init_langgraph()
    sid = (session_id or generate_session_id()) if user_id else None
    memory = load_structured_memory(user_id, sid) if sid else {}
    initial_state: AgentState = {
        "question": question, "history_text": merge_memory_into_context(history_text, memory),
        "intent": "", "topic_mode": "", "search_keyword": "", "answer": "",
        "recommended_products": [],
        "messages": [HumanMessage(content=question)],
        "user_id": user_id,
        "session_id": sid,
    }
    result = _graph.invoke(initial_state)
    if user_id and sid:
        # ToolNode 可能刚保存了 pending_order；重新读取可避免用旧 memory 把它覆盖掉。
        latest_memory = load_structured_memory(user_id, sid)
        updated = update_structured_memory(
            latest_memory, question, result.get("intent", ""), result.get("search_keyword", ""),
            result.get("topic_mode", "continue"),
        )
        save_structured_memory(user_id, sid, updated)
        save_message_to_db(user_id, sid, "user", question, intent=result.get("intent", ""))
        save_message_to_db(user_id, sid, "ai", result["answer"], intent=result.get("intent", ""))
        result["session_id"] = sid
        # 不让模型复述电话、地址；由后端直接从当前会话记忆组装给前端。
        result["order_draft"] = build_order_draft_confirmation(updated)
        # 订单跳转卡片只属于“本轮刚执行确认工具”的通知，绝不从长期 memory_json 重复生成。
        result["created_order"] = get_created_order_from_current_turn(result.get("messages", []))
    return result
# ============================================================
# 第五部分：演示 + 聊天模式（方便本地测试）
# ============================================================
def run_demos(vectorstore, llm, chat_chain, product_chain, history):
    """命令行教学演示：按预设问题依次测试闲聊、RAG、售后和恶意输入。"""
    demos = [
        ("1+1等于几？", "闲聊测试（第1轮）"),
        ("对啦，我刚才问的是什么来着？", "记忆测试（第2轮，看能否想起第1轮）"),
        ("你们有什么便宜的手机？", "商品咨询（第3轮）"),
        ("太贵了，有更便宜的吗？", "上下文连贯测试（第4轮，看能否理解指刚才的手机）"),
        ("我的订单什么时候发货？", "订单售后测试"),
        ("你们卖的都是垃圾！", "恶意问题测试"),
    ]
    print("\n" + "=" * 60)
    print("  📝 合并版：6 个场景演示（含记忆测试）")
    print("=" * 60)
    for question, tag in demos:
        print(f"\n\n【演示：{tag}】")
        try:
            ai_customer_service(vectorstore, llm, chat_chain, product_chain, question, history)
        except Exception as e:
            print(f"  ❌ 出错：{e}")
            import traceback
            traceback.print_exc()


def run_chat_mode(vectorstore, llm, chat_chain, product_chain, history):
    """命令行交互模式：供本地手动输入问题，不参与 FastAPI 网站请求。"""
    print("\n" + "=" * 60)
    print("  💬 进入聊天模式（带上下文记忆 V1）")
    print("  使用说明：输入问题对话")
    print("    quit/q/exit → 退出")
    print("    clear       → 清空历史记忆（从头开始聊）")
    print("=" * 60)
    while True:
        try:
            print("\n" + "-" * 60)
            question = input("👤 你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n✅ 已退出聊天模式")
            break

        if question.lower() == "clear":
            history.clear()
            save_memory(history)
            print("🧹 历史记忆已清空！可以从头开始聊了~")
            continue

        if question.lower() in ("quit", "q", "exit", ""):
            print("✅ 已退出聊天模式")
            break
        try:
            ai_customer_service(vectorstore, llm, chat_chain, product_chain, question, history)
        except Exception as e:
            print(f"  ❌ 出错：{e}")
            import traceback
            traceback.print_exc()


def main():
    """直接运行 ai_core.py 时的教学入口：初始化组件、运行演示，再进入命令行聊天。"""
    print("\n" + "=" * 60)
    print("  🛒 合并版 AI 客服系统 + 记忆 V1 + LangGraph Agent")
    print("=" * 60)
    print("\n📡 正在初始化 LangChain 组件...")
    try:
        vectorstore = get_vectorstore()
        llm = get_llm()
        chat_chain = build_chat_chain(llm)
        product_chain = build_product_chain(vectorstore, llm)
        history = load_memory()
    except Exception as e:
        print(f"❌ 初始化失败：{e}")
        import traceback
        traceback.print_exc()
        return

    run_demos(vectorstore, llm, chat_chain, product_chain, history)

    print("\n" + "=" * 60)
    print("  🎉 演示完成！现在可以自己和 AI 客服聊天了~")
    print("  💡 提示：试试连续问「推荐个手机」→「太贵了」，看 AI 能不能理解上下文")
    print("=" * 60)
    run_chat_mode(vectorstore, llm, chat_chain, product_chain, history)

    print("\n" + "=" * 60)
    print("  ✅ 合并版完成！所有 AI 代码统一在 ai_core.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
