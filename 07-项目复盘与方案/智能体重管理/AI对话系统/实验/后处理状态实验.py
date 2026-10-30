import unittest


class TaskModel:
    def __init__(self):
        self.payloads = {}
        self.effects = set()
        self.done = set()

    def deliver(self, task_id, payload, fail_after_memory=False):
        if task_id in self.payloads and self.payloads[task_id] != payload:
            raise ValueError("同一任务身份的参数冲突")
        self.payloads[task_id] = payload
        if task_id in self.done:
            return "ACK"
        # 集合操作代表资源端幂等效果，真实系统须有对应事务/唯一约束。
        self.effects.add((task_id, "memory"))
        if fail_after_memory:
            return "RETRY_WAIT"
        self.effects.add((task_id, "context"))
        self.done.add(task_id)
        return "ACK"


class StateTests(unittest.TestCase):
    def test_old_premark_loses_work(self):
        claimed = set()
        effects = []

        def old_deliver():
            if "t1" in claimed:
                return "ACK"
            claimed.add("t1")
            # 模拟业务在第一次实际写入前失败。
            return "NACK"

        self.assertEqual(old_deliver(), "NACK")
        self.assertEqual(old_deliver(), "ACK")
        self.assertEqual(effects, [])  # 复现错误：已确认但业务没有执行。

    def test_partial_failure_then_retry(self):
        model = TaskModel()
        self.assertEqual(model.deliver("t1", "v1", True), "RETRY_WAIT")
        self.assertNotIn("t1", model.done)
        self.assertEqual(model.deliver("t1", "v1"), "ACK")
        self.assertEqual(model.effects, {("t1", "memory"), ("t1", "context")})

    def test_duplicate_after_ack_lost(self):
        model = TaskModel()
        model.deliver("t1", "v1")
        before = model.effects.copy()
        self.assertEqual(model.deliver("t1", "v1"), "ACK")
        self.assertEqual(model.effects, before)

    def test_payload_conflict(self):
        model = TaskModel()
        model.deliver("t1", "v1")
        with self.assertRaises(ValueError):
            model.deliver("t1", "v2")
        self.assertEqual(len(model.effects), 2)

    def test_new_task_is_not_duplicate(self):
        model = TaskModel()
        model.deliver("t1", "v1")
        model.deliver("t2", "v1")
        self.assertEqual(len(model.effects), 4)
        self.assertEqual(model.done, {"t1", "t2"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
