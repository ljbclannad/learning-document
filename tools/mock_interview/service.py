"""面试领域操作；所有写操作由 Store.write 包裹为单个事务。"""

import json
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .common import (AppError, boolean, dumps, identifier, integer, keys, now, require,
                     strings, text, uid, utc_time)
from .rules import DEFAULT_RULE, replay, validate_rule


WRITE_FIELDS = {
    "topic create": "id name version_scope timezone",
    "topic configure": "topic_id min_other_questions cross_session_only reason",
    "rule create": "topic_id parameters effective_at reason",
    "concept create": "id topic_id title representative_question scope difficulty",
    "session start": "topic_id host_id thread_id feedback_mode",
    "session resume": "session_id host_id thread_id",
    "session pause": "session_id",
    "session end": "session_id",
    "session defer": "session_id concept_id deferred reason",
    "attempt create": "session_id concept_id question kind",
    "attempt append": "attempt_id event_type content metadata",
    "attempt skip": "attempt_id reason",
    "attempt evaluate": "attempt_id evaluation",
    "attempt revise": "attempt_id evaluation evaluation_version reason",
    "attempt reclassify": "attempt_id event_id event_type reason evaluation evaluation_version restore_kind",
    "stats rebuild": "topic_id expected_data_revision",
}
ANSWER_TYPES = {"answer", "cannot_answer", "clarification_answer"}
EVENT_TYPES = ANSWER_TYPES | {"clarification_question", "hint", "explanation", "correction", "correction_skipped", "supplement"}


