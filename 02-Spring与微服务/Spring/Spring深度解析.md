# 目录

1. [[#IOC/Bean生命周期|IOC/Bean生命周期]]
2. [[#AOP|AOP]]
3. [[#事务（@Transactional 深水区：传播、回滚、失效、并发）|事务（@Transactional 深水区：传播、回滚、失效、并发）]]
4. [[#Spring Boot 自动配置（原理 + 扩展点 + 排障）|Spring Boot 自动配置（原理 + 扩展点 + 排障）]]
5. [[#MVC / Web（链路、扩展点、性能与安全）|MVC / Web（链路、扩展点、性能与安全）]]
6. [[#并发、线程池、可观测性（高级岗位很爱问）|并发、线程池、可观测性（高级岗位很爱问）]]
7. [[#源码/设计题（真正“深度加分”）|源码/设计题（真正“深度加分”）]]

> [!info] 文档定位：进阶知识主文
>
> 本文假定你已掌握 [[Spring|《Spring》]] 中的 IOC/DI、Bean 生命周期、循环依赖、AOP 与事务基础。这里不以“定义背诵”为目标，而是解释源码切入点、严格时序、代理和缓存的一致性、版本/实现边界，以及生产中的设计取舍。
>
> | 主题 | 先读基础主文 | 本文重点 |
> | --- | --- | --- |
> | 容器、DI 与循环依赖 | `Spring` 的循环依赖、生命周期、IOC/DI、`refresh()` | BFPP/BPP 时序、早期引用与 AOP 代理一致性 |
> | AOP | `Spring` 的 AOP 工作原理 | Advisor/Interceptor 链、JDK/CGLIB 边界、AspectJ 取舍 |
> | 事务 | `Spring` 的事务失效与事务调用链概览 | 传播、隔离、线程绑定、Outbox 与生产故障处理 |
> | Boot 与运行时能力 | `SpringBoot` 的自动配置基础 | 条件装配、starter 设计、Web 链路、并发与可观测性 |

## 阅读方式

1. 基础概念不清楚时先回到 [[Spring|《Spring》]]，不要跳过前置知识硬背结论。
2. 本文每一题优先掌握“机制 → 边界 → 生产决策”，源码方法名用于定位而非机械记忆。
3. 与基础文同主题时，本文是进阶解释的唯一维护位置；基础文只保留概览、常见用法与排障入口。

# IOC/Bean生命周期
## 1. Bean 从 BeanDefinition 到可用的完整生命周期有哪些关键节点？哪些扩展点在哪一段执行（BFPP/BPP）
- 结论（标准答案）
  - Spring 把一个 Bean 从“定义（BeanDefinition）”变成“可用对象（ready-to-use singleton/prototype）”，核心经过：注册定义 → 容器刷新 → 扩展点处理（BFPP/BPP）→ 实例化 → 属性填充（依赖注入）→ 初始化 → 放入单例池/返回给调用方 → 销毁回调。
  - BFPP（BeanFactoryPostProcessor）发生在“实例化任何普通 Bean 之前”，用于“改 BeanDefinition/改容器”；BPP（BeanPostProcessor）发生在“Bean 实例创建过程中（初始化前后）”，用于“改 Bean 实例/包装代理”。

- 生命周期关键节点（按 refresh() 主线，面试讲这条最稳）
  - 1) BeanDefinition 载入/注册（阶段：容器准备期）
    - 来源：@ComponentScan、@Configuration/@Bean、XML、ImportSelector、Registrar、自动配置等
    - 产物：BeanDefinitionRegistry 中持有所有 BeanDefinition（此时还没 new 对象）
  - 2) refresh() 启动容器刷新（阶段：容器启动期）
    - prepareRefresh：准备环境、校验、初始化容器状态
    - obtainFreshBeanFactory：拿到/刷新 BeanFactory（本质是 DefaultListableBeanFactory）
    - prepareBeanFactory：注册一些基础设施（ClassLoader、内置 resolvers、Aware 接口处理器等）
  - 3) 执行 BFPP（阶段：实例化普通 Bean 之前，最关键扩展点之一）
    - invokeBeanFactoryPostProcessors
      - BeanDefinitionRegistryPostProcessor（BDRPP）优先：可以“新增/删除/修改 BeanDefinition”（例如 ConfigurationClassPostProcessor）
      - 普通 BeanFactoryPostProcessor：可以“修改 BeanDefinition 属性”（例如 PropertySourcesPlaceholderConfigurer 解析占位符）
  - 4) 注册 BPP（阶段：实例化普通 Bean 之前，先把“改对象的人”准备好）
    - registerBeanPostProcessors：把所有 BeanPostProcessor 实例化并按优先级排序注册到 BeanFactory
    - 关键点：BPP 自身也是 Bean，会被提前创建；这一步完成后，后续创建的普通 Bean 才会被 BPP 处理
  - 5) 初始化消息源、事件广播器、onRefresh（阶段：容器能力组件就绪）
    - initMessageSource / initApplicationEventMulticaster / onRefresh
    - registerListeners：注册 ApplicationListener
  - 6) 实例化单例 Bean（阶段：真正创建对象，生命周期“主战场”）
    - finishBeanFactoryInitialization → preInstantiateSingletons：触发所有非懒加载单例创建
    - 对单个 Bean：AbstractAutowireCapableBeanFactory#doCreateBean 典型流程：
      - 6.1 createBeanInstance（实例化 Instantiation）
        - 构造器注入发生在这里（autowireConstructor）
      - 6.2 **addSingletonFactory（三级缓存：允许提前暴露 early reference，用于循环依赖）**
      - 6.3 populateBean（属性填充 Populate properties）
        - setter/字段注入发生在这里（AutowiredAnnotationBeanPostProcessor 参与）
      - 6.4 initializeBean（初始化 Initialization）
        - Aware 回调：BeanNameAware/BeanFactoryAware/EnvironmentAware 等
        - BPP before：postProcessBeforeInitialization（常见：@PostConstruct 前后、注入检查等）
        - init 方法：@PostConstruct、InitializingBean#afterPropertiesSet、自定义 init-method
        - BPP after：postProcessAfterInitialization（最重要：AOP 代理通常在这里包装返回代理对象）
      - 6.5 注册销毁回调（Destruction）
        - DisposableBean、@PreDestroy、destroy-method（对单例生效，prototype 通常不由容器统一销毁）
      - 6.6 放入一级缓存 singletonObjects（单例最终可见）
  - 7) 发布 ContextRefreshedEvent（阶段：容器可对外服务）
    - finishRefresh：发布事件、暴露生命周期状态

- BFPP / BPP 分段执行表（面试一张表讲清楚）
  - BFPP（BeanFactoryPostProcessor）
    - 执行时机：Bean 实例化之前（准确说：普通 Bean 大规模实例化之前）
    - 作用对象：BeanDefinition / BeanFactory（“改图纸/改工厂”）
    - 常见实现：
      - ConfigurationClassPostProcessor（属于 BDRPP）：解析 @Configuration/@ComponentScan/@Import，注册更多 BeanDefinition
      - PropertySourcesPlaceholderConfigurer：解析 ${} 占位符、把值写回 BeanDefinition
  - BPP（BeanPostProcessor）
    - 执行时机：Bean 创建过程中，初始化前后都会回调
    - 作用对象：Bean 实例（“改成品/加壳”）
    - 关键回调点：
      - postProcessBeforeInitialization：初始化前（常用于注入校验、填充、@PostConstruct 周边）
      - postProcessAfterInitialization：初始化后（AOP 代理、包装器最常发生在这里）
    - 常见实现：
      - AutowiredAnnotationBeanPostProcessor：处理 @Autowired/@Value（主要发生在属性填充阶段，严格说它也会参与 populateBean 流程）
      - CommonAnnotationBeanPostProcessor：处理 @PostConstruct/@PreDestroy
      - AbstractAutoProxyCreator（AOP）：在 afterInitialization 返回代理对象

- 追问：BeanFactoryPostProcessor vs BeanPostProcessor 的执行时机与典型用途？为什么能“改 Bean”？
  - 时机差异
    - **BFPP：Bean 实例化前，拿到的是“定义（BeanDefinition）”，所以能改属性值、Scope、依赖关系，甚至新增定义**
    - **BPP：Bean 实例化过程中，拿到的是“对象实例”，所以能反射改字段、做包装代理、替换返回对象**
  - 为什么能“改”
    - Spring 把“创建 Bean”拆成多步，并在每步暴露 hook；BFPP/BPP 是容器内建的 hook 链
    - BFPP 改的是“未来将如何创建这个 Bean”；BPP 改的是“这个 Bean 创建出来之后长什么样”
  - 典型用途对比（生产落地）
    - BFPP：集中化配置占位符、批量修改 BeanDefinition（灰度开关、默认值注入）、动态注册 Bean（SDK/starter）
    - BPP：AOP（鉴权/日志/限流/事务）、统一注入（TraceId/MDC）、Bean 增强（代理、装饰器）

- 生产级注意事项（能拿分）
  - 启动慢/Bean 多：preInstantiateSingletons 会把所有非懒加载单例都拉起来；BPP 太多、代理太多会显著拉长启动时间与内存占用
  - 循环依赖：三级缓存发生在 doCreateBean 早期（实例化后、属性填充前），构造器循环依赖很难靠这套解
  - 可观测性：定位启动问题优先看 “哪个 BFPP/BPP 最慢、哪个 Bean 初始化最慢”（可开 debug/trace 或用启动分析器/日志钩子）

- 小结（一句话复盘）
  - BFPP 是“改图纸（BeanDefinition）”，BPP 是“改成品（Bean 实例）”；整体生命周期沿 refresh() 主线走：先注册定义→先跑 BFPP→再注册 BPP→再批量创建单例（实例化→填充→初始化→代理）→最终可用。

---

## 2. 解释 Spring 的三级缓存（singletonObjects / earlySingletonObjects / singletonFactories）各自存什么、解决什么问题？
- 结论（标准答案）
  - 三级缓存是 Spring 为了解决“单例 Bean 在创建过程中的可见性与循环依赖（主要是 setter/字段注入）”引入的分层状态机：一级放最终成品，二级放提前暴露的半成品引用，三级放生成早期引用的工厂（可延迟、可生成代理早期引用）。核心目标：**在“实例化完成但尚未属性填充/初始化”这个窗口，把引用先暴露出去，打破 A→B→A 的依赖死结，同时避免不必要的提前暴露与重复代理**。

- 三层分别存什么（你得能一句话讲清）
  - 1) singletonObjects（一级缓存）
    - 存：完全初始化完成的单例 Bean（final singleton）
    - 解决：正常单例复用与快速获取（绝大多数 getBean 直接命中这里）
  - 2) earlySingletonObjects（二级缓存）
    - 存：提前暴露的“早期单例引用”（early reference）
      - 典型是：实例化完成、但尚未完成属性填充/初始化的对象引用
      - 在有 AOP 时，可能是“早期代理引用”（取决于是否需要提前生成代理）
    - 解决：循环依赖中的“提前拿到 A 的引用”，让 B 能注入 A，从而继续创建链路
  - 3) singletonFactories（三级缓存）
    - 存：ObjectFactory（能生成 early reference 的工厂）
      - 不是直接放对象，而是放“生成对象引用的逻辑”，需要时再调用 getObject()
    - 解决：
      - 延迟生成 early reference：只有真正有人需要（发生循环依赖）才创建 early
      - 处理 AOP 场景：通过工厂在 early 阶段调用 getEarlyBeanReference，有机会返回“代理/包装后的引用”，保证后续注入拿到的是同一个“最终形态”

- 解决了什么问题（面试官要听到的关键词）
  - 解决问题 1：setter/字段注入导致的单例循环依赖
    - A 依赖 B（字段/Setter），B 又依赖 A（字段/Setter）
    - Spring 可以：先实例化 A（还没注入 B），把 A 的引用提前暴露 → 去创建 B 时能注入 A → B 创建完成后回头给 A 注入 B → 完成闭环
  - 解决问题 2：AOP 代理与循环依赖的相容性
    - 如果 A 最终需要被代理（事务/切面），那注入到 B 里的 A 应该尽量是“同一个形态”（通常期望是代理）
    - 三级缓存的 ObjectFactory 允许在 early 阶段生成“早期代理引用”，避免 B 拿到原始对象、最终 A 变成代理后出现“引用不一致”的尴尬
  - 解决问题 3：性能与并发正确性
    - 不在所有 Bean 创建时都提前暴露（否则开销大、生命周期更复杂）
    - **仅在确实发生循环依赖时，通过三级工厂按需生成 early reference；并用全局锁与 double-check 保证只生成一次、状态迁移一致**

- 三级缓存的典型状态迁移（你讲这个就很像懂行的）
  - 创建单例 A 的 doCreateBean 过程里（关键窗口：实例化后、属性填充前）：
    - 1) 实例化 A（构造器执行完）得到 raw A
    - 2) 提前暴露：singletonFactories.put("A", factory)（放三级）
    - 3) 若 B 创建时需要 A，则 getSingleton("A", true)：
      - 先查一级 singletonObjects：没有
      - 再查二级 earlySingletonObjects：没有
      - 再查三级 singletonFactories：有 → factory.getObject() 生成 early A（可能走 getEarlyBeanReference 产出 early proxy）
      - 放入二级 earlySingletonObjects，并移除三级 singletonFactories（避免重复生成）
    - 4) A 完成属性填充与初始化（BPP/AOP 等）
    - 5) A 最终成品放入一级 singletonObjects，同时清理二级/三级的残留条目

- 为什么不只用二级缓存（为什么一定要三级）
  - 若只有二级“提前对象引用”，就意味着必须在实例化后立刻把对象引用放进二级——这会导致：
    - 无差别提前暴露（很多根本不会循环依赖的 Bean 也被提前暴露），增加复杂度与风险
    - AOP 场景更麻烦：你无法在“需要时”再决定生成代理引用，容易让依赖方拿到 raw bean，最终 bean 变代理后引用不一致
  - **三级的意义就是“把是否生成 early reference 的决定推迟到真正需要的时候”，并且把“生成逻辑”抽象成工厂，便于插入 AOP 的 early reference 逻辑**

- 边界与不适用（一定要说，不然像背书）
  - 构造器循环依赖（constructor injection）通常无法解决
    - 因为构造器注入要求依赖在实例化之前就必须就绪，无法在实例化后再提前暴露引用来打破死结
  - prototype（原型）Bean 的循环依赖通常也不靠这套解
    - 三级缓存主要服务单例创建流程；prototype 每次创建新对象，缓存语义不同

- 生产级注意事项（加分）
  - 循环依赖能跑≠设计合理：它是一种“容器兜底机制”，容易隐藏架构问题（职责耦合、模块边界不清）
  - AOP + 循环依赖的坑：有时会出现“注入到某处的是原对象而不是代理”的诡异现象，排查思路就是看：是否发生 early reference，是否触发 getEarlyBeanReference，是否存在自调用绕过代理等
  - 并发与 double-check：getSingleton 里对一级/二级做锁外读 + 锁内确认读，是为了避免并发窗口导致重复生成 early reference 或缓存迁移错乱

- 小结（一句话复盘）
  - 一级存最终单例、二级存早期引用、三级存早期引用工厂；它们共同解决 setter/字段注入的单例循环依赖，并让 AOP 代理在循环依赖场景下尽量保持引用一致，同时兼顾性能（按需提前暴露）与并发正确性（double-check + 单锁保护迁移）。

---

## 3. 为什么 setter 循环依赖能解决，而构造器循环依赖通常不行？“通常”在哪些条件下可以绕过？
- 结论（标准答案）
  - setter/字段注入的循环依赖之所以能解，是因为 Spring 能在“实例化之后、属性填充之前”把对象引用提前暴露（三级缓存 early reference），让另一个 Bean 先拿到引用继续创建；而构造器注入的循环依赖通常解不了，**因为构造器在实例化阶段就必须拿到完整依赖，Spring 没机会在对象还没 new 出来前提前暴露引用。**
  - “通常”之所以加引号，是因为有少数条件可以绕过：把其中一条依赖从“强依赖（构造器参数必须有）”变成“可延迟解析/可代理的依赖”，就能打破死结。

- setter/字段循环依赖为什么能解（核心时序）
  - 关键时间窗口：doCreateBean 内部的“实例化 → 提前暴露 → 属性填充”
  - 典型链路（A ↔ B）
    - 1) 创建 A：先实例化 A（构造器执行完，但属性还没注入）
    - 2) Spring 把 A 的 early reference 暴露出去（singletonFactories → earlySingletonObjects）
    - 3) 创建 B 时需要注入 A：从二级/三级缓存拿到 A 的 early reference，于是 B 能完成实例化与属性填充
    - 4) B 完成后回头给 A 注入 B，A 再初始化，最终进入 singletonObjects（一级缓存）
  - 本质：setter/字段注入允许“先有对象壳子，再补依赖”，所以容器可以用提前暴露引用打破环

- 构造器循环依赖为什么通常不行（核心差异）
  - 构造器注入发生在 createBeanInstance/autowireConstructor 阶段：必须先解析构造参数
  - 对 A 而言，要 new A 必须先拿到 B；对 B 而言，要 new B 必须先拿到 A
  - 此时“对象壳子”都没创建出来，三级缓存也没法提前暴露引用（因为暴露发生在实例化之后），所以会卡死并抛出 BeanCurrentlyInCreationException 之类异常

- “通常”在哪些条件下可以绕过（你在面试里这么讲最靠谱）
  - 绕过思路 1：把其中一个构造器依赖变成“延迟获取”
    - 方式：ObjectProvider/Provider/Lazy 注入（让依赖在真正使用时再解析）
    - 原理：构造器里注入的不是 B 本体，而是一个“延迟句柄/代理”，从而允许 A 先构造出来
    - 注意：这不是“消灭循环依赖”，而是把依赖解析推迟到运行期；如果你在构造器/初始化阶段立刻调用它，仍可能触发循环
  - 绕过思路 2：把依赖打断为接口 + 代理（让一边拿到可用的代理）
    - 方式：A 依赖 B 的接口，B 在容器中可被代理/延迟实例化（具体实现还是靠 Lazy/ObjectProvider 或者某些代理机制）
    - 本质：还是“把强依赖变弱依赖”，让构造器阶段只拿到代理
  - 绕过思路 3：重构（生产最推荐）
    - 把环拆掉：引入第三方协调者/事件驱动/领域服务拆分，消除 A↔B 的双向依赖
    - 原因：循环依赖能跑不代表设计健康，容易造成隐蔽耦合和初始化顺序雷

- 顺便回答追问：AOP 代理介入循环依赖时，暴露的是原对象还是代理？为什么要 getEarlyBeanReference？
  - 结论
    - 可能是“原对象”，也可能是“代理”，取决于是否在 early 阶段触发了 AOP 的 early reference 机制；Spring 为了在循环依赖场景下尽量保证注入到别处的引用与最终形态一致，引入了 getEarlyBeanReference 这条钩子。
  - 关键机制
    - 在 doCreateBean 里，Spring 会把一个 ObjectFactory 放进 singletonFactories（三级缓存）
    - 当发生循环依赖、需要 early reference 时，会调用这个 factory.getObject()
    - factory 内部会走 getEarlyBeanReference（典型由 AbstractAutoProxyCreator 等实现），有机会把 raw bean 包装成 early proxy
  - 为什么需要 getEarlyBeanReference
    - 目标：避免“B 注入了 raw A，但最终 A 变成 proxy A”导致引用不一致
    - 典型后果：事务/切面在 B 里调用注入的 A 时不生效（拿到的是原对象），或者同一个 Bean 在系统里出现“原对象/代理对象”两份引用，行为不一致
  - 现实中的坑位（你说出来很加分）
    - 即使有 early proxy，也不是所有场景都能保证一致（例如某些时机下代理生成晚了，或自调用绕过代理）
    - 排查抓手：看是否触发 earlySingletonObjects/singletonFactories，是否走过 AbstractAutoProxyCreator#getEarlyBeanReference，以及最终 singletonObjects 里放的是谁

- 小结（一句话复盘）
  - setter 能解是因为“先实例化再填充”允许提前暴露引用；构造器通常不行是因为“先要依赖才能实例化”没有提前暴露窗口；绕过靠把强依赖变延迟/代理或直接重构拆环；AOP 为了保证循环依赖时引用一致，会通过 getEarlyBeanReference 在 early 阶段尽可能暴露代理而不是原对象。

---

## 4. @Autowired 的注入解析规则是什么？按类型冲突时 Spring 怎么选？@Primary、@Qualifier、@Resource 的差异？
- 结论（标准答案）
  - @Autowired 默认按“类型”注入，必要时结合“名称/Qualifier/Primary/优先级”做二次决策；冲突（同类型多个候选）时，Spring 会按一套固定优先级去缩小候选集合，最终选出一个或报错 NoUniqueBeanDefinitionException。
  - @Primary 是“默认赢家”，@Qualifier 是“点名指定”，@Resource（JSR-250）更偏“先按名、再按类型”，语义和使用习惯与 @Autowired 有明显差别。
  - required=false / Optional / ObjectProvider 解决的是“依赖可能不存在”或“需要延迟/按需获取/多候选遍历”的问题，属于生产里很实用的解耦工具。

- @Autowired 注入解析规则（按决策顺序讲，面试最好这样背）
  - 1) 找候选 Bean（Candidate Set）
    - 先按注入点的“类型”找所有可赋值的 Bean（包含子类、实现类）
    - 过滤：排除不满足条件的（例如 autowire-candidate=false、条件装配未生效等）
  - 2) 处理特殊注入点（直接短路）
    - 注入类型是数组/集合/Map：不是选一个，而是收集一组
      - List/Set：收集所有同类型候选，按顺序规则排序后注入
      - Map：key 是 beanName，value 是实例
    - 注入点带 @Lazy/ObjectProvider/Optional：走延迟/可选语义（后面详述）
  - 3) 如果候选只有 1 个：直接注入
  - 4) 如果候选 > 1：按优先级缩小到唯一
    - 4.1 @Qualifier（以及“限定符匹配”）最强：先按限定符把候选集过滤到更小
    - 4.2 如果仍多：看 @Primary（主候选）
    - 4.3 如果仍多：看 beanName 与注入点名称是否匹配（字段名/参数名/属性名）
    - 4.4 如果仍多：可看 `@Priority` 候选；`Ordered/@Order` 主要用于集合注入排序，不应当作单点注入的常规消歧手段
    - 4.5 还不唯一：抛 NoUniqueBeanDefinitionException（除非注入点允许多值/可选）
  - 5) required=true 且找不到候选：抛 NoSuchBeanDefinitionException；required=false/Optional/ObjectProvider 则允许缺失

- 按类型冲突时 Spring 怎么选（给你一个“可直接复述”的版本）
  - 首选：匹配 @Qualifier（含自定义 Qualifier 注解的匹配）
  - 其次：匹配 @Primary
  - 再次：匹配“名称”（注入点名称 == beanName，或 @Qualifier("name")）
  - 再其次：`@Priority` 可能参与候选缩小；集合注入的排序则主要使用 `Ordered/@Order/@Priority`
  - 兜底：仍不唯一就报错（让你显式指定，避免隐式注入带来线上不确定性）

- @Primary、@Qualifier、@Resource 差异（工程落地视角）
  - @Primary
    - 含义：当按类型有多个候选时，默认选择标注了 @Primary 的那个
    - 适用：框架/组件提供默认实现，业务允许覆盖默认实现但不想处处写 Qualifier
    - 风险：多个 @Primary 会冲突；另外“默认赢家”有时会掩盖误注入（建议配合测试/启动校验）
  - @Qualifier
    - 含义：显式限定要注入哪一个（按名称或限定符标签）
    - 适用：同接口多实现（例如多支付通道、多策略、多数据源客户端），要求注入确定实现
    - 优点：可读性强、行为确定；缺点：侵入注入点，改名/重构要同步改 Qualifier
  - @Resource（JSR-250）
    - 默认解析顺序：先按“名称”找（name=字段名/属性名或显式 name），找不到再按“类型”
    - 适用：你更想表达“我要这个名字的 Bean”（例如 legacy 系统、按名约定），或者与某些规范/老代码兼容
    - 与 @Autowired 的核心区别：@Autowired 更“类型优先”，@Resource 更“名称优先”
    - 生产建议：团队统一风格很重要；如果你们以接口类型注入为主，优先用 @Autowired/@Qualifier；@Resource 更多用于“按名强绑定”的场景

