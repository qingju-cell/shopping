# ============================================================
# step5_rag_chatbot.py —— 阶段四：完整 RAG AI 客服
#
# 目标：把「检索到的商品列表」变成「自然语言回答」
# 流程：
#   用户问题 → 意图路由 → 对应通道 → 回答
#       ├─ chat    → 闲聊通道（不搜商品，直接让大模型回答）
#       ├─ product → 商品通道（检索+阈值过滤+关键词校验+诚实提示词）
#       ├─ service → 售后通道（预留，以后加）
#       └─ abuse   → 礼貌拒绝
# ============================================================

import os
import sys
import re

# ---------- 路径设置 ----------
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ---------- 加载 .env ----------
from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(env_path)

# ---------- 导入阶段三的工具函数 ----------
# 复用阶段三已经写好的：查询扩展、意图重排、连接知识库
from step4_semantic_search import (
    _expand_query,
    _rerank_by_intent,
    get_collection,
    print_results,
)


# ============================================================
# 知识点 1：创建大模型客户端（DeepSeek Chat）
# ============================================================
def get_llm_client():
    """
    创建 DeepSeek 大模型的客户端，用来生成回答
    
    嵌入 vs 大模型：
      - 嵌入模型（智谱 embedding-3）：把文字转成向量，用于检索
      - 聊天大模型（DeepSeek Chat）：理解用户问题，生成自然语言回答
    """
    from openai import OpenAI
    
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    
    if not api_key:
        raise ValueError("请在 .env 里设置 OPENAI_API_KEY（DeepSeek 的 API Key）")
    
    # DeepSeek 兼容 OpenAI SDK，所以可以用 openai 库连接
    client = OpenAI(
        api_key=api_key,
        base_url=base_url,
    )
    print(f"✅ 已连接 DeepSeek 大模型：{base_url}")
    return client


# ============================================================
# 知识点 2：关键词校验（防止不相关商品混进来）
# ============================================================
def keyword_check(question, products, min_hit=1):
    """
    问题里的关键词有没有出现在检索结果里？
    
    作用：
      用户问「飞机」，如果检索结果里连「飞」「机」两个字都不出现，
      直接判定为不相关，返回空，不用交给大模型。
    """
    # 提取问题中的关键词（单字 + 重要词）
    keywords = set()
    
    # 1. 重要词（分类名相关）
    important_words = [
        "手机", "电脑", "笔记本", "水果", "食品", "衣服", "鞋", "美妆",
        "宠物", "汽车", "家电", "电器", "图书", "文具", "服装", "帽子",
        "运动", "户外", "母婴", "玩具", "家居", "零食", "饮料",
    ]
    for w in important_words:
        if w in question:
            keywords.add(w)
    
    # 2. 单个中文字符（简单粗暴但有效）
    for char in question:
        if '\u4e00' <= char <= '\u9fff':
            keywords.add(char)
    
    if not keywords:
        return True  # 没提取到关键词就跳过校验
    
    # 检查所有商品里有没有命中关键词的
    hit_count = 0
    for meta, dist in products:
        text_to_check = f"{meta['product_name']} {meta['category']}"
        for kw in keywords:
            if kw in text_to_check:
                hit_count += 1
                break
    
    return hit_count >= min_hit


