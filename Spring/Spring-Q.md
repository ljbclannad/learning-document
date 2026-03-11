# 1. Spring 容器的 refresh() 大致做了哪些事？为什么它是整个 Spring 启动的核心主线？

## Spring 容器的 `refresh()` 大致做了哪些事？为什么它是整个 Spring 吂动的核心主线？

先给结论：**`refresh()` 就是 Spring `ApplicationContext` 的总装配流水线。**
你可以把它理解成容器启动时的一条“总施工主线”：

**准备上下文 → 准备 BeanFactory → 执行工厂级扩展 → 注册 Bean 级扩展 → 初始化基础设施 → 实例化单例 → 完成收尾发布事件。**

为什么它是核心主线？因为 Spring 容器启动时几乎所有关键动作，最后都被收束到这一个方法里了。
包括：

* 读取并冻结 BeanDefinition
* 给容器级扩展点介入机会
* 给 Bean 级扩展点介入机会
* 初始化事件、多播器、国际化、生命周期处理器
* 提前实例化非懒加载单例
* 发布 `ContextRefreshedEvent`

所以面试里最稳的一句话是：

> `refresh()` 不是一个普通初始化方法，而是 Spring 容器从“只有定义”到“Bean 可用、事件可发、扩展点生效”的完整启动编排入口。

---

## 一、为什么 `refresh()` 是 Spring 启动的核心主线

### 1）它把“定义阶段”和“实例化阶段”串起来了

Spring 启动不是简单 `new` 一堆对象。它至少分两大阶段：

* **BeanDefinition 阶段**：先把“有什么 Bean、怎么创建、作用域、依赖关系、初始化方法”等定义准备好
* **Bean 实例化阶段**：再真正创建对象、属性注入、AOP 代理、初始化

`refresh()` 的价值就在于：
它把这两阶段用严格顺序串起来，并且在中间插入各种扩展点。

---

### 2）它决定了扩展点的时机边界

Spring 为什么扩展能力这么强？
本质上不是因为接口多，而是因为 **扩展点插入时机设计得非常精细**。

比如：

* `BeanFactoryPostProcessor` 处理的是 **BeanDefinition**
* `BeanPostProcessor` 处理的是 **Bean 实例**
* 事件广播器、消息源、生命周期处理器都在特定阶段初始化

这些都靠 `refresh()` 统一编排。
顺序一乱，很多能力就会失效，后面我会展开。

---

## 二、`refresh()` 大致做了哪些事

如果按 `AbstractApplicationContext#refresh()` 的主线来讲，可以拆成下面这些关键阶段。

---

## 三、第一阶段：刷新前准备 `prepareRefresh()`

这一阶段主要做容器级的基础准备。

常见动作包括：

* 记录启动时间
* 设置容器状态为 active
* 初始化一些上下文属性源校验
* 留给子类扩展环境准备逻辑

这一段不是最核心的 Bean 创建逻辑，但它是启动流水线的起跑动作。
相当于正式施工前，先把工地围起来、通电、验场地。

面试里不用展开太深，但要知道它的意义是：

> 容器进入“准备刷新”的状态，做一些最外层上下文初始化。

---

## 四、第二阶段：获取并准备 `BeanFactory` —— `obtainFreshBeanFactory()`

这一步非常关键。

它的核心目标是：

* 刷新或创建内部 `BeanFactory`
* 加载 BeanDefinition
* 让容器拿到一个“可工作的 BeanDefinition 工厂”

对于不同上下文实现，细节不同。
比如 XML 场景下，会经历：

* 创建/刷新 `DefaultListableBeanFactory`
* 读取 XML
* 解析成 BeanDefinition
* 注册到 BeanFactory 中

这一步结束后，Spring 容器里**已经有了 Bean 的定义信息**，但还没有真正创建大多数业务 Bean。

所以你可以这样理解：

> 到这一步，Spring 已经知道“要造什么”，但还没开始真的“造对象”。

---

## 五、第三阶段：准备 `BeanFactory` —— `prepareBeanFactory(beanFactory)`

这一步是在已有 `BeanFactory` 的基础上做标准能力注入。

典型动作有：

* 设置类加载器
* 设置表达式解析器
* 注册一些内建可解析依赖
* 注册几个特殊 aware 接口依赖
* 添加一些内置 `BeanPostProcessor`
* 注册环境、系统属性、系统环境等特殊 Bean

比如一些大家熟悉的能力：

* `ApplicationContextAware`
* `BeanFactoryAware`
* `EnvironmentAware`

之所以后面能自动回调，就是因为这里做了相关准备。

这一步本质上是在干嘛？

