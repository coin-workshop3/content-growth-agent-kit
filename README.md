# Content Growth Agent Kit

一个面向本地 Agent 的企业内容增长工具包。它把 GEO 任务生成、企业内容评分和本地自动剪辑做成可读的 `SKILL.md` 与可执行 CLI，不要求用户安装桌面平台。

## 当前能力

- `generate-geo-tasks`：从可验证的企业事实生成 AI 答案、搜索、对比、风险和证据型内容任务。
- `score-enterprise-content`：按 7 维 rubric 盲评分，执行 6 分准入和事实阻断。
- `auto-edit-local-video`：扫描本机素材、生成 EDL，并用用户自己的 FFmpeg 渲染审片草稿。

这个仓库不会自动上传素材、登录平台、发布内容、私信客户或替企业做商业承诺。

## 最小使用方式

克隆仓库后，在仓库目录中对 Agent 说：

```text
读取 AGENTS.md。使用 generate-geo-tasks，
把 examples/demo-enterprise/enterprise-profile.json 生成 GEO 任务。
```

也可以直接运行确定性脚本：

```bash
python3 skills/generate-geo-tasks/scripts/generate_geo_tasks.py \
  --input examples/demo-enterprise/enterprise-profile.json \
  --out exports/geo-tasks.json

python3 skills/score-enterprise-content/scripts/calculate_score.py \
  --input examples/demo-enterprise/score-evaluation.json \
  --out exports/score-result.json

python3 skills/auto-edit-local-video/scripts/local_video.py check-runtime
```

## 适合谁

第一阶段面向已经使用 Codex、Claude Code 或其他文件型 Agent 的个人和小团队。普通企业客户若没有本地 Agent 环境，后续可以在验证需求后再增加可选 UI，而不是把 UI 作为核心产品。

## 项目状态

当前为 `0.1.0-alpha`。GEO 与评分脚本只依赖 Python 标准库；视频渲染依赖用户本机的 `ffmpeg` 与 `ffprobe`。

## 开源与商业边界

本仓库中的通用 Skills、CLI、基础规则和示例采用 [Apache License 2.0](LICENSE)。行业规则包、客户数据、效果 benchmark、企业私有配置和定制服务不包含在本开源发行中，可以通过独立商业协议提供。
