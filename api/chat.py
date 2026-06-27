from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler

import requests
from openai import OpenAI


DEFAULT_MARKET_DATA_URL = "https://lemonca11.github.io/ai_invest_agent/market/market_data.json"
DEFAULT_ALLOWED_ORIGIN = "https://lemonca11.github.io"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    origin = env("ALLOWED_ORIGIN", DEFAULT_ALLOWED_ORIGIN)
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Access-Control-Allow-Origin", origin)
    handler.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


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


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self) -> None:
        json_response(self, 200, {"ok": True})

    def do_GET(self) -> None:
        json_response(
            self,
            405,
            {
                "error": "Method not allowed",
                "message": "Use POST with a JSON body: {\"question\": \"...\"}",
            },
        )

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            question = str(payload.get("question", "")).strip()
            if not question:
                json_response(self, 400, {"answer": "问题不能为空。"})
                return

            market_data_url = env("MARKET_DATA_URL", DEFAULT_MARKET_DATA_URL)
            market_data = requests.get(market_data_url, timeout=20).json()
            market_context = compact_market_context(question, market_data)
            answer = call_kimi(question, market_context)
            json_response(self, 200, {"answer": answer})
        except Exception as exc:
            json_response(self, 500, {"answer": f"Kimi 后端暂不可用：{exc}"})
