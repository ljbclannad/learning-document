"""将旧记录列表迁移为小标题正文；默认只检查，--apply 才备份并写入。"""
import argparse
import copy
import re
from datetime import datetime
from pathlib import Path
import secrets

from server import (DEFAULT_ROOT, RECORDS, REVIEWS, Store, Conflict, day_matches,
                    field_span, read_field, write_field, parse_week, split_review,
                    HEADING_RE, fence_state, validate_body)


def legacy_body(value):
    """只解除旧围栏块残留的外层缩进，保留代码内部相对缩进和所有文字。"""
    lines = value.split('\n')
    active, indent = None, 0
    result = []
    for line in lines:
        next_active = fence_state(line, active)
        if active is None and next_active is not None:
            indent = len(line) - len(line.lstrip(' '))
        if active is not None or next_active is not None:
            if indent and line.startswith(' ' * indent):
                line = line[indent:]
        result.append(line if line.strip() else '')
        active = next_active
    return '\n'.join(result).strip('\n')


def migrate_section(text, labels):
    expected = {}
    for label in labels:
        start, _, _ = field_span(text, label)
        value = read_field(text, label)
        if not HEADING_RE.match(text[start:]):
            value = legacy_body(value)
        validate_body(value)
        expected[label] = value.strip('\n')
        text = write_field(text, label, value)
    for label, value in expected.items():
        if read_field(text, label) != value:
            raise ValueError(f'迁移内容不一致：{label}')
    return text, expected


def migrate_week(path, source):
    before = parse_week(path, source)
    expected = copy.deepcopy(before)
    result = source
    matches = day_matches(source)
    for index in reversed(range(len(matches))):
        match = matches[index]
        block, values = migrate_section(source[match.start():match.end()], RECORDS)
        result = result[:match.start()] + block + result[match.end():]
        expected['days'][index]['records'] = values
    prefix, review = split_review(result)
    review, values = migrate_section(review, REVIEWS)
    result = prefix + '## 周复盘\n' + review
    expected['review'] = values
    if parse_week(path, result) != expected:
        raise ValueError(f'{path.name} 的内容或学习状态发生非预期变化')
    return result


def migrate(root, apply=False):
    store = Store(root)
    docs = store.read()
    changes = {p: migrate_week(p, text) for p, text in docs.items() if p.name != '学习进度记录.md'}
    for path, text in changes.items():
        if migrate_week(path, text) != text:
            raise ValueError(f'重复转换不稳定：{path.name}')
    changes = {p: text for p, text in changes.items() if text != docs[p]}
    print(f'已核对 {len(docs) - 1} 周、60 个学习日；需要转换 {len(changes)} 份周计划。')
    if not apply or not changes:
        return
    backup = root / '.学习进度备份' / ('格式迁移-' + datetime.now().strftime('%Y%m%d-%H%M%S-') + secrets.token_hex(4))
    backup.mkdir(parents=True)
    for path, text in docs.items():
        (backup / path.name).write_text(text, encoding='utf-8')
    if store.revision(store.read()) != store.revision(docs):
        raise Conflict('备份后发现外部修改，停止迁移。')
    committed = []
    try:
        for path, text in changes.items():
            if path.read_text(encoding='utf-8') != docs[path]:
                raise Conflict(f'{path.name} 已在外部修改，停止迁移。')
            store.atomic_write(path, text)
            committed.append(path)
    except Exception:
        for path in committed:
            if path.read_text(encoding='utf-8') == changes[path]:
                store.atomic_write(path, docs[path])
        raise
    print(f'转换完成，原文备份：{backup}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    migrate(args.root, args.apply)
