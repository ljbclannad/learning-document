"""统一系统的单进程状态契约实验；不模拟数据库事务或真实网络。"""
from dataclasses import dataclass, replace
import hashlib
import json
import unittest


def digest(value):
    """教学规范化：正式系统还需规定数值、Unicode 等跨语言规则。"""
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()).hexdigest()


class Conflict(ValueError):
    pass


class RequestStore:
    def __init__(self):
        self.records = {}

    def accept(self, tenant, actor, operation, key, payload):
        identity = (tenant, actor, operation, key)
        fingerprint = digest(payload)
        if identity in self.records:
            old_hash, resource_id = self.records[identity]
            if old_hash != fingerprint:
                raise Conflict("同键异参")
            return resource_id
        resource_id = len(self.records) + 1
        self.records[identity] = (fingerprint, resource_id)
        return resource_id


@dataclass(frozen=True)
class Binding:
    tenant: str = "t1"
    customer: str = "c1"
    run: str = "r1"
    goal_revision: int = 1
    evidence_revision: int = 1
    draft_version: int = 1
    source_version: int = 1
    input_hash: str = "参数摘要1"
    tool_version: int = 1


class ActionModel:
    """调用者先认证；这里仅模拟范围/审核者、版本与状态规则。"""
    def __init__(self):
        self.current = Binding()
        self.approval_binding = self.current
        self.approval = "PENDING"
        self.expires_at = 100
        self.action = "NONE"
        self.cancelled = False
        self.authorized = True
        self.dispatch_count = 0
        self.effects = 0
        self.receipt = None

    def check(self, tenant="t1", customer="c1", actor="doctor1"):
        if not self.authorized or (tenant, customer, actor) != (
            self.current.tenant, self.current.customer, "doctor1"
        ):
            raise PermissionError("授权范围不匹配")

    def approve(self, now=1, tenant="t1", customer="c1", actor="doctor1"):
        self.check(tenant, customer, actor)
        # 重复同决定只返回凭据，不能重新创建执行任务。
        if self.approval == "APPROVED":
            return self.approval
        if self.approval != "PENDING":
            raise Conflict("审批已经决定")
        if self.cancelled or now >= self.expires_at:
            raise Conflict("取消或过期")
        if self.current != self.approval_binding:
            raise Conflict("审批对象已经变化")
        self.approval = "APPROVED"
        self.action = "READY"
        return self.approval

    def reject(self):
        self.check()
        if self.approval != "PENDING":
            raise Conflict("审批已经决定")
        self.approval = "REJECTED"
        self.cancelled = True

    def dispatch(self, now=2):
        self.check()
        if self.cancelled or now >= self.expires_at:
            raise Conflict("动作不可执行")
        if self.approval != "APPROVED" or self.current != self.approval_binding:
            raise Conflict("未批准或绑定失效")
        if self.action != "READY":
            raise Conflict("不能重复派发或盲重试")
        self.action = "EXECUTING"
        self.dispatch_count += 1

    def external_success_then_timeout(self):
        if self.action != "EXECUTING":
            raise Conflict("动作未开始")
        self.effects += 1  # 模拟资源端已经执行，本地尚不知道。
        self.action = "UNKNOWN"

    def reconcile(self, receipt):
        if self.action == "SUCCEEDED":
            if receipt != self.receipt:
                raise Conflict("同一动作回执冲突")
            return
        if self.action != "UNKNOWN" or not receipt:
            raise Conflict("必须先查证未知结果")
        self.receipt = receipt
        self.action = "SUCCEEDED"

    def cancel(self):
        self.cancelled = True
        if self.action == "READY":
            self.action = "CANCELLED"
        elif self.action == "EXECUTING":
            self.action = "UNKNOWN"  # 不把取消请求等同于外部撤销。


class LeaseModel:
    def __init__(self):
        self.token = 0
        self.until = 0
        self.state = "PENDING"

    def claim(self, now, ttl):
        if self.state == "SUCCEEDED" or (
            self.state == "PROCESSING" and now < self.until
        ):
            raise Conflict("不可领取")
        self.token += 1
        self.until = now + ttl
        self.state = "PROCESSING"
        return self.token

    def finish(self, token, now):
        if self.state != "PROCESSING" or token != self.token or now >= self.until:
            raise Conflict("旧领取或租约失效")
        self.state = "SUCCEEDED"


class ContextModel:
    def __init__(self):
        self.epoch, self.version, self.covered = 1, 0, 0

    def snapshot(self):
        return self.epoch, self.version, self.covered

    def commit(self, base, end, source_sequences):
        if base != self.snapshot():
            raise Conflict("旧摘要基线")
        if end <= self.covered or source_sequences != list(range(self.covered + 1, end + 1)):
            raise Conflict("来源有缺口或覆盖没有推进")
        self.version += 1
        self.covered = end

    def reset(self):
        self.epoch += 1
        self.version, self.covered = 0, 0


