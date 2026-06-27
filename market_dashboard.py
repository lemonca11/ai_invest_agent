#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import ssl
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "market_watchlist.json"
DATA_DIR = ROOT / "data"


def load_config() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def yahoo_chart(symbol: str, start: date, end: date) -> list[dict]:
    period1 = int(datetime.combine(start, datetime.min.time(), timezone.utc).timestamp())
    period2 = int(datetime.combine(end + timedelta(days=1), datetime.min.time(), timezone.utc).timestamp())
    params = urlencode(
        {
            "period1": period1,
            "period2": period2,
            "interval": "1d",
            "events": "history",
            "includeAdjustedClose": "true",
        }
    )
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{params}"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urlopen(req, timeout=30, context=ssl._create_unverified_context()) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    error = payload.get("chart", {}).get("error")
    result = payload.get("chart", {}).get("result")
    if error or not result:
        raise RuntimeError(f"{symbol}: {error or 'no result'}")
    chart = result[0]
    timestamps = chart.get("timestamp") or []
    quote = chart["indicators"]["quote"][0]
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    rows = []
    for i, ts in enumerate(timestamps):
        close = closes[i] if i < len(closes) else None
        volume = volumes[i] if i < len(volumes) else None
        if close is None:
            continue
        rows.append(
            {
                "Date": datetime.fromtimestamp(ts, timezone.utc).date().isoformat(),
                "Close": float(close),
                "Volume": int(volume or 0),
            }
        )
    if not rows:
        raise RuntimeError(f"{symbol}: empty chart response")
    return rows


def read_existing_caps() -> dict[str, float]:
    path = DATA_DIR / "market_signals.csv"
    if not path.exists():
        return {}
    caps = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                if row.get("market_cap"):
                    caps[row["name"]] = float(row["market_cap"])
            except ValueError:
                pass
    return caps


def parse_market_cap_value(text: str) -> float:
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([TtBbMm])", text.strip().replace(",", ""))
    if not match:
        raise ValueError(f"unrecognized market cap value: {text}")
    multiplier = {"T": 1e12, "B": 1e9, "M": 1e6}[match.group(2).upper()]
    return float(match.group(1)) * multiplier


def stockanalysis_market_cap(symbol: str) -> float:
    candidates = [
        f"https://stockanalysis.com/stocks/{symbol.lower()}/market-cap/",
        f"https://stockanalysis.com/quote/otc/{symbol.upper()}/market-cap/",
    ]
    last_error = None
    for url in candidates:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"})
        try:
            with urlopen(req, timeout=30, context=ssl._create_unverified_context()) as resp:
                html = resp.read().decode("utf-8", "ignore")
            match = re.search(r"Market Cap\s*<div[^>]*>\s*<!--\[-->\s*([0-9.]+[TBM])", html)
            if match:
                return parse_market_cap_value(match.group(1))
            last_error = "market cap marker not found"
        except Exception as exc:
            last_error = str(exc)
    raise RuntimeError(last_error or "market cap unavailable")


def pct_change(values: list[float]) -> list[float | None]:
    changes: list[float | None] = [None]
    for previous, current in zip(values, values[1:]):
        changes.append(current / previous - 1 if previous else None)
    return changes


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def stdev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    return math.sqrt(sum((value - avg) ** 2 for value in values) / (len(values) - 1))


def rolling_mean(values: list[float], window: int, idx: int) -> float:
    if idx + 1 < window:
        return 0.0
    return mean(values[idx - window + 1 : idx + 1])


def classify(row: dict, thresholds: dict) -> tuple[str, str]:
    if row["above_ma20_pct"] > thresholds["hot_above_ma20_pct"] and row["above_ma50_pct"] > thresholds["extended_above_ma50_pct"]:
        return "强趋势过热", "等待缩量回踩或放量续强，避免追高。"
    if row["above_ma20_pct"] > 0 and row["above_ma50_pct"] > 0 and row["ret_20d_pct"] > 0:
        return "趋势强", "优先观察回踩 20 日线是否缩量企稳。"
    if row["above_ma20_pct"] < thresholds["weak_below_ma20_pct"] and row["above_ma50_pct"] < thresholds["weak_below_ma50_pct"]:
        return "弱势", "先等重新站回 20 日线，再看 50 日线。"
    if row["above_ma20_pct"] < 0 and row["above_ma50_pct"] > 0:
        return "短线整理", "看 50 日线是否守住，以及放量日方向。"
    if row["volume_vs_20d_pct"] > thresholds["volume_surge_pct"] and row["day_return_pct"] < 0:
        return "放量承压", "不急着接，观察后续是否能收回放量阴线。"
    return "中性观察", "等待价格和成交量给出更明确方向。"


def percentile_ranks(rows: list[dict], key: str) -> dict[str, float]:
    ordered = sorted(rows, key=lambda row: row[key])
    count = len(ordered)
    if not count:
        return {}
    ranks = {}
    for idx, row in enumerate(ordered, start=1):
        ranks[row["name"]] = idx / count
    return ranks


