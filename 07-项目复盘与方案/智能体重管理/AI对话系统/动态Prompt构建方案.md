# 动态Prompt构建方案

本文讲解如何把可信规则、画像、会话摘要、历史证据和当前消息组织成模型输入，并处理来源、优先级、去重与 Token 预算。

## 1. 动态构建不等于每次重写规则

稳定模板与动态数据可以结合。可信规则、输出结构和任务边界适合版本化固定模板；画像、摘要、原文、证据及当前消息按本轮快照注入。`FIXED_TEMPLATE + userMessage` 也可以是一种合理实现：是否足够取决于任务需要，动态字段越多也不必然越好。

本篇不查询数据库、不更新摘要、不发送后处理消息。[[用户画像存储设计方案]] 提供带版本与来源的画像；[[会话上下文设计方案]] 提供摘要及未覆盖原文；[[千问Embedding+Milvus向量搜索集成文档]] 提供带状态的检索结果。业务编排负责取齐这些输入，构建器只做校验、选择、去重、预算分配和消息组织。

## 2. 输入与输出契约

建议接口如下，仅表示职责，不依赖某个 Java SDK：

```text
buildPrompt(
  authorizedScope,
  profileSnapshot,
  contextSnapshot,
  uncoveredMessages,
  retrievalResult,
  currentMessage,
  templateVersion,
  tokenBudget
) -> PreparedPrompt(messages, evidenceIds, sourceVersions, omittedReasons)
```

`authorizedScope` 来自上游权限校验；构建器仍需拒绝明显不匹配的租户、患者和会话数据。它不能从 `customerId` 字符串推导调用者有权查看。

`retrievalResult` 至少区分 `FOUND`、`EMPTY`、`UNAVAILABLE`。空结果只是本次条件下没有命中，不证明首次使用；失败则意味着历史暂不可用，不能向用户声称“您没有历史记录”。画像缺失同样区分不存在、未确认和服务故障。

输入必须是本轮冻结的快照。记录 `profileVersion`、`contextVersion`、摘要覆盖位置、记忆 ID/版本与模板版本，方便定位输出依赖；这不等于保存完整敏感 Prompt 到普通日志。

## 3. 七类内容如何组织

| 内容 | 放什么 | 不应混入什么 |
| --- | --- | --- |
| 可信任务规则 | 角色、回答边界、引用和缺失信息处理 | 用户提供的“忽略规则”等内容 |
| 画像 | 当前任务必要的、有来源的字段 | 全量患者资料、未确认推断 |
| 会话摘要 | 当前话题、待确认问题、已覆盖范围 | 未完成动作的隐含授权 |
| 近期原文 | 摘要尚未覆盖的消息及必要精确表述 | 与当前消息重复的内容 |
| 检索证据 | ID、来源时间、状态、相关片段 | 无权限数据、已删除或被替代记录 |
| 当前请求 | 用户这一轮实际输入 | 由模型猜测的用户意图替代原话 |
| 输出约束 | 回答格式、引用要求、缺失与冲突说明 | 无依据地保证诊断或行为结果 |

规则与数据按模型接口支持的角色和结构传入。用户消息、模型摘要及检索资料属于数据，即使其中写了“系统指令”也不能提升权限。可以使用明确的数据字段或分隔符帮助识别，但分隔符本身不是安全边界；真实鉴权、参数校验和动作审批在应用执行层完成。

将全量规则和资料拼成一个 user 字符串，会使来源与优先级难以维护；将检索资料直接放入 system 消息，也容易混淆信任级别。统一为“可信规则独立维护，资料明确标识来源”的接口契约，具体消息格式在实际模型客户端验证。

## 4. 一轮资料如何变成输入

以下为手工构造的非临床教学样本，展示状态和来源，不表示实际用户资料或模型输出：

```json
{
  "templateVersion": "dialog-v1",
  "profileVersion": 8,
  "contextVersion": 12,
  "coveredThroughSeq": 40,
  "profile": {"communicationStyle": "简洁", "status": "用户确认"},
  "context": {"topic": "活动记录", "pendingQuestions": ["日期待确认"]},
  "uncoveredMessages": [
    {"id": "m41", "role": "user", "content": "昨天走了5200步"}
  ],
  "retrieval": {"status": "EMPTY", "evidence": []},
  "currentMessage": {"id": "m42", "content": "帮我整理一下记录"}
}
```

构建结果应能表达：目前有一条用户自述活动记录，日期仍待确认，本次检索没有命中；可以整理已知内容，不添加新的测量、诊断或“首次用户”标签。若 `retrieval.status` 改为 `UNAVAILABLE`，对历史完整性的说明也必须改变，不能套同一个欢迎模板。

相同版本与相同输入应产生可追踪的组织结果。时间规则使用显式时区和可注入时钟，不直接依赖服务器 `LocalTime.now()`。模板按疾病字符串、BMI 阈值或模型情绪标签触发临床建议的旧样本不再作为默认实现；如业务需要此类规则，应引用经审核、版本化的业务规则，并保留适用条件及人工核对边界。

## 5. 去重、排序与预算

