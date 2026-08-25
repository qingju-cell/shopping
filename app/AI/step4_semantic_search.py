# ============================================================
# step4_semantic_search.py —— 阶段三：语义检索实战
#
# 目标：掌握 5 种检索方式，把用户问题变成相关商品列表
# 嵌入模型：智谱AI（BigModel）embedding-3
# ============================================================

import os
import sys

# ---------- 知识点 1：路径设置 ----------
# 脚本在 app/AI/ 目录下，而项目模块在 app/ 下
# 所以需要把项目根目录加入 sys.path，Python 才能找到 app.database 等模块
# 否则会报错 ModuleNotFoundError: No module named 'app'
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)


# ============================================================
# 知识点 2：导入智谱嵌入函数
# ============================================================
# 从 deepseek_emb.py 导入你写好的 BigModelEmbeddingFunction
# 这个类封装了：
#   - 调用智谱 API 把文字转成向量
#   - Chroma 需要的 name() 和 __call__() 方法
# 这样阶段二、阶段三用的是同一个嵌入模型，向量维度一致，检索才准
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from deepseek_emb import BigModelEmbeddingFunction


# ============================================================
# 知识点 3：同义词扩展（查询改写）
# ============================================================
# 作用：用户问"笔记本电脑"，但知识库里分类叫"电脑办公"，直接搜可能搜不到
#       所以把用户问题"扩展"，加入同义词，让搜索更容易命中
def _expand_query(question):
    """
    查询词扩展：补充同义词，提高召回率

    例子：
      输入："你们有什么笔记本电脑？"
      输出："你们有什么笔记本电脑？ 电脑 计算机 笔记本电脑 笔记本 台式机..."
                                          ↑ 加入了这些同义词
    知识点：
      - "召回率" = 搜到的相关商品 / 所有相关商品
      - 召回率越高，漏搜的可能性越小
    """
    # 扩展规则：如果问题里包含任意一个关键词，就把整组词加进去
    expansion_rules = [
        (["手机", "苹果", "华为", "小米", "OPPO", "vivo"],
         "手机 智能手机 移动电话 数码产品 电子产品 手机数码"),
        (["电脑", "计算机", "笔记本", "台式机", "一体机", "打印机", "键盘"],
         "电脑 计算机 笔记本电脑 台式机 一体机 办公用品 电脑办公"),
        (["便宜", "低价", "性价比", "实惠", "平价"],
         "便宜 低价 性价比 实惠 平价 划算"),
        (["最贵", "高端", "奢侈品", "顶配", "旗舰"],
         "最贵 高端 奢侈品 顶配 旗舰"),
        (["家电", "电器", "大家电"],
         "家电 家用电器 电器 大家电 生活电器"),
        (["衣服", "服装", "鞋子", "帽子"],
         "衣服 服装 服饰 服装鞋帽 穿戴 鞋子 帽子"),
        (["吉他", "乐器", "运动", "户外", "健身"],
         "吉他 乐器 运动 户外 健身 体育用品 运动户外"),
        (["美妆", "化妆", "护肤", "口红", "香水"],
         "美妆 美妆护肤 美妆个护 化妆品 护肤品 美容 彩妆"),
        (["宠物", "猫", "狗", "猫粮", "狗粮"],
         "宠物 宠物生活 猫粮 狗粮 猫砂 宠物用品 猫咪 狗狗"),
        (["食品", "水果", "零食", "饮料"],
         "食品 食品生鲜 零食 吃的 喝的 饮料 水果 蔬菜"),
    ]

    keyword_set = set()  # 用 set 自动去重，避免"手机手机手机"
    keyword_set.add(question)  # 原问题先放进去

    # 检查命中了哪条规则，命中就把扩展词加进去
    for keywords, expansion in expansion_rules:
        hit = any(kw in question for kw in keywords)
        if hit:
            for w in expansion.split():
                keyword_set.add(w)

    expanded = " ".join(keyword_set)  # 拼成字符串
    return expanded