class Service:
    def __init__(self, store):
        self.s = store

    def write(self, operation, data):
        keys(data, WRITE_FIELDS[operation].split() + ["request_id", "expected_revision"])
        handler = getattr(self, operation.replace(" ", "_"))
        return self.s.write(operation, data, lambda: handler(data))

    def concepts(self, topic):
        self.s.get("topics", topic)
        return self.s.rows("SELECT * FROM concepts WHERE topic_id=? ORDER BY id", (topic,))

    def preference(self, topic):
        return self.s.one("SELECT * FROM preference_versions WHERE topic_id=? ORDER BY version DESC LIMIT 1", (topic,))

    def rule(self, topic):
        row = self.s.one("SELECT * FROM rule_versions WHERE topic_id=? AND effective_at<=? "
                         "ORDER BY effective_at DESC,version DESC LIMIT 1", (topic, now()))
        require(row is not None, "没有已生效的评分规则", "INVALID_STATE", exit_code=4)
        return row

    def attempts(self, topic):
        return self.s.rows("SELECT a.* FROM attempts a JOIN sessions s ON s.id=a.session_id "
                           "WHERE s.topic_id=? ORDER BY a.answered_order,a.created_at,a.sequence", (topic,))

    def latest(self, attempt):
        return self.s.one("SELECT * FROM evaluations WHERE attempt_id=? ORDER BY version DESC LIMIT 1", (attempt,))

    def history(self, topic):
        result = []
        for a in self.attempts(topic):
            e = self.latest(a["id"])
            if e is None:
                continue
            rule = self.s.get("rule_versions", a["rule_version_id"])
            events = self.s.rows("SELECT metadata_json FROM attempt_events WHERE attempt_id=?", (a["id"],))
            result.append(dict(a, evaluation_status=e["status"], grade=e["grade"],
                               substantive_hint=e["substantive_hint"], gaps=json.loads(e["gaps_json"]),
                               rule=json.loads(rule["parameters_json"]),
                               order_verified=all(json.loads(x["metadata_json"]).get("order_verified", True)
                                                  for x in events)))
        return result

    def computed(self, topic):
        return replay(self.concepts(topic), self.history(topic))

    def rebuild(self, topic):
        stats, trail = self.computed(topic)
        for row in stats.values():
            item = dict(row)
            item["current_gaps_json"] = dumps(item.pop("current_gaps"))
            item["computed_revision"] = self.s.revision() + 1
            columns = list(item)
            self.s.db.execute("INSERT INTO concept_stats (" + ",".join(columns) + ") VALUES ("
                              + ",".join("?" for _ in columns) + ") ON CONFLICT(concept_id) DO UPDATE SET "
                              + ",".join(k + "=excluded." + k for k in columns if k != "concept_id"),
                              tuple(item.values()))
        return stats, trail

    def topic_create(self, d):
        tid = identifier(d, topic=True)
        tz = d.get("timezone", "Asia/Shanghai")
        require(isinstance(tz, str), "timezone 必须是字符串")
        try:
            ZoneInfo(tz)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise AppError("INVALID_INPUT", "时区不受支持") from exc
        self.s.insert("topics", dict(id=tid, name=text(d, "name"), version_scope=text(d, "version_scope"),
                                      timezone=tz, revision=1, created_at=now()))
        self.s.insert("rule_versions", dict(id=uid("rule"), topic_id=tid, version=1,
                      parameters_json=dumps(DEFAULT_RULE), effective_at=now(), reason="skill 默认规则", created_at=now()))
        self.s.insert("preference_versions", dict(id=uid("preference"), topic_id=tid, version=1,
                      min_other_questions=2, cross_session_only=0, reason="skill 默认间隔", created_at=now()))
        return self.topic_show(tid)

    def topic_show(self, topic):
        row = self.s.get("topics", topic)
        row["rules"] = self.s.rows("SELECT * FROM rule_versions WHERE topic_id=? ORDER BY version", (topic,))
        row["preferences"] = self.preference(topic)
        row["open_session"] = self.s.one("SELECT * FROM sessions WHERE topic_id=? AND status!='ended'", (topic,))
        row["unresolved"] = [a for a in self.attempts(topic)
                             if a["status"] in ("awaiting_answer", "awaiting_evaluation", "pending_verification")]
        return row

    def topic_configure(self, d):
        topic = self.s.get("topics", text(d, "topic_id"))
        self.s.check_revision(topic, d)
        old = self.preference(topic["id"])
        self.s.insert("preference_versions", dict(id=uid("preference"), topic_id=topic["id"], version=old["version"]+1,
                      min_other_questions=integer(d, "min_other_questions", old["min_other_questions"], minimum=2),
                      cross_session_only=int(boolean(d, "cross_session_only", bool(old["cross_session_only"]))),
                      reason=text(d, "reason"), created_at=now()))
        self.s.bump("topics", topic["id"])
        return self.topic_show(topic["id"])

    def rule_create(self, d):
        topic = self.s.get("topics", text(d, "topic_id"))
        self.s.check_revision(topic, d)
        parameters = validate_rule(d.get("parameters", {}), json.loads(self.rule(topic["id"])["parameters_json"]))
        timestamp = now()
        effective = utc_time(d["effective_at"]) if "effective_at" in d else timestamp
        require(effective >= timestamp, "新规则不能回溯生效；立即生效时省略 effective_at")
        version = self.s.one("SELECT MAX(version)+1 AS n FROM rule_versions WHERE topic_id=?", (topic["id"],))["n"]
        self.s.insert("rule_versions", dict(id=uid("rule"), topic_id=topic["id"], version=version,
                      parameters_json=dumps(parameters), effective_at=effective, reason=text(d, "reason"), created_at=timestamp))
        self.s.bump("topics", topic["id"])
        return self.topic_show(topic["id"])

    def concept_create(self, d):
        self.s.get("topics", text(d, "topic_id"))
        cid = identifier(d)
        difficulty = d.get("difficulty", "中等")
        require(difficulty in ("基础", "中等", "进阶"), "difficulty 仅支持基础、中等、进阶")
        self.s.insert("concepts", dict(id=cid, topic_id=d["topic_id"], title=text(d, "title"),
                      representative_question=text(d, "representative_question"), scope=text(d, "scope"),
                      difficulty=difficulty, created_at=now()))
        self.rebuild(d["topic_id"])
        return self.s.get("concepts", cid)

    def session_event(self, sid, kind, payload):
        self.s.insert("session_events", dict(id=uid("session-event"), session_id=sid, event_type=kind,
                      payload_json=dumps(payload), created_at=now()))

    def session_start(self, d):
        self.s.get("topics", text(d, "topic_id"))
        old = self.s.one("SELECT * FROM sessions WHERE topic_id=? AND status!='ended'", (d["topic_id"],))
        require(not old, "主题已有未结束会话，请恢复", "INVALID_STATE", {"open_session": old}, 4)
        mode = d.get("feedback_mode", "training")
        require(mode in ("training", "strict"), "feedback_mode 仅支持 training 或 strict")
        sid = uid("session")
        self.s.insert("sessions", dict(id=sid, topic_id=d["topic_id"], status="active", feedback_mode=mode,
                      started_at=now(), revision=1))
        self.session_event(sid, "start", {"host_id": text(d, "host_id", "local"), "thread_id": text(d, "thread_id")})
        return self.session_show(sid)

    def session_show(self, sid):
        row = self.s.get("sessions", sid)
        row["attempts"] = self.s.rows("SELECT * FROM attempts WHERE session_id=? ORDER BY sequence", (sid,))
        row["events"] = self.s.rows("SELECT * FROM session_events WHERE session_id=? ORDER BY rowid", (sid,))
        return row

    def session_transition(self, d, target):
        session = self.s.get("sessions", text(d, "session_id"))
        self.s.check_revision(session, d)
        require(session["status"] != "ended", "会话已经结束，不能重新打开或修改状态", "INVALID_STATE", exit_code=4)
        self.s.db.execute("UPDATE sessions SET status=?,ended_at=? WHERE id=?",
                          (target, now() if target == "ended" else None, session["id"]))
        if target == "ended":
            self.s.db.execute("UPDATE attempts SET status='abandoned',revision=revision+1 "
                              "WHERE session_id=? AND status='awaiting_answer'", (session["id"],))
        payload = {k: d[k] for k in ("host_id", "thread_id") if k in d}
        for value in payload.values():
            require(isinstance(value, str) and value.strip(), "聊天标识必须是非空字符串")
        self.session_event(session["id"], target, payload)
        self.s.bump("sessions", session["id"])
        result = self.session_show(session["id"])
        if target == "ended":
            result["report"] = self.report_session(session["id"])
        return result

    def session_resume(self, d):
        return self.session_transition(d, "active")

    def session_pause(self, d):
        return self.session_transition(d, "paused")

    def session_end(self, d):
        return self.session_transition(d, "ended")

    def session_defer(self, d):
        session = self.s.get("sessions", text(d, "session_id"))
        self.s.check_revision(session, d)
        concept = self.s.get("concepts", text(d, "concept_id"))
        require(concept["topic_id"] == session["topic_id"], "考点与会话主题不一致")
        require(session["status"] != "ended", "会话已经结束", "INVALID_STATE", exit_code=4)
        self.session_event(session["id"], "defer", dict(concept_id=concept["id"],
                           deferred=boolean(d, "deferred"), reason=text(d, "reason")))
        self.s.bump("sessions", session["id"])
        return self.session_show(session["id"])

    def eligibility(self, session, cid):
        topic, sid = session["topic_id"], session["id"]
        deferred = False
        for event in self.s.rows("SELECT payload_json FROM session_events WHERE session_id=? AND event_type='defer' ORDER BY rowid", (sid,)):
            p = json.loads(event["payload_json"])
            if p["concept_id"] == cid:
                deferred = p["deferred"]
        if deferred:
            return {"eligible": False, "reason": "本轮暂缓"}
        attempts = [a for a in self.attempts(topic) if a["concept_id"] == cid]
        if any(a["status"] in ("awaiting_evaluation", "pending_verification") for a in attempts):
            return {"eligible": False, "reason": "该考点尚有未决评估"}
        # 任何学习反馈都重置调度间隔，避免刚讲解后立刻独立复测。
        anchor = self.s.one("SELECT e.*,a.session_id FROM attempt_events e JOIN attempts a ON a.id=e.attempt_id "
                            "WHERE a.concept_id=? AND e.event_type NOT IN ('correction_skipped','event_reclassification') "
                            "ORDER BY e.occurred_order DESC LIMIT 1", (cid,))
        if not anchor:
            return {"eligible": True, "reason": "尚无回答或学习反馈", "other_questions": 0}
        pref = self.preference(topic)
        others = sum(a["concept_id"] != cid and a["evaluation_status"] == "confirmed"
                     and a["kind"] != "practice" and a["answered_order"] > anchor["occurred_order"]
                     for a in self.history(topic))
        anchor_session = json.loads(anchor["metadata_json"]).get("learning_session_id", anchor["session_id"])
        across = sid != anchor_session
        eligible = across or (not pref["cross_session_only"] and others >= pref["min_other_questions"])
        return {"eligible": bool(eligible), "reason": "满足复测间隔" if eligible else "尚未满足复测间隔",
                "other_questions": others, "required_other_questions": pref["min_other_questions"],
                "cross_session": across, "cross_session_only": bool(pref["cross_session_only"])}

    def next(self, sid):
        session = self.s.get("sessions", sid)
        require(session["status"] == "active", "请先恢复或开始会话", "INVALID_STATE", exit_code=4)
        current = self.s.one("SELECT * FROM attempts WHERE session_id=? AND status IN "
                             "('awaiting_answer','awaiting_evaluation')", (sid,))
        if current:
            return {"mode": "current", "attempt": self.attempt_show(current["id"]), "session_revision": session["revision"]}
        stats, _ = self.computed(session["topic_id"])
        count = sum(a["session_id"] == sid and a["evaluation_status"] == "confirmed" and a["kind"] != "practice"
                    for a in self.history(session["topic_id"]))
        candidates, excluded, new = [], [], []
        for c in self.concepts(session["topic_id"]):
            st = stats[c["id"]]
            evidence = self.eligibility(session, c["id"])
            item = dict(concept=c, stats=st, eligibility=evidence)
            if not evidence["eligible"]:
                excluded.append(item)
            elif not st["attempt_count"]:
                new.append(item)
            elif st["weight"] > 1 or st["last_grade"] in (0, 1):
                candidates.append(item)
        candidates.sort(key=lambda x: (-x["stats"]["weight"], x["stats"]["last_answered_order"] or 0, x["concept"]["id"]))
        mode = "retest" if count % 3 != 2 and candidates else "new_question_needed"
        return dict(mode=mode, candidates=candidates if mode == "retest" else new, excluded=excluded,
                    completed_positions=count, session_revision=session["revision"], preferences=self.preference(session["topic_id"]))

    def attempt_create(self, d):
        session = self.s.get("sessions", text(d, "session_id"))
        self.s.check_revision(session, d)
        require(session["status"] == "active", "仅活动会话可以出题", "INVALID_STATE", exit_code=4)
        concept = self.s.get("concepts", text(d, "concept_id"))
        require(concept["topic_id"] == session["topic_id"], "考点与会话主题不一致")
        require(not self.s.one("SELECT id FROM attempts WHERE session_id=? AND status IN "
                              "('awaiting_answer','awaiting_evaluation')", (session["id"],)),
                "已有当前题，请先完成或跳过", "INVALID_STATE", exit_code=4)
        kind = d.get("kind", "diagnostic")
        require(kind in ("diagnostic", "retest", "practice"), "kind 不受支持")
        st = self.computed(session["topic_id"])[0][concept["id"]]
        if kind != "practice":
            eligible = self.eligibility(session, concept["id"])
            require(eligible["eligible"], eligible["reason"], "INVALID_STATE", eligible, 4)
            require((kind == "diagnostic") == (st["attempt_count"] == 0),
                    "已有独立评分的考点须使用 retest；无独立评分的考点使用 diagnostic")
        aid = uid("attempt")
        sequence = self.s.one("SELECT COALESCE(MAX(sequence),0)+1 AS n FROM attempts WHERE session_id=?", (session["id"],))["n"]
        self.s.insert("attempts", dict(id=aid, session_id=session["id"], concept_id=concept["id"],
                      rule_version_id=self.rule(session["topic_id"])["id"],
                      preference_version_id=self.preference(session["topic_id"])["id"], question=text(d, "question"),
                      kind=kind, status="awaiting_answer", sequence=sequence, created_at=now(), revision=1))
        self.s.bump("sessions", session["id"])
        return self.attempt_show(aid)

    def attempt_show(self, aid):
        a = self.s.get("attempts", aid)
        a["events"] = self.s.rows("SELECT * FROM attempt_events WHERE attempt_id=? ORDER BY occurred_order", (aid,))
        a["effective_events"] = self.effective_events(aid)
        a["evaluations"] = self.s.rows("SELECT * FROM evaluations WHERE attempt_id=? ORDER BY version", (aid,))
        a["session_revision"] = self.s.get("sessions", a["session_id"])["revision"]
        return a

    def effective_events(self, aid):
        """保留原事件，按追加的分类修订生成当前有效视图。"""
        events = self.s.rows("SELECT * FROM attempt_events WHERE attempt_id=? ORDER BY occurred_order", (aid,))
        effective = {}
        for event in events:
            if event["event_type"] == "event_reclassification":
                revision = json.loads(event["metadata_json"])
                target = effective[revision["event_id"]]
                target["event_type"] = revision["to_type"]
                if "kind_before_hint" in revision:
                    target["metadata_json"] = dumps(dict(json.loads(target["metadata_json"]),
                                                        kind_before_hint=revision["kind_before_hint"]))
            else:
                effective[event["id"]] = dict(event, original_event_type=event["event_type"])
        return list(effective.values())

    def attempt_reclassify(self, d):
        a = self.s.get("attempts", text(d, "attempt_id"))
        self.s.check_revision(a, d)
        events = self.effective_events(a["id"])
        target = next((e for e in events if e["id"] == text(d, "event_id")), None)
        require(target is not None, "事件不属于本次尝试")
        new_type = text(d, "event_type")
        require({target["event_type"], new_type} == {"hint", "clarification_question"},
                "仅支持提示与中性澄清提问之间的分类修订")
        require(new_type != "clarification_question" or not any(
            e["event_type"] == "clarification_question" for e in events), "每题最多一次中性澄清")
        reason = text(d, "reason")
        old = self.latest(a["id"])
        if old:
            require("evaluation" in d and "evaluation_version" in d,
                    "已有评估时，分类修订必须同时提交新的完整评估及原评估版本")
        else:
            require("evaluation" not in d and "evaluation_version" not in d,
                    "尚无评估时只修订分类，之后单独 evaluate")
        metadata = dict(event_id=target["id"], from_type=target["event_type"], to_type=new_type,
                        attempt_kind_before=a["kind"])
        before_answer = a["answered_order"] is None or target["occurred_order"] < a["answered_order"]
        restored = None
        if before_answer:
            if new_type == "hint":
                metadata["kind_before_hint"] = a["kind"]
                restored = "practice"
            elif not any(e["id"] != target["id"] and e["event_type"] == "hint" and
                         (a["answered_order"] is None or e["occurred_order"] < a["answered_order"]) for e in events):
                provenance = [json.loads(e["metadata_json"]).get("kind_before_hint") for e in events
                              if a["answered_order"] is None or e["occurred_order"] < a["answered_order"]]
                restored = next((k for k in provenance if k and k != "practice"), None)
                if restored is None:
                    known = json.loads(target["metadata_json"]).get("kind_before_hint")
                    restored = known or d.get("restore_kind")
                require(restored in ("diagnostic", "retest", "practice"),
                        "旧事件缺少题目类型来源，请明确提供 restore_kind 并在 reason 中说明依据")
        if "restore_kind" in d:
            require(restored == d["restore_kind"], "restore_kind 与可恢复的原类型不一致")
        if restored:
            self.s.db.execute("UPDATE attempts SET kind=? WHERE id=?", (restored, a["id"]))
        metadata["attempt_kind_after"] = restored or a["kind"]
        self.s.insert("attempt_events", dict(id=uid("event"), attempt_id=a["id"], event_type="event_reclassification",
                      content=reason, metadata_json=dumps(metadata), occurred_order=self.s.order(), occurred_at=now(), time_precision="exact"))
        if old:
            # 分类和评估处于同一外层事务，任何校验失败都撤销整次修订。
            result = self.evaluate(d, revise=True)
            result["reclassified_event_id"] = target["id"]
            return result
        self.s.bump("attempts", a["id"])
        self.s.bump("sessions", a["session_id"])
        return self.attempt_show(a["id"])

    def attempt_append(self, d):
        a = self.s.get("attempts", text(d, "attempt_id"))
        self.s.check_revision(a, d)
        kind = text(d, "event_type")
        require(kind in EVENT_TYPES, "交互类型不受支持")
        content = text(d, "content")
        metadata = d.get("metadata", {})
        keys(metadata, ["is_summary"])
        if "is_summary" in metadata:
            boolean(metadata, "is_summary")
        status = a["status"]
        events = self.effective_events(a["id"])
        late_cannot = (kind == "cannot_answer" and status == "awaiting_evaluation" and events
                       and events[-1]["event_type"] == "clarification_question")
        if kind in ("answer", "cannot_answer"):
            require(status == "awaiting_answer" or late_cannot, "独立回答已经保存，不能重复追加", "INVALID_STATE", exit_code=4)
            require(self.s.get("sessions", a["session_id"])["status"] == "active", "请先恢复会话再回答", "INVALID_STATE", exit_code=4)
        elif kind in ("clarification_question", "clarification_answer"):
            require(status == "awaiting_evaluation", "澄清仅适用于待评估回答", "INVALID_STATE", exit_code=4)
            if kind == "clarification_question":
                require(not any(e["event_type"] == kind for e in events), "每题最多一次中性澄清")
            else:
                require(events and events[-1]["event_type"] == "clarification_question", "须先保存中性澄清提问")
        elif kind == "hint":
            require(status in ("awaiting_answer", "awaiting_evaluation"), "当前状态不能追加提示", "INVALID_STATE", exit_code=4)
            if status == "awaiting_answer":
                metadata = dict(metadata, kind_before_hint=a["kind"])
                self.s.db.execute("UPDATE attempts SET kind='practice' WHERE id=?", (a["id"],))
        elif kind == "supplement":
            require(status in ("awaiting_evaluation", "pending_verification", "evaluated", "practice_completed"),
                    "补充回答需要已有首次回答", "INVALID_STATE", exit_code=4)
        else:
            require(status in ("evaluated", "practice_completed"), "讲解或修正反馈须在正式评估后追加", "INVALID_STATE", exit_code=4)
        if kind in ("supplement", "explanation", "correction", "correction_skipped"):
            topic = self.s.get("sessions", a["session_id"])["topic_id"]
            current = self.s.one("SELECT id FROM sessions WHERE topic_id=? AND status='active'", (topic,))
            if current:
                metadata = dict(metadata, learning_session_id=current["id"])
        event_id, timestamp, order = uid("event"), now(), self.s.order()
        self.s.insert("attempt_events", dict(id=event_id, attempt_id=a["id"], event_type=kind, content=content,
                      metadata_json=dumps(metadata), occurred_order=order, occurred_at=timestamp, time_precision="exact"))
        if kind in ("answer", "cannot_answer") and not late_cannot:
            self.s.db.execute("UPDATE attempts SET status='awaiting_evaluation',answered_order=?,answered_at=? WHERE id=?",
                              (order, timestamp, a["id"]))
        self.s.bump("attempts", a["id"])
        self.s.bump("sessions", a["session_id"])
        return dict(self.attempt_show(a["id"]), event_id=event_id)

    def attempt_skip(self, d):
        a = self.s.get("attempts", text(d, "attempt_id"))
        self.s.check_revision(a, d)
        require(a["status"] == "awaiting_answer", "仅未作答题可以普通跳过", "INVALID_STATE", exit_code=4)
        self.s.insert("attempt_events", dict(id=uid("event"), attempt_id=a["id"], event_type="skip",
                      content=text(d, "reason"), metadata_json="{}", occurred_order=self.s.order(), occurred_at=now(), time_precision="exact"))
        self.s.db.execute("UPDATE attempts SET status='skipped',revision=revision+1 WHERE id=?", (a["id"],))
        self.s.bump("sessions", a["session_id"])
        return self.attempt_show(a["id"])

    def validate_evaluation(self, a, e):
        keys(e, ["status", "grade", "answer_event_ids", "substantive_hint", "basis", "gaps", "corrected_points", "sources", "disputed_points"])
        state = e.get("status", "confirmed")
        require(state in ("confirmed", "pending_verification", "practice"), "评估状态不受支持")
        require(state == "pending_verification" or (a["kind"] == "practice") == (state == "practice"),
                "练习核实后只允许 practice 反馈，独立回答不能改记练习")
        grade = e.get("grade")
        if state == "confirmed":
            integer(e, "grade", minimum=0, maximum=3)
        else:
            require(grade is None, "非正式评估 grade 必须为空")
        basis = text(e, "basis")
        evidence = strings(e, "answer_event_ids")
        require(bool(evidence) and len(set(evidence)) == len(evidence), "必须引用实际回答事件，且不能重复")
        events = self.effective_events(a["id"])
        evidence_types = ANSWER_TYPES | ({"supplement"} if a["kind"] == "practice" else set())
        answers = {x["id"]: x for x in events if x["event_type"] in evidence_types}
        require(set(evidence) <= set(answers), "引用的回答不属于本次尝试")
        hinted = boolean(e, "substantive_hint")
        hints = [x for x in events if x["event_type"] == "hint"]
        require(not hints or hinted, "存在实质提示事件，评估必须标记 substantive_hint")
        require(not (hinted and grade == 3), "实质提示后的回答不能评为等级 3")
        if hints and state == "confirmed":
            require(all(answers[x]["occurred_order"] < hints[0]["occurred_order"] for x in evidence),
                    "评分依据只能引用实质提示前的独立回答")
        if any(x["event_type"] == "cannot_answer" and (not hints or x["occurred_order"] < hints[0]["occurred_order"])
               for x in events) and state == "confirmed":
            require(grade == 0, "明确不会的独立回答应记为等级 0")
        sources = e.get("sources", [])
        require(isinstance(sources, list), "sources 必须是数组")
        for source in sources:
            keys(source, ["title", "url", "note"])
            text(source, "title")
            url = urlparse(text(source, "url"))
            require(url.scheme in ("https", "http") and url.netloc, "来源必须是 HTTP 或 HTTPS 链接")
            text(source, "note")
        disputed = strings(e, "disputed_points")
        require(state != "pending_verification" or bool(disputed), "待核实评估必须说明争议项")
        return dict(status=state, grade=grade, substantive_hint=int(hinted), basis=basis,
                    answer_event_ids_json=dumps(evidence), gaps_json=dumps(strings(e, "gaps")),
                    corrected_points_json=dumps(strings(e, "corrected_points")), sources_json=dumps(sources),
                    disputed_points_json=dumps(disputed))

    def evaluate(self, d, revise=False):
        a = self.s.get("attempts", text(d, "attempt_id"))
        self.s.check_revision(a, d)
        old = self.latest(a["id"])
        if revise:
            require(old is not None, "尚无评估，请使用 evaluate", "INVALID_STATE", exit_code=4)
            require(integer(d, "evaluation_version", minimum=1) == old["version"], "评估版本已经变化", "REVISION_CONFLICT", exit_code=4)
            reason = text(d, "reason")
        else:
            require(old is None and a["status"] == "awaiting_evaluation", "本题已有评估或尚未回答", "INVALID_STATE", exit_code=4)
            reason = None
        evaluation = self.validate_evaluation(a, d.get("evaluation", {}))
        topic = self.s.get("sessions", a["session_id"])["topic_id"]
        before = self.computed(topic)[0][a["concept_id"]]
        version = old["version"]+1 if old else 1
        self.s.insert("evaluations", dict(evaluation, id=uid("evaluation"), attempt_id=a["id"], version=version,
                      supersedes_id=old["id"] if old else None, revision_reason=reason, created_at=now()))
        status = {"confirmed": "evaluated", "pending_verification": "pending_verification", "practice": "practice_completed"}[evaluation["status"]]
        # 修订成待核实不会占用当前题；正式评估也不占用出题位置。
        self.s.db.execute("UPDATE attempts SET status=?,revision=revision+1 WHERE id=?", (status, a["id"]))
        self.s.bump("sessions", a["session_id"])
        stats, trail = self.rebuild(topic)
        return dict(attempt_id=a["id"], revision=a["revision"]+1, evaluation_version=version, status=status,
                    weight_before=before["weight"], weight_after=stats[a["concept_id"]]["weight"],
                    stats_before=before, stats_after=stats[a["concept_id"]], historical_weight=trail.get(a["id"]),
                    markdown_updated=False)

    def attempt_evaluate(self, d):
        return self.evaluate(d)

    def attempt_revise(self, d):
        return self.evaluate(d, True)

    def stats_rebuild(self, d):
        require(integer(d, "expected_data_revision") == self.s.revision(), "数据已经变化，请重新读取", "REVISION_CONFLICT", exit_code=4)
        stats, _ = self.rebuild(text(d, "topic_id"))
        return {"stats": list(stats.values())}

    def report_weaknesses(self, topic):
        stats, _ = self.computed(topic)
        concepts = {c["id"]: c for c in self.concepts(topic)}
        rows = [dict(s, concept=concepts[cid]) for cid, s in stats.items()
                if s["weight"] > 1 or s["last_grade"] in (0, 1)]
        rows.sort(key=lambda x: (-x["weight"], x["last_answered_order"] or 0, x["concept_id"]))
        return {"topic_id": topic, "weaknesses": rows, "data_revision": self.s.revision()}

    def report_session(self, sid):
        session = self.s.get("sessions", sid)
        attempts = [a for a in self.attempts(session["topic_id"]) if a["session_id"] == sid]
        history = [a for a in self.history(session["topic_id"]) if a["session_id"] == sid]
        graded = [a for a in history if a["evaluation_status"] == "confirmed" and a["kind"] != "practice"]
        groups = {}
        for kind in ("diagnostic", "retest"):
            group = [a for a in graded if a["kind"] == kind]
            groups[kind] = dict(count=len(group), grade_counts={str(g): sum(a["grade"] == g for a in group) for g in range(4)})
        return dict(session=session, groups=groups, graded_count=len(graded),
                    pending=[a["id"] for a in attempts if a["status"] in ("awaiting_answer", "awaiting_evaluation", "pending_verification")],
                    skipped=sum(a["status"] == "skipped" for a in attempts),
                    abandoned=sum(a["status"] == "abandoned" for a in attempts),
                    practice=sum(a["kind"] == "practice" for a in attempts),
                    feedback_delayed=session["feedback_mode"] == "strict" and session["status"] != "ended",
                    data_revision=self.s.revision())

    def check(self, topic=None):
        topics = [self.s.get("topics", topic)] if topic else self.s.rows("SELECT * FROM topics")
        issues = []
        for row in self.s.rows("PRAGMA foreign_key_check"):
            issues.append({"kind": "foreign_key", "detail": row})
        for row in self.s.rows("PRAGMA integrity_check"):
            if row.get("integrity_check") != "ok":
                issues.append({"kind": "integrity", "detail": row})
        for t in topics:
            computed, _ = self.computed(t["id"])
            for cid, expected in computed.items():
                actual = self.s.one("SELECT * FROM concept_stats WHERE concept_id=?", (cid,))
                if actual:
                    actual.pop("computed_revision")
                    actual["current_gaps"] = json.loads(actual.pop("current_gaps_json"))
                if actual != expected:
                    issues.append({"kind": "stats", "concept_id": cid, "expected": expected, "actual": actual})
            for a in self.attempts(t["id"]):
                e = self.latest(a["id"])
                expected_state = {"confirmed": "evaluated", "pending_verification": "pending_verification", "practice": "practice_completed"}.get(e["status"]) if e else None
                if expected_state and a["status"] != expected_state:
                    issues.append({"kind": "state", "attempt_id": a["id"]})
        return {"consistent": not issues, "issues": issues, "data_revision": self.s.revision()}
