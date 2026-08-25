# ============================================================
# step1_load_data.py —— 阶段二第一步：从数据库读取商品数据
# 目的：验证能连上数据库，把商品数据读出来
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

def main():
    """读取并打印所有商品信息"""

    # ---------- 1. 创建数据库会话 ----------
    # SessionLocal() 会创建一个和 MySQL 的连接
    db=SessionLocal()
    print("数据库会话已创建")

    # ---------- 2. 从数据库查询所有商品 ----------
    try:
        #查询所有商品
        products=db.query(Product).filter(Product.status==1).all()
        print(f"📦 查询到 {len(products)} 个上架商品\n")

        #3.---------查询所有分类
        categories=db.query(Category).all()
        # 把分类列表转成字典：{分类ID: 分类名称}
        # 这样后面就能通过 category_map[1] 快速查到 "手机数码"
        category_map={c.id:c.name for c in categories}
        print(f"📦 查询到 {len(categories)} 个分类\n")

        #4.---------打印商品信息------
        for i,product in enumerate(products,start=1):
            category_name=category_map.get(product.category_id,"未知分类")
            print(f"商品 {i}: ")
            print(f"  商品ID: {product.id}")
            print(f"  商品名称:{product.name}")
            print(f"  商品分类: {category_name}")
            print(f"  商品价格: {product.price}")
            print(f"  商品库存: {product.stock}")
            print(f"  商品描述: {product.description or '无描述'}")

    finally:
        #--------5.关闭数据库会话---------
        db.close()
        print("数据库会话已关闭")

if __name__ == "__main__":
    main()