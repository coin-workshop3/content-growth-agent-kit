---
name: auto-edit-local-video
description: Build reviewable local video drafts from a structured script and media folder using a small Python CLI plus the user's own FFmpeg. Use when an agent needs to inspect the local video runtime, index media, match script segments to tagged assets, generate an EDL, diagnose missing shots, or render a 9:16 draft without uploading media or publishing to a platform.
---

# Auto Edit Local Video

Create a conservative first cut on the user's machine. Produce an explicit EDL and stop on missing assets instead of hiding gaps with arbitrary footage.

## Workflow

1. Read `references/video-contract.md` before changing script, asset-index, or EDL structures.
2. Check the runtime:

```bash
python3 skills/auto-edit-local-video/scripts/local_video.py check-runtime
```

3. Scan the authorized media folder:

```bash
python3 skills/auto-edit-local-video/scripts/local_video.py scan-assets \
  --media-dir <local-media> --out <asset-index.json>
```

4. Review and improve asset tags. Filename and parent-folder words become initial tags.
5. Generate the EDL:

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
- The repository does not distribute FFmpeg binaries. Report a missing runtime and let the user choose how to install it.
- Never claim a render succeeded until the process exits successfully and the output file exists.
