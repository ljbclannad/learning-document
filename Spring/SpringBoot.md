# SpringBoot 核心知识

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

**SpringFactoriesLoader 加载机制**
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

**spring.factories 文件示例**
```properties
# Auto Configure
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration,\
org.springframework.boot.autoconfigure.orm.jpa.HibernateJpaAutoConfiguration,\
org.springframework.boot.autoconfigure.web.servlet.WebMvcAutoConfiguration,\
org.springframework.boot.autoconfigure.security.servlet.SecurityAutoConfiguration
```

#### 第二步：条件装配

Spring Boot 使用条件注解判断是否启用某个配置。

**常用条件注解**

| 注解 | 作用 | 示例 |
|------|------|------|
| `@ConditionalOnClass` | 类路径存在指定类时生效 | `@ConditionalOnClass(DataSource.class)` |
| `@ConditionalOnMissingClass` | 类路径不存在指定类时生效 | `@ConditionalOnMissingClass("com.example.CustomConfig")` |
| `@ConditionalOnBean` | 容器中存在指定 Bean 时生效 | `@ConditionalOnBean(DataSource.class)` |
| `@ConditionalOnMissingBean` | 容器中不存在指定 Bean 时生效 | `@ConditionalOnMissingBean(DataSource.class)` |
| `@ConditionalOnProperty` | 配置文件中存在指定属性时生效 | `@ConditionalOnProperty(name="spring.datasource.url")` |
| `@ConditionalOnWebApplication` | 当前应用是 Web 应用时生效 | `@ConditionalOnWebApplication(type=Type.SERVLET)` |
| `@ConditionalOnNotWebApplication` | 当前应用不是 Web 应用时生效 | `@ConditionalOnNotWebApplication` |

**自动配置类示例**
```java
@Configuration
@ConditionalOnClass({DataSource.class, EmbeddedDatabaseType.class})
@ConditionalOnMissingBean(DataSource.class)
@EnableConfigurationProperties(DataSourceProperties.class)
public class DataSourceAutoConfiguration {
    
    @Bean
    @ConditionalOnProperty(name = "spring.datasource.type", havingValue = "com.zaxxer.hikari.HikariDataSource", matchIfMissing = true)
    public DataSource hikariDataSource(DataSourceProperties properties) {
        HikariDataSource dataSource = properties.initializeDataSourceBuilder()
            .type(HikariDataSource.class)
            .build();
        return dataSource;
    }
    
    @Bean
    @ConditionalOnProperty(name = "spring.datasource.type", havingValue = "org.apache.tomcat.jdbc.pool.DataSource")
    public DataSource tomcatDataSource(DataSourceProperties properties) {
        return properties.initializeDataSourceBuilder()
            .type(org.apache.tomcat.jdbc.pool.DataSource.class)
            .build();
    }
}
```

### 2.3 常见自动配置模块

| 模块 | 自动配置类 | 作用 | 触发条件 |
|------|-----------|------|---------|
| Web MVC | `WebMvcAutoConfiguration` | 配置 Spring MVC | 存在 `DispatcherServlet` 类 |
| 数据源 | `DataSourceAutoConfiguration` | 配置数据库连接池 | 存在 `DataSource` 类和 `spring.datasource.url` 配置 |
| JPA | `HibernateJpaAutoConfiguration` | 配置 JPA 和 Hibernate | 存在 `EntityManager` 类 |
| Redis | `RedisAutoConfiguration` | 配置 Redis 连接 | 存在 `RedisOperations` 类 |
| Security | `SecurityAutoConfiguration` | 配置基本安全功能 | 存在 `SecurityFilterChain` 类 |
| Actuator | `EndpointAutoConfiguration` | 配置监控端点 | 存在 `Endpoint` 类 |
| 缓存 | `CacheAutoConfiguration` | 配置缓存管理器 | 存在 `CacheManager` 类 |

### 2.4 生产实战

#### 自定义自动配置

**1. 创建自动配置类**
```java
@Configuration
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

**3. 注册到 spring.factories**
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
   SecurityAutoConfiguration:
      Did not match:
         - @ConditionalOnClass did not find required class 'org.springframework.security.config.annotation.web.configuration.WebSecurityConfigurerAdapter' (OnClassCondition)
```

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
    
    // 支持 SpEL 表达式
    @Value("#{${myapp.database.url}}")
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

| 方式 | 适用场景 | 优点 | 缺点 |
|------|---------|------|------|
| `@Value` | 少量配置 | 简单直观 | 冗长，缺乏类型安全 |
| `@ConfigurationProperties` | 批量配置、复杂结构 | 类型安全、支持验证、IDE 友好 | 需定义配置类 |
| `Environment` | 动态读取、未知配置 | 灵活动态 | 缺乏类型安全 |

**推荐实践**：
- 业务配置：使用 `@ConfigurationProperties`
- 简单配置：使用 `@Value`
- 动态配置：使用 `Environment`

### 3.4 生产实战

#### 多环境配置

**配置文件命名规则**：
- `application.yml`：通用配置
- `application-dev.yml`：开发环境
- `application-test.yml`：测试环境
- `application-prod.yml`：生产环境

**application.yml**：
```yaml
spring:
  profiles:
    active: @spring.profiles.active@  # Maven 占位符

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

#### 敏感信息加密

**使用 Jasypt 加密配置**

**1. 添加依赖**：
```xml
<dependency>
    <groupId>com.github.ulisesbocchio</groupId>
    <artifactId>jasypt-spring-boot-starter</artifactId>
    <version>3.0.5</version>
</dependency>
```

**2. 配置加密密钥**：
```yaml
jasypt:
  encryptor:
    password: ${JASYPT_PASSWORD}  # 从环境变量读取
    algorithm: PBEWithMD5AndDES
```

**3. 加密敏感信息**：
```java
@SpringBootTest
public class JasyptTest {
    
    @Autowired
    private StringEncryptor encryptor;
    
    @Test
    public void encrypt() {
        String password = "my-secret-password";
        String encrypted = encryptor.encrypt(password);
        System.out.println("Encrypted: " + encrypted);
    }
}
```

**4. 使用加密后的配置**：
```yaml
myapp:
  database:
    password: ENC(encrypted-value-here)
```

#### 配置刷新（Spring Cloud Config）

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

---

## 总结

本文档涵盖了 Spring Boot 的三大核心知识：

1. **启动流程**：从 SpringApplication 实例化到应用启动完成的完整流程
2. **自动配置**：@EnableAutoConfiguration 原理、条件装配、自定义自动配置
3. **配置读取**：@Value、@ConfigurationProperties、Environment 三种方式及其适用场景

每个主题都包含原理解析和生产实战示例，帮助理解 Spring Boot 的核心机制并应用到实际项目中。
