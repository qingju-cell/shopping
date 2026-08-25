# ============================================================
# product.py —— 商品表 ORM 模型
# 功能：映射数据库中的 products 表，存储商品信息
# 对应数据库表：products
# 字段说明：
#   - id: 商品ID（主键，自增）
#   - name: 商品名称
#   - description: 商品描述（详细介绍）
#   - price: 商品价格（DECIMAL 精确到 2 位小数）
#   - stock: 库存数量
#   - category_id: 所属分类ID（关联 categories 表）
#   - image_url: 商品主图地址
#   - status: 状态（1 上架 / 0 下架）
#   - created_at: 创建时间
#   - updated_at: 更新时间
# ============================================================

from sqlalchemy import Column, Integer, String, Text, DECIMAL, DateTime, SmallInteger
from sqlalchemy.sql import func
from app.database import Base


# Product 类对应数据库中的 products 表
class Product(Base):
    __tablename__ = "products"

    # ---------- 主键 ----------
    id = Column(Integer, primary_key=True, autoincrement=True, comment="商品ID")

    # ---------- 商品基本信息 ----------
    name = Column(String(200), nullable=False, comment="商品名称")
    # Text 类型可以存储很长的文本，不限长度
    description = Column(Text, comment="商品描述")
    # DECIMAL(10, 2) 表示最多 10 位数字，其中 2 位小数
    # 使用 DECIMAL 而不是 FLOAT 是为了精确存储金额
    price = Column(DECIMAL(10, 2), nullable=False, comment="商品价格")
    stock = Column(Integer, nullable=False, default=0, comment="库存数量")
    category_id = Column(Integer, comment="所属分类ID")
    image_url = Column(String(500), comment="商品主图")

    # ---------- 商品状态 ----------
    # SmallInteger 占用空间更小，适合存储小数字（0/1）
    status = Column(SmallInteger, default=1, comment="状态：1上架 0下架")

    # ---------- 时间戳 ----------
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    def to_dict(self):

        return{
            "id":self.id,
            "name":self.name,
            "description":self.description,
            "price":float(self.price),
            "stock":self.stock,
            "category_id":self.category_id,
            "image_url":self.image_url,
            "status":self.status,
            "created_at":self.created_at.isoformat(),
            "updated_at":self.updated_at.isoformat(),
        }
