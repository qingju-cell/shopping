# ============================================================
# user_service.py —— 用户业务逻辑层
# 功能：
#   1. 密码加密与验证（使用 bcrypt + sha256）
#   2. 用户注册：检查用户名是否重复，加密密码后保存
#   3. 用户登录：验证用户名和密码是否正确
#   4. 根据 ID 查询用户
# 说明：Service 层是 "业务逻辑层"，负责处理核心业务
#       路由层（api/）只负责接收请求和返回响应
# ============================================================

from fastapi import HTTPException
import hashlib
import bcrypt
from sqlalchemy.orm import Session

from app.models.user import User
from app.schemas.user import UserRegister, UserLogin


# ---------- 密码加密辅助函数 ----------
def _hash_password(password: str) -> str:
    """
    加密密码：先 SHA256 归一化长度，再用 bcrypt 加密
    bcrypt 只接受 72 字节以内的输入，超过会截断
    SHA256 会将任意长度的密码转换成固定的 32 字节，解决这个问题
    
    流程：
    1. 原始密码 → SHA256 → 32 字节摘要
    2. 32 字节摘要 → bcrypt（加盐）→ 加密后的密码字符串
    """
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return bcrypt.hashpw(digest, bcrypt.gensalt()).decode("utf-8")


# ---------- 密码验证辅助函数 ----------
def _verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码：用相同的加密方式处理明文密码，然后与数据库中的密文比较
    """
    digest = hashlib.sha256(plain_password.encode("utf-8")).digest()
    try:
        return bcrypt.checkpw(digest, hashed_password.encode("utf-8"))
    except ValueError:
        return False


class UserService:

    # ---------- 对外暴露的密码加密方法 ----------
    @staticmethod
    def get_password_hash(password: str) -> str:
        return _hash_password(password)

    # ---------- 对外暴露的密码验证方法 ----------
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return _verify_password(plain_password, hashed_password)

    # ---------- 用户注册 ----------
    @staticmethod
    def register(db: Session, user_in: UserRegister) -> User:
        """
        注册新用户
        流程：
        1. 检查用户名是否已被注册
        2. 用 bcrypt 加密密码
        3. 创建用户记录并保存到数据库
        """
        # 检查用户名是否已存在
        existing_user = db.query(User).filter(User.username == user_in.username).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="用户名已经被注册")

        # 创建新用户
        new_user = User(
            username=user_in.username,
            password=_hash_password(user_in.password),  # 密码加密
            email=user_in.email,
            phone=user_in.phone,
        )
        db.add(new_user)        # 添加到会话
        db.commit()             # 提交到数据库
        db.refresh(new_user)    # 刷新获取自增 ID
        return new_user

    # ---------- 用户登录 ----------
    @staticmethod
    def login(db: Session, user_in: UserLogin) -> User:
        """
        用户登录验证
        流程：
        1. 根据用户名查找用户
        2. 验证密码是否正确
        """
        user = db.query(User).filter(User.username == user_in.username).first()
        if not user:
            raise HTTPException(status_code=400, detail="用户名或密码不存在")
        if not _verify_password(user_in.password, user.password):
            raise HTTPException(status_code=400, detail="用户名或密码错误")
        return user

    # ---------- 根据 ID 查询用户 ----------
    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> User | None:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return user