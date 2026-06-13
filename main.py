import os
import re
import json
import yaml
import hashlib
import logging
import requests
import feedparser
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone, timedelta

from site_parsers import parse_with_site_parser

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_PATH = os.path.join(BASE_DIR, "config", "sources.yaml")
DATA_DIR = os.path.join(BASE_DIR, "data")
LOG_DIR = os.path.join(BASE_DIR, "logs")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    filename=os.path.join(LOG_DIR, "run.log"),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# 日报默认抓 daily 的 core_watchlist + discovery
FETCH_CADENCES = set(
    item.strip()
    for item in os.getenv("FETCH_CADENCES", "daily").split(",")
    if item.strip()
)

FETCH_SOURCE_GROUPS = set(
    item.strip()
    for item in os.getenv("FETCH_SOURCE_GROUPS", "core_watchlist,discovery").split(",")
    if item.strip()
)

# 默认抓 high + medium，因为 discovery 通常是 medium
FETCH_PRIORITIES = set(
    item.strip()
    for item in os.getenv("FETCH_PRIORITIES", "high,medium").split(",")
    if item.strip()
)

# 今日重大事件窗口：72 小时
LOOKBACK_HOURS = int(os.getenv("LOOKBACK_HOURS", "72"))

# 近期重要变化窗口：168 小时 / 7 天
RECENT_SIGNAL_HOURS = int(os.getenv("RECENT_SIGNAL_HOURS", "168"))

MAX_RSS_ITEMS_PER_SOURCE = int(os.getenv("MAX_RSS_ITEMS_PER_SOURCE", "5"))
MAX_DETAIL_ITEMS_PER_SOURCE = int(os.getenv("MAX_DETAIL_ITEMS_PER_SOURCE", "3"))
DETAIL_TEXT_MAX_LINES = int(os.getenv("DETAIL_TEXT_MAX_LINES", "220"))

MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

BAD_LINK_TEXT = {
    "home", "about", "contact", "privacy", "terms", "cookie",
    "login", "sign in", "subscribe", "menu", "search",
    "careers", "investors", "events", "resources",
    "learn more", "read more", "view more", "see more",
}

BAD_URL_PARTS = [
    "mailto:",
    "javascript:",
    "#",
    "/privacy",
    "/terms",
    "/cookie",
    "/contact",
    "/careers",
    "/login",
    "/signin",
    "/search",
    "facebook.com",
    "twitter.com",
    "x.com",
    "linkedin.com",
    "youtube.com",
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def make_id(url, title=""):
    raw = f"{url}|{title}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def load_sources():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    sources = data.get("sources", [])
    filtered = []

    for source in sources:
        priority = source.get("priority", "medium")
        cadence = source.get("cadence", "manual")
        source_group = source.get("source_group", "background")

        if (
            priority in FETCH_PRIORITIES
            and cadence in FETCH_CADENCES
            and source_group in FETCH_SOURCE_GROUPS
        ):
            filtered.append(source)

    return filtered


def clean_html_text(html, max_lines=120):
    soup = BeautifulSoup(html or "", "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "form", "nav", "footer"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[:max_lines])


def extract_latest_date_from_text(text):
    if not text:
        return None

    candidates = []

    # May 21, 2026 / Apr 8, 2026
    pattern1 = (
        r"\b("
        r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
        r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|"
        r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
        r")\.?\s+(\d{1,2}),\s+(\d{4})\b"
    )

    for match in re.finditer(pattern1, text, flags=re.IGNORECASE):
        month_name = match.group(1).lower().replace(".", "")
        day = int(match.group(2))
        year = int(match.group(3))
        month = MONTHS.get(month_name)

        if month:
            try:
                candidates.append(datetime(year, month, day, tzinfo=timezone.utc))
            except ValueError:
                pass

    # 2026-05-21
    pattern2 = r"\b(\d{4})-(\d{2})-(\d{2})\b"

    for match in re.finditer(pattern2, text):
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))

        try:
            candidates.append(datetime(year, month, day, tzinfo=timezone.utc))
        except ValueError:
            pass

    if not candidates:
        return None

    return max(candidates)


