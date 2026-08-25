# ============================================================
# database.py —— 数据库连接与 ORM 配置
# 功能：
#   1. 创建数据库引擎（engine）
#   2. 创建数据库会话工厂（SessionLocal）
#   3. 定义 ORM 模型基类（Base）
#   4. 提供依赖注入函数（get_db），让路由自动获取数据库会话
# 技术栈：SQLAlchemy + PyMySQL
# ============================================================

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.config import settings

# ---------- 1. 创建数据库引擎 ----------
# create_engine 是 SQLAlchemy 的核心入口，负责管理数据库连接
# 参数说明：
#   - settings.db_url：数据库连接地址（在 config.py 中拼接好的）
#   - echo=True：把执行的 SQL 语句打印到控制台，方便调试
#                生产环境建议关闭（改成 False）
#   - pool_pre_ping=True：每次使用连接前先检测是否存活，避免 "MySQL has gone away" 错误
#   - pool_recycle=3600：连接使用 1 小时后自动回收，防止连接超时断开
engine = create_engine(
    settings.db_url,
    echo=True,
    pool_pre_ping=True,
    pool_recycle=3600
)

# ---------- 2. 创建数据库会话工厂 ----------
# SessionLocal 是一个工厂函数，调用它可以创建新的数据库会话
# ORM 模型通过会话与数据库交互（增删改查）
# 参数说明：
#   - autocommit=False：不自动提交事务，需要手动 commit()
#   - autoflush=False：不自动刷新，避免一些意外的 SQL 执行
#   - bind=engine：绑定到上面创建的引擎
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# ---------- 3. ORM 模型基类 ----------
# 所有数据表模型（User、Product、Order 等）都继承自 Base
# Base 提供了 ORM 的基础能力，比如自动映射、表结构定义等
Base = declarative_base()


# ---------- 4. 依赖注入函数 ----------
# FastAPI 的路由函数可以通过 Depends(get_db) 自动获取数据库会话
# 使用 yield 实现：
#   - 路由函数执行期间，db 会话一直有效
#   - 路由函数执行完毕后，自动关闭会话（finally 块）
def get_db():
    db = SessionLocal()  # 创建新的数据库会话
    try:
        yield db        # 把会话交给路由函数使用
    finally:
        db.close()      # 路由函数执行完后，关闭会话释放资源