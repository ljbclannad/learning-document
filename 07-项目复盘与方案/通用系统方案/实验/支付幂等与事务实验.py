import sqlite3
import unittest


def setup():
    db = sqlite3.connect(":memory:")
    db.executescript("""
        CREATE TABLE orders (
            id TEXT PRIMARY KEY, amount INTEGER NOT NULL,
            status TEXT NOT NULL
        );
        CREATE TABLE receipts (
            receipt_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL UNIQUE, amount INTEGER NOT NULL
        );
        CREATE TABLE entitlements (
            order_id TEXT PRIMARY KEY
        );
        INSERT INTO orders VALUES ('O1', 100, 'PENDING');
        INSERT INTO orders VALUES ('O2', 100, 'PENDING');
    """)
    return db


def pay(db, order_id, receipt_id, amount, fail_after_status=False):
    # 教学前提：单渠道、单商户、金额单位固定；真实系统需扩大身份与校验。
    db.execute("BEGIN IMMEDIATE")
    try:
        old = db.execute(
            "SELECT order_id, amount FROM receipts WHERE receipt_id=?",
            (receipt_id,),
        ).fetchone()
        if old is not None:
            if old != (order_id, amount):
                raise ValueError("同流水参数冲突")
            db.commit()
            return "DUPLICATE"
        order = db.execute(
            "SELECT amount, status FROM orders WHERE id=?", (order_id,)
        ).fetchone()
        if order is None or order[0] != amount or order[1] != "PENDING":
            raise ValueError("订单不存在、金额不符或状态不允许")
        db.execute("INSERT INTO receipts VALUES (?, ?, ?)",
                   (receipt_id, order_id, amount))
        changed = db.execute(
            "UPDATE orders SET status='PAID' WHERE id=? AND status='PENDING'",
            (order_id,),
        ).rowcount
        if changed != 1:
            raise RuntimeError("状态竞争失败")
        if fail_after_status:
            raise RuntimeError("模拟权益写入前失败")
        db.execute("INSERT INTO entitlements VALUES (?)", (order_id,))
        db.commit()
        return "PAID"
    except Exception:
        db.rollback()
        raise


class PaymentProtocolTest(unittest.TestCase):
    def setUp(self):
        self.db = setup()

    def tearDown(self):
        self.db.close()

    def test_repeat_is_one_effect(self):
        self.assertEqual(pay(self.db, "O1", "R1", 100), "PAID")
        self.assertEqual(pay(self.db, "O1", "R1", 100), "DUPLICATE")
        count = self.db.execute("SELECT COUNT(*) FROM entitlements").fetchone()[0]
        self.assertEqual(count, 1)

    def test_failure_rolls_back_and_can_retry(self):
        with self.assertRaises(RuntimeError):
            pay(self.db, "O1", "R1", 100, True)
        state = self.db.execute("SELECT status FROM orders WHERE id='O1'").fetchone()[0]
        self.assertEqual(state, "PENDING")
        for table in ("receipts", "entitlements"):
            self.assertEqual(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
        self.assertEqual(pay(self.db, "O1", "R1", 100), "PAID")

    def test_receipt_conflict(self):
        pay(self.db, "O1", "R1", 100)
        with self.assertRaises(ValueError):
            pay(self.db, "O2", "R1", 100)
        state = self.db.execute("SELECT status FROM orders WHERE id='O2'").fetchone()[0]
        self.assertEqual(state, "PENDING")

    def test_committed_but_response_lost(self):
        # 先完成真实本地提交，再模拟业务响应丢失，不把它当作回滚。
        def request():
            pay(self.db, "O1", "R1", 100)
            raise TimeoutError("模拟提交成功后的响应丢失")
        with self.assertRaises(TimeoutError):
            request()
        self.assertEqual(pay(self.db, "O1", "R1", 100), "DUPLICATE")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM entitlements").fetchone()[0], 1)

    def test_same_receipt_different_amount(self):
        pay(self.db, "O1", "R1", 100)
        with self.assertRaises(ValueError):
            pay(self.db, "O1", "R1", 101)
        self.assertEqual(self.db.execute("SELECT amount FROM receipts").fetchone()[0], 100)

    def test_wrong_amount_and_second_receipt(self):
        with self.assertRaises(ValueError):
            pay(self.db, "O1", "R1", 99)
        pay(self.db, "O1", "R1", 100)
        with self.assertRaises(ValueError):
            pay(self.db, "O1", "R2", 100)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