def is_recent(dt):
    """
    今日重大事件窗口。
    默认最近 72 小时。
    """
    if not dt:
        return False

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=LOOKBACK_HOURS)

    # 防止未来日期误判
    if dt > now + timedelta(hours=6):
        return False

    return dt >= cutoff


def is_recent_signal(dt):
    """
    近期重要变化窗口。
    默认最近 168 小时 / 7 天。
    """
    if not dt:
        return False

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=RECENT_SIGNAL_HOURS)

    # 防止未来日期误判
    if dt > now + timedelta(hours=6):
        return False

    return dt >= cutoff


def parse_entry_datetime(entry):
    dt_tuple = None

    if getattr(entry, "published_parsed", None):
        dt_tuple = entry.published_parsed
    elif getattr(entry, "updated_parsed", None):
        dt_tuple = entry.updated_parsed

    if not dt_tuple:
        return None

    return datetime(*dt_tuple[:6], tzinfo=timezone.utc)


def classify_event_grade(item):
    if item.get("error"):
        return "failed_source"

    source_group = item.get("source_group")
    published_at = item.get("published_at")

    if published_at:
        try:
            dt = datetime.fromisoformat(published_at)

            if is_recent(dt):
                return "confirmed_event"

            if is_recent_signal(dt):
                return "recent_signal"

            return "old_event"
        except Exception:
            pass

    if source_group == "discovery":
        return "watch_signal"

    return "background_ref"


def build_item(
    source,
    title,
    url,
    content,
    published_at,
    time_quality,
    error=None,
    detail_fetched=False,
):
    item = {
        "id": make_id(url, title),
        "company": source.get("company"),
        "layer": source.get("layer"),
        "type": source.get("type", "web"),
        "source_group": source.get("source_group"),
        "source_url": source.get("url"),
        "url": url,
        "priority": source.get("priority"),
        "cadence": source.get("cadence"),
        "purpose": source.get("purpose"),
        "title": title,
        "content": content,
        "published_at": published_at,
        "fetched_at": now_iso(),
        "error": error,
        "time_quality": time_quality,
        "detail_fetched": detail_fetched,
    }

    item["event_grade"] = classify_event_grade(item)
    return item


def get_page(url):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    response = requests.get(url, headers=headers, timeout=25)
    response.raise_for_status()
    return response.text


def is_bad_link(href, text):
    if not href:
        return True

    href_lower = href.lower()
    text_lower = (text or "").strip().lower()

    if any(part in href_lower for part in BAD_URL_PARTS):
        return True

    if text_lower in BAD_LINK_TEXT:
        return True

    if len(text_lower) < 8:
        return True

    return False


def normalize_candidate_title(text):
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return ""

    for line in lines:
        if 12 <= len(line) <= 180:
            return line

    return lines[0][:180]


def get_parent_context(anchor, max_levels=4):
    texts = []

    node = anchor
    for _ in range(max_levels):
        if not node:
            break

        node = node.parent

        if not node:
            break

        text = node.get_text(separator="\n", strip=True)

        if text:
            texts.append(text)

    return "\n".join(texts)


def discover_detail_candidates(source, html):
    """
    通用详情页候选发现。
    只做兜底。
    核心来源优先走 site_parsers.py 的专项解析器。
    """
    source_url = source["url"]
    soup = BeautifulSoup(html or "", "html.parser")

    candidates = []
    seen = set()

    for a in soup.find_all("a"):
        href = a.get("href")
        text = a.get_text(separator=" ", strip=True)

        if is_bad_link(href, text):
            continue

        detail_url = urljoin(source_url, href)

        if detail_url in seen:
            continue

        source_domain = urlparse(source_url).netloc
        detail_domain = urlparse(detail_url).netloc

        if source_domain and detail_domain and source_domain != detail_domain:
            continue

        context = get_parent_context(a, max_levels=4)
        context_date = extract_latest_date_from_text(context)

        if not context_date or not is_recent_signal(context_date):
            continue

        title = normalize_candidate_title(text or context)

        if not title:
            continue

        candidates.append({
            "title": title,
            "url": detail_url,
            "published_at": context_date,
            "context": context,
        })

        seen.add(detail_url)

        if len(candidates) >= MAX_DETAIL_ITEMS_PER_SOURCE:
            break

    return candidates


