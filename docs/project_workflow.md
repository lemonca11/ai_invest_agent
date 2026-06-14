# AI Invest Agent 项目流程说明

本文档梳理 `ai_invest_agent` 当前的完整工作流：数据抓取、日报生成、站点构建、GitHub Pages 发布，以及可选的 Notion 发布。

## 1. 项目目标

项目的目标是每天自动生成一份 AI 投资情报日报，并将结果发布到公开网站 `MetaFinance`。

当前产物包括：

- 中文日报：`reports/YYYY-MM-DD.md`
- 英文日报：`reports_en/YYYY-MM-DD.md`
- 公开站点：`site/`
- 中文站点：首页 `site/index.html`
- 英文站点：首页 `site/en/index.html`

---

## 2. 核心流程

### 2.1 抓取信息源

入口脚本：[`main.py`](/Users/wenzhucui/ai_invest_agent/main.py)

作用：

- 读取 `config/sources.yaml`
- 按来源分组、优先级、抓取节奏过滤需要抓取的源
- 拉取 RSS、新闻页、Release Notes、Blog、Changelog 等内容
- 清洗页面正文，抽取发布时间、标题、正文和来源信息
- 生成结构化原始数据文件

输出：

- `data/raw_items_YYYY-MM-DD.json`
- `logs/run.log`

### 2.2 生成中文日报

入口脚本：[`generate_local_report.py`](/Users/wenzhucui/ai_invest_agent/generate_local_report.py)

作用：

- 读取当天的 `raw_items`
- 按事件等级和 AI 六层结构整理内容
- 输出中文 Markdown 日报
- 控制日报结构，包括：
  - 今日总览
  - 今日重大事件
  - 近期重要变化
  - 风险信号与信息盲区
  - 明日跟踪清单

输出：

- `reports/YYYY-MM-DD.md`

### 2.3 生成监控迭代建议

入口脚本：[`market_source_iterate.py`](/Users/wenzhucui/ai_invest_agent/market_source_iterate.py)

作用：

- 基于当天抓取结果评估来源健康度
- 输出可晋升的候选来源
- 生成监控策略建议

输出：

- `config/source_candidates.yaml`
- `config/source_health.yaml`
- `reports/source_iteration_YYYY-MM-DD.md`

### 2.4 构建公开网站

入口脚本：[`build_site.py`](/Users/wenzhucui/ai_invest_agent/build_site.py)

作用：

- 读取 `reports/*.md`
- 读取 `reports_en/*.md`
- 生成中文与英文双语静态站点
- 生成首页、日报详情页、站点 feed

输出：

- `site/index.html`
- `site/en/index.html`
- `site/reports/YYYY-MM-DD.html`
- `site/en/reports/YYYY-MM-DD.html`
- `site/feed.json`
- `site/en/feed.json`
- `site/.nojekyll`

---

## 3. 本地执行方式

### 3.1 一键跑完整日报

脚本：[`run_daily_report.sh`](/Users/wenzhucui/ai_invest_agent/run_daily_report.sh)

执行内容：

1. 抓取信息源
2. 检查抓取质量，全部失败时停止
3. 生成中文日报
4. 生成来源迭代建议
5. 构建公开站点

适合本地调试整个日报链路。

### 3.2 仅重新构建站点

```bash
cd ~/ai_invest_agent
python3 build_site.py
```

适合在日报内容已经准备好的情况下，只更新公开网页。

---

## 4. 双语站点

站点采用双语目录结构：

- 中文首页：`site/index.html`
- 英文首页：`site/en/index.html`
- 中文日报：`site/reports/YYYY-MM-DD.html`
- 英文日报：`site/en/reports/YYYY-MM-DD.html`

英文站点的数据来源是 `reports_en/`。

当前逻辑是：

- `reports/` 负责中文稿
- `reports_en/` 负责英文稿
- 如果某天没有对应英文稿，英文站只显示已有英文内容

---

## 5. GitHub Pages 发布

仓库里有两个 workflow：

### 5.1 日常自动发布

文件：[`.github/workflows/daily-publish.yml`](/Users/wenzhucui/ai_invest_agent/.github/workflows/daily-publish.yml)

触发方式：

- 每天定时执行
- 也支持手动触发

执行顺序：

1. `main.py`
2. 检查抓取质量，全部失败时停止发布
3. `generate_local_report.py`
4. `market_source_iterate.py`
5. `build_site.py`
6. 上传 `site/`
7. 发布到 GitHub Pages

