import contextlib
import io
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.mock_interview.cli import main
from tools.mock_interview.common import AppError, digest, uid
from tools.mock_interview.importer import import_markdown, preview
from tools.mock_interview.rules import DEFAULT_RULE, replay
from tools.mock_interview.service import Service
from tools.mock_interview.store import Store
from tools.mock_interview.transfer import backup_create, export_markdown


class InterviewTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Store(self.root, initialize=True)
        self.addCleanup(self.store.close)
        self.service = Service(self.store)
        self.write("topic create", id="java", name="Java 并发", version_scope="Java 21")
        for cid in ("A", "B", "C", "D", "E", "F"):
            self.write("concept create", id=cid, topic_id="java", title="考点 " + cid,
                       representative_question="解释机制", scope="测试边界")
        self.sid = self.write("session start", topic_id="java", thread_id="chat-1")["id"]

    def write(self, operation, **data):
        data.setdefault("request_id", uid("request"))
        return self.service.write(operation, data)

    def version(self, table, key):
        return self.store.get(table, key)["revision"]

    def create(self, cid="A", kind=None):
        count = self.service.computed("java")[0][cid]["attempt_count"]
        return self.write("attempt create", session_id=self.sid, concept_id=cid, question="请解释关键机制。",
                          kind=kind or ("retest" if count else "diagnostic"), expected_revision=self.version("sessions", self.sid))

    def append(self, aid, event_type="answer", content="独立回答", **extra):
        return self.write("attempt append", attempt_id=aid, expected_revision=self.version("attempts", aid),
                          event_type=event_type, content=content, **extra)

    def evaluate(self, aid, grade=3, **changes):
        events = self.service.attempt_show(aid)["events"]
        answer_ids = [e["id"] for e in events if e["event_type"] in ("answer", "cannot_answer", "clarification_answer")]
        evaluation = dict(status="confirmed", grade=grade, answer_event_ids=answer_ids,
                          substantive_hint=False, basis="根据用户独立回答评估", gaps=[] if grade is None or grade >= 2 else ["关键机制缺口"],
                          corrected_points=["修正要点"], sources=[])
        evaluation.update(changes)
        return self.write("attempt evaluate", attempt_id=aid, expected_revision=self.version("attempts", aid), evaluation=evaluation)

    def answer(self, cid="A", grade=3, kind=None):
        a = self.create(cid, kind)
        self.append(a["id"])
        self.evaluate(a["id"], grade)
        return a["id"]

    def new_session(self):
        self.write("session end", session_id=self.sid, expected_revision=self.version("sessions", self.sid))
        self.sid = self.write("session start", topic_id="java", thread_id="chat-2")["id"]

    def stats(self, cid="A"):
        return self.service.computed("java")[0][cid]

    def assert_error(self, code, callback):
        with self.assertRaises(AppError) as ctx:
            callback()
        self.assertEqual(code, ctx.exception.code)

    def test_R01_R04_failure_reset_and_cap(self):
        self.answer(grade=0)
        self.assertEqual((3, 1, 1), (self.stats()["weight"], self.stats()["attempt_count"], self.stats()["failure_count"]))
        self.new_session()
        self.answer(grade=1)
        self.assertEqual(5, self.stats()["weight"])
        self.assertEqual(2, self.stats()["consecutive_failures"])
        self.new_session()
        self.answer(grade=2)
        self.assertEqual((5, 0, 2), tuple(self.stats()[x] for x in ("weight", "consecutive_failures", "failure_count")))
        for _ in range(4):
            self.new_session()
            self.answer(grade=0)
        self.assertEqual(10, self.stats()["weight"])

    def test_R05_R11_two_retests_required(self):
        self.answer(grade=0)
        self.new_session()
        self.answer()
        self.assertEqual((3, 1), (self.stats()["weight"], self.stats()["qualified_retests"]))
        self.answer("B")
        self.answer("C")
        self.answer()
        self.assertEqual((2, 0), (self.stats()["weight"], self.stats()["qualified_retests"]))

    def test_R07_grade2_interrupts_qualification(self):
        self.answer(grade=0)
        for grade in (3, 2, 3):
            self.new_session()
            self.answer(grade=grade)
        self.assertEqual((3, 1), (self.stats()["weight"], self.stats()["qualified_retests"]))

    def test_R11_R12_diagnostic_does_not_reduce_minimum(self):
        self.answer()
        self.assertEqual(0, self.stats()["qualified_retests"])
        self.new_session()
        self.answer()
        self.assertEqual(1, self.stats()["qualified_retests"])
        self.new_session()
        self.answer()
        self.assertEqual((1, 0), (self.stats()["weight"], self.stats()["qualified_retests"]))

    def test_R06_insufficient_gap_preserves_anchor_in_replay(self):
        attempts = []
        for order, cid, kind, grade in [(1, "A", "diagnostic", 0), (2, "A", "retest", 3),
                                         (3, "B", "diagnostic", 3), (4, "A", "retest", 3)]:
            attempts.append(dict(id=str(order), concept_id=cid, kind=kind, grade=grade, rule=DEFAULT_RULE,
                                 answered_order=order, answered_at=None, session_id="same", gaps=[],
                                 substantive_hint=False, evaluation_status="confirmed"))
        stats, _ = replay([{"id": "A"}, {"id": "B"}], attempts)
        self.assertEqual((3, 1, "2"), tuple(stats["A"][k] for k in ("weight", "qualified_retests", "qualification_anchor_id")))

    def test_R06_R08_practice_and_hint(self):
        a = self.create()
        self.append(a["id"], "hint", "给出主要结论")
        self.append(a["id"])
        self.assert_error("INVALID_INPUT", lambda: self.evaluate(a["id"]))
        self.evaluate(a["id"], None, status="practice", substantive_hint=True)
        self.assertEqual(0, self.stats()["attempt_count"])
        self.assertEqual(1, self.service.report_session(self.sid)["practice"])

    def test_R08_hinted_grade3_rejected(self):
        a = self.create()
        self.append(a["id"])
        self.append(a["id"], "hint")
        self.assert_error("INVALID_INPUT", lambda: self.evaluate(a["id"], 3, substantive_hint=True))
        self.evaluate(a["id"], 1, substantive_hint=True)
        self.assertEqual(2, self.stats()["weight"])

    def test_R09_skip_abandon_and_correction(self):
        a = self.create()
        self.write("attempt skip", attempt_id=a["id"], expected_revision=1, reason="稍后再练")
        b = self.create("B")
        self.new_session()
        self.assertEqual("abandoned", self.store.get("attempts", b["id"])["status"])
        aid = self.answer(grade=0)
        before = self.stats()
        self.append(aid, "correction_skipped", "跳过复述")
        self.assertEqual(before, self.stats())

    def test_R10_cannot_answer(self):
        a = self.create()
        self.append(a["id"], "cannot_answer", "不会")
        self.assert_error("INVALID_INPUT", lambda: self.evaluate(a["id"], 3))
        self.evaluate(a["id"], 0)
        self.assertEqual(3, self.stats()["weight"])

    def test_S01_S02_pause_resume(self):
        a = self.create()
        self.write("session pause", session_id=self.sid, expected_revision=self.version("sessions", self.sid))
        self.assert_error("INVALID_STATE", lambda: self.write("session start", topic_id="java", thread_id="new"))
        self.write("session resume", session_id=self.sid, expected_revision=self.version("sessions", self.sid), thread_id="new")
        self.assertEqual(a["id"], self.service.next(self.sid)["attempt"]["id"])

    def test_S03_explanation_restarts_gap(self):
        aid = self.answer(grade=0)
        self.answer("B")
        self.append(aid, "explanation", "讲解后重新等待间隔")
        self.answer("C")
        self.assert_error("INVALID_STATE", lambda: self.create())
        self.answer("D")
        self.assertEqual("retest", self.create()["kind"])

    def test_old_attempt_feedback_counts_in_current_session(self):
        aid = self.answer(grade=0)
        self.new_session()
        self.append(aid, "explanation", "新会话刚讲解了旧题")
        self.assert_error("INVALID_STATE", lambda: self.create())
        self.answer("B")
        self.answer("C")
        self.create()

    def test_S04_configured_interval_and_cross_session(self):
        self.write("topic configure", topic_id="java", expected_revision=self.version("topics", "java"),
                   min_other_questions=5, reason="希望拉长间隔")
        self.answer(grade=0)
        for cid in ("B", "C", "D", "E"):
            self.answer(cid)
        self.assert_error("INVALID_STATE", lambda: self.create())
        self.answer("F")
        self.write("topic configure", topic_id="java", expected_revision=self.version("topics", "java"),
                   cross_session_only=True, reason="下轮再练")
        self.assert_error("INVALID_STATE", lambda: self.create())
        self.new_session()
        self.create()

    def test_S05_defer_scoped_to_session(self):
        self.answer(grade=0)
        self.new_session()
        self.write("session defer", session_id=self.sid, expected_revision=self.version("sessions", self.sid),
                   concept_id="A", deferred=True, reason="本轮不练")
        self.assertEqual("本轮暂缓", self.service.next(self.sid)["excluded"][0]["eligibility"]["reason"])
        self.new_session()
        self.assertEqual("retest", self.service.next(self.sid)["mode"])

    def test_S06_S07_readonly_next_and_new_fallback(self):
        self.answer(grade=0)
        before = self.store.revision()
        first = self.service.next(self.sid)
        self.assertEqual("new_question_needed", first["mode"])
        self.assertEqual(first, self.service.next(self.sid))
        self.assertEqual(before, self.store.revision())

    def test_S08_cadence(self):
        self.answer("A", 0)
        self.answer("B", 0)
        self.new_session()
        self.assertEqual("retest", self.service.next(self.sid)["mode"])
        self.answer("A", 3)
        self.assertEqual("retest", self.service.next(self.sid)["mode"])
        self.answer("B", 3)
        self.assertEqual("new_question_needed", self.service.next(self.sid)["mode"])

    def test_S09_C05_pending_resolved_after_end(self):
        a = self.create()
        self.append(a["id"])
        self.evaluate(a["id"], None, status="pending_verification", disputed_points=["版本行为待核实"])
        self.assertEqual(0, self.stats()["attempt_count"])
        sid = self.sid
        self.new_session()
        self.assertEqual([a["id"]], self.service.report_session(sid)["pending"])
        e = self.service.latest(a["id"])
        evaluation = dict(status="confirmed", grade=2, answer_event_ids=json.loads(e["answer_event_ids_json"]),
                          substantive_hint=False, basis="核实后成立")
        self.write("attempt revise", attempt_id=a["id"], expected_revision=self.version("attempts", a["id"]),
                   evaluation_version=1, reason="已核实", evaluation=evaluation)
        self.assertEqual(1, self.service.report_session(sid)["graded_count"])

    def test_C01_C02_idempotency(self):
        a = self.create()
        answer = self.append(a["id"])
        data = dict(request_id="same", attempt_id=a["id"], expected_revision=2,
                    evaluation=dict(status="confirmed", grade=0, answer_event_ids=[answer["event_id"]], basis="不会", substantive_hint=False))
        first = self.service.write("attempt evaluate", data)
        second = self.service.write("attempt evaluate", data)
        self.assertTrue(second["replayed"])
        self.assertEqual(first["data_revision"], second["data_revision"])
        self.assertEqual(1, self.stats()["attempt_count"])
        data["evaluation"]["grade"] = 1
        self.assert_error("IDEMPOTENCY_CONFLICT", lambda: self.service.write("attempt evaluate", data))

    def test_C03_second_connection_stale_revision(self):
        second = Store(self.root)
        self.addCleanup(second.close)
        version = self.version("sessions", self.sid)
        self.write("session pause", session_id=self.sid, expected_revision=version)
        self.assert_error("REVISION_CONFLICT", lambda: Service(second).write("session resume",
                          dict(request_id="second", session_id=self.sid, expected_revision=version)))

    def test_C04_transaction_rollback(self):
        a = self.create()
        self.append(a["id"])
        before = self.store.revision()
        with patch.object(self.service, "rebuild", side_effect=RuntimeError("模拟中断")):
            with self.assertRaises(RuntimeError):
                self.evaluate(a["id"], 0)
        self.assertIsNone(self.service.latest(a["id"]))
        self.assertEqual("awaiting_evaluation", self.store.get("attempts", a["id"])["status"])
        self.assertEqual(before, self.store.revision())

    def test_C06_revise_replays_later_failures(self):
        aid = self.answer(grade=0)
        self.new_session()
        self.answer(grade=1)
        self.assertEqual(5, self.stats()["weight"])
        e = self.service.latest(aid)
        self.write("attempt revise", attempt_id=aid, expected_revision=self.version("attempts", aid), evaluation_version=1,
                   reason="原先误判", evaluation=dict(status="confirmed", grade=3, basis="独立回答正确", substantive_hint=False,
                   answer_event_ids=json.loads(e["answer_event_ids_json"])))
        self.assertEqual((2, 1, 1), tuple(self.stats()[k] for k in ("weight", "failure_count", "consecutive_failures")))
        self.assertEqual(2, len(self.service.attempt_show(aid)["evaluations"]))

    def test_C07_rule_snapshots(self):
        aid = self.create()["id"]
        self.write("rule create", topic_id="java", expected_revision=self.version("topics", "java"),
                   parameters=dict(grade0_increment=3), reason="调整未来规则")
        self.append(aid)
        self.evaluate(aid, 0)
        self.assertEqual(3, self.stats()["weight"])
        self.new_session()
        self.answer(grade=0)
        self.assertEqual(7, self.stats()["weight"])
        self.assertTrue(self.service.check()["consistent"])

    def test_C08_cache_rebuild(self):
        self.answer(grade=0)
        self.store.db.execute("UPDATE concept_stats SET weight=9 WHERE concept_id='A'")
        self.assertFalse(self.service.check()["consistent"])
        self.write("stats rebuild", topic_id="java", expected_data_revision=self.store.revision())
        self.assertTrue(self.service.check()["consistent"])

    def test_C09_retry_after_connection_closes(self):
        d = dict(request_id="lost-response", session_id=self.sid, expected_revision=self.version("sessions", self.sid))
        self.service.write("session pause", d)
        connection = Store(self.root)
        self.addCleanup(connection.close)
        result = Service(connection).write("session pause", d)
        self.assertTrue(result["replayed"])

    def test_D01_report_categories(self):
        self.answer(grade=0)
        a = self.create("B")
        self.write("attempt skip", attempt_id=a["id"], expected_revision=1, reason="跳过")
        a = self.create("A", "practice")
        self.append(a["id"])
        self.evaluate(a["id"], None, status="practice")
        r = self.service.report_session(self.sid)
        self.assertEqual((1, 1, 1), (r["graded_count"], r["skipped"], r["practice"]))

    def test_D02_export_conflict(self):
        self.answer()
        result = export_markdown(self.service, dict(request_id="export1", topic_id="java"))
        path = Path(result["path"])
        self.assertIn("考点索引", path.read_text())
        path.write_text(path.read_text() + "\n手写内容", encoding="utf-8")
        self.assert_error("EXPORT_CONFLICT", lambda: export_markdown(self.service, dict(request_id="export2", topic_id="java")))
        self.assertIn("手写内容", path.read_text())

    def test_D03_export_failure_keeps_evaluation(self):
        self.answer(grade=0)
        with patch("tools.mock_interview.transfer.os.replace", side_effect=OSError("模拟失败")):
            with self.assertRaises(OSError):
                export_markdown(self.service, dict(request_id="export", topic_id="java"))
        self.assertEqual(1, self.stats()["attempt_count"])
        export_markdown(self.service, dict(request_id="export", topic_id="java"))
        self.assertEqual(1, self.stats()["attempt_count"])

    def test_export_recovery_after_file_replaced(self):
        self.answer()
        original = self.store.insert
        def fail_response(table, data):
            if table == "write_requests":
                raise OSError("返回前中断")
            return original(table, data)
        payload = dict(request_id="recover-export", topic_id="java")
        with patch.object(self.store, "insert", side_effect=fail_response):
            with self.assertRaises(OSError):
                export_markdown(self.service, payload)
        result = export_markdown(self.service, payload)
        self.assertTrue(result["recovered"])
        self.assertTrue(Path(result["path"]).exists())

    def test_D08_path_injection(self):
        self.assert_error("INVALID_INPUT", lambda: self.write("topic create", id="../../escape", name="名称", version_scope="范围"))
        self.write("topic create", id="safe", name="../../$(touch injected)", version_scope="范围")
        self.assertFalse((self.root / "injected").exists())

    def test_D09_backup(self):
        self.answer(grade=0)
        result = backup_create(self.service, dict(request_id="backup"))
        with sqlite3.connect(result["path"]) as copy:
            self.assertEqual("ok", copy.execute("PRAGMA integrity_check").fetchone()[0])
            self.assertEqual(1, copy.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0])

    def test_neutral_clarification_and_cross_attempt_evidence(self):
        a = self.create()
        self.append(a["id"])
        self.append(a["id"], "clarification_question", "请澄清你的表述")
        self.append(a["id"], "clarification_answer", "这是我的意思")
        self.assert_error("INVALID_INPUT", lambda: self.append(a["id"], "clarification_question"))
        self.evaluate(a["id"])
        b = self.create("B")
        self.append(b["id"])
        foreign = self.service.attempt_show(a["id"])["events"][0]["id"]
        self.assert_error("INVALID_INPUT", lambda: self.evaluate(b["id"], answer_event_ids=[foreign]))


    def test_clarification_cannot_answer_keeps_original_order_and_counts_once(self):
        aid = self.create()["id"]
        first = self.append(aid)
        self.append(aid, "clarification_question", "请澄清机制")
        cannot = self.append(aid, "cannot_answer", "这个机制确实不会")
        self.assertEqual(first["answered_order"], cannot["answered_order"])
        self.assertEqual(first["answered_at"], cannot["answered_at"])
        self.assert_error("INVALID_INPUT", lambda: self.evaluate(aid, 3, answer_event_ids=[first["event_id"]]))
        self.evaluate(aid, 0)
        self.assertEqual((1, 1, 3), tuple(self.stats()[k] for k in ("attempt_count", "failure_count", "weight")))
        self.assertEqual(2, len([e for e in self.service.attempt_show(aid)["events"]
                               if e["event_type"] in ("answer", "cannot_answer")]))

    def test_hinted_supplement_saved_without_independent_credit(self):
        aid = self.create()["id"]
        answer = self.append(aid)
        self.append(aid, "hint", "实质提示")
        supplement = self.append(aid, "supplement", "提示后补充的答案")
        self.assertEqual(answer["answered_order"], supplement["answered_order"])
        self.assertEqual(0, self.stats()["attempt_count"])
        self.assert_error("INVALID_INPUT", lambda: self.evaluate(aid, 1, substantive_hint=True,
                          answer_event_ids=[supplement["event_id"]]))
        self.evaluate(aid, 1, substantive_hint=True)
        self.assertEqual((1, 2), (self.stats()["attempt_count"], self.stats()["weight"]))
        self.assertIn("提示后补充的答案", self.service.attempt_show(aid)["events"][-1]["content"])

    def reclassify(self, aid, event_id, event_type, **fields):
        return self.write("attempt reclassify", attempt_id=aid, event_id=event_id, event_type=event_type,
                          expected_revision=self.version("attempts", aid), reason="核对原始交互后纠正分类", **fields)

    def test_reclassify_hint_and_revision_are_atomic_and_auditable(self):
        aid = self.create()["id"]
        answer = self.append(aid)
        hint = self.append(aid, "hint", "实际只是中性澄清")
        self.evaluate(aid, 1, substantive_hint=True)
        original = self.service.attempt_show(aid)
        evaluation = dict(status="confirmed", grade=3, basis="原回答正确", substantive_hint=False,
                          answer_event_ids=[answer["event_id"]])
        self.assert_error("REVISION_CONFLICT", lambda: self.reclassify(aid, hint["event_id"],
                          "clarification_question", evaluation_version=99, evaluation=evaluation))
        self.assertEqual(original, self.service.attempt_show(aid))
        result = self.reclassify(aid, hint["event_id"], "clarification_question",
                                 evaluation_version=1, evaluation=evaluation)
        self.assertEqual(1, result["weight_after"])
        detail = self.service.attempt_show(aid)
        self.assertEqual("hint", detail["events"][1]["event_type"])
        self.assertEqual("clarification_question", detail["effective_events"][1]["event_type"])
        self.assertEqual("event_reclassification", detail["events"][-1]["event_type"])
        self.assertEqual(2, len(detail["evaluations"]))
        self.assertTrue(self.service.check()["consistent"])

    def test_reclassify_neutral_to_hint_rejects_grade3(self):
        aid = self.create()["id"]
        answer = self.append(aid)
        question = self.append(aid, "clarification_question", "实际已给出答案")
        self.evaluate(aid, 3)
        evaluation = dict(status="confirmed", grade=3, basis="修改分类", substantive_hint=True,
                          answer_event_ids=[answer["event_id"]])
        self.assert_error("INVALID_INPUT", lambda: self.reclassify(aid, question["event_id"], "hint",
                          evaluation_version=1, evaluation=evaluation))
        evaluation["grade"] = 1
        self.reclassify(aid, question["event_id"], "hint", evaluation_version=1, evaluation=evaluation)
        self.assertEqual(2, self.stats()["weight"])

    def test_reclassify_before_answer_restores_original_kind(self):
        aid = self.create()["id"]
        hint = self.append(aid, "hint", "实际是补充题目条件")
        self.assertEqual("practice", hint["kind"])
        self.reclassify(aid, hint["event_id"], "clarification_question")
        self.assertEqual("diagnostic", self.service.attempt_show(aid)["kind"])
        self.append(aid)
        self.evaluate(aid, 3)
        self.assertEqual(1, self.stats()["attempt_count"])

    def test_reclassify_preserves_explicit_practice(self):
        aid = self.create(kind="practice")["id"]
        hint = self.append(aid, "hint")
        self.reclassify(aid, hint["event_id"], "clarification_question")
        self.assertEqual("practice", self.service.attempt_show(aid)["kind"])

    def test_reclassify_preanswer_hint_after_evaluation_and_retry(self):
        aid = self.create()["id"]
        hint = self.append(aid, "hint", "实际只是澄清题意")
        answer = self.append(aid)
        self.evaluate(aid, None, status="practice", substantive_hint=True)
        payload = dict(request_id="reclassify-retry", attempt_id=aid, event_id=hint["event_id"],
                       event_type="clarification_question", expected_revision=self.version("attempts", aid),
                       evaluation_version=1, reason="核对题意后纠正提示分类",
                       evaluation=dict(status="confirmed", grade=3, substantive_hint=False,
                                       answer_event_ids=[answer["event_id"]], basis="独立回答正确"))
        result = self.service.write("attempt reclassify", payload)
        repeated = self.service.write("attempt reclassify", payload)
        self.assertTrue(repeated["replayed"])
        self.assertEqual(result["data_revision"], repeated["data_revision"])
        self.assertEqual(1, self.stats()["attempt_count"])
        output = export_markdown(self.service, dict(request_id="reclassified-export", topic_id="java"))
        report = Path(output["path"]).read_text()
        self.assertIn("当前有效分类：clarification_question", report)
        self.assertIn("hint → clarification_question", report)

    def test_legacy_preanswer_hint_requires_explicit_provenance(self):
        aid = self.create()["id"]
        hint = self.append(aid, "hint")
        # 构造旧版本未保存原题型的事件，验证不会猜测历史。
        self.store.db.execute("UPDATE attempt_events SET metadata_json='{}' WHERE id=?", (hint["event_id"],))
        self.assert_error("INVALID_INPUT", lambda: self.reclassify(aid, hint["event_id"], "clarification_question"))
        self.reclassify(aid, hint["event_id"], "clarification_question", restore_kind="diagnostic")
        self.assertEqual("diagnostic", self.service.attempt_show(aid)["kind"])

    def test_practice_pending_verification_resolves_without_scores(self):
        aid = self.create(kind="practice")["id"]
        answer = self.append(aid)
        self.evaluate(aid, None, status="pending_verification", disputed_points=["版本差异"])
        self.assertEqual([aid], self.service.report_session(self.sid)["pending"])
        self.new_session()
        evaluation = dict(status="practice", grade=None, basis="已核实，仅学习反馈",
                          substantive_hint=False, answer_event_ids=[answer["event_id"]])
        self.write("attempt revise", attempt_id=aid, expected_revision=self.version("attempts", aid),
                   evaluation_version=1, reason="已核实", evaluation=evaluation)
        self.assertEqual("practice_completed", self.service.attempt_show(aid)["status"])
        self.assertEqual((0, 0, 1), tuple(self.stats()[k] for k in ("attempt_count", "failure_count", "weight")))

    def test_partial_rule_changes_preserve_existing_values_and_snapshots(self):
        aid = self.create()["id"]
        original_rule = self.store.get("rule_versions", self.store.get("attempts", aid)["rule_version_id"])
        self.write("rule create", topic_id="java", expected_revision=self.version("topics", "java"),
                   parameters={"grade0_increment": 3}, reason="调整等级0")
        first = self.service.rule("java")
        self.write("rule create", topic_id="java", expected_revision=self.version("topics", "java"),
                   parameters={"grade1_increment": 2}, reason="只调整等级1")
        actual = json.loads(self.service.rule("java")["parameters_json"])
        self.assertEqual((3, 2), (actual["grade0_increment"], actual["grade1_increment"]))
        self.assertEqual(first, self.store.get("rule_versions", first["id"]))
        self.assertEqual(original_rule, self.store.get("rule_versions", original_rule["id"]))
        self.append(aid)
        self.evaluate(aid, 0)
        self.assertEqual(3, self.stats()["weight"])


