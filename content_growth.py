#!/usr/bin/env python3
"""One-command entry point for the Content Growth Agent Kit."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional


ROOT = Path(__file__).resolve().parent
GEO_SCRIPT = ROOT / "skills/generate-geo-tasks/scripts/generate_geo_tasks.py"
SCORE_SCRIPT = ROOT / "skills/score-enterprise-content/scripts/calculate_score.py"
VIDEO_SCRIPT = ROOT / "skills/auto-edit-local-video/scripts/local_video.py"
EXAMPLE_DIR = ROOT / "examples/demo-enterprise"
BASE_PROTOCOL = ROOT / "protocols/base-methodology.json"


def execute(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(command, cwd=ROOT, text=True, capture_output=capture, check=False)
    if process.returncode != 0:
        if capture:
            if process.stdout:
                print(process.stdout, file=sys.stderr)
            if process.stderr:
                print(process.stderr, file=sys.stderr)
        raise SystemExit(f"command failed ({process.returncode}): {' '.join(command)}")
    return process


def command_available(name: str) -> Optional[str]:
    return shutil.which(name)


def module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def doctor_report() -> dict[str, Any]:
    required_files = [ROOT / "AGENTS.md", GEO_SCRIPT, SCORE_SCRIPT, VIDEO_SCRIPT]
    ffmpeg = command_available("ffmpeg")
    ffprobe = command_available("ffprobe")
    protocol = json.loads(BASE_PROTOCOL.read_text(encoding="utf-8")) if BASE_PROTOCOL.is_file() else {}
    modes = ((protocol.get("video") or {}).get("modes") or {}) if isinstance(protocol, dict) else {}
    return {
        "schema_version": "0.3",
        "methodology": {
            "ready": BASE_PROTOCOL.is_file(),
            "protocol": str(BASE_PROTOCOL),
        },
        "core": {
            "ready": sys.version_info >= (3, 9) and all(path.is_file() for path in required_files),
            "python": {
                "ready": sys.version_info >= (3, 9),
                "version": ".".join(str(part) for part in sys.version_info[:3]),
                "minimum": "3.9",
            },
            "repository_files": {
                "ready": all(path.is_file() for path in required_files),
                "missing": [str(path.relative_to(ROOT)) for path in required_files if not path.is_file()],
            },
        },
        "basic_video": {
            "ready": bool(ffmpeg and ffprobe),
            "required_for": ["media inventory", "EDL render", "basic 9:16 draft"],
            "ffmpeg": ffmpeg,
            "ffprobe": ffprobe,
        },
        "video_modes": {
            "talking_head_cleanup": {
                "ready_for_preview": bool(ffmpeg and ffprobe and modes.get("talking_head_cleanup")),
                "formal_requirement": "reviewed timestamped transcript",
            },
            "scripted_asset_assembly": {
                "ready_for_preview": bool(ffmpeg and ffprobe and modes.get("scripted_asset_assembly")),
                "formal_requirement": "structured script, matched assets, confirmed spoken copy for captions",
            },
        },
        "optional_video": {
            "note": "Detected only; the toolkit never installs or runs these without an explicit task.",
            "whisperx": {"ready": module_available("whisperx"), "adds": "speech transcription and word timestamps"},
            "auto_editor": {"ready": bool(command_available("auto-editor")), "adds": "silence and pause based cutting"},
            "pysubs2": {"ready": module_available("pysubs2"), "adds": "advanced subtitle authoring"},
            "npx": {"ready": bool(command_available("npx")), "adds": "optional Remotion/HyperFrames style packaging"},
            "pyjianyingdraft": {"ready": module_available("pyJianYingDraft"), "adds": "optional Jianying draft export"},
        },
    }


def print_doctor(report: dict[str, Any]) -> None:
    core = report["core"]
    video = report["basic_video"]
    print("Content Growth Agent Kit doctor")
    print(f"  Core GEO/score: {'READY' if core['ready'] else 'BLOCKED'}")
    print(f"  Python: {core['python']['version']} (minimum {core['python']['minimum']})")
    print(f"  Basic video: {'READY' if video['ready'] else 'OPTIONAL / NOT READY'}")
    print(f"  ffmpeg: {video['ffmpeg'] or 'not found'}")
    print(f"  ffprobe: {video['ffprobe'] or 'not found'}")
    print(
        "  Video modes: "
        f"talking-head={'PREVIEW READY' if report['video_modes']['talking_head_cleanup']['ready_for_preview'] else 'NOT READY'}, "
        f"material-assembly={'PREVIEW READY' if report['video_modes']['scripted_asset_assembly']['ready_for_preview'] else 'NOT READY'}"
    )
    optional = report["optional_video"]
    ready_optional = [
        f"{name} ({value.get('adds')})"
        for name, value in optional.items()
        if isinstance(value, dict) and value.get("ready")
    ]
    print(f"  Optional advanced video tools detected: {', '.join(ready_optional) if ready_optional else 'none'}")
    if not video["ready"]:
        print("  GEO and score still work. Install FFmpeg only when local video rendering is needed.")


def command_doctor(args: argparse.Namespace) -> None:
    report = doctor_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_doctor(report)


def run_geo(profile: Path, output: Path) -> None:
    execute([sys.executable, str(GEO_SCRIPT), "--input", str(profile), "--out", str(output)], capture=True)


def run_score(evaluation: Path, output: Path) -> None:
    execute([sys.executable, str(SCORE_SCRIPT), "--input", str(evaluation), "--out", str(output)], capture=True)


def create_demo_video(path: Path, color: str, duration: float, with_audio: bool) -> None:
    ffmpeg = command_available("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is required to create demo video")
    command = [ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x568:d={duration}:r=30"]
    if with_audio:
        command.extend(["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}", "-shortest"])
    command.extend(["-c:v", "libx264", "-pix_fmt", "yuv420p"])
    if with_audio:
        command.extend(["-c:a", "aac"])
    command.append(str(path))
    execute(command, capture=True)


def create_demo_talking_head_video(path: Path) -> None:
    ffmpeg = command_available("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg is required to create talking-head demo video")
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
    execute(command, capture=True)


def run_video(script: Path, media: Path, output: Path, *, fast_preview: bool = False) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    assets = output / "asset-index.json"
    edl = output / "edl.json"
    draft = output / "draft.mp4"
    execute([sys.executable, str(VIDEO_SCRIPT), "scan-assets", "--media-dir", str(media), "--out", str(assets)], capture=True)
    execute([sys.executable, str(VIDEO_SCRIPT), "make-edl", "--script", str(script), "--assets", str(assets), "--out", str(edl)], capture=True)
    edl_data = json.loads(edl.read_text(encoding="utf-8"))
    result: dict[str, Any] = {
        "status": "draft_rendered" if edl_data.get("render_gate") == "ready" else "blocked",
        "edit_mode": "scripted_asset_assembly",
        "formal_gate": edl_data.get("formal_gate"),
        "publication_gate": edl_data.get("publication_gate"),
        "human_review_required": True,
        "assets": str(assets),
        "edl": str(edl),
        "render_gate": edl_data.get("render_gate"),
        "missing": edl_data.get("missing") or [],
    }
    if edl_data.get("render_gate") == "ready":
        command = [
            sys.executable,
            str(VIDEO_SCRIPT),
            "render-edl",
            "--edl", str(edl),
            "--assets", str(assets),
            "--out", str(draft),
        ]
        if fast_preview:
            command.extend(["--width", "320", "--height", "568"])
        execute(command, capture=True)
        result["draft"] = str(draft)
    return result


def recommend_video_mode(workspace: Path, output: Path) -> dict[str, Any]:
    media = workspace / "media"
    output.mkdir(parents=True, exist_ok=True)
    assets = output / "asset-index.recommendation.json"
    recommendation = output / "mode-recommendation.json"
    execute([sys.executable, str(VIDEO_SCRIPT), "scan-assets", "--media-dir", str(media), "--out", str(assets)], capture=True)
    command = [sys.executable, str(VIDEO_SCRIPT), "recommend-mode", "--assets", str(assets), "--out", str(recommendation)]
    script = workspace / "video-script.json"
    if script.is_file():
        command.extend(["--script", str(script)])
    execute(command, capture=True)
    return json.loads(recommendation.read_text(encoding="utf-8"))


def run_talking_head(workspace: Path, output: Path, *, fast_preview: bool = False, asset_id: Optional[str] = None) -> dict[str, Any]:
    media = workspace / "media"
    output.mkdir(parents=True, exist_ok=True)
    assets_path = output / "asset-index.json"
    edl = output / "edl.talking-head.json"
    draft = output / "draft.talking-head.mp4"
    execute([sys.executable, str(VIDEO_SCRIPT), "scan-assets", "--media-dir", str(media), "--out", str(assets_path)], capture=True)
    index = json.loads(assets_path.read_text(encoding="utf-8"))
    source_asset = next(
        (
            asset
            for asset in index.get("assets") or []
            if asset.get("kind") == "video"
            and asset.get("has_audio")
            and (asset_id is None or str(asset.get("asset_id")) == asset_id)
        ),
        None,
    )
    if not source_asset:
        raise SystemExit("talking-head mode needs at least one local video with audio")
    source_path = Path(index["media_base"]) / str(source_asset["path"])
    reviewed_transcript = workspace / "transcript.reviewed.json"
    transcript = reviewed_transcript if reviewed_transcript.is_file() else workspace / "transcript.json"
    make_command = [
        sys.executable,
        str(VIDEO_SCRIPT),
        "make-talking-head-edl",
        "--assets", str(assets_path),
        "--asset-id", str(source_asset["asset_id"]),
        "--out", str(edl),
    ]
    silence_report = output / "silence-report.json"
    if transcript.is_file():
        make_command.extend(["--transcript", str(transcript)])
        source_strategy = "transcript"
    else:
        execute(
            [
                sys.executable,
                str(VIDEO_SCRIPT),
                "detect-silence",
                "--input", str(source_path),
                "--out", str(silence_report),
            ],
            capture=True,
        )
        make_command.extend(["--silence-report", str(silence_report)])
        source_strategy = "ffmpeg_silence_only"
    execute(make_command, capture=True)
    edl_data = json.loads(edl.read_text(encoding="utf-8"))
    render_command = [
        sys.executable,
        str(VIDEO_SCRIPT),
        "render-edl",
        "--edl", str(edl),
        "--assets", str(assets_path),
        "--out", str(draft),
    ]
    if fast_preview:
        render_command.extend(["--width", "320", "--height", "568"])
    execute(render_command, capture=True)
    return {
        "status": "draft_rendered",
        "edit_mode": "talking_head_cleanup",
        "source_strategy": source_strategy,
        "formal_gate": edl_data.get("formal_gate"),
        "publication_gate": edl_data.get("publication_gate"),
        "semantic_safety": edl_data.get("semantic_safety"),
        "assets": str(assets_path),
        "silence_report": str(silence_report) if silence_report.is_file() else None,
        "edl": str(edl),
        "draft": str(draft),
        "joins_requiring_review": len(edl_data.get("join_review") or []),
        "human_review_required": True,
    }


def run_workspace_video(
    workspace: Path,
    output: Path,
    mode: str,
    *,
    fast_preview: bool = False,
    asset_id: Optional[str] = None,
) -> dict[str, Any]:
    selected = mode
    recommendation = None
    if mode == "auto":
        recommendation = recommend_video_mode(workspace, output)
        if recommendation.get("requires_user_choice"):
            return {
                "status": "needs_mode_choice",
                "recommendation": recommendation,
                "action": "Choose talking-head or material-assembly explicitly",
            }
        selected = str(recommendation.get("recommended_mode") or "")
    if selected in {"talking-head", "talking_head_cleanup"}:
        result = run_talking_head(workspace, output, fast_preview=fast_preview, asset_id=asset_id)
    elif selected in {"material-assembly", "scripted_asset_assembly"}:
        script = workspace / "video-script.json"
        if not script.is_file():
            return {"status": "blocked", "reason": "material-assembly requires video-script.json"}
        result = run_video(script, workspace / "media", output, fast_preview=fast_preview)
    else:
        return {"status": "blocked", "reason": f"unsupported video mode: {selected}"}
    if recommendation:
        result["recommendation"] = recommendation
    return result


def command_video(args: argparse.Namespace) -> None:
    workspace = Path(args.workspace).expanduser().resolve()
    media = workspace / "media"
    if not workspace.is_dir() or not has_media(media):
        raise SystemExit("workspace/media must contain at least one supported local media file")
    if not doctor_report()["basic_video"]["ready"]:
        raise SystemExit("ffmpeg and ffprobe are required for video modes")
    output = workspace / "output/video"
    result = run_workspace_video(workspace, output, args.mode, fast_preview=args.fast_preview, asset_id=args.asset_id)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result.get("status") in {"blocked", "needs_mode_choice"}:
        raise SystemExit(2)


def write_summary(output: Path, summary: dict[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "run-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def command_demo(args: argparse.Namespace) -> None:
    output = Path(args.out).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {"schema_version": "0.3", "mode": "synthetic-demo", "output": str(output)}
    geo_output = output / "geo-tasks.json"
    score_output = output / "score-result.json"
    run_geo(EXAMPLE_DIR / "enterprise-profile.json", geo_output)
    run_score(EXAMPLE_DIR / "score-evaluation.json", score_output)
    summary["geo"] = str(geo_output)
    summary["score"] = str(score_output)

    runtime = doctor_report()
    if runtime["basic_video"]["ready"] and not args.skip_video:
        media = output / "synthetic-media"
        media.mkdir(parents=True, exist_ok=True)
        create_demo_video(media / "hook_product.mp4", "red", 2.8, True)
        create_demo_video(media / "proof_inspection.mp4", "blue", 4.2, False)
        create_demo_video(media / "cta_drawing.mp4", "green", 3.2, False)
        material_result = run_video(EXAMPLE_DIR / "video-script.json", media, output / "video/material-assembly", fast_preview=True)
        talking_workspace = output / "synthetic-talking-project"
        talking_media = talking_workspace / "media"
        talking_media.mkdir(parents=True, exist_ok=True)
        create_demo_talking_head_video(talking_media / "talking_head_voice.mp4")
        talking_result = run_talking_head(talking_workspace, output / "video/talking-head", fast_preview=True)
        summary["video"] = {
            "material_assembly": material_result,
            "talking_head": talking_result,
        }
    else:
        summary["video"] = {"status": "skipped", "reason": "--skip-video or ffmpeg/ffprobe unavailable"}
    write_summary(output, summary)
    print(f"Demo complete: {output}")
    print(f"Summary: {output / 'run-summary.json'}")


def write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def copy_if_missing(source: Path, target: Path) -> bool:
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return True


def write_profile_template(target: Path) -> bool:
    if target.exists():
        return False
    profile = json.loads((EXAMPLE_DIR / "enterprise-profile.json").read_text(encoding="utf-8"))
    profile["template_data"] = True
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def command_init(args: argparse.Namespace) -> None:
    workspace = Path(args.workspace).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    if write_profile_template(workspace / "enterprise-profile.json"):
        created.append("enterprise-profile.json")
    if copy_if_missing(EXAMPLE_DIR / "video-script.json", workspace / "video-script.json"):
        created.append("video-script.json")
    for directory in (workspace / "media", workspace / "output"):
        if not directory.exists():
            directory.mkdir(parents=True)
            created.append(directory.name + "/")
    draft = "# 内容草稿\n\n在这里粘贴待评分的文章、短视频脚本或 GEO 回答。\n"
    if write_if_missing(workspace / "draft.md", draft):
        created.append("draft.md")
    agent_task = f"""# Agent task

