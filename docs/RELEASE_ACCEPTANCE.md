# Release acceptance

稳定发布是一个可重复验收过程，不是单纯修改版本号。

## 严重度

- **P0 / release-blocker**：数据泄露、覆盖源文件、自动发布、无法启动、官方 Release ZIP 无法验证、三平台核心流程任一失败。
- **P1 / high**：文档主路径不可执行、doctor 给出错误结论、demo/init 失败、基础 FFmpeg 路径在支持平台失败、版本或校验和不一致。
- **P2 / normal**：有明确替代路径的体验问题、可选能力或文档改进。

发布 `v1.0.0` 前，公开 Issue 中 P0 和 P1 必须为 0。

## 自动准入

- [ ] Python 3.9 语法检查通过。
- [ ] Schema、协议和合成示例校验通过。
- [ ] Ubuntu、macOS、Windows smoke test 通过。
- [ ] `content_growth.py release-check` 通过。
- [ ] 白名单 Release ZIP 构建成功并生成 SHA-256。
- [ ] CI 从全新临时目录解压 ZIP，并在解压目录运行 `release-check`。
- [ ] Release ZIP 中 README、CHANGELOG 和工具版本一致。
- [ ] 敏感路径、密钥和本地媒体扫描无命中。

## 外部 Agent/电脑准入

正式 `v1.0.0` 至少需要 3 个、建议 5 个全新环境。最低覆盖一个 macOS、一个 Windows、一个 Linux，以及至少两种文件型 Agent。

| 编号 | 日期 | OS | Agent | Python | FFmpeg | core release-check | full release-check | demo/init | Issue | 结果 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 |  | macOS |  |  |  |  |  |  |  | pending |
| 2 |  | Windows |  |  |  |  |  |  |  | pending |
| 3 |  | Linux |  |  |  |  |  |  |  | pending |
| 4 |  |  |  |  |  |  |  |  |  | optional |
| 5 |  |  |  |  |  |  |  |  |  | optional |

每个环境使用 [AGENT_HANDOFF.md](AGENT_HANDOFF.md) 的同一提示词，保存去隐私后的 `release-check.json`，记录第一处卡点。不得复用开发者已经装好的项目目录或生成文件。

## 晋级规则

`v1.0.0-rc.1` 可以在仓库内自动准入完成后发布。正式 `v1.0.0` 还必须满足：

1. 至少 3 个全新环境完成交接，覆盖 macOS、Windows、Linux。
2. 核心 release-check 全部通过。
3. 至少一个真实 FFmpeg 视频实践通过；Whisper 若未覆盖，继续明确标记为可选/实验性。
4. 所有 P0/P1 Issue 关闭并有回归证据。
5. RC 发布后至少 24 小时没有新增 P0/P1。

未满足时继续发布新的 RC，不移动或重写已发布标签。
