# ============================================================
# config.py —— 全局配置文件
# 功能：读取环境变量（.env 文件），提供数据库、服务器等配置
# 技术栈：pydantic-settings（自动从 .env 文件加载配置）
# 使用方式：from app.config import settings
# ============================================================

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


# Settings 类：继承 BaseSettings，自动从 .env 文件读取配置
# 每个属性对应 .env 文件中的一个变量
class Settings(BaseSettings):
    # ---------- 服务器配置 ----------
    HOST: str = '0.0.0.0'       # 服务监听地址，0.0.0.0 表示监听所有网卡
    PORT: int = 8000            # 服务端口号
    ENV: str = 'development'    # 运行环境：development / production

    # ---------- 数据库配置 ----------
    # 以下变量必须在 .env 文件中配置，没有默认值
    DB_PORT: int                # MySQL 端口，默认 3306
    DB_USER: str                # MySQL 用户名
    DB_PASSWORD: str            # MySQL 密码
    DB_NAME: str                # 数据库名
    DB_CHARSET: str = 'utf8mb4' # 数据库字符集，支持中文
    DB_HOST: str                # MySQL 主机地址，通常是 localhost

    # ---------- Redis 配置 ----------
    REDIS_HOST: str = '127.0.0.1'
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ''
    REDIS_DB: int = 0
    REDIS_CACHE_EXPIRE: int = 3600

    # ---------- 计算属性：拼接数据库连接 URL ----------
    # 格式：mysql+pymysql://用户名:密码@主机:端口/数据库名?charset=utf8mb4
    @property
    def db_url(self):
        return f'mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset={self.DB_CHARSET}'

    @property
    def redis_url(self):
        if self.REDIS_PASSWORD:
            return f'redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}'
        return f'redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}'

    # ---------- 指定 .env 文件路径 ----------
    # config.py 在 app/ 目录下，向上一级就是项目根目录
    _project_root = Path(__file__).resolve().parent.parent
    _env_file_path = os.path.join(_project_root, ".env")
    # SettingsConfigDict 告诉 pydantic 去哪里找 .env 文件
    # extra="ignore" 表示 .env 中有多余变量时不报错
    model_config = SettingsConfigDict(env_file=_env_file_path, extra="ignore")


# 创建全局 settings 实例，其他模块通过 settings.HOST / settings.db_url 等获取配置
settings = Settings()