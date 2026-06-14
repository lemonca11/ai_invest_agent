from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"
REPORTS_EN_DIR = ROOT / "reports_en"
REPORTS_EARNINGS_DIR = ROOT / "reports_earnings"
DATA_DIR = ROOT / "data"
SITE_DIR = ROOT / "site"
SITE_REPORTS_DIR = SITE_DIR / "reports"
SITE_EARNINGS_DIR = SITE_DIR / "earnings"
SITE_EARNINGS_REPORTS_DIR = SITE_EARNINGS_DIR / "reports"
SITE_EN_DIR = SITE_DIR / "en"
SITE_EN_REPORTS_DIR = SITE_EN_DIR / "reports"
ASSETS_DIR = SITE_DIR / "assets"


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
EARNINGS_RE = re.compile(r"^[A-Z0-9.-]+-.+\.md$")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")


@dataclass
class Report:
    date: str
    title: str
    overview: list[str]
    events: list[str]
    event_anchors: list[tuple[str, str]]
    sections: list[str]
    html: str
    plain: str
    lang: str = "zh"

    @property
    def url(self) -> str:
        return f"reports/{self.date}.html"

    @property
    def display_title(self) -> str:
        title = self.title.replace(f" - {self.date}", "").strip()
        return title or "AI 投资情报日报"


@dataclass
class EarningsReport:
    report_id: str
    ticker: str
    period: str
    title: str
    html: str
    plain: str

    @property
    def url(self) -> str:
        return f"reports/{self.report_id}.html"


def escape(text: str) -> str:
    return html.escape(text, quote=True)


def inline_markdown(text: str) -> str:
    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)

    def replace_link(match: re.Match[str]) -> str:
        label = match.group(1)
        url = match.group(2)
        safe_url = escape(url)
        safe_label = label
        return f'<a href="{safe_url}" target="_blank" rel="noopener">{safe_label}</a>'

    text = LINK_RE.sub(replace_link, text)
    text = re.sub(
        r"(?<![\"=])(https?://[^\s<]+)",
        r'<a href="\1" target="_blank" rel="noopener">\1</a>',
        text,
    )
    return text


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", text.lower()).strip("-")
    return cleaned or "section"


def is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def is_table_separator(line: str) -> bool:
    return bool(TABLE_SEPARATOR_RE.match(line.strip()))


def split_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def parse_report(path: Path, lang: str = "zh") -> Report:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    title = lines[0].lstrip("# ").strip() if lines and lines[0].startswith("# ") else path.stem
    date = path.stem

    overview: list[str] = []
    events: list[str] = []
    event_anchors: list[tuple[str, str]] = []
    sections: list[str] = []
    current_h2 = ""

    for line in lines:
        heading = HEADING_RE.match(line)
        if heading:
            level = len(heading.group(1))
            text = heading.group(2).strip()
            if level == 2:
                current_h2 = text
                sections.append(text)
            elif level == 3 and (text.startswith("事件 ") or text.startswith("Event ")):
                event_title = re.sub(r"^事件\s+\d+[:：]\s*", "", text)
                event_title = re.sub(r"^Event\s+\d+:\s*", "", event_title)
                events.append(event_title)
                event_anchors.append((event_title, slugify(text)))
            continue
        if (current_h2.startswith("1. 今日总览") or current_h2.startswith("1. Executive Overview")) and line.startswith("- "):
            overview.append(re.sub(r"^- ", "", line).strip())

    return Report(
        date=date,
        title=title,
        overview=overview,
        events=events,
        event_anchors=event_anchors,
        sections=sections,
        html=markdown_to_html(raw),
        plain=raw,
        lang=lang,
    )


def parse_earnings_report(path: Path) -> EarningsReport:
    raw = path.read_text(encoding="utf-8")
    lines = raw.splitlines()
    title = lines[0].lstrip("# ").strip() if lines and lines[0].startswith("# ") else path.stem
    parts = path.stem.split("-", 1)
    ticker = parts[0]
    period = parts[1].replace("-", " ") if len(parts) > 1 else ""
    return EarningsReport(
        report_id=path.stem,
        ticker=ticker,
        period=period,
        title=title,
        html=markdown_to_html(raw),
        plain=raw,
    )


