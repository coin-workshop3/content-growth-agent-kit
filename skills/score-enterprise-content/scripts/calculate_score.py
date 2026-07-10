#!/usr/bin/env python3
"""Validate dimension judgments and calculate the enterprise content gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


WEIGHTS = {"ER": 1.5, "SR": 1.5, "HP": 1.5, "QL": 1.0, "NA": 1.0, "AB": 1.0, "SAT": 1.0}
ACTIONS = {
    "ER": "加入一条具体客户原话、触发场景或可感知成本。",
    "SR": "明确一个真实搜索问题、意图和核心实体。",
    "HP": "把开头改为具体风险、反差、判断或即时收益。",
    "QL": "增加一句有边界且有证据支撑的判断句。",
    "NA": "补齐问题、标准、证据、边界和下一步的决策链。",
    "AB": "缩小到明确的买方、决策人或高价值使用者。",
    "SAT": "加入可验证的对比、避坑标准或取舍。",
}


def load(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit("evaluation must be a JSON object")
    return value


def calculate(evaluation: dict[str, Any], threshold: float) -> dict[str, Any]:
    dimensions = evaluation.get("dimensions")
    if not isinstance(dimensions, dict):
        raise SystemExit("dimensions must be an object keyed by ER/SR/HP/QL/NA/AB/SAT")

    normalized: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    weighted = 0.0
    for key, weight in WEIGHTS.items():
        item = dimensions.get(key)
        if not isinstance(item, dict):
            errors.append(f"missing dimension {key}")
            continue
        score = item.get("score")
        if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= 5:
            errors.append(f"{key}.score must be an integer from 0 to 5")
            continue
        reason = str(item.get("reason") or "").strip()
        evidence = str(item.get("evidence") or "").strip()
        if not reason:
            errors.append(f"{key}.reason is required")
        if not evidence:
            errors.append(f"{key}.evidence is required; use an explicit absence when needed")
        weighted += score * weight
        normalized[key] = {"score": score, "weight": weight, "reason": reason, "evidence": evidence}

    if errors:
        raise SystemExit("invalid evaluation:\n- " + "\n- ".join(errors))

    maximum = sum(weight * 5 for weight in WEIGHTS.values())
    composite = round(weighted / maximum * 10, 2)
    blocked = evaluation.get("blocked_reasons") or []
    if not isinstance(blocked, list):
        raise SystemExit("blocked_reasons must be an array")
    blocked = [str(item).strip() for item in blocked if str(item).strip()]
    low = sorted((key for key in WEIGHTS if normalized[key]["score"] < 3), key=lambda key: normalized[key]["score"])

    return {
        "schema_version": "0.1",
        "content_id": evaluation.get("content_id", "unknown"),
        "track": evaluation.get("track", "unspecified"),
        "blind_score": True,
        "formula": "weighted points / maximum weighted points * 10",
        "threshold": threshold,
        "composite": composite,
        "pass": composite >= threshold and not blocked,
        "dimensions": normalized,
        "blocked_reasons": blocked,
        "next_actions": [ACTIONS[key] for key in low[:3]],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Calculate a gated enterprise content score")
    parser.add_argument("--input", required=True, help="Agent-authored dimension evaluation JSON")
    parser.add_argument("--out", help="Output JSON; omit to print only")
    parser.add_argument("--threshold", type=float, default=6.0)
    args = parser.parse_args()
    if not 0 <= args.threshold <= 10:
        raise SystemExit("--threshold must be between 0 and 10")
    result = calculate(load(args.input), args.threshold)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(json.dumps({"content_id": result["content_id"], "composite": result["composite"], "pass": result["pass"], "out": args.out}, ensure_ascii=False))


if __name__ == "__main__":
    main()
