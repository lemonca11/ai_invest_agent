import yaml
from pathlib import Path

path = Path.home() / "ai_invest_agent" / "config" / "sources.yaml"

with open(path, "r", encoding="utf-8") as f:
    data = yaml.safe_load(f) or {}

sources = data.get("sources", [])

def infer_type(item):
    url = (item.get("url") or "").lower()
    name = (item.get("company") or "").lower()
    text = f"{name} {url}"

    if "rss" in text or "feed" in text:
        return "rss"
    if "changelog" in text or "change-log" in text:
        return "changelog"
    if "release-notes" in text or "release notes" in text:
        return "changelog"
    if "investor" in text or "investors" in text or "ir." in text or "/ir/" in text:
        return "ir"
    if "blog" in text:
        return "blog"
    if "news" in text or "press" in text:
        return "newsroom"

    return item.get("type", "web")

def infer_cadence(item):
    url = (item.get("url") or "").lower()
    name = (item.get("company") or "").lower()
    source_type = infer_type(item)
    text = f"{name} {url}"

    if source_type in ["rss", "changelog"]:
        return "daily"
    if "pricing" in text or "deprecation" in text:
        return "weekly"
    if source_type == "ir":
        return "weekly"
    if any(k in text for k in ["reddit", "producthunt", "app store", "google play", "similarweb", "sensortower", "data.ai", "apptopia"]):
        return "manual"
    if source_type in ["blog", "newsroom"]:
        return "daily"

    return "manual"

def infer_purpose(item):
    url = (item.get("url") or "").lower()
    name = (item.get("company") or "").lower()
    layer = item.get("layer", "")
    source_type = infer_type(item)
    text = f"{name} {url}"

    if "pricing" in text:
        return "pricing_change"
    if "deprecation" in text:
        return "api_deprecation"
    if "changelog" in text or "api" in text:
        return "api_change"
    if "models" in text or layer == "models":
        return "model_update"
    if source_type == "ir":
        return "capital_market"
    if layer == "energy":
        return "energy_signal"
    if layer == "chips":
        return "chip_update"
    if layer == "infrastructure":
        return "cloud_infra_update"
    if layer == "applications":
        return "application_signal"
    if layer == "capital":
        return "capital_market"

    return "background"

changed = 0

for item in sources:
    new_type = infer_type(item)

    if item.get("type") != new_type:
        item["type"] = new_type
        changed += 1

    if "cadence" not in item:
        item["cadence"] = infer_cadence(item)
        changed += 1

    if "purpose" not in item:
        item["purpose"] = infer_purpose(item)
        changed += 1

with open(path, "w", encoding="utf-8") as f:
    yaml.safe_dump({"sources": sources}, f, allow_unicode=True, sort_keys=False)

print(f"已升级 sources.yaml，修改字段数量：{changed}")
print(f"来源总数：{len(sources)}")