#!/bin/bash
set -e
set -o pipefail

cd ~/ai_invest_agent || exit 1

TODAY=$(date +%F)
LOG_FILE="logs/daily_report_${TODAY}.log"
REPORT_FILE="reports/${TODAY}.md"
BACKUP_FILE="reports/${TODAY}.md.bak"

mkdir -p logs
: > "$LOG_FILE"

source venv/bin/activate

echo "开始抓取信息源..."
python3 main.py 2>&1 | tee -a "$LOG_FILE"

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

rm -f "$BACKUP_FILE"

echo "完成。日报位置：~/ai_invest_agent/reports/${TODAY}.md"
echo "迭代建议：~/ai_invest_agent/reports/source_iteration_${TODAY}.md"
echo "运行日志：~/ai_invest_agent/${LOG_FILE}"
