import json
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from server import Store, Conflict, DEFAULT_ROOT


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for p in DEFAULT_ROOT.glob('*.md'):
            shutil.copy2(p, self.root / p.name)
        self.store = Store(self.root)
        self.initial = self.store.snapshot()

    def tearDown(self):
        self.temp.cleanup()

    def payload(self):
        w = self.initial['weeks'][0]
        d = w['days'][0]
        return dict(revision=self.initial['revision'], week=w['id'], day=1,
                    status='学习中', level='可独立解释', date='2026-10-27', hours=4.5,
                    checks=[True] + [False] * (len(d['tasks']) - 1),
                    records=dict(d['records']), review=dict(w['review']))

    def test_save_reload_summary_backup_and_preservation(self):
        data = self.payload()
        data['records']['实际完成内容'] = '理解任务与线程\n第二行\n\n## 这只是记录，不是章节'
        data['records']['下次具体起点'] = '继续理解阻塞与等待'
        before = {p.name: p.read_text() for p in self.root.glob('*.md')}
        result = self.store.save(data)
        day = result['weeks'][0]['days'][0]
        self.assertEqual(day['records']['实际完成内容'], data['records']['实际完成内容'])
        self.assertEqual(result['summary']['hours'], 4.5)
        self.assertEqual(result['summary']['completed'], 0)
        self.assertTrue(day['tasks'][0]['done'])
        self.assertEqual((Path(result['backup']) / data['week']).read_text(), before[data['week']])
        tracker = (self.root / '学习进度记录.md').read_text()
        self.assertIn('| 累计实际时长 | 4.5 小时 |', tracker)
        self.assertIn('| 下次具体起点 | 继续理解阻塞与等待 |', tracker)
        self.assertEqual(tracker.split('## 跨日疑点与复测')[1], before['学习进度记录.md'].split('## 跨日疑点与复测')[1])
        for name, content in before.items():
            if name not in (data['week'], '学习进度记录.md'):
                self.assertEqual((self.root / name).read_text(), content)
        data['revision'] = result['revision']
        data['status'] = '已完成'
        result = self.store.save(data)
        self.assertEqual(result['summary']['completed'], 1)
        self.assertEqual(result['summary']['hours'], 4.5)
        self.assertIn('| 当前周次与学习日 | 第 01 周，第 2 天 |', (self.root / '学习进度记录.md').read_text())

    def test_conflict_preserves_external_edit(self):
        data = self.payload()
        path = self.root / data['week']
        path.write_text(path.read_text() + '\n外部修改\n')
        with self.assertRaises(Conflict):
            self.store.save(data)
        self.assertTrue(path.read_text().endswith('外部修改\n'))

    def test_invalid_values_do_not_write(self):
        for key, value in [('hours', -1), ('hours', float('nan')), ('date', '2026-02-30'), ('status', '随便'), ('week', '../其他.md'), ('checks', [])]:
            with self.subTest(key=key, value=value):
                data = self.payload(); data[key] = value
                with self.assertRaises(ValueError):
                    self.store.save(data)
                self.assertEqual(self.store.snapshot()['revision'], self.initial['revision'])

    def test_bridge_without_network(self):
        result = subprocess.run(['/usr/bin/python3', str(Path(__file__).parent / 'native_bridge.py')], input=json.dumps(dict(action='load', root=str(self.root))), text=True, capture_output=True, check=True)
        self.assertEqual(len(json.loads(result.stdout)['weeks']), 12)

    def test_write_failure_restores_first_file(self):
        data = self.payload()
        original_write = self.store.atomic_write
        calls = []
        def fail_second(path, text):
            calls.append(path)
            if len(calls) == 2:
                raise OSError('模拟第二个文件写入失败')
            original_write(path, text)
        with patch.object(self.store, 'atomic_write', side_effect=fail_second):
            with self.assertRaises(OSError):
                self.store.save(data)
        self.assertEqual(self.store.snapshot()['revision'], self.initial['revision'])

    def test_bridge_save_and_reload(self):
        request = dict(action='save', root=str(self.root), data=self.payload())
        result = subprocess.run(['/usr/bin/python3', str(Path(__file__).parent / 'native_bridge.py')], input=json.dumps(request), text=True, capture_output=True, check=True)
        self.assertEqual(json.loads(result.stdout)['summary']['hours'], 4.5)
        self.assertEqual(self.store.snapshot()['weeks'][0]['days'][0]['status'], '学习中')


if __name__ == '__main__':
    unittest.main()
