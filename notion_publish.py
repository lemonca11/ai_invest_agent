import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path

import requests
import yaml


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "notion.yaml"
NOTION_VERSION = "2022-06-28"
MAX_RICH_TEXT = 1900
MAX_CHILDREN_PER_REQUEST = 90


def parse_args():
    parser = argparse.ArgumentParser(description="Publish a local Markdown report to Notion.")
    parser.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Report date in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument(
        "--input",
        default=None,
        help="Markdown file path. Defaults to reports/DATE.md.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render blocks and print a summary without calling Notion.",
    )
    return parser.parse_args()


def load_config():
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def extract_page_id(value):
    value = (value or "").strip()
    if not value:
        raise ValueError("NOTION_PARENT_PAGE_ID 为空")

    matches = re.findall(r"[0-9a-fA-F]{32}", value)
    if matches:
        return matches[-1]

    compact = value.replace("-", "")
    if re.fullmatch(r"[0-9a-fA-F]{32}", compact):
        return compact

    raise ValueError("无法从 NOTION_PARENT_PAGE_ID 中解析 Notion page id")


def rich_text(text, bold=False):
    text = text or ""
    chunks = []
    while text:
        part = text[:MAX_RICH_TEXT]
        text = text[MAX_RICH_TEXT:]
        chunks.append({
            "type": "text",
            "text": {"content": part},
            "annotations": {"bold": bold},
        })
    return chunks or [{"type": "text", "text": {"content": ""}}]


def paragraph_block(text):
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": rich_text(text)},
    }


def heading_block(level, text):
    block_type = f"heading_{min(max(level, 1), 3)}"
    return {
        "object": "block",
        "type": block_type,
        block_type: {"rich_text": rich_text(text)},
    }


def bullet_block(text):
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": rich_text(text)},
    }


def numbered_block(text):
    return {
        "object": "block",
        "type": "numbered_list_item",
        "numbered_list_item": {"rich_text": rich_text(text)},
    }


def quote_block(text):
    return {
        "object": "block",
        "type": "quote",
        "quote": {"rich_text": rich_text(text)},
    }


def divider_block():
    return {
        "object": "block",
        "type": "divider",
        "divider": {},
    }


def code_block(text, language="plain text"):
    return {
        "object": "block",
        "type": "code",
        "code": {
            "rich_text": rich_text(text),
            "language": language,
        },
    }


def strip_md_inline(text):
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    text = text.replace("**", "")
    text = text.replace("__", "")
    text = text.replace("`", "")
    return text.strip()


def markdown_to_blocks(markdown):
    blocks = []
    paragraph_lines = []
    code_lines = []
    in_code = False
    code_language = "plain text"

    def flush_paragraph():
        nonlocal paragraph_lines
        if paragraph_lines:
            text = strip_md_inline(" ".join(line.strip() for line in paragraph_lines))
            if text:
                blocks.append(paragraph_block(text))
            paragraph_lines = []

    def flush_code():
        nonlocal code_lines, code_language
        blocks.append(code_block("\n".join(code_lines), code_language))
        code_lines = []
        code_language = "plain text"

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()

        if line.startswith("```"):
            if in_code:
                flush_code()
                in_code = False
            else:
                flush_paragraph()
                in_code = True
                code_language = line[3:].strip() or "plain text"
            continue

        if in_code:
            code_lines.append(line)
            continue

        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            continue

        if stripped in {"---", "***", "___"}:
            flush_paragraph()
            blocks.append(divider_block())
            continue

        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            blocks.append(heading_block(level, strip_md_inline(heading.group(2))))
            continue

        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet:
            flush_paragraph()
            blocks.append(bullet_block(strip_md_inline(bullet.group(1))))
            continue

        numbered = re.match(r"^\d+\.\s+(.+)$", stripped)
        if numbered:
            flush_paragraph()
            blocks.append(numbered_block(strip_md_inline(numbered.group(1))))
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            blocks.append(quote_block(strip_md_inline(stripped.lstrip(">").strip())))
            continue

        if "|" in stripped and stripped.startswith("|"):
            flush_paragraph()
            table_text = strip_md_inline(stripped.strip("|").replace("|", " | "))
            if not re.fullmatch(r"[-:\s|]+", stripped):
                blocks.append(paragraph_block(table_text))
            continue

        paragraph_lines.append(stripped)

    if in_code:
        flush_code()
    flush_paragraph()

    return blocks


def notion_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def notion_request(method, url, token, payload=None):
    response = requests.request(
        method,
        url,
        headers=notion_headers(token),
        data=json.dumps(payload) if payload is not None else None,
        timeout=30,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Notion API error {response.status_code}: {response.text}")
    return response.json()


def create_page(token, parent_page_id, title):
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "properties": {
            "title": {
                "title": rich_text(title)
            }
        },
    }
    return notion_request("POST", "https://api.notion.com/v1/pages", token, payload)


def append_blocks(token, page_id, blocks):
    for start in range(0, len(blocks), MAX_CHILDREN_PER_REQUEST):
        chunk = blocks[start:start + MAX_CHILDREN_PER_REQUEST]
        payload = {"children": chunk}
        notion_request(
            "PATCH",
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            token,
            payload,
        )


def prepare_publish(report_date, input_path=None):
    config = load_config()
    token_env = config.get("token_env", "NOTION_TOKEN")
    parent_env = config.get("parent_page_id_env", "NOTION_PARENT_PAGE_ID")

    token = os.getenv(token_env)
    parent_value = os.getenv(parent_env)

    if not token:
        raise RuntimeError(f"环境变量 {token_env} 未设置")
    parent_page_id = extract_page_id(parent_value)

    report_path = Path(input_path) if input_path else BASE_DIR / "reports" / f"{report_date}.md"
    if not report_path.exists():
        raise FileNotFoundError(f"找不到日报文件：{report_path}")

    markdown = report_path.read_text(encoding="utf-8")
    blocks = markdown_to_blocks(markdown)
    title_prefix = config.get("title_prefix", "AI 投资情报日报")
    title = f"{title_prefix} - {report_date}"

    return {
        "blocks": blocks,
        "markdown": markdown,
        "parent_page_id": parent_page_id,
        "report_path": report_path,
        "title": title,
        "token": token,
    }


def dry_run_report(report_date, input_path=None):
    prepared = prepare_publish(report_date, input_path)
    return {
        "blocks": len(prepared["blocks"]),
        "parent_page_id": prepared["parent_page_id"],
        "report_path": str(prepared["report_path"]),
        "title": prepared["title"],
    }


def publish_report(report_date, input_path=None):
    prepared = prepare_publish(report_date, input_path)
    page = create_page(
        prepared["token"],
        prepared["parent_page_id"],
        prepared["title"],
    )
    page_id = page["id"]
    append_blocks(prepared["token"], page_id, prepared["blocks"])

    return {
        "blocks": len(prepared["blocks"]),
        "page_id": page_id,
        "title": prepared["title"],
        "url": page.get("url"),
    }


def main():
    args = parse_args()
    prepared = prepare_publish(args.date, args.input)

    if args.dry_run:
        print(f"Dry run: {prepared['report_path']}")
        print(f"Title: {prepared['title']}")
        print(f"Parent page id: {prepared['parent_page_id']}")
        print(f"Blocks: {len(prepared['blocks'])}")
        return

    result = publish_report(args.date, args.input)

    print(f"Notion 发布完成：{result['title']}")
    print(f"Page ID: {result['page_id']}")
    print(f"URL: {result['url']}")


if __name__ == "__main__":
    main()
