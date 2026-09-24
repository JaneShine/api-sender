# Signal Feed 接收端 Agent 接入说明

本文供接收端开发 Agent 直接读取并执行。目标是在不改动服务端的情况下，完成 Signal Feed API 的读取接入和连通性验证。

## 1. 接入方提供的信息

开始前，向用户获取以下三项配置；不要要求用户把真实凭据写入代码或提交到 Git：

```text
SIGNAL_API_BASE_URL=https://api-sender-v68f.onrender.com
SIGNAL_API_USER=<account>
SIGNAL_API_TOKEN=<token>
```

认证值由账号和 Token 拼接而成：

```text
<account>:<token>
```

请求头格式：

```http
Authorization: Bearer <account>:<token>
```

例如账号为 `alice`、Token 为 `abc123` 时，请求头应为 `Authorization: Bearer alice:abc123`。示例值不是有效凭据。

## 2. Agent 执行要求

接收端 Agent 应自动完成以下工作：

1. 确认项目使用的语言和现有 HTTP 客户端，优先复用已有依赖。
2. 将 URL、账号和 Token 接入环境变量或项目现有的 Secret 管理方式。
3. 请求 `GET /health` 验证服务可达。
4. 请求 `GET /v1/latest` 验证读取权限。
5. 将返回 JSON 接入调用方业务逻辑，并正确处理状态码。
6. 添加最小测试或连通性检查。
7. 不打印、记录、上传或提交完整认证值。

不要调用 `POST /v1/publish`。接收端只拥有读取权限。

## 3. API

### 健康检查

```http
GET /health
```

不需要认证。成功响应：

```json
{
  "status": "ok",
  "service": "signal-feed-api"
}
```

### 获取最新信号

```http
GET /v1/latest
Authorization: Bearer <account>:<token>
```

成功响应示例：

```json
{
  "channel": "index",
  "asset": "IH",
  "signal": "risk_off",
  "value": 0.73,
  "confidence": 0.81,
  "source": "vol_structure",
  "expires_at": "2026-09-24T01:30:00Z",
  "metadata": {
    "model": "index_signal_v3"
  },
  "id": "example-id",
  "published_at": "2026-09-24T01:00:00Z"
}
```

只有 `channel`、`asset` 和 `signal` 是发布请求的必填业务字段。接收端应允许其他可选字段为 `null`，并忽略未来新增的未知字段。

## 4. 状态码处理

| 状态码 | 含义 | 接收端行为 |
| --- | --- | --- |
| `200` | 成功 | 解析并处理信号 |
| `401` | 未提供或认证头格式错误 | 检查 Bearer 请求头 |
| `403` | 账号与 Token 组合无效 | 停止重试并提示更新凭据 |
| `404` | 服务正常，但当前没有信号 | 视为“暂无信号”，不要视为安装失败 |
| `422` | 请求格式错误 | 检查客户端实现 |
| `429` | 请求过多 | 指数退避后重试 |
| `5xx` | 服务暂时不可用 | 指数退避后有限重试 |

Render 免费实例休眠后，第一次请求可能需要约 50 秒。首次连接超时建议设置为 90 秒；正常轮询不要高频请求。

## 5. Python 最小实现

安装依赖：

```bash
python -m pip install requests
```

设置环境变量后运行：

```python
import os

import requests


base_url = os.environ["SIGNAL_API_BASE_URL"].rstrip("/")
account = os.environ["SIGNAL_API_USER"]
token = os.environ["SIGNAL_API_TOKEN"]

response = requests.get(
    f"{base_url}/v1/latest",
    headers={"Authorization": f"Bearer {account}:{token}"},
    timeout=90,
)

if response.status_code == 404:
    signal = None
else:
    response.raise_for_status()
    signal = response.json()

print(signal)
```

生产代码不要输出环境变量、Authorization 请求头或完整 Token。

## 6. 验收标准

接入完成必须满足：

- `/health` 返回 `200`。
- `/v1/latest` 返回 `200` 或“暂无信号”的 `404`。
- 错误 Token 返回 `403`。
- 凭据仅存在于环境变量或 Secret 管理系统中。
- 凭据文件已加入 `.gitignore`，且 Git 历史中不存在真实凭据。
- 客户端能处理可选字段、未知字段、超时和服务临时不可用。

## 7. 给 Agent 的一键指令

可以把下面这段话连同本文件交给接收端 Agent：

```text
请阅读 RECEIVER_AGENT.md，并在当前项目中自动完成 Signal Feed 读取端接入。
我会单独提供 SIGNAL_API_USER 和 SIGNAL_API_TOKEN；不要把凭据写进源码、日志或 Git。
请复用项目现有技术栈，实现 GET /health 和 GET /v1/latest，完成错误处理和最小验证，并汇报修改文件及验证结果。
```
