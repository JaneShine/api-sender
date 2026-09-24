---
name: signal-feed-reader
description: Read the latest authorized Signal Feed JSON for a specified channel and asset. Use when the user asks to fetch, inspect, or consume a signal such as industry/electronics from the configured Signal Feed API.
---

# Signal Feed Reader

Read exactly one independent signal JSON identified by channel and asset.

## Configuration

Require the SIGNAL_API_USER and SIGNAL_API_TOKEN environment variables. Use SIGNAL_API_BASE_URL when set; otherwise default to https://api-sender-v68f.onrender.com.

The authorization credential is user:token. Never display, log, persist, or commit either secret or the assembled Authorization header.

## Reading a signal

Determine the requested channel and asset from the user's request. If either is missing, use SIGNAL_DEFAULT_CHANNEL or SIGNAL_DEFAULT_ASSET when configured. Ask for the missing identifier only when it cannot be inferred or defaulted.

Run the bundled script relative to this SKILL.md, regardless of the user's current working directory:

    python scripts/read_latest.py <channel> <asset>

Examples:

    python scripts/read_latest.py industry electronics
    python scripts/read_latest.py macro rates

## Card output

For a successful read, show a compact Markdown card before any explanation. Do not show raw JSON unless the user explicitly asks for it.

Use this shape, adapting labels and rows to the actual payload:

> ### 📊 {strategy_name}
> **综合信号：** 🟢 {composite_signal}
>
> | 指标 | 状态 |
> | --- | --- |
> | 宏观 | ⚪ false |
> | 景气 | 🟢 true |
> | 交易 | 🟢 true |
>
> **频道 / 资产：** {channel} / {asset}  
> **数据日期：** {as_of_date}  
> **发布时间：** {published_at converted to Asia/Shanghai and labeled 北京时间}  
> **Owner：** {owner}

Always include owner. Render every entry in the signals object, not only the three example rows. Preserve the source key when no clear Chinese label exists.

Status markers:
- Boolean true: 🟢 true
- Boolean false: ⚪ false
- Numeric 1: 🟢 1
- Numeric 0: ⚪ 0
- Numeric -1: 🔴 -1
- Other values: display unchanged without inventing an interpretation

If strategy_name is absent, use strategy_id; if both are absent, use channel / asset as the title. Older payloads may contain a singular signal field; show it as the main signal. Do not claim that one signal represents another channel or asset.

## Response handling

- 200: report the returned signal.
- 404: report that this channel and asset currently have no published signal. This is not an authentication failure.
- 401: report malformed or missing authentication configuration.
- 403: report invalid credentials or missing permission without exposing credentials.
- Timeout or 5xx: explain that the service may be waking or temporarily unavailable; retry once when the user asked for a current reading.
- Any other failure: report the status and safe error detail.

Do not call /v1/publish; this skill is read-only.
