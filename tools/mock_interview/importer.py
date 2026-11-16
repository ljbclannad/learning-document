"""旧 Markdown 预检与显式导入；遇到不明确的事实停止，不猜测评分。"""

import json
import re
from datetime import date
from pathlib import Path

from .common import boolean, digest, dumps, integer, keys, now, require, text, uid
from .rules import DEFAULT_RULE, replay


def field(block, *names):
    for name in names:
        m = re.search(r"^- " + re.escape(name) + r"(?:（[^\n]*?）)?：(.+)$", block, re.M)
        if m:
            return m.group(1).strip()
    return ""


def preview(data):
    keys(data, ["request_id", "source_path", "topic_id", "mode", "report_hash", "source_hash", "resolutions", "rules_confirmed"])
    path = Path(text(data, "source_path")).expanduser().resolve()
    require(path.is_file(), "导入源文件不存在", "NOT_FOUND", exit_code=3)
    raw = path.read_bytes()
    content = raw.decode("utf-8")
    resolutions = data.get("resolutions", {})
    require(isinstance(resolutions, dict), "resolutions 必须是对象")
    blockers, warnings, records, index = [], [], [], {}
    for line in content.splitlines():
        if line.startswith("| "):
            cells = [x.strip() for x in line.strip().strip("|").split("|")]
            if len(cells) == 11 and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]+", cells[0]):
                if cells[0] in index:
                    blockers.append({"code": "DUPLICATE_CONCEPT", "concept_id": cells[0]})
                index[cells[0]] = cells
    if re.search(r"主动(?:加权|调为)|单题权重调整", content):
        blockers.append({"code": "MANUAL_WEIGHT_ADJUSTMENT", "message": "存在独立于评分的人工加权，第一版无法无损迁移；保留原文件，不导入。"})
    if "拉长复测间隔" in content or "隔一段时间" in content:
        warnings.append("旧记录有未量化的复测偏好，导入不会猜测数值；请另行明确配置。")
    if not boolean(data, "rules_confirmed"):
        blockers.append({"code": "RULES_UNCONFIRMED", "message": "核对来源规则与默认规则一致后，设置 rules_confirmed=true。"})
    current, number = None, 0
    pieces = re.split(r"(?=^###(?:#)? )", content, flags=re.M)
    for piece in pieces:
        heading = piece.splitlines()[0] if piece else ""
        if heading.startswith("### "):
            match = re.fullmatch(r"### ([A-Za-z0-9][A-Za-z0-9_-]+)\s*", heading)
            current = match.group(1) if match else None
            if "跳过记录" in heading:
                warnings.append("来源包含未评分跳过说明，将完整保留在导入批次来源文本中，不加入评分。")
        if not heading.startswith("#### 尝试"):
            continue
        number += 1
        source_key = "record-" + str(number)
        if not current:
            blockers.append({"code": "MISSING_CONCEPT", "source_key": source_key})
            continue
        question = field(piece, "实际问法")
        answer = field(piece, "用户回答摘要", "用户回答")
        grade_text = field(piece, "等级")
        match = re.match(r"([0-3])(?:\D|$)", grade_text)
        hint_text = field(piece, "是否提示")
        hinted = False if re.match(r"无|独立回答阶段无|评分前一次中性澄清", hint_text) else None
        session = field(piece, "会话").rstrip("。")
        session = session.split("（")[0].strip()
        date_match = re.search(r"\d{4}-\d{2}-\d{2}", field(piece, "时间"))
        attempt_number = re.search(r"尝试\s*(\d+)", heading)
        row = dict(source_key=source_key, concept_id=current, question=question, answer=answer,
                   is_summary="用户回答摘要" in piece, grade=int(match.group(1)) if match else None,
                   substantive_hint=hinted, session=session, time=date_match.group(0) if date_match else None,
                   time_precision="date" if date_match else "unknown", order=number, order_verified=False,
                   kind="retest" if attempt_number and int(attempt_number.group(1)) > 1 else "diagnostic",
                   basis=field(piece, "依据"), gaps=[field(piece, "具体错误或遗漏")],
                   corrected_points=[field(piece, "修正版要点")], raw=piece)
        patch = resolutions.get(source_key, {})
        keys(patch, ["grade", "substantive_hint", "session", "time", "order", "order_verified", "kind"])
        row.update(patch)
        if not row["question"] or not row["answer"] or not row["basis"]:
            blockers.append({"code": "MISSING_EVIDENCE", "source_key": source_key})
        if type(row["grade"]) is not int or row["grade"] not in range(4):
            blockers.append({"code": "UNKNOWN_GRADE", "source_key": source_key})
        if type(row["substantive_hint"]) is not bool:
            blockers.append({"code": "UNKNOWN_HINT", "source_key": source_key, "text": hint_text})
        if row["substantive_hint"] and row["grade"] == 3:
            blockers.append({"code": "HINTED_GRADE3", "source_key": source_key})
        require(isinstance(row["session"], str), "session 必须是字符串")
        if not row["session"]:
            blockers.append({"code": "UNKNOWN_SESSION", "source_key": source_key})
        integer(row, "order", minimum=1)
        boolean(row, "order_verified")
        require(row["kind"] in ("diagnostic", "retest"), "导入 kind 必须为 diagnostic 或 retest")
        if row["time"] is not None:
            require(isinstance(row["time"], str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["time"]), "旧记录仅支持明确的日期或 null")
            date.fromisoformat(row["time"])
        row["time_precision"] = "date" if row["time"] else "unknown"
        row["gaps"] = [x for x in row["gaps"] if x]
        row["corrected_points"] = [x for x in row["corrected_points"] if x]
        records.append(row)
    require(not (set(resolutions) - {r["source_key"] for r in records}), "resolutions 引用了不存在的来源条目")
    if not records:
        blockers.append({"code": "NO_ATTEMPTS", "message": "未发现支持的尝试历史格式，不能只从索引生成答题。"})
    if len({r["order"] for r in records}) != len(records):
        blockers.append({"code": "DUPLICATE_ORDER"})
    for cid, cells in index.items():
        found = [r for r in records if r["concept_id"] == cid]
        if not cells[4].isdigit() or len(found) != int(cells[4]):
            blockers.append({"code": "COUNT_MISMATCH", "concept_id": cid, "index_count": cells[4], "history_count": len(found)})
    for row in records:
        if row["concept_id"] not in index:
            blockers.append({"code": "MISSING_INDEX", "source_key": row["source_key"]})
    if any(not r["order_verified"] for r in records):
        warnings.append("未确认实际答题顺序的条目按来源顺序保留，不授予降权资格。可在 resolutions 中明确顺序及 order_verified。")
    differences = []
    if not blockers:
        history = [dict(id=r["source_key"], concept_id=r["concept_id"], session_id=r["session"],
                        kind=r["kind"], grade=r["grade"], rule=DEFAULT_RULE, answered_order=r["order"],
                        answered_at=r["time"], evaluation_status="confirmed", substantive_hint=r["substantive_hint"],
                        gaps=r["gaps"], order_verified=r["order_verified"]) for r in records]
        stats, _ = replay([{"id": cid} for cid in index], history)
        for cid, cells in index.items():
            for column, key in [(3, "weight"), (4, "attempt_count"), (5, "failure_count"), (6, "consecutive_failures"), (7, "qualified_retests"), (8, "last_grade")]:
                if not cells[column].isdigit() or stats[cid][key] != int(cells[column]):
                    differences.append({"concept_id": cid, "field": key, "source": cells[column], "computed": stats[cid][key]})
        if differences:
            blockers.append({"code": "STATS_MISMATCH", "message": "历史重算与来源索引不一致，请核对映射。"})
    report = dict(source_path=str(path), source_hash=digest(raw), topic_id=text(data, "topic_id"),
                  records=sorted(records, key=lambda r: r["order"]), index=index, blockers=blockers, warnings=warnings, differences=differences,
                  rules_confirmed=bool(data.get("rules_confirmed")), source_text=content)
    report["report_hash"] = digest(report)
    return report


