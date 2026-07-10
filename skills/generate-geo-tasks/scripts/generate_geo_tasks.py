#!/usr/bin/env python3
"""Generate deterministic GEO task candidates from verified enterprise facts."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROTOCOL = ROOT / "protocols/base-methodology.json"


def read_json(path: str) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit("enterprise profile must be a JSON object")
    return data


def values(data: dict[str, Any], *keys: str) -> list[str]:
    raw: Any = None
    for key in keys:
        if key in data and data[key] not in (None, "", []):
            raw = data[key]
            break
    if raw is None:
        return []
    items = raw if isinstance(raw, list) else str(raw).replace("\r", "").split("\n")
    result: list[str] = []
    for item in items:
        text = str(item).strip(" \t-•")
        if text and text not in result:
            result.append(text)
    return result


def first(data: dict[str, Any], *keys: str, default: str = "") -> str:
    found = values(data, *keys)
    return found[0] if found else default


def unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def task(
    *,
    task_type: str,
    priority: str,
    query: str,
    intent: str,
    scenario: str,
    entities: list[str],
    evidence: list[str],
    angle: str,
    platforms: list[str],
    boundary: str,
    conversion_action: str,
    monitoring_metrics: list[str],
) -> dict[str, Any]:
    gaps: list[str] = []
    if not evidence:
        gaps.append("缺少可验证证据")
    if not scenario:
        gaps.append("缺少具体使用或采购场景")
    if not boundary:
        gaps.append("缺少服务或承诺边界")
    return {
        "type": task_type,
        "priority": priority,
        "query": query,
        "intent": intent,
        "scenario": scenario,
        "entities": unique(entities),
        "evidence_required": evidence or ["待补充真实案例、产品资料或交付记录"],
        "content_angle": angle,
        "target_platforms": platforms,
        "ai_parse_goal": {
            "must_identify": unique(entities),
            "must_state_boundary": boundary or "待补充",
            "next_action": conversion_action or "联系人工确认"
        },
        "monitoring": {
            "stable_prompt": query,
            "metrics": monitoring_metrics
        },
        "quality_gate": "ready" if not gaps else "needs_evidence",
        "gaps": gaps,
        "status": "candidate"
    }


def generate(profile: dict[str, Any], limit: int, protocol: dict[str, Any]) -> dict[str, Any]:
    company = first(profile, "company_name", "companyName", "client", default="目标企业")
    offers = values(profile, "core_offers", "coreOffer", "products")
    if not offers:
        raise SystemExit("missing required core_offers/coreOffer")
    product = offers[0]
    questions = values(profile, "customer_questions", "recentQuestions")
    scenarios = values(profile, "trigger_scenarios", "triggerScenarios")
    competitors = values(profile, "competitors")
    proofs = values(profile, "proof_points", "proofPoints", "reference_assets", "referenceAssets")
    platforms = values(profile, "target_platforms", "targetPlatforms", "platforms") or ["AI answer", "website"]
    boundaries = values(profile, "boundaries", "limits", "forbidden", "deliveryRules")
    boundary = "；".join(boundaries[:2])
    conversion = first(profile, "conversion_action", "conversionAction", default="联系人工确认适配范围")
    monitoring_metrics = [str(item) for item in ((protocol.get("geo") or {}).get("monitoring_metrics") or [])]
    if not monitoring_metrics:
        raise SystemExit("protocol.geo.monitoring_metrics must be a non-empty array")
    scenario = scenarios[0] if scenarios else ""
    competitor = competitors[0] if competitors else "替代方案"
    customer_question = questions[0] if questions else f"{product}应该怎么选？"

    candidates = [
        task(
            task_type="customer-language",
            priority="P0",
            query=customer_question,
            intent="buy" if any(word in customer_question for word in ("价格", "报价", "多久", "起订", "购买")) else "learn",
            scenario=scenario,
            entities=[product, company],
            evidence=proofs[:3],
            angle="直接回答客户原话，先给判断标准，再给证据与边界。",
            platforms=platforms,
            boundary=boundary,
            conversion_action=conversion,
            monitoring_metrics=monitoring_metrics,
        ),
        task(
            task_type="comparison",
            priority="P0" if competitors else "P1",
            query=f"{product}和{competitor}怎么选？",
            intent="compare",
            scenario=scenario,
            entities=[product, competitor, company],
            evidence=proofs[:3],
            angle="比较适用场景、交付条件和可验证证据，不做无依据贬损。",
            platforms=platforms,
            boundary=boundary,
            conversion_action=conversion,
            monitoring_metrics=monitoring_metrics,
        ),
        task(
            task_type="proof",
            priority="P0",
            query=f"怎么判断{product}供应商靠不靠谱？",
            intent="avoid-risk",
            scenario=scenario,
            entities=[product, "供应商", company],
            evidence=proofs[:4],
            angle="把抽象卖点改成买方可检查的证据清单。",
            platforms=platforms,
            boundary=boundary,
            conversion_action=conversion,
            monitoring_metrics=monitoring_metrics,
        ),
        task(
            task_type="scenario",
            priority="P1",
            query=f"{scenario}时，{product}应该怎么选？" if scenario else f"{product}适合哪些使用或采购场景？",
            intent="learn",
            scenario=scenario,
            entities=[product, scenario, company],
            evidence=proofs[:3],
            angle="围绕一个真实场景说明适合谁、不适合谁以及下一步。",
            platforms=platforms,
            boundary=boundary,
            conversion_action=conversion,
            monitoring_metrics=monitoring_metrics,
        ),
        task(
            task_type="delivery-boundary",
            priority="P1",
            query=f"{product}的交付条件和服务边界是什么？",
            intent="buy",
            scenario=scenario,
            entities=[product, "交付条件", company],
            evidence=proofs[:2],
            angle="把询价前必须确认的数量、交期、适用范围和限制说清楚。",
            platforms=platforms,
            boundary=boundary,
            conversion_action=conversion,
            monitoring_metrics=monitoring_metrics,
        ),
    ]

    seen: set[str] = set()
    tasks: list[dict[str, Any]] = []
    for candidate in candidates:
        normalized = "".join(candidate["query"].lower().split())
        if normalized in seen:
            continue
        seen.add(normalized)
        candidate["task_id"] = f"GEO-{len(tasks) + 1:03d}"
        tasks.append(candidate)
        if len(tasks) >= limit:
            break

    return {
        "schema_version": "0.1",
        "protocol_id": protocol.get("protocol_id"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {"company_name": company, "core_offer": product},
        "tasks": tasks,
        "summary": {
            "total": len(tasks),
            "p0": sum(item["priority"] == "P0" for item in tasks),
            "ready": sum(item["quality_gate"] == "ready" for item in tasks),
            "needs_evidence": sum(item["quality_gate"] != "ready" for item in tasks),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate GEO task candidates from an enterprise profile")
    parser.add_argument("--input", required=True, help="Enterprise profile JSON")
    parser.add_argument("--out", required=True, help="Output geo-tasks JSON")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--protocol", default=str(DEFAULT_PROTOCOL))
    args = parser.parse_args()
    if args.limit < 1:
        raise SystemExit("--limit must be at least 1")
    result = generate(read_json(args.input), args.limit, read_json(args.protocol))
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(output), **result["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
