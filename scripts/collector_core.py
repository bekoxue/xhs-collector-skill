"""采集 skill 通用核心（产品无关）：配置、HTTP、设备指纹、错误映射、文件输出、断点续采。

仅使用 Python 标准库，零 pip 依赖。被 xhs.py（CLI 入口）与 product_xhs.py（产品声明）复用；
后续其他产品（抖音等）复制本文件 + 各自的 product_*.py 即可。
"""
from __future__ import annotations

import csv
import getpass
import hashlib
import http.client
import json
import math
import os
import platform
import re
import shlex
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

SKILL_VERSION = "0.1.7"

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

_RESULT_UNKNOWN_ACTION = (
    "请先运行 balance 查看最近流水，确认本次请求是否已扣费，再决定是否重试；"
    "持续失败请联系客服微信 baojian_xue"
)
_BALANCE_UNAVAILABLE_ACTION = (
    "余额查询暂不可用，请稍后重试；持续失败请联系客服微信 baojian_xue"
)


class CollectorError(Exception):
    def __init__(
        self, code: str, message: str, retry_after: int = 0, action: str | None = None
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after = retry_after
        self._action = action

    @property
    def exit_code(self) -> int:
        return _CODE_EXIT.get(self.code, EXIT_ERROR)

    @property
    def action(self) -> str:
        return self._action if self._action is not None else _CODE_ACTION.get(self.code, "")


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


def _result_unknown(message: str) -> CollectorError:
    return CollectorError(
        "SERVICE_UNAVAILABLE", message, action=_RESULT_UNKNOWN_ACTION
    )


def _response_failure(
    path: str, collection_message: str, balance_message: str
) -> CollectorError:
    if path == "/api/account/balance":
        return CollectorError(
            "SERVICE_UNAVAILABLE",
            balance_message,
            action=_BALANCE_UNAVAILABLE_ACTION,
        )
    return _result_unknown(collection_message)


def _is_dict_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(item, dict) for item in value)


def _is_finite_number(value: object) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def _is_ledger_list(value: object) -> bool:
    if not _is_dict_list(value):
        return False
    for entry in value:
        created_at = entry.get("created_at")
        if (
            not _is_finite_number(created_at)
            or not _is_finite_number(entry.get("amount"))
        ):
            return False
        try:
            datetime.fromtimestamp(created_at)
        except (OSError, OverflowError, TypeError, ValueError):
            return False
    return True


def _is_field_list(value: object) -> bool:
    return _is_dict_list(value) and all(
        isinstance(field.get("key"), str)
        and bool(field["key"].strip())
        and (field.get("label") is None or isinstance(field.get("label"), str))
        for field in value
    )


def _validate_success_response(
    path: str, data: object, expected_data_type: str = ""
) -> dict:
    valid = isinstance(data, dict) and data.get("ok") is True
    if valid and path == "/api/account/balance":
        balance = data.get("balance")
        valid = (
            _is_finite_number(balance)
            and _is_ledger_list(data.get("ledger"))
            and isinstance(data.get("license_info"), dict)
        )
    elif valid and path.startswith(("/api/collect/", "/api/enrich/")):
        fields = data.get("fields")
        valid = (
            isinstance(data.get("data_type"), str)
            and bool(data.get("data_type"))
            and (
                not expected_data_type
                or data.get("data_type") == expected_data_type
            )
            and _is_dict_list(data.get("records"))
            and (fields is None or _is_field_list(fields))
            and isinstance(data.get("summary"), dict)
        )
    if not valid:
        raise _response_failure(
            path,
            "服务响应结构异常。注意：服务端可能已完成采集并扣费，请先运行 "
            "balance 查看流水再决定是否重试",
            "余额查询服务响应结构异常，请稍后重试",
        )
    return data


