---
name: auto-edit-local-video
description: "Build reviewable local video drafts with two explicit FFmpeg modes: talking-head cleanup and scripted material assembly. Use when an agent needs to recommend a mode, inspect local media, detect long pauses, use a reviewed transcript for sentence-safe talking-head cuts, match script segments to tagged product assets, generate an EDL, diagnose missing shots, or render a 9:16 draft without uploading media or publishing to a platform."
---

# Auto Edit Local Video

Create a conservative first cut on the user's machine using one of two protocol modes: `talking_head_cleanup` (口播精剪) or `scripted_asset_assembly` (素材拼接). Produce an explicit EDL and stop on unsafe or missing inputs instead of hiding gaps.

## Choose a mode

1. Scan assets and run `recommend-mode` when the user did not choose a mode.
2. Recommend `talking_head_cleanup` for one primary video with audio and few or no cutaway assets.
3. Recommend `scripted_asset_assembly` for a structured script plus multiple product, scene, proof, or CTA assets.
4. Ask the user when confidence is below 0.7. Never silently choose an ambiguous mode.

Use the user-facing command when working in a toolkit project:

```bash
python3 content_growth.py video <project> --mode auto
python3 content_growth.py video <project> --mode talking-head
python3 content_growth.py video <project> --mode material-assembly
```

## Talking-head standard

- Prefer `transcript.reviewed.json`. Use its keep/delete segments as sentence-safe cut boundaries.
- Without a reviewed transcript, run FFmpeg `silencedetect` and create only a conservative `preview_only` draft.
- Never claim that a silence-only draft removed filler words, preserved meaning, or completed semantic cleanup.
- Keep 9:16, 30 fps, local source audio, manual join review, and a one-second visual fade at the end.
- Treat every join as a manual review point for swallowed syllables, broken sentences, and meaning changes.

## Material-assembly standard

- Require `video-script.json` with executable segments and asset tags.
- Match Hook / Problem / SceneEmotion / Product / Proof / CTA needs to local assets.
- Block rendering when any segment has no matching asset unless the user explicitly requests a rough fallback.
- Treat the current base renderer as a tag-matched draft. Formal captions and a continuous audio bed require confirmed spoken copy or a real transcript.

## Workflow

1. Read `references/video-contract.md` before changing script, asset-index, or EDL structures. Read `references/dependency-levels.md` when deciding whether FFmpeg is enough or an advanced tool is justified.
2. Check the runtime:

```bash
python3 skills/auto-edit-local-video/scripts/local_video.py check-runtime
```

3. For lower-level use, scan the authorized media folder:

```bash
python3 skills/auto-edit-local-video/scripts/local_video.py scan-assets \
  --media-dir <local-media> --out <asset-index.json>
```

4. Review and improve asset tags. Filename and parent-folder words become initial tags.
5. For material assembly, generate the EDL:

```bash
python3 skills/auto-edit-local-video/scripts/local_video.py make-edl \
  --script <script.json> --assets <asset-index.json> --out <edl.json>
```

6. If the EDL reports missing clips, request or identify the exact shots and regenerate. Use `--allow-fallback` only for a deliberate rough montage.
7. Render after all clips are resolved:

```bash
python3 skills/auto-edit-local-video/scripts/local_video.py render-edl \
  --edl <edl.json> --assets <asset-index.json> --out <draft.mp4>
```

8. Require human review for factual accuracy, framing, pacing, captions, rights, and publication readiness.

## Boundaries

- Keep all media local. Do not upload, publish, log in, or modify social accounts.
- Use only media paths the user placed in scope. Reject paths escaping the declared media directory.
- This alpha renderer makes a simple 9:16 cut and preserves source audio when present. It does not transcribe speech, burn captions, normalize loudness, or promise final-edit quality.
- A talking-head silence-only result is always `preview_only`; only a reviewed timestamped transcript can move it to `ready_for_human_review`.
- The repository does not distribute FFmpeg binaries. Report a missing runtime and let the user choose how to install it.
- Do not install optional GitHub video tools merely because they are detected as missing. Use the basic FFmpeg path unless the requested result needs a listed advanced capability.
- Never claim a render succeeded until the process exits successfully and the output file exists.