class TurnModel:
    """单进程模拟同会话串行轮次；每个方法代表一个已提交的状态变化。"""
    def __init__(self):
        self.epoch = 1
        self.turns = {}
        self.messages = []
        self.active = None
        self.jobs = set()

    def enqueue(self, turn_id, text):
        if turn_id in self.turns:
            raise Conflict("实验调用方应先完成请求去重")
        self.turns[turn_id] = {"epoch": self.epoch, "state": "QUEUED", "text": text}

    def start(self, turn_id):
        if self.active is not None:
            raise Conflict("已有运行轮次")
        queued = [key for key, turn in self.turns.items()
                  if turn["epoch"] == self.epoch and turn["state"] == "QUEUED"]
        if not queued or queued[0] != turn_id:
            raise Conflict("不是队头")
        turn = self.turns[turn_id]
        turn["state"] = "RUNNING"
        self.active = turn_id
        self.messages.append((turn_id, "user", turn["text"]))
        return self.epoch, list(self.messages)

    def finish(self, turn_id, epoch, text, complete=True):
        turn = self.turns[turn_id]
        if epoch != self.epoch:
            raise Conflict("旧会话")
        if turn["state"] == "COMPLETED":
            if turn["answer"] != text:
                raise Conflict("完成回调冲突")
            return
        if self.active != turn_id or turn["state"] != "RUNNING":
            raise Conflict("非法完成")
        if complete:
            self.messages.append((turn_id, "assistant", text))
            turn["answer"] = text
            turn["state"] = "COMPLETED"
            self.jobs.add((self.epoch, turn_id, "POSTPROCESS"))
        else:
            turn["state"] = "PARTIAL"
        self.active = None

    def reset(self):
        self.epoch += 1
        for turn in self.turns.values():
            if turn["state"] in ("QUEUED", "RUNNING"):
                turn["state"] = "CANCELLED"
        self.active = None
        self.messages = []
        # 实际系统保留旧任务审计，由 epoch 检查阻止继续处理。