def api_post(
    spec: dict,
    path: str,
    body: dict,
    api_key: str = "",
    timeout: int = 180,
    expected_data_type: str = "",
) -> dict:
    """POST JSON。仅对「确定请求未到服务端」的连接失败和 429 自动重试；
    超时、连接重置等结果不明的错误不重试，避免服务端已扣费后重复调用。"""
    url = resolve_base_url(spec) + path
    key = api_key or resolve_api_key(spec)
    if not key:
        raise CollectorError("INVALID_TOKEN", "尚未配置令牌，请先运行 configure 命令")
    payload = json.dumps(body, ensure_ascii=True).encode()
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
                data = json.loads(resp.read().decode("utf-8"))
                return _validate_success_response(path, data, expected_data_type)
        except urllib.error.HTTPError as e:
            retry_after = _retry_after_seconds((e.headers or {}).get("Retry-After"))
            try:
                error_body = e.read()
            except (OSError, http.client.HTTPException) as read_error:
                raise _response_failure(
                    path,
                    f"读取采集服务错误响应时连接中断：{read_error}。服务端可能已完成采集并扣费，请先运行 balance 查看流水再决定是否重试",
                    f"读取余额查询错误响应时连接中断：{read_error}，请稍后重试",
                )
            err = _parse_error(e.code, error_body, retry_after)
            if e.code == 429 and err.code == "RATE_LIMITED" and attempts <= 2:
                time.sleep(err.retry_after or min(60, 15 * attempts))
                continue
            if e.code >= 500:
                raise _response_failure(
                    path,
                    "采集服务返回异常。注意：服务端可能已完成采集并扣费，请先运行 "
                    "balance 查看流水再决定是否重试",
                    "余额查询服务暂时不可用，请稍后重试",
                )
            raise err
        except (UnicodeDecodeError, json.JSONDecodeError, http.client.IncompleteRead):
            raise _response_failure(
                path,
                "服务响应内容异常。注意：服务端可能已完成采集并扣费，请先运行 balance 查看流水再决定是否重试",
                "余额查询服务响应内容异常，请稍后重试",
            )
        except urllib.error.URLError as e:
            reason = getattr(e, "reason", e)
            if isinstance(reason, TimeoutError) or "timed out" in str(reason).lower():
                raise _response_failure(
                    path,
                    "请求超时。注意：服务端可能已完成采集并扣费，请先运行 balance 查看流水再决定是否重试（分页命令可用 --resume-file 续采）",
                    "余额查询请求超时，请稍后重试",
                )
            # 只有 DNS 解析失败、连接被拒绝能确认请求尚未到达服务端，可安全重试。
            # 连接重置等错误可能发生在服务端完成采集之后，自动重试会造成重复扣费。
            if isinstance(reason, (socket.gaierror, ConnectionRefusedError)) and attempts <= 2:
                time.sleep(2 * attempts)
                continue
            raise _response_failure(
                path,
                f"连接采集服务失败：{reason}。服务端可能已完成采集并扣费，请先运行 balance 查看流水再决定是否重试",
                f"连接余额查询服务失败：{reason}，请稍后重试",
            )
        except TimeoutError:
            raise _response_failure(
                path,
                "请求超时。注意：服务端可能已完成采集并扣费，请先运行 balance 查看流水再决定是否重试",
                "余额查询请求超时，请稍后重试",
            )
        except (OSError, http.client.HTTPException) as e:
            raise _response_failure(
                path,
                f"读取采集结果时发生网络或协议异常：{e}。服务端可能已完成采集并扣费，请先运行 balance 查看流水再决定是否重试",
                f"读取余额查询结果时发生网络或协议异常：{e}，请稍后重试",
            )


# ---------------------------------------------------------------------------
# 输出：全量落盘 + stdout 摘要（防撑爆智能体上下文）
# ---------------------------------------------------------------------------
def prepare_output_dir(out_dir: str) -> Path:
    """在付费请求前确认输出目录可创建且可真实写入。"""
    out = Path(out_dir)
    try:
        out.mkdir(parents=True, exist_ok=True)
        if not out.is_dir():
            raise NotADirectoryError(str(out))
        with tempfile.TemporaryFile(dir=out):
            pass
    except (OSError, UnicodeError) as exc:
        raise CollectorError(
            "INVALID_REQUEST",
            f"输出目录不可写：{out}",
            action="请更换可写的 --out-dir 后重新运行；本次采集请求尚未发送，不会扣费",
        ) from exc
    return out


def _slug(text: str, max_len: int = 24) -> str:
    text = re.sub(r"[^0-9A-Za-z一-鿿_-]+", "_", str(text or "")).strip("_")
    return text[:max_len] or "data"


