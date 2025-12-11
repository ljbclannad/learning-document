# MySQL场景题

[TOC]
[1. 需求建模、拆分维度](#1-需求建模拆分维度)
[2. 分库分表方案选型 & 落地（ShardingSphere / MyCat / 自研）](#2-分库分表方案选型--落地shardingsphere--mycat--自研)
[3. SQL & 路由错误场景类](#3-sql--路由错误场景类)
[4. 事务 & 一致性问题类（医疗场景特化）](#4-事务--一致性问题类医疗场景特化)
[5. 扩容 & 数据迁移类](#5-扩容--数据迁移类)
[6. 故障排查 & 性能优化类](#6-故障排查--性能优化类)
[7. 安全、合规 & 多租户（医共体 / 医联体）类](#7-安全合规--多租户医共体--医联体类)

# 1. 需求建模、拆分维度

## 1.1 一个省级医疗云平台，要承载多家三甲医院的挂号、门诊、住院、检查、收费等业务。

### 1.1.1 患者主数据按什么维度分？ID？证件号？区域？
患者主数据的核心维度选 patient_id，而不是证件号/区域
1. 为什么不用证件号 / 区域？
    - 证件号做分片键的问题：
        - 有境外患者、儿童、无证件人群，证件号并不完备。
        - 证件号将来可能要加密/脱敏，一旦加密之后，范围查询、前缀查询都废了，用来分片也不友好。
        - 政策变化（新证件类型、电子医保码等）会频繁扩展字段，不适合拿来当长期的技术维度。
    - 区域做分片键的问题：
        - 患者是“流动的”，今天在 A 市，明天搬去 B 市；按区域分片，会导致跨区域迁移时数据迁移和历史查询都很难看。
        - 医疗云从业务上更想强调“一人一档、全省通看”，如果按区域分片，某些“省级视图”查询就天然跨分片。

2. 我的做法：全省唯一的 patient_id 作为技术主键 + hash 分片
    - 给每个患者生成一个全省唯一的 patient_id（雪花算法/号段），这才是分片键：
        - 底层库：patient_db_00 ~ patient_db_15（举例 16 个库）
        - 路由：db = hash(patient_id) % 16
        - 表内必要时再进一步分表（按 hash 或按时间），但对外只有一个逻辑表 t_patient。
    - 证件号、手机号、医保号这些都是业务键，放到“索引表”里，而不是直接拿来当分片键：
        - 建一张或几张索引表，比如 t_patient_index：
            - id_type（身份证/护照/军官证…）
            - id_no（可以是加密后的）
            - phone
            - insurance_no
            - patient_id
            - db_index / shard_key（可选：告诉上层当前 patient_id 在哪个库）
            - 这样通过索引表就能快速从“身份证/手机号” → patient_id → 路由到对应分片。
    - 区域只是属性字段，不参与分片：
        - region_code、city_code 放在 patient_profile 里，主要为统计和标签使用。
        - 真正要做“按区域的大报表”，不在这套 OLTP 基础库搞，而是同步到数仓 / ES 再分析。

3. 总结：以全省唯一的 patient_id 作为技术主键和分片键，做 hash(patient_id) 分库分表；身份证/手机号/医保号只作为业务键，放在索引表中做查询 -> patient_id -> 路由到对应分片。

### 1.1.2 就诊记录（就诊号、挂号记录、门诊处方）又按什么维度分？

1. 先定库：医院 / 区域维度做“租户级”隔离
    - 在省级医疗云里，就诊类数据（挂号、门诊、住院、处方）有几个明显特征：
        - 事务强烈围绕“单医院”闭环：挂号 -> 排队 -> 叫号 -> 处方 -> 收费 -> 结算，绝大多数都是在同一家医院内部发生。
        - 单个医院内部 QPS 很高，比如省级三甲上午挂号 + 门诊暴涨，但医院之间的压力是相对可分割的。
    - 第一维度：先按 hospital_id（或 hospital_group_id）划分库：
        - 比如：visit_db_01：A 三甲 + 其下几个分院
        - visit_db_02：B 三甲 + 分院
        - 或者按城市/片区划分医院组，再映射到库，但最终是**“一批医院归一套库集群”**。
        - 好处：单医院内的关键事务（挂号 + 诊断 + 收费）尽量在同一个库集群内完成，分布式事务范围可控。
        - 一个医院炸了不会影响全省所有医院；数据量规模也可按医院数量线性扩容。

2. 再定表：在库里再按时间/visit_id 分表
    - 在单个医院/医院组的库里，挂号表 / 就诊表 / 处方表的数据量依旧很大，因此在表级再做分表。
        - t_registration_{yyyyMM}：按 挂号日期 月分表或天分表
            - 分片键：hospital_id + reg_date（路由到库）
            - 表内再按 reg_date 拆分（如 _202501, _202502）
            - 绝大多数业务查询都是“某日某医院挂号列表/某科室排队情况”，非常适配时间分表。
        - t_visit_{yyyyMM}（门诊就诊记录）
            - 同样按 hospital_id + visit_date 分片
            - 业务查询最常见的也是“今天某医生/科室的就诊列表”。
        - t_prescription_{yyyyMM}
            - 通常和 t_visit 表同步分片维度（hospital_id + visit_date），方便 join 或同库事务。

3. 为什么不用 patient_id 或 visit_id 做主分片键？
    - 如果用 patient_id 做分片键，就诊 / 处方 / 收费会按照患者散落在不同库，单次挂号到收费这条链路会频繁跨库，本来是单医院本地事务被搞成分布式事务，得不偿失。
    - 如果用 visit_id 纯 hash 分散，今天这个医院的所有就诊记录会被打散到一堆分片上，“某医院今日门诊列表”这种高频接口，会变成跨分片大查询。

4. 所以我的选择是：
    - 库层：医院维度（或医院组）→ 让一次就诊尽量落在一个库
    - 表层：时间维度分表 → 适配“当天/最近一段时间”的高频查询

### 1.1.3 当出现“同一个患者多院区就诊”时，如何保证查询某个患者的就诊全量历史，不至于跨几十个分片扫？

1. 在线查询（给医生看最近几次就诊）
    - 场景：医生开诊时，只关心“近 N 次就诊”，比如近 1 年。
    - 实现方式：
        - 先从就诊索引表/ES 查出该 patient 最近在哪些医院就诊、对应的 visit_id，
        - 然后按医院维度去对应的 visit 库拉明细（通常就 3～10 条记录）。
        - 这个查询是跨库的，但数据量很小，可以接受。

2. 全量历史（大屏、风控、科研）
    - 全量的“终身就诊史”我不会让在线 OLTP 库扛，而是：
        - 从门诊/住院/收费库通过 binlog / CDC 实时或准实时同步到大数据或 ES：
            - Hive / Iceberg / Hudi / ClickHouse / ES 等。
        - “省级大屏/风控/临床科研”走这条链路查。
    - 在架构上主动区分：
        - 交易库（事务、一致性、低延迟）
        - 分析库（全量、复杂聚合、高吞吐）

### 1.1.4 你如何衡量“按 patient_id 聚合查询”在真实生产中的占比？如果发现跨分片查询比例远高于预期，你会如何迭代分片策略，又如何保证迁移过程对业务无感？

#### 1.1.4.1 怎么衡量“按 patient_id 聚合查询”的真实占比？

1. 采集点：在“路由层”做埋点，而不是只看数据库
    - 在省级医疗云这种架构里，通常有：
    - API 网关 / BFF
    - 分库分表中间件（ShardingSphere / 自研数据访问层）
    - 各分片 DB

我会把采集重点放在分库分表层，因为它最清楚：
    - 这次请求的 SQL / ORM 方法
    - 使用了什么分片键（patient_id / hospital_id / date …）
    - 这条查询最终打了几个分片

每次查询打点信息大概包括：
    - api_name / biz_scenario（如：patientHistory, outpatientList）
    - sharding_key_type：PATIENT_ID / HOSPITAL_ID / DATE / MIXED / NONE
    - shards_touched：命中了多少个库 / 表
    - rows_returned：返回行数（粗略）
    - latency_ms：RT
    - is_cross_shard：shards_touched > 1

    - 这些日志统一打到 ELK / ClickHouse / Prometheus + Loki 之类的平台。

2. 几个关键指标
	1. 占比：patient_id 相关查询占所有查询的比例
        - 例如：所有查询 QPS：1w/s，sharding_key_type = PATIENT_ID 的查询 QPS：2k/s → 20%，如果只占 5%，其实不用命太大。
	2. 跨分片比例：patient_id 查询中，有多少是跨分片的
        - patient_qps：所有带 patient_id 条件的查询数量
        - patient_cross_shard_qps：其中命中分片数量 > 1 的
        - patient_cross_shard_p99_latency：patient_cross_shard_qps / patient_qspatient_cross_shard_p99_latency
	3. 业务维度：是哪些接口在疯狂按 patient_id 聚合？

#### 1.1.4.2 发现跨分片比例很高，怎么迭代分片策略？
    
1. 第一层：确认问题是不是“真的需要改分片”，而不是“接口设计问题”
    1. 有两种情况是可以不动分片规则的：
        - QPS 不高，只是偶尔慢
            - 比如 patient_id 跨分片查询占总 QPS 5%，但是都是医生点“患者历史就诊”时查 5~10 条记录，这种慢一点也没事。
            - 这时候更多是做缓存、索引优化，而不是重构分片。
        - 是几个特定接口搞的鬼
            - 比如某个“运营大屏”接口直接按 patient_id + 时间范围扫全省所有就诊记录，那它本来就应该走数仓/ES，而不是 OLTP 库。
            - 这种是接口错位，不是分片错。

    2. 如果确认：按 patient_id 聚合的查询 QPS 高，且主要是“刚需在线接口”（医生开诊、问诊前必须看到），那才进入第二层。

2. 第二层：加一层“患者维度的二级存储 / 索引”，而不是强行改所有分片
    1. 新建一个“患者时间线库”，比如：
        - 库分片：按 hash(patient_id) 分库分表
        - 表：t_patient_visit_timeline
        - patient_id
        - visit_id
        - hospital_id
        - visit_type（门诊/急诊/住院）
        - visit_date
        - brief_diagnosis

    2. 数据来源：
        - 通过 binlog / CDC（比如 Canal / Debezium）或业务侧双写：
        - 每产生一条门诊 / 住院记录，就往 timeline 库写一条摘要。
        - 医生查“患者全省就诊历史”时，就走这套 timeline 库，只命中按 patient_id 分片的一个库，避免全库 fan-out。

    3. 优点：
        - 现有 hospital_id 分片事务库不动；
        - 只对“患者维度查询”做定向优化；
        - 支持横向扩展，慢慢增长。

    4. 缺点：
        - 会多维护一条数据链路，需要数据一致性监控。

3. 第三层：若真的要改底层分片规则，怎么做在线迁移 + 无感切换？
    1. 定义新规则 & 建新库
        - 现有规则：按 region_code 分库。
        - 新规则：按 hash(patient_id) 分库。
        - 在新集群上创建一套同结构的 patient 分库分表。

    2. 升级业务代码，让它同时支持“旧规则 + 新规则”
        - DAO / 分片层同时知道：
            - 旧规则怎么路由
            - 新规则怎么路由
            - 给每条记录加一个“分片规则版本号 shard_version”，或者维护一张 patient_route 映射表。

    3. 全量迁移 + 增量同步（常见两种）
        1. 方案一：离线 + 增量回放
            - 先按批次把旧库数据导到新库（脚本 / 数据迁移工具）。
            - 从某个时间点开始，记录所有对 patient 的变更（binlog / 操作日志）。
            - 回放这些变更到新库，直到延迟收敛。

        2. 方案二：上线双写
            - 在某个版本之后，对 patient 的所有写操作：
                - 旧库写一次
                - 新库写一次
                - 并行跑一段时间，保证新库数据追平旧库。

    4. 灰度切换读流量（保证“无感”）
        1. 按接口灰度：
            - 比如先让“内部后台报表”读新库，观察一段时间；
            - 再逐步把“医生工作站/移动医生端/患者 APP”切到新库。
        2. 按医院灰度：
            - 比如先切 1 个试点医院的 patient 查询到新库，没问题再全省铺开。
        3. 双读校验：关键接口先读新库，再随机抽样读旧库比对结果（异步比对即可）。
        4. 监控：新库延迟/慢 SQL，数据差异数 / 校验失败率。
        5. 完成切换后，下线旧规则：当所有读写都已切到新库，并且数据校验 OK，一段观测期后：代码中去掉旧规则；旧库降级为备份，只对审计/追溯开放。
        6. 这个过程对业务来说是“不停机 + 不改接口”的，变化只发生在数据访问层和底层存储。

### 1.1.5 如果分片维度是 hospital_id，患者跨院就诊，做“患者画像 / 慢病随访”这种全局分析时，你会怎么设计全局索引 / 中央患者索引 CPI？是落 MySQL 还是 ES，如何保证一致性？

#### 1.1.5.1 先把问题翻译成架构目标 
1. 前提：
    - 所有就诊业务库（挂号/门诊/住院/处方）都按 hospital_id 分库分表。
    - 患者经常跨院就诊（省级平台很正常）。

2. 需求：
    - 做 “患者画像 / 慢病随访 / 全省就诊视图”：
    - 需要拿到这个患者在所有医院的就诊记录集合，
    - 并且能做各种条件过滤（时间、病种、用药、检查结果等）。

3. 解决方案：中央患者索引 CPI（Central Patient Index / EMPI），把“全省视角的 patient_id ↔ 各医院局部 patient_编号”打通。

#### 1.1.5.2 CPI / EMPI 怎么设计结构？
1. CPI 的角色定位
    - 把 CPI 定义成一个独立域，只干两件事：
        - 管理全省唯一的 global_patient_id（统一患者 ID）；
        - 维护“各种身份标识、各医院本地 patient_id ↔ global_patient_id”的映射。
    - 它本身不存所有就诊明细，而是存“索引 + 少量画像摘要”。

2. 核心几张表（示意）
    1. 患者主索引表：cpi_patient
    ```sql
        cpi_patient (
            global_patient_id      BIGINT PK,      -- 全省统一患者ID
            master_name            VARCHAR,        -- 当前主姓名
            master_id_type         VARCHAR,        -- 主证件类型
            master_id_no_hash      VARCHAR,        -- 主证件号（加密/Hash）
            gender                 CHAR(1),
            birthday               DATE,
            mobile_hash            VARCHAR,
            create_time,
            update_time,
            merge_version          INT             -- 合并/拆分用的版本号
        )
    ```
    2. 身份证/手机号等多标识映射：cpi_identifier
    ```sql
        cpi_identifier (
            id                     BIGINT PK,       -- 自增ID
            id_type                VARCHAR,        -- 身份证/医保号/手机号/电子健康卡…
            id_value_hash          VARCHAR,        -- 加密后的值
            global_patient_id      BIGINT,
            status                 TINYINT,        -- 正常/失效/已合并
            UNIQUE(id_type, id_value_hash)
        )
    ```
    3. 各医院本地 ID 映射：cpi_hosp_mapping
    ```sql
        cpi_hosp_mapping (
            id                     BIGINT PK,       -- 自增ID
            hospital_id            BIGINT,           -- 医院ID  
            local_patient_id       VARCHAR,        -- 医院本地 pat_id / mrn
            global_patient_id      BIGINT,         -- 全局患者ID
            first_visit_time       DATETIME,       -- 首次就诊时间
            last_visit_time        DATETIME,       -- 最后就诊时间
            visit_count            INT,            -- 就诊次数
            UNIQUE(hospital_id, local_patient_id)
        )
    ```

3. 慢病随访 / 患者画像时：
    - 第一步：先在 CPI 里确定这个人是谁（global_patient_id）。
    - 第二步：查出 TA 出现过的所有 (hospital_id, local_patient_id)。
    - 第三步：再去各个按 hospital_id 分片的就诊库/数仓里拉明细或聚合。

#### 1.1.5.3 CPI 落 MySQL 还是 ES？

1. CPI 的主库必须是 MySQL
    - CPI 是“谁是谁”的问题，典型需求是：
        - 唯一性约束（不能把两个不同的人合成一个 patient，也不能一个人 N 个 ID 乱飞）。
        - 合并/拆分：发现两个 global_patient_id 其实是同一人 → 需要合并。发现合并错了 → 需要拆分回滚。
        - 法规/审计要求：每次合并/拆分都要可追溯。
    - 这些都需要：事务；强一致；严格约束（UNIQUE / 外键）；binlog 做审计和 CDC。
    - 所以 MySQL（或 PG 一类）是天然选择，并且我会对 CPI 单独建一个高可用集群，按 hash(global_patient_id) 分库分表即可。

2. ES的作用
    - 搜索：
        - 患者可能信息不完整（只知道大概名字、手机号中间几位、住址模糊等）。
        - ES 支持模糊匹配、权重 scoring 等，适合做患者候选列表：比如：模糊查出 5 个候选，再由业务 / 人员干预确认是哪一个。
    - 画像检索/聚合：
        - 慢病管理需要按标签、特征筛选患者群体（如：糖尿病 + 最近一年没复诊 + 某些检验指标范围）。
        - 可以将 CPI + 少量就诊特征同步到 ES 索引里，做复杂组合查询。

#### 1.1.5.4 一致性怎么保证？（三个方向）

1. CPI 自己内部的一致性（MySQL 集群内部）
    - CPI 自己就是一套相对独立的分库分表 MySQL 集群，对外暴露 CPI Service / gRPC / HTTP API。
    - 外部系统不直接写 CPI MySQL，都走 CPI 应用服务，统一校验 & 事务：
    - 例如：“新患者建档”流程：
        - 先查 cpi_identifier 看是否已有该证件/手机号绑定的 global_patient_id。
        - 如果有，复用；如果没有，新建一条 cpi_patient + 若干 cpi_identifier 记录。
        - 整个过程在 CPI Service 内是一致性的本地事务。
    - 医院的 local_patient_id 与 global_patient_id 的绑定也是通过 CPI Service 做，避免“各医院自己乱写”。

2. CPI ↔ ES 的一致性（主从、最终一致）
    - CPI MySQL 开 binlog；
    - 使用 Canal / Debezium / 自研 CDC 组件订阅变更；
    - 转成事件流（Kafka / RocketMQ / RabbitMQ）；
    - 下游有一个 ES 索引刷新服务，消费这些事件，做：
        - upsert 到 ES；
        - 删除 / 合并时更新相关记录。

特点：
    - ES 只是读索引，允许秒级延迟（最终一致）；
    - CPI MySQL 和 ES 之间通过事件实现幂等更新（比如用 global_patient_id + version）；
    - 若 ES 索引更新失败，可通过重试队列和定时全量重建兜底。

3. CPI ↔ 各医院就诊库的一致性

    - 医院业务库按 hospital_id 分片；
    - CPI 是按 global_patient_id 分片；
    - 就诊数据在医院本地库产生，CPI 是一个“横向中心”。

    - 方案一：挂号/建档必须先经过 CPI（强耦合写）
    - 典型流程：
        - 患者到 A 医院挂号 / 建档；
        - HIS 调用 CPI Service：按身份证/手机/姓名模糊查候选；选择一个已有患者或创建新 global_patient；CPI 内部完成 cpi_patient / cpi_identifier / cpi_hosp_mapping 的写。
        - HIS 拿到 global_patient_id + local_patient_id，写本地挂号/就诊记录。
    - 这样：每条就诊在产生时，就已经绑定了 global_patient_id；就诊库和 CPI 在“ID 映射”上是强一致的（一次事务链路完成）。

    - 方案二：对存量医院或老系统，用事件/本地消息做最终一致
    - 有些老 HIS 系统没法每次改流程，这时就：
        - 医院本地先生成就诊 / 患者记录（写本地分片库）；
        - 在本地库写一条“患者建档/就诊事件”到本地消息表（outbox）；
        - 本地系统的消息转发程序（或 binlog CDC）把这些事件投递给 CPI：CPI 消费事件，识别患者 → 建立/更新 cpi_patient + cpi_hosp_mapping；生成 global_patient_id / 回写绑定关系（可异步或下次交互时回传）。
    - 这种方式是一种最终一致模式：短时间内可能存在“就诊记录已经写了，CPI 尚未建索引”的情况；但通过消息重试 + 夜间批量对账，可以保证最终不漏。

#### 1.1.5.5 总结

- CPI 里维护全省统一的 global_patient_id，以及所有身份证/手机号/医保号、各医院 local_patient_id 的映射关系；
- CPI 的主数据落在 MySQL 分库分表集群 上，保证身份唯一性、合并/拆分、审计等强一致需求；
- 同时用 ES 做一层搜索/画像索引，用于模糊查找和复杂筛选，但 ES 只是读索引，所有权威写入都经过 CPI MySQL；
- 一致性方面：
    - CPI 内部通过单库事务 + 唯一约束保证强一致；
    - CPI → ES 通过 binlog/CDC + MQ 异步同步，做到最终一致；
    - CPI ↔ 各医院就诊库，要么在挂号/建档链路中“强同步写 CPI”，要么通过本地消息表 + 事件驱动实现最终一致，并用对账/重放兜底。

### 1.1.6 SQL编写
CPI（中央患者索引）：按 global_patient_id 分库分表，负责**“这个人是谁、在哪些医院就诊过”**。
业务库（挂号/门诊/住院）：按 hospital_id + 日期 分库分表，负责**“这家医院里他干了啥”**。

#### 1.1.8.1 医生在“本院”看患者最近几次就诊记录
1. 先在 CPI 里拿本院的 local_patient_id

```sql
    SELECT local_patient_id
    FROM cpi_hosp_mapping
    WHERE hospital_id = ?
    AND global_patient_id = ?;
```
Java / MyBatis 接口示例：
```java
@Mapper
public interface CpiHospMappingMapper {
    @Select("""
        SELECT local_patient_id
        FROM cpi_hosp_mapping
        WHERE hospital_id = #{hospitalId}
          AND global_patient_id = #{globalPatientId}
        """)
    String findLocalPatientId(@Param("hospitalId") Long hospitalId,
                              @Param("globalPatientId") Long globalPatientId);
}
```

2. 再在本院的就诊库里查最近 N 次就诊，假设你按 hospital_id + visit_date 分库分表，当前月份是 t_visit_202512：

```sql
    SELECT v.*
    FROM t_visit_202512 v
    WHERE v.hospital_id = ?
    AND v.local_patient_id = ?
    AND v.visit_date >= ?
    ORDER BY v.visit_time DESC
    LIMIT 20;
```

```java
@Mapper
public interface VisitMapper {
    @Select("""
        SELECT *
        FROM t_visit_${tableSuffix}
        WHERE hospital_id = #{hospitalId}
          AND local_patient_id = #{localPatientId}
          AND visit_date >= #{startDate}
        ORDER BY visit_time DESC
        LIMIT #{limit}
        """)
    List<Visit> findRecentVisits(@Param("hospitalId") Long hospitalId,
                                 @Param("localPatientId") String localPatientId,
                                 @Param("startDate") LocalDate startDate,
                                 @Param("limit") int limit,
                                 @Param("tableSuffix") String tableSuffix);
}
```
业务 Service 伪代码：
```java
public List<Visit> getRecentVisits(Long hospitalId, Long globalPatientId) {
    String localPatientId = cpiHospMappingMapper.findLocalPatientId(hospitalId, globalPatientId);
    if (localPatientId == null) {
        return Collections.emptyList();
    }
    String tableSuffix = YearMonth.now().format(DateTimeFormatter.ofPattern("yyyyMM"));
    return visitMapper.findRecentVisits(
        hospitalId, localPatientId,
        LocalDate.now().minusMonths(6),
        20,
        tableSuffix
    );
}
```
注意点：
- SQL 里永远带 hospital_id，让分库中间件能只路由到一个库。
- 不在业务库里写类似 WHERE global_patient_id = ? 这种跨医院、跨分片的条件。

#### 1.1.8.2 做“全省就诊历史”：跨院，怎么查？

1. CPI 查出该患者在哪些医院有档案
```sql
    SELECT hospital_id, local_patient_id
    FROM cpi_hosp_mapping
    WHERE global_patient_id = ?;
``` 
```java
@Mapper
public interface CpiHospMappingMapper {
    @Select("""
        SELECT hospital_id, local_patient_id
        FROM cpi_hosp_mapping
        WHERE global_patient_id = #{globalPatientId}
        """)
    List<CpiHospMapping> findAllHospMappings(@Param("globalPatientId") Long globalPatientId);
}
```

2. 对这些医院逐个分片去查就诊信息（或者查 timeline 库 / ES）
    1. Java 层 for 循环按医院查
    ```sql
        SELECT v.*
        FROM t_visit_${tableSuffix} v
        WHERE v.hospital_id = ?
        AND v.local_patient_id = ?
        AND v.visit_date BETWEEN ? AND ?
        ORDER BY v.visit_date DESC;
    ```
    ```java
    public List<Visit> getAllVisits(Long globalPatientId, LocalDate start, LocalDate end) {
        List<CpiHospMapping> mappings = cpiHospMappingMapper.findAllHospMappings(globalPatientId);
        Map<Long, List<String>> byHospital = mappings.stream()
            .collect(Collectors.groupingBy(
                CpiHospMapping::getHospitalId,
                Collectors.mapping(CpiHospMapping::getLocalPatientId, Collectors.toList())
            ));

        List<Visit> all = new ArrayList<>();
        for (Map.Entry<Long, List<String>> entry : byHospital.entrySet()) {
            Long hospitalId = entry.getKey();
            List<String> localPatientIds = entry.getValue();
            String tableSuffix = calcTableSuffix(start, end); // 简化写法，实际可能按月拆多次

            List<Visit> visits = visitMapper.findVisitsByLocalIds(
                hospitalId, localPatientIds, start, end, tableSuffix
            );
            all.addAll(visits);
        }
        // 最后按时间排序
        all.sort(Comparator.comparing(Visit::getVisitDate).reversed());
        return all;
    }

    @Mapper
    public interface VisitMapper {
        @Select("""
            <script>
            SELECT *
            FROM t_visit_${tableSuffix}
            WHERE hospital_id = #{hospitalId}
            AND visit_date BETWEEN #{startDate} AND #{endDate}
            AND local_patient_id IN
            <foreach collection="localPatientIds" item="pid" open="(" separator="," close=")">
                #{pid}
            </foreach>
            ORDER BY visit_date DESC
            </script>
            """)
        List<Visit> findVisitsByLocalIds(@Param("hospitalId") Long hospitalId,
                                        @Param("localPatientIds") List<String> localPatientIds,
                                        @Param("startDate") LocalDate startDate,
                                        @Param("endDate") LocalDate endDate,
                                        @Param("tableSuffix") String tableSuffix);
    }
    ```
关键点：
- 每条 SQL 都有明确的 hospital_id，不会跨分片；
- Java 负责把多医院结果 merge。

## 1.2 医保结算对账库的拆分依据？

医保结算流水量巨大（门诊+住院+慢病报销），但又强依赖按医保局、按账期对账。

### 1.2.1 如果按 hospital_id + 账期 分库/分表，会带来哪些跨库查询问题？
我们假设现在分片策略是：
- 分库：db = hash(hospital_id)
- 分表：t_insurance_bill_YYYYMM（账期分表）
- 索引里都有：hospital_id, insure_org_code, settle_period 之类字段

#### 1.2.1.1 按“医保局 + 账期”查的时候，天然是“全库扫”

典型需求：某医保局要对 2025-11 账期内，所有定点医院的结算明细做对账。

业务 SQL 理想长这样（逻辑上）：
```sql
    SELECT *
    FROM t_insurance_bill
    WHERE insure_org_code = '440100'
    AND settle_period = '2025-11';
```
但你是按 hospital_id 分库的，而 insure_org_code 在分片维度之外，所以中间件是这么看的：
- 分片键：hospital_id？没有。
- 能路由到哪个库？不知道。
- 只能：广播到所有库所有表。

结果：所有库的 t_insurance_bill_202511 都要扫一遍；如果这个医保局管了全省大部分医院，这个查询就是“全库大表扫描”。

#### 1.2.1.2 按医保局做汇总统计，所有聚合都得“跨库汇总二次计算”

对账、稽核不会只看明细，还会看汇总：
```sql
SELECT insure_org_code, settle_period,
       COUNT(*) AS claim_cnt,
       SUM(med_fee) AS med_fee_sum,
       SUM(fund_pay) AS fund_pay_sum
FROM t_insurance_bill
WHERE settle_period = '2025-11'
GROUP BY insure_org_code, settle_period;
```
在单库时，这条 SQL 就是一个大 GROUP BY。
但现在：数据分散在 N 个 hospital_id 分库中；每个库都只能算出本库的 partial sum：
```sql
-- 每个分片
SELECT insure_org_code, settle_period,
       COUNT(*) AS claim_cnt,
       SUM(med_fee) AS med_fee_sum,
       SUM(fund_pay) AS fund_pay_sum
FROM t_insurance_bill_202511
GROUP BY insure_org_code, settle_period;
``` 
然后你需要在中间件 / 应用层做一个二次聚合：把所有分片的 (claim_cnt, med_fee_sum, fund_pay_sum) 再 GROUP BY 一次

结果：任何“按医保局 / 帐期 / 病种 / 统筹区”的聚合，都会变成多阶段聚合：分片上聚合一次 → 拉到中间层再聚合一次 → 再吐给报表/对账平台。一旦统计维度变多（医保局 + 医院等级 + 科室 + 疾病组…），跨库聚合代价会放大。

#### 1.2.1.3 医保局和医院之间不是 1:1，还会导致“逻辑割裂”

1. 现实情况经常是：一个医院可能挂多个医保局（城镇职工/城乡居民/异地/商保合作等）；一个医保局管多家医院，甚至跨区域。但你分库是按 hospital_id：同一医保局的结算，散在多个库里；同一医院不同医保局的结算，都在同一库里。从业务视角看：医保局侧想的是：“我这个基金池的钱去哪了？”你数据库侧的切片却是：“这家医院这个账期干了什么”。

2. 一旦维度从“医院视角”切换到“医保局视角”，所有查询都变成“跨医院聚合 → 跨库汇总”的模式，没有任何天然“命中单库”的场景。简单说：你的切片轴和他们的管理轴是错位的。

#### 1.2.1.4 医保稽核不会只有一个维度，它典型会这么玩：
查 2025-11 账期内，某医保局下所有医院中：人次异常多的医院、某些高值耗材使用异常、某些 DRG 组别的费用异常、以及这些患者的跨院就医、重复收费行为

这些查询一般长得又长又丑：
```sql
SELECT insure_org_code, hospital_id, drg_code,
       COUNT(DISTINCT patient_id) AS patient_cnt,
       SUM(fund_pay) AS fund_pay_sum
FROM t_insurance_bill
WHERE settle_period = '2025-11'
  AND insure_org_code = '440100'
  AND drg_code IN (...)
GROUP BY insure_org_code, hospital_id, drg_code;
```
问题：insure_org_code / drg_code 都不在你的分片键里；这种 SQL 无法命中单库，且聚合维度还要跨多个字段；如果还要 join DRG 规则表 / 医保目录表，很容易变成跨库 join + 跨库 group by → 中间件大多不支持，或者性能炸裂。

#### 1.2.1.5 异常修复 / 冲正时，定位粒度和分片粒度不匹配
实际运维里经常要做：指定某个“医保局 + 账期 + 批次号”的结算任务重算或冲正；或者修复某个医保策略变更前后的差额。
你从医保局侧拿到的信息往往是：insure_org_code、settle_period、batch_no 或 bill_no
但你分片是 hospital_id + 账期：除非你事先在每条记录上冗余 hospital_id + batch_no 并建立索引，不然定位某个“批次”的数据时，很难只触及有限几个分片。

#### 1.2.1.6 总结
1. 按医保局 + 账期对账时，insure_org_code 不在分片键上，所有查询本质都是跨分片：中间件只能广播到所有 hospital_id 分片，再在上层把结果聚合回来，分库越多，对账压力越大。
2. 各种统计 / 汇总 / 稽核查询（按医保局、统筹区、病种、基金等）都变成“多阶段聚合”：每个分片算一份 partial，应用层再二次汇总，灵活 ad hoc 查询非常吃力。
3. 医保局视角和医院视角不一致：医保局要看的是“一个基金池下所有医院”，但数据是按医院散在各个库里，任何“跨医院、多维度”的风控/稽核都不得不变成全库/多库扫描。
4. 在异常修复、冲正、重算某个医保局账期批次时，只能先全局检索哪些分片有这批数据，再打散跑脚本，维护成本很高。

### 1.2.2 会不会考虑“冷热分离 + 分库分表”混合？

#### 1.2.2.1 为什么一定要上“冷热分离 + 分库分表混合”？

1. 医保结算有两个完全不同的诉求：
    1. 在线交易 / 单院对账（OLTP）
        - QPS 高，实时性强，事务性要求高
        - 典型操作：某医院查今天的门诊结算记录、对某条结算流水做冲正/补记
        - 视角偏 hospital_id
	2.	医保局视角的全局对账 / 稽核 / 风控（OLAP-ish）
        - 维度多（医保局、统筹区、账期、DRG、医院等级、科室…）
        - 查询范围大（跨医院、跨账期）
        - 一次跑一大坨 SQL 或离线任务
        - 视角偏 insure_org_code + settle_period

#### 1.2.2.2 怎么混用“冷热分离 + 分库分表”？
1. 我会画三层：热库（在线交易）→ 温库（对账汇总） → 冷库（离线数仓/归档）。
2. 热库：按 hospital_id + 时间 分库分表（保持你现在的设计）
    1. 热库主要负责：挂号、结算、退费、冲正等在线交易；医院内部当天/近几天的对账、挂账、异常处理。
    2. 典型设计：分库：shard = hash(hospital_id)、分表：t_insurance_bill_YYYYMM 或按天、SQL 特点：都带 hospital_id，命中单库；账期只起“时间剪裁”作用，防止大表。
    3. 例如：SELECT * FROM t_insurance_bill_202512 WHERE hospital_id = ? AND settle_date BETWEEN ? AND ?; 这个库只解决“谁在某家医院某天/某账期结了什么算什么钱”。
3. 温库：为对账/医保局视角而建（可以改用医保局 + 账期分库）
    1. 对账/医保局的诉求是：
        - 按 insure_org_code + 账期 来看一堆医院的汇总/明细；
        - T+1 或 T+N 延迟是可以接受的。
    2. 所以我会建一套对账/清算库，它本身就是一个“聚合后的明细+汇总库”，分片维度可以完全不同：
        1. 分库：按 insure_org_code 分（一个医保局/统筹区一块库或一个分片组）
        2. 分表：按 settle_period（账期）或者 settle_date 分表
        3. 例如：db_insure_440100       -- 广州市医保局
            - └─ t_settle_detail_202511
            - └─ t_settle_detail_202512
            - db_insure_440300       -- 珠海市医保局
            - └─ t_settle_detail_202511
             - ...
        4. 数据从哪里来？从“热库”同步（binlog / CDC / ETL / 对账任务），在入温库的时候就已经按医保局+账期重新分片、清洗和归一。
    3. 在温库里，对账类查询就非常友好了：
        ```sql
        SELECT hospital_id, COUNT(*) AS bill_cnt, SUM(fund_pay) AS fund_sum
        FROM t_settle_detail_202512
        WHERE insure_org_code = '440100'
        GROUP BY hospital_id;
        ```

4. 冷库：长周期归档 / 数仓（按分析维度建模）
    1. 再往外一层，是真的冷数据 / 大数据平台：保存 5 年 / 10 年 / 15 年历史的医保结算；主要给：稽核、风控、科研、政策评估使用；通常用：Hudi / Iceberg / Hive / ClickHouse / ES 之类，再配上 Spark / Flink 来做批/流计算。
    2. 这里的分区/分片可以完全不拘泥于 OLTP：分区：insure_org_code、settle_year、settle_month、分桶：patient_id / fund_pool 等、并且可以建各种宽表 / 主题宽表（DRG 决策、费用结构分析等等）

#### 1.2.2.3 数据怎么在热/温/冷之间流转？（关键是“不推翻现有架构”）
1. 重点是不要把现有“按 hospital_id 分库的热库”推倒重建，而是：
    1. 热 → 温：明细同步 + 汇总重算
    2. 两种常见方式：
        1. 方式 A：CDC / Binlog 同步
            - 对在线结算库开启 binlog；
            - 用 Canal / Debezium 订阅 t_insurance_bill_* 变更；
            - 写一个同步服务，根据每条明细的：hospital_id、insure_org_code、settle_period等字段，将记录路由到对应的“对账库（insure_db）”，并做必要转换、清洗。
        2. 方式 B：对账任务 T+1 批量跑
            - 每天夜里 / 每个账期结束：从热库抽取增量（按时间戳或账期标记）；
            - 汇总成标准的“医保对账明细格式” → 入对账库；
            - 同时生成医院侧 / 医保局侧的汇总表，后续对账直接对比汇总表。
    3. 两种方式可以并存：
        - 常规需求用 T+1 批；
        - 风控/预警场景可以用 CDC 提供“接近实时”的流水。
2. 温 → 冷：周期归档 / 数仓 ETL
    - 每个账期结束后，把温库中的 t_settle_detail_YYYYMM 推送到大数据平台；
    - 按需转换成事实表 + 维度表（医院维、医保局维、患者维、DRG 维等）。
3. 关键：
    - 热库只保留近几个月 / 一年数据，其余归档到温/冷；
    - 热库压力可控；
    - 分片规则可以保持相对简单，专注在线服务。
#### 1.2.2.4 会不会牵扯一致性问题？怎么避免“账不对”？
1. 账目的“权威来源”要明确
    - 一般以“温库对账表 / 清算表”为最终结算依据；
    - 热库流水只是“原始明细来源”。
2. 热→温同步要可重放、可校验
    - 所有明细在温库有唯一幂等键（如 (hospital_id, bill_no)）；
    - 可以通过校验任务对比：热库明细总数 vs 温库明细总数；热库按维度的 sum vs 温库汇总表的 sum。
3. 对账过程中的状态机要清晰
    - 明细状态：INIT / SETTLED / ADJUSTED / REVERSED 等；
    - 每一步在热库、温库都有对应映射，避免“医院已冲正、对账库没冲正”这种鬼故事。
#### 1.2.2.5 一段“面试版总结”
在医保结算场景下，我会优先选择“冷热分离 + 分库分表混合”的方案：
    1. **热库（在线结算明细）**继续按 hospital_id + 时间 分库分表，保证医院内部交易和对账的高并发、低延迟、强事务；
    2. **温库（对账/清算库）**单独设计，通常按 insure_org_code + settle_period 分库分表，直接适配医保局按账期、按统筹区的对账需求，避免所有查询都变成跨医院跨库聚合；
    3. 冷库 / 数仓承接长周期历史数据，按分析维度重新建模（医保局、DRG、病种、患者等），承担稽核、风控、科研类大查询。

## 1.3 医技（检查/检验）报告场景下的拆分冲突？

医技报告（检验单/检查影像）天然是以就诊为主线，但查询报表又常常按科室、医生、时间、项目来聚合。

### 1.3.1 表结构中，你会选哪些字段作为分片键？
### 1.3.2 分片键选了 visit_id vs patient_id vs hospital_id + 检查日期，分别会导致什么具体问题？
### 1.3.3 对运营统计（比如：某个检验项目近半年各医院的量）会产生怎样的跨分片代价？如何预先设计避免“全库扫”？
### 1.3.4 对于“高频查询维度”和“主业务事务维度”不一致的情况，你会如何在写入路径上尽可能简单，同时在查询路径上用索引表/ES/缓存来补齐？给一个你认可的组合方案。
### 1.3.5 医技报告经常需要“按患者终身维度”拉全量结果，那么当分片按 hospital_id + 日期 时，你会不会考虑影像/报告落 ES 或对象存储 + 元数据表？如何保证查询性能和一致性？
### 1.3.6 遇到“历史系统没分库分表、你这套有分”，跨系统拉取报告时，如何设计一个统一的查询网关/聚合服务，屏蔽复杂度？
### 1.3.7 当运营突然提出一个新维度（例如：某检验项目+设备型号+批号），你如何评估是否“值得”为其新增索引表或物化视图，而不是直接怼在线库？

# 2. 分库分表方案选型 & 落地（ShardingSphere / MyCat / 自研）

## 2.1 如何解释引入分库分表中间件的“边界”？

公司准备在大型医疗系统中引入 ShardingSphere 作为分库分表中间件：

### 2.1.1 你会如何划定“哪些库/表接入 ShardingSphere，哪些保持单库单表”？
#### 2.1.1.1 先说一个总原则

1. 只有“写多 / 量大 / 增长快 / 单机扛不住”的核心业务表才进分库分表；
2. “小而稳 / 配置类 / 强依赖单点事务 / 报表分析”尽量保持单库或走专门分析库。

#### 2.1.1.2 哪些库/表“应该接入 ShardingSphere（做分库分表）”

这类是热数据 + 高并发 + 明显水平扩展诉求的：
1. 核心交易域（强业务闭环）
    - 门诊挂号：t_registration
    - 门诊就诊：t_visit_outpatient
    - 急诊/住院就诊：t_visit_inpatient
    - 收费 / 结算明细：t_charge_detail
    - 医保结算明细（在线那部分）：t_insurance_bill_online
    - 检查/检验申请单：t_exam_request, t_lab_request

2. 这些表有几个共同特点：
    - 单表数据量年增长非常快（3 年后 > 5,000 万甚至 1 亿行）；
    - 写多读多，RT 对医生/收费窗口敏感；
    - 明显存在“按医院 / 按日期 / 按账期”的自然分片维度。

3. 做法：
    - 这类表接入 ShardingSphere，并定义清晰的分片规则（如 hospital_id + 日期）；
    - 同域内强 join 的表一起接入，并配置为绑定表（bindingTable），减少跨分片 join。

#### 2.1.1.3 哪些库/表“接入 ShardingSphere，但保持单库/广播表角色”

1. 有一类是虽然接入中间件，但不做水平拆分，只是借 ShardingSphere 做：
    - 读写分离
    - 统一数据源管理
    - 广播表同步

2. 典型包括：
    - 主数据 / 字典类
    - 医疗机构：t_hospital
    - 科室：t_dept
    - 医护人员：t_doctor, t_nurse
    - 诊断/手术/药品/耗材字典：t_diag_dict, t_drug_dict, t_material_dict
    - 医保目录、结算规则：t_insure_catalog, t_insure_rule

3. 特点：
    - 数据量小（几千~几万条）；
    - 更新频率低；
    - 要在所有分片上“看起来一样”。

4. 做法：
    - 配置成 broadcastTable（广播表）：
    - 在每个数据源里都存一份；
    - 变更时由平台保证多库同步。
    - 这样 join 核心分片表时，不会产生跨库问题，又不用为这种小表搞独立连接。

5. 系统配置 / 权限 / 工作流
    - 用户、角色、权限：sys_user, sys_role, sys_permission
    - 系统配置：sys_config
    - 审批流程定义：wf_definition

6. 做法：
    - 也挂到 ShardingSphere，但配置为单数据源表（实际 dataSource 只有一个），
    - 方便业务侧用同一套数据源访问，不用区分“直连某个库”。

#### 2.1.1.4 哪些库/表“坚决不要挂 ShardingSphere（保持独立单库或走数仓）”

这是边界里更重要的部分：哪些坚决别接。

1. 报表 / OLAP / 医保稽核 / 风控大查询
    - 各种报表库：report_db
    - 医保局对账、稽核明细：insure_settle_detail_agg
    - 风控画像库：risk_patient_profile, risk_case
    - 数据仓库：Hive / ClickHouse / Hudi / Iceberg 那一堆

    1. 特点：
        - 查询维度多、聚合重、扫大范围历史数据；
        - 本质是 OLAP / 分析，不是 OLTP；
        - 分片维度和在线交易完全可以不一样（按医保局/账期/DRG/患者）。

    2. 做法：
        - 不用 ShardingSphere，走专用分析引擎（CH、Presto、SparkSQL 等）；
        - 通过 ETL/CDC 从在线库同步数据到这些分析库；
        - 真正的大报表、稽核都不要往在线分片库上怼。

2. 日志 / 审计流水 / 访问追踪
    - 操作审计表：audit_operation_log
    - 接口访问日志：api_access_log
    - 医疗行为审计：audit_medical_action（看规模）

    1. 如果量非常大，直接进 ES / 日志平台 / 大数据，而不是挂在 ShardingSphere 上硬撑。

3. 第三方系统库 / 中间件自带库
    - ES 索引存储、Redis 持久化、消息中间件自带表
    - 其他产品（LIS、PACS）的自有数据库

这些通常都是别人的系统的 schema，你用 ShardingSphere 去包一层，运维和排查都很难看。

#### 2.1.1.5 在“接入的库里面”，也不是所有表都要分片
1. 就算某个业务库接入了 ShardingSphere，我也会在表级别再做一次划分：
    - 大表 / 热表：挂分片策略；
    - 小表 / 配置表：配置为单表或广播表；
    - 中间表 / 临时表：视情况，很多时候保持单库即可。

2. 比如：“门诊业务库”里：
    - t_registration, t_visit, t_charge_detail → 分片表（按 hospital_id + 日期）
    - t_clinic_room, t_schedule_template → 单表（不分片）
    - t_doctor, t_dept → 广播表

3. 这样：
    - 大部分 join 都可以发生在单分片 + 广播表内，中间件非常好处理；
    - 只有那些天然“跨医院 / 跨患者”的查询才交给数仓/ES/风控侧路。

#### 2.1.1.6 回答
1. 接入并分库分表的，是挂号、就诊、收费、医保在线结算这种高并发、数据量爆炸、有明确分片维度的核心交易表；
2. 接入但不分片的，是字典、科室、医生、医保规则、配置等小而稳的表，我会配置成广播表或单表，让它们在各分片保持一致，同时统一数据源访问；
3. 绝不接入的，是报表/医保稽核/风控分析类库、日志审计库、数仓，这些天然属于 OLAP，会挂在专门的分析引擎上，通过 CDC/ETL 从在线分片库同步过去；
4. 在已经接入的业务库里，我也会按表粒度控制：只给大表挂分片策略，其它保持单表/广播表，通过绑定表等机制保证常见 join 都能在单分片内完成。

### 2.1.2 如何跟业务侧约定“不能做的 SQL”？举 3 条你认为在分库场景下要禁止或慎用的 SQL 写法。

#### 2.1.2.1 约定

1. 写成《分库分表 SQL 规范》，不是散落在聊天记录里
2. 哪些是“禁止”，哪些是“慎用”，哪些必须走数仓/报表库
3. 每条后面要写“为什么”，不然没人当回事
4. 在代码层做拦截
5. MyBatis Interceptor / JPA 自定义 wrapper + JSqlParser 解析 SQL
6. 匹配到“无分片键 / 跨分片 join / 不支持的子查询”直接打日志 + 拒绝上线 / 报警
7. CI 阶段做 SQL 审核
8. Mapper XML / 注解 SQL 走一次静态扫描
9. 不符合规范的 PR 直接打回
10. 预发集成环境接 ShardingSphere 真实例
11. 让大家在测试环境里就看到“广播 SQL”“路由失败”的真实报警，而不是线上才知道

#### 2.1.2.2 明确写进规范里的 3 条“禁止/慎用 SQL 写法”

1. 禁止：不带分片键的“大范围查询 / 更新 / 删除”
    ```sql
    -- 在门诊结算表上这么干，直接是全库扫
    SELECT *
    FROM t_charge_detail
    WHERE settle_date BETWEEN '2025-01-01' AND '2025-01-31';
    ```
    1. 在我们按 hospital_id 分库的医疗系统里：
        - 分片键是 hospital_id
        - 你只按 settle_date 查，ShardingSphere 根本不知道去哪一库
        - 结果就是：广播到所有分片执行，然后在中间层 merge
    2. 在分片表上，任何 SELECT/UPDATE/DELETE 必须显式带上分片键条件（例如门诊结算表必须带 hospital_id），否则视为非法 SQL。


2. 禁止 / 强制重构：跨分片 JOIN 两张大表（尤其是不同分片策略）
    1. 问题：
        - join 条件没用到分片键 hospital_id；
        - WHERE 里只有 insure_org_code / settle_period，也不是分片键；
        - 中间件没法把这俩表路由到同一分片，只能对两张逻辑大表在所有分片做笛卡尔 join（要么直接报不支持，要么性能爆炸）。

    2. 在分片表之间做 join，必须满足：
        - 要么两表是绑定表（同一分片策略、同一分片键）且 join on 分片键；
        - 要么将 join 上移到业务层 / 报表侧，不允许在 OLTP 分片库里跨分片 join 两张大表。

    3. 医疗场景正确姿势：
        ```sql
        -- 正确：先按 hospital_id 分片查处方列表
        SELECT *
        FROM t_prescription
        WHERE hospital_id = ?
        AND visit_date BETWEEN ? AND ?;
        -- 再按 hospital_id 在医保结算表查对应的结算信息
        SELECT *
        FROM t_insurance_bill
        WHERE hospital_id = ?
        AND visit_no IN ( ... );
        ```

3. 慎用 / 限制：会破坏路由的函数 / 表达式 / 子查询
    1. ShardingSphere 这种中间件的路由逻辑很依赖静态 SQL 解析，一些写法会让它看不懂分片键，从而退化成全路由。
    2. 典型坑 1：对分片键做函数/运算
        ```sql
        SELECT *
        FROM t_visit
        WHERE CAST(hospital_id AS CHAR) = '1001';

        SELECT *
        FROM t_visit
        WHERE hospital_id + 0 = ?;
        ```
    3. 我会要求：
        - 在 WHERE 中，分片键必须出现在简单等号条件里：hospital_id = ?、hospital_id IN (?,?,?)，禁止在分片键上套函数/运算/复杂表达式。
    4. 典型坑 2：子查询里藏着分片键，外层不带
        ```sql
        SELECT *
        FROM t_visit
        WHERE visit_id IN (
        SELECT visit_id
        FROM t_registration
        WHERE hospital_id = ?
            AND reg_date = ?
        );
        ```

#### 2.1.2.3 小结
1. 写一份《分库分表 SQL 规范》发到项目里，配合 MyBatis 拦截器 + CI SQL 扫描做强约束；
2. 其中我会明确标红至少 3 类写法：
    - 不带分片键的 SELECT/UPDATE/DELETE，在分片表上统一禁止，所有操作必须带上分片键如 hospital_id，否则就是全库扫或全库写；
    - 跨分片 join 两张大表的 SQL，尤其是 join 条件不含分片键的查询，一律要求拆成“分片内查 + 业务层聚合”，需要多维分析的走报表库/数仓；
    - 在分片键上套函数/运算/深层子查询，导致中间件无法正确识别路由条件的写法，一律认定为违规，要求改成简单等值/IN 条件，或拆成多步查询。
3. 在预发环境全量接入 ShardingSphere，配置广播/路由日志，把这类 SQL 尽早暴露出来，通过报警和 code review 形成团队共识。

### 2.1.3 对于“高频查询维度”和“主业务事务维度”不一致的情况，你会如何在写入路径上尽可能简单，同时在查询路径上用索引表/ES/缓存来补齐？给一个你认可的组合方案。

1. 主表分片只管写 + 索引表（患者/医生/科室时间线）+ ES + Redis 缓存。
2. 下面用一个具体场景串一下：医技报告（检查/检验）
    1. 主事务维度：hospital_id + visit_id + report_id（就诊内闭环）
    2. 高频查询维度：patient_id + 最近 N 次报告 / doctor_id + 时间范围 / 模糊搜索（项目、部位、关键字）

#### 2.1.3.1 写模型：主表尽量“傻”，不迎合所有查询
1. 主表设计（只按事务维度建）
    - 比如检查报告主表（分片表）：
    ```sql
    t_exam_report (
    report_id        BIGINT PK,        -- 全局唯一
    hospital_id      BIGINT,           -- 分片键1
    visit_id         BIGINT,
    patient_id       BIGINT,           -- 只是字段，不参与分片
    exam_type        VARCHAR,
    exam_time        DATETIME,
    dept_id          BIGINT,
    doctor_id        BIGINT,
    result_summary   TEXT,
    status           TINYINT,
    create_time      DATETIME,
    update_time      DATETIME
    )
    -- Sharding: db/table by hospital_id + exam_time (或 visit_date)
    ```

    - 原则：分片维度只考虑事务闭环：
        - 希望“同一次就诊的大部分写操作都在一个库里完成”，比如 hospital_id + exam_date。
        - 不去迎合 “patient 维度 / doctor 维度 / 模糊搜索”，不然分片规则会变成怪物。

2. 写入路径尽量只写“主表 + outbox 消息”
    - 写报告时的事务逻辑（伪代码）：
    ```java
    @Transactional
    public void saveExamReport(ExamReport report) {
        examReportMapper.insert(report);         // 写主表（分片）
        outboxEventMapper.insert(new OutboxEvent(
            "exam_report_created",
            report.getReportId(),
            buildPayload(report)  // 里面带 hospitalId / patientId / doctorId / examTime 等
        ));
    }
    ```
    - 一个本地事务里只做两件事：
        - 主表 insert + outbox 记账，写路径非常干净。
        - 不在这里直接写 ES、不在这里跨库搞一堆索引表写入。

#### 2.1.3.2 读模型：用“索引表 + ES + 缓存”补齐患者/医生维度查询
1. 患者维度索引表：Patient Timeline（关系型）
    - 新建一套按 patient_id 分片的“时间线库”，专门服务患者维度查询：
    ```sql
    t_patient_exam_timeline (
    id               BIGINT PK,
    patient_id       BIGINT,           -- 分片键
    report_id        BIGINT,           -- 指向主表
    hospital_id      BIGINT,
    exam_time        DATETIME,
    exam_type        VARCHAR,
    dept_id          BIGINT,
    doctor_id        BIGINT,
    brief_result     VARCHAR(256),     -- 简要结论，可冗余
    create_time      DATETIME
    )
    -- Sharding: db/table by hash(patient_id)
    ```
    - 消费刚才的 outbox：
    ```java
    public void handleExamReportCreated(OutboxEvent event) {
        ExamReportPayload p = parse(event.getPayload());
        timelineMapper.insert(
            new PatientExamTimeline(
                patientId = p.getPatientId(),
                reportId  = p.getReportId(),
                hospitalId= p.getHospitalId(),
                examTime  = p.getExamTime(),
                examType  = p.getExamType(),
                ...
            )
        );
    }
    ```
    - 这样带来的好处：
        - 患者维度的高频查询，都落到按 patient_id 分片的库上，和主表分片无关；
        - 写路径仍然只有“一条主流水 + 一条事件”，时间线只是一条异步读模型。

2. ES：做复杂筛选 / 模糊搜索 / 多维组合
    - 再加一层 ES 索引（按 report_id / patient_id 做 routing）：
    ```json
    // exam_report_index 文档示例
        {
        "report_id": 123,
        "patient_id": 888,
        "hospital_id": 1001,
        "exam_time": "2025-12-10T10:20:00",
        "exam_type": "CT",
        "body_part": "脑部",
        "keywords": "脑内出血 轻度 右侧额叶",
        "doctor_id": 567,
        "dept_id": 12
        }
    ```
    - 消费同一条 outbox 事件：
    ```java
    public void indexExamReportToEs(OutboxEvent event) {
    ExamReportPayload p = parse(event.getPayload());
    esClient.index("exam_report_index", buildEsDoc(p));
    }
    ```
    - 用它来支持：
        - 模糊查：关键字 / 部位 / 组合条件；
        - 复杂筛选：某时间范围+多个医院+某 exam_type。

    - 查询例子：
        - “查这个患者最近一年所有 CT 报告” → ES patient_id + exam_type + time range；
        - 只要少量字段就可以直接从 ES 返回，详细 report 再按 report_id 去主表补充。

3. Redis 缓存：短期热点（最近 N 次报告）
    - 对 UI 高频场景再加一层缓存，比如**“患者最近 5 次检查报告列表”**：
        - Key 设计：
        - key: patient:exam:recent:{patientId}
        - value: List<ReportSummary> (JSON), 按 exam_time 倒序
        - TTL: 1~6 小时

    - 更新策略：
        - 新报告产生时，异步消费事件后：
        - 更新 timeline 表；
        - 也顺带 LPUSH + LTRIM 或直接 SET 覆盖最近 N 条缓存。

    - 查询顺序：
        - 1. 从 Redis 拿 patient:exam:recent:{patientId} → 命中则直接用（对医生查最近几次很友好）；
        - 2. 未命中：
        - 去 t_patient_exam_timeline 查最近 N 条；
        - 回写缓存。

#### 2.1.3.3 查询路径示例：几类典型高频查询怎么走？
1. 医生在“本院”查患者最近 10 次检查报告
    - 维度：patient_id + 时间排序
    - 目标：低延迟、QPS 高、只关心这一个患者
    - 查询路径：
        - 1. Redis：
            - GET patient:exam:recent:{patientId}
            - 命中 → 直接返回（连 DB 都不用打）
            - 未命中则：
                - 走 patient timeline 库（按 patient_id 分片）
                - SELECT *
                - FROM t_patient_exam_timeline
                - WHERE patient_id = ?
                - ORDER BY exam_time DESC
                - LIMIT 10;

2. 运营/科研查：全省某类检查项目的分布情况（复杂过滤）
    - 维度：exam_type / body_part / 时间 / 医院 / 科室 / 年龄段…

    - 这种直接丢 ES：
    ```json
    // ES 查询伪代码
    {
    "query": {
        "bool": {
        "must": [
            { "term": { "exam_type": "CT" } },
            { "range": { "exam_time": { "gte": "2025-01-01", "lte": "2025-12-31" } } },
            { "terms": { "hospital_id": [1001, 1002, 1003] } }
        ]
        }
    },
    "aggs": {
        "by_hospital": { "terms": { "field": "hospital_id" } },
        "by_body_part": { "terms": { "field": "body_part" } }
    }
    }
    ```
    - 这类本来就是分析/统计需求，不让 OLTP 分片库背锅，ES / 数仓来搞。


3. 退一步：只靠索引表，不上 ES 可不可？也可以，只是你要知道 tradeoff：
    - 只用 MySQL timeline 索引表：
    - 写简单，技术栈少；
    - 但对“模糊查询/组合查询/模糊名字”等场景非常不友好，SQL 又长又容易慢。
    - 加 ES：
    - 栈变复杂，但是搜索体验、组合查询和聚合会舒服很多；
    - 数据一致性是“最终一致”，要接受秒级延迟。

4. 这一套的优点 / 代价
    - 优点：
        - 主逻辑事务只操作分片主表 + outbox，一条直线，RT 可控，失败补偿好做。
        - 每个库的分片规则都简单纯粹：
        - 主库按 hospital 维度；
        - timeline 库按 patient 维度；
        - ES 不管分片规则，只管搜索。
        - 查询按场景走最合适的存储：
        - 强事务 / 小范围 → 主表；
        - 单患者时间线 → timeline；
        - 全局搜索 / 聚合 → ES / 数仓。

    - 代价：
        - 多了一条数据同步链路，需要：
        - outbox / MQ / CDC；
        - 幂等控制（report_id 唯一）；
        - 延迟监控（timeline/ES 是否滞后过多）。
        - 读写模型变双向：
            - 写是“单写多播”，读要按场景选源，Java 侧要有一层访问策略封装（不要到处 if-else）。

#### 2.1.3.4 面试版总结一句话
1. 当“主业务事务维度”（比如医院/就诊）和“高频查询维度”（比如患者/医生/模糊检索）不一致时，我不会在一张表上硬凑所有维度，而是：
    - 写路径上保持单一分片主表 + outbox 记账，只按事务闭环的维度分片，保证写简单、事务可控；
    - 查询路径上增加一套按患者/医生分片的索引表（时间线库）+ ES 搜索索引 + Redis 热点缓存：
    - 患者最近 N 次查询 → timeline + Redis；
    - 模糊搜索/多维筛选 → ES；
    - 大统计 → 数仓/分析库。
    - 核心理念是：写模型保持纯粹，读模型多副本按查询维度优化，通过 outbox/MQ/CDC 异步补齐，接受秒级最终一致性，用监控和幂等保证这条链路稳定。
 
### 2.1.4 医技报告经常需要“按患者终身维度”拉全量结果，那么当分片按 hospital_id + 日期 时，你会不会考虑影像/报告落 ES 或对象存储 + 元数据表？如何保证查询性能和一致性？
#### 2.1.4.1 存储/索引整体布局：主库管事务，旁边拉一条“患者视角”的链路
1. 影像/大文件：PACS 或对象存储
    - 真正的大头是：DICOM 影像、PDF 报告、JPG/PNG 等。
    - 这些统一放到：PACS 系统（第三方/自研），或者S3/OSS/MinIO 这种对象存储
2. 在数据库里只存：
    - study_uid / series_uid / sop_uid
    - object_key（例如 OSS 路径）
    - thumbnail_key（缩略图 optional）
3. 主事务表：仍然按 hospital_id + 日期 分片（不动）
    - 比如 t_exam_report_main：
    ```sql
    t_exam_report_main (
    report_id      BIGINT PK,
    hospital_id    BIGINT,       -- 分片键
    visit_id       BIGINT,
    patient_id     BIGINT,       -- 字段，不分片
    exam_time      DATETIME,
    exam_type      VARCHAR(32),
    status         TINYINT,
    pacs_study_uid VARCHAR(64),
    object_key     VARCHAR(255), -- 影像/报告地址
    ...
    )
    -- Sharding: db/table by hospital_id + exam_date
    ```
    - 它做什么？
        - 写事务、审签、撤回、修改 → 都在这张分片表上完成；
    - 跟其它门诊/住院事务一样，只考虑医院视角 + 当期数据。
4. 患者时间线表：按 patient_id 分片的“终身索引”
    - 为了“终身维度查询”，我会单独搞一套**“患者影像时间线表”**：
    ```sql
    t_patient_exam_timeline (
    id             BIGINT PK,
    patient_id     BIGINT,       -- 分片键（hash 分库）
    report_id      BIGINT,       -- 指回主表
    hospital_id    BIGINT,
    exam_time      DATETIME,
    exam_type      VARCHAR(32),
    dept_id        BIGINT,
    doctor_id      BIGINT,
    summary        VARCHAR(256),
    object_key     VARCHAR(255), -- 用于快速预览/下载
    create_time    DATETIME
    )
    -- Sharding: db/table by hash(patient_id)
    ```
    - 这套库只负责“按 patient_id 拉时间线”；
    - 不参与复杂事务，只是一个同步的读模型。
5. ES：做全文搜索与复杂筛选
    - ES 上建一个影像/报告索引，比如 exam_report_idx：
    ```json
    {
    "report_id": 123,
    "patient_id": 888,
    "hospital_id": 1001,
    "exam_time": "2025-12-10T10:20:00",
    "exam_type": "CT",
    "body_part": "脑部",
    "keywords": "脑出血 右侧额叶 轻度",
    "object_key": "pacs://..."
    }
    ```
    - ES 主要用来：
        - 按关键词、部位、项目、医生、时间范围等复杂条件组合筛选；
        - 做聚合/统计（某患者某类检查分布、全省统计）。
    - 注意： ES 里也不存大 blob，只放元数据 + 文本。

#### 2.1.4.2 “按患者终身维度拉全量结果”时，查询路径怎么走？
关键是：千万别让这个查询直接扫 hospital_id+日期 分片表。
场景：医生/稽核/风控需要看“某患者终身的所有检查报告”
1. 常规“全量报告列表” → 走 patient timeline 表
    1. 直连时间线库（按 patient_id 分片）：
        ```sql
        SELECT *
        FROM t_patient_exam_timeline
        WHERE patient_id = ?
        ORDER BY exam_time DESC
        LIMIT ?, ?;   -- 分页
        ```
        - 只命中一组分片（hash(patient_id)）；
        - 拿到的是“所有报告的索引列表 + 元信息 + object_key”。

	2.	前端展示列表时，只用时间线里的 summary + 部分字段，
        - 需要查看详细报告时，再按 report_id 去主表拿详细结构化数据，按 object_key / study_uid 去 PACS/OSS 拉影像。
        - 这样终身维度查询的压力主要打在“patient timeline”库上，主库（按 hospital 分片）只是偶尔被点进某条明细。

2. 高级筛选/模糊搜索 → 走 ES，然后再回查时间线/主表
    - 比如：“查这个患者终身所有 CT + 包含‘出血’关键字的报告”：
    1. 先在 ES 查：
    ```json
    {
    "query": {
        "bool": {
        "must": [
            { "term": { "patient_id": 888 } },
            { "term": { "exam_type": "CT" } },
            { "match": { "keywords": "出血" } }
        ]
        }
    },
    "sort": [{ "exam_time": "desc" }],
    "from": 0,
    "size": 50
    }
    ```
	2.	ES 返回的是 report_id / object_key / exam_time 等列表；
	3.	如需准确结构化字段，再按 report_id 到：
        - t_patient_exam_timeline / t_exam_report_main 里补数据；
        - 或直接按 object_key 去 OSS/PACS 拉。
        - 性能要点：
            - timeline 库采用 hash(patient_id) 分库，扩容简单；
            - ES 用 routing = patient_id，避免一个患者的数据散落多个 shard；
            - 终身维度拉的是“列表 + 分页”，不是一次把几十年全装内存。

#### 2.1.4.3 一致性：主表 ↔ 时间线 ↔ ES ↔ 对象存储，怎么保证不乱？
分 3 层来说。
1. 谁是“真相源”？（单一事实来源）
    - 我会明确：
        - 单一事实来源：t_exam_report_main（分片主表） + 对象存储/PACS
        - 主表里存在且状态是有效，代表这份报告是“官方版”；
        - 对象存储中存在对应 object_key 的文件。
        - 时间线表 + ES 都是读模型/索引副本，可以重建，可以修。

2. 主表 → 时间线 & ES：用 Outbox/MQ + 幂等
    1. 写主表时：
        ```java
        @Transactional
        public void createReport(Report r) {
            examReportMainMapper.insert(r);
            outboxMapper.insert(new OutboxEvent(
                eventType = "exam_report_created",
                bizKey = r.getReportId().toString(),
                payload = json(r)
            ));
        }
        ```
    2. 异步消费者：
        ```java
        // 消费 outbox → MQ → timeline / ES
        public void onExamReportCreated(ExamReportPayload p) {
            // 1. 写 timeline（按 patient_id 分片）
            patientTimelineMapper.upsertByReportId(p); // 用 report_id 做唯一约束，幂等
            // 2. 写 ES 索引（upsert）
            esClient.index("exam_report_idx", p.getReportId(), buildEsDoc(p));
        }
        ```

    3. 要点：
        - 幂等键：report_id（timeline 表里建唯一索引，ES 用相同 id）；
        - 消费失败可重试 / 进死信队列（DLQ）；
        - 延迟通过监控：
        - 比如：主表写入数 vs timeline/ES 写入数状态对比。

    4. 更新场景（修改报告、撤回、删除）：
        - 主表里 status 切换、summary 变化；
        - 写一条 exam_report_updated 事件；
        - timeline & ES 中根据 report_id 改状态/内容；
        - 删除一般用软删除（加 is_deleted 标记），ES 里打 tombstone，图片可延迟清理。

3. 主表 ↔ 对象存储：如何避免“有元数据没文件”/“有文件没元数据”
    1. 常见策略：
        1. 上传顺序：
            - 先传对象存储，拿到 object_key；
            - 再写主表 + outbox；
            - 所以“有元数据但没文件”的概率较小（只有对象存储极端故障）。
        2. 定期对账任务： 
            - 从 t_exam_report_main 拉最近 N 天的记录，对照 OSS/PACS 看文件是否存在：
            - 没文件 → 报警 + 人工/自动补传；
            - 从 OSS/PACS 列目录，对比 DB，看是否有“孤儿文件”，按策略清理。

#### 2.1.4.4 总结

1. 影像/报告本体放 PACS 或对象存储，主库只存 report_id + object_key + study_uid 等元数据；
2. 主表 t_exam_report_main 仍按 hospital_id + exam_date 分库分表，专注于单院事务；
3. 旁路建设一套按 patient_id 分片的 t_patient_exam_timeline 作为“患者终身时间线索引”，另建 ES 索引用于模糊搜索和复杂筛选；
4. 写入路径保持简单：上传影像 → 写主表 + outbox 事件，
异步消费者基于事件去更新 timeline 和 ES，report_id 作为幂等键；
5. “按患者终身拉全量结果”时，查询只打 timeline 库（按 patient_id 命中一个分片）+ 分页，必要时再按 report_id / object_key 去主库/PACS 补充明细，复杂条件则走 ES；
6. 一致性通过 outbox/MQ/CDC + 幂等 + 定期对账（主表 vs timeline vs ES vs 对象存储）来保证，接受秒级最终一致，但确保最终不丢、不乱、可修。



## 2.2 路由策略设计题
挂号表 t_registration 已经按 hospital_id + registration_date 水平拆分到 16 个分片。

### 2.2.1 如何设计 ShardingSphere 的分片算法，既能支持按医院+日期查询，又能支持按 registration_id 精确查询？

1.	先把 registration_id 设计成“带分片信息的 ID”（不然中间件看到它也不知道去哪片）
2.	在 ShardingSphere 里用 ComplexKeysShardingAlgorithm 自定义一个“多钥匙分片算法”，
    - 有 registration_id 就用 ID 解出分片
    - 没 ID 但有 hospital_id + registration_date 就用这俩算分片
    - 都没有就广播 / 报警

#### 2.2.1.1 第一步：先把 registration_id 搞成“可反推分片”的 ID
1. 你现在的物理拆分是：
    - 按 hospital_id + registration_date → 16 个分片
    - 那么插入时你肯定已经用某个函数算过 shardIndex，例如：
    ```java
    shardIndex = (hash(hospital_id) + hash(registration_date)) % 16
    ```
2. 要让 registration_id 能精确路由，必须让它携带这个 shardIndex。
    - 最简单粗暴的做法：
        - 让 registration_id 的低 4 bit = shardIndex（因为 2^4 = 16）
        - 比如一个 64 位的雪花 ID 大致结构：
        ```java
        [ 1bit 符号 ][ 41bit 时间戳 ][ 10bit 业务/机房/机器 ][ 9bit 自增序列 ][ 3~4bit shardIndex ]
        ```
    - 或者更明确一点（伪代码）：
        ```java
        long generateRegistrationId(Long hospitalId, LocalDate regDate) {
            int shardIndex = computeShardIndex(hospitalId, regDate); // 0..15
            long timestampPart = ...;
            long workerPart = ...;
            long seqPart = ...;
            return (timestampPart << 22) | (workerPart << 12) | (seqPart << 4) | shardIndex;
            }
        ```
    - 这样就做到：
        - 插入时：用 hospital_id + registration_date 算 shardIndex
        - 用同一个 shardIndex 写入 t_registration_${shardIndex}
        - 精确查询时（只有 registration_id）：从 registration_id 解出 shardIndex
        - ShardingSphere 直接路由到那一个真实表

#### 2.2.1.2 第二步：在 ShardingSphere 里写一个 “多 key 分片算法”
1. ShardingSphere 提供了 ComplexKeysShardingAlgorithm，能同时看到多个列的值。
我们可以声明这个表的分片列为：hospital_id, registration_date, registration_id
2. 然后写一个算法：
    - 如果 SQL 里有 registration_id：直接按 ID 解出 shardIndex。
    - 否则，如果有 hospital_id + registration_date：走你原来的 hash 规则算 shardIndex。
    - 否则：返回所有分片（广播）或者直接报不支持。

3. YAML 配置示意
    ```yaml
    假设 1 个逻辑库，16 张表：
    tables:
    t_registration:
        actualDataNodes: ds_0.t_registration_$->{0..15}
        tableStrategy:
        complex:
            shardingColumns: hospital_id,registration_date,registration_id
            shardingAlgorithmName: reg_complex_tbl_alg

    shardingAlgorithms:
    reg_complex_tbl_alg:
        type: COMPLEX
        props:
        algorithmClassName: com.xxx.sharding.RegistrationComplexShardingAlgorithm
    ```
    - 这里用的是 “Complex” 策略，而不是 standard，因为要根据多个列动态选择分片逻辑。

4. 分片算法伪代码（Java）
    ```java
    public class RegistrationComplexShardingAlgorithm 
            implements ComplexKeysShardingAlgorithm<Long> {

        @Override
        public Collection<String> doSharding(Collection<String> availableTargetNames,
                                            ComplexKeysShardingValue<Long> shardingValue) {
            Map<String, Collection<Long>> columnValuesMap = shardingValue.getColumnNameAndShardingValuesMap();

            Collection<Long> regIds = columnValuesMap.get("registration_id");
            if (regIds != null && !regIds.isEmpty()) {
                // 场景1：按 registration_id 精确/IN 查询
                return routeByRegistrationId(availableTargetNames, regIds);
            }

            Collection<Long> hospitalIds = columnValuesMap.get("hospital_id");
            Collection<Object> regDates = shardingValue.getColumnNameAndRangeValuesMap()
                                                    .get("registration_date"); 
            // 或从 columnValuesMap 里拿 Range，同理处理

            if (hospitalIds != null && !hospitalIds.isEmpty() && regDates != null && !regDates.isEmpty()) {
                // 场景2：按 hospital_id + registration_date 查询
                return routeByHospitalAndDate(availableTargetNames, hospitalIds, regDates);
            }

            // 场景3：没带分片键，视为广播或抛异常（看你团队规范）
            // return availableTargetNames; // 广播
            throw new UnsupportedOperationException("Sharding key is required");
        }

        private Collection<String> routeByRegistrationId(Collection<String> availableTargetNames, 
                                                        Collection<Long> regIds) {
            Set<String> result = new HashSet<>();
            for (Long regId : regIds) {
                int shardIndex = extractShardIndex(regId);  // 从ID低4位取
                String actualTable = "t_registration_" + shardIndex;
                if (availableTargetNames.contains(actualTable)) {
                    result.add(actualTable);
                }
            }
            return result;
        }

        private Collection<String> routeByHospitalAndDate(Collection<String> availableTargetNames,
                                                        Collection<Long> hospitalIds,
                                                        Collection<Object> regDates) {
            Set<String> result = new HashSet<>();
            for (Long hospitalId : hospitalIds) {
                for (Object dateObj : regDates) {
                    LocalDate regDate = toLocalDate(dateObj);
                    int shardIndex = computeShardIndex(hospitalId, regDate); // 与插入时一致
                    String actualTable = "t_registration_" + shardIndex;
                    if (availableTargetNames.contains(actualTable)) {
                        result.add(actualTable);
                    }
                }
            }
            return result;
        }

        private int extractShardIndex(Long regId) {
            return (int)(regId & 0x0F); // 低4bit
        }

        private int computeShardIndex(Long hospitalId, LocalDate regDate) {
            int hash1 = hospitalId.hashCode();
            int hash2 = regDate.toString().hashCode(); // 或 yyyyMMdd
            return (hash1 ^ hash2) & 0x0F;             // 0..15
        }
    }
    ```

5. 关键点：
    - 分片算法里两处用到 shardIndex：
    - computeShardIndex(hospitalId, regDate) → 插入时用的规则；
    - extractShardIndex(regId) → 从 ID 中解出的分片号；
    - 这两个必须完全一致，否则插入/查询的分片对不上。

#### 2.2.1.3 实际 SQL 场景下怎么路由？

1. 按医院+日期查今日挂号列表（最常见）
    ```sql
    SELECT *
    FROM t_registration
    WHERE hospital_id = 1001
    AND registration_date = '2025-12-11'
    ORDER BY create_time DESC
    LIMIT 100;
    ```
    - ShardingSphere 看到 hospital_id + registration_date → 调用 routeByHospitalAndDate；
    - 算出 shardIndex = N → 命中 t_registration_N；
    - 路由只到 1 个分片。

2. 按 registration_id 精确查一条记录
    ```sql
        SELECT *
        FROM t_registration
        WHERE registration_id = 987654321012345678;
    ```
    - 算 shardIndex = regId & 0x0F；
    - 直接命中 t_registration_${shardIndex} 单表；
    - 不需要扫 16 片。

3. 支持 IN 也一样：最多命中若干个分片，不会全路由。
    ```sql
        SELECT *
        FROM t_registration
        WHERE registration_id IN (987654321012345678, 123456789012345678);
    ```
    - 算 shardIndex = regId & 0x0F；
    - 直接命中 t_registration_${shardIndex} 单表；
    - 不需要扫 16 片。
4. 极端情况：只带医院、不带日期（比如历史统计）
    ```sql  
    SELECT *
    FROM t_registration
    WHERE hospital_id = 1001;
    ```
    - 你算法里 hospital + date 两个条件至少缺一个，就会走 fallback：
    - 要么全路由（性能差），
    - 要么直接抛异常（推荐，让开发知道这是非法 SQL）。

#### 2.2.1.4 小结
1. 这个场景下我会这样设计 ShardingSphere 的分片方案：
    - 物理上，t_registration 已经按 hospital_id + registration_date 拆成 16 个分片；
    - ID 设计上，让 registration_id 携带分片号，比如用雪花 ID 的低 4 bit 存 shardIndex，shardIndex 的计算规则与 hospital_id + registration_date 的分片函数一致；
    - ShardingSphere 里，为 t_registration 配一个 ComplexKeysShardingAlgorithm，分片列声明为 hospital_id, registration_date, registration_id：
        - 如果 SQL 带 registration_id，直接从 ID 解出 shardIndex 定位分片；
        - 如果 SQL 带 hospital_id + registration_date，用这两个字段计算 shardIndex；
        - 如果两种分片键都不带，则视为非法 SQL 或广播执行，由规范禁止。

### 2.2.2 当未来要从 16 分片扩容到 32 分片时，这套路由算法如何提前设计避免大规模数据迁移？
1. 已有的 t_registration 已经按 hospital_id + registration_date 拆成 16 片，而且 registration_id 低 4 bit = shardIndex，这种场景从 16 扩到 32，我不会暴力把老数据全部重新分片迁移，而是：
    - 做一套“分片规则版本化”的设计：
        - 保留 V1：旧规则只使用 0..15 片，所有历史数据继续按原分片落在 16 片上，不动；
        - 新增 V2：在 registration_id 中预留版本位和 5bit shardIndex，新数据按 32 片规则分布到 0..31；
        - 在 ShardingSphere 里写 ComplexKeysShardingAlgorithm：
        - 按 registration_id 时，先解析 version+shardIndex 决定去哪个物理分片；
        - 按 hospital_id + registration_date 时，根据日期是否跨过切换时间点 T 来选择使用 V1 还是 V2 规则，必要时命中两套分片。

2. 这样做的结果是：
    - 既无需对历史数据做大规模迁移，又能让新增数据利用 32 片的扩展能力；
    - 唯一的成本是：跨 T 的范围查询可能会命中两个分片集合，但这个局部开销远小于重分全库。
    - 如果是从零设计，我则会直接用“slot + 映射表”的方案，把可扩容能力埋进 ID 设计和分片算法里，后续 16→32→64 都只是调整映射的运维动作。

### 2.2.3 如果已有历史数据是按 hash(registration_id) % 16 路由的，现在要改为 hash(patient_id)，你会怎么做迁移方案？
1. 总体策略：新老集群并存 + 双写 + 全量回放 + 校验 + 灰度切换
	1.	新建一套“按 patient_id 分片”的影子集群
        •	表结构与旧集群一致；
        •	ShardingSphere 配置改为 shardingColumn = patient_id，路由规则走 hash(patient_id) % 16；
        •	先不对外，只作为迁移目标。
	2.	业务升级一版：引入“分片规则双栈”和本地消息 / outbox
        - 写挂号时，事务里多写一条 outbox 事件（包含 registration_id + patient_id + 全量字段）；
        - 先只写旧集群，读也只读旧集群，新集群暂时还没启用。
	3.	全量历史数据离线回放到新集群
        - 从旧集群 16 分片依次扫表（按主键/时间分批），对每行：
        - 取出 patient_id，按 hash(patient_id)%16 路由，写入新集群；
        - 用 registration_id 做幂等键（唯一约束），支持重跑；
        - 这是纯离线任务，可按医院/时间窗口分批，控制对线上影响。
	4.	开启“增量双写”（旧集群 = 真事实，新集群 = 跟随）
        - 上线第二版业务：
        - 写挂号时：同时写旧集群 + 新集群（或消费 outbox 异步写新集群）；
        - 失败策略：旧库写失败 = 业务失败；新库写失败重试/告警，但不影响主链路；
        - 保证从这一刻起，新集群不再丢任何新增/更新的数据。
	5.	数据校验：对齐新旧两套集群
        - 维度：行数、聚合值（按 hospital_id / 日期 / patient_id）、抽样 row 校验；
        - 工具：离线比对脚本 / 校验服务；
        - 如果发现差异：要么补跑对应分片，要么按 registration_id 做单条纠错。
	6.	灰度切换读流量（先部分接口 / 部分医院）
        - 第三版业务：
        - 对“按 patient_id 查询挂号历史”的接口，优先读新集群；
        - “按 registration_id 精确查”的，可以：
        - 短期仍从旧集群读；
        - 或增加一张 reg_id → patient_id 的映射表，用 patient_id 路由到新集群。
        - 可以按“医院维度”灰度：先切一两家试点医院，观察 RT 和错误率。
	7.	全量切读到新集群，旧集群只读不写
        - 当：
        - 双写稳定一段时间；
        - 校验通过；
        - 将业务切为：
        - 所有挂号读写都走“按 patient_id 分片”的新集群；
        - 旧集群标记为只读，用于回溯/审计一段时间。
	8.	下线双写，退役旧集群
        - 一段观察期后：
        - 去掉双写逻辑，只保留新集群写；
        - 将旧集群彻底下线或归档。

2. 总结
    - hash(registration_id) → hash(patient_id) 本质是重分片，不能在原集群原地魔改。
    - 我会新建一套“按 patient_id 分片”的影子集群，先用离线任务把历史数据全量回放过去，再通过业务层的 outbox 双写保证增量同步；
    - 在新旧集群数据校验一致后，按接口/按医院灰度把读流量切到新集群，最终停止写旧集群并退役。
    - 整个过程依赖：影子集群 + outbox/MQ + 幂等回放 + 双写 + 灰度切换 + 数据校验，而不是一次性暴力重分片。

### 2.2.4 对于“按 registration_id 精确路由”和“按 hospital_id + date 范围查询”两种模式并存，是否会考虑复合分片键或标准分片键 + 辅助路由表？具体怎么设计？

#### 2.2.4.1 复合分片键（推荐）：一个算法同时支持两种路由

1. 思路：
    - ShardingSphere 配置：shardingColumns = registration_id,hospital_id,registration_date（ComplexKeysShardingAlgorithm）。
    - ID 设计：registration_id 里带 slotIndex（或 shardIndex）。

2. 路由规则：
	1.	SQL 有 registration_id
        - → 从 ID 解出 slotIndex → 直接路由到 t_registration_${slotIndex}。
	2.	否则，SQL 有 hospital_id + registration_date
        - → 用同一套 hash(hospital_id, date) 算出 slotIndex → 路由到单分片。
    3. 都没有 → 视为非法/广播，规范上禁止。

3. 好处：不用路由表，不多一次查询，业务只管三列，算法里做优先级判断。

#### 2.2.4.2 标准分片键 = registration_id + 辅助路由表（多用于历史/迁移场景）

1. 思路：
    - ShardingSphere 标准分片列只认 registration_id，真正分片靠 ID 中的 slotIndex。
    - 额外建一张小表：t_registration_route(registration_id, hospital_id, registration_date, slot_index)。

2. 使用方式：
    - 写入时：同事务写主表 + route 表（或用 outbox 异步补齐），保证一一对应。
    - 查询时：
        - 精确查：直接 WHERE registration_id = ? → 用 ID 路由。
        - 按 hospital_id + date 拉列表：
        - 先查 t_registration_route 按医院+日期得到 registration_id 列表（它可以按 hospital_id 分片），
        - 再按 ID 批量去主表查详情。

#### 2.2.4.3 总结：
1. 新系统/可改 ID 的前提下，我优先用 “复合分片键 + ComplexKeysShardingAlgorithm + ID 带 slotIndex”，在算法里按“有 registration_id 先走 ID、否则用 hospital_id+date”的优先级路由；
2. 只有在历史包袱/迁移场景下，我才会引入 registration_id 标准分片 + 辅助路由表，用它做“按医院+日期查 ID → 再按 ID 精确路由”的两段式查询。

## 2.3 医疗业务对“强一致事务”的特殊要求怎么兼容？

在分库分表中间件下，门诊收费流程通常是：
1）写挂号表
2）写费用明细表
3）写医保结算流水表
这 3 个表已经被拆分到不同分片。

### 2.3.1 如果产品经理要求“这三个表必须要么都成功，要么都回滚”，你会如何在分库分表 + 分布式事务之间做权衡？

#### 2.3.1.1 首选方案：改分片，让 3 表在一个分片里，本地事务解决

1. 原则：收费这条链是“现金流 + 法规敏感”，优先为它让路。

2. 做法：
    - 统一分片键：
    - 三表都按 hospital_id + encounter_id/registration_id 分片；
    - 在 ShardingSphere 里配成 bindingTable。
    - 这样收费流程：
        BEGIN;
        INSERT t_registration ...
        INSERT t_fee_detail ...
        INSERT t_insurance_bill ...
        COMMIT;
    - 变成单库本地事务，真·要么都成功，要么都回滚。

3. 代价：
    - 按患者/医保局等其他维度的查询，走索引表/ES/对账库，不再指望主库直接查。
    - 换句话说：为强事务牺牲部分查询直达性，用“读模型”补齐。

#### 2.3.1.2 备选方案：保持跨分片，用“业务级强一致”（SAGA/TCC），而不是 XA
1. 如果出于各种历史包袱，这 3 表就是没法放一片，那只能退一步：
    - 引入一张 收费主订单表 t_charge_order（单库/强一致源）：
    - 状态：INIT / PARTIAL / SUCCESS / FAILED / COMPENSATED。
    - 每一步在自己分片内本地事务：
        1. 创建 charge_order 记录（单库强一致）。
        2. 本地事务写挂号 + 标记子步骤成功 / 失败。
        3. 本地事务写费用明细。
        4. 本地事务写医保结算流水。
    - 用 状态机 + 补偿（反冲正） 保证：
    - 任一步失败 → 执行补偿，把前面成功的那几步“冲正/作废”，
    - 最终 charge_order.status 只会落在 SUCCESS 或 FAILED。

2. 对产品侧来说：
    - “要么都成功，要么都回滚”变成：
    - 账单最终视图是一致的（没有半拉吊子收费），
    - 底层表有冲正记录但对业务是“整体失败”。

3. 不做的事：
    - 不做跨库 XA（Seata XA / 两阶段提交）当主解：
    - 医疗场景高并发 + 可用性要求高，跨分片 XA 很容易把系统搞死。


#### 2.3.1.3 总结
1. 医疗收费这类“强一致事务”，我会优先把 挂号表/费用明细表/医保结算表改成同一分片的 bindingTable，用本地事务真原子；
2. 只有在确实无法同片时，才用 charge_order + 状态机 + 补偿 的 SAGA 模式实现“业务级全成功/全失败”，而不会在分库场景下上大规模跨分片 XA。

### 2.3.2 哪些场景你会坚持“为了可用性，事务降级”，请举医疗业务中的具体例子去说服面试官。
1. 收费成功，但「电子发票」「短信通知」失败
	- 主事务：收费记账 + 医保结算 + 患者余额变动 → 强一致，本地事务内必须成功/回滚。
	- 周边动作：开电子发票、发短信、推微信通知，我一定做成异步消息 + 补偿重试。
	- 理由：患者已经交钱拿到凭证了，不能因为短信网关/发票服务挂了，把整个收费回滚，这就是典型“为了可用性，外围事务降级”。

2. 处方开立成功，但「医保实时上传/第三方监管接口」挂了
	- 处方本身（t_prescription / t_order）是医生行为记录，不能随便回滚。
	- 医保/监管实时上传我会用本地消息表 + 重试任务，失败打标记，“稍后补传”，而不是把处方整单回滚。
	- 理由：医生工作不可中断，监管链路问题是外围系统的可用性，优先保证开方流程顺畅。

3. 挂号成功，但「排队大屏/叫号系统/BI 实时看板」更新失败
	- 挂号记录 + 费用扣减 + 医生当天号源剩余 → 强一致。
	- 大屏排队列表、实时 BI 看板、运营监控，我会走 MQ/ES，允许延迟甚至短暂不一致。
	- 理由：排队大屏延迟 10 秒刷新可以接受，但挂号失败/卡死窗口绝对不可接受。

4. 检查报告入库成功，但「患者 App/家属微信」同步失败
	- 报告入库 + 风险标记 + 审核状态 → 在医技系统里强一致，保证院内诊疗安全。
	- 患者 App/家属微信的“报告可见状态”通过异步推送/轮询获取，绝不和医技主事务绑在一个分布式事务里。
	- 理由：医生看得到报告是刚性要求，家属晚几分钟在手机上看到是软需求。

5. 总结
在医疗里，我只对收费记账、医保结算入账、核心诊疗记录（医嘱/处方/病历）坚持强一致；
对通知、报表、监管上传、患者侧展示、风控日志等外围场景，一律通过本地消息表/MQ 做最终一致，宁可“晚一点对”也不能“现在卡死”，这就是我在分库分表下“为了可用性主动事务降级”的边界。


# 3. SQL & 路由错误场景类

## 3.1 经典坑：跨分片 join

门诊药品处方表 t_prescription 与药品主数据表 t_drug 存在关联：
- t_prescription 按 visit_id 分表
- t_drug 按 drug_id 分表（甚至可能单库）

一个新同事写了 SQL：

SELECT p.*, d.drug_name 
FROM t_prescription p 
JOIN t_drug d ON p.drug_id = d.id 
WHERE p.visit_id = ?;

### 3.1.1 在分库分表环境中，这条 SQL 在生产上可能会遇到哪些性能问题或错误？

1. 跨分片 JOIN 不可控 / 直接报错
    - t_prescription 按 visit_id 分片，t_drug 按 drug_id 分片（或单库）。
    - 在 ShardingSphere 里这俩不是 bindingTable，分片键也不一致。
    - 常见结果：
    - 要么中间件直接提示“不支持跨分片 join”；
    - 要么退化为：先在每个分片查 p，再到每个分片查 d，做笛卡尔 join / 内存关联，非常恐怖。
2. d表如果也是分片表 → N×M 查询 + 内存 join
    - 每个 p 所在分片会再去所有 t_drug 分片拉数据，
    - 变成 prescription 分片数 × drug 分片数 的组合查询，
    - 中间件在 JVM 里把结果做 join，内存占用和网络 IO 都爆炸。
3. d 表是单库/广播表 → 每次都要打额外连接，join 无法下推
    - 即使 t_drug 是单库或广播表，
    - Join 很可能在中间件层做：
    - 先路由到处方分片拿 p，再单独查 d，在中间件拼接。
    - 不能利用数据库层的 join 优化，RT 明显比“先查 p，再按 drug_id 批量查 d”慢。
4. 索引利用差 / 扩展性差
    - 处方表按 visit_id 路由，OK，只命中一个分片。
    - 但 JOIN t_drug 这一步，在中间件层做 join 时，容易变成对 t_drug 的多次 point query / 无法批量利用索引，
    - 药品数多时，对 t_drug 压力很大。
5. 结果不一致 / 路由错误风险（如果有人乱配置）
    - 有的同事为了“跑起来”，会把 t_drug 也搞成分片表，但不配置广播/绑定，
    - 结果就是：
    - 某些分片根本没有对应的药品数据 → join 丢数据；
    - 或只在一个库里查到一部分药，结果集悄悄不完整。

6. 总结：
在分库分表环境下，这条 p JOIN d 的 SQL 因为两表分片维度不一致，会导致 跨分片 join 不支持 / 被迫全路由 + JVM 内存 join / RT 巨高 / 结果集不完整 等问题；
正确做法应该是：先按 visit_id 在处方分片查出所有 drug_id，再用批量 IN 去单库/广播的 t_drug 查名，而不是直接在逻辑层写跨分片 join。

## 3.2 医保稽核大查询压垮分片

医保稽核部门要跑一个巨大的统计报表：按“省、市、医院、科室、医生、病种、医保目录”多维度统计近 3 年所有数据，写了一条巨型多表 join + group by SQL。

### 3.2.1 在分库分表场景下，这类查询为什么特别危险？
1. 天然跨分片、几乎必全路由
    - 分片一般按 hospital_id + 日期，
    - 你的维度是 “省、市、医院、科室、医生、病种、医保目录 + 近 3 年”。
    - 结果：几乎不可能命中单分片，16/32/64 个分片一起扫，每个库都在跑大聚合。
2. 多表 join + group by 无法下推，变成“分布式大锅乱炖”
    - 医保明细 × 诊断表 × 医院表 × 科室表 × 医生表 × 目录表…
    - 分片规则又不一致（有的按医院，有的单库，有的广播）。
    - 中间件要么直接不支持，要么变成：
    - 每分片本地算一堆 partial result；
    - 汇总节点再二次 group by，内存爆 + 网络打满。
3. 时间范围过大，直接把 OLTP 拖死
    - “近 3 年” = 全量历史大表扫描；
    - 本来交易库应该只扛“当天/近几个月”的短查询，结果被当成数仓用。
    - 高峰期一跑，医生开处方、收费挂号都跟着抖。
4. 分库分表的优势完全被废掉
    - 分片是为“按键命中少量分片、每次查少量数据”设计的。
    - 你这条 SQL 效果等价于：
    "帮我把所有分片的 3 年数据搬出来汇总一下”
    - 扩到 32/64 分片只会 放大问题，不是解决问题。

### 3.2.2 你会提出什么替代方案？比如：离线数仓/ODS、按日汇总表、预聚合中间表等，怎么和分库分表设计配合？
1. 明细：分库分表的 OLTP 只干交易
    - 现有分片库：按 hospital_id + 日期 拆的医保明细表，只服务挂号/收费/对账接口。
    - 约束：
    - 只能查“单院 + 短时间（天/周/月）”；
    - 严禁跑 3 年多维统计。

2. ODS / 数仓：专门承接“全省、全历史”的统计
    1. 数据链路：
        1. 从分片库做 CDC / Binlog → 落到 ODS（按业务表 1:1 镜像）；
        2. ODS 再 ETL 到数仓（Hive/Hudi/Iceberg/ClickHouse 都行），建星型模型：
            - 事实表：fact_insurance_claim
            - 维表：dim_hospital / dim_dept / dim_doctor / dim_disease / dim_insure_catalog / dim_region

    2. 大报表去哪跑？
        - 所有“近 3 年 × 多维度”的报表 SQL 统一在数仓跑，
        - 可以用 Presto/Trino/Spark/ClickHouse 提供查询服务，
        - 完全绕开分库分表的 OLTP。

3. 预聚合：按日/账期/维度建汇总表，加速统计
    1. 在数仓里再往上叠一层“预聚合中间表”，比如：
        - agg_claim_d_yyyymmdd：
        - 粒度：日期 + 省 + 市 + 医院 + 科室 + 医生 + 病种 + 目录
        - 指标：sum(med_fee), sum(fund_pay), count(distinct patient_id)…
        - agg_claim_m_yyyymm：
        - 粒度：账期 + 医保局 + 医院

    2. 跑大报表时：
        - 先查这些 按日/按月预聚合表 再 group by，
        - SQL 复杂度和数据量都小很多，性能会稳定在秒级~十几秒级。

4. 总结
分库分表的交易库只负责在线明细、短期对账；
明细通过 CDC/ETL 进入 ODS，再进数仓做全省、全历史、多维统计；
数仓在事实表之上再建按日/账期/多维的预聚合表，所有医保稽核的巨型报表都跑在这些表上，而不是跑在分片 OLTP 上。

### 3.2.3 你会如何隔离“稽核大查询”和“在线交易”？仅靠读写分离够不够？是否需要单独的分析集群/数仓？

#### 3.2.3.1 读写分离为什么不够？

1. 还是同一套库表结构，还是 OLTP 模型
    - 分片规则还是按 hospital_id + 日期；
    - 你那种“省/市/医院/科室/医生/病种/目录 × 近 3 年”的 SQL
    - 依然是跨全分片 JOIN + GROUP BY，
    - 只是从 主库 换成 只读库 在挨打而已。
    - 分库分表中间件还是要做分布式路由、聚合，CPU/JVM 内存一样会爆。
2. 读流量一大，会拖慢复制 / 影响高可用
    - 从库本质上要跟主库同步 binlog，如果你在上面跑超重的统计：
    - IO / CPU 被报表吃掉 → 复制延迟变大；
    - 一旦主挂，从库顶上来，用的是“几分钟前的数据”，很尴尬。
    - 医疗领域特别怕这种“主从延迟高 + 随时要切换”的组合。
3. 你无法针对稽核/报表的特点做特殊建模
    - 读写分离只能做到“同一套表复制多份”；
    - 但稽核需求明明想要的是：
    - 按日/月账期的预聚合表；
    - 按医保局/统筹区/病种的宽表；
    - 历史 3 年压缩/分区，方便长周期扫描。
    - 这些都和 OLTP 的细粒度行模型冲突，只靠只读库搞不出来。

#### 3.2.3.2 推荐的隔离方案：三层架构
1. 分库分表交易集群（OLTP）
    1. 角色：
        - N 个分片，按 hospital_id + 日期 拆；
        - 只负责：挂号、收费、医保结算入账、单院对账、窗口查询等在线交易。
    2. 隔离手段：
        - 严格 SQL 规范：
        - 必须带分片键（hospital_id）+ 小时间窗口；
        - 禁止无条件全表扫 / 禁止 3 年历史 / 禁止 N 表大 JOIN。
        - ShardingSphere / 网关层做 SQL 黑名单/限流：
        - 一旦检测到“疑似报表 SQL”，直接拒绝或引导走报表接口。
        - 读写分离在这一层可以用，但只服务在线接口（比如医生工作站查询当天历史），而不是大报表。
        - 这层的目标是：稳、快，不背报表。
2. 稽核/对账库（ODS/报表库）——专门给医保局和财务玩
    1. 数据来源：
        - 从 OLTP 分片库通过 CDC / Binlog / 定时抽取 进入 ODS；
        - ODS 表 = 与 OLTP 结构基本一致的明细表；
        - ODS 之上再建：
        - 日级汇总表：agg_claim_d（按日期 + 医院 + 科室 + 医生 + 病种 + 目录）；
        - 月级/账期汇总表：agg_claim_m（按医保局 + 账期 + 医院）。

    2. 隔离效果：
        - 大部分医保局日常“按账期对账、按医院/科室/医生看费用”的报表
        - 这套库可以有自己独立的实例/集群，CPU/IO 撑不住时单独扩；
        - 就算这层被报表跑慢了，不会影响挂号收费主链路。

3. 离线数仓/分析集群（真正扛 3 年大报表的地方）
    1. 角色：
        - 承接 “近 3~10 年全历史、多维度、临时口径” 的重度医保稽核、风控、科研分析。
        - 技术选型：
        - 数据湖/数仓：Hive + Presto/Trino / SparkSQL / Hudi / Iceberg；
        - 或者 ClickHouse/Doris 这类列存 MPP。

    2. 数据流动：
        1.	ODS 每天/每小时 增量抽数到数仓：
            - 事实表：fact_insurance_claim（拉平医保结算明细）；
            - 维表：医院/科室/医生/病种/医保目录/区域等。
        2. 在数仓里建：
            - 细粒度事实表（全历史）；
            - 各种按日、账期、维度的宽表 & 预聚合表。

4. 总结
	1. 分库分表 OLTP 集群：只服务挂号、收费、医保结算等在线交易，强约束 SQL，只允许“按医院 + 短时间”的明细查询，禁止长周期多维统计；
	2. ODS/稽核对账库：从分片库通过 CDC/ETL 汇总明细，按日/账期、医院/医保局建预聚合表，承接大部分对账和常规稽核报表，这一层可以独立扩容；
	3. 离线数仓/分析集群：承接全省多年历史的多维分析和临时报表，把那种“省/市/医院/科室/医生/病种/医保目录 × 3 年”的 SQL 全部放在这里跑。

# 4. 事务 & 一致性问题类（医疗场景特化）

## 4.1 床位管理超卖 / 重复入院
住院系统中，床位表 t_bed 与住院登记表 t_inpatient 分布在不同分片，业务要求同一个 bed_id 同一时间只能被一名住院患者占用。

### 4.1.1 在分库分表 + 高并发入院流程下，会出现哪些数据不一致问题（例如：重复入住、床位数不准）？

1. 同一张床被占用两次（经典超卖）
    1. 流程常见是这样：
        1. 流程 A：
            - 查 t_bed：bed_101 状态 = 空闲
            - 写 t_inpatient 插入一条住院记录（bed_id=101）
            - 更新 t_bed 状态为占用
        2. 流程 B（几乎同时）在另一个分片/事务也查到 bed_101 = 空闲
            - 同样插一条 t_inpatient、更新 t_bed 占用
    2. 如果：
        - 查床位和写入住分在两个库、两个事务；
        - 没有全局唯一约束 / 分布式锁兜底；
    3. 结果就是：两名患者同时住进 bed_101，系统数据看起来没报错，但业务炸了。

2. 患者有入住记录，但床位显示“空闲”（半成功事务）
    1. 典型链路：
        - 先写 t_inpatient 成功（跨分片写入 A 库）；
        - 再写 t_bed 更新状态时失败（B 库网络抖动 / 超时）

    2. 结果：
        - t_inpatient 里这个病人是“在院 + 绑定 bed_id”；
        - t_bed 仍显示空闲 → 前台看到这张床还能分配，继续给别人用。

    3. 反之亦然：
        - t_bed 状态提前改成占用；
        - t_inpatient 插入失败 / 回滚 → 床被“锁死”，没人住。

3. 床位统计数不准（剩余床位、空床率乱掉）
    1. 比如：
        - 空床数是按 t_bed.status 统计；
        - 实际住院情况看 t_inpatient 的在院记录。
    2. 在高并发 + 异步更新/重试情况下，很容易出现：
        - t_bed 统计出 5 张空床；
        - t_inpatient 里其实已有 5 条占用该床位的在院记录（或相反）。

    3. 表现出来就是：
        - 科主任看报表觉得“还有床”，前台却分不出；
        - 或者系统提示满床，实际上有床没用。

4. 并发调床 / 退床导致“床位错乱”“病人漂移”
    1. 比如两个操作同时发生：
        - 操作 A：给患者 P 从床 101 → 102（更新两张床 + 一条住院记录）
        - 操作 B：护士在另一个终端给 P 退院 / 改到其他床
    2. 如果这几个更新散落在多个分片，没有统一锁/事务：
        - A 改了 t_bed，B 改了 t_inpatient，
        - 最后可能出现：
            - P 显示在 bed_102，但 bed_102 状态 = 空闲；
            - 或 P 已退院，但 bed_101/102 仍处于占用状态。

5. 同一患者重复住院（跨分片唯一性失效）
    1. 虽然你问的是床，但现实常一起出现：
        - t_inpatient 按 visit_id 或 inpatient_id 分片，
        - 没有全局唯一约束保证：一个患者在同一时间最多只有一条“在院”记录；
    2. 高并发下两个入院操作并发过来：
        - 各自命中不同分片，
        - 各插入一条 status=在院 的记录，
    3. 最后：
        - 系统上看这个人“同时在两次住院中”，床位统计、医保结算、费用汇总全乱。

### 4.1.2 你会如何设计“幂等 + 锁 + 版本号 + 事件最终一致”组合拳？给出一个你认可的方案轮廓。

1. 核心思想：把“占床”收敛成一个聚合根（t_bed_occupy），在这个点上用：幂等 + 锁 + 唯一约束/版本号 + 事件驱动， t_inpatient 等其它表都变成事件消费者，做到最终一致。

#### 4.1.2.1 单一真相源：床位占用表 t_bed_occupy
1. 新增一张专门管理占床的表（可以在“床位服务”库里，按 bed_id 分片）：
    ```sql
    t_bed_occupy (
    id              BIGINT PK,
    bed_id          BIGINT,      -- 床位ID，分片键
    inpatient_id    BIGINT,      -- 住院登记ID
    biz_request_id  VARCHAR(64), -- 幂等键（一次入院请求一个）
    status          TINYINT,     -- INIT / CONFIRMED / RELEASED / CANCELED
    active_flag     TINYINT,     -- 1=当前占用, 0=已释放
    version         INT,         -- 版本号，用于乐观锁
    occupy_start    DATETIME,
    occupy_end      DATETIME NULL,
    create_time     DATETIME,
    update_time     DATETIME
    -- 关键约束：同一时刻只能有一个 active 占用
    UNIQUE KEY uq_bed_active (bed_id, active_flag)  -- active_flag=1 的行最多一条
    -- 幂等约束
    UNIQUE KEY uq_biz_req (biz_request_id)
    );
    ```

2. 幂等：biz_request_id 把所有重试都“吃掉”
    1. 所有“占床/退床/调床”指令都带一个 biz_request_id：
        - 同一个按钮，多次点击 → 同一个 biz_request_id；
        - 网关重试 / MQ 重试 → 也用同一个 biz_request_id。
    2. 在 t_bed_occupy 上做唯一约束：
        - 第一次请求：插入成功；
        - 后续重试：命中 uq_biz_req 冲突 → 查询原记录，直接返回之前的结果，天然幂等。

3. 锁：针对单个 bed_id 的分布式锁（减并发冲突）
    1. 为避免单 bed 在高并发下疯狂冲击唯一索引，我会再加一层细粒度分布式锁：
        - Key：bed:lock:{bedId}
        - 实现：Redis SET NX + EX / Redisson / 或者单库 t_bed_lock 行级锁。
    2. 入院占床的第一步：
        - try lock("bed:lock:101", 3s)
        - 失败 → 返回“床位忙/重试”，保护后端
        - 成功 → 继续下面的事务逻辑
    3. 锁只是减小并发窗口，真正兜底还是依赖下面的唯一约束+版本号。
4. 版本号 + 唯一约束：真正保证“同一时刻只有一个占用”
    1. 占床本地事务（在“床位服务”库内）大致这样：
        ```sql
        - BEGIN
        - 幂等检查
        - SELECT * FROM t_bed_occupy WHERE biz_request_id = ?;
        - 若存在 → 直接返回（幂等）
        - 尝试插入一条 active 占用记录
        
        INSERT INTO t_bed_occupy (bed_id, inpatient_id, biz_request_id,
                                    status, active_flag, version, occupy_start)
        VALUES (?, ?, ?, 'INIT', 1, 0, now());
        -- 若报 uq_bed_active 冲突 → 床已被占，抛业务异常“床已被占用”
        -- 状态流转为 CONFIRMED（乐观锁 + version）
        UPDATE t_bed_occupy
        SET status = 'CONFIRMED', version = version + 1
        WHERE id = ? AND version = 0;
        -- 若影响行数=0，说明被并发修改，按失败处理

        -- 4. 同一事务里写一条 outbox 事件（给住院系统用）
        INSERT INTO t_outbox (event_type, biz_key, payload, status)
        VALUES ('BED_OCCUPIED', ?, json(...), 'NEW');

        COMMIT
        ```
    2. 关键点：
        - UNIQUE (bed_id, active_flag) 保证同一床位 active=1 只有一条 → 不可能出现“两个患者同时入住”；
        - version 只在更新/释放/调床时用：
        - WHERE id=? AND version=? 方式做乐观锁，避免并发改错状态。
    3. 释放床位、退院、调床也是类似：
        - 退床：UPDATE ... SET active_flag=0, status='RELEASED', version=version+1 WHERE id=? AND version=? + outbox 事件；
        - 调床：先释放旧床占用，再对新床做一次上面的“占床步骤”，两个步骤可以串行/事务性 orchestrate（业务层 SAGA）。

5. 事件：跟 t_inpatient / t_bed 主表做最终一致
    1. 现在床位占用的强约束已经在一个库、一个事务里保证了，接下来：t_inpatient 和原来的 t_bed（主数据/展示）都通过事件来同步。
    2. Outbox → MQ → 住院服务：
        在刚才的事务里同时写了 t_outbox：
        - 消费器扫描 t_outbox，把 BED_OCCUPIED 推到 MQ；
        - 住院服务消费：
            - ```sql
            on BED_OCCUPIED:
                - 在 t_inpatient 相应分片里创建/更新住院记录（bed_id, inpatient_status 等）
                - 必要时更新 t_bed 展示状态（如某库里的库存表）
                - 若消费失败，重复消费靠event_id + 消费端本地表做幂等。
            ```

    3. 失败补偿：住院写失败 → 回滚床位占用（业务级 SAGA）
        1. 如果住院服务消费 BED_OCCUPIED 失败严重（多次重试不成），有两种选项：
            - 简单版：报警 + 人工处理，短时间内床位被锁住；
            - 完整版：发一个“补偿命令”：
                - ```sql
                SEND COMMAND: RELEASE_BED {bed_occupy_id, reason='inpatient_failed'}
                ```

        2. 床位服务收到后：
            - 用 version 做乐观锁，把 active_flag=1 的记录改为 CANCELED，再发布 BED_RELEASED 事件；
            - 下游把 t_inpatient 状态调整回来。

# 5. 扩容 & 数据迁移类

## 5.1 既有单库系统迁移到分库分表的“切流”方案

老的 HIS 系统是一套单库 MySQL，业务方要求“零停机迁移”到分库分表架构上。

### 5.1.1 你会如何设计这次迁移的步骤？双写？回放 binlog 做增量同步？如何进行数据校验？

1. 搭好目标分库分表集群（不对外）
    - 按未来规划建好：
        - 分库分表规则（按 hospital_id / visit_id / patient_id 等）
        - ShardingSphere 规则、数据源配置
        - 在新集群上建好和单库结构等价的表（适当加上分片键索引、冗余字段）。

2. 全量迁移（单库 → 分片集群）
    - 从单库做全量导出（mysqldump / mydumper / 自写批量任务），
    - 通过一个“迁移程序”按分片规则把数据灌入新集群：
    - 对每行计算目标分片（按 hospital_id / visit_id / patient_id）；
    - 支持断点续传（按主键或时间分段）。

3. 增量同步：首选 Binlog 回放，不首选长期双写
    1. 这是关键：老库仍是“写主”，新集群是“影子库”。
        - 老 MySQL 开 binlog（ROW 格式）；
        - 用 CDC 组件订阅：Canal / Debezium / 自研 binlog consumer；
        - 同步逻辑：监听 insert/update/delete；
        - 根据业务主键拿到分片键（hospital_id / patient_id 等）→ 路由到对应分片；
        - 写入新集群；
        - 用幂等（主键 + 版本号）避免重复。

    2. 为什么不一开始就应用双写？
        - 应用层双写很容易两边写失败顺序不一致；
        - Binlog 是“老库真实提交顺序”，拿它做源 of truth 更稳。
        - 双写只适合短窗口校验，不适合整个迁移周期。

4. 校验：行数 + 聚合 + 抽样三层
    1. 行数对比
        - 按表、按分片键范围（如 hospital_id、日期段）统计 count(*)
        - 单库 vs 新集群汇总，一致才通过。
    2. 聚合对比
        - 对关键金额/数量字段做 sum/avg 同步核对：
        - 如收费总金额、医保基金支付总额、就诊人次等。
        - 发现差异就按分区缩小范围再查。
    3. 抽样 row 级对账
        - 随机选一批主键（订单号 / visit_id），
        - 对比单库和分片库整行字段是否一致。

5. 灰度切流：先读灰度，再写切换
    1. 读灰度（影子读）
        - 在应用中间加一层开关：
        - 某些非关键、只读接口（比如历史查询）
        - 可按“医院 / 用户 / 接口”灰度从新集群读；
        - 观察：
        - RT、错误率、日志对比（新老查询结果一致性）
        - 有问题可以随时关掉灰度，回到老库读。

    2. 写切换（小窗口 + 可回滚）
        - 选低峰时间点；
        - 短暂“冻结配置变更”，但不断业务：
            - 继续对老库写，同时 Binlog 同步保持开着，观测延迟在可控范围；
        - 切应用配置：
            - 将写流量切到新集群（ShardingSphere 数据源）；
            - 老库变成“只读 + Binlog 继续放给新库做兜底一小段时间”。

    3. 要不要双写？
        - 切写之后，可以考虑短时间“双写回老库” 做兜底：
        - 应用写新库的同时，异步把变更写回老单库（或者新库 Binlog 反向写入老库）；
        - 如果发现新集群有严重问题，可以快速把业务指回老库。
        - 这段“双写期”一般只保留 1~2 周，待稳定后完全退役老库。

6. 切换后继续校验 & 回滚预案
    1. 切到新集群写之后，继续跑一段时间的对账/校验：
        - 新库 vs 老库（此时老库相当于影子备库）
        - 一致性 OK 再考虑下线老库写入。
    2. 回滚预案：
        - 新库写有严重 bug 时：
        - 立刻切开关让应用重新只写老库；
        - 视情况用 Binlog / 校验脚本从老库“反向修补”新库。

7. 最后给面试官的一段总结话术
    1. 老 HIS 单库迁到分库分表，我会用 “影子集群 + 全量迁移 + Binlog 增量同步 + 多轮校验 + 灰度切流” 的套路：
        - 不让应用一上来就双写，而是先把新分片集群当成“实时同步的从库”；
        - 全量导 + Binlog 回放保证新集群和老库几乎实时一致；
        - 行数、聚合、抽样多层数据校验后，再灰度把读迁过去，最后在极短窗口内切写；
        - 切写之后可以短期双写回老库作为回滚兜底，稳定后再完全退役老库。

### 5.1.2 切换过程中如何保证挂号、收费、处方开立等关键业务不受影响？

#### 5.1.2.1 应用层：灰度切、可回滚，不搞“一键全切”
1. 配置中心 + 开关控制数据源
    - 应用里访问 DB 通过一个 DataSource 路由层（比如 ShardingSphere 或自封装）：
        - mode = LEGACY：所有读写都打老单库；
        - mode = SHARDING_SHADOW：写老库，读可以灰度打新库做对比；
        - mode = SHARDING_PRIMARY：写新分片集群（老库作为影子）。
    - 开关放在配置中心（Nacos / Apollo 等），支持按应用实例/医院维度灰度，不是一刀全切。

2. 滚动重启实例，保证“永远有一批在老库上服务”
    - 做切换时不全体重启：
        - 先挑 5% 实例切到 SHARDING_PRIMARY，观察挂号/收费/处方接口 RT 和错误率；
        - 没问题再扩大到 20% / 50% / 100%。
    - 任何阶段发现问题：
        - 配置切回 LEGACY；
        - 新流量立刻回老库，不中断业务，只是短时间 RT 抖一下。

#### 5.1.2.2 数据层：始终保持“只有一个写主”，读可以灰度
1. 切换那一刻，写流量只切一次，不双主
    - 切换前：
        - 写：全部打老库；
        - Binlog/CDC 同步：老库 → 新分片集群。
    - 切换后：
        - 写：全部打新分片集群；
        - （可选）短期反向同步：新库 → 老库，用于回滚兜底。
    - 从头到尾只有一个“权威写库”，避免“两个库都在收挂号/收费”的脑裂场景。

2. 读流量可以提前灰度，关键写接口延后切
	-对 只读接口（查历史挂号、历史收费、处方明细）：
    - 可以提前灰度到新分片集群，做线上“对账验证”。
    - 对 关键写接口（挂号、收费、处方录入）：
    - 坚持“最后一批切”；
    - 等新分片数据经全量 + 增量同步 + 校验都稳定之后再切。

#### 5.1.2.3 关键事务链路：幂等 + 重试 + 降级，别怕多扣/多开

1. 给关键操作加业务幂等键
    - 挂号：biz_key = hospital_id + reg_no
    - 收费：biz_key = hospital_id + charge_no
    - 处方：biz_key = hospital_id + prescription_no
    - 无论请求被路由到老库还是新库，只要：
        - 表上有 UNIQUE(biz_key)
        - 逻辑里先查后插
        - 即使重试 / 抖动，也不会产生重复挂号 / 重复扣费 / 重复处方。

2. 关键链路使用“本地消息表 + 重试”，切换时可以安全重放
    - 收费 / 处方开立这些都会往下游扔消息（医保、发票、短信…）。
    - 开本地消息表，写主业务表 + 消息表在一个本地事务里完成。
    - 切流过程中如果下游调用失败：
        - 可以安全重试，
        - 即便重放到新库/老库，凭 幂等键 保证“不多扣一次钱”。

3. 遇到新集群抖动，关键链路立即“快速降级”
    - 监控指标：挂号/收费/处方接口：
        - 错误率、RT、超时数。
    - 一旦新分片集群出问题：
        - 自动/人工拉开关 → 写流量退回老库；
        - 非关键能力（报表、推荐、统计）先降级或关闭，保证“挂号、收费、开方”优先活着。

#### 5.1.2.4 变更窗口的“操作纪律”
1.	冻结 DDL 和大任务
    - 迁移前后某个时间窗口，禁止：
        - 新建表/字段；
        - 跑全表 UPDATE/统计任务。
2.	冻结大版本发布
    - 切库期间，应用逻辑尽量不大改；
    - 否则出问题很难分辨是“逻辑 bug”还是“迁移问题”。
3.	预案明确：发现下面几种现象立刻回滚
    - 医生端大量 5xx；
    - 收费端出现“已扣款但无记录”/“反复提示失败但实际上成功”；
    - 监控显示分片集群连接池耗尽、慢 SQL 突增。

#### 5.1.2.5 面试用的收尾总结
1. 零停机迁移时，我是通过“影子集群 + Binlog 同步 + 灰度切流 + 可快速回滚”保证挂号、收费、处方这些关键业务不受影响：
    - 整个过程中始终只有一个写主，读可以灰度，新集群出问题随时切回老库；
    - 关键操作统一加业务幂等键 + 本地消息表，即使在切换抖动或重试时，也不会出现重复挂号、重复扣费、处方重复开立；
    - 切换按“接口/医院/实例”逐步放量，配合监控和降级策略，一旦异常马上回滚配置，保证医生和收费窗口感知到的只是短暂延迟，而不是系统不可用或数据错误。

## 5.2 分表扩容：从 8 张到 64 张表

挂号明细表 t_registration_xx 目前按 hash(patient_id) % 8 分成了 8 张表，已经面临单表 1 亿+ 数据。

### 5.2.1 你会采用哪几种扩容策略？（在线重分片、双写新老分片、按时间维度新旧规则共存等）
### 5.2.2 在扩容期（规则双轨）的读写路由如何设计，避免读混乱？
### 5.2.3 医保对账时要对全量挂号记录进行抽查，如何在规则切换期间保证能完整查全？

## 5.3 存量冷数据迁归档库

医疗法规要求数据保留 15 年，但大量历史数据几乎不再被实时访问。

### 5.3.1 你会如何对历史数据进行归档？是按时间分库还是转移到专门的归档实例/对象存储？
### 5.3.2 归档后的查询需求（比如：医保稽核追溯 10 年前某患者的住院记录）如何做到“可用但不拖垮线上”？
### 5.3.3 会不会考虑“在线分片 + 冷数据离线仓库 + API 层聚合”的组合？

# 6. 故障排查 & 性能优化类

## 6.1 某个片区医院访问突然变慢，你如何从分库分表角度排查？

现象：
- 只有 A 市的几家医院挂号/缴费变慢，B 市正常。
- 这些医院的数据主要集中在若干个分片上。

### 6.1.1 你会从哪些维度排查？分片节点的 CPU/IO/锁等待？路由规则异常导致大量跨分片？热点医院的请求没有按预期分摊？
### 6.1.2 请给出一个你实际会采取的排查路径。

## 6.2 慢 SQL 分布在多个分片，如何统一观测与调优？

在分库分表后，每个分片数据库都有自己的慢查询日志。

### 6.2.1 你如何在“多分片、多实例”的环境中构建一套统一的慢 SQL 观测和分析体系？
### 6.2.2 对于“某个 SQL 在不同分片表现差异巨大”的情况，你会如何解释和优化？表统计信息？索引差异？数据分布倾斜？

## 6.3 线上突然出现大量路由失败 / SQL 不支持异常

应用日志里频繁出现：
- “No route result, sharding key is null”
- “This SQL is not supported in sharding mode”

### 6.3.1 在医疗系统场景下，这很可能是什么原因导致的？新业务表上线但没有配置分片规则？老代码遗留的“全表扫描统计”被搬到了分库分表库？
### 6.3.2 你会如何组织“规则治理 + 编码规范 + SQL 审核流程”来减少类似问题？

# 7. 安全、合规 & 多租户（医共体 / 医联体）类

## 7.1 医共体场景下的多租户隔离

一个省平台上挂了几百家医院，每家医院是一个“租户”。

### 7.1.1 分库分表时，你会如何设计多租户隔离？每个租户一库？多租户共享库但按 tenant_id 分表？
### 7.1.2 怎么保证某家医院的 DBA 无法访问其他医院的数据？
### 7.1.3 在审计/风控层面，你会引入哪些机制保证“跨租户查询”的可追踪？

## 7.2 数据脱敏与分库分表的冲突

法规要求对患者敏感信息（姓名、证件号、手机号）进行脱敏存储或加密。

### 7.2.1 当你使用这些字段作为分片键或查询条件时，会遇到什么典型问题？
### 7.2.2 你会如何折中？分片键使用加密后的值？建立“脱敏索引表”做路由？引入搜索服务（ES）作为中介？

## 7.3 灾备切换下的分库分表一致性

医疗系统必须有跨机房甚至跨城市灾备。

### 7.3.1 在主机房的多个分片如何同步到灾备机房？
### 7.3.2 当主机房故障切到灾备后，如何保证分库分表规则一致、分片拓扑一致？
### 7.3.3 在回切主机房时，对业务（特别是医保和对账）有什么注意事项？