- 追问：required=false、Optional、ObjectProvider 的语义与最佳使用场景
  - required=false（@Autowired(required=false)）
    - 语义：依赖不存在时不报错，注入为 null（字段/Setter）或跳过注入
    - 适用：可选组件（监控、可选策略、灰度开关插件）
    - 风险：null 容易把问题推迟到运行期 NPE；生产更推荐 Optional/ObjectProvider 表达语义
  - Optional
    - 语义：依赖存在则 Optional.of(bean)，不存在则 Optional.empty()
    - 适用：明确表达“可选依赖”，业务代码必须显式处理存在/不存在分支
    - 优点：语义清晰；缺点：不适合频繁按需查找多个候选的场景
  - ObjectProvider（或 ObjectFactory）
    - 语义：延迟、按需获取 Bean，可选择 getIfAvailable / getIfUnique / stream() 遍历
    - 适用场景（非常生产）
      - 1) 延迟获取：避免启动期过早初始化、避免循环依赖爆炸（把强依赖变弱依赖）
      - 2) 可选依赖：getIfAvailable() 不存在就返回 null/默认值
      - 3) 多候选策略：stream() 拉一组实现按条件选择（策略模式/插件化）
      - 4) 与 scope 配合：在 request/session scope 下按需取当前上下文 Bean
    - 注意：ObjectProvider 本身是轻量句柄，但你调用 getObject() 可能触发真实 Bean 创建；要避免在构造器/初始化阶段盲目调用导致“延迟变立即”

- 生产级注意事项（面试加分）
  - 同接口多实现强烈建议：默认实现标 @Primary，业务明确选择用 @Qualifier；不要依赖“字段名碰巧匹配 beanName”的隐式规则（重构易炸）
  - 可选依赖优先 Optional/ObjectProvider，减少 null；并为缺失情况提供降级/默认实现
  - 集合注入（List/Map）用于插件化很香，但要控制排序规则（@Order/@Priority），否则实现顺序不稳定会引发线上行为漂移

- 小结（一句话复盘）
  - @Autowired 类型优先，冲突时按 Qualifier → Primary → 名称匹配 → `@Priority` 缩小候选；集合注入再按排序规则排列。@Primary 给默认赢家，@Qualifier 强制点名，@Resource 名称优先；required=false/Optional 解决“可选”，ObjectProvider 解决“可选 + 延迟 + 多候选遍历”，是生产解耦利器。

---
## 5. FactoryBean 和普通 Bean 有什么本质差异？&beanName 是什么？Spring 为什么需要 FactoryBean？
- 结论（标准答案）
  - 普通 Bean：容器创建出来的对象本身就是你要注入/使用的对象。
  - FactoryBean：容器创建的是一个“工厂对象”，但对外暴露（getBean(beanName) 返回）的默认是它生产的对象（getObject() 的结果），而不是工厂对象本身。FactoryBean 是 Spring 提供的“把复杂对象创建过程纳入容器生命周期与依赖注入体系”的机制。
  - &beanName：是 Spring 的一个“转义/前缀语法”，表示“我要拿到 FactoryBean 工厂对象本身”，而不是它生产的产品对象。

- 本质差异（按容器视角拆开讲）
  - 1) getBean("x") 的返回语义不同
    - 普通 Bean：返回 x 实例
    - FactoryBean：默认返回 factory.getObject() 的“产品实例”
  - 2) 容器管理的生命周期对象是谁
    - FactoryBean 本身也是一个 Bean：它会走完整 Bean 生命周期（实例化、依赖注入、初始化、销毁）
    - 由 FactoryBean 生产的对象（产品）也会被容器按规则管理（通常会注册为单例/原型，取决于 isSingleton）
  - 3) 创建控制权不同
    - 普通 Bean：Spring 通过构造器/属性填充直接创建
    - FactoryBean 产品：由 FactoryBean 的 getObject() 决定如何创建（可接入第三方、动态代理、复杂初始化等）

- &beanName 是什么（面试一句话 + 举例）
  - 语义：获取 FactoryBean 自身实例的“转义前缀”
  - 举例：
    - getBean("sqlSessionFactory")：拿到 SqlSessionFactory（产品）
    - getBean("&sqlSessionFactory")：拿到 SqlSessionFactoryBean（工厂本身）
  - 为什么需要：因为默认语义被 FactoryBean 改成“返回产品”，那就必须提供一种方式拿到工厂对象，否则工厂本身不可访问、不可配置/排障。

- Spring 为什么需要 FactoryBean（解决什么工程问题）
  - 1) 让“复杂对象/第三方对象”的创建也能享受 Spring 能力
    - 复杂对象：需要多步构建、依赖多个 Bean、需要读取配置、需要做资源初始化（连接、扫描、代理等）
    - FactoryBean 自己先走依赖注入/生命周期 → 再在 getObject() 里创建产品对象
  - 2) 统一生命周期与可观测性/可替换性
    - 你可以像管理普通 Bean 一样管理这些复杂对象：配置、条件装配、profile、销毁回收
  - 3) 适配“产品不是简单 new 出来的对象”
    - 典型：JDK 动态代理/CGLIB 代理、ORM SessionFactory、RPC Client、Mapper 代理、连接工厂等
  - 4) 延迟与缓存（单例产品）
    - FactoryBean 可以控制产品是否单例（isSingleton），并对产品做内部缓存/懒加载（具体实现可选）

- FactoryBean 关键接口方法（你说出来就很“源码味”）
  - getObject()：生产产品对象
  - getObjectType()：告诉容器产品类型（用于按类型注入/条件判断）
  - isSingleton()：产品是否单例（决定容器是否缓存产品）
  - （常见基类）AbstractFactoryBean、FactoryBeanRegistrySupport 内部维护 factoryBeanObjectCache（产品缓存）

- 追问：MyBatis 的 SqlSessionFactoryBean/MapperFactoryBean 属于哪类？怎么参与容器生命周期？
  - 结论
    - SqlSessionFactoryBean：FactoryBean（生产 SqlSessionFactory 产品）
    - MapperFactoryBean：FactoryBean（生产某个 Mapper 接口的代理对象产品）
  - SqlSessionFactoryBean 怎么参与生命周期（典型流程）
    - 它本身作为 Bean 被创建：依赖注入 DataSource、mapperLocations、typeAliasesPackage 等配置
    - 初始化阶段（afterPropertiesSet 或 init-method）构建 SqlSessionFactory（解析 mybatis-config、加载 mapper xml）
    - getObject() 返回构建好的 SqlSessionFactory（通常单例）
    - 销毁阶段可释放资源（视实现而定；SqlSessionFactory 本身多为轻量，但其依赖资源如 DataSource 由别的 Bean 管）
  - MapperFactoryBean 怎么参与生命周期（典型流程）
    - 它本身作为 Bean 创建：注入 SqlSessionFactory/SqlSessionTemplate、mapperInterface 等
    - 初始化阶段校验 mapperInterface、准备配置
    - getObject() 返回该 Mapper 接口的代理对象（MyBatis 通过 MapperProxy 机制把接口方法映射为 SQL 执行）
    - 产品（Mapper 代理）通常是单例注入到你的 Service 中
  - 容器层面的关键点（面试加分）
    - MapperFactoryBean 的 getObjectType() 能让 Spring 在按类型注入时把“Mapper 接口类型”当成候选，这样你才能 @Autowired 注入某个 Mapper 接口
    - Mapper 扫描（@MapperScan）底层会向容器注册很多 MapperFactoryBean 的 BeanDefinition（这一步常由 ImportBeanDefinitionRegistrar 完成），属于“把定义注册进容器”的那类扩展点（BDRPP/Registrar）

- 生产级注意事项（容易被追问）
  - getObjectType() 返回不准会导致：按类型注入失败、条件装配判断错误（这是写自定义 FactoryBean 常踩坑）
  - isSingleton 与线程安全：产品若非单例，每次 getObject 都创建新对象会有成本与资源泄露风险（比如客户端连接类）
  - 调试技巧：当你怀疑拿到的到底是“工厂”还是“产品”，用 & 前缀验证最直接

- 小结（一句话复盘）
  - FactoryBean 改变了 getBean 的语义：默认返回产品而非工厂；&beanName 用来取工厂本体；它的价值是把复杂对象（如 MyBatis 的 SqlSessionFactory、Mapper 代理）的构建过程纳入 Spring 的依赖注入与生命周期管理，从而获得统一配置、扩展与可观测能力。

---

# AOP
## 1. Spring AOP 的执行链是什么样的（Advisor/Advice/Interceptor）？Around/Before/After/AfterThrowing 的顺序？（含追问：多个切面叠加时顺序怎么控制？@Order 在哪里生效？）
- 结论（标准答案）
  - Spring AOP 在运行时通过代理（JDK/CGLIB）把一组 Advisor 应用到目标方法上；每个 Advisor 本质是“切点 Pointcut + 通知 Advice”。执行时 Advice 会被适配成 MethodInterceptor，所有拦截器按顺序组成一条拦截器链（Interceptor Chain），由 MethodInvocation.proceed() 逐个推进。
  - Around/Before/After/AfterThrowing 的顺序可以理解为：外层 Around 包裹内层调用；Before 在 proceed 前执行；After（finally）在 proceed 后一定执行；AfterReturning 在正常返回后执行；AfterThrowing 在抛异常时执行。多个切面叠加时，链路顺序由 Advisor 排序决定，@Order/Ordered/@Priority 在创建代理与组装拦截器链阶段生效。

- 执行链模型（把抽象名词对齐到“运行态对象”）
  - Pointcut
    - 定义“哪些连接点（方法）会被增强”，例如 execution 表达式、注解匹配等
  - Advice
    - 定义“增强逻辑是什么”，例如 @Before/@After/@Around/@AfterThrowing 等
  - Advisor
    - Pointcut + Advice 的组合体，是 Spring AOP 应用切面的基本单元
  - Interceptor
    - 运行时真正参与调用链的对象，Advice 会被适配为一个或多个 MethodInterceptor
  - Invocation
    - MethodInvocation（ReflectiveMethodInvocation）持有：目标对象、方法、参数、拦截器列表、当前下标；proceed() 会推进拦截器链直到调用目标方法

- 关键类与调用链（源码级骨架，面试讲到这里很稳）
  - 代理入口
    - JDK 动态代理：InvocationHandler#invoke
    - CGLIB：MethodInterceptor#intercept
  - 获取拦截器链
    - AdvisedSupport#getInterceptorsAndDynamicInterceptionAdvice(method, targetClass)
    - 通过 AdvisorChainFactory 把匹配的 Advisor 转为 MethodInterceptor 列表（并按顺序组装）
  - 执行拦截器链
    - ReflectiveMethodInvocation#proceed()
      - 如果还有下一个 interceptor：调用该 interceptor.invoke(invocation)
      - 否则：反射调用目标方法

- 单个切面内部各通知的真实落点（Advice 如何变成 Interceptor）
  - @Around
    - 直接对应一个 MethodInterceptor（通常是 AspectJAroundAdvice）
    - 它控制是否/何时调用 invocation.proceed()
  - @Before
    - 适配为 MethodBeforeAdviceInterceptor
    - 在 proceed 之前执行
  - @AfterReturning
    - 适配为 AfterReturningAdviceInterceptor
    - 在 proceed 正常返回后执行
  - @AfterThrowing
    - 适配为 ThrowsAdviceInterceptor 或 AspectJAfterThrowingAdvice
    - 在 proceed 抛异常时执行
  - @After（finally）
    - 在 AspectJ 语义里属于“最终通知”，通常表现为一个 after（finally）型拦截器或在 around 结构里保证 finally 执行
    - 无论正常返回还是异常都会执行

- Around/Before/After/AfterThrowing 的执行顺序（用“嵌套栈”记最不容易错）
  - 假设只有一个切面，且同时定义了 @Around、@Before、@After、@AfterReturning、@AfterThrowing，则对一次方法调用：
    - 1) Around（进入，proceed 之前的部分）
    - 2) Before
    - 3) 目标方法执行（由链路推进到终点）
    - 4a) 正常返回路径：
      - AfterReturning
      - After（finally）
      - Around（退出，proceed 之后的部分）
    - 4b) 异常路径：
      - AfterThrowing
      - After（finally）
      - Around（退出，proceed 之后的部分；如果 Around 捕获并吞掉异常则可能转为正常返回）
  - 关键认知点
    - After（finally）一定执行（除非 JVM 崩溃/进程被 kill）
    - AfterReturning 与 AfterThrowing 二选一（除非 Around 捕获异常并转换成返回值）
    - Around 是“包裹层”，相当于你手写 try/catch/finally 包住 proceed()

- 多个切面叠加时的整体顺序（追问 1：顺序怎么控制）
  - 规则（面试可复述）
    - “外层切面”先进入 Around，再进入“内层切面”，最终按栈结构反向退出
    - 进入顺序取决于 Advisor 的排序结果：排序靠 Ordered/@Order/@Priority 等；同优先级再按注册顺序等因素
  - 直观示例（两个切面 A、B）
    - 若 A 的优先级更高（排序更靠前，通常表现为 order 值更小），则调用表现为：
      - A.Around(enter)
      - A.Before
      - B.Around(enter)
      - B.Before
      - target()
      - B.AfterReturning 或 B.AfterThrowing
      - B.After(finally)
      - B.Around(exit)
      - A.AfterReturning 或 A.AfterThrowing
      - A.After(finally)
      - A.Around(exit)
  - 生产建议
    - 把“安全/鉴权/租户隔离/审计”放外层（更早拦截、失败更快）
    - 把“性能监控/日志埋点”也常放外层（覆盖全链路）
    - 把“业务补偿/降级兜底”视需求放在合适层级（尤其注意异常吞掉会影响事务回滚与上游感知）

- @Order 在哪里生效（追问 2：@Order 生效点与作用对象）
  - 生效点（容器启动期/代理创建期）
    - Spring 在为目标 Bean 创建代理时，会收集所有匹配该方法的 Advisor，并对 Advisor 排序
    - 排序依据来自：
      - Advisor/Advice 实现 Ordered 接口
      - 注解 @Order（通过 OrderComparator 解析）
      - 注解 @Priority（JSR-250，亦可参与排序）
    - 排序完成后，才生成该方法的拦截器链（Interceptor List），此时顺序固定
  - 作用对象（你贴 @Order 到哪里）
    - 常见写法：@Aspect 类上加 @Order，影响该切面生成的 Advisor 的优先级
    - 某些场景：Advisor/Bean 自身实现 Ordered 也可
  - 排序方向（容易被追问的点）
    - order 值越小通常优先级越高（更靠外层、进入更早、退出更晚）
    - 同 order 值的相对顺序不应该依赖，最好显式区分 order，避免线上行为漂移

- 生产级注意事项（面试加分）
  - Around 里吞异常会改变链路语义
    - 可能导致 @AfterThrowing 不执行，甚至导致事务不回滚（因为异常被吃掉）
    - 规范：除非你明确要把异常转换为业务返回，否则不要随便 catch 并吞掉
  - 代理边界导致 AOP 失效
    - 同类自调用、final/private、非 Spring 管理对象绕过代理，这些都会让执行链根本进不来
  - 性能与可观测性
    - 切面过多会显著增加调用栈深度与分配开销，P99 可能抖动；建议对关键路径做压测与链路追踪验证

- 小结（一句话复盘）
  - Spring AOP 以 Advisor（Pointcut+Advice）为单位匹配方法，再把 Advice 适配成 MethodInterceptor 组装成拦截器链，由 proceed() 串行推进；Around 外层包裹、Before 在前、After(finally)必执行、AfterReturning/AfterThrowing 依返回/异常分支；多切面顺序由 Advisor 排序决定，@Order/Ordered/@Priority 在代理创建时生效，order 越小通常越外层。

---

## 2. JDK 动态代理 vs CGLIB：选择条件、性能差异、对 final/private 的限制是什么？（含追问：为什么同类方法自调用会导致 AOP 失效？生产上你如何结构化修复？）
- 结论（标准答案）
  - JDK 动态代理基于接口（InvocationHandler），只能代理“接口方法”；CGLIB 基于继承生成子类（MethodInterceptor），可以代理“没有接口的类”，但无法覆盖 final 方法，且对 private 方法无能为力（private 不可覆写，调用也不走子类拦截）。
  - 性能上现代 JVM 下两者差距通常不再是决定性因素：真正影响更大的往往是“切面数量、拦截器链深度、反射/参数装箱、目标方法本身耗时”。选择应以“是否有接口、是否需要代理类、是否有 final 限制、框架兼容性”优先。
  - 同类自调用 AOP 失效的根因是“绕过代理”：this.xxx() 是对目标对象内部方法的直接调用，不经过代理对象，所以拦截器链不会触发。生产修复应优先用结构重构：拆分 Bean 边界，确保调用从外部进入代理。

- 选择条件（Spring 默认策略与可控开关）
  - 默认选择策略（常见语义）
    - 目**标类实现了至少一个接口：优先用 JDK 动态代理（只代理接口方法）**
    - **目标类没有接口：使用 CGLIB（生成子类代理）**
  - 强制使用 CGLIB 的常见方式
    - 开启类代理：如 @EnableAspectJAutoProxy(proxyTargetClass = true) 或 Boot 中相关配置
  - 何时更推荐哪个
    - 更推荐 JDK 动态代理
      - 你的服务天然有清晰接口（Service/Facade），希望代理边界显式、稳定
      - 避免 CGLIB 对 final 的限制与字节码增强带来的调试复杂度
    - 更推荐 CGLIB
      - 类没有接口或不想暴露接口
      - 需要代理类本身（例如某些框架内部按具体类类型做判断/注入；不过这类场景要谨慎评估）

- 机制差异（面试要点：代理如何拦截）
  - JDK 动态代理
    - 生成一个实现同样接口的代理类
    - 接口方法调用进入 InvocationHandler#invoke → 组装拦截器链 → proceed → 调用目标对象
  - CGLIB
    - 生成目标类的子类，重写可重写的方法
    - 方法调用进入 MethodInterceptor#intercept → 组装拦截器链 → proceed → 调用父类/目标逻辑

- final / private 限制（必须精准）
  - final 类
    - CGLIB 无法生成子类代理（不能继承 final 类）→ 直接失败或回退（视框架策略）
    - JDK 代理不关心类是否 final，因为它代理的是接口
  - final 方法
    - CGLIB 无法重写 final 方法 → 该方法无法被拦截增强（切面不会生效）
    - JDK 代理：只要是接口方法，是否 final 与否不相关（接口方法本身不存在“final 覆写”概念）
  - private 方法
    - CGLIB 无法拦截 private 方法：private 方法不可覆写，且通常是静态绑定调用
    - JDK 代理：只能拦截接口方法，private 不在接口上也拦截不到
  - static 方法（额外加分点）
    - 两者都无法以 Spring AOP 的运行时代理方式拦截 static（除非 AspectJ 编译期/加载期织入）

- 性能差异（面试要讲“现实主义”）
  - 启动期成本
    - CGLIB 需要生成子类字节码，类加载与生成成本更高（但通常是一次性的）
    - JDK 代理生成也有成本，但一般更轻
  - 运行期成本（现代 JVM 下）
    - 代理调用的固定开销主要来自：拦截器链推进、参数处理、反射/MethodHandle 调用路径、异常栈等
    - 真实系统里：AOP 层开销常被业务逻辑/IO/SQL 掩盖；但在极高 QPS 的纯内存路径上，切面数量会明显影响 P99
  - 生产建议
    - 不要为了“代理性能”盲选；优先控制切面数量与粒度，避免在热点路径堆满环绕通知
    - 对关键链路用压测与火焰图验证，不要凭感觉

- 追问：为什么同类方法自调用会导致 AOP 失效？
  - 根因：代理只拦截“进入代理对象的外部调用”
    - AOP 生效前提：调用必须走代理对象（Proxy）
    - 同类内部调用是 this.xxx()，本质是对目标对象方法的直接调用，绕过代理，因此不会经过拦截器链
  - 典型表现
    - 外部调用 publicMethod() 能生效
    - publicMethod() 内部调用 transactionalMethod()/aspectMethod() 不生效（事务不生效、日志切面不打印等）

- 生产上如何结构化修复（给你可落地的优先级）
  - 首选：拆分职责到独立 Bean（推荐做法）
    - 把需要 AOP 的方法抽到另一个 @Service/@Component 中
    - 让调用变为“跨 Bean 调用”，自然经过代理
    - 优点：无侵入、结构清晰、可测试、可演进
  - 次选：通过参数注入/事件驱动解耦（适用于复杂链路）
    - 将内部调用改为发布领域事件/应用事件，由监听器（单独 Bean）处理，需要事务边界时用 @TransactionalEventListener 等
    - 优点：更符合边界与最终一致性设计；缺点：引入异步/事件复杂度
  - 不推荐但可用的兜底手段
    - 注入自身代理（Self injection）：在类中注入自身接口/类型的代理再调用（容易绕晕、维护成本高）
    - AopContext.currentProxy()：强侵入、依赖 exposeProxy，容易在异步/非代理线程下出坑
  - 特别针对事务的建议
    - 将 @Transactional 放在“对外的应用服务层边界”上，而不是深层内部私有方法
    - 避免把事务边界藏在内部自调用里（非常难排障）

- 小结（一句话复盘）
  - JDK 代理靠接口，CGLIB 代理靠继承；CGLIB 不能代理 final 类/方法，private/static 也拦不到；性能差异在现代 JVM 下通常不是主矛盾，切面链深度才是；自调用失效是因为绕过代理，生产修复优先拆分 Bean 边界让调用经过代理，兜底才考虑 self proxy/AopContext。

---

## 3. Spring AOP 和 AspectJ（编译期/加载期织入）区别是什么？为什么大多数业务只用 Spring AOP？（含追问：哪些场景你会考虑 AspectJ？）
- 结论（标准答案）
  - Spring AOP 是“运行时代理式 AOP”：只对 Spring 容器管理的 Bean 生效，主要拦截 public 方法调用，织入点发生在方法调用经过代理时；优势是简单、可控、侵入小、与 Spring 生命周期天然集成。
  - AspectJ 是“字节码织入式 AOP”：可在编译期（CTW）或类加载期（LTW）把增强逻辑直接织入目标类字节码，理论上可拦截更广的连接点（包括 private、构造器、静态方法等，取决于织入点表达式与配置），不依赖代理调用路径；代价是构建/运行链路更复杂，对排障与运维要求更高。
  - 大多数业务只用 Spring AOP 的原因：业务需求多集中在“服务层方法边界”（事务、日志、鉴权、限流、审计），这些用代理就足够；而 AspectJ 的复杂度、构建集成与运行风险通常不划算。

