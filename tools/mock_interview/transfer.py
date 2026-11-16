"""Markdown 导出与一致性备份。"""

import json
import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .common import digest, dumps, keys, now, require, text, uid


def quote(value):
    """以引用块保留回答中的代码、换行和标题，避免破坏报告结构。"""
    return "\n".join("> " + line for line in str(value).splitlines()) or "> （无）"


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def local_time(value, tz):
    if not value:
        return "未知"
    if len(value) == 10:
        return value + "（仅日期）"
    return datetime.fromisoformat(value).astimezone(ZoneInfo(tz)).isoformat(timespec="seconds")


def render(service, topic):
    s = service.s
    info = service.topic_show(topic)
    stats, trail = service.computed(topic)
    concepts = service.concepts(topic)
    timestamp = now()
    revision = s.revision()
    lines = ["# " + info["name"].replace("\n", " ") + "面试训练记录", "",
             "<!-- mock-interview:managed-v1 -->", "",
             "本文件由工具生成，手写内容请保存在独立笔记中。", "",
             f"生成时间：{local_time(timestamp, info['timezone'])}；数据修订号：{revision}。", "",
             "## 范围与规则", "", quote(info["version_scope"]), ""]
    for r in info["rules"]:
        lines.extend([f"- 规则版本 {r['version']}：{r['parameters_json']}；生效时间 {local_time(r['effective_at'], info['timezone'])}。"])
    lines.extend(["", "当前调度偏好：" + dumps_preference(info["preferences"]), "", "## 考点索引", "",
                  "| 考点 | 难度 | 权重 | 独立作答 | 累计失误 | 连续失误 | 合格复测 | 最近等级 | 最后独立作答 | 当前缺口 |",
                  "|---|---|---|---|---|---|---|---|---|---|"])
    for c in concepts:
        st = stats[c["id"]]
        values = [c["id"] + "：" + c["title"], c["difficulty"], st["weight"], st["attempt_count"], st["failure_count"],
                  st["consecutive_failures"], st["qualified_retests"], st["last_grade"] if st["last_grade"] is not None else "未评分",
                  local_time(st["last_answered_at"], info["timezone"]), "；".join(st["current_gaps"])]
        lines.append("| " + " | ".join(cell(x) for x in values) + " |")
    lines.extend(["", "## 会话汇总", ""])
    for session in s.rows("SELECT * FROM sessions WHERE topic_id=? ORDER BY started_at,id", (topic,)):
        report = service.report_session(session["id"])
        lines.extend([f"### {session['id']}", "",
                      f"状态：{session['status']}。已评分独立作答 {report['graded_count']} 次；"
                      f"首次诊断 {report['groups']['diagnostic']['count']} 次；复测 {report['groups']['retest']['count']} 次。",
                      f"跳过 {report['skipped']} 题；未回答结束 {report['abandoned']} 题；练习 {report['practice']} 次；未决 {len(report['pending'])} 题。", ""])
    lines.extend(["训练成绩仅反映已确认的独立作答，不代表岗位胜任度。", "", "## 尝试历史", ""])
    for a in service.attempts(topic):
        detail = service.attempt_show(a["id"])
        effective_types = {e["id"]: e["event_type"] for e in detail["effective_events"]}
        lines.extend([f"### {a['concept_id']} 第 {a['sequence']} 题", "",
                      f"尝试 ID：{a['id']}；会话：{a['session_id']}；类型：{a['kind']}；状态：{a['status']}。", "",
                      "实际问法：", "", quote(a["question"]), ""])
        for e in detail["events"]:
            metadata = json.loads(e["metadata_json"])
            label = "摘要" if metadata.get("is_summary") else "原始记录"
            lines.extend([f"{e['event_type']}（{label}；{local_time(e['occurred_at'], info['timezone'])}）：", "", quote(e["content"]), ""])
            if e["event_type"] == "event_reclassification":
                lines.extend([f"分类修订目标：{metadata['event_id']}；{metadata['from_type']} → {metadata['to_type']}。", ""])
            elif effective_types.get(e["id"]) != e["event_type"]:
                lines.extend([f"当前有效分类：{effective_types[e['id']]}；原始分类保留。", ""])
        for e in detail["evaluations"]:
            lines.extend([f"评估版本 {e['version']}：{e['status']}；等级：{e['grade'] if e['grade'] is not None else '未评分'}；"
                          f"实质提示：{'是' if e['substantive_hint'] else '否'}。", "", quote(e["basis"]), "",
                          "缺口：" + "；".join(json.loads(e["gaps_json"])), "",
                          "修正版要点：", "", quote("\n".join(json.loads(e["corrected_points_json"]))), ""])
            if e["revision_reason"]:
                lines.extend(["修订原因：", "", quote(e["revision_reason"]), ""])
            for source in json.loads(e["sources_json"]):
                lines.extend([quote(source["title"] + "：" + source["url"] + "；" + source["note"]), ""])
            if json.loads(e["disputed_points_json"]):
                lines.extend(["待核实：", "", quote("\n".join(json.loads(e["disputed_points_json"]))), ""])
        if a["id"] in trail:
            step = trail[a["id"]]
            lines.extend([f"按当前有效评估重算的历史权重：{step['before']} → {step['after']}。", ""])
    return "\n".join(lines), timestamp, revision