class ContractTests(unittest.TestCase):
    def test_queued_input_not_in_previous_prompt(self):
        m = TurnModel(); m.enqueue("t1", "问题1"); m.enqueue("t2", "问题2")
        with self.assertRaises(Conflict):
            m.start("t2")
        epoch, prompt = m.start("t1")
        self.assertEqual(prompt, [("t1", "user", "问题1")])
        with self.assertRaises(Conflict):
            m.start("t2")
        m.finish("t1", epoch, "回复1")
        _, prompt2 = m.start("t2")
        self.assertEqual(prompt2, [("t1", "user", "问题1"),
                                  ("t1", "assistant", "回复1"),
                                  ("t2", "user", "问题2")])

    def test_completed_callback_creates_one_postprocess_job(self):
        m = TurnModel(); m.enqueue("t1", "问题")
        epoch, _ = m.start("t1")
        m.finish("t1", epoch, "回复"); m.finish("t1", epoch, "回复")
        self.assertEqual(len(m.jobs), 1)
        self.assertEqual(len(m.messages), 2)
        with self.assertRaises(Conflict):
            m.finish("t1", epoch, "另一回复")

    def test_partial_has_no_complete_reply_job_and_unblocks_queue(self):
        m = TurnModel(); m.enqueue("t1", "问题1"); m.enqueue("t2", "问题2")
        epoch, _ = m.start("t1")
        m.finish("t1", epoch, "半句", complete=False)
        self.assertEqual(m.jobs, set())
        _, prompt = m.start("t2")
        self.assertEqual([item[1] for item in prompt], ["user", "user"])

    def test_reset_blocks_late_reply(self):
        m = TurnModel(); m.enqueue("t1", "问题")
        epoch, _ = m.start("t1"); m.reset()
        with self.assertRaises(Conflict):
            m.finish("t1", epoch, "迟到回复")
        self.assertEqual(m.messages, [])
        self.assertEqual(m.jobs, set())

    def test_request_replay_and_conflict(self):
        s = RequestStore()
        first = s.accept("t", "a", "run", "k", {"goal": "整理"})
        self.assertEqual(first, s.accept("t", "a", "run", "k", {"goal": "整理"}))
        with self.assertRaises(Conflict):
            s.accept("t", "a", "run", "k", {"goal": "发送"})
        self.assertEqual(len(s.records), 1)

    def test_request_scope_isolation(self):
        s = RequestStore()
        ids = {s.accept(t, a, op, "k", {}) for t, a, op in (
            ("t1", "a1", "run"), ("t2", "a1", "run"),
            ("t1", "a2", "run"), ("t1", "a1", "turn")
        )}
        self.assertEqual(len(ids), 4)

    def test_hash_preserves_semantics(self):
        self.assertEqual(digest({"a": 1, "b": 2}), digest({"b": 2, "a": 1}))
        self.assertNotEqual(digest({"v": "1.5"}), digest({"v": "15"}))

    def test_approval_scope(self):
        for wrong in ({"tenant": "t2"}, {"customer": "c2"}, {"actor": "doctor2"}):
            m = ActionModel()
            with self.assertRaises(PermissionError):
                m.approve(**wrong)
            self.assertEqual(m.action, "NONE")

    def test_duplicate_approval_does_not_duplicate_action(self):
        m = ActionModel()
        m.approve(); m.approve(); m.dispatch(); m.approve()
        with self.assertRaises(Conflict):
            m.dispatch()
        self.assertEqual(m.dispatch_count, 1)

    def test_expired_approval(self):
        m = ActionModel()
        with self.assertRaises(Conflict):
            m.approve(now=100)
        self.assertEqual(m.action, "NONE")

    def test_rejected_cannot_approve(self):
        m = ActionModel(); m.reject()
        with self.assertRaises(Conflict):
            m.approve()
        self.assertTrue(m.cancelled)

    def test_each_binding_change_invalidates_pending_approval(self):
        changes = {"goal_revision": 2, "evidence_revision": 2,
                   "draft_version": 2, "source_version": 2,
                   "input_hash": "不同参数", "tool_version": 2}
        for field, value in changes.items():
            with self.subTest(field=field):
                m = ActionModel()
                m.current = replace(m.current, **{field: value})
                with self.assertRaises(Conflict):
                    m.approve()
                self.assertEqual(m.dispatch_count, 0)

    def test_source_changes_after_approval(self):
        m = ActionModel(); m.approve()
        m.current = replace(m.current, source_version=2)
        with self.assertRaises(Conflict):
            m.dispatch()
        self.assertEqual(m.dispatch_count, 0)

    def test_revoked_permission_after_approval(self):
        m = ActionModel(); m.approve(); m.authorized = False
        with self.assertRaises(PermissionError):
            m.dispatch()

    def test_action_expiry_before_dispatch(self):
        m = ActionModel(); m.approve()
        with self.assertRaises(Conflict):
            m.dispatch(now=100)

    def test_unknown_does_not_blindly_resend(self):
        m = ActionModel(); m.approve(); m.dispatch()
        m.external_success_then_timeout()
        with self.assertRaises(Conflict):
            m.dispatch()
        m.reconcile("receipt-1"); m.reconcile("receipt-1")
        self.assertEqual((m.dispatch_count, m.effects, m.action), (1, 1, "SUCCEEDED"))
        with self.assertRaises(Conflict):
            m.reconcile("receipt-2")

    def test_cancel_before_dispatch(self):
        m = ActionModel(); m.approve(); m.cancel()
        with self.assertRaises(Conflict):
            m.dispatch()
        self.assertEqual(m.effects, 0)

    def test_cancel_after_send_preserves_external_fact(self):
        m = ActionModel(); m.approve(); m.dispatch()
        m.external_success_then_timeout(); m.cancel(); m.reconcile("receipt")
        self.assertTrue(m.cancelled)
        self.assertEqual(m.effects, 1)
        self.assertEqual(m.action, "SUCCEEDED")

    def test_old_worker_cannot_finish_new_attempt(self):
        j = LeaseModel(); old = j.claim(0, 10)
        new = j.claim(10, 10)
        with self.assertRaises(Conflict):
            j.finish(old, 11)
        j.finish(new, 11)
        self.assertEqual(j.state, "SUCCEEDED")

    def test_expired_worker_cannot_finish_even_without_reclaim(self):
        j = LeaseModel(); token = j.claim(0, 10)
        with self.assertRaises(Conflict):
            j.finish(token, 10)

    def test_late_summary_and_reset(self):
        c = ContextModel(); base = c.snapshot()
        c.commit(base, 4, [1, 2, 3, 4])
        with self.assertRaises(Conflict):
            c.commit(base, 2, [1, 2])
        old = c.snapshot(); c.reset()
        with self.assertRaises(Conflict):
            c.commit(old, 5, [5])
        self.assertEqual(c.snapshot(), (2, 0, 0))

    def test_summary_gap_is_rejected(self):
        c = ContextModel()
        with self.assertRaises(Conflict):
            c.commit(c.snapshot(), 3, [1, 3])
        self.assertEqual(c.covered, 0)

    def test_legacy_marker_parser_counterexample(self):
        args = {"message": "请解释 Final Answer: 标签"}
        legacy = "Action: explain\nAction Input: " + json.dumps(args, ensure_ascii=False)
        self.assertIn("Final Answer:", legacy)  # 原 contains 判定会错误完成。
        decision = {"type": "tool_call", "name": "explain", "input": args}
        self.assertEqual(decision["type"], "tool_call")
        self.assertEqual(decision["input"], args)


if __name__ == "__main__":
    unittest.main(verbosity=2)
