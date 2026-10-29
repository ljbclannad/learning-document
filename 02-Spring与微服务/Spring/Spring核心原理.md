# Spring核心原理

> 本文统一维护原《Spring》《Spring深度解析》中的核心机制，以及“Spring 解决的工程问题”“Bean 依赖关系表示与解析”。按工程问题、运行时模型、调用时序、失败边界与实验展开，不再按基础和进阶重复维护。
>
> 基线：JDK 17、Spring Framework 6.2.x；源码与实验固定到 **6.2.0**，配套 Boot **3.4.0**。这是可复现学习基线，不代表当前最新版或生产升级建议。Spring 5/Boot 2、Framework 7/Boot 4 需另查对应版本；命令式 JDBC 事务与响应式事务分开讨论。

## 目录

- [[#1. 从工程问题建立 Spring 模型]]
- [[#2. Bean 定义、容器与依赖关系]]
- [[#3. 从注册定义到 refresh]]
- [[#4. 一次 Bean 创建的生命周期]]
- [[#5. DI、构造器与候选选择]]
- [[#6. Scope、Lazy 与配置类方法调用]]
- [[#7. 循环依赖与早期引用的一致性]]
- [[#8. FactoryBean 与第三方对象集成]]
- [[#9. AOP：对象创建与方法调用两条链]]
- [[#10. 事务的资源模型与提交时序]]
- [[#11. 传播、回滚与自调用的真实边界]]
- [[#12. 事件、Outbox 与提交后副作用]]
- [[#13. Async、调度与上下文]]
- [[#14. 项目推演：待确认任务与策略组件]]
- [[#15. 排障、实验与源码入口]]

## 1. 从工程问题建立 Spring 模型

医生助手需要工具注册、风险判定、待确认任务保存、审批与执行。如果每个业务类都自己创建仓储、HTTP 客户端和执行器，会出现实现难替换、连接和线程无人统一关闭、事务规则散落等问题。

Spring 将对象组装和生命周期交给容器，把调用增强放到代理边界，把事务等基础设施操作放到统一接口之后。业务仍负责权限、不变量、幂等和失败语义；框架无法凭注解推断这些规则。

| 工程问题 | 核心抽象 | 收益与代价 |
| --- | --- | --- |
| 依赖实现散落在构造代码中 | IoC、DI、BeanDefinition | 组装集中、替换方便；需理解候选和生命周期 |
| 初始化与清理顺序混乱 | ApplicationContext、生命周期回调 | 建立统一时序；提前访问会破坏处理链 |
| 每个服务手写事务、审计 | Advisor、Interceptor、事务管理器 | 横切逻辑集中；调用必须跨越有效边界 |
| 数据访问 API 各不相同 | 模板、策略、资源绑定 | 调用方式一致；底层隔离和资源语义仍有差异 |
| 项目重复配置基础设施 | Boot 自动配置与 Starter | 默认装配可复用；需要条件、覆盖与版本治理 |

DI 也可以手工完成：`new Service(repository)` 已是显式注入。容器的额外价值是规模化管理对象图、扩展点和销毁，不是禁止业务代码使用 `new`。普通 DTO、值对象无需全部注册为 Bean。

两条学习主线：

```text
启动：定义 → 配置解析 → 定义扩展 → 实例扩展就绪 → 创建对象图 → 完成刷新
运行：进入代理 → 增强链 → 目标方法 → 提交/回滚与事件 → 资源清理
```

案例依据是 [[07-项目复盘与方案/智能体重管理/医生助手Agent/医生助手Agent开发方案-代码实现|医生助手方案]] 与 [[07-项目复盘与方案/通用系统方案/RabbitMQ与Outbox可靠消息方案|Outbox 方案]]。本文用于审视方案和构造实验，不把文档中的设计描述成已经验证的生产实现。

## 2. Bean 定义、容器与依赖关系

### 2.1 四个对象不要混为一谈

- **Java Class**：类型定义，可以产生多个实例。
- **BeanDefinition**：某个命名 Bean 的创建描述，包含类型、scope、构造参数、工厂方法、懒加载、限定信息等。
- **Bean 实例**：根据定义创建的实际对象；对外暴露的可能是代理。
- **ApplicationContext**：组织容器刷新、环境、资源、事件和生命周期；内部 BeanFactory 负责定义管理、依赖解析与对象创建。

同一个类可以注册多个 BeanDefinition，所以 Spring singleton 是**每容器、每个 Bean 定义的共享实例语义**，不是“同类在 JVM 中永远只有一个对象”。父子容器可有同名 Bean，子容器能访问父容器，反向不成立；本地同名定义可以遮蔽父容器候选。

`BeanFactory` 并不等于“永远懒加载的容器”。是否批量预实例化取决于使用方式；ApplicationContext 的刷新流程通常会预实例化非懒加载单例。原型 Bean、懒 Bean、FactoryBean 产品需分别看待。

### 2.2 定义表、依赖索引、实例缓存各司其职

| 结构 | 回答什么问题 | 示例 |
| --- | --- | --- |
| `beanDefinitionMap` | 应该如何创建这个命名 Bean | `approvalService → BeanDefinition` |
| `dependenciesForBeanMap` | 这个 Bean 依赖谁 | `approvalService → [taskRepository]` |
| `dependentBeanMap` | 谁依赖这个 Bean | `taskRepository → [approvalService]` |
| `containedBeanMap` | 谁包含内部 Bean | XML 内部 Bean 等包含关系 |
| `singletonObjects` | 已注册的单例对象是谁 | 最终暴露的单例引用 |
| `earlySingletonObjects` | 已生成的早期引用是谁 | 循环创建期间的引用 |
| `singletonFactories` | 如何按需取得早期引用 | 生成早期引用的 ObjectFactory |

运行时索引服务于依赖查询、销毁顺序等，不是业务调用关系的完整追踪。普通方法调用、手工创建的对象、某些延迟获取路径不一定记录为期望的边；未实例化 Bean 的依赖也可能尚未解析。不能因为索引为空就断言对象没有依赖。

```java
// 片段：context 是已刷新的 ConfigurableApplicationContext。
import java.util.Arrays;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;

ConfigurableListableBeanFactory factory = context.getBeanFactory();
System.out.println(Arrays.toString(factory.getDependenciesForBean("approvalService")));
System.out.println(Arrays.toString(factory.getDependentBeans("taskRepository")));
```

### 2.3 为什么不是一次性构建完整图

配置类、扫描、Import 与定义后处理器会继续注册定义；注入候选还依赖类型、泛型、限定符和当时可见的容器状态。构造参数在实例创建前解析，字段和 Setter 在实例化后解析，Provider 则可延后取得目标。

因此源码不能简化为“所有对象先 new 完，再统一连线”。它更像递归创建与分阶段解析：创建 A 需要 B，就转入 B 的获取流程，再返回 A。

## 3. 从注册定义到 refresh

### 3.1 注册和实例化是两个阶段

XML 由 reader 读取，组件扫描发现候选，`@Bean` 描述工厂方法，`@Import` 可导入配置类、ImportSelector 或 Registrar。入口不同，最终大多形成定义注册；`registerSingleton` 直接交付现成实例属于另一条路径，不会替你补做完整的创建与初始化过程。

对于 `AnnotationConfigApplicationContext`，注册初始配置类不等于其中的全部 `@Bean` 已被展开。`ConfigurationClassPostProcessor` 在刷新中的定义扩展阶段处理配置、扫描和导入。不能把所有注解解析都放到 `obtainFreshBeanFactory()` 中。

### 3.2 refresh 的职责顺序

以下是逻辑图，不是可复制执行的源码：

```text
prepareRefresh
  → obtainFreshBeanFactory / prepareBeanFactory
  → postProcessBeanFactory
  → invokeBeanFactoryPostProcessors
      → 配置类解析、更多定义注册、定义调整
  → registerBeanPostProcessors
      → 实例处理器就绪
  → initMessageSource / initApplicationEventMulticaster
  → onRefresh / registerListeners
  → finishBeanFactoryInitialization
      → 转换器等准备、非懒加载单例预实例化
  → finishRefresh
      → 生命周期启动、ContextRefreshedEvent
```

XML、通用注解容器、Servlet Web 容器会在相应钩子中做不同工作。Boot 的服务器启动和应用就绪另见 [[02-Spring与微服务/Spring/SpringBoot|SpringBoot]]，不能用一条抽象 refresh 图证明“端口直到 Ready 才监听”。

刷新失败会尝试销毁已创建单例并取消刷新，但外部 HTTP 请求、已经提交的数据不会因此自动回滚。不要在构造器或初始化钩子里启动无法撤销的业务流程。

### 3.3 扩展点的时机比接口名字更重要

| 扩展点 | 主要对象 | 适合做什么 | 常见错误 |
| --- | --- | --- | --- |
| BeanDefinitionRegistryPostProcessor | 定义注册表 | 扫描并注册新定义 | 为注册定义提前调用业务服务 |
| BeanFactoryPostProcessor | 定义和工厂配置 | 修改属性、校验装配 | `getBean` 导致业务对象过早创建 |
| BeanPostProcessor | 实例 | 初始化前后处理与包装 | 注册太晚，部分 Bean 漏增强 |
| InstantiationAware / SmartInstantiationAware BPP | 创建过程与类型预测 | 构造器候选、注入、早期引用 | 认为 BPP 只在 init 前后运行 |
| SmartInitializingSingleton | 单例预实例化结束阶段 | 检查已创建单例的整体关系 | 以为所有懒 Bean 也必然已创建 |
| Lifecycle / SmartLifecycle | 组件运行状态 | 有序启动、停止工作者 | 把启动停止和构造销毁当同一事件 |

基础设施自身需要先创建，因此“BFPP 执行前绝对没有任何 Bean 实例”不成立。基础设施直接依赖业务 Bean，会把业务 Bean 一起提前拉起；此时完整 BPP 链可能尚未就绪，出现 `not eligible for getting processed by all BeanPostProcessors` 提示。

定义 BFPP/BPP 的 `@Bean` 方法可使用 `static`，减少过早实例化配置类的需求，并给出明确返回类型。`@Order` 不统一控制所有扩展点：自动检测的 BPP 排序以 `PriorityOrdered` / `Ordered` 等相应契约为准；编程式注册还有自己的顺序规则。

## 4. 一次 Bean 创建的生命周期

常规 `doCreateBean` 路径可以这样追踪：

```text
类型/构造器选择 → 解析构造参数 → 实例化
  → 必要时登记早期引用工厂
  → populateBean：属性、字段、Setter 注入
  → initializeBean：部分 Aware、初始化前处理、初始化回调、初始化后处理
  → 协调早期引用与最终引用 → 注册销毁处理 → 发布可用单例
```

`createBean` 还有实例化前短路等扩展路径，所以它不是每个 Bean 的绝对执行清单。

### 4.1 初始化回调的准确位置

`BeanNameAware`、`BeanClassLoaderAware`、`BeanFactoryAware` 由相应初始化路径直接处理；`ApplicationContextAware` 等由处理器提供。`@PostConstruct` 也是处理器在初始化前阶段触发，不是在所有 BPP-before 执行完以后额外独立调用一次。

常规多个初始化机制并存时，可观察到 `@PostConstruct → afterPropertiesSet → 自定义 init-method`，但不能据此给所有 BPP 画统一固定顺序。初始化后处理器还可返回包装对象；调用方拿到的不一定是构造器创建的原对象。

初始化时通常还没拿到最终代理，在 `@PostConstruct` 中自调用 `@Transactional` 不能作为可靠的事务入口。必要的初始化数据操作可由外部就绪阶段服务调用明确的事务边界，或显式使用 TransactionTemplate，并评估重复启动的幂等性。

### 4.2 停止工作与销毁资源

先停止新任务接纳，限时完成或登记在途任务，再释放客户端和数据源。依赖关系会影响销毁次序，但不会替任意自行创建的线程定义停机协议。

prototype 初始化由容器处理，交付后通常不自动调用销毁回调；使用者负责资源释放。不要把“不追踪销毁”写成“不管理任何生命周期”。

## 5. DI、构造器与候选选择

### 5.1 先满足对象不变量

必需依赖优先构造器注入，配合 `final` 引用表达构造后不替换。`final Repository` 不会让 Repository 的内部状态不可变；线程安全仍要看依赖与共享状态。

单个构造器通常无需 `@Autowired`。多个构造器时，应明确候选；多个 `required=false` 候选会考虑依赖可满足性和参数数量，不能推广为“永远选择参数最多的构造器”。`@Bean` 方法中的 `new Service(repo)` 已明确构造方式，容器解析的是工厂方法参数。

字段注入可以通过反射测试，也不自动违反设计原则；它的代价是必需依赖不在构造 API 中。Setter 是否可选由配置决定，不是所有 Setter 注入都天然可缺失。

### 5.2 注入点进入依赖解析器

```text
构造参数 → ConstructorResolver
字段/注入方法 → AutowiredAnnotationBeanPostProcessor
  → DependencyDescriptor
  → resolveDependency / doResolveDependency
  → 类型与泛型匹配、候选过滤、单值选择或多值聚合
  → getBean 候选 → 注入与依赖登记
```

Qualifier 是在类型候选中进一步限定，可以用业务标签，也可使用名称匹配；它不是绕过类型系统任意按名字取对象。Primary 通常参与单值消歧；`List<T>` / `Map<String,T>` 的聚合不会因一个 Primary 就只留下它。`@Order` 可影响列表注入排序，不是业务启动先后的通用保证。

Spring 6.2 还引入了 `@Fallback` 等候选能力；参数名捷径也有版本和编译元数据前提。团队应用应显式表达关键多实现选择，不背一条跨版本不变的“Qualifier → Primary → 名字 → Priority”算法。源码入口与[限定符文档](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config/autowired-qualifiers.html)用于确认当前版本。

`@Resource` 默认名称推断与按类型回退有配置前提；显式给出 `name` 后，缺少该名称不能期待自动寻找任意同类型 Bean。Spring 6 的常见注解包为 `jakarta.annotation`；`javax.sql.DataSource` 属于 Java SE，不随之改成 `jakarta.sql`。

### 5.3 可选不等于忽略歧义

| 形式 | 缺少候选 | 多个未消歧候选 | 取得目标的时机 |
| --- | --- | --- | --- |
| 普通必需注入 | 失败 | 失败 | 创建依赖方时 |
| Optional | 空值语义 | 通常仍失败 | 注入解析时 |
| ObjectProvider.getObject | 失败 | 失败 | 调用时 |
| ObjectProvider.getIfAvailable | 可返回 null | 通常仍失败 | 调用时 |
| ObjectProvider.getIfUnique | 可返回 null | 无唯一可选项时返回 null | 调用时 |
| ObjectProvider.orderedStream | 可为空 | 返回候选流 | 消费时，按顺序规则 |

Provider 可以推迟创建，但在构造器中立即调用 `getObject()` 又恢复了强依赖。策略集合注入应校验业务 key 唯一，不能让同一 `toolName` 的多个实现通过 Map 最后写入静默覆盖。

## 6. Scope、Lazy 与配置类方法调用

### 6.1 Scope 决定对象复用边界

singleton 在容器内按定义复用；prototype 每次向容器解析可得到新实例；request、session、application、websocket 依赖相应 Web 环境。session 可能被多个并行请求使用，不能等同于线程封闭。

单例构造时直接注入 prototype，只解析一次，之后仍持有那一个对象。每次操作需要独立缓冲时可用 `ObjectProvider` 获取，并负责释放资源。请求 scope 注入长期存活 Bean 时，可用作用域代理，但后台线程没有有效请求上下文时代理仍不能凭空取得目标。[Scope 契约](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html)

### 6.2 Lazy 的两种语义

定义上的 `@Lazy` 抑制主动预实例化，但被非懒单例直接依赖时仍可能在启动时创建。注入点上的 `@Lazy` 通常提供延迟解析代理；它只能推迟取得目标，无法保证第一次使用时配置一定正确。

让首次患者请求承担客户端初始化、模型预热和连接创建，会把启动耗时转移成首次请求长尾。核心依赖是否应延迟，要结合 readiness 和首次访问验收。

### 6.3 full 与 lite 配置模式

默认 `@Configuration(proxyBeanMethods=true)` 会增强可拦截的 `@Bean` 方法间调用，使其遵循容器语义。`proxyBeanMethods=false` 或普通组件上的 `@Bean` 属于不做这类拦截的使用方式：在 Java 代码中直接调用另一个工厂方法，会按普通方法执行，可能再次 `new` 对象。

优先用方法参数表达依赖：

```java
// 片段：Repository 和 ApprovalService 是业务类型。
@Bean
ApprovalService approvalService(Repository repository) {
    return new ApprovalService(repository);
}
```

配置类方法代理和业务 AOP 代理解决不同问题，不能因为都使用子类增强，就把配置类内部调用与业务 `this.xxx()` 当成同一规则。

## 7. 循环依赖与早期引用的一致性

### 7.1 能解的关键是实例化窗口

在允许循环引用的容器中，A、B 都是可参与早期暴露的单例，且通过属性注入互相依赖时，可能发生：

```text
实例化 A → 登记 A 的早期工厂
  → A 注入 B：实例化 B
      → B 注入 A：调用工厂，取得 A 的早期引用
      → B 完成
  → A 填入 B → A 初始化 → 发布最终引用
```

两边都要求构造器参数立即到位时，连 A 的实例都无法生成，缺少提前暴露窗口。Provider/Lazy 改变的是依赖取得时机；仅增加一个接口而保留 A↔B 的强依赖，不会自动拆环。

Spring Framework 的机制能力与 Boot 的策略不同：Boot 3.4 默认禁止循环引用，不能拿一个原生 AnnotationConfigApplicationContext 的成功实验推导 Boot 默认支持。实验分别显式启用和禁用，避免依赖默认值。

### 7.2 三个缓存的意义

一级供正常访问；三级保存生成早期引用的逻辑；发生早期请求后，二级缓存已经生成的引用，避免重复生成。很多无环 Bean 不经过二级缓存，不能把“三级→二级→一级”当作所有 Bean 必经步骤。

如果 A 最终需要 AOP 增强，而 B 已拿到 raw A，则 B 的调用可能绕过增强。自动代理创建器通过 `getEarlyBeanReference` 等钩子参与早期引用，并与初始化后包装协调，力求让注入引用和最终暴露对象一致。不支持早期协调的自定义包装器仍可能失败。

“三张 Map 是理论上唯一解法”不成立。需要的是按需生成、缓存、最终一致性和并发协调这些能力；换一种设计也可能实现。学习 Spring 应解释它为什么这样组织，而不是证明别的结构绝无可能。

### 7.3 旧源码的锁不能套在新版本上

原笔记的 `synchronized(singletonObjects)` 片段属于旧实现语境。固定的 [6.2.0 DefaultSingletonBeanRegistry](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-beans/src/main/java/org/springframework/beans/factory/support/DefaultSingletonBeanRegistry.java) 使用 `singletonLock` 等机制，并存在 tryLock 与创建线程的处理边界。

共同原理是：快路径读取后，进入受协调区域需重新确认当前状态，不能依据锁外的旧观察重复创建早期引用。具体锁、Map 类型与后台初始化行为应对照实际补丁版本。

工程上优先让审批编排器依赖执行器和仓储，避免执行器反向依赖审批编排器。允许循环引用是兼容策略，不是完成对象设计的证明；早期对象也不应在初始化未完成时开始业务执行。

## 8. FactoryBean 与第三方对象集成

`BeanFactory` 是容器接口；`FactoryBean<T>` 是一个生产 T 的 Bean。对名为 `mapper` 的 FactoryBean，`getBean("mapper")` 默认取得产品，`getBean("&mapper")` 取得工厂本身。

| 方法或结构 | 作用 | 边界 |
| --- | --- | --- |
| getObject | 返回产品 | 可缓存、可动态创建，由实现决定 |
| getObjectType | 暴露产品类型 | 提供准确类型有助于候选判断，不宜为判断类型做重型初始化 |
| isSingleton | 描述产品共享语义 | 不等于产品线程安全 |
| factoryBeanObjectCache | 管理可缓存产品 | 与普通 singletonObjects 不同 |

产品可能经过特定后处理，但**不自动享有普通 Bean 的整套生命周期**。尤其产品的 close/destroy 不会仅因由 FactoryBean 暴露而自动调用；工厂应按需要实现销毁并委托释放产品，或明确资源由其他 Bean 拥有。[固定版本 FactoryBean 契约](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-beans/src/main/java/org/springframework/beans/factory/FactoryBean.java)

MyBatis 的 MapperFactoryBean 生产 Mapper 代理，SqlSessionFactoryBean 生产 SqlSessionFactory。产品类型暴露、扫描注册、执行 SQL 与事务资源绑定是不同阶段，细节集中在 [[03-数据存储与缓存/数据库/Mybatis|MyBatis]]。

## 9. AOP：对象创建与方法调用两条链

### 9.1 创建阶段决定哪些调用有机会被增强

自动代理创建器作为容器处理器，查找适用 Advisor、判断目标方法与类型，再返回代理。应用开发通常由容器完成，也可以用 ProxyFactory 编程式创建代理，不应把 Spring AOP 的 API 能力限定成“只能扫描注解”。

Advisor 组织 Advice 与适用范围；Pointcut 描述匹配；Advice 最终被适配为拦截器。JDK 代理实现接口，类代理通过继承覆盖方法。类代理不能继承 final 类或覆盖 final/private 方法；JDK 接口代理不受目标实现类 final 的同样限制，但只暴露接口调用能力。

原生代理选择与 Boot AOP 自动配置默认值不同。Boot 3.4 在相应自动配置启用时默认偏向类代理；“有接口就一定使用 JDK 代理”不是跨配置规则。代理选择依据见[代理机制](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)。

### 9.2 运行阶段是嵌套调用

```text
客户端 → 代理 → 拦截器 A.before
                → 拦截器 B.before
                  → 目标方法
                ← B.after / B.catch / B.finally
              ← A.after / A.catch / A.finally
```

`ReflectiveMethodInvocation.proceed()` 推进链。外层 Around 可以不调用 proceed，因此内层通知不一定执行；“After 在任何情况下都一定执行”缺少已经进入对应拦截器的前提。相同 order 的顺序不要作为业务契约。

吞异常的位置会改变事务观察结果：如果兜底拦截器在事务拦截器内部把异常转为正常值，事务可能提交；如果事务已观察到异常并回滚，外层再兜底也无法撤销这个决定。审计需明确记录方法返回、事务提交还是消息发送成功，三者不是同一时点。

### 9.3 自调用与 AspectJ

普通业务 `this.inner()` 从目标对象内部出发，不再穿过外部代理，因此 inner 的事务、异步或缓存增强可能不生效。优先拆出职责明确的 Bean 或使用显式模板；自注入、AopContext 需要额外配置和调用上下文，不作为默认修复。

AspectJ 编译期/加载期织入可覆盖更广连接点，也有额外构建、类加载和排障成本。仅使用 `@Aspect` 注解并不意味着启用了 AspectJ 字节码织入，Spring 也可解析这些注解建立代理。

## 10. 事务的资源模型与提交时序

### 10.1 注解背后是资源管理

本文默认 `PlatformTransactionManager` 管理命令式 JDBC 事务。TransactionInterceptor 读取事务属性，通过 TransactionAspectSupport 调用管理器；DataSourceTransactionManager 操作连接。响应式事务使用 Reactor Context 和 ReactiveTransactionManager，不能机械套用线程绑定模型。

```text
代理调用 → 事务属性与管理器选择
  → getTransaction：新建、加入、挂起或保存点
  → 目标方法 → JDBC/MyBatis 复用绑定资源
  → commit/rollback 决策
  → 同步回调 → 清理、解绑、释放资源、恢复外层
```

同线程也不自动保证同事务：需要相同资源与正确的 Spring 获取连接方式。绕过 Spring 直接取独立连接、选择不同 DataSource/管理器，仍可能产生独立提交。JdbcTemplate 等使用 DataSourceUtils；MyBatis 应核实 SqlSessionTemplate 与数据源配置。

### 10.2 新建本地 JDBC 事务的典型完成顺序

```text
业务正常返回
  → prepareForCommit
  → beforeCommit
  → beforeCompletion
  → doCommit（物理提交）
  → afterCommit
  → afterCompletion
  → cleanupAfterCompletion（解绑、连接恢复与释放等）
```

这条正常路径可在 [6.2.0 AbstractPlatformTransactionManager](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-tx/src/main/java/org/springframework/transaction/support/AbstractPlatformTransactionManager.java) 核对。异常、加入外部事务和保存点会进入不同分支。

原文“先清理连接再触发所有完成回调”的顺序不准确。回调中资源可能仍可见，但事务已经提交，不能据此继续向旧事务写入并期待再次提交。确需回调后落库应设计独立事务，同时承认它与原业务不再原子。

直接 `TransactionSynchronization.afterCommit()` 抛异常可以传给调用方，但数据库已提交，不能当作业务未发生；事务事件的 AFTER_COMMIT 监听位于完成回调协议中，异常传播策略也不能与直接 afterCommit 简单混为一谈。

### 10.3 事务属性不是业务超时和隔离的万能开关

`readOnly` 通常是优化提示，是否强制禁止写入取决于管理器、配置和数据库。`timeout` 需要具体资源/API 配合，不会给任意 HTTP 请求自动加取消计时器。

加入既有事务时，内层声明的隔离等属性通常不会重建物理事务；可通过管理器的参与事务校验策略发现部分不一致。MySQL MVCC、锁范围、索引和幻读属于 [[03-数据存储与缓存/数据库/MySQL|MySQL]] 的维护范围。

## 11. 传播、回滚与自调用的真实边界

### 11.1 逻辑事务与物理事务

| 传播 | 外层有事务时 | 外层没有事务时 | 主要代价或约束 |
| --- | --- | --- | --- |
| REQUIRED | 加入现有物理事务 | 新建 | 内层可影响共享 rollback-only |
| REQUIRES_NEW | 挂起外层、独立新建 | 新建 | 额外连接；挂起不释放外层数据库锁 |
| NESTED | 支持时建立保存点 | 新建 | 管理器/驱动支持；最终仍受外层提交决定 |
| SUPPORTS | 参与 | 非事务执行 | 无事务与同步范围需区分 |
| NOT_SUPPORTED | 挂起、非事务执行 | 非事务执行 | 不提供整体原子性 |
| MANDATORY | 参与 | 报错 | 强制调用方已有事务 |
| NEVER | 报错 | 非事务执行 | 禁止在事务中调用 |

内层 REQUIRED 经代理抛出需回滚异常，可能把共享事务标为 rollback-only。外层 catch 后正常返回并不保证成功提交，可能出现 UnexpectedRollbackException。NESTED 回滚到保存点后可以继续，但外层最终回滚会撤销包括内层成功操作在内的整体事务。

REQUIRES_NEW 独立提交不等于内外完全无影响：异常可继续传播，连接池可能耗尽，内层可能等待外层持有的锁。外层一边等待内层、一边不释放内层需要的资源，可能直到超时才能解除。不能用一条固定“连接池翻倍”公式覆盖所有嵌套与负载。[传播契约](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html)

### 11.2 自调用有两种不同结果

```text
无事务 outer → this.inner(@Transactional)
  → inner 注解未被拦截：不能凭它创建事务

经代理进入 outer(@Transactional) → this.inner(@Transactional(REQUIRES_NEW))
  → outer 的事务仍在
  → inner 的 REQUIRES_NEW 未被拦截：不会因此产生独立新事务
```

所以原文两个方法都带事务且内层抛运行时异常的示例，不能直接证明“自调用导致数据库不回滚”。外层事务仍可能正常回滚。实验同时验证无外层与有外层两条路径。

### 11.3 回滚规则与代理可达性

默认规则对 RuntimeException、Error 回滚，受检异常通常不回滚；可按异常类型设置 rollbackFor/noRollbackFor。Spring 6.2 还支持全局默认回滚策略配置，不能忽略项目配置只背默认规则。字符串匹配型规则可能误匹配同名片段，关键业务优先使用类型。

Spring 6 类代理的事务可支持 protected/package-private 方法，JDK 代理要求接口可调用方法；private、类代理的 final、自调用、未经过事务增强的对象都需分别检查。业务边界使用 public 方法更容易保持跨配置可预期。

`AopUtils.isAopProxy(bean)` 为 true 仅证明它是代理，不能证明事务 Advisor 匹配了当前方法，也不能证明使用了预期的数据源。验证应检查实际调用路径、事务状态、连接与数据库结果。

## 12. 事件、Outbox 与提交后副作用

### 12.1 同步事件和事务事件

默认简单事件广播通常在发布线程执行；可配置其他执行方式，`publishEvent` 本身不承诺可靠持久化。普通 `@EventListener` 在事务内立即运行时，外部通知可能先于数据库提交发生。

`@TransactionalEventListener` 将处理绑定到阶段，默认 AFTER_COMMIT；没有合适事务时默认不执行，`fallbackExecution=true` 改变这个语义。BEFORE_COMMIT 也不保证最终提交一定成功。[事务事件说明](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)

### 12.2 提交后不等于一定送达

```text
数据库提交成功 → 进程崩溃 → 内存中的提交后任务没有执行
数据库提交成功 → 提交异步任务 → 执行器拒绝
数据库提交成功 → 远端收到通知 → 本地未收到确认 → 重试可能重复
```

仅把发 MQ 移到 AFTER_COMMIT，消除了“回滚后仍已发消息”的部分窗口，却没有保证可靠交付。需要可靠恢复时，业务行与 outbox 行必须在**同一原事务**写入。先提交业务，再在 AFTER_COMMIT 新事务写 outbox，会重新引入两次提交之间的丢失窗口。

Outbox 投递允许重复，消费者幂等记录与本地业务变更应在同一事务内完成；“先单独写去重标记、再执行实际业务”在崩溃后可能永久漏处理。外部副作用还需资源端幂等键或核实补偿。

### 12.3 结合现有方案审视调用边界

知识库 Outbox 方案包含 `enqueue()` 内直接调用同类 `@Async triggerProcessAsync()` 的写法。按默认代理模型，这次内部调用不会自动切换线程；即使拆成真正异步，也要处理原事务未提交时的读取竞态。

可采用“事务内持久化 → 提交后唤醒投递器 → 定时扫描兜底”的结构。唤醒只是降低延迟，可靠性来自持久记录与恢复协议。这是对方案代码的机制分析，不是声称真实生产存在该事故；本次不改项目方案实现。

## 13. Async、调度与上下文

`@EnableAsync` 注册异步处理基础设施；Boot 提供执行器自动配置不等于自动开启所有 `@Async` 注解。`@Async("analysisExecutor")` 应明确执行域，避免隐式共享池。

```text
请求线程：权限校验 → 保存任务并提交事务 → 提交/触发分析
工作线程：安装必要上下文 → 调用独立事务服务 → 执行/记录结果 → 恢复上下文
```

工作线程可以通过另一个 Bean 的事务代理建立自己的事务；无需为了“换线程”一律使用 REQUIRES_NEW，没有既有事务时 REQUIRED 就会新建。把异步入口与事务服务分开，通常比依赖同一方法上多个 Advisor 的组合顺序更易测试。

void 异步方法的执行异常交给 AsyncUncaughtExceptionHandler；Future/CompletableFuture 结果要显式处理。提交时拒绝可能直接反馈给调用方，CallerRuns 又可能让工作回到提交线程，所以“加 Async 后立即返回且一定新线程”不成立。

TaskDecorator 可捕获 TraceId 等必要上下文，在运行时安装，并在 finally 恢复原值，兼容嵌套与调用线程执行。不要复制事务连接；上下文传播也不替代资源授权。代理调用、连接线程归属和业务结果必须分别验证。

`@Scheduled` 负责触发，并不提供集群单次执行保证。多实例任务认领、租约、幂等与有界执行应另外设计。线程池接纳、取消与资源释放原理集中于 [[01-Java基础与并发/并发编程/Java并发编程|Java并发编程]]，这里只维护 Spring 接入边界。

## 14. 项目推演：待确认任务与策略组件

### 14.1 装配图不应等同于业务状态机

可以让审批服务依赖 `TaskRepository`、`ToolRegistry`、`PermissionService`；ToolRegistry 收集工具实现并校验唯一 key。Bean 构建完成只表示组件可被调用，不表示某患者任务已获授权或允许执行。

将请求的 patientId、doctorId、taskId 放入单例字段，会让并发请求互相覆盖。它们应作为调用参数或明确作用域的数据；组件持有的共享缓存另行设计同步和容量。

### 14.2 确认操作的原子边界

```text
请求身份与资源授权
  → 短事务：条件认领 PENDING 任务 + 记录执行意图/outbox
  → 提交
  → 工作者调用外部工具
  → 另一个短事务：按认领令牌记录结果
```

单个 Java 事务不能回滚已经发送的外部医嘱或通知。远端超时可能是“结果未知”，不能等同执行失败后直接再次执行。外部调用使用稳定幂等键，任务状态区分运行、未知、可重试和完成，迟到工作者写回需校验版本。

权限 AOP、事务 AOP 与审计 AOP 的嵌套顺序要对应具体问题：权限失败是否应消耗连接，审计记录的是尝试还是已提交事实，失败审计是否允许独立提交。不存在对所有业务适用的一张固定切面排序表。

### 14.3 用故障时序检验设计

| 条件 | 应观察什么 | 验收方向 |
| --- | --- | --- |
| 同名工具注册两个实现 | 启动校验与候选列表 | 明确失败，不随机选择 |
| 审批重复提交 | 条件更新结果与幂等键 | 不重复认领/执行 |
| 原事务回滚 | 任务和 outbox 行 | 二者一起回滚 |
| 提交后工作池拒绝 | outbox backlog、最终状态 | 可恢复，不把拒绝伪装完成 |
| 服务重启 | 已持久化任务与认领租约 | 可恢复在途责任 |
| 内层 REQUIRED 失败被捕获 | 最终数据库结果 | 不返回虚假成功 |
| 事务回调执行慢 | 连接占用和响应耗时 | 不只看数据库锁释放时间 |

## 15. 排障、实验与源码入口

阅读设计模式时，将名称还原为责任分配：`refresh` 用模板流程约束阶段，事务管理器用策略接口隔离资源实现，AOP 用代理与拦截器链组合增强，事件广播将发布方和监听方解耦。模式本身不保证可靠性；例如进程内观察者没有持久恢复能力，模板回调也不会回滚已经发生的外部副作用。

`JdbcTemplate` 的价值在于统一连接获取、语句执行、异常转换和资源释放，让调用方提供变化部分。异常翻译形成统一访问异常层次，不代表可以忽略底层约束、死锁与重试条件。它与管理器通过资源获取协议协作，不能因为用了模板就认为每次调用都自动开启事务。


排障先写出实际调用者、目标引用、线程、事务管理器和数据源，再决定断点。不要先堆日志或打开循环引用开关。

| 现象 | 最小证据 | 对应机制 |
| --- | --- | --- |
| Bean 找不到/不唯一 | 定义来源、条件报告、候选类型 | 注册与 DI |
| 只有部分组件没有增强 | 创建时间、BPP 注册、实际代理 | 提前实例化 |
| 注解存在但事务不符合预期 | 代理路径、Advisor、事务状态、数据库行 | AOP 与事务 |
| 已提交但请求报失败 | 提交与回调时间线 | 提交后异常 |
| 异步读取不到新行 | 提交时刻与任务开始时刻 | 线程与事务边界 |

可运行实验见 [[02-Spring与微服务/Spring/示例/spring-mechanism-lab/README|Spring 机制实验]]：容器生命周期、依赖登记、scope、配置类调用、循环引用开关、FactoryBean 销毁，以及真实 H2 事务的自调用、传播、事件与资源清理。H2 结果不用于推导 MySQL 的锁和隔离实现。

源码阅读顺序固定到项目实际版本；本次入口使用 v6.2.0：

1. [AbstractApplicationContext](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-context/src/main/java/org/springframework/context/support/AbstractApplicationContext.java)：刷新和失败清理。
2. [AbstractAutowireCapableBeanFactory](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-beans/src/main/java/org/springframework/beans/factory/support/AbstractAutowireCapableBeanFactory.java)：创建、填充、初始化、早期引用。
3. [DefaultListableBeanFactory](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-beans/src/main/java/org/springframework/beans/factory/support/DefaultListableBeanFactory.java)：候选解析。
4. [AbstractAutoProxyCreator](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-aop/src/main/java/org/springframework/aop/framework/autoproxy/AbstractAutoProxyCreator.java)：代理的创建与早期协调。
5. [TransactionAspectSupport](https://github.com/spring-projects/spring-framework/blob/v6.2.0/spring-tx/src/main/java/org/springframework/transaction/interceptor/TransactionAspectSupport.java)：事务调用与异常决策。

学习导航见 [[02-Spring与微服务/Spring/Spring学习路线图|Spring学习路线图]]；自测见 [[02-Spring与微服务/Spring/Spring-Q|Spring 问答索引]]；启动装配见 [[02-Spring与微服务/Spring/SpringBoot|SpringBoot]]；HTTP 链路见 [[02-Spring与微服务/Spring/SpringMVC|SpringMVC]]；服务治理见 [[02-Spring与微服务/Spring/SpringCloud|SpringCloud]]。