# ============================================================
# 知识点 4：意图识别 + 重排序
# ============================================================
# 作用：用户问"最便宜的手机"，相似度检索可能先返回 iPhone（贵的）
#       但用户真正要的是价格排序，所以要按意图重新排序
def _rerank_by_intent(question, results_list, n=3):
    """
    按用户意图重新排序搜索结果

    参数：
      question: 用户问题
      results_list: [(元数据, 距离), (元数据, 距离), ...]
      n: 返回前 n 条

    知识点：
      - "两阶段检索"：
          第一阶段：相似度检索，拿回 10-20 条候选（粗筛）
          第二阶段：按业务规则重排（精排）
      - 这样既快（向量检索快），又准（业务规则精排）
    """
    q = question

    # 判断是不是问"最便宜/最低"
    if ("最便宜" in q) or ("最低" in q) or ("最实惠" in q):
        results_list.sort(key=lambda x: x[0]["price"])  # 价格从低到高
    # 判断是不是问"最贵/最高"
    elif ("最贵" in q) or ("最高" in q) or ("顶级" in q):
        results_list.sort(key=lambda x: x[0]["price"], reverse=True)  # 价格从高到低

    return results_list[:n]  # 取前 n 条


# ============================================================
# 工具函数：连接 Chroma 知识库
# ============================================================
def get_collection():
    """
    获取 Chroma 的 shopping 集合（就是你阶段二建好的知识库）

    知识点：
      - Chroma 的 "集合" = 关系型数据库的 "表"
      - 存数据和取数据必须用同一个嵌入函数（向量维度相同）
      - 否则向量距离计算会完全错误
    """
    import chromadb

    # 1. 创建和阶段二一模一样的嵌入函数
    #    必须和存数据时用的完全相同
    embedding_func = BigModelEmbeddingFunction()

    # 2. 创建 Chroma 客户端，指向同一个数据目录
    persist_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
    client = chromadb.PersistentClient(path=persist_dir)

    # 3. 获取已经存在的集合
    #    注意：这里用 get_collection（只获取），不是 get_or_create_collection（获取或创建）
    #    因为阶段二已经创建好了，如果不存在就应该报错而不是新建
    collection = client.get_collection(
        name="shopping",
        embedding_function=embedding_func
    )

    print(f"✅ 已连接知识库，共 {collection.count()} 条商品")
    return collection


# ============================================================
# 辅助函数：打印结果（统一格式，方便看）
# ============================================================
def print_results(results_list):
    """
    打印检索结果列表

    结果格式说明：
      元数据 = {product_name, price, stock, category, ...}
      距离 = 0~2 之间的数
          0.0-0.8 = 强相关（⭐）
          0.8-1.2 = 中等相关（🤔）
          >1.2   = 相关性弱（⚠️）
    """
    for i, (meta, distance) in enumerate(results_list, 1):
        if distance < 0.8:
            tag = "⭐ 强相关"
        elif distance < 1.2:
            tag = "🤔 相关一般"
        else:
            tag = "⚠️  相关性弱"
        stock_text = "有货" if meta["stock"] > 0 else "缺货"

        print(f"\n  #{i} {meta['product_name']}")
        print(f"     价格：{meta['price']}元 | 库存：{stock_text} | 分类：{meta['category']}")
        print(f"     距离：{distance:.4f}  {tag}")


# ============================================================
# 检索方式 1：基础相似度检索
# ============================================================
def demo_1_basic_search(collection):
    """
    【最简单最常用的检索】
    原理：问题 → 向量 → 找向量距离最近的商品

    业务场景：通用问答
      用户："你们有什么手机？"
      返回：最相似的 5 个商品
    """
    print("\n" + "=" * 60)
    print("  检索方式 1：基础相似度检索")
    print("  原理：直接计算问题和商品的向量距离")
    print("  适用：普通问答，没有特殊要求")
    print("=" * 60)

    question = "你们有什么手机？"
    print(f"\n  用户问题：「{question}」")
    print("  处理流程：")
    print("    1. 问题文本 → 智谱嵌入 API → 问题向量")
    print("    2. 问题向量 vs 所有商品向量 → 计算距离")
    print("    3. 取距离最小的 5 条 → 输出")

    results = collection.query(
        query_texts=[question],  # 查询文本（会自动转成向量）
        n_results=5,             # 返回几条
    )

    # 把结果整理成 [(meta, distance), ...] 方便处理
    results_list = list(zip(results["metadatas"][0], results["distances"][0]))
    print_results(results_list)


