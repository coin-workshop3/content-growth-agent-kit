# Troubleshooting

先运行：

```bash
python3 content_growth.py doctor
python3 content_growth.py release-check --core-only
```

Windows 把 `python3` 替换为 `py -3` 或 `python`。

## 找不到 Python

- 要求 Python 3.9+。
- Windows 安装时启用 **Add Python to PATH**，或使用 `py -3`。
- macOS 可以使用 python.org 或 Homebrew 的 Python。
- Linux 使用发行版包管理器安装 Python 3。

## FFmpeg 或 ffprobe 缺失

这不会阻断 GEO 和评分。`doctor` 会把视频标记为 `OPTIONAL / NOT READY`，demo 会跳过视频。

- macOS：安装 Homebrew 后运行 `brew install ffmpeg`。
- Windows：从 [FFmpeg 官方下载页](https://ffmpeg.org/download.html) 选择 Windows build，并把 `ffmpeg`、`ffprobe` 加入 PATH。
- Linux：使用发行版包管理器或 FFmpeg 官方说明。

安装后关闭并重新打开终端，再运行 `doctor`。

## 字幕只有 SRT，没有烧进视频

这是受支持的降级结果。字幕烧录需要以下任一路径：

- FFmpeg 提供 `subtitles/libass`；或
- 已安装 Pillow，并且 FFmpeg 提供 `overlay` 滤镜。

没有这些能力时仍会保留可移植的 SRT 文件。

## Whisper 未就绪

Whisper 是可选依赖，不影响核心、GEO、评分和基础 FFmpeg 工作流。用户明确需要本地自动转写时，才按 `setup` 给出的命令安装。自动转写永远保持未复核状态。

## demo 通过，但真实口播只能得到 preview_only

没有人工复核的时间戳转写时，这是正确的安全行为。静音检测不能证明切点语义安全。需要增加 `transcript.reviewed.json` 并人工核对文本与时间戳。

## 企业资料模板阻止 GEO 生成

`init` 创建的是合成模板。把字段替换为经过核实的企业事实，再把 `template_data` 改为 `false`。

## 多条有声视频选错主素材

查看 `mode-recommendation.json` 的候选 `asset_id`，然后通过 `--asset-id` 指定目标口播素材。

## release-check 失败

使用 JSON 报告定位具体检查：

```bash
python3 content_growth.py release-check --json --out release-check.json
```

- `release_files_and_version`：下载包不完整或版本文档不同步。
- `doctor_core`：Python 版本或必需文件不满足。
- `contracts`：协议、Schema 或示例不一致。
- `release_privacy_scan`：发布输入中出现疑似密钥、个人绝对路径、本地媒体或意外二进制。
- `smoke`：确定性流程或本机视频运行时失败。
- `agent_handoff_demo_and_init`：首次 demo/init 交接路径失败。

提交 Issue 前删除报告中的个人路径、客户资料和素材名称，只保留必要错误信息。

## 权限与隐私

不要把源视频、客户资料、转写、密钥或环境变量附到公开 Issue。若错误只能通过私有素材复现，先用合成素材最小化问题。
