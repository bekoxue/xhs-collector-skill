"""采集 skill 通用核心（产品无关）：配置、HTTP、设备指纹、错误映射、文件输出、断点续采。

仅使用 Python 标准库，零 pip 依赖。被 xhs.py（CLI 入口）与 product_xhs.py（产品声明）复用；
后续其他产品（抖音等）复制本文件 + 各自的 product_*.py 即可。
"""
from __future__ import annotations

import csv
import getpass
import hashlib
import json
import os
import platform
import re
import shlex
import socket
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

SKILL_VERSION = "0.1.2"

# 退出码约定（SKILL.md 同步维护）
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INVALID_TOKEN = 2
EXIT_INSUFFICIENT_BALANCE = 3
EXIT_LICENSE_INVALID = 4
EXIT_RATE_LIMITED = 5
EXIT_SERVICE_UNAVAILABLE = 6
EXIT_INVALID_REQUEST = 7
EXIT_DEVICE_MISMATCH = 8

_CODE_EXIT = {
    "INVALID_TOKEN": EXIT_INVALID_TOKEN,
    "PRODUCT_MISMATCH": EXIT_INVALID_TOKEN,
    "INSUFFICIENT_BALANCE": EXIT_INSUFFICIENT_BALANCE,
    "LICENSE_INVALID": EXIT_LICENSE_INVALID,
    "PATH_NOT_ALLOWED": EXIT_LICENSE_INVALID,
    "RATE_LIMITED": EXIT_RATE_LIMITED,
    "SERVICE_UNAVAILABLE": EXIT_SERVICE_UNAVAILABLE,
    "INVALID_REQUEST": EXIT_INVALID_REQUEST,
    "TOKEN_DEVICE_MISMATCH": EXIT_DEVICE_MISMATCH,
}

_CODE_ACTION = {
    "INSUFFICIENT_BALANCE": "充值后重跑本命令；分页命令用 --resume-file 从断点续采，不会重复扣费",
    "INVALID_TOKEN": "令牌无效或已失效（生成新令牌/修改密码都会作废旧令牌），请到网页端「我的账户→智能体接入」重新生成后运行 configure",
    "PRODUCT_MISMATCH": "该令牌属于其他产品，请在对应产品的网页端生成本产品令牌后运行 configure",
    "TOKEN_DEVICE_MISMATCH": "令牌已绑定其他设备。如您更换了电脑，请到网页端「我的账户→智能体接入」解绑设备或重新生成令牌",
    "LICENSE_INVALID": "请登录网页平台绑定/续费激活码后再使用",
    "RATE_LIMITED": "采集频率过高，请稍后重试",
    "SERVICE_UNAVAILABLE": "采集服务暂不可用，请稍后重试；持续失败请联系客服微信 baojian_xue",
    "INVALID_REQUEST": "请检查命令参数后重试",
}


class CollectorError(Exception):
    def __init__(self, code: str, message: str, retry_after: int = 0):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after = retry_after

    @property
    def exit_code(self) -> int:
        return _CODE_EXIT.get(self.code, EXIT_ERROR)

    @property
    def action(self) -> str:
        return _CODE_ACTION.get(self.code, "")


# ---------------------------------------------------------------------------
# 配置与凭证
# ---------------------------------------------------------------------------
def config_path(spec: dict) -> Path:
    return Path(os.path.expanduser(spec["config_dir"])) / "config.json"


def load_config(spec: dict) -> dict:
    p = config_path(spec)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(spec: dict, cfg: dict) -> Path:
    p = config_path(spec)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        p.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass
    return p


def resolve_api_key(spec: dict) -> str:
    """凭证优先级：环境变量（OpenClaw skills.entries 注入）> 配置文件（configure 命令写入）。"""
    key = (os.environ.get("COLLECTOR_API_KEY") or "").strip()
    if key:
        return key
    return (load_config(spec).get("api_key") or "").strip()


def resolve_base_url(spec: dict) -> str:
    """生产地址写死；仅显式开发模式允许 localhost 覆盖（防止对话内容诱导改地址）。"""
    if os.environ.get("COLLECTOR_DEV_MODE") == "1":
        dev = (os.environ.get("COLLECTOR_BASE_URL") or "").strip().rstrip("/")
        if dev.startswith("http://127.0.0.1") or dev.startswith("http://localhost"):
            return dev
    return spec["base_url"]


def device_fingerprint() -> str:
    """设备指纹：env 显式覆盖（容器/OpenClaw 注入通道）> 运行时硬件哈希。

    运行时计算而非落盘：拷贝配置文件到其他机器时指纹不同，服务端会拒绝。
    """
    explicit = (os.environ.get("COLLECTOR_DEVICE_ID") or "").strip()
    if explicit:
        return explicit[:64]
    basis = f"{platform.node()}|{uuid.getnode()}|{os.environ.get('USER') or os.environ.get('USERNAME') or ''}"
    return hashlib.sha256(basis.encode()).hexdigest()[:32]


