"""本地SQLite事务实验与发布状态模型，不连接任何业务库或RabbitMQ。"""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import tempfile
import unittest


ROOT = Path(tempfile.mkdtemp(prefix="reliable-boundary-lab-"))


@contextmanager
def transaction(db):
    db.execute("BEGIN IMMEDIATE")
    try:
        yield
        db.commit()
    except Exception:
        db.rollback()
        raise


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=0, isolation_level=None)

    def create(self, event="e1", fail=False):
        with transaction(self.db):
            self.db.execute("INSERT INTO orders VALUES (?, ?)", (event, "CREATED"))
            if fail:
                raise RuntimeError("模拟写入事件前失败")
            self.db.execute("INSERT INTO outbox VALUES (?, ?)", (event, "PENDING"))

    def consume(self, consumer="projection", event="e1", payload_hash="hash1", fail=False):
        with transaction(self.db):
            old = self.db.execute(
                "SELECT payload_hash FROM inbox WHERE consumer=? AND event_id=?",
                (consumer, event),
            ).fetchone()
            if old:
                if old[0] != payload_hash:
                    raise Conflict("同事件身份的载荷冲突")
                return "DUPLICATE"
            # 本实验BEGIN IMMEDIATE已串行化写入；生产并发还需处理唯一键冲突。
            self.db.execute("INSERT INTO inbox VALUES (?, ?, ?)", (consumer, event, payload_hash))
            self.db.execute("UPDATE effects SET n=n+1 WHERE consumer=?", (consumer,))
            if fail:
                raise RuntimeError("模拟业务提交前失败")
        return "COMMITTED"

    def count(self, table):
        assert table in {"orders", "outbox", "inbox"}
        return self.db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]

    def effect(self, consumer="projection"):
        return self.db.execute("SELECT n FROM effects WHERE consumer=?", (consumer,)).fetchone()[0]

    def revoke(self):
        with transaction(self.db):
            self.db.execute("UPDATE policy SET allowed=0, version=version+1")

    def protected_write(self):
        with transaction(self.db):
            allowed = self.db.execute("SELECT allowed FROM policy").fetchone()[0]
            if not allowed:
                return False
            self.db.execute("UPDATE managed_resource SET value=value+1")
        return True


