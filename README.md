# API Sender

一个已经可运行的 Signal Feed API。内部策略程序通过 Publish Key 发布结构化信号，外部 Agent 通过 Read Key 获取最新信号。

GitHub：<https://github.com/JaneShine/api-sender>

## 当前状态

- FastAPI 服务已实现并推送到 GitHub `main` 分支
- 已实现健康检查、信号发布、最新信号读取
- 发布权限和读取权限使用不同 API Key
- 已通过本地接口验收
- 尚未部署到 Render；完成下方部署步骤后即可获得公网 HTTPS 地址

## API

| 方法 | 地址 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | `/health` | 无 | 健康检查 |
| POST | `/v1/publish` | Publish Key | 发布信号并覆盖内存中的上一条信号 |
| GET | `/v1/latest` | Read Key | 获取最新信号 |
| GET | `/docs` | 无 | Swagger API 文档 |

认证请求头：

```http
Authorization: Bearer <API_KEY>
```

## 快速启动

要求 Python 3.10 或更高版本。

```powershell
git clone git@github.com:JaneShine/api-sender.git
cd api-sender
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

$env:PUBLISH_API_KEY="替换为发布Key"
$env:READ_API_KEYS="读取Key-A,读取Key-B"
python -m uvicorn main:app --reload
```

启动后访问：

- Swagger：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/health>

生成安全 API Key：

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

建议生成一个 Publish Key，并为每位读取者分别生成 Read Key。真实 Key 只放在环境变量中，不要写进代码或提交到 GitHub。

## 发布信号

PowerShell 示例：

```powershell
$headers = @{ Authorization = "Bearer 替换为发布Key" }
$body = @{
  channel = "index"
  asset = "IH"
  signal = "risk_off"
  value = 0.73
  confidence = 0.81
  source = "vol_structure"
  expires_at = "2026-09-24T01:30:00Z"
  metadata = @{ model = "index_signal_v3" }
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/v1/publish" `
  -Headers $headers `
  -ContentType "application/json" `
  -Body $body
```

服务会自动补充 `id` 和 UTC 时间 `published_at`。

## 获取最新信号

```powershell
$headers = @{ Authorization = "Bearer 替换为读取Key" }
Invoke-RestMethod -Method Get `
  -Uri "http://127.0.0.1:8000/v1/latest" `
  -Headers $headers
```

尚未发布任何信号时返回 `404`；缺少认证头返回 `401`；Key 错误或权限不匹配返回 `403`。

## Python 客户端

```python
import requests

base_url = "http://127.0.0.1:8000"

response = requests.get(
    f"{base_url}/v1/latest",
    headers={"Authorization": "Bearer <READ_API_KEY>"},
    timeout=10,
)
response.raise_for_status()
print(response.json())
```

## 部署到 Render

1. 登录 Render，选择 **New → Web Service**。
2. 连接 GitHub 仓库 `JaneShine/api-sender`。
3. Runtime 选择 **Python**。
4. Build Command 填写 `pip install -r requirements.txt`。
5. Start Command 填写 `uvicorn main:app --host 0.0.0.0 --port $PORT`。
6. 添加环境变量：
   - `PUBLISH_API_KEY`：发布端专用 Key
   - `READ_API_KEYS`：多个 Read Key 用英文逗号分隔
7. 部署后访问 `https://<Render服务名>.onrender.com/health` 验证服务。
8. 将上方调用示例中的本地地址替换为 Render HTTPS 地址。

健康检查应返回：

```json
{
  "status": "ok",
  "service": "signal-feed-api"
}
```

## 数据字段

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `channel` | string | 是 | 信号类别 |
| `asset` | string | 是 | 标的 |
| `signal` | string | 是 | 决策状态 |
| `value` | float | 否 | 原始数值 |
| `confidence` | float | 否 | 置信度 |
| `source` | string | 否 | 信号来源 |
| `expires_at` | datetime | 否 | 失效时间 |
| `metadata` | object | 否 | 扩展数据 |
| `id` | string | 服务生成 | 信号 ID |
| `published_at` | datetime | 服务生成 | 发布时间 |

## 当前限制

当前版本只在进程内存中保存最新一条信号：

- 服务重启或重新部署后，最新信号会清空
- 不支持历史查询
- 不要配置多个 Uvicorn worker，否则每个进程会保存不同的数据
- `expires_at` 当前只作为数据字段返回，不会自动过滤过期信号

这是当前 MVP 的预期行为；需要持久化或多进程部署时再引入数据库。