> 给 BeanFactory 安装“容器级标配能力”，让后续 Bean 创建时可以识别 Spring 特有语义。

---

## 六、第四阶段：留给子类增强 `postProcessBeanFactory(beanFactory)`

这是模板方法，给不同 `ApplicationContext` 子类一个继续加工 `BeanFactory` 的机会。

比如 Web 场景、特殊上下文实现，可以在这里追加自己的处理逻辑。

这一步面试里不用背具体谁实现了什么，但要知道它的定位：

> 这是 Spring 在标准 BeanFactory 准备之后，给具体上下文实现预留的增强挂点。

---

## 七、第五阶段：执行 `BeanFactoryPostProcessor`

这是面试非常高频的一段。

### 1）它处理的是 BeanDefinition，不是 Bean 实例

这是核心。

`BeanFactoryPostProcessor` 以及它的子接口 `BeanDefinitionRegistryPostProcessor`，主要作用于：

* BeanDefinition 元数据
* BeanDefinition 注册表

也就是说，这时候 Spring 还没大规模实例化 Bean，
所以你可以：

* 改 BeanDefinition
* 加新的 BeanDefinition
* 替换属性值
* 调整作用域
* 做条件注册

例如非常经典的：

* `ConfigurationClassPostProcessor`

它就是在这里处理 `@Configuration`、`@Bean`、`@ComponentScan`、`@Import` 等配置类机制的。

### 2）为什么这一步一定要早于 Bean 实例化

因为如果对象都已经创建好了，你再改 BeanDefinition 就晚了。
木头都已经锯完钉好了，你再改图纸，工人只会看着你沉默。

所以这一阶段的本质是：

> 在真正创建 Bean 之前，先把“图纸”改完、补完、注册完。

---

## 八、第六阶段：注册 `BeanPostProcessor`

这也是核心中的核心。

### 1）它处理的是 Bean 实例创建前后过程

`BeanPostProcessor` 跟前面的 BFPP 最大区别在于：

* BFPP 作用于定义
* BPP 作用于对象实例

典型用途包括：

* Aware 回调增强
* `@Autowired`
* `@Resource`
* `@PostConstruct`
* AOP 代理创建
* 初始化前后包装

Spring 大量高级特性，本质上都是靠各种 `BeanPostProcessor` 插进去的。

### 2）为什么必须在单例实例化前先注册好

因为后面 Bean 一旦开始创建，Spring 就会在创建链路里回调这些 BPP。
如果 BPP 没先注册，后创建的 Bean 就没法享受到这些增强能力。

比如：

* 没注册自动注入相关 BPP，`@Autowired` 不生效
* 没注册 AOP 相关 BPP，代理不会创建
* 没注册初始化注解处理器，`@PostConstruct` 不执行

所以这一步必须在实例化前完成。
本质上是：

> 先把“加工流水线上的工位”装好，后面 Bean 才能一个个经过这些工位被加工。

---

## 九、第七阶段：初始化消息源、事件广播器等基础设施

这一段主要包括：

* `initMessageSource()`
* `initApplicationEventMulticaster()`
* `onRefresh()`
* `registerListeners()`

### 1）消息源 `MessageSource`

用于国际化消息解析。
比如 `getMessage()` 这一套能力。

### 2）事件广播器 `ApplicationEventMulticaster`

用于后续事件发布和监听器派发。

### 3）`onRefresh()`

也是留给子类的扩展点。
例如 Web 容器场景会在这里做额外初始化。

### 4）注册监听器

把容器里的 `ApplicationListener` 注册进去，确保后续事件能被正确接收。

这一步的意义是：

> 在业务 Bean 大规模可用前，先把容器自己的基础设施搭起来。

---

## 十、第八阶段：实例化所有非懒加载单例 —— `finishBeanFactoryInitialization(beanFactory)`

这一步是很多人讲 `refresh()` 时最容易漏掉“重量级主戏”的地方。

这里 Spring 会做的事，本质上是：

* 完成 ConversionService 等剩余初始化
* 冻结 BeanDefinition 配置
* **预实例化所有非懒加载单例**

### 1）为什么最后才实例化单例

因为在此之前，容器必须先保证：

* BeanDefinition 已经最终稳定
* BFPP 都执行完了
* BPP 都注册完了
* 基础设施就绪了

否则对象一旦创建，很多增强机会就错过了。

所以这里体现了 Spring 一个非常重要的设计思想：

> 先把规则、图纸、加工器和基础设施都准备齐，再统一生产单例 Bean。

### 2）这一步会触发什么

这里才会真正大量触发：