@dataclass
class PublisherModel:
    """输入为适配器已关联的confirm/return结果；不模拟网络回调顺序。"""
    status: str = "PENDING"
    token: int = 0
    lease_until: int = 0
    attempts: int = 0
    max_attempts: int = 3

    def claim(self, now, ttl=10):
        if self.status == "IN_FLIGHT" and now >= self.lease_until:
            self.status = "RETRY_WAIT"
        if self.status not in {"PENDING", "RETRY_WAIT"}:
            raise Conflict("当前状态不能领取")
        if self.attempts >= self.max_attempts:
            self.status = "MANUAL"
            return None
        self.token += 1
        self.attempts += 1
        self.lease_until = now + ttl
        self.status = "IN_FLIGHT"
        return self.token

    def result(self, token, now, ack, returned):
        if self.status != "IN_FLIGHT" or token != self.token or now >= self.lease_until:
            return False
        self.status = "PUBLISHED" if ack and not returned else "RETRY_WAIT"
        return True


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.path = ROOT / (self._testMethodName + ".sqlite")
        self.store = Store(self.path)
        self.store.db.executescript("""
          CREATE TABLE orders(id TEXT PRIMARY KEY, status TEXT NOT NULL);
          CREATE TABLE outbox(event_id TEXT PRIMARY KEY, status TEXT NOT NULL);
          CREATE TABLE inbox(consumer TEXT, event_id TEXT, payload_hash TEXT NOT NULL,
                             PRIMARY KEY(consumer, event_id));
          CREATE TABLE effects(consumer TEXT PRIMARY KEY, n INTEGER NOT NULL);
          INSERT INTO effects VALUES('projection', 0), ('notification', 0);
          CREATE TABLE policy(version INTEGER, allowed INTEGER);
          INSERT INTO policy VALUES(1, 1);
          CREATE TABLE managed_resource(value INTEGER);
          INSERT INTO managed_resource VALUES(0);
        """)

    def tearDown(self):
        self.store.db.close()

    def test_business_and_outbox_rollback_together(self):
        with self.assertRaises(RuntimeError):
            self.store.create(fail=True)
        self.assertEqual((self.store.count("orders"), self.store.count("outbox")), (0, 0))

    def test_committed_event_survives_reopen(self):
        self.store.create()
        self.store.db.close()
        self.store = Store(self.path)
        self.assertEqual((self.store.count("orders"), self.store.count("outbox")), (1, 1))

    def test_effect_and_inbox_rollback_together(self):
        with self.assertRaises(RuntimeError):
            self.store.consume(fail=True)
        self.assertEqual((self.store.effect(), self.store.count("inbox")), (0, 0))
        self.assertEqual(self.store.consume(), "COMMITTED")
        self.assertEqual(self.store.effect(), 1)

    def test_redelivery_after_commit_before_ack(self):
        self.store.consume()  # 模拟业务已提交，但没有把ACK发给broker。
        self.store.db.close()
        self.store = Store(self.path)
        self.assertEqual(self.store.consume(), "DUPLICATE")
        self.assertEqual(self.store.effect(), 1)

    def test_conflicting_payload_rejected(self):
        self.store.consume()
        with self.assertRaises(Conflict):
            self.store.consume(payload_hash="different")
        self.assertEqual(self.store.effect(), 1)

    def test_consumers_have_separate_dedup_scopes(self):
        self.store.consume()
        self.store.consume(consumer="notification")
        self.assertEqual(self.store.count("inbox"), 2)
        self.assertEqual(self.store.effect("notification"), 1)

    def test_short_retention_allows_duplicate_effect_counterexample(self):
        self.store.consume()
        # 仅删除本实验临时数据库中的去重行，模拟错误保留策略。
        with transaction(self.store.db):
            self.store.db.execute("DELETE FROM inbox")
        self.store.consume()
        self.assertEqual(self.store.effect(), 2)

    def test_entry_check_then_revoke_allows_stale_write_counterexample(self):
        cached_allowed = self.store.db.execute("SELECT allowed FROM policy").fetchone()[0]
        other = Store(self.path)
        try:
            other.revoke()
            if cached_allowed:
                with transaction(self.store.db):
                    self.store.db.execute("UPDATE managed_resource SET value=value+1")
            self.assertEqual(self.store.db.execute("SELECT value FROM managed_resource").fetchone()[0], 1)
            self.assertEqual(self.store.db.execute("SELECT allowed FROM policy").fetchone()[0], 0)
        finally:
            other.db.close()

    def test_revoke_before_protected_transaction_blocks_write(self):
        other = Store(self.path)
        try:
            other.revoke()
            self.assertFalse(self.store.protected_write())
            self.assertEqual(self.store.db.execute("SELECT value FROM managed_resource").fetchone()[0], 0)
        finally:
            other.db.close()

    def test_shared_transaction_orders_write_before_revoke(self):
        other = Store(self.path)
        try:
            with transaction(self.store.db):
                self.assertEqual(self.store.db.execute("SELECT allowed FROM policy").fetchone()[0], 1)
                # SQLite同一时刻只允许一个写事务；不冒充MySQL行锁测试。
                with self.assertRaises(sqlite3.OperationalError):
                    other.revoke()
                self.store.db.execute("UPDATE managed_resource SET value=value+1")
            other.revoke()
            self.assertFalse(self.store.protected_write())
            self.assertEqual(self.store.db.execute("SELECT value FROM managed_resource").fetchone()[0], 1)
        finally:
            other.db.close()


class ProtocolTests(unittest.TestCase):
    def test_return_then_ack_is_not_published(self):
        m = PublisherModel(); token = m.claim(0)
        self.assertTrue(m.result(token, 1, ack=True, returned=True))
        self.assertEqual(m.status, "RETRY_WAIT")

    def test_old_callback_cannot_overwrite_new_attempt(self):
        m = PublisherModel(); old = m.claim(0); current = m.claim(10)
        self.assertFalse(m.result(old, 11, ack=True, returned=False))
        self.assertEqual(m.status, "IN_FLIGHT")
        self.assertTrue(m.result(current, 11, ack=True, returned=False))
        self.assertFalse(m.result(old, 12, ack=False, returned=False))
        self.assertEqual(m.status, "PUBLISHED")

    def test_max_attempts_go_to_manual(self):
        m = PublisherModel()
        for now in (0, 10, 20):
            m.claim(now)
        self.assertIsNone(m.claim(30))
        self.assertEqual(m.status, "MANUAL")

    def test_premark_is_not_completion_counterexample(self):
        claimed = {"e1"}  # 第一次领取成功、业务还未成功即退出。
        effects = []
        second_delivery_ack = "e1" in claimed
        self.assertTrue(second_delivery_ack)
        self.assertEqual(effects, [])

    def test_multirole_scope_does_not_form_cartesian_product(self):
        grants = {"update": {"D1"}, "read": {"D1", "D2"}}
        wrong_actions, wrong_depts = set(grants), set().union(*grants.values())
        self.assertTrue("update" in wrong_actions and "D2" in wrong_depts)
        self.assertNotIn("D2", grants["update"])
        self.assertIn("D2", grants["read"])

    def test_explicit_empty_is_not_inheritance(self):
        role = {"read", "update"}
        override = set()
        wrong = override or role
        correct = role if override is None else override
        self.assertEqual(wrong, role)
        self.assertEqual(correct, set())


if __name__ == "__main__":
    print("SQLite版本：", sqlite3.sqlite_version, flush=True)
    print("仅本地实验数据库保留于：", ROOT, flush=True)
    unittest.main(verbosity=2)
