CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT OR IGNORE INTO app_meta VALUES ('schema_version', '1');
INSERT OR IGNORE INTO app_meta VALUES ('data_revision', '0');

CREATE TABLE IF NOT EXISTS topics (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, version_scope TEXT NOT NULL,
 timezone TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rule_versions (
 id TEXT PRIMARY KEY, topic_id TEXT NOT NULL REFERENCES topics(id), version INTEGER NOT NULL,
 parameters_json TEXT NOT NULL, effective_at TEXT NOT NULL, reason TEXT NOT NULL,
 created_at TEXT NOT NULL, UNIQUE(topic_id, version)
);
CREATE INDEX IF NOT EXISTS rule_effective ON rule_versions(topic_id, effective_at);
CREATE TABLE IF NOT EXISTS preference_versions (
 id TEXT PRIMARY KEY, topic_id TEXT NOT NULL REFERENCES topics(id), version INTEGER NOT NULL,
 min_other_questions INTEGER NOT NULL CHECK(min_other_questions >= 2),
 cross_session_only INTEGER NOT NULL CHECK(cross_session_only IN (0,1)),
 reason TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(topic_id, version)
);
CREATE TABLE IF NOT EXISTS concepts (
 id TEXT PRIMARY KEY, topic_id TEXT NOT NULL REFERENCES topics(id), title TEXT NOT NULL,
 representative_question TEXT NOT NULL, scope TEXT NOT NULL,
 difficulty TEXT NOT NULL CHECK(difficulty IN ('基础','中等','进阶')), created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS concept_topic ON concepts(topic_id);
CREATE TABLE IF NOT EXISTS sessions (
 id TEXT PRIMARY KEY, topic_id TEXT NOT NULL REFERENCES topics(id),
 status TEXT NOT NULL CHECK(status IN ('active','paused','ended')),
 feedback_mode TEXT NOT NULL CHECK(feedback_mode IN ('training','strict')),
 started_at TEXT NOT NULL, ended_at TEXT, revision INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_session ON sessions(topic_id) WHERE status != 'ended';
CREATE TABLE IF NOT EXISTS session_events (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
 event_type TEXT NOT NULL, payload_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS session_event_order ON session_events(session_id, created_at);
CREATE TABLE IF NOT EXISTS attempts (
 id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
 concept_id TEXT NOT NULL REFERENCES concepts(id), rule_version_id TEXT NOT NULL REFERENCES rule_versions(id),
 preference_version_id TEXT NOT NULL REFERENCES preference_versions(id), question TEXT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('diagnostic','retest','practice')),
 status TEXT NOT NULL CHECK(status IN ('awaiting_answer','awaiting_evaluation','pending_verification',
 'evaluated','skipped','abandoned','practice_completed')),
 sequence INTEGER NOT NULL, answered_order INTEGER, answered_at TEXT,
 time_precision TEXT NOT NULL DEFAULT 'exact' CHECK(time_precision IN ('exact','date','unknown')),
 created_at TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, UNIQUE(session_id, sequence)
);
CREATE UNIQUE INDEX IF NOT EXISTS one_current_attempt ON attempts(session_id)
 WHERE status IN ('awaiting_answer','awaiting_evaluation');
CREATE INDEX IF NOT EXISTS attempt_concept ON attempts(concept_id, answered_order);
CREATE TABLE IF NOT EXISTS attempt_events (
 id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES attempts(id), event_type TEXT NOT NULL,
 content TEXT NOT NULL, metadata_json TEXT NOT NULL, occurred_order INTEGER NOT NULL UNIQUE,
 occurred_at TEXT, time_precision TEXT NOT NULL CHECK(time_precision IN ('exact','date','unknown'))
);
CREATE INDEX IF NOT EXISTS attempt_event_order ON attempt_events(attempt_id, occurred_order);
CREATE TABLE IF NOT EXISTS evaluations (
 id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES attempts(id), version INTEGER NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('confirmed','pending_verification','practice')),
 grade INTEGER CHECK(grade BETWEEN 0 AND 3), substantive_hint INTEGER NOT NULL CHECK(substantive_hint IN (0,1)),
 answer_event_ids_json TEXT NOT NULL, basis TEXT NOT NULL, gaps_json TEXT NOT NULL,
 corrected_points_json TEXT NOT NULL, sources_json TEXT NOT NULL, disputed_points_json TEXT NOT NULL,
 supersedes_id TEXT REFERENCES evaluations(id), revision_reason TEXT, created_at TEXT NOT NULL,
 UNIQUE(attempt_id, version),
 CHECK((status = 'confirmed' AND grade IS NOT NULL) OR (status != 'confirmed' AND grade IS NULL))
);
CREATE TABLE IF NOT EXISTS concept_stats (
 concept_id TEXT PRIMARY KEY REFERENCES concepts(id), weight INTEGER NOT NULL CHECK(weight BETWEEN 1 AND 10),
 attempt_count INTEGER NOT NULL CHECK(attempt_count >= 0), failure_count INTEGER NOT NULL CHECK(failure_count >= 0),
 consecutive_failures INTEGER NOT NULL CHECK(consecutive_failures >= 0),
 qualified_retests INTEGER NOT NULL CHECK(qualified_retests >= 0), qualification_anchor_id TEXT,
 last_grade INTEGER, last_answered_at TEXT, last_answered_order INTEGER,
 current_gaps_json TEXT NOT NULL, computed_revision INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS write_requests (
 request_id TEXT PRIMARY KEY, operation TEXT NOT NULL, payload_hash TEXT NOT NULL,
 response_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS import_batches (
 id TEXT PRIMARY KEY, source_path TEXT NOT NULL, source_hash TEXT NOT NULL UNIQUE,
 report_hash TEXT NOT NULL, status TEXT NOT NULL, mapping_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS exports (
 topic_id TEXT PRIMARY KEY REFERENCES topics(id), path TEXT NOT NULL, content_hash TEXT NOT NULL,
 data_revision INTEGER NOT NULL, exported_at TEXT NOT NULL
);