* 构造器调用
* 属性注入
* 依赖解析
* Aware 回调
* `BeanPostProcessor` 前置后置处理
* 初始化方法
* AOP 代理生成
* 循环依赖处理

所以你平时看到的大部分 Bean 生命周期问题，真正爆发点都在这个阶段。

---

## 十一、第九阶段：完成刷新 —— `finishRefresh()`

这是收尾阶段。

典型动作包括：

* 初始化 `LifecycleProcessor`
* 回调生命周期相关方法
* 发布 `ContextRefreshedEvent`
* 清理启动过程中的一些缓存

这里意味着什么？

意味着容器正式宣布：

> 我已经刷新完成，可以对外提供完整服务了。

比如很多监听器依赖 `ContextRefreshedEvent` 做启动后逻辑，就是在这里触发。

---

## 十二、为什么顺序必须是：先 `BeanFactoryPostProcessor`，再 `BeanPostProcessor`，最后实例化单例

这块是面试高频追问，我单独拎出来。

### 1）先 BFPP，因为它改的是“定义”

它要先把 BeanDefinition 调整好。
例如：

* 配置类解析
* 新 BeanDefinition 注册
* 属性修改
* 占位符替换

如果这一步放晚了，Bean 已经按旧定义创建出来，就来不及了。

---

### 2）再 BPP，因为它改的是“对象创建过程”

BPP 必须在 Bean 创建前注册好，后续每个 Bean 创建时才能参与：

* 实例化前处理
* 初始化前处理
* 初始化后包装
* 代理替换

---

### 3）最后再实例化单例，因为前面两类扩展都依赖“对象还没真正大规模创建”

所以这个顺序本质上就是：

**先改图纸，再装流水线，最后正式生产。**

这是你在面试里最值得说出来的一句工程化总结。

---

## 十三、如果顺序错了，会怎样

这也是高级题的关键。

### 1）BFPP 晚了

后果：

* 配置类可能没被解析
* 占位符可能没替换
* 新 BeanDefinition 没注册进去
* Bean 会按旧定义被创建

典型表现就是容器行为不符合预期。

---

### 2）BPP 晚了

后果：

* `@Autowired` 失效
* `@PostConstruct` 不执行
* AOP 代理不生效
* 各种 aware / 注解驱动机制异常

因为 Bean 已经创建完了，再注册 BPP 就像菜都端上桌了，你才想起来厨房没装灶。

---

### 3）单例实例化太早

后果：

* 会跳过本该参与的后处理器
* 代理缺失
* 生命周期回调错乱
* 某些基础设施 Bean 还没准备好

这类问题在线上非常难排，因为现象往往不是直接报错，而是“功能看起来有一点不对”。

---

## 十四、面试里的一个标准回答模板

你可以直接这么答：

“`refresh()` 是 Spring 容器启动的总入口，它把容器从‘只有 BeanDefinition’推进到‘Bean 可用、扩展点生效、事件机制可用’的完整过程串起来了。
大致流程上，先是准备上下文环境，然后获取并刷新内部 BeanFactory，加载 BeanDefinition；接着对 BeanFactory 做标准能力准备，再执行 `BeanFactoryPostProcessor`，这一步主要是处理和修改 BeanDefinition，比如配置类解析、占位符替换、额外 BeanDefinition 注册。
之后注册 `BeanPostProcessor`，因为后续 Bean 创建、依赖注入、AOP 代理、初始化回调都依赖这些后处理器。然后初始化消息源、事件广播器和监听器等基础设施。
最后才是预实例化所有非懒加载单例，在这个过程中会真正触发 Bean 的创建、依赖注入、初始化和代理生成。全部完成后，Spring 会发布容器刷新完成事件。
之所以这个顺序不能乱，是因为 Spring 先要把 Bean 的定义和加工规则准备好，再去真正创建对象；如果扩展点顺序错了，像 `@Autowired`、AOP、配置类解析这些核心能力都会失效或行为异常。”

---

## 十五、小结

这题你记住 5 句话就够了：

`refresh()` 是 Spring 容器启动总入口。
它先准备 BeanDefinition，再准备扩展点，再实例化单例。
`BeanFactoryPostProcessor` 处理“定义”。
`BeanPostProcessor` 处理“实例”。
最后预实例化单例，才真正触发大部分 Bean 生命周期。

# 2. 为什么 Spring 要把扩展点分成 `BeanFactoryPostProcessor` 和 `BeanPostProcessor`？两者分别解决哪类问题？

## 为什么 Spring 要把扩展点分成 `BeanFactoryPostProcessor` 和 `BeanPostProcessor`？两者分别解决哪类问题？

