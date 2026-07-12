#!/usr/bin/env python3
"""Small local-only media index, EDL, and FFmpeg draft renderer."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
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


def pillow_available() -> bool:
    return importlib.util.find_spec("PIL") is not None


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
        "schema_version": "0.5",
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
            "png_overlay": bool(ffmpeg and ffmpeg_filter_available(ffmpeg, "overlay") and pillow_available()),
            "required_filter": "subtitles (libass)",
        },
    }
    if args.out:
        write_json(args.out, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def display_dimensions(video: dict[str, Any]) -> tuple[int, int, int]:
    encoded_width = int(video.get("width") or 0)
    encoded_height = int(video.get("height") or 0)
    rotation = 0
    for side_data in video.get("side_data_list") or []:
        if not isinstance(side_data, dict) or side_data.get("rotation") is None:
            continue
        try:
            rotation = int(round(float(side_data["rotation"])))
        except (TypeError, ValueError):
            rotation = 0
        break
    if rotation % 360 in {90, 270}:
        return encoded_height, encoded_width, rotation
    return encoded_width, encoded_height, rotation


def probe(path: Path, ffprobe: str) -> dict[str, Any]:
    process = subprocess.run(
        [
            ffprobe,
            "-v", "error",
            "-show_entries", "format=duration:stream=codec_type,width,height:stream_side_data=rotation",
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
    encoded_width = int(video.get("width") or 0)
    encoded_height = int(video.get("height") or 0)
    width, height, rotation = display_dimensions(video)
    duration_raw = (data.get("format") or {}).get("duration")
    try:
        duration = round(float(duration_raw), 3)
    except (TypeError, ValueError):
        duration = 0.0
    return {
        "duration": duration,
        "width": width,
        "height": height,
        "encoded_width": encoded_width,
        "encoded_height": encoded_height,
        "rotation": rotation,
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
        "schema_version": "0.2",
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
        "schema_version": "0.5",
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
        "schema_version": "0.5",
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
        if end - start < 0.2 or not text:
            continue
        normalized_segment: dict[str, Any] = {
            "id": f"auto-{position:04d}",
            "start": round(start, 3),
            "end": round(end, 3),
            "text": text,
            "action": "review",
        }
        words: list[dict[str, Any]] = []
        for word in segment.get("words") or []:
            if not isinstance(word, dict):
                continue
            word_start = float(word.get("start") or 0)
            word_end = float(word.get("end") or word_start)
            word_text = str(word.get("word") or "").strip()
            if word_end <= word_start or not word_text:
                continue
            normalized_word: dict[str, Any] = {
                "word": word_text,
                "start": round(word_start, 3),
                "end": round(word_end, 3),
            }
            if isinstance(word.get("probability"), (int, float)):
                normalized_word["probability"] = round(float(word["probability"]), 4)
            words.append(normalized_word)
        if words:
            normalized_segment["words"] = words
            normalized_segment["timestamp_precision"] = "word_level"
        else:
            normalized_segment["timestamp_precision"] = "segment_level"
        segments.append(normalized_segment)
    if not segments:
        raise SystemExit("local Whisper returned no usable timestamped speech")
    result: dict[str, Any] = {
        "schema_version": "0.5",
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
        if args.word_timestamps:
            command.extend(["--word_timestamps", "True"])
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
    if not re.search(r"[\u3400-\u9fff]", normalized):
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
    normalized = re.sub(
        r"(?<=[\u3400-\u9fff，。！？；：、,.!?;:]) +(?=[\u3400-\u9fff，。！？；：、,.!?;:])",
        "",
        normalized,
    )
    chunks = []
    current = ""
    punctuation = set("，。！？；：、,.!?;:")
    for index, character in enumerate(normalized):
        current += character
        next_character = normalized[index + 1] if index + 1 < len(normalized) else ""
        natural_break = character in punctuation and len(current) >= max(4, max_chars // 2)
        length_break = len(current) >= max_chars and next_character not in punctuation
        if natural_break or length_break:
            chunks.append(current.strip())
            current = ""
    remainder = current.strip()
    if remainder:
        if chunks and all(character in punctuation for character in remainder):
            chunks[-1] += remainder
        else:
            chunks.append(remainder)
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


def transcript_segment_bounds(segment: dict[str, Any]) -> tuple[float, float, str]:
    words = [word for word in (segment.get("words") or []) if isinstance(word, dict)]
    valid_words = [
        word
        for word in words
        if float(word.get("end") or 0) > float(word.get("start") or 0) and str(word.get("word") or "").strip()
    ]
    if valid_words:
        return float(valid_words[0]["start"]), float(valid_words[-1]["end"]), "word_level"
    start = float(segment.get("start") or 0)
    return start, float(segment.get("end") or start), "segment_level"


def merge_stage_heading_spans(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    stage_heading = re.compile(r"^第[一二三四五六七八九十百0-9]+阶段[：:]?$")
    index = 0
    while index < len(spans):
        current = dict(spans[index])
        caption = str(current.get("caption") or "").strip()
        following_gap = (
            float(spans[index + 1]["start"]) - float(current["end"])
            if index + 1 < len(spans)
            else float("inf")
        )
        if stage_heading.match(caption) and index + 1 < len(spans) and following_gap <= 0.8:
            following = spans[index + 1]
            current["end"] = following["end"]
            current["caption"] = f"{caption} {str(following.get('caption') or '').strip()}".strip()
            current["segment_id"] = f"{current['segment_id']}+{following['segment_id']}"
            current["source_timing"] = (
                "word_level" if current.get("source_timing") == following.get("source_timing") == "word_level" else "mixed"
            )
            current["stage_heading_merged"] = True
            index += 2
        else:
            merged.append(current)
            index += 1
            continue
        merged.append(current)
    return merged


def transcript_spans(
    transcript: dict[str, Any],
    source_duration: float,
    pre_roll: float,
    post_roll: float,
    min_silence_gap: float,
    final_tail: float,
) -> tuple[list[dict[str, Any]], str, list[dict[str, Any]]]:
    raw_segments = transcript.get("segments")
    if not isinstance(raw_segments, list) or not raw_segments:
        raise SystemExit("transcript.segments must be a non-empty array")
    spans: list[dict[str, Any]] = []
    for index, segment in enumerate(raw_segments, start=1):
        if not isinstance(segment, dict) or segment.get("keep") is False or str(segment.get("action") or "").lower() in {"delete", "skip"}:
            continue
        raw_start, raw_end, source_timing = transcript_segment_bounds(segment)
        start = max(0.0, raw_start - pre_roll)
        end = min(source_duration, raw_end + post_roll)
        if end - start < 0.2:
            continue
        spans.append(
            {
                "start": start,
                "end": end,
                "caption": str(segment.get("text") or ""),
                "segment_id": segment.get("id") or f"sentence-{index:03d}",
                "source_timing": source_timing,
            }
        )
    if not spans:
        raise SystemExit("no transcript segments survived the keep/delete gate")
    spans = merge_stage_heading_spans(spans)
    joins: list[dict[str, Any]] = []
    for index in range(1, len(spans)):
        previous = spans[index - 1]
        current = spans[index]
        gap_before = float(current["start"]) - float(previous["end"])
        action = "pass"
        if gap_before < min_silence_gap:
            overlap = max(0.0, -gap_before)
            midpoint = (float(previous["end"]) + float(current["start"])) / 2
            previous["end"] = max(float(previous["start"]) + 0.2, midpoint - min_silence_gap / 2)
            current["start"] = min(float(current["end"]) - 0.2, midpoint + min_silence_gap / 2)
            action = "tighten_both_boundaries"
        else:
            overlap = 0.0
        joins.append(
            {
                "previous_segment_id": previous["segment_id"],
                "current_segment_id": current["segment_id"],
                "gap_before_adjust_sec": round(gap_before, 3),
                "gap_after_adjust_sec": round(float(current["start"]) - float(previous["end"]), 3),
                "overlap_before_adjust_sec": round(overlap, 3),
                "action": action,
                "status": "manual_check",
                "previous_text": str(previous.get("caption") or ""),
                "current_text": str(current.get("caption") or ""),
            }
        )
    spans[-1]["end"] = min(source_duration, max(float(spans[-1]["end"]), float(spans[-1]["end"]) + final_tail))
    safety = "transcript_reviewed" if transcript.get("reviewed") is True else "transcript_unreviewed"
    return spans, safety, joins


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
        spans, semantic_safety, join_details = transcript_spans(
            transcript,
            source_duration,
            args.pre_roll,
            args.post_roll,
            args.min_silence_gap,
            args.final_tail,
        )
        mode_variant = "word_timed_transcript" if all(span.get("source_timing") == "word_level" for span in spans) else "transcript_driven"
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
        join_details = []
    else:
        raise SystemExit("provide --transcript or --silence-report")

    if semantic_safety == "transcript_reviewed":
        boundary_reason = "Reviewed transcript boundary"
    elif semantic_safety == "transcript_unreviewed":
        boundary_reason = "Unreviewed local transcript boundary; verify text and timing"
    else:
        boundary_reason = "Conservative FFmpeg silence boundary; semantic continuity is unverified"
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
                "reason": boundary_reason,
                "source_timing": span.get("source_timing", "silence_boundary"),
                "stage_heading_merged": bool(span.get("stage_heading_merged")),
            }
        )
        if sequence > 1:
            previous = clips[-2]
            detail = join_details[sequence - 2] if sequence - 2 < len(join_details) else {}
            joins.append(
                {
                    "previous_clip_id": previous["clip_id"],
                    "current_clip_id": clips[-1]["clip_id"],
                    "removed_gap_sec": round(start - float(previous["source_end"]), 3),
                    "status": "manual_check",
                    **detail,
                }
            )
    protocol = read_json(args.protocol)
    formal_gate = "ready_for_human_review" if semantic_safety == "transcript_reviewed" else "preview_only"
    result = {
        "schema_version": "0.5",
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
        "cut_parameters": {
            "pre_roll_sec": args.pre_roll,
            "post_roll_sec": args.post_roll,
            "min_silence_gap_sec": args.min_silence_gap,
            "final_tail_sec": args.final_tail,
        },
        "transition": {"video": "fade", "duration_sec": 0.18, "audio": "acrossfade"},
        "render_gate": "ready",
        "end_fade_duration": 1.0,
        "human_review_required": True,
        "review_checks": ["No sentence is cut in half", "No final syllable is swallowed", "Removed pauses do not change meaning", "Claims and captions are accurate"],
    }
    write_json(args.out, result)
    if args.join_report_out:
        write_json(
            args.join_report_out,
            {
                "schema_version": "0.5",
                "source_transcript": args.transcript,
                **result["cut_parameters"],
                "total_joins": len(joins),
                "review_required": True,
                "joins": joins,
                "pass_rule": "Listen to every join for overlap, swallowed syllables, broken sentences, and removed meaningful pauses.",
            },
        )
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
        "schema_version": "0.5",
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


def caption_timing_windows(caption: str, duration: float, max_chars: int = 16) -> list[dict[str, Any]]:
    chunks = split_caption_text(caption, max_chars)
    if not chunks or duration <= 0:
        return []
    weights = [max(4, len(chunk)) for chunk in chunks]
    total_weight = sum(weights)
    cursor = 0.0
    windows: list[dict[str, Any]] = []
    for index, (chunk, weight) in enumerate(zip(chunks, weights)):
        end = duration if index == len(chunks) - 1 else min(duration, cursor + duration * weight / total_weight)
        windows.append({"text": chunk, "start": cursor, "end": max(cursor + 0.2, end)})
        cursor = end
    return windows


def caption_font_path() -> Optional[str]:
    candidates = [
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/Supplemental/Songti.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    ]
    return next((candidate for candidate in candidates if Path(candidate).is_file()), None)


def write_caption_overlay(path: Path, caption: str, width: int, height: int, style: str) -> bool:
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return False
    font_path = caption_font_path()
    if not font_path:
        return False
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    clean = " ".join(caption.replace("\n", " ").split()).strip()
    if not clean:
        return False
    font_size = max(22, int(round(width * 0.06)))
    max_width = int(width * 0.88)
    while font_size >= max(18, int(width * 0.038)):
        font = ImageFont.truetype(font_path, font_size)
        box = draw.textbbox((0, 0), clean, font=font, stroke_width=max(2, width // 270))
        if box[2] - box[0] <= max_width:
            break
        font_size -= 2
    stroke_width = max(2, width // 270)
    box = draw.textbbox((0, 0), clean, font=font, stroke_width=stroke_width)
    text_width = box[2] - box[0]
    text_height = box[3] - box[1]
    padding_x = max(12, int(width * 0.03))
    padding_y = max(8, int(height * 0.012))
    x = (width - text_width) / 2
    y = min(height - text_height - padding_y * 3, int(height * 0.82))
    draw.rounded_rectangle(
        (x - padding_x, y - padding_y, x + text_width + padding_x, y + text_height + padding_y),
        radius=max(8, width // 60),
        fill=(0, 0, 0, 118),
    )
    if style == "white_yellow_keyword" and len(clean) >= 6:
        split_at = max(1, len(clean) - min(6, max(2, len(clean) // 3)))
        lead, keyword = clean[:split_at], clean[split_at:]
        draw.text((x, y), lead, font=font, fill=(255, 255, 255, 255), stroke_width=stroke_width, stroke_fill=(0, 0, 0, 230))
        lead_width = draw.textbbox((0, 0), lead, font=font, stroke_width=stroke_width)[2]
        draw.text(
            (x + lead_width, y),
            keyword,
            font=font,
            fill=(255, 214, 74, 255),
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 230),
        )
    else:
        fill = (255, 214, 74, 255) if style == "bold_b2b" else (255, 255, 255, 255)
        draw.text((x, y), clean, font=font, fill=fill, stroke_width=stroke_width, stroke_fill=(0, 0, 0, 230))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return True


def global_caption_windows(clips: list[dict[str, Any]], transition_duration: float) -> list[dict[str, Any]]:
    windows: list[dict[str, Any]] = []
    cursor = 0.0
    for index, clip in enumerate(clips):
        duration = max(0.0, float(clip.get("duration") or 0))
        output_start = cursor if index == 0 else max(0.0, cursor - transition_duration)
        for window in caption_timing_windows(str(clip.get("caption") or ""), duration):
            windows.append(
                {
                    "text": window["text"],
                    "start": output_start + float(window["start"]),
                    "end": output_start + float(window["end"]),
                    "clip_id": clip.get("clip_id"),
                }
            )
        cursor = output_start + duration
    for index in range(len(windows) - 1):
        if windows[index]["end"] > windows[index + 1]["start"]:
            windows[index]["end"] = windows[index + 1]["start"]
    return [window for window in windows if float(window["end"]) - float(window["start"]) >= 0.1]


def render_sync_report(
    edl: dict[str, Any],
    clips: list[dict[str, Any]],
    output: Path,
    actual_duration: float,
    transition: str,
    transition_duration: float,
    audio_transition: str,
) -> dict[str, Any]:
    cursor = 0.0
    timeline: list[dict[str, Any]] = []
    for index, clip in enumerate(clips):
        duration = float(clip.get("duration") or 0)
        output_start = cursor if index == 0 else max(0.0, cursor - transition_duration)
        output_end = output_start + duration
        timeline.append(
            {
                "clip_id": clip.get("clip_id"),
                "source_start": clip.get("source_start"),
                "source_end": clip.get("source_end"),
                "output_start": round(output_start, 3),
                "output_end": round(output_end, 3),
                "caption": str(clip.get("caption") or "")[:80],
            }
        )
        cursor = output_end
    expected = cursor
    drift = actual_duration - expected
    warnings: list[str] = []
    if abs(drift) > 0.6:
        warnings.append(f"Output duration drift is {drift:.3f}s; inspect late captions and audio sync.")
    if audio_transition == "acrossfade":
        warnings.append("Acrossfade can overlap adjacent speech; listen to every join before approval.")
    return {
        "schema_version": "0.5",
        "edl_id": edl.get("edl_id"),
        "edit_mode": edl.get("edit_mode"),
        "output": str(output),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "transition": {"video": transition, "duration_sec": transition_duration, "audio": audio_transition},
        "duration": {
            "edl_clip_sum_sec": round(sum(float(clip.get("duration") or 0) for clip in clips), 3),
            "expected_output_sec": round(expected, 3),
            "actual_output_sec": round(actual_duration, 3),
            "drift_sec": round(drift, 3),
        },
        "timeline": timeline,
        "warnings": warnings,
        "review_points": ["first 2 seconds", "every join", "last 2 seconds", "caption and voice sync after 60 seconds"],
    }


def render_edl(args: argparse.Namespace) -> None:
    ffmpeg = runtime_path("ffmpeg")
    ffprobe = runtime_path("ffprobe")
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
    video_preset = str(render_config.get("video_preset", "medium"))
    video_crf = min(51, max(0, int(render_config.get("video_crf", 21))))
    audio_codec = str(render_config.get("audio_codec", "aac"))
    caption_style = args.caption_style or str(render_config.get("default_caption_style") or "clean")
    captions_path = Path(args.captions_srt).expanduser().resolve() if args.captions_srt else None
    if captions_path and not captions_path.is_file():
        raise SystemExit(f"caption file does not exist: {captions_path}")
    burn_in_available = ffmpeg_filter_available(ffmpeg, "subtitles")
    png_overlay_available = ffmpeg_filter_available(ffmpeg, "overlay") and pillow_available()
    use_png_overlay = bool(
        captions_path
        and args.caption_layout == "single_line_sequence"
        and args.caption_mode in {"auto", "burn"}
        and png_overlay_available
    )
    use_ass = bool(
        captions_path
        and not use_png_overlay
        and args.caption_mode in {"auto", "burn"}
        and burn_in_available
    )
    if captions_path and args.caption_mode == "burn" and not (use_png_overlay or use_ass):
        raise SystemExit("caption burn-in requires subtitles/libass or Pillow plus the FFmpeg overlay filter")

    requested_transition = args.transition
    transition = (
        "fade"
        if requested_transition == "auto" and edl.get("edit_mode") == "talking_head_cleanup"
        else ("none" if requested_transition == "auto" else requested_transition)
    )
    durations = [float(clip.get("duration") or 0) for clip in clips]
    transition_duration = 0.0
    if transition != "none" and len(clips) > 1 and ffmpeg_filter_available(ffmpeg, "xfade"):
        transition_duration = min(max(0.03, args.transition_duration), min(durations) / 3)
    else:
        transition = "none"
    audio_transition = args.audio_transition
    if audio_transition == "auto":
        audio_transition = "acrossfade" if edl.get("edit_mode") == "talking_head_cleanup" else "acrossfade"
    if transition == "none":
        audio_transition = "concat"
    elif audio_transition == "acrossfade" and not ffmpeg_filter_available(ffmpeg, "acrossfade"):
        audio_transition = "trim_concat"

    command = [ffmpeg, "-y"]
    filters: list[str] = []
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
        filters.append(
            f"[{position}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps={fps},trim=duration={duration},"
            f"settb=AVTB,setpts=PTS-STARTPTS[v{position}]"
        )
        if asset.get("kind") == "video" and asset.get("has_audio"):
            filters.append(
                f"[{position}:a]aresample=48000,aformat=sample_rates=48000:channel_layouts=stereo,"
                f"atrim=duration={duration},asetpts=PTS-STARTPTS[a{position}]"
            )
        else:
            filters.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={duration},asetpts=PTS-STARTPTS[a{position}]")

    if transition != "none":
        current_video_label = "v0"
        elapsed = durations[0]
        for position in range(1, len(clips)):
            output_label = f"vx{position}"
            offset = max(0.0, elapsed - transition_duration)
            filters.append(
                f"[{current_video_label}][v{position}]xfade=transition={transition}:"
                f"duration={transition_duration:.3f}:offset={offset:.3f}[{output_label}]"
            )
            current_video_label = output_label
            elapsed += durations[position] - transition_duration
        if audio_transition == "acrossfade":
            current_audio_label = "a0"
            for position in range(1, len(clips)):
                output_label = f"ax{position}"
                filters.append(
                    f"[{current_audio_label}][a{position}]acrossfade=d={transition_duration:.3f}[{output_label}]"
                )
                current_audio_label = output_label
        else:
            trimmed_audio: list[str] = []
            for position, duration in enumerate(durations):
                audio_duration = duration if position == len(durations) - 1 else max(0.2, duration - transition_duration)
                label = f"at{position}"
                filters.append(f"[a{position}]atrim=0:{audio_duration:.3f},asetpts=PTS-STARTPTS[{label}]")
                trimmed_audio.append(f"[{label}]")
            filters.append(f"{''.join(trimmed_audio)}concat=n={len(clips)}:v=0:a=1[aconcat]")
            current_audio_label = "aconcat"
        total_duration = elapsed
    else:
        concat_inputs = "".join(f"[v{position}][a{position}]" for position in range(len(clips)))
        filters.append(f"{concat_inputs}concat=n={len(clips)}:v=1:a=1[vconcat][aconcat]")
        current_video_label = "vconcat"
        current_audio_label = "aconcat"
        total_duration = sum(durations)

    end_fade_duration = min(
        max(0.0, float(edl.get("end_fade_duration") or 0)),
        max(0.0, total_duration / 2),
    )
    if end_fade_duration > 0 and not use_png_overlay:
        fade_start = max(0.0, total_duration - end_fade_duration)
        filters.append(f"[{current_video_label}]fade=t=out:st={fade_start}:d={end_fade_duration}:color=black[vfade]")
        current_video_label = "vfade"
    if use_ass and captions_path:
        subtitle_path = escape_subtitles_path(captions_path)
        style = caption_force_style(render_config, caption_style)
        filters.append(f"[{current_video_label}]subtitles=filename='{subtitle_path}':force_style='{style}'[vout]")
    else:
        filters.append(f"[{current_video_label}]null[vout]")
    output = Path(args.out).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix="content-growth-render-", dir=str(output.parent))
    temporary_dir = Path(temporary.name)
    base_output = temporary_dir / "base.mp4" if use_png_overlay else output
    command.extend(
        [
            "-filter_complex", ";".join(filters),
            "-map", "[vout]", "-map", f"[{current_audio_label}]",
            "-t", f"{total_duration:.3f}",
            "-c:v", video_codec, "-preset", video_preset, "-crf", str(video_crf), "-pix_fmt", "yuv420p",
            "-c:a", audio_codec, "-b:a", "128k", "-movflags", "+faststart",
            str(base_output),
        ]
    )
    if args.dry_run:
        print(json.dumps({"command": command}, ensure_ascii=False, indent=2))
        temporary.cleanup()
        return
    process = subprocess.run(command, capture_output=True, text=True, check=False)
    if process.returncode != 0 or not base_output.is_file() or base_output.stat().st_size == 0:
        temporary.cleanup()
        raise SystemExit((process.stderr or f"ffmpeg render failed with exit code {process.returncode}").strip())

    caption_delivery = "sidecar_srt" if captions_path else "none"
    caption_style_applied = False
    if use_png_overlay:
        windows = global_caption_windows(clips, transition_duration)
        overlay_files: list[tuple[Path, dict[str, Any]]] = []
        for position, window in enumerate(windows):
            overlay_path = temporary_dir / f"caption-{position:03d}.png"
            if write_caption_overlay(overlay_path, str(window["text"]), width, height, caption_style):
                overlay_files.append((overlay_path, window))
        if overlay_files:
            overlay_command = [ffmpeg, "-y", "-i", str(base_output)]
            for overlay_path, _ in overlay_files:
                overlay_command.extend(
                    ["-loop", "1", "-framerate", str(fps), "-t", f"{total_duration:.3f}", "-i", str(overlay_path)]
                )
            overlay_filters: list[str] = []
            current_label = "0:v"
            for position, (_, window) in enumerate(overlay_files, start=1):
                output_label = f"captioned{position}"
                overlay_filters.append(
                    f"[{current_label}][{position}:v]overlay=0:0:format=auto:"
                    f"enable='between(t,{float(window['start']):.3f},{float(window['end']):.3f})'[{output_label}]"
                )
                current_label = output_label
            if end_fade_duration > 0:
                fade_start = max(0.0, total_duration - end_fade_duration)
                overlay_filters.append(
                    f"[{current_label}]fade=t=out:st={fade_start}:d={end_fade_duration}:color=black[vfinal]"
                )
                current_label = "vfinal"
            overlay_command.extend(
                [
                    "-filter_complex", ";".join(overlay_filters),
                    "-map", f"[{current_label}]", "-map", "0:a:0",
                    "-t", f"{total_duration:.3f}",
                    "-c:v", video_codec, "-preset", video_preset, "-crf", str(video_crf), "-pix_fmt", "yuv420p",
                    "-c:a", "copy", "-movflags", "+faststart", str(output),
                ]
            )
            overlay_process = subprocess.run(overlay_command, capture_output=True, text=True, check=False)
            if overlay_process.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
                temporary.cleanup()
                raise SystemExit((overlay_process.stderr or "PNG caption overlay render failed").strip())
            caption_delivery = "png_overlay"
            caption_style_applied = True
        else:
            shutil.copyfile(base_output, output)
    elif use_ass:
        caption_delivery = "burned_in"
        caption_style_applied = True

    if not output.is_file() or output.stat().st_size == 0:
        temporary.cleanup()
        raise SystemExit("render output was not created")
    actual_duration = float(probe(output, ffprobe).get("duration") or 0)
    sync_report_path = Path(args.sync_report_out).expanduser().resolve() if args.sync_report_out else output.with_suffix(".sync-report.json")
    sync_report = render_sync_report(
        edl,
        clips,
        output,
        actual_duration,
        transition,
        transition_duration,
        audio_transition,
    )
    write_json(str(sync_report_path), sync_report)
    temporary.cleanup()
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
                "caption_style_applied": caption_style_applied,
                "video_preset": video_preset,
                "video_crf": video_crf,
                "transition": transition,
                "transition_duration": round(transition_duration, 3),
                "audio_transition": audio_transition,
                "duration": actual_duration,
                "sync_report": str(sync_report_path),
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
    transcribe.add_argument("--word-timestamps", action="store_true")
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
    talking.add_argument("--min-silence-gap", type=float, default=0.08)
    talking.add_argument("--final-tail", type=float, default=0.5)
    talking.add_argument("--join-report-out")
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
    render.add_argument("--caption-style", choices=("clean", "bold_b2b", "white_yellow_keyword"))
    render.add_argument("--caption-layout", choices=("standard", "single_line_sequence"), default="standard")
    render.add_argument("--transition", choices=("auto", "none", "fade"), default="auto")
    render.add_argument("--transition-duration", type=float, default=0.18)
    render.add_argument("--audio-transition", choices=("auto", "acrossfade", "trim_concat"), default="auto")
    render.add_argument("--sync-report-out")
    render.add_argument("--protocol", default=str(DEFAULT_PROTOCOL))
    render.add_argument("--dry-run", action="store_true")
    render.set_defaults(func=render_edl)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
