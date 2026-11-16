# 自适应模拟面试本地工具

本工具为 `learning-adaptive-mock-interview` 提供本地记录、权重计算、复测调度、评估修订及 Markdown 导出。模型负责评估答案；工具执行已提交的等级与规则，不联网、不调用模型、不启动数据库服务。

**日常在 Codex 聊天中使用，请先阅读 [模拟面试聊天使用指南](../../面试训练记录/模拟面试聊天使用指南.md)。** 你只需要用自然语言开始、回答和结束训练，无需手动执行 CLI。本文面向 Codex 调用工具和开发维护，介绍命令、JSON 契约及故障处理。

第一版使用 Python 标准库，要求 Python 3.9 或更新版本。当前已在 Python 3.12.9、SQLite 3.51.3 上验证；其他版本尚未验证。数据库位于指定工作区的 `面试训练记录/.state/training.sqlite3`，Markdown 位于 `面试训练记录/导出/`。首次运行只在执行 `init` 后创建数据库，不导入现有文件。

## 启动

在当前工作区中查看帮助：

```sh
python3 tools/mock-interview.py --help
python3 tools/mock-interview.py attempt evaluate --help
```

从其他目录调用时，用入口文件的绝对路径，并始终明确工作区：

```sh
python3 '/Users/lejinbo/Documents/Obsidian Vault/Learning-document/tools/mock-interview.py' \
  --workspace '/Users/lejinbo/Documents/Obsidian Vault/Learning-document' \
  topic list
```

也可在工作区根目录使用 `python3 -m tools.mock_interview`。全局 `--workspace` 放在子命令之前。没有安装全局 `mock-interview` 命令，也没有常驻进程。

## 输入输出约定

写命令使用 `--input 文件路径`，或使用 `--input -` 从标准输入读取 UTF-8 JSON。不要把回答内容拼接进 shell 命令。输入不接受重复 JSON 键、未知字段或非有限数字。

每次新的写操作使用新的 `request_id`。重试同一操作必须保留请求 ID 和完整内容，包括旧的 `expected_revision`。相同请求重试返回已有结果并标记 `replayed=true`；相同 ID 不同内容返回冲突。修订已有对象时使用最近读取到的版本号。

正常输出为一个 JSON 对象，包含 `ok`、`schema_version`、`workspace`、`data`、`warnings`。失败时包含 `error.code`、`error.message` 和 `error.details`。`--help` 和 `--version` 输出供人阅读的文本。

| 退出码 | 含义 |
|---|---|
| 0 | 命令正常完成；`check` 还须查看 `data.consistent` |
| 2 | 输入或参数不正确 |
| 3 | 数据库尚未初始化，或对象不存在 |
| 4 | 状态、对象版本、请求 ID 或数据库约束冲突 |
| 5 | 文件、数据库读写失败或数据库忙 |
| 6 | 导入需要核对，或导出目标发生冲突 |

响应中的 `data_revision` 是整个数据库写入修订号；`revision` 是目标对象版本。它们不能互换。导出响应另有 `exported_data_revision`，表示文档使用的数据快照。

## 完成一道题

下面是调用协议示例。请求内容中的题目、答案是示例，实际使用时应替换成真实问答；不要直接把示例批量写入个人训练记录。

### 初始化和主题

执行 `init --input -`，输入：

```json
{"request_id":"init-01"}
```

执行 `topic create --input -`，输入：

```json
{
  "request_id":"topic-mysql-01",
  "id":"mysql",
  "name":"MySQL",
  "version_scope":"MySQL 8.0，InnoDB",
  "timezone":"Asia/Shanghai"
}
```

主题 ID 仅允许小写字母、数字和连字符，用作稳定标识和导出文件名；中文名称用于显示。默认间隔为两道其他有效作答，初始规则随主题创建。

### 考点与会话

执行 `concept create --input -`：

```json
{
  "request_id":"concept-mysql-read-01",
  "id":"MYSQL-SNAPSHOT-CURRENT-READ",
  "topic_id":"mysql",
  "title":"快照读与当前读",
  "representative_question":"同一事务中两种读取方式为什么可能得到不同结果？",
  "scope":"只考查 RR 下读取方式与可见性，不扩展到完整锁范围分析",
  "difficulty":"中等"
}
```

考点 ID 在数据库中全局唯一，支持字母、数字、下划线和连字符。难度仅支持“基础”“中等”“进阶”。

执行 `session start --input -`：

```json
{"request_id":"session-01","topic_id":"mysql","host_id":"local","thread_id":"实际聊天标识","feedback_mode":"training"}
```

保存响应中的会话 `id` 和 `revision`。已有未结束会话时使用 `topic show --topic mysql` 找到它，再 `session resume`，不要重复创建。