# ============================================================
# 知识点 3：意图分类（路由器）—— 关键词版
# ============================================================
def classify_intent_by_keywords(question):
    """
    判断用户的问题属于哪一类，决定走哪个通道
    
    返回值：
      product → 商品咨询（走 RAG）
      chat    → 闲聊/常识（直接让大模型聊）
      service → 订单/售后（预留）
      abuse   → 辱骂/恶意（礼貌拒绝）
    
    知识点：
      "意图路由" = 就像医院的导诊台：
        头痛 → 神经内科
        骨折 → 骨科
        感冒 → 呼吸内科
    """
    q = question
    
    # ========== 1. 恶意问题 ==========
    abuse_words = ["傻逼", "垃圾", "滚", "废物", "脑残", "去死", "操", "草"]
    for w in abuse_words:
        if w in q:
            return "abuse"
    
    # ========== 2. 订单/售后 ==========
    service_keywords = [
        "订单", "下单", "付款", "支付", "发货", "物流", "快递", "运单号",
        "退货", "退款", "换货", "售后", "退换", "发票", "收货", "配送",
        "优惠券", "红包", "满减", "地址", "修改地址",
    ]
    for kw in service_keywords:
        if kw in q:
            return "service"
    
    # ========== 3. 商品咨询 ==========
    product_keywords = [
        # 商品相关词
        "商品", "产品", "卖", "买", "有", "推荐", "介绍", "选", "挑",
        # 分类
        "手机", "电脑", "笔记本", "衣服", "鞋", "水果", "食品", "零食",
        "美妆", "护肤", "宠物", "汽车", "家电", "电器", "图书", "文具",
        "服装", "帽子", "运动", "户外", "母婴", "玩具", "家居", "日用",
        # 属性
        "价格", "多少钱", "便宜", "贵", "性价比", "优惠", "打折", "折扣",
        "库存", "有货", "没货", "缺货", "现货",
        "品牌", "什么牌子", "哪款", "哪个好", "怎么样", "对比",
        "质量", "评价", "口碑", "评论",
    ]
    product_hit = 0
    for kw in product_keywords:
        if kw in q:
            product_hit += 1
    if product_hit >= 1:
        return "product"
    
    # ========== 4. 其他 = 闲聊 ==========
    return "chat"


# ============================================================
# 知识点 4：商品通道 —— 三层过滤 + 诚实 RAG
# ============================================================
def build_product_prompt(question, products):
    """
    把「用户问题」和「检索到的商品」拼成给大模型的提示词（Prompt）
    
    核心：加诚实规则，让大模型不要瞎编
    """
    # 把检索到的商品格式化成文本
    products_text = ""
    for i, (meta, dist) in enumerate(products, 1):
        stock_text = "有货" if meta["stock"] > 0 else "缺货"
        products_text += f"""
【商品 {i}】
  名称：{meta['product_name']}
  分类：{meta['category']}
  价格：{meta['price']}元
  库存状态：{stock_text}（剩余{meta['stock']}件）
  内部相似度：{dist:.4f}
"""
    
    # 提示词模板：诚实规则 + 可推荐商品 + 用户问题
    prompt = f"""
你是「小购」，一个友好、专业的电商平台AI客服。

【核心规则（必须严格遵守！）】
1. **诚实第一**：只能从【可推荐商品】中挑选推荐，绝对不可以编造不存在的商品。
2. **不强行推荐**：如果【可推荐商品】和用户问题不相关，直接说"抱歉，我们暂时没有这类商品哦~"，
   不要硬把不相关的商品塞给用户。
3. **不编造信息**：商品的价格、库存、分类以【可推荐商品】里写的为准，不要自己编。
4. **有货优先**：如果有多个推荐，优先推荐库存 > 0 的商品。
5. **简洁明了**：回答 3-5 句话，不要长篇大论。

【可推荐商品】
{products_text if products_text else "（没有检索到符合条件的商品）"}

【用户问题】
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
    return prompt


def product_rag_channel(collection, llm_client, question):
    """
    商品咨询通道：完整 RAG 流程
    
    三层过滤：
      1. 向量距离阈值（<= 1.2）
      2. 关键词校验（有没有命中相关词）
      3. 大模型诚实判断（提示词里加规则）
    """
    print("  📦 通道：商品咨询（RAG）")
    
    # ---------- 第 1 步：查询扩展 ----------
    expanded_q = _expand_query(question)
    if expanded_q != question:
        print(f"  🔧 查询扩展：{expanded_q}")
    
    # ---------- 第 2 步：向量检索 ----------
    results = collection.query(query_texts=[expanded_q], n_results=10)
    candidates = list(zip(results["metadatas"][0], results["distances"][0]))
    print(f"  📊 粗筛出 {len(candidates)} 条候选")
    
    # ---------- 第 3 步：第一层：距离阈值过滤 ----------
    THRESHOLD = 1.2
    filtered = [(meta, dist) for (meta, dist) in candidates if dist <= THRESHOLD]
    print(f"  🎯 阈值过滤（<={THRESHOLD}）：剩 {len(filtered)} 条")
    
    if len(filtered) == 0:
        answer = "抱歉，我们暂时没有这类商品哦~ 可以看看我们的手机数码、电脑办公、食品生鲜等热门品类~"
        print(f"  🤖 AI：{answer}")
        return answer
    
    # ---------- 第 4 步：意图重排（最便宜/最贵按价格排）----------
    ranked = _rerank_by_intent(question, filtered, n=5)
    print(f"  📈 意图重排后：取 {len(ranked)} 条")
    print_results(ranked)
    
    # ---------- 第 5 步：第二层：关键词校验 ----------
    if not keyword_check(question, ranked):
        answer = "抱歉，我们暂时没有这类商品哦~ 可以看看我们的手机数码、电脑办公、食品生鲜等热门品类~"
        print(f"  ⚠️  关键词校验未通过 → 直接返回无货")
        print(f"  🤖 AI：{answer}")
        return answer
    
    # ---------- 第 6 步：第三层：交给大模型（诚实提示词）----------
    print(f"  🧠 交给 DeepSeek 大模型生成回答...")
    prompt = build_product_prompt(question, ranked)
    
    response = llm_client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,  # 商品咨询要严谨！温度调低，不瞎编
    )
    answer = response.choices[0].message.content.strip()
    
    print(f"  🤖 AI：{answer}")
    return answer


# ============================================================
# 知识点 5：闲聊通道（不搜商品，直接聊）
# ============================================================
def chat_channel(llm_client, question):
    """
    闲聊/常识通道：处理 1+1、天气、讲笑话等非购物问题
    
    关键点：
      - 不检索知识库！省嵌入 API 钱，也不被商品信息干扰
      - 加人设，记得自己是购物客服，聊完后引导回购物
    """
    print("  💬 通道：闲聊/常识")
    print(f"  🧠 交给 DeepSeek 大模型闲聊回答...")
    
    prompt = f"""