LEGACY = """# 测试记录

| 稳定 ID | 考点及代表问题 | 难度 | 权重 | 累计独立作答次数 | 累计失误 | 连续失误 | 连续合格复测次数 | 最近等级 | 最后独立作答时间 | 当前缺口 |
| TEST-A | 机制问题 | 中等 | 3 | 1 | 1 | 1 | 0 | 0 | 2026-11-10 | 不会 |

## 尝试历史

### TEST-A

#### 尝试 1

- 时间：2026-11-10（未记录时分）。
- 会话：旧会话。
- 实际问法：请解释机制。
- 用户回答摘要：不会。
- 是否提示：无。
- 等级：0（不会）。
- 依据：明确表示不会。
- 具体错误或遗漏：机制不清楚。
- 修正版要点：关键机制。
"""


class ImportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.path = self.root / "旧记录.md"
        self.path.write_text(LEGACY, encoding="utf-8")
        self.data = dict(source_path=str(self.path), topic_id="legacy", rules_confirmed=True)

    def initialized(self):
        s = Store(self.root, initialize=True)
        self.addCleanup(s.close)
        service = Service(s)
        service.write("topic create", dict(request_id="topic", id="legacy", name="旧主题", version_scope="旧范围"))
        return service

    def apply_data(self):
        report = preview(self.data)
        return dict(self.data, mode="apply", request_id="import", source_hash=report["source_hash"], report_hash=report["report_hash"])

    def test_D04_D07_preview_is_readonly_and_preserves_precision(self):
        before = self.path.read_bytes()
        report = preview(self.data)
        self.assertEqual([], report["blockers"])
        self.assertEqual("date", report["records"][0]["time_precision"])
        self.assertTrue(report["records"][0]["is_summary"])
        self.assertEqual(before, self.path.read_bytes())
        self.assertFalse((self.root / "面试训练记录").exists())

    def test_D05_source_change_rejects(self):
        service = self.initialized()
        data = self.apply_data()
        self.path.write_text(LEGACY + "\n来源已经变化", encoding="utf-8")
        with self.assertRaises(AppError) as ctx:
            import_markdown(service, data)
        self.assertEqual("IMPORT_REVIEW_REQUIRED", ctx.exception.code)

    def test_D06_D07_import_once(self):
        service = self.initialized()
        data = self.apply_data()
        first = import_markdown(service, data)
        self.assertEqual(1, first["imported_attempts"])
        self.assertTrue(import_markdown(service, data)["replayed"])
        data["request_id"] = "new-request"
        self.assertTrue(import_markdown(service, data)["already_imported"])
        attempt = service.attempts("legacy")[0]
        self.assertEqual("2026-11-10", attempt["answered_at"])
        self.assertEqual("date", attempt["time_precision"])
        self.assertTrue(service.check()["consistent"])
        self.assertEqual(LEGACY, self.path.read_text())

    def test_manual_weights_block_import(self):
        self.path.write_text(LEGACY + "\n单题权重调整：用户主动加权。", encoding="utf-8")
        report = preview(self.data)
        self.assertIn("MANUAL_WEIGHT_ADJUSTMENT", [x["code"] for x in report["blockers"]])

    def test_index_mismatch_rolls_back_whole_import(self):
        service = self.initialized()
        self.path.write_text(LEGACY.replace("| 3 | 1 |", "| 7 | 1 |"), encoding="utf-8")
        with self.assertRaises(AppError):
            import_markdown(service, self.apply_data())
        self.assertEqual([], service.concepts("legacy"))
        self.assertEqual([], service.attempts("legacy"))


