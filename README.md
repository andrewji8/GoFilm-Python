

```markdown
#  GoFilm-Python

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.0-009688.svg)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0.36-red.svg)](https://www.sqlalchemy.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> 基于 **FastAPI + SQLAlchemy 2.0 异步 + Redis + APScheduler** 打造的高性能、高并发在线影视资源采集与聚合后端。

---

##  目录 (Table of Contents)

- [✨ 核心特性](#-核心特性)
- [🛠️ 技术栈](#️-技术栈)
- [🚀 快速开始](#-快速开始)
  - [方案 A：本地开发 (Windows 推荐)](#方案-a本地开发-windows-推荐)
  - [方案 B：Docker 一键部署 (生产推荐)](#方案-bdocker-一键部署-生产推荐)
- [⚙️ 环境变量配置](#️-环境变量配置)
- [📚 API 文档与核心接口](#-api-文档与核心接口)
- [⏱️ 定时任务说明](#️-定时任务说明)
- [️ 生产环境最佳实践](#️-生产环境最佳实践)
- [📜 许可证](#-许可证)

---

## ✨ 核心特性

- ⚡ **极致异步**：全链路 `async/await`，基于 `httpx` 连接池复用与 `orjson` 极速序列化。
- 🛡️ **数据强一致**：原生 MySQL `ON DUPLICATE KEY UPDATE` 批量 Upsert，彻底消除并发竞态条件。
- 🌐 **多源智能聚合**：基于 64 位归一化哈希 (`mid`)，完美跨站点聚合主/从播放源。
- 🚀 **内存安全**：采用 Redis `HSCAN` 游标分批同步，杜绝海量数据同步时的 OOM 风险。
-  **Windows 友好**：默认采用纯 Python `aiomysql` 驱动，彻底告别 C++ 编译环境地狱。

---

## 🛠️ 技术栈

| 组件 | 版本 | 核心作用 |
| :--- | :--- | :--- |
| **Python** | `3.11+` | 运行时环境 |
| **FastAPI** | `0.115.0` | 高性能异步 Web 框架 |
| **SQLAlchemy** | `2.0.36` | 现代异步 ORM 引擎 |
| **aiomysql** | `0.2.0` | 纯 Python MySQL 异步驱动 |
| **Redis** | `5.2.0` | 采集任务暂存与高速缓存 |
| **APScheduler** | `3.10.4` | 健壮的定时采集与同步调度 |
| **httpx** | `0.27.2` | 异步 HTTP 客户端 (带重试机制) |
| **lxml** | `5.3.0` | 极速 XML/HTML 解析 |
| **orjson** | `3.10.7` | Rust 编写的高性能 JSON 引擎 |
| **pydantic-settings**| `2.6.1` | 类型安全的配置管理 |

---

## 🚀 快速开始

### 方案 A：本地开发 (Windows 推荐)

适合需要频繁修改代码、利用热更新 (`--reload`) 进行开发的场景。

**1. 创建并激活虚拟环境**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 💡 若提示“无法加载文件...”，请先解除执行策略限制：
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**2. 安装项目依赖**

```powershell
pip install -r requirements.txt
```

**3. 配置环境变量**

```powershell
Copy-Item .env.example .env
```

> 请打开 `.env` 文件，根据本地情况修改数据库及 Redis 密码。

**4. 启动基础服务 (MySQL + Redis)**

```powershell
docker compose up -d mysql redis
```

**5. ⚠️ 初始化数据库约束 (关键步骤)**

> [!IMPORTANT]
> 为支持高效的批量 Upsert，必须为从站表添加联合唯一索引。请在 PowerShell 中执行以下命令（请确保 `.env` 中的 `MYSQL_ROOT_PASSWORD` 已正确设置）：
> 
> ```powershell
> docker exec -i gofilm-mysql mysql -u root -p"%MYSQL_ROOT_PASSWORD%" gofilm -e "ALTER TABLE slave_movie_info ADD CONSTRAINT uq_slave_sid_mid UNIQUE (sid, mid);"
> ```

**6. 启动 FastAPI 应用**

```powershell
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

---

### 方案 B：Docker 一键部署 (生产推荐)

适合服务器部署，环境完全隔离，开箱即用。以下命令请在 **PowerShell** 或 **Linux 终端** 中执行：

**1. 进入项目目录并准备环境**

```powershell
# 进入项目根目录 (请替换为您服务器的实际路径)
cd D:\aistudypython\GoFilm-Python 

# 确保 .env 文件已存在并配置好密码
if (!(Test-Path .env)) { Copy-Item .env.example .env }
```

