# Changelog

版本号单一来源：本文件最新条目 + `scripts/collector_core.py` 的 `SKILL_VERSION`（打包脚本会校验两者一致）。

## 0.1.0 - 2026-07-17

首个版本。

- 8 个采集命令：note / user-info / user-notes / search / topic / comments / replies / enrich
- configure（网页令牌粘贴配置）与 balance（余额+流水）
- 全量结果落盘（JSON/CSV）+ stdout 摘要，防止撑爆智能体上下文
- 断点续采（--resume-file，含 comments 去重），余额中断保留部分结果
- 结构化错误码与充值/换设备指引
- 设备绑定（运行时指纹；`COLLECTOR_DEVICE_ID` env 可覆盖）
- 双平台：Claude Code（`~/.claude/skills/`）与 OpenClaw（`~/.openclaw/skills/`，支持 `COLLECTOR_API_KEY` env 注入）
