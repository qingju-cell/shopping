# ============================================================
# step2_create_documents.py —— 阶段二第二步：把商品转换成知识库文档
# 目的：理解"文本分块"的概念
# ============================================================
import os
import sys

# ---------- 设置 Python 路径（让脚本能导入项目模块）----------
# 这一步很重要，因为脚本在 app/AI/ 下
# 而项目模块在 app/ 下，需要让 Python 能找到它们

project_root=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0,project_root)

from app.database import SessionLocal  # 导入数据库会话
from app.models.product import Product   # 导入商品模型
from app.models.category import Category  # 导入分类模型

def load_products():
    """从数据库读取商品数据（和 step1 相同）"""
    db = SessionLocal()
    try:
        products = db.query(Product).filter(Product.status == 1).all()
        categories = db.query(Category).all()
        category_map = {c.id: c.name for c in categories}

        result=[]
        for p in products:
            result.append({
                "id": p.id,
                "name":p.name,
                "description":p.description,
                "price":p.price,
                "stock":p.stock,
                "category_id":p.category_id,
                "category_name":category_map.get(p.category_id,"未知分类"),
                "image_url":p.image_url or "",
            })
        return result
    finally:
        db.close()

def convert_to_document(products):
    """
       把每个商品转换成一段文本（文档分块）

       分块策略：
         - 一个商品 = 一块文档
         - 每块文档包含：商品名称、价格、库存、分类、描述
         - 这样 AI 检索到后，能直接把这段内容展示给用户

       为什么要把分类名称放进去？
         - 用户问 "你们有什么手机？"，"手机" 两个字能匹配到 "手机数码" 分类
         - 增加检索的命中率
       """
    documents=[]  # 存储所有文档的文本
    metadatas=[]  # 存储所有文档的元数据（如商品ID、分类等）

    for product in products:
        #----------拼接文档文本----------
        #格式自然，避免过长的句子
        doc_text=f"""
        {product['name']}，
        价格{product['price']}元，
        库存{product['stock']}件，
        属于{product['category_name']}分类，
        商品描述: {product['description']  }
        """
        documents.append(doc_text)

        # ---------- 保存元数据 ----------
        # 元数据的作用：
        #   1. 检索后返回给前端展示（显示商品图片、价格等）
        #   2. 支持条件筛选（比如只搜价格 < 1000 的商品）
        metadatas.append({
            "product_id":product["id"],
            "product_name":product["name"],
            "price":product["price"],
            "stock": product["stock"],
            "category": product["category_name"],
            "image_url": product["image_url"],
        })

    return documents,metadatas

def main():
    print("=" * 60)
    print("  阶段二：把商品转换成知识库文档")
    print("=" * 60)

    # 第 1 步：读取商品
    print("\n📦 第 1 步：从数据库读取商品...")
    products=load_products()
    print(f"成功读取 {len(products)} 条商品数据")

    # 第 2 步：转换商品数据为文档
    print("\n📦 第 2 步：转换商品数据为文档...")
    documents,metadatas=convert_to_document(products)
    print(f"成功转换 {len(documents)} 条文档")

    # 第 3 步：展示转换结果
    print("\n" + "=" * 60)
    print("  转换结果预览")
    print("=" * 60)
    for i,(doc,meta) in enumerate(zip(documents,metadatas),start=1):
        print(f"\n--文档{i}--")
        print("文本内容")
        print(doc)
        print("元数据")
        print(f"  商品ID:{meta['product_id']}")
        print(f"  商品名:{meta['product_name']}")
        print(f"  价格: {meta['price']}元")
        print(f"  库存: {meta['stock']}件")
        print(f"  分类: {meta['category']}")

    print("\n" + "=" * 60)
    print(f"\n✅ 转换完成！共 {len(documents)} 段文档")
    print("   下一步：把这些文档存到向量数据库")
if __name__ == "__main__":
    main()