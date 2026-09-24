# 接收端 Agent 一键接入

本文交给接收方或其 Agent 阅读。接收端只负责读取信号，不允许调用发布接口。

## 管理员需要单独提供

管理员通过安全渠道分别提供 account、token 和允许读取的 channel:asset。认证请求由 Skill 自动组装为：

~~~text
Authorization: Bearer <account>:<token>
~~~

默认 API 地址是 https://api-sender-v68f.onrender.com。

## 一键安装 Skill

先克隆仓库：

~~~powershell
git clone https://github.com/JaneShine/api-sender.git
cd api-sender
~~~

Windows PowerShell：

~~~powershell
$skillRoot = if ($env:CODEX_HOME) { Join-Path $env:CODEX_HOME "skills" } else { Join-Path $HOME ".codex\skills" }
New-Item -ItemType Directory -Force -Path $skillRoot | Out-Null
Copy-Item -Recurse -Force ".\skills\signal-feed-reader" $skillRoot
~~~

macOS/Linux：

~~~bash
SKILL_ROOT="$HOME/.codex/skills"
mkdir -p "$SKILL_ROOT"
cp -R ./skills/signal-feed-reader "$SKILL_ROOT/"
~~~

安装后重新启动 Codex，使新 Skill 被发现。

## 配置凭据

启动 Codex 前设置环境变量。账号和 Token 分开配置，Skill 会自动拼成 account:token。

Windows PowerShell 当前会话：

~~~powershell
$env:SIGNAL_API_USER="管理员提供的account"
$env:SIGNAL_API_TOKEN="管理员提供的token"
$env:SIGNAL_API_BASE_URL="https://api-sender-v68f.onrender.com"
$env:SIGNAL_DEFAULT_CHANNEL="industry"
$env:SIGNAL_DEFAULT_ASSET="electronics"
~~~

macOS/Linux：

~~~bash
export SIGNAL_API_USER="管理员提供的account"
export SIGNAL_API_TOKEN="管理员提供的token"
export SIGNAL_API_BASE_URL="https://api-sender-v68f.onrender.com"
export SIGNAL_DEFAULT_CHANNEL="industry"
export SIGNAL_DEFAULT_ASSET="electronics"
~~~

不要把真实凭据写入源码、聊天记录、日志或 Git。若使用本地凭据文件，必须加入该项目的 .gitignore。

## 直接使用

显式调用 Skill：

~~~text
$signal-feed-reader 读取 industry/electronics 的最新信号
~~~

也可以直接说：

~~~text
读取 industry 频道 electronics 资产的最新信号
~~~

配置默认 channel 和 asset 后，可以说：

~~~text
读取最新信号
~~~

每次调用只返回一个 channel + asset 对应的独立 JSON，不会把多个信号合并到一个响应里。

Skill 默认将结果展示为紧凑信号卡牌，并始终显示 owner；只有用户明确要求时才展开原始 JSON。

industry/electronics 返回示例：

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
  "owner": "jxxie@efund",
  "id": "服务端生成",
  "published_at": "服务端生成的UTC时间"
}
~~~

## API 等价调用

~~~http
GET /v1/latest?channel=industry&asset=electronics
Authorization: Bearer <account>:<token>
~~~

也可以直接运行 Skill 自带脚本：

~~~powershell
python skills/signal-feed-reader/scripts/read_latest.py industry electronics
~~~

脚本只使用 Python 标准库，无需安装 requests。

## 状态码

| 状态码 | 含义 |
| --- | --- |
| 200 | 成功返回指定信号 |
| 400 | channel 和 asset 没有同时提供 |
| 401 | 缺少或错误的 Bearer 格式 |
| 403 | account/token 错误或没有该信号权限 |
| 404 | 有权限，但该 channel + asset 尚未发布信号 |
| 5xx | 服务暂时不可用 |

Render 免费实例休眠后，首次调用可能需要约 50 秒。Skill 使用 90 秒超时。

## 给接收端 Agent 的指令

~~~text
请安装并使用仓库中的 signal-feed-reader Skill。
我会通过安全渠道分别提供 SIGNAL_API_USER 和 SIGNAL_API_TOKEN。
请不要显示、记录或提交凭据。
读取信号时必须明确 channel 和 asset；如果我没有指定，则使用已配置的默认值。
每次只返回一个独立信号 JSON，并正确区分无信号的 404 和无权限的 403。
~~~