- 核心差异对比（面试最清晰的维度）
  - 生效范围
    - Spring AOP：仅 Spring 管理的 Bean；通常只拦截通过代理进入的方法调用
    - AspectJ：可作用于任意类（不一定是 Spring Bean），只要字节码被织入即可
  - 织入时机
    - Spring AOP：运行时生成代理（JDK/CGLIB），调用时走拦截器链
    - AspectJ：
      - CTW（Compile-Time Weaving）：编译期织入，产物字节码已包含增强逻辑
      - LTW（Load-Time Weaving）：类加载时织入（基于 javaagent/类加载器织入）
  - 可拦截的连接点（Join Point）能力
    - Spring AOP：主要是“方法执行”这一类 join point（method execution），且通常要求 public（代理边界）
    - AspectJ：join point 更丰富（方法调用/执行、构造器、字段读写、异常处理、静态初始化等），并可织入 private/static（不依赖覆写/接口）
  - 调用路径依赖
    - Spring AOP：强依赖“调用是否经过代理”
      - 同类自调用、new 出来的对象、private/final/static 等常导致不生效
    - AspectJ：不依赖代理，织入后对调用路径更鲁棒
  - 运维与排障复杂度
    - Spring AOP：简单，问题定位集中在代理边界与拦截器链
    - AspectJ：复杂，需关注编译/织入配置、类加载、agent、与框架/容器的兼容性、以及线上可观测性与回滚策略

- 为什么大多数业务只用 Spring AOP（工程落地原因）
  - 1) 需求匹配：绝大多数横切需求是“服务层边界”
    - 事务、日志、鉴权、审计、限流、埋点、缓存等，代理拦截 public service 方法已足够
  - 2) 成本与风险更低
    - 不需要引入 weaver/agent，不需要改构建链路，不需要处理类加载织入的兼容性与调试难度
  - 3) 与 Spring 生态天然集成
    - 事务（@Transactional）、缓存（@Cacheable）、安全（Spring Security）等都基于 Spring AOP 的代理模型，心智成本统一
  - 4) 可控性强
    - 代理只作用于 Bean 边界，增强范围相对可控；AspectJ 若配置不当可能扩大织入面，导致性能/行为风险

- 典型限制（你说出来就是“懂边界”）
  - Spring AOP 的限制
    - 只能拦截通过代理调用的 public 方法
    - 同类自调用绕过代理
    - private/static 方法拦截不到；final 方法在 CGLIB 下也无法覆写拦截
  - AspectJ 的限制（不是万能）
    - 引入编译期/加载期织入链路，构建与运行更复杂
    - 对容器/框架版本、类加载机制更敏感
    - 排障难度更高（“为什么织入没生效/织入过度/类冲突”）

- 追问：哪些场景你会考虑 AspectJ（以及为什么）
  - 1) 需要拦截非 Spring 管理对象
    - 场景：大量对象由第三方库/手工 new 创建（SDK、旧代码、领域模型），但你仍需要横切能力（监控/审计/校验）
    - 代理做不到，因为对象不在容器里；AspectJ 可直接织入类
  - 2) 需要拦截 private/static/构造器/字段访问等代理难以覆盖的点
    - 场景：必须对 private 方法也做统一埋点/校验，或对构造器做对象创建统计
    - 代理模型无法覆盖（private 不可覆写，static 不走实例方法分派）
  - 3) 需要消除“自调用失效”且不想重构
    - 场景：遗留系统大量内部调用链，重构成本极高，但必须保证事务/审计/埋点覆盖
    - AspectJ 因为不依赖代理调用路径，可以覆盖内部调用
  - 4) 极端性能/一致性需求下的“更低边界开销”或“更强一致覆盖”
    - 场景：希望在极其细粒度的连接点上织入且保证覆盖一致（例如全链路埋点到私有方法级别）
    - 但注意：AspectJ 并不必然更快，织入点选择不当反而更慢；必须压测与火焰图验证
  - 5) 框架/平台级能力建设（而不是普通业务项目）
    - 场景：公司级 APM/安全审计 agent、统一字节码增强平台
    - 这类场景有专门的构建与运维能力承接 AspectJ/字节码增强的复杂度

- 生产级取舍建议（面试加分）
  - 业务系统优先 Spring AOP：边界清晰、可控、和 Spring 生态一致
  - 只有在“代理模型确实覆盖不了 + 重构不可行 + 团队能承接织入复杂度”的情况下再选 AspectJ
  - 采用 AspectJ 时必须提前规划：
    - 构建链路（CTW）或运行链路（LTW/agent）
    - 织入范围白名单化（避免全量织入导致性能风险）
    - 可观测性与回滚方案（如何快速关闭织入/回退构建产物）

- 小结（一句话复盘）
  - Spring AOP 是运行时代理，简单可控但受代理边界限制；AspectJ 是字节码织入，覆盖更广但复杂度更高；业务多数横切需求在服务层边界，代理足够且风险更低，所以通常只用 Spring AOP；当需要对非容器对象或 private/static/内部调用链做强覆盖时，才会考虑 AspectJ。

---

# 事务（@Transactional 深水区：传播、回滚、失效、并发）

> 本章默认讨论命令式 JDBC/MyBatis 事务：`DataSourceTransactionManager` 通过 `TransactionSynchronizationManager` 的 `ThreadLocal` 绑定连接与同步回调。Reactive 事务使用 `ReactiveTransactionManager` 并依赖 Reactor Context 传播事务状态；不要把本章“换线程即断事务”的结论直接套用到 Reactor 链路。

## 1. Spring 事务是怎么工作的？TransactionInterceptor 到 DataSourceTransactionManager 的关键调用链是什么？（含追问：TransactionSynchronizationManager 为什么要 ThreadLocal？这对异步有什么影响？）
- 结论（标准答案）
  - Spring 声明式事务本质是 AOP：@Transactional 让目标方法在代理上被 TransactionInterceptor 拦截；拦截器读取事务属性（传播/隔离/回滚规则等），委派给 PlatformTransactionManager（JDBC/MyBatis 场景通常是 DataSourceTransactionManager）完成“获取连接→关闭 autoCommit→绑定线程→提交/回滚→清理释放连接”的全过程。
  - TransactionSynchronizationManager 使用 ThreadLocal 绑定 Connection 与事务同步回调，是为了保证同一线程内的多次 DAO 调用共享同一个物理连接/事务上下文；代价是事务上下文默认不会自动跨线程传播，所以异步（@Async/线程池/CompletableFuture）会天然“断事务”，需要显式设计边界与一致性方案。

- 工作流程（按一次方法调用时序拆解）
  - 1) 调用进入代理（Proxy）
    - 目标方法被 Advisor 命中（事务切点），进入 TransactionInterceptor
  - 2) 解析事务属性
    - TransactionAttributeSource 读取 @Transactional（类/方法合并）得到 TransactionAttribute
      - propagation / isolation / timeout / readOnly / rollbackRules
  - 3) 选择事务管理器
    - determineTransactionManager：默认用容器里唯一的 PlatformTransactionManager；多数据源时可通过 @Transactional(transactionManager="xxx") 指定
  - 4) 创建或加入事务
    - PlatformTransactionManager#getTransaction(definition)
      - 传播行为 REQUIRED/REQUIRES_NEW/NESTED 在 AbstractPlatformTransactionManager 内分支处理（挂起/恢复/保存点等）
      - 对 JDBC：最终走到 DataSourceTransactionManager#doBegin，拿到 Connection 并设置事务属性
  - 5) 执行业务方法
    - invocation.proceed() 执行目标方法
    - MyBatis/JDBC 获取连接时会通过 Spring 的绑定资源拿到“同一个 Connection”，因此多次 SQL 处于同一个事务
  - 6) 正常返回：提交
    - TransactionInterceptor → commitTransactionAfterReturning → PlatformTransactionManager#commit
      - 若 rollback-only 则转回滚或抛 UnexpectedRollbackException（取决于状态）
      - 否则 DataSourceTransactionManager#doCommit → connection.commit()
  - 7) 异常抛出：回滚
    - TransactionInterceptor → completeTransactionAfterThrowing
      - 根据回滚规则（默认 RuntimeException/Error）决定 rollback 或 commit
      - DataSourceTransactionManager#doRollback → connection.rollback()
  - 8) 清理资源
    - 解绑 ThreadLocal、恢复连接属性（autoCommit/隔离级别/只读标记）、释放连接回连接池
    - 触发事务同步回调（afterCommit/afterCompletion）

- 关键调用链（TransactionInterceptor → DataSourceTransactionManager）
  - 代理拦截入口
    - TransactionInterceptor#invoke(MethodInvocation)
      - → TransactionAspectSupport#invokeWithinTransaction(method, targetClass, invocationCallback)
  - 事务创建/获取（传播行为总控）
    - TransactionAspectSupport#createTransactionIfNecessary(...)
      - → PlatformTransactionManager#getTransaction(definition)
      - → AbstractPlatformTransactionManager#getTransaction(...)
        - → doGetTransaction()
        - → isExistingTransaction(...) / handleExistingTransaction(...)（处理 REQUIRED/REQUIRES_NEW/NESTED）
        - → doBegin(...)（真正开启事务）
  - JDBC 事务开启（最常考）
    - DataSourceTransactionManager#doBegin(...)
      - 从 DataSource 获取 Connection（通常来自 Hikari）
      - DataSourceUtils.prepareConnectionForTransaction(con, definition)（隔离级别/只读 hint）
      - con.setAutoCommit(false)
      - TransactionSynchronizationManager.bindResource(dataSource, connectionHolder)（绑定到线程）
  - 提交/回滚
    - AbstractPlatformTransactionManager#commit(...)
      - → processCommit → doCommit(status) → DataSourceTransactionManager#doCommit → con.commit()
    - AbstractPlatformTransactionManager#rollback(...)
      - → processRollback → doRollback(status) → DataSourceTransactionManager#doRollback → con.rollback()
  - 清理（释放连接、解绑线程）
    - DataSourceTransactionManager#doCleanupAfterCompletion(...)
      - TransactionSynchronizationManager.unbindResource(dataSource)
      - 恢复 autoCommit、隔离级别
      - DataSourceUtils.releaseConnection(con, dataSource)

- 追问：TransactionSynchronizationManager 为什么要 ThreadLocal？
  - 目的 1：同线程共享同一物理事务资源
    - 事务对 JDBC 来说最终落在 Connection 上；ThreadLocal 绑定 ConnectionHolder 可以让同一线程中的多个 DAO 调用复用同一个 Connection，从而处于同一事务边界
  - 目的 2：事务同步回调的线程一致性
    - afterCommit/afterCompletion 等回调需要在“事务完成的同一线程上下文”执行，ThreadLocal 是最简洁可靠的绑定方式
  - 目的 3：避免侵入业务代码传递 Connection/TxContext
    - 业务层无需显式传 Connection，容器统一管理，开发体验与可维护性更好

- 这对异步有什么影响（非常高频的生产追问）
  - 影响 1：事务上下文默认不跨线程传播
    - @Async/线程池/CompletableFuture 会在新线程执行，ThreadLocal 里没有绑定的 Connection
    - 结果：异步方法中的数据库操作要么开启了“新事务”（如果它自己标了 @Transactional），要么以 autoCommit=true 方式独立提交
  - 影响 2：一致性风险（典型事故）
    - 外层事务未提交时就触发异步读取：异步线程读不到未提交数据（RC/RR 下都读不到），出现“读写不一致”
    - 外层事务回滚了，但异步线程已把某些副作用提交/发出：出现“部分成功”的不一致
  - 影响 3：排障特征
    - 日志/trace 显示同一请求链路里出现多个独立事务（不同连接、不同 txId），且顺序错乱
  - 生产级修复策略（结构化）
    - 最推荐：把异步副作用放到 afterCommit 再触发
      - 使用 TransactionSynchronization 或 @TransactionalEventListener(phase = AFTER_COMMIT) 发布事件，提交后再异步处理（发 MQ/通知/索引更新）
    - 需要异步但要一致性：采用 Outbox/事务消息表
      - 本地事务内写业务表 + outbox 表，提交后异步投递，消费端幂等
    - 避免“在事务里起异步线程做 DB 写”
      - 如果一定要做，明确异步方法自己的事务边界（REQUIRES_NEW）并评估连接池压力与锁竞争

- 小结（一句话复盘）
  - 对命令式 JDBC/MyBatis 而言，Spring 事务=代理拦截+事务模板：TransactionInterceptor 解析 @Transactional 并调用 DataSourceTransactionManager 在 JDBC 层开启/提交/回滚；TransactionSynchronizationManager 用 ThreadLocal 绑定 Connection 与回调以保证同线程共享事务资源，因此异步天然断开该上下文。Reactive 事务改由 Reactor Context 传播，需使用对应的 ReactiveTransactionManager 与响应式操作符设计边界。

---

## 2. 传播行为 REQUIRED / REQUIRES_NEW / NESTED 的语义差异与典型业务使用场景？（含追问：REQUIRES_NEW 的连接池/锁副作用与规避）
- 结论（标准答案）
  - REQUIRED：默认传播行为；“有事务就加入，没有就新开”，因此一条调用链上的多个 REQUIRED 方法通常共享同一个物理事务，成败同生共死。
  - REQUIRES_NEW：无论外层是否有事务，都“挂起外层事务，开启一个全新事务”；内外事务互不影响，内层可以独立提交/回滚。
  - NESTED：在同一个物理事务里创建保存点（Savepoint）；内层回滚只回到保存点，不影响外层继续执行（前提：底层支持保存点，且通常要求 JDBC/DataSourceTransactionManager 场景）。
  - 选择原则：**业务主链路用 REQUIRED 保证原子性；需要“独立落库”的副作用用 REQUIRES_NEW；需要“局部回滚但不拆物理事务”的少量场景可用 NESTED（但团队常规不推荐滥用）**。

- 语义差异（用“外层事务存在”这一前提对比）
  - REQUIRED
    - 外层有事务：加入外层（同一个 Connection/同一个 Tx）
    - 外层无事务：创建新事务
    - 结果：内层异常触发回滚（若未被吞）通常会导致整个事务回滚；或至少把外层标记 rollback-only
  - REQUIRES_NEW
    - 外层有事务：挂起外层（suspend），新开一个事务（新 Connection）
    - 外层无事务：创建新事务
    - 结果：内层提交/回滚不影响外层是否提交（除非你显式把异常向外抛并让外层也回滚）
  - NESTED
    - 外层有事务：创建保存点 Savepoint（仍是同一个 Connection）
    - 外层无事务：行为通常退化为 REQUIRED（新建事务），具体取决于实现与配置
    - 结果：内层回滚回到保存点，外层仍可继续；外层最终决定整体 commit/rollback

- 典型业务使用场景（生产落地）
  - REQUIRED（主流程原子性）
    - 下单：创建订单 + 扣减库存（同库）+ 记录支付单（同库）需要“一起成功一起失败”
    - 写多张强一致表：订单主表/明细表/流水表
    - 更新缓存/写扩展表放到事务外或 afterCommit 触发，避免扩大事务时间
  - REQUIRES_NEW（独立事务的“旁路副作用”）
    - 审计/操作日志：主业务失败也要记录“失败原因/请求参数/审计轨迹”
    - 失败补偿登记：主流程回滚也要把“补偿任务”落库（便于异步重试）
    - 幂等记录/防重表：有时需要独立提交“我处理过了”的标记（但要小心业务语义）
    - 注意：如果你把关键业务步骤放在 REQUIRES_NEW，可能破坏整体原子性（主流程回滚但旁路已提交）
  - NESTED（同物理事务内的“局部可回滚”）
    - 批处理/循环处理：希望某一条失败只回滚该条，不影响同一事务内其它步骤继续（但最终还是外层事务决策）
    - 某些复杂流程：希望尝试性写入，失败回滚到保存点继续走其他分支
    - 团队实践：多数业务会用“拆事务 + 最终一致性/补偿”替代 NESTED，因为保存点语义对新人不友好、排障成本高

- 行为差异的关键点（面试官常追问）
  - rollback-only 的传播
    - REQUIRED：内层抛出需回滚异常，通常会把同一个事务标记 rollback-only，外层即使 catch 住也可能在 commit 时抛 UnexpectedRollbackException
    - REQUIRES_NEW：内层回滚只回滚自己的事务，不会把外层标记 rollback-only（除非外层因捕获后再抛导致外层也回滚）
    - NESTED：内层回滚到保存点，不等价于整个事务回滚；外层仍可提交（提交时会包含保存点之前与之后的操作）
  - 连接层面
    - REQUIRED/NESTED：通常复用同一个 Connection（同物理事务）
    - REQUIRES_NEW：需要新的 Connection（新物理事务），外层 Connection 会被挂起

- 追问：REQUIRES_NEW 会带来哪些连接池/锁方面的副作用？如何规避？
  - 副作用 1：连接池压力（最常见）
    - 表现：外层事务占用一个连接不释放，同时内层 REQUIRES_NEW 又要再占用一个连接；嵌套层数越多，占用连接越多
    - 风险：连接池耗尽（Hikari active 接近 max，pending 增大），请求排队，P99 抖动甚至雪崩
    - 规避：
      - 降低 REQUIRES_NEW 使用频率与嵌套深度；把“日志/审计/通知”改为 afterCommit 异步或 Outbox
      - 合理设置连接池 maxPoolSize，并用监控（active/pending/borrow time）压测校准
      - 避免在大循环里对每条记录开 REQUIRES_NEW（会造成连接风暴），改为批量落库或异步队列
  - 副作用 2：锁竞争与死锁概率上升
    - 表现：外层事务持有锁未释放，内层新事务又去访问相同资源（同表/同行）可能被阻塞或形成死锁
    - 典型坑：外层更新某行未提交，内层 REQUIRES_NEW 也更新同一行 → 内层等待锁；若内层持有其他锁与外层互相等待 → 死锁
    - 规避：
      - 设计上避免内外事务访问同一行/同一热点资源（尤其是更新）
      - 缩小外层事务范围：把 IO/远程调用移出事务，减少锁持有时间
      - 用统一的锁顺序与合适索引，减少锁范围；必要时拆分表/去热点
  - 副作用 3：语义不一致（业务层面更隐蔽）
    - 表现：内层事务已提交，但外层事务最终回滚，系统出现“旁路成功、主流程失败”的状态
    - 规避：
      - 只把“允许独立存在”的副作用放入 REQUIRES_NEW（审计日志/补偿登记），不要把“必须与主流程一致”的核心状态放进去
      - 对外可见行为（发消息/推送/回调）尽量 afterCommit 或通过 Outbox 保证一致性

- 小结（一句话复盘）
  - REQUIRED 共享事务，适合主流程原子性；REQUIRES_NEW 挂起外层新开事务，适合独立落库的审计/补偿，但会增加连接占用与锁竞争并可能引入语义不一致；NESTED 用保存点做局部回滚，适用面较窄且排障成本高，生产上多用 afterCommit/Outbox/补偿模式替代。

---

## 3. @Transactional 为什么会失效？列出至少 5 种，并给出生产级修复方案。（含追问：为什么非 public 常失效？为什么 catch 异常不抛会导致提交？）
- 结论（标准答案）
  - @Transactional 失效的根因可以归为两类：1）调用没有经过 Spring 代理（拦截器链根本没进来）；2）进了代理但事务决策/边界不符合预期（异常规则、传播行为、事务管理器选择等导致“看起来没生效”）。生产修复要优先用“结构化边界”解决（拆 Bean/明确事务边界/明确异常与回滚规则），不要用 AopContext 之类侵入式手段硬顶。

- 至少 5 种常见失效原因（给你 10 条，面试随便抽）
  - 1) 同类自调用（this.xxx()）
    - 现象：外部调用事务生效，内部调用标注 @Transactional 的方法不生效
    - 原因：绕过代理，未进入 TransactionInterceptor
    - 修复（推荐优先级）
      - 抽到独立 Bean（最推荐）
      - 或事件驱动/消息驱动，把事务边界放到应用服务层
      - 兜底：注入自身代理/ AopContext.currentProxy（不推荐，侵入且易踩坑）
  - 2) 方法可见性或可代理性不满足条件
    - 现象：看起来加了 @Transactional，但实际无事务或不回滚
    - 原因：JDK 动态代理只能拦截接口的 public 方法；Spring 6 的类代理默认也可拦截 protected/package-private 方法，但 private、final 方法仍不可由子类代理覆盖。跨版本、跨代理策略时可见性差异会使事务边界难以判断。
    - 修复
      - 把事务方法改为 public，作为对外事务边界
      - 或把事务放到 public 的“应用服务层”方法上（更符合分层）
  - 3) Bean 不是由 Spring 容器管理（new 出来的对象/静态工具类）
    - 现象：注解写了但完全不生效
    - 原因：没有代理就没有拦截
    - 修复
      - 交给 Spring 管理（@Component/@Service 注入使用）
      - 工具类改为 Bean 或者改为显式 TransactionTemplate（少用但可控）
  - 4) 异常被 catch 吞掉（不抛出）
    - 现象：业务报错了但数据提交了
    - 原因：事务拦截器以“方法是否抛异常”作为回滚决策依据之一；你吞异常=方法正常返回=走 commit
    - 修复
      - 不要吞：catch 后记录日志并重新抛出（推荐）
      - 或显式 setRollbackOnly（兜底，不建议泛滥）
  - 5) 抛出的是 checked exception（受检异常）且未配置 rollbackFor
    - 现象：抛了异常但还是提交
    - 原因：默认只回滚 RuntimeException/Error
    - 修复
      - @Transactional(rollbackFor = Exception.class) 或指定具体异常
      - 或统一使用业务运行时异常封装（注意别滥用）
  - 6) 多数据源/多事务管理器选错
    - 现象：部分库回滚、部分库提交；或压根没进你想要的数据源事务
    - 原因：@Transactional 默认选主事务管理器；DAO 实际走了另一个 DataSource
    - 修复
      - 明确 @Transactional(transactionManager="xxx")
      - 规范数据源路由与 DAO 分包，避免一个事务里混用多个 DataSource（除非你上分布式事务）
  - 7) 代理类型不匹配（JDK 代理导致按类注入/调用绕过）
    - 现象：你按实现类类型拿 Bean，结果拿到的不是代理或类型转换异常，或某些方法没被代理
    - 原因：JDK 代理只实现接口；如果你绕过接口引用，可能导致调用路径不经代理或注入失败
    - 修复
      - 面向接口编程，用接口类型注入与调用
      - 或强制 CGLIB（proxyTargetClass=true），但要评估 final 方法限制
  - 8) 事务传播行为导致“看起来没回滚”
    - 现象：外层 catch 后继续执行，最后提交时报 UnexpectedRollbackException 或最终仍回滚
    - 原因：内层 REQUIRED 抛异常标记 rollback-only；外层吞异常仍尝试 commit
    - 修复
      - 外层不要吞关键异常；或明确分离事务（REQUIRES_NEW/补偿）
      - 明确异常策略与返回码策略（不要用吞异常伪装成功）
  - 9) @Transactional 放在接口/实现类/方法上的位置与代理策略不一致
    - 现象：注解写了但没被解析到（尤其在某些组合与历史配置下）
    - 原因：事务属性解析以实际被代理的方法元数据为准，接口/实现不一致可能踩坑
    - 修复
      - 统一把 @Transactional 放在实现类的 public 方法上（最稳）
  - 10) 在事务方法内开新线程/异步执行数据库操作
    - 现象：你以为在一个事务里，实际上异步线程独立提交
    - 原因：事务上下文 ThreadLocal 不跨线程
    - 修复
      - afterCommit 触发异步（@TransactionalEventListener AFTER_COMMIT）
      - Outbox/事务消息表等最终一致性方案

- 生产级修复方案（按优先级给“结构化打法”）
  - 1) 把事务边界放到“应用服务层”的 public 方法上
    - 原则：事务是边界能力，不要藏在私有方法/内部自调用里
  - 2) 拆分 Bean，确保调用跨 Bean（保证经过代理）
    - 将需要事务的方法抽到 TxService/RepositoryFacade 等独立 Bean
  - 3) 明确异常策略
    - 关键异常必须抛出（或转为运行时异常），避免吞异常伪成功
    - checked 异常要么 rollbackFor，要么统一封装运行时异常
  - 4) 明确事务管理器与数据源
    - 多数据源必须指定 transactionManager，必要时用统一路由或分布式事务/Outbox
  - 5) 异步/消息/外部副作用一律 afterCommit 或 Outbox
    - 避免“事务未提交就发消息/回调”，避免不一致

  - 追问：为什么非 public 常失效？
  - 关键原因（代理模型的边界）
    - JDK 动态代理只能代理接口方法，而接口方法天然是 public；所以非 public 方法根本不会出现在 JDK 代理的可拦截集合里
    - 对 Spring 6 的类代理，protected/package-private 方法默认可以参与事务拦截；但 private/final 方法不能被子类代理覆盖。历史版本、JDK 代理或自调用仍会让非 public 方法表现为“注解不生效”。
  - 生产实践结论
    - 把事务边界放在 public 方法上是最稳的团队规范；非 public 事务方法容易让“代理边界”变得隐蔽且难排障

