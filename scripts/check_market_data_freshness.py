#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MARKET_DATA_PATH = ROOT / "site" / "market" / "market_data.json"
MAX_AGE_DAYS = int(os.environ.get("MARKET_MAX_AGE_DAYS", "4"))


def main() -> None:
    payload = json.loads(MARKET_DATA_PATH.read_text(encoding="utf-8"))
    latest_date = payload.get("latest_date")
    if not latest_date:
        raise SystemExit("market_data.json does not contain latest_date")

    latest = date.fromisoformat(latest_date)
    age_days = (date.today() - latest).days
    print(f"Market Radar latest_date={latest.isoformat()} age_days={age_days}")

    if age_days > MAX_AGE_DAYS:
        raise SystemExit(
            f"Market Radar data is stale: latest_date={latest.isoformat()} age_days={age_days} max_age_days={MAX_AGE_DAYS}"
        )


if __name__ == "__main__":
    main()
