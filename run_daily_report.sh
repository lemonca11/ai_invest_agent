#!/bin/bash
set -e
set -o pipefail

cd ~/ai_invest_agent || exit 1

TODAY=$(date +%F)
LOG_FILE="logs/daily_report_${TODAY}.log"
REPORT_FILE="reports/${TODAY}.md"
BACKUP_FILE="reports/${TODAY}.md.bak"
RAW_FILE="data/raw_items_${TODAY}.json"

mkdir -p logs
: > "$LOG_FILE"

source venv/bin/activate

echo "开始抓取信息源..."
python3 main.py 2>&1 | tee -a "$LOG_FILE"

echo "检查抓取质量..."
python3 - "$RAW_FILE" <<'PY' 2>&1 | tee -a "$LOG_FILE"
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(f"失败：未生成抓取文件 {path}")

payload = json.loads(path.read_text(encoding="utf-8"))
items = payload.get("items", [])
failed = sum(1 for item in items if item.get("event_grade") == "failed_source")
successful = len(items) - failed

print(f"抓取质量：total={len(items)}, successful={successful}, failed={failed}")
if not items:
    raise SystemExit("失败：抓取结果为空，停止生成日报和站点")
if successful == 0:
    raise SystemExit("失败：全部来源抓取失败，停止生成日报和站点")
PY

echo "开始生成本地日报..."

if [ -f "$REPORT_FILE" ]; then
  cp "$REPORT_FILE" "$BACKUP_FILE"
fi
rm -f "$REPORT_FILE"

python3 generate_local_report.py --date "$TODAY" 2>&1 | tee -a "$LOG_FILE"

if [ ! -f "$REPORT_FILE" ]; then
  if [ -f "$BACKUP_FILE" ]; then
    cp "$BACKUP_FILE" "$REPORT_FILE"
  fi
  echo "失败：未生成 ${REPORT_FILE}，请查看日志：~/ai_invest_agent/${LOG_FILE}" | tee -a "$LOG_FILE"
  exit 1
fi

echo "开始生成监控系统迭代建议..."
python3 market_source_iterate.py --date "$TODAY" 2>&1 | tee -a "$LOG_FILE"

echo "开始构建公开站点..."
python3 build_site.py 2>&1 | tee -a "$LOG_FILE"

rm -f "$BACKUP_FILE"

echo "完成。日报位置：~/ai_invest_agent/reports/${TODAY}.md"
echo "迭代建议：~/ai_invest_agent/reports/source_iteration_${TODAY}.md"
echo "站点目录：~/ai_invest_agent/site"
echo "运行日志：~/ai_invest_agent/${LOG_FILE}"
