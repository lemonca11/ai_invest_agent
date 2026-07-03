# Market Radar Automation

生产站点 `https://aiinvestagent.vercel.app` 的 `Market Radar` 现在由 GitHub Actions 自动更新。

## Workflow

- 文件：`.github/workflows/update-market-radar-vercel.yml`
- 触发时间：工作日 `21:30 UTC`
- 对应北京时间：次日 `05:30`

执行步骤：

1. 运行 `scripts/update_market_radar.sh`
2. 刷新 `data/market_*.csv`
3. 重建 `site/market/market_data.json` 和静态页面
4. 检查 `latest_date` 是否过旧
5. 只在产物有变化时提交回仓库
6. 只在产物有变化时发布到 Vercel 生产环境

## Required GitHub Secrets

需要在仓库 Secrets 中配置：

- `VERCEL_TOKEN`
- `VERCEL_ORG_ID`
- `VERCEL_PROJECT_ID`

其中 `VERCEL_ORG_ID` 和 `VERCEL_PROJECT_ID` 可以从本地 `.vercel/project.json` 获取。

## Local parity

本地手动执行与 CI 保持一致：

```bash
bash scripts/update_market_radar.sh
python3 scripts/check_market_data_freshness.py
```