你是「小购」，一个活泼、友好的电商平台AI客服。

你的任务：
  1. 用户问非购物类的问题，先简短准确地回答
  2. 回答完后，**用一句话把话题引导回购物**
  3. 回答要自然，不要生硬，1-2句话就好

【用户问题】
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
    
    response = llm_client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,  # 闲聊可以活泼一点
    )
    answer = response.choices[0].message.content.strip()
    
    print(f"  🤖 AI：{answer}")
    return answer


# ============================================================
# 知识点 6：售后通道（预留，以后加数据库查询）
# ============================================================
def service_channel(llm_client, question):
    """
    订单/售后通道（暂时写死，以后可以接入订单数据库）
    
    以后要加的功能：
      - 查询订单状态：查 MySQL 的 orders 表
      - 查询物流：调快递 API
      - 申请退货：写退货表
      - 开发票：调用财务系统
    """
    print("  📞 通道：订单/售后（预留接口）")
    
    # 暂时用简单模板回答，以后扩展
    answer = "订单/售后功能正在完善中~ 您可以在网站的「个人中心-我的订单」里查看订单状态和物流信息哦~ 如需人工客服，请拨打 400-xxx-xxxx~"
    print(f"  🤖 AI：{answer}")
    return answer


# ============================================================
# 知识点 7：恶意问题通道（礼貌拒绝）
# ============================================================
def abuse_channel(question):
    """
    处理辱骂、恶意内容
    """
    print("  ⚠️  通道：恶意问题 → 礼貌拒绝")
    answer = "请您文明用语哦~ 我是您的购物助手小购，有任何购物相关的问题，我都会尽力帮您解决的~"
    print(f"  🤖 AI：{answer}")
    return answer


# ============================================================
# 知识点 8：总入口 —— AI 客服函数
# ============================================================
def ai_customer_service(collection, llm_client, question):
    """
    完整的 AI 客服入口函数
    
    流程：
      1. 意图分类（走哪个通道？）
      2. 通道路由（对应通道处理）
      3. 返回回答
    """
    print("\n" + "=" * 60)
    print(f"🙋 用户：{question}")
    print("-" * 60)
    
    # 第 1 步：意图分类
    intent = classify_intent_by_keywords(question)
    intent_map = {
        "chat": "闲聊/常识",
        "product": "商品咨询",
        "service": "订单/售后",
        "abuse": "恶意问题",
    }
    print(f"🧭 意图识别：{intent_map.get(intent, '未知')}（{intent}）")
    
    # 第 2 步：按意图路由到对应通道
    if intent == "abuse":
        return abuse_channel(question)
    elif intent == "chat":
        return chat_channel(llm_client, question)
    elif intent == "service":
        return service_channel(llm_client, question)
    elif intent == "product":
        return product_rag_channel(collection, llm_client, question)
    else:
        return "抱歉，我没理解您的意思，可以再说一遍吗？"