def markdown_to_html(raw: str) -> str:
    output: list[str] = []
    list_stack: list[str] = []
    in_code = False
    code_lines: list[str] = []
    table_rows: list[str] = []

    def close_lists(target_indent: int = -1) -> None:
        while list_stack and len(list_stack) > target_indent + 1:
            output.append(f"</{list_stack.pop()}>")

    def flush_table() -> None:
        nonlocal table_rows
        if not table_rows:
            return
        rows = [split_table_row(row) for row in table_rows if not is_table_separator(row)]
        table_rows = []
        if not rows:
            return
        header = rows[0]
        body = rows[1:]
        output.append('<div class="table-wrap"><table>')
        output.append("<thead><tr>" + "".join(f"<th>{inline_markdown(cell)}</th>" for cell in header) + "</tr></thead>")
        if body:
            output.append("<tbody>")
            for row in body:
                cells = row + [""] * max(0, len(header) - len(row))
                output.append("<tr>" + "".join(f"<td>{inline_markdown(cell)}</td>" for cell in cells[: len(header)]) + "</tr>")
            output.append("</tbody>")
        output.append("</table></div>")

    for raw_line in raw.splitlines():
        line = raw_line.rstrip()

        if line.startswith("```"):
            flush_table()
            if in_code:
                output.append("<pre><code>" + escape("\n".join(code_lines)) + "</code></pre>")
                code_lines = []
                in_code = False
            else:
                close_lists()
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        if is_table_row(line) or (table_rows and is_table_separator(line)):
            close_lists()
            table_rows.append(line)
            continue

        if not line.strip():
            flush_table()
            close_lists()
            continue

        if line.strip() == "---":
            flush_table()
            close_lists()
            output.append("<hr>")
            continue

        heading = HEADING_RE.match(line)
        if heading:
            flush_table()
            close_lists()
            level = len(heading.group(1))
            text = heading.group(2).strip()
            anchor = slugify(text)
            if level == 1:
                output.append(f'<h1 id="{anchor}">{inline_markdown(text)}</h1>')
            else:
                output.append(f'<h{level} id="{anchor}">{inline_markdown(text)}</h{level}>')
            continue

        bullet = re.match(r"^(\s*)-\s+(.+)$", line)
        if bullet:
            flush_table()
            indent = min(len(bullet.group(1)) // 2, 3)
            while len(list_stack) <= indent:
                output.append("<ul>")
                list_stack.append("ul")
            close_lists(indent)
            output.append(f"<li>{inline_markdown(bullet.group(2))}</li>")
            continue

        number = re.match(r"^(\s*)\d+\.\s+(.+)$", line)
        if number:
            flush_table()
            indent = min(len(number.group(1)) // 2, 3)
            while len(list_stack) <= indent:
                output.append("<ol>")
                list_stack.append("ol")
            close_lists(indent)
            output.append(f"<li>{inline_markdown(number.group(2))}</li>")
            continue

        if line.startswith("> "):
            flush_table()
            close_lists()
            output.append(f"<blockquote>{inline_markdown(line[2:])}</blockquote>")
            continue

        flush_table()
        close_lists()
        output.append(f"<p>{inline_markdown(line)}</p>")

    flush_table()
    close_lists()
    return "\n".join(output)


def report_card(report: Report, latest: bool = False, lang: str = "zh") -> str:
    summary = report.overview[0] if report.overview else "AI investment intelligence report."
    event_count = len(report.events)
    class_name = "report-card latest-card" if latest else "report-card"
    label = "Latest Report" if latest else ("Daily Report" if lang == "en" else "Daily Report")
    event_label = "key events" if lang == "en" else "key events"
    section_label = "sections" if lang == "en" else "sections"
    return f"""
    <article class="{class_name}">
      <div class="card-kicker">{label}</div>
      <h3><a href="{report.url}">{escape(report.date)} · {escape(report.display_title)}</a></h3>
      <p>{inline_markdown(summary)}</p>
      <div class="card-meta">
        <span>{event_count} {event_label}</span>
        <span>{len(report.sections)} {section_label}</span>
      </div>
    </article>
    """


def report_table(reports: list[Report], lang: str = "zh") -> str:
    date_label = "Date" if lang == "en" else "日期"
    report_label = "Report" if lang == "en" else "报告"
    signals_label = "Signals" if lang == "en" else "信号"
    top_signal_label = "Top signal" if lang == "en" else "核心信号"
    rows = []
    for idx, report in enumerate(reports):
        summary = report.overview[0] if report.overview else "AI investment intelligence report."
        top_signal = report.events[0] if report.events else report.display_title
        badge = "Latest" if idx == 0 else "Daily"
        signal_count = len(report.events)
        rows.append(
            f"""
            <tr>
              <td class="archive-date">{escape(report.date)}<span>{escape(badge)}</span></td>
              <td class="archive-report">
                <a href="{report.url}">{escape(report.display_title)}</a>
                <p>{inline_markdown(summary)}</p>
              </td>
              <td class="archive-count">{escape(str(signal_count))}</td>
              <td class="archive-signal">{escape(top_signal)}</td>
            </tr>
            """
        )
    return f"""
    <div class="archive-table-wrap">
      <table class="archive-table">
        <thead>
          <tr>
            <th>{escape(date_label)}</th>
            <th>{escape(report_label)}</th>
            <th>{escape(signals_label)}</th>
            <th>{escape(top_signal_label)}</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    """


def layout(title: str, body: str, description: str = "", lang: str = "zh-CN", css_href: str = "assets/styles.css") -> str:
    desc = description or "MetaFinance publishes bilingual AI investment intelligence for global markets."
    return f"""<!doctype html>
<html lang="{escape(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <meta name="description" content="{escape(desc)}">
  <link rel="stylesheet" href="{escape(css_href)}">
</head>
<body>
{body}
</body>
</html>
"""


EARNINGS_DEMO_CALENDAR = [
    {
        "ticker": "ORCL",
        "company": "Oracle",
        "period": "Q4 FY2026",
        "date": "2026-06-11",
        "time": "After close",
        "layer": "Cloud infrastructure / Applications",
        "status": "Analyzed",
        "url": "reports/ORCL-Q4-FY2026.html",
        "source": "Official IR",
        "action": "Read analysis",
    },
    {
        "ticker": "ADBE",
        "company": "Adobe",
        "period": "Q2 FY2026",
        "date": "2026-06-11",
        "time": "After close",
        "layer": "AI applications",
        "status": "Released",
        "url": "#",
        "source": "Official IR",
        "action": "Queue analysis",
    },
    {
        "ticker": "AVGO",
        "company": "Broadcom",
        "period": "Q2 FY2026",
        "date": "2026-06-05",
        "time": "After close",
        "layer": "AI networking / ASIC",
        "status": "Analyzing",
        "url": "#",
        "source": "Official IR",
        "action": "In progress",
    },
    {
        "ticker": "NVDA",
        "company": "NVIDIA",
        "period": "Q1 FY2027",
        "date": "2026-05-27",
        "time": "After close",
        "layer": "Chips / AI infrastructure",
        "status": "Upcoming",
        "url": "#",
        "source": "Third-party calendar",
        "action": "Wait for release",
    },
]


def latest_earnings_calendar() -> list[dict]:
    paths = sorted(DATA_DIR.glob("earnings_calendar_*.json"))
    if not paths:
        return EARNINGS_DEMO_CALENDAR

    try:
        payload = json.loads(paths[-1].read_text(encoding="utf-8"))
    except Exception:
        return EARNINGS_DEMO_CALENDAR

    rows = []
    for item in payload.get("items", []):
        status = item.get("status") or "upcoming"
        if status == "released":
            display_status = "Released"
            action = "Queue analysis"
        elif status == "upcoming":
            display_status = "Upcoming"
            action = "Wait for release"
        elif status == "no_official_release":
            display_status = "No official release"
            action = "Check source"
        else:
            display_status = status.replace("_", " ").title()
            action = "Review"

        rows.append(
            {
                "ticker": item.get("ticker") or "",
                "company": item.get("company") or "",
                "period": item.get("fiscal_period") or "",
                "date": item.get("expected_date") or "",
                "time": (item.get("timing") or "").replace("_", " ").title(),
                "layer": item.get("layer") or "",
                "status": display_status,
                "url": "#",
                "source": "Official IR" if item.get("official_release_url") else "Third-party calendar",
                "action": action,
            }
        )

    return rows or EARNINGS_DEMO_CALENDAR


def report_for_ticker(earnings_reports: list[EarningsReport], ticker: str) -> EarningsReport | None:
    ticker = ticker.upper()
    for report in earnings_reports:
        if report.ticker.upper() == ticker:
            return report
    return None


def earnings_items(earnings_reports: list[EarningsReport]) -> list[dict]:
    items = []
    for item in latest_earnings_calendar():
        row = dict(item)
        report = report_for_ticker(earnings_reports, row["ticker"])
        if report:
            row["period"] = report.period or row["period"]
            row["status"] = "Analyzed"
            row["url"] = report.url
            row["action"] = "Read analysis"
            row["title"] = report.title
        items.append(row)
    return items


def earnings_preview(earnings_reports: list[EarningsReport]) -> str:
    rows = []
    for item in earnings_items(earnings_reports)[:3]:
        link = item["url"] if item["url"] != "#" else "earnings/index.html"
        rows.append(
            f"""
            <tr>
              <td><strong>{escape(item["ticker"])}</strong><span>{escape(item["company"])}</span></td>
              <td>{escape(item["period"])}<span>{escape(item["date"])}</span></td>
              <td><span class="status-pill {escape(item["status"].lower().replace(" ", "-"))}">{escape(item["status"])}</span></td>
              <td><a href="{escape('earnings/' + link if link.startswith('reports/') else link)}">{escape(item["action"])}</a></td>
            </tr>
            """
        )
    return f"""
  <section class="earnings-strip" aria-label="AI earnings monitor">
    <div class="section-heading">
      <p>Earnings</p>
      <h2>AI 财报雷达</h2>
    </div>
    <div class="earnings-strip-copy">
      <p>跟踪 AI 相关科技股财报日历、官方 IR 公告和财报解读。</p>
      <a href="earnings/index.html">Open earnings desk</a>
    </div>
    <div class="mini-table-wrap">
      <table class="mini-table">
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
  </section>
"""


def earnings_index_layout(earnings_reports: list[EarningsReport]) -> str:
    rows = []
    for item in earnings_items(earnings_reports):
        status_class = item["status"].lower().replace(" ", "-")
        link = item["url"]
        action = (
            f'<a href="{escape(link)}">{escape(item["action"])}</a>'
            if link != "#"
            else f'<span>{escape(item["action"])}</span>'
        )
        rows.append(
            f"""
            <tr>
              <td class="ticker-cell"><strong>{escape(item["ticker"])}</strong><span>{escape(item["company"])}</span></td>
              <td>{escape(item["period"])}</td>
              <td>{escape(item["date"])}<span>{escape(item["time"])}</span></td>
              <td>{escape(item["layer"])}</td>
              <td><span class="status-pill {escape(status_class)}">{escape(item["status"])}</span></td>
              <td>{escape(item["source"])}</td>
              <td class="action-cell">{action}</td>
            </tr>
            """
        )

    body = f"""
<header class="site-header compact">
  <a class="brand" href="../index.html" aria-label="MetaFinance home">
    <span class="brand-mark">MF</span>
    <span><strong>MetaFinance</strong><small>AI Investment Intelligence</small></span>
  </a>
  <nav>
    <a href="../index.html#reports">Reports</a>
    <a href="index.html">Earnings</a>
    <a href="../feed.json">Data</a>
  </nav>
</header>
<main>
  <section class="earnings-desk-head">
    <div>
      <p class="eyebrow">AI Earnings Desk</p>
      <h1>财报日历与官方解读</h1>
      <p>聚焦 AI 产业链科技股财报。日历用于提醒，解读优先使用公司 IR 和 SEC 官方材料。</p>
    </div>
    <a href="reports/ORCL-Q4-FY2026.html">View ORCL demo</a>
  </section>

  <section class="earnings-dashboard">
    <div class="earnings-kpi"><strong>30 days</strong><span>forward calendar</span></div>
    <div class="earnings-kpi"><strong>Official first</strong><span>IR / SEC sources</span></div>
    <div class="earnings-kpi"><strong>AI lens</strong><span>cloud, chips, apps, energy</span></div>
  </section>

  <section class="earnings-calendar-section">
    <div class="section-heading">
      <p>Calendar</p>
      <h2>Upcoming and released earnings</h2>
    </div>
    <div class="archive-table-wrap">
      <table class="archive-table earnings-calendar-table">
        <thead>
          <tr>
            <th>Company</th>
            <th>Period</th>
            <th>Release date</th>
            <th>AI layer</th>
            <th>Status</th>
            <th>Source</th>
            <th>Analysis</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
  </section>

  <section class="earnings-system">
    <div class="latest-summary">
      <div class="section-heading">
        <p>Source Policy</p>
        <h2>信息源优先级</h2>
      </div>
      <ol class="event-list">
        <li>公司 Investor Relations 新闻稿、财报 PDF、prepared remarks。</li>
        <li>SEC 8-K、10-Q、10-K，用于补齐正式披露和风险因素。</li>
        <li>第三方财报日历只用于提醒，不作为正文事实来源。</li>
      </ol>
    </div>
    <div class="market-map">
      <div class="section-heading">
        <p>Workflow</p>
        <h2>发布流水线</h2>
      </div>
      <div class="layer-grid">
        <span>Calendar</span><span>Official IR</span><span>SEC filings</span>
        <span>Analysis skill</span><span>Markdown report</span><span>Publish</span>
      </div>
    </div>
  </section>
</main>
<footer class="site-footer">
  <span>MetaFinance</span>
  <span>Earnings demo generated inside the same static site.</span>
</footer>
"""
    return layout(
        "MetaFinance · AI Earnings Desk",
        body,
        description="AI related technology earnings calendar and official earnings analysis.",
        css_href="../assets/styles.css",
    )


def earnings_report_layout(report: EarningsReport) -> str:
    body = f"""
<header class="site-header compact">
  <a class="brand" href="../../index.html" aria-label="MetaFinance home">
    <span class="brand-mark">MF</span>
    <span><strong>MetaFinance</strong><small>AI Investment Intelligence</small></span>
  </a>
  <nav>
    <a href="../../index.html#reports">Reports</a>
    <a href="../index.html">Earnings</a>
    <a href="../../feed.json">Data</a>
  </nav>
</header>
<main class="report-page">
  <aside class="report-aside">
    <div class="date-label">{escape(report.ticker)} · {escape(report.period)}</div>
    <h2>Earnings Brief</h2>
    <p>官方财报信息源优先，面向 AI 投资链条的结构化解读。</p>
    <div class="report-toc">
      <span>Contents</span>
      <a href="#1-一句话结论">一句话结论</a>
      <a href="#2-官方来源">官方来源</a>
      <a href="#3-关键财务指标">关键财务指标</a>
      <a href="#4-ai-相关看点">AI 相关看点</a>
      <a href="#5-投资含义">投资含义</a>
    </div>
    <a class="back-link" href="../index.html">← Back to earnings</a>
  </aside>
  <article class="markdown-body">
    {report.html}
  </article>
</main>
"""
    return layout(
        f"MetaFinance · {report.title}",
        body,
        description=f"{report.ticker} earnings analysis for AI infrastructure investors.",
        css_href="../../assets/styles.css",
    )


def oracle_demo_report_layout() -> str:
    raw = """# ORCL Q4 FY2026 财报解读 Demo

## 1. 一句话结论

Oracle 这份财报的主线不是传统数据库业务，而是云基础设施需求、RPO 积压和 AI 训练 / 推理工作负载能否继续拉动 OCI 增长。Demo 中的分析结构展示未来 skill 输出的阅读体验。

## 2. 官方来源

| 字段 | 内容 |
|---|---|
| 公司 | Oracle |
| Ticker | ORCL |
| 财报期 | Q4 FY2026 / FY2026 |
| 来源类型 | Official Investor Relations |
| 官方链接 | [Oracle Announces Record Q4 and FY 2026 Results Driven by Cloud Infrastructure & Cloud Applications](https://investor.oracle.com/investor-news/news-details/2026/Oracle-Announces-Record-Q4-and-FY-2026-Results-Driven-by-Cloud-Infrastructure--Cloud-Applications/default.aspx) |

## 3. AI 相关看点

- **OCI 需求**：重点看 cloud infrastructure revenue、AI 训练集群租用、GPU / 加速器容量扩张和客户 backlog。
- **RPO / backlog**：如果剩余履约义务继续高增长，说明未来云收入可见度提高。
- **Capex 节奏**：AI 基础设施增长通常伴随资本开支上行，需要判断投入是否能转化为高质量云收入。
- **应用层联动**：Cloud Applications 增长能说明 Oracle 是否把基础设施需求转化为更宽的企业软件关系。

## 4. 财务指标面板

| 指标 | Demo 展示口径 | 分析用途 |
|---|---|---|
| Total revenue | 从官方公告抽取 | 判断整体增长质量 |
| Cloud revenue | 从官方公告抽取 | 判断云业务贡献 |
| OCI growth | 从官方公告抽取 | 判断 AI 基础设施拉动 |
| EPS / operating margin | 从官方公告抽取 | 判断增长是否牺牲盈利质量 |
| RPO | 从官方公告或 10-Q 抽取 | 判断未来收入可见度 |

## 5. 投资含义

如果 OCI、RPO 和 capex 三者同步上行，Oracle 会更像 AI 基础设施供给侧公司，而不只是传统企业软件公司。反过来，如果云收入增长依赖高强度 capex 且利润率承压，市场可能会重新评估 AI 基建投资回报周期。

## 6. 待验证问题

- OCI 增长里有多少来自 AI 客户，多少来自传统云迁移。
- GPU / 数据中心产能是否限制短期收入确认。
- RPO 增长是否对应高质量客户和可持续毛利。
- 管理层是否给出下一财年的 capex、云收入和 margin 指引。
"""
    report_html = markdown_to_html(raw)
    body = f"""
<header class="site-header compact">
  <a class="brand" href="../../index.html" aria-label="MetaFinance home">
    <span class="brand-mark">MF</span>
    <span><strong>MetaFinance</strong><small>AI Investment Intelligence</small></span>
  </a>
  <nav>
    <a href="../../index.html#reports">Reports</a>
    <a href="../index.html">Earnings</a>
    <a href="../../feed.json">Data</a>
  </nav>
</header>
<main class="report-page">
  <aside class="report-aside">
    <div class="date-label">ORCL · Q4 FY2026</div>
    <h2>Earnings Brief</h2>
    <p>Demo 页面用于展示官方财报抓取和财报分析 skill 的最终发布效果。</p>
    <div class="report-toc">
      <span>Contents</span>
      <a href="#1-一句话结论">一句话结论</a>
      <a href="#2-官方来源">官方来源</a>
      <a href="#3-ai-相关看点">AI 相关看点</a>
      <a href="#4-财务指标面板">财务指标面板</a>
      <a href="#5-投资含义">投资含义</a>
    </div>
    <a class="back-link" href="../index.html">← Back to earnings</a>
  </aside>
  <article class="markdown-body">
    {report_html}
  </article>
</main>
"""
    return layout(
        "MetaFinance · ORCL Q4 FY2026 Earnings Demo",
        body,
        description="Oracle earnings analysis demo for AI infrastructure investors.",
        css_href="../../assets/styles.css",
    )


def report_layout(report: Report, lang: str = "zh", alt_href_override: str | None = None) -> str:
    is_en = lang == "en"
    home_href = "../index.html" if not is_en else "../index.html"
    data_href = "../feed.json" if not is_en else "../feed.json"
    earnings_href = "../earnings/index.html" if not is_en else "../../earnings/index.html"
    alt_href = alt_href_override or (f"../en/reports/{report.date}.html" if not is_en else f"../../reports/{report.date}.html")
    alt_label = "English" if not is_en else "中文"
    aside_text = (
        "English edition for global AI investment tracking."
        if is_en
        else "中文为主，保留英文公司与产品名，面向全球 AI 投资跟踪。"
    )
    back_text = "Back to reports" if is_en else "Back to reports"
    toc_items = "\n".join(
        f'<a href="#{slugify(section)}">{escape(section)}</a>' for section in report.sections[:7]
    )
    body = f"""
<header class="site-header compact">
  <a class="brand" href="../index.html" aria-label="MetaFinance home">
    <span class="brand-mark">MF</span>
    <span><strong>MetaFinance</strong><small>AI Investment Intelligence</small></span>
  </a>
  <nav>
    <a href="{home_href}">Reports</a>
    <a href="{earnings_href}">Earnings</a>
    <a href="{data_href}">Data</a>
    <a class="lang-link" href="{alt_href}">{alt_label}</a>
  </nav>
</header>
<main class="report-page">
  <aside class="report-aside">
    <div class="date-label">{escape(report.date)}</div>
    <h2>Daily Brief</h2>
    <p>{escape(aside_text)}</p>
    <div class="report-toc">
      <span>Contents</span>
      {toc_items}
    </div>
    <a class="back-link" href="{home_href}">← {escape(back_text)}</a>
  </aside>
  <article class="markdown-body">
    {report.html}
  </article>
</main>
"""
    css_href = "../assets/styles.css" if not is_en else "../../assets/styles.css"
    html_lang = "en" if is_en else "zh-CN"
    return layout(f"MetaFinance · {report.date}", body, lang=html_lang, css_href=css_href)


def index_layout(reports: list[Report], lang: str = "zh", earnings_reports: list[EarningsReport] | None = None) -> str:
    is_en = lang == "en"
    latest = reports[0]
    overview_items = "\n".join(f"<li>{inline_markdown(item)}</li>" for item in latest.overview[:5])
    event_items = "\n".join(
        f'<li><a href="{latest.url}#{escape(anchor)}">{escape(event)}</a></li>'
        for event, anchor in latest.event_anchors[:8]
    )
    cards = "\n".join(report_card(report, latest=(idx == 0), lang=lang) for idx, report in enumerate(reports[:2]))
    archive = report_table(reports, lang=lang)
    total_events = sum(len(report.events) for report in reports)
    home_href = "index.html"
    data_href = "feed.json"
    earnings_href = "earnings/index.html" if not is_en else "../earnings/index.html"
    alt_href = "en/index.html" if not is_en else "../index.html"
    alt_label = "English" if not is_en else "中文"
    hero_kicker = "Global AI Markets · 中文 / English" if not is_en else "Global AI Markets · English Edition"
    lead = (
        "Daily intelligence on frontier AI, semiconductors, cloud infrastructure, enterprise adoption, energy and capital flows."
        if is_en
        else "Daily intelligence on frontier AI, semiconductors, cloud infrastructure, enterprise adoption, energy and capital flows."
    )
    latest_label = "Latest Brief" if is_en else "Latest Brief"
    today_label = "Today" if is_en else "Today"
    events_heading = "Key Events" if is_en else "关键事件"
    framework_heading = "Research Framework" if is_en else "研究框架"
    archive_heading = "Report Archive" if is_en else "日报列表"
    archive_kicker = "Archive" if is_en else "Archive"
    read_latest = "Read latest" if is_en else "Read latest"
    browse_archive = "Browse archive" if is_en else "Browse archive"

    body = f"""
<header class="site-header">
  <a class="brand" href="{home_href}" aria-label="MetaFinance home">
    <span class="brand-mark">MF</span>
    <span><strong>MetaFinance</strong><small>AI Investment Intelligence</small></span>
  </a>
  <nav>
    <a href="#reports">Reports</a>
    <a href="{earnings_href}">Earnings</a>
    <a href="{data_href}">Data</a>
    <a class="lang-link" href="{alt_href}">{alt_label}</a>
  </nav>
</header>

<main>
  <section class="hero-band">
    <div class="hero-copy">
      <p class="eyebrow">{escape(hero_kicker)}</p>
      <h1>MetaFinance</h1>
      <p class="lead">{escape(lead)}</p>
      <div class="hero-actions">
        <a href="{latest.url}">{escape(read_latest)}</a>
        <a href="#reports">{escape(browse_archive)}</a>
      </div>
    </div>
    <div class="signal-panel" aria-label="Latest report summary">
      <div class="panel-topline">
        <span>{escape(latest_label)}</span>
        <strong>{escape(latest.date)}</strong>
      </div>
      <ul>{overview_items}</ul>
    </div>
  </section>

  <section class="source-strip" aria-label="Monitored sources">
    <span>Monitored sources</span>
    <p>Anthropic · NVIDIA · AMD · Google Cloud · AWS · Microsoft · OpenAI · TSMC · SK Hynix · Cloudflare</p>
  </section>

  <section class="metrics-strip" aria-label="Report coverage">
    <div><strong>{len(reports)}</strong><span>Reports</span></div>
    <div><strong>{total_events}</strong><span>Signals</span></div>
    <div><strong>6</strong><span>Coverage layers</span></div>
    <div><strong>CN / EN</strong><span>Editions</span></div>
  </section>

  <section class="content-grid">
    <div class="latest-summary">
      <div class="section-heading">
        <p>{escape(today_label)}</p>
        <h2>{escape(events_heading)}</h2>
      </div>
      <ul class="event-list">{event_items}</ul>
    </div>
    <div class="market-map" aria-label="AI stack map">
      <div class="section-heading">
        <p>Coverage Map</p>
        <h2>{escape(framework_heading)}</h2>
      </div>
      <div class="layer-grid">
        <span>Models</span><span>Chips</span><span>Cloud</span>
        <span>Apps</span><span>Energy</span><span>Capital</span>
      </div>
    </div>
  </section>

  {earnings_preview(earnings_reports or [])}

  <section id="reports" class="reports-section">
    <div class="section-heading">
      <p>{escape(archive_kicker)}</p>
      <h2>{escape(archive_heading)}</h2>
    </div>
    {archive}
    <div class="report-list featured-reports">{cards}</div>
  </section>
</main>

<footer class="site-footer">
  <span>MetaFinance</span>
  <span>Generated from AI investment research reports.</span>
</footer>
"""
    css_href = "assets/styles.css" if not is_en else "../assets/styles.css"
    html_lang = "en" if is_en else "zh-CN"
    return layout("MetaFinance · AI Investment Intelligence", body, lang=html_lang, css_href=css_href)


def write_feed(path: Path, reports: list[Report]) -> None:
    feed = [
        {
            "date": report.date,
            "title": report.title,
            "url": report.url,
            "overview": report.overview,
            "events": report.events,
        }
        for report in reports
    ]
    path.write_text(json.dumps(feed, ensure_ascii=False, indent=2), encoding="utf-8")


def build() -> None:
    SITE_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    SITE_EARNINGS_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    SITE_EN_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    for old_page in SITE_EARNINGS_REPORTS_DIR.glob("*.html"):
        old_page.unlink()
    reports = [parse_report(path) for path in sorted(REPORTS_DIR.glob("*.md")) if DATE_RE.match(path.name)]
    reports.sort(key=lambda item: item.date, reverse=True)
    if not reports:
        raise SystemExit("No dated markdown reports found in reports/")

    en_dates = {path.stem for path in REPORTS_EN_DIR.glob("*.md") if DATE_RE.match(path.name)}
    for report in reports:
        alt_href = f"../en/reports/{report.date}.html" if report.date in en_dates else "../en/index.html"
        page = report_layout(report, lang="zh", alt_href_override=alt_href)
        (SITE_REPORTS_DIR / f"{report.date}.html").write_text(page, encoding="utf-8")

    earnings_reports = [
        parse_earnings_report(path)
        for path in sorted(REPORTS_EARNINGS_DIR.glob("*.md"))
        if EARNINGS_RE.match(path.name)
    ]
    earnings_reports.sort(key=lambda item: item.report_id, reverse=True)
    if earnings_reports:
        for report in earnings_reports:
            (SITE_EARNINGS_REPORTS_DIR / f"{report.report_id}.html").write_text(earnings_report_layout(report), encoding="utf-8")
    else:
        (SITE_EARNINGS_REPORTS_DIR / "ORCL-Q4-FY2026.html").write_text(oracle_demo_report_layout(), encoding="utf-8")

    (SITE_DIR / "index.html").write_text(index_layout(reports, lang="zh", earnings_reports=earnings_reports), encoding="utf-8")
    (SITE_EARNINGS_DIR / "index.html").write_text(earnings_index_layout(earnings_reports), encoding="utf-8")
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")
    write_feed(SITE_DIR / "feed.json", reports)

    en_reports = [parse_report(path, lang="en") for path in sorted(REPORTS_EN_DIR.glob("*.md")) if DATE_RE.match(path.name)]
    en_reports.sort(key=lambda item: item.date, reverse=True)
    if en_reports:
        for report in en_reports:
            page = report_layout(report, lang="en")
            (SITE_EN_REPORTS_DIR / f"{report.date}.html").write_text(page, encoding="utf-8")
        (SITE_EN_DIR / "index.html").write_text(index_layout(en_reports, lang="en"), encoding="utf-8")
        write_feed(SITE_EN_DIR / "feed.json", en_reports)

    print(f"Built {len(reports)} CN reports and {len(en_reports)} EN reports into {SITE_DIR}")


if __name__ == "__main__":
    build()
