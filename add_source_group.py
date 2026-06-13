import yaml
from pathlib import Path

path = Path.home() / "ai_invest_agent" / "config" / "sources.yaml"

with open(path, "r", encoding="utf-8") as f:
    data = yaml.safe_load(f) or {}

sources = data.get("sources", [])

def infer_source_group(item):
    layer = item.get("layer", "")
    source_type = item.get("type", "")
    cadence = item.get("cadence", "")
    purpose = item.get("purpose", "")
    company = (item.get("company") or "").lower()
    url = (item.get("url") or "").lower()

    text = f"{company} {url} {purpose}"

    if layer == "capital" or source_type == "ir" or "investor" in text or "revenue" in text:
        return "capital_event"

    if any(k in text for k in [
        "github",
        "huggingface",
        "lmarena",
        "artificialanalysis",
        "producthunt",
        "trending",
        "benchmark",
        "spaces"
    ]):
        return "discovery"

    if cadence == "manual" or purpose in ["reference", "background"]:
        return "background"

    return "core_watchlist"

changed = 0

for item in sources:
    if "source_group" not in item:
        item["source_group"] = infer_source_group(item)
        changed += 1

with open(path, "w", encoding="utf-8") as f:
    yaml.safe_dump({"sources": sources}, f, allow_unicode=True, sort_keys=False)

print(f"已补充 source_group 字段，修改数量：{changed}")
print(f"来源总数：{len(sources)}")
