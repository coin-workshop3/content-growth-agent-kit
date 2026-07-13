# Agent handoff

这份文档用于验证最重要的稳定版场景：用户只提供 GitHub 链接和一句提示词，文件型 Agent 能完成下载、环境检查、公开 demo 和项目初始化。

## 可直接复制的提示词

```text
请把 https://github.com/coin-workshop3/content-growth-agent-kit 下载到一个新的本地目录，并完成首次验收。

要求：
1. 先确认操作系统、Python 命令和目标目录，不覆盖已有文件。
2. 优先查看 GitHub Releases，下载最新非草稿版本中名为 content-growth-agent-kit-v<版本>.zip 的资产和相邻 .sha256，并在解压前验证 SHA-256；不要把 GitHub 自动生成的 Source code ZIP 当作已验收资产。没有 Release 资产时再使用 git clone，最后才使用 main ZIP。
3. 进入仓库后先阅读 AGENTS.md、README.md 和 docs/AGENT_HANDOFF.md。
4. macOS/Linux 优先使用 python3；Windows 优先尝试 py -3，再尝试 python。
5. 依次运行：
   - content_growth.py doctor
   - content_growth.py release-check --core-only
   - content_growth.py demo --skip-video
   - content_growth.py init projects/first-project
6. 如果 FFmpeg 和 ffprobe 已存在，再运行完整的 content_growth.py release-check。
7. 不自动安装软件、不上传媒体、不登录发布平台、不使用未经授权的素材。
8. 最后汇报：系统、Python、FFmpeg/Whisper 状态、每条命令的结果、生成路径、失败点和建议下一步。
```

Agent 应自行把上面的命令补成当前系统可用的 Python 启动方式，例如：

```bash
python3 content_growth.py doctor
python3 content_growth.py release-check --core-only
python3 content_growth.py demo --skip-video
python3 content_growth.py init projects/first-project
```

Windows 常见写法：

```powershell
py -3 content_growth.py doctor
py -3 content_growth.py release-check --core-only
py -3 content_growth.py demo --skip-video
py -3 content_growth.py init projects/first-project
```

## 首次交接通过标准

- Agent 使用的是新目录，没有复用开发者的本地输出。
- `doctor` 能区分核心能力、FFmpeg、字幕和可选 Whisper。
- `release-check --core-only` 返回 `PASSED`。
- demo 生成 `geo-tasks.json`、`score-result.json` 和 `run-summary.json`。
- init 生成 `AGENT_TASK.md`、企业资料模板、草稿、媒体目录和输出目录。
- 没有 FFmpeg 时，Agent 能解释视频被跳过，而不是把它报告为整个项目失败。
- Agent 没有擅自安装依赖、上传数据或发布内容。

## 视频交接

只有用户明确要求视频处理并提供已授权素材时，才继续：

1. 运行 `doctor`，确认 FFmpeg/ffprobe。
2. 把素材放进项目 `media/`。
3. 运行 `video <project> --mode auto`。
4. Whisper 只在本机已经安装且用户明确要求转写时使用。
5. 自动转写保持未复核；人工审核前不得把草稿描述为可发布成片。

支持范围和已知限制见 [SUPPORT_MATRIX.md](SUPPORT_MATRIX.md)，失败处理见 [TROUBLESHOOTING.md](TROUBLESHOOTING.md)。
