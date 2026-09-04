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

import os
import sys
import json
from datetime import datetime
from typing import TypedDict

# ---------- 路径设置 ----------
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(env_path)

import requests
import numpy as np

# ---------- LangChain 组件 ----------
from langchain_deepseek import ChatDeepSeek
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough, RunnableLambda
from langchain_core.embeddings import Embeddings
from langchain_chroma import Chroma as LCChroma

# ---------- LangGraph ----------
from langgraph.graph import StateGraph, END


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
# 第三部分：LangChain RAG 全套（原 step5_rag_chatbot_langchain.py）
# ============================================================
# ============================================================
# 记忆功能 V1：JSON 文件保存（最简单的版本）
# ============================================================
def get_memory_file_path():
    """获取记忆文件的完整路径（和脚本同目录）"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_history.json")


def load_memory():
    """
    从 JSON 文件加载历史对话
    返回格式：
      [
        {"role": "user", "content": "你好"},
        {"role": "ai",  "content": "你好呀~"},
        ...
      ]
    """
    memory_file = get_memory_file_path()
    if not os.path.exists(memory_file):
        print(f"📝 没找到历史记忆文件，开始新对话（{os.path.basename(memory_file)}）")
        return []
    try:
        with open(memory_file, "r", encoding="utf-8") as f:
            history = json.load(f)
        print(f"💾 已加载历史记忆：{len(history)//2} 轮对话")
        return history
    except Exception as e:
        print(f"⚠️  记忆文件读取失败，忽略历史：{e}")
        return []


def save_memory(history):
    """把历史对话保存到 JSON 文件"""
    memory_file = get_memory_file_path()
    try:
        with open(memory_file, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        print(f"💾 记忆已保存：{len(history)//2} 轮 → {os.path.basename(memory_file)}")
    except Exception as e:
        print(f"⚠️  记忆保存失败：{e}")


# ---------- 数据库版：历史消息持久化 ----------
import uuid

def _get_db_session():
    """获取数据库会话（懒加载，避免文件被 import 时就连数据库）"""
    from app.database import SessionLocal
    return SessionLocal()


def save_message_to_db(user_id: int, session_id: str, role: str,
                       content: str, intent: str = ""):
    """保存单条消息到 ai_chat_messages 表"""
    try:
        from app.models.ai_chat_message import AIChatMessage
        db = _get_db_session()
        msg = AIChatMessage(
            user_id=user_id,
            session_id=session_id,
            role=role,
            content=content,
            intent=intent,
        )
        db.add(msg)
        db.commit()
        db.close()
    except Exception as e:
        print(f"⚠️  消息入库失败：{e}")


def load_history_from_db(user_id: int, session_id: str = None,
                         limit: int = 20) -> list:
    """
    从数据库加载历史消息，返回格式与 load_memory() 一致
    [{role: "user", content: "xxx", time: "..."}, ...]
    """
    try:
        from app.models.ai_chat_message import AIChatMessage
        db = _get_db_session()
        q = db.query(AIChatMessage).filter(AIChatMessage.user_id == user_id)
        if session_id:
            q = q.filter(AIChatMessage.session_id == session_id)
        messages = q.order_by(AIChatMessage.created_at.asc()).limit(limit).all()
        result = [{"role": m.role, "content": m.content,
                    "time": m.created_at.isoformat() if m.created_at else ""}
                  for m in messages]
        db.close()
        return result
    except Exception as e:
        print(f"⚠️  历史消息加载失败：{e}")
        return []


def generate_session_id() -> str:
    """生成唯一会话ID"""
    return uuid.uuid4().hex[:12]


def format_memory_for_prompt(history, max_turns=6):
    """
    把历史对话格式化成 Prompt 能直接用的文本
    max_turns=6 表示最多取最近 6 条消息 = 3 轮对话（user+ai）
    防止历史太长把 Prompt 撑爆
    """
    if not history:
        return "（无历史对话）"
    recent = history[-max_turns:]
    lines = []
    for msg in recent:
        role_name = "用户" if msg["role"] == "user" else "小购"
        lines.append(f"{role_name}：{msg['content']}")
    return "\n".join(lines)


def _extract_last_user_msg(history_text):
    """
    从格式化后的历史文本中提取所有历史用户消息（除最后一条当前问题）
    历史格式："用户：xxx\n小购：xxx\n用户：yyy\n小购：zzz"
    返回所有历史用户消息拼接的字符串，如 "xxx yyy"
    """
    lines = history_text.strip().split("\n")
    user_msgs = []
    for line in lines:
        if line.startswith("用户："):
            user_msgs.append(line[3:].strip())
    # 去掉最后一条（当前问题），其余全部拼上作为上下文
    if len(user_msgs) >= 2:
        return " ".join(user_msgs[:-1])
    return ""


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
- product：用户想搜索/购买/咨询商品
- chat：日常闲聊（问候、常识问答、讲笑话等）
- service：售后问题（订单、物流、退换货等）
- abuse：恶意内容（辱骂等）

【任务2：搜索关键词提取】（仅当意图为 product 时需要）
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
<意图>|<搜索关键词>

示例：
product|手机 便宜 性价比
chat|
service|
abuse|

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
6. **简洁明了**：回答 3-5 句话，不要长篇大论。

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
    return response.content.strip().lower()


def classify_intent_and_expand(question, llm, history_text):
    """
    合并版：一次 LLM 调用同时完成意图分类 + 搜索关键词提取
    返回: (intent, search_keywords)
      - intent: "product" | "chat" | "service" | "abuse"
      - search_keywords: 搜索关键词字符串（仅 product 意图有值）
    """
    prompt = get_intent_and_expand_prompt_template()
    response = llm.invoke(prompt.format(question=question, history_text=history_text))
    raw = response.content.strip()
    
    # 解析 "product|手机 便宜 性价比" 格式
    if "|" in raw:
        parts = raw.split("|", 1)
        intent = parts[0].strip().lower()
        keywords = parts[1].strip() if len(parts) > 1 else ""
    else:
        # 兼容旧格式：只有意图没有关键词
        intent = raw.lower()
        keywords = ""
    
    # 确保意图是有效值
    valid_intents = {"product", "chat", "service", "abuse"}
    if intent not in valid_intents:
        intent = "chat"
    
    return intent, keywords


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
        ranked = _rerank_by_intent(question, filtered, n=5)
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
            return skip_answer
        # Step 3：准备 Prompt 输入
        prompt_inputs = prepare_step.invoke(search_result)
        # Step 4：Prompt → LLM → 解析文本
        prompt_value = prompt.invoke(prompt_inputs)
        llm_result = llm.invoke(prompt_value)
        answer = output_parser.invoke(llm_result)
        return answer

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
        return output_parser.invoke(llm_result)

    return RunnableLambda(_chat_with_memory)


# ============================================================
# 通道函数（V1：增加 history_text 参数）
# ============================================================
def abuse_channel(question):
    print("  ⚠️  通道：恶意问题 → 礼貌拒绝")
    answer = "请您文明用语哦~ 我是您的购物助手小购，有任何购物相关的问题，我都会尽力帮您解决的~"
    print(f"  🤖 AI：{answer}")
    return answer

def service_channel(question):
    print("  📞 通道：订单/售后（预留接口）")
    answer = "订单/售后功能正在完善中~ 您可以在网站的「个人中心-我的订单」里查看订单状态和物流信息哦~"
    print(f"  🤖 AI：{answer}")
    return answer

def chat_channel(chat_chain, question, history_text=""):
    print("  💬 通道：闲聊/常识（LangChain Chat Chain）")
    print(f"  🧠 交给 DeepSeek 大模型闲聊回答...（含历史记忆）")
    answer = chat_chain.invoke({
        "question": question,
        "history_text": history_text,
    }).strip()
    print(f"  🤖 AI：{answer}")
    return answer

def product_channel(product_chain, question, history_text="", search_keywords=""):
    print("  📦 通道：商品咨询（LangChain RAG Chain）")
    if search_keywords:
        print(f"  🔧 复用意图分类阶段的关键词：{search_keywords}")
    print(f"  🧠 交给 RAG Chain 处理...（含历史记忆）")
    answer = product_chain.invoke({
        "question": question,
        "history_text": history_text,
        "search_keywords": search_keywords,
    })
    if hasattr(answer, "strip"):
        answer = answer.strip()
    print(f"  🤖 AI：{answer}")
    return answer


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
        answer = product_channel(product_chain, question, history_text)
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
    search_keyword:str # 搜索关键词
    answer:str        # 回答文本


# ---------- 节点 1：意图分类 ----------
def classify_intent_node(state:AgentState)->dict:
    intent, search_keywords = classify_intent_and_expand(
        state["question"], _llm, state["history_text"]
    )
    print(f"意图分类结果：{intent}, 搜索关键词：{search_keywords}")
    return {"intent": intent, "search_keyword": search_keywords}

# ---------- 节点 2：商品推荐（RAG）----------
def product_node(state:AgentState)->dict:
    answer = product_channel(
        _product_chain,
        state["question"],
        state["history_text"],
        state["search_keyword"],
    )
    print(f"商品推荐结果：{answer}")
    return {"answer": answer}


# ---------- 节点 3：闲聊 ----------
def chat_node(state: AgentState) -> dict:
    answer = chat_channel(_chat_chain, state["question"], state["history_text"])
    print(f"闲聊结果：{answer}")
    return {"answer": answer}


# ---------- 节点 4：售后 ----------
def service_node(state: AgentState) -> dict:
    """
    对应手写版：service_channel(question)
    """

    answer = service_channel(state["question"])
    print (f"售后结果：{answer}")
    return {"answer": answer}


# ---------- 节点 5：恶意拒绝 ----------
def abuse_node(state: AgentState) -> dict:
    """
    对应手写版：abuse_channel(question)
    """

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
    workflow.add_conditional_edges(
        "classify_intent_node",   # 从哪个节点出发
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

    _llm = get_llm()
    _chat_chain = build_chat_chain(_llm)
    vectorstore = get_vectorstore()
    _product_chain = build_product_chain(vectorstore, _llm)

    _graph = build_graph()
    _initialized = True
    print("✅ LangGraph 工作流初始化完成")



def run_agent(question: str, history_text: str = "",
              user_id: int = None, session_id: str = None) -> dict:
    """
    执行 LangGraph 工作流，返回最终 State

    参数：
        question:     用户问题
        history_text: 格式化后的历史对话文本
        user_id:      用户ID（传入则自动保存消息到数据库）
        session_id:   会话ID（传入则复用，否则自动生成新会话）

    返回格式：
        {"answer": "...", "intent": "..."}
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

    if user_id:
        sid = session_id or generate_session_id()
        save_message_to_db(user_id, sid, "user", question, intent=result.get("intent", ""))
        save_message_to_db(user_id, sid, "ai", result["answer"], intent=result.get("intent", ""))
        result["session_id"] = sid

    return result
# ============================================================
# 第五部分：演示 + 聊天模式（方便本地测试）
# ============================================================
def run_demos(vectorstore, llm, chat_chain, product_chain, history):
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