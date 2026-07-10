#!/usr/bin/env python3
"""Small local-only media index, EDL, and FFmpeg draft renderer."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PROTOCOL = ROOT / "protocols/base-methodology.json"
FILLER_REVIEW_PATTERNS = [
    ("hesitation", re.compile(r"嗯+"), 0.85, "Hesitation sound; verify against audio before removing."),
    ("hesitation", re.compile(r"(?:呃|额)+"), 0.85, "Hesitation sound; verify against audio before removing."),
    ("repetition", re.compile(r"((?:然后|然後))\1+"), 0.92, "Adjacent repeated connector."),
    ("repetition", re.compile(r"(就是)\1+"), 0.9, "Adjacent repeated phrase."),
    ("repetition", re.compile(r"((?:那个|那個))\1+"), 0.9, "Adjacent repeated phrase."),
    ("repetition", re.compile(r"(所以)\1+"), 0.88, "Adjacent repeated connector."),
    ("repetition", re.compile(r"(但是)\1+"), 0.88, "Adjacent repeated connector."),
]


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


def ffmpeg_filter_available(ffmpeg: str, filter_name: str) -> bool:
    process = subprocess.run([ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True, check=False)
    if process.returncode != 0:
        return False
    pattern = re.compile(rf"^\s*[.A-Z|]+\s+{re.escape(filter_name)}\s", re.MULTILINE)
    return bool(pattern.search(process.stdout))


def transcription_provider() -> Optional[dict[str, str]]:
    whisper = shutil.which("whisper")
    if whisper:
        return {"name": "openai-whisper-cli", "command": whisper}
    return None


def version_line(executable: str) -> str:
    process = subprocess.run([executable, "-version"], capture_output=True, text=True, check=False)
    return (process.stdout or process.stderr).splitlines()[0] if process.returncode == 0 else "unavailable"


def check_runtime(args: argparse.Namespace) -> None:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    provider = transcription_provider()
    result = {
        "schema_version": "0.4",
        "ready": bool(ffmpeg and ffprobe),
        "ffmpeg": {"path": ffmpeg, "version": version_line(ffmpeg) if ffmpeg else None},
        "ffprobe": {"path": ffprobe, "version": version_line(ffprobe) if ffprobe else None},
        "distribution": "user-provided runtime; this repository ships no FFmpeg binary",
        "capability_levels": video_protocol(args.protocol).get("capability_levels"),
        "transcription": {
            "ready": provider is not None,
            "provider": provider,
            "local_only": True,
            "source_upload": False,
        },
        "captions": {
            "sidecar_srt": True,
            "burn_in": bool(ffmpeg and ffmpeg_filter_available(ffmpeg, "subtitles")),
            "required_filter": "subtitles (libass)",
        },
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
        "schema_version": "0.4",
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
        "schema_version": "0.4",
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


def normalize_whisper_transcript(raw: dict[str, Any], source: Path, provider: dict[str, str], args: argparse.Namespace) -> dict[str, Any]:
    raw_segments = raw.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise SystemExit("local Whisper returned no timestamped segments")
    segments: list[dict[str, Any]] = []
    for position, segment in enumerate(raw_segments, start=1):
        if not isinstance(segment, dict):
            continue
        start = float(segment.get("start") or 0)
        end = float(segment.get("end") or start)
        text = str(segment.get("text") or "").strip()
        if end <= start or not text:
            continue
        segments.append(
            {
                "id": f"auto-{position:04d}",
                "start": round(start, 3),
                "end": round(end, 3),
                "text": text,
                "action": "review",
            }
        )
    if not segments:
        raise SystemExit("local Whisper returned no usable timestamped speech")
    result: dict[str, Any] = {
        "schema_version": "0.4",
        "reviewed": False,
        "language": str(raw.get("language") or args.language or "unknown"),
        "provider": provider["name"],
        "model": args.model,
        "source": str(source),
        "source_upload": False,
        "review_gate": "needs_human_review",
        "segments": segments,
    }
    if args.source_asset_id:
        result["source_asset_id"] = args.source_asset_id
    add_filler_review(result)
    return result


def add_filler_review(transcript: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for segment in transcript.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text") or "")
        if not text:
            continue
        segment_start = float(segment.get("start") or 0)
        segment_end = float(segment.get("end") or segment_start)
        segment_duration = max(0.0, segment_end - segment_start)
        for kind, pattern, confidence, reason in FILLER_REVIEW_PATTERNS:
            for match in pattern.finditer(text):
                estimated_start = segment_start + segment_duration * match.start() / len(text)
                estimated_end = segment_start + segment_duration * match.end() / len(text)
                candidates.append(
                    {
                        "candidate_id": f"candidate-{len(candidates) + 1:03d}",
                        "segment_id": segment.get("id"),
                        "kind": kind,
                        "phrase": match.group(0),
                        "confidence": confidence,
                        "estimated_start": round(estimated_start, 3),
                        "estimated_end": round(estimated_end, 3),
                        "timestamp_precision": "estimated_from_segment",
                        "reason": reason,
                        "suggested_action": "human_review",
                    }
                )
    transcript["filler_review"] = {
        "candidates": candidates,
        "candidate_count": len(candidates),
        "automatic_deletion": False,
        "gate": "human_decision_required",
        "limitations": [
            "A transcription model may omit spoken fillers.",
            "Segment-level timestamps do not prove exact filler boundaries.",
            "Discourse markers can carry meaning and must not be deleted blindly.",
        ],
    }
    return candidates


def analyze_transcript(args: argparse.Namespace) -> None:
    transcript = read_json(args.input)
    candidates = add_filler_review(transcript)
    write_json(args.out, transcript)
    print(
        json.dumps(
            {
                "out": args.out,
                "candidate_count": len(candidates),
                "automatic_deletion": False,
                "gate": "human_decision_required",
            },
            ensure_ascii=False,
        )
    )


def transcribe_local(args: argparse.Namespace) -> None:
    source = Path(args.input).expanduser().resolve()
    if not source.is_file():
        raise SystemExit(f"transcription input does not exist: {source}")
    provider = transcription_provider()
    if args.provider != "auto" and args.provider != "openai-whisper-cli":
        raise SystemExit(f"unsupported local transcription provider: {args.provider}")
    if not provider:
        raise SystemExit(
            "local transcription is unavailable: install OpenAI Whisper so the `whisper` command is on PATH; "
            "the toolkit will not upload media or install it automatically"
        )
    output = Path(args.out).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="content-growth-whisper-", dir=str(output.parent)) as temp_raw:
        temp_dir = Path(temp_raw)
        command = [
            provider["command"],
            str(source),
            "--model", args.model,
            "--task", "transcribe",
            "--output_format", "json",
            "--output_dir", str(temp_dir),
            "--verbose", "False",
        ]
        if args.language and args.language.lower() != "auto":
            command.extend(["--language", args.language])
        process = subprocess.run(command, capture_output=True, text=True, check=False)
        if process.returncode != 0:
            detail = (process.stderr or process.stdout or "local Whisper failed").strip()
            raise SystemExit(detail)
        candidates = sorted(temp_dir.glob("*.json"))
        if not candidates:
            raise SystemExit("local Whisper completed but did not create JSON output")
        raw = read_json(str(candidates[0]))
    result = normalize_whisper_transcript(raw, source, provider, args)
    write_json(str(output), result)
    print(
        json.dumps(
            {
                "out": str(output),
                "provider": provider["name"],
                "segments": len(result["segments"]),
                "filler_candidates": result["filler_review"]["candidate_count"],
                "review_gate": result["review_gate"],
                "source_upload": False,
            },
            ensure_ascii=False,
        )
    )


def split_caption_text(text: str, max_chars: int) -> list[str]:
    normalized = " ".join(text.strip().split())
    if not normalized:
        return []
    if " " in normalized:
        chunks: list[str] = []
        current: list[str] = []
        for word in normalized.split(" "):
            candidate = " ".join([*current, word])
            if current and len(candidate) > max_chars:
                chunks.append(" ".join(current))
                current = [word]
            else:
                current.append(word)
        if current:
            chunks.append(" ".join(current))
        return chunks
    chunks = []
    current = ""
    punctuation = set("，。！？；：、,.!?;:")
    for character in normalized:
        current += character
        if len(current) >= max_chars or (character in punctuation and len(current) >= max(4, max_chars // 2)):
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    return chunks


def srt_timestamp(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def make_srt(args: argparse.Namespace) -> None:
    if args.max_chars < 4:
        raise SystemExit("--max-chars must be at least 4")
    edl = read_json(args.edl)
    entries: list[str] = []
    timeline = 0.0
    sequence = 1
    for clip in edl.get("clips") or []:
        duration = max(0.0, float(clip.get("duration") or 0))
        caption = str(clip.get("caption") or "").strip()
        chunks = split_caption_text(caption, args.max_chars)
        if chunks and duration > 0:
            chunk_duration = duration / len(chunks)
            for position, chunk in enumerate(chunks):
                start = timeline + position * chunk_duration
                end = timeline + (position + 1) * chunk_duration
                entries.extend([str(sequence), f"{srt_timestamp(start)} --> {srt_timestamp(end)}", chunk, ""])
                sequence += 1
        timeline += duration
    output = Path(args.out).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(entries), encoding="utf-8")
    print(json.dumps({"out": str(output), "entries": sequence - 1, "timeline_duration": round(timeline, 3)}, ensure_ascii=False))


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
        "schema_version": "0.4",
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
        "schema_version": "0.4",
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


def escape_subtitles_path(path: Path) -> str:
    value = str(path).replace("\\", "/")
    return value.replace(":", "\\:").replace("'", "\\'")


def caption_force_style(render_config: dict[str, Any], profile_name: str) -> str:
    profiles = render_config.get("caption_styles") or {}
    profile = profiles.get(profile_name)
    if not isinstance(profile, dict) or not profile:
        raise SystemExit(f"caption style profile not found in protocol: {profile_name}")
    allowed = {"FontName", "FontSize", "PrimaryColour", "OutlineColour", "BorderStyle", "Outline", "Shadow", "Alignment", "MarginV"}
    return ",".join(f"{key}={value}" for key, value in profile.items() if key in allowed)


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
    caption_style = args.caption_style or str(render_config.get("default_caption_style") or "clean")
    captions_path = Path(args.captions_srt).expanduser().resolve() if args.captions_srt else None
    if captions_path and not captions_path.is_file():
        raise SystemExit(f"caption file does not exist: {captions_path}")
    burn_in_available = ffmpeg_filter_available(ffmpeg, "subtitles")
    if captions_path and args.caption_mode == "burn" and not burn_in_available:
        raise SystemExit("caption burn-in requires an FFmpeg build with the subtitles/libass filter")
    burn_captions = bool(captions_path and (args.caption_mode == "burn" or (args.caption_mode == "auto" and burn_in_available)))
    caption_delivery = "burned_in" if burn_captions else ("sidecar_srt" if captions_path else "none")

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
    filters.append(f"{concat_inputs}concat=n={len(clips)}:v=1:a=1[vbase][aout]")
    current_video_label = "vbase"
    if end_fade_duration > 0:
        fade_start = max(0.0, total_duration - end_fade_duration)
        filters.append(f"[{current_video_label}]fade=t=out:st={fade_start}:d={end_fade_duration}:color=black[vfade]")
        current_video_label = "vfade"
    if burn_captions and captions_path:
        subtitle_path = escape_subtitles_path(captions_path)
        style = caption_force_style(render_config, caption_style)
        filters.append(f"[{current_video_label}]subtitles=filename='{subtitle_path}':force_style='{style}'[vout]")
    else:
        filters.append(f"[{current_video_label}]null[vout]")
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
    print(
        json.dumps(
            {
                "out": str(output),
                "bytes": output.stat().st_size,
                "clips": len(clips),
                "edit_mode": edl.get("edit_mode"),
                "caption_delivery": caption_delivery,
                "captions": str(captions_path) if captions_path else None,
                "caption_style": caption_style,
                "caption_style_applied": burn_captions,
            },
            ensure_ascii=False,
        )
    )


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

    transcribe = subcommands.add_parser("transcribe-local")
    transcribe.add_argument("--input", required=True)
    transcribe.add_argument("--out", required=True)
    transcribe.add_argument("--provider", choices=("auto", "openai-whisper-cli"), default="auto")
    transcribe.add_argument("--model", default="small")
    transcribe.add_argument("--language", default="zh")
    transcribe.add_argument("--source-asset-id")
    transcribe.set_defaults(func=transcribe_local)

    review_transcript = subcommands.add_parser("analyze-transcript")
    review_transcript.add_argument("--input", required=True)
    review_transcript.add_argument("--out", required=True)
    review_transcript.set_defaults(func=analyze_transcript)

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

    captions = subcommands.add_parser("make-srt")
    captions.add_argument("--edl", required=True)
    captions.add_argument("--out", required=True)
    captions.add_argument("--max-chars", type=int, default=16)
    captions.set_defaults(func=make_srt)

    render = subcommands.add_parser("render-edl")
    render.add_argument("--edl", required=True)
    render.add_argument("--assets", required=True)
    render.add_argument("--out", required=True)
    render.add_argument("--media-base")
    render.add_argument("--width", type=int)
    render.add_argument("--height", type=int)
    render.add_argument("--captions-srt")
    render.add_argument("--caption-mode", choices=("auto", "sidecar", "burn"), default="auto")
    render.add_argument("--caption-style", choices=("clean", "bold_b2b"))
    render.add_argument("--protocol", default=str(DEFAULT_PROTOCOL))
    render.add_argument("--dry-run", action="store_true")
    render.set_defaults(func=render_edl)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
