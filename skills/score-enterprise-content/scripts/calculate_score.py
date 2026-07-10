#!/usr/bin/env python3
"""Validate dimension judgments and calculate the enterprise content gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROTOCOL = ROOT / "protocols/base-methodology.json"


def load(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit("evaluation must be a JSON object")
    return value


def load_score_protocol(path: str) -> dict[str, Any]:
    protocol = load(path)
    score = protocol.get("score")
    if not isinstance(score, dict) or not isinstance(score.get("dimensions"), list):
        raise SystemExit("protocol.score.dimensions must be an array")
    result = dict(score)
    result["protocol_id"] = protocol.get("protocol_id")
    return result


def calculate(evaluation: dict[str, Any], threshold: float, protocol: dict[str, Any]) -> dict[str, Any]:
    dimensions = evaluation.get("dimensions")
    if not isinstance(dimensions, dict):
        raise SystemExit("dimensions must be an object keyed by ER/SR/HP/QL/NA/AB/SAT")

    protocol_dimensions = protocol["dimensions"]
    weights = {str(item["key"]): float(item["weight"]) for item in protocol_dimensions}
    actions = {str(item["key"]): str(item["low_score_action"]) for item in protocol_dimensions}

    normalized: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    weighted = 0.0
    for key, weight in weights.items():
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

    maximum = sum(weight * 5 for weight in weights.values())
    composite = round(weighted / maximum * 10, 2)
    blocked = evaluation.get("blocked_reasons") or []
    if not isinstance(blocked, list):
        raise SystemExit("blocked_reasons must be an array")
    blocked = [str(item).strip() for item in blocked if str(item).strip()]
    low = sorted((key for key in weights if normalized[key]["score"] < 3), key=lambda key: normalized[key]["score"])

    return {
        "schema_version": "0.1",
        "protocol_id": protocol.get("protocol_id"),
        "content_id": evaluation.get("content_id", "unknown"),
        "track": evaluation.get("track", "unspecified"),
        "blind_score": True,
        "formula": "weighted points / maximum weighted points * 10",
        "threshold": threshold,
        "composite": composite,
        "pass": composite >= threshold and not blocked,
        "dimensions": normalized,
        "blocked_reasons": blocked,
        "next_actions": [actions[key] for key in low[:3]],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Calculate a gated enterprise content score")
    parser.add_argument("--input", required=True, help="Agent-authored dimension evaluation JSON")
    parser.add_argument("--out", help="Output JSON; omit to print only")
    parser.add_argument("--threshold", type=float)
    parser.add_argument("--protocol", default=str(DEFAULT_PROTOCOL))
    args = parser.parse_args()
    protocol = load_score_protocol(args.protocol)
    threshold = args.threshold if args.threshold is not None else float(protocol.get("pass_threshold", 6.0))
    if not 0 <= threshold <= 10:
        raise SystemExit("--threshold must be between 0 and 10")
    result = calculate(load(args.input), threshold, protocol)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        output = Path(args.out)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    print(json.dumps({"content_id": result["content_id"], "composite": result["composite"], "pass": result["pass"], "out": args.out}, ensure_ascii=False))


if __name__ == "__main__":
    main()
