#!/usr/bin/env python3
"""Small local-only media index, EDL, and FFmpeg draft renderer."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROTOCOL = ROOT / "protocols/base-methodology.json"


def read_json(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return value


def write_json(path: str, value: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def video_protocol(path: str) -> dict[str, Any]:
    protocol = read_json(path)
    video = protocol.get("video")
    if not isinstance(video, dict) or not isinstance(video.get("render"), dict):
        raise SystemExit("protocol.video.render must be an object")
    return video


def runtime_path(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise SystemExit(f"{name} is required but was not found on PATH")
    return found


def version_line(executable: str) -> str:
    process = subprocess.run([executable, "-version"], capture_output=True, text=True, check=False)
    return (process.stdout or process.stderr).splitlines()[0] if process.returncode == 0 else "unavailable"


def check_runtime(args: argparse.Namespace) -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    result = {
        "schema_version": "0.3",
        "ready": bool(ffmpeg and ffprobe),
        "ffmpeg": {"path": ffmpeg, "version": version_line(ffmpeg) if ffmpeg else None},
        "ffprobe": {"path": ffprobe, "version": version_line(ffprobe) if ffprobe else None},
        "distribution": "user-provided runtime; this repository ships no FFmpeg binary",
        "capability_levels": video_protocol(args.protocol).get("capability_levels"),
    }
    if args.out:
        write_json(args.out, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def probe(path: Path, ffprobe: str) -> dict[str, Any]:
    process = subprocess.run(
        [
            ffprobe,
            "-v", "error",
            "-show_entries", "format=duration:stream=codec_type,width,height",
            "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        raise ValueError((process.stderr or "ffprobe failed").strip())
    data = json.loads(process.stdout)
    streams = data.get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), {})
    duration_raw = (data.get("format") or {}).get("duration")
    try:
        duration = round(float(duration_raw), 3)
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "duration": duration,
        "width": int(video.get("width") or 0),
        "height": int(video.get("height") or 0),
        "has_audio": any(item.get("codec_type") == "audio" for item in streams),
    }


def path_tags(relative: Path) -> list[str]:
    raw = " ".join([*relative.parts[:-1], relative.stem]).lower()
    tokens = [token for token in re.split(r"[_\W]+", raw, flags=re.UNICODE) if len(token) > 1]
    return list(dict.fromkeys(tokens))


def scan_assets(args: argparse.Namespace) -> None:
    ffprobe = runtime_path("ffprobe")
    media_base = Path(args.media_dir).expanduser().resolve()
    if not media_base.is_dir():
        raise SystemExit(f"media directory does not exist: {media_base}")
    assets: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for path in sorted(item for item in media_base.rglob("*") if item.is_file()):
        extension = path.suffix.lower()
        if extension not in VIDEO_EXTENSIONS | IMAGE_EXTENSIONS:
            continue
        relative = path.relative_to(media_base)
        try:
            media = probe(path, ffprobe)
        except (ValueError, json.JSONDecodeError) as error:
            skipped.append({"path": str(relative), "reason": str(error)})
            continue
        kind = "video" if extension in VIDEO_EXTENSIONS else "image"
        assets.append(
            {
                "asset_id": "asset-" + hashlib.sha1(str(relative).encode("utf-8")).hexdigest()[:10],
                "path": str(relative),
                "kind": kind,
                **media,
                "tags": path_tags(relative),
            }
        )
    result = {
        "schema_version": "0.1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "media_base": str(media_base),
        "assets": assets,
        "skipped": skipped,
    }
    write_json(args.out, result)
    print(json.dumps({"out": args.out, "assets": len(assets), "skipped": len(skipped)}, ensure_ascii=False))


def recommend_mode(args: argparse.Namespace) -> None:
    index = read_json(args.assets)
    assets = index.get("assets") or []
    videos = [asset for asset in assets if asset.get("kind") == "video"]
    audio_videos = [asset for asset in videos if asset.get("has_audio")]
    talk_tags = {"talking", "head", "talk", "voice", "speaker", "口播", "老板", "达人", "讲解"}
    tagged_talk = [asset for asset in audio_videos if talk_tags & {str(tag).lower() for tag in asset.get("tags") or []}]
    script_exists = bool(args.script and Path(args.script).is_file())
    reasons: list[str] = []
    if len(assets) == 1 and len(audio_videos) == 1:
        mode = "talking_head_cleanup"
        confidence = 0.94
        reasons.append("Only one local video is present and it has an audio track.")
    elif tagged_talk and len(assets) <= 2:
        mode = "talking_head_cleanup"
        confidence = 0.86
        reasons.append("An audio video is tagged as a talking-head source and there are few cutaway assets.")
    elif script_exists and len(assets) >= 2:
        mode = "scripted_asset_assembly"
        confidence = 0.92
        reasons.append("A structured video script and multiple local assets are available.")
    elif len(assets) >= 3:
        mode = None
        confidence = 0.55
        reasons.append("Multiple assets are present, but no structured script proves that material assembly is intended.")
    else:
        mode = None
        confidence = 0.35
        reasons.append("The media set is ambiguous; ask the user to choose a mode.")
    result = {
        "schema_version": "0.3",
        "recommended_mode": mode,
        "confidence": confidence,
        "reasons": reasons,
        "inventory": {
            "assets": len(assets),
            "videos": len(videos),
            "audio_videos": len(audio_videos),
            "script": script_exists,
            "audio_video_candidates": [
                {"asset_id": asset.get("asset_id"), "path": asset.get("path"), "duration": asset.get("duration")}
                for asset in audio_videos
            ],
        },
        "requires_user_choice": mode is None or confidence < 0.7,
    }
    if args.out:
        write_json(args.out, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def detect_silence(args: argparse.Namespace) -> None:
    ffmpeg = runtime_path("ffmpeg")
    ffprobe = runtime_path("ffprobe")
    source = Path(args.input).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"talking-head input does not exist: {source}")
    media = probe(source, ffprobe)
    if not media.get("has_audio"):
        raise SystemExit("talking-head input must have an audio track")
    command = [
        ffmpeg,
        "-hide_banner",
        "-i", str(source),
        "-af", f"silencedetect=noise={args.threshold}:d={args.min_duration}",
        "-f", "null",
        "-",
    ]
    process = subprocess.run(command, capture_output=True, text=True, check=False)
    if process.returncode != 0:
        raise SystemExit((process.stderr or "ffmpeg silencedetect failed").strip())
    intervals: list[dict[str, float]] = []
    pending_start: Optional[float] = None
    for line in process.stderr.splitlines():
        start_match = re.search(r"silence_start:\s*([0-9.]+)", line)
        if start_match:
            pending_start = float(start_match.group(1))
        end_match = re.search(r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)", line)
        if end_match:
            end = float(end_match.group(1))
            duration = float(end_match.group(2))
            start = pending_start if pending_start is not None else max(0.0, end - duration)
            intervals.append({"start": round(start, 3), "end": round(end, 3), "duration": round(duration, 3)})
            pending_start = None
    media_duration = float(media.get("duration") or 0)
    if pending_start is not None and media_duration > pending_start:
        intervals.append({"start": round(pending_start, 3), "end": round(media_duration, 3), "duration": round(media_duration - pending_start, 3)})
    result = {
        "schema_version": "0.3",
        "mode": "talking_head_cleanup",
        "source": str(source),
        "source_duration": media_duration,
        "threshold": args.threshold,
        "min_duration": args.min_duration,
        "silences": intervals,
        "total_silence_duration": round(sum(item["duration"] for item in intervals), 3),
        "semantic_safety": "unverified",
        "formal_gate": "preview_only",
        "human_review_required": True,
    }
    write_json(args.out, result)
    print(json.dumps({"out": args.out, "silences": len(intervals), "total_silence_duration": result["total_silence_duration"]}, ensure_ascii=False))


def choose_talking_head_asset(assets: list[dict[str, Any]], asset_id: Optional[str]) -> dict[str, Any]:
    if asset_id:
        selected = next((asset for asset in assets if str(asset.get("asset_id")) == asset_id), None)
        if not selected:
            raise SystemExit(f"talking-head asset not found: {asset_id}")
    else:
        selected = next((asset for asset in assets if asset.get("kind") == "video" and asset.get("has_audio")), None)
    if not selected or selected.get("kind") != "video" or not selected.get("has_audio"):
        raise SystemExit("talking-head mode requires a local video with audio")
    return selected


def transcript_spans(transcript: dict[str, Any], source_duration: float, pre_roll: float, post_roll: float) -> tuple[list[dict[str, Any]], str]:
    raw_segments = transcript.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise SystemExit("transcript.segments must be a non-empty array")
    spans: list[dict[str, Any]] = []
    for index, segment in enumerate(raw_segments, start=1):
        if not isinstance(segment, dict) or segment.get("keep") is False or str(segment.get("action") or "").lower() in {"delete", "skip"}:
            continue
        start = max(0.0, float(segment.get("start") or 0) - pre_roll)
        end = min(source_duration, float(segment.get("end") or start) + post_roll)
        if spans and start < float(spans[-1]["end"]):
            start = float(spans[-1]["end"])
        if end - start < 0.2:
            continue
        spans.append({"start": start, "end": end, "caption": str(segment.get("text") or ""), "segment_id": segment.get("id") or f"sentence-{index:03d}"})
    if not spans:
        raise SystemExit("no transcript segments survived the keep/delete gate")
    safety = "transcript_reviewed" if transcript.get("reviewed") is True else "transcript_unreviewed"
    return spans, safety


def silence_keep_spans(report: dict[str, Any], source_duration: float, padding: float, min_clip: float) -> list[dict[str, Any]]:
    spans: list[dict[str, Any]] = []
    cursor = 0.0
    for index, silence in enumerate(report.get("silences") or [], start=1):
        silence_start = max(cursor, float(silence.get("start") or 0))
        silence_end = min(source_duration, float(silence.get("end") or silence_start))
        keep_end = min(source_duration, silence_start + padding)
        if keep_end - cursor >= min_clip:
            spans.append({"start": cursor, "end": keep_end, "caption": "", "segment_id": f"speech-{len(spans) + 1:03d}"})
        cursor = max(cursor, silence_end - padding)
    if source_duration - cursor >= min_clip:
        spans.append({"start": cursor, "end": source_duration, "caption": "", "segment_id": f"speech-{len(spans) + 1:03d}"})
    if not spans and source_duration > 0:
        spans.append({"start": 0.0, "end": source_duration, "caption": "", "segment_id": "speech-001"})
    return spans


def make_talking_head_edl(args: argparse.Namespace) -> None:
    index = read_json(args.assets)
    assets = index.get("assets") or []
    source = choose_talking_head_asset(assets, args.asset_id)
    source_duration = float(source.get("duration") or 0)
    if source_duration <= 0:
        raise SystemExit("talking-head source duration is unavailable")
    if args.transcript:
        transcript = read_json(args.transcript)
        transcript_asset_id = transcript.get("source_asset_id")
        if transcript_asset_id and str(transcript_asset_id) != str(source.get("asset_id")):
            raise SystemExit("transcript.source_asset_id does not match the selected talking-head asset")
        spans, semantic_safety = transcript_spans(transcript, source_duration, args.pre_roll, args.post_roll)
        mode_variant = "transcript_driven"
    elif args.silence_report:
        report = read_json(args.silence_report)
        report_source = report.get("source")
        media_base = Path(str(index.get("media_base") or "")).expanduser().resolve()
        selected_source = safe_media_path(media_base, str(source.get("path") or ""))
        if report_source and Path(str(report_source)).expanduser().resolve() != selected_source:
            raise SystemExit("silence report source does not match the selected talking-head asset")
        spans = silence_keep_spans(report, source_duration, args.silence_padding, args.min_clip)
        semantic_safety = "silence_only_unverified"
        mode_variant = "silence_only_conservative"
    else:
        raise SystemExit("provide --transcript or --silence-report")

    clips: list[dict[str, Any]] = []
    joins: list[dict[str, Any]] = []
    for sequence, span in enumerate(spans, start=1):
        start = round(float(span["start"]), 3)
        end = round(float(span["end"]), 3)
        clips.append(
            {
                "clip_id": f"voice-{sequence:03d}",
                "segment_id": span["segment_id"],
                "role": "talking_head",
                "caption": span.get("caption", ""),
                "requested_tags": ["talking-head"],
                "duration": round(end - start, 3),
                "source_start": start,
                "source_end": end,
                "status": "matched",
                "asset_id": source["asset_id"],
                "path": source["path"],
                "reason": "Reviewed transcript boundary" if args.transcript else "Conservative FFmpeg silence boundary; semantic continuity is unverified",
            }
        )
        if sequence > 1:
            previous = clips[-2]
            joins.append(
                {
                    "previous_clip_id": previous["clip_id"],
                    "current_clip_id": clips[-1]["clip_id"],
                    "removed_gap_sec": round(start - float(previous["source_end"]), 3),
                    "status": "manual_check",
                }
            )
    protocol = read_json(args.protocol)
    formal_gate = "ready_for_human_review" if semantic_safety == "transcript_reviewed" else "preview_only"
    result = {
        "schema_version": "0.3",
        "protocol_id": protocol.get("protocol_id"),
        "edl_id": f"edl-{source['asset_id']}-talking-head",
        "edit_mode": "talking_head_cleanup",
        "mode_variant": mode_variant,
        "semantic_safety": semantic_safety,
        "formal_gate": formal_gate,
        "publication_gate": "blocked_pending_human_review",
        "media_base": index.get("media_base"),
        "clips": clips,
        "missing": [],
        "join_review": joins,
        "render_gate": "ready",
        "end_fade_duration": 1.0,
        "human_review_required": True,
        "review_checks": ["No sentence is cut in half", "No final syllable is swallowed", "Removed pauses do not change meaning", "Claims and captions are accurate"],
    }
    write_json(args.out, result)
    print(json.dumps({"out": args.out, "clips": len(clips), "mode_variant": mode_variant, "formal_gate": formal_gate}, ensure_ascii=False))


def validate_script(script: dict[str, Any]) -> list[dict[str, Any]]:
    segments = script.get("segments")
    if not isinstance(segments, list) or not segments:
        raise SystemExit("script.segments must be a non-empty array")
    normalized: list[dict[str, Any]] = []
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict):
            raise SystemExit(f"segment {index} must be an object")
        duration = segment.get("duration")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration <= 0:
            raise SystemExit(f"segment {index}.duration must be positive")
        normalized.append(segment)
    return normalized


def asset_score(asset: dict[str, Any], requested: set[str], use_count: Counter[str]) -> float:
    available = {str(tag).lower() for tag in asset.get("tags") or []}
    overlap = len(requested & available)
    return overlap * 20 - use_count[str(asset.get("asset_id"))] * 5


def make_edl(args: argparse.Namespace) -> None:
    script = read_json(args.script)
    index = read_json(args.assets)
    protocol = read_json(args.protocol)
    segments = validate_script(script)
    assets = index.get("assets")
    if not isinstance(assets, list) or not assets:
        raise SystemExit("asset index contains no assets")
    use_count: Counter[str] = Counter()
    clips: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []

    for sequence, segment in enumerate(segments, start=1):
        requested = {str(tag).lower() for tag in (segment.get("asset_tags") or []) if str(tag).strip()}
        role = str(segment.get("role") or "").lower().strip()
        if role:
            requested.add(role)
        ranked = sorted(assets, key=lambda item: asset_score(item, requested, use_count), reverse=True)
        selected = ranked[0] if ranked and (asset_score(ranked[0], requested, use_count) > 0 or args.allow_fallback) else None
        requested_duration = float(segment["duration"])
        clip = {
            "clip_id": f"clip-{sequence:03d}",
            "segment_id": segment.get("id") or f"segment-{sequence:03d}",
            "role": role or "scene",
            "caption": str(segment.get("text") or ""),
            "requested_tags": sorted(requested),
            "duration": round(requested_duration, 3),
        }
        if selected:
            source_duration = float(selected.get("duration") or 0)
            if selected.get("kind") == "video" and source_duration > 0:
                clip["duration"] = round(min(requested_duration, source_duration), 3)
            clip.update({"status": "matched", "asset_id": selected["asset_id"], "path": selected["path"]})
            use_count[str(selected["asset_id"])] += 1
        else:
            clip.update({"status": "missing", "asset_id": None, "path": None})
            missing.append({"segment_id": clip["segment_id"], "requested_tags": sorted(requested), "caption": clip["caption"]})
        clips.append(clip)

    result = {
        "schema_version": "0.3",
        "protocol_id": protocol.get("protocol_id"),
        "edl_id": f"edl-{script.get('script_id') or 'draft'}",
        "edit_mode": "scripted_asset_assembly",
        "mode_variant": "tag_matched_basic",
        "semantic_safety": "script_and_tag_match_only",
        "formal_gate": "draft_requires_human_review",
        "publication_gate": "blocked_pending_human_review",
        "script_id": script.get("script_id"),
        "aspect_ratio": script.get("aspect_ratio", "9:16"),
        "media_base": index.get("media_base"),
        "clips": clips,
        "missing": missing,
        "render_gate": "blocked" if missing else "ready",
        "human_review_required": True,
    }
    write_json(args.out, result)
    print(json.dumps({"out": args.out, "clips": len(clips), "missing": len(missing), "render_gate": result["render_gate"]}, ensure_ascii=False))


def safe_media_path(base: Path, relative: str) -> Path:
    candidate = (base / relative).resolve()
    try:
        candidate.relative_to(base)
    except ValueError as error:
        raise SystemExit(f"asset path escapes media base: {relative}") from error
    if not candidate.is_file():
        raise SystemExit(f"asset does not exist: {candidate}")
    return candidate


def render_edl(args: argparse.Namespace) -> None:
    ffmpeg = runtime_path("ffmpeg")
    edl = read_json(args.edl)
    index = read_json(args.assets)
    clips = edl.get("clips") or []
    missing = [clip for clip in clips if clip.get("status") != "matched" or not clip.get("asset_id")]
    if not clips:
        raise SystemExit("EDL contains no clips")
    if missing:
        raise SystemExit(f"render blocked: {len(missing)} clip(s) are missing assets")
    indexed = {str(asset.get("asset_id")): asset for asset in index.get("assets") or []}
    media_base_raw = args.media_base or edl.get("media_base") or index.get("media_base")
    if not media_base_raw:
        raise SystemExit("media base is required")
    media_base = Path(media_base_raw).expanduser().resolve()
    render_config = video_protocol(args.protocol)["render"]
    width = args.width or int(render_config.get("width", 1080))
    height = args.height or int(render_config.get("height", 1920))
    fps = int(render_config.get("fps", 30))
    video_codec = str(render_config.get("video_codec", "libx264"))
    audio_codec = str(render_config.get("audio_codec", "aac"))

    command = [ffmpeg, "-y"]
    filters: list[str] = []
    total_duration = 0.0
    for position, clip in enumerate(clips):
        asset = indexed.get(str(clip["asset_id"]))
        if not asset:
            raise SystemExit(f"asset not found in index: {clip['asset_id']}")
        duration = float(clip.get("duration") or 0)
        source_start = max(0.0, float(clip.get("source_start") or 0))
        if duration <= 0:
            raise SystemExit(f"invalid clip duration: {clip.get('clip_id')}")
        path = safe_media_path(media_base, str(asset["path"]))
        if asset.get("kind") == "image":
            command.extend(["-loop", "1", "-framerate", str(fps), "-t", str(duration), "-i", str(path)])
        else:
            command.extend(["-ss", str(source_start), "-t", str(duration), "-i", str(path)])
        total_duration += duration
        filters.append(
            f"[{position}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps={fps},trim=duration={duration},setpts=PTS-STARTPTS[v{position}]"
        )
        if asset.get("kind") == "video" and asset.get("has_audio"):
            filters.append(
                f"[{position}:a]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo,"
                f"atrim=duration={duration},asetpts=PTS-STARTPTS[a{position}]"
            )
        else:
            filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={duration},asetpts=PTS-STARTPTS[a{position}]")

    concat_inputs = "".join(f"[v{position}][a{position}]" for position in range(len(clips)))
    end_fade_duration = min(max(0.0, float(edl.get("end_fade_duration") or 0)), max(0.0, total_duration / 2))
    concat_video_label = "vconcat" if end_fade_duration > 0 else "vout"
    filters.append(f"{concat_inputs}concat=n={len(clips)}:v=1:a=1[{concat_video_label}][aout]")
    if end_fade_duration > 0:
        fade_start = max(0.0, total_duration - end_fade_duration)
        filters.append(f"[vconcat]fade=t=out:st={fade_start}:d={end_fade_duration}:color=black[vout]")
    output = Path(args.out).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    command.extend(
        [
            "-filter_complex", ";".join(filters),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", video_codec, "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", audio_codec, "-b:a", "128k", "-movflags", "+faststart",
            str(output),
        ]
    )
    if args.dry_run:
        print(json.dumps({"command": command}, ensure_ascii=False, indent=2))
        return
    process = subprocess.run(command, check=False)
    if process.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
        raise SystemExit(f"ffmpeg render failed with exit code {process.returncode}")
    print(json.dumps({"out": str(output), "bytes": output.stat().st_size, "clips": len(clips), "edit_mode": edl.get("edit_mode")}, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local-only agent video draft tools")
    subcommands = parser.add_subparsers(dest="command", required=True)

    runtime = subcommands.add_parser("check-runtime")
    runtime.add_argument("--out")
    runtime.add_argument("--protocol", default=str(DEFAULT_PROTOCOL))
    runtime.set_defaults(func=check_runtime)

    scan = subcommands.add_parser("scan-assets")
    scan.add_argument("--media-dir", required=True)
    scan.add_argument("--out", required=True)
    scan.set_defaults(func=scan_assets)

    recommend = subcommands.add_parser("recommend-mode")
    recommend.add_argument("--assets", required=True)
    recommend.add_argument("--script")
    recommend.add_argument("--out")
    recommend.set_defaults(func=recommend_mode)

    silence = subcommands.add_parser("detect-silence")
    silence.add_argument("--input", required=True)
    silence.add_argument("--out", required=True)
    silence.add_argument("--threshold", default="-35dB")
    silence.add_argument("--min-duration", type=float, default=0.8)
    silence.set_defaults(func=detect_silence)

    talking = subcommands.add_parser("make-talking-head-edl")
    talking.add_argument("--assets", required=True)
    talking.add_argument("--out", required=True)
    talking.add_argument("--asset-id")
    talking.add_argument("--transcript")
    talking.add_argument("--silence-report")
    talking.add_argument("--pre-roll", type=float, default=0.05)
    talking.add_argument("--post-roll", type=float, default=0.08)
    talking.add_argument("--silence-padding", type=float, default=0.12)
    talking.add_argument("--min-clip", type=float, default=0.35)
    talking.add_argument("--protocol", default=str(DEFAULT_PROTOCOL))
    talking.set_defaults(func=make_talking_head_edl)

    edl = subcommands.add_parser("make-edl")
    edl.add_argument("--script", required=True)
    edl.add_argument("--assets", required=True)
    edl.add_argument("--out", required=True)
    edl.add_argument("--allow-fallback", action="store_true")
    edl.add_argument("--protocol", default=str(DEFAULT_PROTOCOL))
    edl.set_defaults(func=make_edl)

    render = subcommands.add_parser("render-edl")
    render.add_argument("--edl", required=True)
    render.add_argument("--assets", required=True)
    render.add_argument("--out", required=True)
    render.add_argument("--media-base")
    render.add_argument("--width", type=int)
    render.add_argument("--height", type=int)
    render.add_argument("--protocol", default=str(DEFAULT_PROTOCOL))
    render.add_argument("--dry-run", action="store_true")
    render.set_defaults(func=render_edl)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
