# Kimi Chat Backend

Market Radar 的网页问答默认保留静态规则问答。配置后端后，会优先调用 Kimi；如果后端失败，会自动回退到静态规则问答。

## Vercel 环境变量

在 Vercel 项目 Settings -> Environment Variables 配置：

```text
KIMI_API_KEY=你的 Kimi / Moonshot API Key
KIMI_BASE_URL=https://api.moonshot.ai/v1
KIMI_MODEL=kimi-k2.6
MARKET_DATA_URL=https://lemonca11.github.io/ai_invest_agent/market/market_data.json
ALLOWED_ORIGIN=https://lemonca11.github.io
```

只有 `KIMI_API_KEY` 是必填，其余都有默认值。

## GitHub Pages 前端指向后端

GitHub Actions 构建站点时，可以设置环境变量：

```text
MARKET_CHAT_API_URL=https://你的-vercel-domain.vercel.app/api/chat
```

如果没有设置，页面仍会使用静态问答。

## 本地验证

```bash
python3 -m py_compile api/chat.py build_site.py
python3 build_site.py
```

## API 请求格式

```json
{
  "question": "云平台里谁最强？"
}
```

返回：

```json
{
  "answer": "..."
}
```

## 安全原则

- 不要把 `KIMI_API_KEY` 写进前端或提交到 GitHub。
- 后端只读取公开的 `market_data.json`。
- 模型提示词要求只基于给定数据回答，不直接给买卖建议。