- 追问：为什么 catch 异常不抛会导致提交？
  - 原因（事务拦截器的决策点）
    - TransactionInterceptor 的核心逻辑是：try 执行业务方法；catch 到异常时根据回滚规则决定 rollback；如果业务方法正常返回则走 commit
    - 你在方法内部 catch 并吞掉异常，相当于对拦截器“伪装成成功返回”，拦截器就会 commit
  - 规范修复
    - 业务异常要么向外抛出，要么显式 setRollbackOnly（仅作为兜底），同时返回码/错误码与事务策略要一致，避免“返回成功但实际回滚/或返回失败但实际提交”的语义错乱

- 小结（一句话复盘）
  - @Transactional 失效要么是没走代理（自调用、不可代理方法、非容器对象、代理类型不匹配），要么是决策不触发回滚（吞异常、checked 异常、传播行为/管理器选择错误、异步断事务）；生产修复优先把事务放在 public 边界、跨 Bean 调用、明确异常与回滚规则、明确 transactionManager，并把异步/外部副作用移到 afterCommit 或 Outbox。

---

## 4. 事务隔离级别在 Spring 设置后，真正语义在哪？MySQL RR 下“幻读”怎么理解？（含追问：什么 SQL 会触发 next-key lock？索引不命中会发生什么？）

> 本节的 MVCC、间隙锁和 next-key lock 结论以 MySQL InnoDB 为前提，并会随 MySQL 版本、索引设计、SQL 形态和事务隔离级别变化；它们不是 Spring 或 SQL 标准的统一保证。
### 1) 结论（标准答案）
- Spring 能做的是：在开启新事务时把隔离级别设置到 JDBC `Connection`（例如 `SET SESSION TRANSACTION ISOLATION LEVEL ...` 的效果）；真正决定“读到什么、锁怎么加、幻读怎么表现”的语义在数据库（这里是 MySQL InnoDB）的 MVCC（多版本并发控制）与锁实现（记录锁/间隙锁/next-key lock）里。
- MySQL 的默认隔离级别通常是 `REPEATABLE READ (RR)`：一致性读（普通 SELECT）依赖 MVCC 快照，能避免“同一事务内两次一致性读看到不同结果”；但“幻读”要分场景讨论：一致性读通常不会出现“结果集变化”，而加锁读（SELECT ... FOR UPDATE/LOCK IN SHARE MODE）是否出现幻读，取决于是否使用 next-key lock 把范围锁住。
- next-key lock 的触发与否，核心看：是否是“范围条件 + 索引可用 + 加锁读/更新删除”等需要锁范围的语句；索引不命中时会扩大锁范围（更容易退化成更粗粒度锁），带来锁等待/死锁/吞吐下降。

### 2) Spring 设置隔离级别后，真正语义在哪？
- Spring 负责“设置”
  - 在新事务 `doBegin` 时对 `Connection` 设置隔离级别（若你显式配置 `@Transactional(isolation=...)` 且是新事务）。
  - 如果是加入已有事务（REQUIRED 加入外层），Spring 通常不会强行改变隔离级别，避免破坏外层事务语义。
- MySQL InnoDB 负责“语义”
  - MVCC：决定一致性读看到哪个版本（快照读）
  - 锁：决定加锁读/更新的并发行为（记录锁/间隙锁/next-key lock）
  - 事务日志与回滚段：保证可回滚与一致性

### 3) MySQL RR 下“幻读”怎么理解（别背概念，要讲清边界）
- 幻读的经典定义（面试版）
  - 同一事务中，两次按同一条件查询，第二次出现了第一次没有的“新行”（或消失了行），导致结果集发生变化。
- 在 InnoDB RR 下要分两类读
  - 一致性读（普通 SELECT，不加锁）
    - 读的是“快照”：同一事务内多次执行相同条件查询，通常看到同一份快照结果（不会因别的事务插入而变化）。
    - 所以很多人会说：RR 下“不会幻读”，指的是“快照读不幻读”这一层面。
  - 加锁读（SELECT ... FOR UPDATE / LOCK IN SHARE MODE）与写操作（UPDATE/DELETE）
    - 读的是“当前读”：要对读取范围施加锁，防止并发写入破坏一致性。
    - 是否能彻底避免幻读，取决于 InnoDB 是否对查询范围加了 next-key lock（记录+间隙），从而阻止在范围内插入新行。
- 面试最稳的表达
  - “RR 通过 MVCC 让快照读稳定；通过 next-key lock 在必要时对范围加锁来抑制加锁读场景下的幻读。但是否加 next-key lock 取决于 SQL 形态与索引命中情况，不是所有查询都会自动锁住范围。”

### 4) 追问：什么 SQL 会触发 next-key lock？
- 触发 next-key lock 的高概率场景（生产也最常见）
  - 范围更新/删除（UPDATE/DELETE 带范围条件）
    - 例如：`UPDATE t SET ... WHERE idx_col BETWEEN 10 AND 20;`
  - 加锁范围读（SELECT ... FOR UPDATE / LOCK IN SHARE MODE）且走索引范围扫描
    - 例如：`SELECT * FROM t WHERE idx_col >= 10 AND idx_col < 20 FOR UPDATE;`
  - 唯一索引/主键的等值查询通常更倾向于“记录锁”（record lock）
    - 例如：`SELECT ... WHERE pk = 100 FOR UPDATE;` 一般只锁一条记录（前提：确实命中唯一索引且是等值）
- 不一定触发 next-key lock 的场景（容易被追问）
  - 普通 SELECT（不加锁）通常不加 next-key lock（走 MVCC 快照读）
  - 等值命中唯一索引的加锁读多为记录锁，而不是范围 next-key（但仍可能因优化器/条件变化出现范围锁）

### 5) 追问：索引不命中会发生什么？
- 结论
  - 索引不命中会导致扫描方式退化（可能全表扫描），并且在“需要加锁”的语句里锁范围会显著扩大，典型后果是：锁等待显著增加、并发吞吐下降、死锁概率上升。
- 具体表现（按语句类型拆）
  - 对于 UPDATE/DELETE
    - InnoDB 需要锁住“将要修改的行”；如果无法用索引精准定位行，会扫描更多记录并对更多记录加锁（甚至接近全表），导致大面积阻塞。
  - 对于 SELECT ... FOR UPDATE/LOCK IN SHARE MODE
    - 同理：无法走索引范围定位，就会在扫描过程中对大量记录加锁，锁冲突急剧增多。
- 生产级建议（你说出来面试官很舒服）
  - 给加锁读/写的 WHERE 条件配合适索引，确保走索引、缩小锁范围。
  - 尽量使用“等值命中唯一索引”的锁定方式来锁定单行，避免范围锁。
  - 通过 EXPLAIN 确认：type（range/ref/const）、key 是否命中、rows 估算是否过大。
  - 线上排障抓手：InnoDB 锁等待、死锁日志、慢日志、performance_schema 的锁相关表，结合 trace 看事务持锁时间。

### 6) 小结（一句话复盘）
- Spring 只是把隔离级别设置到连接，真正读写与锁语义由 InnoDB 的 MVCC 与锁实现决定；RR 下快照读通常稳定不幻读，加锁读是否避免幻读取决于 next-key lock 是否锁住范围；next-key lock 常见于范围条件的加锁读/更新删除，索引不命中会扩大扫描与锁范围，导致锁等待与死锁风险飙升。

---
## 5. 事务里发 MQ / 调远程接口为什么危险？你如何设计最终一致性（Outbox/事务消息/对账补偿）？（含追问：如何保证幂等？如何做补偿与可观测性？）
### 1) 结论（标准答案）
- 在本地事务里直接发 MQ 或调用远程接口（RPC/HTTP）危险的根因是：数据库事务与外部系统的提交/回滚不在同一个原子边界里，任何网络抖动、超时、重试、进程崩溃都会造成“DB 成功但消息/远程失败”或“消息/远程成功但 DB 回滚”的不一致。
- 生产上最稳的最终一致性落地通常是三件套：Outbox（事务消息表）+ 异步投递（可靠重试）+ 消费端幂等；必要时再加“对账与补偿”闭环来兜底极端边界。
- 如果 MQ 产品支持事务消息（例如部分 MQ 的半消息/两阶段提交能力），可以用“事务消息”替代 Outbox 的投递环节，但仍要消费端幂等与对账补偿。

### 2) 为什么危险（失败模型要讲清）
- 失败窗口 1：DB 已 commit，但 MQ 发送失败/超时
  - 结果：业务数据已生效，但下游永远收不到事件（库存/积分/发票/ES 索引不同步）
- 失败窗口 2：MQ 已发送成功，但 DB 最终 rollback
  - 结果：下游做了副作用（扣库存/发券），但主库没有订单，出现“幽灵事件”
- 失败窗口 3：超时重试导致重复发送/重复调用
  - 结果：同一业务事件被执行多次（重复扣库存、重复加积分、重复出账）
- 失败窗口 4：事务持锁期间做远程调用
  - 结果：锁持有时间被外部延长，锁等待/死锁概率飙升，连接池耗尽，P99 抖动甚至雪崩
- 失败窗口 5：进程崩溃/宕机发生在“DB 与外部动作之间”
  - 结果：出现不可恢复的中间态，需要对账/补偿兜底

### 3) 最终一致性方案 1：Outbox（事务消息表/本地消息表）（最通用、最稳）
- 核心思想
  - 在同一个本地事务里：写业务表 + 写 outbox 表（事件表）
  - 提交后由异步任务把 outbox 事件可靠投递到 MQ
- 表结构建议（最小可用）
  - outbox_event(id, biz_key, event_type, payload, status, retry_count, next_retry_at, created_at, updated_at, trace_id)
  - 关键索引：status + next_retry_at，biz_key 唯一（或 event_id 唯一）
- 关键流程
  - 写入阶段（同事务）
    - 业务变更（订单/支付/库存）与 outbox 插入同事务提交，保证“事件不会丢”
  - 投递阶段（事务外）
    - 扫描 status=NEW/RETRY 且 next_retry_at<=now 的记录
    - 发送 MQ 成功 -> 标记 SENT；失败 -> 递增 retry_count，计算 next_retry_at（指数退避+抖动），必要时进入 DEAD 状态
  - 消费阶段（下游）
    - 消费端幂等处理（见第 6 节）
- 优点
  - 不依赖特定 MQ 能力；失败可重试；数据可审计；可对账
- 风险与治理
  - 扫描与投递要限流、分片（避免扫描抖动）
  - 投递与更新状态需要幂等（避免重复投递与状态错乱）
  - 大流量需做分库分表/按时间分区/冷热分离

### 4) 最终一致性方案 2：事务消息（MQ 两阶段/半消息）
- 核心思想
  - 先发送“半消息/预消息”到 MQ（对消费者不可见）
  - 本地事务提交后再提交消息（让其可见）；回滚则回滚消息
  - MQ 通过回查机制兜底“提交状态不明”
- 适用场景
  - 你的 MQ 支持事务消息且团队熟悉其回查/幂等/可观测机制
- 仍需注意
  - 消费端必须幂等（重复投递仍可能发生）
  - 回查依赖业务侧提供“事务状态查询接口”，需要高可用与低延迟
  - 事务消息并非免费午餐：实现复杂度更高，且依赖 MQ 产品特性

### 5) 最终一致性方案 3：对账补偿（兜底闭环）
- 核心思想
  - 任何异步系统都可能存在边缘丢失/重复/延迟，最终要靠“可计算真相”的对账任务发现差异并补偿
- 典型做法
  - 以主库业务表为真相源（订单/支付流水）
  - 定期对账：找出“订单已支付但积分未发放/库存未扣/发票未开”等差异
  - 生成补偿任务表（compensation_task）并执行补偿（可重试、可回溯）
- 适用场景
  - 金融/支付/医保结算/电子票据这类强审计业务（你这种背景非常常见）
- 关键点
  - 补偿任务要可观测（状态机、重试次数、死信）
  - 补偿动作必须幂等（重复执行不产生额外副作用）

### 6) 追问：如何保证幂等？（生产级落地清单）
- 幂等目标
  - 同一事件/同一请求执行 1 次或多次，最终状态一致，且副作用不会重复叠加
- 常用幂等键（Idempotency Key）
  - event_id（消息唯一 ID）或 biz_key（如 order_id + event_type + version）
  - request_id（网关生成）或业务流水号（支付流水号/对账流水号）
- 消费端幂等实现（推荐组合）
  - 1) 幂等表（数据库唯一约束）
    - consumer_dedup(event_id PK/UK, consumed_at, handler, status)
    - 处理流程：INSERT 成功才执行业务；冲突表示已消费，直接 ACK
  - 2) 业务表状态机 + 乐观锁
    - 例如订单状态从 PAID->INVOICED，只允许一次成功更新：UPDATE ... WHERE status=PAID
  - 3) Redis 幂等（快速但要注意一致性）
    - SETNX(event_id) + 合理 TTL；适合高 QPS 但要防止 Redis 故障导致重复（仍建议最终落库校验）
- 发送端幂等（Outbox/事务消息侧）
  - outbox_event 表对 biz_key 建唯一索引，防止重复写事件
  - 投递更新状态用条件更新：UPDATE ... WHERE status IN (NEW,RETRY)
- 重要提醒
  - ACK 策略：业务处理成功后再 ACK；处理失败要 NACK/重试并配合死信与告警
  - “至少一次投递”是常态，幂等是必须品

### 7) 追问：如何做补偿与可观测性？（闭环能力）
- 补偿设计（任务化 + 状态机）
  - compensation_task(task_id, biz_key, task_type, payload, status, retry_count, next_retry_at, last_error, created_at, updated_at)
  - 状态：NEW -> RUNNING -> SUCCESS/RETRY/DEAD
  - 重试：指数退避 + 最大次数 + 人工介入通道（DEAD）
- 关键可观测指标（Prometheus/Grafana/日志/Trace）
  - Outbox：
    - backlog（NEW/RETRY 数量）、最老事件年龄（age）、投递成功率、重试次数分布、DEAD 数量
  - MQ：
    - 消费延迟（lag）、消费成功率、重试/死信量、堆积深度
  - 业务一致性：
    - 对账差异数、补偿成功率、补偿耗时、重复消费命中率
- 关键日志与链路追踪
  - 统一 trace_id/req_id 贯穿：写业务 -> 写 outbox -> 投递 MQ -> 消费处理
  - 消费失败必须记录：event_id、biz_key、payload 摘要、异常栈、重试次数
- 灰度与回滚
  - 事件 schema 版本化（event_type + version），消费者向后兼容
  - 支持快速停投递/停消费（开关），用于“秒级止血”
  - 补偿任务可暂停与回放，保证事故处理可控

### 8) 小结（一句话复盘）
- 事务内直发 MQ/调远程会因无法跨系统原子提交而产生丢失/重复/不一致，并扩大锁持有时间；生产上用 Outbox/事务消息实现“本地事务保证不丢 + 异步可靠投递 + 消费幂等”，再用对账补偿与可观测指标形成闭环，才能在真实故障模型下长期稳定运行。

---
# Spring Boot 源码级补充（自动配置、扩展点与排障）

> `SpringBoot.md` 负责 Starter、基础自动配置和外部化配置。本章只保留“条件评估、覆盖顺序、Starter 冲突治理”等进阶解释；使用前先阅读 [[SpringBoot|《SpringBoot》]]，避免在两篇笔记中分别维护相同的基础结论。
## 1. Boot 自动配置是怎么生效的？@SpringBootApplication 启动时加载了哪些关键东西？（含追问：Conditional 决策发生在哪？@ConditionalOnMissingBean 的 Missing 怎么判断？）
### 1) 结论（标准答案）
- Spring Boot 自动配置的核心是：启动时把一批“自动配置类”作为普通的 `@Configuration` 导入到容器里；这些配置类通过 `@Conditional...` 条件注解决定“要不要生效”，再通过 `@Bean` 提供默认实现，并用 `@ConditionalOnMissingBean` 让用户自定义 Bean 可以覆盖默认 Bean。
- `@SpringBootApplication` 本质是三个注解的组合：`@SpringBootConfiguration`（= `@Configuration`）、`@EnableAutoConfiguration`（开启自动配置导入）、`@ComponentScan`（包扫描注册业务 Bean）。

### 2) @SpringBootApplication 启动时加载的关键东西（按启动主线）
- 入口：`SpringApplication.run(...)`
  - 推断应用类型（servlet/reactive）、创建并准备 `ApplicationContext`
  - 准备 Environment（配置文件、profile、系统变量、命令行参数等）
  - 执行容器 `refresh()`（注册定义、执行 BFPP/BPP、实例化单例等）
- @SpringBootApplication 的三件套
  - `@SpringBootConfiguration`
    - 标识这是配置类（等价于 `@Configuration`），会走 CGLIB 增强（默认 proxyBeanMethods=true）
  - `@ComponentScan`
    - 从启动类所在包开始扫描：`@Component/@Service/@Repository/@Controller` 等，注册为 BeanDefinition
  - `@EnableAutoConfiguration`
    - 关键：通过 `AutoConfigurationImportSelector` 把“自动配置类列表”导入容器（本质是 Import 机制）
- 自动配置导入（真正“生效”的入口）
  - 自动配置类来源（概念上）
    - 从 classpath 中收集一批“候选自动配置类”
    - 再按各种过滤规则（排除、条件、环境）筛选
    - 最终作为配置类导入，参与普通的 Spring 生命周期（BFPP/BPP、@Bean 创建等）

### 3) 自动配置“怎么生效”的流程（讲清楚这条链就够用）
- 1) 导入自动配置类（Import）
  - `@EnableAutoConfiguration` → `AutoConfigurationImportSelector#selectImports()`
  - 产出：一组自动配置类的类名（全限定名）
  - 容器把这些类当作配置类注册为 BeanDefinition
- 2) 自动配置类作为 @Configuration 参与 refresh()
  - 在 `ConfigurationClassPostProcessor` 解析配置类时，处理自动配置类里的 `@Bean` 方法、`@Import` 等
- 3) 条件评估（Conditional）
  - 每个自动配置类或其中的 @Bean 方法往往带 `@Conditional...`
  - 条件满足才会注册对应 BeanDefinition/Bean
- 4) 默认 Bean 提供与用户覆盖
  - 自动配置通常写成：`@Bean` + `@ConditionalOnMissingBean`
  - 如果用户自己定义了同类型/同名 Bean，则 Missing 条件不成立，默认 Bean 不创建，实现“用户优先”

### 4) 追问：Conditional 系列注解的决策发生在哪？
- 结论
  - 条件决策发生在“配置类解析/BeanDefinition 注册阶段”，本质是 Spring 的 `@Conditional` 机制在评估条件：条件不满足时，对应的配置类或 @Bean 方法不会被注册为 BeanDefinition（或不会被实例化）。
- 关键机制（源码级名词对齐）
  - Spring Core：`Condition` / `ConditionEvaluator`
    - `ConditionEvaluator#shouldSkip(...)` 决定是否跳过某个配置类/某个 @Bean 方法
  - Boot 扩展：`SpringBootCondition`（大量 OnClass/OnBean/OnProperty 条件的基类）
    - 例如 `OnClassCondition`、`OnBeanCondition`、`OnPropertyCondition` 等
- 发生时机（面试可复述）
  - 配置类解析阶段（ConfigurationClassPostProcessor 处理 @Configuration）
  - 以及 @Bean 方法解析/注册阶段（读取 @Bean 元数据时评估条件）
  - 部分条件也会在更后阶段再次参与（例如与 BeanFactory 状态相关的判断），但主决策点在“是否注册”这一刻

### 5) 追问：@ConditionalOnMissingBean 的 Missing 怎么判断？
- 结论（最重要的一句）
  - Missing 的判断是“看容器里是否已经存在匹配条件的 Bean（或 BeanDefinition）”，存在则不创建默认 Bean；不存在才创建。它不是只看运行时实例，有时会看 BeanDefinition 元数据与类型预测（避免过早实例化）。
- 判断维度（常见匹配项）
  - 按类型：是否存在某个类型（或其子类型/实现）的 Bean
  - 按名称：是否存在指定 beanName
  - 按注解：是否存在带某些注解的 Bean（部分条件支持）
  - 按泛型：例如 `RedisTemplate<String, Object>` 这类，Boot 会尽量做泛型匹配（但复杂场景可能退化）
- 判断时机与策略（工程理解）
  - 在注册 @Bean 时就评估：如果用户在更早阶段已注册了同类型 BeanDefinition，那么 Missing 条件就会失败
  - 为避免“为了判断而提前实例化”，Boot 会优先做：
    - BeanDefinition/类型预测层面的检查（例如 `BeanFactory#getBeanNamesForType` 的逻辑）
    - 必要时再延后到实例化阶段确认（少数复杂条件）
- 为什么能覆盖默认 Bean（你在面试里这么说）
  - 自动配置提供的是“有条件的默认实现”；用户自己定义 Bean 属于“更明确的意图”，所以 Missing 条件让默认实现退让，确保用户配置优先级更高

### 6) 生产级排障要点（非常实用）
- 现象 1：某个自动配置没生效
  - 排查：是否被 exclude？是否 classpath 缺少依赖（OnClass）？是否某个 property 没开（OnProperty）？是否被用户 Bean 覆盖导致默认 Bean 没创建（OnMissingBean）？
- 现象 2：Bean 冲突/同类型多个 Bean
  - 排查：是否引入多个 starter 都提供了同类 Bean？是否 Missing 条件没挡住（因为类型不匹配/泛型不匹配/名称不同）？
- 现象 3：配置没生效
  - 排查：Environment 优先级、profile 激活、绑定到 @ConfigurationProperties 是否成功（可用 actuator/configprops 或日志确认）

### 7) 小结（一句话复盘）
- Boot 自动配置通过 @EnableAutoConfiguration 导入一组自动配置类，条件注解决定是否注册默认 Bean；Conditional 的决策主要发生在配置类/BeanDefinition 注册阶段；@ConditionalOnMissingBean 通过检查容器中是否已存在匹配 Bean（优先基于定义与类型预测）来决定默认 Bean 是否创建，从而实现“默认可用、用户可覆盖”。

---

## 2. 你怎么覆盖/替换 Boot 默认 Bean？有哪些手段？各自风险是什么？（含追问：exclude 自动配置有哪些坑？为什么不建议乱 exclude？）
### 1) 结论（标准答案）
- 覆盖/替换 Boot 默认 Bean 的首选方式是“提供你自己的同类型 Bean”，让自动配置里的 `@ConditionalOnMissingBean` 自动失效，从而用你的实现替代默认实现；这也是最符合 Boot 设计哲学的方式。
- 手段从稳到猛依次是：自定义 Bean 覆盖（推荐）→ `@Primary/@Qualifier` 选择注入 → 属性配置调整（用配置改变默认 Bean 行为）→ AutoConfiguration 顺序控制 → exclude 自动配置（最后手段）。
- exclude 的坑在于：自动配置之间有隐含依赖链，你排除一个可能连带破坏一串条件与 Bean 创建，导致启动失败或更隐蔽的运行时缺能力；因此不建议“看到冲突就 exclude”，应优先用覆盖/参数化解决。

