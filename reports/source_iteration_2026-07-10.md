# 监控系统迭代建议 - 2026-07-10

## 1. 当前覆盖判断

- 正式监控源数量：69
- 按层级分布：applications: 16, capital: 7, chips: 12, energy: 6, infrastructure: 15, models: 13
- 按来源组分布：background: 19, capital_event: 8, core_watchlist: 34, discovery: 8
- 迭代策略：官方 news / blog / changelog / IR 可以进入自动晋级候选；媒体、聚合页和社区榜单只进入候选池。

## 2. 建议优先加入

- 暂无高分自动晋级候选。

## 3. 需要人工确认

- 暂无需要人工确认的候选。

## 4. 质量与清理建议

- 未发现重复 URL 或重复公司名。
- **AMD Press Releases**：近期没有 confirmed_event，继续观察，暂不降级。
- **OpenAI API Changelog**：多次缺少发布时间，建议写专项解析器或降级为 background。；近期没有 confirmed_event，继续观察，暂不降级。
- **OpenAI Apps SDK Changelog**：多次缺少发布时间，建议写专项解析器或降级为 background。；近期没有 confirmed_event，继续观察，暂不降级。
- **Eaton News**：连续或累计失败偏多，建议检查 URL、超时、反爬或降级为 manual。；多次缺少发布时间，建议写专项解析器或降级为 background。；近期没有 confirmed_event，继续观察，暂不降级。
- **xAI News**：连续或累计失败偏多，建议检查 URL、超时、反爬或降级为 manual。；多次缺少发布时间，建议写专项解析器或降级为 background。；近期没有 confirmed_event，继续观察，暂不降级。
- **Mistral AI News**：多次缺少发布时间，建议写专项解析器或降级为 background。
- **CoreWeave Blog**：多次缺少发布时间，建议写专项解析器或降级为 background。；近期没有 confirmed_event，继续观察，暂不降级。
- **SK Hynix Newsroom**：连续或累计失败偏多，建议检查 URL、超时、反爬或降级为 manual。；多次缺少发布时间，建议写专项解析器或降级为 background。
- **Perplexity Blog**：连续或累计失败偏多，建议检查 URL、超时、反爬或降级为 manual。；多次缺少发布时间，建议写专项解析器或降级为 background。；近期没有 confirmed_event，继续观察，暂不降级。
- **Broadcom News**：多次缺少发布时间，建议写专项解析器或降级为 background。；近期没有 confirmed_event，继续观察，暂不降级。
- **Schneider Electric Newsroom**：连续或累计失败偏多，建议检查 URL、超时、反爬或降级为 manual。；多次缺少发布时间，建议写专项解析器或降级为 background。；近期没有 confirmed_event，继续观察，暂不降级。
- **Cohere Blog**：近期没有 confirmed_event，继续观察，暂不降级。
- **Oracle Cloud Infrastructure Blog**：连续或累计失败偏多，建议检查 URL、超时、反爬或降级为 manual。；多次缺少发布时间，建议写专项解析器或降级为 background。；近期没有 confirmed_event，继续观察，暂不降级。
- **Marvell Newsroom**：多次缺少发布时间，建议写专项解析器或降级为 background。；近期没有 confirmed_event，继续观察，暂不降级。
- **Arm Newsroom**：近期没有 confirmed_event，继续观察，暂不降级。
- **ServiceNow Newsroom**：连续或累计失败偏多，建议检查 URL、超时、反爬或降级为 manual。；多次缺少发布时间，建议写专项解析器或降级为 background。；近期没有 confirmed_event，继续观察，暂不降级。
- **Salesforce Newsroom**：近期没有 confirmed_event，继续观察，暂不降级。
- **Palantir Newsroom**：多次缺少发布时间，建议写专项解析器或降级为 background。；近期没有 confirmed_event，继续观察，暂不降级。
- **Vistra Newsroom**：连续或累计失败偏多，建议检查 URL、超时、反爬或降级为 manual。；多次缺少发布时间，建议写专项解析器或降级为 background。；近期没有 confirmed_event，继续观察，暂不降级。

## 5. 本次自动写入

- 未自动修改 sources.yaml。本轮只生成候选池和建议。

## 6. 输出文件

- 候选池：`config/source_candidates.yaml`
- 健康记录：`config/source_health.yaml`
- 本报告：`reports/source_iteration_2026-07-10.md`
