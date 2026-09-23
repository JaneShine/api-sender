# Signal Feed API

一个轻量的公网信号分发 MVP：内部策略用发布 Key 写入结构化信号，外部 Agent 用读取 Key 获取最新信号。

第一版只把最新一条信号保存在进程内存中，不使用数据库。服务重启或重新部署后，信号会被清空。

## API

| 方法 | 路径 | 认证 | 用途 |
| --- | --- | --- | --- |
| GET | `/health` | 无 | 健康检查 |
| POST | `/v1/publish` | Publish Key | 发布并覆盖最新信号 |
| GET | `/v1/latest` | Read Key | 获取最新信号 |

认证头统一使用：`Authorization: Bearer <API_KEY>`。

## 本地运行

要求 Python 3.10 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

$env:PUBLISH_API_KEY="请替换为发布Key"
$env:READ_API_KEYS="读取Key-A,读取Key-B"
python -m uvicorn main:app --reload
```

打开 `http://127.0.0.1:8000/docs` 使用 Swagger；健康检查地址是 `http://127.0.0.1:8000/health`。

生成安全 Key：

```powershell
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

分别生成一个 Publish Key 和每位使用者各自的 Read Key。真实 Key 只能写入环境变量，不要提交到 GitHub。

## 本地验收

发布信号：

```powershell
$headers = @{ Authorization = "Bearer 请替换为发布Key" }
$body = @{
  channel = "index"
  asset = "IH"
  signal = "risk_off"
  value = 0.73
  confidence = 0.81
  source = "vol_structure"
  metadata = @{ model = "index_signal_v3" }
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/v1/publish" `
  -Headers $headers -ContentType "application/json" -Body $body
```

读取最新信号：

```powershell
$headers = @{ Authorization = "Bearer 请替换为读取Key" }
Invoke-RestMethod -Method Get `
  -Uri "http://127.0.0.1:8000/v1/latest" -Headers $headers
```

还应检查：无 Key 返回 401，错误 Key 返回 403，尚未发布时返回 404，Read Key 不能调用发布接口。

## 上传 GitHub

在 GitHub 新建一个空仓库 `signal-feed-api`，不要勾选自动创建 README，然后执行：

```powershell
git init
git add .
git commit -m "Initial signal feed API"
git branch -M main
git remote add origin https://github.com/<你的用户名>/signal-feed-api.git
git push -u origin main
```

如果已经安装并登录 GitHub CLI，可直接创建远端仓库：

```powershell
gh auth login
gh repo create signal-feed-api --public --source=. --remote=origin --push
```

上传后确认仓库只有 `main.py`、`requirements.txt`、`.env.example`、`.gitignore` 和 `README.md`，不存在 `.env`。

## 部署到 Render

1. 登录 Render，选择 **New → Web Service**，连接 GitHub 的 `signal-feed-api` 仓库。
2. Runtime 选择 **Python**。
3. Build Command 填写 `pip install -r requirements.txt`。
4. Start Command 填写 `uvicorn main:app --host 0.0.0.0 --port $PORT`。
5. Environment 添加 `PUBLISH_API_KEY` 和 `READ_API_KEYS`；多个读取 Key 用英文逗号分隔。
6. 部署后访问 `https://<你的服务名>.onrender.com/health`，应返回：

```json
{"status":"ok","service":"signal-feed-api"}
```

将本地验收命令中的地址替换为 Render HTTPS 地址，即可完成公网测试。

## Python 客户端示例

```python
import requests

base_url = "https://<你的服务名>.onrender.com"
published = requests.post(
    f"{base_url}/v1/publish",
    headers={"Authorization": "Bearer <PUBLISH_API_KEY>"},
    json={"channel": "index", "asset": "IH", "signal": "risk_off"},
    timeout=10,
)
published.raise_for_status()

latest = requests.get(
    f"{base_url}/v1/latest",
    headers={"Authorization": "Bearer <READ_API_KEY>"},
    timeout=10,
)
latest.raise_for_status()
print(latest.json())
```

`channel`、`asset`、`signal` 必填；`value`、`confidence`、`source`、`expires_at`、`metadata` 可选。服务会生成 `id` 和 UTC 时间 `published_at`。

> 当前实现仅适合单进程 MVP。不要配置多个 Uvicorn worker，否则每个进程会保存不同的最新信号。
