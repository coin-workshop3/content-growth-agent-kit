# Changelog

## v0.5.1-alpha

- Raise standard video quality with protocol-owned libx264 `medium` and CRF 21 settings instead of the previous hard-coded `veryfast` preset.
- Report the applied video preset and CRF in CLI results so render quality is auditable.
- Preserve the reviewed-transcript safety boundary: isolated connectors are removed only when a human-reviewed transcript explicitly marks them `keep: false`.
- Validate the quality patch against an authorized local 4K/60 fps talking-head source without uploading or committing source media.

## v0.5.0-alpha

- Restore the reviewed talking-head standard with word-timed cuts, stage-heading merge, tunable cut padding, join review, dissolve transitions, audio acrossfade, sync reporting, and a protected final tail.
- Add local Whisper word timestamps while keeping automatic transcripts unreviewed and filtering unusably short timestamp artifacts.
- Add single-line white/yellow talking-head captions with a Pillow + FFmpeg PNG overlay fallback when libass is unavailable.
- Respect phone rotation metadata in the local asset index and preserve encoded dimensions separately.
- Keep every video draft behind human review and publication gates; no media upload or automatic publishing is added.

## v0.4.1-alpha

- Add conservative transcript filler/repetition review candidates, real local Whisper validation, caption styles, and three-platform CI coverage.
