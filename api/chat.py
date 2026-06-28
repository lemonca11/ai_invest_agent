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


def make_semantic_sentence(row: dict) -> str:
    name = row.get("name", "Unknown")
    symbol = row.get("symbol", "")
    label = f"{name}({symbol})" if symbol else name
    state = str(row.get("state") or "unknown")
    ret_20d = float(row.get("ret_20d_pct") or 0)
    vol_20d = float(row.get("volume_vs_20d_pct") or 0)
    above_ma20 = float(row.get("above_ma20_pct") or 0)
    above_ma50 = float(row.get("above_ma50_pct") or 0)
    drawdown = float(row.get("current_drawdown_pct") or 0)

    if state in {"weak", "弱势"}:
        stance = "近期偏弱，买盘还没有重新接回。"
    elif state in {"strong", "强势"}:
        stance = "走势相对稳，资金接力还算顺。"
    elif state in {"distribution", "放量承压", "short-term pressure"}:
        stance = "短线承压，放量后没有顺畅延续。"
    elif state in {"accumulation", "吸筹"}:
        stance = "底部资金在吸收，但还没完全走成趋势。"
    else:
        stance = f"当前状态是 {state}。"

    clues: list[str] = []
    if ret_20d <= -5:
        clues.append("20日表现偏弱")
    elif ret_20d >= 5:
        clues.append("20日表现偏强")
    if abs(above_ma20) > 1:
        clues.append("价格相对 20 日线有偏离")
    if abs(above_ma50) > 1:
        clues.append("与 50 日线也有偏离")
    if abs(vol_20d) > 15:
        clues.append("量能没有完全匹配价格变化")
    if drawdown <= -8:
        clues.append("回撤仍然比较深")

    clue_text = "；".join(clues[:3])
    if clue_text:
        clue_text = f" 线索上看，{clue_text}。"

    return f"{label} {stance}{clue_text}"


def group_regime(rows: list[dict]) -> str:
    if not rows:
        return "暂无足够数据判断分类状态。"
    weak = sum(1 for row in rows if str(row.get("state")) in {"weak", "弱势", "distribution", "放量承压", "short-term pressure"})
    strong = sum(1 for row in rows if str(row.get("state")) in {"strong", "强势", "accumulation", "吸筹"})
    avg_ret = sum(float(row.get("ret_20d_pct") or 0) for row in rows) / len(rows)
    if strong > weak and avg_ret > 0:
        return "整体偏强，说明资金仍在沿着这条线继续做延伸。"
    if weak > strong and avg_ret < 0:
        return "整体偏弱，说明这条线目前还没有明显修复。"
    return "整体处在分化阶段，方向还不算一致。"


def topic_label(question: str, context: dict) -> str:
    if context.get("selected_group"):
        return f"{context['selected_group']}这条线"
    if context.get("selected_stock"):
        row = context["selected_stock"]
        return f"{row.get('name')}({row.get('symbol')})"
    return "当前这组市场样本"


