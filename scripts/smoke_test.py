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


def run(command: list[str]) -> None:
    process = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if process.returncode != 0:
        print(process.stdout)
        print(process.stderr, file=sys.stderr)
        raise SystemExit(f"failed: {' '.join(command)}")


def create_video(ffmpeg: str, path: Path, color: str, with_audio: bool) -> None:
    command = [ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x568:d=1.2:r=30"]
    if with_audio:
        command.extend(["-f", "lavfi", "-i", "sine=frequency=440:duration=1.2", "-shortest"])
    command.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p"])
    if with_audio:
        command.extend(["-c:a", "aac"])
    command.append(str(path))
    run(command)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="content-growth-smoke-") as temp_raw:
        temp = Path(temp_raw)
        geo_out = temp / "geo.json"
        score_out = temp / "score.json"
        run(
            [
                sys.executable,
                "skills/generate-geo-tasks/scripts/generate_geo_tasks.py",
                "--input", "examples/demo-enterprise/enterprise-profile.json",
                "--out", str(geo_out),
            ]
        )
        run(
            [
                sys.executable,
                "skills/score-enterprise-content/scripts/calculate_score.py",
                "--input", "examples/demo-enterprise/score-evaluation.json",
                "--out", str(score_out),
            ]
        )
        geo = json.loads(geo_out.read_text(encoding="utf-8"))
        score = json.loads(score_out.read_text(encoding="utf-8"))
        assert geo["summary"]["total"] >= 3
        assert score["pass"] is True
        assert score["composite"] == 7.53

        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        video_status = "skipped: ffmpeg/ffprobe not installed"
        if ffmpeg and ffprobe:
            media = temp / "media"
            media.mkdir()
            create_video(ffmpeg, media / "hook_product.mp4", "red", True)
            create_video(ffmpeg, media / "proof_inspection.mp4", "blue", False)
            create_video(ffmpeg, media / "cta_drawing.mp4", "green", False)
            assets = temp / "assets.json"
            edl = temp / "edl.json"
            draft = temp / "draft.mp4"
            video_cli = "skills/auto-edit-local-video/scripts/local_video.py"
            run([sys.executable, video_cli, "scan-assets", "--media-dir", str(media), "--out", str(assets)])
            run(
                [
                    sys.executable,
                    video_cli,
                    "make-edl",
                    "--script", "examples/demo-enterprise/video-script.json",
                    "--assets", str(assets),
                    "--out", str(edl),
                ]
            )
            edl_data = json.loads(edl.read_text(encoding="utf-8"))
            assert edl_data["render_gate"] == "ready"
            run([sys.executable, video_cli, "render-edl", "--edl", str(edl), "--assets", str(assets), "--out", str(draft), "--width", "320", "--height", "568"])
            assert draft.stat().st_size > 0
            video_status = f"passed: {draft.stat().st_size} bytes"

    print(json.dumps({"geo": "passed", "score": "passed", "video": video_status}, ensure_ascii=False))


if __name__ == "__main__":
    main()
