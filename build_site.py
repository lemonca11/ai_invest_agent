from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"
REPORTS_EN_DIR = ROOT / "reports_en"
SITE_DIR = ROOT / "site"
SITE_REPORTS_DIR = SITE_DIR / "reports"
SITE_EN_DIR = SITE_DIR / "en"
SITE_EN_REPORTS_DIR = SITE_EN_DIR / "reports"
ASSETS_DIR = SITE_DIR / "assets"


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
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


def report_layout(report: Report, lang: str = "zh", alt_href_override: str | None = None) -> str:
    is_en = lang == "en"
    home_href = "../index.html" if not is_en else "../index.html"
    data_href = "../feed.json" if not is_en else "../feed.json"
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


def index_layout(reports: list[Report], lang: str = "zh") -> str:
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
    SITE_EN_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    reports = [parse_report(path) for path in sorted(REPORTS_DIR.glob("*.md")) if DATE_RE.match(path.name)]
    reports.sort(key=lambda item: item.date, reverse=True)
    if not reports:
        raise SystemExit("No dated markdown reports found in reports/")

    en_dates = {path.stem for path in REPORTS_EN_DIR.glob("*.md") if DATE_RE.match(path.name)}
    for report in reports:
        alt_href = f"../en/reports/{report.date}.html" if report.date in en_dates else "../en/index.html"
        page = report_layout(report, lang="zh", alt_href_override=alt_href)
        (SITE_REPORTS_DIR / f"{report.date}.html").write_text(page, encoding="utf-8")

    (SITE_DIR / "index.html").write_text(index_layout(reports, lang="zh"), encoding="utf-8")
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
