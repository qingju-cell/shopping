# Docker 本地部署开发文档

## 1. 这次改动解决什么问题

原项目可以在开发电脑上分别启动 Python 后端、Vue 前端、MySQL 和 Redis。现在新增的 Docker 配置把这四个运行部分固定为一套可复制的环境：换电脑或以后搬到云服务器时，使用同一条命令即可启动。

本次**没有修改任何业务代码**，也没有修改 `.env` 中的密码或密钥。

运行结构如下：

```text
浏览器 http://localhost:8080
        │
        ▼
Nginx（Vue 静态页面，并转发 /api 请求）
        │
        ▼
FastAPI 后端 http://backend:8000

        │                 │
        ▼                 ▼
     MySQL              Redis
        │
        ▼
  Chroma AI 知识库数据卷
```

## 2. 新增了哪些文件

| 文件 | 做什么 |
| --- | --- |
| `requirements.txt` | 记录后端和 AI 模块在容器中需要安装的 Python 包。 |
| `Dockerfile` | 描述 FastAPI 后端镜像怎样制作和启动。 |
| `.dockerignore` | 规定哪些文件不发送进 Docker 构建包。 |
| `docker-compose.yml` | 一次性启动 MySQL、Redis、后端和前端。 |
| `fronted/Dockerfile` | 打包 Vue 前端，并用 Nginx 提供页面。 |
| `fronted/nginx.conf` | Nginx 的访问与转发规则。 |
| `docs/docker-deployment-guide.md` | 本文档。 |

## 3. 每一步改动在做什么

### 第一步：`requirements.txt`——固定 Python 依赖

这个文件列出了从项目实际 `import` 语句整理出来的依赖，例如 FastAPI、SQLAlchemy、PyMySQL、Redis、Chroma、LangChain 和 LangGraph。

Docker 在制作后端环境时执行：

```dockerfile
RUN pip install --no-cache-dir -r requirements.txt
```

因此不需要在容器里手动逐个 `pip install`。以后你添加新的第三方 Python 包，也要同步写入这个文件。

### 第二步：根目录 `Dockerfile`——制作后端运行环境

它的流程是：

1. `FROM python:3.11-slim`：使用精简版 Python 3.11 Linux 环境。
2. `WORKDIR /app`：容器内的工作目录设为 `/app`。
3. 设置 Python 和 pip 环境变量，减少无用缓存并即时显示日志。
4. 复制并安装 `requirements.txt`。
5. 复制项目的 `app` 目录。
6. 用 `uvicorn app.main:app --host 0.0.0.0 --port 8000` 启动 FastAPI。

`0.0.0.0` 的意思是允许容器外的 Nginx 和浏览器访问后端；它不是公网地址。

### 第三步：`.dockerignore`——避免把不该打包的内容放进镜像

其中排除了：

- `.env`：密码和密钥不会写进镜像；运行时再由 Compose 注入。
- `.git`、编辑器目录、日志、Python 缓存：减少镜像体积。
- `fronted/node_modules`、`fronted/dist`：容器会自己安装和构建，避免使用你电脑上的产物。
- `app/AI/chroma_db`：AI 向量库改为 Docker 数据卷保存，避免被镜像固定住。

### 第四步：`fronted/Dockerfile`——构建前端并交给 Nginx

这是两阶段构建：

1. 第一阶段使用 Node 24，执行 `npm ci` 和 `npm run build`，得到 Vue 的 `dist` 静态文件。
2. 第二阶段使用轻量的 Nginx，只复制 `dist`，不带 Node 和源代码，因此镜像更小、更接近生产环境。

### 第五步：`fronted/nginx.conf`——前端路由和 API 代理

这个文件做两件事：

- `location /` 使用 `try_files ... /index.html`，保证 Vue 单页应用刷新页面不会出现 404。
- `location /api/` 将 API 请求转发到 Compose 内部的 `backend:8000`。

因此浏览器只需要认识一个地址 `http://localhost:8080`。前端代码仍使用 `/api`，不需要写死 `localhost:8000`。

### 第六步：`docker-compose.yml`——把四个服务连起来

#### `db`：MySQL 8