### 保存题目与回答

先用 `next --session 会话ID` 获取候选，再执行 `attempt create --input -`：

```json
{
  "request_id":"question-01",
  "session_id":"替换为会话ID",
  "expected_revision":1,
  "concept_id":"MYSQL-SNAPSHOT-CURRENT-READ",
  "kind":"diagnostic",
  "question":"这里填写向用户提出的完整问题及版本条件。"
}
```

`expected_revision` 是会话当前版本。创建题目后会话版本变化。`kind` 支持：首次独立诊断 `diagnostic`、独立复测 `retest`、即时练习 `practice`。工具会校验历史和间隔；即时重练应明确使用 `practice`。

收到回答后执行 `attempt append --input -`：

```json
{
  "request_id":"answer-01",
  "attempt_id":"替换为尝试ID",
  "expected_revision":1,
  "event_type":"answer",
  "content":"用户实际回答原文。",
  "metadata":{"is_summary":false}
}
```

返回 `event_id` 供评估引用。摘要必须标记 `is_summary=true`。每题只能保存一次初始回答；中性澄清另用 `clarification_question` 和 `clarification_answer`，最多一次。

在澄清提问后才明确“不会”，仍可追加 `cannot_answer`，不会覆盖首次回答时间或新增尝试。已有首次回答后，提示引出的补充使用 `supplement` 保存；待评估、待核实及评估完成后均可追加，不参与独立评分，也不要求先评估才能保存。

### 提交评估与讲解

执行 `attempt evaluate --input -`：

```json
{
  "request_id":"evaluate-01",
  "attempt_id":"替换为尝试ID",
  "expected_revision":2,
  "evaluation":{
    "status":"confirmed",
    "grade":1,
    "answer_event_ids":["替换为回答事件ID"],
    "substantive_hint":false,
    "basis":"说明哪些内容正确，以及影响结论的实质缺口。",
    "gaps":["需要补齐的关键机制"],
    "corrected_points":["适合面试表达的修正要点"],
    "sources":[]
  }
}
```

仅在响应 `ok=true` 后向用户确认已保存，并使用返回的 `weight_before`、`weight_after` 和统计。修订历史时，这两个字段表示修订前后当前总权重；`historical_weight` 表示本次尝试在历史重算中的权重前后值。

展示讲解时用 `attempt append` 保存 `explanation`；用户复述用 `correction`。这两者重置后续复测间隔，但不增加独立作答次数。跳过复述用 `correction_skipped`。存储有误时保留同一请求重试，不能改用 Markdown 另记一次。

## 全部命令与字段

所有写命令需要 `request_id`；下表只列业务字段。带“版本”的命令还需要 `expected_revision`。正文和解释字段不能为空。

| 命令 | 字段或参数 |
|---|---|
| `init --input` | 无业务字段；重复初始化不清空数据 |
| `topic list` | 无 |
| `topic create --input` | `id`、`name`、`version_scope`，可选 `timezone` |
| `topic show --topic ID` | 返回规则、偏好、未结束会话及所有未决题目 |
| `topic configure --input` | `topic_id`、主题版本、`reason`，可选 `min_other_questions`、`cross_session_only` |
| `rule create --input` | `topic_id`、主题版本、`parameters`、`reason`，可选 `effective_at` |
| `concept list --topic ID` | 返回考点及考查边界 |
| `concept create --input` | `id`、`topic_id`、`title`、`representative_question`、`scope`，可选 `difficulty` |
| `session start --input` | `topic_id`、`thread_id`，可选 `host_id`、`feedback_mode` |
| `session show --session ID` | 返回当前版本、题目与会话事件 |
| `session resume --input` | `session_id`、会话版本，可选当前 `host_id`、`thread_id` |
| `session pause --input` | `session_id`、会话版本 |
| `session end --input` | `session_id`、会话版本；未回答题放弃，已回答题仍可评估 |
| `session defer --input` | `session_id`、会话版本、`concept_id`、`deferred` 布尔值、`reason` |
| `next --session ID` | 只读推荐；`current` 表示先处理当前题，`retest` 表示复测，`new_question_needed` 表示新题 |
| `attempt create --input` | `session_id`、会话版本、`concept_id`、`question`、`kind` |
| `attempt show --attempt ID` | 返回题目、交互、全部评估版本及当前会话版本 |
| `attempt append --input` | `attempt_id`、尝试版本、`event_type`、`content`，可选 `metadata.is_summary` |
| `attempt skip --input` | `attempt_id`、尝试版本、`reason`；只允许未回答题 |
| `attempt evaluate --input` | `attempt_id`、尝试版本、`evaluation` |
| `attempt revise --input` | `attempt_id`、尝试版本、`evaluation_version`、`reason`、新的完整 `evaluation` |
| `attempt reclassify --input` | `attempt_id`、尝试版本、`event_id`、`event_type`、`reason`；已有评估时还需 `evaluation_version` 和完整 `evaluation`；旧事件恢复题型时可需 `restore_kind` |
| `report weaknesses --topic ID` | 权重、重复失误、缺口及考点边界 |
| `report session --session ID` | 首次诊断、复测、跳过、练习、未决分别统计 |
| `export markdown --input` | `topic_id`；输出到固定专用目录 |
| `import markdown --input` | 见历史导入说明 |
| `check [--topic ID]` | 只读核对外键、完整性、状态及缓存 |
| `stats rebuild --input` | `topic_id`、`expected_data_revision`，无对象版本 |
| `backup create --input` | 无业务字段；返回一致性数据库备份路径 |

