#!/usr/bin/env python3
"""Repository smoke test using only temporary files."""

from __future__ import annotations

import json
import shutil
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


def create_talking_head_video(ffmpeg: str, path: Path) -> None:
    command = [
        ffmpeg,
        "-y",
        "-f", "lavfi", "-i", "color=c=purple:s=320x568:d=8:r=30",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=2",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono:d=1",
        "-f", "lavfi", "-i", "sine=frequency=520:sample_rate=48000:duration=2",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono:d=1.2",
        "-f", "lavfi", "-i", "sine=frequency=600:sample_rate=48000:duration=1.8",
        "-filter_complex", "[1:a][2:a][3:a][4:a][5:a]concat=n=5:v=0:a=1[aout]",
        "-map", "0:v", "-map", "[aout]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
        str(path),
    ]
    run(command)


def create_silent_video(ffmpeg: str, path: Path) -> None:
    run([
        ffmpeg,
        "-y",
        "-f", "lavfi", "-i", "color=c=gray:s=320x568:d=1:r=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(path),
    ])


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
            draft = Path(summary["video"]["material_assembly"]["draft"])
            assert draft.stat().st_size > 0
            assert Path(summary["video"]["talking_head"]["draft"]).stat().st_size > 0
            assert summary["video"]["talking_head"]["formal_gate"] == "preview_only"
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

        if doctor["basic_video"]["ready"]:
            talking_workspace = temp / "talking-workspace"
            talking_media = talking_workspace / "media"
            talking_media.mkdir(parents=True)
            talking_source = talking_media / "talking_head_voice.mp4"
            create_talking_head_video(str(doctor["basic_video"]["ffmpeg"]), talking_source)
            talking_result = json.loads(
                run([sys.executable, "content_growth.py", "video", str(talking_workspace), "--mode", "auto", "--fast-preview"]).stdout
            )
            assert talking_result["edit_mode"] == "talking_head_cleanup"
            assert talking_result["recommendation"]["inventory"]["audio_video_candidates"]
            assert talking_result["source_strategy"] == "ffmpeg_silence_only"
            assert talking_result["formal_gate"] == "preview_only"
            assert talking_result["publication_gate"] == "blocked_pending_human_review"
            silence_report = json.loads(Path(talking_result["silence_report"]).read_text(encoding="utf-8"))
            assert len(silence_report["silences"]) >= 2
            assert Path(talking_result["draft"]).stat().st_size > 0

            shutil.copyfile(ROOT / "examples/demo-enterprise/transcript.reviewed.json", talking_workspace / "transcript.reviewed.json")
            reviewed_result = json.loads(
                run([sys.executable, "content_growth.py", "video", str(talking_workspace), "--mode", "talking-head", "--fast-preview"]).stdout
            )
            assert reviewed_result["source_strategy"] == "transcript"
            assert reviewed_result["formal_gate"] == "ready_for_human_review"

            material_workspace = temp / "material-workspace"
            material_media = material_workspace / "media"
            material_media.mkdir(parents=True)
            shutil.copyfile(ROOT / "examples/demo-enterprise/video-script.json", material_workspace / "video-script.json")
            for source in (demo / "synthetic-media").glob("*.mp4"):
                shutil.copyfile(source, material_media / source.name)
            material_result = json.loads(
                run([sys.executable, "content_growth.py", "video", str(material_workspace), "--mode", "auto", "--fast-preview"]).stdout
            )
            assert material_result["edit_mode"] == "scripted_asset_assembly"
            assert material_result["recommendation"]["recommended_mode"] == "scripted_asset_assembly"
            assert material_result["publication_gate"] == "blocked_pending_human_review"
            assert Path(material_result["draft"]).stat().st_size > 0

            ambiguous_workspace = temp / "ambiguous-workspace"
            ambiguous_media = ambiguous_workspace / "media"
            ambiguous_media.mkdir(parents=True)
            create_silent_video(str(doctor["basic_video"]["ffmpeg"]), ambiguous_media / "silent.mp4")
            ambiguous_process = subprocess.run(
                [sys.executable, "content_growth.py", "video", str(ambiguous_workspace), "--mode", "auto", "--fast-preview"],
                cwd=ROOT,
                text=True,
                capture_output=True,
            )
            assert ambiguous_process.returncode == 2
            ambiguous_result = json.loads(ambiguous_process.stdout)
            assert ambiguous_result["status"] == "needs_mode_choice"
            assert ambiguous_result["recommendation"]["requires_user_choice"] is True

    print(json.dumps({"doctor": "passed", "demo": "passed", "init": "passed", "run": "passed", "material_assembly": video_status, "talking_head": "passed" if doctor["basic_video"]["ready"] else "skipped"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
