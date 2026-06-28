from __future__ import annotations

import json
import os
import time
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
        context["top_score"] = sorted(signals, key=lambda row: float(row.get("score") or 0), reverse=True)[:6]
        context["bottom_score"] = sorted(signals, key=lambda row: float(row.get("score") or 0))[:4]
    return context


def build_evidence_cards(question: str, market_data: dict) -> dict:
    groups = market_data.get("groups", {})
    summaries = market_data.get("summaries", [])
    correlations = market_data.get("correlations", {})
    signals = market_data.get("signals", [])
    context = compact_market_context(question, market_data)
    cards: list[str] = []

    cards.append(
        f"市场时间点是 {market_data.get('latest_date', 'unknown')}，当前覆盖 {len(groups)} 个分类、{len(signals)} 只标的。"
    )

    summary_by_group = {item.get("group"): item for item in summaries}
    selected_group = context.get("selected_group")
    selected_stock = context.get("selected_stock")

    if selected_group:
        summary = summary_by_group.get(selected_group, {})
        if summary:
            cards.append(
                f"{selected_group} 这个分类当前总市值约为 {summary.get('market_cap_label', 'N/A')}，"
                f"20日成交额约 {summary.get('avg_dollar_volume_20d_label', 'N/A')}，"
                f"分类领涨标的是 {summary.get('leader', 'N/A')}。"
            )
        group_rows = sorted(context.get("group_signals", []), key=lambda row: float(row.get("score") or 0), reverse=True)[:4]
        for row in group_rows:
            cards.append(
                f"{row.get('name')}({row.get('symbol')}): 当前状态是 {row.get('state')}，"
                f"分数 {float(row.get('score') or 0):.0f}，20日涨跌 {float(row.get('ret_20d_pct') or 0):.2f}%，"
                f"量能变化 {float(row.get('volume_vs_20d_pct') or 0):.2f}%。"
            )
        hint = correlations.get(selected_group, {})
        for pair in hint.get("top_pairs", [])[:2]:
            cards.append(
                f"{selected_group} 内部相关性里，{pair.get('a')} 和 {pair.get('b')} 的相关系数约 {float(pair.get('corr') or 0):.2f}。"
            )
    elif selected_stock:
        row = selected_stock
        cards.append(
            f"{row.get('name')}({row.get('symbol')}) 当前状态是 {row.get('state')}，"
            f"分数 {float(row.get('score') or 0):.0f}，市值约 {row.get('market_cap_label', 'N/A')}，"
            f"20日涨跌 {float(row.get('ret_20d_pct') or 0):.2f}%，量能变化 {float(row.get('volume_vs_20d_pct') or 0):.2f}%。"
        )
        for group in context.get("stock_groups", [])[:2]:
            summary = summary_by_group.get(group, {})
            if summary:
                cards.append(
                    f"它所在的 {group} 分类总市值约 {summary.get('market_cap_label', 'N/A')}，"
                    f"分类领涨标的是 {summary.get('leader', 'N/A')}。"
                )
            related = context.get("related_group_data", {}).get(group, {})
            pair_text = related.get("correlation", {}).get("top_pairs", [])
            if pair_text:
                pair = pair_text[0]
                cards.append(
                    f"在 {group} 里，{pair.get('a')} 和 {pair.get('b')} 的相关系数约 {float(pair.get('corr') or 0):.2f}。"
                )
    else:
        leaders = sorted(signals, key=lambda row: float(row.get("score") or 0), reverse=True)[:5]
        for row in leaders:
            cards.append(
                f"{row.get('name')}({row.get('symbol')}) 处于 {row.get('state')}，"
                f"分数 {float(row.get('score') or 0):.0f}，20日涨跌 {float(row.get('ret_20d_pct') or 0):.2f}%，"
                f"量能变化 {float(row.get('volume_vs_20d_pct') or 0):.2f}%。"
            )
        for item in summaries[:3]:
            cards.append(
                f"{item.get('group')} 分类的总市值约 {item.get('market_cap_label', 'N/A')}，"
                f"20日成交额约 {item.get('avg_dollar_volume_20d_label', 'N/A')}，"
                f"当前领涨标的是 {item.get('leader', 'N/A')}。"
            )

    return {
        "question": question,
        "latest_date": market_data.get("latest_date"),
        "evidence_cards": cards[:8],
    }


def load_market_data() -> dict:
    local_path = SITE_DIR / "market" / "market_data.json"
    if local_path.is_file():
        return json.loads(local_path.read_text(encoding="utf-8"))
    return {}


def call_kimi(question: str, market_context: dict) -> str:
    api_key = env("KIMI_API_KEY")
    if not api_key:
        raise RuntimeError("KIMI_API_KEY is not configured")

    model = env("KIMI_MODEL", "kimi-k2.5")
    base_url = env("KIMI_BASE_URL", "https://api.moonshot.cn/v1").rstrip("/")
    response = requests.post(
        f"{base_url}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "temperature": 0.6,
            "top_p": 0.9,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是一个自然语言市场分析助手。"
                        "你只会看到问题和若干自然语言证据卡。"
                        "你的任务不是复述证据卡，而是把它们融成一段自然、连贯、像人说的话的分析。"
                        "不要输出列表式摘要，不要重复证据卡里的句式，不要提检索过程。"
                        "写法要像资深分析师对话，允许口语化，但要清楚、具体、自然。"
                        "可以一到三段，先说判断，再说依据，再说风险和观察点。"
                        "允许推断，但必须明确是推断。"
                        "不要给直接买卖建议。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"问题：{question}\n\n"
                        f"证据卡：\n- "
                        + "\n- ".join(market_context.get("evidence_cards", []))
                        + "\n\n请只基于以上证据写出自然、连贯的分析。"
                    ),
                },
            ],
        },
        timeout=12,
    )
    response.raise_for_status()
    payload = response.json()
    return (
        payload.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )


def fallback_answer(question: str, market_context: dict) -> str:
    cards = market_context.get("evidence_cards", [])
    if not cards:
        return "当前没有足够的市场证据来回答这个问题。"
    lead = cards[0]
    rest = " ".join(cards[1:4])
    return f"基于当前市场证据，我更倾向于这样看：{lead} {rest}".strip()


@app.after_request
def add_cors_headers(response: Response) -> Response:
    return with_cors(response)


@app.route("/api/health", methods=["GET"])
def health() -> Response:
    return json_response(
        {
            "ok": True,
            "service": "chat-api",
        },
        status=200,
    )


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

        market_data = load_market_data()
        market_context = build_evidence_cards(question, market_data)
        model = env("KIMI_MODEL", "kimi-k2.5")
        started_at = time.perf_counter()
        try:
            answer = call_kimi(question, market_context)
            source = "kimi"
            error = None
        except Exception:
            answer = fallback_answer(question, market_context)
            source = "fallback"
            error = "Kimi request failed; returned local fallback."
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        return json_response(
            {
                "answer": answer,
                "source": source,
                "model": model,
                "latency_ms": latency_ms,
                "error": error,
            },
            status=200,
        )
    except Exception as exc:
        return json_response(
            {
                "answer": f"市场数据暂不可用：{exc}",
                "source": "error",
                "model": env("KIMI_MODEL", "kimi-k2.5"),
                "latency_ms": 0,
                "error": str(exc),
            },
            status=500,
        )


@app.route("/", defaults={"path": ""}, methods=["GET"])
@app.route("/<path:path>", methods=["GET"])
def serve_site(path: str) -> Response:
    file_path = static_file_for_path(f"/{path}")
    if file_path is None:
        return json_response({"error": "Not found", "path": path}, status=404)
    return with_cors(send_file(file_path))
