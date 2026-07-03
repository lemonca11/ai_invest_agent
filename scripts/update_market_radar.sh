#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"

python3 market_dashboard.py "$@"
python3 build_site.py

python3 - <<'PY'
import json
from pathlib import Path

payload = json.loads(Path("site/market/market_data.json").read_text(encoding="utf-8"))
print(f"Market Radar latest_date={payload.get('latest_date', '')}")
print(f"Market Radar signals={len(payload.get('signals', []))}")
PY
