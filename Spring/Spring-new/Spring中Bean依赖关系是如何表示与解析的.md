# Spring 中 Bean 依赖关系是如何表示与解析的

## 目录

1. [[#一、两个核心问题|一、两个核心问题]]
2. [[#二、如何查看依赖关系|二、如何查看依赖关系]]
3. [[#三、Spring 中“依赖关系”不是只有一种|三、Spring 中“依赖关系”不是只有一种]]
4. [[#四、依赖关系的数据结构|四、依赖关系的数据结构]]
5. [[#五、依赖关系是怎么一步步解析出来的|五、依赖关系是怎么一步步解析出来的]]
6. [[#六、为什么不会一开始就有完整依赖图|六、为什么不会一开始就有完整依赖图]]
7. [[#七、这些数据结构各自解决什么问题|七、这些数据结构各自解决什么问题]]
8. [[#八、学习源码时最值得盯的入口|八、学习源码时最值得盯的入口]]
9. [[#九、你最后应该形成的整体图景|九、你最后应该形成的整体图景]]

关联笔记：

- [[Spring学习路线图]]
- [[Spring到底解决了哪些工程问题]]

## 一、两个核心问题

关于 Spring 的依赖关系，最常见的两个问题是：

- 怎么方便地查看 Bean 之间谁依赖谁？
- 这些依赖关系在 Spring 内部到底是怎么存的？

先给结论：

### 1. 查看依赖关系最方便的方式

- 看运行时 `BeanFactory` 提供的依赖查询接口
- 在源码里沿着 `doCreateBean -> populateBean -> doResolveDependency` 跟调用链
- 用 IDE 的 Spring 图辅助观察

### 2. Spring 内部最核心的几类结构

- `beanDefinitionMap`：保存 Bean 的定义信息
- `dependentBeanMap`：保存“谁依赖我”
- `dependenciesForBeanMap`：保存“我依赖谁”
- `singletonObjects`、`earlySingletonObjects`、`singletonFactories`：保存 Bean 创建过程中的实例状态，不直接等于依赖图，但和依赖解析、循环依赖密切相关

所以要先建立一个观念：

**Spring 的依赖关系不是存在某一个单一结构里，而是分散在“定义信息”“运行时依赖登记”“实例创建状态”这几层里。**

---

## 二、如何查看依赖关系

如果你的目的是学习 Spring 原理，而不是只看项目里某个 Bean 注入了谁，那么最推荐下面三种方式。

### 1. 运行时通过 BeanFactory 查询

这是最直接也最贴近 Spring 内部模型的方式。

常用接口：

- `getBeanDefinitionNames()`
- `getDependenciesForBean(beanName)`
- `getDependentBeans(beanName)`

示例：

```java
ConfigurableApplicationContext context = SpringApplication.run(App.class, args);
ConfigurableListableBeanFactory factory = context.getBeanFactory();

for (String beanName : factory.getBeanDefinitionNames()) {
    System.out.println("Bean: " + beanName);
    System.out.println("  depends on: " + Arrays.toString(factory.getDependenciesForBean(beanName)));
    System.out.println("  depended by: " + Arrays.toString(factory.getDependentBeans(beanName)));
}
```

这个方式的价值在于：

- 能看到容器最终登记下来的依赖关系
- 能把“我依赖谁”和“谁依赖我”两个方向都看见
- 很适合你自己做 demo 验证

### 2. 在源码里跟依赖解析主线

如果你要理解“为什么会形成这些依赖关系”，最好的方式不是只看输出，而是跟源码。

建议重点盯这几个方法：

- `AbstractAutowireCapableBeanFactory#doCreateBean`
- `AbstractAutowireCapableBeanFactory#populateBean`
- `DefaultListableBeanFactory#doResolveDependency`

你会看到：

- Bean 是什么时候开始解析依赖的
- 注解注入为什么能生效
- 依赖解析成功后是怎么登记进容器里的

### 3. 用 IDE 辅助看 Bean 关系

比如 IntelliJ IDEA Ultimate 对 Spring 项目有：

- Bean 导航
- 注入关系跳转
- Spring 图形化视图

它的优点是上手快，适合快速观察。

它的局限是：

- 更适合“看项目”
- 不足以替代你对 Spring 内部机制的理解

所以最好的学习方式是：

**IDE 看现象，源码看本质，运行时查询做验证。**

---

## 三、Spring 中“依赖关系”不是只有一种

很多人一提到“依赖关系”，会默认以为就是 `@Autowired` 注入关系。

其实 Spring 中至少有下面几类相关关系：

### 1. 定义层依赖

比如：

- 构造器参数依赖
- 属性注入依赖
- `dependsOn`
- 工厂方法参数依赖

这些关系在 BeanDefinition 层就已经有一部分信息了。

### 2. 解析层依赖

比如：

- `@Autowired`
- `@Qualifier`
- `@Resource`
- 泛型匹配、主候选匹配

这些不是一开始就完全静态确定，而是在 Bean 创建过程中解析出来的。

### 3. 运行时登记依赖

Spring 在真正解析出某个 Bean 依赖另一个 Bean 之后，会把这种关系登记进依赖表中。

这个阶段的依赖关系是容器真正能回答“谁依赖谁”的基础。

### 4. 创建时序关系

比如循环依赖场景下：

- 谁先实例化
- 谁提前暴露 early reference
- 谁在等谁完成初始化

这类不完全是业务意义上的依赖图，但和容器创建流程密切相关。

所以以后你看 Spring 依赖关系时，要把它拆开：

- **定义层的信息**
- **解析层的行为**
- **运行时登记的关系**
- **创建过程中的状态**

---

## 四、依赖关系的数据结构

这部分是理解 Spring 内部实现的核心。

### 1. `beanDefinitionMap`：Bean 定义表

位置上主要在 `DefaultListableBeanFactory` 中。

典型结构：

```java
Map<String, BeanDefinition> beanDefinitionMap
```

它保存的是：

- Bean 的类信息
- scope
- 构造参数
- 属性值
- 工厂方法
- `dependsOn`
- lazy、primary、autowireCandidate 等元信息

你可以把它理解成：

**这是 Spring 容器里“Bean 图纸”的仓库。**

它描述的是：

- 这个 Bean 是谁
- 这个 Bean 怎么创建

但它还不是完整运行时依赖图。

### 2. `dependentBeanMap`：谁依赖我

位置上主要在 `DefaultSingletonBeanRegistry` 中。

典型结构：

```java
Map<String, Set<String>> dependentBeanMap
```

含义：

- key：被依赖的 Bean
- value：依赖它的 Bean 集合

例如：

```text
orderRepository -> [orderService]
```

意思是：

- `orderService` 依赖 `orderRepository`
- 从 `orderRepository` 视角看，是“谁依赖我”

### 3. `dependenciesForBeanMap`：我依赖谁

同样主要在 `DefaultSingletonBeanRegistry` 中。

典型结构：

```java
Map<String, Set<String>> dependenciesForBeanMap
```

含义：

- key：当前 Bean
- value：它依赖的 Bean 集合

例如：

```text
orderService -> [orderRepository, paymentService]
```

意思是：

- `orderService` 依赖 `orderRepository` 和 `paymentService`

这个结构和 `dependentBeanMap` 是一对正反向索引。

### 4. `containedBeanMap`：包含关系

还有一类容易被忽略的结构，是 Bean 的包含关系。

典型场景：

- 内部 Bean
- 某些组合式定义

这类关系不是最核心，但它影响销毁顺序和容器管理边界。

### 5. `singletonObjects` / `earlySingletonObjects` / `singletonFactories`

这三个结构不是“依赖图存储表”，但学习依赖关系时一定会碰到。

它们主要用于：

- 单例缓存
- 早期引用暴露
- 循环依赖处理

典型结构：

```java
Map<String, Object> singletonObjects
Map<String, Object> earlySingletonObjects
Map<String, ObjectFactory<?>> singletonFactories
```

它们回答的问题不是“谁依赖谁”，而是：

- 这个 Bean 现在创建到哪一步了
- 能不能先把一个早期引用交出去

所以要区分：

- `dependentBeanMap` / `dependenciesForBeanMap` 是依赖关系索引
- `singletonObjects` 等是实例状态缓存

---

## 五、依赖关系是怎么一步步解析出来的

这部分最值得你真正吃透。

### 1. 先有 BeanDefinition

Spring 启动时，首先会通过：

- 组件扫描
- `@Configuration`
- `@Bean`
- `@Import`
- XML

把 Bean 的定义注册进容器。

这时容器知道的是：

- 有哪些 Bean
- 每个 Bean 的基本创建信息

但这时还没有完整运行时依赖图。

### 2. 创建 Bean 时进入主流程

当 Spring 真正创建某个 Bean 时，会进入：

- `createBean`
- `doCreateBean`

在这个阶段，Spring 开始做：

- 实例化
- 依赖注入
- 初始化

### 3. 在 `populateBean()` 阶段解析属性和注入点

如果一个 Bean 有字段注入、setter 注入、注解注入，那么通常会在 `populateBean()` 阶段处理。

这时会有相关的后处理器参与，比如：

- `AutowiredAnnotationBeanPostProcessor`

它会做的事大致是：

- 找出哪些字段、方法、构造参数需要注入
- 为这些注入点生成依赖描述
- 交给 BeanFactory 去解析候选 Bean

### 4. 在 `doResolveDependency()` 中真正匹配候选 Bean

这是 Spring 依赖解析的关键入口之一。

它会综合考虑：

- 类型匹配
- `@Qualifier`
- `@Primary`
- 名称匹配
- 泛型信息
- 可选依赖

最后决定：

- 这个注入点到底应该注入哪个 Bean

### 5. 解析成功后登记依赖关系

当 Spring 确认某个 Bean 依赖另一个 Bean 后，会调用类似：

- `registerDependentBean`

把依赖关系同时登记进：

- `dependentBeanMap`
- `dependenciesForBeanMap`

这是非常重要的一步，因为从这一刻起，容器才真正“记住了”这条依赖关系。

### 6. 后续用于销毁顺序、查询和循环依赖辅助

登记后的依赖关系不会只在注入那一刻使用一次，它后面还会被用来处理：

- 销毁顺序
- `getDependenciesForBean`
- `getDependentBeans`
- 部分依赖检查与生命周期管理

所以依赖关系表本质上是容器运行时治理能力的一部分。

---

## 六、为什么不会一开始就有完整依赖图

这个问题很关键，因为它能帮助你理解 Spring 的设计风格。

直觉上你可能会想：

- 既然最终都要依赖关系，为什么不启动时直接扫描出完整依赖图？

原因在于很多依赖关系不是纯静态的。

### 1. 一部分依赖要到创建时才能确定

比如：

- `@Autowired` 的候选匹配
- `@Qualifier` 的选择
- 泛型推断
- 工厂方法返回类型判断

这些都可能依赖容器当时的完整上下文。

### 2. 有些 Bean 本身会动态注册更多 Bean

比如：

- `BeanFactoryPostProcessor`
- `BeanDefinitionRegistryPostProcessor`
- 配置类解析

这意味着容器前期的“图”并不是最终图。

### 3. Spring 更偏向“分阶段构建”

Spring 一直是这种设计风格：

- 先注册定义
- 再处理定义
- 再实例化
- 再解析依赖
- 再登记关系

这种方式的好处是：

- 更灵活
- 更适合扩展
- 更能容纳动态行为

代价是：

- 理解成本更高
- 很多关系要顺着生命周期看，不能只看静态结构

所以你可以把 Spring 理解为：

**它不是在启动时一次性生成一张静态依赖图，而是在容器生命周期中逐步把依赖关系构建出来。**

---

## 七、这些数据结构各自解决什么问题

为了防止后面读源码时混掉，可以直接这样记。

### 1. `beanDefinitionMap`

解决的是：

- Bean 定义存储
- Bean 注册管理

一句话：

**存“这个 Bean 怎么造”。**

### 2. `dependenciesForBeanMap`

解决的是：

- 当前 Bean 依赖谁

一句话：

**存“我依赖谁”。**

### 3. `dependentBeanMap`

解决的是：

- 谁依赖当前 Bean

一句话：

**存“谁依赖我”。**

### 4. `singletonObjects`

解决的是：

- 完整单例缓存

一句话：

**存“已经造好的 Bean”。**

### 5. `earlySingletonObjects`

解决的是：

- 循环依赖中的早期引用暴露

一句话：

**存“先借出去用的半成品引用”。**

### 6. `singletonFactories`

解决的是：

- 按需生成 early reference
- 支持 AOP 场景下的早期代理引用

一句话：

**存“如果有人现在急着要，我该怎么给他一个早期引用”。**

---

## 八、学习源码时最值得盯的入口

如果你接下来要结合源码学，建议优先盯下面几个位置。

### 1. `DefaultListableBeanFactory`

重点看：

- BeanDefinition 管理
- 依赖解析主入口

### 2. `AbstractAutowireCapableBeanFactory#doCreateBean`

重点看：

- Bean 创建主线
- 依赖注入和初始化的分阶段处理

### 3. `AbstractAutowireCapableBeanFactory#populateBean`

重点看：

- 注入点是怎么被处理的

### 4. `DefaultListableBeanFactory#doResolveDependency`

重点看：

- 候选 Bean 是怎么匹配出来的

### 5. `DefaultSingletonBeanRegistry`

重点看：

- 依赖关系登记
- 单例缓存
- 循环依赖相关结构

如果你后面要真正啃这块源码，最好的顺序是：

`refresh() -> doCreateBean() -> populateBean() -> doResolveDependency() -> registerDependentBean()`

---

## 九、你最后应该形成的整体图景

学完这块之后，你最好脑子里有这样一张图：

### 1. Spring 先存定义，不先存完整依赖图

也就是：

- 先有 `BeanDefinition`
- 再在创建时解析依赖

### 2. 依赖关系是在运行时逐步登记的

也就是：

- 注入点解析成功后
- 才会写入依赖关系表

### 3. 依赖关系索引和实例缓存是两套结构

也就是：

- `dependentBeanMap` / `dependenciesForBeanMap` 回答“谁依赖谁”
- `singletonObjects` / `earlySingletonObjects` / `singletonFactories` 回答“Bean 现在创建到哪一步”

### 4. Spring 管理的不只是对象，而是对象图、生命周期和扩展秩序

这才是你真正应该看到的重点。

Spring 不是一个“高级 new 工具”，它本质上是在维护：

- 对象定义
- 对象关系
- 对象创建过程
- 对象增强过程
- 对象销毁顺序

当你能把这几层连起来理解时，你对 Spring 容器的理解就会开始真正成型。
