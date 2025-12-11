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

### 1.1.8 SQL编写
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
### 2.1.2 医保对账库、日志库、规则库、黑名单库、实时计费事务库，分别适合/不适合接入的原因？
### 2.1.3 如何跟业务侧约定“不能做的 SQL”？举 3 条你认为在分库场景下要禁止或慎用的 SQL 写法。
### 2.1.4 对于“高频查询维度”和“主业务事务维度”不一致的情况，你会如何在写入路径上尽可能简单，同时在查询路径上用索引表/ES/缓存来补齐？给一个你认可的组合方案。
### 2.1.5 医技报告经常需要“按患者终身维度”拉全量结果，那么当分片按 hospital_id + 日期 时，你会不会考虑影像/报告落 ES 或对象存储 + 元数据表？如何保证查询性能和一致性？
### 2.1.6 遇到“历史系统没分库分表、你这套有分”，跨系统拉取报告时，如何设计一个统一的查询网关/聚合服务，屏蔽复杂度？
### 2.1.7 当运营突然提出一个新维度（例如：某检验项目+设备型号+批号），你如何评估是否“值得”为其新增索引表或物化视图，而不是直接怼在线库？

## 2.2 路由策略设计题

挂号表 t_registration 已经按 hospital_id + registration_date 水平拆分到 16 个分片。

### 2.2.1 如何设计 ShardingSphere 的分片算法，既能支持按医院+日期查询，又能支持按 registration_id 精确查询？
### 2.2.2 当未来要从 16 分片扩容到 32 分片时，这套路由算法如何提前设计避免大规模数据迁移？
### 2.2.3 如果已有历史数据是按 hash(registration_id) % 16 路由的，现在要改为 hash(patient_id)，你会怎么做迁移方案？
### 2.2.4 对于“按 registration_id 精确路由”和“按 hospital_id + date 范围查询”两种模式并存，是否会考虑复合分片键或标准分片键 + 辅助路由表？具体怎么设计？
### 2.2.5 在扩容 16→32 时，你会更倾向一次性重分片迁移，还是“新流量新规则 + 老数据保留旧规则”的双轨？说说你会选哪种以及权衡点。
### 2.2.6 若采用“虚拟节点 + 一致性哈希”，如何应对医疗系统常见的院区压根不均匀的情况（核心三甲 vs 边缘社区医院）？
### 2.2.7 迁移过程中，如果某些请求走了错误路由（比如历史 bug），你会如何对账和修复，避免数据在不同分片“各有一份”？

## 2.3 医疗业务对“强一致事务”的特殊要求怎么兼容？

在分库分表中间件下，门诊收费流程通常是：
1）写挂号表
2）写费用明细表
3）写医保结算流水表
这 3 个表已经被拆分到不同分片。

### 2.3.1 如果产品经理要求“这三个表必须要么都成功，要么都回滚”，你会如何在分库分表 + 分布式事务之间做权衡？
### 2.3.2 哪些场景你会坚持“为了可用性，事务降级”，请举医疗业务中的具体例子去说服面试官。
### 2.3.3 对于“按 registration_id 精确路由”和“按 hospital_id + date 范围查询”两种模式并存，是否会考虑复合分片键或标准分片键 + 辅助路由表？具体怎么设计？
### 2.3.4 在扩容 16→32 时，你会更倾向一次性重分片迁移，还是“新流量新规则 + 老数据保留旧规则”的双轨？说说你会选哪种以及权衡点。
### 2.3.5 若采用“虚拟节点 + 一致性哈希”，如何应对医疗系统常见的院区压根不均匀的情况（核心三甲 vs 边缘社区医院）？
### 2.3.6 迁移过程中，如果某些请求走了错误路由（比如历史 bug），你会如何对账和修复，避免数据在不同分片“各有一份”？

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
### 3.1.2 你会如何定位并解决？
### 3.1.3 对中台/公共服务层有什么改造建议，避免开发再写类似 SQL？
### 3.1.4 对于“按 registration_id 精确路由”和“按 hospital_id + date 范围查询”两种模式并存，是否会考虑复合分片键或标准分片键 + 辅助路由表？具体怎么设计？
### 3.1.5 在扩容 16→32 时，你会更倾向一次性重分片迁移，还是“新流量新规则 + 老数据保留旧规则”的双轨？说说你会选哪种以及权衡点。
### 3.1.6 若采用“虚拟节点 + 一致性哈希”，如何应对医疗系统常见的院区压根不均匀的情况（核心三甲 vs 边缘社区医院）？
### 3.1.7 迁移过程中，如果某些请求走了错误路由（比如历史 bug），你会如何对账和修复，避免数据在不同分片“各有一份”？

