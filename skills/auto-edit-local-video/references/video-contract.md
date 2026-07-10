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