# ============================================================
# 知识点 9：演示几个预设问题
# ============================================================
def run_demos(collection, llm_client):
    """
    演示 6 个典型场景，让你看每个通道的效果
    """
    demos = [
        ("1+1等于几？",                          "闲聊测试"),
        ("你们有什么便宜的手机？",                "商品咨询测试"),
        ("推荐几款不同类型的产品？",              "多样性商品推荐"),
        ("我的订单什么时候发货？",                "订单售后测试"),
        ("你们卖的都是垃圾！",                    "恶意问题测试"),
        ("最便宜的电脑是什么？",                  "价格意图测试"),
    ]
    
    print("\n" + "=" * 60)
    print("  📝 阶段四：6 个典型场景演示")
    print("=" * 60)
    
    for question, tag in demos:
        print(f"\n\n【演示：{tag}】")
        try:
            ai_customer_service(collection, llm_client, question)
        except Exception as e:
            print(f"  ❌ 出错：{e}")
            import traceback
            traceback.print_exc()


# ============================================================
# 知识点 10：交互式聊天（和 AI 客服对话）
# ============================================================
def run_chat_mode(collection, llm_client):
    """
    交互式聊天：像聊天一样不断问问题
    
    输入 quit 退出
    """
    print("\n" + "=" * 60)
    print("  💬 进入聊天模式")
    print("  使用说明：")
    print("    • 直接输入问题，按回车和 AI 客服对话")
    print("    • 试试闲聊：1+1等于几？/ 讲个笑话")
    print("    • 试试商品：推荐便宜的手机？/ 有水果吗？")
    print("    • 输入 quit / q 退出")
    print("  💡 提示：如果回答不满意，多换几种问法试试~")
    print("=" * 60)
    
    while True:
        try:
            print("\n" + "-" * 60)
            question = input("👤 你：").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n✅ 已退出聊天模式")
            break
        
        if question.lower() in ("quit", "q", "exit", ""):
            print("✅ 已退出聊天模式")
            break
        
        try:
            ai_customer_service(collection, llm_client, question)
        except Exception as e:
            print(f"  ❌ 出错：{e}")


# ============================================================
# 主函数
# ============================================================
def main():
    print("\n" + "=" * 60)
    print("  🛒 阶段四：完整 RAG AI 客服系统")
    print("  功能：意图路由 + 三层过滤 + 诚实回答 + 闲聊")
    print("=" * 60)
    
    # ---------- 1. 初始化：连接知识库 + 大模型 ----------
    print("\n📡 正在初始化系统...")
    try:
        collection = get_collection()
        llm_client = get_llm_client()
    except Exception as e:
        print(f"❌ 初始化失败：{e}")
        import traceback
        traceback.print_exc()
        return
    
    # ---------- 2. 先跑几个演示 ----------
    run_demos(collection, llm_client)
    
    # ---------- 3. 进入聊天模式 ----------
    print("\n" + "=" * 60)
    print("  🎉 演示完成！现在可以自己和 AI 客服聊天了~")
    print("=" * 60)
    run_chat_mode(collection, llm_client)
    
    # ---------- 4. 总结 ----------
    print("\n" + "=" * 60)
    print("  ✅ 阶段四完成！你已经掌握了完整的 RAG 客服：")
    print("     1. 意图分类（导诊台）")
    print("     2. 闲聊通道（回答常识类问题）")
    print("     3. 商品通道 RAG（三层过滤 + 诚实提示词）")
    print("     4. 售后通道（预留接口）")
    print("     5. 礼貌拒绝（处理恶意内容）")
    print("  下一步：把 AI 客服接入 FastAPI 后端 + 前端聊天界面")
    print("=" * 60)


if __name__ == "__main__":
    main()