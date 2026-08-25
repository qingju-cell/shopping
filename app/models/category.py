# ============================================================
# category.py —— 商品分类表 ORM 模型
# 功能：映射数据库中的 categories 表，商品分类可以是多级的
# 对应数据库表：categories
# 字段说明：
#   - id: 分类ID（主键，自增）
#   - name: 分类名称
#   - parent_id: 父分类ID（0 表示顶级分类）
#   - sort: 排序权重（数字越小越靠前）
#   - created_at: 创建时间
# ============================================================

from sqlalchemy import Column, DateTime, Enum, Integer, String
from sqlalchemy.sql import func
from app.database import Base


# Category 类对应数据库中的 categories 表
class Category(Base):
    __tablename__ = "categories"

    # ---------- 主键 ----------
    id = Column(Integer, primary_key=True, autoincrement=True, comment="分类ID")

    # ---------- 分类信息 ----------
    name = Column(String(50), nullable=False, comment="分类名称")
    # parent_id=0 表示顶级分类，大于0表示该分类属于某个父分类下
    parent_id = Column(Integer, default=0, comment="父分类ID")
    # sort 用于排序，数字越小越靠前
    sort = Column(Integer, default=0, comment="排序权重")

    # ---------- 时间戳 ----------
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")

    def to_dict(self):
        return{
            "id":self.id,
            "name":self.name,
            "parent_id":self.parent_id,
            "sort":self.sort,
            "created_at":self.created_at.isoformat(),
        }