默认时区已设为 `Asia/Shanghai`，避免日报日期按 UTC 偏移。
GitHub 定时任务的今日重大事件窗口设为 30 小时，近期重要变化窗口保留 168 小时，减少连续日报重复。

### 5.2 代码推送时构建站点

文件：[`.github/workflows/deploy-pages.yml`](/Users/wenzhucui/ai_invest_agent/.github/workflows/deploy-pages.yml)

触发方式：

- 推送到 `main`
- 或手动触发

作用：

- 只重新构建 `site/`
- 用于代码或样式更新后的网页刷新

### 5.3 Pages 设置要求

在 GitHub 仓库里需要把：

- `Settings -> Pages -> Build and deployment -> Source`
- 设置为 `GitHub Actions`

这样 workflow 才会真正把静态站点发布到 Pages。

---

## 6. 可选 Notion 发布

如果需要把日报同步到 Notion，可以使用：

- [`notion_publish.py`](/Users/wenzhucui/ai_invest_agent/notion_publish.py)
- [`config/notion.yaml`](/Users/wenzhucui/ai_invest_agent/config/notion.yaml)

作用：

- 将当天生成的 Markdown 日报发布到指定 Notion 页面

当前它是一个可选链路，不影响 GitHub Pages 的公开发布。

---

## 7. 关键配置文件

- [`config/sources.yaml`](/Users/wenzhucui/ai_invest_agent/config/sources.yaml)：全部监控来源
- [`config/source_health.yaml`](/Users/wenzhucui/ai_invest_agent/config/source_health.yaml)：来源健康状态
- [`config/source_candidates.yaml`](/Users/wenzhucui/ai_invest_agent/config/source_candidates.yaml)：可晋升候选来源
- [`requirements.txt`](/Users/wenzhucui/ai_invest_agent/requirements.txt)：Python 依赖

---

## 8. 日志与排错

常见日志位置：

- `logs/run.log`
- `logs/daily_report_YYYY-MM-DD.log`

常见排错顺序：

1. 先看 `main.py` 是否成功抓到 `raw_items`
2. 再看 `generate_local_report.py` 是否产出日报
3. 再看 `build_site.py` 是否成功生成 `site/`
4. 最后看 GitHub Actions 是否成功上传 Pages artifact

---

## 9. 典型日常操作

### 本地手动生成

```bash
cd ~/ai_invest_agent
bash run_daily_report.sh
```

### 发布到网站

只要 GitHub Actions 和 Pages 已启用，推送到 `main` 后会自动构建并发布。

### 生成英文版

把英文 Markdown 放进 `reports_en/YYYY-MM-DD.md`，再运行：

```bash
python3 build_site.py
```

英文站点会自动更新。

---

## 10. 财报模块

财报模块和日报共用同一个公开站点，不另建网站。

当前页面结构：

- 财报首页：`site/earnings/index.html`
- 财报报告页：`site/earnings/reports/TICKER-PERIOD.html`

核心文件：

- [`config/earnings_watchlist.yaml`](/Users/wenzhucui/ai_invest_agent/config/earnings_watchlist.yaml)：AI 相关科技股财报观察名单
- [`earnings_pipeline.py`](/Users/wenzhucui/ai_invest_agent/earnings_pipeline.py)：财报日历、官方财报抓取和 Markdown 报告生成入口
- `data/earnings_calendar_YYYY-MM-DD.json`：财报日历快照
- `data/earnings/TICKER-PERIOD.json`：官方财报原始数据
- `reports_earnings/TICKER-PERIOD.md`：财报分析 Markdown

执行方式：

```bash
cd ~/ai_invest_agent
venv/bin/python earnings_pipeline.py --ticker ORCL
python3 build_site.py
```

当前财报抓取策略：

1. 日历可以来自 watchlist 或第三方日历。
2. 财报正文优先使用公司 Investor Relations 官方页面。
3. 如果官方页面被 bot challenge、正文过短或无法提取，流水线只记录 raw JSON，不生成分析报告。
4. 后续接入财报分析 skill 后，由 `earnings_pipeline.py` 把官方 raw JSON 转成 skill 输入，再写入 `reports_earnings/`。

---

## 11. 当前项目的最短理解

一句话概括：

> `main.py` 抓数据，`generate_local_report.py` 写日报，`build_site.py` 生成站点，GitHub Actions 每天自动跑，GitHub Pages 对外发布。