def dumps_preference(p):
    return f"至少隔 {p['min_other_questions']} 道其他有效作答；仅跨会话复测：{'是' if p['cross_session_only'] else '否'}。"


def export_markdown(service, data):
    keys(data, ["request_id", "topic_id"])
    topic = text(data, "topic_id")
    s = service.s

    def apply():
        service.s.get("topics", topic)
        require(any(a["answered_order"] is not None for a in service.attempts(topic)),
                "尚无实际回答，不生成空白训练报告", "INVALID_STATE", exit_code=4)
        path = s.workspace / "面试训练记录/导出" / (topic + ".md")
        journal = s.path.parent / ("export-" + topic + ".json")
        previous = s.one("SELECT * FROM exports WHERE topic_id=?", (topic,))
        old_hash = digest(path.read_bytes()) if path.exists() else None
        require(not path.is_symlink(), "导出目标不能是符号链接", "EXPORT_CONFLICT", exit_code=6)
        fingerprint = digest(data)
        # 文件已替换、数据库事务未提交时，用写前日志认领已经完成的同一份导出。
        if journal.exists():
            pending = json.loads(journal.read_text(encoding="utf-8"))
            if old_hash == pending["content_hash"] and (not previous or previous["content_hash"] != old_hash):
                s.db.execute("INSERT INTO exports VALUES (?,?,?,?,?) ON CONFLICT(topic_id) DO UPDATE SET "
                             "path=excluded.path,content_hash=excluded.content_hash,data_revision=excluded.data_revision,exported_at=excluded.exported_at",
                             (topic, str(path), old_hash, pending["data_revision"], pending["exported_at"]))
                previous = s.one("SELECT * FROM exports WHERE topic_id=?", (topic,))
                if pending["request_hash"] == fingerprint:
                    return {"path": str(path), "exported_data_revision": pending["data_revision"],
                            "database_saved": True, "markdown_updated": True, "recovered": True}
        require(old_hash is None or (previous and old_hash == previous["content_hash"]),
                "导出目标已存在或被手工修改，未覆盖", "EXPORT_CONFLICT", {"path": str(path)}, 6)
        body, timestamp, revision = render(service, topic)
        raw = body.encode("utf-8")
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=".mock-export-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            # 重新检查，拒绝覆盖渲染期间已发生的外部编辑。
            current_hash = digest(path.read_bytes()) if path.exists() else None
            require(current_hash == old_hash and not path.is_symlink(), "导出期间目标被修改", "EXPORT_CONFLICT", exit_code=6)
            # 日志写入成功后才替换文档；日志本身同样使用原子替换。
            journal_fd, journal_tmp = tempfile.mkstemp(prefix=".export-journal-", dir=s.path.parent)
            try:
                with os.fdopen(journal_fd, "w", encoding="utf-8") as output:
                    output.write(dumps(dict(content_hash=digest(raw), data_revision=revision,
                                            exported_at=timestamp, request_hash=fingerprint)))
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(journal_tmp, journal)
            finally:
                if os.path.exists(journal_tmp):
                    os.unlink(journal_tmp)
            os.replace(temp_path, path)
            s.db.execute("INSERT INTO exports VALUES (?,?,?,?,?) ON CONFLICT(topic_id) DO UPDATE SET "
                         "path=excluded.path,content_hash=excluded.content_hash,data_revision=excluded.data_revision,exported_at=excluded.exported_at",
                         (topic, str(path), digest(raw), revision, timestamp))
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
        return {"path": str(path), "exported_data_revision": revision, "database_saved": True, "markdown_updated": True}

    return s.write("export markdown", data, apply)


def backup_create(service, data):
    keys(data, ["request_id"])
    s = service.s
    # 由独立只读连接制作备份，避免在持有写事务的连接上调用 backup 导致等待自身。
    def apply():
        directory = s.path.parent / "backups"
        directory.mkdir(exist_ok=True)
        path = directory / (uid("backup") + ".sqlite3")
        source = sqlite3.connect(s.path.as_uri() + "?mode=ro", uri=True)
        destination = sqlite3.connect(path)
        try:
            source.backup(destination)
        finally:
            destination.close()
            source.close()
        return {"path": str(path), "backup_data_revision": s.revision()}
    return s.write("backup create", data, apply)
