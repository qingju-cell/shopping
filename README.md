# Shopping 购物系统

一个基于 **FastAPI + Vue 3 + Redis** 的全栈电商系统，包含完整的商品、分类、购物车、订单、用户模块，并集成了基于 **RAG（检索增强生成）的 AI 智能客服**。

本项目是学习 Redis 缓存三大问题（穿透 / 击穿 / 雪崩）防护的实战案例。

---

## 技术栈

### 后端
| 技术 | 用途 |
|------|------|
| FastAPI | Web 框架，自动生成 OpenAPI 文档 |
| SQLAlchemy + PyMySQL | ORM 框架 + MySQL 驱动 |
| Redis | 缓存 + 分布式锁 |
| Pydantic | 数据校验 |
| Uvicorn | ASGI 服务器 |

### 前端
| 技术 | 用途 |
|------|------|
| Vue 3 + TypeScript | 前端框架 |
| Element Plus | UI 组件库 |
| Pinia | 状态管理 |
| Vue Router | 路由 |
| Axios | HTTP 请求 |
| Vite | 构建工具 |

### AI 模块
| 技术 | 用途 |
|------|------|
| Chroma | 向量数据库（本地持久化） |
| 智谱 BigModel | 文本嵌入 / 向量化 |
| DeepSeek | 大语言模型对话 |

---

## 功能特性

### 业务功能
- **用户系统**：注册、登录、个人信息
- **商品管理**：商品分页列表、分类筛选、关键词搜索、商品详情
- **分类管理**：分类增删改查
- **购物车**：加入购物车、修改数量、删除商品
- **订单系统**：下单、订单列表、订单详情
- **AI 智能客服**：基于 RAG 的商品问答，知识库向量化检索 + 大模型生成回答

### 后端管理
- 商品 / 分类的后台增删改查

---

## 缓存防护设计（项目核心亮点）

针对 Redis 缓存的三大经典问题，本项目都做了实战级防护：

### 1. 缓存穿透（Cache Penetration）

> 查询数据库中根本不存在的数据，导致每次请求都穿透缓存打到 DB。

**防护措施（两道防线）**：

| 防线 | 实现 | 说明 |
|------|------|------|
| 第一道：参数校验 | 入口处校验 id > 0、page >= 1、page_size <= 100 等 | 不合法请求直接 400 拦截，连 Redis 都不查 |
| 第二道：缓存空对象 | DB 查不到时写入标记值 __NULL__，60 秒过期 | 不存在的 ID 第二次请求直接命中空对象缓存，不查 DB |

### 2. 缓存击穿（Cache Breakdown）

> 单个热点 key 过期瞬间，大量并发请求同时涌入打 DB。

**防护措施：互斥锁自旋**

```
请求进来 -> 查缓存未命中 -> SET NX 抢锁
  |- 抢到锁：查 DB -> 写缓存 -> 释放锁 -> 返回
  |- 没抢到：sleep 50ms -> 查缓存（别人可能已写好）-> 命中则返回
              最多自旋 5 次（共 250ms）
              还是没等到 -> 兜底直接查 DB
```

核心代码：`redis_client.set(lock_key, 1, nx=True, ex=lock_expire)`
- NX：key 不存在才设置成功（保证互斥，Redis 单线程命令原子性）
- EX：锁过期时间（防止拿锁的进程挂了导致死锁）

### 3. 缓存雪崩（Cache Avalanche）

> 大量 key 同时过期，或 Redis 实例宕机，导致请求指数级打 DB。

**防护措施**：

| 措施 | 实现 | 说明 |
|------|------|------|
| 过期时间打散 | TTL = 3600 + random.randint(-300, 300) | 避免大量 key 同一时刻过期，分散到 10 分钟窗口内 |
| Redis 不可用降级 | 所有 Redis 操作包 try-except + redis_available() 前置检查 | Redis 挂了直接走兜底 DB 查询，业务不中断 |
| 兜底必走 DB | 兜底查询逻辑在 if redis_available() 外面 | 无论 Redis 状态如何，最终一定能查到数据返回给用户 |

### 缓存与 DB 一致性

采用 **Cache Aside Pattern（先更新 DB，再删缓存）**：
- update_product / delete_product 改完 DB 后，删除对应的 products:detail:{id} 和所有 products:page:* 列表缓存
- 下次查询时缓存未命中，自然从 DB 重新加载最新数据

---

## 项目结构