class CliTest(unittest.TestCase):
    def call(self, argv, payload=None):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), patch("sys.stdin", io.StringIO(json.dumps(payload) if payload is not None else "")):
            code = main(argv)
        return code, json.loads(out.getvalue())

    def test_missing_db_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as root:
            code, result = self.call(["--workspace", root, "topic", "list"])
            self.assertEqual(3, code)
            self.assertEqual("NOT_INITIALIZED", result["error"]["code"])
            self.assertFalse((Path(root) / "面试训练记录").exists())

    def test_initialization_idempotent_and_json_output(self):
        with tempfile.TemporaryDirectory() as root:
            argv = ["--workspace", root, "init", "--input", "-"]
            code, first = self.call(argv, {"request_id": "init"})
            _, second = self.call(argv, {"request_id": "init"})
            self.assertEqual(0, code)
            self.assertTrue(second["data"]["replayed"])
            self.assertEqual(first["workspace"], str(Path(root).resolve()))

    def test_invalid_cli_returns_structured_error(self):
        code, result = self.call(["topic", "missing"])
        self.assertEqual(2, code)
        self.assertFalse(result["ok"])

    def test_foreign_database_not_modified_by_init(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "面试训练记录/.state/training.sqlite3"
            db.parent.mkdir(parents=True)
            with sqlite3.connect(db) as connection:
                connection.execute("CREATE TABLE foreign_data (id TEXT)")
            before = db.read_bytes()
            code, result = self.call(["--workspace", root, "init", "--input", "-"], {"request_id": "init"})
            self.assertEqual(4, code)
            self.assertEqual(before, db.read_bytes())

    def test_real_process_end_to_end(self):
        entry = Path(__file__).resolve().parents[2] / "mock-interview.py"
        with tempfile.TemporaryDirectory() as root:
            def cli(command, payload=None):
                args = [sys.executable, str(entry), "--workspace", root] + command.split()
                if payload is not None:
                    args += ["--input", "-"]
                    payload = dict(payload, request_id=uid("req"))
                completed = subprocess.run(args, input=json.dumps(payload) if payload else None,
                                           text=True, capture_output=True, cwd=root, timeout=10)
                self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
                return json.loads(completed.stdout)["data"]
            cli("init", {})
            cli("topic create", dict(id="flow", name="流程验收", version_scope="测试范围"))
            cli("concept create", dict(id="FLOW-A", topic_id="flow", title="流程考点", scope="测试", representative_question="问题"))
            session = cli("session start", dict(topic_id="flow", thread_id="chat-1"))
            attempt = cli("attempt create", dict(session_id=session["id"], expected_revision=session["revision"],
                                               concept_id="FLOW-A", question="实际问题", kind="diagnostic"))
            answer = cli("attempt append", dict(attempt_id=attempt["id"], expected_revision=attempt["revision"],
                                               event_type="answer", content="独立回答"))
            question = cli("attempt append", dict(attempt_id=attempt["id"], expected_revision=answer["revision"],
                                                 event_type="clarification_question", content="中性澄清"))
            clarified = cli("attempt append", dict(attempt_id=attempt["id"], expected_revision=question["revision"],
                                                  event_type="clarification_answer", content="澄清回答"))
            result = cli("attempt evaluate", dict(attempt_id=attempt["id"], expected_revision=clarified["revision"],
                         evaluation=dict(status="confirmed", grade=1, basis="存在缺口", answer_event_ids=[answer["event_id"], clarified["event_id"]], substantive_hint=False)))
            self.assertEqual(2, result["weight_after"])
            feedback = cli("attempt append", dict(attempt_id=attempt["id"], expected_revision=result["revision"],
                                                 event_type="explanation", content="讲解"))
            paused = cli("session pause", dict(session_id=session["id"], expected_revision=feedback["session_revision"]))
            resumed = cli("session resume", dict(session_id=session["id"], expected_revision=paused["revision"], thread_id="chat-2"))
            revised = cli("attempt revise", dict(attempt_id=attempt["id"], expected_revision=feedback["revision"],
                         evaluation_version=1, reason="核对后纠正误判", evaluation=dict(status="confirmed", grade=3,
                         basis="原答案已覆盖关键机制", answer_event_ids=[answer["event_id"]], substantive_hint=False)))
            self.assertEqual(1, revised["weight_after"])
            session_now = cli("session show --session " + session["id"])
            cli("session end", dict(session_id=session["id"], expected_revision=session_now["revision"]))
            exported = cli("export markdown", dict(topic_id="flow"))
            self.assertIn("评估版本 2", Path(exported["path"]).read_text())
            self.assertTrue(cli("check")["consistent"])


if __name__ == "__main__":
    unittest.main()
