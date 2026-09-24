<div align="center">

# Signal Feed API

**一个轻量、带权限控制、支持历史快照的结构化信号发布与读取服务**

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Render](https://img.shields.io/badge/Deploy-Render-46E3B7?logo=render&logoColor=black)](https://render.com/)
[![Neon](https://img.shields.io/badge/PostgreSQL-Neon-00E699?logo=postgresql&logoColor=white)](https://neon.tech/)

[在线 API](https://api-sender-v68f.onrender.com) · [Swagger 文档](https://api-sender-v68f.onrender.com/docs) · [接收端安装指南](./RECEIVER_AGENT.md)

</div>

Signal Feed API 用于在策略发布端与多个接收端之间安全地传递结构化信号。每条信号由 **channel + asset + as_of_date** 唯一标识；同日重发会更新当日快照，不同日期的数据会分别保留。

## 工作流程

```mermaid
flowchart LR
    Sender["策略程序 / Sender"] -->|"POST /v1/publish<br/>Publish Key"| API["Signal Feed API<br/>FastAPI · Render"]
    API -->|"按 channel + asset + as_of_date 写入"| DB[("Neon PostgreSQL<br/>持久化信号快照")]
    Reader["接收端 Agent"] -->|"GET /v1/latest<br/>account:token"| API
    ACL["Reader ACL<br/>账号与信号权限"] -.->|"鉴权"| API
    DB -->|"读取最新或指定日期快照"| API
    API -->|"返回独立信号 JSON"| Reader
```

## 特性

- 独立信号流：每次请求只发布或返回一个 **channel + asset** 信号。
- 历史快照：以 **as_of_date** 区分日期，同日更新、跨日保留。
- 持久化存储：配置 Neon PostgreSQL 后，休眠、重启和重新部署不会丢失信号。
- 细粒度权限：每个接收方使用独立的 **account:token**，可授权一个或多个信号。
- 通配授权：支持 `industry:*`、`*:electronics` 和 `*:*`。
- Agent 友好：附带只读 Skill、命令行脚本和紧凑信号卡片。
- 自动文档：FastAPI 自动生成 Swagger/OpenAPI 文档。
- 安全兼容：使用常量时间 Token 比较，并兼容旧版 READ_API_KEYS 迁移。

## 当前服务

~~~text
https://api-sender-v68f.onrender.com
~~~

| 方法 | 路径 | 说明 | 鉴权 |
| --- | --- | --- | --- |
| GET | /health | 服务和存储状态 | 无 |
| POST | /v1/publish | 发布或更新一个日期快照 | Publish Key |
| GET | /v1/latest?channel=...&asset=... | 读取该信号的最新日期快照 | Reader 凭据 |
| GET | /v1/latest?channel=...&asset=...&as_of_date=... | 读取指定日期快照 | Reader 凭据 |
| GET | /docs | Swagger 文档 | 无 |

> Render 免费实例可能在闲置后休眠，首次访问通常会比后续请求慢。

## 快速开始

### 1. 安装并启动

需要 Python 3.10 或更高版本。

~~~powershell
git clone https://github.com/JaneShine/api-sender.git
cd api-sender
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
~~~

设置环境变量后启动：

~~~powershell
$env:PUBLISH_API_KEY="替换为发布端密钥"
$env:READ_API_ACL='{"alice":{"token":"替换为Alice的Token","allow":["industry:electronics"]}}'
$env:DATABASE_URL="postgresql://user:password@host/database?sslmode=require"
python -m uvicorn main:app --reload
~~~

打开 <http://127.0.0.1:8000/docs> 即可在线调试。

生成随机 Token：

~~~powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
~~~

### 2. 发布信号

~~~http
POST /v1/publish
Authorization: Bearer <PUBLISH_API_KEY>
Content-Type: application/json
~~~

~~~json
{
  "channel": "industry",
  "asset": "electronics",
  "strategy_id": "industry_electronics",
  "strategy_name": "量化行业策略：电子（申信）",
  "strategy_version": "1.0",
  "universe": "elec",
  "as_of_date": "2026-09-23",
  "signals": {
    "macro_bull": false,
    "prosperity_bull": true,
    "trading_bull": true,
    "composite_signal": 1
  },
  "owner": "jxxie@efund"
}
~~~

服务端会自动补充：

- **id**：本次发布的唯一 ID。
- **published_at**：UTC 发布时间。

**owner** 与 **as_of_date** 为必填字段。模型允许携带额外 JSON 字段，便于后续扩展。

### 3. 读取信号

读取最新日期：

~~~http
GET /v1/latest?channel=industry&asset=electronics
Authorization: Bearer alice:<Alice的实际Token>
~~~

读取指定日期：

~~~http
GET /v1/latest?channel=industry&asset=electronics&as_of_date=2026-09-23
Authorization: Bearer alice:<Alice的实际Token>
~~~

## 数据版本规则

数据库主键是：

~~~text
channel + asset + as_of_date
~~~

| 发布情况 | 结果 |
| --- | --- |
| 相同频道、资产和日期 | 更新该日期的快照 |
| 相同频道和资产，不同日期 | 新增快照并保留旧日期 |
| 查询不带 as_of_date | 返回该频道和资产日期最新的快照 |
| 查询带 as_of_date | 返回指定日期快照；不存在则返回 404 |

应用启动时会自动创建 **signal_snapshots** 表，并迁移旧版 **latest_signals** 数据，无需手工执行 SQL。未配置 DATABASE_URL 时会退回内存模式，但服务重启后数据会丢失。

## Reader ACL

每个接收方只需要一个 Token，一个 Token 可以拥有多个 **channel:asset** 权限。Render 环境变量 READ_API_ACL 示例：

~~~json
{
  "alice": {
    "token": "Alice的实际随机Token",
    "allow": [
      "industry:electronics",
      "industry:automobile"
    ]
  },
  "bob": {
    "token": "Bob的实际随机Token",
    "allow": [
      "industry:electronics"
    ]
  }
}
~~~

在 Render 中应保存为单行 JSON。

| 权限模式 | 含义 |
| --- | --- |
| industry:electronics | 只允许读取这一组信号 |
| industry:* | 允许读取 industry 下全部资产 |
| *:electronics | 允许读取所有频道的 electronics |
| *:* | 允许读取全部信号 |

旧环境变量 READ_API_KEYS 仅用于平滑迁移，旧 Key 默认拥有全量读取权限。所有客户端迁移至 ACL 后，应从 Render 删除它。

## 接收端 Agent / Skill

仓库提供 [signal-feed-reader](./skills/signal-feed-reader) 只读 Skill。完整的一键安装、凭据配置和 Agent 指令见：

> [RECEIVER_AGENT.md — 接收端 Agent 一键接入](./RECEIVER_AGENT.md)

安装并配置后，接收方可以直接说：

~~~text
读取 industry 频道 electronics 资产的最新信号
~~~

或显式调用：

~~~text
$signal-feed-reader 读取 industry/electronics 在 2026-09-23 的信号
~~~

Skill 会展示紧凑信号卡片，并始终包含 **owner**；只有明确要求时才展开原始 JSON。

## 配置项

| 环境变量 | 必需 | 说明 |
| --- | --- | --- |
| PUBLISH_API_KEY | 是 | 发布接口 Bearer Key，只交给发布端 |
| READ_API_ACL | 推荐 | Reader 账号、Token 和权限的 JSON 映射 |
| DATABASE_URL | 生产环境推荐 | Neon/PostgreSQL 连接串，用于持久化 |
| READ_API_KEYS | 否 | 旧版 Reader Key 兼容项，迁移完成后删除 |

接收端 Skill 使用：

| 环境变量 | 说明 |
| --- | --- |
| SIGNAL_API_USER | Reader account |
| SIGNAL_API_TOKEN | Reader token |
| SIGNAL_API_BASE_URL | API 地址，默认指向当前 Render 服务 |
| SIGNAL_DEFAULT_CHANNEL | 可选的默认频道 |
| SIGNAL_DEFAULT_ASSET | 可选的默认资产 |

## Render + Neon 部署

1. 在 Neon 创建 PostgreSQL 项目并复制 pooled connection string。
2. 在 Render 创建 Web Service，并连接本 GitHub 仓库。
3. 设置启动命令：**uvicorn main:app --host 0.0.0.0 --port $PORT**。
4. 在 Render Environment 中配置 PUBLISH_API_KEY、READ_API_ACL 和 DATABASE_URL。
5. 部署完成后访问 /health，确认 storage 为 postgresql。
6. 分别测试发布、授权读取、越权读取和指定日期读取。

健康检查示例：

~~~json
{
  "status": "ok",
  "service": "signal-feed-api",
  "storage": "postgresql"
}
~~~

## 测试

smoke_test.py 会先发布示例信号，再使用 Reader 凭据读取并校验内容：

~~~powershell
$env:PUBLISH_API_KEY="发布端密钥"
$env:SIGNAL_API_USER="Reader账号"
$env:SIGNAL_API_TOKEN="Reader Token"
$env:SIGNAL_API_BASE_URL="https://api-sender-v68f.onrender.com"
python smoke_test.py
~~~

成功时，脚本会输出发布状态、读取状态、信号内容、owner、id 和 published_at，不会打印凭据。

## 状态码

| 状态码 | 含义 |
| --- | --- |
| 200 | 请求成功 |
| 400 | 查询参数组合错误 |
| 401 | 缺少认证或 Bearer 格式错误 |
| 403 | 凭据错误或没有目标信号权限 |
| 404 | 尚未发布对应信号或指定日期不存在 |
| 503 | PostgreSQL 暂时不可用 |

## 安全建议

- 不要把真实 Token、Authorization 请求头或数据库连接串提交到 Git。
- 发布端和接收端使用不同凭据；PUBLISH_API_KEY 绝不提供给接收方。
- 每个接收方使用独立账号和 Token，便于单独撤销。
- 调整权限时只需修改 allow；只有 Token 泄露时才需要轮换 Token。
- 本地秘密文件必须加入 .gitignore，生产秘密只保存在 Render Environment。
- 权限变更后应使用允许和禁止的信号各测试一次。

## 项目结构

~~~text
.
├── main.py                         # FastAPI 服务、ACL 与 PostgreSQL 存储
├── smoke_test.py                   # 发布 + 读取端到端测试
├── requirements.txt
├── RECEIVER_AGENT.md               # 接收端安装与使用文档
└── skills/
    └── signal-feed-reader/         # Agent 只读 Skill
~~~

## 致谢

本项目当前依靠以下平台的免费方案运行，感谢它们为小型项目和原型验证提供基础设施支持：

- [Render](https://render.com/) — 托管并自动部署 FastAPI Web Service。
- [Neon](https://neon.tech/) — 提供 Serverless PostgreSQL 持久化存储。

也感谢 [FastAPI](https://fastapi.tiangolo.com/)、[Uvicorn](https://www.uvicorn.org/) 和 [psycopg](https://www.psycopg.org/) 等开源项目。

---

<div align="center">

Made for simple, secure signal delivery.

</div>