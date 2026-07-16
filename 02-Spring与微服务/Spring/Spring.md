> [!info] 文档定位：基础知识主文
>
> 本文负责回答“是什么、为什么、基本如何使用”，并给出容器主流程、常见配置和排障入口。建议按「循环依赖 → 生命周期/IOC → `ApplicationContext` 与 `refresh()` → DI/Scope/Profile → AOP/事务常见问题」学习。
>
> 遇到源码调用链、代理边界、早期引用一致性、事务传播与并发取舍时，进入 [[Spring深度解析|《Spring深度解析》]]；不要在两篇笔记中维护同一份深度推导。

## 目录

1. [[#1. 循环依赖|循环依赖与三级缓存]]：[[#2. 三级缓存|缓存状态迁移]]、[[#4. @Lazy 的作用|`@Lazy`]]
2. [[#6. Bean 生命周期|Bean 生命周期]]、[[#7. IoC 与 DI|IoC/DI]]、[[#8. ApplicationContext|容器]]、[[#9. refresh()|`refresh()`]]
3. [[#10. Bean Scope|Scope]]、[[#11. Spring Profile 的原理|Profile]]、[[#12. 依赖注入原理|依赖解析]]、[[#13. Spring 注册 Bean 的整体详细源码解析|Bean 注册]]
4. [[#14. Spring 的单例 Bean 是线程安全的吗|单例并发]]、[[#15. Spring事务失效|事务失效]]、[[#17. 为什么不推荐使用字段注入|注入风格]]、[[#18. Spring AOP 的工作原理|AOP]]、[[#19. Spring 事务原理（进阶入口）|事务调用链]]

# 1. 循环依赖
在Spring中，循环依赖是指两个或多个Bean相互依赖，形成一个闭环。Spring处理循环依赖的方式取决于Bean的作用域（如单例或原型）。

### 1. 单例Bean的循环依赖
三级缓存只适用于**单例 Bean 的属性注入**（Setter/字段注入）场景：Bean 已实例化、但尚未完成属性填充时，容器才能暴露早期引用。构造器循环依赖在实例化前就必须拿到对方，通常会创建失败并抛出 `BeanCurrentlyInCreationException`。

- **三级缓存机制**：
  1. **早期引用**：Bean 实例化后、初始化前，容器可将其早期引用暴露给正在创建的依赖方。
  2. **二级缓存**：Bean的实例会在完全初始化前被放入二级缓存中。
  3. **正式缓存**：一旦Bean完全初始化，会被放入正式的单例缓存中。

### 2. 原型Bean的循环依赖
对于原型 Bean，Spring 不使用单例三级缓存处理循环依赖，通常会在创建阶段抛出 `BeanCurrentlyInCreationException`；不要把它理解为会稳定地递归到 `StackOverflowError`。

### 3. 示例
假设有两个Bean A和B：

```java
@Component
public class A {
    private B b;

    @Autowired
    public A(B b) {
        this.b = b;
    }
}

@Component
public class B {
    private A a;

    @Autowired
    public B(A a) {
        this.a = a;
    }
}
```

这是**构造器循环依赖**：创建 `A` 需要完整的 `B`，创建 `B` 又需要完整的 `A`；三级缓存尚未来得及暴露任何实例，因此默认无法解决。

### 4. 解决方法
- **重构代码**：尽量避免循环依赖，可以通过重构代码来消除相互依赖的关系。（**依赖倒置**：> **依赖倒置让代码依赖于“稳定的抽象”而非“易变的实现”，从而提高复用性、可测试性和灵活性。**）
``` java
interface Processor {
    void process();
}

@Component
class A implements Processor {
    public void process() {
        System.out.println("A processing");
    }
}

@Component
class B {
    private final Processor processor;

    @Autowired
    public B(Processor processor) {
        this.processor = processor;
    }
}

```
- **使用 `@Lazy` 注解**：在一条注入边上延迟解析依赖，可作为兼容性手段；优先选择重构。
- **理解属性注入的可解边界**：先让 Spring 实例化 `A`，在属性填充前提前暴露 `A` 的 early reference；创建 `B` 时取到该引用，最后再回填 `A` 的 `B` 属性。它解释了三级缓存为何能处理部分单例循环依赖，并不是推荐以字段注入来设计业务对象。
  
  ```java
  @Autowired
  @Lazy
  private B b;
  ```

通过理解和处理循环依赖，可以提高Spring应用的稳定性和可维护性。

# 2. 三级缓存
在Spring中，为了解决单例Bean的循环依赖问题，Spring使用了三级缓存机制。下面详细解释这个机制的工作原理。

``` java
DefaultSingletonBeanRegistry.class
protected Object getSingleton(String beanName, boolean allowEarlyReference) {  
    // Quick check for existing instance without full singleton lock  
    Object singletonObject = this.singletonObjects.get(beanName);  
    if (singletonObject == null && isSingletonCurrentlyInCreation(beanName)) {  
       singletonObject = this.earlySingletonObjects.get(beanName);  
       if (singletonObject == null && allowEarlyReference) {  
          synchronized (this.singletonObjects) {  
             // Consistent creation of early reference within full singleton lock  
             singletonObject = this.singletonObjects.get(beanName);  
             if (singletonObject == null) {  
                singletonObject = this.earlySingletonObjects.get(beanName);  
                if (singletonObject == null) {  
                   ObjectFactory<?> singletonFactory = this.singletonFactories.get(beanName);  
                   if (singletonFactory != null) {  
                      singletonObject = singletonFactory.getObject();  
                      this.earlySingletonObjects.put(beanName, singletonObject);  
                      this.singletonFactories.remove(beanName);  
                   }  
                }  
             }  
          }  
       }  
    }  
    return singletonObject;  
}
```

## 1. 三级缓存的概念

Spring的三级缓存主要包括：

- **一级缓存**：即`singletonObjects`，存储完全初始化的单例Bean。
- **二级缓存**：即`earlySingletonObjects`，存储早期引用的单例Bean（未完全初始化）。
- **三级缓存**：即`singletonFactories`，存储`ObjectFactory`的引用，用于创建Bean的早期引用。(使用`HashMap`，其他使用的为`ConcurrentHashMap`，原因为三级缓存使用时是被synchronized包围)

## 2. 缓存机制详解

### 1) 创建Bean的流程

当请求一个单例Bean时，Spring的处理流程如下：

1. **检查一级缓存**：
   - 首先检查`singletonObjects`，如果找到对应的Bean，直接返回。

2. **检查二级缓存**：
   - 如果一级缓存中没有，检查`earlySingletonObjects`。如果找到了早期引用，直接返回。

3. **创建Bean**：
   - 如果一级和二级缓存都没有，Spring 开始创建 Bean：
     - 在创建过程中，Spring会将当前Bean的`ObjectFactory`放入三级缓存`singletonFactories`中。
     - 同时将该Bean的引用添加到`earlySingletonObjects`中。

4. **依赖注入**：
   - 如果Bean的构造函数或属性需要其他Bean（可能是处于循环依赖中），Spring会先从`earlySingletonObjects`中获取早期引用。

5. **完成初始化**：
   - 一旦所有依赖注入完成，Bean会被完全初始化，并放入一级缓存`singletonObjects`中。

### 2) 解决循环依赖

通过三级缓存，Spring能够在创建Bean时允许依赖注入的部分进行引用，从而解决单例Bean的循环依赖问题。

## 3. 注意事项

- **仅适用于单例Bean**：三级缓存机制只对单例Bean有效，原型Bean无法解决循环依赖。
- **可能引入不完整的状态**：使用三级缓存可能导致某些Bean在未完全初始化时被引用，因此要谨慎使用，避免引入不一致的状态。

## 4.  重复读取2次的原因

这段代码里 **“同一个 Map get 两遍”**不是手滑，而是一个非常典型的并发套路：**先无锁快速读（fast path），再在加锁后做一次“确认读”（double-check）**，用来同时满足 **性能** 和 **正确性**。

Spring 的单例缓存又是“三层结构”（一级 singletonObjects、二级 earlySingletonObjects、三级 singletonFactories），所以锁外/锁内都要分别再查一次，避免在你抢锁的这段时间里，别的线程已经把对象放进缓存，导致你重复创建早期引用/重复升级缓存，甚至把生命周期搞乱。

---

### **1）为什么**  **singletonObjects.get(beanName)** **要查两遍？**

#### **1.1 第一次：无锁快路径，省性能**

```
Object singletonObject = this.singletonObjects.get(beanName);
```

绝大多数情况下（Bean 已创建完成），直接从一级缓存拿到最终单例就返回。

如果这里就加锁，会导致所有单例读取都竞争同一把锁（synchronized (this.singletonObjects)），启动期/高并发获取 Bean 时非常伤。
#### **1.2 第二次：加锁后的“确认读”，保证正确性（Double-Check）**

``` java
synchronized (this.singletonObjects) {
  singletonObject = this.singletonObjects.get(beanName);
  ...
}
```

原因：**在你第一次无锁读到 null 到你进入 synchronized 之间，有时间窗口**。

别的线程可能已经完成了创建并把最终对象放进了 singletonObjects（一级缓存）。

如果你不在锁内再读一次，你会继续走“早期引用/工厂创建”逻辑，产生两个问题：

- **重复创建早期引用**：明明已经有最终对象了，你却又从 singletonFactory.getObject() 造一个 early reference（可能是代理对象），会造成“同名 Bean 出现多个不同实例引用”的风险。
    
- **破坏缓存升级顺序**：正常顺序是 singletonFactories → earlySingletonObjects → singletonObjects。别人已经升级到一级了，你这边还在从三级/二级折腾，会让状态机混乱（尤其是 AOP 提前暴露代理那种场景）。
    

所以锁内第二次读，是为了“以锁为边界”确认当前权威状态。

---

### **2）为什么**  **earlySingletonObjects.get(beanName)** **也要查两遍？**

同理，但这里更关键，因为 **early 引用的创建本身有副作用**（会触发 singletonFactory.getObject()）。
#### **2.1 第一次：无锁快路径**

```
singletonObject = this.earlySingletonObjects.get(beanName);
```

如果正在创建中（isSingletonCurrentlyInCreation），优先从二级缓存拿 early bean（解决循环依赖的核心）。无锁读取性能好。
#### **2.2 第二次：锁内确认，避免重复“从三级工厂生成早期引用”**

``` java
synchronized (this.singletonObjects) {
  singletonObject = this.earlySingletonObjects.get(beanName);
  if (singletonObject == null) {
    ObjectFactory<?> singletonFactory = this.singletonFactories.get(beanName);
    if (singletonFactory != null) {
      singletonObject = singletonFactory.getObject();
      this.earlySingletonObjects.put(beanName, singletonObject);
      this.singletonFactories.remove(beanName);
    }
  }
}
```

这里必须锁内再读一次 early cache，因为：

- 在你抢锁前，**另一个线程可能已经执行了** **singletonFactory.getObject()**，并把结果放进 earlySingletonObjects 了。
    
- singletonFactory.getObject() 可能会创建 **AOP 代理早期引用**（比如 getEarlyBeanReference），这是一次“不可重复且要一致”的动作：
    
    你不希望两个线程分别生成两个 early 引用（哪怕都长得像代理，也可能不是同一个对象实例）。
    

锁内确认读的目的就是：**保证 early 引用只会被提升一次**，且提升过程是原子的（生成 → put 二级 → remove 三级）。

---
### **3）为什么锁用的是** **singletonObjects** **这个 Map？**
你会注意到 synchronized 锁的是 this.singletonObjects，但里面同时操作了三张表。原因是 Spring 把这三层缓存当成一个整体状态机：
- 一级：最终单例
    
- 二级：提前暴露的单例引用
    
- 三级：提前暴露引用的工厂（用于延迟生成 early reference）
    

为了保证它们之间的“升级/迁移”一致性，必须用 **同一把全局锁**保护“跨 Map 的复合操作”，否则会出现：
- 线程 A 把三级移到二级
    
- 线程 B 同时把二级移到一级
    
    最终导致重复实例或丢失引用。
    
---
### **4）用一个具体竞态场景解释（不二次 get 会怎样）**

假设两个线程 T1/T2 都在拿 bean A（A 正在创建中）：

1. T1：无锁读 singletonObjects 为 null；读 earlySingletonObjects 为 null；准备进锁创建 early
    
2. **切换到 T2**：T2 抢到锁，执行 singletonFactory.getObject()，把 early A 放进 earlySingletonObjects，并移除 singletonFactories
    
3. 切回 T1：如果 T1 进锁后**不再读 earlySingletonObjects**，它会以为还是 null，然后去拿 singletonFactories.get()（可能已经被移除），要么拿不到导致返回 null，要么在别的实现里造成重复创建/状态错乱
    

所以锁内第二次读是为了在锁边界内看到“最新一致状态”。

---
### **5）小结（面试一句话）**
这段代码两次 get 是典型的 **double-check + 状态机一致性**：第一次无锁读走快路径，避免每次取 Bean 都加锁；如果可能处于创建中，则进入全局锁后再次确认一级/二级缓存状态，避免在并发窗口里被其他线程更新导致重复生成 early reference 或破坏三级→二级→一级的升级过程，从而保证循环依赖场景下的单例一致性与性能。
## 5. 总结

Spring的三级缓存机制是处理单例Bean循环依赖的重要手段。通过合理利用这个机制，可以增强应用的稳定性，但在设计Bean之间的依赖关系时，仍需尽量避免循环依赖的出现。
# 3. 原型 Bean
在 Spring 框架中，**原型 Bean（Prototype Bean）**是一种 Bean 作用域定义。它的主要特点是每次请求都会返回一个新的 Bean 实例。

### 1. 原型Bean的特性

- **每次创建新实例**：每当通过Spring容器请求一个原型Bean时，都会创建并返回一个新的实例，而不是共享一个单一实例。
- **不存储在单例缓存中**：原型Bean不会被存储在Spring的单例缓存中，因此其状态是独立的，修改一个实例的状态不会影响其他实例。

### 2. 原型Bean的定义

可以通过在Bean的定义中指定作用域为`prototype`来创建原型Bean：

```java
@Component
@Scope("prototype")
public class MyPrototypeBean {
    // Bean的属性和方法
}
```

### 3. 使用场景

原型Bean适用于以下场景：

- **需要状态独立的Bean**：当每个Bean实例的状态需要独立时，使用原型Bean非常合适。
- **需要频繁创建的Bean**：如果Bean的创建和销毁开销较小，并且需要频繁使用新实例，可以选择原型作用域。

### 4. 生命周期

原型Bean的生命周期与单例Bean有所不同：

- **初始化**：原型Bean的初始化是在每次请求时进行的。
- **销毁**：Spring容器不会管理原型Bean的销毁，因此需要开发者手动处理相关资源的释放（如关闭连接等）。
``` java
@PreDestroy  
public void destroy() {  
    System.out.println("ProtoBean destroyed: " + this);  
}
```

### 5. 注意事项

- **循环依赖**：原型Bean之间的循环依赖处理较为复杂，通常需要通过setter注入或其他方式来避免。
- **性能开销**：由于每次请求都要创建新实例，可能会导致性能开销，尤其在频繁请求的情况下。

### 总结

原型Bean是Spring中定义的一种作用域，适用于需要独立实例的情况。理解原型Bean的特性和生命周期，有助于合理设计和管理Spring应用中的Bean。


# 4. @Lazy 的作用
`@Lazy`注解在Spring中用于延迟加载Bean。它的主要功能是推迟Bean的实例化，直到实际需要时才创建。以下是`@Lazy`注解的原理及其工作机制的详细解释。

### 1. 使用场景

`@Lazy`注解适用于以下情况：

- **减少启动时间**：在应用启动时，某些Bean的创建可能会消耗较多资源，通过延迟加载可以提高启动速度。
- **延后依赖解析**：在注入点使用 `@Lazy` 可以推迟获取某个依赖，偶尔可作为打破直接依赖的权衡方案；它不能替代消除循环依赖的设计工作。

### 2. 原理

`@Lazy`注解的工作原理主要体现在以下几个方面：

#### 1) 注解的定义

在Spring中，`@Lazy`可以应用于类、构造函数、方法或字段。它的基本定义如下：

```java
@Target({ElementType.TYPE, ElementType.METHOD, ElementType.CONSTRUCTOR, ElementType.FIELD, ElementType.PARAMETER})
@Retention(RetentionPolicy.RUNTIME)
public @interface Lazy {
    boolean value() default true;
}
```

#### 2) 延迟加载的实现

需要区分两种用法：

1. **Bean 定义上的 `@Lazy`**：容器不在启动时预实例化该 Bean，而是在首次请求它时创建。
2. **注入点上的 `@Lazy`**：Spring 向依赖方注入一个可延迟解析的引用，首次使用时再获取目标 Bean。

懒初始化并不意味着“任何场景都会有代理”。例如，懒 Bean 若被非懒加载 singleton 直接依赖，为满足该 singleton 的依赖，容器仍可能在启动时创建它。

### 3. 示例

以下是一个使用`@Lazy`注解的示例：

```java
@Component
public class A {
    private final B b;

    @Autowired
    public A(@Lazy B b) {
        this.b = b;
    }
}

@Component
public class B {
    public B() {
        System.out.println("B is created");
    }
}
```

在上述代码中，`@Lazy` 标注的是 `A` 对 `B` 的**注入点**。创建 `A` 时可先注入延迟解析引用；当业务实际调用 `b` 时，容器才需要获取 `B`。

### 4. 小结

`@Lazy` 的主要用途是延迟 Bean 初始化或依赖解析，从而控制启动成本和依赖获取时机。它可以缓解某些创建阶段的依赖冲突，但不应替代循环依赖的设计治理。

# 6. Bean 生命周期
Spring Bean 的生命周期是指从 Bean 实例化到销毁的完整过程，由 Spring 容器管理。了解其生命周期有助于开发者更好地控制对象的行为和资源管理。

### **Spring Bean 生命周期的完整流程**

以下是 Spring 管理 Bean 的生命周期的详细步骤：

---

#### **1. Bean 实例化（Instantiation）**

- 容器先解析构造器参数，再调用构造器或工厂方法创建 Bean 实例。
- 构造器注入属于这一阶段；字段和 Setter 注入尚未发生。

---

#### **2. 设置属性（Populate Properties，依赖注入）**

- 容器解析并注入字段、Setter 等依赖。`@Autowired` 通常按类型解析，再结合 `@Qualifier`、`@Primary` 或参数名等规则消除歧义，不能简单概括为固定的“先 byType 再 byName”。
- 依赖注入的方式：
    1. 构造函数注入（**发生在实例化**）
    2. Setter 方法注入
    3. 字段注入（通过 `@Autowired` 等）

---

#### **3. 调用 Aware 接口方法**

- 如果 Bean 实现了以下 Aware 接口，Spring 容器会回调这些方法，以注入特定信息：
    - `BeanNameAware`：注入当前 Bean 的名称。
    - `BeanFactoryAware`：注入 BeanFactory 容器实例。
    - `ApplicationContextAware`：注入 ApplicationContext 容器实例。

---

#### **4. BeanPostProcessor（前置处理）**

- **作用：** 在初始化方法调用前，容器会调用所有注册的 `BeanPostProcessor` 的 `postProcessBeforeInitialization()` 方法。
- **常见应用：**
    - 修改 Bean 属性。
    - 替换或代理 Bean。

---

#### **5. 调用初始化方法**

- 初始化方法是开发者定义的钩子，用于在 Bean 初始化时执行自定义逻辑。
- **定义方式：**
    1. 在 XML 配置中指定 `init-method`。
    2. 使用注解 `@PostConstruct`（现代 Spring 使用 `jakarta.annotation.PostConstruct`）。
    3. 实现 `InitializingBean` 接口的 `afterPropertiesSet()` 方法。
  当三种回调同时存在时，常见执行顺序为 `@PostConstruct` → `afterPropertiesSet()` → 自定义 `init-method`；其实现仍受 BeanPostProcessor 协调，不应泛化为“优先级最高”。

---

#### **6. BeanPostProcessor（后置处理）**

- **作用：** 在初始化方法调用后，容器会调用所有 `BeanPostProcessor` 的 `postProcessAfterInitialization()` 方法。
- **常见用途：**
    - 创建代理对象（如 AOP 功能）。

---

#### **7. Bean 就绪（Ready for Use）**

- Bean 被容器管理，随时可供应用程序使用。

---

#### **8. Bean 销毁（Destruction）**

- 容器关闭时，Spring 会销毁所有单例作用域的 Bean。
- **销毁方法定义方式：**
    1. 在 XML 配置中指定 `destroy-method`。
    2. 使用注解 `@PreDestroy`。
    3. 实现 `DisposableBean` 接口的 `destroy()` 方法。

---

### **Spring Bean 生命周期的图示**

```
1. 实例化（Instantiation）、构造函数
     ↓
2. 属性设置（Populate Properties）、依赖注入（字段 / setter）
     ↓
3. 调用 Aware 接口（如 BeanNameAware）
     ↓
4. 前置处理（postProcessBeforeInitialization）
     ↓
5. 初始化方法（@PostConstruct/ afterPropertiesSet() / init-method）
     ↓
6. 后置处理（postProcessAfterInitialization/AOP）
     ↓
7. Bean 就绪（Ready for Use）
     ↓
8. 销毁（@PreDestroy / destroy-method）
```

---

### **Bean 生命周期中的扩展点**

开发者可以通过以下方式扩展或自定义 Bean 的生命周期：

1. **实现 Aware 接口**
    
    - 例如，通过实现 `ApplicationContextAware` 获取 Spring 容器实例。
2. **实现 InitializingBean 或 DisposableBean 接口**
    
    - `afterPropertiesSet()`：在初始化阶段执行自定义逻辑。
    - `destroy()`：在销毁阶段释放资源。
3. **使用 BeanPostProcessor**
    
    - 在 Bean 初始化前后插入逻辑。
4. **使用 @PostConstruct 和 @PreDestroy**
    
    - 定义初始化和销毁逻辑，推荐使用这两个注解，代码更加简洁且符合标准。

---

### **典型面试问题**

1. **Spring 是如何解决循环依赖的？**
    
    - **答：** 通过三级缓存（`singletonFactories`）提前暴露 Bean 的引用，允许未完全初始化的 Bean 被其他 Bean 使用。
2. **BeanPostProcessor 的作用是什么？能否举例？**
    
    - **答：** 在 Bean 初始化前后执行自定义逻辑，例如：
        - AOP 代理的实现。
        - 自定义日志记录。
3. **Bean 初始化方法的优先级？**
    
    - **答：**
        1. `@PostConstruct`
        2. `afterPropertiesSet()`（来自 `InitializingBean`）
        3. XML 或 `@Bean` 配置的 `init-method`（通常按此顺序执行）
4. **什么是 FactoryBean？和普通 Bean 有什么区别？**
    
    - **答：**
        - `FactoryBean` 是一个特殊的 Bean，其 `getObject()` 方法返回的是创建的对象，而非 `FactoryBean` 本身。

# 7. IoC 与 DI
### **IOC（Inversion of Control，控制反转）**

#### **什么是 IOC？**

- IOC 是一种设计原则，通过将对象的创建和依赖的管理交给外部容器（例如 Spring 容器），实现对象的解耦。
- 在传统编程中，对象主动创建它依赖的其他对象；而在 IOC 中，对象所需要的依赖由容器注入，从而实现控制权的反转。

---

#### **IOC 的核心思想**

- 控制反转的核心是 **谁控制谁** 和 **控制了什么**：
    1. **谁控制谁：** Spring 容器控制对象的创建和生命周期。
    2. **控制了什么：** 控制对象之间的依赖。
- **反转的是什么：**
    - 对象本身不再负责依赖的管理，而是由 Spring 容器管理，传统模式下由程序员手动控制的依赖被反转给容器。

---

#### **IOC 的实现方式**

1. **依赖查找（Dependency Lookup）**
    
    - 对象通过查找容器获取所需的依赖。
    - 示例：使用 `ApplicationContext.getBean()`。
2. **依赖注入（Dependency Injection，DI）**
    
    - 容器在运行时将对象的依赖自动注入给它。
    - DI 是 IOC 的一种实现方式，也是 Spring 的主要实现方式。

---

### DI（Dependency Injection，依赖注入）

#### **什么是 DI？**

- DI 是 IOC 的具体实现方法，指ta'm的是容器将对象的依赖（通常是其他对象）注入到该对象中，而不是让对象自己主动获取依赖。
- **目标：** 解耦对象之间的依赖关系，使代码更易于扩展、测试和维护。

---

#### **DI 的注入方式**

Spring 提供以下三种依赖注入方式：

1. **构造器注入**
    
    - 通过构造函数注入依赖。
    - 推荐用于 **强依赖** 场景。
    - 示例：
        
        ```java
        @Component
        public class Car {
            private final Engine engine;
        
            @Autowired
            public Car(Engine engine) {
                this.engine = engine;
            }
        }
        ```
        
2. **Setter 方法注入**
    
    - 通过 Setter 方法注入依赖。
    - 适合 **可选依赖** 场景。
    - 示例：
        
        ```java
        @Component
        public class Car {
            private Engine engine;
        
            @Autowired(required = false)
            public void setEngine(Engine engine) {
                this.engine = engine;
            }
        }
        ```
        
3. **字段注入**
    
    - 直接在字段上使用注解（如 `@Autowired`）。
    - 常用于简化代码，但会降低可测试性。
    - 示例：
        
        ```java
        @Component
        public class Car {
            @Autowired
            private Engine engine;
            
            @Autowired
		    private ObjectProvider<LoggerService> loggerProvider
        }
        ```
        

---

#### **DI 的底层实现**

- Spring 通过 **反射** 实现依赖注入：
    1. 容器解析配置文件或注解，创建 Bean 实例。
    2. 根据注入方式，通过构造器或 Setter 方法调用或直接反射设置字段。

---

### **IOC 和 DI 的关系**

1. **IOC 是一种思想，DI 是其实现方式。**
    
    - IOC 解决了控制权的转移问题，使对象不再主动管理依赖。
    - DI 是实现 IOC 的具体手段，容器通过注入的方式为对象提供依赖。
2. **IOC 是框架的基础，DI 是开发者的使用方法。**
    
    - 在 Spring 中，IOC 是整个框架的核心思想，DI 是开发者和容器交互的主要方式。

---

### **实际应用中的 IOC 和 DI**

#### **1. IOC 的应用场景**

- **解耦对象的创建和依赖管理：** 通过容器控制对象的生命周期，避免强耦合。
- **AOP（面向切面编程）：** 通过 IOC 容器动态注入切面逻辑。

#### **2. DI 的应用场景**

- **服务类依赖注入：** 为 Service 层注入 Repository 层。
- **配置注入：** 使用 `@Value` 或 `@ConfigurationProperties` 读取配置文件。
- **动态代理和测试：** DI 使得可以轻松替换依赖，从而方便进行单元测试。

---

### 常见问题

1. **IOC 和 DI 的区别是什么？**
    
    - **答：**
        - IOC 是一种思想，DI 是实现 IOC 的一种方式。
        - IOC 强调控制反转，DI 强调依赖关系的注入。
2. **构造器注入和 Setter 注入的区别？使用场景是什么？**
    
    - **答：**
        - 构造器注入：
            - 依赖在对象创建时提供。
            - 用于强依赖关系（必须有依赖对象）。
        - Setter 注入：
            - 依赖在对象创建后提供。
            - 用于可选依赖关系（依赖对象可有可无）。
3. **为什么推荐使用构造器注入而不是字段注入？**
    - **答：**
        - 构造器注入：
            1. 保证对象的不可变性（final 属性）。
            2. 便于单元测试。
        - 字段注入：
            - 隐式注入，降低可测试性和可维护性。

# 8. ApplicationContext
在 Spring 框架中，**`ApplicationContext`** 是 Spring IOC 容器的核心接口之一。它继承了 `BeanFactory`，并扩展了更多高级功能，如国际化支持、事件机制和 AOP 集成。

以下是对 **`ApplicationContext`** 的详细讲解，包括其功能、实现原理和源码解析。

---

### **1. 什么是 `ApplicationContext`？**

- **`ApplicationContext` 是 Spring 的高级 IOC 容器：**
    - 它负责加载 `BeanDefinition`，创建和管理 Bean。
    - 通过继承 `BeanFactory` 提供了基本的 IOC 容器功能。
    - 增强功能包括事件发布、资源加载、国际化和环境抽象等。

---

### **2. `ApplicationContext` 的主要功能**

#### **(1) IOC 容器功能**

- 提供 `getBean()` 方法从容器中获取 Bean。同时能创建Bean
- 支持单例、原型和其他作用域的 Bean。

#### **(2) 国际化支持**

- 提供 `MessageSource` 接口，用于支持多语言和国际化消息。

#### **(3) 事件发布和监听**

- 提供事件机制：
    - 发布事件：`publishEvent()`。
    - 监听事件：实现 `ApplicationListener` 接口。

#### **(4) 资源加载**

- 提供 `Resource` 接口，用于加载文件、URL 或类路径中的资源。
- 方法：`getResource()`。

#### **(5) 环境抽象**

- 通过 `Environment` 接口提供运行时环境的抽象，包括属性、配置文件和激活的环境。

---

### **3. `ApplicationContext` 的主要实现类**

| 实现类                                                    | 描述                               |
| ------------------------------------------------------ | -------------------------------- |
| **ClassPathXmlApplicationContext**                     | 从类路径下加载 XML 配置文件，适用于传统 XML 配置项目。 |
| **FileSystemXmlApplicationContext**                    | 从文件系统加载 XML 配置文件。                |
| **AnnotationConfigApplicationContext**                 | 支持基于注解的配置类，适用于现代化 Spring 项目。     |
| **AnnotationConfigServletWebServerApplicationContext** | Spring Boot 默认的 Web 应用容器。        |
| **GenericApplicationContext**                          | 通用实现类，可与其他上下文类型结合使用。             |

---

### **4. `ApplicationContext` 的初始化流程**

#### **代码示例**

```java
ApplicationContext context = new AnnotationConfigApplicationContext(AppConfig.class);
MyService myService = context.getBean(MyService.class);
```

#### 核心初始化流程

1. **创建容器实例**
    
    - 通过 `AnnotationConfigApplicationContext` 的构造方法初始化容器。
		``` java
		public AnnotationConfigApplicationContext(Class<?>... componentClasses) {  
		    this();  
		    this.register(componentClasses);  
		    this.refresh();  
		}
		```
2. **加载配置**
    
    - 调用 `register()` 方法注册配置类。
    - 解析注解 `@Component`、`@Bean` 等，生成 `BeanDefinition(包含Bean的定义信息:bean className,Bean scope等)`。
    - 添加到DefaultListableBeanFactory.BeanDefinitionMap<ClassName,BeanDefinition>
		``` java
		this.beanDefinitionMap.put(beanName, beanDefinition);  
		this.beanDefinitionNames.add(beanName);  
		this.removeManualSingletonName(beanName);
		```
3. **刷新容器**
    
    - 调用 `refresh()` 方法完成容器初始化。
4. **注册后置处理器**
    
    - 注册所有 `BeanPostProcessor` 和 `BeanFactoryPostProcessor`。
5. **实例化单例 Bean**
    
    - 调用 `preInstantiateSingletons()` 创建所有单例作用域的 Bean。

---

### **5. 源码剖析：`ApplicationContext` 的核心实现**

#### **(1) `refresh()` 方法**

- 入口：`AbstractApplicationContext#refresh()`
- 核心功能：
    1. **初始化 `BeanFactory`**
        - 加载配置，解析为 `BeanDefinition`。
    2. **调用 `BeanFactoryPostProcessor`**
        - 修改 Bean 的定义信息。
    3. **注册 `BeanPostProcessor`**
        - 提供扩展点，在 Bean 初始化前后执行自定义逻辑。
    4. **实例化单例 Bean**
        - 创建所有单例 Bean，并调用初始化方法。

完整的 `refresh()` 源码骨架和各阶段说明见后文「9. Spring refresh」。这里保留其在 `ApplicationContext` 中的职责，避免同一段启动流程在一篇笔记中重复维护。

---

#### **(2) `getBean()` 方法**

- 入口：`AbstractBeanFactory#getBean(String name)`
- ` AbstractBeanFactory.doGetBean()`
- `DefaultSingletonBeanRegistry.getSingleton()`
- 核心功能：
    1. **检查是否存在缓存实例**
        - 单例作用域的 Bean 存储在 `singletonObjects` 中。
    2. **创建 Bean**
        - 如果 Bean 未实例化，调用 `createBean()` 方法。
    3. **返回实例**
        - 返回单例对象或新创建的对象。

```java
@Override
public Object doGetBean(String name) {
    Object sharedInstance = getSingleton(name);
    if (sharedInstance == null) {
        sharedInstance = createBean(name, ...);
    }
    return sharedInstance;
}
```

---

### **6. `ApplicationContext` 的高级特性**

#### **(1) 事件机制**

- 通过 `ApplicationEventPublisher` 接口实现事件发布与监听。
- **示例：**
    
    ```java
    // 定义事件
    public class CustomEvent extends ApplicationEvent {
        public CustomEvent(Object source) {
            super(source);
        }
    }
    
    // 发布事件
    context.publishEvent(new CustomEvent("Hello World"));
    
    // 监听事件
    @Component
    public class CustomEventListener implements ApplicationListener<CustomEvent> {
        @Override
        public void onApplicationEvent(CustomEvent event) {
            System.out.println("Received event: " + event.getSource());
        }
    }
    ```
    

---

#### **(2) 多环境支持**

- 使用 `Environment` 接口管理配置文件。
- **示例：**
    
    ```java
    @PropertySource("classpath:application.properties")
    public class AppConfig {
        @Value("${app.name}")
        private String appName;
    }
    ```
    

---

#### **(3) 动态加载资源**

- 通过 `Resource` 接口加载文件、类路径、URL 等资源。
- **示例：**
    
    ```java
    Resource resource = context.getResource("classpath:application.properties");
    Properties properties = new Properties();
    properties.load(resource.getInputStream());
    ```
    

---

### **7. 面试常见问题**

#### **(1) `ApplicationContext` 和 `BeanFactory` 的区别？**

- `BeanFactory` 是 Spring 的核心容器，提供基本的 IOC 功能。
- `ApplicationContext` 是 `BeanFactory` 的增强版本，提供了事件、国际化、AOP 等高级功能。

#### **(2) 如何实现延迟加载 Bean？**

- 配置 `@Lazy` 注解，避免 Bean 在容器启动时立即初始化：
    
    ```java
    @Lazy
    @Component
    public class LazyBean {
        public LazyBean() {
            System.out.println("LazyBean Initialized");
        }
    }
    ```
    

#### **(3) 如何实现动态注册 Bean？**

- 使用 `GenericApplicationContext` 的 `registerBean()` 方法：
    
    ```java
    GenericApplicationContext context = new GenericApplicationContext();
    context.registerBean("myBean", MyBean.class);
    context.refresh();
    ```
    

---

### **总结**

1. **`ApplicationContext` 是 Spring 的核心容器接口，支持 Bean 管理、事件机制、资源加载等高级功能。**
2. **Spring Boot 默认使用 `AnnotationConfigServletWebServerApplicationContext`，加载注解配置类并启动 Web 容器。**
3. **源码级别理解：重点关注 `refresh()` 和 `getBean()` 方法，掌握容器初始化与 Bean 创建的流程。**

# 9. refresh()


---

### **代码逻辑解析**

```java
public void refresh() throws BeansException, IllegalStateException {
    synchronized (this.startupShutdownMonitor) {
        // 1. 预准备（设置启动时间、校验环境变量等）
        prepareRefresh();

        // 2. 创建并加载 BeanFactory（包括解析配置类、扫描 @Component）
        ConfigurableListableBeanFactory beanFactory = obtainFreshBeanFactory();

        // 3. 设置 BeanFactory 的各种属性（ClassLoader、Aware 支持等）
        prepareBeanFactory(beanFactory);

        // 4. 扩展点：允许子类进一步处理 BeanFactory
        postProcessBeanFactory(beanFactory);

        // 5. 调用 BeanFactoryPostProcessor（如解析 @Configuration、@Import）
        invokeBeanFactoryPostProcessors(beanFactory);

        // 6. 注册所有的 BeanPostProcessor（如 @Autowired、AOP）
        registerBeanPostProcessors(beanFactory);

        // 7. 初始化国际化 MessageSource（可选）
        initMessageSource();

        // 8. 初始化事件广播器 ApplicationEventMulticaster
        initApplicationEventMulticaster();

        // 9. 留给子类扩展，如 Web 环境下初始化 DispatcherServlet
        onRefresh();

        // 10. 注册所有事件监听器（包括 @EventListener）
        registerListeners();

        // 11. 完成所有非懒加载单例 Bean 的实例化（🔥 Bean 注入 + AOP 创建都在此步）
        finishBeanFactoryInitialization(beanFactory);

        // 12. 发布 ContextRefreshedEvent，标志容器启动完成
        finishRefresh();
    }
}
```

---

### **1. `prepareRefresh()`：准备环境**

- **主要任务：**
    
    - 清理上下文状态。
    - 初始化环境属性。
    - 验证环境配置的有效性。
- **底层实现：**
    
    ```java
    protected void prepareRefresh() {
        // 设置启动时间戳
        this.startupDate = System.currentTimeMillis();
    
        // 初始化环境属性（Environment）
        this.environment.validateRequiredProperties();
    
        // 初始化事件监听器集合
        this.earlyApplicationEvents = new LinkedHashSet<>();
    }
    ```
    
- **作用：**
    
    - 确保容器启动的基本信息和环境设置已准备好。

---

### **2. `obtainFreshBeanFactory()`：获取 BeanFactory**

- **主要任务：**
    
    - 加载或刷新 BeanDefinition 信息。
    - 创建 BeanFactory 容器，存储所有 Bean 定义。
    - 在这一步会触发 @Import → 调用 registerBeanDefinitions() 注册 AOP、事务增强器等
- **底层实现：**
    
    ```java
    protected ConfigurableListableBeanFactory obtainFreshBeanFactory() {
        refreshBeanFactory();
        return getBeanFactory();
    }
    ```
    
- **关键步骤：**
    
    1. **刷新 BeanFactory：**
        - 加载配置文件或注解，将 Bean 信息解析成 `BeanDefinition`。
``` java 
	最后调用
	private <T> void doRegisterBean(Class<T> beanClass, @Nullable String name,  
       @Nullable Class<? extends Annotation>[] qualifiers, @Nullable Supplier<T> supplier,  
       @Nullable BeanDefinitionCustomizer[] customizers) {  
  
    AnnotatedGenericBeanDefinition abd = new AnnotatedGenericBeanDefinition(beanClass);  
    if (this.conditionEvaluator.shouldSkip(abd.getMetadata())) {  
       return;  
    }  
  
    abd.setAttribute(ConfigurationClassUtils.CANDIDATE_ATTRIBUTE, Boolean.TRUE);  
    abd.setInstanceSupplier(supplier);  
    ScopeMetadata scopeMetadata = this.scopeMetadataResolver.resolveScopeMetadata(abd);  
    abd.setScope(scopeMetadata.getScopeName());  
    String beanName = (name != null ? name : this.beanNameGenerator.generateBeanName(abd, this.registry));  
  
    AnnotationConfigUtils.processCommonDefinitionAnnotations(abd);  
    if (qualifiers != null) {  
       for (Class<? extends Annotation> qualifier : qualifiers) {  
          if (Primary.class == qualifier) {  
             abd.setPrimary(true);  
          }  
          else if (Lazy.class == qualifier) {  
             abd.setLazyInit(true);  
          }  
          else {  
             abd.addQualifier(new AutowireCandidateQualifier(qualifier));  
          }  
       }  
    }  
    if (customizers != null) {  
       for (BeanDefinitionCustomizer customizer : customizers) {  
          customizer.customize(abd);  
       }  
    }  
  
    BeanDefinitionHolder definitionHolder = new BeanDefinitionHolder(abd, beanName);  
    definitionHolder = AnnotationConfigUtils.applyScopedProxyMode(scopeMetadata, definitionHolder, this.registry);  
    BeanDefinitionReaderUtils.registerBeanDefinition(definitionHolder, this.registry);  
}
```
    1. **返回 BeanFactory：**
        - `DefaultListableBeanFactory` 是默认实现类，负责存储和管理 `BeanDefinition`。

---

### **3. `prepareBeanFactory(beanFactory)`：设置 BeanFactory 属性**

- **主要任务：**
    
    - 为 BeanFactory 配置一些基础设置，包括注册默认 Bean 和内置处理器。
- **底层实现：**
    
    ```java
    protected void prepareBeanFactory(ConfigurableListableBeanFactory beanFactory) {
        // 设置类加载器
        beanFactory.setBeanClassLoader(getClassLoader());
    
        // 注册默认的环境 Bean
        beanFactory.registerSingleton("environment", getEnvironment());
        beanFactory.registerSingleton("systemProperties", getEnvironment().getSystemProperties());
        beanFactory.registerSingleton("systemEnvironment", getEnvironment().getSystemEnvironment());
    
        // 添加一些后置处理器
        beanFactory.addBeanPostProcessor(new ApplicationContextAwareProcessor(this));
    }
    ```
    
- **作用：**
    
    - 注册与容器相关的内置 Bean，例如环境配置（`environment`）和系统属性。
    - 添加基础的 BeanPostProcessor，例如 `ApplicationContextAwareProcessor`。

---

### **4. `invokeBeanFactoryPostProcessors(beanFactory)`：执行 BeanFactoryPostProcessor**

- **主要任务：**
    
    - 在所有 Bean 实例化之前，允许开发者修改 `BeanDefinition`。
    - 例如，解析 `@Configuration` 注解。
- **底层实现：**
    
    ```java
    protected void invokeBeanFactoryPostProcessors(ConfigurableListableBeanFactory beanFactory) {
        PostProcessorRegistrationDelegate.invokeBeanFactoryPostProcessors(beanFactory, getBeanFactoryPostProcessors());
    }
    ```
    
- **关键点：**
    
    1. **`BeanFactoryPostProcessor` 是扩展点：**
        - 它允许在 Bean 创建前修改 Bean 的定义信息。
    2. **常见实现类：**
        - `ConfigurationClassPostProcessor`：解析 `@Configuration` 和 `@Bean`。

---

### **5. `registerBeanPostProcessors(beanFactory)`：注册 BeanPostProcessor**

- **主要任务：**
    
    - 注册 `BeanPostProcessor`，为 Bean 实例化前后提供扩展逻辑。
- **底层实现：**
    
    ```java
    protected void registerBeanPostProcessors(ConfigurableListableBeanFactory beanFactory) {
        PostProcessorRegistrationDelegate.registerBeanPostProcessors(beanFactory, this);
    }
    ```
    
- **作用：**
    
    1. **`BeanPostProcessor` 是另一大扩展点：**
        - 在 Bean 初始化前后执行特定逻辑。
    2. **常见实现类：**
        - `AutowiredAnnotationBeanPostProcessor`：处理依赖注入。
        - `ProxyBeanPostProcessor`：处理 AOP 代理。

---

### **6. `finishBeanFactoryInitialization(beanFactory)`：初始化单例 Bean**

- **主要任务：**
    
    - 创建所有单例作用域的 Bean，并完成依赖注入和初始化操作。
    - 创建代理对象（AOP）
- **底层实现：**
    
    ```java
    protected void finishBeanFactoryInitialization(ConfigurableListableBeanFactory beanFactory) {
        // 初始化非懒加载的单例 Bean
        beanFactory.preInstantiateSingletons();
    }
    ```
    
- **关键步骤：**
    
    1. **实例化 Bean：**
        - 调用 `createBean()` 方法创建 Bean 实例。
    2. **依赖注入：**
        - 调用 `populateBean()` 方法注入依赖。
    3. **调用初始化方法：**
        - 执行 `@PostConstruct` 或 `InitializingBean#afterPropertiesSet()`。

---

### **底层关键类与接口**

1. **`ConfigurableListableBeanFactory`**
    
    - 管理 BeanDefinition 的核心接口，定义了 Bean 的加载、实例化和管理方法。
2. **`BeanFactoryPostProcessor`**
    
    - 在 Bean 实例化之前修改 BeanDefinition 的扩展点。
3. **`BeanPostProcessor`**
    
    - 在 Bean 实例化之后、初始化之前或之后进行操作的扩展点。
4. **`DefaultListableBeanFactory`**
    
    - Spring 中 BeanFactory 的默认实现类，支持所有功能。

---

### **总结：底层逻辑与扩展点**

- **这段代码的主要作用：**
    
    1. 准备 Spring 容器的运行环境。
    2. 加载和解析 Bean 的配置信息。
    3. 注册扩展点（`BeanFactoryPostProcessor` 和 `BeanPostProcessor`）。
    4. 创建所有单例作用域的 Bean。
- **核心扩展点：**
    
    1. `BeanFactoryPostProcessor`：修改 Bean 定义。
    2. `BeanPostProcessor`：扩展 Bean 初始化逻辑。

这段代码展示了 Spring 容器启动的核心流程。如果需要进一步探讨具体步骤（如 `@Autowired` 或 AOP 的实现），可以继续展开！

# 10. Bean Scope
在 Spring 框架中，**Bean 的范围（Scope）** 定义了 Spring 容器中 Bean 的生命周期和实例化规则。不同的范围控制 Bean 在容器中是否共享实例或根据请求创建新实例。

---

### **1. Spring 支持的 Bean Scope 类型**

| 范围            | 描述                                                        | 适用场景                     |
| --------------- | ----------------------------------------------------------- | ---------------------------- |
| **singleton**   | 默认范围，每个 Spring 容器中仅存在一个共享实例。            | 无状态 Bean，例如服务类。    |
| **prototype**   | 每次请求都会创建一个新的实例。                              | 有状态 Bean，例如配置对象。  |
| **request**     | 每个 HTTP 请求都会创建一个新的 Bean 实例，适用于 Web 应用。 | Web 应用中的请求范围数据。   |
| **session**     | 每个 HTTP 会话共享一个 Bean 实例，适用于 Web 应用。         | Web 应用中的会话范围数据。   |
| **application** | 整个 ServletContext 共享一个 Bean 实例，适用于 Web 应用。   | 应用级别的全局数据。         |
| **websocket**   | 每个 WebSocket 会话共享一个 Bean 实例，适用于 Web 应用。    | WebSocket 通信中的会话数据。 |

---

### **2. Bean Scope 使用方式**

#### **(1) 使用 `@Scope` 注解**

- Spring 支持在类或方法级别通过 `@Scope` 注解定义范围。

```java
@Component
@Scope("prototype") // 定义为原型作用域
public class PrototypeBean {
    public PrototypeBean() {
        System.out.println("PrototypeBean created");
    }
}
```

#### **(2) 在 XML 配置中定义**

- 可以通过 `<bean>` 标签的 `scope` 属性指定范围。

```xml
<bean id="myBean" class="com.example.MyBean" scope="singleton" />
```

---

### **3. Scope 类型的详细解析**

#### **(1) Singleton（默认）**

- **特点：**
    - Spring 容器中仅创建一个共享实例。
    - 默认范围。
- **生命周期：**
    - 在容器启动时创建 Bean。
    - 在容器关闭时销毁 Bean。
- **适用场景：**
    - 无状态的 Bean，例如服务类、DAO 层对象。

#### **(2) Prototype**

- **特点：**
    - 每次通过 `getBean()` 方法获取时都会创建一个新的实例。
    - 容器仅负责 Bean 的创建，不管理其生命周期。
- **生命周期：**
    - 每次请求时创建新实例，使用完后由调用者负责销毁。
- **适用场景：**
    - 有状态的 Bean，例如需要频繁创建和销毁的对象。

#### **(3) Request（Web 环境）**

- **特点：**
    - 每个 HTTP 请求都会创建一个新的 Bean 实例。
    - 生命周期与 HTTP 请求相同。
- **适用场景：**
    - Web 应用中针对单个请求的数据处理 Bean。

#### **(4) Session（Web 环境）**

- **特点：**
    - 每个 HTTP 会话共享一个 Bean 实例。
    - 生命周期与 HTTP 会话相同。
- **适用场景：**
    - Web 应用中针对用户会话的数据处理 Bean。

#### **(5) Application（Web 环境）**

- **特点：**
    - 整个 ServletContext 范围内共享一个实例。
    - 生命周期与 ServletContext 相同。
- **适用场景：**
    - 应用级全局资源。

#### **(6) WebSocket**

- **特点：**
    - 每个 WebSocket 会话共享一个实例。
    - 生命周期与 WebSocket 会话相同。
- **适用场景：**
    - WebSocket 通信。

---

### **4. Prototype 和 Singleton 的区别**

| **特性**         | **Singleton**                        | **Prototype**                    |
| ---------------- | ------------------------------------ | -------------------------------- |
| **实例数量**     | 容器中始终只有一个共享实例。         | 每次请求都会创建一个新的实例。   |
| **生命周期管理** | 由 Spring 容器管理，容器关闭时销毁。 | 不受容器管理，由调用者负责销毁。 |
| **适用场景**     | 无状态 Bean（例如服务类）。          | 有状态 Bean（例如配置对象）。    |

---

### **5. 配合 Scope 的代理模式**

当使用 `request` 或 `session` 范围时，可能会遇到作用域 Bean 注入到单例 Bean 中的场景，此时需要通过代理模式解决。

#### **方法：使用 `proxyMode` 属性**

- **代码示例：**
    
    ```java
    @Component
    @Scope(value = "request", proxyMode = ScopedProxyMode.TARGET_CLASS)
    public class RequestBean {
    }
    
    @Component
    public class SingletonBean {
        @Autowired
        private RequestBean requestBean; // 注入代理对象
    }
    ```
    
- **`proxyMode` 的作用：**
    
    - 通过代理对象延迟访问实际的作用域 Bean。

---

### **6. 源码分析**

#### **(1) Scope 的定义**

- `Scope` 注解通过 `@AliasFor` 链接到 `ConfigurableBeanFactory` 的范围常量：
    
    ```java
    public static final String SCOPE_SINGLETON = "singleton";
    public static final String SCOPE_PROTOTYPE = "prototype";
    ```
    

#### **(2) Bean 的作用域处理**

- 在 `AbstractBeanFactory#doGetBean()` 中，根据 Bean 的作用域创建实例。
- 单例处理：
    
    ```java
    if (isSingleton(beanName)) {
        return getSingleton(beanName, () -> createBean(beanName, mbd, args));
    }
    ```
    
- 原型处理：
    
    ```java
    if (isPrototype(beanName)) {
        return createBean(beanName, mbd, args);
    }
    ```
    

#### **(3) Web 环境中的作用域管理**

- 使用 `RequestScope`、`SessionScope` 等 Spring 内置作用域处理器。
- 注册作用域：
    
    ```java
    this.scopes.put("request", new RequestScope());
    this.scopes.put("session", new SessionScope());
    ```
    

---

### **7. 常见面试问题**

#### (1) 什么是 Spring Bean 的作用域？如何选择合适的 Scope？

- **答：** Bean 的作用域定义了 Bean 的生命周期和实例数量：
    - `singleton`：默认，适合无状态服务类。
    - `prototype`：需要频繁创建和销毁的 Bean。
    - `request`/`session`：适用于 Web 应用中的 HTTP 请求或会话数据。

#### **(2) 为什么 prototype Bean 不会被销毁？**

- **答：** Spring 容器仅负责 `prototype` Bean 的创建，生命周期由调用者管理。

#### **(3) 如何解决作用域 Bean 注入单例 Bean 的问题？**

- **答：** 使用 `ScopedProxyMode` 创建代理对象，实现延迟加载。

---

### **总结**

1. **Spring 支持多种 Bean 作用域，通过 `@Scope` 注解或 XML 配置进行定义。**
2. **单例（singleton）和原型（prototype）是最常用的作用域，其生命周期和管理方式差别显著。**
3. **Web 环境下的作用域（如 request、session）需要结合代理模式处理依赖注入问题。**
4. **深入理解 Spring 的作用域管理有助于优化内存使用和提升系统性能。**

如果需要进一步探讨某个作用域或结合实际场景分析，可以继续讨论！

# 11. Spring Profile 的原理

Spring Profile 是 Spring 框架提供的一种功能，用于在不同的环境（如开发、测试、生产）中激活不同的配置。它通过逻辑分组和条件激活机制，让开发者能够灵活地管理环境相关的 Bean 定义和配置。

---

### **1. Spring Profile 的基本概念**

#### **什么是 Profile？**

- Profile 是一个逻辑分组，Spring 可以根据当前激活的 Profile 加载对应的 Bean 或配置。
- 主要用于环境隔离，比如：
    - `dev`（开发环境）
    - `test`（测试环境）
    - `prod`（生产环境）

#### **核心功能：**

- 根据 Profile 激活特定的 Bean 定义。
- 加载特定的配置文件。
- 提供一种灵活的条件化 Bean 配置机制。

---

### **2. 使用 Profile 的方式**

#### **（1）基于注解的配置**

- 在 `@Configuration` 或 `@Component` 上使用 `@Profile` 注解。

```java
@Configuration
@Profile("dev")
public class DevConfig {
    @Bean
    public DataSource dataSource() {
        return new HikariDataSource(); // 开发环境的数据源配置
    }
}
```

#### **（2）基于 XML 的配置**

- 在 XML 中使用 `<beans>` 标签的 `profile` 属性。

```xml
<beans profile="dev">
    <bean id="dataSource" class="com.example.DevDataSource"/>
</beans>
```

#### **（3）激活 Profile 的方式**

- **通过环境变量：**
    - 设置 JVM 参数：`-Dspring.profiles.active=dev`
- **通过配置文件：**
    - 在 `application.properties` 中设置：
        
    ```properties
        spring.profiles.active=dev
    ```
        
- **通过代码：**
    
    ```java
    ConfigurableApplicationContext context = new AnnotationConfigApplicationContext();
    context.getEnvironment().setActiveProfiles("dev");
    context.register(AppConfig.class);
    context.refresh();
    ```
    

---

### **3. Profile 的底层实现原理**

#### **（1）Profile 的关键接口和类**

- **`Environment` 接口：**
    
    - `Environment` 是 Profile 功能的核心接口，用于管理当前激活的 Profile 和环境属性。
    - 关键方法：
        
        ```java
        String[] getActiveProfiles();
        void setActiveProfiles(String... profiles);
        ```
        
- **`AbstractEnvironment` 类：**
    
    - `Environment` 接口的默认实现类，维护所有激活的 Profile 和默认 Profile。
    - 关键字段：
        
        ```java
        private final Set<String> activeProfiles = new LinkedHashSet<>();
        private final Set<String> defaultProfiles = new LinkedHashSet<>(DEFAULT_PROFILES);
        ```
        

#### **（2）`@Profile` 注解的处理**

- **核心逻辑：**
    
    - Spring 在解析配置类或扫描组件时，会检查 `@Profile` 注解的值。
    - 如果当前环境中未激活该 Profile，则对应的 Bean 定义会被忽略。
- **源码解析：`ConfigurationClassParser`**
    
    - `@Profile` 注解的处理由 `ConfigurationClassParser` 类完成。
    - 逻辑代码：
        
        ```java
        if (!environment.acceptsProfiles(profileResolver.resolveSpecifiedProfiles(profileAnnotation))) {
            // 如果 Profile 不匹配，跳过此配置类
            return false;
        }
        ```
        

#### **（3）条件化 Bean 的注册**

- Spring 在注册 Bean 时，会检查 Profile 的匹配情况：
    - **方法入口：`AbstractApplicationContext#refresh()`**
        - 调用 `invokeBeanFactoryPostProcessors()`。
        - 在 `ConfigurationClassPostProcessor` 中解析配置类。
    - 如果 `@Profile` 注解的条件不满足，则对应的 `BeanDefinition` 不会注册到容器中。

---

### **4. Profile 与配置文件的集成**

#### **（1）加载不同环境的配置文件**

- Spring Boot 提供了基于 Profile 的配置文件机制：
    - `application.properties`：默认配置文件。
    - `application-dev.properties`：开发环境的配置文件。
    - `application-prod.properties`：生产环境的配置文件。

#### **（2）激活特定的 Profile 配置文件**

- **通过 `spring.profiles.active` 激活：**
    - 当 `spring.profiles.active=dev` 时，Spring 会优先加载 `application-dev.properties`。
- **加载顺序：**
    1. `application.properties` 总是加载。
    2. 根据激活的 Profile，加载对应的配置文件并覆盖默认配置。

---

### **5. Profile 的高级用法**

#### **（1）多个 Profile 的激活**

- 可以同时激活多个 Profile：
    
    ```properties
    spring.profiles.active=dev,test
    ```
    

#### **（2）默认 Profile**

- 如果未显式激活 Profile，Spring 会使用默认的 Profile。
- 设置默认 Profile 的方式：
    
    ```java
    ConfigurableApplicationContext context = new AnnotationConfigApplicationContext();
    context.getEnvironment().setDefaultProfiles("default");
    ```
    

#### **（3）条件注解的结合**

- 使用 `@Conditional` 和 `@Profile` 实现更灵活的条件加载：
    
    ```java
    @Configuration
    @ConditionalOnProperty(name = "env", havingValue = "dev")
    public class DevConfig {
        // 仅在满足条件时加载
    }
    ```
    

---

### **6. 源码解析总结**

#### **关键点：`AbstractEnvironment`**

- Profile 的管理由 `AbstractEnvironment` 负责：
    - **激活 Profile：**
        - 在 `AbstractApplicationContext#refresh()` 时，读取 `spring.profiles.active`。
    - **检查 Profile：**
        - 在 `ConfigurationClassParser` 中，根据 `@Profile` 的值匹配激活的 Profile。

#### **关键点：`BeanDefinition` 的筛选**

- Spring 在注册 Bean 时，会根据 Profile 条件过滤：
    - 如果 `@Profile` 的条件不满足，则对应的 `BeanDefinition` 会被标记为不可用状态。

---

### **7. 常见面试问题**

#### **（1）什么是 Spring Profile？它的作用是什么？**

- Spring Profile 是一种逻辑分组机制，用于在不同环境中激活不同的配置和 Bean 定义。
- 作用包括：
    - 环境隔离（如开发、测试、生产）。
    - 条件化 Bean 加载。

#### **（2）如何在 Spring Boot 中使用 Profile？**

- 在 `application.properties` 中配置：
    
    ```properties
    spring.profiles.active=dev
    ```
    

#### **（3）默认 Profile 是什么？如何设置？**

- 默认 Profile 是当未激活任何 Profile 时使用的配置。
- 可以通过 `setDefaultProfiles()` 方法设置。

---

### **8. 总结**

- **Spring Profile 是一种环境管理工具**，通过条件化加载配置文件和 Bean，为多环境开发提供便利。
- **核心机制：**
    1. `Environment` 接口负责管理激活的 Profile。
    2. 在容器初始化时，根据 `@Profile` 注解或 XML 配置条件注册 Bean。
    3. Spring Boot 通过 `application.properties` 文件和 `spring.profiles.active` 实现自动化环境配置。


# 12. 依赖注入原理

Spring 中的 **依赖注入（DI, Dependency Injection）** 是 IOC（控制反转）思想的具体实现方式，它将对象的依赖管理交给 Spring 容器，在运行时自动注入所需的依赖对象。依赖注入的实现基于反射、`BeanDefinition` 和 `BeanFactory` 的功能。

---

### **1. 依赖注入的基本原理**

#### **核心思想**

- **传统方式：** 对象在代码中自己创建其依赖。
- **依赖注入：** 对象的依赖由外部容器（Spring）负责管理和提供。
- **优点：**
    - 解耦对象之间的依赖。
    - 方便单元测试。
    - 提高代码的可扩展性和维护性。

#### **依赖注入的触发点**

依赖注入通常在以下场景下触发：

1. Bean 的实例化过程。
2. 注解（如 `@Autowired`、`@Resource`）。
3. 构造器、Setter 方法、字段等。

---

### **2. 依赖注入的流程**

以下是依赖注入的执行流程，结合 Spring 源码逐步解析：

#### **（1）BeanDefinition 的解析**

- Spring 通过配置文件（XML、注解或 Java 配置类）加载 Bean 的元信息。
- **核心接口：`BeanDefinition`**
    - 保存 Bean 的类名、作用域、依赖属性等信息。
    - **主要实现：`GenericBeanDefinition`**。

```java
<bean id="userService" class="com.example.UserService">
    <property name="userRepository" ref="userRepository"/>
</bean>
```

#### **（2）容器创建 Bean**

- 容器在调用 `DefaultListableBeanFactory#getBean()` 时开始创建 Bean。
- 如果依赖其他 Bean，会先解析依赖。

#### **（3）依赖解析**

- 调用 `DefaultListableBeanFactory#resolveDependency()` 方法解析依赖。
- 根据依赖的类型（构造器、Setter 或字段），决定注入的方式。

#### **（4）依赖注入**

- 通过 `AbstractAutowireCapableBeanFactory` 的 `populateBean()` 方法进行注入。
- 使用反射为字段、Setter 方法或构造器参数赋值。

#### **（5）后置处理**

- 在依赖注入完成后，Spring 调用 `BeanPostProcessor` 扩展点对 Bean 进行额外处理（如代理增强）。

---

### **3. 依赖注入的实现方式**

Spring 提供了多种依赖注入方式，不同方式的底层实现略有不同。

#### **（1）构造器注入**

- 使用构造器注入依赖。
- **实现：`ConstructorResolver`**
    - 在 `AbstractAutowireCapableBeanFactory` 中调用 `autowireConstructor()`。
    - 通过 `ConstructorResolver` 查找匹配的构造器。

**示例代码：**

```java
@Component
public class UserService {
    private final UserRepository userRepository;

    @Autowired
    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }
}
```

**源码解析：**

```java
protected BeanWrapper autowireConstructor(...) {
    Constructor<?> constructorToUse = determineConstructor();
    Object[] argsToUse = resolveConstructorArguments();
    return instantiateClass(constructorToUse, argsToUse);
}
```

#### **（2）Setter 方法注入**

- 使用 Setter 方法注入依赖。
- **实现：`populateBean()`**
    - 遍历所有属性，调用对应的 Setter 方法注入。

**示例代码：**

```java
@Component
public class UserService {
    private UserRepository userRepository;

    @Autowired
    public void setUserRepository(UserRepository userRepository) {
        this.userRepository = userRepository;
    }
}
```

**源码解析：**

```java
protected void populateBean(String beanName, RootBeanDefinition mbd, BeanWrapper bw) {
    PropertyValues pvs = mbd.getPropertyValues();
    applyPropertyValues(beanName, mbd, bw, pvs);
}
```

#### **（3）字段注入**

- 直接通过字段注入依赖。
- **实现：`AutowiredAnnotationBeanPostProcessor`**
    - 扫描 Bean 的字段，查找 `@Autowired` 注解并注入。

**示例代码：**

```java
@Component
public class UserService {
    @Autowired
    private UserRepository userRepository;
}
```

**源码解析：**

```java
public PropertyValues postProcessProperties(PropertyValues pvs, Object bean, String beanName) {
    InjectionMetadata metadata = findAutowiringMetadata(beanName, bean.getClass(), pvs);
    metadata.inject(bean, beanName, pvs);
    return pvs;
}
```

---

### **4. 注解驱动的依赖注入**

Spring 提供了多种注解来支持依赖注入：

#### **（1）@Autowired**

- 默认按类型注入。
- 支持通过 `@Qualifier` 指定 Bean 名称。

#### **（2）@Resource**

- 属于 Jakarta Common Annotations（Spring 6+ 使用 `jakarta.annotation.Resource`），默认按名称注入，找不到名称时再按类型匹配。

#### **（3）@Inject**

- 来自 JSR-330 标准，与 `@Autowired` 类似。

---

### **5. 源码深度解析**

以下是依赖注入的核心逻辑，结合 `populateBean()` 方法展开分析：

#### **（1）入口方法：`populateBean()`**

- 负责解析依赖并注入属性。

```java
protected void populateBean(String beanName, RootBeanDefinition mbd, BeanWrapper bw) {
    PropertyValues pvs = mbd.getPropertyValues();

    // 自动装配逻辑
    if (mbd.isAutowireCandidate()) {
        pvs = autowireByType(beanName, mbd, bw, new MutablePropertyValues(pvs));
    }

    // 应用属性值
    applyPropertyValues(beanName, mbd, bw, pvs);
}
```

#### **（2）依赖解析：`resolveDependency()`**

- 解析依赖的核心方法。

```java
public Object resolveDependency(DependencyDescriptor descriptor, String beanName, Set<String> autowiredBeanNames, TypeConverter typeConverter) {
    // 获取所有候选 Bean
    Map<String, Object> matchingBeans = findAutowireCandidates(descriptor);

    // 选择匹配的 Bean
    Object resolved = determinePrimaryCandidate(matchingBeans, descriptor);
    return resolved;
}
```

#### **（3）注解处理：`AutowiredAnnotationBeanPostProcessor`**

- 在 Bean 初始化过程中，扫描 `@Autowired` 并注入。

```java
@Override
public PropertyValues postProcessProperties(PropertyValues pvs, Object bean, String beanName) {
    InjectionMetadata metadata = findAutowiringMetadata(beanName, bean.getClass(), pvs);
    metadata.inject(bean, beanName, pvs);
    return pvs;
}
```

---

### **6. 常见面试问题**

#### **（1）什么是依赖注入？它如何实现解耦？**

- **答：**
    - 依赖注入是将对象所需的依赖从外部注入到对象中。
    - 通过将依赖的管理交给 Spring 容器，消除了对象之间的直接依赖关系，实现解耦。

#### **（2）Spring 如何实现依赖注入？**

- **答：**
    - Spring 使用 `populateBean()` 方法注入依赖，通过反射为字段、构造器或 Setter 方法赋值。
    - 注解处理通过 `AutowiredAnnotationBeanPostProcessor` 实现。

#### **（3）构造器注入和 Setter 注入的区别？**

- **答：**
    - 构造器注入：依赖在对象创建时提供，适用于强依赖。
    - Setter 注入：依赖在对象创建后提供，适用于可选依赖。

#### **（4）Spring 如何解决循环依赖？**

- **答：**
    - 对于单例 Bean，Spring 使用 **三级缓存** 提前暴露 Bean 的引用，允许未完全初始化的 Bean 被依赖。

---

### **7. 总结**

1. **依赖注入是 Spring 框架的核心特性，基于 IOC 的思想实现。**
2. **核心流程：**
    - 解析依赖：`resolveDependency()`
    - 注入依赖：`populateBean()`
    - 处理注解：`AutowiredAnnotationBeanPostProcessor`
3. **扩展点：**
    - 支持构造器注入、Setter 注入和字段注入。
    - 注解支持：`@Autowired`、`@Resource`、`@Inject`。


# 13. Spring 注册 Bean 的整体详细源码解析

Spring 的 Bean 注册是指将 Bean 定义信息（`BeanDefinition`）加载到 IOC 容器（`BeanFactory`）中，并根据需要创建实例的过程。以下是从启动到 Bean 注册的全流程和核心源码解析。

---

### **1. Bean 注册的总体流程**

1. **扫描或加载配置：** Spring 从 XML 配置、Java 配置类或注解扫描中加载 `BeanDefinition`。
2. **生成 BeanDefinition：** 将类的元信息（类名、作用域、依赖等）封装为 `BeanDefinition` 对象。
3. **注册 BeanDefinition：** 将 `BeanDefinition` 注册到容器中的 `BeanDefinitionRegistry`。
4. **实例化 Bean：** 在容器启动时或第一次获取时，根据 `BeanDefinition` 创建 Bean 实例。

---

### **2. 核心入口点**

- Bean 注册的入口点是 `DefaultListableBeanFactory`，这是 Spring 默认的 BeanFactory 实现类，负责管理 `BeanDefinition` 和 Bean 的实例化。

---

### **3. 注册 Bean 的详细流程**

#### **Step 1: 加载配置或扫描注解**

**配置方式：**

1. **XML 配置文件**：
    
    - 使用 `XmlBeanDefinitionReader` 读取并解析 XML 文件，生成 `BeanDefinition`。
    
    ```xml
    <bean id="userService" class="com.example.UserService" />
    ```
    
2. **注解配置：`@Component` 或 `@Bean`**：
    
    - 使用 `ClassPathBeanDefinitionScanner` 扫描指定包路径中的类，生成 `BeanDefinition`。
    
    ```java
    @Component
    public class UserService {}
    ```
    
3. **Java 配置类：`@Configuration` 和 `@Bean`**：
    
    - 通过 `ConfigurationClassPostProcessor` 解析配置类的方法，生成 `BeanDefinition`。

#### **Step 2: 生成 BeanDefinition**

- **`BeanDefinition` 是 Spring 容器对 Bean 的抽象描述。**
    - 包含类名、作用域、是否懒加载、构造器参数等信息。

```java
public interface BeanDefinition {
    String SCOPE_SINGLETON = ConfigurableBeanFactory.SCOPE_SINGLETON;
    String SCOPE_PROTOTYPE = ConfigurableBeanFactory.SCOPE_PROTOTYPE;

    void setBeanClassName(String beanClassName);
    String getBeanClassName();
}
```

---

#### **Step 3: 注册 BeanDefinition**

**核心接口：`BeanDefinitionRegistry`**

- **职责：** 注册和管理 `BeanDefinition`。
- **主要方法：**
    
    ```java
    void registerBeanDefinition(String beanName, BeanDefinition beanDefinition);
    boolean containsBeanDefinition(String beanName);
    BeanDefinition getBeanDefinition(String beanName);
    ```
    

**实现类：`DefaultListableBeanFactory`**

- **`registerBeanDefinition` 方法：**
    
    - 将 `BeanDefinition` 存入 `beanDefinitionMap`（核心容器 Map）。
    
    ```java
    public void registerBeanDefinition(String beanName, BeanDefinition beanDefinition) throws BeanDefinitionStoreException {
        this.beanDefinitionMap.put(beanName, beanDefinition);
    }
    ```
    

---

#### **Step 4: 初始化单例 Bean**

- 单例作用域的 Bean 会在容器启动时完成实例化。
- **核心方法：`preInstantiateSingletons()`**
    - 遍历 `beanDefinitionMap` 中所有非懒加载的单例 Bean，并调用 `getBean()` 实例化。

```java
protected void preInstantiateSingletons() {
    for (String beanName : this.beanDefinitionNames) {
        getBean(beanName);
    }
}
```

---

### **4. 源码剖析**

#### **（1）解析配置或扫描注解**

- **XML 配置文件**：
    
    - 通过 `XmlBeanDefinitionReader` 的 `doLoadBeanDefinitions()` 方法解析 XML 文件。
    
    ```java
    public int doLoadBeanDefinitions(InputSource inputSource, Resource resource) throws BeanDefinitionStoreException {
        Document doc = doLoadDocument(inputSource, resource);
        return registerBeanDefinitions(doc, resource);
    }
    ```
    
- **注解扫描**：
    
    - 通过 `ClassPathBeanDefinitionScanner` 扫描指定包路径。
    
    ```java
    public Set<BeanDefinition> findCandidateComponents(String basePackage) {
        Set<BeanDefinition> candidates = new LinkedHashSet<>();
        for (Resource resource : resourcePatternResolver.getResources(basePackage)) {
            MetadataReader metadataReader = metadataReaderFactory.getMetadataReader(resource);
            if (isCandidateComponent(metadataReader)) {
                candidates.add(new ScannedGenericBeanDefinition(metadataReader));
            }
        }
        return candidates;
    }
    ```
    

#### **（2）注册 BeanDefinition**

- **`DefaultListableBeanFactory#registerBeanDefinition()`**
    
    ```java
    public void registerBeanDefinition(String beanName, BeanDefinition beanDefinition) {
        this.beanDefinitionMap.put(beanName, beanDefinition);
    }
    ```
    

#### **（3）实例化 Bean**

- **调用链：**
    
    - `DefaultListableBeanFactory#getBean()` → `AbstractBeanFactory#doGetBean()` → `createBean()`。
- **`AbstractAutowireCapableBeanFactory#createBean()`**
    
    ```java
    protected Object createBean(String beanName, RootBeanDefinition mbd, Object[] args) {
        // 1. 实例化 Bean
        Object beanInstance = createBeanInstance(beanName, mbd, args);
    
        // 2. 属性注入
        populateBean(beanName, mbd, beanWrapper);
    
        // 3. 初始化方法调用
        Object exposedObject = initializeBean(beanName, beanInstance, mbd);
    
        return exposedObject;
    }
    ```
    

#### **（4）属性注入**

- **`populateBean()` 方法：**
    - 调用 `AutowiredAnnotationBeanPostProcessor` 处理 `@Autowired` 注解。

```java
protected void populateBean(String beanName, RootBeanDefinition mbd, BeanWrapper bw) {
    PropertyValues pvs = mbd.getPropertyValues();
    applyPropertyValues(beanName, mbd, bw, pvs);
}
```

---

### **5. Bean 注册的关键数据结构**

1. **`beanDefinitionMap`**
    
    - 存储所有 `BeanDefinition`，键为 Bean 名称。
    
    ```java
    private final Map<String, BeanDefinition> beanDefinitionMap = new ConcurrentHashMap<>();
    ```
    
2. **`singletonObjects`**
    
    - 存储单例 Bean 实例。
    
    ```java
    private final Map<String, Object> singletonObjects = new ConcurrentHashMap<>();
    ```
    
3. **`beanDefinitionNames`**
    
    - 存储注册的 Bean 名称列表。
    
    ```java
    private final List<String> beanDefinitionNames = new ArrayList<>();
    ```
    

---

### **6. 流程图**

```plaintext
+----------------------------+
| XML/注解/配置类加载        |
+----------------------------+
             ↓
+----------------------------+
| BeanDefinition 生成        |
+----------------------------+
             ↓
+----------------------------+
| BeanDefinition 注册到容器   |
| (beanDefinitionMap)        |
+----------------------------+
             ↓
+----------------------------+
| Bean 初始化                |
| 调用 createBean()          |
+----------------------------+
             ↓
+----------------------------+
| 依赖注入、初始化方法调用    |
+----------------------------+
             ↓
+----------------------------+
| Bean 完成实例化            |
+----------------------------+
```

---

### **7. 常见面试问题**

#### **（1）BeanDefinition 是什么？有什么作用？**

- **答：**
    - `BeanDefinition` 是对 Bean 的抽象描述，包含 Bean 的类名、作用域、依赖属性等元信息。
    - 它是 Spring 容器加载、解析和注册 Bean 的核心数据结构。

#### **（2）Spring 如何注册一个 Bean？**

- **答：**
    1. 解析配置（XML、注解、Java 配置类）。
    2. 将解析的元信息封装为 `BeanDefinition`。
    3. 调用 `BeanDefinitionRegistry.registerBeanDefinition()` 注册到容器。

#### **（3）单例 Bean 是什么时候实例化的？**

- **答：**
    - 默认情况下，单例 Bean 会在容器启动时通过 `preInstantiateSingletons()` 方法实例化。

---

### **8. 总结**

1. **Spring 的 Bean 注册分为配置加载、生成 BeanDefinition、注册 BeanDefinition 和实例化四个阶段。**
2. **核心实现：**
    - `DefaultListableBeanFactory`：Bean 注册和管理的核心实现。
    - `BeanDefinition`：描述 Bean 的元信息。
3. **关键扩展点：**
    - 自定义 `BeanFactoryPostProcessor` 和 `BeanPostProcessor`。

如果需要更详细的某个阶段源码分析或实际应用场景的解读，可以继续探讨！


# 14. Spring 的单例 Bean 是线程安全的吗

### **Spring 的单例 Bean 是线程安全的吗？**

**简短回答：Spring 的单例（Singleton）Bean 本身** 不是 **线程安全的。**  
Spring 容器管理的单例 Bean 是 **无状态的**，在大多数情况下是线程安全的；但如果 Bean 设计为 **有状态**（即包含可变字段），则需要额外处理以保证线程安全。

---

## **1. Spring 单例 Bean 的特性**

- **Spring 中的单例模式** 指的是 **Spring 容器中的单例（Singleton Scope）**，即 Spring 仅在 IOC 容器内 **创建一个 Bean 实例**，并在整个应用生命周期内 **共享** 这个实例。
- **它不是 Java 语言中的单例模式（`Singleton` 设计模式），而是 Spring 容器级别的单例。**

```java
@Component
public class MySingletonBean {
    public void doSomething() {
        System.out.println("Executing business logic...");
    }
}
```

**这个 `MySingletonBean` 作为 Spring 容器的单例 Bean，所有线程都共享同一个实例**。

---

## **2. Spring 单例 Bean 线程安全分析**

### **情况 1：无状态 Bean（线程安全 ✅）**

- **无状态 Bean** 是指 **不包含可变字段**，即每个方法调用时不依赖或修改共享状态。
- 例如，**Service 层、DAO 层的 Bean** 通常是无状态的，因而是线程安全的。

```java
@Component
public class StatelessService {
    public String process(String input) {
        return "Processed: " + input;
    }
}
```

- **线程安全分析：**
    - 这个 `StatelessService` 没有成员变量，每个线程调用 `process()` 方法时不会影响其他线程。
    - 这种 Bean **是线程安全的**，不需要额外同步机制。

---

### **情况 2：有状态 Bean（线程不安全 ❌）**

- **有状态 Bean** 是指 **包含可变字段（实例变量）**，且这些字段可能在多个线程间共享和修改。
- 例如，以下 Bean 维护了一个 `count` 变量：

```java
@Component
public class StatefulService {
    private int count = 0;

    public void increment() {
        count++;
        System.out.println("Count: " + count);
    }
}
```

- **线程安全分析：**
    - `count` 变量在多个线程之间共享，如果多个线程同时调用 `increment()`，可能会发生 **竞态条件**（Race Condition）。
    - **并发问题示例：**
        - 线程 A 读取 `count = 5`，线程 B 也读取 `count = 5`。
        - 线程 A 递增 `count++`，得到 `count = 6`。
        - 线程 B 也递增 `count++`，但由于它最初读到 `count = 5`，它的结果也是 `count = 6`（而不是 `7`）。
        - **最终结果出错，发生数据竞争。**

---

## **3. 如何保证线程安全？（解决方案）**

### **方法 1：使用 `ThreadLocal`（每个线程独立变量）**

`ThreadLocal` 可以为每个线程提供独立变量，避免多线程共享同一个状态。

```java
@Component
public class ThreadLocalService {
    private final ThreadLocal<Integer> threadLocalCount = ThreadLocal.withInitial(() -> 0);

    public void increment() {
        try {
            threadLocalCount.set(threadLocalCount.get() + 1);
            System.out.println("ThreadLocal Count: " + threadLocalCount.get());
        } finally {
            threadLocalCount.remove(); // 在线程池复用线程时必须清理
        }
    }
}
```

**优点：** ✅ 线程独立，每个线程的 `threadLocalCount` 变量不会相互影响。  
**适用于：** 线程隔离的数据，如用户请求上下文、事务管理等；在线程池中必须在任务结束时 `remove()`，否则可能残留上下文或造成内存泄漏。

---

### **方法 2：按需获取 prototype Bean**

Spring 提供 `@Scope("prototype")` 作用域，每次 `getBean()` 调用都会返回新的实例，从而避免多个线程共享同一个实例。

```java
@Component
@Scope("prototype")
public class PrototypeService {
    private int count = 0;

    public void increment() {
        count++;
        System.out.println("Prototype Count: " + count);
    }
}
```

`prototype` 表示每次由容器解析该 Bean 时创建新实例，不等于“每个线程一个实例”。若 prototype 直接注入 singleton，注入只发生一次，singleton 仍会持有同一个 prototype 实例；需要反复获取新对象时，应注入 `ObjectProvider<PrototypeService>` 或使用 scoped proxy。

**优点：** ✅ 适用于短生命周期、有状态的临时对象。
**缺点：** ❌ 需要自行管理销毁；不自动解决线程隔离或 singleton 中的共享问题。

---

### **方法 3：使用 `synchronized` 关键字**

如果有状态 Bean 必须在多线程环境中使用，可以通过 `synchronized` 关键字来保证线程安全。

```java
@Component
public class SynchronizedService {
    private int count = 0;

    public synchronized void increment() {
        count++;
        System.out.println("Synchronized Count: " + count);
    }
}
```

**优点：** ✅ 线程安全，避免竞态条件。  
**缺点：** ❌ 影响性能，多个线程会阻塞等待。

---

### **方法 4：使用 `ConcurrentHashMap` 代替普通 `HashMap`**

如果 Bean 需要存储共享数据，建议使用 `ConcurrentHashMap` 代替普通 `HashMap`。

```java
@Component
public class ConcurrentService {
    private Map<String, String> cache = new ConcurrentHashMap<>();

    public void put(String key, String value) {
        cache.put(key, value);
    }

    public String get(String key) {
        return cache.get(key);
    }
}
```

**优点：** ✅ 高效的并发读写，避免 `synchronized` 过多的锁竞争。  
**适用于：** 需要共享数据的缓存服务。

---

## **4. 什么时候需要考虑线程安全？**

| **场景**                           | **是否需要线程安全？** | **推荐方案**                            |
| ---------------------------------- | ---------------------- | --------------------------------------- |
| **Controller 层**（`@Controller`） | ⭕ 取决于是否持有可变状态 | 保持无状态；不要把请求数据存到实例字段 |
| **Service 层**（`@Service`）       | ⭕ 取决于是否持有可变状态 | 避免实例变量；必要时选用并发容器或显式同步 |
| **Repository 层**（`@Repository`） | ⭕ 取决于实现与资源类型   | 保持无状态；不要共享非线程安全的持久化资源 |
| **存储共享数据的 Bean**            | ✅ 需要线程安全         | 1. `ConcurrentHashMap`2. `synchronized` |

---

## **5. 结论**

1. **Spring 的 singleton 只表示“容器中通常共享同一个实例”，并不保证线程安全**；无状态 Bean 往往天然线程安全，有可变共享状态时则需要自行设计并发控制。
2. **如果 Bean 维护了可变状态（如成员变量），那么它在多线程环境下就不是线程安全的，需要采取措施**：
    - ✅ **使用 `ThreadLocal` 进行线程隔离**
    - ✅ **在确实需要短生命周期对象时按需获取 prototype Bean，并明确其生命周期**
    - ✅ **使用 `synchronized` 或 `Lock` 保证并发安全**
    - ✅ **使用 `ConcurrentHashMap` 代替 `HashMap` 进行共享数据存储**
3. **一般情况下，Spring 的 Service 和 Repository 层是无状态的，因此不需要额外的线程安全措施**。

如果 Bean 需要存储和修改全局数据，就必须考虑线程安全问题！希望这个解析能帮到你 😃。



# 15. Spring事务失效
在默认的 **Spring AOP 代理模式** 下，声明式事务依赖 AOP 代理；调用未经过代理、事务属性不匹配或事务管理器选择错误时，可能导致事务不符合预期。若使用 AspectJ 事务模式，织入边界不同，本节的“自调用绕过代理”结论不直接适用。
``` 
@Configuration + @EnableTransactionManagement
        ↓
注册 AOP 代理生成器 + 注册事务拦截器（TransactionInterceptor）
        ↓
Bean 创建时（通过 BeanPostProcessor）扫描 @Transactional
        ↓
为匹配的 Bean 创建代理对象（替换原始对象）
        ↓
你调用方法 → 实际调用代理 → 触发 TransactionInterceptor（拦截器） → 控制事务
```

### **1. 事务失效的常见场景**

---

| **事务失效场景**                     | **原因**                                                                                                                                                                              | **解决方案**                                                                                                                                                |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **（1）自调用问题（this.method()）** | Spring 事务基于代理，如果在同一个类中调用事务方法，代理不会生效。                                                                                                                     | 1. 通过 `AopContext.currentProxy()` 调用代理对象。2. 使用 `ApplicationContext.getBean()` 获取代理对象。                                                     |
| **（2）事务方法不可被代理拦截**       | JDK 接口代理只能拦截接口中的 `public` 方法；类代理不能覆盖 `private`、`final` 方法。Spring 6 起类代理默认也可处理 `protected` 和包可见方法，但版本和代理类型会影响结果。 | 事务边界优先放在 `public` 的具体类方法上；不要依赖 `private`/`final` 方法的事务注解。 |
| **（3）异常未被捕获**                | 事务只对 **运行时异常（RuntimeException）或 Error** 生效，**CheckedException 不会触发回滚**。- CheckedException 通常表示“外部问题” → 比如文件找不到、远程调用失败，不一定代表业务失败 | 1. 手动抛出 `RuntimeException`（throw new RuntimeException(new IOException())）。2. 使用 `rollbackFor = Exception.class` 让 `@Transactional` 回滚所有异常。 |
| **（4）事务方法被 final`修饰**       | CGLIB 代理模式下，`final` 方法无法被子类重写，因此事务不会生效。                                                                                                                      | **移除 final 修饰符**，让 Spring 能够动态代理该方法。                                                                                                       |
| **（5）事务管理器没有正确配置**      | 事务管理器可能没有正确配置，如使用 `@Transactional` 但 `DataSourceTransactionManager` 没有生效。                                                                                      | 1. 确保 `@EnableTransactionManagement` 生效。2. 检查 `@Transactional` 是否正确标注在类或方法上。                                                            |
| **（6）不同的 TransactionManager**   | 事务方法 A 使用 `DataSourceTransactionManager`，事务方法 B 使用 `JpaTransactionManager`，事务不会共用。                                                                               | 确保所有相关事务使用相同的 `TransactionManager`。                                                                                                           |
| **（7）多线程导致事务失效**          | Spring 事务是 **线程绑定的**，但如果事务方法在 **新线程** 中执行，事务上下文不会传播。                                                                                                | 1. **使用 @TransactionalEventListener 监听异步任务**。2. **避免在事务方法中使用 @Async**。                                                                  |
| **（8）事务注解位置与代理模式不一致** | 接口、类和方法都可声明 `@Transactional`；但接口注解在 AspectJ 等场景存在识别边界，且 JDK 代理只拦截接口的 `public` 方法。 | 优先标注在具体类的 `public` 方法上，并统一团队约定。 |
| **（9）误解传播行为** | `REQUIRES_NEW` 会挂起外层并开启独立事务，内外提交/回滚相互独立；这不是“回滚失效”，而是事务边界不同。 | 按业务原子性选择 `REQUIRED`、`REQUIRES_NEW` 或 `NESTED`，并评估连接池与锁竞争。 |

---

### **2. 事务失效的详细源码剖析**

以下是 Spring 事务失效的关键源码解析：

#### **（1）自调用导致事务失效**

```java
@Service
public class OrderService {

    @Transactional
    public void createOrder() {
        System.out.println("创建订单...");
        this.createPayment(); // 事务不会生效
    }

    @Transactional
    public void createPayment() {
        System.out.println("创建支付记录...");
        throw new RuntimeException("支付失败");
    }
}
```

**为什么事务失效？**

- `this.createPayment()` 是 **普通方法调用**，不会触发 AOP 代理，因此 `@Transactional` 不会生效。

**解决方案 1：使用 `AopContext.currentProxy()`**

```java
public void createOrder() {
    System.out.println("创建订单...");
    OrderService proxy = (OrderService) AopContext.currentProxy();
    proxy.createPayment(); // 事务生效
}
```

**解决方案 2：通过 Spring 容器获取代理对象**

```java
@Autowired
private ApplicationContext context;

public void createOrder() {
    System.out.println("创建订单...");
    OrderService proxy = context.getBean(OrderService.class);
    proxy.createPayment(); // 事务生效
}
```

---

#### **（2）非 `public` 方法事务失效**

```java
@Service
public class UserService {
    
    @Transactional
    private void updateUser() {
        System.out.println("更新用户信息...");
    }
}
```

**为什么事务失效？**

- `private` 方法无法被类代理覆盖；若使用 JDK 接口代理，事务方法还必须是接口中声明的 `public` 方法。Spring 6 的类代理虽默认支持 `protected` 和包可见方法，但为了避免代理类型和版本差异，业务事务边界仍建议使用 `public` 方法。

**解决方案：**

- **把方法改为 `public`**

```java
@Transactional
public void updateUser() {
    System.out.println("更新用户信息...");
}
```

---

#### **（3）异常未触发回滚**

```java
@Service
public class PaymentService {

    @Transactional
    public void processPayment() throws Exception {
        throw new Exception("支付失败"); // 受检异常不会回滚
    }
}
```

**为什么事务失效？**

- Spring 只会对 **`RuntimeException`（运行时异常）** 进行回滚，**受检异常 `Exception` 不会触发回滚**。

**解决方案 1：手动抛出 `RuntimeException`**

```java
@Transactional
public void processPayment() {
    throw new RuntimeException("支付失败");
}
```

**解决方案 2：使用 `rollbackFor = Exception.class`**

```java
@Transactional(rollbackFor = Exception.class)
public void processPayment() throws Exception {
    throw new Exception("支付失败"); // 现在事务会回滚
}
```

---

#### **（4）多线程导致事务失效**

```java
@Service
public class ReportService {

    @Transactional
    @Async
    public void generateReport() {
        System.out.println("生成报表...");
        throw new RuntimeException("报表生成失败");
    }
}
```

**为什么事务失效？**

- `@Async` **会在新线程中执行**，而 Spring 事务是**线程绑定的**，事务上下文不会传播到新线程。

**解决方案 1：手动获取事务**

```java
@Autowired
private PlatformTransactionManager transactionManager;

public void generateReport() {
    DefaultTransactionDefinition def = new DefaultTransactionDefinition();
    TransactionStatus status = transactionManager.getTransaction(def);
    try {
        // 业务逻辑
        transactionManager.commit(status);
    } catch (Exception e) {
        transactionManager.rollback(status);
    }
}
```

**解决方案 2：避免 `@Async` 与 `@Transactional` 一起使用**

- 让异步任务在事务完成后执行。

---

### **3. 事务失效的 Debug 方法**

如果遇到事务失效问题，可以通过以下方式进行排查：

#### **（1）检查是否是 Spring 代理**

```java
System.out.println(AopUtils.isAopProxy(myService)); // true: 说明事务生效
```

#### **（2）启用 Spring 事务日志**

在 `application.properties` 中开启事务日志：

```properties
logging.level.org.springframework.transaction=DEBUG
logging.level.org.springframework.jdbc.datasource.DataSourceTransactionManager=DEBUG
```

启动后，可以看到 Spring 事务的执行流程。

---

### **4. 结论**

| **事务失效场景**             | **原因**                         | **解决方案**                                  |
| ---------------------------- | -------------------------------- | --------------------------------------------- |
| `this.method()` 调用事务方法 | 代理失效                         | 使用 `AopContext.currentProxy()` 获取代理对象 |
| `private` 方法               | AOP 只拦截 `public` 方法         | 改成 `public` 方法                            |
| `CheckedException` 不回滚    | Spring 只回滚 `RuntimeException` | `rollbackFor = Exception.class`               |
| `@Async` 事务失效            | 事务上下文不能跨线程             | 避免 `@Async`，或手动管理事务                 |

如果你在项目中遇到事务失效的问题，可以按照这些步骤进行排查和优化。

# 16. Spring推断构造方法
### **Spring 如何推断构造方法？**

Spring 在创建 Bean 时会解析构造器，但“选择参数最多的构造器”不是通用规则。是否能走构造器注入还取决于 BeanDefinition 中是否指定了构造参数、是否存在 `@Autowired` 候选，以及候选参数能否从容器解析。

---

## **1. Spring 推断构造方法的策略**

Spring 在 **实例化 Bean** 时，主要使用 **`ConstructorResolver`** 进行构造方法解析。推断逻辑如下：

1. **如果只有一个构造方法（无论是否带参数）**
    
    - 直接使用该构造方法。
2. **只有一个 `required = true` 的 `@Autowired` 构造器**

    - 使用该构造器；它的依赖都必须能满足。
3. **有多个 `@Autowired(required = false)` 构造器**
    
    - 它们都是候选；Spring 选择“可满足依赖数最多”的那个。若没有候选可满足，才会退回默认/无参构造器（若存在）。
4. **多个构造器都没有 `@Autowired`**
    
    - Spring 不会因为参数更多而自动选择其中一个；存在默认/无参构造器时通常使用它。没有可用默认构造器时，应显式标注要注入的构造器，避免依赖于内部解析细节。

---

## **2. 源码分析：Spring 如何推断构造方法？**

`ConstructorResolver#autowireConstructor()` 的真实实现还要处理显式构造参数、参数名匹配、类型转换和歧义检测。以下是帮助理解决策边界的伪代码，并非 Spring 源码：

```text
if (只有一个构造器) {
    使用它;
} else if (存在一个 required = true 的 @Autowired 构造器) {
    使用它，所有参数都必须可解析;
} else if (存在多个 required = false 的 @Autowired 构造器) {
    选择可解析参数最多的候选;
} else if (存在默认/无参构造器) {
    使用默认/无参构造器;
} else {
    报出构造器歧义或参数无法解析的异常;
}
```

---

## **3. 具体案例分析**

### **（1）只有一个无参构造方法**

如果类只有一个无参构造方法，Spring **自动使用它**：

```java
@Component
public class UserService {
    public UserService() {
        System.out.println("UserService 无参构造方法被调用");
    }
}
```

**Spring 会推断并调用该无参构造方法。**

---

### **（2）多个构造方法，Spring 选择 `@Autowired` 标注的构造方法**

如果类有多个构造方法，Spring **优先使用带 `@Autowired` 的构造方法**：

```java
@Component
public class OrderService {
    private final UserService userService;

    public OrderService() {
        System.out.println("OrderService 无参构造方法");
        this.userService = null;
    }

    @Autowired
    public OrderService(UserService userService) {
        System.out.println("OrderService 带 UserService 的构造方法");
        this.userService = userService;
    }
}
```

**Spring 选择有 `@Autowired` 的构造方法**

```
OrderService 带 UserService 的构造方法
```

---

### **（3）多个构造方法都没有 `@Autowired` 时，使用默认构造方法**

当存在默认/无参构造器时，Spring 使用它，而不会仅按参数数量猜测：

```java
@Component
public class ProductService {
    private final UserService userService;
    private final OrderService orderService;

    public ProductService() {
        System.out.println("ProductService 无参构造方法");
        this.userService = null;
        this.orderService = null;
    }

    public ProductService(UserService userService) {
        System.out.println("ProductService 单参数构造方法");
        this.userService = userService;
        this.orderService = null;
    }

    public ProductService(UserService userService, OrderService orderService) {
        System.out.println("ProductService 双参数构造方法");
        this.userService = userService;
        this.orderService = orderService;
    }
}
```

**Spring 选择无参构造方法；若希望注入依赖，应在目标构造器上显式标注 `@Autowired`。**

```
ProductService 无参构造方法
```

---

### **（4）使用 `@Primary` 指定首选 Bean**

如果 `ProductService` 依赖 `UserService`，但 `UserService` 有多个实现，我们可以用 `@Primary` 让 Spring 选择 **默认实现**：

```java
@Component
@Primary
public class DefaultUserService extends UserService {}

@Component
public class VIPUserService extends UserService {}
```

**Spring 自动选择 `DefaultUserService` 作为 `UserService` 的依赖。**

---

### **（5）手动指定 `@Bean` 方式**

如果 Bean 是通过 `@Bean` 方式定义，Spring 也能推断：

```java
@Configuration
public class AppConfig {
    @Bean
    public ProductService productService(UserService userService, OrderService orderService) {
        return new ProductService(userService, orderService);
    }
}
```

这里调用的是配置类中的 `productService(...)` 工厂方法；方法参数由 Spring 注入，`new ProductService(...)` 明确决定了使用哪个构造器，不存在“再次推断参数最多构造器”。

---

## **4. `@Transactional` 与构造器选择**

事务代理在目标对象创建完成后再包装 Bean，不会改变目标 Bean 的构造器选择：

```java
@Service
@Transactional
public class PaymentService {
    private final OrderService orderService;

    @Autowired
    public PaymentService(OrderService orderService) {
        this.orderService = orderService;
    }
}
```

代理类型会影响哪些业务方法可被事务拦截，但不应被当作构造器推断规则的一部分。

---

## **5. 总结**

| **场景**                        | **Spring 选择的构造方法**               |
| ------------------------------- | --------------------------------------- |
| 只有一个构造方法                | 直接使用该构造方法                      |
| 有 `@Autowired` 的构造方法      | **优先使用 `@Autowired`** 标注的方法    |
| 多个构造方法且均未标注          | 使用默认/无参构造器（若存在）；否则显式标注目标构造器 |
| 有 `@Bean` 配置方法             | 由工厂方法直接创建；工厂方法参数由 Spring 注入          |
| **CGLIB 代理（事务等）**        | 在目标对象创建后包装，不改变构造器选择                  |

### **最佳实践**

✅ **推荐始终使用构造器注入**，避免字段注入：

```java
@Component
public class MyService {
    private final DependencyA dependencyA;
    private final DependencyB dependencyB;

    @Autowired
    public MyService(DependencyA dependencyA, DependencyB dependencyB) {
        this.dependencyA = dependencyA;
        this.dependencyB = dependencyB;
    }
}
```

✅ **如果有多个构造方法，推荐显式标注 `@Autowired` 以提高可读性**：

```java
@Autowired
public MyService(DependencyA dependencyA, DependencyB dependencyB) {
    this.dependencyA = dependencyA;
    this.dependencyB = dependencyB;
}
```

❌ **不要使用字段注入**

```java
@Autowired
private DependencyA dependencyA;  // ❌ 不推荐
```

❌ **不要使用 `final` 修饰 `@Transactional` 的类**

```java
@Transactional
public final class PaymentService {}  // ❌ 不推荐
```

---

**总结：**

- **Spring 通过 `ConstructorResolver` 自动推断构造方法。**
- **单构造器无需 `@Autowired`；它会被用于构造器注入。**
- **多个构造器时，使用 `@Autowired` 明确选择，或保留默认构造器。**
- **“参数最多”只适用于多个非必需 `@Autowired` 候选之间的比较。**
- **事务或 AOP 代理不改变目标 Bean 的构造器选择。**

以上内容可作为排查入口；复杂边界以实际 Spring 版本与配置为准。

# 17. 为什么不推荐使用字段注入
### **为什么不要使用字段注入（Field Injection）？**

在 Spring 开发中，尽管 **字段注入（Field Injection）** 是一种简单快捷的方式，但通常 **不推荐** 使用，而是推荐使用 **构造器注入（Constructor Injection）**。下面详细解释 **为什么不推荐字段注入**，并对比 **不同的依赖注入方式**。

---

## **1. 依赖注入的三种方式**

在 Spring 中，依赖注入主要有三种方式：

### **（1）字段注入（Field Injection） ❌**

使用 `@Autowired` 直接标注在字段上：

```java
@Component
public class FieldInjectionService {
    @Autowired
    private UserRepository userRepository; // 直接注入
}
```

**主要代价：**

- 必需依赖没有体现在构造器签名中，读者无法仅从 API 看出对象的完整前置条件。
- 无法将依赖声明为 `final`，也不便于在不启动容器时直接构造对象。
- 单元测试仍可通过反射或 Mockito 注入，但测试更依赖框架行为，意图不如构造器注入清晰。

---

### **（2）Setter 方法注入（Setter Injection） 🟡**

通过 `@Autowired` 注解标注 Setter 方法：

```java
@Component
public class SetterInjectionService {
    private UserRepository userRepository;

    @Autowired
    public void setUserRepository(UserRepository userRepository) {
        this.userRepository = userRepository;
    }
}
```

**优点：**

- 适用于**可选依赖**（依赖可能为空）。
- 适合框架在初始化阶段注入可选依赖；是否允许运行时替换应由类的 API 和封装策略决定。

**缺点：**

- 依赖无法天然声明为构造后不可变；若 Setter 对外暴露，才可能被外部重新赋值。
- 对象可在依赖尚未设置时被构造出来，因此需要明确可选性与使用时机。

---

### **（3）构造器注入（Constructor Injection） ✅**

通过构造器传入依赖：

```java
@Component
public class ConstructorInjectionService {
    private final UserRepository userRepository;

    @Autowired
    public ConstructorInjectionService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }
}
```

**优点：**

- **强制依赖注入**，在对象创建时就确保依赖已被正确提供。
- **支持 `final` 关键字**，使依赖不可变，提高安全性。
- **易于测试**，可以通过手动创建实例并传递 Mock 依赖。
- **适用于依赖倒置原则（DIP）**，符合面向对象设计原则。

---

## **2. 为什么不要使用字段注入？**

### **（1）必需依赖不显式**

**问题：**

- 私有字段本身仍受封装保护；问题在于依赖没有通过构造器 API 明确声明。
- 类在 Spring 外部仍可被创建，但需要借助反射或测试工具设置依赖，不如构造器注入直接。

**示例：**

```java
@Component
public class UserService {
    @Autowired
    private UserRepository userRepository;
}
```

在 `UserService` 之外，无法手动创建这个类，因为它的 `userRepository` 需要由 Spring 注入。

---

### **（2）不支持 `final` 关键字，依赖不安全**

构造器注入允许 `final` 修饰依赖字段，保证其不可变性，而字段注入不能使用 `final`。

**构造器注入**

```java
@Component
public class UserService {
    private final UserRepository userRepository;

    @Autowired
    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }
}
```

✅ `userRepository` 是 `final`，保证了不变性。

**字段注入**

```java
@Component
public class UserService {
    @Autowired
    private UserRepository userRepository;
}
```

❌ `userRepository` **无法加 `final`**，因此无法用语言级不可变性表达“创建后不替换依赖”。这不等同于必然产生线程安全问题；线程安全仍取决于对象是否共享可变状态以及并发访问方式。

---

### **（3）无法在构造器中进行依赖检查**

Spring 容器启动时，**构造器注入可以强制依赖注入**，确保所有必需的依赖都被提供。

**错误示例（字段注入）**

```java
@Component
public class UserService {
    @Autowired
    private UserRepository userRepository;

    public void processUser() {
        userRepository.save(); // ⚠️ 如果 `userRepository` 没有正确注入，会抛出 `NullPointerException`
    }
}
```

**正确示例（构造器注入）**

```java
@Component
public class UserService {
    private final UserRepository userRepository;

    @Autowired
    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    public void processUser() {
        userRepository.save(); // ✅ 依赖在对象创建时已被注入，保证了安全性
    }
}
```

✅ **避免 `NullPointerException`，保证在运行前就有所有必要的依赖。**

---

### **（4）不利于单元测试**

**字段注入的测试问题**

```java
@Component
public class UserService {
    @Autowired
    private UserRepository userRepository;
}
```

在单元测试中可以 Mock `userRepository`，但依赖注入由 Mockito 的反射规则隐式完成：

```java
@ExtendWith(MockitoExtension.class)
public class UserServiceTest {

    @InjectMocks
    private UserService userService;

    @Mock
    private UserRepository userRepository;

    @Test
    void testUserService() {
        userService.processUser(); // Mockito 可注入字段，但构造器注入的依赖更显式
    }
}
```

---

**构造器注入的测试**

```java
@ExtendWith(MockitoExtension.class)
public class UserServiceTest {

    private UserService userService;

    @Mock
    private UserRepository userRepository;

    @BeforeEach
    void setup() {
        userService = new UserService(userRepository);
    }

    @Test
    void testUserService() {
        userService.processUser(); // ✅ 依赖已正确注入
    }
}
```

✅ **手动创建实例，不依赖 Spring 容器，方便测试。**

---

### **（5）设计表达更弱**

字段注入并不天然违反 SRP、DIP 或 OCP；这些原则取决于职责划分和依赖方向。构造器注入的优势是把依赖显式写进 API，更容易发现依赖过多、保持必需依赖不可变，并在测试中直接替换实现。

---

## **3. 什么时候可以使用字段注入？**

虽然字段注入不推荐，但在某些 **特殊场景** 下，它是可接受的：

1. **测试代码**
    - 仅用于 **简单的集成测试**，不影响代码质量。
2. **Spring 内部组件**
    
    - 如 `@Configuration` 类、Spring `Filter` 或 `Controller`，因为它们主要受 Spring 管理。
    
    ```java
    @Component
    public class MyFilter implements Filter {
        @Autowired
        private MyService myService;
    }
    ```
    
3. **临时/小型项目**
    - 如果项目较小，且不需要进行单元测试，使用字段注入可以减少代码量，但不推荐长期使用。

---

## **4. 结论**

| **注入方式**    | **优点**                       | **缺点**                         | **推荐度**       |
| --------------- | ------------------------------ | -------------------------------- | ---------------- |
| **字段注入**    | 代码简短 | 必需依赖不显式、不能使用 `final`、脱离容器构造不便 | ❌ 不推荐 |
| **Setter 注入** | 适合可选依赖 | 需明确对象何时可用，通常不适合必需依赖 | 🟡 适用于少数情况 |
| **构造器注入**  | 必需依赖显式、可使用 `final`、易于测试 | 依赖过多时会暴露设计需要拆分 | ✅ 推荐 |

**最佳实践：使用构造器注入，避免字段注入。**

# 18. Spring AOP 的工作原理

Spring AOP 主要依赖 **动态代理** 实现方法增强，使用 **JDK 动态代理** 或 **CGLIB 代理** 来生成代理对象，并在调用目标方法前后执行切面逻辑。

> 本节只建立代理与通知链的基础模型；多个切面的排序、`@Around` 的精确嵌套和代理边界请以 [[Spring深度解析|《Spring深度解析》]] 的 AOP 章节为准。下方源码均为理解调用链的示意，不等同于特定 Spring 版本的完整源码。

---

### **1. 代理对象的创建**

Spring AOP 在容器启动时，会扫描所有 `@Aspect` 定义的切面，并为匹配的目标对象 **创建代理对象**。

- **如果目标对象实现了接口** → 使用 **JDK 动态代理**（`Proxy.newProxyInstance()`）。
- **如果目标对象没有接口** → 使用 **CGLIB 代理**（通过子类继承实现）。

核心类：

- **`ProxyFactory`**：创建代理对象
- **`AdvisedSupport`**：存储切面信息
- **`CglibAopProxy` / `JdkDynamicAopProxy`**：执行代理逻辑

---

### **2. 方法调用拦截**

代理对象会按拦截器链处理调用。以单个切面同时包含各种通知为例，可以将顺序理解为：

1. `@Around` 的 `proceed()` 前逻辑（若存在）包裹整个调用；
2. `@Before`；
3. 目标方法；正常返回时执行 `@AfterReturning`，抛出异常时执行 `@AfterThrowing`；
4. `@After` 在 finally 语义下执行；
5. 回到 `@Around` 的 `proceed()` 后逻辑，再返回或继续抛出异常。

**调用链**

1. `JdkDynamicAopProxy.invoke() / CglibAopProxy.intercept()`
2. **`ReflectiveMethodInvocation.proceed()`**
3. **执行 `Advisor` 列表中的增强方法**
4. **调用 `MethodInterceptor` 进行增强**
5. **最终执行目标方法**

---

### **3. 关键源码解析**

#### **（1）代理对象创建**

**入口：`AnnotationAwareAspectJAutoProxyCreator`**

```java
public Object postProcessAfterInitialization(Object bean, String beanName) {
    if (isEligibleForProxying(bean)) {
        return wrapIfNecessary(bean, beanName);
    }
    return bean;
}
```

- 这里会检查 Bean 是否匹配切面逻辑，符合的话就会 **创建代理对象**。

---

#### **（2）方法拦截**

**入口：`JdkDynamicAopProxy.invoke()`**

```java
@Override
public Object invoke(Object proxy, Method method, Object[] args) throws Throwable {
    List<Object> chain = this.advised.getInterceptorsAndDynamicInterceptionAdvice(method);
    if (chain.isEmpty()) {
        return method.invoke(target, args);
    }
    return new ReflectiveMethodInvocation(target, method, args, chain).proceed();
}
```

- 获取所有拦截器（`Advisor`）。
- 通过 **责任链模式** 调用拦截器并最终执行目标方法。

---

#### **（3）执行增强逻辑**

**入口：`ReflectiveMethodInvocation.proceed()`**

```java
@Override
public Object proceed() throws Throwable {
    if (this.currentInterceptorIndex == this.interceptorsAndDynamicMethodMatchers.size() - 1) {
        return this.method.invoke(this.target, this.arguments);
    }
    MethodInterceptor interceptor = this.interceptorsAndDynamicMethodMatchers.get(++this.currentInterceptorIndex);
    return interceptor.invoke(this);
}
```

- 递归调用所有增强逻辑。
- 最终执行 `this.method.invoke(target, args)` 调用目标方法。

---

### **4. 总结**

1. **Spring 在启动时扫描 `@Aspect`，解析 `@Pointcut`、`@Around`、`@Before`、`@After` 等增强逻辑。**
2. **对匹配的 Bean 生成代理对象**（JDK 动态代理或 CGLIB）。
3. **代理对象拦截方法调用**，按 **拦截器链** 执行增强逻辑。
4. **调用目标方法后继续执行后置增强（`@After`、`@AfterReturning`、`@AfterThrowing`）。**
5. **最终返回结果给调用者。**

Spring AOP 的核心是**代理模式 + 责任链模式**：通过动态代理实现无侵入的切面增强。

# 19. Spring 事务原理（进阶入口）

> 本节只用于建立事务调用链的全局认知。传播行为的精细语义、多数据源、异步边界、隔离级别和最终一致性，以 [[Spring深度解析|《Spring深度解析》]] 的「事务」章节为准；基础排障则回看本文「15. Spring事务失效」。
## 1. Spring 事务到底是什么
Spring 事务的本质是：Spring 通过 AOP（代理 + 拦截器链）把“开启事务/提交/回滚”的控制逻辑织入到方法调用边界；数据库事务仍由底层数据库实现（如 MySQL InnoDB），Spring 负责正确地获取连接、设置事务属性、在方法前后调用 commit/rollback，并在执行完毕后清理线程上下文与释放连接。以下默认讨论代理模式；该模式下调用必须经过 Spring 生成的代理对象，AspectJ 模式的织入边界不同。
## 2. 核心组件与职责划分
### 2.1 PlatformTransactionManager（事务管理器：真正干活的人）
常见实现：DataSourceTransactionManager（JDBC/MyBatis）、JpaTransactionManager（JPA/Hibernate）。职责：getTransaction() 创建或加入事务；commit() 提交；rollback() 回滚。
### 2.2 TransactionDefinition（事务定义：配置载体）
由 @Transactional 解析而来：传播行为、隔离级别、超时、只读、回滚规则等。
### 2.3 TransactionStatus（事务状态：运行态载体）
记录事务是否新建、是否 rollback-only、是否已完成、是否有保存点（NESTED）等。
### 2.4 TransactionInterceptor（事务拦截器：AOP 入口）
围绕目标方法执行“开启/执行/提交/回滚”模板逻辑，并基于回滚规则决策 commit/rollback。
### 2.5 TransactionSynchronizationManager（线程级上下文：关键）
基于 ThreadLocal 绑定 Connection/资源与事务同步回调；保证同线程 DAO 共享同一连接与事务。
## 3. @Transactional 如何从注解变成可执行的事务逻辑
@EnableTransactionManagement 会注册 TransactionInterceptor 与对应 Advisor（切点 + 通知）；容器启动时自动代理创建器扫描 Advisor，发现 Bean 方法匹配事务切点就创建代理；调用经过代理进入 TransactionInterceptor 执行事务模板。必要条件：Spring 管理的 Bean、经过代理调用且满足拦截条件。实践中建议将事务放在 public 服务方法上；JDK 代理要求接口方法为 public，Spring 6 的类代理还支持 protected/package-private 方法。
## 4. 一次事务调用的完整执行链路（按时序拆解）
进入代理→读取事务属性→getTransaction()（创建/加入）→执行目标方法→正常 commit/异常 rollback→清理线程绑定与释放连接→触发事务同步回调（afterCommit/afterCompletion）。
## 5. 源码阅读入口

基础文只保留调用链：`TransactionInterceptor` 委托 `TransactionAspectSupport` 执行事务模板；`AbstractPlatformTransactionManager` 处理传播、挂起/恢复和同步回调；具体实现（例如 `DataSourceTransactionManager`）再对连接执行开启、提交、回滚和清理。`rollback-only` 会让外层即使正常返回，也在最终提交时转为回滚或抛出 `UnexpectedRollbackException`。

## 6. JDBC / MyBatis 场景

`DataSourceTransactionManager` 获取连接、设置事务属性并关闭自动提交；随后将 `ConnectionHolder` 绑定到 `TransactionSynchronizationManager`，使同一线程的 DAO 复用该连接。完成后恢复连接状态、解绑并归还连接池。因此 `@Async`、线程池和 `CompletableFuture` 默认不继承事务上下文。

## 7. 基础排障清单

- 事务方法必须经 Spring 代理调用；同类自调用会绕过代理，通常应拆到独立 Bean。
- 默认对 `RuntimeException` 和 `Error` 回滚；受检异常需要配置 `rollbackFor`，吞掉异常则要明确标记 rollback-only 或重新抛出。
- 多数据源需指定正确的事务管理器；异步消息或外部副作用应放到提交后回调或 Outbox 中。

需要跟源码验证传播、保存点、线程绑定和事务失效的完整推导时，阅读 [[Spring深度解析|《Spring深度解析》]] 的事务章节。
