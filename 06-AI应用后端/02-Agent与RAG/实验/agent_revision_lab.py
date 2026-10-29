"""Python 3.10+ 标准库教学实验：串行事件、不可变快照与条件提交。

只模拟一个任务，每个方法代表不可分割的状态转换。没有网络、模型、
数据库或发布动作；并发系统需以事务/CAS 实现同样的检查与写入边界。
"""
from dataclasses import dataclass
from itertools import permutations
import unittest


@dataclass(frozen=True)
class Snapshot:
    goal_revision: int
    evidence_revision: int
    days: int
    evidence: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Draft:
    snapshot: Snapshot
    text: str


class Task:
    def __init__(self):
        self.goal_revision = 1
        self.evidence_revision = 0
        self.days = 90
        # 调用的修订号由发起方记录，不信任回调自行声称的版本。
        self.calls: dict[str, int] = {}
        self.receipts: dict[str, str] = {}
        self.evidence: dict[str, str] = {}
        self.draft: Draft | None = None

    def change_goal(self, days: int) -> None:
        if days <= 0:
            raise ValueError('时间范围必须为正数')
        self.goal_revision += 1
        self.days = days
        self.evidence.clear()
        self.evidence_revision += 1
        self.draft = None

    def start_call(self, call_id: str) -> None:
        if call_id in self.calls:
            raise ValueError('调用 ID 不可复用')
        self.calls[call_id] = self.goal_revision

    def receive(self, call_id: str, payload: str) -> str:
        """仅模拟成功、终态、文本结果；真实系统还需错误类型与认证。"""
        if call_id not in self.calls:
            raise ValueError('未知调用')
        if call_id in self.receipts:
            if self.receipts[call_id] != payload:
                raise ValueError('同一调用的结果冲突')
            return 'duplicate'
        self.receipts[call_id] = payload
        if self.calls[call_id] != self.goal_revision:
            return 'stale'
        self.evidence[call_id] = payload
        self.evidence_revision += 1
        self.draft = None
        return 'accepted'

    def snapshot(self) -> Snapshot:
        if not self.evidence:
            raise ValueError('没有可用于生成草稿的证据')
        return Snapshot(self.goal_revision, self.evidence_revision, self.days,
                        tuple(sorted(self.evidence.items())))

    def commit(self, snapshot: Snapshot, text: str) -> bool:
        # 生成在方法外完成；检查和提交在一个串行事件内完成。
        # 快照由应用保存并回传，真实系统不能信任模型填写的版本字段。
        if (snapshot.goal_revision, snapshot.evidence_revision) != (
                self.goal_revision, self.evidence_revision):
            return False
        if snapshot != self.snapshot():
            return False
        self.draft = Draft(snapshot, text)
        return True


def ready_task() -> Task:
    task = Task()
    task.start_call('C1')
    task.receive('C1', '证据 A')
    return task


class RevisionTests(unittest.TestCase):
    def test_old_result_isolated(self):
        """旧查询最后返回，只保留回执，不覆盖新证据。"""
        task = Task()
        task.start_call('C1')
        task.change_goal(30)
        task.start_call('C2')
        task.receive('C2', '30 天资料')
        before = task.snapshot()
        self.assertEqual(task.receive('C1', '90 天资料'), 'stale')
        self.assertEqual(task.snapshot(), before)
        self.assertEqual(task.receipts['C1'], '90 天资料')

    def test_duplicate_preserves_draft(self):
        """重复回调不增加证据版本，也不使有效草稿失效。"""
        task = ready_task()
        snapshot = task.snapshot()
        self.assertTrue(task.commit(snapshot, '草稿 A'))
        draft = task.draft
        self.assertEqual(task.receive('C1', '证据 A'), 'duplicate')
        self.assertEqual(task.snapshot(), snapshot)
        self.assertEqual(task.draft, draft)

    def test_conflicting_callback_rejected(self):
        """相同调用 ID、不同内容必须报冲突，而不是静默去重。"""
        task = ready_task()
        before = task.snapshot()
        with self.assertRaisesRegex(ValueError, '冲突'):
            task.receive('C1', '矛盾的证据')
        self.assertEqual(task.snapshot(), before)
        self.assertEqual(task.receipts['C1'], '证据 A')

    def test_unknown_and_reused_call_rejected(self):
        """无关联调用和复用 ID 都不能改变证据。"""
        task = ready_task()
        before = task.snapshot()
        with self.assertRaisesRegex(ValueError, '未知'):
            task.receive('unknown', '资料')
        with self.assertRaisesRegex(ValueError, '不可复用'):
            task.start_call('C1')
        self.assertEqual(task.snapshot(), before)

    def test_goal_changes_during_generation(self):
        """生成期间改目标，旧草稿提交失败，新快照可成功提交。"""
        task = ready_task()
        old = task.snapshot()
        task.change_goal(30)
        task.start_call('C2')
        task.receive('C2', '证据 B')
        self.assertTrue(task.commit(task.snapshot(), '当前草稿'))
        draft = task.draft
        self.assertFalse(task.commit(old, '迟到的旧草稿'))
        self.assertEqual(task.draft, draft)

    def test_evidence_changes_during_generation(self):
        """回归：目标不变、证据更新，仍拒绝旧草稿。"""
        task = ready_task()
        old = task.snapshot()
        task.start_call('C2')
        task.receive('C2', '补充证据 B')
        self.assertEqual(old.goal_revision, task.goal_revision)
        self.assertFalse(task.commit(old, '遗漏 B 的草稿'))
        self.assertIsNone(task.draft)
        self.assertTrue(task.commit(task.snapshot(), '包含 A 和 B 的草稿'))

    def test_committed_draft_invalidated(self):
        """提交成功后再改目标或补证据，当前草稿立即失效。"""
        for change in ('goal', 'evidence'):
            with self.subTest(change=change):
                task = ready_task()
                self.assertTrue(task.commit(task.snapshot(), '草稿'))
                if change == 'goal':
                    task.change_goal(30)
                else:
                    task.start_call('C2')
                    task.receive('C2', '新证据')
                self.assertIsNone(task.draft)

    def test_no_evidence_no_generation(self):
        """缺少证据不能当作空查询结果生成。"""
        with self.assertRaisesRegex(ValueError, '没有'):
            Task().snapshot()

    def test_all_callback_orders(self):
        """穷举旧、新回调各投递两次的 6 种顺序。"""
        for order in sorted(set(permutations(('old', 'old', 'new', 'new')))):
            with self.subTest(order=order):
                task = Task()
                task.start_call('old')
                task.change_goal(30)
                task.start_call('new')
                before_revision = task.evidence_revision
                results = [task.receive(call, call + '资料') for call in order]
                self.assertCountEqual(results, ['accepted', 'stale', 'duplicate', 'duplicate'])
                self.assertEqual(task.evidence, {'new': 'new资料'})
                self.assertEqual(task.evidence_revision, before_revision + 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
