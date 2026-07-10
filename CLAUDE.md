# Claude Code entry point

Read `AGENTS.md` first, then route the request to the matching `skills/*/SKILL.md` file. Keep enterprise facts and media local, write generated files under the selected project `output/` directory, and never upload or publish automatically.

For a first run:

```bash
python3 content_growth.py doctor
python3 content_growth.py demo
```