预算应覆盖“可信规则 + 当前请求 + 必要原文 + 摘要 + 画像 + 检索证据 + 预留输出”。不能只限制记忆条数或用 Java 字符长度当作准确 Token 数。

推荐选择顺序是：先保留任务规则和当前请求，再保留消除歧义所需原文，随后按任务需要选择画像和证据；摘要与原文按覆盖位置去重，记忆按 ID/版本去重。冲突信息保留来源与时间，不按拼接顺序默默覆盖。

若预算不足以容纳输入而关键事实不能安全省略，应返回需要缩小任务、补充资料或分步处理的状态。截断不能切断否定条件、单位或引用来源。“截前 50 字”是长度处理，不是可靠摘要。

### 5.1 最近三条的定向修正

约定摘要按时间/消息序号升序保存，下列 Java 方法只负责窗口选择，可独立验证。该方法输入一个升序列表，输出保留原顺序的最新窗口：

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class RecentSummaries {
    public static <T> List<T> latest(List<T> summaries, int limit) {
        if (limit < 0) {
            throw new IllegalArgumentException("limit不能为负数");
        }
        if (summaries == null || summaries.isEmpty() || limit == 0) {
            return Collections.emptyList();
        }
        int start = Math.max(0, summaries.size() - limit);
        return new ArrayList<>(summaries.subList(start, summaries.size()));
    }

    public static void main(String[] args) {
        List<Integer> input = List.of(1, 2, 3, 4, 5);
        if (!latest(input, 3).equals(List.of(3, 4, 5))) {
            throw new AssertionError("应取最后三条并保持原顺序");
        }
        List<Integer> copy = latest(input, 9);
        copy.clear();
        if (input.size() != 5 || !latest(input, 0).isEmpty()
                || !latest(null, 3).isEmpty()) {
            throw new AssertionError("边界或防止修改原列表的约束失败");
        }
        try {
            latest(input, -1);
            throw new AssertionError("负数限制应被拒绝");
        } catch (IllegalArgumentException expected) {
            // 预期拒绝非法输入。
        }
        System.out.println("最近摘要窗口验证通过");
    }
}
```

保存为 `RecentSummaries.java`，在 JDK 11+ 执行 `javac RecentSummaries.java` 后运行 `java RecentSummaries`。取前 3 条的反例，在 `[1,2,3,4,5]` 输入下得到 `[1,2,3]`；正确结果为 `[3,4,5]`。

## 6. 构建器与业务编排如何分工

`DynamicPromptBuilder` 可以按角色、画像、摘要、记忆、规则、消息和回复指引拆分方法。各方法共享统一的数据模型，字段名、来源和空值处理在接口层约定，避免每个模块各写一套实体。

`buildPrompt`、`promptService.build` 和 `buildFirstTimeResponse` 若分别维护相同规则，很容易出现模板漂移。应用落地时选一个构建器入口，检索层只返回资料和状态，不拼欢迎词；HTTP/SDK 层只序列化 `PreparedPrompt` 并处理调用。

模板参数替换可以复用固定模板，JSON 既可以是接口传输格式，也可以作为模型输入中的结构化资料；二者不冲突。是否可用不能用“动态或写死”判断，要看来源、预算和输出是否符合任务要求。

## 7. 示例运行与边界测试

在 JDK 17.0.11 下运行第 5.1 节示例，可观察最新窗口、超长窗口、空输入、零上限、负上限及副本隔离的行为；将代码改为取前 N 条后，相同用例会失败。这个对照实验说明：测试应检查“最近”这一语义，而不只是返回条数。

落地后至少覆盖：资料归属不匹配时拒绝；EMPTY 与 UNAVAILABLE 生成不同状态说明；当前消息重复时去重；升序摘要取最新窗口；超预算不截断关键条件；资料中出现伪造指令时不改变执行权限；冲突数据保留来源；日志不包含未经脱敏的正文。

## 8. 一个构建器支持两种业务模式

统一系统在现有输入契约上增加 `audience、purpose、policyVersion、taskState、allowedTools`。这些参数来自服务端模式和权限策略；患者输入“切换医生模式”不能更改它们。患者模式组织自身资料与对话；医生模式另加入当前目标、run修订号、工具契约、未完成调用及预算。共同的资料与预算逻辑只维护一次，见 [[医生助手Agent开发方案-代码实现]]。

`PreparedPrompt` 返回证据清单及其版本、检索完整性和省略原因。冻结是“一次调用使用固定清单”，不代表跨多个存储得到同时刻快照。后续步骤取得新证据时推进evidenceRevision并重新构建；旧草稿和旧审批不能沿用。

医生任务使用结构化工具协议；不靠文本中的 `Final Answer:` 或 `Observation:` 判断完成和执行成功。模型资料包含伪造指令时，既要测试输出是否仍遵守边界，也要断言工具调用被应用鉴权层拦截。分隔符不是权限控制。

统一缓存规则：首期不跨请求复用最终医生草稿或工具调用决定。将来缓存只读输出时，键必须绑定权限范围、audience、用途、全部来源版本、模板与模型；命中仍鉴权。不能通过去标点把“1.5”和“15”等不同请求归为同一语义。