### 2) 覆盖/替换默认 Bean 的手段清单（按推荐顺序）
#### 2.1 提供同类型 Bean（最推荐）
- 做法
  - 你在业务侧定义一个与默认 Bean “同类型/可赋值类型”的 Bean：
    - 默认 Bean 上通常有 `@ConditionalOnMissingBean(SomeType.class)`
    - 你提供 `@Bean SomeType mySomeType()` 后，Missing 条件不成立，默认 Bean 不会创建
- 风险与注意
  - 类型要“匹配得上”：有时默认 Bean 的 Missing 判断按更具体的类型/泛型判断，导致你以为覆盖了但实际没覆盖（尤其是泛型类型、子类/接口差异）
  - 若多个 Bean 同类型并存，注入点可能产生 `NoUniqueBeanDefinitionException`，需要配合 `@Primary/@Qualifier`

#### 2.2 使用 @Primary / @Qualifier 控制注入选择（推荐）
- 做法
  - 你不一定要阻止默认 Bean 创建，也可以让注入点选择你的实现：
    - `@Primary`：让你的 Bean 成为默认注入候选
    - `@Qualifier("xxx")`：在注入点点名要哪个
- 风险与注意
  - 默认 Bean 仍存在：某些地方（尤其框架内部）可能仍会按类型注入触发冲突，或被别的组件误注入
  - `@Primary` 太“隐式”：团队需要规范，避免多个 Primary 或误选导致线上行为漂移

#### 2.3 用配置改变默认 Bean 行为（更轻量，常用于连接池/线程池/HTTP client）
- 做法
  - 通过 `application.yml` 调整 `@ConfigurationProperties` 绑定的参数，让默认 Bean “变成你想要的样子”
  - 典型：DataSource/Hikari、Tomcat/Undertow、Redis、Jackson、线程池、Feign/HttpClient 等
- 风险与注意
  - 你并没有替换 Bean，只是调参：若你需要的是“行为完全不同”的实现，这种方式不够
  - 配置优先级/多 profile 覆盖容易踩坑，“看起来没生效”要会排障（env/configprops）

#### 2.4 提供自定义 AutoConfiguration / Starter（平台化推荐）
- 做法
  - 写自己的 starter：提供自动配置类，用 `@AutoConfigureBefore/@AutoConfigureAfter`、`@Conditional...`、`@Import` 控制顺序与条件
  - 用“更高优先级的默认实现”覆盖 Boot 默认策略（仍遵守 MissingBean 语义）
- 风险与注意
  - 需要把条件、顺序、backward compatibility 设计清楚，否则 starter 之间容易打架
  - 要注意元数据与提示（configuration metadata）提升可用性

#### 2.5 直接 exclude 自动配置（最后手段）
- 做法
  - `@SpringBootApplication(exclude = XxxAutoConfiguration.class)` 或 `spring.autoconfigure.exclude=...`
- 风险与注意
  - 属于“砍掉整块默认能力”，容易引入连锁反应（见第 4 节）

### 3) 各手段的风险对比（给面试官的“取舍说明”）
- 自定义 Bean 覆盖（推荐）
  - 优点：遵循 Boot 设计、最可控、升级兼容性最好
  - 风险：类型/泛型不匹配导致覆盖失败；需要注意注入冲突
- @Primary/@Qualifier（次推荐）
  - 优点：改动小，注入点明确
  - 风险：默认 Bean 仍存在，可能引发别处冲突或误注入；@Primary 过隐式
- 配置调参（常用）
  - 优点：最轻量、最符合“约定大于配置”
  - 风险：只能调行为不能换实现；配置层级复杂易误配
- 自定义 starter（平台化）
  - 优点：可复用、统一治理、可控的条件与顺序
  - 风险：需要良好的版本管理与兼容策略，避免 starter 冲突
- exclude（最后手段）
  - 优点：快速止血（例如明确不需要某能力且它导致启动失败）
  - 风险：破坏依赖链、升级风险大、排障成本高

### 4) 追问：exclude 自动配置有哪些坑？为什么不建议乱 exclude？
- 坑 1：自动配置之间存在隐含依赖链（你砍一个会带崩一串）
  - 例如某些 AutoConfiguration 依赖另一个提供的基础 Bean（converter、customizer、builder、properties）
  - exclude 后可能出现启动期缺 Bean（NoSuchBeanDefinitionException）或运行期缺能力（比如指标、序列化、校验器没注册）
- 坑 2：你可能排除的是“条件装配的入口”，但真正冲突在别处
  - 结果：问题没解决，反而把其他默认能力关掉了
- 坑 3：升级风险大
  - Boot 升级后自动配置拆分/合并/类名变化，你的 exclude 可能失效或排错对象，引发不可预期问题
- 坑 4：容易造成“环境差异”
  - dev 没事、prod 出事：因为 classpath/配置不同导致条件装配路径不同，exclude 的副作用在某些环境才出现
- 为什么不建议乱 exclude（推荐做法）
  - 优先使用“覆盖默认 Bean”或“配置调参”，让 Boot 的条件体系自然工作
  - 只有在以下场景才考虑 exclude：
    - 你明确完全不需要某能力（例如明确不用某种 Web 技术栈）
    - 或该自动配置在当前环境必定错误（例如冲突不可调和）且你有替代实现
    - 且你能写清楚回归测试与升级检查项

### 5) 生产级建议（怎么选最靠谱）
- 想“换实现”→ 自定义同类型 Bean 覆盖（必要时配合 @Primary）
- 想“改行为”→ 配置调参（并用 actuator/configprops/env 验证生效）
- 想“平台统一”→ 自研 starter + 条件与顺序治理
- 想“临时止血”→ exclude（但要补回归测试与升级检查清单）

### 6) 小结（一句话复盘）
- 覆盖 Boot 默认 Bean 的最佳实践是“自定义 Bean 触发 @ConditionalOnMissingBean 失效”，其次用 @Primary/@Qualifier 控制注入或用配置调参；exclude 属于最后手段，因为自动配置存在依赖链与升级不确定性，容易引发连锁缺失与排障困难。

---
## 3. 配置加载优先级（properties/yaml、环境变量、命令行、profile）怎么排？“配置没生效”怎么排障？（含追问：生产如何快速确认实际生效值）
### 1) 结论（标准答案）
- Boot 的配置本质是多来源 PropertySource 的叠加，优先级原则很简单：越“靠近运行时/越显式指定”的优先级越高（命令行 > 环境变量 > 外部配置文件 > 包内默认配置）。
- profile 不是“另一套规则”，而是把 `application-{profile}.yml` 等文件按激活的 profile 加进同一条优先级链里；同名 key 以优先级高者覆盖低者。
- “配置没生效”的排障遵循四步：找 key 是否正确 → 找配置源是否加载 → 找优先级是否被覆盖 → 找绑定/使用是否正确（@ConfigurationProperties 是否绑定、Bean 是否真的用到了该配置）。

### 2) 配置加载优先级怎么排（工程可用的排序口径）
- 优先级总体从高到低（常用口径）
  - 1) 命令行参数（--server.port=...）
  - 2) 系统属性（-Dserver.port=...）
  - 3) 环境变量（SERVER_PORT=...，或容器/平台注入的 env）
  - 4) 外部配置文件（应用工作目录、指定 config 目录等位置的 application.yml/properties）
  - 5) 包内配置文件（classpath 下的 application.yml/properties）
  - 6) 默认值（代码中的默认值、@Value 默认、@ConfigurationProperties 默认字段值）
- profile 的覆盖关系（关键点）
  - 激活 profile 后会加载：
    - application.yml（基础）
    - application-{profile}.yml（profile 特化）
  - 同一配置源内部通常是“profile 文件覆盖基础文件”；
  - 不同配置源之间仍按优先级覆盖（例如：命令行里的 key 会覆盖 profile 文件里的同名 key）。

### 3) “配置没生效”怎么排障（生产级步骤）
- Step 1：确认 key 本身没写错/没写到错误前缀
  - 常见坑：
    - 驼峰/短横线（relaxed binding）虽然宽松，但前缀/层级错了仍然无效
    - 写在错误的命名空间（例如 spring.redis 与 spring.data.redis 搞混）
- Step 2：确认配置源真的被加载了
  - 常见坑：
    - 你以为用的是外部 application-prod.yml，但实际上应用没从那个目录加载
    - 容器镜像里没有你挂载的 config，或者挂载路径不对
    - profile 根本没激活（prod 没生效）
- Step 3：确认是否被更高优先级覆盖
  - 常见坑：
    - K8s/平台注入的 env 覆盖了文件
    - 启动脚本传了 --xxx 覆盖了文件
    - 同一 key 在多个地方重复定义，最终以最高优先级为准
- Step 4：确认“绑定/使用链路”没断
  - @Value / @ConfigurationProperties 是否绑定成功？
  - 你改的配置是不是被某个 Bean 读取过一次缓存了（例如某些客户端初始化时读取一次）？
  - 相关 Bean 是否真的启用了（条件装配没命中导致 Bean 根本没创建）？

### 4) 追问：生产如何快速确认“实际生效值”（Actuator/env、日志、/configprops）
- 4.1 使用 Actuator 快速确认（最推荐）
  - /actuator/env
    - 查某个 key 的最终值，以及它来自哪个 PropertySource（谁覆盖了谁一眼看出）
    - 生产建议：开启访问控制与脱敏（敏感配置不能裸露）
  - /actuator/configprops
    - 查看 @ConfigurationProperties 绑定后的对象值（能确认“文件→绑定→对象”是否成功）
    - 特别适合排查：你配置写对了，但绑定没生效（前缀错/未启用/未扫描）
  - /actuator/beans 或 /actuator/conditions（如果启用）
    - beans：确认相关 Bean 是否创建
    - conditions：确认自动配置为何生效/为何没生效（ConditionalOnProperty/OnClass/OnMissingBean）
- 4.2 日志与启动诊断（生产常用）
  - 启动时打印关键配置（注意脱敏）
    - 例如打印：active profiles、关键连接串、线程池大小、超时配置等
  - 开启配置绑定日志（排查期临时）
    - 可以看到配置源加载与绑定过程，确认是否被覆盖/是否绑定
  - 打开 auto-configuration report（排查期）
    - 用于确认某个自动配置为何没生效（OnProperty/OnClass 不满足等）
- 4.3 最快的“定位覆盖源”技巧（实战）
  - 用 /actuator/env 搜索 key，看“最终值 + 来源”
  - 若最终值对但行为不对：用 /actuator/configprops 看绑定对象是否一致
  - 若绑定对象对但行为不对：说明该配置没有被实际使用（Bean 初始化时机/缓存/条件装配/版本差异）

### 5) 常见“配置没生效”事故清单（面试加分）
- profile 没激活：以为 prod，实际跑 default（看启动日志 active profiles）
- env 覆盖文件：K8s ConfigMap/Secret 注入覆盖了 application.yml
- 多份配置文件路径不一致：镜像里 classpath 有一份，挂载目录又一份，最终加载顺序与你预期不同
- 配置写对但 Bean 没创建：条件装配没命中（OnClass 缺依赖、OnProperty 没开开关）
- 配置绑定对象没启用：缺 @EnableConfigurationProperties 或未被扫描到（老项目迁移常见）

### 6) 小结（一句话复盘）
- 配置优先级遵循“越运行时越高”：命令行/系统属性/env 通常覆盖外部与包内配置；profile 只是把 profile 文件加入同一覆盖链；排障按“key→配置源→覆盖源→绑定/使用”四步走，生产最快用 Actuator 的 /env 与 /configprops 确认最终值与来源。

---

## 4. 你如何写一个 starter？starter 的边界、自动配置、条件装配、配置绑定、元数据提示怎么做？（含追问：如何避免 starter 互相打架）
### 1) 结论（标准答案）
- Starter 的目标是把一项可复用能力“产品化”：引入一个依赖就能用，并且默认配置合理、可观测、可覆盖、可禁用。实现上通常分两块：starter（依赖聚合）+ autoconfigure（自动配置实现）。
- 边界原则：starter 只做“能力的装配与默认实现”，不侵入业务逻辑；对外提供清晰的配置项（@ConfigurationProperties），并用 Conditional 做“按需启用、可覆盖、可关闭”；同时提供 metadata 让 IDE 有提示与校验。
- 互相打架的治理靠三件套：条件收敛（OnClass/OnProperty/OnMissingBean）、顺序控制（@AutoConfigureBefore/@AutoConfigureAfter）、以及显式分层（基础 starter vs 增强 starter）避免重复提供同类型 Bean。

### 2) Starter 的工程结构（推荐拆分：starter + autoconfigure）
- 模块 1：xxx-spring-boot-starter
  - 只放依赖声明（pom 依赖聚合），不放代码或只放很少的桥接
  - 依赖：xxx-spring-boot-autoconfigure + 该能力所需第三方依赖
- 模块 2：xxx-spring-boot-autoconfigure
  - 放自动配置类、@ConfigurationProperties、默认 Bean、Conditional 条件、指标/健康检查等
- 为什么要拆分
  - autoconfigure 可以被其它 starter/业务直接依赖；starter 作为“用户入口”提供最少心智成本
  - 便于版本管理与避免依赖污染

### 3) Starter 的边界怎么定（面试要说清“做什么/不做什么”）
- 做什么
  - 提供默认 Bean 与合理默认参数
  - 提供配置开关、可替换点（@ConditionalOnMissingBean）
  - 提供可观测性：metrics、health indicator、日志关键点
  - 提供安全边界：超时、重试、限流（如果能力需要）
- 不做什么
  - 不直接耦合业务表/业务流程
  - 不默认开启破坏性行为（例如全局拦截器强制改写响应、全量扫描全类路径）
  - 不强制依赖重型组件（能 optional 就 optional）

### 4) 自动配置怎么写（核心骨架）
- 4.1 自动配置类（AutoConfiguration）
  - 写一个配置类：提供默认 Bean
  - 用条件注解控制是否生效：OnClass/OnProperty/OnMissingBean 等
  - 用 @EnableConfigurationProperties 绑定配置对象
	```java
	@AutoConfiguration
	@ConditionalOnClass(SomeClient.class)
	@EnableConfigurationProperties(SomeProperties.class)
	@ConditionalOnProperty(prefix = "acme.some", name = "enabled", havingValue = "true", matchIfMissing = true)
	public class SomeAutoConfiguration {
	    @Bean
	    @ConditionalOnMissingBean
	    public SomeClient someClient(SomeProperties props) {
	        return new SomeClient(props.getEndpoint(), props.getTimeout());
	    }
	}
	```
- 4.2 注册自动配置入口（不同版本的声明方式）
	•	现代方式（推荐）：在 META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports 写入自动配置类全限定名（一行一个）
	•	旧方式：META-INF/spring.factories（仍可见于老项目/老 starter）
- 4.3 配置属性类（@ConfigurationProperties）
	``` java
	@ConfigurationProperties(prefix = "acme.some")
	public class SomeProperties {
	    private boolean enabled = true;
	    private String endpoint;
	    private Duration timeout = Duration.ofSeconds(2);
	    // getter/setter
	}
	```
 - 4.4 配置校验（强烈建议）
	•	用 @Validated + JSR-303 注解（@NotBlank/@Min 等），启动即失败，避免带病运行
	``` java
	@Validated
	@ConfigurationProperties(prefix = "acme.some")
	public class SomeProperties {
	    @NotBlank
	    private String endpoint;
	}
	```
5) 条件装配怎么做（让 starter “默认可用 + 可控可禁用”）
	•	常用条件组合（建议形成团队模板）
	•	@ConditionalOnClass：classpath 有依赖才启用（避免 NoClassDef）
	•	@ConditionalOnProperty：配置开关控制是否启用（enabled=true/false）
	•	@ConditionalOnMissingBean：用户提供同类型 Bean 则默认实现退让（可覆盖）
	•	@ConditionalOnBean：依赖某基础 Bean 存在才启用（分层 starter 常用）
	•	@ConditionalOnWebApplication：只在 web/reactive 场景启用
	•	条件装配的设计原则
	•	“入口条件”尽量收敛：用 enabled 开关兜住所有能力
	•	“默认实现”必须可覆盖：所有关键 Bean 都应 MissingBean
	•	“避免过早初始化”：不要在配置类静态块或构造器里做重活

6) 配置绑定与元数据提示怎么做（IDE 提示、可发现性）
	•	配置绑定
	•	@ConfigurationProperties + @EnableConfigurationProperties（或 @ConfigurationPropertiesScan）
	•	提供默认值、范围校验、注释说明
	•	元数据提示（spring-configuration-metadata）
	•	在 autoconfigure 模块引入配置处理器（annotation processor）
	•	会生成 META-INF/spring-configuration-metadata.json
	•	为每个配置项写清楚 description、默认值、类型，IDE 才能智能提示
	•	额外增强（生产友好）
	•	提供示例 application.yml 片段（README）
	•	提供 “fail-fast” 行为：关键配置缺失直接启动失败（可通过开关关闭）

7) 追问：如何避免 starter 互相打架（条件、顺序、@AutoConfigureAfter/Before）
	•	7.1 条件收敛（最重要）
	•	避免两个 starter 同时创建同类型核心 Bean
	•	方式：
	•	两边都用 @ConditionalOnMissingBean 限制默认实现
	•	用 @ConditionalOnProperty 做互斥开关（例如 mode=A/B）
	•	用 @ConditionalOnBean 做分层依赖（基础 starter 提供基础 Bean，增强 starter 只有在基础 Bean 存在时才生效）
	•	7.2 顺序控制（让“谁先装配”可控）
	•	使用：
	•	@AutoConfigureAfter(XxxAutoConfiguration.class)
	•	@AutoConfigureBefore(YyyAutoConfiguration.class)
	•	场景：
	•	你要在另一个自动配置创建 Bean 之前先提供一个替代 Bean
	•	或者你依赖另一个自动配置先完成某些 BeanDefinition 注册
	•	7.3 明确分层（避免重复提供）
	•	基础 starter：只提供最基础、最通用的 Bean（Client、Template、Converter）
	•	增强 starter：提供可选增强（Metrics、Tracing、Retry、CircuitBreaker），并用 ConditionalOnBean(基础 Bean) 挂载
	•	7.4 避免“类型看似相同但泛型/名称不同”的隐性冲突
	•	对泛型 Bean（如 RedisTemplate<K,V>、ObjectMapper 定制）要明确约定 beanName 或提供专用的 Customizer（例如 *Customizer 模式）
	•	优先提供 Customizer/Builder 扩展点，而不是直接创建第二个同类核心 Bean

8) 生产级清单（写 starter 的验收项）
	•	能力可开关：enabled=true/false
	•	默认 Bean 可覆盖：MissingBean 覆盖成功且有测试
	•	配置项有校验：缺关键项 fail-fast
	•	有可观测性：metrics/health/logs 至少一项
	•	有兼容策略：升级不破坏用户覆盖（保持 Bean 类型/名称稳定或提供迁移指引）
	•	有冲突治理：条件互斥/顺序控制/分层设计

9) 小结（一句话复盘）
	•	写 starter 的关键是把能力装配成“默认可用、可配置、可覆盖、可禁用”的自动配置：用 @ConfigurationProperties 做配置绑定与校验，用 Conditional 控制启用与覆盖，用 AutoConfiguration.imports 声明入口并配元数据提示；避免打架靠 MissingBean + Property 互斥 + 分层依赖 + Before/After 顺序控制。

---
# MVC / Web（链路、扩展点、性能与安全）
## 1. 从请求进入到 Controller 返回的完整链路是什么？DispatcherServlet 做了哪些关键选择？（含追问：HandlerMapping/HandlerAdapter 的意义是什么？为什么要这样抽象？）
### 1) 结论（标准答案）
- Spring MVC 的请求链路本质是一个“前端控制器（Front Controller）模式”：所有 HTTP 请求先进入 `DispatcherServlet`，它负责做三件关键选择：选择谁来处理（HandlerMapping）、用什么方式调用（HandlerAdapter）、以及怎么把结果写回（ViewResolver/HttpMessageConverter + 异常处理）。
- 你把它理解成：`DispatcherServlet` 是总导演，`HandlerMapping` 负责“找演员”，`HandlerAdapter` 负责“按演员的演法去调用”，最终通过视图渲染或消息转换把响应输出。

### 2) 完整链路（从请求到返回，按时序）
- 1) 请求进入容器
  - Tomcat/Jetty/Undertow 接收请求 → Servlet 容器把请求分发到 `DispatcherServlet`
- 2) `DispatcherServlet#doDispatch`（核心总控）
  - 2.1 处理 multipart（如果是文件上传）
    - `MultipartResolver` 解析并包装 request
  - 2.2 获取 Handler（谁来处理）
    - 调用 `HandlerMapping#getHandler(request)` 得到 `HandlerExecutionChain`
    - chain 包含：Handler（通常是 Controller 方法）+ 一组 HandlerInterceptor
  - 2.3 执行拦截器 preHandle（前置）
    - 常用于鉴权、灰度路由、日志、限流（更常在网关/Filter，但这里也能做）
  - 2.4 获取 HandlerAdapter（怎么调用）
    - `HandlerAdapter#supports(handler)` 选择一个能执行该 handler 的适配器
    - `HandlerAdapter#handle(request, response, handler)` 执行真正的业务方法
  - 2.5 参数解析与调用 Controller 方法
    - `HandlerMethodArgumentResolver` 解析参数（@RequestParam/@PathVariable/@RequestBody 等）
    - `HttpMessageConverter` 负责请求体反序列化（JSON/XML/表单）
    - 通过反射/方法调用执行 Controller 方法
  - 2.6 返回值处理（把结果变成响应）
    - 如果返回 `ModelAndView`：走视图渲染
      - `ViewResolver` 解析视图名 → `View#render` 输出
    - 如果是 `@ResponseBody` / `ResponseEntity` / Rest 风格：
      - `HandlerMethodReturnValueHandler` 处理返回值
      - `HttpMessageConverter` 序列化为 JSON 等写入 response
  - 2.7 异常处理（出错怎么办）
    - 捕获异常后交给 `HandlerExceptionResolver` 链处理
      - 常见：`@ControllerAdvice`、`ResponseStatusExceptionResolver` 等
  - 2.8 执行拦截器 afterCompletion（收尾）
    - 释放资源、记录耗时、清理 ThreadLocal（尤其是 MDC/Trace）
- 3) 响应返回容器
  - Servlet 容器把 response 写回客户端，连接复用/关闭由容器与客户端协商

### 3) DispatcherServlet 做了哪些关键选择（面试要点）
- 选择 1：请求对应哪个处理器（Handler）
  - 通过一组 `HandlerMapping` 查找最匹配的 handler
  - 典型实现：`RequestMappingHandlerMapping`（@RequestMapping/@GetMapping 等）
- 选择 2：用哪个适配器调用 handler
  - 通过一组 `HandlerAdapter` 找到 supports 的那个
  - 典型实现：`RequestMappingHandlerAdapter`（调用 @Controller 方法）
- 选择 3：怎么处理返回值
  - 视图渲染：ViewResolver/ModelAndView
  - 直接写 body：ReturnValueHandler + HttpMessageConverter
- 选择 4：异常交给谁处理
  - `HandlerExceptionResolver` 链决定最终响应（状态码、body、view）
- 选择 5：拦截器链什么时候执行
  - `preHandle` → handler → `postHandle` → 渲染 → `afterCompletion`

### 4) 追问：HandlerMapping/HandlerAdapter 的意义是什么？为什么要这样抽象？
- 核心意义：解耦“如何找到处理器”和“如何执行处理器”
  - HandlerMapping 只负责“路由”：把 request 映射到某个 handler
  - HandlerAdapter 只负责“调用协议”：不同类型的 handler 用不同方式执行
