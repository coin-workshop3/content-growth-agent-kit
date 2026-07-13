# Support matrix

本矩阵区分“稳定支持”“有条件支持”和“实验性能力”。稳定版承诺只覆盖明确列为 Stable 的范围。

## 操作系统与核心能力

| 能力 | macOS | Windows | Linux | 状态 |
|---|---|---|---|---|
| Python CLI、doctor、setup、demo、init | CI + 本地实测 | CI | CI | Stable |
| GEO 任务生成 | CI + 本地实测 | CI | CI | Stable |
| 企业内容评分 | CI + 本地实测 | CI | CI | Stable |
| 缺少 FFmpeg 时的安全降级 | 本地实测 | CI 路径覆盖 | CI 路径覆盖 | Stable |
| FFmpeg 素材扫描与基础草稿 | 真实素材 + CI | 合成素材 CI | 合成素材 CI | Stable with FFmpeg |
| SRT 字幕旁挂 | CI | CI | CI | Stable |
| PNG 单行字幕烧录 | Pillow + overlay 实测 | 依赖本机 Pillow/FFmpeg | 依赖本机 Pillow/FFmpeg | Conditional |
| libass 字幕烧录 | 取决于 FFmpeg build | 取决于 FFmpeg build | 取决于 FFmpeg build | Conditional |
| 本地 OpenAI Whisper CLI | 真实中文素材实测 | 尚缺真实素材外部验收 | 尚缺真实素材外部验收 | Optional / experimental outside macOS |
| WhisperX、auto-editor、剪映草稿、复杂动效 | 未纳入稳定基础层 | 未纳入稳定基础层 | 未纳入稳定基础层 | Experimental |

## Python

- 最低版本：Python 3.9。
- macOS/Linux 文档使用 `python3`。
- Windows 优先使用 `py -3`，也可以使用 PATH 中的 `python`。
- GEO 和评分只依赖 Python 标准库。

## 视频依赖

- 基础视频：`ffmpeg`、`ffprobe`。
- PNG 字幕 fallback：Pillow 和 FFmpeg `overlay` 滤镜。
- 本地自动转写：OpenAI Whisper CLI；首次使用模型可能需要下载模型文件。
- 所有依赖都由用户或 Agent 在获得用户确认后安装；工具包不会自动安装。

## Agent 支持

| Agent 类型 | 支持方式 | 状态 |
|---|---|---|
| Codex | 读取 `AGENTS.md` 和项目 `AGENT_TASK.md` | Primary |
| Claude Code | 读取 `CLAUDE.md`、`AGENTS.md` 和项目任务 | Primary |
| 其他文件型 Agent | 读取 README 和 `docs/AGENT_HANDOFF.md`，运行 CLI | Compatible, requires handoff validation |
| 纯聊天机器人、无文件/终端权限的 Agent | 无法自行下载或运行 CLI | Not supported |

## 稳定范围边界

“Stable”表示确定性核心流程、错误处理和基础 FFmpeg 路径有自动化验收；不表示自动发布、自动事实背书、自动删词或所有第三方依赖都由本项目维护。所有对外发布仍要求人工审核。