- 使用 `DB_NAME` 创建数据库，使用 `.env` 的 `DB_PASSWORD` 设置 root 密码。
- `MYSQL_ROOT_HOST: "%"` 允许后端容器连接 MySQL。
- `mysql_data` 数据卷保存数据库文件；停止容器不会清空数据。
- 健康检查成功后，后端才会启动，减少“数据库还没准备好”的报错。

当前项目本来就使用 MySQL `root` 用户，所以配置沿用它以方便你本地学习。真正部署到云服务器时，应再创建权限受限的应用用户，不直接让业务程序使用 root。

#### `redis`：缓存服务

- 使用 `.env` 中已有的 `REDIS_PASSWORD` 启动密码保护。
- `redis_data` 保存 Redis 数据。
- 健康检查确认 Redis 可以响应 `PONG` 后，后端再启动。

#### `backend`：FastAPI

- `build: .` 表示使用根目录 `Dockerfile` 制作镜像。
- `env_file: .env` 保留原有环境变量。
- 但将 `DB_HOST` 改为 `db`、`REDIS_HOST` 改为 `redis`：在 Docker 网络中，服务名就是访问地址，不能再用 `127.0.0.1`。
- `8000:8000` 让你在电脑上直接打开 `http://localhost:8000/docs` 查看接口文档。
- `chroma_data` 保存 AI 向量库；重启服务后知识库数据仍会保留。

#### `web`：Vue + Nginx

- 从 `fronted` 目录构建镜像。
- `8080:80` 表示电脑的 8080 端口对应 Nginx 的 80 端口。
- 浏览器访问 `http://localhost:8080` 即可打开前端。

## 4. 如何启动

在你平时能正常运行 `docker version` 的 PowerShell 中执行：

```powershell
cd D:\python\project\shopping
docker compose up --build
```

首次启动会下载 Python、Node、MySQL、Redis、Nginx 镜像并安装依赖，时间较长属于正常现象。看到各服务持续运行且没有报错后，访问：

- 前端：<http://localhost:8080>
- 后端接口文档：<http://localhost:8000/docs>

另开一个 PowerShell 窗口查看状态：

```powershell
cd D:\python\project\shopping
docker compose ps
```

## 5. 如何停止和再次启动

停止正在前台运行的服务，按 `Ctrl + C`。

保留数据库数据地停止全部服务：

```powershell
docker compose down
```

下次重新启动通常不必重新构建：

```powershell
docker compose up
```

修改了 Python 依赖、`Dockerfile` 或前端依赖时，才重新构建：

```powershell
docker compose up --build
```

> 不要随意执行 `docker compose down -v`。`-v` 会删除 MySQL、Redis 和 AI 知识库的数据卷，等同清空这些容器中的数据。

## 6. 测试数据与 AI 知识库

项目的 `seed_data.sql` 只有插入测试数据的语句，没有建表语句。后端启动时会通过 SQLAlchemy 自动建表，所以应先保证后端成功启动，再处理测试数据导入。

AI 向量库同样要先由项目的 AI 数据处理步骤生成；生成后它会写入 `chroma_data` 数据卷。这个初始化流程会在 Docker 服务成功启动后单独验证，避免因为空表或缺少 API Key 导入失败。

## 7. 常见问题

### 8080 或 8000 端口被占用

在 `docker-compose.yml` 中将左边端口改掉，例如 `"8081:80"`，然后通过 `http://localhost:8081` 访问。

### 看不到前端或后端报错

使用下面命令查看实时日志：

```powershell
docker compose logs -f backend
docker compose logs -f web
```

### 数据库连接失败

先运行 `docker compose ps`。只有 `db` 和 `redis` 显示健康后，`backend` 才应该启动。若仍有问题，保留最后 30 行错误日志用于排查，不要发送 `.env` 的密码。

## 8. 目前验证到哪里

配置文件已通过 Git 的空白格式检查。当前写文档的辅助环境没有可用的 Docker 命令，因此没有替你实际拉取镜像或启动容器；请在你已验证过 `docker version` 的本机 PowerShell 执行第 4 节命令。启动输出将用于完成下一轮验证。
