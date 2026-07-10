# Local video contracts

## Script

```json
{
  "schema_version": "0.1",
  "script_id": "demo-001",
  "aspect_ratio": "9:16",
  "segments": [
    {
      "id": "hook",
      "role": "hook",
      "text": "The spoken or on-screen idea",
      "duration": 3.0,
      "asset_tags": ["product", "closeup"]
    }
  ]
}
```

`duration` must be positive. `asset_tags` should describe observable footage, not abstract marketing claims.

## Asset index

The scanner writes `media_base` and relative asset paths. Agents may improve `tags` but must not change a path without rescanning or verifying the file.

## EDL

The EDL is the review boundary between planning and rendering. Every clip keeps `segment_id`, `caption`, selected `asset_id`, duration, and match status. A `missing` status blocks rendering.

The alpha renderer outputs 1080×1920, 30 fps, H.264/AAC MP4. It center-crops visual media to fill the canvas. Captions remain in the EDL for human review and are not burned into the video.

## Talking-head inputs

Preferred transcript file:

```json
{
  "reviewed": true,
  "language": "zh",
  "segments": [
    {"start": 0.2, "end": 2.8, "text": "第一句真实口播", "keep": true, "role": "Hook"},
    {"start": 2.8, "end": 4.1, "text": "需要删除的重录", "keep": false}
  ]
}
```

If no transcript exists, `detect-silence` writes `silence-report.json`. The resulting EDL uses `source_start` and `source_end` but must retain `semantic_safety: silence_only_unverified` and `formal_gate: preview_only`.

## Mode gates

- `talking_head_cleanup`: require one local video with audio. A reviewed transcript is required for sentence-safe acceptance.
- `scripted_asset_assembly`: require a structured video script and an asset index. Missing assets block render.
- Both modes produce drafts only and require human review before publication.
