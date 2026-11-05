import json
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from server import Store, Conflict, DEFAULT_ROOT, read_field, write_field, field_span


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for p in DEFAULT_ROOT.glob('*.md'):
            shutil.copy2(p, self.root / p.name)
        self.store = Store(self.root)
        self.initial = self.store.snapshot()
        # 测试副本会包含实际学习进度，汇总应保留其他学习日的时长。
        self.expected_hours = sum(d['hours'] or 0 for w in self.initial['weeks'] for d in w['days']) - (self.initial['weeks'][0]['days'][0]['hours'] or 0) + 4.5

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
        self.assertEqual(result['summary']['hours'], self.expected_hours)
        self.assertEqual(result['summary']['completed'], 0)
        self.assertTrue(day['tasks'][0]['done'])
        self.assertEqual((Path(result['backup']) / data['week']).read_text(), before[data['week']])
        tracker = (self.root / '学习进度记录.md').read_text()
        self.assertIn(f'| 累计实际时长 | {self.expected_hours:g} 小时 |', tracker)
        self.assertIn('| 下次具体起点 | 继续理解阻塞与等待 |', tracker)
        self.assertEqual(tracker.split('## 跨日疑点与复测')[1], before['学习进度记录.md'].split('## 跨日疑点与复测')[1])
        for name, content in before.items():
            if name not in (data['week'], '学习进度记录.md'):
                self.assertEqual((self.root / name).read_text(), content)
        data['revision'] = result['revision']
        data['status'] = '已完成'
        result = self.store.save(data)
        self.assertEqual(result['summary']['completed'], 1)
        self.assertEqual(result['summary']['hours'], self.expected_hours)
        self.assertIn('| 当前周次与学习日 | 第 01 周，第 2 天 |', (self.root / '学习进度记录.md').read_text())

    def test_image_reference_round_trip(self):
        data = self.payload()
        value = '说明\n\n![实践图片](附件/实践笔记/图片-测试.png)\n\n```java\nrun();\n```'
        data['records']['代码、图、实验或问答证据'] = value
        self.store.save(data)
        self.assertEqual(self.store.snapshot()['weeks'][0]['days'][0]['records']['代码、图、实验或问答证据'], value)

    def test_heading_markdown_save_is_stable(self):
        data = self.payload()
        value = ('1. 第一项\n2. 第二项\n   - 子项\n\n'
                 '- [ ] 正文中的任务，不属于当日任务\n\n'
                 '## 普通正文标题\n\n'
                 '| 项目 | 结论 |\n| --- | --- |\n| A | B |\n\n'
                 '```md\n#### 实际完成内容\n## 周复盘\n## 第 2 天 示例\n```\n\n'
                 '![实践图片](附件/实践笔记/图片.png)')
        data['records']['代码、图、实验或问答证据'] = value
        result = self.store.save(data)
        path = self.root / data['week']
        first = path.read_text()
        self.assertIn('#### 代码、图、实验或问答证据\n\n' + value, first)
        self.assertEqual(result['weeks'][0]['days'][0]['records']['代码、图、实验或问答证据'], value)
        data['revision'] = result['revision']
        self.store.save(data)
        self.assertEqual(path.read_text(), first)

    def test_invalid_structure_does_not_write(self):
        for value in ['```java\n未闭合', '#### 实际完成内容\n冲突', '## 第 2 天 冲突']:
            data = self.payload()
            data['records']['代码、图、实验或问答证据'] = value
            with self.assertRaises(ValueError):
                self.store.save(data)
            self.assertEqual(self.store.snapshot()['revision'], self.initial['revision'])

    def test_migration_preserves_records_and_is_idempotent(self):
        from migrate_notes import migrate_week
        for path in self.root.glob('第*周-*.md'):
            source = path.read_text()
            changed = migrate_week(path, source)
            self.assertEqual(migrate_week(path, changed), changed)
        label = '代码、图、实验或问答证据'
        source = '- ' + label + '：```java\n  void run() {\n      work();\n  }\n  ```\n- 反馈与需要修正的理解：待记录。\n'
        value = read_field(source, label)
        changed = write_field(source, label, value)
        self.assertIn('#### ' + label + '\n\n```java\nvoid run() {\n    work();\n}\n```', changed)
        self.assertEqual(read_field(changed, label), value)

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

    def test_evidence_code_fences_round_trip(self):
        data = self.payload()
        evidence = '示例说明\n\n```java\nif (ready) {\n    run();\n\n    finish();\n}\n```\n\n验证完成'
        data['records']['代码、图、实验或问答证据'] = evidence
        self.store.save(data)
        self.assertEqual(self.store.snapshot()['weeks'][0]['days'][0]['records']['代码、图、实验或问答证据'], evidence)

    def test_external_unindented_fences_read_and_replace(self):
        label = '代码、图、实验或问答证据'
        value = '1. 中断丢失的示例：\n``` java\nvoid execute() {\n    prepare();\n    doBusiness();\n}\n```\n\n```kotlin\nACC_SYNCHRONIZED步骤原理：\n    ↓\nObjectMonitor\n```'
        path = self.root / self.initial['weeks'][0]['id']
        source = path.read_text()
        # 直接改临时 Markdown，模拟 Obsidian 手工编辑，不能通过 write_field 生成输入。
        start, _, end = field_span(source, label)
        source = source[:start] + '- ' + label + '：' + value + '\n' + source[end:]
        path.write_text(source)
        self.initial = self.store.snapshot()
        # 测试副本会包含实际学习进度，汇总应保留其他学习日的时长。
        self.expected_hours = sum(d['hours'] or 0 for w in self.initial['weeks'] for d in w['days']) - (self.initial['weeks'][0]['days'][0]['hours'] or 0) + 4.5
        self.assertEqual(self.initial['weeks'][0]['days'][0]['records'][label], value)
        data = self.payload()
        self.store.save(data)
        self.assertEqual(self.store.snapshot()['weeks'][0]['days'][0]['records'][label], value)
        self.assertEqual(path.read_text().count('void execute()'), 1)
        self.assertEqual(path.read_text().count('ACC_SYNCHRONIZED步骤原理'), 1)
        data['revision'] = self.store.snapshot()['revision']
        data['records'][label] = '新证据'
        self.store.save(data)
        self.assertNotIn('void execute()', path.read_text())
        self.assertNotIn('ACC_SYNCHRONIZED步骤原理', path.read_text())

    def test_field_boundaries_inside_fence(self):
        label = '代码、图、实验或问答证据'
        value = '```md\n- 反馈与需要修正的理解：代码中的文本\n## 第 2 天 代码中的标题\n```\n补充说明'
        source = '- ' + label + '：' + value + '\n- 反馈与需要修正的理解：真正的下一字段\n'
        self.assertEqual(read_field(source, label), value)
        changed = write_field(source, label, '替换后')
        self.assertIn('真正的下一字段', changed)
        self.assertNotIn('代码中的文本', changed)

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
        self.assertEqual(json.loads(result.stdout)['summary']['hours'], self.expected_hours)
        self.assertEqual(self.store.snapshot()['weeks'][0]['days'][0]['status'], '学习中')


if __name__ == '__main__':
    unittest.main()
