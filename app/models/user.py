# ============================================================
# user.py —— 用户表 ORM 模型
# 功能：映射数据库中的 users 表，定义表结构
# 对应数据库表：users
# 字段说明：
#   - id: 用户ID（主键，自增）
#   - username: 用户名（唯一，不能为空）
#   - password: 加密后的密码
#   - email: 邮箱
#   - phone: 手机号
#   - role: 角色（customer 普通用户 / admin 管理员）
#   - created_at: 创建时间
#   - updated_at: 更新时间
# ============================================================

from sqlalchemy import Column, Integer, String, DateTime, Enum, func

from app.database import Base


# User 类继承自 Base，对应数据库中的 users 表
# 每个 Column() 定义一个数据库字段
class User(Base):
    # 指定映射的数据库表名
    __tablename__ = "users"

    # ---------- 主键 ----------
    id = Column(Integer, primary_key=True, autoincrement=True, comment="用户ID")

    # ---------- 用户基本信息 ----------
    username = Column(String(50), unique=True, nullable=False, comment="用户名")
    password = Column(String(255), nullable=False, comment="加密密码")
    email = Column(String(100), comment="邮箱")
    phone = Column(String(20), comment="手机号")

    # ---------- 角色 ----------
    # Enum 限制只能是 'customer' 或 'admin'，默认 'customer'
    role = Column(Enum("customer", "admin"), default="customer", comment="角色用户")

    # ---------- 时间戳 ----------
    # server_default=func.now() 表示由数据库自动填充当前时间
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    # onupdate=func.now() 表示记录更新时自动更新时间
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    def to_dict(self):

        return{
            "id":self.id,
            "username":self.username,
            "email":self.email,
            "phone":self.phone,
            "role":self.role,
            "created_at":self.created_at.isoformat(),
            "updated_at":self.updated_at.isoformat(),
        }