```
shopping/
|-- app/                          # 后端
|   |-- main.py                   # FastAPI 入口
|   |-- config.py                 # 全局配置（从 .env 读取）
|   |-- database.py               # 数据库连接 + ORM 会话
|   |-- redis_client.py           # Redis 连接池 + 可用性检查
|   |-- api/                      # 路由层
|   |   |-- user.py / product.py / category.py
|   |   |-- cart.py / order.py / ai.py
|   |-- models/                   # SQLAlchemy ORM 模型
|   |-- schemas/                  # Pydantic 请求/响应模型
|   |-- services/                 # 业务逻辑层（缓存防护核心）
|   |   |-- product_service.py    # 商品（穿透+击穿+雪崩防护）
|   |   |-- category_service.py   # 分类（穿透+击穿+雪崩防护）
|   |-- common/                   # 通用组件（响应封装、异常处理）
|   |-- AI/                       # AI 智能客服模块（RAG）
|       |-- ai_core.py            # 大模型对话核心
|       |-- deepseek_emb.py       # 文本嵌入
|       |-- chroma_db/            # 本地向量数据库（已 gitignore）
|       |-- step1~step5_*.py      # RAG 流程分步脚本
|-- fronted/                      # 前端（Vue 3）
|   |-- src/
|   |   |-- views/                # 页面组件
|   |   |-- stores/               # Pinia 状态
|   |   |-- api/                  # 接口请求
|   |   |-- components/           # 公共组件（含 AI 聊天浮窗）
|-- .env                          # 环境变量（已 gitignore）
|-- .gitignore
```

---

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 16+
- MySQL 5.7+ / 8.0
- Redis 5.0+

### 1. 克隆项目

```bash
git clone https://github.com/qingju-cell/shopping.git
cd shopping
```

### 2. 后端启动

**安装依赖**：

```bash
pip install fastapi uvicorn sqlalchemy pymysql redis pydantic-settings python-dotenv
```

**配置环境变量**：

在项目根目录创建 `.env` 文件：

```env
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=你的数据库密码
DB_NAME=shopping

REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
```

**创建数据库**：

```sql
CREATE DATABASE shopping DEFAULT CHARACTER SET utf8mb4;
```

**启动后端**：

```bash
python -m app.main
```

启动后访问 http://localhost:8000/docs 查看自动生成的 API 文档。

### 3. 前端启动

```bash
cd fronted
npm install
npm run dev
```

访问 http://localhost:5173

### 4. AI 模块配置（可选）

如果需要使用 AI 智能客服功能：

```bash
cd app/AI
cp .env.example .env
```

在 `app/AI/.env` 中填入你的 API 密钥：

```env
OPENAI_API_KEY=你的DeepSeek_API_Key
OPENAI_BASE_URL=https://api.deepseek.com/v1
BIGMODEL_API_KEY=你的智谱BigModel_API_Key
```

---

## 环境变量说明

| 变量 | 说明 | 默认值 |
|------|------|--------|
| DB_HOST | MySQL 主机 | - |
| DB_PORT | MySQL 端口 | - |
| DB_USER | MySQL 用户名 | - |
| DB_PASSWORD | MySQL 密码 | - |
| DB_NAME | 数据库名 | - |
| REDIS_HOST | Redis 主机 | 127.0.0.1 |
| REDIS_PORT | Redis 端口 | 6379 |
| REDIS_PASSWORD | Redis 密码 | 空 |
| REDIS_DB | Redis DB 编号 | 0 |
| REDIS_CACHE_EXPIRE | 正常缓存过期时间（秒） | 3600 |
| REDIS_NULL_CACHE_EXPIRE | 空对象缓存过期时间（秒） | 60 |
| OPENAI_API_KEY | DeepSeek API Key（AI 模块） | - |
| OPENAI_BASE_URL | DeepSeek API 地址 | https://api.deepseek.com/v1 |
| BIGMODEL_API_KEY | 智谱 BigModel API Key（AI 模块） | - |

---

## API 接口概览

所有接口前缀：`/api`

| 模块 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 用户 | POST | /api/users/register | 注册 |
| 用户 | POST | /api/users/login | 登录 |
| 商品 | GET | /api/products | 分页查询商品列表 |
| 商品 | GET | /api/products/{id} | 商品详情 |
| 商品 | POST | /api/products | 新增商品 |
| 商品 | PUT | /api/products/{id} | 更新商品 |
| 商品 | DELETE | /api/products/{id} | 删除商品（软删除） |
| 分类 | GET | /api/categories | 分类列表 |
| 分类 | POST | /api/categories | 新增分类 |
| 分类 | PUT | /api/categories/{id} | 更新分类 |
| 分类 | DELETE | /api/categories/{id} | 删除分类 |
| 购物车 | GET | /api/cart | 购物车列表 |
| 购物车 | POST | /api/cart | 加入购物车 |
| 购物车 | PUT | /api/cart/{id} | 修改数量 |
| 购物车 | DELETE | /api/cart/{id} | 删除购物车商品 |
| 订单 | POST | /api/orders | 下单 |
| 订单 | GET | /api/orders | 订单列表 |
| 订单 | GET | /api/orders/{id} | 订单详情 |
| AI | POST | /api/ai/chat | AI 对话 |

完整接口文档：启动后端后访问 `http://localhost:8000/docs`

---

## 数据库表

| 表名 | 说明 |
|------|------|
| users | 用户表 |
| categories | 商品分类表 |
| products | 商品表 |
| cart_items | 购物车表 |
| orders | 订单表 |
| order_items | 订单明细表 |
| ai_chat_messages | AI 聊天消息记录表 |