# ============================================================
# 检索方式 2：带条件过滤的检索
# ============================================================
def demo_2_filtered_search(collection):
    """
    【带条件的精准检索】
    原理：先按 where 条件过滤元数据，再在过滤后做相似度检索

    业务场景：
      用户："1000 元以下的手机有哪些？"
      条件：分类="手机数码" 且 价格<=1000
      结果：只返回符合条件的商品
    """
    print("\n" + "=" * 60)
    print("  检索方式 2：带条件过滤的检索")
    print("  原理：先按条件过滤商品，再做相似度检索")
    print("  适用：用户明确说了价格范围、分类等条件")
    print("=" * 60)

    # --- 场景 A：按分类过滤 ---
    question = "推荐几款产品"
    category_filter = "食品生鲜"

    print(f"\n  用户问题：「{question}」")
    print(f"  过滤条件：分类 = {category_filter}")
    print("  处理流程：")
    print("    1. 从知识库中挑出分类='食品生鲜'的商品")
    print("    2. 在这些商品中做相似度检索")
    print("    3. 返回最相关的 3 条")

    results = collection.query(
        query_texts=[question],
        n_results=3,
        # 知识点：Chroma 的 where 语法
        #   $eq = 等于   $gte = 大于等于   $lte = 小于等于
        #   类似 MongoDB 的查询语法
        where={"category": {"$eq": category_filter}},
    )
    results_list = list(zip(results["metadatas"][0], results["distances"][0]))
    print_results(results_list)

    # --- 场景 B：按价格范围过滤 ---
    question = "有什么便宜的商品？"
    max_price = 200

    print(f"\n  用户问题：「{question}」")
    print(f"  过滤条件：价格 <= {max_price} 元")

    results = collection.query(
        query_texts=[question],
        n_results=3,
        # 知识点：价格小于等于 200
        where={"price": {"$lte": max_price}},
    )
    results_list = list(zip(results["metadatas"][0], results["distances"][0]))
    print_results(results_list)


# ============================================================
# 检索方式 3：查询扩展 + 意图重排（升级版）
# ============================================================
def demo_3_upgraded_search(collection):
    """
    【升级版：两步优化】
    步骤 1：查询扩展 → 加入同义词，让检索更准（提高召回率）
    步骤 2：意图重排 → 根据问题按价格排序（提高准确率）

    业务场景：复杂查询
      用户："最便宜的手机是什么？"
      过程：
        1. 扩展查询词：加入"手机 智能手机 移动电话..."
        2. 相似度检索：先搜 10 条候选
        3. 意图识别：用户问"最便宜" → 按价格升序排
        4. 返回：前 3 条（从便宜到贵）
    """
    print("\n" + "=" * 60)
    print("  检索方式 3：查询扩展 + 意图重排（升级版）")
    print("  步骤：先扩展查询词 → 粗筛10条 → 按意图精排")
    print("  适用：复杂查询，如'最便宜的手机'、'最贵的电脑'")
    print("=" * 60)

    # --- 场景 A：最便宜 ---
    question = "最便宜的商品是什么？"
    print(f"\n  用户问题：「{question}」")

    # 第 1 步：查询扩展
    expanded_q = _expand_query(question)
    if expanded_q != question:
        print(f"  🔧 扩展为：{expanded_q}")

    # 第 2 步：先粗搜 10 条
    results = collection.query(query_texts=[expanded_q], n_results=10)
    candidates = list(zip(results["metadatas"][0], results["distances"][0]))
    print(f"  📋 粗筛出 {len(candidates)} 条候选")

    # 第 3 步：按"最便宜"重排，取前 3 条
    ranked = _rerank_by_intent(question, candidates, n=3)
    print(f"  📊 按意图重排后（价格从低到高）：")
    print_results(ranked)

    # --- 场景 B：笔记本电脑（最容易搜不准，因为同义词多）---
    question = "有没有笔记本电脑？"
    print(f"\n  用户问题：「{question}」")

    expanded_q = _expand_query(question)
    if expanded_q != question:
        print(f"  🔧 扩展为：{expanded_q}")

    results = collection.query(query_texts=[expanded_q], n_results=10)
    candidates = list(zip(results["metadatas"][0], results["distances"][0]))
    ranked = _rerank_by_intent(question, candidates, n=3)
    print(f"  📊 最终结果（最相关的 3 条）：")
    print_results(ranked)


