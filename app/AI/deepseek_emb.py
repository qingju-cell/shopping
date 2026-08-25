# ============================================================
# step3_save_to_chroma.py —— 阶段二第三步：把文档存入 Chroma 向量数据库
# 目的：创建知识库，让 AI 能检索
# ============================================================

import os
import sys


# ---------- 设置路径 ----------
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
from app.database import SessionLocal
from app.models.product import Product
from app.models.category import Category

# 加载 AI 目录下的 .env（DeepSeek API Key）
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(env_path)

import requests
import numpy as np
# ============================================================
# 本地嵌入函数（使用 sentence-transformers，不需要 API）
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
        self.api_key = "2e6028fcb89443bfa0218360e6e4114f.4E28yfEMMc42lMIY"
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
# 第 1 步：读取商品数据（和 step1/step2 相同）
# ============================================================
def load_products():
    db = SessionLocal()
    try:
        products = db.query(Product).filter(Product.status == 1).all()
        categories = db.query(Category).all()
        category_map = {c.id: c.name for c in categories}

        result = []
        for p in products:
            result.append({
                "id": p.id,
                "name": p.name,
                "description": p.description or "",
                "price": float(p.price),
                "stock": p.stock,
                "category_name": category_map.get(p.category_id, "未分类"),
                "image_url": p.image_url or "",
            })
        return result
    finally:
        db.close()

# ============================================================
# 第 2 步：把商品转换成文本 + 元数据（关键词增强版）
# ============================================================
def convert_to_documents(products):
    documents = []
    metadatas = []

    for p in products:
        # ✅ 关键词增强：分类名重复 2 次，提高分类匹配权重
        # ✅ 增加同义词：让 "笔记本电脑"/"电脑"/"计算机" 等能互相匹配
        category_keywords = p['category_name']
        # 分类同义词扩展，提高召回率
        # ⚠️ 注意：这里的 key 必须和数据库 Category 表中的 name 完全一致！
        synonym_map = {
            "手机数码": "手机数码 智能手机 数码产品 电子产品 移动设备 手机",
            "电脑办公": "电脑办公 笔记本电脑 台式机 电脑 计算机 办公设备 一体机 手提电脑",
            "办公用品": "办公用品 电脑 笔记本电脑 台式机 打印机 键盘 鼠标 一体机 办公设备 文具 高拍仪",
            "家用电器": "家用电器 家电 电器 大家电 生活电器",
            "服装鞋帽": "服装鞋帽 衣服 鞋子 帽子 服饰 穿戴",
            "美妆护肤": "美妆护肤 化妆品 护肤品 美容 彩妆 香水",
            "美妆个护": "美妆个护 化妆品 护肤品 美容 彩妆 香水 个人护理 洗护 面膜 口红 粉底",
            "汽车用品": "汽车用品 车载 车品 汽车配件 内饰 外饰 保养 机油 轮胎 行车记录仪",
            "宠物生活": "宠物生活 宠物 猫粮 狗粮 猫砂 狗窝 宠物用品 猫咪 狗狗 宠物食品",
            "食品生鲜": "食品生鲜 零食 吃的 喝的 饮料 水果 蔬菜 美食",
            "母婴玩具": "母婴玩具 婴儿 小孩 儿童 玩具 宝宝 奶粉 纸尿裤",
            "家居日用": "家居日用 家具 日用品 生活用品 家居 家装",
            "运动户外": "运动户外 运动健身 户外装备 体育用品 运动鞋 吉他 乐器",
            "图书文娱": "图书文娱 书 书籍 图书 文具 学习用品 教育",
        }
        extra_keywords = synonym_map.get(p['category_name'], "")
        if not extra_keywords:
            # 分类没在映射中，加个兜底警告
            print(f"⚠️  未识别到分类同义词映射: [{p['category_name']}]")
        price_level = "低价" if p['price'] < 100 else ("平价" if p['price'] < 1000 else ("中高端" if p['price'] < 5000 else "高端"))

        doc_text = f"""【商品名称】{p['name']}
【所属分类】{p['category_name']}。{category_keywords}类商品，{extra_keywords}
【价格信息】售价{p['price']}元人民币，{price_level}商品
【库存数量】现有库存{p['stock']}件
【商品描述】{p['description']}
【标签】{p['category_name']}，{price_level}"""

        documents.append(doc_text)
        metadatas.append({
            "product_id": p["id"],
            "product_name": p["name"],
            "price": p["price"],
            "stock": p["stock"],
            "category": p["category_name"],
            "image_url": p["image_url"],
        })

    return documents, metadatas