def compute_signals(price_rows: dict[str, list[dict]], caps: dict[str, float], config: dict) -> list[dict]:
    thresholds = config["thresholds"]
    rows = []
    for name, records in price_rows.items():
        if len(records) < 61:
            continue
        closes = [row["Close"] for row in records]
        volumes = [row["Volume"] for row in records]
        returns = pct_change(closes)
        idx = len(records) - 1
        valid_returns = [value for value in returns if value is not None]
        ma20 = rolling_mean(closes, 20, idx)
        ma50 = rolling_mean(closes, 50, idx)
        vol20 = rolling_mean([float(v) for v in volumes], 20, idx)
        drawdown = closes[-1] / max(closes) - 1
        accumulation = 0
        distribution = 0
        for i, daily_return in enumerate(returns):
            if i < 20 or daily_return is None:
                continue
            base_volume = mean([float(v) for v in volumes[i - 20 : i]])
            if daily_return > 0.01 and volumes[i] > 1.5 * base_volume:
                accumulation += 1
            if daily_return < -0.01 and volumes[i] > 1.5 * base_volume:
                distribution += 1
        high_threshold = sorted(volumes[1:])[max(0, int(len(volumes[1:]) * 0.9) - 1)]
        high_returns = [returns[i] for i in range(1, len(returns)) if returns[i] is not None and volumes[i] >= high_threshold]
        row = {
            "name": name,
            "symbol": config["tickers"].get(name, ""),
            "market_cap": caps.get(name, 0.0),
            "last_date": records[-1]["Date"],
            "last_close": closes[-1],
            "day_return_pct": (returns[-1] or 0.0) * 100,
            "ret_20d_pct": (closes[-1] / closes[-21] - 1) * 100,
            "ret_60d_pct": (closes[-1] / closes[-61] - 1) * 100,
            "above_ma20_pct": (closes[-1] / ma20 - 1) * 100 if ma20 else 0.0,
            "above_ma50_pct": (closes[-1] / ma50 - 1) * 100 if ma50 else 0.0,
            "volume": volumes[-1],
            "volume_vs_20d_pct": (volumes[-1] / vol20 - 1) * 100 if vol20 else 0.0,
            "dollar_volume": closes[-1] * volumes[-1],
            "current_drawdown_pct": drawdown * 100,
            "last20_volatility_pct": stdev([value for value in returns[-20:] if value is not None]) * 100,
            "accumulation_days": accumulation,
            "distribution_days": distribution,
            "high_volume_avg_return_pct": mean(high_returns) * 100 if high_returns else 0.0,
        }
        row["state"], row["playbook"] = classify(row, thresholds)
        rows.append(row)

    rank_inputs = {
        "ret_20d_pct": percentile_ranks(rows, "ret_20d_pct"),
        "ret_60d_pct": percentile_ranks(rows, "ret_60d_pct"),
        "above_ma20_pct": percentile_ranks(rows, "above_ma20_pct"),
        "above_ma50_pct": percentile_ranks(rows, "above_ma50_pct"),
        "volume_vs_20d_pct": percentile_ranks(rows, "volume_vs_20d_pct"),
    }
    acc_rank_rows = [{**row, "acc_minus_dist": row["accumulation_days"] - row["distribution_days"]} for row in rows]
    acc_ranks = percentile_ranks(acc_rank_rows, "acc_minus_dist")
    for row in rows:
        row["score"] = (
            rank_inputs["ret_20d_pct"][row["name"]] * 25
            + rank_inputs["ret_60d_pct"][row["name"]] * 25
            + rank_inputs["above_ma20_pct"][row["name"]] * 15
            + rank_inputs["above_ma50_pct"][row["name"]] * 15
            + rank_inputs["volume_vs_20d_pct"][row["name"]] * 10
            + acc_ranks[row["name"]] * 10
        )
    return sorted(rows, key=lambda row: row["score"], reverse=True)


def write_wide_csv(path: Path, price_rows: dict[str, list[dict]], field: str) -> None:
    dates = sorted({row["Date"] for records in price_rows.values() for row in records})
    names = list(price_rows.keys())
    lookup = {name: {row["Date"]: row[field] for row in records} for name, records in price_rows.items()}
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Date", *names])
        for day in dates:
            writer.writerow([day, *[lookup[name].get(day, "") for name in names]])


def write_signals(path: Path, rows: list[dict]) -> None:
    fields = [
        "name",
        "symbol",
        "market_cap",
        "last_date",
        "last_close",
        "day_return_pct",
        "ret_20d_pct",
        "ret_60d_pct",
        "above_ma20_pct",
        "above_ma50_pct",
        "volume",
        "volume_vs_20d_pct",
        "dollar_volume",
        "current_drawdown_pct",
        "last20_volatility_pct",
        "accumulation_days",
        "distribution_days",
        "high_volume_avg_return_pct",
        "state",
        "playbook",
        "score",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh Market Radar CSV files.")
    parser.add_argument("--lookback-days", type=int, default=220)
    parser.add_argument("--refresh-caps", action="store_true")
    args = parser.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    config = load_config()
    end = date.today()
    start = end - timedelta(days=args.lookback_days)
    price_rows = {}
    errors = []
    for name, symbol in config["tickers"].items():
        try:
            price_rows[name] = yahoo_chart(symbol, start, end)
        except Exception as exc:
            errors.append({"name": name, "symbol": symbol, "error": str(exc)})
        time.sleep(0.05)

    caps = {} if args.refresh_caps else read_existing_caps()
    for name, symbol in config["tickers"].items():
        if name in caps and caps[name]:
            continue
        try:
            caps[name] = stockanalysis_market_cap(symbol)
        except Exception as exc:
            errors.append({"name": name, "symbol": symbol, "error": f"market_cap: {exc}"})
        time.sleep(0.05)

    signals = compute_signals(price_rows, caps, config)
    write_wide_csv(DATA_DIR / "market_close.csv", price_rows, "Close")
    write_wide_csv(DATA_DIR / "market_volume.csv", price_rows, "Volume")
    write_signals(DATA_DIR / "market_signals.csv", signals)
    with (DATA_DIR / "market_fetch_errors.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "symbol", "error"])
        writer.writeheader()
        writer.writerows(errors)

    print(f"market symbols requested={len(config['tickers'])}, loaded={len(price_rows)}, errors={len(errors)}")
    if len(price_rows) < max(1, len(config["tickers"]) - 5):
        raise SystemExit("Too many market symbols failed to load.")


if __name__ == "__main__":
    main()