- 为什么要这样抽象（工程收益）
  - 1) 支持多种 Handler 形态
    - 除了 @Controller 方法，还可以有 HttpRequestHandler、Controller（老接口）、RouterFunction（WebFlux）等
    - 如果没有 Adapter，你就只能支持一种 handler 形态，扩展性差
  - 2) 扩展点清晰且可插拔
    - 新增一种路由规则 → 加一个 HandlerMapping
    - 新增一种 handler 执行方式 → 加一个 HandlerAdapter
    - 不改 DispatcherServlet 核心逻辑
  - 3) 性能与可维护性更好
    - 匹配与调用分离，便于缓存匹配结果、做排序与条件过滤
    - 便于在不同层做观测与治理（路由命中、参数解析耗时、序列化耗时）
- 你可以用一句话总结（面试版）
  - “Mapping 解决选谁，Adapter 解决怎么调，DispatcherServlet 负责把这些插件串成一条稳定的执行链。”

### 5) 生产级注意事项（加分）
- 性能热点通常不在 DispatcherServlet，而在：
  - 参数解析（复杂对象绑定、校验）
  - JSON 序列化/反序列化（大对象/大列表）
  - 异常栈与日志（频繁异常会拖垮）
- 观测建议
  - 打点：mapping 命中耗时、handler 执行耗时、converter 耗时、异常分类统计
  - 线上排障：慢请求先看 trace，再拆分是 controller 慢、SQL 慢还是序列化慢

### 6) 小结（一句话复盘）
- Spring MVC 以 DispatcherServlet 为总控：通过 HandlerMapping 找 handler，通过 HandlerAdapter 执行 handler，借助参数解析器与消息转换器完成入参/出参处理，并用异常解析器与拦截器链完成统一治理；Mapping/Adapter 的抽象让路由与执行协议解耦，从而支持多形态处理器与高可扩展性。

---

## 2. Filter vs Interceptor vs AOP 的边界与适用场景？你会把鉴权放哪里？为什么？（含追问：跨域、body 重复读取、灰度 Header 注入分别在哪层做最合适？）
### 1) 结论（标准答案）
- Filter 是 Servlet 规范层（容器级）拦截，最靠近网络入口，适合做与 MVC 无关的通用能力：跨域、请求包装（body 缓存）、安全头、链路上下文、限流粗筛等。
- Interceptor 是 Spring MVC 层（Handler 调用前后）拦截，知道“将要执行哪个 HandlerMethod”，适合做与路由/用户态相关的治理：登录态校验、权限校验（粗粒度）、灰度路由（基于 handler/路径）、请求级审计等。
- AOP 是 Spring Bean 方法层（业务层）拦截，适合做“与业务方法语义相关”的横切：事务、方法级鉴权（细粒度到方法/注解）、幂等、审计、指标埋点、缓存等。
- 鉴权放哪里：推荐“分层防御”
  - 网关/Filter 做最外层的快速拒绝与基础校验（token 结构/签名/黑名单/限流）
  - MVC Interceptor 做登录态与请求级权限（是否登录、租户/组织上下文）
  - 业务层 AOP 或 Spring Security Method Security 做细粒度授权（方法级、资源级），避免绕过网关/旁路调用导致越权

### 2) 三者边界（按“所在层级/能看到什么/适合做什么”）
- Filter
  - 所在层级：Servlet 容器链（DispatcherServlet 之前/之后）
  - 能看到：原始 HttpServletRequest/Response；不知道 handler 是谁（除非你自己解析）
  - 适合：
    - 跨域 CORS（设置响应头、预检 OPTIONS 快速返回）
    - body 包装与重复读取（ContentCachingRequestWrapper 等）
    - 全链路 traceId/MDC 注入、统一安全响应头
    - 粗粒度限流/黑白名单/IP 控制
  - 不适合：
    - 依赖 HandlerMethod/注解的逻辑（需要反射解析 mapping，成本高且不可靠）
- Interceptor
  - 所在层级：Spring MVC 调用链（拿到 handler 之后、调用 handler 之前/之后）
  - 能看到：Handler/HandlerMethod（方法、注解、路径变量等）
  - 适合：
    - 登录态校验、会话/用户上下文构建（userId/tenantId）
    - 基于路径/handler 的灰度路由策略（更精确）
    - 请求级审计（记录谁访问了哪个接口）
    - 统一幂等 token 校验（偏 HTTP 语义）
  - 不适合：
    - 非 MVC 请求（静态资源、某些特殊 servlet）可能不走
    - 业务方法内部调用/异步线程（覆盖不到）
- AOP
  - 所在层级：Spring Bean 方法调用（Service/Component）
  - 能看到：方法签名、注解、参数、返回值、异常；可组合事务等
  - 适合：
    - 方法级鉴权（@PreAuthorize/@Secured/@RequiresPermission 等）
    - 事务、缓存、幂等（基于业务 key）、审计、指标埋点
    - 统一异常转换（谨慎使用，避免吞异常影响事务）
  - 不适合：
    - 依赖 HTTP 层细节（request/response body 原始流）
    - 同类自调用绕过代理导致失效（需要结构化修复）

### 3) 鉴权放哪里（为什么这么选）
- 推荐架构：分层防御（Defense in Depth）
  - 入口层（网关或 Filter）
    - 做“能快速拒绝且不依赖业务语义”的鉴权：JWT 格式/签名校验、过期校验、黑名单、基础限流
    - 原因：越靠前越省资源，减少无效请求进入业务与数据库
  - MVC 层（Interceptor）
    - 做“请求级上下文”构建与粗粒度权限：解析 userId/tenantId、校验登录态、校验接口级权限
    - 原因：拿得到 HandlerMethod，易做白名单、注解开关、灰度策略
  - 业务层（AOP / Spring Security Method Security）
    - 做“最终授权”与资源级控制：比如订单只能看自己的、科室数据按角色过滤
    - 原因：防旁路调用（内部服务直连绕过网关）、防未来新增入口绕过 MVC 拦截器；授权必须贴近业务资源语义
- 一句话面试版
  - “入口做快速拒绝，MVC 做上下文与接口级权限，业务层做资源级最终授权，避免任何单点绕过。”

### 4) 追问：跨域、body 重复读取、灰度 Header 注入分别在哪层做最合适？
- 跨域（CORS）
  - 最合适：Filter（或网关层）
  - 原因：
    - CORS 需要处理预检 OPTIONS，越靠前越好，避免进入 MVC/业务层
    - 需要设置响应头，对所有请求统一生效
- body 重复读取（request body 只能读一次）
  - 最合适：Filter
  - 原因：
    - 输入流在进入 Controller 之前就可能被读取（日志、鉴权、签名校验），需要在最早位置包装 request（缓存 body）
    - Interceptor/AOP 已经太晚，body 可能已被消费
  - 注意：
    - 缓存大 body 会占内存，必须限制大小、对大文件上传走 streaming，避免 OOM
- 灰度 Header 注入（例如注入 X-Gray-Tag、X-Canary）
  - 最合适：网关层（首选）或 Filter/Interceptor（视灰度维度）
  - 选择建议：
    - 按用户/按比例/按地域的灰度：网关最合适（统一入口、避免多服务重复实现）
    - 单体应用或无网关：Filter/Interceptor 都可
      - 如果灰度规则只依赖请求信息（cookie/header/ip）：Filter 足够
      - 如果灰度规则依赖 handler/注解/接口维度：Interceptor 更合适（能拿到 HandlerMethod）
  - 注意：
    - 注入 header 要防客户端伪造：对外只信任网关注入（可用内部 header + 网关签名、或在入口层清洗外部同名 header）

### 5) 生产级注意事项（加分）
- 鉴权不要只做一层
  - 只在网关鉴权会被内部直连绕过；只在业务层鉴权会浪费资源且难统一
- 性能与超时
  - Filter/Interceptor 中的远程鉴权（调用 IAM）要谨慎：容易把请求链路拉长，建议本地校验 + 缓存 + 降级策略
- 可观测性
  - 统一记录：鉴权失败原因码、命中规则、耗时、用户/租户维度指标；灰度注入要打点以便回溯

### 6) 小结（一句话复盘）
- Filter 是容器级通用入口能力（跨域、body 包装、全局上下文），Interceptor 是 MVC 级路由与请求治理（登录态、handler 级策略），AOP 是业务方法级横切（事务、方法级授权与资源控制）；鉴权应分层防御，跨域与 body 缓存放 Filter，灰度 header 注入优先网关，缺网关时按规则维度选 Filter 或 Interceptor。

---

## 3. Spring MVC 参数解析与消息转换（HttpMessageConverter）如何工作？自定义 Converter 的坑？（含追问：大 JSON 内存抖动/慢请求怎么优化）
### 1) 结论（标准答案）
- Spring MVC 在调用 Controller 方法前，会用一组 `HandlerMethodArgumentResolver` 把 HTTP 请求映射成方法参数；涉及请求体（@RequestBody）时，参数解析会委托 `HttpMessageConverter` 根据 `Content-Type` 反序列化成 Java 对象。
- 返回值同理：`HandlerMethodReturnValueHandler` 决定如何处理返回值；如果是 `@ResponseBody/ResponseEntity`，再交给 `HttpMessageConverter` 按 `Accept`/`produces` 选择合适的 converter 序列化输出。
- 自定义 Converter 的最大坑：排序与匹配（Content-Type/Accept）、覆盖默认 Jackson 配置导致行为变化、以及大对象序列化/反序列化引发内存与延迟问题。生产优化要围绕“限制、流式、压缩、分页、字段裁剪、异步与背压”。

### 2) 参数解析如何工作（HandlerMethodArgumentResolver 链）
- 入口位置
  - `RequestMappingHandlerAdapter` 在执行 handler 方法前，会把方法参数逐个交给 argument resolvers 处理
- 解析链路（简化版）
  - 1) 获取 `HandlerMethod`（Controller 方法 + 参数元信息）
  - 2) 对每个参数依次遍历 resolvers：`supportsParameter()` 命中则 `resolveArgument()`
- 常见参数解析器（你说几个就加分）
  - `@PathVariable`：从 URI 模板变量取值
  - `@RequestParam`：从 query/form 取值（带类型转换、默认值）
  - `@RequestHeader`：从 header 取值
  - `@CookieValue`：从 cookie 取值
  - `@RequestBody`：走消息转换（HttpMessageConverter）
  - `@ModelAttribute`：把请求参数绑定到对象（DataBinder + 类型转换 + 校验）
  - `HttpServletRequest/Response`：直接注入原始对象
- 类型转换与校验（常见追问点）
  - `ConversionService/Formatter` 负责 String->目标类型转换（日期、枚举等）
  - `@Valid/@Validated` 触发 Bean Validation（Hibernate Validator）并在失败时抛异常交给异常处理器

### 3) 消息转换如何工作（HttpMessageConverter 选择与读写）
- 请求体反序列化（@RequestBody）
  - Spring 会根据：
    - 请求 `Content-Type`（例如 application/json）
    - 目标参数类型（Java Type，含泛型）
    - converter 的 `canRead(...)`
  - 选择一个 converter 执行 `read(...)`
  - 典型：`MappingJackson2HttpMessageConverter` 使用 Jackson ObjectMapper 读 JSON
- 响应体序列化（@ResponseBody / ResponseEntity）
  - Spring 会根据：
    - 请求 `Accept`（客户端希望的媒体类型）
    - Controller 的 `produces`
    - 返回值类型
    - converter 的 `canWrite(...)`
  - 选择 converter 执行 `write(...)`
- 选择顺序（非常关键）
  - converters 是一个有序列表：先匹配的先用
  - 自定义 converter 插入位置会影响匹配结果（可能抢走本该由 Jackson 处理的请求/响应）

### 4) 自定义 Converter 的常见坑（生产踩雷点）
- 坑 1：Content-Type/Accept 匹配不严谨导致“误命中”
  - 表现：你加了一个 converter，结果 application/json 也被它处理，Jackson 不用了
  - 规避：精确声明支持的 mediaTypes，只做自己该做的
- 坑 2：converter 顺序导致覆盖默认行为
  - 表现：响应 Content-Type 变了、字段格式变了、日期序列化策略变了
  - 规避：明确注册顺序；优先用 `extendMessageConverters` 而不是 `configureMessageConverters`（后者可能清空默认列表）
- 坑 3：ObjectMapper 被全局替换引发“兼容性事故”
  - 表现：某些字段忽略策略变化、null 处理变化、日期/枚举格式变化，线上接口兼容性破坏
  - 规避：
    - 使用 `Jackson2ObjectMapperBuilderCustomizer` 或局部 ObjectMapper
    - 对外接口保持稳定的序列化协议（版本化/契约测试）
- 坑 4：泛型类型解析不一致
  - 表现：List / Map 反序列化成 LinkedHashMap、类型擦除导致转换失败
  - 规避：确保 converter 能正确获取 `JavaType`（Jackson 的 TypeFactory），或不要用过于宽泛的 Object 类型
- 坑 5：大对象导致内存抖动与 GC 压力
  - 表现：Young GC/Full GC 增多，P99 飙升，甚至 OOM
  - 规避：见第 5 节优化策略

### 5) 追问：大 JSON 导致内存抖动、慢请求怎么优化（流式、限制、压缩）
- 5.1 限制（先止血）
  - 请求体大小限制
    - Tomcat/Undertow 的 max post size、Spring 的 multipart/请求限制（按你的容器栈配置）
    - 网关层也要限（更靠前更省资源）
  - 字段与结构限制
    - 对外 API 明确最大数组长度、最大嵌套深度（防止恶意/异常 payload）
  - 超时预算
    - 将解析/处理时间纳入整体超时预算，避免客户端超时后服务端还在反序列化占资源
- 5.2 流式（减少峰值内存）
  - 使用 Jackson Streaming API（JsonParser/JsonGenerator）或 `MappingJackson2HttpMessageConverter` 的 streaming 能力（针对特定场景自定义）
  - 对超大列表采用分片/分页/游标（cursor）返回，而不是一次性返回全量
  - 文件/大数据传输用二进制流或 NDJSON（逐行 JSON）等更易流式处理的格式（按场景评估）
- 5.3 压缩（降低网络与解析压力）
  - 启用 gzip/br（服务端响应压缩，客户端请求压缩视生态而定）
  - 注意：压缩节省带宽但增加 CPU；在 CPU 紧张时要评估得失，并对大响应/特定 content-type 开启
- 5.4 序列化裁剪（减少输出量）
  - 只返回必要字段：DTO 分层、字段白名单
  - 使用视图/投影（如 Jackson @JsonView 或自定义 DTO）
  - 对大字段（如 base64、长文本）按需返回或改为对象存储链接
- 5.5 可观测与定位（避免“猜”）
  - 指标：请求体大小分布、反序列化耗时、序列化耗时、响应大小、GC 次数与停顿
  - Trace：拆分 Controller 耗时中 converter 的占比
  - 日志：对超阈值 body 只记录摘要（hash/前 N 字节），避免日志放大事故

### 6) 小结（一句话复盘）
- Spring MVC 通过 ArgumentResolver 解析参数、通过 HttpMessageConverter 按 Content-Type/Accept 选择读写实现；自定义 converter 的坑主要在媒体类型匹配与顺序、全局 ObjectMapper 覆盖与泛型类型处理；大 JSON 优化优先限流限大小，其次流式/分页与字段裁剪，再结合压缩与观测把内存抖动与慢请求压下去。

---

## 4. 全局异常处理怎么做？为什么有时 @ControllerAdvice 接不住异常？（含追问：Filter 异常/网关超时/异步线程异常怎么兜）
### 1) 结论（标准答案）
- Spring MVC 全局异常处理的主战场是 `@ControllerAdvice + @ExceptionHandler`（或继承 `ResponseEntityExceptionHandler`），它本质是注册到 `HandlerExceptionResolver` 链中，在“Controller 调用链内部”捕获异常并转换为统一响应。
- @ControllerAdvice 接不住异常的根因通常是：异常发生在 MVC 链路之外（Filter/Servlet 容器/网关/异步线程），或者响应已提交（response committed），又或者异常被其它 Resolver/容器错误页机制提前处理。
- 兜底策略要分层：网关层处理超时与统一错误码；Filter/容器层用 ErrorPage/异常处理 Filter 兜底；MVC 层用 ControllerAdvice；异步线程用线程级异常处理与任务回收机制。

### 2) 全局异常处理怎么做（推荐落地方案）
- 2.1 基础方案：@ControllerAdvice + @ExceptionHandler
  - 目标：统一返回体、统一错误码、统一日志与 traceId
  - 典型结构
    - 定义业务异常：BizException（含 errorCode、message、httpStatus 可选）
    - @ControllerAdvice 捕获：
      - BizException → 返回业务错误码
      - MethodArgumentNotValidException / BindException → 参数校验错误
      - ConstraintViolationException → path/query 校验错误
      - HttpMessageNotReadableException → JSON 解析错误
      - Exception → 兜底 500（注意不要吞掉关键日志）
- 2.2 进阶方案：继承 ResponseEntityExceptionHandler
  - 优点：对 Spring MVC 常见异常（参数绑定、媒体类型、方法不支持）已有默认处理入口，便于统一覆盖
- 2.3 统一响应规范（生产建议）
  - 返回体包含：traceId、code、message、timestamp、path
  - 对外 message 做脱敏，对内日志保留完整堆栈与上下文
- 2.4 与日志/链路追踪联动
  - 在 Filter/Interceptor 注入 traceId（MDC），异常处理器返回 traceId，便于线上定位
  - 记录关键字段：uri、method、userId/tenantId、params 摘要、body 摘要（谨慎）、耗时

### 3) 为什么有时 @ControllerAdvice 接不住异常（高频原因清单）
- 原因 1：异常发生在 DispatcherServlet 之外（Filter/Servlet 容器阶段）
  - 例如：Filter 中抛异常、body wrapper 读流异常、跨域/编码处理异常
  - 结果：还没进入 HandlerExceptionResolver 链，@ControllerAdvice 自然接不到
- 原因 2：异常发生在 Controller 之后但响应已提交（response committed）
  - 例如：流式下载/分块写出过程中抛异常
  - 结果：响应头/部分 body 已写出，无法再返回你定义的 JSON 错误体
- 原因 3：异常被其它 HandlerExceptionResolver 提前处理或被容器错误页接管
  - Spring MVC 有一条 resolver 链：谁先处理谁生效
  - 某些异常可能被默认 resolver 处理成特定响应，导致你的 Advice 不生效（或你匹配不到）
- 原因 4：异常发生在异步线程/异步请求分派之外
  - @Async、线程池任务、CompletableFuture 内部异常不在当前请求线程
  - 结果：Advice 只管当前请求线程里的 MVC 调用链
- 原因 5：你捕获的异常类型不对（包装异常/根因未 unwrap）
  - 例如：ServletException 包住业务异常，Advice 只写了 BizException
  - 结果：未命中你的 @ExceptionHandler
- 原因 6：异常被你自己 catch 掉了
  - 结果：Advice 看不到异常，只能看到“正常返回”，可能导致错误码不一致

### 4) 追问：Filter 里抛的异常怎么兜？
- 推荐做法 1：在 Filter 链最外层放一个“异常兜底 Filter”
  - 捕获链路中所有异常，统一写出 JSON 错误体（或转发到 /error）
  - 注意：
    - 必须判断 response 是否已提交
    - 必须保证字符集、content-type、错误码一致
- 推荐做法 2：使用容器错误页机制 / Spring Boot 的 /error
  - Boot 默认提供 BasicErrorController（/error），可通过 ErrorAttributes 自定义输出
  - Filter 异常可通过抛出到容器，由容器转发到 /error（取决于配置与异常类型）
- 生产建议
  - 对外统一：Filter 兜底 + /error 统一输出，避免出现 HTML 错误页混入 JSON API
  - 对内记录：Filter 兜底要记录完整异常堆栈与 traceId

### 5) 追问：网关超时怎么兜？
- 关键认知
  - 网关超时很多时候发生在“请求还没到后端”或“后端处理太慢但网关先断开”
  - 后端即使有 @ControllerAdvice，也无法把错误返回给客户端（连接已断/响应已由网关返回）
- 推荐策略（网关层）
  - 统一超时响应体与错误码（例如 GATEWAY_TIMEOUT）
  - 配置合理的超时预算（网关 < 服务 < DB/下游），避免层级倒挂
  - 对超时做观测与报警：按路由/服务/方法维度统计超时率、P99
- 后端配合（服务层）
  - 降低事务持锁时间，避免慢 IO 在事务内
  - 对外部依赖加超时/熔断/限流，防止级联超时
  - 在日志/trace 中记录“请求被取消/客户端断开”的信号（若框架能提供）

### 6) 追问：异步线程异常怎么兜（@Async/线程池/CompletableFuture）
- 6.1 @Async 的异常处理
  - 返回类型是 void：异常不会抛到调用方，必须配置 AsyncUncaughtExceptionHandler 记录与告警
  - 返回 Future/CompletableFuture：异常封装在 future 中，需要调用方显式处理（exceptionally/handle/get）
- 6.2 线程池任务兜底
  - 为线程池设置统一的 UncaughtExceptionHandler（对非捕获异常兜底日志）
  - 对任务执行包装：捕获异常 → 记录 traceId → 上报 metrics → 进入补偿队列/死信
- 6.3 与一致性相关的建议
  - 不要指望 @ControllerAdvice 处理异步异常；异步任务应该有自己的失败语义与重试/补偿机制
  - 对外副作用建议 afterCommit 触发；失败进入补偿任务表（可观测、可重试、可人工介入）

### 7) 生产级注意事项（加分）
- 响应已提交时的策略
  - 只能记录日志与指标，无法改变响应；对流式接口要特别设计错误输出协议（如在流中嵌入错误标记）
- 异常分类与告警
  - 业务异常（4xx）与系统异常（5xx）分开统计
  - 对关键异常（DB 超时、连接池耗尽、下游熔断）要单独告警与联动降级
- 安全与合规
  - 对外不要返回堆栈与敏感信息；对内日志要脱敏并控制采样

### 8) 小结（一句话复盘）
- 全局异常处理以 @ControllerAdvice 为核心，它只覆盖 MVC 调用链内部；接不住通常因为异常发生在 Filter/网关/异步线程或响应已提交；兜底要分层：Filter/容器用异常兜底与 /error，网关统一超时输出，异步任务用专用异常处理与补偿重试闭环。

---
# 并发、线程池、可观测性（高级岗位很爱问）
## 1. @Async 的原理是什么？和事务/AOP 的关系与坑点？（含追问：异步线程如何拿到 MDC/TraceId？如何做上下文传播？）
### 1) 结论（标准答案）
- `@Async` 本质也是 Spring AOP：被标注的方法会被代理拦截，拦截器把方法调用封装成 `Runnable/Callable` 提交到线程池（TaskExecutor）执行；调用方线程立即返回（void）或返回一个 Future/CompletableFuture。
- 与事务/AOP 的关系关键在两点：1）异步线程与原线程不是同一线程，`TransactionSynchronizationManager` 的 ThreadLocal 事务上下文不会传播，所以异步方法默认不在原事务里；2）`@Async` 同样受代理边界限制，自调用会失效，且与 `@Transactional` 的组合顺序与边界会影响最终行为。
- MDC/TraceId 这类上下文通常也基于 ThreadLocal，因此异步线程默认拿不到；生产上需要“上下文传播”机制（TaskDecorator/包装 Runnable、或使用框架的 Context Propagation）。

### 2) @Async 的原理（执行链与关键组件）
- 生效条件
  - 开启异步：`@EnableAsync`（Boot 常见通过自动配置或显式开启）
  - 容器注册异步基础设施：AsyncAnnotationBeanPostProcessor（负责识别 @Async 并为 Bean 创建代理/增强）
- 核心执行过程（简化版）
  - 1) 调用进入代理
  - 2) 异步拦截器识别 @Async
  - 3) 选择执行器（TaskExecutor）
    - 优先使用 `@Async("executorBeanName")` 指定的执行器
    - 否则使用容器中默认的 TaskExecutor（或 SimpleAsyncTaskExecutor 兜底，生产不建议）
  - 4) 将方法调用封装为任务提交线程池
    - 返回 void：提交后立即返回，异常走 AsyncUncaughtExceptionHandler
    - 返回 Future/CompletableFuture：异常封装在 future 中，由调用方处理
