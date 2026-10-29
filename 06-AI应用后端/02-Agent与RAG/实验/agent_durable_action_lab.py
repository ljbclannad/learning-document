"""单进程 SQLite 教学实验：持久意图、独立副作用、幂等与恢复。

只在临时目录读写，无网络请求。故障注入不代表真实断电测试。
"""
import hashlib
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest


def digest(payload):
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


class Remote:
    """测试替身：业务记录与幂等键共用一行，在同一事务落库。"""

    def __init__(self, path):
        self.db = sqlite3.connect(path)
        self.db.execute('''CREATE TABLE IF NOT EXISTS registrations (
            action_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL,
            payload TEXT NOT NULL, receipt TEXT NOT NULL)''')
        self.db.commit()

    def get(self, action_id):
        return self.db.execute(
            'SELECT payload_hash, receipt FROM registrations WHERE action_id=?',
            (action_id,)).fetchone()

    def apply(self, action_id, payload_hash, payload):
        if digest(payload) != payload_hash:
            raise ValueError('摘要与正文不符')
        # BEGIN IMMEDIATE 使本地测试中的查重与插入同属一个写事务。
        self.db.execute('BEGIN IMMEDIATE')
        try:
            old = self.get(action_id)
            if old:
                if old[0] != payload_hash:
                    raise ValueError('同一动作身份不能改变内容')
                receipt = old[1]
            else:
                receipt = 'receipt:' + action_id
                self.db.execute('INSERT INTO registrations VALUES (?, ?, ?, ?)',
                                (action_id, payload_hash, payload, receipt))
            self.db.commit()
            return receipt
        except Exception:
            self.db.rollback()
            raise

    def count(self):
        return self.db.execute('SELECT count(*) FROM registrations').fetchone()[0]

    def close(self):
        self.db.close()


