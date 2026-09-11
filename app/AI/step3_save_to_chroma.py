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

# ============================================================
# 本地嵌入函数（使用 sentence-transformers，不需要 API）
# ============================================================
class LocalEmbeddingFunction:
    def __init__(self, model_name="shibing624/text2vec-base-chinese"):
        """
        本地嵌入模型，支持中文，无需联网调用 API
        第一次运行会自动下载模型（约 400MB），之后就离线可用
        """
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        if self._model is None:
            print(f"   📥 首次使用，正在加载嵌入模型：{self.model_name} ...")
            print("   🌐 使用国内镜像源（hf-mirror.com）加速下载...")
            os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

            from sentence_transformers import SentenceTransformer
            try:
                self._model = SentenceTransformer(self.model_name)
            except Exception as e:
                print(f"   ⚠️  从镜像下载失败：{e}")
                print("   🧲 尝试使用魔搭社区（ModelScope）模型...")
                self._model = self._load_from_modelscope()
            print("   ✅ 模型加载完成")

    def _load_from_modelscope(self):
        """备用方案：从 ModelScope（国内）加载模型"""
        try:
            from modelscope import AutoModel, AutoTokenizer
            import torch
            import numpy as np

            model_dir = "shibing624/text2vec-base-chinese"
            tokenizer = AutoTokenizer.from_pretrained(model_dir)
            model = AutoModel.from_pretrained(model_dir)
            model.eval()

            class ModelScopeWrapper:
                def __init__(self, model, tokenizer):
                    self.model = model
                    self.tokenizer = tokenizer

                def encode(self, sentences, convert_to_numpy=True):
                    encoded = self.tokenizer(
                        sentences, padding=True, truncation=True,
                        max_length=512, return_tensors="pt"
                    )
                    with torch.no_grad():
                        outputs = self.model(**encoded)
                        attention_mask = encoded["attention_mask"].unsqueeze(-1)
                        embeddings = (outputs.last_hidden_state * attention_mask).sum(1) / attention_mask.sum(1)
                        embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
                    if convert_to_numpy:
                        return embeddings.cpu().numpy()
                    return embeddings

            return ModelScopeWrapper(model, tokenizer)
        except ImportError:
            raise RuntimeError(
                "❌ 请先安装 modelscope：pip install modelscope\n"
                "   或者手动设置 HF_ENDPOINT=https://hf-mirror.com 环境变量"
            )

    def name(self):
        return "local_chinese_embedding"

    def __call__(self, input):
        self._load_model()
        embeddings = self._model.encode(
            input,
            convert_to_numpy=True,
            normalize_embeddings=True  # ✅ 向量归一化：相似度距离会降到 0~2 之间，更准确
        ).tolist()
        return embeddings

    def embed_documents(self, documents=None, input=None):
        """Chroma 要求：批量嵌入文档时调用，返回二维列表 [[向量1], [向量2], ...]"""
        texts = documents if documents is not None else input
        if isinstance(texts, str):
            texts = [texts]
        return self.__call__(texts)

    def embed_query(self, query=None, input=None):
        """Chroma 要求：查询时调用，统一返回二维列表 [[向量], ...]"""
        text = query if query is not None else input
        if isinstance(text, str):
            text = [text]
        return self.__call__(text)

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
        synonym_map = {
            "手机数码": "手机数码 智能手机 数码产品 电子产品 移动设备",
            "电脑办公": "电脑办公 笔记本电脑 台式机 电脑 计算机 办公设备 一体机",
            "家用电器": "家用电器 家电 电器 大家电 生活电器",
            "服装鞋帽": "服装鞋帽 衣服 鞋子 帽子 服饰 穿戴",
            "美妆护肤": "美妆护肤 化妆品 护肤品 美容 彩妆 香水",
            "食品生鲜": "食品生鲜 零食 吃的 喝的 饮料 水果 蔬菜 美食",
            "母婴玩具": "母婴玩具 婴儿 小孩 儿童 玩具 宝宝 奶粉 纸尿裤",
            "家居日用": "家居日用 家具 日用品 生活用品 家居 家装",
            "运动户外": "运动户外 运动健身 户外装备 体育用品 运动鞋",
            "图书文娱": "图书文娱 书 书籍 图书 文具 学习用品 教育",
        }
        extra_keywords = synonym_map.get(p['category_name'], "")
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

    # 3.1 使用智谱 AI 嵌入模型（和查询时保持一致，维度必须匹配！）
    from deepseek_emb import BigModelEmbeddingFunction
    # 写入和查询都必须使用同一嵌入模型、同一向量维度；ai_core.py 查询端是 512 维。
    # 维度不一致的向量不能比较距离，因此这里也固定为 512。
    embedding_func = BigModelEmbeddingFunction(dimensions=512)
    print(f"使用智谱AI嵌入模型：{embedding_func.model}（维度：{embedding_func.dimensions}）")

    # 3.2 创建 Chroma 客户端
    # PersistentClient：数据保存到本地文件夹，重启后不丢失
    # 数据保存位置：app/AI/chroma_db/
    persist_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
    client = chromadb.PersistentClient(path=persist_dir)
    print(f"数据保存到：{persist_dir}")

    # 3.3 创建集合（集合 = 一组相关文档的容器）
    # 注意：换了嵌入模型，必须删除旧集合重建，否则向量空间不兼容
    try:
        client.delete_collection(name="shopping")
        print(f"  🗑️  已删除旧集合（嵌入模型已更换，必须重建）")
    except Exception:
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
    print(f"   正在嵌入 {len(documents)} 条文档（调用智谱 API，请稍候...）")
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
    """✅ 查询词扩展：补充同义词，提高召回率"""
    expansions = {
        "手机": "手机 智能手机 移动电话 苹果 华为 小米 OPPO vivo",
        "电脑": "电脑 计算机 笔记本电脑 笔记本 台式机 一体机 手提电脑",
        "笔记本电脑": "笔记本电脑 笔记本 电脑 计算机 手提电脑 电脑办公",
        "便宜": "便宜 低价 性价比 实惠 平价 划算",
        "最贵": "最贵 高端 奢侈品 顶配 旗舰",
        "家电": "家电 家用电器 电器 大家电 生活电器",
        "衣服": "衣服 服装 服饰 服装鞋帽 穿戴",
    }
    expanded = question
    for kw, ex in expansions.items():
        if kw in question:
            expanded += " " + ex
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