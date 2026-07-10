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
from typing import Any


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
        "schema_version": "0.1",
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
        "schema_version": "0.1",
        "protocol_id": protocol.get("protocol_id"),
        "edl_id": f"edl-{script.get('script_id') or 'draft'}",
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
    for position, clip in enumerate(clips):
        asset = indexed.get(str(clip["asset_id"]))
        if not asset:
            raise SystemExit(f"asset not found in index: {clip['asset_id']}")
        duration = float(clip.get("duration") or 0)
        if duration <= 0:
            raise SystemExit(f"invalid clip duration: {clip.get('clip_id')}")
        path = safe_media_path(media_base, str(asset["path"]))
        if asset.get("kind") == "image":
            command.extend(["-loop", "1", "-framerate", str(fps), "-t", str(duration), "-i", str(path)])
        else:
            command.extend(["-ss", "0", "-t", str(duration), "-i", str(path)])
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
    filters.append(f"{concat_inputs}concat=n={len(clips)}:v=1:a=1[vout][aout]")
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
    print(json.dumps({"out": str(output), "bytes": output.stat().st_size, "clips": len(clips)}, ensure_ascii=False))


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
