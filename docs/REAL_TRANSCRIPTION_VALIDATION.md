# Real local Whisper validation

Date: 2026-07-10

This is a functional integration check, not an accuracy benchmark. It used no customer media and uploaded no source audio.

## Environment

- macOS on Apple Silicon (`arm64`)
- Python 3.9 isolated virtual environment
- `openai-whisper` 20250625
- Whisper model: `tiny`, language fixed to Chinese
- FFmpeg 8.1.1

## Synthetic spoken input

The local macOS Chinese voice read:

> 嗯，那个，我们今天讲一下企业内容工具。其实，就是，把素材放进去以后，系统会生成字幕。然后，然后你需要人工检查，再决定是否发布。

The audio was wrapped in a 9:16 local MP4 and passed through the repository's public `transcribe` command.

## Observed result

- The command produced five timestamped segments and a review-gated transcript.
- The `tiny` model omitted the opening hesitation words `嗯，那个`.
- Some Simplified Chinese text was returned as Traditional Chinese.
- It retained the adjacent repetition `然後然後`.
- The deterministic review layer marked that repetition as one candidate with estimated segment-relative timestamps.
- The generated video draft retained audio, produced five SRT entries, and remained `preview_only` with publication blocked.

## Product conclusion

Automatic transcription is useful for cut and caption candidates, but it cannot prove that filler words were fully detected. Filler candidates therefore remain review-only, use approximate timestamps, and never trigger automatic deletion. Real customer speech, accents, background noise, and larger Whisper models still require separate validation.

## Authorized real talking-head follow-up

A second local check used one authorized, non-customer Chinese talking-head recording. No transcript text, frames, personal path, or source media is committed to this repository.

- Source: about 108 seconds, HEVC/AAC, phone rotation metadata, one continuous speaker.
- Model: Whisper `small`, Chinese fixed explicitly.
- First-run cost: about 429 MB of model data downloaded locally; download plus CPU transcription took roughly 14 minutes on this machine.
- Output: 12 timestamped segments, zero deterministic filler/repetition candidates, SRT sidecar captions, and a low-resolution 9:16 review draft with audio.
- Gates remained correct: `reviewed=false`, `formal_gate=preview_only`, `publication_gate=blocked_pending_human_review`, and `source_upload=false`.
- Manual transcript inspection found likely recognition mistakes even though no filler candidate was returned. This reinforces that candidate count is not an accuracy score.

The run also exposed three integration issues that are covered by the next patch release: phone rotation metadata must affect display dimensions, an unreviewed transcript boundary must not be labeled as reviewed, and caption wrapping must not leave punctuation on a line by itself.

## Restored standard-path validation

Using the separately reviewed local transcript from the user's prior private workbench as a local test input (not committed), the public CLI now reproduces the standard talking-head path:

- 35 word-timed clips with stage-heading merge and 34 join-review records.
- 1080×1920, 30 fps H.264/AAC preview at 64.27 seconds.
- Single-line `white_yellow_keyword` captions rendered through the Pillow + FFmpeg overlay fallback because this machine's FFmpeg lacks libass.
- 0.18-second video dissolve, audio acrossfade, 1-second end fade, and 0.027-second measured duration drift.
- `formal_gate=ready_for_human_review`; `publication_gate=blocked_pending_human_review` remains enforced.

The restored output is a reviewable draft, not a publish-ready file: every join and the final two seconds still require listening review, and acrossfade may overlap adjacent speech.