先给结论：**因为 Spring 容器启动不是一个阶段，而是至少分成“定义阶段”和“实例阶段”两层问题。**
所以 Spring 必须把扩展点拆开：

* **`BeanFactoryPostProcessor`**：处理 **BeanDefinition / 容器元数据**
* **`BeanPostProcessor`**：处理 **Bean 实例创建前后**

这不是接口设计“想分就分”，而是容器架构决定的。
如果不分开，Spring 很多核心能力会互相打架：

* 你还没把 Bean 的图纸改完，就开始造对象
* 对象都造完了，你又想回头改定义
* AOP、自动注入、配置类解析、占位符替换这些时机全会乱掉

所以这题最稳的一句话是：

> Spring 把扩展点拆成 BFPP 和 BPP，本质上是把“修改生产图纸”和“加工已生产对象”分层处理，确保容器启动顺序和职责边界清晰。

---

## 一、先把两者最本质的区别说透

### 1）`BeanFactoryPostProcessor`：改“图纸”

它处理的是 **BeanDefinition**，也就是 Bean 的元数据定义。
此时大部分 Bean **还没有被创建**。

它能做的事情像是：

* 新增 BeanDefinition
* 修改 BeanDefinition 属性
* 替换占位符
* 改作用域
* 调整依赖关系
* 解析配置类、扫描注册更多 Bean

你可以把它理解成：

> 房子还没开工，这时候 архитектор（建筑师）还可以改施工图。

---

### 2）`BeanPostProcessor`：加工“成品或半成品对象”

它处理的是 **Bean 实例**。
Bean 已经进入创建流程了，它可以在：

* 初始化前
* 初始化后
* 某些实现里甚至实例化前后

对 Bean 做增强、替换、包装。

典型事情包括：

* 自动注入
* Aware 回调增强
* `@PostConstruct`
* AOP 代理
* 初始化前后加工

你可以把它理解成：

> 房子已经盖出来了，现在开始刷漆、装门、加智能家居，必要时甚至套一层外壳。

---

## 二、为什么 Spring 不能只保留一种扩展点

这是这题的核心，不要只背区别，要讲“为什么必须分”。

### 1）因为“定义问题”和“实例问题”根本不是一回事

Spring 容器启动时，至少有两类完全不同的问题：

#### 第一类：Bean 还没创建，先改定义

比如：

* `@Configuration` 要解析
* `@Bean` 方法要变成 BeanDefinition
* `${}` 占位符要替换
* `@ComponentScan` 要注册扫描出来的 Bean
* 条件装配要决定哪些 Bean 存在

这些事情都发生在“对象还没创建之前”。

#### 第二类：Bean 开始创建了，要加工对象

比如：

* `@Autowired` 注入
* `@PostConstruct`
* AOP 代理包装
* 自定义初始化增强
* 给某些 Bean 自动织入通用逻辑

这些事情已经进入“对象生命周期”了。

所以如果只用一个扩展点，就会出现一个非常别扭的问题：

> 同一套接口既要处理“对象还不存在时的定义变更”，又要处理“对象已经创建后的实例增强”。

这在设计上会非常混乱。

---

### 2）因为时机要求完全不同

这个特别重要。

#### BFPP 必须在 Bean 大规模实例化前执行

因为它改的是定义。
如果对象都创建好了，再改 BeanDefinition，等于图纸改了但房子已经盖完。

#### BPP 必须在 Bean 创建过程中提前就位

因为它要拦截 Bean 的生命周期。
如果 Bean 都创建完了，你再注册 BPP，那这些 Bean 就错过加工时机了。

所以 Spring 必须强制拆成两类，才能在 `refresh()` 流程里安排成：

**先 BFPP → 再注册 BPP → 最后实例化单例**

这条顺序链是容器成立的基础。

---

## 三、`BeanFactoryPostProcessor` 主要解决哪类问题

它主要解决的是：
**“容器应该生产什么，以及按什么定义生产”的问题。**

### 1）配置类解析问题

最经典的例子就是 `ConfigurationClassPostProcessor`。

它会处理：

* `@Configuration`
* `@Bean`
* `@ComponentScan`
* `@Import`
* `@ImportResource`

这些能力本质上都不是“实例增强”，而是：

> 把配置语义转换成更多 BeanDefinition。

这一步当然得发生在实例化前。

---

### 2）属性占位符和环境变量替换

例如：

```java id="g2jjv5"
@Value("${db.url}")
```

或者 XML / Java Config 里的 `${}` 占位符替换，本质上往往需要先在 BeanDefinition 层处理。

比如 `PropertySourcesPlaceholderConfigurer` 就属于这一路。