def build_evidence_cards(question: str, market_data: dict) -> dict:
    groups = market_data.get("groups", {})
    summaries = market_data.get("summaries", [])
    correlations = market_data.get("correlations", {})
    signals = market_data.get("signals", [])
    context = compact_market_context(question, market_data)
    facts: list[str] = []
    watchpoints: list[str] = []
    summary_by_group = {item.get("group"): item for item in summaries}
    selected_group = context.get("selected_group")
    selected_stock = context.get("selected_stock")

    facts.append(
        f"市场时间点是 {market_data.get('latest_date', 'unknown')}，当前覆盖 {len(groups)} 个分类、{len(signals)} 只标的。"
    )

    if selected_group:
        summary = summary_by_group.get(selected_group, {})
        if summary:
            facts.append(
                f"{selected_group} 这条线的总市值约 {summary.get('market_cap_label', 'N/A')}，"
                f"20日成交额约 {summary.get('avg_dollar_volume_20d_label', 'N/A')}，"
                f"领涨标的是 {summary.get('leader', 'N/A')}。"
            )
        group_rows = sorted(context.get("group_signals", []), key=lambda row: float(row.get("score") or 0), reverse=True)[:4]
        facts.append(group_regime(group_rows))
        if group_rows:
            best = group_rows[0]
            worst = group_rows[-1]
            facts.append(
                f"这条线里，最强的是 {best.get('name')}，最弱的是 {worst.get('name')}，"
                f"说明内部强弱已经开始分开。"
            )
        hint = correlations.get(selected_group, {})
        for pair in hint.get("top_pairs", [])[:2]:
            facts.append(
                f"{selected_group} 内部里，{pair.get('a')} 和 {pair.get('b')} 的联动度约为 {float(pair.get('corr') or 0):.2f}。"
            )
        watchpoints.extend([
            f"看 {selected_group} 是否能继续维持内部扩散，而不是只靠单一龙头。",
            f"看 {selected_group} 里的领涨标的能不能把其它成员一起带起来。",
        ])
    elif selected_stock:
        row = selected_stock
        facts.append(make_semantic_sentence(row))
        for group in context.get("stock_groups", [])[:2]:
            summary = summary_by_group.get(group, {})
            if summary:
                facts.append(
                    f"{row.get('name')} 所在的 {group} 这条线，当前总市值约 {summary.get('market_cap_label', 'N/A')}，"
                    f"领涨的是 {summary.get('leader', 'N/A')}。"
                )
            related = context.get("related_group_data", {}).get(group, {})
            pair_text = related.get("correlation", {}).get("top_pairs", [])
            if pair_text:
                pair = pair_text[0]
                facts.append(
                    f"{group} 里，{pair.get('a')} 和 {pair.get('b')} 的联动度约为 {float(pair.get('corr') or 0):.2f}。"
                )
        watchpoints.extend([
            f"重点看 {row.get('name')} 能不能重新站稳关键均线，而不是只做弱反弹。",
            f"重点看它所在分类里，是否有别的标的一起跟上。",
        ])
    else:
        leaders = sorted(signals, key=lambda row: float(row.get("score") or 0), reverse=True)[:5]
        market_strength = group_regime(leaders)
        facts.append(market_strength)
        if leaders:
            top = leaders[0]
            facts.append(
                f"当前样本里最强的是 {top.get('name')}，但这不一定代表整条链都同步转强。"
            )
        for item in summaries[:3]:
            facts.append(
                f"{item.get('group')} 这条线的总市值约 {item.get('market_cap_label', 'N/A')}，"
                f"当前领涨标的是 {item.get('leader', 'N/A')}。"
            )
        watchpoints.extend([
            "看资金是不是从单点龙头扩散到同一条产业链的其他标的。",
            "看高分标的之间能否形成同向共振，而不是各走各的。",
        ])

    return {
        "topic": topic_label(question, context),
        "latest_date": market_data.get("latest_date"),
        "facts": facts[:6],
        "watchpoints": watchpoints[:3],
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
                        "你只会看到问题和一份语义事实包。"
                        "你的任务不是复述事实包，而是把它们融成自然、连贯、像人说的话的分析。"
                        "不要输出列表式摘要，不要重复事实包里的句式，不要提检索过程。"
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
                        f"主题：{market_context.get('topic', '当前市场样本')}\n"
                        f"时间点：{market_context.get('latest_date', 'unknown')}\n\n"
                        "语义事实包：\n- "
                        + "\n- ".join(market_context.get("facts", []))
                        + ("\n\n观察点：\n- " + "\n- ".join(market_context.get("watchpoints", [])) if market_context.get("watchpoints") else "")
                        + "\n\n请只基于以上材料写出自然、连贯的分析，不要复述字段，不要逐条展开。"
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
    facts = market_context.get("facts", [])
    if not facts:
        return "当前没有足够的市场证据来回答这个问题。"
    lead = facts[0]
    rest = " ".join(facts[1:3])
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