**2. 一键构建并启动所有服务**

```powershell
# 后台构建并启动 App、MySQL 和 Redis
docker compose up -d --build

# 等待 15 秒，确保 MySQL 和 Redis 完成健康检查并完全就绪
Start-Sleep -Seconds 15
```

**3. ⚠️ 初始化数据库约束 (关键步骤)**

> [!IMPORTANT]
> 纯 Docker 部署时，必须通过命令行进入 MySQL 容器执行唯一索引初始化，否则数据同步会报错！

```powershell
# 进入 MySQL 容器并执行 ALTER TABLE 语句
# (请将下方引号内的密码替换为您在 .env 中设置的真实 MYSQL_ROOT_PASSWORD)
docker exec -i gofilm-mysql mysql -u root -p"root_secret_pwd_change_me" gofilm -e "ALTER TABLE slave_movie_info ADD CONSTRAINT uq_slave_sid_mid UNIQUE (sid, mid);"
```

**4. 验证服务状态与日志**

```powershell
# 查看所有容器状态 (确保 gofilm-app, gofilm-mysql, gofilm-redis 均为 healthy/running)
docker compose ps

# 实时查看应用运行日志，确认无报错启动
docker compose logs -f app
```

---

## ⚙️ 环境变量配置

项目使用 `pydantic-settings` 管理配置，支持 `__` 嵌套分隔符。核心变量如下：

| 变量名                   | 默认值                 | 说明                                  |
|:--------------------- |:------------------- |:----------------------------------- |
| `APP_ENV`             | `dev`               | 运行环境 (`dev` / `prod`)               |
| `MYSQL__HOST`         | `127.0.0.1`         | MySQL 主机 *(Docker部署时自动覆写为 `mysql`)* |
| `MYSQL__PORT`         | `3306`              | MySQL 端口                            |
| `MYSQL__USER`         | `gofilm`            | MySQL 用户名                           |
| `MYSQL__PASSWORD`     | `gofilm_secret_pwd` | MySQL 密码 *(生产环境务必修改)*               |
| `MYSQL__DB`           | `gofilm`            | 数据库名称                               |
| `REDIS__HOST`         | `127.0.0.1`         | Redis 主机 *(Docker部署时自动覆写为 `redis`)* |
| `SPIDER__CONCURRENCY` | `8`                 | 爬虫最大并发数                             |
| `SPIDER__DELAY_MS`    | `500`               | 单请求间隔 (毫秒)，防封禁                      |

---

## 📚 API 文档与核心接口

应用启动后，可通过内置的交互式文档进行测试：

- 📘 **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- 📕 **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

| 方法     | 路径                       | 描述                  |
|:------:|:------------------------ |:------------------- |
| `GET`  | `/api/v1/movies`         | 分页获取影片列表 (支持分类筛选)   |
| `GET`  | `/api/v1/movie/{mid}`    | 获取影片详情 (自动聚合多站点播放源) |
| `POST` | `/api/v1/spider/collect` | 提交后台异步采集任务          |

---

## ⏱️ 定时任务说明

系统内置了健壮的 APScheduler 调度器，默认配置如下：

| 任务名称       | 执行时间        | 核心逻辑                                       |
|:---------- |:----------- |:------------------------------------------ |
| **每日增量采集** | 每天 `03:00`  | 遍历所有启用的采集源，抓取最新 3 页数据暂存至 Redis             |
| **全量同步**   | 每周日 `04:00` | 使用 `HSCAN` 游标分批将 Redis 缓存安全 Upsert 至 MySQL |

---

## 🛡️ 生产环境最佳实践

1. 🔒 **强化安全**：务必修改 `.env` 中的所有默认密码，尤其是 `MYSQL_ROOT_PASSWORD`。
2. 🌐 **反向代理**：生产环境请勿直接暴露 Uvicorn，建议使用 Nginx 或 Traefik 进行反向代理并配置 HTTPS/TLS。
3. 💾 **定期备份**：配置 Cron 任务，定期备份 MySQL 数据库 (`mysqldump`) 和 Redis 持久化文件 (`dump.rdb` / `appendonly.aof`)。
4. **监控告警**：建议接入 Prometheus + Grafana 或 ELK 栈，监控 API 响应延迟、数据库连接池水位及后台任务执行状态。

---

## 📜 许可证

本项目基于 [MIT License](LICENSE) 开源协议发布。您可以自由地使用、修改和分发本软件。