def write_outputs(resp: dict, out_dir: str, fmt: str, name_hint: str = "") -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    data_type = resp.get("data_type") or "result"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    unique = uuid.uuid4().hex
    prefix = f"{data_type}_{_slug(name_hint)}" if name_hint else data_type
    base = f"{prefix}_{ts}_{unique}"
    paths = {}
    if fmt in ("json", "both"):
        p = out / f"{base}.json"
        with p.open(
            "x", encoding="utf-8", errors="backslashreplace"
        ) as fh:
            json.dump({
                "data_type": data_type,
                "fields": resp.get("fields") or [],
                "records": resp.get("records") or [],
                "summary": resp.get("summary") or {},
            }, fh, ensure_ascii=False, indent=1)
        paths["output_json"] = str(p)
    if fmt in ("csv", "both"):
        fields = resp.get("fields") or []
        records = resp.get("records") or []
        keys = [f.get("key") for f in fields if f.get("key")] or sorted(
            {k for r in records for k in r}
        )
        labels = {f.get("key"): f.get("label") or f.get("key") for f in fields}
        p = out / f"{base}.csv"
        with p.open(
            "x", newline="", encoding="utf-8-sig", errors="backslashreplace"
        ) as fh:
            w = csv.writer(fh)
            w.writerow([labels.get(k, k) for k in keys])
            for r in records:
                w.writerow([_csv_safe_cell(r.get(k, "")) for k in keys])
        paths["output_csv"] = str(p)
    return paths


def _csv_safe_cell(value):
    """阻止不可信采集文本被表格软件解释为公式，非字符串值保持原类型。"""
    if not isinstance(value, str):
        return value
    probe = value.lstrip(" \t\r\n")
    if probe.startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r")):
        return "'" + value
    return value


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
            "action", "warning", "resume_hint",
        )}
        rendered = json.dumps(slim, ensure_ascii=False)
        fallback = json.dumps(slim, ensure_ascii=True)
    else:
        rendered = json.dumps(obj, ensure_ascii=False, indent=1)
        fallback = json.dumps(obj, ensure_ascii=True, indent=1)
    try:
        print(rendered)
    except UnicodeEncodeError:
        print(fallback)


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
    run_id = uuid.uuid4().hex
    return Path(out_dir) / f".resume_{data_type}_{_slug(ident)}_{run_id}.json"


def resume_context(command: str, data_type: str, request_body: dict) -> dict:
    canonical = json.dumps(
        request_body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return {
        "version": 1,
        "command": command,
        "data_type": data_type,
        "request_fingerprint": hashlib.sha256(
            canonical.encode("utf-8", errors="surrogatepass")
        ).hexdigest(),
    }


def save_resume(
    path: Path, request_patch: dict, seen_ids: list, context: dict
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({
        "context": context,
        "request_patch": request_patch,
        "seen_ids": seen_ids,
        "saved_at": int(time.time()),
    }, ensure_ascii=False)
    temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temp_created = False
    try:
        with temp_path.open(
            "x", encoding="utf-8", errors="backslashreplace"
        ) as fh:
            temp_created = True
            fh.write(payload)
        os.replace(temp_path, path)
    finally:
        if temp_created:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass


def load_resume(path: str, expected_context: dict) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CollectorError("INVALID_REQUEST", f"续采文件不存在：{path}")
    except Exception:
        raise CollectorError("INVALID_REQUEST", f"续采文件损坏，请重新采集：{path}")
    if not isinstance(data, dict):
        raise CollectorError("INVALID_REQUEST", f"续采文件损坏，请重新采集：{path}")
    if data.get("context") != expected_context:
        raise CollectorError(
            "INVALID_REQUEST",
            "续采文件与当前命令或采集对象不匹配，请使用本任务生成的 resume_hint",
        )
    if not isinstance(data.get("request_patch"), dict) or not data["request_patch"]:
        raise CollectorError("INVALID_REQUEST", "续采文件没有有效断点，请重新发起采集")
    if not isinstance(data.get("seen_ids"), list):
        raise CollectorError("INVALID_REQUEST", f"续采文件损坏，请重新采集：{path}")
    return data


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
