import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import yaml


BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"

SOURCES_PATH = CONFIG_DIR / "sources.yaml"
CANDIDATES_PATH = CONFIG_DIR / "source_candidates.yaml"
HEALTH_PATH = CONFIG_DIR / "source_health.yaml"

CORE_LAYERS = ["energy", "chips", "infrastructure", "models", "applications", "capital"]


STRATEGIC_CANDIDATES = [
    {
        "company": "Meta AI Blog",
        "layer": "models",
        "type": "blog",
        "url": "https://ai.meta.com/blog/",
        "priority": "high",
        "cadence": "daily",
        "purpose": "model_product_update",
        "source_group": "core_watchlist",
        "reason": "Meta is a major open-model and AI infrastructure player; official blog is an authoritative source.",
        "authority_score": 5,
        "freshness_score": 4,
        "signal_score": 5,
        "noise_score": 1,
        "auto_promote_safe": True,
    },
    {
        "company": "xAI News",
        "layer": "models",
        "type": "newsroom",
        "url": "https://x.ai/news",
        "priority": "high",
        "cadence": "daily",
        "purpose": "model_product_update",
        "source_group": "core_watchlist",
        "reason": "xAI is a frontier-model company; official news should be watched for model and product launches.",
        "authority_score": 5,
        "freshness_score": 4,
        "signal_score": 5,
        "noise_score": 1,
        "auto_promote_safe": True,
    },
    {
        "company": "Mistral AI News",
        "layer": "models",
        "type": "newsroom",
        "url": "https://mistral.ai/news/",
        "priority": "high",
        "cadence": "daily",
        "purpose": "model_product_update",
        "source_group": "core_watchlist",
        "reason": "Mistral is a key European model company; official news captures model, product, and enterprise updates.",
        "authority_score": 5,
        "freshness_score": 4,
        "signal_score": 5,
        "noise_score": 1,
        "auto_promote_safe": True,
    },
    {
        "company": "Cohere Blog",
        "layer": "models",
        "type": "blog",
        "url": "https://cohere.com/blog",
        "priority": "medium",
        "cadence": "daily",
        "purpose": "model_product_update",
        "source_group": "core_watchlist",
        "reason": "Cohere is enterprise-model focused; official blog can signal enterprise AI adoption and model releases.",
        "authority_score": 5,
        "freshness_score": 3,
        "signal_score": 4,
        "noise_score": 1,
        "auto_promote_safe": True,
    },
    {
        "company": "Perplexity Blog",
        "layer": "applications",
        "type": "blog",
        "url": "https://www.perplexity.ai/hub/blog",
        "priority": "medium",
        "cadence": "daily",
        "purpose": "application_signal",
        "source_group": "core_watchlist",
        "reason": "Perplexity is a consumer and enterprise AI search application; product and partnership updates are investment-relevant.",
        "authority_score": 5,
        "freshness_score": 4,
        "signal_score": 4,
        "noise_score": 1,
        "auto_promote_safe": True,
    },
    {
        "company": "CoreWeave Blog",
        "layer": "infrastructure",
        "type": "blog",
        "url": "https://www.coreweave.com/blog",
        "priority": "high",
        "cadence": "daily",
        "purpose": "cloud_infra_update",
        "source_group": "core_watchlist",
        "reason": "CoreWeave is a major AI cloud provider; official updates can reveal capacity, product, and customer signals.",
        "authority_score": 5,
        "freshness_score": 4,
        "signal_score": 5,
        "noise_score": 1,
        "auto_promote_safe": True,
    },
    {
        "company": "Oracle Cloud Infrastructure Blog",
        "layer": "infrastructure",
        "type": "blog",
        "url": "https://blogs.oracle.com/cloud-infrastructure/",
        "priority": "medium",
        "cadence": "daily",
        "purpose": "cloud_infra_update",
        "source_group": "core_watchlist",
        "reason": "Oracle Cloud is increasingly relevant to AI infrastructure and model training capacity.",
        "authority_score": 5,
        "freshness_score": 4,
        "signal_score": 4,
        "noise_score": 2,
        "auto_promote_safe": True,
    },
    {
        "company": "Cloudflare AI Blog",
        "layer": "infrastructure",
        "type": "blog",
        "url": "https://blog.cloudflare.com/tag/ai/",
        "priority": "medium",
        "cadence": "daily",
        "purpose": "cloud_infra_update",
        "source_group": "core_watchlist",
        "reason": "Cloudflare AI and Workers AI can signal edge inference, developer infrastructure, and inference pricing shifts.",
        "authority_score": 5,
        "freshness_score": 4,
        "signal_score": 4,
        "noise_score": 2,
        "auto_promote_safe": True,
    },
    {
        "company": "Broadcom News",
        "layer": "chips",
        "type": "newsroom",
        "url": "https://www.broadcom.com/company/news",
        "priority": "high",
        "cadence": "daily",
        "purpose": "chip_update",
        "source_group": "core_watchlist",
        "reason": "Broadcom is important for AI networking and custom silicon; official news can signal AI infrastructure demand.",
        "authority_score": 5,
        "freshness_score": 3,
        "signal_score": 5,
        "noise_score": 1,
        "auto_promote_safe": True,
    },
    {
        "company": "Marvell Newsroom",
        "layer": "chips",
        "type": "newsroom",
        "url": "https://www.marvell.com/company/newsroom.html",
        "priority": "high",
        "cadence": "daily",
        "purpose": "chip_update",
        "source_group": "core_watchlist",
        "reason": "Marvell is relevant for custom silicon, networking, and data-center AI infrastructure.",
        "authority_score": 5,
        "freshness_score": 3,
        "signal_score": 4,
        "noise_score": 1,
        "auto_promote_safe": True,
    },
    {
        "company": "SK Hynix Newsroom",
        "layer": "chips",
        "type": "newsroom",
        "url": "https://news.skhynix.com/",
        "priority": "high",
        "cadence": "daily",
        "purpose": "chip_update",
        "source_group": "core_watchlist",
        "reason": "SK Hynix is a key HBM supplier; HBM supply and roadmap are central to AI compute capacity.",
        "authority_score": 5,
        "freshness_score": 4,
        "signal_score": 5,
        "noise_score": 1,
        "auto_promote_safe": True,
    },
    {
        "company": "Samsung Semiconductor Newsroom",
        "layer": "chips",
        "type": "newsroom",
        "url": "https://semiconductor.samsung.com/news-events/news/",
        "priority": "high",
        "cadence": "daily",
        "purpose": "chip_update",
        "source_group": "core_watchlist",
        "reason": "Samsung memory and foundry developments affect HBM, advanced memory, and AI semiconductor supply.",
        "authority_score": 5,
        "freshness_score": 4,
        "signal_score": 5,
        "noise_score": 1,
        "auto_promote_safe": True,
    },
    {
        "company": "Arm Newsroom",
        "layer": "chips",
        "type": "newsroom",
        "url": "https://newsroom.arm.com/",
        "priority": "medium",
        "cadence": "daily",
        "purpose": "chip_update",
        "source_group": "core_watchlist",
        "reason": "Arm is relevant to CPUs, edge AI, data-center architecture, and licensing economics.",
        "authority_score": 5,
        "freshness_score": 4,
        "signal_score": 4,
        "noise_score": 2,
        "auto_promote_safe": True,
    },
    {
        "company": "ServiceNow Newsroom",
        "layer": "applications",
        "type": "newsroom",
        "url": "https://www.servicenow.com/company/media/press-room.html",
        "priority": "medium",
        "cadence": "daily",
        "purpose": "application_signal",
        "source_group": "core_watchlist",
        "reason": "ServiceNow is a major enterprise workflow AI application platform; official updates can signal enterprise adoption.",
        "authority_score": 5,
        "freshness_score": 4,
        "signal_score": 4,
        "noise_score": 2,
        "auto_promote_safe": True,
    },
    {
        "company": "Salesforce Newsroom",
        "layer": "applications",
        "type": "newsroom",
        "url": "https://www.salesforce.com/news/",
        "priority": "medium",
        "cadence": "daily",
        "purpose": "application_signal",
        "source_group": "core_watchlist",
        "reason": "Salesforce Agentforce and enterprise AI adoption are important application-layer signals.",
        "authority_score": 5,
        "freshness_score": 4,
        "signal_score": 4,
        "noise_score": 2,
        "auto_promote_safe": True,
    },
    {
        "company": "Adobe Newsroom",
        "layer": "applications",
        "type": "newsroom",
        "url": "https://news.adobe.com/",
        "priority": "medium",
        "cadence": "daily",
        "purpose": "application_signal",
        "source_group": "core_watchlist",
        "reason": "Adobe Firefly and creative AI adoption are important application-layer monetization signals.",
        "authority_score": 5,
        "freshness_score": 4,
        "signal_score": 4,
        "noise_score": 2,
        "auto_promote_safe": True,
    },
    {
        "company": "Palantir Newsroom",
        "layer": "applications",
        "type": "newsroom",
        "url": "https://www.palantir.com/newsroom/",
        "priority": "medium",
        "cadence": "daily",
        "purpose": "application_signal",
        "source_group": "core_watchlist",
        "reason": "Palantir AIP adoption and enterprise/government deals are relevant to AI application monetization.",
        "authority_score": 5,
        "freshness_score": 4,
        "signal_score": 4,
        "noise_score": 2,
        "auto_promote_safe": True,
    },
    {
        "company": "Cursor Changelog",
        "layer": "applications",
        "type": "changelog",
        "url": "https://cursor.com/changelog",
        "priority": "medium",
        "cadence": "daily",
        "purpose": "coding_agent_update",
        "source_group": "core_watchlist",
        "reason": "Cursor is a key AI coding application; changelog can reveal product velocity and competitive pressure.",
        "authority_score": 5,
        "freshness_score": 4,
        "signal_score": 4,
        "noise_score": 1,
        "auto_promote_safe": True,
    },
    {
        "company": "Schneider Electric Newsroom",
        "layer": "energy",
        "type": "newsroom",
        "url": "https://www.se.com/ww/en/about-us/newsroom/",
        "priority": "medium",
        "cadence": "daily",
        "purpose": "energy_signal",
        "source_group": "core_watchlist",
        "reason": "Schneider Electric is important in data-center power and cooling infrastructure.",
        "authority_score": 5,
        "freshness_score": 4,
        "signal_score": 4,
        "noise_score": 2,
        "auto_promote_safe": True,
    },
    {
        "company": "Constellation Newsroom",
        "layer": "energy",
        "type": "newsroom",
        "url": "https://www.constellationenergy.com/newsroom.html",
        "priority": "medium",
        "cadence": "daily",
        "purpose": "energy_signal",
        "source_group": "core_watchlist",
        "reason": "Constellation is relevant to AI data-center power supply and nuclear power contracts.",
        "authority_score": 5,
        "freshness_score": 3,
        "signal_score": 4,
        "noise_score": 2,
        "auto_promote_safe": True,
    },
    {
        "company": "Vistra Newsroom",
        "layer": "energy",
        "type": "newsroom",
        "url": "https://vistracorp.com/newsroom/",
        "priority": "medium",
        "cadence": "daily",
        "purpose": "energy_signal",
        "source_group": "core_watchlist",
        "reason": "Vistra is relevant to power availability for data-center growth and AI electricity demand.",
        "authority_score": 5,
        "freshness_score": 3,
        "signal_score": 4,
        "noise_score": 2,
        "auto_promote_safe": True,
    },
    {
        "company": "NVIDIA Quarterly Results",
        "layer": "capital",
        "type": "ir",
        "url": "https://investor.nvidia.com/financial-info/quarterly-results/default.aspx",
        "priority": "high",
        "cadence": "weekly",
        "purpose": "capital_market",
        "source_group": "capital_event",
        "reason": "Quarterly results are essential for AI revenue, margin, supply, and guidance tracking.",
        "authority_score": 5,
        "freshness_score": 3,
        "signal_score": 5,
        "noise_score": 1,
        "auto_promote_safe": True,
    },
]