# ============================================================
# 第 3 步：创建 Chroma 向量数据库
# ============================================================
def create_chroma_db(documents, metadatas):
    """
        创建 Chroma 数据库并存入文档

        Chroma 会自动做三件事：
          1. 调用嵌入模型，把每段文本转成向量
          2. 把向量存入数据库
          3. 保存原文和元数据
    """
    import chromadb


    print("\n💾 第 3 步：创建向量数据库...")

    # 3.1 使用智谱 AI 嵌入模型
    embedding_func = BigModelEmbeddingFunction()
    print(f"使用 智谱AI 嵌入模型：{embedding_func.model}（维度：{embedding_func.dimensions}，支持中文语义搜索）")

    # 3.2 创建 Chroma 客户端
    # PersistentClient：数据保存到本地文件夹，重启后不丢失
    # 数据保存位置：app/AI/chroma_db/
    persist_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
    client = chromadb.PersistentClient(path=persist_dir)
    print(f"数据保存到：{persist_dir}")

    # 3.3 创建集合（集合 = 一组相关文档的容器）
    # 注意：Chroma 集合一旦创建，向量维度就固定了，不能修改
    # 所以如果旧集合维度不对，必须删除后重新创建
    try:
        # 先尝试删除旧集合（避免维度不匹配问题）
        client.delete_collection(name="shopping")
        print(f"🗑️  已删除旧集合（防止维度不匹配）")
    except Exception:
        # 集合不存在就忽略
        pass

    collection = client.create_collection(
        name="shopping",  # 集合名称
        embedding_function=embedding_func,   # 嵌入函数
    )
    print(f"集合名称：shopping（维度：{embedding_func.dimensions}）")

    # 3.5 生成文档 ID
    # 每个文档需要唯一 ID，用 "product_商品ID" 格式
    ids = [f"product_{p['product_id']}" for p in metadatas]

    # 3.6 存入数据
    # Chroma 会自动：文本 → 向量 → 存储
    print(f"   正在嵌入 {len(documents)} 条文档（本地运算，请稍候...）")
    collection.add(
        ids=ids,  # 文档 ID 列表
        documents=documents,  # 文本内容列表
        metadatas=metadatas,  # 元数据列表
    )

    count = collection.count()
    print(f"    存入 {count} 条文档")
    return collection

# ============================================================
# 第 4 步：测试检索效果（升级版：查询扩展 + 意图识别）
# ============================================================
def _expand_query(question):
    """✅ 查询词扩展：补充同义词，提高召回率（关键词去重版）"""
    # 扩展关键词表：命中任意一个就把整组词加进去
    expansion_rules = [
        (["手机", "苹果", "华为", "小米", "OPPO", "vivo", "智能手机"],
         "手机 智能手机 移动电话 苹果 华为 小米 OPPO vivo 数码产品 电子产品 手机数码"),
        (["电脑", "计算机", "笔记本", "笔记本电脑", "台式机", "一体机", "手提电脑", "办公", "打印机", "键盘"],
         "电脑 计算机 笔记本电脑 笔记本 台式机 一体机 手提电脑 办公用品 电脑办公 办公设备 打印机 键盘 鼠标"),
        (["便宜", "低价", "性价比", "实惠", "平价", "划算"],
         "便宜 低价 性价比 实惠 平价 划算"),
        (["最贵", "高端", "奢侈品", "顶配", "旗舰"],
         "最贵 高端 奢侈品 顶配 旗舰"),
        (["家电", "家用电器", "电器", "大家电", "生活电器"],
         "家电 家用电器 电器 大家电 生活电器"),
        (["衣服", "服装", "服饰", "服装鞋帽", "穿戴", "鞋子", "帽子"],
         "衣服 服装 服饰 服装鞋帽 穿戴 鞋子 帽子"),
        (["吉他", "乐器", "运动", "户外", "健身"],
         "吉他 乐器 运动 户外 健身 体育用品 运动户外"),
        (["美妆", "化妆", "护肤", "口红", "香水", "面膜", "个护", "洗护"],
         "美妆 美妆护肤 美妆个护 化妆品 护肤品 美容 彩妆 香水 个人护理 洗护 面膜 口红 粉底"),
        (["汽车", "车载", "车品", "行车记录仪", "机油", "轮胎"],
         "汽车 汽车用品 车载 车品 汽车配件 内饰 外饰 保养 机油 轮胎 行车记录仪"),
        (["宠物", "猫", "狗", "猫粮", "狗粮", "猫砂"],
         "宠物 宠物生活 猫粮 狗粮 猫砂 狗窝 宠物用品 猫咪 狗狗 宠物食品"),
    ]

    # 用 set 收集关键词，自动去重
    keyword_set = set()
    # 先把原问题拆成词加入
    keyword_set.add(question)

    # 命中规则就把扩展词加进去（但同一规则只加一次，避免重复）
    for keywords, expansion in expansion_rules:
        hit = any(kw in question for kw in keywords)
        if hit:
            for w in expansion.split():
                keyword_set.add(w)

    # 拼成去重后的查询文本
    expanded = " ".join(keyword_set)
    return expanded

