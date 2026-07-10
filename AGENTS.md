# Content Growth Agent Kit

This repository is an agent-native toolkit, not a hosted platform. Keep enterprise facts and media local unless the user explicitly authorizes an upload.

## Route requests

- GEO questions, AI-answer discoverability, search-intent tasks, or content opportunity generation: read `skills/generate-geo-tasks/SKILL.md`.
- Draft scoring, publication gates, rubric evaluation, or revision priorities: read `skills/score-enterprise-content/SKILL.md`.
- Local media scanning, EDL generation, or FFmpeg draft rendering: read `skills/auto-edit-local-video/SKILL.md`.

## Repository rules

- Treat `examples/` as synthetic data. Never replace it with confidential customer data.
- Put generated files under `exports/`; it is gitignored.
- Do not upload media, publish content, log into social accounts, or send messages automatically.
- Do not invent enterprise claims, evidence, customer cases, prices, certifications, or performance results.
- Preserve JSON input/output contracts. Add a schema version when changing a contract.
- Run the relevant script and its smoke test after changing behavior.
- Keep the toolkit usable with Python 3.9+ standard library. FFmpeg/ffprobe are optional dependencies used only by video operations.
- Prefer `python3 content_growth.py doctor|demo|init|run` for user-facing workflows; keep lower-level skill scripts available for agents and debugging.