# ============================================================
# 检索方式 4：业务级检索（过滤无货 + 价格排序）
# ============================================================
def demo_4_business_search(collection):
    """
    【真实业务场景的检索】
    额外要求：
      - 不能推荐没货的（否则用户投诉）
      - 按价格升序（便宜的在前，用户体验好）

    流程：
      1. 相似度检索：先拿 20 条候选
      2. 过滤：库存 > 0 的商品
      3. 排序：按价格从低到高
      4. 取前 5 条展示
    """
    print("\n" + "=" * 60)
    print("  检索方式 4：业务级检索（过滤无货 + 价格排序）")
    print("  步骤：粗筛 20 条 → 去无货 → 按价格排 → 取前 5")
    print("  适用：生产环境的真实业务")
    print("=" * 60)

    question = "文具类有什么"
    print(f"\n  用户问题：「{question}」")

    # 第 1 步：先粗搜 20 条（宁可多拿，也别漏）
    results = collection.query(query_texts=[question], n_results=20)
    candidates = list(zip(
        results["metadatas"][0],
        results["distances"][0],
    ))

    # 第 2 步：过滤掉库存=0的
    in_stock = [(meta, dist) for (meta, dist) in candidates if meta["stock"] > 0]
    print(f"  📦 过滤前：{len(candidates)} 条 → 过滤无货后：{len(in_stock)} 条")

    # 第 3 步：按价格升序（便宜在前）
    in_stock_sorted = sorted(in_stock, key=lambda x: x[0]["price"])

    # 第 4 步：取前 5 条
    final = in_stock_sorted[:5]
    print(f"  💰 按价格排序后，取前 {len(final)} 条：")
    print_results(final)


# ============================================================
# 检索方式 5：交互式检索（自己测试）
# ============================================================
def demo_5_interactive(collection):
    """
    【交互式测试】你可以不断输入问题测试效果

    用途：
      - 找到检索不准的 case（比如问"水果"却返回了"牙刷"）
      - 记录下来，后面加同义词或优化文档
    """
    print("\n" + "=" * 60)
    print("  检索方式 5：交互式测试模式")
    print("  使用说明：")
    print("    1. 输入你的问题，按回车")
    print("    2. 会自动：查询扩展 → 检索 → 意图重排")
    print("    3. 输入 quit 或 q 退出")
    print("=" * 60)

    while True:
        try:
            print("\n" + "-" * 50)
            question = input("请输入问题：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n✅ 已退出交互模式")
            break

        if question.lower() in ("quit", "q", "exit", ""):
            print("✅ 已退出交互模式")
            break

        # 走完整流程：扩展 → 检索 → 重排
        expanded_q = _expand_query(question)
        results = collection.query(query_texts=[expanded_q], n_results=10)
        candidates = list(zip(results["metadatas"][0], results["distances"][0]))
        ranked = _rerank_by_intent(question, candidates, n=5)

        if expanded_q != question:
            print(f"  🔧 查询已扩展：{expanded_q}")
        print(f"  🎯 为你找到以下 {len(ranked)} 个商品：")
        print_results(ranked)


# ============================================================
# 主函数：依次演示 5 种检索方式
# ============================================================
def main():
    print("\n" + "=" * 60)
    print("  🚀 阶段三：语义检索实战（智谱嵌入版）")
    print("=" * 60)

    # 先连接知识库
    print("\n📡 正在连接知识库...")
    collection = get_collection()

    # 演示 1：基础相似度检索
    demo_1_basic_search(collection)

    # 演示 2：带条件过滤
    demo_2_filtered_search(collection)

    # 演示 3：查询扩展 + 意图重排
    demo_3_upgraded_search(collection)

    # 演示 4：业务级检索
    demo_4_business_search(collection)

    # 演示 5：交互模式（你可以自己输入问题）
    print("\n" + "=" * 60)
    print("  🎉 以上是 4 种检索方式的演示")
    print("  接下来进入交互模式，自己输入问题试试吧！")
    print("=" * 60)
    demo_5_interactive(collection)

    print("\n" + "=" * 60)
    print("  ✅ 阶段三完成！你已经掌握了：")
    print("     1. 基础相似度检索")
    print("     2. 带条件过滤（分类、价格）")
    print("     3. 查询扩展 + 意图重排（升级版）")
    print("     4. 业务级检索（去无货、排序）")
    print("     5. 交互式测试方法")
    print("  下一步：阶段四 - 把检索结果交给 AI 生成自然回答")
    print("=" * 60)


if __name__ == "__main__":
    main()