## 3.2 医保稽核大查询压垮分片

医保稽核部门要跑一个巨大的统计报表：按“省、市、医院、科室、医生、病种、医保目录”多维度统计近 3 年所有数据，写了一条巨型多表 join + group by SQL。

### 3.2.1 在分库分表场景下，这类查询为什么特别危险？
### 3.2.2 你会提出什么替代方案？比如：离线数仓/ODS、按日汇总表、预聚合中间表等，怎么和分库分表设计配合？
### 3.2.3 你会如何隔离“稽核大查询”和“在线交易”？仅靠读写分离够不够？是否需要单独的分析集群/数仓？
### 3.2.4 如果短时间内无法搭数仓，只能在现有库上做，你会有什么“止血”手段？例如：限制查询窗口、按医院分批、强制分页等。
### 3.2.5 如何从架构层面防止“分析型 SQL 不小心跑到 OLTP 集群”？你会引入 SQL 网关还是多数据源路由？
### 3.2.6 医保稽核有时要回溯很多年，你会如何规划历史数据分层（冷/温/热），并让稽核人员“感知到延迟但系统稳定”？

## 3.3 热点分片问题：急诊科夜间挂号

系统中门诊挂号按 hospital_id + registration_date 分片，但现实中急诊科夜间挂号极端集中在某几家医院，导致这些分片 QPS & TPS 爆高。

### 3.3.1 这种“业务热点+分片热点”有什么典型表现？
### 3.3.2 除了“堆机器”，你会如何调整分片键/路由策略或者做“热点拆分”？
### 3.3.3 除了观察 QPS/TPS，你还会用哪些指标确认“是分片热点而不是网络/依赖问题”？比如：锁等待、行热点、连接池耗尽等。
### 3.3.4 对于急诊这类强热点业务，你会考虑按业务线拆库（急诊单独一套）还是在现有库内做逻辑热点分裂（如热点数据单独路由）？
### 3.3.5 如果改分片键已经非常困难，你会考虑在应用层做预分摊吗，比如使用“号池”、“预创建挂号记录”等模式？
### 3.3.6 面对热点，Redis/本地缓存能缓解多少？哪些操作绝对不能被缓存（例如强一致扣费）？

# 4. 事务 & 一致性问题类（医疗场景特化）

## 4.1 床位管理超卖 / 重复入院

住院系统中，床位表 t_bed 与住院登记表 t_inpatient 分布在不同分片，业务要求同一个 bed_id 同一时间只能被一名住院患者占用。

### 4.1.1 在分库分表 + 高并发入院流程下，会出现哪些数据不一致问题（例如：重复入住、床位数不准）？
### 4.1.2 你会如何设计“幂等 + 锁 + 版本号 + 事件最终一致”组合拳？给出一个你认可的方案轮廓。

## 4.2 医保扣费与退费的不一致

医保扣费是在医保库，医院收费明细在业务库，两个库已经分库分表并且在不同实例。

### 4.2.1 当医保扣费成功但业务库写失败时，你如何处理？
### 4.2.2 如果采用本地消息表或事务消息保证最终一致，你会把消息表放在哪一侧？（医保库 or 业务库）为什么？
### 4.2.3 对对账和异常修复流程，你会如何落地，以应对“总有极端失败场景”？

## 4.3 医疗合规场景下的“数据不可丢 + 可追溯”

法规要求医疗数据不可丢失且可追溯，分库分表后整个链路更复杂。

### 4.3.1 在分库分表体系里，你会如何设计 binlog / CDC（变更数据捕获）方案，既满足审计，又不拖垮线上？
### 4.3.2 当部分分片出现损坏或回滚时，如何保证审计链条完整？

# 5. 扩容 & 数据迁移类

## 5.1 既有单库系统迁移到分库分表的“切流”方案

老的 HIS 系统是一套单库 MySQL，业务方要求“零停机迁移”到分库分表架构上。

### 5.1.1 你会如何设计这次迁移的步骤？双写？回放 binlog 做增量同步？如何进行数据校验？
### 5.1.2 切换过程中如何保证挂号、收费、处方开立等关键业务不受影响？
### 5.1.3 如果切换后发现部分分片路由规则有 bug，如何快速回滚？

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