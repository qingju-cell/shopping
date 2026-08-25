import redis
from app.config import settings

redis_pool = redis.ConnectionPool.from_url(
    settings.redis_url,
    max_connections=10,
    decode_responses=True
)

redis_client = redis.Redis(connection_pool=redis_pool)


def redis_available() -> bool:
    """
    检查 Redis 是否可用
    尝试 ping，连不上返回 False，不抛异常
    """
    try:
        return redis_client.ping()
    except redis.ConnectionError:
        return False


def get_redis():
    return redis_client