def extract_detail_content(detail_html):
    """
    详情页正文清洗。
    通用版本，核心站点后续继续在 site_parsers.py 中专项优化。
    """
    return clean_html_text(detail_html, max_lines=DETAIL_TEXT_MAX_LINES)


def fetch_detail_item(source, candidate):
    detail_url = candidate["url"]
    title = candidate.get("title") or ""

    try:
        detail_html = get_page(detail_url)
        detail_soup = BeautifulSoup(detail_html, "html.parser")

        page_title = detail_soup.title.string.strip() if detail_soup.title else ""
        detail_title = title or page_title

        content = extract_detail_content(detail_html)

        detail_date = extract_latest_date_from_text(content) or candidate["published_at"]

        item = build_item(
            source=source,
            title=detail_title,
            url=detail_url,
            content=content,
            published_at=detail_date.isoformat() if detail_date else None,
            time_quality="detail_page_extracted",
            error=None,
            detail_fetched=True,
        )

        if item["event_grade"] == "old_event":
            return None

        return item

    except Exception as e:
        logging.exception(f"Detail fetch failed: {detail_url}")

        return build_item(
            source=source,
            title=title,
            url=detail_url,
            content=candidate.get("context", ""),
            published_at=candidate["published_at"].isoformat()
            if candidate.get("published_at")
            else None,
            time_quality="list_context_only",
            error=f"detail_fetch_failed: {str(e)}",
            detail_fetched=False,
        )


def fetch_rss_source(source):
    source_url = source["url"]
    feed = feedparser.parse(source_url)

    items = []

    if feed.bozo:
        logging.warning(f"RSS parse warning: {source_url} | {feed.bozo_exception}")

    for entry in feed.entries[:MAX_RSS_ITEMS_PER_SOURCE * 3]:
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        summary = getattr(entry, "summary", "").strip()
        published_at_dt = parse_entry_datetime(entry)

        if not published_at_dt:
            continue

        if not is_recent_signal(published_at_dt):
            continue

        if not link:
            continue

        try:
            detail_html = get_page(link)
            content = extract_detail_content(detail_html)
            detail_fetched = True
        except Exception:
            content = clean_html_text(summary, max_lines=80)
            detail_fetched = False

        item = build_item(
            source=source,
            title=title,
            url=link,
            content=content,
            published_at=published_at_dt.isoformat(),
            time_quality="rss_published_at",
            error=None,
            detail_fetched=detail_fetched,
        )

        if item["event_grade"] != "old_event":
            items.append(item)

        if len(items) >= MAX_RSS_ITEMS_PER_SOURCE:
            break

    return items


def fetch_web_like_source(source):
    url = source["url"]

    try:
        # 1. 优先使用站点专项解析器
        site_items = parse_with_site_parser(
            source,
            lookback_hours=RECENT_SIGNAL_HOURS,
            max_items=MAX_DETAIL_ITEMS_PER_SOURCE,
        )

        if site_items is not None:
            parsed_items = []

            for site_item in site_items:
                item = build_item(
                    source=source,
                    title=site_item.get("title", ""),
                    url=site_item.get("url"),
                    content=site_item.get("content", ""),
                    published_at=site_item.get("published_at"),
                    time_quality=site_item.get("time_quality", "site_parser"),
                    error=None,
                    detail_fetched=site_item.get("detail_fetched", True),
                )

                if item["event_grade"] != "old_event":
                    parsed_items.append(item)

            return parsed_items

        # 2. 没有专项解析器，则走通用抓取
        html = get_page(url)
        soup = BeautifulSoup(html, "html.parser")
        page_title = soup.title.string.strip() if soup.title else ""

        candidates = discover_detail_candidates(source, html)

        detail_items = []

        for candidate in candidates:
            item = fetch_detail_item(source, candidate)

            if item:
                detail_items.append(item)

        if detail_items:
            return detail_items

        # 3. 如果找不到详情页，则退回页面级 item
        content = clean_html_text(html, max_lines=120)
        extracted_date = extract_latest_date_from_text(content)

        published_at = extracted_date.isoformat() if extracted_date else None
        time_quality = "extracted_from_text" if extracted_date else "unknown"

        item = build_item(
            source=source,
            title=page_title,
            url=url,
            content=content,
            published_at=published_at,
            time_quality=time_quality,
            error=None,
            detail_fetched=False,
        )

        if item["event_grade"] == "old_event":
            return []

        return [item]

    except Exception as e:
        logging.exception(f"Fetch failed: {url}")

        item = build_item(
            source=source,
            title="",
            url=url,
            content="",
            published_at=None,
            time_quality="unknown",
            error=str(e),
            detail_fetched=False,
        )

        return [item]


