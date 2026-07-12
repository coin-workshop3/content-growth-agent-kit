#!/usr/bin/env python3
"""Repository smoke test using only temporary files."""

from __future__ import annotations

import json
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional


ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], *, env: Optional[dict[str, str]] = None) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, env=env)
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


def create_mock_whisper(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import json
import sys
from pathlib import Path

source = Path(sys.argv[1])
output_dir = Path(sys.argv[sys.argv.index("--output_dir") + 1])
output_dir.mkdir(parents=True, exist_ok=True)
(output_dir / f"{source.stem}.json").write_text(json.dumps({
    "language": "zh",
    "text": "自动转写测试。然后然后第二句话。",
    "segments": [
        {"start": 0.2, "end": 2.0, "text": "自动转写测试。"},
        {"start": 3.1, "end": 5.0, "text": "然后然后第二句话。"}
    ]
}, ensure_ascii=False), encoding="utf-8")
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def main() -> None:
    video_module = runpy.run_path(str(ROOT / "skills/auto-edit-local-video/scripts/local_video.py"))
    assert video_module["display_dimensions"](
        {"width": 3840, "height": 2160, "side_data_list": [{"rotation": 90}]}
    ) == (2160, 3840, 90)
    caption_chunks = video_module["split_caption_text"]("名字、文件名,找到你的文件信息吗?", 16)
    assert caption_chunks[-1].endswith("?")
    assert caption_chunks[-1] != "?"

    with tempfile.TemporaryDirectory(prefix="content-growth-smoke-") as temp_raw:
        temp = Path(temp_raw)
        doctor_process = run([sys.executable, "content_growth.py", "doctor", "--json"])
        doctor = json.loads(doctor_process.stdout)
        assert doctor["core"]["ready"] is True
        assert doctor["methodology"]["ready"] is True
        assert doctor["captions"]["sidecar_srt"] is True
        assert "png_overlay" in doctor["captions"]
        setup = json.loads(run([sys.executable, "content_growth.py", "setup", "--json"]).stdout)
        assert setup["automatic_install"] is False
        assert setup["official_guides"]["whisper"].startswith("https://")

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

            if os.name != "nt":
                mock_bin = temp / "mock-bin"
                mock_bin.mkdir()
                create_mock_whisper(mock_bin / "whisper")
                whisper_env = dict(os.environ)
                whisper_env["PATH"] = str(mock_bin) + os.pathsep + whisper_env.get("PATH", "")
                auto_result = json.loads(
                    run(
                        [
                            sys.executable,
                            "content_growth.py",
                            "video",
                            str(talking_workspace),
                            "--mode", "talking-head",
                            "--auto-transcribe",
                            "--fast-preview",
                        ],
                        env=whisper_env,
                    ).stdout
                )
                assert auto_result["source_strategy"] == "local_whisper_unreviewed"
                assert auto_result["transcription"]["status"] == "complete_needs_human_review"
                assert auto_result["transcription"]["filler_candidates"] == 1
                assert auto_result["formal_gate"] == "preview_only"
                assert auto_result["caption_entries"] == 2
                assert Path(auto_result["captions"]).stat().st_size > 0
                auto_edl = json.loads(Path(auto_result["edl"]).read_text(encoding="utf-8"))
                assert all(
                    clip["reason"].startswith("Unreviewed local transcript boundary")
                    for clip in auto_edl["clips"]
                )
                transcribe_result = json.loads(
                    run(
                        [sys.executable, "content_growth.py", "transcribe", str(talking_workspace)],
                        env=whisper_env,
                    ).stdout
                )
                assert transcribe_result["review_gate"] == "needs_human_review"
                assert transcribe_result["filler_candidates"] == 1
                auto_transcript = json.loads(
                    (talking_workspace / "output/video/transcript.auto.json").read_text(encoding="utf-8")
                )
                assert auto_transcript["filler_review"]["candidate_count"] == 1
                assert auto_transcript["filler_review"]["automatic_deletion"] is False
                review_result = json.loads(
                    run([sys.executable, "content_growth.py", "review-transcript", str(talking_workspace)]).stdout
                )
                assert review_result["candidate_count"] == 1
                assert review_result["automatic_deletion"] is False
                assert (talking_workspace / "output/video/transcript.review-candidates.json").is_file()
                reused_result = json.loads(
                    run(
                        [sys.executable, "content_growth.py", "video", str(talking_workspace), "--mode", "talking-head", "--fast-preview"]
                    ).stdout
                )
                assert reused_result["source_strategy"] == "local_whisper_unreviewed"
                assert reused_result["transcription"]["status"] == "existing_auto_transcript"

            shutil.copyfile(ROOT / "examples/demo-enterprise/transcript.reviewed.json", talking_workspace / "transcript.reviewed.json")
            reviewed_result = json.loads(
                run([sys.executable, "content_growth.py", "video", str(talking_workspace), "--mode", "talking-head", "--fast-preview"]).stdout
            )
            assert reviewed_result["source_strategy"] == "transcript"
            assert reviewed_result["formal_gate"] == "ready_for_human_review"
            assert reviewed_result["caption_entries"] > 0
            assert Path(reviewed_result["captions"]).stat().st_size > 0
            assert reviewed_result["video_preset"] == "medium"
            assert reviewed_result["video_crf"] == 21
            reviewed_edl = json.loads(Path(reviewed_result["edl"]).read_text(encoding="utf-8"))
            assert all(clip["reason"] == "Reviewed transcript boundary" for clip in reviewed_edl["clips"])

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
            assert material_result["caption_entries"] > 0
            assert Path(material_result["captions"]).stat().st_size > 0
            assert material_result["caption_delivery"] in {"sidecar_srt", "burned_in"}
            assert material_result["caption_style"] == "bold_b2b"
            assert material_result["caption_style_applied"] == (material_result["caption_delivery"] == "burned_in")

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
