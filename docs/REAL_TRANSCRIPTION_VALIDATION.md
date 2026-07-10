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
