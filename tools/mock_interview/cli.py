"""面向 Codex 的 JSON 命令行入口。"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from . import VERSION
from .common import AppError, dumps, keys, require
from .importer import import_markdown, preview
from .service import Service, WRITE_FIELDS
from .store import Store
from .transfer import backup_create, export_markdown


class Parser(argparse.ArgumentParser):
    def format_help(self):
        return (super().format_help().replace("usage:", "用法：").replace("positional arguments:", "位置参数：")
                .replace("options:", "选项：").replace("show this help message and exit", "显示帮助并退出")
                .replace("show program's version number and exit", "显示版本并退出"))

    def error(self, message):
        raise AppError("INVALID_INPUT", "命令参数不正确", {"detail": message})


def parser():
    root = Parser(description="本地自适应面试记录工具；正文通过 UTF-8 JSON 输入。")
    root.add_argument("--workspace", default=".", help="工作区绝对路径，默认当前目录")
    root.add_argument("--version", action="version", version=VERSION)
    commands = root.add_subparsers(dest="group", required=True)
    groups = {}
    for operation in list(WRITE_FIELDS) + ["topic list", "topic show", "concept list", "session show", "attempt show",
                                         "report weaknesses", "report session", "export markdown", "import markdown", "backup create"]:
        group, action = operation.split()
        if group not in groups:
            groups[group] = commands.add_parser(group).add_subparsers(dest="action", required=True)
        cmd = groups[group].add_parser(action)
        if operation in WRITE_FIELDS or group in ("import", "export", "backup"):
            cmd.add_argument("--input", required=True, help="JSON 文件路径；- 表示标准输入")
        elif operation in ("topic show", "concept list", "report weaknesses"):
            cmd.add_argument("--topic", required=True)
        elif operation in ("session show", "report session"):
            cmd.add_argument("--session", required=True)
        elif operation == "attempt show":
            cmd.add_argument("--attempt", required=True)
    cmd = commands.add_parser("init", help="初始化空数据库，不创建主题或评分")
    cmd.add_argument("--input", required=True, help="含 request_id 的 JSON")
    cmd = commands.add_parser("next", help="只读推荐下一题")
    cmd.add_argument("--session", required=True)
    cmd = commands.add_parser("check", help="只读检查数据一致性")
    cmd.add_argument("--topic")
    return root


def load_input(filename):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "JSON 包含重复字段", details={"field": key})
            result[key] = value
        return result
    raw = sys.stdin.read() if filename == "-" else Path(filename).read_text(encoding="utf-8")
    value = json.loads(raw, object_pairs_hook=pairs,
                       parse_constant=lambda x: (_ for _ in ()).throw(AppError("INVALID_INPUT", "JSON 不支持非有限数值")))
    require(isinstance(value, dict), "输入必须是 JSON 对象")
    return value


def main(argv=None):
    store = None
    workspace = str(Path.cwd())
    try:
        args = parser().parse_args(argv)
        workspace = str(Path(args.workspace).expanduser().resolve())
        operation = args.group + (" " + args.action if hasattr(args, "action") else "")
        data = load_input(args.input) if hasattr(args, "input") else None
        # 预检无需数据库，也不创建目录或初始化文件。
        if operation == "import markdown" and data.get("mode", "preview") == "preview":
            result = preview(data)
        else:
            if operation == "init":
                keys(data, ["request_id"])
                require(isinstance(data.get("request_id"), str) and data["request_id"].strip(), "request_id 必须是非空字符串")
            store = Store(workspace, initialize=operation == "init")
            service = Service(store)
            if operation == "init":
                result = store.write(operation, data, lambda: {"database": str(store.path), "initialized": True})
            elif operation in WRITE_FIELDS:
                result = service.write(operation, data)
            elif operation == "export markdown":
                result = export_markdown(service, data)
            elif operation == "backup create":
                result = backup_create(service, data)
            elif operation == "import markdown":
                result = import_markdown(service, data)
            else:
                readers = {
                    "topic list": lambda: {"topics": store.rows("SELECT * FROM topics ORDER BY id")},
                    "topic show": lambda: service.topic_show(args.topic),
                    "concept list": lambda: {"concepts": service.concepts(args.topic)},
                    "session show": lambda: service.session_show(args.session),
                    "attempt show": lambda: service.attempt_show(args.attempt),
                    "report weaknesses": lambda: service.report_weaknesses(args.topic),
                    "report session": lambda: service.report_session(args.session),
                    "next": lambda: service.next(args.session),
                    "check": lambda: service.check(args.topic),
                }
                result = store.read(readers[operation])
        print(dumps(dict(ok=True, schema_version=1, workspace=workspace, data=result, warnings=result.get("warnings", []))))
        return 0
    except AppError as exc:
        error = exc
    except sqlite3.IntegrityError as exc:
        error = AppError("INVALID_STATE", "数据违反唯一性或完整性约束", {"detail": str(exc)}, 4)
    except sqlite3.Error as exc:
        busy = "locked" in str(exc).lower() or "busy" in str(exc).lower()
        error = AppError("DATABASE_BUSY" if busy else "STORAGE_ERROR", "数据库暂不可写" if busy else "数据库操作失败",
                         {"detail": str(exc)}, 5)
    except (OSError, UnicodeError) as exc:
        error = AppError("STORAGE_ERROR", "本地文件读写失败", {"detail": str(exc)}, 5)
    except (ValueError, TypeError) as exc:
        error = AppError("INVALID_INPUT", "输入内容不符合格式", {"detail": str(exc)})
    finally:
        if store is not None:
            store.close()
    print(dumps(dict(ok=False, schema_version=1, workspace=workspace,
                     error=dict(code=error.code, message=error.message, details=error.details))))
    return error.exit_code
