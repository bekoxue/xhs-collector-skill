# Changelog

版本号单一来源：本文件最新条目 + `scripts/collector_core.py` 的 `SKILL_VERSION`（打包脚本会校验两者一致）。

## 0.1.5 - 2026-07-17

- 付费采集前真实预检输出目录是否可写；响应返回后的落盘异常改为结构化错误并明确要求先查流水、不要直接重采，断点文件单独写入失败时保留主结果并输出警告
- 余额响应进一步校验 balance、流水时间和金额为有限数值，且时间戳可安全格式化，避免异常字段触发 traceback

## 0.1.4 - 2026-07-17

- 结果未知的网络或响应错误（含付费接口 5xx、读取响应时直接断连、TLS 或 HTTP 协议错误）改为明确要求先查 balance 流水，不再泄漏 traceback 或通过 action 指导智能体直接重试；quiet 输出同样保留 action
- 校验 HTTP 200 响应的顶层类型、成功标记、采集/余额必要字段、命令对应 data_type、records/fields/ledger 元素类型及字段 key；余额查询异常使用独立指引，不再错误提示采集已扣费或要求再次运行 balance
- 续采文件绑定命令、数据类型及原始请求指纹，空文件、旧版文件或其他任务的断点会在请求前被拒绝

## 0.1.3 - 2026-07-17

- CSV 输出自动转义公式型第三方文本，避免用表格软件打开时执行不可信公式
- 200 非 JSON、非法编码或截断响应改为结构化错误，并提示先查流水再决定是否重试
- 付费采集请求不再重复占用 API Key 限流名额

## 0.1.2 - 2026-07-17

- 连接重置等可能已到达服务端的网络错误不再自动重试，避免重复扣费；仅 DNS 失败和连接被拒绝会安全重试
- comments / replies 在单次 10 单元护栏中断时保存楼中楼回复游标，续采不跳过未完成回复
- replies / enrich 支持 `--resume-file`，批量补全会显示请求数、跳过数并保存剩余 ID
- 区分 `reached_request_limit` 与 `insufficient_balance`，余额充足时不再错误提示充值

## 0.1.1 - 2026-07-17

- 续采命令使用 Shell 安全转义，关键词或输出目录含空格、特殊字符时可直接复制执行
- 触发服务端限流时遵循 `Retry-After` 后再重试，避免在限流窗口内重复失败

## 0.1.0 - 2026-07-17

首个版本。

- 8 个采集命令：note / user-info / user-notes / search / topic / comments / replies / enrich
- configure（网页令牌粘贴配置）与 balance（余额+流水）
- 全量结果落盘（JSON/CSV）+ stdout 摘要，防止撑爆智能体上下文
- 断点续采（--resume-file，含 comments 去重），余额中断保留部分结果
- 结构化错误码与充值/换设备指引
- 设备绑定（运行时指纹；`COLLECTOR_DEVICE_ID` env 可覆盖）
- 双平台：Claude Code（`~/.claude/skills/`）与 OpenClaw（`~/.openclaw/skills/`，支持 `COLLECTOR_API_KEY` env 注入）