def import_markdown(service, data):
    report = preview(data)
    if data.get("mode", "preview") == "preview":
        return report
    require(data.get("mode") == "apply", "mode 必须是 preview 或 apply")
    require(data.get("source_hash") == report["source_hash"] and data.get("report_hash") == report["report_hash"],
            "源文件或核对报告已变化，请重新预检", "IMPORT_REVIEW_REQUIRED", exit_code=6)
    require(not report["blockers"], "导入存在阻断项，请先核对", "IMPORT_REVIEW_REQUIRED", {"blockers": report["blockers"]}, 6)
    s = service.s

    def apply():
        topic = text(data, "topic_id")
        s.get("topics", topic)
        prior = s.one("SELECT * FROM import_batches WHERE source_hash=?", (report["source_hash"],))
        if prior:
            require(prior["report_hash"] == report["report_hash"], "该来源已按不同映射导入", "IMPORT_REVIEW_REQUIRED", exit_code=6)
            return {"batch_id": prior["id"], "already_imported": True}
        require(not service.attempts(topic) and not service.concepts(topic),
                "目标主题已有数据，第一版不合并导入", "IMPORT_REVIEW_REQUIRED", exit_code=6)
        require(not s.one("SELECT id FROM sessions WHERE topic_id=?", (topic,)), "目标主题已有会话", "IMPORT_REVIEW_REQUIRED", exit_code=6)
        current_rule = json.loads(service.rule(topic)["parameters_json"])
        require(current_rule == DEFAULT_RULE, "旧记录导入仅支持默认评分规则", "IMPORT_REVIEW_REQUIRED", exit_code=6)
        session_map, mapping = {}, []
        for cid, cells in report["index"].items():
            service.concept_create(dict(id=cid, topic_id=topic, title=cells[1], representative_question=cells[1],
                                        scope="从旧记录导入：" + cells[1], difficulty="进阶" if "难" in cells[2] else "中等"))
        for r in report["records"]:
            if r["session"] not in session_map:
                sid = uid("session")
                session_map[r["session"]] = sid
                s.insert("sessions", dict(id=sid, topic_id=topic, status="ended", feedback_mode="training",
                         started_at=r["time"] or "未知", ended_at=r["time"], revision=1))
                service.session_event(sid, "import", {"source_session": r["session"], "time_precision": r["time_precision"]})
            sid = session_map[r["session"]]
            sequence = s.one("SELECT COALESCE(MAX(sequence),0)+1 AS n FROM attempts WHERE session_id=?", (sid,))["n"]
            aid, eid, order = uid("attempt"), uid("event"), s.order()
            s.insert("attempts", dict(id=aid, session_id=sid, concept_id=r["concept_id"],
                     rule_version_id=service.rule(topic)["id"], preference_version_id=service.preference(topic)["id"],
                     question=r["question"], kind=r["kind"], status="evaluated", sequence=sequence,
                     answered_order=order, answered_at=r["time"], time_precision=r["time_precision"], created_at=now(), revision=1))
            s.insert("attempt_events", dict(id=eid, attempt_id=aid, event_type="answer", content=r["answer"],
                     metadata_json=dumps({"is_summary": r["is_summary"], "order_verified": r["order_verified"], "source_key": r["source_key"]}),
                     occurred_order=order, occurred_at=r["time"], time_precision=r["time_precision"]))
            s.insert("evaluations", dict(id=uid("evaluation"), attempt_id=aid, version=1, status="confirmed",
                     grade=r["grade"], substantive_hint=int(r["substantive_hint"]), answer_event_ids_json=dumps([eid]),
                     basis=r["basis"], gaps_json=dumps(r["gaps"]), corrected_points_json=dumps(r["corrected_points"]),
                     sources_json="[]", disputed_points_json="[]", revision_reason="从已核对来源导入", created_at=now()))
            mapping.append({"source_key": r["source_key"], "attempt_id": aid})
        stats, _ = service.rebuild(topic)
        differences = []
        for cid, cells in report["index"].items():
            st = stats[cid]
            for column, key in [(3, "weight"), (4, "attempt_count"), (5, "failure_count"), (6, "consecutive_failures"), (7, "qualified_retests"), (8, "last_grade")]:
                if not cells[column].isdigit() or st[key] != int(cells[column]):
                    differences.append({"concept_id": cid, "field": key, "source": cells[column], "computed": st[key]})
        require(not differences, "历史重算与索引不一致，本次导入已回滚；请核对顺序、类型和评分",
                "IMPORT_REVIEW_REQUIRED", {"differences": differences}, 6)
        batch_id = uid("import")
        s.insert("import_batches", dict(id=batch_id, source_path=report["source_path"], source_hash=report["source_hash"],
                 report_hash=report["report_hash"], status="applied", mapping_json=dumps({"mapping": mapping, "source_text": report["source_text"]}), created_at=now()))
        return {"batch_id": batch_id, "imported_attempts": len(mapping), "already_imported": False}
    return s.write("import markdown", data, apply)