def device_name() -> str:
    return (platform.node() or "unknown-host")[:64]


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _parse_error(status: int, body: bytes, retry_after: int = 0) -> CollectorError:
    detail = None
    try:
        detail = json.loads(body.decode("utf-8", "replace")).get("detail")
    except Exception:
        pass
    if isinstance(detail, dict) and detail.get("code"):
        return CollectorError(
            str(detail["code"]), str(detail.get("message") or ""), retry_after
        )
    message = detail if isinstance(detail, str) else f"HTTP {status}"
    fallback = {
        400: "INVALID_REQUEST", 401: "INVALID_TOKEN", 402: "INSUFFICIENT_BALANCE",
        403: "LICENSE_INVALID", 429: "RATE_LIMITED",
    }
    code = fallback.get(status, "SERVICE_UNAVAILABLE" if status >= 500 else "INVALID_REQUEST")
    return CollectorError(code, message, retry_after)


def _retry_after_seconds(value: str | None) -> int:
    """解析服务端 Retry-After 秒数，并限制最长自动等待时间。"""
    try:
        return min(300, max(1, int(value or "0")))
    except (TypeError, ValueError):
        return 0


def api_post(spec: dict, path: str, body: dict, api_key: str = "", timeout: int = 180) -> dict:
    """POST JSON。仅对「确定请求未到服务端」的连接失败和 429 自动重试；
    超时、连接重置等结果不明的错误不重试，避免服务端已扣费后重复调用。"""
    url = resolve_base_url(spec) + path
    key = api_key or resolve_api_key(spec)
    if not key:
        raise CollectorError("INVALID_TOKEN", "尚未配置令牌，请先运行 configure 命令")
    payload = json.dumps(body, ensure_ascii=False).encode()
    headers = {
        "Content-Type": "application/json",
        "X-Api-Key": key,
        "X-Device-Id": device_fingerprint(),
        "X-Device-Name": device_name(),
        "User-Agent": f"{spec['product']}-collector-skill/{SKILL_VERSION}",
    }
    attempts = 0
    while True:
        attempts += 1
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            retry_after = _retry_after_seconds((e.headers or {}).get("Retry-After"))
            err = _parse_error(e.code, e.read(), retry_after)
            if err.code == "RATE_LIMITED" and attempts <= 2:
                time.sleep(err.retry_after or min(60, 15 * attempts))
                continue
            raise err
        except urllib.error.URLError as e:
            reason = getattr(e, "reason", e)
            if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
                raise CollectorError(
                    "SERVICE_UNAVAILABLE",
                    "请求超时。注意：服务端可能已完成采集并扣费，请先运行 balance 查看流水再决定是否重试（分页命令可用 --resume-file 续采）",
                )
            # 只有 DNS 解析失败、连接被拒绝能确认请求尚未到达服务端，可安全重试。
            # 连接重置等错误可能发生在服务端完成采集之后，自动重试会造成重复扣费。
            if isinstance(reason, (socket.gaierror, ConnectionRefusedError)) and attempts <= 2:
                time.sleep(2 * attempts)
                continue
            raise CollectorError(
                "SERVICE_UNAVAILABLE",
                f"连接采集服务失败：{reason}。服务端可能已完成采集并扣费，请先运行 balance 查看流水再决定是否重试",
            )
        except TimeoutError:
            raise CollectorError(
                "SERVICE_UNAVAILABLE",
                "请求超时。注意：服务端可能已完成采集并扣费，请先运行 balance 查看流水再决定是否重试",
            )


# ---------------------------------------------------------------------------
# 输出：全量落盘 + stdout 摘要（防撑爆智能体上下文）
# ---------------------------------------------------------------------------
def _slug(text: str, max_len: int = 24) -> str:
    text = re.sub(r"[^0-9A-Za-z一-鿿_-]+", "_", str(text or "")).strip("_")
    return text[:max_len] or "data"


def write_outputs(resp: dict, out_dir: str, fmt: str, name_hint: str = "") -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    data_type = resp.get("data_type") or "result"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{data_type}_{_slug(name_hint)}_{ts}" if name_hint else f"{data_type}_{ts}"
    paths = {}
    if fmt in ("json", "both"):
        p = out / f"{base}.json"
        p.write_text(json.dumps({
            "data_type": data_type,
            "fields": resp.get("fields") or [],
            "records": resp.get("records") or [],
            "summary": resp.get("summary") or {},
        }, ensure_ascii=False, indent=1), encoding="utf-8")
        paths["output_json"] = str(p)
    if fmt in ("csv", "both"):
        fields = resp.get("fields") or []
        records = resp.get("records") or []
        keys = [f.get("key") for f in fields if f.get("key")] or sorted(
            {k for r in records for k in r}
        )
        labels = {f.get("key"): f.get("label") or f.get("key") for f in fields}
        p = out / f"{base}.csv"
        with p.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.writer(fh)
            w.writerow([labels.get(k, k) for k in keys])
            for r in records:
                w.writerow([r.get(k, "") for k in keys])
        paths["output_csv"] = str(p)
    return paths