追加事件类型：`answer`、`cannot_answer`、`clarification_question`、`clarification_answer`、`hint`、`explanation`、`correction`、`correction_skipped`、`supplement`。普通跳过使用独立命令，首次或中性澄清后明确不会使用 `cannot_answer` 并评为 0；提示后的补充只记学习反馈。

评估状态为 `confirmed`、`pending_verification` 或 `practice`。只有 `confirmed` 有 0–3 等级；其他状态 `grade` 为 `null`。独立题和练习题均可进入 `pending_verification`，必须有非空 `disputed_points` 数组；后续通过 `attempt revise` 确认。练习核实后恢复为 `practice`，不得转为独立评分。练习反馈可引用 `supplement`，独立评估不可引用。

评估的 `answer_event_ids` 只能引用该尝试的回答事件。提示前尚未回答时，追加 `hint` 会将题目改为练习；提示后不能引用提示后的澄清答案作为独立评估依据。标记实质提示时不能评为 3。核实来源 `sources` 是由 `title`、HTTP/HTTPS `url`、`note` 组成的对象数组。

规则参数支持 `initial_weight`、`min_weight`、`max_weight`、`grade0_increment`、`grade1_increment`、`consecutive_bonus`、`qualified_retests_required`。主题初始使用 skill 默认值；后续 `rule create` 按当前生效规则局部更新，未提交参数保持原值。权重限制在 1–10，降权至少需要两次合格复测。新规则立即生效时省略 `effective_at`；未来时间使用带时区的 ISO 8601，不允许回溯生效。每次创建均冻结完整规则快照，已排期的未来版本不被后续局部修改自动改写，已创建题目继续使用绑定规则。

### 纠正事件误分类

`attempt reclassify` 仅支持 `hint` 与 `clarification_question` 之间的转换，必须说明理由。它追加 `event_reclassification` 审计事件，不修改原始事件；`attempt show` 的 `events` 保留原始历史，`effective_events` 返回用于校验的当前分类。导出文档同时标注原分类、有效分类和修订原因。分类修订本身不重新启动复测间隔。

已有评估时，一次请求同时携带新的完整评估，分类和评估一起保存并重算；任何校验失败都会整体回滚。比如将误标提示恢复为中性澄清：

```json
{
  "request_id":"reclassify-01",
  "attempt_id":"替换为尝试ID",
  "expected_revision":4,
  "event_id":"替换为误标事件ID",
  "event_type":"clarification_question",
  "reason":"核对原文后确认只是澄清表述，没有提供答案线索",
  "evaluation_version":1,
  "evaluation":{
    "status":"confirmed",
    "grade":3,
    "substantive_hint":false,
    "answer_event_ids":["替换为独立回答事件ID"],
    "basis":"独立回答已经覆盖本题要求的关键机制"
  }
}
```

尚无评估时省略 `evaluation` 和 `evaluation_version`，随后正常提交评估。答题前误标提示曾导致自动降为练习时，可根据保存的原题型恢复；1.0.0 旧事件缺少该信息时，需要核对后明确传入 `restore_kind`（`diagnostic`、`retest` 或 `practice`）。原本明确指定为练习的题保持练习，不能借此获取独立评分。

1.1.0 沿用数据库结构版本 1，无需迁移表或改写旧历史；升级后使用新版 CLI 读取分类修订和补充回答。

`feedback_mode=strict` 只要求模型延后展示反馈，数据库仍立即保存评估。CLI 是本地可信记录接口，不作为对模型隐藏答案的权限边界。

## 评分与调度口径

