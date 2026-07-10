# Video dependency levels

## Basic local edit

Required: `ffmpeg` and `ffprobe` on the user's PATH.

This level scans media, reads dimensions and duration, detects long talking-head silences, matches tagged shots to script segments, writes an auditable EDL, generates SRT captions, center-crops to 9:16, preserves source audio when available, and renders an H.264/AAC review draft.

Caption burn-in is automatic only when the FFmpeg build exposes the `subtitles` filter backed by libass. Otherwise the SRT sidecar remains the portable output.

## Optional local transcription

OpenAI Whisper CLI is the supported v0.4 transcription adapter. It runs against local media and writes an unreviewed timestamped transcript. The toolkit does not install it, upload source media, or mark its output reviewed. First use may download the selected model.

No additional GitHub video repository is required for this level.

## Optional advanced capabilities

Install and authorize only what the task requires:

| Capability | Typical optional tool | Why it is not in the base |
|---|---|---|
| Local segment-level speech transcript | OpenAI Whisper CLI | Large model/runtime and platform-specific setup |
| Word alignment and speaker-aware transcript | WhisperX | Heavier alignment/runtime requirements |
| More advanced silence/motion first pass | auto-editor | Base FFmpeg detects long pauses; more aggressive timing changes need careful review |
| Complex subtitle authoring | pysubs2 | Unnecessary for a basic rough cut |
| Animated callouts and packaging | Remotion or HyperFrames | Node runtime and template maintenance |
| Jianying draft export | pyJianYingDraft | Depends on Jianying formats and versions |

The doctor command detects common optional tools but never downloads, installs, or executes them automatically. External repositories and model downloads require explicit user authorization and their own license review.