如果这类事情放到实例创建后才做，很多依赖值就已经错过时机了。

---

### 3）统一修改 Bean 定义元数据

例如你想在容器启动时统一把某类 Bean：

* 改成 prototype
* 改默认属性
* 加 dependsOn
* 改懒加载策略

这些都是典型 BFPP 适合做的事。

---

### 4）新增 BeanDefinition

有些框架扩展会根据注解、配置、外部资源动态向容器里注册新的 BeanDefinition。
这也必须发生在实例化前。

---

## 四、`BeanPostProcessor` 主要解决哪类问题

它主要解决的是：
**“Bean 已经开始创建或已创建完成后，怎么增强它”的问题。**

### 1）依赖注入

很多人容易误会，觉得 `@Autowired` 是 Spring 原生语言特性。其实不是，它本质上靠的是后处理器链。

典型如：

* `AutowiredAnnotationBeanPostProcessor`

它会在 Bean 生命周期中识别字段、方法、构造器注入点，并完成依赖注入。

也就是说，自动注入不是“定义阶段改图纸”能解决的，而是**对象级处理**。

---

### 2）初始化相关注解

比如：

* `@PostConstruct`

也是通过相关 BPP/生命周期处理机制介入的。

---

### 3）AOP 代理

这是最关键的 BPP 场景之一。

Spring AOP 的核心能力，很大程度依赖类似：

* `AnnotationAwareAspectJAutoProxyCreator`

本质上也是一个 `BeanPostProcessor` 体系里的家伙。

为什么一定要放在 BPP？

因为 AOP 代理处理的不是“BeanDefinition 长什么样”，而是：

> 某个 Bean 实例创建好后，要不要用代理对象替换它。

这显然是实例级问题，不是定义级问题。

---

### 4）Bean 包装和替换

BPP 可以在初始化后返回另一个对象替代原对象。
这就是为什么很多框架能“悄悄把你的 Bean 换成代理”。

例如：

* 原始对象是 `UserService`
* 返回给容器的却是代理后的 `UserService$$EnhancerBySpringCGLIB`

这件事只能发生在实例阶段。

---

## 五、为什么 BFPP 不能干 BPP 的活，BPP 也不能干 BFPP 的活

这题如果答到这层，会很加分。

### 1）BFPP 不适合做实例增强

因为 BFPP 执行时，大多数 Bean 还没创建。
它面对的是定义元数据，不是对象本体。

所以你没法在 BFPP 里做这些事：

* 给某个对象注入运行时依赖
* 看对象实例内容决定怎么包装
* 为实例创建代理

因为压根还没有“那个对象”。

---

### 2）BPP 不适合做容器定义级结构调整

虽然理论上你可以在某些奇怪时点里搞些骚操作，但从容器设计角度看，BPP 已经太晚了。

比如：

* 新增大量 BeanDefinition
* 改配置类解析规则
* 改占位符解析策略
* 调整容器图谱结构

这些都应该在 Bean 批量创建前完成。
等 Bean 开始创建了，你再大改定义，整个容器一致性就容易乱。

---

## 六、Spring 这样分层，带来了什么架构好处

### 1）容器阶段清晰

Spring 可以非常稳定地保证：

* 先确定“容器中有什么”
* 再决定“怎么创建这些东西”
* 最后决定“怎么增强这些对象”

这比一锅炖强太多。

---

### 2）扩展点职责清晰

框架作者和业务开发者都知道：

* 要改 BeanDefinition，就找 BFPP
* 要改 Bean 实例，就找 BPP

这使得 Spring 扩展生态非常可控。

---

### 3）很多高级能力才能解耦共存

例如：

* 配置类解析
* 条件装配
* 自动注入
* AOP
* 生命周期注解
* 事件监听器自动注册

这些能力之所以能一起工作，就是因为它们被安排在不同阶段，而不是抢同一个钩子。

---

## 七、最经典的代表类，面试里最好顺手提

### 1）BFPP 代表

* `BeanFactoryPostProcessor`
* `BeanDefinitionRegistryPostProcessor`
* `ConfigurationClassPostProcessor`
* `PropertySourcesPlaceholderConfigurer`

### 2）BPP 代表

* `BeanPostProcessor`
* `InstantiationAwareBeanPostProcessor`
* `SmartInstantiationAwareBeanPostProcessor`
* `AutowiredAnnotationBeanPostProcessor`
* `CommonAnnotationBeanPostProcessor`
* `AnnotationAwareAspectJAutoProxyCreator`

你不用全背，但至少知道：

> Spring 很多核心能力，表面是注解，底层其实都是后处理器体系在撑着。

---

