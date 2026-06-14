from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parent
WATCHLIST_PATH = ROOT / "config" / "earnings_watchlist.yaml"
DATA_DIR = ROOT / "data"
EARNINGS_DATA_DIR = DATA_DIR / "earnings"
REPORTS_EARNINGS_DIR = ROOT / "reports_earnings"
SKILL_NAME = "科技股财报分析"
SEC_USER_AGENT = os.getenv("SEC_USER_AGENT", "MetaFinance ai_invest_agent research contact@example.com")


def load_watchlist(path: Path = WATCHLIST_PATH) -> list[dict]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return payload.get("companies", [])


def clean_text(html: str, max_lines: int = 260) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "form", "nav", "footer"]):
        tag.decompose()
    lines = [line.strip() for line in soup.get_text(separator="\n").splitlines() if line.strip()]
    return "\n".join(lines[:max_lines])


def fetch_page(url: str) -> tuple[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text, response.url


def fetch_json(url: str) -> dict:
    last_error = None
    for attempt in range(3):
        try:
            response = requests.get(url, headers={"User-Agent": SEC_USER_AGENT}, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise last_error


def fetch_sec_text(url: str) -> tuple[str, str]:
    last_error = None
    for attempt in range(3):
        try:
            response = requests.get(url, headers={"User-Agent": SEC_USER_AGENT}, timeout=30)
            response.raise_for_status()
            return response.text, response.url
        except requests.RequestException as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    raise last_error


def page_title(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    if soup.title and soup.title.get_text(strip=True):
        return soup.title.get_text(" ", strip=True)
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(" ", strip=True)
    return ""


def find_release_url(company: dict) -> str | None:
    official = company.get("official_sources") or {}
    if official.get("latest_release_url"):
        return official["latest_release_url"]

    # Placeholder for the next iteration: discover the latest earnings release
    # from company-specific IR pages.
    return None


def infer_status(company: dict, release_url: str | None) -> str:
    if release_url:
        return "released"
    expected = ((company.get("calendar") or {}).get("expected_date") or "")
    if expected and expected >= datetime.now().strftime("%Y-%m-%d"):
        return "upcoming"
    return "no_official_release"


def write_calendar(companies: list[dict]) -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    DATA_DIR.mkdir(exist_ok=True)
    rows = []
    for company in companies:
        release_url = find_release_url(company)
        calendar = company.get("calendar") or {}
        rows.append(
            {
                "ticker": company.get("ticker"),
                "company": company.get("company"),
                "priority": company.get("priority"),
                "layer": company.get("layer"),
                "ai_focus": company.get("ai_focus") or [],
                "fiscal_period": calendar.get("fiscal_period"),
                "expected_date": calendar.get("expected_date"),
                "timing": calendar.get("timing"),
                "status": infer_status(company, release_url),
                "official_release_url": release_url,
                "ir_home": (company.get("official_sources") or {}).get("ir_home"),
            }
        )

    path = DATA_DIR / f"earnings_calendar_{today}.json"
    path.write_text(json.dumps({"generated_at": datetime.now().isoformat(), "items": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def stable_report_id(ticker: str, fiscal_period: str) -> str:
    safe_period = re.sub(r"[^A-Za-z0-9]+", "-", fiscal_period).strip("-")
    return f"{ticker.upper()}-{safe_period}"


def extract_metric_hints(text: str) -> dict:
    compact = re.sub(r"\s+", " ", text)

    def first(pattern: str) -> str | None:
        match = re.search(pattern, compact, flags=re.IGNORECASE)
        if not match:
            return None
        return match.group(1).rstrip(",")

    hints = {}
    patterns = {
        "Q4 Total Revenues": r"Q4 Total Revenues\s+(\$[0-9][0-9.,]*\s*(?:billion|million)?)",
        "Q4 Total Cloud Revenues": r"Q4 Total Cloud Revenues\s+(\$[0-9][0-9.,]*\s*(?:billion|million)?)",
        "Q4 Cloud Infra IaaS Revenue": r"Q4 Cloud Infra\s*\(IaaS\)\s*Revenue\s+(\$[0-9][0-9.,]*\s*(?:billion|million)?)",
        "Q4 Cloud Apps SaaS Revenue": r"Q4 Cloud Apps\s*\(SaaS\)\s*Revenue\s+(\$[0-9][0-9.,]*\s*(?:billion|million)?)",
        "RPO Ending Balance": r"RPO.{0,140}?ended the quarter at\s+(\$[0-9][0-9.,]*\s*(?:billion|million)?)",
        "RPO Sequential Increase": r"RPO.{0,180}?up\s+(\$[0-9][0-9.,]*\s*(?:billion|million)?)\s+sequentially",
        "Q4 GAAP EPS": r"Q4 Earnings per Share GAAP.{0,80}?(\$[0-9][0-9.,]*)",
        "Q4 Non-GAAP EPS": r"Q4 Earnings per Share GAAP.{0,120}?non-GAAP.{0,40}?(\$[0-9][0-9.,]*)",
        "FY Operating Cash Flow": r"operating cash flow of\s+(\$[0-9][0-9.,]*\s*(?:billion|million)?)",
    }
    for label, pattern in patterns.items():
        value = first(pattern)
        if value:
            hints[label] = value

    free_cash_flow = first(r"Free cash flow was\s+(negative\s+\$[0-9][0-9.,]*\s*(?:billion|million)?)")
    if free_cash_flow:
        hints["FY Free Cash Flow"] = free_cash_flow
    return hints


def release_title_from_text(text: str, fallback: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip()
        if re.search(r"\bannounces\b.+\bresults\b", cleaned, flags=re.IGNORECASE):
            return cleaned
    return fallback


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def sec_cik(company: dict) -> str | None:
    cik = (company.get("official_sources") or {}).get("sec_cik")
    if not cik:
        return None
    return str(cik).zfill(10)


def select_sec_filing(company: dict) -> dict | None:
    cik = sec_cik(company)
    if not cik:
        return None

    submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    data = fetch_json(submissions_url)
    recent = (data.get("filings") or {}).get("recent") or {}
    forms = recent.get("form") or []
    accession_numbers = recent.get("accessionNumber") or []
    filing_dates = recent.get("filingDate") or []
    primary_docs = recent.get("primaryDocument") or []
    primary_descriptions = recent.get("primaryDocDescription") or []

    expected = parse_date((company.get("calendar") or {}).get("expected_date"))
    best = None
    best_distance = 10_000
    for index, form in enumerate(forms):
        if form not in {"8-K", "10-Q", "10-K"}:
            continue
        filing_date = parse_date(filing_dates[index] if index < len(filing_dates) else None)
        if not filing_date:
            continue
        distance = abs((filing_date - expected).days) if expected else index
        if expected and distance > 45:
            continue
        if distance < best_distance:
            best_distance = distance
            best = {
                "form": form,
                "accession_number": accession_numbers[index],
                "filing_date": filing_dates[index],
                "primary_document": primary_docs[index] if index < len(primary_docs) else "",
                "primary_description": primary_descriptions[index] if index < len(primary_descriptions) else "",
            }
    return best


def sec_archive_base(cik: str, accession_number: str) -> str:
    cik_no_zeros = str(int(cik))
    accession_no_dashes = accession_number.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{cik_no_zeros}/{accession_no_dashes}"


def select_sec_document(cik: str, filing: dict) -> dict:
    base = sec_archive_base(cik, filing["accession_number"])
    index_json = fetch_json(f"{base}/index.json")
    items = ((index_json.get("directory") or {}).get("item") or [])
    html_items = [
        item for item in items
        if str(item.get("name", "")).lower().endswith((".htm", ".html", ".txt"))
    ]

    def score(item: dict) -> tuple[int, str]:
        name = str(item.get("name", "")).lower()
        description = str(item.get("description", "")).lower()
        text = f"{name} {description}"
        value = 0
        if "ex-99" in text or "ex99" in text or "ex99_" in text or "ex_99" in text or "exhibit 99" in text:
            value += 100
        if "press release" in text or "earnings" in text or "results" in text:
            value += 50
        if name == str(filing.get("primary_document", "")).lower():
            value += 20
        return (-value, name)

    selected = sorted(html_items, key=score)[0] if html_items else {"name": filing.get("primary_document")}
    selected_url = f"{base}/{selected.get('name')}"
    return {
        "url": selected_url,
        "name": selected.get("name"),
        "description": selected.get("description") or filing.get("primary_description"),
    }


def fetch_sec_fallback(company: dict) -> dict | None:
    cik = sec_cik(company)
    if not cik:
        return None
    filing = select_sec_filing(company)
    if not filing:
        return None
    document = select_sec_document(cik, filing)
    html, final_url = fetch_sec_text(document["url"])
    text = clean_text(html, max_lines=900)
    if len(text) < 800:
        return {
            "fetch_status": "sec_content_incomplete",
            "error": "SEC filing was found but did not expose enough text for analysis.",
            "official_url": final_url,
            "title": document.get("description") or filing.get("primary_description") or final_url,
            "raw_text": text,
            "source_type": "sec_filing",
            "sec_filing": filing,
        }
    return {
        "fetch_status": "ok",
        "error": None,
        "official_url": final_url,
        "title": release_title_from_text(text, document.get("description") or filing.get("primary_description") or final_url),
        "raw_text": text,
        "source_type": "sec_filing",
        "sec_filing": filing,
    }


def fetch_release(company: dict) -> Path | None:
    release_url = find_release_url(company)
    if not release_url:
        return None

    calendar = company.get("calendar") or {}
    fiscal_period = calendar.get("fiscal_period") or "unknown-period"
    report_id = stable_report_id(company["ticker"], fiscal_period)
    final_url = release_url
    title = ""
    text = ""
    fetch_status = "ok"
    error = None
    try:
        html, final_url = fetch_page(release_url)
        title = page_title(html)
        text = clean_text(html)
    except requests.RequestException as exc:
        fetch_status = "fetch_failed"
        error = str(exc)

    if "Just a moment" in title or "Enable JavaScript and cookies" in text:
        fetch_status = "blocked"
        error = "Official IR page returned a bot challenge instead of earnings content."
    elif len(text) < 800:
        fetch_status = "content_incomplete"
        error = "Official IR page was reachable but did not expose enough text for analysis."

    if fetch_status != "ok":
        try:
            fallback = fetch_sec_fallback(company)
        except requests.RequestException as exc:
            fallback = {
                "fetch_status": "sec_fetch_failed",
                "error": str(exc),
            }
        if fallback and fallback.get("fetch_status") == "ok":
            fetch_status = "ok"
            error = None
            final_url = fallback["official_url"]
            title = fallback["title"]
            text = fallback["raw_text"]
            source_type = fallback["source_type"]
            sec_filing = fallback.get("sec_filing")
        else:
            source_type = "official_ir"
            sec_filing = fallback.get("sec_filing") if fallback else None
            if fallback and fallback.get("error"):
                error = f"{error} SEC fallback: {fallback.get('error')}"
    else:
        source_type = "official_ir"
        sec_filing = None

    payload = {
        "id": hashlib.sha256(f"{company['ticker']}|{fiscal_period}|{final_url}".encode("utf-8")).hexdigest()[:16],
        "ticker": company.get("ticker"),
        "company": company.get("company"),
        "layer": company.get("layer"),
        "ai_focus": company.get("ai_focus") or [],
        "fiscal_period": fiscal_period,
        "expected_date": calendar.get("expected_date"),
        "source_type": source_type,
        "official_url": final_url,
        "title": title,
        "fetched_at": datetime.now().isoformat(),
        "fetch_status": fetch_status,
        "error": error,
        "raw_text": text,
        "metric_hints": extract_metric_hints(text),
        "sec_filing": sec_filing,
        "report_id": report_id,
    }
    EARNINGS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = EARNINGS_DATA_DIR / f"{report_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_analysis_markdown(raw: dict) -> str:
    ai_focus = "、".join(raw.get("ai_focus") or [])
    metrics = raw.get("metric_hints") or {}
    metric_rows = "\n".join(
        f"| {key} | {value} | 待补充 | 待补充 | 待补充 | 自动抽取，需复核 |"
        for key, value in metrics.items()
    ) or "| Revenue | 待补充 | 待补充 | 待补充 | 待补充 | 需要从官方公告和 SEC 文件复核 |"

    return f"""# {raw.get('ticker')} {raw.get('fiscal_period')} 财报解读

## 1. 核心结论

| 维度 | 判断 |
|---|---|
| 财报质量 | 待分析 |
| 增长质量 | 待分析 |
| 利润质量 | 待分析 |
| 现金流质量 | 待分析 |
| 指引质量 | 待分析 |
| 估值压力 | 待分析 |
| 股价反应 | 待分析 |

一句话结论：

> {raw.get('company')} 本期财报需要围绕 {ai_focus or raw.get('layer')} 判断：官方公告已经获取，下一步应按《{SKILL_NAME}》复核市场预期、业务拆解、利润质量、现金流、指引和估值。

## 2. 官方来源

| 字段 | 内容 |
|---|---|
| 公司 | {raw.get('company')} |
| Ticker | {raw.get('ticker')} |
| 财报期 | {raw.get('fiscal_period')} |
| 来源类型 | {raw.get('source_type')} |
| 官方链接 | [{raw.get('title') or raw.get('official_url')}]({raw.get('official_url')}) |

## 3. 市场预期

| 指标 | 市场预期 | 实际结果 | 差异 |
|---|---:|---:|---:|
| Revenue | 待补充 | 待补充 | 待补充 |
| EPS | 待补充 | 待补充 | 待补充 |
| Guidance | 待补充 | 待补充 | 待补充 |

## 4. 财报结果

| 指标 | 本季度 | 去年同期 | YoY | 环比 | 评价 |
|---|---:|---:|---:|---:|---|
{metric_rows}

## 5. 业务拆解

| 业务线 | 收入 | YoY | 占比 | 评价 |
|---|---:|---:|---:|---|
| AI / Cloud 相关 | 待补充 | 待补充 | 待补充 | 重点关注 {ai_focus or raw.get('layer')} |

核心判断：

待分析。

## 6. 利润质量

| 指标 | 本季度 | 去年同期 | 变化 | 评价 |
|---|---:|---:|---:|---|
| Gross Margin | 待补充 | 待补充 | 待补充 | 待分析 |
| Operating Margin | 待补充 | 待补充 | 待补充 | 待分析 |
| SBC | 待补充 | 待补充 | 待补充 | 待分析 |
| GAAP / Non-GAAP 差异 | 待补充 | 待补充 | 待补充 | 待分析 |

核心判断：

待分析。

## 7. 现金流质量

| 指标 | 本季度 | 去年同期 | 变化 | 评价 |
|---|---:|---:|---:|---|
| Operating Cash Flow | 待补充 | 待补充 | 待补充 | 待分析 |
| CapEx | 待补充 | 待补充 | 待补充 | 待分析 |
| Free Cash Flow | 待补充 | 待补充 | 待补充 | 待分析 |
| FCF Margin | 待补充 | 待补充 | 待补充 | 待分析 |

核心判断：

待分析。

## 8. 指引

| 项目 | 公司指引 | 市场预期 | 差异 | 评价 |
|---|---:|---:|---:|---|
| 下季度收入 | 待补充 | 待补充 | 待补充 | 待分析 |
| 下季度利润率 | 待补充 | 待补充 | 待补充 | 待分析 |
| 全年收入 | 待补充 | 待补充 | 待补充 | 待分析 |
| CapEx | 待补充 | 待补充 | 待补充 | 待分析 |

核心判断：

待分析。

## 9. 估值

| 指标 | 当前水平 | 历史区间 | 评价 |
|---|---:|---:|---|
| Forward PE | 待补充 | 待补充 | 待分析 |
| EV/Sales | 待补充 | 待补充 | 待分析 |
| FCF Yield | 待补充 | 待补充 | 待分析 |
| PEG | 待补充 | 待补充 | 待分析 |

核心判断：

待分析。

## 10. 股价反应

| 项目 | 结果 |
|---|---|
| 财报前1个月股价表现 | 待补充 |
| 财报后股价表现 | 待补充 |
| 期权隐含波动 | 待补充 |
| 是否 price in | 待补充 |
| 市场真正交易的变量 | 待补充 |

核心判断：

待分析。

## 11. AI 相关看点

- **关注范围**：{ai_focus or 'AI 相关业务线索'}。
- **官方事实**：本页内容来自公司 IR 官方公告，适合作为财报分析的主事实源。
- **待分析**：需要结合 Revenue / EPS / FCF / CapEx / RPO / 指引判断 AI 增长质量。

## 12. 看多理由

1. 待分析。
2. 待分析。
3. 待分析。

## 13. 看空理由

1. 待分析。
2. 待分析。
3. 待分析。

## 14. 下一季度跟踪指标

| 指标 | 为什么重要 |
|---|---|
| AI / Cloud 收入增速 | 验证 AI 需求是否转化为收入 |
| CapEx 与 FCF | 判断增长是否消耗现金流 |
| 指引和 RPO | 判断未来收入可见度 |

## 15. 最终判断

| 维度 | 分数 |
|---|---:|
| 财报质量 | /10 |
| 增长质量 | /10 |
| 利润质量 | /10 |
| 现金流质量 | /10 |
| 指引质量 | /10 |
| 估值压力 | /10 |

最终结论：

> 待分析。

## 16. 风险与待验证问题

- 官方公告中的非 GAAP 指标需要和 GAAP 指标分开解释。
- AI 相关收入线索需要避免把全部云收入直接等同为 AI 收入。
- 如果出现高 capex 或 backlog 增长，需要验证利润率和交付能力。
"""


def build_skill_input(raw: dict) -> str:
    return f"""你是一个美股科技股财报分析师。

请按照《{SKILL_NAME}》分析以下公司最新财报。

公司：{raw.get('company')}
Ticker：{raw.get('ticker')}
季度：{raw.get('fiscal_period')}
官方链接：{raw.get('official_url')}
AI 关注点：{"、".join(raw.get("ai_focus") or [])}

要求：
1. 先分析市场预期，再分析财报结果。
2. 拆解收入、利润、现金流、指引、估值和股价反应。
3. 必须区分 GAAP 和 Non-GAAP。
4. 必须关注 SBC、CapEx、FCF、毛利率、经营利润率。
5. 所有判断必须对应具体数据。
6. 输出 Markdown，尽量使用表格。

官方财报原文：

```text
{raw.get('raw_text') or ''}
```
"""


def analyze_release(raw_path: Path) -> Path:
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    if raw.get("fetch_status") != "ok":
        raise RuntimeError(f"Cannot analyze incomplete official release: {raw.get('error')}")
    REPORTS_EARNINGS_DIR.mkdir(parents=True, exist_ok=True)
    skill_input_path = raw_path.with_name(f"{raw['report_id']}_skill_input.md")
    skill_input_path.write_text(build_skill_input(raw), encoding="utf-8")
    output = REPORTS_EARNINGS_DIR / f"{raw['report_id']}.md"
    output.write_text(build_analysis_markdown(raw), encoding="utf-8")
    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch and generate AI earnings reports.")
    parser.add_argument("--ticker", help="Only process one ticker from the watchlist.")
    parser.add_argument("--calendar-only", action="store_true", help="Only write the earnings calendar JSON.")
    parser.add_argument("--fetch-only", action="store_true", help="Fetch official releases but do not generate Markdown.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    all_companies = load_watchlist()
    companies = all_companies
    if args.ticker:
        companies = [item for item in all_companies if item.get("ticker", "").upper() == args.ticker.upper()]
    if not companies:
        raise SystemExit("No matching earnings watchlist companies.")

    calendar_path = write_calendar(all_companies)
    print(f"Earnings calendar written: {calendar_path}")
    if args.calendar_only:
        return

    for company in companies:
        raw_path = fetch_release(company)
        if not raw_path:
            print(f"No official release configured yet: {company.get('ticker')}")
            continue
        print(f"Official release written: {raw_path}")
        if not args.fetch_only:
            try:
                report_path = analyze_release(raw_path)
            except RuntimeError as exc:
                print(f"Skipped analysis for {company.get('ticker')}: {exc}")
                continue
            print(f"Earnings analysis written: {report_path}")


if __name__ == "__main__":
    main()
