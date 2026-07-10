# Video dependency levels

## Basic local edit

Required: `ffmpeg` and `ffprobe` on the user's PATH.

This level scans media, reads dimensions and duration, matches tagged shots to script segments, writes an auditable EDL, center-crops to 9:16, preserves source audio when available, and renders an H.264/AAC review draft.

No additional GitHub video repository is required for this level.

## Optional advanced capabilities

Install and authorize only what the task requires:

| Capability | Typical optional tool | Why it is not in the base |
|---|---|---|
| Speech transcript and word timestamps | WhisperX | Large model/runtime and platform-specific setup |
| Silence and pause cutting | auto-editor | Changes narrative timing and needs careful review |
| Complex subtitle authoring | pysubs2 | Unnecessary for a basic rough cut |
| Animated callouts and packaging | Remotion or HyperFrames | Node runtime and template maintenance |
| Jianying draft export | pyJianYingDraft | Depends on Jianying formats and versions |

The doctor command detects common optional tools but never downloads, installs, or executes them automatically. External repositories and model downloads require explicit user authorization and their own license review.