## 八、如果 Spring 不这么分，会出现什么问题

这个问题特别像架构设计题的收束。

### 1）配置类解析会和 Bean 创建互相踩时机

比如还没把 `@Bean` 解析成定义，就开始实例化，那很多 Bean 根本不存在。

### 2）对象增强会漏掉时机

比如 AOP 后处理器没提前注册，后面的 Bean 就不会被代理。

### 3）容器可预测性变差

一旦“定义”和“实例”混在同一扩展阶段里，容器行为会变得很难推断：

* 某个扩展到底是在改定义还是改对象
* 某个 Bean 到底是不是按最新定义创建的
* 某个后处理器是不是错过了之前创建的 Bean

Spring 之所以能保持强大但又有秩序，很大程度上靠的就是这种阶段分层。

---

## 九、一个适合面试的标准回答

你可以直接这么答：

“Spring 把扩展点分成 `BeanFactoryPostProcessor` 和 `BeanPostProcessor`，本质上是因为容器启动时有两个完全不同层次的问题。
`BeanFactoryPostProcessor` 处理的是 BeanDefinition，也就是 Bean 的定义和元数据，它主要解决‘容器里应该有哪些 Bean、这些 Bean 应该按什么规则创建’的问题，比如配置类解析、占位符替换、BeanDefinition 注册和修改。
而 `BeanPostProcessor` 处理的是 Bean 实例创建前后的增强，它主要解决‘对象创建出来以后怎么加工和包装’的问题，比如自动注入、`@PostConstruct`、Aware 回调、AOP 代理等。
Spring 必须把它们拆开，是因为二者作用时机完全不同：BFPP 必须在大规模实例化前执行，否则图纸改晚了；BPP 必须在 Bean 创建前注册好，否则后续对象就错过增强时机。
所以这个设计本质上是在把‘改图纸’和‘加工对象’分层，保证容器启动顺序清晰，也让 Spring 的各种扩展能力能够稳定协作。”

## 十、小结

这题你记住 4 句话就够了：

BFPP 处理定义，BPP 处理实例。
BFPP 解决“造什么”，BPP 解决“造出来后怎么加工”。
两者时机不同，所以必须拆开。
Spring 本质上是在分离“改图纸”和“做成品增强”。

# 3. 为什么 Spring 要在创建普通 Bean 之前，先提前实例化一些基础设施 Bean（尤其是某些 `BeanPostProcessor`）？顺序错了会怎样？

## 为什么 Spring 要在创建普通 Bean 之前，先提前实例化一些基础设施 Bean（尤其是某些 `BeanPostProcessor`）？顺序错了会怎样？

先给结论：**因为很多“普通 Bean 看起来天然拥有的能力”，本质上不是 Bean 自己会，而是容器提前装好的一批“加工机器”赋予它的。**
这些加工机器里最关键的一类，就是各种 `BeanPostProcessor`。

所以 Spring 必须先做这件事：

**先把工厂、规则、加工器、基础设施准备好，再开始批量生产普通 Bean。**

否则就会出现非常典型的问题：

* `@Autowired` 不生效
* `@PostConstruct` 不执行
* AOP 不生效
* 事务代理没织入
* `@Async`、`@Resource`、`@Value` 等行为异常
* 某些 Bean 提前被“裸实例化”，后面再也补不回增强

这题最稳的一句话是：

> Spring 提前实例化基础设施 Bean，本质上是在确保“Bean 创建流水线”先被搭好；如果流水线没搭好就先生产普通 Bean，那后面很多增强能力会永久错过时机。

---

## 一、为什么一定要“先基础设施，后普通 Bean”

### 1）因为普通 Bean 的很多能力依赖容器加工，不是对象天然自带

例如你写：

```java
@Service
public class OrderService {
    @Autowired
    private UserService userService;
}
```

很多人潜意识会觉得：

> `@Autowired` 是 Spring 天然会的

其实不是。
它背后要依赖类似：

* `AutowiredAnnotationBeanPostProcessor`

这个后处理器在 Bean 创建流程里识别注入点、解析依赖、完成注入。

也就是说，如果这个 BPP 还没准备好，`OrderService` 就被提前创建了，那么这个对象很可能就是一个**没经过自动注入加工的半成品**。

---

### 2）因为 Bean 生命周期拦截是“一次性时机”

`BeanPostProcessor` 之所以叫后处理器，不是说它能随时把历史遗留 Bean 全部重新加工一遍。
它的能力是嵌在 **Bean 创建链路** 里的。

也就是说，一个普通 Bean 创建时，大致会经过：

* 实例化前处理
* 实例化
* 属性填充
* 初始化前处理
* 初始化
* 初始化后处理

