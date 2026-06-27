from __future__ import annotations

import json
import os
from pathlib import Path

from flask import Flask, Response, jsonify, make_response, request, send_file
import requests
from openai import OpenAI


DEFAULT_MARKET_DATA_URL = "https://lemonca11.github.io/ai_invest_agent/market/market_data.json"
DEFAULT_ALLOWED_ORIGIN = "https://lemonca11.github.io"
BASE_DIR = Path(__file__).resolve().parents[1]
SITE_DIR = BASE_DIR / "site"
app = Flask(__name__)


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def with_cors(response: Response) -> Response:
    origin = env("ALLOWED_ORIGIN", DEFAULT_ALLOWED_ORIGIN)
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def json_response(payload: dict, status: int = 200) -> Response:
    response = make_response(jsonify(payload), status)
    return with_cors(response)


def static_file_for_path(path: str) -> Path | None:
    normalized = path.split("?", 1)[0].split("#", 1)[0]
    if normalized in {"", "/"}:
        candidate = SITE_DIR / "index.html"
    elif normalized in {"/market", "/market/"}:
        candidate = SITE_DIR / "market" / "index.html"
    elif normalized in {"/earnings", "/earnings/"}:
        candidate = SITE_DIR / "earnings" / "index.html"
    elif normalized in {"/en", "/en/"}:
        candidate = SITE_DIR / "en" / "index.html"
    elif normalized == "/feed.json":
        candidate = SITE_DIR / "feed.json"
    elif normalized.startswith("/assets/"):
        candidate = SITE_DIR / normalized.removeprefix("/")
    else:
        candidate = SITE_DIR / normalized.removeprefix("/")
        if candidate.is_dir():
            candidate = candidate / "index.html"
    try:
        candidate.resolve().relative_to(SITE_DIR.resolve())
    except Exception:
        return None
    return candidate if candidate.is_file() else None


def compact_market_context(question: str, market_data: dict) -> dict:
    q = question.lower()
    groups = market_data.get("groups", {})
    signals = market_data.get("signals", [])
    by_name = {row.get("name"): row for row in signals}

    selected_group = None
    for group in groups:
        if group and group in question:
            selected_group = group
            break

    selected_stock = None
    aliases = {
        "英伟达": "NVIDIA",
        "美光": "Micron",
        "微软": "Microsoft",
        "谷歌": "Google",
        "亚马逊": "Amazon",
        "台积电": "TSMC",
        "博通": "Broadcom",
    }
    for alias, name in aliases.items():
        if alias in question:
            selected_stock = name
            break
    if not selected_stock:
        for row in signals:
            name = str(row.get("name", ""))
            symbol = str(row.get("symbol", ""))
            if name and name.lower() in q:
                selected_stock = name
                break
            if symbol and symbol.lower() in q:
                selected_stock = name
                break

    context = {
        "latest_date": market_data.get("latest_date"),
        "summaries": market_data.get("summaries", []),
    }
    if selected_group:
        names = groups.get(selected_group, [])
        context["selected_group"] = selected_group
        context["group_signals"] = [by_name[name] for name in names if name in by_name]
        context["group_correlation"] = market_data.get("correlations", {}).get(selected_group, {})
    elif selected_stock and selected_stock in by_name:
        stock_groups = [group for group, names in groups.items() if selected_stock in names]
        context["selected_stock"] = by_name[selected_stock]
        context["stock_groups"] = stock_groups
        context["related_group_data"] = {
            group: {
                "signals": [by_name[name] for name in groups.get(group, []) if name in by_name],
                "correlation": market_data.get("correlations", {}).get(group, {}),
            }
            for group in stock_groups[:2]
        }
    else:
        context["top_score"] = sorted(signals, key=lambda row: float(row.get("score") or 0), reverse=True)[:15]
        context["bottom_score"] = sorted(signals, key=lambda row: float(row.get("score") or 0))[:10]
    return context


def call_kimi(question: str, market_context: dict) -> str:
    api_key = env("KIMI_API_KEY")
    if not api_key:
        raise RuntimeError("KIMI_API_KEY is not configured")

    client = OpenAI(
        api_key=api_key,
        base_url=env("KIMI_BASE_URL", "https://api.moonshot.ai/v1"),
    )
    model = env("KIMI_MODEL", "kimi-k2.6")
    response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        messages=[
            {
                "role": "system",
                "content": (
                    "你是 MetaFinance 的市场数据助手。"
                    "你只能基于用户提供的 market_context 回答，不要编造缺失数据。"
                    "不要给直接买卖建议；输出应简洁、可操作、说明口径。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "question": question,
                        "market_context": market_context,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    )
    return response.choices[0].message.content or ""


@app.after_request
def add_cors_headers(response: Response) -> Response:
    return with_cors(response)


@app.route("/api/chat", methods=["GET"])
def chat_get() -> Response:
    return json_response(
        {
            "error": "Method not allowed",
            "message": 'Use POST with a JSON body: {"question": "..."}',
        },
        status=405,
    )


@app.route("/api/chat", methods=["POST"])
def chat_post() -> Response:
    try:
        payload = request.get_json(silent=True) or {}
        question = str(payload.get("question", "")).strip()
        if not question:
            return json_response({"answer": "问题不能为空。"}, status=400)

        market_data_url = env("MARKET_DATA_URL", DEFAULT_MARKET_DATA_URL)
        market_data = requests.get(market_data_url, timeout=20).json()
        market_context = compact_market_context(question, market_data)
        answer = call_kimi(question, market_context)
        return json_response({"answer": answer}, status=200)
    except Exception as exc:
        return json_response({"answer": f"Kimi 后端暂不可用：{exc}"}, status=500)


@app.route("/", defaults={"path": ""}, methods=["GET"])
@app.route("/<path:path>", methods=["GET"])
def serve_site(path: str) -> Response:
    file_path = static_file_for_path(f"/{path}")
    if file_path is None:
        return json_response({"error": "Not found", "path": path}, status=404)
    return with_cors(send_file(file_path))