class Harness:
    def __init__(self, path, remote):
        self.remote = remote
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                payload TEXT NOT NULL, approved_revision INTEGER,
                approved_hash TEXT, cancelled INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS actions (
                action_id TEXT PRIMARY KEY, task_id TEXT NOT NULL,
                revision INTEGER NOT NULL, payload_hash TEXT NOT NULL,
                payload TEXT NOT NULL, state TEXT NOT NULL, receipt TEXT);
            CREATE UNIQUE INDEX IF NOT EXISTS one_action_per_task_revision
                ON actions(task_id, revision);
            CREATE TABLE IF NOT EXISTS attempts (
                attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_id TEXT NOT NULL, outcome TEXT NOT NULL);
        ''')

    def task(self, task_id):
        return self.db.execute('SELECT * FROM tasks WHERE task_id=?',
                               (task_id,)).fetchone()

    def action(self, action_id):
        return self.db.execute('SELECT * FROM actions WHERE action_id=?',
                               (action_id,)).fetchone()

    def create_task(self, task_id, payload):
        with self.db:
            self.db.execute('INSERT INTO tasks(task_id,revision,payload) VALUES (?,1,?)',
                            (task_id, payload))

    def approve(self, task_id):
        t = self.task(task_id)
        with self.db:
            self.db.execute('UPDATE tasks SET approved_revision=?, approved_hash=? WHERE task_id=?',
                            (t['revision'], digest(t['payload']), task_id))

    def revise(self, task_id, payload):
        with self.db:
            self.db.execute('UPDATE tasks SET revision=revision+1, payload=? WHERE task_id=?',
                            (payload, task_id))

    def cancel(self, task_id):
        with self.db:
            self.db.execute('UPDATE tasks SET cancelled=1 WHERE task_id=?', (task_id,))

    @staticmethod
    def check(t):
        if t['cancelled']:
            raise PermissionError('任务已取消')
        if (t['approved_revision'] != t['revision'] or
                t['approved_hash'] != digest(t['payload'])):
            raise PermissionError('当前版本未获批准')

    def prepare(self, task_id, action_id):
        # 教学实现为顺序调用；生产还需并发抢占、条件更新及完整授权范围。
        t = self.task(task_id)
        self.check(t)
        old = self.action(action_id)
        if old:
            if (old['task_id'], old['revision'], old['payload_hash']) != (
                    task_id, t['revision'], digest(t['payload'])):
                raise ValueError('动作身份冲突')
            return
        bound = self.db.execute(
            'SELECT action_id FROM actions WHERE task_id=? AND revision=?',
            (task_id, t['revision'])).fetchone()
        if bound:
            raise ValueError('该任务版本已有动作，请复用已保存的 action_id')
        with self.db:
            self.db.execute('INSERT INTO actions VALUES (?,?,?,?,?,?,NULL)',
                            (action_id, task_id, t['revision'], digest(t['payload']),
                             t['payload'], 'PREPARED'))

    def confirm(self, action_id, receipt):
        with self.db:
            self.db.execute("UPDATE actions SET state='CONFIRMED',receipt=? WHERE action_id=?",
                            (receipt, action_id))
        return receipt

    def dispatch(self, action_id, fault=None):
        a = self.action(action_id)
        if a['state'] == 'CONFIRMED':
            return a['receipt']  # 读取已发生事实，不产生新的写操作
        t = self.task(a['task_id'])
        self.check(t)
        if (a['revision'], a['payload_hash']) != (t['revision'], digest(t['payload'])):
            raise PermissionError('旧动作不能代表当前版本')
        with self.db:
            attempt_id = self.db.execute(
                "INSERT INTO attempts(action_id,outcome) VALUES (?, 'UNKNOWN')",
                (action_id,)).lastrowid
            self.db.execute("UPDATE actions SET state='UNKNOWN' WHERE action_id=?", (action_id,))
        if fault == 'before_remote':
            raise TimeoutError('发送前注入故障')
        receipt = self.remote.apply(action_id, a['payload_hash'], a['payload'])
        if fault == 'after_remote':
            raise TimeoutError('下游已提交，回执未记账')
        with self.db:
            self.db.execute("UPDATE attempts SET outcome='ACKNOWLEDGED' WHERE attempt_id=?",
                            (attempt_id,))
        return self.confirm(action_id, receipt)

    def recover(self, action_id):
        a = self.action(action_id)
        found = self.remote.get(action_id)
        if found:
            if found[0] != a['payload_hash']:
                raise ValueError('下游记录与原动作不符')
            # 即使任务已取消/改版，也要记录原动作事实；不修改当前任务状态。
            return self.confirm(action_id, found[1])
        # 本替身查询是确定的；真实下游查不到可能是延迟，仍不能更换幂等键。
        return self.dispatch(action_id)

    def close(self):
        self.db.close()


class DurableActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.local_path = Path(self.tmp.name)/'local.sqlite'
        self.remote_path = Path(self.tmp.name)/'remote.sqlite'
        self.open_connections()
        self.h.create_task('task-1', '学习报告 v1')
        self.h.approve('task-1')
        self.h.prepare('task-1', 'action-1')

    def open_connections(self):
        self.remote = Remote(self.remote_path)
        self.h = Harness(self.local_path, self.remote)

    def tearDown(self):
        self.h.close()
        self.remote.close()

    def lose_receipt(self):
        with self.assertRaises(TimeoutError):
            self.h.dispatch('action-1', fault='after_remote')
        self.assertEqual(self.h.action('action-1')['state'], 'UNKNOWN')
        self.assertEqual(self.remote.count(), 1)

    def test_normal_and_repeated_dispatch(self):
        first = self.h.dispatch('action-1')
        self.assertEqual(self.h.dispatch('action-1'), first)
        self.assertEqual(self.remote.count(), 1)

    def test_reopen_and_recover_lost_receipt(self):
        self.lose_receipt()
        self.h.close()
        self.remote.close()
        self.open_connections()
        self.assertEqual(self.h.recover('action-1'), 'receipt:action-1')
        self.assertEqual(self.h.action('action-1')['state'], 'CONFIRMED')
        self.assertEqual(self.remote.count(), 1)
        self.assertEqual(self.h.db.execute('SELECT count(*) FROM attempts').fetchone()[0], 1)

    def test_regenerated_action_id_rejected_after_reopen(self):
        """回归：同一登记意图不能因恢复后换键而变成第二次登记。"""
        self.lose_receipt()
        self.h.close()
        self.remote.close()
        self.open_connections()
        with self.assertRaisesRegex(ValueError, '已有动作'):
            self.h.prepare('task-1', 'action-2')
        self.assertIsNone(self.h.action('action-2'))
        self.h.prepare('task-1', 'action-1')
        self.h.recover('action-1')
        self.assertEqual(self.remote.count(), 1)

    def test_new_approved_task_can_register_identical_content(self):
        """相同正文不等于同一业务意图；新任务须独立批准。"""
        self.h.dispatch('action-1')
        self.h.create_task('task-2', '学习报告 v1')
        with self.assertRaises(PermissionError):
            self.h.prepare('task-2', 'action-2')
        self.h.approve('task-2')
        self.h.prepare('task-2', 'action-2')
        self.h.dispatch('action-2')
        self.assertEqual(self.remote.count(), 2)

    def test_retry_after_missing_remote_uses_new_attempt_same_action(self):
        with self.assertRaises(TimeoutError):
            self.h.dispatch('action-1', fault='before_remote')
        self.assertEqual(self.remote.count(), 0)
        self.h.recover('action-1')
        rows = self.h.db.execute('SELECT attempt_id,action_id FROM attempts').fetchall()
        self.assertEqual(len({r['attempt_id'] for r in rows}), 2)
        self.assertEqual({r['action_id'] for r in rows}, {'action-1'})
        self.assertEqual(self.remote.count(), 1)

    def test_downstream_same_key_retry_is_idempotent(self):
        self.lose_receipt()
        self.h.dispatch('action-1')
        self.assertEqual(self.remote.count(), 1)

    def test_same_key_changed_payload_rejected(self):
        self.h.dispatch('action-1')
        with self.assertRaises(ValueError):
            self.remote.apply('action-1', digest('另一份报告'), '另一份报告')
        self.assertEqual(self.remote.count(), 1)
        self.assertEqual(self.remote.get('action-1')[0], digest('学习报告 v1'))

    def test_old_approval_and_old_action_rejected(self):
        self.h.revise('task-1', '学习报告 v2')
        with self.assertRaises(PermissionError):
            self.h.dispatch('action-1')
        self.h.approve('task-1')
        with self.assertRaises(PermissionError):
            self.h.dispatch('action-1')
        self.assertEqual(self.remote.count(), 0)
        self.h.prepare('task-1', 'action-2')
        self.h.dispatch('action-2')
        self.assertEqual(self.remote.count(), 1)

    def test_cancel_before_dispatch(self):
        self.h.cancel('task-1')
        with self.assertRaises(PermissionError):
            self.h.recover('action-1')
        self.assertEqual(self.remote.count(), 0)

    def test_cancel_after_remote_does_not_erase_fact(self):
        self.lose_receipt()
        self.h.cancel('task-1')
        self.h.recover('action-1')
        self.assertEqual(self.h.task('task-1')['cancelled'], 1)
        self.assertEqual(self.h.action('action-1')['state'], 'CONFIRMED')
        self.assertEqual(self.remote.count(), 1)

    def test_late_result_does_not_replace_new_goal(self):
        self.lose_receipt()
        self.h.revise('task-1', '学习报告 v2')
        self.h.recover('action-1')
        self.assertEqual(self.h.task('task-1')['revision'], 2)
        self.assertEqual(self.h.task('task-1')['payload'], '学习报告 v2')
        self.assertEqual(self.h.action('action-1')['revision'], 1)
        self.assertEqual(self.remote.count(), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