def build_preview(resp: dict, limit: int = 3, field_limit: int = 4) -> list:
    fields = resp.get("fields") or []
    keys = [f.get("key") for f in fields[:field_limit] if f.get("key")]
    preview = []
    for rec in (resp.get("records") or [])[:limit]:
        if keys:
            preview.append({k: rec.get(k) for k in keys})
        else:
            preview.append(dict(list(rec.items())[:field_limit]))
    return preview


def balance_yuan(resp: dict):
    bal = resp.get("balance")
    if bal is None:
        bal = (resp.get("billing") or {}).get("balance")  # 兼容其他产品的 envelope
    return round(bal / 1000, 3) if isinstance(bal, (int, float)) else None


def emit(obj: dict, quiet: bool = False) -> None:
    if quiet:
        slim = {k: v for k, v in obj.items() if k in (
            "ok", "count", "requested", "skipped_insufficient", "skipped_request_limit",
            "stop_reason", "has_more", "output_json", "output_csv", "error_code", "message",
            "warning", "resume_hint",
        )}
        print(json.dumps(slim, ensure_ascii=False))
    else:
        print(json.dumps(obj, ensure_ascii=False, indent=1))


def emit_error(err: CollectorError, quiet: bool = False) -> int:
    emit({
        "ok": False,
        "error_code": err.code,
        "message": err.message,
        "action": err.action,
    }, quiet)
    return err.exit_code


# ---------------------------------------------------------------------------
# 断点续采文件
# ---------------------------------------------------------------------------
def resume_file_path(out_dir: str, data_type: str, ident: str) -> Path:
    return Path(out_dir) / f".resume_{data_type}_{_slug(ident)}.json"


def save_resume(path: Path, request_patch: dict, seen_ids: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "request_patch": request_patch,
        "seen_ids": seen_ids,
        "saved_at": int(time.time()),
    }, ensure_ascii=False), encoding="utf-8")


def load_resume(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CollectorError("INVALID_REQUEST", f"续采文件不存在：{path}")
    except Exception:
        raise CollectorError("INVALID_REQUEST", f"续采文件损坏，请重新采集：{path}")


def build_resume_hint(resume_path: Path) -> str:
    argv = [a for a in sys.argv[1:]]
    if "--resume-file" in argv:
        i = argv.index("--resume-file")
        del argv[i:i + 2]
    parts = ["python3", sys.argv[0]] + argv + ["--resume-file", str(resume_path)]
    if os.name == "nt":
        return subprocess.list2cmdline(parts)
    return shlex.join(parts)


# ---------------------------------------------------------------------------
# configure / balance（产品无关命令）
# ---------------------------------------------------------------------------
def cmd_configure(spec: dict, api_key: str = "", quiet: bool = False) -> int:
    key = (api_key or "").strip()
    if not key:
        print(f"请到 {spec['base_url']} 登录 → 我的账户 → 智能体接入 → 生成令牌，然后粘贴到下方。", file=sys.stderr)
        key = getpass.getpass("请粘贴令牌（输入不回显）: ").strip()
    if not key.startswith(spec["key_prefix"]):
        return emit_error(CollectorError(
            "INVALID_TOKEN", f"令牌格式不正确（应以 {spec['key_prefix']} 开头），请从网页端复制完整令牌"), quiet)
    try:
        resp = api_post(spec, "/api/account/balance", {}, api_key=key)
    except CollectorError as e:
        return emit_error(e, quiet)
    save_config(spec, {"api_key": key, "product": spec["product"]})
    info = resp.get("license_info") or {}
    emit({
        "ok": True,
        "message": f"配置完成，令牌已绑定本机（{device_name()}）",
        "config_file": str(config_path(spec)),
        "balance_yuan": balance_yuan(resp),
        "license_status": info.get("status") or ("有效" if info.get("valid") else "未知"),
        "license_expires_at": info.get("expires_at") or "",
    }, quiet)
    return EXIT_OK


def cmd_balance(spec: dict, quiet: bool = False) -> int:
    try:
        resp = api_post(spec, "/api/account/balance", {})
    except CollectorError as e:
        return emit_error(e, quiet)
    info = resp.get("license_info") or {}
    recent = [
        {
            "time": datetime.fromtimestamp(l.get("created_at") or 0).strftime("%Y-%m-%d %H:%M"),
            "type": l.get("type"),
            "channel": "智能体" if l.get("channel") == "agent" else "网页",
            "endpoint": l.get("endpoint") or "",
            "amount_yuan": round((l.get("amount") or 0) / 1000, 3),
        }
        for l in (resp.get("ledger") or [])[:10]
    ]
    emit({
        "ok": True,
        "balance_yuan": balance_yuan(resp),
        "license_status": info.get("status") or ("有效" if info.get("valid") else "未知"),
        "license_expires_at": info.get("expires_at") or "",
        "recent_ledger": recent,
    }, quiet)
    return EXIT_OK