1. Read `{ROOT / 'AGENTS.md'}`.
2. Replace synthetic fields in `enterprise-profile.json` with verified company facts, then set `template_data` to `false`.
3. Generate GEO tasks into `output/geo-tasks.json`.
4. Read `draft.md`, use `score-enterprise-content`, and write `score-evaluation.json`.
5. Put authorized local media in `media/`. Run video mode `auto`; use `talking-head` for one spoken source or `material-assembly` for a script plus multiple assets.
6. For sentence-safe talking-head cleanup, add a reviewed timestamped `transcript.reviewed.json`. Without it, accept only a silence-based preview.
7. Do not upload media or publish content automatically.

Run deterministic stages with:

```bash
python3 {ROOT / 'content_growth.py'} run {workspace}
python3 {ROOT / 'content_growth.py'} video {workspace} --mode auto
```
"""
    if write_if_missing(workspace / "AGENT_TASK.md", agent_task):
        created.append("AGENT_TASK.md")
    print(
        json.dumps(
            {
                "workspace": str(workspace),
                "created": created,
                "overwrite_policy": "never overwrite existing files",
                "warning": "enterprise-profile.json contains synthetic example data; replace it before real use",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def has_media(media: Path) -> bool:
    extensions = {".mp4", ".mov", ".m4v", ".mkv", ".webm", ".jpg", ".jpeg", ".png", ".webp"}
    return media.is_dir() and any(path.is_file() and path.suffix.lower() in extensions for path in media.rglob("*"))


def command_run(args: argparse.Namespace) -> None:
    workspace = Path(args.workspace).expanduser().resolve()
    if not workspace.is_dir():
        raise SystemExit(f"workspace does not exist: {workspace}; run init first")
    output = workspace / "output"
    output.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {"schema_version": "0.3", "mode": "workspace", "workspace": str(workspace)}
    profile = workspace / "enterprise-profile.json"
    if not profile.is_file():
        raise SystemExit("enterprise-profile.json is required")
    profile_data = json.loads(profile.read_text(encoding="utf-8"))
    if profile_data.get("template_data") is True:
        summary["geo"] = {
            "status": "blocked_template",
            "action": "Replace synthetic enterprise facts and set template_data to false",
        }
    else:
        geo_output = output / "geo-tasks.json"
        run_geo(profile, geo_output)
        summary["geo"] = {"status": "complete", "out": str(geo_output)}

    evaluation = workspace / "score-evaluation.json"
    if evaluation.is_file():
        score_output = output / "score-result.json"
        run_score(evaluation, score_output)
        summary["score"] = {"status": "complete", "out": str(score_output)}
    else:
        summary["score"] = {"status": "waiting_for_agent", "action": "Score draft.md and create score-evaluation.json"}

    media = workspace / "media"
    if args.skip_video:
        summary["video"] = {"status": "skipped", "reason": "--skip-video"}
    elif has_media(media):
        if doctor_report()["basic_video"]["ready"]:
            summary["video"] = run_workspace_video(workspace, output / "video", args.video_mode, asset_id=args.video_asset_id)
        else:
            summary["video"] = {"status": "blocked", "reason": "ffmpeg/ffprobe unavailable"}
    else:
        summary["video"] = {"status": "waiting_for_media", "action": "Add authorized media, or run with --skip-video"}
    incomplete_statuses = {"blocked", "blocked_template", "waiting_for_agent", "waiting_for_media", "needs_mode_choice"}
    summary["complete"] = not any(
        isinstance(value, dict)
        and (value.get("status") in incomplete_statuses or value.get("render_gate") == "blocked")
        for value in summary.values()
    )
    write_summary(output, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.strict and not summary["complete"]:
        raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Content Growth Agent Kit")
    subcommands = parser.add_subparsers(dest="command", required=True)

    doctor = subcommands.add_parser("doctor", help="Check required and optional capabilities")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=command_doctor)

    demo = subcommands.add_parser("demo", help="Run a synthetic end-to-end demonstration")
    demo.add_argument("--out", default="demo-output")
    demo.add_argument("--skip-video", action="store_true")
    demo.set_defaults(func=command_demo)

    init = subcommands.add_parser("init", help="Create a local project workspace without overwriting files")
    init.add_argument("workspace")
    init.set_defaults(func=command_init)

    run = subcommands.add_parser("run", help="Run every deterministic stage available in a workspace")
    run.add_argument("workspace")
    run.add_argument("--skip-video", action="store_true")
    run.add_argument("--video-mode", choices=("auto", "talking-head", "material-assembly"), default="auto")
    run.add_argument("--video-asset-id", help="Select a specific talking-head asset when multiple audio videos exist")
    run.add_argument("--strict", action="store_true", help="Exit 2 when any requested stage is incomplete")
    run.set_defaults(func=command_run)

    video = subcommands.add_parser("video", help="Recommend or run one of the two video standards")
    video.add_argument("workspace")
    video.add_argument("--mode", choices=("auto", "talking-head", "material-assembly"), default="auto")
    video.add_argument("--asset-id", help="Select a specific talking-head asset when multiple audio videos exist")
    video.add_argument("--fast-preview", action="store_true", help="Render a small preview for validation")
    video.set_defaults(func=command_video)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