def _rerank_by_intent(question, results_list, n=3):
    """✅ 按用户意图重排结果：比如「最便宜」就按价格升序排"""
    q = question
    metas = [m for m, _ in results_list]
    if ("最便宜" in q) or ("最低" in q) or ("最实惠" in q):
        # 按价格从低到高排序
        results_list.sort(key=lambda x: x[0]["price"])
    elif ("最贵" in q) or ("最高" in q) or ("最好" in q and "价格" in q):
        # 按价格从高到低排序
        results_list.sort(key=lambda x: x[0]["price"], reverse=True)
    return results_list[:n]

def test_search(collection):
    """
       用几个问题测试向量检索效果（升级版）

       - 查询扩展：补充同义词，让"笔记本电脑"能匹配"电脑办公"分类
       - 意图识别："最便宜/最贵"这类查询按价格重排
       - 归一化后距离：0 = 完全相同，< 1.0 = 非常相关，> 1.5 = 相关性弱
    """
    print("\n" + "=" * 60)
    print("  🔍 第 4 步：测试检索效果（升级版）")
    print("=" * 60)
    print("  📖 距离说明：归一化后 0 = 完全相同，< 1.0 = 强相关")
    print("=" * 60)

    test_questions = [
        "你们有什么手机？",
        "最便宜的商品是什么？",
        "有没有笔记本电脑？",
    ]

    for question in test_questions:
        print(f"\n📌 问题：「{question}」")
        expanded_q = _expand_query(question)
        if expanded_q != question:
            print(f"    🔧 查询扩展：{expanded_q}")
        print("-" * 40)

        # 先搜多一点候选（10条），再做重排
        results = collection.query(
            query_texts=[expanded_q],
            n_results=10,
        )

        if results["documents"] and results["documents"][0]:
            candidates = list(zip(
                results["metadatas"][0],
                results["distances"][0],
            ))
            # 按意图重排（如"最便宜"按价格排）
            ranked = _rerank_by_intent(question, candidates, n=3)

            for i, (meta, distance) in enumerate(ranked):
                tag = "⭐ 强相关" if distance < 1.0 else ("🤔 匹配中" if distance < 1.3 else "⚠️  相关性弱")
                print(f"\n  #{i + 1} {meta['product_name']}")
                print(f"     价格：{meta['price']}元 | 分类：{meta['category']}")
                print(f"     相似度距离：{distance:.4f}  {tag}")
        else:
            print("  没有找到相关内容")

    print("\n" + "=" * 60)

    # ============================================================
    # 主函数：整合所有步骤
    # ============================================================
def main():
        print("\n" + "=" * 60)
        print("  🛒 阶段二：构建购物系统知识库")
        print("=" * 60)

        # 第 1 步：读取数据
        print("\n📦 第 1 步：读取商品数据...")
        products = load_products()
        if not products:
            print("❌ 没有商品数据，请先添加商品")
            return
        print(f"   读取到 {len(products)} 个商品")

        # 第 2 步：转换文档
        print("\n📝 第 2 步：转换为知识库文档...")
        documents, metadatas = convert_to_documents(products)
        print(f"   生成 {len(documents)} 段文档")

        # 第 3 步：存入向量数据库
        collection = create_chroma_db(documents, metadatas)
        if not collection:
            return

        # 第 4 步：测试检索
        test_search(collection)

        print("\n✅ 阶段二完成！知识库已构建成功。")
        print("   下一步：进入阶段三，实现完整的语义检索")

if __name__ == "__main__":
    main()