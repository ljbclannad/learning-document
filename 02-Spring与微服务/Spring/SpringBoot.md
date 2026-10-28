# SpringBoot：启动、自动配置与工程边界

> 学习基线：JDK 17、Spring Boot 3.4.0、Spring Framework 6.2.0。固定版本用于复现实验，不代表当前最新版或生产升级建议。Boot 2 的自动配置注册方式、Boot 3 的 Jakarta 迁移、Boot 4 的模块变化不能混用。
>
> 容器、代理与事务见 [[02-Spring与微服务/Spring/Spring核心原理|Spring核心原理]]；HTTP 请求链见 [[02-Spring与微服务/Spring/SpringMVC|SpringMVC]]。本文集中解释 Boot 如何选择和组装基础设施，以及如何验证这些选择。

## 目录

- [[#1. Boot 解决的是默认组装与运行问题]]
- [[#2. 依赖、扫描和自动配置是三条不同路径]]
- [[#3. SpringApplication 的启动时序]]
- [[#4. 自动配置如何从候选变成 Bean]]
- [[#5. ActionGuard：整组选择与单项退让]]
- [[#6. 外部配置：来源、覆盖与 Profile]]
- [[#7. 类型安全绑定与失败前置]]
- [[#8. 自研 Starter 的边界与测试矩阵]]
- [[#9. 执行器、调度与优雅关闭]]
- [[#10. 排障：从缺失 Bean 到可服务状态]]
- [[#11. 实验与源码阅读]]

## 1. Boot 解决的是默认组装与运行问题

Spring 提供容器、事务、MVC 等机制，但单独使用这些模块时，项目还要选择兼容依赖、注册基础设施、加载环境配置、创建 Web 容器并建立运维入口。Boot 把这部分重复工作变成有条件的默认配置。

因此，Boot 不会改变 Java 的对象模型，也不会让事务绕过代理。`@SpringBootApplication` 不等于“所有框架功能都自动启用”：例如提供执行器的自动配置与启用 `@Async` 拦截是两件事。

| 组成 | 负责什么 | 不应推导出的结论 |
| --- | --- | --- |
| 依赖管理 BOM | 管理一组依赖版本 | 项目随意覆盖一个版本仍保证兼容 |
| Starter | 提供常用依赖组合 | 只要依赖存在就必定创建某个 Bean |
| 自动配置 | 根据类路径、配置和已有 Bean 注册默认定义 | 容器会持续按运行时配置热切换全部对象 |
| SpringApplication | 协调环境、上下文、刷新和启动回调 | `main` 返回前所有外部系统已经可用 |
| Actuator | 提供管理端点、健康与观测集成 | 健康探针已经覆盖所有业务正确性 |

以医生助手为例，应用可以复用数据库连接池、Web 转换器和配置绑定，但“高风险工具必须先审批”“患者数据按机构隔离”仍由业务与安全设计实现。

## 2. 依赖、扫描和自动配置是三条不同路径

### 2.1 先有兼容的类路径，再谈条件装配

Starter 通常通过传递依赖引入自动配置模块和客户端实现；BOM 提供版本约束，不能代替实际声明依赖。应用使用 Boot parent 或导入 BOM 后，仍需声明所用 Starter。

遇到 `NoSuchMethodError`、类缺失或 Jakarta/Javax 类型不兼容，先看实际解析出的依赖树和冲突来源。修改 `@ComponentScan` 通常不能修复二进制版本冲突。

在本实验工程中：

```bash
mvn dependency:tree
mvn help:effective-pom
```

第一条用于确认实际依赖，第二条用于看继承与管理后的配置。不要把示例中的固定旧版本当作业务项目的升级结论；生产升级还需核查安全维护周期、第三方兼容与回归结果。

### 2.2 三类注册入口

`@SpringBootApplication` 组合了 Boot 配置标识、组件扫描和自动配置启用。

- **应用组件扫描**：从启动类所在包向下发现组件；启动类放错包可能漏扫，也可能扫进测试或不相关配置。
- **显式导入**：`@Import`、选择器、注册器等把指定配置或定义加入容器。
- **自动配置导入**：从约定元数据得到候选配置，再经过筛选与条件判断。

普通组件扫描不会天然把依赖包里所有带注解的类全部导入。自研 Starter 应通过自动配置元数据注册，不应要求业务方扫描第三方库的大包名。

### 2.3 Boot 3 的自动配置注册文件

Boot 3.4 的候选文件是：

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

内容为每行一个自动配置类全限定名，例如：

```text
com.example.guard.autoconfigure.ActionGuardAutoConfiguration
```

旧教程把自动配置类写到 `spring.factories` 的 `EnableAutoConfiguration` 键下，是版本相关的历史方式；不能把它当成 Boot 3 的备用自动配置注册方式。`spring.factories` 仍用于其他扩展机制，“自动配置不再用该键”不等于“整个文件失效”。

## 3. SpringApplication 的启动时序

可以先按职责看，再跟源码，而不是背一串方法名：

```text
构造 SpringApplication，确定应用类型与扩展
  → 准备 Environment，读取配置数据与启动参数
  → 创建对应 ApplicationContext
  → 应用初始化器，加载应用配置源
  → refresh：解析定义、处理扩展、创建基础设施和对象
  → 上下文刷新完成，发布启动阶段事件
  → 执行 ApplicationRunner / CommandLineRunner
  → 发布就绪阶段事件，进入可服务状态
```

容器创建细节回到核心文。Web 应用刷新期间会创建和启动嵌入式服务器；**端口已经监听不等于所有 Runner 完成、业务已经就绪**。流量接入应关注应用就绪状态及探针策略。

`ApplicationRunner` 接收解析后的 `ApplicationArguments`，`CommandLineRunner` 接收字符串数组。两类 Runner 可以排序，但不要靠“Bean 文件顺序”推断执行顺序，也不要在 Runner 中无限阻塞地执行后台消费循环。

### 3.1 启动事件能观察哪些阶段

| 观察点 | 适合做什么 | 注意事项 |
| --- | --- | --- |
| 环境准备 | 观察配置来源、激活环境 | 完整 Bean 容器尚不可用 |
| 上下文初始化/准备 | 添加定义或观察装配准备 | 不要提前拉起大量普通 Bean |
| 刷新后、Runner 前 | 观察上下文启动 | 仍可能在 Runner 中失败 |
| Ready | 应用启动回调完成 | 下游随时仍可故障，需持续健康监测 |
| Failed | 汇总启动失败 | 早期失败不能只依赖容器内 `@EventListener` |

需要接收早期事件的监听器应通过 `SpringApplication` 注册等对应扩展入口加入，而不是假设组件扫描已经发生。事件的时间戳是事件发生时间，不能直接当“总启动耗时”；计时应明确起终点或使用该版本提供的阶段耗时信息。

### 3.2 启动慢要拆分证据

先区分配置加载、类扫描与解析、Bean 初始化、服务器启动、Runner、外部连接握手。条件报告解释“为什么装配/没装配”，不负责完整度量每个阶段耗时。

`ApplicationStartup` 可记录启动步骤，结合支持的实现与 Actuator startup 端点或 JFR 分析。采集本身也有成本；不要在启动线程逐个打印完整 Bean 对象，`toString()` 可能触发额外初始化甚至访问敏感数据。

## 4. 自动配置如何从候选变成 Bean

### 4.1 配置解析和定义注册不是一次判断

以 `@EnableAutoConfiguration` 导入链为主线，选择器读取候选、排除显式 exclusions、过滤明显不匹配的配置，再在配置解析和注册阶段应用具体条件。`@ConditionalOnClass`、`@ConditionalOnBean` 等并不全在同一时刻完成判断。

理解两个阶段尤其有用：配置类是否继续解析，与其内部 Bean 定义是否可以注册。Bean 条件依赖当时已经处理的定义，因此自动配置的顺序会影响条件观察到什么。

`@AutoConfiguration(before/after = ...)` 调整的是**自动配置定义的处理顺序**。实例何时创建仍由依赖关系、懒加载和容器流程决定，不是把自动配置排序直接变成所有 Bean 的构造顺序。

### 4.2 常见条件与误判

| 条件 | 判断对象 | 常见坑 |
| --- | --- | --- |
| `@ConditionalOnClass` | 类路径上的指定类型 | 配置方法签名过早引用可选类型，条件尚未保护就加载失败 |
| `@ConditionalOnMissingBean` | 已处理的 Bean 定义/类型信息 | `@Bean` 返回类型过于宽泛，条件识别不符合预期 |
| `@ConditionalOnProperty` | Environment 中的属性 | 把绑定对象里的默认值当作 Environment 属性 |
| `@ConditionalOnWebApplication` | 应用上下文/Web 类型 | Servlet 与 Reactive 的条件混为一谈 |
| `@ConditionalOnResource` | 指定资源存在与否 | 资源存在并不保证内容有效 |

对于可选第三方类型，可将有关 Bean 方法放入受类路径条件保护的独立配置中，避免在不满足条件的场景仍要求 JVM 解析其方法类型。排查需要同时看“类能否加载”和“条件是否命中”。

`@ConditionalOnProperty` 默认语义不是简单的布尔类型转换：在未指定 `havingValue` 时，通常是属性存在且不等于 `false`；集合属性也不能按普通单值属性随意推断。关键开关应明确 `havingValue` 与缺失行为。

排除自动配置适合明确不需要整个能力、或由应用完整接管的情况，可通过对应注解排除项或 `spring.autoconfigure.exclude` 表达。排除某个上游配置可能连带让下游条件失效；缺少一个 Bean 时先查原因，不应反复 exclude 直到错误消失。

### 4.3 退让、覆盖、选择是三件事

- **退让**：`@ConditionalOnMissingBean` 让默认定义不注册。
- **覆盖**：同名定义冲突时是否允许后者替换前者，是容器策略；Boot 默认不鼓励依靠覆盖解决冲突。
- **选择**：多个候选已存在时，`@Primary`、`@Qualifier` 等影响注入选择。

声明了 `@Primary` 不会删除默认 Bean，也不保证默认 Bean 停止初始化；允许覆盖不等于按类型退让。Starter 优先提供清晰的按类型退让契约，业务需要多个实现时再用限定符表达意图。

## 5. ActionGuard：整组选择与单项退让

以下沿用原笔记的 ActionGuard 设计示例，不声称已验证某个生产组件。设组件有待审批任务仓储、审批记录仓储，以及共享的存储类型配置。

```yaml
action:
  guard:
    store:
      type: memory
      timeout: 2s
```

### 5.1 类级条件选方案，方法级条件让用户替换

一种设计是内存配置类上使用 `@ConditionalOnProperty(prefix="action.guard.store", name="type", havingValue="memory")`，类内每个仓储方法再使用 `@ConditionalOnMissingBean(对应接口.class)`。

含义是：先选择整套内存方案，再在每个能力上允许业务提供实现。如果业务只替换任务仓储，审批记录仍可用默认仓储。这种灵活性也引入风险：两个仓储是否要求同事务、同数据源？如果要求，却允许混搭，组件接口就隐含了无法兑现的一致性保证。

因此需先明确替换单位：可独立替换时按单个接口退让；必须成组时通过聚合 SPI 或启动校验约束完整组合。不要只为了“扩展方便”把全部 Bean 都无条件开放替换。

### 5.2 未配置 type，不等于自动选择 memory

设 `@ConfigurationProperties` 的 `type` 默认值是 `memory`，但 `@ConditionalOnProperty` 没有 `matchIfMissing=true`。配置绑定后对象可以读到 `memory`，条件仍会因为 Environment 中没有该属性而不匹配。

实验 `AutoConfigurationTest` 专门验证了这个差异。要让缺失时默认选择，必须让装配契约与属性契约一致，例如显式采用 `matchIfMissing=true`；如果要求用户必须选择存储，缺失就应该以清晰错误失败。

原笔记中的启动失败来自显式校验逻辑，不能归因于条件注解“自动报错”。`@ConditionalOnProperty` 不匹配通常只是跳过注册。

### 5.3 条件不是运行时热开关

修改配置中心的 type，并不会自动销毁旧仓储、替换对象图、迁移内存数据。普通条件在容器构建阶段起作用。运行时切换需要独立设计路由、数据一致性、连接清理及并发切换策略。

对审批任务来说，从 memory 切到 JDBC 还涉及未完成任务持久化和重复执行防护。即使 Bean 能被替换，也没有证明任务状态已经安全迁移。

## 6. 外部配置：来源、覆盖与 Profile

### 6.1 查最终值，也查来源

Boot 将多个来源组织成 Environment，后加入且优先级更高的来源可覆盖前面的同名属性。常见生产场景中，命令行参数通常能覆盖系统属性、环境变量和配置文件；测试还可引入优先级更高的测试属性来源。完整顺序应查所用版本的官方表，不要背一条省略测试、JSON 和配置数据阶段的全局公式。

配置文件还受外部/包内、Profile 文件、导入位置、位置分组与加载顺序影响。同目录混用 `.properties` 和 YAML 会增加认知负担，统一格式并查看实际来源更可靠。

`spring.config.location` 用于指定配置位置时会替换默认搜索位置；要在默认位置之外增加配置，使用 `spring.config.additional-location`。误用前者会表现为“本地默认配置突然不见了”。`optional:` 表示允许该位置缺失，不是忽略文件内容中的全部错误。

### 6.2 Profile 是装配条件，不是完整隔离环境

Profile 可以选择配置文档与 `@Profile` Bean。`@Profile("!prod")` 是一个否定条件，并不意味着剩余每个环境都适合开启测试能力。对危险调试功能优先明确允许环境，避免新增环境时意外启用。

激活 Profile 的配置应放在合法的非 Profile 专属来源中，避免在已经由 Profile 激活的文档里反向声明激活规则。Profile group 可组织组合，但不要制造隐式的多层激活迷宫。

测试替身和生产实现同时注册时，先确认激活环境、扫描范围和条件报告；不能仅加 `@Primary` 把冲突藏起来。数据库地址、认证凭据、日志与管理端口仍需单独隔离，Profile 名字本身不提供安全边界。

### 6.3 脱敏与配置诊断

排查配置问题可记录来源名、是否存在和非敏感摘要，不应打印整份 Environment。管理端点的访问控制与敏感值展示策略需要单独配置；“仅内网可访问”不等于可以公开密钥。

## 7. 类型安全绑定与失败前置

配置应优先映射成职责明确的 `@ConfigurationProperties` 对象，而不是在几十个类里散布 `@Value` 字符串。

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties("action.guard.store")
public record GuardProperties(
        @DefaultValue("memory") String type,
        @DefaultValue("2s") Duration timeout) {
}
```

通过 `@EnableConfigurationProperties(GuardProperties.class)` 或配置属性扫描注册。使用构造器绑定的配置对象，不应再机械地当普通组件走无关的组件创建路径。上例与实验里的属性模型一致，但没有承担完整生产校验。

关键边界：

1. `Duration`、`DataSize` 等带单位的类型减少“这个 30 是秒还是毫秒”的歧义；仍应明确允许范围。
2. 校验需要校验实现依赖及 `@Validated` 等合适入口；Boot 3 的 Web Starter 不应被当作已经显式引入 validation Starter。
3. 嵌套对象要触发级联校验，需要正确使用 `@Valid`，不能只在最外层写一次 `@Validated` 就假设所有内层约束都生效。
4. record 限制字段重新赋值，不会自动深度冻结其中的可变集合；需要防御性复制或不可变值设计。
5. 绑定失败应报告具体属性与约束，同时避免把密钥原值写进异常日志。

配置元数据处理器可改善 IDE 提示，它不等于运行时验证器。程序能启动也不证明超时、池容量和外部服务地址在业务上合理。

## 8. 自研 Starter 的边界与测试矩阵

### 8.1 模块职责

可按需要区分纯 API/核心实现、自动配置模块、Starter 依赖聚合。小组件不必为形式拆出过多模块，但核心业务接口应尽量避免依赖 Boot 的启动过程。

自动配置应具有明确前缀、可解释的默认值、稳定替换点、资源销毁责任和失败消息。不要默认扫描业务包、偷偷注册全局过滤器或无界线程池，更不要让引入依赖就自动连接生产服务执行破坏性动作。

### 8.2 用 ApplicationContextRunner 验证装配

`ApplicationContextRunner` 创建小上下文，适合验证条件、默认值、用户定义优先与失败报告。最基本的矩阵包括：

| 场景 | 应验证的结果 |
| --- | --- |
| 属性缺失 | 明确是退让、默认注册还是启动失败 |
| 属性为支持值 | Bean 数量、类型与绑定值正确 |
| 属性为不支持值 | 不应静默落到意外实现 |
| 用户已有同类型实现 | 默认实现退让，其他必要能力仍存在 |
| 可选依赖不存在 | 不因类加载提前失败 |
| 多个自动配置组合 | 条件和定义处理顺序符合契约 |
| 关闭上下文 | 自建执行器、连接、调度资源被正确关闭 |

配套实验覆盖前四项的精简契约。它通过 `AutoConfigurations.of(...)` 直接导入类，**没有验证发布后的 JAR 是否正确携带 imports 文件**。发布 Starter 还应增加打包后消费者应用测试，确认依赖、资源文件和真实扫描路径。

## 9. 执行器、调度与优雅关闭

自动配置执行器要结合应用类型、已有 Bean、名称与条件理解。业务不能只因为注入了某个 `Executor` 就假设它同时承担 MVC 异步、`@Async` 与所有后台任务。

审批执行、消息通知和慢速报告生成应按隔离需求划分容量与拒绝语义。共用一个无界队列会把流量突增变成持续堆积；共用过小的连接池会让任务线程全部阻塞在取连接上。先估算请求并发、任务耗时、数据库连接和下游限流，再设置线程与队列。

启用虚拟线程也不会增加数据库连接数、下游配额或消除线程绑定事务的边界。采用虚拟线程前要重新观察阻塞点、上下文传递和关闭行为，而不是只比较线程创建成本。

优雅关闭应协调入口停止接流、在途请求、后台任务、消息消费、事务完成与资源关闭。Boot 的 Web 服务器关闭配置不等于所有自建线程都被等待；容器销毁回调、执行器关闭策略与部署平台终止宽限期必须配合。

## 10. 排障：从缺失 Bean 到可服务状态

| 现象 | 先看什么 | 常见错误修法 |
| --- | --- | --- |
| 找不到某个 Bean | 类路径、扫描范围、条件报告、属性来源 | 扩大扫描到所有第三方包 |
| 同类型 Bean 歧义 | Bean 名与来源、用户实现、退让条件 | 全部加 Primary |
| 配置类默认值正确但 Bean 未注册 | Environment 属性与条件缺失策略 | 误以为属性绑定会回写 Environment |
| 启动慢 | 阶段耗时、外部连接、初始化与 Runner | 把所有 Bean 改懒加载后宣布解决 |
| 启动成功但第一批请求失败 | Ready、缓存预热、连接就绪、探针 | 只检查端口已开放 |
| 退出后进程不结束 | 非守护线程、调度器、销毁回调 | 直接隐藏泄漏而不明确所有权 |

懒加载会把部分初始化错误和耗时推迟到首次使用，可能降低表面启动时间，但需要评估首次请求延迟、故障暴露时机和容量准备。

健康、存活与就绪也要区别。短暂下游故障是否应该让所有实例重启，取决于恢复模型；把共享数据库波动直接映射成全实例存活失败，可能造成重启风暴。

## 11. 实验与源码阅读

[[02-Spring与微服务/Spring/示例/spring-mechanism-lab/README|Spring 机制实验]] 的 `AutoConfigurationTest` 验证属性缺失、显式选择、用户实现退让与不支持值。容器部分则用实验区分 full/lite 配置，避免把 `@Bean` 方法调用误读成普通业务 AOP。

阅读源码时围绕具体问题：

| 问题 | 入口 |
| --- | --- |
| 谁协调启动阶段 | `SpringApplication.run` |
| 自动配置候选从哪里来 | `AutoConfigurationImportSelector`、`ImportCandidates` |
| 属性为什么没命中 | `OnPropertyCondition` |
| 默认 Bean 为什么没退让 | `OnBeanCondition` 与定义处理顺序 |
| 配置绑定与转换如何完成 | `Binder`、配置属性绑定后处理器 |
| 条件结果如何诊断 | `ConditionEvaluationReport` |

官方依据：[Boot 3.4 自动配置开发](https://docs.spring.io/spring-boot/3.4/reference/features/developing-auto-configuration.html)、[外部配置](https://docs.spring.io/spring-boot/3.4/reference/features/external-config.html)、[SpringApplication](https://docs.spring.io/spring-boot/3.4/reference/features/spring-application.html)。源码可从 [Boot v3.4.0](https://github.com/spring-projects/spring-boot/tree/v3.4.0) 固定标签开始，避免跟随 main 分支解释旧项目。

继续阅读：[[02-Spring与微服务/Spring/Spring学习路线图|学习路线]] · [[02-Spring与微服务/Spring/Spring核心原理|核心机制]] · [[02-Spring与微服务/Spring/SpringMVC|MVC 请求链]] · [[02-Spring与微服务/Spring/Spring-Q|自测问题]]。
