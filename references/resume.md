# 断点续采机制

## 工作原理

可续采命令（user-notes / search / topic / comments / replies / enrich）每次成功采集后，如果服务端返回 `has_more: true`，CLI 会：

1. 初次采集为每个任务生成独立断点文件 `{out_dir}/.resume_{data_type}_{标识}_{run_id}.json`，保存服务端返回的游标、搜索会话、翻页位置等状态
2. 在断点文件中保存命令、数据类型及原始请求指纹；续采前自动校验，防止把其他任务的游标用于当前采集
3. 使用 `--resume-file` 续采时，读取 `request_patch` 并在成功后通过同目录临时文件原子更新传入的同一断点文件；对 comments / replies 同时累积已采集记录的 ID 列表（seen_ids）
4. 在 stdout 摘要的 `resume_hint` 字段给出完整续采命令（原命令 + `--resume-file` 参数），直接复制执行即可

## 各命令的续采状态字段

| 命令 | 保存的状态 |
|---|---|
| user-notes | `resume_cursor`（翻页游标） |
| search | `page` + `search_id` + `search_session_id`（搜索会话，跨请求保持结果连续） |
| topic | `cursor_score` + `last_note_id` + `last_note_ct` + `session_id` + `first_load_time` |
| comments | 主评论 `resume_cursor` + `resume_index` + `resume_page_area`，楼中楼 `resume_replies` + `resume_top_has_more`，以及 `seen_ids` 去重列表 |
| replies | `resume_replies`（未完成父评论的回复 cursor / index）+ `seen_ids` 去重列表 |
| enrich | `note_ids`（超过单请求护栏或余额范围的剩余 ID） |

## 余额中断的续采

`stop_reason: insufficient_balance` 表示分页过程中余额耗尽。此时：

- 已采集的记录**已经保存到输出文件**，已扣费部分对应的数据不会丢失
- 续采状态照常保存，`resume_hint` 照常给出
- 用户充值后执行 resume_hint 中的命令即可从断点继续，不会重复扣费

`stop_reason: reached_request_limit` 只表示达到单请求安全消费上限，余额仍然可用，直接执行 `resume_hint` 即可继续。

## 注意事项

- 续采文件与采集参数（同一博主/关键词/笔记）强绑定；文件不匹配、断点为空或缺少绑定信息时，CLI 会在发起计费请求前拒绝执行
- 0.1.3 及更早版本生成的续采文件没有绑定信息，升级后需重新发起一次采集生成新断点
- 续采文件保存在输出目录下（`.resume_` 前缀的隐藏文件），采集任务彻底完成后可以删除
- 每次初始采集使用独立断点文件，避免同关键词、同博主或 replies / enrich 任务互相覆盖
- 每次续采成功后原子更新传入的同一文件，始终指向最新断点；不要并发执行同一个 `resume_hint`