REASON_CN = {
    "Meta AI Blog": "Meta 是开源模型、AI 基础设施和应用生态的重要玩家，官方博客适合跟踪模型、产品和基础设施更新。",
    "xAI News": "xAI 是前沿模型公司，官方新闻适合跟踪 Grok、模型能力、产品和商业化变化。",
    "Mistral AI News": "Mistral 是欧洲重要模型公司，官方新闻适合跟踪模型发布、企业产品和合作生态。",
    "Cohere Blog": "Cohere 聚焦企业模型和 RAG/搜索场景，官方博客适合观察企业 AI 采用和模型产品变化。",
    "Perplexity Blog": "Perplexity 是 AI 搜索和问答应用的重要标的，产品、合作和企业化动作具备应用层投资信号。",
    "CoreWeave Blog": "CoreWeave 是重要 AI 云厂商，官方更新可能反映算力供给、客户、产品和数据中心扩张信号。",
    "Oracle Cloud Infrastructure Blog": "Oracle Cloud 与 AI 训练和推理基础设施相关度上升，OCI 更新可补充云算力供给侧信号。",
    "Cloudflare AI Blog": "Cloudflare AI 和 Workers AI 代表边缘推理、开发者基础设施和推理成本变化方向。",
    "Broadcom News": "Broadcom 在 AI 网络、定制芯片和数据中心连接中重要，官方新闻可捕捉 AI 基础设施需求信号。",
    "Marvell Newsroom": "Marvell 与定制芯片、网络和数据中心 AI 基础设施相关，是芯片链补充标的。",
    "SK Hynix Newsroom": "SK Hynix 是 HBM 核心供应商，HBM 供给、路线图和客户进展直接影响 AI 算力供给。",
    "Samsung Semiconductor Newsroom": "Samsung 的存储和代工进展影响 HBM、先进内存和 AI 半导体供应链。",
    "Arm Newsroom": "Arm 与 CPU、边缘 AI、数据中心架构和授权经济相关，是芯片架构层的重要观察源。",
    "ServiceNow Newsroom": "ServiceNow 是企业工作流 AI 的重要应用平台，官方更新可观察企业 AI 落地。",
    "Salesforce Newsroom": "Salesforce Agentforce 和企业 AI 产品代表 CRM/办公应用层商业化方向。",
    "Adobe Newsroom": "Adobe Firefly 和创意 AI 是生成式 AI 应用变现的重要方向。",
    "Palantir Newsroom": "Palantir AIP 在企业和政府场景中具备 AI 应用层商业化信号。",
    "Cursor Changelog": "Cursor 是 AI 编程工具核心标的，changelog 能反映产品速度和竞争压力。",
    "Schneider Electric Newsroom": "Schneider Electric 与数据中心电力、冷却和能源管理相关，是 AI 物理基础设施重要标的。",
    "Constellation Newsroom": "Constellation 与核电和数据中心长期电力供应相关，适合跟踪 AI 电力约束。",
    "Vistra Newsroom": "Vistra 与电力供给和数据中心用电需求相关，是能源层补充信号。",
    "NVIDIA Quarterly Results": "NVIDIA 财报是 AI 收入、毛利率、供给、订单和指引的核心资本层信号。",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Score AI market monitoring gaps and write source candidates."
    )
    parser.add_argument(
        "--date",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="Date in YYYY-MM-DD format. Defaults to today.",
    )
    parser.add_argument(
        "--apply-official",
        action="store_true",
        help="Promote high-score safe official sources into sources.yaml.",
    )
    return parser.parse_args()


