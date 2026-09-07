# API 自动化测试说明

本项目提供一组只读 API 冒烟测试，验证 Docker 启动后最基本的服务能力：

- FastAPI 文档可访问；
- 分类接口返回有效的整数 `parent_id`；
- 商品分页接口可返回数据；
- 商品详情接口可返回对应商品。

## 在 Docker 中运行

先启动项目：

```powershell
docker compose up -d
```

再运行测试：

```powershell
docker compose exec -T backend pytest -q
```

## 生成 JUnit 测试报告

```powershell
docker compose exec -T backend pytest -q --junitxml=/tmp/junit.xml
```

这组测试只发送 GET 请求，不会修改现有商品、分类、用户或订单。

### 复制 JUnit 报告到本机

JUnit 文件先生成在容器的临时目录。生成后立刻运行下面两行，把它复制到本机项目的 `reports/junit.xml`：

```powershell
New-Item -ItemType Directory -Path reports -Force
docker compose cp backend:/tmp/junit.xml reports/junit.xml
```

`reports/*.xml` 已被 Git 忽略，因为它是每次测试自动生成的结果。
## GitHub Actions 自动测试

仓库中的 `.github/workflows/docker-api-tests.yml` 会在推送到 `main` 分支或创建针对 `main` 的 Pull Request 时自动执行：

1. GitHub 创建一台临时 Ubuntu 电脑；
2. 复制 `.env.ci` 为 `.env`，其中只有 CI 临时密码，不含真实密钥；
3. 构建并启动 Docker Compose 的四个服务；
4. 等待 FastAPI 的 `/health` 接口可访问；
5. 运行 pytest，并上传 JUnit 报告作为可下载的构建产物；
6. 停止临时容器。GitHub 的临时机器随后会销毁，不会访问本机 Docker 数据。