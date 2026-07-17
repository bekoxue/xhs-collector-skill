#!/usr/bin/env python3
"""小红书采集 skill CLI（零 pip 依赖，Python 3.9+）。

用法示例：
  python3 xhs.py configure                 # 首次配置：粘贴网页端生成的令牌
  python3 xhs.py balance                   # 余额与最近流水
  python3 xhs.py note <链接|note_id>
  python3 xhs.py user-info <主页链接|user_id>
  python3 xhs.py user-notes <user_id> --max-pages 3
  python3 xhs.py search 关键词 --max-pages 2
  python3 xhs.py topic --page <话题页ID或链接> --name <话题名>
  python3 xhs.py comments <链接|note_id> --include-sub
  python3 xhs.py replies <链接|note_id> --parent-ids id1,id2
  python3 xhs.py enrich --ids id1,id2

输出约定：records 全量写入 --out-dir 下的 JSON/CSV 文件，stdout 只打印摘要
（count / 断点 / 文件路径 / 余额 / 前 3 条预览），避免大结果撑爆智能体上下文。
"""
from __future__ import annotations

import argparse
import sys

import collector_core as core
import product_xhs as product

SPEC = product.SPEC


def add_common(
    p: argparse.ArgumentParser, paginated: bool = False, resumable: bool = False
) -> None:
    p.add_argument("--out-dir", default=SPEC["default_out_dir"], help="结果输出目录")
    p.add_argument("--format", choices=("json", "csv", "both"), default="json")
    p.add_argument("--quiet", action="store_true", help="只输出最精简的一行 JSON")
    if paginated:
        p.add_argument("--max-pages", type=int, default=1, help="本次最多采集页数（每页计费一次，默认 1）")
    if paginated or resumable:
        p.add_argument("--resume-file", default="", help="断点续采文件（上次输出的 resume_hint 会带上）")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="xhs.py", description="小红书采集 skill CLI")
    ap.add_argument("--version", action="version", version=f"xhs-collector-skill/{core.SKILL_VERSION}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("configure", help="首次配置：保存网页端生成的令牌")
    p.add_argument("--api-key", default="", help="令牌（省略则交互式隐藏输入，推荐）")
    p.add_argument("--quiet", action="store_true")

    p = sub.add_parser("balance", help="查询余额与最近流水")
    p.add_argument("--quiet", action="store_true")

    p = sub.add_parser("note", help="笔记详情（图文/视频）")
    p.add_argument("input", help="笔记链接 / 分享文本 / note_id")
    p.add_argument("--kind", choices=("auto", "image", "video"), default="auto")
    add_common(p)

    p = sub.add_parser("user-info", help="博主主页信息")
    p.add_argument("input", help="主页链接 / 分享链接 / user_id")
    add_common(p)

    p = sub.add_parser("user-notes", help="博主笔记列表（分页）")
    p.add_argument("input", help="主页链接 / user_id")
    add_common(p, paginated=True)

    p = sub.add_parser("search", help="关键词搜索笔记（分页）")
    p.add_argument("keyword")
    p.add_argument("--sort", default="general", help="排序：general/time_descending/popularity_descending")
    p.add_argument("--note-type", default="不限", dest="note_type")
    p.add_argument("--time-filter", default="不限", dest="time_filter")
    add_common(p, paginated=True)

    p = sub.add_parser("topic", help="话题笔记列表（分页）")
    p.add_argument("--page", required=True, help="话题页面 ID 或话题页链接")
    p.add_argument("--name", required=True, help="话题名称")
    p.add_argument("--sort", choices=("trend", "time"), default="trend")
    add_common(p, paginated=True)

    p = sub.add_parser("comments", help="笔记评论（分页，可含楼中楼）")
    p.add_argument("input", help="笔记链接 / note_id")
    p.add_argument("--include-sub", action="store_true", help="同时采集楼中楼回复（消费更高）")
    p.add_argument("--sort-strategy", default="latest_v2", dest="sort_strategy")
    add_common(p, paginated=True)

    p = sub.add_parser("replies", help="指定评论的楼中楼回复")
    p.add_argument("input", help="笔记链接 / note_id")
    p.add_argument("--parent-ids", required=True, help="父评论 ID，逗号分隔")
    add_common(p, resumable=True)

    p = sub.add_parser("enrich", help="批量补全笔记互动数据")
    p.add_argument("--ids", required=True, help="note_id 列表，逗号分隔")
    add_common(p, resumable=True)
    return ap


# 命令 → (端点, 请求体构建器, 断点标识取值, data_type)
COMMANDS = {
    "note": ("/api/collect/image_note", product.note_body, None, "image_note"),
    "user-info": ("/api/collect/user_info", product.user_input_body, None, "user_info"),
    "user-notes": ("/api/collect/user_notes", product.user_notes_body,
                   lambda a: a.input, "user_notes"),
    "search": ("/api/collect/search_notes", product.search_body,
               lambda a: a.keyword, "search_notes"),
    "topic": ("/api/collect/topic_notes", product.topic_body,
              lambda a: a.name, "topic_notes"),
    "comments": ("/api/collect/comments", product.comments_body,
                 lambda a: a.input, "comments"),
    "replies": ("/api/collect/comment_replies", product.replies_body, None, "comment_replies"),
    "enrich": ("/api/enrich/notes", product.enrich_body, None, "enrich_notes"),
}


def run_collect(args) -> int:
    endpoint, body_fn, ident_fn, data_type = COMMANDS[args.cmd]
    body = body_fn(args)
    ident = ident_fn(args) if ident_fn else ""
    context = core.resume_context(args.cmd, data_type, body)

    seen_ids: list = []
    if getattr(args, "resume_file", ""):
        saved = core.load_resume(args.resume_file, context)
        body.update(saved.get("request_patch") or {})
        seen_ids = saved.get("seen_ids") or []
        seen_key = product.SEEN_ID_KEYS.get(data_type)
        if seen_key and seen_ids:
            body["seen_ids"] = seen_ids

    core.prepare_output_dir(args.out_dir)
    resp = core.api_post(
        SPEC, endpoint, body, expected_data_type=data_type
    )
    try:
        paths = core.write_outputs(
            resp, args.out_dir, args.format, name_hint=ident or args.cmd
        )
    except (OSError, UnicodeError) as exc:
        raise core.CollectorError(
            "INVALID_REQUEST",
            f"采集结果已返回，但未能完整写入输出目录：{args.out_dir}",
            action=(
                "本次请求可能已扣费，请勿直接重新采集；请先运行 balance 查看流水，"
                "确认后更换可写的 --out-dir，持续失败请联系客服微信 baojian_xue"
            ),
        ) from exc
    summary = resp.get("summary") or {}
    out = {
        "ok": True,
        "data_type": resp.get("data_type") or data_type,
        "count": summary.get("count", len(resp.get("records") or [])),
        **({"pages": summary["pages"]} if "pages" in summary else {}),
        **({"requested": summary["requested"]} if "requested" in summary else {}),
        **({"skipped_insufficient": summary["skipped_insufficient"]}
           if "skipped_insufficient" in summary else {}),
        **({"skipped_request_limit": summary["skipped_request_limit"]}
           if "skipped_request_limit" in summary else {}),
        "stop_reason": summary.get("stop_reason"),
        "has_more": bool(summary.get("has_more") or summary.get("can_continue")),
        **paths,
        "balance_yuan": core.balance_yuan(resp),
        "preview": core.build_preview(resp),
    }
    if resp.get("errors"):
        out["errors"] = resp["errors"]

    warnings = []
    resume_spec = product.RESUME_SPECS.get(data_type)
    if resume_spec and out["has_more"] and hasattr(args, "resume_file"):
        patch = {}
        for summary_field, request_field in resume_spec.items():
            value = summary.get(summary_field)
            if value not in (None, ""):
                patch[request_field] = value
        seen_key = product.SEEN_ID_KEYS.get(data_type)
        new_seen = seen_ids
        if seen_key:
            new_seen = seen_ids + [
                r.get(seen_key) for r in (resp.get("records") or []) if r.get(seen_key)
            ]
        resume_path = core.resume_file_path(args.out_dir, data_type, ident or args.cmd)
        try:
            core.save_resume(resume_path, patch, new_seen, context)
        except (OSError, UnicodeError):
            warnings.append(
                "采集结果已保存，但断点文件写入失败；本次请求可能已扣费，请勿从头重采，"
                "请先运行 balance 查看流水"
            )
        else:
            out["resume_hint"] = core.build_resume_hint(resume_path)
    if summary.get("stop_reason") == "insufficient_balance":
        if out.get("resume_hint"):
            warnings.append(
                f"余额已耗尽，已保存本次采集的 {out['count']} 条结果（已扣费部分不会丢失）。"
                "充值后用 resume_hint 中的命令续采，不会重复扣费。充值请添加微信 baojian_xue。"
            )
        else:
            warnings.append(
                f"余额已耗尽，已保存本次采集的 {out['count']} 条结果，但断点文件未能保存。"
                "请勿从头重采；请先运行 balance 查看流水并联系客服微信 baojian_xue。"
            )
    elif summary.get("stop_reason") == "reached_request_limit":
        if out.get("resume_hint"):
            warnings.append(
                "已达到单次请求的安全消费上限，本次结果和断点均已保存。"
                "请运行 resume_hint 中的命令继续，续采不会重复请求已完成的数据。"
            )
        else:
            warnings.append("已达到单次请求的安全消费上限，请分批继续采集。")
    if warnings:
        out["warning"] = " ".join(warnings)
    core.emit(out, args.quiet)
    return core.EXIT_OK


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.cmd == "configure":
            return core.cmd_configure(SPEC, args.api_key, args.quiet)
        if args.cmd == "balance":
            return core.cmd_balance(SPEC, args.quiet)
        return run_collect(args)
    except core.CollectorError as e:
        return core.emit_error(e, getattr(args, "quiet", False))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