- 关键类（面试加分）
  - `AsyncAnnotationBeanPostProcessor`（扫描 @Async 并注册增强）
  - `AnnotationAsyncExecutionInterceptor` / `AsyncExecutionInterceptor`（把调用转为线程池任务）
  - `TaskExecutor`（通常是 ThreadPoolTaskExecutor）

### 3) 和事务/AOP 的关系（最常被追问的坑）
- 事务 ThreadLocal 不会跨线程
  - 原因：事务资源绑定在 `TransactionSynchronizationManager` 的 ThreadLocal 上
  - 结果：
    - 外层事务未提交时启动 @Async：异步线程读不到未提交数据（RC/RR 都如此）
    - 异步线程的写操作若标注 @Transactional，将开启自己的新事务（独立 commit/rollback）
- AOP 代理边界仍然存在
  - 同类自调用：`this.asyncMethod()` 不会走代理，@Async 不生效
  - 解决：拆分到独立 Bean，通过注入调用；或用事件驱动（ApplicationEvent）间接触发
- @Async 与 @Transactional 组合的典型语义（你要能讲清）
  - 场景 A：外层方法 @Transactional，内部调用 @Async 方法
    - 异步方法与外层事务无关，外层回滚不影响异步已提交的副作用（极易不一致）
    - 推荐：把异步触发推迟到 afterCommit（见第 5 节）
  - 场景 B：@Async 方法自身 @Transactional
    - 异步线程内会开启自己的事务（REQUIRED），独立提交/回滚
    - 注意连接池与锁：异步任务并发高时事务会放大数据库压力
- 顺序与边界（高级追问点）
  - Spring 是多个 Advisor 叠加：@Async 和 @Transactional 都是拦截器
  - 实际效果取决于谁在外层包裹谁：通常希望 @Async 拦截后把任务丢给线程池，事务在异步线程内再创建（即事务边界在异步线程）
  - 最稳做法：把 @Async 与 @Transactional 放在同一个异步方法上，让事务明确发生在异步线程

### 4) 常见坑点清单（生产级）
- 坑 1：异步任务异常“悄悄丢了”
  - void 返回的 @Async 异常不会抛回调用方，默认只日志或被吞
  - 解决：配置 AsyncUncaughtExceptionHandler；或返回 CompletableFuture 并强制处理异常
- 坑 2：线程池不合理导致雪崩
  - 默认执行器或无界队列导致 OOM/延迟无限增长
  - 解决：ThreadPoolTaskExecutor 明确 core/max/queue/reject，指标监控与压测调参
- 坑 3：上下文丢失（MDC/TraceId/用户上下文）
  - ThreadLocal 不传播，日志断链
  - 解决：TaskDecorator 或框架 Context Propagation
- 坑 4：事务与一致性错位
  - 外层事务回滚了，异步任务已做了副作用（发消息、写表、回调）
  - 解决：afterCommit 触发异步；Outbox/事务消息；消费幂等
- 坑 5：自调用导致 @Async 不生效
  - 解决：拆 Bean、注入代理调用

### 5) 追问：异步线程如何拿到 MDC/TraceId？如何做上下文传播？
- 关键认知
  - MDC/TraceId 通常基于 ThreadLocal（如 slf4j MDC），异步线程默认拿不到
  - 上下文传播要做两件事：提交任务时“捕获上下文”，执行任务时“恢复上下文”，执行完再“清理”
- 推荐方案 1：TaskDecorator（Spring 官方推荐路径之一）
  - 思路：为线程池设置 TaskDecorator，统一包装 Runnable/Callable
  - 行为：复制父线程 MDC -> 设置到子线程 -> 执行 -> finally 清理
  - 适用：你们统一使用 ThreadPoolTaskExecutor
- 推荐方案 2：手工包装（小范围快速落地）
  - 提交任务时捕获 MDC map 和 traceId
  - Runnable.run 里 set，再 finally remove/clear
  - 缺点：侵入业务代码，容易漏
- 推荐方案 3：使用统一的上下文传播框架
  - 若你们用了 Micrometer Tracing/OpenTelemetry，通常有现成的上下文传播能力（trace context）
  - 目标：不仅传播 traceId，还传播 baggage（tenantId、userId 等）并与日志关联
- 生产注意事项
  - 必须清理：线程池线程会复用，不清理会“串上下文”（A 请求的 traceId 出现在 B 请求日志里）
  - 传播内容要受控：避免把大对象放入 ThreadLocal 导致内存泄漏
  - 用户上下文传播要审慎：涉及权限/租户时要防止越权（只传播必要字段）

### 6) 生产级推荐组合（能直接落地）
- 异步触发时机：优先 afterCommit
  - 用 @TransactionalEventListener(phase = AFTER_COMMIT) 发布事件，再由 @Async 监听器处理
- 执行器：显式 ThreadPoolTaskExecutor + 指标
  - core/max/queue/reject + 线程命名 + 监控 active/queue/rejected
- 上下文：TaskDecorator + Trace/MDC 统一
  - 捕获/恢复/清理三个动作固定模板化
- 异常：Future/CompletableFuture 强制处理 + 失败进入补偿任务表
  - 不要让异步失败变成“黑洞”

### 7) 小结（一句话复盘）
- @Async 通过 AOP 代理把方法调用提交到线程池执行；事务与 MDC 都依赖 ThreadLocal，因此默认不跨线程，容易造成一致性与链路丢失问题；生产上用 afterCommit 触发异步、让事务发生在异步线程内、用 TaskDecorator 传播并清理 MDC/TraceId，并配套线程池治理与异常补偿，才能稳定上线。

---
## 2. Spring 里你如何统一治理线程池（命名、队列、拒绝策略、监控）？生产怎么压测与调参？（含追问：线程池打满时的止血动作）
### 1) 结论（标准答案）
- 线程池治理的核心目标是：可控（有边界）、可观测（能看见）、可恢复（打满能止血）、可演进（压测可调参）。在 Spring 里建议统一用 `ThreadPoolTaskExecutor`（或显式 `ThreadPoolExecutor`）集中定义，提供统一命名、统一拒绝策略、统一上下文传播（TaskDecorator）、统一指标采集，并禁止随手 new Thread/Executors.newFixedThreadPool。
- 调参靠压测与指标闭环：用目标 QPS/并发把队列、线程、下游依赖的 P99、GC 与 CPU 一起压出来；不要凭经验拍 core/max。线程池打满时先“限流/降级/熔断/快速失败”止血，再做容量与架构优化。

### 2) 统一治理的设计方案（生产可落地）
- 2.1 线程池分域（不要一个池子打天下）
  - IO 型（远程调用、MQ、文件、HTTP）与 CPU 型（计算、加密、序列化）分池
  - 关键业务与非关键业务分池（例如：下单核心池 vs 异步通知池）
  - 避免：非关键任务堆积把核心线程池拖死
- 2.2 统一命名与线程工厂（定位问题的第一生产力）
  - 线程名前缀包含：业务域 + 机器/实例标识 + 池用途
  - 线程未捕获异常处理：UncaughtExceptionHandler 统一记录 + 指标上报
- 2.3 队列策略（有界优先）
  - 生产推荐：有界队列（ArrayBlockingQueue/LinkedBlockingQueue with capacity）
  - 不推荐：无界队列（默认 LinkedBlockingQueue 无容量）→ 延迟无限增长，最终 OOM
  - 选择思路
    - 需要“削峰”但可接受排队：有界队列
    - 需要“低延迟优先”：小队列 + 更强拒绝/回压
- 2.4 拒绝策略（必须与业务语义绑定）
  - AbortPolicy（抛异常）：最清晰的快速失败（很多核心链路推荐）
  - CallerRunsPolicy（调用线程执行）：形成回压，但会拖慢上游线程（可能拖垮 Tomcat 工作线程，需谨慎）
  - Discard/DiscardOldest：不建议用于关键业务（丢任务不可控），除非是可丢弃的“统计/埋点”类任务
  - 自定义 RejectedExecutionHandler（推荐）
    - 记录拒绝指标、按任务类型分流（例如写入补偿表/转 MQ/返回快速失败）
- 2.5 统一监控（没有监控=不可控）
  - 必备指标
    - activeCount（活跃线程数）
    - poolSize/core/max
    - queueSize/queueRemaining
    - rejectedCount（拒绝次数）
    - taskCount/completedTaskCount
    - taskLatency（任务执行耗时分布，P95/P99）
    - queueWaitTime（排队等待耗时，P95/P99）
  - 采集方式（Spring 生态）
    - Micrometer + Prometheus：对 ThreadPoolTaskExecutor 注册 Gauge/Counter/Timer
    - 日志：拒绝时打关键字段（池名、active、queueSize、任务摘要、traceId）
- 2.6 统一上下文传播（TaskDecorator）
  - MDC/TraceId、用户/租户上下文按需传播
  - 注意清理，避免线程复用导致串上下文

### 3) Spring 中的实现落地（推荐做法）
- 3.1 集中定义线程池 Bean（按用途命名）
  - orderCoreExecutor、ioExecutor、notifyExecutor、schedulerExecutor 等
- 3.2 禁止散落创建
  - 代码规范：禁止 Executors.new*；禁止 new Thread；统一从容器注入
  - 通过静态扫描/代码审查/单测约束
- 3.3 对 @Async 指定执行器
  - `@Async("orderCoreExecutor")` 明确绑定到业务域线程池
  - 避免全部落到默认池导致互相影响
- 3.4 调度任务也统一线程池
  - @Scheduled 任务使用独立的 scheduler 线程池，避免与异步任务抢资源

### 4) 生产怎么压测与调参（闭环方法）
- 4.1 先明确边界条件（没有就用假设）
  - 目标：QPS、并发、P99、可接受的排队时间、失败策略（快速失败还是排队）
  - 下游依赖：DB/MQ/HTTP 的 P99 与超时预算
- 4.2 用 Little 定律做初始估算（工程师口径）
  - 并发需求 ≈ QPS * 平均耗时（或 P95/P99 耗时做保守估计）
  - 对 IO 型任务：线程数通常与外部等待有关，可能 > CPU 核数
  - 对 CPU 型任务：线程数不应显著超过 CPU 核数（避免上下文切换）
- 4.3 压测维度（不要只压接口）
  - 压接口同时观察：线程池队列、拒绝、任务耗时、DB 连接池、GC、CPU、负载
  - 关键看：排队时间是否开始主导 P99（queueWaitTime 飙升即危险信号）
- 4.4 调参顺序（建议）
  - 先修业务：降低单任务耗时（减少锁、减少远程、批处理、缓存）
  - 再调超时：缩短外部依赖超时避免线程长期阻塞
  - 再调容量：core/max/queue
  - 最后调策略：拒绝/降级/回压策略与告警阈值
- 4.5 验收标准（上线前必须过）
  - 高峰期 active 不长期贴顶
  - queue 不持续增长（增长=系统无法消化输入）
  - rejected 在可控范围（或为 0）
  - P99 达标且无长尾失控
  - 故障注入（下游变慢/超时）时能稳定降级而不是雪崩

### 5) 追问：线程池打满时的“止血动作”怎么做？
- 止血目标（先保核心链路）
  - 让系统从“排队爆炸/资源耗尽”回到“可控失败”
- 立即可做的止血动作（按优先级）
  - 1) 快速失败 + 限流
    - 在入口（网关/Filter/业务入口）对相关接口限流，返回明确错误码（系统繁忙）
    - 对非核心功能直接降级/关闭开关（通知、报表、画像刷新）
  - 2) 调整拒绝策略为可控行为
    - 核心链路：AbortPolicy + 明确错误码（避免把 Tomcat 线程拖死）
    - 非核心链路：可改为丢弃/合并/采样（例如埋点任务）
  - 3) 降低单任务耗时（立刻见效的）
    - 缩短下游超时（HTTP/RPC/DB），避免线程长时间阻塞
    - 熔断慢依赖（Sentinel/Resilience4j），让慢依赖不再吞线程
  - 4) 控制提交速率（回压）
    - 对生产者侧加 backpressure（例如队列长度阈值触发降级）
    - 谨慎使用 CallerRuns：可能把压力传导到 Web 容器线程导致整体不可用
  - 5) 临时扩容（最后但有效）
    - 水平扩容实例数，前提是下游能扛住（DB/MQ 不是瓶颈）
    - 垂直扩容/调大线程池参数需要评估 CPU 与上下文切换风险，不能盲目加大
- 事后优化（避免复发）
  - 将任务异步化/批量化/合并（削峰）
  - 将外部调用移出事务、减少锁持有
  - 给每类任务建立独立线程池与隔离舱壁（Bulkhead）
  - 建立告警阈值：queueWaitTime、rejectedCount、active贴顶时提前告警

### 6) 小结（一句话复盘）
- 线程池治理要做到分域隔离、命名可定位、队列有界、拒绝可控、指标齐全；调参靠压测与指标闭环，重点盯排队时间与拒绝；打满时先限流降级与快速失败止血，再通过超时/熔断/隔离与容量规划把系统拉回可控区间。

---

## 3. Spring 事件机制（ApplicationEvent / Listener）在事务里的执行时机？@TransactionalEventListener 有何价值？（含追问：afterCommit 才发消息怎么实现？失败如何补偿？）
### 1) 结论（标准答案）
- Spring 事件机制的默认行为是“同步发布、同步执行”：在当前线程里 `ApplicationEventPublisher.publishEvent()` 立刻调用所有匹配的 Listener；如果你在事务方法里发布事件，那么默认 Listener 也是在“事务尚未提交”的阶段执行。
- `@TransactionalEventListener` 的价值是把事件处理挂到事务同步回调上：你可以指定在 `AFTER_COMMIT/AFTER_ROLLBACK/AFTER_COMPLETION/BEFORE_COMMIT` 某个阶段再执行，从而实现“事务提交后再做副作用”（发 MQ、发通知、刷新缓存/索引），避免“DB 回滚但消息已发出”的不一致。
- afterCommit 发消息最稳的落地通常是：`@TransactionalEventListener(phase = AFTER_COMMIT)` + 异步执行（@Async）或 Outbox；失败补偿用重试/死信/补偿任务表/对账闭环。

### 2) Spring 事件机制在事务里的执行时机（默认 vs 事务感知）
- 默认事件（ApplicationEvent / @EventListener）
  - publishEvent 发生在哪：当前线程立即执行
  - 在事务内发布：Listener 运行时事务通常“仍在进行中”，尚未 commit
  - 风险：Listener 做外部副作用（发 MQ/HTTP 回调）时，后续事务回滚会导致不一致
- 事务感知事件（@TransactionalEventListener）
  - publishEvent 时不一定立刻执行（取决于 phase）
  - 事件会被注册为事务同步（TransactionSynchronization）
  - 事务到达指定 phase 时才回调执行
  - 好处：把“外部副作用”与“本地事务提交”对齐，减少分布式不一致

### 3) @TransactionalEventListener 的 phase 语义（面试高频）
- BEFORE_COMMIT
  - 提交前触发（仍在事务中）
  - 适用：需要在提交前做校验/准备，但仍要谨慎做外部调用（会延长锁）
- AFTER_COMMIT（最常用）
  - 事务提交成功后触发
  - 适用：发 MQ、通知、刷新缓存、异步计算、更新 ES 索引等副作用
- AFTER_ROLLBACK
  - 事务回滚后触发
  - 适用：记录失败审计、写失败补偿任务、回滚告警
- AFTER_COMPLETION
  - 提交或回滚都会触发
  - 适用：清理资源、释放本地上下文、收尾统计

### 4) @TransactionalEventListener 的价值（为什么它是生产利器）
- 价值 1：把副作用推迟到“提交已确定”的时刻
  - 避免“消息先发出、事务后回滚”导致的幽灵事件
- 价值 2：降低锁持有时间（提升吞吐）
  - 外部调用不放在事务内执行，减少事务时间与锁等待
- 价值 3：让一致性设计更结构化
  - 主流程只负责本地一致性
  - 事件监听器负责副作用，失败有专用补偿路径
- 价值 4：与异步天然组合
  - AFTER_COMMIT + @Async：提交后异步处理，吞吐更高且语义更正确

### 5) 追问：afterCommit 才发消息怎么实现？
- 方式 A：@TransactionalEventListener + @Async（常用且简单）
  - 流程
    - 事务内 publishEvent（只注册，不立刻做副作用）
    - commit 成功后触发 Listener
    - Listener 用 @Async 投递 MQ（或调用远程）
  - 注意点
    - Listener 执行失败不会回滚已提交事务，因此必须设计重试/补偿（见第 6 节）
- 方式 B：Outbox（事务消息表）（更强一致与可审计）
  - 流程
    - 事务内：写业务表 + 写 outbox_event
    - commit 后：后台扫描 outbox_event 投递 MQ（可重试、可对账）
  - 与 TransactionalEventListener 的关系
    - 事件监听器可以负责“写 outbox”（而不是直接发 MQ）
    - 或者主流程直接写 outbox，再由投递器发送
- 方式 C：事务消息（MQ 支持两阶段）
  - 事务内发半消息，提交后确认消息
  - 仍需消费端幂等与回查机制

### 6) 追问：失败如何补偿？（事件/消息失败闭环）
- 关键认知
  - AFTER_COMMIT 的监听器失败时，本地事务已经提交，不可能靠回滚修复；必须通过“重试 + 幂等 + 死信/补偿任务 + 对账”闭环。
- 补偿策略（推荐组合）
  - 6.1 重试（有上限 + 退避）
    - Listener 内部捕获异常，写入重试任务表或 outbox 状态置为 RETRY
    - 指数退避 + 抖动，设置最大重试次数，超过进入 DEAD
  - 6.2 幂等（必须）
    - 发送端：event_id/biz_key 唯一，避免重复写事件
    - 消费端：幂等表（唯一键）或业务状态机（条件更新）
  - 6.3 死信与人工介入
    - DEAD 任务进入告警与工单，支持手动重放/补发
  - 6.4 对账（最终兜底）
    - 定期检查业务真相源与下游状态差异，生成补偿任务，保证最终一致
- 可观测性（必须有，否则补偿不可控）
  - 指标：待处理事件数、最老事件年龄、成功率、重试次数、DEAD 数量
  - 日志：event_id、biz_key、traceId、payload 摘要、异常栈、重试轨迹
  - 告警：backlog 超阈值、age 超阈值、DEAD>0、成功率下降

### 7) 生产级注意事项（容易踩坑的边界）
- 事务不存在时怎么办
  - @TransactionalEventListener 默认需要事务上下文；无事务发布事件可能不触发（可用 fallbackExecution=true 作为兜底，但要明确语义）
- 同步 vs 异步
  - 事务回调本身是同步触发的；你要异步必须显式 @Async 或投递到队列
- 不要在 BEFORE_COMMIT 做外部调用
  - 会拉长事务时间与锁持有，影响吞吐并放大故障面

### 8) 小结（一句话复盘）
- 默认 Spring 事件在事务内是同步执行，可能在 commit 前就做副作用；@TransactionalEventListener 通过事务同步回调把事件处理挂到 AFTER_COMMIT 等阶段，实现提交后再发消息；失败不能靠回滚，只能用重试+幂等+死信/补偿任务+对账与监控闭环兜底。

---

# 源码/设计题（真正“深度加分”）
## 1. Spring 为什么要把扩展点分成 BFPP/BPP？分别解决哪类问题？
### 1) 结论（标准答案）
- Spring 把扩展点分成 BFPP（BeanFactoryPostProcessor）和 BPP（BeanPostProcessor），本质是把“改图纸”和“改成品”分开：BFPP 发生在实例化普通 Bean 之前，用来批量/全局地修改 BeanDefinition 或 BeanFactory 配置；BPP 发生在 Bean 创建过程中（初始化前后），用来增强或替换 Bean 实例（典型是 AOP 代理、注解注入处理、初始化回调处理）。
- 这种拆分解决了两类完全不同的问题：1）在“对象尚未创建”时对定义与创建策略做全局调整（BFPP）；2）在“对象已创建”时对实例做装配、包装与横切增强（BPP）。同时还能保证容器启动的时序可控：先把“改定义的人”跑完，再把“改实例的人”准备好，最后批量创建业务 Bean。

### 2) BFPP（BeanFactoryPostProcessor）解决什么问题（改图纸/改工厂）
- 作用对象
  - BeanDefinition（图纸）：beanName、class、scope、dependsOn、propertyValues、constructorArgs 等元信息
  - BeanFactory（工厂）：如占位符解析、属性源、解析器、注册表等
- 执行时机
  - refresh() 早期：在大规模实例化业务 Bean 之前执行
- 典型能力
  - 统一替换/补全属性：把 `${...}` 占位符解析成真实值写回 BeanDefinition
  - 动态注册/修改 BeanDefinition：扫描并注册额外 Bean（例如解析 @Configuration/@Import/@MapperScan）
  - 批量调整创建策略：统一设置 scope、懒加载、依赖关系、优先级等
- 典型实现（面试常点名）
  - BeanDefinitionRegistryPostProcessor（BFPP 的子类，更强）
    - `ConfigurationClassPostProcessor`：解析 @Configuration/@ComponentScan/@Import，注册更多 BeanDefinition
  - `PropertySourcesPlaceholderConfigurer`：解析配置占位符
- 适用场景（生产）
  - 写 starter/SDK：想在不改业务代码的情况下“注册一批 BeanDefinition”
  - 全局配置注入：把环境配置映射成 BeanDefinition 属性
  - 批量改造：统一加前缀、统一 scope、统一懒加载策略（谨慎）

### 3) BPP（BeanPostProcessor）解决什么问题（改成品/加壳）
- 作用对象
  - Bean 实例：已经 new 出来或即将初始化的对象
- 执行时机
  - Bean 创建过程中的关键钩子：
    - 初始化前：postProcessBeforeInitialization
    - 初始化后：postProcessAfterInitialization（AOP 代理最常发生在这里）
  - 另外一些 BPP 还会参与属性填充阶段（如处理 @Autowired/@Value）
- 典型能力
  - AOP 代理与装饰：给目标 Bean 包一层代理，织入事务/日志/鉴权等
  - 注解驱动的依赖注入与生命周期：处理 @Autowired/@Value/@PostConstruct/@PreDestroy
  - 统一增强：对某些类型 Bean 注入公共依赖、做校验、做包装（如添加拦截器、添加 listener）
- 典型实现（面试常点名）
  - `AutowiredAnnotationBeanPostProcessor`：处理 @Autowired/@Value（会参与属性注入）
  - `CommonAnnotationBeanPostProcessor`：处理 @PostConstruct/@PreDestroy
  - `AbstractAutoProxyCreator`：AOP 自动代理创建（事务、切面等）

### 4) 为什么必须拆成两类（设计动机与时序控制）
- 4.1 解决“时机不同”的问题
  - 定义阶段能解决的事（改 BeanDefinition）在实例创建后就很难/不该做；实例阶段能解决的事（代理/注入）在定义阶段又做不了。
- 4.2 保证容器启动顺序可控
  - 必须先执行 BFPP：否则配置类解析、占位符替换、动态注册 BeanDefinition 都来不及，后续创建 Bean 会缺定义或属性不完整。
  - 必须尽早注册 BPP：否则业务 Bean 创建时不会被增强（例如 @Autowired 不注入、AOP 不代理）。
- 4.3 减少副作用与提高可维护性
  - BFPP 只碰元数据，适合做全局批量改造；BPP 碰实例，副作用更大，需要严格控制范围与顺序。
- 4.4 支持更强的扩展生态
  - Spring Boot 的自动配置、本质也是在定义阶段完成 BeanDefinition 的导入与条件判断（依赖 BFPP/配置类解析链路），而 AOP/注解注入在实例阶段生效（依赖 BPP）。