这些步骤里，BPP 会在关键节点插进去。

问题是：

> 如果 Bean 已经在这些阶段“走过去了”，而当时对应的后处理器还没注册，那这个 Bean 就错过了。

这不是后面“补注册一下 BPP”就能自动追回来的。
流水线上的工件已经出厂了，你再把喷漆工位装上去，不会让仓库里已出厂的货自动自己回来排队重刷。

---

## 二、为什么尤其要提前实例化某些 `BeanPostProcessor`

这块是关键。

### 1）因为 BPP 本身就是“Bean 创建链路的拦截器”

BPP 不是普通工具类，它本身就是 Bean 创建过程中非常核心的拦截点。

典型代表包括：

* `AutowiredAnnotationBeanPostProcessor`
* `CommonAnnotationBeanPostProcessor`
* `AnnotationAwareAspectJAutoProxyCreator`

这些家伙决定了：

* 能不能自动注入
* 能不能识别 `@PostConstruct`
* 能不能织入 AOP / 事务代理

所以 Spring 在 `refresh()` 里一定会先：

**注册并初始化这些 BPP**，然后才去创建普通单例 Bean。

因为只有这样，后续所有普通 Bean 在创建时，才能经过完整处理链。

---

### 2）因为有些基础设施 Bean 决定了容器“后面的游戏规则”

除了 BPP，还有一些基础设施 Bean 也是类似道理，比如：

* 事件广播器
* 生命周期处理器
* 消息源
* 环境解析相关组件
* 自动代理创建器
* 配置类处理器

这些都不是简单“先后无所谓”的 Bean。
它们定义的是：

* 容器怎么解释注解
* 怎么注入依赖
* 怎么创建代理
* 怎么发布事件
* 怎么驱动生命周期

所以它们必须先于大多数业务 Bean 就绪。

---

## 三、Spring 为什么要专门把这些 Bean 当“基础设施”看待

### 1）因为它们不是业务对象，而是容器能力的一部分

你可以把 Spring 容器想成一个工厂。

那业务 Bean 是要生产出来的产品。
而基础设施 Bean 更像是：

* 传送带
* 机械臂
* 质检工位
* 喷漆工位
* 总控台

这些东西不能混在“普通产品批量生产阶段”里慢慢碰运气初始化。
它们必须优先就位。

---

### 2）因为 Spring 要保证“后创建的 Bean 都遵守同一套规则”

如果不提前准备基础设施，就会出现很糟糕的不一致：

* 某些早创建的 Bean 没有 AOP
* 某些晚创建的 Bean 有 AOP
* 某些 Bean 的 `@Autowired` 生效
* 某些 Bean 的 `@Autowired` 不生效

这会让容器行为变得不可预测。
而 Spring 作为框架，最重要的一件事就是：**容器行为必须稳定、可预测。**

所以它宁愿在前面多做一轮基础设施初始化，也要保证后面普通 Bean 走的是统一流水线。

---

## 四、顺序错了会怎样

这题一定要答具体，不然会飘。

---

## 五、第一类问题：依赖注入类能力失效

### 1）`@Autowired`、`@Resource`、`@Value` 可能失效

如果相关后处理器还没就位，普通 Bean 就先被创建了，那么这些 Bean 在属性填充阶段就拿不到对应增强。

表现可能是：

* 字段仍然是 `null`
* 配置值没注进去
* 方法注入没生效

这种问题非常坑，因为很多时候不是容器直接启动失败，而是业务运行时 NPE。

---

## 六、第二类问题：初始化回调缺失

### 1）`@PostConstruct` 可能不执行

如果 `CommonAnnotationBeanPostProcessor` 之类没及时参与，Bean 的初始化增强阶段就会漏掉。

表现为：

* 初始化逻辑没跑
* 缓存没预热
* 本地状态没准备
* 连接没建立
* 注册动作没发生

这类问题尤其容易造成“程序能启动，但功能不对”。

---

## 七、第三类问题：AOP / 事务 / 异步代理失效

这类是高频重灾区。

### 1）事务代理失效

例如：

```java
@Transactional
public void pay() { ... }
```

如果自动代理创建器相关 BPP 没先准备好，这个 Bean 可能会以**原始对象**形式直接进容器，而不是代理对象。

那后果就是：

* `@Transactional` 看着在，实际上没切事务
* 回滚不生效
* 传播行为失效
* 你以为在事务里，其实根本不在

这个线上很危险，因为它不是“报错”，而是**静悄悄地错**。

---

### 2）AOP 切面不生效

