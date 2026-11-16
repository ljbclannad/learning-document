"""数据库事务、幂等请求与修订号。"""

import json
import sqlite3
from pathlib import Path

from .common import AppError, digest, dumps, now, require, text


class Store:
    def __init__(self, workspace, initialize=False):
        self.workspace = Path(workspace).expanduser().resolve()
        require(self.workspace.is_dir(), "工作区目录不存在")
        self.path = self.workspace / "面试训练记录/.state/training.sqlite3"
        if not initialize:
            require(self.path.is_file(), "尚未初始化，请先执行 init", "NOT_INITIALIZED", exit_code=3)
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path.as_uri() + ("?mode=rwc" if initialize else "?mode=rw"),
                                  uri=True, timeout=2, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        existing = self.one("SELECT name FROM sqlite_master WHERE type='table' AND name='app_meta'")
        version = self.one("SELECT value FROM app_meta WHERE key='schema_version'") if existing else None
        if existing:
            require(version is not None and version["value"] == "1", "数据库结构版本不受支持", "INVALID_STATE", exit_code=4)
        elif self.one("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1"):
            raise AppError("INVALID_STATE", "目标文件不是面试工具数据库，未修改其结构", exit_code=4)
        if initialize:
            # 同一个初始化事务可安全重试，不清空既有数据。
            self.db.executescript("BEGIN IMMEDIATE;\n" + Path(__file__).with_name("schema.sql").read_text()
                                  + "\nCOMMIT;")
        version = self.one("SELECT value FROM app_meta WHERE key='schema_version'")
        require(version is not None and version["value"] == "1",
                "数据库结构版本不受支持", "INVALID_STATE", exit_code=4)

    def close(self):
        self.db.close()

    def one(self, sql, args=()):
        row = self.db.execute(sql, args).fetchone()
        return dict(row) if row is not None else None

    def rows(self, sql, args=()):
        return [dict(row) for row in self.db.execute(sql, args)]

    def insert(self, table, data):
        # 表名与列名仅来自程序内部，用户输入均绑定为参数。
        columns = ",".join(data)
        self.db.execute(f"INSERT INTO {table} ({columns}) VALUES ({','.join('?' for _ in data)})",
                        tuple(data.values()))

    def get(self, table, key):
        row = self.one(f"SELECT * FROM {table} WHERE id=?", (key,))
        require(row is not None, "记录不存在", "NOT_FOUND", {"table": table, "id": key}, 3)
        return row

    def revision(self):
        return int(self.one("SELECT value FROM app_meta WHERE key='data_revision'")["value"])

    def order(self):
        return self.one("SELECT COALESCE(MAX(occurred_order),0)+1 AS n FROM attempt_events")["n"]

    def check_revision(self, row, data):
        require(type(data.get("expected_revision")) is int, "expected_revision 必须是整数")
        require(row["revision"] == data["expected_revision"], "记录已变化，请读取最新版本",
                "REVISION_CONFLICT", {"current_revision": row["revision"]}, 4)

    def bump(self, table, key):
        self.db.execute(f"UPDATE {table} SET revision=revision+1 WHERE id=?", (key,))

    def write(self, operation, data, callback):
        request_id = text(data, "request_id")
        fingerprint = digest({"operation": operation, "input": data})
        self.db.execute("BEGIN IMMEDIATE")
        try:
            prior = self.one("SELECT * FROM write_requests WHERE request_id=?", (request_id,))
            if prior:
                require(prior["payload_hash"] == fingerprint, "相同请求 ID 携带了不同内容",
                        "IDEMPOTENCY_CONFLICT", exit_code=4)
                result = json.loads(prior["response_json"])
                result["replayed"] = True
            else:
                result = callback()
                revision = self.revision() + 1
                self.db.execute("UPDATE app_meta SET value=? WHERE key='data_revision'", (str(revision),))
                result.update(data_revision=revision, replayed=False)
                self.insert("write_requests", dict(request_id=request_id, operation=operation,
                            payload_hash=fingerprint, response_json=dumps(result), created_at=now()))
            self.db.execute("COMMIT")
            return result
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def read(self, callback):
        self.db.execute("BEGIN")
        try:
            result = callback()
            self.db.execute("COMMIT")
            return result
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
