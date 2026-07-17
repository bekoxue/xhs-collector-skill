"""小红书产品声明：服务地址、命令 → 端点 → 请求体 → 续采映射。

新增产品（如抖音）时复制 collector_core.py + 本文件模板，改 SPEC 与 COMMANDS 即可。
"""
from __future__ import annotations

SPEC = {
    "product": "xhs",
    "product_name": "小红书",
    "key_prefix": "xhs_sk_",
    "base_url": "https://xhs.baojianlab.com",
    "config_dir": "~/.xhs-collector",
    "default_out_dir": "./xhs_data",
}


def _is_link(text: str) -> bool:
    t = (text or "").strip().lower()
    return "http" in t or "xhslink" in t or "xiaohongshu.com" in t


def note_body(args) -> dict:
    body = {"note_kind": args.kind}
    if _is_link(args.input):
        body["share_text"] = args.input.strip()
    else:
        body["note_id"] = args.input.strip()
    return body


def user_input_body(args) -> dict:
    if _is_link(args.input):
        return {"share_text": args.input.strip()}
    return {"user_id": args.input.strip()}


def user_notes_body(args) -> dict:
    body = user_input_body(args)
    body["max_pages"] = args.max_pages
    return body


def search_body(args) -> dict:
    return {
        "keyword": args.keyword,
        "sort_type": args.sort,
        "note_type": args.note_type,
        "time_filter": args.time_filter,
        "max_pages": args.max_pages,
    }


def topic_body(args) -> dict:
    return {
        "page_id": args.page,
        "topic_name": args.name,
        "sort": args.sort,
        "max_pages": args.max_pages,
    }


def comments_body(args) -> dict:
    body = {"include_sub": args.include_sub, "max_pages": args.max_pages,
            "sort_strategy": args.sort_strategy}
    if _is_link(args.input):
        body["share_text"] = args.input.strip()
    else:
        body["note_id"] = args.input.strip()
    return body


def replies_body(args) -> dict:
    body = {"parent_ids": [x.strip() for x in args.parent_ids.split(",") if x.strip()]}
    if _is_link(args.input):
        body["share_text"] = args.input.strip()
    else:
        body["note_id"] = args.input.strip()
    return body


def enrich_body(args) -> dict:
    return {"note_ids": [x.strip() for x in args.ids.split(",") if x.strip()]}


# 分页命令的续采映射：summary 字段 → 下一次请求体字段（与 backend/main.py 各路由契约一致）
RESUME_SPECS = {
    "user_notes": {"next_cursor": "resume_cursor"},
    "search_notes": {
        "next_page": "page",
        "search_id": "search_id",
        "search_session_id": "search_session_id",
    },
    "topic_notes": {
        "cursor_score": "cursor_score",
        "last_note_id": "last_note_id",
        "last_note_ct": "last_note_ct",
        "session_id": "session_id",
        "first_load_time": "first_load_time",
    },
    "comments": {
        "next_cursor": "resume_cursor",
        "next_index": "resume_index",
        "next_page_area": "resume_page_area",
    },
}

# 需要客户端累积去重 ID 的命令：data_type → 记录里的 ID 字段
SEEN_ID_KEYS = {"comments": "comment_id"}
