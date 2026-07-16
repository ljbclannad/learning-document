# SpringBoot 核心知识

> [!info] 文档定位
>
> 本文以 Spring Boot 3.x 为主线；Boot 2.x 的 `spring.factories` 注册方式仅用于理解存量项目。Spring Boot 建立在 [[Spring|《Spring》]] 之上，容器生命周期、AOP 和事务基础请先阅读基础主文。

## 目录

1. [[#零、先建立整体理解|整体理解：Spring 与 Spring Boot 的关系]]
2. [[#一、SpringBoot 启动流程|启动流程：从 `run()` 到应用就绪]]
3. [[#二、SpringBoot 自动配置|自动配置：候选、条件与覆盖]]
4. [[#三、读取自定义配置|外部化配置：绑定、优先级与多环境]]
5. [[#总结|总结与复习主线]]

## 零、先建立整体理解

### 0.1 Spring 和 Spring Boot 的关系

1. `Spring` 更像基础框架，核心提供的是 IoC、AOP、事务、MVC、Bean 生命周期这些底层能力。
2. `Spring Boot` 不是替代 Spring，而是在 Spring 之上做了一层工程化封装，目标是让项目更快跑起来、减少样板配置、统一依赖管理、方便接入生产级能力。
3. 一句话理解：
   - **Spring 解决“能力怎么提供”，Spring Boot 解决“项目怎么更快落地”。**

### 0.2 Spring Boot 到底解决了什么问题

在没有 Spring Boot 的时候，做一个 Spring 项目通常要自己处理很多重复工作：

- 依赖怎么选
- MVC 怎么开
- JSON 转换器怎么配
- Tomcat 怎么部署
- 数据源怎么建
- 配置文件怎么组织

Spring Boot 主要就是在解决这些工程问题。它最核心的三件事是：

1. **Starter**
   - 解决“依赖怎么组合”的问题
2. **Auto Configuration**
   - 解决“常见 Bean 怎么自动配起来”的问题
3. **外部化配置**
   - 解决“同一套程序怎么在不同环境下灵活运行”的问题

### 0.3 一句话理解

> Spring Boot 本质上不是新的 IoC 或 AOP 框架，它还是建立在 Spring 之上。它真正解决的是工程落地效率问题，通过 Starter、自动配置和外部化配置，把 Spring 项目里大量重复的依赖选择、Bean 配置和启动流程标准化，让项目能更快跑起来。

## 一、SpringBoot 启动流程

### 1.1 启动流程概述

Spring Boot 应用的启动入口是包含 `@SpringBootApplication` 注解的主类，通过调用 `SpringApplication.run()` 方法启动应用。

**启动入口示例**：
```java
@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

### 1.2 启动流程详解

#### 第一步：SpringApplication 实例化

创建 `SpringApplication` 对象时完成以下操作：

1. **推断应用类型**
   - 判断是普通 Java 应用、Servlet Web 应用还是 Reactive Web 应用
   - 通过检查类路径中的特定类来判断（如 `DispatcherServlet`、`DispatcherHandler`）

2. **加载初始化器（Initializers）**
   - 从 `META-INF/spring.factories` 加载 `ApplicationContextInitializer` 实现类
   - 用于在 ApplicationContext 刷新之前进行自定义初始化

3. **加载监听器（Listeners）**
   - 从 `META-INF/spring.factories` 加载 `ApplicationListener` 实现类
   - 用于监听应用启动过程中的各种事件

4. **推断主类**
   - 通过堆栈跟踪找到包含 `main` 方法的类

**源码示例**：
```java
public SpringApplication(ResourceLoader resourceLoader, Class<?>... primarySources) {
    this.resourceLoader = resourceLoader;
    this.primarySources = new LinkedHashSet<>(Arrays.asList(primarySources));
    
    // 推断应用类型
    this.webApplicationType = WebApplicationType.deduceFromClasspath();
    
    // 加载初始化器
    setInitializers((Collection) getSpringFactoriesInstances(ApplicationContextInitializer.class));
    
    // 加载监听器
    setListeners((Collection) getSpringFactoriesInstances(ApplicationListener.class));
    
    // 推断主类
    this.mainApplicationClass = deduceMainApplicationClass();
}
```

#### 第二步：执行 run() 方法

`SpringApplication.run()` 方法包含核心启动逻辑：

**1. 准备环境（prepareEnvironment）**
```java
ConfigurableEnvironment environment = prepareEnvironment(listeners, applicationArguments);
```
- 创建并配置 `Environment` 对象
- 加载配置文件（`application.properties`、`application.yml`）
- 加载系统环境变量、命令行参数
- 触发 `ApplicationEnvironmentPreparedEvent` 事件

**2. 打印 Banner**
```java
Banner printedBanner = printBanner(environment);
```
- 在控制台打印 Spring Boot 标志
- 可通过 `spring.banner.location` 自定义
- 可通过 `spring.main.banner-mode=off` 关闭

**3. 创建 ApplicationContext**
```java
context = createApplicationContext();
```
- 根据应用类型创建对应的 ApplicationContext：
  - Servlet Web：`AnnotationConfigServletWebServerApplicationContext`
  - Reactive Web：`AnnotationConfigReactiveWebServerApplicationContext`
  - 非 Web：`AnnotationConfigApplicationContext`

**4. 准备上下文（prepareContext）**
```java
prepareContext(context, environment, listeners, applicationArguments, printedBanner);
```
- 将 Environment 设置到 ApplicationContext
- 执行 ApplicationContextInitializer
- 触发 `ApplicationContextInitializedEvent` 事件
- 加载主配置类（@SpringBootApplication 标注的类）
- 触发 `ApplicationPreparedEvent` 事件

**5. 刷新上下文（refreshContext）**
```java
refreshContext(context);
```
- 调用 `AbstractApplicationContext.refresh()` 方法
- 完成 Bean 的扫描、注册、实例化、依赖注入
- 启动内嵌 Web 服务器（Tomcat、Jetty、Undertow）
- 触发 `ApplicationStartedEvent` 事件

**6. 执行运行器（callRunners）**
```java
callRunners(context, applicationArguments);
```
- 执行所有 `CommandLineRunner` 和 `ApplicationRunner` 实现类
- 按 `@Order` 注解或 `Ordered` 接口指定的顺序执行
- 触发 `ApplicationReadyEvent` 事件

**7. 启动完成**
- 应用开始监听请求（Web 应用）
- 返回 ApplicationContext 对象

### 1.3 启动流程图

```
主程序入口 (main)
    ↓
创建 SpringApplication 实例
    ↓
准备环境 (Environment)
    ↓
打印 Banner
    ↓
创建 ApplicationContext
    ↓
准备上下文 (加载配置类)
    ↓
刷新上下文 (Bean 初始化)
    ↓
执行 CommandLineRunner / ApplicationRunner
    ↓
启动完成 (监听请求)
```

### 1.4 生产实战

#### 自定义启动行为

**1. 实现 CommandLineRunner**
```java
@Component
@Order(1)
public class DataInitRunner implements CommandLineRunner {
    
    @Autowired
    private UserRepository userRepository;
    
    @Override
    public void run(String... args) throws Exception {
        // 应用启动后初始化数据
        if (userRepository.count() == 0) {
            User admin = new User("admin", "admin@example.com");
            userRepository.save(admin);
            System.out.println("Admin user created");
        }
    }
}
```

**2. 实现 ApplicationRunner（推荐）**
```java
@Component
@Order(2)
public class CacheWarmupRunner implements ApplicationRunner {
    
    @Autowired
    private CacheManager cacheManager;
    
    @Override
    public void run(ApplicationArguments args) throws Exception {
        // 预热缓存
        Cache userCache = cacheManager.getCache("users");
        // 加载热点数据到缓存
        System.out.println("Cache warmed up");
    }
}
```

**3. 自定义 ApplicationContextInitializer**
```java
public class CustomInitializer implements ApplicationContextInitializer<ConfigurableApplicationContext> {
    
    @Override
    public void initialize(ConfigurableApplicationContext applicationContext) {
        // 在 ApplicationContext 刷新之前执行
        ConfigurableEnvironment environment = applicationContext.getEnvironment();
        
        // 添加自定义属性源
        Map<String, Object> customProps = new HashMap<>();
        customProps.put("custom.property", "value");
        environment.getPropertySources().addFirst(
            new MapPropertySource("customProperties", customProps));
        
        System.out.println("Custom initializer executed");
    }
}

// 注册方式 1：在 META-INF/spring.factories 中注册
// org.springframework.context.ApplicationContextInitializer=com.example.CustomInitializer

// 注册方式 2：在主类中手动添加
@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(Application.class);
        app.addInitializers(new CustomInitializer());
        app.run(args);
    }
}
```

**4. 监听启动事件**
```java
@Component
public class ApplicationEventListener {
    
    @EventListener
    public void handleContextRefreshed(ContextRefreshedEvent event) {
        System.out.println("ApplicationContext refreshed");
    }
    
    @EventListener
    public void handleApplicationReady(ApplicationReadyEvent event) {
        System.out.println("Application is ready to serve requests");
        // 记录启动时间
        long startupTime = System.currentTimeMillis() - event.getTimestamp();
        System.out.println("Startup time: " + startupTime + "ms");
    }
    
    @EventListener
    public void handleApplicationFailed(ApplicationFailedEvent event) {
        System.err.println("Application failed to start");
        event.getException().printStackTrace();
    }
}
```

### 1.5 复述卡片：启动流程

#### 30 秒口述版

Spring Boot 启动我一般会从 `SpringApplication.run()` 讲起。它先推断应用类型，准备环境和配置源，再创建对应的 `ApplicationContext`，然后加载主配置类和自动配置类，执行 `refresh()` 完成 Bean 创建、依赖注入和后置处理器注册；如果是 Web 应用，还会在这个过程中启动内嵌 Tomcat，最后再执行 `ApplicationRunner` / `CommandLineRunner`。

#### 一条主线记忆

可以把启动流程记成：

`run() -> 准备 Environment -> 创建 ApplicationContext -> 加载配置类 -> refresh 容器 -> 启动内嵌服务器 -> 执行 Runner`

---

## 二、SpringBoot 自动配置

### 2.1 自动配置原理

Spring Boot 的自动配置（Auto Configuration）是其核心特性，可以根据项目依赖和环境自动配置 Spring 应用。

#### 核心注解

**@SpringBootApplication 复合注解**
```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
@SpringBootConfiguration      // 等同于 @Configuration
@EnableAutoConfiguration       // 启用自动配置
@ComponentScan                 // 组件扫描
public @interface SpringBootApplication {
    // ...
}
```

**@EnableAutoConfiguration 注解**
```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Inherited
@AutoConfigurationPackage
@Import(AutoConfigurationImportSelector.class)
public @interface EnableAutoConfiguration {
    // 排除指定的自动配置类
    Class<?>[] exclude() default {};
    String[] excludeName() default {};
}
```

### 2.2 自动配置加载机制

#### 第一步：加载自动配置类

Spring Boot 自动配置的核心入口是 `@EnableAutoConfiguration`，它通过 `AutoConfigurationImportSelector` 导入候选自动配置类。

**版本口径要区分**

- **Spring Boot 2.6 及以前的常见口径**：
  - 自动配置类通常通过 `META-INF/spring.factories` 中的 `EnableAutoConfiguration` 键注册
- **Spring Boot 2.7 / 3.x 更推荐的口径**：
  - 自动配置类通过 `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` 注册
  - 这是官方现在更推荐、也更适合新项目的说法

更稳的理解不是死背某一个文件名，而是：

> Spring Boot 会从约定的自动配置注册文件里加载候选自动配置类，再结合条件注解决定哪些真正生效。

**早期 / 兼容口径示例（spring.factories）**
```java
public class AutoConfigurationImportSelector implements DeferredImportSelector {
    
    protected List<String> getCandidateConfigurations(AnnotationMetadata metadata, 
                                                      AnnotationAttributes attributes) {
        // 从 META-INF/spring.factories 加载自动配置类
        List<String> configurations = SpringFactoriesLoader.loadFactoryNames(
            EnableAutoConfiguration.class, 
            getBeanClassLoader());
        
        return configurations;
    }
}
```

**spring.factories 文件示例（Boot 2.x 常见）**
```properties
# Auto Configure
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration,\
org.springframework.boot.autoconfigure.orm.jpa.HibernateJpaAutoConfiguration,\
org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration,\
org.springframework.boot.autoconfigure.security.servlet.SecurityAutoConfiguration
```

**AutoConfiguration.imports 文件示例（Boot 3.x 更推荐）**
```properties
org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
org.springframework.boot.autoconfigure.orm.jpa.HibernateJpaAutoConfiguration
org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration
org.springframework.boot.autoconfigure.security.servlet.SecurityAutoConfiguration
```

#### 第二步：条件装配

Spring Boot 使用条件注解判断是否启用某个配置。

**常用条件注解**

| 注解                              | 作用                         | 示例                                                     |
| --------------------------------- | ---------------------------- | -------------------------------------------------------- |
| `@ConditionalOnClass`             | 类路径存在指定类时生效       | `@ConditionalOnClass(DataSource.class)`                  |
| `@ConditionalOnMissingClass`      | 类路径不存在指定类时生效     | `@ConditionalOnMissingClass("com.example.CustomConfig")` |
| `@ConditionalOnBean`              | 容器中存在指定 Bean 时生效   | `@ConditionalOnBean(DataSource.class)`                   |
| `@ConditionalOnMissingBean`       | 容器中不存在指定 Bean 时生效 | `@ConditionalOnMissingBean(DataSource.class)`            |
| `@ConditionalOnProperty`          | 配置属性满足指定条件时生效 | `@ConditionalOnProperty(prefix="sms", name="enabled", havingValue="true")` |
| `@ConditionalOnWebApplication`    | 当前应用是 Web 应用时生效    | `@ConditionalOnWebApplication(type=Type.SERVLET)`        |
| `@ConditionalOnNotWebApplication` | 当前应用不是 Web 应用时生效  | `@ConditionalOnNotWebApplication`                        |

**自动配置示意（不是 `DataSourceAutoConfiguration` 的真实源码）**
```java
@AutoConfiguration
@ConditionalOnClass(SmsClient.class)
@ConditionalOnMissingBean(SmsClient.class)
@EnableConfigurationProperties(SmsProperties.class)
public class SmsAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    @ConditionalOnProperty(prefix = "sms", name = "enabled", havingValue = "true")
    public SmsClient smsClient(SmsProperties properties) {
        return new SmsClient(properties.getEndpoint());
    }
}
```

真实自动配置通常由多个嵌套配置和条件共同组成，不宜把简化代码当作框架源码。以数据源为例：类路径存在相关 JDBC 能力且用户未声明 `DataSource` 时，Boot 会继续尝试配置；既可以绑定 `spring.datasource.*`，也可能配置嵌入式数据库，并非必须提供 `spring.datasource.url`。

#### 第三步：用户配置覆盖默认配置

Spring Boot 自动配置不是“强行配死”，而是会给用户留覆盖入口。

最常见的覆盖方式有：

1. 你自己声明同类型 Bean
   - 配合 `@ConditionalOnMissingBean`，默认配置就会让位
2. 通过配置项开关控制
   - 比如 `@ConditionalOnProperty`
3. 显式排除自动配置类
   - 例如：
   ```java
   @SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
   ```

这也是理解 Spring Boot 的关键点：

> 它不是“偷偷帮你配”，而是“先按约定给默认值，你要特殊行为时再覆盖它”。

### 2.3 常见自动配置模块

| 模块 | 代表性自动配置类 | 作用 | 常见前提（还会叠加其他条件） |
| --- | --- | --- | --- |
| Web MVC | `WebMvcAutoConfiguration` | 配置 Spring MVC | Servlet Web 环境与 MVC 相关类存在 |
| 数据源 | `DataSourceAutoConfiguration` | 配置 `DataSource` 或嵌入式数据库 | JDBC 相关类存在且用户未声明 `DataSource` |
| JPA | `HibernateJpaAutoConfiguration` | 配置 JPA 与 Hibernate | JPA/Hibernate 相关类、数据源等条件满足 |
| Redis | `RedisAutoConfiguration` | 配置 Redis 连接工厂与模板 | Redis 客户端相关类存在 |
| Security | `SecurityAutoConfiguration` | 导入基础安全配置 | Spring Security 相关类存在 |
| Actuator | `EndpointAutoConfiguration` | 装配端点基础设施 | Actuator 端点基础设施与相应端点条件满足 |
| 缓存 | `CacheAutoConfiguration` | 配置缓存管理器 | Cache API 与具体缓存实现条件满足 |

### 2.4 Starter 是什么

1. `Starter` 不是自动配置本身，而是**一组依赖的聚合入口**。
2. 例如 `spring-boot-starter-web` 往往会帮你带上：
   - Spring MVC
   - Jackson
   - Validation
   - 内嵌 Tomcat
   - 一些常用日志依赖
3. 所以更准确地说：
   - **Starter 负责把依赖组织好**
   - **Auto Configuration 负责把默认 Bean 配起来**
4. 两者职责不同：Starter 决定“带什么依赖”，自动配置决定“在什么条件下创建哪些默认 Bean”。

### 2.5 Starter 的工程边界

一个可复用的 Starter 通常拆为两个模块：

| 模块 | 职责 | 典型内容 |
| --- | --- | --- |
| `xxx-spring-boot-starter` | 依赖聚合，不放业务实现 | 依赖 `spring-boot-starter`、`xxx-spring-boot-autoconfigure` 和必要的第三方库 |
| `xxx-spring-boot-autoconfigure` | 条件装配与扩展点 | `@AutoConfiguration`、`@ConfigurationProperties`、`AutoConfiguration.imports` |

自动配置应避免组件扫描；使用显式 `@Import`、条件注解和用户 Bean 覆盖点来保持边界清晰。若自动配置之间存在先后要求，可用 `@AutoConfiguration(before = …, after = …)` 表达 **Bean 定义注册顺序**，它不等同于 Bean 的实例化顺序。

### 2.6 生产实战

#### 自定义自动配置

**1. 创建自动配置类**
```java
@AutoConfiguration
@ConditionalOnClass(SmsService.class)
@EnableConfigurationProperties(SmsProperties.class)
public class SmsAutoConfiguration {
    
    @Bean
    @ConditionalOnMissingBean
    @ConditionalOnProperty(name = "sms.provider", havingValue = "aliyun")
    public SmsService aliyunSmsService(SmsProperties properties) {
        return new AliyunSmsService(properties.getAccessKey(), properties.getSecretKey());
    }
    
    @Bean
    @ConditionalOnMissingBean
    @ConditionalOnProperty(name = "sms.provider", havingValue = "tencent")
    public SmsService tencentSmsService(SmsProperties properties) {
        return new TencentSmsService(properties.getAccessKey(), properties.getSecretKey());
    }
}
```

**2. 创建配置属性类**
```java
@ConfigurationProperties(prefix = "sms")
public class SmsProperties {
    
    private String provider = "aliyun";
    private String accessKey;
    private String secretKey;
    private int timeout = 5000;
    
    // Getters and Setters
}
```

**3. 注册自动配置**

Spring Boot 3.x 更推荐：
```properties
# META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
com.example.autoconfigure.SmsAutoConfiguration
```

Spring Boot 2.x 常见写法：
```properties
# META-INF/spring.factories
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.example.autoconfigure.SmsAutoConfiguration
```

**4. 使用自动配置**
```yaml
# application.yml
sms:
  provider: aliyun
  access-key: your-access-key
  secret-key: your-secret-key
  timeout: 10000
```

```java
@Service
public class UserService {
    
    @Autowired
    private SmsService smsService;  // 自动注入
    
    public void sendVerificationCode(String phone) {
        String code = generateCode();
        smsService.send(phone, "Your code is: " + code);
    }
}
```

#### 排除自动配置

**方式 1：使用 @SpringBootApplication 注解**
```java
@SpringBootApplication(exclude = {
    DataSourceAutoConfiguration.class,
    SecurityAutoConfiguration.class
})
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

**方式 2：使用配置文件**
```yaml
spring:
  autoconfigure:
    exclude:
      - org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
      - org.springframework.boot.autoconfigure.security.servlet.SecurityAutoConfiguration
```

#### 查看自动配置报告

**启用 debug 模式**
```yaml
debug: true
```

或启动时添加参数：
```bash
java -jar app.jar --debug
```

**输出示例**：
```
============================
CONDITIONS EVALUATION REPORT
============================

Positive matches:
-----------------
   DataSourceAutoConfiguration matched:
      - @ConditionalOnClass found required classes 'javax.sql.DataSource', 'org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType' (OnClassCondition)

Negative matches:
-----------------
   SomeAutoConfiguration:
      Did not match:
         - @ConditionalOnClass did not find required class 'com.example.OptionalLibrary' (OnClassCondition)
```

**排障闭环**：

- 启动期先用 `--debug` 或 `debug=true` 查看条件报告。
- 已启用 Actuator 时，可用 `/actuator/conditions` 查看条件匹配结果；用 `/actuator/configprops` 和 `/actuator/env` 追踪配置绑定值及其来源。
- 这些端点可能暴露配置和环境细节，生产环境应按需暴露并配置访问控制、脱敏策略。

### 2.7 复述卡片：自动配置

#### 30 秒口述版

Spring Boot 自动配置的核心不是“自动猜”，而是“按条件装配”。启动时它会加载一批候选自动配置类，再根据类路径、配置项、容器里已有的 Bean 等条件判断哪些配置该生效。比如你引入了 Web 依赖，它就可能自动配 MVC；你自己又声明了同类 Bean，默认配置就会让位。

#### 最好记的一句话

> Spring Boot 自动配置 = 候选配置类加载 + 条件判断 + 用户配置覆盖默认配置。

---

## 三、读取自定义配置

### 3.1 配置文件格式

Spring Boot 支持多种配置文件格式：

**application.properties**
```properties
myapp.name=SpringBootDemo
myapp.version=1.0.0
myapp.features.enabled=true
myapp.database.url=jdbc:mysql://localhost:3306/db
myapp.database.username=root
myapp.database.password=password
```

**application.yml（推荐）**
```yaml
myapp:
  name: SpringBootDemo
  version: 1.0.0
  features:
    enabled: true
  database:
    url: jdbc:mysql://localhost:3306/db
    username: root
    password: password
```

### 3.2 读取配置的方式

#### 方式一：@Value 注解

**适用场景**：读取少量配置

```java
@Component
public class MyAppConfig {
    
    @Value("${myapp.name}")
    private String appName;
    
    @Value("${myapp.version}")
    private String version;
    
    @Value("${myapp.features.enabled:false}")  // 默认值
    private boolean featuresEnabled;
    
    // 普通配置占位符；SpEL 仅用于确有表达式计算需求的场景
    @Value("${myapp.database.url}")
    private String dbUrl;
    
    public void printConfig() {
        System.out.println("App Name: " + appName);
        System.out.println("Version: " + version);
        System.out.println("Features Enabled: " + featuresEnabled);
    }
}
```

**优点**：
- 简单直观
- 支持 SpEL 表达式

**缺点**：
- 配置项多时代码冗长
- 缺乏类型安全
- 不支持复杂嵌套结构

#### 方式二：@ConfigurationProperties（推荐）

**适用场景**：批量读取配置，支持复杂嵌套结构

```java
@Component
@ConfigurationProperties(prefix = "myapp")
@Validated  // 启用 JSR-303 验证
public class MyAppProperties {
    
    @NotBlank(message = "应用名称不能为空")
    private String name;
    
    @Pattern(regexp = "\\d+\\.\\d+\\.\\d+", message = "版本号格式不正确")
    private String version;
    
    private Features features = new Features();
    private Database database = new Database();
    
    public static class Features {
        private boolean enabled = false;
        private List<String> modules = new ArrayList<>();
        
        // Getters and Setters
        public boolean isEnabled() {
            return enabled;
        }
        
        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
        
        public List<String> getModules() {
            return modules;
        }
        
        public void setModules(List<String> modules) {
            this.modules = modules;
        }
    }
    
    public static class Database {
        @NotBlank
        private String url;
        
        @NotBlank
        private String username;
        
        @NotBlank
        private String password;
        
        private int maxPoolSize = 10;
        private int minIdle = 5;
        
        // Getters and Setters
        public String getUrl() {
            return url;
        }
        
        public void setUrl(String url) {
            this.url = url;
        }
        
        public String getUsername() {
            return username;
        }
        
        public void setUsername(String username) {
            this.username = username;
        }
        
        public String getPassword() {
            return password;
        }
        
        public void setPassword(String password) {
            this.password = password;
        }
        
        public int getMaxPoolSize() {
            return maxPoolSize;
        }
        
        public void setMaxPoolSize(int maxPoolSize) {
            this.maxPoolSize = maxPoolSize;
        }
        
        public int getMinIdle() {
            return minIdle;
        }
        
        public void setMinIdle(int minIdle) {
            this.minIdle = minIdle;
        }
    }
    
    // Getters and Setters
    public String getName() {
        return name;
    }
    
    public void setName(String name) {
        this.name = name;
    }
    
    public String getVersion() {
        return version;
    }
    
    public void setVersion(String version) {
        this.version = version;
    }
    
    public Features getFeatures() {
        return features;
    }
    
    public void setFeatures(Features features) {
        this.features = features;
    }
    
    public Database getDatabase() {
        return database;
    }
    
    public void setDatabase(Database database) {
        this.database = database;
    }
}
```

**使用配置类**：
```java
@Service
public class ConfigService {
    
    @Autowired
    private MyAppProperties properties;
    
    public void printConfig() {
        System.out.println("App Name: " + properties.getName());
        System.out.println("Version: " + properties.getVersion());
        System.out.println("Features Enabled: " + properties.getFeatures().isEnabled());
        System.out.println("DB URL: " + properties.getDatabase().getUrl());
    }
}
```

**优点**：
- 类型安全
- 支持复杂嵌套结构
- 支持 JSR-303 验证
- 配置集中管理
- IDE 自动补全

**缺点**：
- 需要定义配置类
- 代码量稍多

**Boot 3 推荐的注册与不可变绑定方式**：

在业务应用中，可在启动类上使用 `@ConfigurationPropertiesScan` 统一发现属性类；在自动配置模块中则继续使用 `@EnableConfigurationProperties`。对于不需要运行期修改的配置，`record` 能减少样板代码并保证不可变性：

```java
@ConfigurationProperties(prefix = "myapp")
@Validated
public record MyAppProperties(
        @NotBlank String name,
        Database database) {

    public record Database(@NotBlank String url, @NotBlank String username) {
    }
}
```

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class Application {
}
```

#### 方式三：Environment 动态读取

**适用场景**：动态读取配置，获取未知配置项

```java
@Component
public class DynamicConfigReader {
    
    @Autowired
    private Environment environment;
    
    public void printConfig() {
        String appName = environment.getProperty("myapp.name");
        String version = environment.getProperty("myapp.version", "1.0.0");  // 默认值
        boolean featuresEnabled = environment.getProperty("myapp.features.enabled", Boolean.class, false);
        
        System.out.println("App Name: " + appName);
        System.out.println("Version: " + version);
        System.out.println("Features Enabled: " + featuresEnabled);
        
        // 检查配置是否存在
        if (environment.containsProperty("myapp.database.url")) {
            String dbUrl = environment.getProperty("myapp.database.url");
            System.out.println("DB URL: " + dbUrl);
        }
        
        // 获取激活的 profile
        String[] activeProfiles = environment.getActiveProfiles();
        System.out.println("Active Profiles: " + String.join(", ", activeProfiles));
    }
}
```

**优点**：
- 灵活动态
- 可获取未知配置项
- 可检查配置是否存在

**缺点**：
- 缺乏类型安全
- 需要手动类型转换
- 无法利用 IDE 自动补全

### 3.3 配置方式对比

| 方式                       | 适用场景           | 优点                         | 缺点               |
| -------------------------- | ------------------ | ---------------------------- | ------------------ |
| `@Value`                   | 少量配置           | 简单直观                     | 冗长，缺乏类型安全 |
| `@ConfigurationProperties` | 批量配置、复杂结构 | 类型安全、支持验证、IDE 友好 | 需定义配置类       |
| `Environment`              | 动态读取、未知配置 | 灵活动态                     | 缺乏类型安全       |

**推荐实践**：
- 业务配置：使用 `@ConfigurationProperties`
- 简单配置：使用 `@Value`
- 动态配置：使用 `Environment`

### 3.4 配置优先级怎么理解

Spring Boot 支持多种配置源，不必死背完整顺序，但至少要知道：

1. **命令行参数** 通常优先级很高
2. **JVM 参数 / 环境变量** 通常会覆盖本地配置文件
3. **application.yml / application.properties** 是项目里最常见的默认配置源
4. **profile 配置文件** 会在通用配置基础上做环境覆盖

可以这样理解：

- `application.yml` 放通用默认值
- `application-prod.yml` 覆盖生产差异
- 命令行参数或环境变量再覆盖部署时的最终值

一句话收口：

> Spring Boot 的配置体系本质上是“多配置源叠加 + 高优先级覆盖低优先级”，目的就是让同一套程序在不同环境下不用重新打包就能运行。

### 3.5 Config Data 与 Profile 的组织方式

`application.yml` 适合放通用默认值，`application-{profile}.yml` 放环境差异。Profile 专用文件会覆盖同一位置的通用配置；不要在 profile 专用文件中再配置 `spring.profiles.active` 或 `spring.profiles.include`。

跨文件或外部配置中心使用 `spring.config.import`；缺失允许时加 `optional:`，避免部署环境没有该文件而启动失败：

```yaml
spring:
  config:
    import: optional:file:./secrets.yml
  profiles:
    group:
      production: prod,metrics
```

`spring.config.location` 会替换默认搜索位置，`spring.config.additional-location` 则是在默认位置之外追加；两者都应由环境变量、JVM 参数或命令行在启动早期提供。

### 3.6 生产实战

#### 多环境配置

**配置文件命名规则**：
- `application.yml`：通用配置
- `application-dev.yml`：开发环境
- `application-test.yml`：测试环境
- `application-prod.yml`：生产环境

**application.yml（通用默认值，不固定激活环境）**：
```yaml
myapp:
  name: SpringBootDemo
  version: 1.0.0
```

**application-dev.yml**：
```yaml
myapp:
  database:
    url: jdbc:mysql://localhost:3306/db_dev
    username: dev_user
    password: dev_pass
  
logging:
  level:
    root: DEBUG
```

**application-prod.yml**：
```yaml
myapp:
  database:
    url: jdbc:mysql://prod-server:3306/db_prod
    username: prod_user
    password: ${DB_PASSWORD}  # 从环境变量读取
  
logging:
  level:
    root: WARN
```

**激活 profile**：
```bash
# 方式 1：命令行参数
java -jar app.jar --spring.profiles.active=prod

# 方式 2：环境变量
export SPRING_PROFILES_ACTIVE=prod
java -jar app.jar

# 方式 3：JVM 参数
java -Dspring.profiles.active=prod -jar app.jar
```

#### 敏感信息管理

不要把明文密钥、数据库密码提交到仓库，也不要把应用内“可解密的密文”当成密钥管理的替代方案。生产环境优先使用云 Secret Manager、Vault、Kubernetes Secret 或 CI/CD 注入；应用只从环境变量或受控挂载文件读取。

```yaml
myapp:
  database:
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
```

如果由于遗留系统必须使用 Jasypt 等应用内加密方案，应让主密钥由外部密钥系统注入，并避免已不安全的 `PBEWithMD5AndDES`；同时评估轮换、审计与泄露后的处置流程。

#### 配置刷新（Spring Cloud Config）

`@RefreshScope` 和 `/actuator/refresh` 属于 **Spring Cloud Context** 能力，并非纯 Spring Boot Actuator 默认提供。需要引入 Spring Cloud 相关依赖、配置端点暴露策略，并认识到刷新会重建带 `@RefreshScope` 的 Bean；数据库连接池、静态字段和已被其他对象缓存的值未必会按预期更新。

**使用 @RefreshScope 实现配置热更新**：
```java
@Component
@RefreshScope  // 支持配置刷新
@ConfigurationProperties(prefix = "myapp")
public class RefreshableConfig {
    
    private String name;
    private String version;
    
    // Getters and Setters
}
```

**触发刷新**：
```bash
curl -X POST http://localhost:8080/actuator/refresh
```

### 3.7 复述卡片：配置体系

#### 30 秒口述版

Spring Boot 配置体系我一般会从三点讲：第一是外部化配置，支持 `application.yml`、环境变量、命令行参数等多种配置源；第二是配置绑定，少量配置可以用 `@Value`，批量结构化配置更推荐 `@ConfigurationProperties`；第三是多环境覆盖，同一套程序可以通过 `profile` 和更高优先级配置源在不同环境下运行。

---

## 总结

本文档覆盖了 Spring Boot 最核心的几条主线：

1. **Spring 和 Spring Boot 的关系**：Boot 解决的是工程落地效率问题，不是替代 Spring 核心能力
2. **启动流程**：从 `SpringApplication.run()` 到容器刷新、内嵌服务器启动的完整链路
3. **自动配置**：候选配置类加载、条件装配、用户配置覆盖默认配置
4. **Starter**：依赖聚合入口，和自动配置配合实现开箱即用
5. **外部化配置**：`@Value`、`@ConfigurationProperties`、`Environment`、profile、多配置源覆盖

快速复习时，可优先记住下面这 4 句：

1. Spring Boot 不是替代 Spring，而是把 Spring 项目的依赖、配置和启动流程标准化。
2. `SpringApplication.run()` 的本质是准备环境、创建容器、加载配置、刷新上下文、启动内嵌服务器。
3. 自动配置不是“猜配置”，而是“候选配置类 + 条件判断 + 用户可覆盖默认配置”。
4. Starter 负责依赖聚合，AutoConfiguration 负责默认 Bean 装配，外部化配置负责让同一套程序适配不同环境。