def load_yaml(path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or default


def save_yaml(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def load_raw_items(report_date):
    path = DATA_DIR / f"raw_items_{report_date}.json"
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    if isinstance(payload, list):
        return payload
    return payload.get("items") or []


def final_score(candidate, existing_layer_counts, raw_mentions):
    relevance_score = 5
    authority_score = candidate.get("authority_score", 3)
    freshness_score = candidate.get("freshness_score", 3)
    signal_score = candidate.get("signal_score", 3)
    noise_score = candidate.get("noise_score", 2)

    layer = candidate.get("layer")
    gap_bonus = 1 if existing_layer_counts.get(layer, 0) < 6 else 0
    mention_bonus = min(raw_mentions.get(candidate.get("company", "").lower(), 0), 2)

    score = (
        relevance_score
        + authority_score
        + freshness_score
        + signal_score
        + gap_bonus
        + mention_bonus
        - noise_score
    )

    return {
        "relevance_score": relevance_score,
        "authority_score": authority_score,
        "freshness_score": freshness_score,
        "signal_score": signal_score,
        "noise_score": noise_score,
        "gap_bonus": gap_bonus,
        "mention_bonus": mention_bonus,
        "final_score": score,
    }


def promotion_bucket(candidate, score_data):
    if score_data["final_score"] >= 18 and candidate.get("auto_promote_safe"):
        return "auto_promote_candidate"
    if score_data["final_score"] >= 15:
        return "needs_review"
    if score_data["final_score"] >= 12:
        return "watch_only"
    return "reject"


def source_key(source):
    return (source.get("url") or "").strip().rstrip("/")


def detect_discovery_mentions(items):
    tokens = [
        "cursor", "windsurf", "coreweave", "oracle", "cloudflare", "xai",
        "mistral", "perplexity", "cohere", "meta", "broadcom", "marvell",
        "hynix", "samsung", "arm", "servicenow", "salesforce", "adobe",
        "palantir", "schneider", "constellation", "vistra",
    ]
    mentions = Counter()
    for item in items:
        text = (
            f"{item.get('company') or ''}\n"
            f"{item.get('title') or ''}\n"
            f"{item.get('content') or ''}"
        ).lower()
        for token in tokens:
            if token in text:
                mentions[token] += 1
    return mentions


def update_health(existing_sources, items, report_date):
    health = load_yaml(HEALTH_PATH, {"sources": {}})
    health_sources = health.setdefault("sources", {})

    items_by_source_url = defaultdict(list)
    for item in items:
        source_url = source_key({"url": item.get("source_url") or item.get("url")})
        if source_url:
            items_by_source_url[source_url].append(item)

    for source in existing_sources:
        key = source_key(source)
        if not key:
            continue

        source_items = items_by_source_url.get(key, [])
        failed = [item for item in source_items if item.get("error")]
        unknown_time = [item for item in source_items if not item.get("published_at")]
        confirmed = [
            item for item in source_items
            if item.get("event_grade") == "confirmed_event"
        ]

        record = health_sources.setdefault(key, {
            "company": source.get("company"),
            "layer": source.get("layer"),
            "source_group": source.get("source_group"),
            "first_seen_at": report_date,
            "runs": 0,
            "success_runs": 0,
            "failure_runs": 0,
            "unknown_time_runs": 0,
            "confirmed_event_runs": 0,
        })

        record["company"] = source.get("company")
        record["layer"] = source.get("layer")
        record["source_group"] = source.get("source_group")
        record["last_checked_at"] = report_date
        record["last_item_count"] = len(source_items)
        record["last_failed_count"] = len(failed)
        record["last_unknown_time_count"] = len(unknown_time)
        record["last_confirmed_event_count"] = len(confirmed)
        record["runs"] = int(record.get("runs", 0)) + 1

        if source_items and not failed:
            record["success_runs"] = int(record.get("success_runs", 0)) + 1
            record["last_success_at"] = report_date

        if failed:
            record["failure_runs"] = int(record.get("failure_runs", 0)) + 1

        if unknown_time:
            record["unknown_time_runs"] = int(record.get("unknown_time_runs", 0)) + 1

        if confirmed:
            record["confirmed_event_runs"] = int(record.get("confirmed_event_runs", 0)) + 1

        recommendations = []
        if record["failure_runs"] >= 3:
            recommendations.append("连续或累计失败偏多，建议检查 URL、超时、反爬或降级为 manual。")
        if record["unknown_time_runs"] >= 3 and source.get("source_group") == "core_watchlist":
            recommendations.append("多次缺少发布时间，建议写专项解析器或降级为 background。")
        if source_items and not confirmed and source.get("source_group") == "core_watchlist":
            recommendations.append("近期没有 confirmed_event，继续观察，暂不降级。")
        record["recommendations"] = recommendations

    health["updated_at"] = datetime.now().isoformat(timespec="seconds")
    save_yaml(HEALTH_PATH, health)
    return health


def build_candidates(existing_sources, items, report_date):
    existing_urls = {source_key(source) for source in existing_sources}
    existing_names = {
        (source.get("company") or "").strip().lower()
        for source in existing_sources
    }
    existing_layer_counts = Counter(source.get("layer") for source in existing_sources)
    mentions = detect_discovery_mentions(items)

    candidate_records = []
    for candidate in STRATEGIC_CANDIDATES:
        key = source_key(candidate)
        name_key = (candidate.get("company") or "").strip().lower()

        if key in existing_urls or name_key in existing_names:
            continue

        score_data = final_score(candidate, existing_layer_counts, mentions)
        bucket = promotion_bucket(candidate, score_data)

        record = {
            "company": candidate["company"],
            "layer": candidate["layer"],
            "type": candidate["type"],
            "url": candidate["url"],
            "priority": candidate["priority"],
            "cadence": candidate["cadence"],
            "purpose": candidate["purpose"],
            "source_group": candidate["source_group"],
            "status": bucket,
            "final_score": score_data["final_score"],
            "scores": score_data,
            "reason": REASON_CN.get(candidate["company"], candidate["reason"]),
            "auto_promote_safe": candidate.get("auto_promote_safe", False),
            "suggested_at": report_date,
        }
        candidate_records.append(record)

    candidate_records.sort(key=lambda item: item["final_score"], reverse=True)

    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "date": report_date,
        "policy": {
            "auto_promote_candidate": "Official or stable high-score source; safe to add after review or with --apply-official.",
            "needs_review": "Potentially useful but should be reviewed before adding.",
            "watch_only": "Keep in candidate pool; do not add yet.",
            "reject": "Do not add under current evidence.",
        },
        "candidates": candidate_records,
    }
    save_yaml(CANDIDATES_PATH, payload)
    return candidate_records


def promote_official_candidates(existing_sources, candidates):
    existing_urls = {source_key(source) for source in existing_sources}
    promoted = []

    for candidate in candidates:
        if candidate.get("status") != "auto_promote_candidate":
            continue
        if not candidate.get("auto_promote_safe"):
            continue
        if source_key(candidate) in existing_urls:
            continue

        source = {
            key: candidate[key]
            for key in [
                "company", "layer", "type", "url", "priority",
                "cadence", "purpose", "source_group",
            ]
        }
        existing_sources.append(source)
        existing_urls.add(source_key(source))
        promoted.append(source)

    if promoted:
        save_yaml(SOURCES_PATH, {"sources": existing_sources})

    return promoted


def duplicate_sources(existing_sources):
    by_url = defaultdict(list)
    by_name = defaultdict(list)
    for source in existing_sources:
        by_url[source_key(source)].append(source)
        by_name[(source.get("company") or "").strip().lower()].append(source)

    duplicates = []
    for key, values in by_url.items():
        if key and len(values) > 1:
            duplicates.append({
                "type": "url",
                "key": key,
                "companies": [item.get("company") for item in values],
            })
    for key, values in by_name.items():
        if key and len(values) > 1:
            duplicates.append({
                "type": "company",
                "key": key,
                "urls": [item.get("url") for item in values],
            })
    return duplicates


def write_iteration_report(report_date, candidates, health, existing_sources, promoted):
    report_path = REPORTS_DIR / f"source_iteration_{report_date}.md"
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    by_layer = Counter(source.get("layer") for source in existing_sources)
    by_group = Counter(source.get("source_group") for source in existing_sources)
    duplicates = duplicate_sources(existing_sources)

    auto_candidates = [
        item for item in candidates
        if item.get("status") == "auto_promote_candidate"
    ]
    needs_review = [
        item for item in candidates
        if item.get("status") == "needs_review"
    ]

    lines = [
        f"# 监控系统迭代建议 - {report_date}",
        "",
        "## 1. 当前覆盖判断",
        "",
        f"- 正式监控源数量：{len(existing_sources)}",
        f"- 按层级分布：{', '.join(f'{k}: {v}' for k, v in sorted(by_layer.items()))}",
        f"- 按来源组分布：{', '.join(f'{k}: {v}' for k, v in sorted(by_group.items()))}",
        "- 迭代策略：官方 news / blog / changelog / IR 可以进入自动晋级候选；媒体、聚合页和社区榜单只进入候选池。",
        "",
        "## 2. 建议优先加入",
        "",
    ]

    if not auto_candidates:
        lines.append("- 暂无高分自动晋级候选。")
    else:
        for item in auto_candidates[:15]:
            lines.append(
                f"- **{item['company']}**（{item['layer']} / {item['source_group']} / score {item['final_score']}）：{item['reason']}  URL: {item['url']}"
            )

    lines.extend(["", "## 3. 需要人工确认", ""])
    if not needs_review:
        lines.append("- 暂无需要人工确认的候选。")
    else:
        for item in needs_review[:15]:
            lines.append(
                f"- **{item['company']}**（{item['layer']} / score {item['final_score']}）：{item['reason']}  URL: {item['url']}"
            )

    lines.extend(["", "## 4. 质量与清理建议", ""])
    if duplicates:
        for item in duplicates:
            if item["type"] == "company":
                lines.append(f"- 重复公司名：`{item['key']}`，URLs: {item['urls']}")
            else:
                lines.append(f"- 重复 URL：`{item['key']}`，companies: {item['companies']}")
    else:
        lines.append("- 未发现重复 URL 或重复公司名。")

    health_sources = health.get("sources", {})
    weak_records = [
        record for record in health_sources.values()
        if record.get("recommendations")
    ]
    if weak_records:
        for record in weak_records[:20]:
            lines.append(
                f"- **{record.get('company')}**：{'；'.join(record.get('recommendations') or [])}"
            )
    else:
        lines.append("- 暂无基于健康记录的降级建议。")

    lines.extend(["", "## 5. 本次自动写入", ""])
    if promoted:
        for source in promoted:
            lines.append(f"- 已加入 sources.yaml：{source['company']} | {source['url']}")
    else:
        lines.append("- 未自动修改 sources.yaml。本轮只生成候选池和建议。")

    lines.extend([
        "",
        "## 6. 输出文件",
        "",
        f"- 候选池：`config/source_candidates.yaml`",
        f"- 健康记录：`config/source_health.yaml`",
        f"- 本报告：`reports/source_iteration_{report_date}.md`",
        "",
    ])

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def main():
    args = parse_args()
    sources_payload = load_yaml(SOURCES_PATH, {"sources": []})
    existing_sources = sources_payload.get("sources", [])
    items = load_raw_items(args.date)

    health = update_health(existing_sources, items, args.date)
    candidates = build_candidates(existing_sources, items, args.date)
    promoted = []

    if args.apply_official:
        promoted = promote_official_candidates(existing_sources, candidates)
        health = update_health(existing_sources, items, args.date)

    report_path = write_iteration_report(
        args.date,
        candidates,
        health,
        existing_sources,
        promoted,
    )

    print(f"来源迭代完成：{report_path}")
    print(f"候选源数量：{len(candidates)}")
    print(f"自动晋级候选：{sum(1 for item in candidates if item.get('status') == 'auto_promote_candidate')}")
    print(f"本次自动写入：{len(promoted)}")


if __name__ == "__main__":
    main()