比如日志埋点、权限校验、审计、限流这些切面，全可能失效。
因为 Bean 一旦作为裸对象提前创建，后面自动代理器再注册，也不会自动把这个对象重新代理一遍。

---

### 3）`@Async`、`@Cacheable` 等注解增强失效

本质也是一样。
它们通常最终也依赖代理链路。
如果顺序错了，这些增强也会漏掉。

---

## 八、第四类问题：出现“Bean 没走完整生命周期”的隐性 bug

这是最难排的。

### 1）Bean 被提前实例化，变成“早产 Bean”

Spring 启动时如果某些基础设施 Bean 自己依赖了普通 Bean，或者某些扩展点里不小心调用了 `getBean()`，就可能导致普通 Bean 被提前创建。

这种 Bean 创建时，容器可能还没完全准备好，于是会出现：

* 没经过完整 BPP 链
* 没有代理
* 没有完整注入
* 生命周期时机异常

Spring 日志里有时会提示类似：

> Bean is not eligible for getting processed by all BeanPostProcessors

这个提示背后的本质就是：

> 这个 Bean 创建太早了，它没赶上完整的后处理器链。

这在面试里顺手说出来，味道就很对。

---

## 九、第五类问题：容器行为不一致，排障非常困难

这是架构层面的坏处。

如果基础设施没先就绪，普通 Bean 创建顺序变得混乱，就会出现：

* 有的 Bean 被代理，有的没被代理
* 有的能注入，有的不能注入
* 有的回调执行了，有的没执行
* 同类 Bean 行为不一致

这种问题最烦，不是“全坏”，而是“半坏半不坏”，像系统里埋了几个定时抽风的小妖怪。

---

## 十、为什么 Spring 会特别警惕“在 BPP 注册阶段触发普通 Bean 创建”

这是很细但很加分的点。

Spring 自己在注册 `BeanPostProcessor` 的时候，其实非常小心，尽量避免这时候提前创建普通 Bean。
因为一旦普通 Bean 在这个阶段被拉起来，它很可能：

* 还没经过所有 BPP
* 只经过一部分处理器
* 成为早期裸对象

所以框架设计上会尽量把：

* BFPP 执行完
* BPP 注册完
* 基础设施 Bean 准备完

之后，再进入大规模普通单例预实例化。

这本质上是在保护容器启动顺序的纯洁性。听着有点宗教味，但确实很重要。

---

## 十一、一个很典型的面试加分点：为什么“自动代理创建器”必须特别早

像 `AnnotationAwareAspectJAutoProxyCreator` 这种东西，本质上是个非常关键的 BPP。
它决定很多 Bean 最终是不是要被替换成代理。

如果它晚了，会发生什么？

* 某些 Bean 已经按原始对象创建完成
* 它们不会被代理
* 事务/AOP/缓存等增强直接失效

所以自动代理创建器这类基础设施 Bean 必须非常早就参与容器流程。
你可以理解成它是整个代理世界的总闸门，闸门晚装，前面放过去的水就不会倒流回来重过一遍。

---

## 十二、面试里的一个标准回答模板

你可以直接这么答：

“Spring 要在创建普通 Bean 之前，先提前实例化一些基础设施 Bean，尤其是某些 `BeanPostProcessor`，本质上是因为很多普通 Bean 的能力不是对象天然具备的，而是依赖容器在创建过程中通过后处理器链加工出来的。
比如 `@Autowired`、`@Resource`、`@PostConstruct`、AOP 代理、`@Transactional`、`@Async` 等，底层都依赖不同类型的 `BeanPostProcessor`。如果这些处理器没有提前注册和就位，普通 Bean 一旦被提前创建，就会错过对应生命周期拦截点，后面再注册处理器也补不回来。
顺序错了，典型后果包括自动注入失效、初始化回调缺失、AOP 和事务代理失效，甚至出现某些 Bean 没经过完整后处理链，只以裸对象形式进入容器。Spring 日志里常见的‘某 Bean is not eligible for getting processed by all BeanPostProcessors’本质上就是这个问题。
所以 Spring 必须先把基础设施和加工流水线搭好，再去批量创建普通 Bean，这样才能保证后续 Bean 统一经过完整生命周期和增强链。”

## 十三、小结

这题你记住 4 句话就够了：

很多普通 Bean 的能力依赖后处理器，不是天生就有。
BPP 本质是 Bean 创建流水线上的加工工位。
工位没装好就先生产，很多增强会永久错过。
顺序错了，最典型的后果就是注入失效、AOP/事务失效、早期裸 Bean 混入容器。

# 4. Spring 里循环依赖为什么通常只解决单例的 setter/字段注入，为什么构造器循环依赖很难解？
