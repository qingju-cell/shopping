# Prometheus + Grafana 本地监控说明

## 启动后访问

执行：

```powershell
docker compose up -d --build
```

打开：

- Prometheus：`http://localhost:9090`
- Grafana：`http://localhost:3000`

Grafana 本地默认账号为 `admin`，密码也为 `admin`。如果要修改密码，在根目录 `.env` 中设置 `GRAFANA_ADMIN_PASSWORD` 后重新创建 Grafana 容器。

## 数据流

```text
浏览器请求接口
  -> FastAPI 中间件记录次数、状态码、耗时
  -> /metrics 输出 Prometheus 格式文本
  -> Prometheus 每 5 秒抓取 backend:8000/metrics
  -> Grafana 使用 PromQL 查询 Prometheus 并绘制图表
```

## 采集的指标

| 指标 | 含义 | 用途 |
| --- | --- | --- |
| `shopping_http_requests_total` | 已完成 HTTP 请求总数 | 计算 QPS、累计访问量、错误率 |
| `shopping_http_request_duration_seconds` | HTTP 请求耗时直方图 | 计算 p95 延迟 |

每条指标带有 `method`、`path`、`status` 标签。例如商品详情路由记录为 `/products/{product_id}`，不会为每个商品 ID 生成一条新时间序列。

## Grafana 预置面板

| 面板 | PromQL | 含义 |
| --- | --- | --- |
| 接口 QPS | `sum(rate(shopping_http_requests_total[1m]))` | 最近一分钟内每秒处理多少请求 |
| 接口 p95 延迟 | `histogram_quantile(0.95, sum by (le) (rate(shopping_http_request_duration_seconds_bucket[5m])))` | 95% 的请求在该耗时以内完成 |
| 5xx 错误率 | `sum(rate(shopping_http_requests_total{status=~"5.."}[5m])) / clamp_min(sum(rate(shopping_http_requests_total[5m])), 0.001)` | 服务端异常请求所占比例 |
| 累计接口请求数 | `sum(shopping_http_requests_total)` | 后端启动以来处理的请求总数 |

## 如何制造图表数据

打开前端页面、多次刷新商品列表和详情页，再回到 Grafana。Prometheus 每 5 秒采集一次，因此图表会稍有延迟。

## AI Token 用量

后端现在会在每次真实 DeepSeek/LangChain 调用后，读取原始 `AIMessage` 的 `usage_metadata`（兼容 `response_metadata.token_usage`）。它只接受服务商返回的 `input_tokens`、`output_tokens`、`total_tokens`；没有该字段时不记录，也不会按字符数估算。

指标名为 `shopping_ai_tokens_total`，带有：

- `operation`：`intent_classification`、`query_expansion`、`product_answer`、`chat_answer`；
- `token_type`：`input`、`output`、`total`。

Grafana 的两个 Token 面板分别展示 Token/秒，以及最近一小时按调用环节累计的总 Token。只有实际使用 AI 客服、且服务商响应包含用量字段后，图表才会有数据；普通商品页访问不会产生 AI Token。

测试中的模拟响应只验证提取逻辑，不调用 DeepSeek，因此不会消耗 API 额度。