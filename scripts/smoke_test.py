#!/usr/bin/env python3
"""Repository smoke test using only temporary files."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if process.returncode != 0:
        print(process.stdout)
        print(process.stderr, file=sys.stderr)
        raise SystemExit(f"failed: {' '.join(command)}")
    return process


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="content-growth-smoke-") as temp_raw:
        temp = Path(temp_raw)
        doctor_process = run([sys.executable, "content_growth.py", "doctor", "--json"])
        doctor = json.loads(doctor_process.stdout)
        assert doctor["core"]["ready"] is True
        assert doctor["methodology"]["ready"] is True

        demo = temp / "demo"
        run([sys.executable, "content_growth.py", "demo", "--out", str(demo)])
        summary = json.loads((demo / "run-summary.json").read_text(encoding="utf-8"))
        geo = json.loads((demo / "geo-tasks.json").read_text(encoding="utf-8"))
        score = json.loads((demo / "score-result.json").read_text(encoding="utf-8"))
        assert geo["summary"]["total"] >= 3
        assert score["pass"] is True
        assert score["composite"] == 7.53
        if doctor["basic_video"]["ready"]:
            draft = Path(summary["video"]["draft"])
            assert draft.stat().st_size > 0
            video_status = f"passed: {draft.stat().st_size} bytes"
        else:
            assert summary["video"]["status"] == "skipped"
            video_status = "skipped: ffmpeg/ffprobe not installed"

        workspace = temp / "workspace"
        first_init = json.loads(run([sys.executable, "content_growth.py", "init", str(workspace)]).stdout)
        second_init = json.loads(run([sys.executable, "content_growth.py", "init", str(workspace)]).stdout)
        assert first_init["created"]
        assert second_init["created"] == []
        strict_template = subprocess.run(
            [sys.executable, "content_growth.py", "run", str(workspace), "--skip-video", "--strict"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        assert strict_template.returncode == 2
        template_summary = json.loads((workspace / "output/run-summary.json").read_text(encoding="utf-8"))
        assert template_summary["geo"]["status"] == "blocked_template"
        assert template_summary["complete"] is False
        (workspace / "score-evaluation.json").write_text(
            (ROOT / "examples/demo-enterprise/score-evaluation.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        profile = json.loads((workspace / "enterprise-profile.json").read_text(encoding="utf-8"))
        profile["template_data"] = False
        (workspace / "enterprise-profile.json").write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        run([sys.executable, "content_growth.py", "run", str(workspace), "--skip-video"])
        workspace_summary = json.loads((workspace / "output/run-summary.json").read_text(encoding="utf-8"))
        assert workspace_summary["geo"]["status"] == "complete"
        assert workspace_summary["score"]["status"] == "complete"
        assert workspace_summary["video"]["status"] == "skipped"
        assert workspace_summary["complete"] is True

    print(json.dumps({"doctor": "passed", "demo": "passed", "init": "passed", "run": "passed", "video": video_status}, ensure_ascii=False))


if __name__ == "__main__":
    main()
