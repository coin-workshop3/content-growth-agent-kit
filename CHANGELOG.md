# Changelog

## v0.5.0-alpha

- Restore the reviewed talking-head standard with word-timed cuts, stage-heading merge, tunable cut padding, join review, dissolve transitions, audio acrossfade, sync reporting, and a protected final tail.
- Add local Whisper word timestamps while keeping automatic transcripts unreviewed and filtering unusably short timestamp artifacts.
- Add single-line white/yellow talking-head captions with a Pillow + FFmpeg PNG overlay fallback when libass is unavailable.
- Respect phone rotation metadata in the local asset index and preserve encoded dimensions separately.
- Keep every video draft behind human review and publication gates; no media upload or automatic publishing is added.

## v0.4.1-alpha

- Add conservative transcript filler/repetition review candidates, real local Whisper validation, caption styles, and three-platform CI coverage.