- 等级 0 加 2，等级 1 加 1；连续第 2 次及以后的失误额外加 1。等级 2、3 清零连续失误。
- 首次诊断不进入降权计数。两次合格无提示等级 3 复测，间隔两道其他有效作答或位于不同会话，权重减 1 并清零计数。
- 其他有效作答不包含跳过、练习、修正复述和待核实回答。待核实确认后按原回答顺序重新计算。
- 高权重优先；同权重按最后回答顺序从早到晚排序。时间由工具生成；旧记录日期不完整时也有明确顺序。
- 三题节奏为“复测、复测、新题”，只有正式独立评分推进位置。候选不足时安排新题，`next` 本身不改变状态。
- 同考点最近的回答、讲解、提示或修正会启动间隔检查；跨会话可再次复测。本轮暂缓只作用于当前会话。
- 即使修订导致历史成绩变化，已经提出的问题不会被删除或重写。

## 历史导入

仅支持已有 skill 的“题目索引 + 按考点组织的 `#### 尝试` 历史”格式。导出的新工具文档是阅读产物，不作为第二份数据库重新导入。

先执行 `import markdown --input 文件`，输入示例：

```json
{
  "source_path":"/绝对路径/旧记录.md",
  "topic_id":"java-concurrency",
  "mode":"preview",
  "rules_confirmed":false
}
```

预检不需要数据库，不创建文件，返回 `records`、`index`、`blockers`、`warnings`、`differences`、来源及报告指纹。核对旧规则与默认规则一致后设 `rules_confirmed=true`。有歧义的条目可通过 `resolutions` 明确事实；键是报告中的 `source_key`，可修改字段仅限 `grade`、`substantive_hint`、`session`、`time`、`order`、`order_verified`、`kind`。

```json
{
  "record-2":{
    "substantive_hint":false,
    "order":18,
    "order_verified":true,
    "kind":"retest"
  }
}
```

上面是 `resolutions` 字段值示例。原问题、回答摘要和评分依据保持来源原文。`time` 仅支持明确日期或 `null`，不填造时分秒；未确认实际顺序的回答不获得降权资格。

预检无阻断项且核对完成后，使用完全相同的来源与映射，增加 `request_id`、`mode=apply`、`source_hash`、`report_hash`，导入到已创建的空主题。应用前重新计算指纹；整个导入在一个事务内完成，重算与索引不一致时整体回滚。来源全文保留在导入批次中，原文件不改动。

**当前 Java 并发旧记录含人工加权，第一版将其列为阻断项，不能无损导入。** 可继续原 Markdown 训练，或新建独立主题开始新训练。不要删除旧文件中的人工调整来绕过检查。后续若增加人工权重事件模型，再迁移这类历史。本轮开发仅做过只读预检，识别出 43 个考点和 46 次尝试，未导入。

## 数据保护与恢复

SQLite 的记录、评估、统计和请求回执在同一事务内提交。所有外键启用；第一版无删除业务记录命令。`check` 发现派生缓存不一致时，可读取数据修订号后显式 `stats rebuild`。

导出只写专用目录。已经存在但未登记的文件，或被手工修改的导出文件，均拒绝覆盖。数据库提交和文件导出分开进行；导出失败不影响已保存的评估。导出写前日志保存在 `.state/export-主题ID.json`，支持文件替换后进程中断的重试恢复。工具管理的临时文件由操作自行清理。

同一请求重试返回原结果，不重新生成更新后的报告；需要反映后续新数据时，创建新的导出请求 ID。避免在导出瞬间用其他程序编辑同一目标文件。

`backup create` 使用 SQLite 一致性备份，保存到 `.state/backups/`，不自动清理。恢复备份前应停止 CLI 写操作，另行核对恢复目标；第一版不提供覆盖现有数据库的自动恢复命令。数据库结构版本不匹配时拒绝访问，第一版没有跨版本迁移。

## 测试与验收

在工作区根目录运行：

```sh
python3 -m unittest discover -s tools/mock_interview/tests -v
```

测试使用临时工作区，覆盖设计中的评分、状态、调度、重复请求、修订、备份、导出及导入验收条件。额外覆盖提示证据约束、跨连接版本冲突和文件替换后的恢复；不在真实训练数据库上注入故障。

2026-11-12，1.1.0 验证结果：51 项测试通过。新增 10 项回归覆盖澄清后不会、提示后补充、分类修订与回滚、旧事件恢复、练习待核实、局部规则调整和修订导出；保留独立 CLI 进程的完整流程测试。当前个人工作区没有初始化训练数据库。

实现模块：`common.py` 定义输入契约，`store.py` 和 `schema.sql` 管理事务与表结构，`rules.py` 计算评分，`service.py` 处理训练流程，`transfer.py` 负责导出和备份，`importer.py` 处理历史预检，`cli.py` 提供命令入口。

完整范围与验收条目见 [第一版设计](../../面试训练记录/自适应模拟面试本地工具第一版设计.md)。