### 5) 常见追问点（你答得更像“懂源码的人”）
- 为什么 BDRPP（BeanDefinitionRegistryPostProcessor）要比普通 BFPP 更早执行？
  - 因为它能“新增 BeanDefinition”，必须在其它 BFPP/BPP 以及单例实例化前完成注册，否则后续流程看不到这些定义。
- 为什么要先 registerBeanPostProcessors 再 preInstantiateSingletons？
  - 因为 BPP 要参与业务 Bean 的创建过程（注入、代理、初始化回调），如果业务 Bean 先创建就错过增强时机。

### 6) 小结（一句话复盘）
- BFPP 负责在实例化前改 BeanDefinition/工厂配置（改图纸），BPP 负责在实例化过程中增强/替换 Bean 实例（改成品）；拆分的核心价值是把“可在定义阶段做的全局改造”和“只能在实例阶段做的对象增强”分离，并通过严格时序保证配置解析、条件装配、注入与 AOP 等能力稳定生效。

---
## 2. Spring 为什么要在创建 Bean 前提前实例化一些基础设施（例如某些 BPP）？顺序错了会怎样？
### 1) 结论（标准答案）
- Spring 之所以要在创建业务 Bean 之前“提前实例化基础设施”（最典型就是各种 BeanPostProcessor、部分 Aware 处理器、事件广播器等），是因为这些基础设施本身就是“参与创建 Bean 的创建过程”的插件：如果它们没先就绪，后续业务 Bean 在实例化/注入/初始化阶段就会错过增强与处理，导致注入失效、AOP 不生效、生命周期回调错过、配置类解析不完整等问题。
- 顺序错了会出现两类后果：1）功能性错误（某些注解不生效、代理没创建、依赖未注入、@PostConstruct 不执行）；2）更隐蔽的运行时不一致（部分 Bean 走了增强、部分没走增强，系统行为随机且难排障）。

### 2) “基础设施”有哪些（面试常点名）
- BeanPostProcessor 体系（最关键）
  - AutowiredAnnotationBeanPostProcessor：@Autowired/@Value 注入
  - CommonAnnotationBeanPostProcessor：@PostConstruct/@PreDestroy
  - AbstractAutoProxyCreator / InfrastructureAdvisorAutoProxyCreator：AOP 代理创建（事务、切面）
- BeanFactoryPostProcessor / BeanDefinitionRegistryPostProcessor（更早期）
  - ConfigurationClassPostProcessor：解析 @Configuration/@Import/@ComponentScan，注册更多 BeanDefinition
  - PropertySourcesPlaceholderConfigurer：解析 ${} 占位符
- 其它常见基础设施
  - ApplicationEventMulticaster（事件广播器）
  - ConversionService、Validator、MessageSource（类型转换、校验、国际化）

### 3) 为什么必须提前实例化（从“参与点”解释，而不是背顺序）
- 3.1 因为 BPP 要介入 Bean 创建流水线
- BPP 的介入点包括（关键时刻）
  - 属性填充阶段：例如 AutowiredAnnotationBeanPostProcessor 在 populateBean/后续回调中把依赖注入进去
  - 初始化前后：postProcessBeforeInitialization / postProcessAfterInitialization
    - AOP 代理通常在 afterInitialization 包装返回代理对象
- 如果业务 Bean 在 BPP 注册之前就被创建了
  - 它不会走这些回调 → 注入/代理/初始化增强全都缺失或不完整

- 3.2 因为 BFPP/BDRPP 要先“把图纸准备好”
- ConfigurationClassPostProcessor 需要先把 @Configuration 等解析成 BeanDefinition
- PlaceholderConfigurer 需要先把 ${} 替换成真实值写回 BeanDefinition
- 如果你先创建 Bean，再去改图纸
  - Bean 已经创建出来了，改图纸没有意义，甚至会造成定义与实例不一致

- 3.3 因为 Spring 需要保证“容器能力一致性”
- 容器启动时要保证：所有业务 Bean 都在同一套插件（BPP/Advisor/Converter/Validator）下创建
- 否则会出现“有的 Bean 被代理、有的 Bean 没代理”的不可控状态

### 4) 关键顺序（refresh() 主线里最相关的两步）
- 先 invokeBeanFactoryPostProcessors（BFPP/BDRPP）
  - 确保 BeanDefinition 完整、配置解析完成
- 再 registerBeanPostProcessors（注册并实例化 BPP）
  - 确保后续创建的 Bean 都会被 BPP 链处理
- 最后 finishBeanFactoryInitialization → preInstantiateSingletons
  - 才开始批量创建非懒加载单例业务 Bean

### 5) 顺序错了会怎样（典型故障清单）
- 5.1 BPP 注册太晚（或没注册）
- 现象与后果
  - @Autowired/@Value 不生效：字段为 null 或占位符未替换
  - @PostConstruct 不执行：初始化逻辑缺失（例如加载缓存/注册回调）
  - AOP 不生效：@Transactional、@Async、@Cacheable 等全失效或部分失效
  - 部分 Bean 没被代理：导致同一个接口的实现行为不一致（线上最难排）
- 典型事故
  - 事务方法不回滚/拦截器不执行，但只有“某几个 Bean”有问题（因为它们被提前实例化了）

- 5.2 BFPP/BDRPP 执行太晚
- 现象与后果
  - @Configuration/@Import 没解析完全：BeanDefinition 缺失，启动时报找不到 Bean
  - ${} 没替换：配置值是字面量字符串，导致连接串/超时/阈值异常
  - 条件装配判断错误：因为环境与定义未准备好
- 典型事故
  - “配置没生效”或“Bean 缺失”，但看代码没问题，实际上是解析顺序错了

- 5.3 更隐蔽的问题：不一致与随机性
- 场景
  - 某些 Bean 因为被早期引用/提前 getBean 而提前实例化
  - 导致它们在“BPP 完整注册之前”就创建了
- 后果
  - 同一套切面/注入规则对不同 Bean 生效不一致
  - 行为取决于启动时机与访问顺序，极难复现

### 6) 生产级定位与规避（面试加分）
- 定位
  - 开启 Spring 的 bean 创建与后处理日志（排查期）
  - 关注“谁触发了提前实例化”（某些配置类、静态初始化、@PostConstruct 里调用 getBean）
  - 看哪些 Bean 是在 registerBeanPostProcessors 前创建的（通常很危险）
- 规避
  - 不在配置类静态代码块、构造器、@PostConstruct 中随意调用 getBean（尤其是在容器刷新早期）
  - 基础设施与业务 Bean 分层清晰：基础设施通过自动配置/Registrar 注册，业务 Bean 不要触发容器早期访问
  - 对需要早期暴露的能力（比如 AOP）使用框架推荐的方式（Advisor/BPP），不要手写提前初始化逻辑

### 7) 小结（一句话复盘）
- 基础设施（尤其 BPP）必须在业务 Bean 创建前就绪，因为它们要参与 Bean 的注入、初始化与代理增强；顺序错了会导致注入/事务/AOP/生命周期回调失效或出现部分 Bean 生效、部分不生效的不一致状态，排障困难且容易线上事故。
---

## 3. 解释“容器刷新 refresh()”的大致阶段（不要求背源码，但要讲出关键阶段与目的）。
### 1) 结论（标准答案）
- `ApplicationContext#refresh()` 是 Spring 容器从“有一堆 BeanDefinition”到“容器可对外提供服务”的总装流程。你不需要背源码，但必须讲清三条主线：准备环境与工厂 → 先跑定义级扩展点（BFPP/BDRPP）→ 再注册实例级扩展点（BPP）→ 再创建单例 → 最后发布事件完成启动。

### 2) refresh() 的大致阶段（按顺序 + 每步目的）
- 1) 准备刷新（Prepare）
  - 目的：标记容器进入刷新状态、初始化时间/状态、校验必要属性、准备环境（Environment）与资源
  - 典型动作：prepareRefresh（重置标记、校验配置、准备 early events 容器等）
- 2) 获取/创建 BeanFactory（Obtain Fresh BeanFactory）
  - 目的：拿到一个“干净可用”的 BeanFactory（通常是 DefaultListableBeanFactory），并把加载到的 BeanDefinition 绑定进来
  - 典型动作：obtainFreshBeanFactory（创建/刷新 BeanFactory、加载/注册 BeanDefinitions）
- 3) 准备 BeanFactory（Prepare BeanFactory）
  - 目的：给 BeanFactory 注入容器基础能力与默认策略，让后续创建 Bean 有完整运行环境
  - 典型动作：
    - 设置 ClassLoader、表达式解析器、类型转换等
    - 注册一些内建的 Aware 处理器与可解析依赖（Environment、ResourceLoader 等）
- 4) BeanFactory 后置处理（BFPP/BDRPP）
  - 目的：在任何业务 Bean 实例化之前，对“图纸/工厂”做全局改造与补全
  - 典型动作：invokeBeanFactoryPostProcessors
    - ConfigurationClassPostProcessor：解析 @Configuration/@Import/@ComponentScan，注册更多 BeanDefinition
    - Placeholder/Property 处理：把 ${} 替换成真实值
- 5) 注册 BeanPostProcessor（BPP）
  - 目的：把“参与 Bean 创建流程的插件”提前就绪，保证后续业务 Bean 创建都经过同一套增强链
  - 典型动作：registerBeanPostProcessors（实例化并排序注册各种 BPP，包括 AOP 相关 BPP）
- 6) 初始化容器能力组件（Infrastructure）
  - 目的：让容器具备事件、国际化、以及子类扩展能力，为业务 Bean 创建与运行提供基础设施
  - 典型动作：
    - initMessageSource（国际化）
    - initApplicationEventMulticaster（事件广播器）
    - onRefresh（留给子类扩展，如 WebApplicationContext 初始化 web 相关组件）
    - registerListeners（注册 ApplicationListener）
- 7) 完成 BeanFactory 初始化（Instantiate Singletons）
  - 目的：实例化所有非懒加载单例业务 Bean，让容器进入“可服务”状态
  - 典型动作：finishBeanFactoryInitialization → preInstantiateSingletons
    - 对单个 Bean：实例化 → 提前暴露（三级缓存）→ 属性注入 → 初始化（@PostConstruct/afterPropertiesSet）→ AOP 代理 → 放入 singletonObjects
- 8) 完成刷新（Finish）
  - 目的：发布容器刷新完成事件、清理临时状态、宣告容器可用
  - 典型动作：finishRefresh
    - 发布 ContextRefreshedEvent
    - 初始化/启动 LifecycleProcessor（若有）
    - 清理资源缓存等

### 3) 失败处理（面试加分：refresh 失败会做什么）
- refresh 过程中如果发生异常
  - 目标：尽量销毁已创建的单例，释放资源，避免半初始化容器留在内存里
  - 典型动作：destroyBeans / cancelRefresh / resetCommonCaches（不同版本细节略有差异）
- 生产意义
  - 启动失败不应留下“部分启动成功”的隐患；但你仍要避免在 Bean 初始化里做不可逆副作用（比如启动期直接发外部请求/写外部系统）

### 4) 你在面试里怎么一句话串起来（口径）
- “refresh 先准备环境与 BeanFactory，再跑 BFPP 把图纸补全，再注册 BPP 让创建链可增强，然后批量实例化单例，最后发布刷新完成事件；核心目的是保证所有 Bean 都在同一套扩展点链路与基础设施下被创建并进入可服务状态。”

### 5) 小结（一句话复盘）
- refresh() 是容器启动总装线：Prepare → BeanFactory → BFPP → BPP → Infrastructure → Instantiate Singletons → Finish；每一步都在为下一步创造正确的前置条件，顺序错了就会出现定义不全、增强失效或部分 Bean 行为不一致的问题。
---

## 4. 循环依赖 + AOP 代理场景下，为什么必须有三级缓存（singletonFactories）而不是只靠二级？
### 1) 结论（标准答案）
- 在“循环依赖 + AOP 代理”场景下，必须引入三级缓存 `singletonFactories` 的根因是：Spring 需要在“是否真的发生循环依赖”这一刻，按需生成一个“早期引用（early reference）”，而这个早期引用在 AOP 场景下可能必须是“早期代理（early proxy）”。二级缓存只能存“已经生成好的对象引用”，无法同时满足“延迟生成 + 生成时可插入 AOP 的 early 代理逻辑 + 保证只生成一次并与最终引用一致”这三个目标。
- 三级缓存提供的是 ObjectFactory（生成逻辑），让 Spring 能在真正需要提前暴露时调用 `getObject()`，并在其中走 `getEarlyBeanReference`（AOP 早期代理钩子），从而尽量保证：被注入到别处的引用和最终放入一级缓存的引用形态一致（通常是同一个代理语义）。

### 2) 只靠二级缓存会遇到什么硬问题（从能力缺口讲清楚）
- 缺口 1：无法“按需”提前暴露（会被迫对所有 Bean 无差别提前暴露）
  - 如果没有三级工厂，想支持循环依赖只能在实例化后立刻把对象引用塞进二级缓存
  - 结果：绝大多数没有循环依赖的 Bean 也会提前暴露，增加复杂度与风险（例如半初始化对象被意外拿到）
- 缺口 2：无法在“生成早期引用时”插入 AOP 逻辑
  - AOP 代理通常在初始化后（postProcessAfterInitialization）生成
  - 但循环依赖需要在属性填充前暴露引用
  - 三级缓存的 factory.getObject() 可以在暴露早期引用时调用 `getEarlyBeanReference`，提前返回代理/包装引用
  - 二级缓存只有“成品引用槽位”，没有“生成时机与生成路径控制”，很难把 AOP 的 early hook 串进去
- 缺口 3：引用一致性与并发原子性难保证
  - 循环依赖时必须保证“早期引用只生成一次”，并且从三级到二级到一级的迁移是原子的
  - 三级缓存配合 getSingleton 的 double-check 与单锁，能做到：
    - 同一时刻只有一个线程执行 factory.getObject()
    - 生成后立刻放入二级并移除三级，避免重复生成不同引用
  - 只用二级缓存更容易在并发窗口中生成多份 early 引用或出现状态错乱

### 3) 三级缓存怎么解决（把状态机讲出来）
- 三层语义（面试一句话）
  - 一级：singletonObjects = 最终成品（fully initialized）
  - 二级：earlySingletonObjects = 早期引用（已经生成好的 early reference）
  - 三级：singletonFactories = 早期引用工厂（延迟生成 early reference 的逻辑）
- 关键迁移（只在发生循环依赖时触发）
  - 1) Bean A 实例化完成后，Spring 不立刻生成 early 引用，而是先放入三级：
    - singletonFactories.put(A, factory)
  - 2) 当创建 B 需要注入 A 时，getSingleton(A, allowEarlyReference=true) 触发：
    - 查一级没有 → 查二级没有 → 查三级有
    - 调用 factory.getObject() 生成 early reference
    - 放入二级 earlySingletonObjects，并移除三级 singletonFactories（保证只生成一次）
  - 3) A 完成属性填充与初始化后，最终成品放入一级，并清理二级/三级残留

### 4) 循环依赖 + AOP 代理下“早期代理一致性”问题（为什么三级是必要条件）
- 典型问题：B 注入到的 A 应该是“代理”还是“原对象”？
  - 若 B 注入的是原对象，而最终 A 变成代理
    - B 调用 A 时绕过切面（事务/鉴权/审计不生效）
    - 系统里出现两份引用：raw A 与 proxy A，行为不一致
- 三级缓存的关键价值
  - factory.getObject() 阶段可以调用 `getEarlyBeanReference`
    - AOP 的 AutoProxyCreator 有机会在“提前暴露阶段”就返回一个 early proxy
  - 这样 B 注入到的就是 proxy 语义（尽量与最终一致）
- 为什么二级做不到
  - 二级只存“已经存在的 early reference”
  - 但你需要的是“在需要时才创建 early reference，并且创建时走 AOP early hook”
  - 没有三级工厂，就没有“延迟且可插拔的创建路径”

### 5) 为什么不能简单地“提前把代理放进二级”（面试官可能追问）
- 你无法提前确定是否需要代理、也无法提前确定是否会发生循环依赖
  - 代理创建可能依赖于 BPP 链、Advisor 集合、BeanFactory 状态等
  - 对所有 Bean 都提前创建代理会显著增加启动成本与复杂度
- 代理创建时机需要可控
  - 三级缓存把“创建 early reference”延迟到真正有人请求它的时刻
  - 既避免无意义提前代理，也确保循环依赖时能生成一致引用

### 6) 生产级注意事项（加分：承认边界与风险）
- 三级缓存主要解决的是“单例 + setter/字段注入”的循环依赖
  - 构造器循环依赖通常仍然不行（没有实例化后的提前暴露窗口）
- 即便有三级缓存，AOP 早期代理也不一定在所有场景完全一致
  - 某些复杂依赖链、不同代理类型、或自调用绕过代理，仍可能出现“引用不一致”
- 工程建议：循环依赖能跑不是好设计
  - 更推荐拆分职责、引入中介者/事件驱动，减少双向依赖

### 7) 小结（一句话复盘）
- 三级缓存的本质价值是“延迟生成早期引用的能力”，让 Spring 在循环依赖发生时才调用 ObjectFactory 生成 early reference，并在生成时插入 AOP 的 `getEarlyBeanReference` 以尽量保持代理一致性；二级缓存只能存引用，无法同时满足按需、可插拔生成与并发一致迁移，因此在循环依赖 + AOP 场景下必须有三级缓存。
---

## 5. 你如何定位启动慢（Bean 太多、条件装配、类路径扫描、代理过多）？有哪些可观测手段？
### 1) 结论（标准答案）
- 启动慢的本质是：refresh() 某些阶段耗时异常（扫描/解析配置类、条件装配评估、实例化单例、初始化逻辑、代理创建、外部依赖连接等）。定位要把启动拆成“阶段耗时 + Top Bean 耗时 + 外部依赖耗时”，用可观测手段把问题从“感觉慢”变成“哪一步慢、谁最慢、为什么慢”。
- 常用抓手：Boot 启动阶段日志（Startup/StartupStep）、条件报告（conditions）、Bean 创建日志（debug）、火焰图/Java Flight Recorder（JFR）、以及运行时指标（CPU/GC/类加载/线程）。结论导向：先找最大头，再做削减（减少扫描/减少 Bean/减少代理/延迟初始化/移出事务与初始化的外部调用）。

### 2) 启动慢的高频根因地图（面试要能分类）
- Bean 太多
  - 扫描到过多组件、引入太多 starter、自动配置创建了大量 Bean
- 条件装配耗时
  - OnClass/OnBean/OnProperty 评估过多、反复做类型推断、过多候选 Bean 导致判断慢
- 类路径扫描慢
  - 扫描包范围过大、依赖 jar 多且 classpath 巨大、包含大体量反射扫描
- 代理过多
  - AOP/事务/缓存等切面多，AutoProxyCreator 为大量 Bean 生成代理；链路长导致初始化慢
- Bean 初始化做了重活
  - @PostConstruct/afterPropertiesSet 里做远程调用、加载大文件、全表扫描、预热缓存、创建大量线程/连接
- 外部依赖慢
  - DB/MQ/Redis/注册中心连接与握手耗时、DNS 慢、网络抖动

### 3) 定位方法论（生产可落地的排障步骤）
- Step 1：把启动拆成“阶段耗时”
  - 看 refresh() 的关键阶段谁慢：扫描/解析、BFPP、BPP 注册、单例实例化、事件广播等
- Step 2：拿到“Top 慢 Bean”
  - 找出创建/初始化最慢的 Bean（通常是外部连接、代理生成、复杂初始化）
- Step 3：确认慢点类别并对症下药
  - 扫描慢 → 缩小扫描范围/减少依赖/优化 classpath
  - 代理慢 → 减少切面、避免对全量 Bean 织入、优化 pointcut
  - 初始化慢 → 延迟/异步/afterReady、移出事务、加超时与熔断
  - 条件评估慢 → 简化条件、减少 OnBean 的复杂类型推断、减少自动配置数量

### 4) 可观测手段清单（你要能说出“用什么看见”）
- 4.1 Boot 启动阶段观测（首选）
  - 启动日志分段（开启更细日志）
    - 打印 active profiles、配置源、关键自动配置报告
  - Startup 指标/步骤（Boot 的启动步骤统计能力）
    - 能看到启动阶段与部分组件耗时（不同版本能力略有差异）
- 4.2 条件装配观测（定位“为什么加载了这么多”）
  - /actuator/conditions（如果启用）
    - 查看哪些自动配置生效/未生效，未生效原因（OnClass/OnProperty 等）
  - Auto-configuration report（排查期开启）
    - 直接看每个自动配置的匹配与否
- 4.3 Bean 创建与初始化观测（定位 Top 慢 Bean）
  - DEBUG 日志（排查期）
    - org.springframework.beans、org.springframework.context、org.springframework.transaction 等
    - 能看到 Bean 创建顺序、依赖关系、是否被代理
  - BeanFactory/BeanPostProcessor 相关日志
    - 看哪些 BPP 很慢（尤其是 AutoProxyCreator）
- 4.4 性能剖析（最硬核也最可靠）
  - Java Flight Recorder (JFR)
    - 看 CPU、锁竞争、类加载、方法热点；适合定位“扫描/反射/代理生成”类问题
  - Async-profiler/火焰图（如在预发环境）
    - 定位启动期间 CPU 热点、对象分配热点（代理/反射/JSON/日志）
- 4.5 JVM 与系统指标（定位资源瓶颈）
  - CPU 利用率、load、线程数
  - GC 次数与停顿（Young/Full）
  - 类加载数量与耗时（classpath 过大常见）
  - 连接池初始化耗时（DB/MQ/Redis）

### 5) 针对四类典型问题的“对症策略”（面试加分：能落地）
- 5.1 Bean 太多
  - 精简 starter 依赖（避免引入整套不需要的能力）
  - 用 conditions 把不需要的自动配置关掉（优先配置开关，不优先 exclude）
  - 按需启用（enabled=false 默认关闭非核心能力）
- 5.2 条件装配/自动配置评估慢
  - 减少复杂 OnBean 条件（尤其是扫描大量候选类型）
  - 合并/收敛配置类，避免大量细碎的 auto configuration
  - 用 /actuator/conditions 找到“最重的自动配置链”
- 5.3 类路径扫描慢
  - 缩小 @ComponentScan 基础包范围（避免扫根包/公共包）
  - 避免 classpath 过大（裁剪依赖、排除不必要的 jar）
  - 对反射扫描类库（如某些 mapper/serializer 扫描）控制扫描包
- 5.4 代理过多（AOP/事务/缓存）
  - 优化 pointcut：避免 execution(* com..*.*(..)) 这种全量匹配
  - 只对必要 Bean 织入（按注解/包名/类型精准匹配）
  - 评估 proxyBeanMethods=false（配置类互不调用时）降低 CGLIB 开销
  - 减少不必要的 @Transactional/@Async/@Cacheable 全域使用
- 5.5 初始化做重活/外部依赖慢（最常见）
  - 把重活从 @PostConstruct 移到 ApplicationReadyEvent 之后（或懒加载）
  - 对外部依赖连接加超时、重试、熔断；避免启动期无限等待
  - 缓存预热/全量加载改为分批/异步/按需加载

### 6) 生产级“验收与回归”建议
- 建立启动基线：启动总耗时、Top10 慢 Bean、类加载数量、GC 次数
- 每次升级依赖或新增 starter 做启动回归对比（避免启动时间温水煮青蛙）
- 对关键服务设置启动超时告警与自动化探针（readiness/liveness）并区分“启动未就绪”与“就绪后性能退化”

### 7) 小结（一句话复盘）
- 定位启动慢要把 refresh 拆阶段、找 Top 慢 Bean，并用 conditions/启动日志/Bean 创建日志/火焰图与 JVM 指标把原因定位到扫描、条件评估、代理生成或初始化重活；解决则通过缩小扫描、精简自动配置、优化切点、延迟重活与外部依赖超时治理形成可观测闭环。
---
