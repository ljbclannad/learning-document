# Git

[TOC]

- [[#1. 分支模型 & 工作流设计|一、分支模型 & 工作流设计]]
- [二、rebase / merge / reset / revert 深水区](#2-rebase--merge--reset--revert-深水区)
- [三、历史管理 & 提交规范](#3-历史管理--提交规范)
- [四、高级工具：worktree、submodule 等](#4-高级工具worktreesubmodule-等)

# 1. 分支模型 & 工作流设计

## 1.1 你负责一个 20+ 人团队的代码管理，如何在 GitFlow、GitHub Flow、Trunk-Based Development 之间做选择？请结合：发布频率、线上稳定性要求、回滚难度、代码审查成本来说明。

### 1.1.1 GitFlow
典型结构：main + develop + feature/* + release/* + hotfix/*
优点：
- 发布节奏偏版本制（1～4 周一次）时，非常好管理：release 分支可以冻结需求，只接 bugfix。
- 支持多版本并行维护（线上有 1.0 / 1.1 / 2.0 时会比较舒服）。

缺点：
- 分支多、流程重，对 20+ 团队来说，培训成本 + 心智负担都不低。
- 分支存活时间长，合并冲突、回归成本高。

### 1.1.2 GitHub Flow

典型结构：main + feature/*，所有东西都从 main 开分支、合 PR 回 main。
优点：
- 流程极简：拉分支 → 开发 → 提 PR → 合并 → 部署。
- 非常适合高频发布 / 持续交付：一天多次部署完全 ok。

缺点：
- 对发布过程的「阶段」刻画不够强（没有 release 分支），想要「候选版本在预发布环境 freeze 一段时间」会比较别扭（需要靠环境 + tag 补）。
- 要求配套 CI / 测试 / 代码规范比较成熟，否则 main 容易被搞脏。

### 1.1.3 Trunk-Based Development（主干开发）

核心思想：
- 所有人尽量直接基于主干（main / trunk）做小改动；
- 分支如果有，也必须是极短生命周期（1～2 天内合并）；
- 通过**Feature Flag（特性开关）**控制未完成功能，不靠长期分支。

优点：
- 提交粒度小、迭代快，天然适配 CI/CD 和高频部署。
- 历史干净，冲突早发现早解决。

缺点：
- 对工程基础要求很高：自动化测试、质量门禁、灰度/回滚机制、Feature Flag 等都要跟上。
- 团队开发习惯要改造，不适合“测试全靠人眼 + 手点”的原始部落。

### 1.1.4 发布频率

一句话版本：发布越频繁，越偏向 GitHub Flow / Trunk；发布越“版本化”，越偏向 GitFlow。

### 1.1.5 线上稳定性要求

GitFlow 的稳定性手段：
- 「稳定」体现在 release 分支：在 release 分支上只做 bugfix，不再混入新需求；可以长时间回归、联调。
- 适合：强监管行业（金融、医疗）、测试周期长、回归复杂的情况。

GitHub Flow / Trunk-Based 的稳定性手段：
- 靠的是：严格保护 main（必须 PR + Review + CI 通过）；自动化回归（单测、集成测试、静态检查）；线上 Feature Flag、灰度发布、蓝绿部署。
- 适合：服务拆得比较细（挂一个服务不至于全站爆炸）；团队已经习惯自动化测试，而不是全靠人肉点。

### 1.1.6 回滚难度

从“回滚操作的直观程度”来对比：
- GitHub Flow / Trunk-Based：所有东西都在 main 上，发布通常对应一个 tag 或某个 commit：回滚 = 部署上一个 tag / 上一个稳定 commit；或者对问题 commit 做 git revert。对于已自动化的流水线，属于一键部署回滚的友好模型。
- GitFlow：典型情况：某次发布对应 release/1.2.0 合并 main 后的某个 tag。想回滚：运维层面可以回滚到上一个 tag（跟 GitHub Flow 类似）；但热修 bug 时，需要在多个分支同步（main / develop / 还活着的 release).如果版本线多，回滚 + bugfix 分支同步会比较烧脑。

### 1.1.7 代码审查成本

主要看两点：PR 粒度 和 分支存活时间。
- GitFlow：feature 分支往往活得比较久（1～2 周甚至更长）。一个 PR 改动很大，Reviewer 心理阴影面积也大：审查时间长；容易漏问题；冲突也更容易积累。
- GitHub Flow / Trunk-Based：强调「小步快跑」：功能拆分成小任务，小 PR 频繁合并；审查成本分摊到日常，而不是发版前堆成山。对 20+ 人团队来说，有利于把 Review 当日常工程实践，而不是大考前突击。

总结：
- 希望 “大版本前集中审查” → GitFlow 更贴合老派流程。
- 希望 “平时多上小作业，期末不搞破防” → GitHub Flow / Trunk-Based 会更舒服。

### 1.1.8 结合“20+ 人团队”的实战选型

#### 1.1.8.1 老牌系统 + 月度发版 + 线下/人工测试为主
1. 特征：
    - 发版频率：1～2 周甚至更慢；
    - 行业敏感（医疗、金融、政务等）；
    - 自动化测试还不算给力，大量回归靠测试同学手点；
    - 版本维度需要很清晰（每次上线要有明确“版本包”的概念）。

2. 我会选：简化版 GitFlow
    - 保留：main（线上稳定）、develop（集成测试）、feature/*（需求）、hotfix/ *（热修）、release 分支按需使用（重大版本或大促前）。
    - 但会弱化：不鼓励长期 release/* 乱飞；能用 tag 解决的就用 tag，不强行造分支。

3. 理由对齐四点：
    - 发布频率低：GitFlow 天然支持“版本制”。
    - 稳定性：release 分支可冻结，给测试足够窗口。
    - 回滚：通过 tag 管理版本，部署层面回滚简单。
    - 审查：feature 合并 develop 前做 Review，重大版本可以在 release 上再做一轮集中 Review。

#### 1.1.8.2 微服务 + 每周多次发布 + 有 CI/自动化测试
1. 特征：
    - 10+ 微服务，服务拆得还算细；
    - 每个服务一周 1～3 次小版本发布；
    - 单元测试 + 少量集成测试已经跑在 CI 里。

2. 我会选：GitHub Flow + 一点点 Trunk 思想
    - 流程基本是：
        - 所有人从 main 拉 feature/*；
        - 必须走 PR，必须过 CI；
        - 合并 main 自动部署测试环境，人工验一下后再推灰度 / 正式。
        - 发版用 tag + 发布流水线 管理。

3. 理由对齐四点：
    - 发布频率：对高频发布非常友好。
    - 稳定性：通过 CI + 保护 main 分支 + 灰度/回滚方案保证。
    - 回滚：版本 = tag，对运维最友好。
    - 审查：小 PR，日常 Review 成本更均衡，不会集中爆炸。

#### 1.1.8.3 工程体系成熟 + 希望走真正的持续交付
1. 特征：
    - 单测、集成测覆盖不错；
    - Feature Flag 体系完善（开关控制、灰度、按用户/租户放量）；
    - 有能力做到“一合并就能自动上线某环境”。

2. 我会选：Trunk-Based Development
    - 规范：分支生命周期控制在 1～2 天之内；
    - 大需求拆成多个小改动，通过特性开关串起来；
    - 合并 main 后自动流转到测试 / 预发环境。

3. 理由对齐四点：
    - 发布频率：想多快就多快。
    - 稳定性：靠测试 + flag + 灰度，而不是复杂分支。
    - 回滚：部署上一个版本，或对问题 commit 做 revert。
    - 审查：PR 小，Review 流畅，不堆积。
 
## 1.2 需求变更与发布流程

只要这次变动“不一定要进这次发布”，就去 dev 上改；只要被强行要求“本次一定要带上”，就要在 release 上做，但要保证 dev 也同步。

### 1.2.1 这波需求变动可以下个版本再发（推荐）
1. 当前 release：只修 bug，不加新需求
    - 继续在 release/x.y.z 上只合并 bugfix 分支：
    ```bash
        git checkout release/x.y.z
        git merge bugfix/xxx
    ```

2. 需求变更 → dev 分支实现
    - 在 dev 上开 feature 分支：
    ```bash
        git checkout dev
        git pull origin dev
        git checkout -b feature/new-change
        # 开发、提测，准备下个版本合并
    ```

3.	发完本次版本之后：
    - release/x.y.z 合并回 main & dev，然后删掉；
    ```bash
        git checkout main
        git merge release/x.y.z
        git push origin main
        git checkout dev
        git merge release/x.y.z
        git push origin dev
    ```
    - 下一次再从 dev 切 release/x.y+1.0，就自然带上了这个变更。
    ```bash
        git checkout dev
        git pull origin dev
        git checkout -b release/x.y+1.0
        git push -u origin release/x.y+1.0
    ```

### 1.2.2 这波必须进本次 release（现实经常发生）
1. 变更要基于当前 release/x.y.z 做（因为测试是在这个基线之上）。
    - 在 release/x.y.z 上开 feature 分支：
    ```bash
        git checkout release/x.y.z
        git pull origin release/x.y.z
        git checkout -b feature/change-on-release
    ```
2. 改完后合并到 release，并再同步回 dev。
    ```bash
        git checkout release/x.y.z
        git merge feature/change-on-release
        git push origin release/x.y.z
    ```

3. 提 PR 到 release/x.y.z，测试回归：
    ```bash
        git checkout release/x.y.z
        git merge feature/change-on-release
        git push origin release/x.y.z
    ```
4. 额外一步：同步回 dev（非常关键！）
    - 两种选项选其一：
    - 方式 A：把 release/x.y.z 合并回 dev
    ```bash
        git checkout dev
        git pull origin dev
        git merge release/x.y.z   # 或 rebase，看你团队规范
        git push origin dev
    ```
    - 方式 B：只把那次变更 cherry-pick 到 dev
    ```bash
        git checkout dev
        git pull origin dev
        git cherry-pick abc1234
        git push origin dev
    ```

## 1.3 假设你们现在用 GitFlow，主干分支结构如下：main、develop、feature/*、release/*、hotfix/*。某版本上线后连续出现 3 次紧急线上 bug，你会如何调整分支策略或流程，降低“热修”成本？

### 1.3.1 为什么会连续 3 次紧急线上 bug？
1. 在 GitFlow 下，出现这种情况通常是几个通病叠加：
	1. 版本太“大锅炖”
        - 一堆 feature 同时从 develop 合到 release，一次上大堆改动。
        - 一出问题，你很难快速定位是哪个改动引起的。
    2. release 分支存活时间太长，逻辑老是分叉
        - release 上有一些临时改动 / 应急 hack，dev 又在往前飞。
        - 每次 hotfix 都要想：这个修复是修 main？修 release？两个都要？
        - 一不小心就出现“线上修好了，下一版又恢复成老 bug”。
    3. 热修路径不统一
        - 有人直接在 release 上改；
        - 有人从 main 开 hotfix；
        - 有人从 develop 搞一搞再 cherry-pick

2. 结果就是：修复分散在不同分支，回流没做好，下次发版继续踩。

3. 所以题目问“怎么调整分支策略或流程，降低热修成本”，重点是：
    - 减少“修在哪里”的选择题 → 统一路径
    - 减少“修几次”的重复劳动 → 统一回流策略
    - 减少“会不会再炸”的不确定 → 提前防 / 更小发布粒度

### 1.3.2 我会怎么改分支策略？
1. 重新定位 main：main 永远 == 当前线上版本
    - main 分支永远代表“当前线上版本及其所有已上线 hotfix”。
    - 紧急修复的时候，只需要问一句：“这个 bug 是线上有吗？是 → 直接基于 main 修”。
    - 不会再出现“热修是基于上一个 release 还是 develop”的分歧。
    - 热修标准流程：
        ```bash
            # 基于 main 拉热修分支
            git checkout main
            git pull origin main
            git checkout -b hotfix/xxx-critical-bug
            # 修改 + 自测 + CI
            git commit -m "fix: xxx 线上紧急问题"
            git push -u origin hotfix/xxx-critical-bug
            # 提 PR -> 合并回 main
            git tag -a v1.2.1 -m "patch: 修复xxx紧急问题"
            git push origin v1.2.1
        ```

2. 规范热修回流：修一次，保证主线都带上
    - 连续 3 次 bug 很大概率是“修了，但没让后续版本带上”，所以我要把回流策略写进流程：
    - 热修合并 main 之后，必须立即做两件事：
        1. 合并回 develop
        2. 视情况 cherry-pick / merge 到正在提测的 release/*
    - 具体操作：
        ```bash
            # 热修已合并 main
            git checkout develop
            git pull origin develop
            git merge --no-ff main          # 或 cherry-pick 那个 hotfix commit
            git push origin develop

            # 如果当前有在测 release/x.y.z
            git checkout release/x.y.z
            git pull origin release/x.y.z
            git cherry-pick <hotfix-commit-id>   # 只挑这次修复
            git push origin release/x.y.z
        ```

3. 规范 release 使用方式：缩短寿命，只做“版本整合 + 回归”
    1. 提测之后的 release 分支视为“冻结分支”
        - 只允许：
            - hotfix 回流；
            - 针对该版本发现的 bugfix。
        - 禁止在 release 上“裸写修复”然后忘记同步。
        - 热修必须走 hotfix → main → develop / release 这条官道，不准走小路。
    2. 标准收尾：
        ```bash
            # 发版成功后
            git checkout main
            git merge --no-ff release/x.y.z
            git tag -a vX.Y.Z -m "正式发布 X.Y.Z"
            git push origin main vX.Y.Z

            git checkout develop
            git merge --no-ff release/x.y.z
            git push origin develop

            git branch -d release/x.y.z
            git push origin --delete release/x.y.z
        ```

4. 适当“弱化 GitFlow”，往小批次发布靠拢
    - 3 次连续紧急 bug，很可能说明你们现在是典型「大版本 + 大合并」：
        - develop 上憋了一堆功能，一起合 release，一起上线，一起炸。
    - 在保证线上的前提下，我会适度“瘦身” GitFlow，往更小粒度的发布靠拢。
        - 从「几周一个大 release」→ 「一周一个小 release」，甚至关键服务单独发；
        - 支持部分服务走类似 GitHub Flow：main + feature/，CI 通过就能上测试环境；
        - 分支上少攒代码，尽量小改动、快合并、快验证，bug 更容易定位。

### 1.3.3 流程层面怎么配合降成本？
1. 为 hotfix 单独设计一条“快速通道”
    - hotfix 分支必须：
        - 修改范围可控（代码行数 / 文件数有上限预警）；
        - 必须写明对应线上问题单号；
        - 必须至少 1 人 Review（可以不走大流程，但不能裸 merge）。
        - CI pipeline 为 hotfix 优先级提升：
            - 单测 + 少量关键集成测试通过即可发版；
            - 部署策略：先灰度再全量。
2. 利用 tag 管理线上 patch 版本，回滚简单
    - 既然连续 3 次紧急 bug，很大概率会涉及多次线上回滚 / 重发 patch，我会说明：
        - 每次正式发版用 tag：v1.3.0
        - 每个热修 patch 再打：v1.3.1-p1、v1.3.1-p2 之类
        - 运维层面所有部署只认 tag，不认裸 SHA

### 1.3.4 总结
1. 如果要在面试中说出来，我会压成类似这样：
    - 连续 3 次线上紧急 hotfix，说明我们的 GitFlow 在“release、hotfix、回流”这块比较松散，导致：修复点分散、回流不彻底、下个版本又炸。
    - 我会做三类调整：
        1. 主干定位：main 永远等于当前线上版本，所有 hotfix 统一从 main 开分支，修完合回 main，并打 patch tag。
        2. 回流规范：每次 hotfix 合并 main 后，必须立刻同步回 develop，视情况 cherry-pick 到当前 release，禁止在 release 上裸写修复又不回流。
        3. release 策略：提测之后的 release 冻结，只接 bugfix，用完就合并回 main + develop 并删除，避免长期多 release 并行。
    - 再配合：给 hotfix 设计 CI 快速通道 + 小步发布策略，降低每次发版的改动范围，从根上减少“连续救火”的概率。

# 2. rebase / merge / reset / revert 深水区

## 2.1 rebase和merge的区别
rebase = 换一个“起点”，把你这几个 commit 拿起来，重新“摞”到别的 commit 后面。

### 2.1.1 先从一个简单场景看 rebase 在干嘛

```bash
#有一个仓库，历史长这样（字母代表 commit）：
A - B - C      (main)
     \
      D - E    (feature)
```

1. git rebase main 做的事就是：
	1. 找出：在 feature 上有、但在 main 上没有的 commit → D、E
	2. 把 feature 的起点从 B 改为 C
	3. 按顺序重新“重放” D、E 的改动（实际上生成新的 commit）
	4. 变成：
        ```bash
        A - B - C         (main)
                \
                D' - E' (feature)
        ```


### 2.1.2 和 merge 的差别：历史长啥样不一样
1. 还是那幅图：
```bash

A - B - C      (main)
     \
      D - E    (feature)
```
2. 用 git merge main：
    ```bash
    A - B - C --------- M  (feature)
        \            /
        D - E -----
    ```
    - M 是一个新的 merge commit
	- 历史是“有分叉再合并”的样子，有“面条”

3. 用 git rebase main：
    ```bash
    A - B - C - D' - E'    (feature)
    ```
    - 历史看起来是一条直线，好像“D/E 就是基于 C 写的一样”
    - 分叉消失了，逻辑上更干净，但历史被重写了

4. 概念上的区别：
    - merge：保留真实发生过的历史（像 git 的“录像回放”）
    - rebase：改编历史，让它看上去像“从来就是这么写的”

### 2.1.3 从 Git 的内部视角看：rebase 在做两件事

1. 稍微硬核一点，但很关键：
	1. 改变当前分支的 base（基点）
        - git rebase main 等价于：
        - 把当前分支的“起点”从旧的 commit（比如 B）换成了新的 commit（比如 C）
2. 重放（replay）一串 patch
    - 找出当前分支相对于 base 的那些 commit（D/E）
    - 把每个 commit 的 diff 拿出来，按顺序重新 apply 到新的 base 上
    - 每个被“重放”的 commit 都会生成一个新的 commit（D’/E’）

## 2.2 说一下你在实际项目中使用 git rebase 的场景和明确“不应该使用 rebase” 的场景。请给出至少 2 个反例，说明可能带来的严重后果。

### 2.2.1 我实际会用 git rebase 的场景

1. 场景 1：本地 feature 分支同步主干，保持历史“直线”
    - 流程是：main → feature/xxx → 提 PR。
	- 这期间 main 不停有其他人合 PR。
	- 在我准备提 PR 前，会用 rebase 把自己的分支“挪到最新 main 上”，避免一堆 merge commit。
	- 示例：
        ```bash
            # 已在 feature/queue-optimize 上开发了一段时间
            git checkout feature/queue-optimize
            git fetch origin
            git rebase origin/main
            git push -f origin feature/queue-optimize
        ```

2. 场景 2：合 PR 之前用 rebase -i 整理提交历史
    - 流程是：main → feature/xxx → 提 PR。
    - 这期间 main 不停有其他人合 PR。
    - 在我准备提 PR 前，会用 rebase -i 整理提交历史，避免一堆 merge commit。
    - 示例：
        ```bash
            git rebase -i origin/main
        ```
    - 开发过程很真实：会有一堆：fix typo、adjust log、fix test 这种 commit；真正合到 main 时，我希望是：feat: 支持排队预测 refactor: 抽象挂号与排队公共逻辑
    - 示例：
        ```bash
            git rebase -i origin/main
        ```
    - 目的：
        - 控制 commit 粒度：每个 commit 都尽量是“可独立回滚 / 可独立阅读的功能单元”；
        - 日后 git bisect / 回滚时更友好。

3. 场景 3：个人分支用 git pull --rebase 避免无意义 merge
    - 如果某个远程分支只有我一个人在用（比如个人长期实验分支），我会：
        ```bash
            git pull --rebase
        ```
    - 而不是：
        ```bash
            git pull   # 默认可能是 pull + merge
        ```

### 2.2.2 我明确不会用 git rebase 的场景

1. 不要对“公共分支”做 rebase：main / develop / 共享 feature 分支
    - 例如：
        - main：对应线上版本，是所有人“唯一真相来源”；
        - develop：所有人都在基于它拉 feature；
        - 某个团队多人共同开发的 feature/big-refactor。
    - 只要有可能别人已经：
        - 基于这个分支拉新分支；
        - 拉了代码在本地做修改；
        - 基于这个分支构建、部署过。
    - 那么你对它做 rebase + push -f，就等于：
        ```bash
            git rebase -i origin/main
            git push -f origin feature/big-refactor
        ```
    - 你把他们脚下的地板换了一遍，所有 commit hash 全变，他们手里的历史全乱了。

2. 不要对已经发过版、打过 tag 的历史再 rebase
    - 如果 tag 已经被用作：
        - 生产环境发布版本的标记：v1.3.0；
        - CI/CD 的构建来源；
        - 问题排查 / 审计记录。
    - 这时再 rebase 之前的 commit，相当于：
3. 不要在你不完全掌控的分支上“随便帮别人 rebase”
    - 例如：
        - 你看别人的分支历史很乱，手痒帮忙 git rebase -i 一波；
        - 结果人家本地还有很多没有 push 的提交、stash、worktree。
    - 这类“热心 rebase”非常容易造成协作灾难（下面反例会写）。

### 2.2.3 两个（加码成三个）“血泪反例”：乱用 rebase 的后果

1. 共享 feature 分支被 rebase，导致别人提交“消失”
    - 例如：
        - 你们有个大重构分支：feature/big-refactor，团队 A/B/C 三个人都在上面开发；
        - 大家都已经基于这个分支工作了几天，push 了一些 commit；
        - 你觉得历史太丑，决定来个 rebase -i + git push -f 美化一下。
    - 你做了：
        ```bash
            git checkout feature/big-refactor
            git fetch origin
            git rebase -i origin/main   # 本地历史重写一波
            git push -f origin feature/big-refactor
        ```

    - 后果：
        - 同事 B、C 本地的 feature/big-refactor 还在旧历史上；
        - 他们下一次 push 会看到一堆奇怪的错误：
            ```bash
                git push origin feature/big-refactor
            ``` 
        - 有人用 git reset --hard origin/feature/big-refactor 直接覆盖本地，丢了没提交的几天代码；
        - 有人乱 merge，一堆重复代码、冲突标记、幽灵 commit 出现在历史里面。
    - 总结给面试官：
        - 在多人共同开发的分支上做 rebase，本质上是单方面改整个团队的历史，很容易导致别人本地 commit 丢失、冲突极度复杂。
        - 所以我会约定：只有“自己一人负责的分支”上允许 rebase；公共分支统一禁止 rebase，只能 merge。

2. 对 main 做 rebase，线上的 tag 和代码对不上号
    - 例如：
        - 你们的发布模型是：
            - 每次发版前打 tag：v1.2.0；
            - 运维用 v1.2.0 这个 tag 对应的构建部署到生产。
            - 上线后发现历史有点难看，你心想“美化一下 main 历史更好看”，然后对 main 做了 rebase。
    - 你做了：
        ```bash
            git checkout main
            git fetch origin
            git rebase -i origin/main
            git push -f origin main
        ```
    - 后果：
        - 原来的 v1.2.0 指向的是旧的 commit（已经不在 main 这条链上了）；
        - 然后有人又在新的 main 上重打了一个 v1.2.0（更惨）；
        - 结果：
            - 生产环境跑的是“旧 v1.2.0 对应的构建”；
            - Git 仓库里展示的 v1.2.0 是“新 v1.2.0 所在的 commit”；
            - 问题排查时，你 git show v1.2.0 看出来的代码和线上完全不一样。
    - 总结给面试官：
        - 对已经用于生产部署的分支 / 历史（尤其是打过生产 tag 的 commit）做 rebase，会直接破坏“代码 → 版本 → 生产”的映射关系，是严重的工程事故。
        - 所以我会坚持：生产 tag 一旦打出，tag 所在历史就绝对不能 rebase。

3. rebase 导致 CI/CD 触发重复部署甚至错误回滚
    - 例如：
        - CI/CD 配置为：“监听某个分支（比如 main）的 push，就自动构建 + 部署测试 / 预发”；
        - 你对 main 做 rebase，会把一串老 commit“再推一遍新的历史上去”。
    - 后果：
        - CI 看到的是“有一堆新 commit（其实只是 hash 变了）”；
        - 结果疯狂触发多次 pipeline：
            - 重复构建镜像、重复部署测试环境；
            - 若 pipeline 中有“自动回滚”逻辑，还可能混淆版本，导致错误回滚到已 rebase 的旧 commit。
    - 总结给面试官：
        - 在 CI/CD 依赖分支线性历史、commit hash 的场景下，rebase 公共分支不仅会影响开发者本地，还会让流水线重复执行、部署错版本。
        - 所以我会坚持：生产 tag 一旦打出，tag 所在历史就绝对不能 rebase。

### 2.2.4 总结
1. 我平时用 rebase 的场景：
    - 在自己维护的 feature 分支上，合 PR 前会用 git rebase origin/main 同步主干，保持提交历史是“直线”，冲突自己消化；
    - 合并前用 git rebase -i 把一堆 fix/wip commit squash 掉，让每个 commit 都有清晰语义，方便以后回滚和 bisect；
    - 偶尔在只属于我个人的远程分支上用 git pull --rebase 避免无意义 merge commit。
2. 我明确不会用 rebase 的场景：
    - 对任何已经被多人使用的“公共分支”（main / develop / 共享 feature 分支）禁止 rebase，因为这会重写团队的历史；
    - 对已经发过版本、打过线上 tag 的历史绝不做 rebase，避免 tag 与生产环境代码不一致。
3. 两个严重后果的例子：
    - 例子一：共享 feature 分支被人 rebase + push -f，其他同事本地分支与远端历史完全不一致，导致有人 reset --hard 丢了几天代码，有人陷入复杂冲突中半天出不来。
    - 例子二：有人对 main 做 rebase，重打了生产 tag，导致 v1.2.0 这个 tag 在线上代表的代码跟 Git 仓库里看到的不一致，排查线上 bug 时完全对不上号，回滚和审计都出了问题。
    - 所以我的原则是：“只 rebase 自己的私有历史，从不 rebase 已经公开的历史”，并在团队规范里明确这一点。

## 2.3 git revert 和 git reset 在「线上已发布」场景下的使用边界是什么？如果一次发布里 10 个 commit，只想撤回其中 2 个，你会如何操作，为什么？

### 2.3.1 线上已发布场景下：git revert vs git reset 的边界

1. git reset 在线上场景的问题
    - reset 做的是：把当前分支 HEAD 指针强行挪到另一个 commit 上，然后你再 push -f 把远端也改掉。
    - 这意味着：
        - 原来已经发布出去的那段历史上的 commit
        - 在远端分支上会“消失”（其实还在某些 clone 和 reflog 里，但对主线来说没了）。
        - 所有已经 pull 过这段历史的同事，本地分支与远端严重分叉：
            - 要么强制 reset --hard origin/main 丢本地改动；
            - 要么遇到一堆诡异冲突。
        - 如果之前基于这些 commit：
            - 打过 tag（生产版本用的）
            - 构建过镜像 / jar 并发布
        - 那代码 → tag → 生产环境之间的映射会变得极其混乱。

    - 所以边界很清楚：
        - reset 适用：
            - 你自己的本地分支，还没 push；
            - 或者一个只属于你自己的远端分支（没人基于它开发、发版、打 tag）
        - 不建议对：
            - main / master / 已发布版本所在分支
            - 任意已经被多人 clone、被 CI/CD 使用、被打了 tag 的历史

2. git revert 在线上场景的角色
    - revert 做的是：在当前分支上再生成一个新的 commit，这个 commit 的效果是“抵消之前某个 commit 的改动”。
    - 特点：
        - 不会删历史，也不改已有 commit 的 hash；
        - 新增一个“反向补丁”commit；
        - 审计上很好解释：
            - “X 版本引入了 bug 的 commit：abc1234”
            - “后面用 revert 生成了一条修正 commit：def5678”。
    - 所以对于“已发布、已被多人使用的分支”，首选 revert：
        - 安全：不会炸别人本地 repo；
        - 清晰：历史上看得到“问题是哪个 commit，引入了什么修复/撤销”。

    - 总结边界：
        - 线上已发布 + 公共分支：用 revert 回滚逻辑，用 reset 基本等同于工程事故。
        - reset 仅用于“未对外承诺的历史”（你自己用的工作分支）。

### 2.3.2 一次发布里有 10 个 commit，只想撤回其中 2 个，怎么做？

1. 正确做法：用 git revert 有选择地反做那两个 commit
    - 假设你刚发布了 v1.3.0，里面包含 10 个 commit：C1...C10；
    - 发现其中两个 commit（比如 C3 和 C7）有问题；
    - 要撤回它们，但不想影响其他 8 个。
    - 假设现在 main HEAD 就在 C10，且已经上线。

    - 标准流程：
        ```bash
            git checkout main
            git pull origin main
            git checkout -b hotfix/revert-bad-commits

            # 注意：如果两个 commit 有依赖关系，一般要先 revert 较新的那个
            git revert <C7的hash>
            git revert <C3的hash>

            # 过程中如果有冲突，按正常流程解决，然后 git add、git revert --continue
        ```

    - 提交 hotfix 分支，走代码审查 + CI
        ```bash
            git push -u origin hotfix/revert-bad-commits
        ```

    - PR 合并回 main，触发新的构建/发布
        ```bash
            git push -u origin hotfix/revert-bad-commits
        ```

    - 执行完后，历史会变成类似这样：
        ```bash
            ... - C1 - C2 - C3 - ... - C7 - ... - C10 - R7 - R3
                                ^           ^
                              出问题       revert 提交
        ```
        - R7：撤销 C7 的 commit；
        - R3：撤销 C3 的 commit。

    - 为什么不直接 reset 回 C2 或 C9？
        - reset --hard C2 会丢掉 C3~C10 全部提交，8 个好 commit 也没了；
        - 你可以再 cherry-pick 那 8 个好 commit，但这本质上还是在重写历史，
        - 对已经在线上发布的 main 分支来说风险太大，而且会完全打乱历史结构。

    - 线上环境的基本原则是：
        - 在原版基础上叠加“修正”，而不是把原版当作没发生过。

2. 若两个问题 commit 是“一个功能分支”的整体，也可以考虑 revert merge
    - 还有一种常见情况：
        - 你们每个 feature 都是一个独立分支，通过 PR 合并到 main，发布由几个 feature 组成。
        - 比如：
            - feature/queue-predict 合并时产生了一个 merge commit：M_feature；
            - 而你知道“这个功能整个不要了”，而不是撤销其中一部分。

    - 解释：
        - -m 1 表示“保留主干（父分支）的那条线，只撤销 merge 进来的那条线的变化”；
        - 相当于“一键撤掉这个 feature 的所有改动”。

3. 什么时候可以考虑用 reset + cherry-pick 的极端方案？

    - 严格来说，在这些前提下才可以讨论 reset：
        - 这个分支虽然“线上已发布”，但你有极强的组织能力和流程管控：
            - 所有开发者都能迅速同步操作；
            - 可以接受一次性的“大范围强制 reset”；
            - CI/CD、tag 关联、审计也能统一调整；
        - 这 10 个 commit 里问题很多，需要大面积回滚，再精挑细选往前带。

### 2.3.3 可以把回答压缩成面试版这样说：
1. 在线上已发布的场景里，我会把 git reset 和 git revert 的边界划得比较清楚：
    - reset 会重写历史，需要强推，会让所有已经基于该分支工作的同事本地历史和远端不一致，也会破坏 tag → 版本 → 生产环境之间的映射，所以只在本地私有分支或未公开的远端分支上用；
    - 对于已经发布到线上、并被多人使用的分支（比如 main），我只使用 git revert 来撤销某些提交，通过新增“反向提交”的方式来保留完整历史和审计链路。

2. 如果一次发布里包含 10 个 commit，只想撤回其中 2 个，我会：
    - 从当前生产对应的 main 拉一个 hotfix/xxx 分支；
    - 在这个分支上对那两个问题 commit 执行 git revert <hash>（注意顺序，先新的后旧的），解决冲突后提交；
    - 提 PR 合回 main，触发新的构建和发布。

## 2.4 给出一个你在真实项目遇到的复杂冲突案例（例如多分支并行重构），请说明：你如何分析冲突来源（哪些 commit / 分支）、用了哪些 Git 命令帮助你定位问题（如 git log -p、git blame、git bisect）、你如何在解决冲突的同时保证不引入回归。

### 2.4.1 场景背景：多分支并行重构，同一块核心逻辑
1. 假设项目里有一个老模块 patient-service，负责：
    - 患者基础信息查询 PatientService
    - 患者挂号记录查询 RegistrationService
    - 统一的 PatientDTO

2. 这次你们做了两条并行大改动：
    - 分支 A：feature/refactor-patient
    - 重构患者领域模型、DTO、Repository
    - 大量改类名 / 字段名 / 包结构
    - 分支 B：feature/optimize-registration
    - 优化挂号查询性能，引入批量查询 + 缓存
    - 同时顺手改了一点 PatientDTO 字段（例如新增了 cardType 之类）

3. 两条线都持续开发了 1～2 周，各自都有十几个 commit。现在的顺序是：
	1.	feature/refactor-patient 先合并进 develop 成功；
	2.	轮到 feature/optimize-registration 要合进 develop 时，发生了大面积冲突，涉及：
        - PatientService.java
        - PatientDTO.java
        - 若干 Mapper / Repository
        - 若干单测
        - 你要做的事：把 B 线的改动正确叠加到已经重构过的 A 线上，不能丢 A 的重构，也不能丢 B 的性能优化。

### 2.4.2 第一步：先搞清楚“到底谁改了什么”

1. 找出哪些文件冲突
    - 合并时 Git 会直接告诉你一堆冲突文件：
    ```bash
        git merge feature/optimize-registration
        # 冲突…
        git status
    ```
    - git status 会列出 both modified 的文件，比如：
    ```text
        both modified:   patient-service/src/main/java/.../PatientService.java
        both modified:   patient-service/src/main/java/.../dto/PatientDTO.java
        both modified:   patient-service/src/main/java/.../RegistrationService.java
    ```
2. 对单个文件，用 git log 看清楚两边的改动线
    - PatientDTO.java
        ```bash
        # 只看这个文件的提交历史，带图形和分支标记
        git log --oneline --graph --decorate -- patient-service/.../PatientDTO.java
        ```
    - 我会重点看：
        - 哪些 commit 来自 feature/refactor-patient（A 线）
        - 哪些来自 feature/optimize-registration（B 线）
        - 哪些 commit 已经在 develop 上了（A 已经合了）
    - 你可以顺便用：

3. 对关键逻辑，用 git blame 看“最近是谁动了这几行”
    - 比如你看到冲突出现在 PatientService.getPatientDetail() 里：
    ```bash
        git blame patient-service/.../PatientService.java
    ```
    - 我关注：
        - 来自 A 线重构的 commit：通常是改模型 / DTO / 包结构
        - 来自 B 线优化的 commit：通常是性能相关改动，比如加缓存、批量查询


### 2.4.3 第二步：解决冲突的策略——先“对齐结构”，再“叠加行为”

1. 把 A 线重构当成“新的地基”，先接受结构变化
    - 在 feature/refactor-patient 里：
    ```java
        private String idCardNo;
    ```
    ``` java
        // -> 改成
        private String certNo;
        private CertType certType;
    ``` 
    - PatientService.getPatientDetail 返回类型改了：
    ```java
        public PatientInfoDTO getPatientDetail(Long patientId)
        // -> 变成
        public PatientDTO getPatient(Long patientId)
    ```
    - 这类统一重命名 / 结构调整我会优先以 A 为准：
    - 在冲突块里，直接用 --ours 作为底，手动把 B 线逻辑贴过来：
    ```bash
        # 对于明显应该保留 A 结构的类
        git checkout --ours patient-service/.../PatientDTO.java
        # 再在此基础上，把 B 分支增加的字段逻辑手动 merge 进去
    ```
    - 或者结合三方 diff 工具比对。

2. 再把 B 线的“行为改动”叠加进来
    - B 分支可能做了这些事：
        - 把多次单条查询变成 IN 批量查询；
        - 加了本地缓存 / Redis 缓存；
        - 加了分页 / 限流逻辑。
    - 处理方式：
        - 在已经“采用 A 结构”的版本上打开文件，靠 git diff 看 B 分支到底改了什么：
        ```bash
            git diff origin/develop..feature/optimize-registration -- patient-service/.../RegistrationService.java
        ```

    - 然后把纯业务行为改动迁移过来：
        - 原来 getPatientDetail 里查询逻辑改成批量查询；
        - 把缓存逻辑、异常处理逻辑一点点搬到新结构下。
    - 这样做的核心思想：
        - 优先统一“API / DTO / 领域模型”的形状，再在这个新形状上叠加性能优化 / 缓存行为。
    - 你可以一边用 IDE 的对比工具，一边用：
        ```bash
            git diff --ours --theirs -- patient-service/.../PatientService.java
        ```
    - 明确看到 ours（A 分支的结果） 和 theirs（B 分支的结果）差异，把两边需要的东西都留下。

### 2.4.4 第三步：怎么保证不引入回归？
光把冲突修完还不行，最容易出事的是：修完冲突之后某条逻辑悄悄回退到了旧行为 / 少了一步校验。
我通常会从三层防线来讲：用测试“锁住行为” + 用 git 工具“确认改对” + 用 git bisect 兜底排查。
1. 行为锁定：先写（或补）关键用例
    - 先补充/确认关键自动化测试
        - 单元测试：
            - 针对 PatientService.getPatient、RegistrationService.listRegistration 写/补测试：
                - 区分：有 ID 卡、护照、社保卡等不同 CertType
                - 老数据的兼容场景（历史记录里 certType = null 时的行为）
            - 集成测试：
                - 挂号接口从“并发 100 条请求”下依旧返回正确的患者信息；
                - 批量查询 + 缓存一致性场景（比如更新后缓存失效）。
    - 冲突解决前后，对同一个接口打一套回归用例
        - 在合并前，从 B 分支切一个本地环境，记录几组关键请求+响应；
        - 合并冲突后，在 develop 上部署，跑同样的请求，用脚本比对响应字段。

2. 用 Git 再核对一遍：确保“该有的改动都在”
    - 对比合并前后的差异范围
        ```bash
            git diff origin/develop..feature/optimize-registration -- patient-service
        ```
    - 再看合并之后 develop 上对应目录的改动
        ```bash
            git diff origin/develop..HEAD -- patient-service
        ```
    - 我会肉眼确认几个点：
        - B 线对缓存、批量查询、异常处理的改动是否都出现在合并后的 diff 里；
        - DTO 字段变化（比如 certNo/certType）的相关处理逻辑没有消失。

    - 用 git log -p 看关键方法的历史
        ```bash
            git log -p develop -- patient-service/.../PatientService.java
        ```
    - 关注：
        - 最后一次变更 getPatient 的 commit 信息是否合理；
        - 有没有“用旧版代码把新逻辑盖回去”的嫌疑。

3. 真的线上出问题，用 git bisect 兜底定位
    - 合并冲突之后，集成环境没发现问题；
    - 上线后某个复杂场景爆了（比如某些老患者查不出信息）。

    - 这时你可以用 git bisect 给自己加分：
        ```bash
            git bisect start
            git bisect bad <当前有问题的 commit，比如 develop HEAD>
            git bisect good <上线前最后一个稳定版本的 tag，比如 v1.2.5>
        ```

        - Git 会帮你二分跳 commit， 每次你只需要：
            - 构建 + 跑那组会复现bug的测试脚本：
                ```bash
                    ./run_regression_test.sh
                ```
            - 根据结果标记：
                ```bash
                    git bisect good   # 测试通过
                    git bisect bad    # 测试失败
                ```
        - 最终 Git 会告诉你“第一个引入问题的 commit”
            ```bash
                git bisect reset
            ```

### 2.4.5 总结
1. 场景背景：团队里两个大分支并行重构同一个患者模块，一个分支在做领域模型 / DTO 的重构，另一个分支在做挂号查询的性能优化（批量查询 + 缓存），结果先把重构分支合进 develop，再合优化分支时，在 PatientDTO、PatientService 这些核心类上直接炸了一片冲突。
2. 分析冲突来源时，我先用 git status 看哪些文件是 both modified，然后对关键文件用：
    ```bash
        git log --oneline --graph --decorate -- path 看这几行代码是分别在两个分支上被谁改过；
        git diff feature/refactor-patient..feature/optimize-registration -- path 确认一边主要是结构重构，一边主要是性能逻辑；
        git blame 辅助判断最近一次改动的意图。
    ```
    1. 总结下来就是：一边在改“形状”（DTO/Service 签名），一边在改“行为”（查询策略/缓存），这帮助我决定谁当“新地基”。

3. 解决冲突的时候，我的策略是：
    - 先以重构分支为基准接受新的领域模型和接口形状（相当于 --ours 为主），保证 DTO / Service 签名统一，然后再把优化分支上的行为改动（比如批量查询、缓存逻辑）按 git diff 的结果一点点迁移到新的结构上。在实际操作里，我一边用 IDE/三方 diff 对比 ours/theirs，一边用 git diff origin/develop..feature/optimize-registration 确认性能相关改动有没有被保留下来。

4. 为了避免引入回归，我做了三层防线：
    - 第一，在合并前后，对 PatientService / RegistrationService 补了一些关键单元测试和集成测试，用测试用例“锁住”挂号查询、患者信息查询这些核心行为；
    - 第二，合完冲突后，用 git diff origin/develop..HEAD 对比整块 patient 模块的改动范围，确认缓存、批量查询这些逻辑仍然存在，同时用 git log -p 看关键方法最近一次修改是否就是这次冲突解决的结果；
    - 第三，如果后续在测试环境或线上仍然发现细微回归，我会配合一个自动化回归脚本，用 git bisect 在合并前后的 commit 区间里二分查找，定位是具体哪一次提交引入了问题。

5. 整体来说，我不是“硬把冲突改到编译通过就算完”，而是先搞清楚两条分支各自的改动意图，用 log / diff / blame 把冲突拆成“结构 + 行为”两层处理，再用测试和 bisect 去兜底，保证这次复杂合并不会把之前修过的问题或者性能优化给悄悄弄丢。

# 3. 历史管理 & 提交规范

## 3.1 假设一个 feature 分支开发了两周，有 30 个 commit，其中很多是「修 typo」「修单测」之类，你希望合并到主干时只保留 3 个有意义的 commit。请写出你完整的操作命令和大致步骤，并说明这样做的好处和风险。

### 3.1.1 操作步骤
    
1. 切到 feature 分支，先跟主干对齐
```bash
# 1. 切到 feature 分支
git checkout feature/order-v2

# 2. 拉取远端最新 main
git fetch origin

# 3. 先基于最新 main 做一次 rebase（可选但推荐）
git rebase origin/main
# 这一步让你的 30 个提交排在最新 main 后面，后面好一锅端处理
```

2. 交互式 rebase，把 30 个拆成 3 组再 squash
    - 假设这两周一共 30 个 commit，最后想保留 3 个有意义的：
        - feat: 新增订单创建流程
        - feat: 新增订单支付与回调
        - refactor: 抽象订单领域模型与仓储
    ```bash
        git log --oneline -30
    ```
    - 对最近 30 个提交做交互式 rebase
        ```bash
            git rebase -i HEAD~30
        ```
    - 编辑器会打开类似这样的东西（从老到新）：
        ```bash
            git log --oneline -30
            pick a111111 feat: init order module
            pick b222222 feat: create order api
            pick c333333 fix: typo in OrderService
            pick d444444 test: add create order test
            pick e555555 fix: adjust create order log
        ```
    - 你要做的是，把这 30 行分类到三个“有意义的大提交”里，比如：
        - 跟「订单创建流程」相关的都 squah 到第一个 pick 里
        - 跟「支付与回调」相关的都 squash 到第二个 pick
        - 跟「领域模型/重构」相关的都 squash 到第三个 pick

        - 示例（只示意前几行）：
        ```bash
        # 第 1 组：订单创建
        pick a111111 feat: create order api
        squash c333333 fix: typo in OrderService
        squash d444444 test: add create order test
        squash e555555 fix: adjust create order log

        # 第 2 组：支付与回调
        pick f666666 feat: add payment callback
        squash g777777 fix: payment sign bug
        squash h888888 test: add payment callback test

        # 第 3 组：重构
        pick i999999 refactor: extract order domain
        squash j101010 fix: adjust domain model
        squash k111111 test: add domain unit tests
        ```
    - 有两点小技巧：
        - 临时的「修 typo」「修单测」建议用 fixup 而不是 squash：
            - fixup：自动丢掉这些小 commit 的 message，直接并入上一个 pick
            - squash：会让你编辑合并后的 commit message
            - 如果你想完全重写这 3 个最终 commit 的 message，把对应的 pick 改成 reword：
                ```bash
                    reword a111111 feat: create order api
                    fixup c333333 ...
                    fixup d444444 ...
                ```
    - 保存并退出编辑器后，Git 会开始重放这 30 个 commit 并按你的指令 squash。

    - 如果中间有冲突：
        - 按正常流程解决冲突
        - 编辑文件 -> git add 修改过的文件
        - git rebase --continue
        - 直到所有步骤完成

    - 完成后再看 log：
        ```bash
            git log --oneline
            # 你会看到刚才那 30 个小提交变成了 3 个大 commit

3. 本地验证 + 强制推送远端 feature 分支
    - 跑一遍测试，确保没玩脱
        ```bash
            mvn test
            # 或 ./gradlew test 之类
        ```
    - rebase 改了历史，推远端需要强制
        ```bash
            git push -f origin feature/order-v2
        ```
    - 这里的 -f 是关键：
        - 你把远端 feature/order-v2 的那 30 个原 commit 替换成了 3 个新 commit
        - hash 全变，所以必须强推
        - 前提是：这个分支只有你一个人用，或团队已经协调好“大家都要重新拉分支”的情况

    - 然后就可以用这个干净的分支提 PR → 合并到主干了。

### 3.1.2 这样做的好处
1. - 主干历史更干净，可读性更强
    - 不会在 main 上留下 fix typo、fix test、update 这种垃圾 commit；
    - 每个 commit 都是一个相对完整的业务单元，代码审查/历史回溯更友好。
2. 回滚 / 排查问题更容易
    - 如果将来发现“订单支付逻辑有问题”，你可以一眼看出是哪一个 commit 引入的，只需 git revert 那个大的 commit；
    - 而不是在 30 个碎 commit 里翻半天。
3. 配合 git bisect 更实用
    - 每个 commit 都相对自洽，git bisect 时不容易遇到“这个中间 commit 本来就是红的/测试没写完”的尴尬；
    - 减少「本来就不稳定的中间版本」对 bisect 的干扰。
4. 更符合“一个 commit = 一个可描述的改动”的工程习惯
    - 方便 code review，别人看到 commit message 就大致知道这一批改动的目的。

### 3.1.3 这样做的风险 & 注意点
1. 风险 1：改了已经“公开”的历史，搞崩别人
    - 如果这个 feature 分支已经被别人基于开发、或 CI/CD 已经用它做过构建：
        - 你 rebase + push -f 后，别人的本地 history 和远端完全对不上；
        - 别人必须强制 reset --hard 自己的分支，可能丢掉自己的本地修改；
        - CI 也会看到一堆新 commit（其实是老东西重写了一遍）重新跑流水线。
    - 规避方式：
        - 只对自己控制的分支这么干：
            - 没有别人基于它再拉分支；
            - 没有 tag/发布绑定这个分支上的具体 commit。
        - 或者在团队里事先打招呼：“我要 rebase 这个分支，大家别再基于当前版本开发，等我整理完再拉。”
2. 风险 2：Squash 搞错分组，导致逻辑混在一起 / 难以回滚
    - 比如把「订单创建」和「支付回调」混进一个 commit 里：
        - 将来只想回滚支付逻辑，会牵连订单创建部分；
        - git revert 不再是干净的“只撤这一块”。
    - 规避方式：
        - 在写 rebase -i 的那一大坨 pick/squash 时，对照 git log --oneline 和文件 diff，把 commit 按功能分组：
            - feat: create order 这一组
            - feat: payment callback 那一组
            - refactor: domain model 那一组
            - 最终控制在 2~5 个 commit，每个 commit 的范围足够聚焦。
3. 风险 3：rebase 过程中冲突很多，手抖搞错
    - 尤其是两周 30 个提交，rebase 可能重放很多次、冲突多：
    - 你可能在某一次 rebase --continue 时误操作，把某些改动丢了；
    - 规避方式：
        - 每轮 rebase 完成后，务必跑一遍测试：
            - mvn test
            - 或 ./gradlew test 之类
        - 对核心文件再看一眼 diff：
            - git diff origin/main..HEAD -- src/main/java/.../OrderService.java
            - 确认该有的逻辑都在。
        - 一旦搞砸，随时：
        ```bash
            git checkout feature/order-v2
            git reset --hard backup/feature-order-v2-before-rebase
        ```
### 3.1.4 可以对面试官说的总结话术
1. 先在 feature/order-v2 上 git fetch origin && git rebase origin/main，把自己的 30 个 commit 移到最新主干后面；
2. 然后用 git rebase -i HEAD~30 做交互式 rebase，把这 30 个 commit 分成 3 组，通过 pick/squash/fixup/reword 整理成 3 个有语义的提交，例如「订单创建流程」「支付与回调」「领域模型重构」；
3. 解决完冲突后跑一遍测试，确认行为没问题，再用 git push -f origin feature/order-v2 把这个干净历史推到远端，最后用这个分支提 PR 合并 main。
4. 这样做的好处是：主干历史非常干净，每个 commit 都是一个清晰的业务单元，将来回滚、审计、用 git bisect 排查问题都很方便。但我也会非常注意风险：
    - 这是在重写历史，只会对“没有别人依赖的 feature 分支”这样操作，绝不会对 main 或公共分支 rebase；
    - 在 rebase -i 时按功能分组，避免把不相关的改动 squash 在一起导致后续不好回滚；
    - rebase 前先打一个 backup 分支，rebase 后必须跑自动化测试，确认没引入行为回退。

# 4. 高级工具：worktree、submodule 等
## 4.1 你在同一个仓库里需要同时开发两个 feature（A/B），A 分支要跑一套环境，B 分支要跑另一套环境，经常切分支（git checkout）很痛苦。请设计一套基于 git worktree 的开发方式，说明如何创建、使用、清理附加工作树。

### 4.1.1 整体思路：一套仓库，多块“工作地”
假设当前目录结构：
project/           # 你现在的仓库目录（已有 .git）
需求：
	•	feature/A 跑一个环境（比如挂号新流程）
	•	feature/B 跑另一个环境（比如支付 refactor）
	•	希望两个项目目录都能 mvn spring-boot:run / docker-compose up，各自独立
目标结构：
project/           # 用来开发 feature/A
project-b/         # 同一个仓库的“第二块工作地”，用来开发 feature/B（通过 worktree 创建）
两个目录共用同一个 .git 仓库数据，但每个目录都有各自的工作区和分支。

### 4.1.2 创建 worktree：把 B 分支“长”到另一个目录里
1. 确保主仓库是干净的
    ```bash
        cd project
        git status
        # 确认没有未提交的修改 / 未 tracked 的大文件
    ```
2. 从当前仓库创建 feature 分支（A、B）
    ```bash
        # 基于 main 拉 A 分支
        git checkout main
        git pull origin main
        git checkout -b feature/A

        # 开发一点点也行，然后提交
        git commit -am "feat: init feature A"

        # 推到远端（可选，但推荐）
        git push -u origin feature/A

        # 回到 main，拉 B 分支
        git checkout main
        git checkout -b feature/B
        git commit -am "feat: init feature B"
        git push -u origin feature/B
    ```

3. 用 git worktree add 给 B 分支开一个新工作目录
    - 在 project/ 根目录执行：
    ```bash
        # 给 feature/B 开一个新的工作树目录
        git worktree add ../project-b feature/B
    ```
    - 解释一下这个命令：
        - ../project-b：新目录名（自己改也行，比如 project-feature-b/）
	- feature/B：这个工作树默认 checkout 的分支

    - 执行完之后，你会看到：
        ```bash
            project/       # 还是老目录，目前在 main 或 feature/A 上
            project-b/     # 新目录，里面是完整的代码，但 HEAD 在 feature/B 分支
        ```

### 4.1.3 使用方式：两个目录，两套环境，告别来回 checkout
1. A 功能开发在 project/
    ```bash
        cd project
        git checkout feature/A
        # 跑 A 的环境（比如 A 的 Spring profile）
        mvn spring-boot:run -Dspring.profiles.active=featureA
        # 或 docker-compose -f docker-compose.featureA.yml up
    ```
2. B 功能开发在 project-b/
    ```bash
        cd ../project-b
        # 这里已经是 feature/B 分支，worktree 自动 checkout 好了
        # 跑 B 的环境（用另一个端口 / profile）
        mvn spring-boot:run -Dspring.profiles.active=featureB
    ```

### 4.1.4 常用的 worktree 命令组合
1. 查看目前有哪些工作树
    ```bash
        git worktree list
    ```
    - 输出类似：
        ```bash
            /path/to/project      abcd1234 [feature/A]
            /path/to/project-b    efgh5678 [feature/B]
        ```
2. 在 B 的目录里正常开发、提交、push
    ```bash
        cd project-b

        # 编辑代码，写测试
        git status
        git add .
        git commit -m "feat: 完成 B 功能的支付回调逻辑"
        git push
    ```
    - 同样在 project/ 里：
    ```bash
        cd ../project
        git checkout feature/A
        git commit -am "feat: 完成 A 功能的挂号排队优化"
        git push
    ```
    - 注意一个限制：
        - 同一个分支不能同时在多个 worktree 里 checkout ——Git 会阻止。
        - 但你这里 A / B 是两个分支，所以没问题。

### 4.1.5 开发完之后：如何清理 worktree & 分支
假设你先把 B 分支的功能合并进 main 了。

1. B 分支合并 + 删除（正常 Git 流程）
    - 在任一工作树下（比如 project/）合并：
    ```bash
        cd project
        git checkout main
        git pull origin main
        git merge --no-ff feature/B
        git push origin main
    ```

2. 移除 B 的工作树目录
    - 在 project/ 下操作（一般用主仓库来管）：
    ```bash
        cd project
        git worktree list
        git worktree remove ../project-b
    ```
    - 解释一下这个命令：
        - git worktree list：看一下当前 worktree 列表
        - git worktree remove ../project-b：移除 B 的工作树
    - 这会做几件事：
        - 从 Git 的 worktree 管理中删除 project-b 条目；
        - 默认也会尝试删除 ../project-b 目录（如果目录干净）。
    - 如果系统提示目录不干净，可以加：
        ```bash
            git worktree remove --force ../project-b
        ```
    - 千万别自己手动 rm -rf project-b，那样 .git/worktrees 里还会残留记录，将来需要 git worktree prune 额外收拾。

3. 删除本地 B 分支（可选）
    ```bash
        git branch -d feature/B
    ```
    - 如果 Git 说没合并就 -D：
        ```bash
            git branch -D feature/B
        ```
4. 如果之前直接删过目录：用 prune 清理残留
    ```bash
        git worktree prune
    ```

### 4.1.6 这样用 worktree 的好处 & 小坑

1. 好处：
    - 真正并行两条分支环境
    - A/B 两个 feature 分支可以同时跑各自的 Spring Boot / Docker 环境
    - 不要再为 git checkout + mvn clean 折腾
    - 共享同一个 Git 仓库数据，更省空间
    - 跟重新 git clone 两份仓库相比，worktree 的 .git 数据是共享的
    - 大项目里节省磁盘 + 提升操作速度
    - 上下文隔离很好
    - 每个目录里只关心当前分支
    - IDE 可以分别打开 project 和 project-b，互不干扰，比如不同配置文件、不同 JVM 参数

2. 确定：
    - 别手动删 worktree 目录
        - 正确姿势：git worktree remove <path>
        - 实在删了，用 git worktree prune 收尾
    - 同一个分支只能在一个 worktree 里 checkout
        - Git 会阻止你在第二个 worktree 里 checkout 已在别处使用的分支
        - 解决办法：
            - 开新分支：git checkout -b feature/B-test origin/feature/B
            - 或者在原 worktree 换掉该分支
    - 记得在主仓库里操作 git 命令时，清楚自己当前在哪个 worktree
        - 避免在 A 目录里误操作到 B 的东西（反过来也是）

### 4.1.7 总结
1. 在需要同时开发两个 feature 且各自跑一套环境时，我会用 git worktree 来避免频繁 checkout。
2. 比如当前仓库目录是 project/，我会保留它用于 feature A，然后通过 git worktree add ../project-b feature/B 再创建一个 project-b/ 目录，绑定到 feature B 分支。这样我可以在 project/ 里跑 A 的环境，在 project-b/ 里跑 B 的环境，完全不需要来回切分支。
3. 平时开发、commit、push 在各自目录下像普通仓库一样操作；工作树列表可以通过 git worktree list 查看。等 B 功能合并进 main 后，我会在主仓库里执行 git worktree remove ../project-b 清理 B 的工作树，再删掉本地 B 分支，必要时用 git worktree prune 清理残留。
4. 相比重新 clone 多份仓库，worktree 的好处是共享同一个 .git 数据、磁盘占用小，而且能同时跑多套环境，极大减少来回 checkout 带来的编译/缓存损耗。