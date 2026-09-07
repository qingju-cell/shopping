"""Prometheus 指标定义、HTTP 请求采集与真实 AI Token 用量采集。"""

from collections.abc import Mapping
from time import perf_counter

from prometheus_client import Counter, Histogram
from starlette.requests import Request

HTTP_REQUESTS = Counter(
    "shopping_http_requests_total",
    "Total HTTP requests handled by the shopping API.",
    ["method", "path", "status"],
)

HTTP_REQUEST_DURATION = Histogram(
    "shopping_http_request_duration_seconds",
    "Time spent handling HTTP requests in seconds.",
    ["method", "path", "status"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

AI_TOKENS = Counter(
    "shopping_ai_tokens_total",
    "Token usage reported by the LLM provider.",
    ["operation", "token_type"],
)


def request_start_time() -> float:
    """返回单调计时器的起点，避免系统时钟变化影响耗时统计。"""
    return perf_counter()


def record_http_request(request: Request, status_code: int, started_at: float) -> None:
    """记录一次已完成 HTTP 请求的数量、状态码和耗时。"""
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)
    labels = {
        "method": request.method,
        "path": path,
        "status": str(status_code),
    }
    HTTP_REQUESTS.labels(**labels).inc()
    HTTP_REQUEST_DURATION.labels(**labels).observe(perf_counter() - started_at)


def extract_llm_token_usage(response: object) -> dict[str, int] | None:
    """从 LangChain/DeepSeek 原始响应中提取服务商实际返回的 Token 用量。

    LangChain 新版通常将用量放在 usage_metadata；部分兼容响应将其放在
    response_metadata.token_usage。没有该字段时返回 None，绝不进行估算。
    """
    usage = getattr(response, "usage_metadata", None)
    if not isinstance(usage, Mapping):
        response_metadata = getattr(response, "response_metadata", {})
        if isinstance(response_metadata, Mapping):
            usage = response_metadata.get("token_usage")

    if not isinstance(usage, Mapping):
        return None

    def token_count(*names: str) -> int:
        for name in names:
            value = usage.get(name)
            if isinstance(value, (int, float)) and value >= 0:
                return int(value)
        return 0

    input_tokens = token_count("input_tokens", "prompt_tokens")
    output_tokens = token_count("output_tokens", "completion_tokens")
    total_tokens = token_count("total_tokens") or input_tokens + output_tokens
    return {
        "input": input_tokens,
        "output": output_tokens,
        "total": total_tokens,
    }


def record_llm_token_usage(response: object, operation: str) -> bool:
    """将服务商实际返回的 Token 用量累计到 Prometheus。

    返回 True 表示成功获得真实用量；False 表示该响应不包含用量字段。
    """
    usage = extract_llm_token_usage(response)
    if usage is None:
        return False

    for token_type, value in usage.items():
        if value > 0:
            AI_TOKENS.labels(operation=operation, token_type=token_type).inc(value)
    return True