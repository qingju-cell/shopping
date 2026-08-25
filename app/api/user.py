# ============================================================
# user.py —— 用户模块路由
# 功能：定义用户相关的 HTTP 接口
# 接口列表：
#   - POST /api/user/register  用户注册
#   - POST /api/user/login     用户登录
#   - GET  /api/user/{user_id} 根据 ID 获取用户信息
# ============================================================

from fastapi import APIRouter
from fastapi.params import Depends
from sqlalchemy.orm import Session

from app.common.response import ApiResponse
from app.database import get_db
from app.schemas.user import UserRegister, UserResponse, UserLogin
from app.services.user_service import UserService

# 创建用户模块路由，前缀为 /user
# tags 用于在 Swagger 文档中分组
router = APIRouter(prefix="/user", tags=["用户模块"])


# ---------- 用户注册 ----------
@router.post("/register", summary="用户注册")
def register(user_in: UserRegister, db: Session = Depends(get_db)):
    """
    用户注册接口
    - user_in: 前端传来的注册数据（会自动校验）
    - db: 数据库会话（通过依赖注入自动获取）
    
    返回：用户信息（不含密码）
    """
    user = UserService.register(db=db, user_in=user_in)
    # UserResponse.model_validate(user) 将 ORM 对象转换为响应模型
    return ApiResponse.success(data=UserResponse.model_validate(user), msg="用户注册成功")


# ---------- 用户登录 ----------
@router.post("/login", summary="用户登录")
def login(user_in: UserLogin, db: Session = Depends(get_db)):
    """
    用户登录接口
    验证用户名和密码，成功后返回用户信息
    """
    user = UserService.login(db=db, user_in=user_in)
    return ApiResponse.success(data=UserResponse.model_validate(user), msg="用户登录成功")


# ---------- 根据 ID 获取用户信息 ----------
@router.get("/{user_id}", summary="根据用户ID获取用户")
def get_user_by_id(user_id: int, db: Session = Depends(get_db)):
    """
    根据用户 ID 查询用户详细信息
    """
    user = UserService.get_user_by_id(db=db, user_id=user_id)
    return ApiResponse.success(data=UserResponse.model_validate(user), msg="用户获取成功")