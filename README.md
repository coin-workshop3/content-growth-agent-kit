# Content Growth Agent Kit

一个面向本地 Agent 的企业内容增长工具包。它把 GEO 任务生成、企业内容评分和本地自动剪辑做成可读的 `SKILL.md` 与可执行 CLI，不要求用户安装桌面平台。

## 当前能力

- `generate-geo-tasks`：从可验证的企业事实生成 AI 答案、搜索、对比、风险和证据型内容任务。
- `score-enterprise-content`：按 7 维 rubric 盲评分，执行 6 分准入和事实阻断。
- `auto-edit-local-video`：扫描本机素材、生成 EDL，并用用户自己的 FFmpeg 渲染审片草稿。

这个仓库不会自动上传素材、登录平台、发布内容、私信客户或替企业做商业承诺。

## 下载后先运行

只需要 Python 3.9+：

```bash
git clone https://github.com/coin-workshop3/content-growth-agent-kit.git
cd content-growth-agent-kit
python3 content_growth.py doctor
python3 content_growth.py demo
```

也可以在 GitHub 选择 **Download ZIP**，解压后进入目录运行相同的两条 Python 命令，不要求安装 Git。

`doctor` 会说明当前机器能运行哪些能力；`demo` 会生成 GEO、评分结果，并在本机有 FFmpeg 时生成一条合成视频草稿。输出默认位于 `demo-output/`。

## 创建自己的项目

```bash
python3 content_growth.py init projects/my-project
```

然后：

1. 把 `projects/my-project/enterprise-profile.json` 换成经过核实的企业资料。
   完成后把其中的 `template_data` 改为 `false`；模板状态不会生成真实 GEO 任务。
2. 把待评分稿件放进 `projects/my-project/draft.md`。
3. 把授权使用的本地素材放进 `projects/my-project/media/`。
4. 在 Agent 中打开仓库并说：`读取 projects/my-project/AGENT_TASK.md，完成能完成的步骤。`

确定性阶段可以统一运行：

```bash
python3 content_growth.py run projects/my-project
```

默认 `run` 允许部分完成，并在 `run-summary.json` 标记等待 Agent 或素材的阶段。自动化流程可使用 `--strict`：任何请求阶段未完成时返回退出码 2。

已有经验的 Agent 仍可直接调用底层脚本：

```bash
python3 skills/generate-geo-tasks/scripts/generate_geo_tasks.py \
  --input projects/my-project/enterprise-profile.json \
  --out projects/my-project/output/geo-tasks.json

python3 skills/score-enterprise-content/scripts/calculate_score.py \
  --input projects/my-project/score-evaluation.json \
  --out projects/my-project/output/score-result.json

python3 skills/auto-edit-local-video/scripts/local_video.py check-runtime
```

## 视频依赖：FFmpeg 够不够

基础剪辑只需要用户本机的 `ffmpeg` 与 `ffprobe`，不需要再下载其他 GitHub 视频项目：

- 扫描本地图片和视频
- 读取时长、尺寸和音轨
- 按脚本标签匹配素材
- 生成可检查的 EDL
- 输出基础 9:16 H.264/AAC 视频草稿

高级能力才可能需要额外工具：

| 目标 | 可选工具 |
|---|---|
| 语音转写和逐字时间戳 | WhisperX |
| 智能删停顿和气口 | auto-editor |
| 复杂字幕 | pysubs2 |
| 动效、强调层和 CTA 包装 | Remotion / HyperFrames |
| 剪映草稿导出 | pyJianYingDraft |

这些工具不属于基础必装项。`doctor` 只检测，不会擅自下载或运行第三方代码。

如果 `doctor` 显示 FFmpeg 缺失，请从 [FFmpeg 官方下载页](https://ffmpeg.org/download.html) 选择适合当前系统的安装方式；本仓库不捆绑或分发 FFmpeg 二进制。

## 底层框架

- `protocols/base-methodology.json`：开源基础 GEO、评分和视频协议。
- `schemas/`：企业资料、评分、脚本、素材索引、GEO 任务和 EDL 数据契约。
- `skills/`：Agent 工作流和底层执行脚本。
- `content_growth.py`：用户入口，提供 `doctor/demo/init/run`。
- `AGENTS.md` / `CLAUDE.md`：Codex 和 Claude Code 的入口说明。

## Agent 最小提示词

```text
读取 AGENTS.md 和目标项目的 AGENT_TASK.md。
只使用经过核实的企业事实和已授权的本地素材，
完成 GEO、评分和可执行的视频阶段，不上传或自动发布。
```

## 适合谁

第一阶段面向已经使用 Codex、Claude Code 或其他文件型 Agent 的个人和小团队。普通企业客户若没有本地 Agent 环境，后续可以在验证需求后再增加可选 UI，而不是把 UI 作为核心产品。

## 项目状态

当前为 `0.2.0-alpha`。GEO 与评分只依赖 Python 标准库；视频基础层依赖用户本机的 `ffmpeg` 与 `ffprobe`。自动转写、复杂字幕、智能删停顿、剪映草稿和高级动效仍属于可选高级能力。

## 开源与商业边界

本仓库中的通用 Skills、CLI、基础规则和示例采用 [Apache License 2.0](LICENSE)。行业规则包、客户数据、效果 benchmark、企业私有配置和定制服务不包含在本开源发行中，可以通过独立商业协议提供。
