import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from datetime import datetime, timezone, timedelta

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


def get_page(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=25)
    response.raise_for_status()
    return response.text


def clean_text(html, max_lines=260):
    soup = BeautifulSoup(html or "", "html.parser")

    for tag in soup(["script", "style", "noscript", "svg", "form", "nav", "footer"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines[:max_lines])


def extract_dates(text):
    if not text:
        return []

    results = []

    pattern1 = (
        r"\b("
        r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|"
        r"Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t|tember)?|"
        r"Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
        r")\.?\s+(\d{1,2}),\s+(\d{4})\b"
    )

    for m in re.finditer(pattern1, text, flags=re.IGNORECASE):
        month_name = m.group(1).lower().replace(".", "")
        month = MONTHS.get(month_name)
        day = int(m.group(2))
        year = int(m.group(3))

        if month:
            try:
                results.append(datetime(year, month, day, tzinfo=timezone.utc))
            except ValueError:
                pass

    pattern2 = r"\b(\d{4})-(\d{2})-(\d{2})\b"

    for m in re.finditer(pattern2, text):
        year = int(m.group(1))
        month = int(m.group(2))
        day = int(m.group(3))

        try:
            results.append(datetime(year, month, day, tzinfo=timezone.utc))
        except ValueError:
            pass

    return results


def is_recent(dt, lookback_hours=72):
    if not dt:
        return False

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=lookback_hours)

    # 禁止未来日期误判
    if dt > now + timedelta(hours=6):
        return False

    return dt >= cutoff


def extract_title_from_detail(html, fallback=""):
    soup = BeautifulSoup(html or "", "html.parser")

    h1 = soup.find("h1")
    if h1:
        text = h1.get_text(" ", strip=True)
        if text:
            return text[:220]

    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    if title:
        return title[:220]

    return fallback[:220]


def get_same_domain_links(source_url, html):
    soup = BeautifulSoup(html or "", "html.parser")
    source_domain = urlparse(source_url).netloc

    links = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href")
        full_url = urljoin(source_url, href)

        if full_url in seen:
            continue

        domain = urlparse(full_url).netloc
        if domain != source_domain:
            continue

        text = a.get_text(" ", strip=True)

        links.append({
            "url": full_url,
            "text": text,
        })
        seen.add(full_url)

    return links


def parse_amd_press_releases(source, lookback_hours=72, max_items=5):
    """
    AMD 专项规则：
    - 列表页只负责发现 /detail/ 链接
    - 详情页日期才是最终日期
    - 详情页日期不在最近窗口内，直接丢弃
    """
    source_url = source["url"]
    html = get_page(source_url)

    links = get_same_domain_links(source_url, html)

    detail_links = []
    seen = set()

    for link in links:
        url = link["url"]

        if "/news-events/press-releases/detail/" not in url:
            continue

        if url in seen:
            continue

        detail_links.append(link)
        seen.add(url)

        if len(detail_links) >= max_items * 3:
            break

    items = []

    for link in detail_links:
        detail_html = get_page(link["url"])
        content = clean_text(detail_html, max_lines=280)

        dates = extract_dates(content)
        recent_dates = [d for d in dates if is_recent(d, lookback_hours)]

        if not recent_dates:
            continue

        published_at = max(recent_dates)
        title = extract_title_from_detail(detail_html, fallback=link.get("text", ""))

        items.append({
            "title": title,
            "url": link["url"],
            "published_at": published_at.isoformat(),
            "content": content,
            "time_quality": "site_parser_amd",
            "detail_fetched": True,
        })

        if len(items) >= max_items:
            break

    return items


def parse_anthropic_news(source, lookback_hours=72, max_items=5):
    """
    Anthropic 专项规则：
    - 列表页只负责发现 /news/ 或 /research/ 链接
    - 不再使用父级文本日期
    - 必须打开详情页，并以详情页正文日期为准
    - 详情页真实日期不在最近窗口内，直接丢弃
    """
    source_url = source["url"]
    html = get_page(source_url)

    links = get_same_domain_links(source_url, html)

    candidate_links = []
    seen = set()

    for link in links:
        url = link["url"].rstrip("/")

        if url == source_url.rstrip("/"):
            continue

        if "/news/" not in url and "/research/" not in url:
            continue

        # 排除列表页或无效入口
        if url.endswith("/news") or url.endswith("/research"):
            continue

        if url in seen:
            continue

        candidate_links.append(link)
        seen.add(url)

        if len(candidate_links) >= max_items * 4:
            break

    items = []

    for link in candidate_links:
        detail_html = get_page(link["url"])
        content = clean_text(detail_html, max_lines=300)

        dates = extract_dates(content)
        recent_dates = [d for d in dates if is_recent(d, lookback_hours)]

        # 关键：没有详情页近期日期，直接跳过
        if not recent_dates:
            continue

        published_at = max(recent_dates)
        title = extract_title_from_detail(detail_html, fallback=link.get("text", ""))

        items.append({
            "title": title,
            "url": link["url"],
            "published_at": published_at.isoformat(),
            "content": content,
            "time_quality": "site_parser_anthropic",
            "detail_fetched": True,
        })

        if len(items) >= max_items:
            break

    return items


def parse_with_site_parser(source, lookback_hours=72, max_items=5):
    company = source.get("company", "")

    if company == "AMD Press Releases":
        return parse_amd_press_releases(source, lookback_hours, max_items)

    if company == "Anthropic News":
        return parse_anthropic_news(source, lookback_hours, max_items)

    return None