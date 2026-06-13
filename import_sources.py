import os
import csv
import yaml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CSV_PATH = os.path.join(BASE_DIR, "config", "sources_import.csv")
YAML_PATH = os.path.join(BASE_DIR, "config", "sources.yaml")

VALID_LAYERS = {
    "energy",
    "chips",
    "infrastructure",
    "models",
    "applications",
    "capital",
}

VALID_TYPES = {
    "web",
    "rss",
    "changelog",
    "release_notes",
    "newsroom",
    "blog",
    "ir",
    "benchmark",
    "discovery",
    "github_release",
    "rss_index",
    "rss_page",
    "aggregator",
}

VALID_PRIORITIES = {
    "high",
    "medium",
    "low",
}

VALID_CADENCES = {
    "daily",
    "weekly",
    "monthly",
    "manual",
}

VALID_SOURCE_GROUPS = {
    "core_watchlist",
    "discovery",
    "capital_event",
    "background",
}


def load_existing_sources():
    if not os.path.exists(YAML_PATH):
        return []

    with open(YAML_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return data.get("sources", [])


def normalize_row(row):
    return {
        "company": (row.get("company") or "").strip(),
        "layer": (row.get("layer") or "").strip(),
        "type": (row.get("type") or "").strip(),
        "url": (row.get("url") or "").strip(),
        "priority": (row.get("priority") or "").strip(),
        "cadence": (row.get("cadence") or "").strip(),
        "purpose": (row.get("purpose") or "").strip(),
        "source_group": (row.get("source_group") or "").strip(),
    }


def validate_source(source):
    if not source["company"]:
        return False, "company 为空"

    if not source["url"]:
        return False, "url 为空"

    if source["layer"] not in VALID_LAYERS:
        return False, f"layer 不合法：{source['layer']}"

    if source["type"] not in VALID_TYPES:
        return False, f"type 不合法：{source['type']}"

    if source["priority"] not in VALID_PRIORITIES:
        return False, f"priority 不合法：{source['priority']}"

    if source["cadence"] not in VALID_CADENCES:
        return False, f"cadence 不合法：{source['cadence']}"

    if not source["purpose"]:
        return False, "purpose 为空"

    if source["source_group"] not in VALID_SOURCE_GROUPS:
        return False, f"source_group 不合法：{source['source_group']}"

    if not source["url"].startswith(("http://", "https://")):
        return False, "url 必须以 http:// 或 https:// 开头"

    return True, ""


def load_import_sources():
    if not os.path.exists(CSV_PATH):
        raise FileNotFoundError(f"找不到导入文件：{CSV_PATH}")

    sources = []

    with open(CSV_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        required_fields = {
            "company",
            "layer",
            "type",
            "url",
            "priority",
            "cadence",
            "purpose",
            "source_group",
        }

        fieldnames = set(reader.fieldnames or [])

        if not required_fields.issubset(fieldnames):
            raise ValueError(
                "CSV 表头必须是：company,layer,type,url,priority,cadence,purpose,source_group"
            )

        for row in reader:
            source = normalize_row(row)
            ok, reason = validate_source(source)

            if not ok:
                print(f"跳过：{reason}：{source}")
                continue

            sources.append(source)

    return sources


def save_sources(sources):
    with open(YAML_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            {"sources": sources},
            f,
            allow_unicode=True,
            sort_keys=False,
        )


def main():
    existing_sources = load_existing_sources()
    import_sources = load_import_sources()

    existing_urls = {item.get("url") for item in existing_sources}

    added = []
    skipped = []

    for source in import_sources:
        url = source.get("url")

        if url in existing_urls:
            skipped.append(source)
            continue

        existing_sources.append(source)
        existing_urls.add(url)
        added.append(source)

    save_sources(existing_sources)

    print("导入完成")
    print(f"新增来源数量：{len(added)}")
    print(f"跳过重复数量：{len(skipped)}")
    print(f"最终来源总数：{len(existing_sources)}")
    print(f"配置文件位置：{YAML_PATH}")

    if added:
        print("\n本次新增：")
        for item in added:
            print(
                f"- {item['company']} | {item['layer']} | {item['type']} | "
                f"{item['cadence']} | {item['source_group']} | {item['url']}"
            )


if __name__ == "__main__":
    main()