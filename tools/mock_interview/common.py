"""共享的输入校验与错误契约。"""

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone


class AppError(Exception):
    def __init__(self, code, message, details=None, exit_code=2):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.exit_code = exit_code


def require(condition, message, code="INVALID_INPUT", details=None, exit_code=2):
    if not condition:
        raise AppError(code, message, details, exit_code)


def dumps(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else dumps(value).encode("utf-8")).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def uid(prefix):
    return prefix + "-" + uuid.uuid4().hex


def text(data, key, default=None):
    value = data.get(key, default)
    require(isinstance(value, str) and bool(value.strip()), key + " 必须是非空字符串")
    return value


def identifier(data, key="id", topic=False):
    value = text(data, key)
    pattern = r"[a-z0-9]+(?:-[a-z0-9]+)*" if topic else r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}"
    require(len(value) <= 128 and re.fullmatch(pattern, value), key + " 格式不合法")
    return value


def integer(data, key, default=None, minimum=0, maximum=1000000):
    value = data.get(key, default)
    require(type(value) is int and minimum <= value <= maximum, key + " 超出整数范围")
    return value


def boolean(data, key, default=False):
    value = data.get(key, default)
    require(type(value) is bool, key + " 必须是布尔值")
    return value


def strings(data, key, default=None):
    value = data.get(key, [] if default is None else default)
    require(isinstance(value, list) and all(isinstance(x, str) and x.strip() for x in value),
            key + " 必须是非空字符串组成的数组")
    return value


def keys(data, allowed):
    require(isinstance(data, dict), "输入必须是 JSON 对象")
    unknown = set(data) - set(allowed)
    require(not unknown, "存在未支持的字段", details={"fields": sorted(unknown)})


def utc_time(value):
    require(isinstance(value, str), "时间必须是 ISO 8601 字符串")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(parsed.tzinfo is not None, "时间必须包含时区")
        return parsed.astimezone(timezone.utc).isoformat(timespec="microseconds")
    except ValueError as exc:
        raise AppError("INVALID_INPUT", "时间格式不正确") from exc
