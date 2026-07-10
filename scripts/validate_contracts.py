#!/usr/bin/env python3
"""Validate repository-owned JSON contracts without third-party packages."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return value


def main() -> None:
    schemas = sorted((ROOT / "schemas").glob("*.schema.json"))
    if len(schemas) < 8:
        raise SystemExit("expected at least eight base schemas")
    for path in schemas:
        value = read(path)
        if value.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise SystemExit(f"unexpected JSON Schema version: {path}")
        if value.get("type") != "object":
            raise SystemExit(f"top-level schema must be an object: {path}")

    protocol = read(ROOT / "protocols/base-methodology.json")
    if not all(key in protocol for key in ("geo", "score", "video")):
        raise SystemExit("base methodology must include geo, score, and video")
    score_keys = [str(item.get("key")) for item in protocol["score"].get("dimensions") or []]
    if score_keys != ["ER", "SR", "HP", "QL", "NA", "AB", "SAT"]:
        raise SystemExit(f"unexpected score dimension order: {score_keys}")
    if float(protocol["score"].get("pass_threshold", -1)) != 6.0:
        raise SystemExit("base score threshold must be 6.0")
    video = protocol["video"]
    if set((video.get("modes") or {}).keys()) != {"talking_head_cleanup", "scripted_asset_assembly"}:
        raise SystemExit("video protocol must expose exactly the two supported editing modes")
    if (video.get("render") or {}).get("caption_fallback") != "sidecar_srt":
        raise SystemExit("video protocol must preserve portable SRT captions when burn-in is unavailable")
    local_transcription = (video.get("capability_levels") or {}).get("local_transcription_optional") or {}
    if local_transcription.get("source_upload") is not False or local_transcription.get("human_transcript_review_required") is not True:
        raise SystemExit("local transcription must prohibit source upload and require human transcript review")

    for path in sorted((ROOT / "examples").rglob("*.json")):
        read(path)
    print(json.dumps({"schemas": len(schemas), "protocol": protocol["protocol_id"], "examples": "valid"}))


if __name__ == "__main__":
    main()
