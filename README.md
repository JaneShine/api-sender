# API Sender

Signal Feed API 用于发布和读取彼此独立的结构化信号。每个信号流由 channel + asset 唯一标识。

GitHub：<https://github.com/JaneShine/api-sender>

接收端一键安装和 Agent 使用说明见 [RECEIVER_AGENT.md](./RECEIVER_AGENT.md)。

## 当前服务

~~~text
https://api-sender-v68f.onrender.com
~~~

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /health | 健康检查 |
| POST | /v1/publish | 发布信号，需要 Publish Key |
| GET | /v1/latest?channel=...&asset=... | 读取指定信号，需要 Reader 凭据 |
| GET | /docs | Swagger 文档 |

## 数据模型

每个 channel + asset 是独立信号流，例如 industry/electronics、industry/automobile 和 macro/rates。发布新的 industry/electronics 只更新该组合，不覆盖其他组合。API 每次只返回一个独立 JSON。

同一组合目前只保留最新一条。服务重启或重新部署后，所有内存信号都会清空。

## 本地运行

要求 Python 3.10 或更高版本。

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:PUBLISH_API_KEY="替换为发布Key"
$env:READ_API_KEYS="旧版兼容Key"
$env:READ_API_ACL='{"alice":{"token":"替换为Alice的Token","allow":["industry:electronics"]}}'
python -m uvicorn main:app --reload
~~~

打开 <http://127.0.0.1:8000/docs>。

生成 Token：

~~~powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
~~~

## 发布信号

请求：

~~~http
POST /v1/publish
Authorization: Bearer <PUBLISH_API_KEY>
Content-Type: application/json
~~~

Body 示例：

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
    "trading_bull": true
  },
  "owner": "jxxie@efund"
}
~~~

## Reader ACL

一个用户只需一个 Token，同一个 Token 可以拥有多个信号权限。Render 环境变量 READ_API_ACL 示例：

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

Render 中需要填写为单行 JSON。

| 权限 | 含义 |
| --- | --- |
| industry:electronics | 精确读取一个信号 |
| industry:* | 读取 industry 下所有资产 |
| *:electronics | 读取所有频道的 electronics |
| *:* | 读取全部信号 |

认证和读取示例：

~~~http
GET /v1/latest?channel=industry&asset=electronics
Authorization: Bearer alice:<Alice的实际Token>
~~~

旧 READ_API_KEYS 暂时保留兼容能力，旧 Key 可以读取所有信号。确认所有接收端迁移到 ACL 后，应从 Render 删除 READ_API_KEYS。

## Render 升级步骤

1. 推送代码并等待 Render 自动部署。
2. 打开 api-sender Web Service 的 Environment。
3. 新增 READ_API_ACL，值为单行 JSON。
4. 暂时保留现有 READ_API_KEYS。
5. 保存并等待重新部署。
6. 使用新 account:token 分别测试授权和越权信号。
7. 所有旧客户端迁移完成后，删除 READ_API_KEYS。

修改环境变量会重启服务并清空内存信号，需要发布端重新发布。

## 安全要求

- PUBLISH_API_KEY 只交给发布端。
- 每个接收方使用独立 account 和 Token。
- 不在日志中打印 Token 或 Authorization 请求头。
- Token 文件必须加入 .gitignore。
- 撤销用户时，从 READ_API_ACL 删除该 account。
- 修改权限时只调整 allow，无需更换 Token。