def fetch_source(source):
    source_type = source.get("type", "web")

    try:
        if source_type == "rss":
            return fetch_rss_source(source)

        return fetch_web_like_source(source)

    except Exception as e:
        logging.exception(f"Source fetch failed: {source.get('url')}")

        item = build_item(
            source=source,
            title="",
            url=source.get("url"),
            content="",
            published_at=None,
            time_quality="unknown",
            error=str(e),
            detail_fetched=False,
        )

        return [item]


def dedupe_items(items):
    seen = set()
    result = []

    for item in items:
        key = item.get("url") or item.get("id")

        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return result


def count_by(items, field):
    result = {}

    for item in items:
        key = item.get(field) or "unknown"
        result[key] = result.get(key, 0) + 1

    return result


def save_raw_items(items, source_count):
    today = datetime.now().strftime("%Y-%m-%d")
    output_path = os.path.join(DATA_DIR, f"raw_items_{today}.json")

    payload = {
        "generated_at": datetime.now().isoformat(),
        "fetch_priorities": sorted(FETCH_PRIORITIES),
        "fetch_cadences": sorted(FETCH_CADENCES),
        "fetch_source_groups": sorted(FETCH_SOURCE_GROUPS),
        "lookback_hours": LOOKBACK_HOURS,
        "recent_signal_hours": RECENT_SIGNAL_HOURS,
        "source_count": source_count,
        "item_count": len(items),
        "summary": {
            "by_source_group": count_by(items, "source_group"),
            "by_event_grade": count_by(items, "event_grade"),
            "by_layer": count_by(items, "layer"),
            "by_time_quality": count_by(items, "time_quality"),
            "detail_fetched": sum(1 for item in items if item.get("detail_fetched")),
        },
        "items": items,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return output_path


def main():
    logging.info("AI Invest Fetcher started")

    sources = load_sources()

    all_items = []

    for source in sources:
        source_items = fetch_source(source)
        all_items.extend(source_items)

    items = dedupe_items(all_items)
    output_path = save_raw_items(items, len(sources))

    error_count = sum(1 for item in items if item.get("error"))
    rss_count = sum(1 for item in items if item.get("type") == "rss")
    unknown_time_count = sum(1 for item in items if not item.get("published_at"))

    extracted_time_count = sum(
        1 for item in items
        if item.get("time_quality") in [
            "extracted_from_text",
            "detail_page_extracted",
            "list_context_only",
            "site_parser_amd",
            "site_parser_anthropic",
            "rss_published_at",
        ]
    )

    detail_fetched_count = sum(1 for item in items if item.get("detail_fetched"))

    source_group_count = count_by(items, "source_group")
    event_grade_count = count_by(items, "event_grade")
    time_quality_count = count_by(items, "time_quality")

    print(f"抓取完成：{output_path}")
    print(f"启用优先级：{', '.join(sorted(FETCH_PRIORITIES))}")
    print(f"启用频率：{', '.join(sorted(FETCH_CADENCES))}")
    print(f"启用来源组：{', '.join(sorted(FETCH_SOURCE_GROUPS))}")
    print(f"今日重大事件窗口：最近 {LOOKBACK_HOURS} 小时")
    print(f"近期重要变化窗口：最近 {RECENT_SIGNAL_HOURS} 小时")
    print(f"来源数量：{len(sources)}")
    print(f"内容条目：{len(items)}")
    print(f"RSS条目：{rss_count}")
    print(f"详情页正文条目：{detail_fetched_count}")
    print(f"提取到发布时间条目：{extracted_time_count}")
    print(f"发布时间未知条目：{unknown_time_count}")
    print(f"失败条目：{error_count}")
    print(f"source_group 分布：{source_group_count}")
    print(f"event_grade 分布：{event_grade_count}")
    print(f"time_quality 分布：{time_quality_count}")


if __name__ == "__main__":
    main()