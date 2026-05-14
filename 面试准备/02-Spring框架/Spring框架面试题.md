# Spring框架面试题（基于简历项目）

> 结合互联网医疗平台、电商平台实战场景

---

## 项目背景（面试开场）

**面试官：介绍下你在项目中是如何使用Spring的？**

**答：**
我在两个项目中深度使用了Spring全家桶：

**1. 互联网医疗平台**
- **Spring Boot 2.7**：快速搭建微服务应用
- **Spring MVC**：RESTful API开发
- **Spring Data JPA / MyBatis-Plus**：数据访问层
- **Spring Security**：用户认证与权限控制
- **Spring Cloud**：微服务治理（Nacos、Sentinel、Gateway）
- **Spring Transaction**：分布式事务管理（Seata）
- **Spring AOP**：日志记录、权限校验、性能监控

**2. 电商平台**
- **Spring Boot**：微服务架构
- **Spring Cache**：缓存抽象（Redis）
- **Spring Async**：异步任务处理
- **Spring Validation**：参数校验
- **Spring Retry**：重试机制
- **Spring Event**：事件驱动

**技术栈：**
- Spring Boot 2.7+
- Spring Cloud Alibaba
- MyBatis-Plus
- Redis、RabbitMQ、MySQL

---

## 一、Spring Core（必问）

### 1. 什么是IOC（控制反转）和DI（依赖注入）？
**答：**

**IOC（Inversion of Control）：**
- **定义**：将对象的创建和管理权交给Spring容器
- **传统方式**：对象自己创建依赖对象
- **IOC方式**：Spring容器创建对象并注入依赖

**DI（Dependency Injection）：**
- **定义**：IOC的一种实现方式，通过注入的方式提供依赖
- **三种注入方式**：构造器注入、Setter注入、字段注入

**示例：**
```java
// 传统方式
public class OrderService {
    private UserService userService = new UserService();  // 自己创建
}

// IOC + DI方式
@Service
public class OrderService {
    @Autowired
    private UserService userService;  // Spring注入
}
```

**优点：**
- 解耦：对象之间松耦合
- 易测试：可以注入Mock对象
- 易维护：集中管理对象

**项目实例：** 医疗平台所有Service、Mapper都由Spring容器管理

---

### 2. Spring Bean的生命周期？
**答：**

**完整生命周期：**
```
1. 实例化（Instantiation）
   ↓
2. 属性赋值（Populate Properties）
   ↓
3. 初始化前（BeanPostProcessor.postProcessBeforeInitialization）
   ↓
4. 初始化（InitializingBean.afterPropertiesSet / @PostConstruct）
   ↓
5. 初始化后（BeanPostProcessor.postProcessAfterInitialization）
   ↓
6. 使用（Bean Ready）
   ↓
7. 销毁（DisposableBean.destroy / @PreDestroy）
```

**代码示例：**
```java
@Component
public class UserService implements InitializingBean, DisposableBean {
    
    @Autowired
    private UserMapper userMapper;
    
    // 1. 构造器（实例化）
    public UserService() {
        System.out.println("1. 构造器");
    }
    
    // 2. 属性赋值后
    @PostConstruct
    public void init() {
        System.out.println("2. @PostConstruct");
    }
    
    // 3. InitializingBean接口
    @Override
    public void afterPropertiesSet() {
        System.out.println("3. afterPropertiesSet");
    }
    
    // 4. 销毁前
    @PreDestroy
    public void preDestroy() {
        System.out.println("4. @PreDestroy");
    }
    
    // 5. DisposableBean接口
    @Override
    public void destroy() {
        System.out.println("5. destroy");
    }
}
```

**项目实例：** 医疗平台使用@PostConstruct初始化缓存，@PreDestroy清理资源

---

### 3. Spring Bean的作用域有哪些？
**答：**

| 作用域 | 说明 | 适用场景 |
|--------|------|----------|
| **singleton** | 单例（默认） | 无状态Bean |
| **prototype** | 每次获取创建新实例 | 有状态Bean |
| **request** | 每个HTTP请求一个实例 | Web应用 |
| **session** | 每个HTTP会话一个实例 | Web应用 |
| **application** | 整个ServletContext一个实例 | Web应用 |

**代码示例：**
```java
// 单例（默认）
@Service
public class UserService {
}

// 原型
@Service
@Scope("prototype")
public class OrderService {
}

// 请求作用域
@Component
@Scope(value = WebApplicationContext.SCOPE_REQUEST, proxyMode = ScopedProxyMode.TARGET_CLASS)
public class RequestContext {
    private String requestId;
}
```

**注意：** 单例Bean注入原型Bean时，原型Bean只会创建一次

**解决方案：**
```java
@Service
public class SingletonService {
    
    @Autowired
    private ApplicationContext context;
    
    public void doSomething() {
        // 每次从容器获取新实例
        PrototypeService service = context.getBean(PrototypeService.class);
    }
}
```

**项目实例：** 医疗平台大部分Bean使用单例，线程池任务使用原型

---

### 4. @Autowired和@Resource的区别？
**答：**

| 特性 | @Autowired | @Resource |
|------|-----------|-----------|
| **来源** | Spring注解 | JDK注解（JSR-250） |
| **装配方式** | 按类型（byType） | 按名称（byName） |
| **required属性** | 支持 | 不支持 |
| **配合注解** | @Qualifier | @Named |

**代码示例：**
```java
// @Autowired（按类型）
@Service
public class OrderService {
    @Autowired
    private UserService userService;
    
    // 多个实现时，配合@Qualifier指定名称
    @Autowired
    @Qualifier("alipayService")
    private PayService payService;
}

// @Resource（按名称）
@Service
public class OrderService {
    @Resource(name = "userService")
    private UserService userService;
}
```

**推荐：** 优先使用@Autowired（Spring原生，功能更强大）

**项目实例：** 医疗平台统一使用@Autowired

---

### 5. Spring如何解决循环依赖？
**答：**

**循环依赖示例：**
```java
@Service
public class A {
    @Autowired
    private B b;
}

@Service
public class B {
    @Autowired
    private A a;
}
```

**Spring解决方案：三级缓存**

```java
// 一级缓存：singletonObjects（成品Bean）
private final Map<String, Object> singletonObjects = new ConcurrentHashMap<>();

// 二级缓存：earlySingletonObjects（半成品Bean）
private final Map<String, Object> earlySingletonObjects = new HashMap<>();

// 三级缓存：singletonFactories（Bean工厂）
private final Map<String, ObjectFactory<?>> singletonFactories = new HashMap<>();
```

**解决流程：**
```
1. 创建A，放入三级缓存
2. A注入B，发现B不存在
3. 创建B，放入三级缓存
4. B注入A，从三级缓存获取A（半成品）
5. B创建完成，放入一级缓存
6. A注入B成功，A创建完成，放入一级缓存
```

**注意：** 只能解决单例Bean的setter注入循环依赖，无法解决：
- 构造器注入循环依赖
- 原型Bean循环依赖

**项目实例：** 医疗平台避免循环依赖，通过重构代码解决

---

## 二、Spring AOP（必问）

### 6. 什么是AOP？有哪些应用场景？
**答：**

**AOP（Aspect Oriented Programming）：面向切面编程**
- **定义**：将横切关注点（日志、事务、权限）从业务逻辑中分离
- **核心概念**：
  - **切面（Aspect）**：横切关注点的模块化
  - **连接点（JoinPoint）**：程序执行的某个点（方法调用）
  - **切点（Pointcut）**：匹配连接点的表达式
  - **通知（Advice）**：在切点执行的代码
  - **织入（Weaving）**：将切面应用到目标对象

**五种通知类型：**
- **@Before**：前置通知
- **@After**：后置通知
- **@AfterReturning**：返回通知
- **@AfterThrowing**：异常通知
- **@Around**：环绕通知（最强大）

**应用场景：**
1. 日志记录
2. 性能监控
3. 权限校验
4. 事务管理
5. 异常处理

**项目实例：** 医疗平台使用AOP实现操作日志、接口耗时监控、权限校验

---

### 7. 如何使用AOP实现操作日志？
**答：**

**自定义注解：**
```java
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface OperationLog {
    String value() default "";  // 操作描述
    String type() default "";   // 操作类型
}
```

**AOP切面：**
```java
@Aspect
@Component
@Slf4j
public class OperationLogAspect {
    
    @Autowired
    private OperationLogMapper logMapper;
    
    @Around("@annotation(operationLog)")
    public Object around(ProceedingJoinPoint pjp, OperationLog operationLog) throws Throwable {
        // 1. 获取请求信息
        HttpServletRequest request = ((ServletRequestAttributes) 
            RequestContextHolder.getRequestAttributes()).getRequest();
        
        String username = SecurityUtils.getCurrentUsername();
        String ip = getIpAddress(request);
        String method = pjp.getSignature().getName();
        String params = JSON.toJSONString(pjp.getArgs());
        
        // 2. 执行方法
        long startTime = System.currentTimeMillis();
        Object result = null;
        String status = "SUCCESS";
        String errorMsg = null;
        
        try {
            result = pjp.proceed();
        } catch (Exception e) {
            status = "FAIL";
            errorMsg = e.getMessage();
            throw e;
        } finally {
            long endTime = System.currentTimeMillis();
            
            // 3. 保存日志
            OperationLogEntity log = OperationLogEntity.builder()
                .username(username)
                .operation(operationLog.value())
                .type(operationLog.type())
                .method(method)
                .params(params)
                .ip(ip)
                .status(status)
                .errorMsg(errorMsg)
                .time(endTime - startTime)
                .createTime(new Date())
                .build();
            
            logMapper.insert(log);
        }
        
        return result;
    }
}
```

**使用：**
```java
@RestController
@RequestMapping("/user")
public class UserController {
    
    @PostMapping("/create")
    @OperationLog(value = "创建用户", type = "CREATE")
    public Result createUser(@RequestBody UserDTO dto) {
        userService.createUser(dto);
        return Result.success();
    }
    
    @DeleteMapping("/{id}")
    @OperationLog(value = "删除用户", type = "DELETE")
    public Result deleteUser(@PathVariable Long id) {
        userService.deleteUser(id);
        return Result.success();
    }
}
```

**项目实例：** 医疗平台所有敏感操作都记录日志，方便审计

---

### 8. AOP的实现原理（动态代理）？
**答：**

**两种动态代理方式：**

#### 1. JDK动态代理（基于接口）
```java
public interface UserService {
    void createUser(User user);
}

@Service
public class UserServiceImpl implements UserService {
    @Override
    public void createUser(User user) {
        System.out.println("创建用户");
    }
}

// JDK动态代理
UserService proxy = (UserService) Proxy.newProxyInstance(
    UserService.class.getClassLoader(),
    new Class[]{UserService.class},
    (proxy, method, args) -> {
        System.out.println("前置通知");
        Object result = method.invoke(target, args);
        System.out.println("后置通知");
        return result;
    }
);
```

#### 2. CGLIB动态代理（基于继承）
```java
@Service
public class UserService {  // 没有接口
    public void createUser(User user) {
        System.out.println("创建用户");
    }
}

// CGLIB动态代理
Enhancer enhancer = new Enhancer();
enhancer.setSuperclass(UserService.class);
enhancer.setCallback((MethodInterceptor) (obj, method, args, proxy) -> {
    System.out.println("前置通知");
    Object result = proxy.invokeSuper(obj, args);
    System.out.println("后置通知");
    return result;
});
UserService proxy = (UserService) enhancer.create();
```

**Spring选择策略：**
- 目标对象实现了接口 → JDK动态代理
- 目标对象没有实现接口 → CGLIB动态代理
- 可以强制使用CGLIB：`@EnableAspectJAutoProxy(proxyTargetClass = true)`

**项目实例：** 医疗平台Service层都实现接口，使用JDK动态代理

---

## 三、Spring事务（必问）

### 9. Spring事务的传播机制有哪些？
**答：**

| 传播机制 | 说明 | 使用场景 |
|---------|------|----------|
| **REQUIRED**（默认） | 有事务加入，无事务创建 | 最常用 |
| **REQUIRES_NEW** | 总是创建新事务，挂起当前事务 | 独立事务 |
| **SUPPORTS** | 有事务加入，无事务非事务执行 | 查询方法 |
| **NOT_SUPPORTED** | 非事务执行，挂起当前事务 | 不需要事务 |
| **MANDATORY** | 必须在事务中执行，否则抛异常 | 强制事务 |
| **NEVER** | 不能在事务中执行，否则抛异常 | 禁止事务 |
| **NESTED** | 嵌套事务，外层回滚内层也回滚 | 部分回滚 |

**代码示例：**
```java
@Service
public class OrderService {
    
    @Autowired
    private LogService logService;
    
    // REQUIRED（默认）
    @Transactional
    public void createOrder(Order order) {
        orderMapper.insert(order);
        
        // logService.saveLog() 加入当前事务
        // 如果saveLog()失败，createOrder()也回滚
        logService.saveLog(order);
    }
}

@Service
public class LogService {
    
    // REQUIRES_NEW（新事务）
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveLog(Order order) {
        logMapper.insert(new Log(order));
        
        // 独立事务，即使createOrder()失败，日志也保存
    }
}
```

**项目实例：** 医疗平台操作日志使用REQUIRES_NEW，保证日志一定保存

---

### 10. @Transactional失效的场景有哪些？
**答：**

**常见失效场景：**

#### 1. 方法不是public
```java
@Service
public class UserService {
    
    @Transactional
    private void createUser(User user) {  // private方法，事务失效
        userMapper.insert(user);
    }
}
```

#### 2. 同类方法调用
```java
@Service
public class UserService {
    
    public void createUser(User user) {
        // 同类方法调用，事务失效（没有走代理）
        this.saveUser(user);
    }
    
    @Transactional
    public void saveUser(User user) {
        userMapper.insert(user);
    }
}

// 解决方案1：注入自己
@Service
public class UserService {
    @Autowired
    private UserService self;
    
    public void createUser(User user) {
        self.saveUser(user);  // 走代理
    }
}

// 解决方案2：使用AopContext
@Service
public class UserService {
    public void createUser(User user) {
        ((UserService) AopContext.currentProxy()).saveUser(user);
    }
}
```

#### 3. 异常被捕获
```java
@Transactional
public void createUser(User user) {
    try {
        userMapper.insert(user);
    } catch (Exception e) {
        // 异常被捕获，事务不回滚
        log.error("创建用户失败", e);
    }
}

// 解决方案：手动回滚
@Transactional
public void createUser(User user) {
    try {
        userMapper.insert(user);
    } catch (Exception e) {
        TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
        throw e;
    }
}
```

#### 4. 异常类型不匹配
```java
@Transactional  // 默认只回滚RuntimeException和Error
public void createUser(User user) throws Exception {
    userMapper.insert(user);
    throw new Exception("业务异常");  // 不回滚
}

// 解决方案：指定异常类型
@Transactional(rollbackFor = Exception.class)
public void createUser(User user) throws Exception {
    userMapper.insert(user);
    throw new Exception("业务异常");  // 回滚
}
```

#### 5. 数据库不支持事务
```java
// MyISAM引擎不支持事务
CREATE TABLE user (
    id INT PRIMARY KEY
) ENGINE=MyISAM;

// 解决方案：使用InnoDB
CREATE TABLE user (
    id INT PRIMARY KEY
) ENGINE=InnoDB;
```

**项目实例：** 医疗平台统一使用InnoDB，所有事务方法都是public

---

## 四、Spring Boot（必问）

### 11. Spring Boot自动配置原理？
**答：**

**核心注解：@SpringBootApplication**
```java
@SpringBootApplication
= @SpringBootConfiguration  // 配置类
+ @EnableAutoConfiguration  // 自动配置
+ @ComponentScan           // 组件扫描
```

**自动配置流程：**
```
1. @EnableAutoConfiguration
   ↓
2. @Import(AutoConfigurationImportSelector.class)
   ↓
3. 读取 META-INF/spring.factories
   ↓
4. 加载所有自动配置类（xxxAutoConfiguration）
   ↓
5. 根据@Conditional条件判断是否生效
   ↓
6. 创建Bean并注入容器
```

**示例：RedisAutoConfiguration**
```java
@Configuration
@ConditionalOnClass(RedisOperations.class)  // 类路径存在RedisOperations
@EnableConfigurationProperties(RedisProperties.class)
public class RedisAutoConfiguration {
    
    @Bean
    @ConditionalOnMissingBean(name = "redisTemplate")  // 容器中不存在redisTemplate
    public RedisTemplate<Object, Object> redisTemplate(
            RedisConnectionFactory redisConnectionFactory) {
        RedisTemplate<Object, Object> template = new RedisTemplate<>();
        template.setConnectionFactory(redisConnectionFactory);
        return template;
    }
}
```

**常用@Conditional注解：**
- `@ConditionalOnClass`：类路径存在指定类
- `@ConditionalOnMissingBean`：容器中不存在指定Bean
- `@ConditionalOnProperty`：配置文件存在指定属性
- `@ConditionalOnWebApplication`：Web应用

**项目实例：** 医疗平台自定义Starter，实现自动配置

---

### 12. 如何自定义Starter？
**答：**

**步骤：**

**1. 创建Maven项目（xxx-spring-boot-starter）**
```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
    </dependency>
</dependencies>
```

**2. 创建配置属性类**
```java
@ConfigurationProperties(prefix = "sms")
public class SmsProperties {
    private String accessKey;
    private String secretKey;
    private String signName;
    
    // getter/setter
}
```

**3. 创建自动配置类**
```java
@Configuration
@EnableConfigurationProperties(SmsProperties.class)
@ConditionalOnClass(SmsService.class)
@ConditionalOnProperty(prefix = "sms", name = "enabled", havingValue = "true")
public class SmsAutoConfiguration {
    
    @Bean
    @ConditionalOnMissingBean
    public SmsService smsService(SmsProperties properties) {
        return new SmsService(properties);
    }
}
```

**4. 创建spring.factories**
```properties
# src/main/resources/META-INF/spring.factories
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.example.sms.SmsAutoConfiguration
```

**5. 使用Starter**
```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>sms-spring-boot-starter</artifactId>
    <version>1.0.0</version>
</dependency>
```

```yaml
# application.yml
sms:
  enabled: true
  access-key: xxx
  secret-key: xxx
  sign-name: xxx
```

```java
@Service
public class UserService {
    @Autowired
    private SmsService smsService;  // 自动注入
    
    public void sendCode(String phone) {
        smsService.send(phone, "验证码：123456");
    }
}
```

**项目实例：** 医疗平台自定义短信Starter，统一短信发送逻辑

### 13. Spring Boot配置文件加载顺序？
**答：**

**配置文件优先级（从高到低）：**
```
1. 命令行参数
   java -jar app.jar --server.port=8081

2. SPRING_APPLICATION_JSON环境变量

3. ServletConfig初始化参数

4. ServletContext初始化参数

5. JNDI属性

6. Java系统属性（System.getProperties()）

7. 操作系统环境变量

8. RandomValuePropertySource（random.*）

9. jar包外的application-{profile}.properties/yml

10. jar包内的application-{profile}.properties/yml

11. jar包外的application.properties/yml

12. jar包内的application.properties/yml

13. @PropertySource注解

14. 默认属性（SpringApplication.setDefaultProperties）
```

**配置文件位置优先级（从高到低）：**
```
1. file:./config/          # 当前目录的config子目录
2. file:./                 # 当前目录
3. classpath:/config/      # classpath的config目录
4. classpath:/             # classpath根目录
```

**多环境配置：**
```yaml
# application.yml（主配置）
spring:
  profiles:
    active: dev  # 激活dev环境

# application-dev.yml（开发环境）
server:
  port: 8080
spring:
  datasource:
    url: jdbc:mysql://localhost:3306/dev_db

# application-prod.yml（生产环境）
server:
  port: 80
spring:
  datasource:
    url: jdbc:mysql://prod-server:3306/prod_db
```

**项目实例：** 医疗平台使用dev、test、prod三套环境配置

---

### 14. Spring Boot常用注解？
**答：**

**启动类注解：**
```java
@SpringBootApplication  // 启动类
@EnableScheduling       // 开启定时任务
@EnableAsync           // 开启异步
@EnableCaching         // 开启缓存
@EnableTransactionManagement  // 开启事务（默认开启）
```

**配置类注解：**
```java
@Configuration         // 配置类
@Bean                 // 定义Bean
@ConfigurationProperties  // 绑定配置文件
@Value                // 注入单个属性
@PropertySource       // 指定配置文件
```

**条件注解：**
```java
@ConditionalOnClass           // 类路径存在指定类
@ConditionalOnMissingBean     // 容器中不存在指定Bean
@ConditionalOnProperty        // 配置文件存在指定属性
@ConditionalOnWebApplication  // Web应用
```

**Web注解：**
```java
@RestController       // RESTful控制器
@RequestMapping       // 请求映射
@GetMapping          // GET请求
@PostMapping         // POST请求
@RequestBody         // 请求体
@RequestParam        // 请求参数
@PathVariable        // 路径变量
@Validated           // 参数校验
```

**项目实例：** 医疗平台使用@Validated统一参数校验

---

## 五、Spring MVC（必问）

### 15. Spring MVC请求处理流程？
**答：**

**完整流程：**
```
1. 用户请求 → DispatcherServlet（前端控制器）
   ↓
2. DispatcherServlet → HandlerMapping（处理器映射器）
   查找Handler（Controller方法）
   ↓
3. HandlerMapping → DispatcherServlet
   返回HandlerExecutionChain（Handler + 拦截器）
   ↓
4. DispatcherServlet → HandlerAdapter（处理器适配器）
   执行Handler
   ↓
5. HandlerAdapter → Handler（Controller）
   执行业务逻辑
   ↓
6. Handler → HandlerAdapter
   返回ModelAndView
   ↓
7. HandlerAdapter → DispatcherServlet
   返回ModelAndView
   ↓
8. DispatcherServlet → ViewResolver（视图解析器）
   解析视图名称
   ↓
9. ViewResolver → DispatcherServlet
   返回View
   ↓
10. DispatcherServlet → View
    渲染视图
    ↓
11. View → 用户
    返回响应
```

**核心组件：**
- **DispatcherServlet**：前端控制器，统一处理请求
- **HandlerMapping**：处理器映射器，查找Handler
- **HandlerAdapter**：处理器适配器，执行Handler
- **ViewResolver**：视图解析器，解析视图

**项目实例：** 医疗平台使用@RestController，返回JSON，不需要视图解析

---

### 16. 如何实现统一异常处理？
**答：**

**方案1：@ControllerAdvice + @ExceptionHandler（推荐）**
```java
@RestControllerAdvice
@Slf4j
public class GlobalExceptionHandler {
    
    // 业务异常
    @ExceptionHandler(BusinessException.class)
    public Result handleBusinessException(BusinessException e) {
        log.error("业务异常: {}", e.getMessage());
        return Result.fail(e.getCode(), e.getMessage());
    }
    
    // 参数校验异常
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public Result handleValidException(MethodArgumentNotValidException e) {
        BindingResult result = e.getBindingResult();
        String message = result.getFieldErrors().stream()
            .map(FieldError::getDefaultMessage)
            .collect(Collectors.joining(", "));
        
        log.error("参数校验失败: {}", message);
        return Result.fail(400, message);
    }
    
    // SQL异常
    @ExceptionHandler(SQLException.class)
    public Result handleSQLException(SQLException e) {
        log.error("数据库异常", e);
        return Result.fail(500, "数据库异常，请联系管理员");
    }
    
    // 未知异常
    @ExceptionHandler(Exception.class)
    public Result handleException(Exception e) {
        log.error("系统异常", e);
        return Result.fail(500, "系统异常，请联系管理员");
    }
}
```

**自定义业务异常：**
```java
@Data
public class BusinessException extends RuntimeException {
    private Integer code;
    private String message;
    
    public BusinessException(Integer code, String message) {
        super(message);
        this.code = code;
        this.message = message;
    }
    
    public BusinessException(String message) {
        this(400, message);
    }
}
```

**使用：**
```java
@RestController
@RequestMapping("/user")
public class UserController {
    
    @PostMapping("/create")
    public Result createUser(@RequestBody @Validated UserDTO dto) {
        // 业务校验
        if (userService.existsByUsername(dto.getUsername())) {
            throw new BusinessException("用户名已存在");
        }
        
        userService.createUser(dto);
        return Result.success();
    }
}
```

**项目实例：** 医疗平台使用统一异常处理，前端统一处理错误信息

### 17. 拦截器和过滤器的区别？
**答：**

| 特性 | 过滤器（Filter） | 拦截器（Interceptor） |
|------|-----------------|---------------------|
| **规范** | Servlet规范 | Spring规范 |
| **依赖** | 依赖Servlet容器 | 依赖Spring容器 |
| **作用范围** | 所有请求 | Spring MVC请求 |
| **执行时机** | DispatcherServlet之前 | DispatcherServlet之后 |
| **访问Spring Bean** | 不能直接访问 | 可以访问 |
| **使用场景** | 编码、跨域、认证 | 权限校验、日志、性能监控 |

**执行顺序：**
```
Filter前置 → DispatcherServlet → Interceptor前置 → Controller → Interceptor后置 → Filter后置
```

**过滤器示例：**
```java
@Component
public class CorsFilter implements Filter {
    
    @Override
    public void doFilter(ServletRequest request, ServletResponse response, 
                         FilterChain chain) throws IOException, ServletException {
        HttpServletResponse resp = (HttpServletResponse) response;
        resp.setHeader("Access-Control-Allow-Origin", "*");
        resp.setHeader("Access-Control-Allow-Methods", "*");
        
        chain.doFilter(request, response);
    }
}
```

**拦截器示例：**
```java
@Component
public class AuthInterceptor implements HandlerInterceptor {
    
    @Autowired
    private UserService userService;
    
    @Override
    public boolean preHandle(HttpServletRequest request, 
                            HttpServletResponse response, 
                            Object handler) {
        String token = request.getHeader("Authorization");
        
        if (StringUtils.isEmpty(token)) {
            throw new BusinessException("未登录");
        }
        
        // 验证token
        User user = userService.getUserByToken(token);
        if (user == null) {
            throw new BusinessException("token无效");
        }
        
        // 存储用户信息
        UserContext.set(user);
        return true;
    }
    
    @Override
    public void afterCompletion(HttpServletRequest request, 
                               HttpServletResponse response, 
                               Object handler, Exception ex) {
        // 清理用户信息
        UserContext.remove();
    }
}

// 注册拦截器
@Configuration
public class WebConfig implements WebMvcConfigurer {
    
    @Autowired
    private AuthInterceptor authInterceptor;
    
    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(authInterceptor)
            .addPathPatterns("/**")
            .excludePathPatterns("/login", "/register");
    }
}
```

**项目实例：** 医疗平台使用拦截器实现登录校验、权限校验

---

## 六、项目场景深挖题（重点）

### 18. 如何实现全局参数校验？
**答：**

**1. 引入依赖**
```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

**2. DTO添加校验注解**
```java
@Data
public class UserDTO {
    
    @NotBlank(message = "用户名不能为空")
    @Length(min = 3, max = 20, message = "用户名长度3-20")
    private String username;
    
    @NotBlank(message = "密码不能为空")
    @Pattern(regexp = "^(?=.*[a-z])(?=.*[A-Z])(?=.*\\d)[a-zA-Z\\d]{8,}$", 
             message = "密码至少8位，包含大小写字母和数字")
    private String password;
    
    @NotBlank(message = "手机号不能为空")
    @Pattern(regexp = "^1[3-9]\\d{9}$", message = "手机号格式不正确")
    private String phone;
    
    @NotNull(message = "年龄不能为空")
    @Min(value = 1, message = "年龄最小为1")
    @Max(value = 150, message = "年龄最大为150")
    private Integer age;
    
    @NotBlank(message = "邮箱不能为空")
    @Email(message = "邮箱格式不正确")
    private String email;
}
```

**3. Controller添加@Validated**
```java
@RestController
@RequestMapping("/user")
@Validated
public class UserController {
    
    // 校验请求体
    @PostMapping("/create")
    public Result createUser(@RequestBody @Validated UserDTO dto) {
        userService.createUser(dto);
        return Result.success();
    }
    
    // 校验路径变量
    @GetMapping("/{id}")
    public Result getUser(@PathVariable @Min(1) Long id) {
        User user = userService.getById(id);
        return Result.success(user);
    }
    
    // 校验请求参数
    @GetMapping("/list")
    public Result listUsers(@RequestParam @Min(1) Integer page,
                           @RequestParam @Min(1) @Max(100) Integer size) {
        List<User> users = userService.list(page, size);
        return Result.success(users);
    }
}
```

**4. 统一异常处理**
```java
@RestControllerAdvice
public class GlobalExceptionHandler {
    
    // 处理@Validated校验异常（请求体）
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public Result handleValidException(MethodArgumentNotValidException e) {
        String message = e.getBindingResult().getFieldErrors().stream()
            .map(FieldError::getDefaultMessage)
            .collect(Collectors.joining(", "));
        return Result.fail(400, message);
    }
    
    // 处理@Validated校验异常（路径变量、请求参数）
    @ExceptionHandler(ConstraintViolationException.class)
    public Result handleConstraintViolationException(ConstraintViolationException e) {
        String message = e.getConstraintViolations().stream()
            .map(ConstraintViolation::getMessage)
            .collect(Collectors.joining(", "));
        return Result.fail(400, message);
    }
}
```

**5. 自定义校验注解**
```java
// 自定义注解
@Target({ElementType.FIELD})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = IdCardValidator.class)
public @interface IdCard {
    String message() default "身份证号格式不正确";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}

// 校验器
public class IdCardValidator implements ConstraintValidator<IdCard, String> {
    
    @Override
    public boolean isValid(String value, ConstraintValidatorContext context) {
        if (StringUtils.isEmpty(value)) {
            return true;
        }
        // 身份证号校验逻辑
        return value.matches("^[1-9]\\d{5}(18|19|20)\\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\\d|3[01])\\d{3}[\\dXx]$");
    }
}

// 使用
@Data
public class UserDTO {
    @IdCard(message = "身份证号格式不正确")
    private String idCard;
}
```

**项目实例：** 医疗平台所有接口都使用@Validated校验参数

---

### 19. 如何实现接口幂等性？
**答：**

**幂等性：** 同一个请求多次执行，结果一致

**应用场景：**
- 订单创建
- 支付
- 退款

**方案1：Token机制（推荐）**
```java
// 1. 自定义注解
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface Idempotent {
    long timeout() default 300;  // 超时时间（秒）
}

// 2. AOP切面
@Aspect
@Component
public class IdempotentAspect {
    
    @Autowired
    private RedisTemplate<String, String> redisTemplate;
    
    @Around("@annotation(idempotent)")
    public Object around(ProceedingJoinPoint pjp, Idempotent idempotent) throws Throwable {
        HttpServletRequest request = ((ServletRequestAttributes) 
            RequestContextHolder.getRequestAttributes()).getRequest();
        
        // 获取幂等token
        String token = request.getHeader("Idempotent-Token");
        if (StringUtils.isEmpty(token)) {
            throw new BusinessException("缺少幂等token");
        }
        
        // 检查token是否存在
        String key = "idempotent:" + token;
        Boolean success = redisTemplate.opsForValue()
            .setIfAbsent(key, "1", idempotent.timeout(), TimeUnit.SECONDS);
        
        if (Boolean.FALSE.equals(success)) {
            throw new BusinessException("请勿重复提交");
        }
        
        try {
            // 执行业务
            return pjp.proceed();
        } catch (Exception e) {
            // 失败删除token，允许重试
            redisTemplate.delete(key);
            throw e;
        }
    }
}

// 3. 使用
@RestController
@RequestMapping("/order")
public class OrderController {
    
    // 获取幂等token
    @GetMapping("/token")
    public Result getToken() {
        String token = UUID.randomUUID().toString();
        return Result.success(token);
    }
    
    // 创建订单（幂等）
    @PostMapping("/create")
    @Idempotent(timeout = 300)
    public Result createOrder(@RequestBody OrderDTO dto) {
        orderService.createOrder(dto);
        return Result.success();
    }
}
```

**方案2：唯一索引**
```sql
-- 订单表添加唯一索引
CREATE UNIQUE INDEX uk_order_no ON t_order(order_no);
```

```java
@PostMapping("/create")
public Result createOrder(@RequestBody OrderDTO dto) {
    try {
        orderMapper.insert(order);
    } catch (DuplicateKeyException e) {
        // 订单已存在，返回成功
        return Result.success();
    }
}
```

**项目实例：** 电商平台订单创建使用Token机制保证幂等性

### 20. 如何实现接口限流？
**答：**

**方案1：Guava RateLimiter（单机限流）**
```java
// 1. 自定义注解
@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface RateLimit {
    double value() default 10.0;  // 每秒允许请求数
}

// 2. AOP切面
@Aspect
@Component
public class RateLimitAspect {
    
    private final Map<String, RateLimiter> limiters = new ConcurrentHashMap<>();
    
    @Around("@annotation(rateLimit)")
    public Object around(ProceedingJoinPoint pjp, RateLimit rateLimit) throws Throwable {
        String key = pjp.getSignature().toString();
        
        // 获取或创建限流器
        RateLimiter limiter = limiters.computeIfAbsent(key, 
            k -> RateLimiter.create(rateLimit.value()));
        
        // 尝试获取令牌
        if (!limiter.tryAcquire()) {
            throw new BusinessException("请求过于频繁，请稍后重试");
        }
        
        return pjp.proceed();
    }
}

// 3. 使用
@RestController
@RequestMapping("/user")
public class UserController {
    
    @GetMapping("/list")
    @RateLimit(value = 10.0)  // 每秒10个请求
    public Result listUsers() {
        return Result.success(userService.list());
    }
}
```

**方案2：Redis + Lua（分布式限流，推荐）**
```java
// 1. Lua脚本（滑动窗口）
String script = 
    "local key = KEYS[1] " +
    "local limit = tonumber(ARGV[1]) " +
    "local window = tonumber(ARGV[2]) " +
    "local now = tonumber(ARGV[3]) " +
    "local windowStart = now - window " +
    
    "redis.call('zremrangebyscore', key, 0, windowStart) " +
    "local count = redis.call('zcard', key) " +
    
    "if count < limit then " +
    "    redis.call('zadd', key, now, now) " +
    "    redis.call('expire', key, window) " +
    "    return 1 " +
    "else " +
    "    return 0 " +
    "end";

// 2. AOP切面
@Aspect
@Component
public class RateLimitAspect {
    
    @Autowired
    private RedisTemplate<String, String> redisTemplate;
    
    @Around("@annotation(rateLimit)")
    public Object around(ProceedingJoinPoint pjp, RateLimit rateLimit) throws Throwable {
        String userId = SecurityUtils.getCurrentUserId();
        String key = "rate:limit:" + pjp.getSignature().getName() + ":" + userId;
        
        long now = System.currentTimeMillis();
        
        Long result = redisTemplate.execute(
            new DefaultRedisScript<>(script, Long.class),
            Collections.singletonList(key),
            String.valueOf(rateLimit.count()),
            String.valueOf(rateLimit.period() * 1000),
            String.valueOf(now)
        );
        
        if (result == 0) {
            throw new BusinessException("请求过于频繁，请稍后重试");
        }
        
        return pjp.proceed();
    }
}
```

**方案3：Sentinel（推荐）**
```java
@RestController
@RequestMapping("/user")
public class UserController {
    
    @GetMapping("/list")
    @SentinelResource(value = "listUsers", blockHandler = "handleBlock")
    public Result listUsers() {
        return Result.success(userService.list());
    }
    
    public Result handleBlock(BlockException ex) {
        return Result.fail("请求过于频繁，请稍后重试");
    }
}
```

**项目实例：** 医疗平台使用Sentinel限流，保护核心接口

---

## 七、生产事故深挖题（重点）

### 21. 生产事故：事务失效导致数据不一致
**场景：** 订单创建后，库存未扣减，数据不一致

**排查过程：**
```java
@Service
public class OrderService {
    
    @Autowired
    private StockService stockService;
    
    @Transactional
    public void createOrder(Order order) {
        // 1. 创建订单
        orderMapper.insert(order);
        
        // 2. 扣减库存（同类方法调用，事务失效）
        this.deductStock(order.getProductId(), order.getQuantity());
    }
    
    @Transactional
    public void deductStock(Long productId, Integer quantity) {
        stockMapper.deduct(productId, quantity);
    }
}
```

**问题原因：**
- 同类方法调用，没有走代理
- `this.deductStock()` 直接调用，事务失效

**解决方案：**
```java
// 方案1：注入自己
@Service
public class OrderService {
    
    @Autowired
    private OrderService self;
    
    @Transactional
    public void createOrder(Order order) {
        orderMapper.insert(order);
        
        // 通过代理调用
        self.deductStock(order.getProductId(), order.getQuantity());
    }
    
    @Transactional
    public void deductStock(Long productId, Integer quantity) {
        stockMapper.deduct(productId, quantity);
    }
}

// 方案2：拆分到不同Service
@Service
public class OrderService {
    
    @Autowired
    private StockService stockService;
    
    @Transactional
    public void createOrder(Order order) {
        orderMapper.insert(order);
        
        // 调用其他Service
        stockService.deductStock(order.getProductId(), order.getQuantity());
    }
}

@Service
public class StockService {
    
    @Transactional
    public void deductStock(Long productId, Integer quantity) {
        stockMapper.deduct(productId, quantity);
    }
}
```

**项目实例：** 电商平台订单创建事务失效，拆分Service后解决

---

### 22. 生产事故：循环依赖导致启动失败
**场景：** 应用启动失败，报错循环依赖

**错误信息：**
```
Error creating bean with name 'orderService': 
Requested bean is currently in creation: Is there an unresolvable circular reference?
```

**问题代码：**
```java
@Service
public class OrderService {
    
    @Autowired
    private UserService userService;
    
    public OrderService(UserService userService) {  // 构造器注入
        this.userService = userService;
    }
}

@Service
public class UserService {
    
    @Autowired
    private OrderService orderService;
    
    public UserService(OrderService orderService) {  // 构造器注入
        this.orderService = orderService;
    }
}
```

**问题原因：**
- 构造器注入循环依赖
- Spring无法解决构造器注入的循环依赖

**解决方案：**
```java
// 方案1：改为Setter注入
@Service
public class OrderService {
    
    @Autowired
    private UserService userService;  // Setter注入
}

@Service
public class UserService {
    
    @Autowired
    private OrderService orderService;  // Setter注入
}

// 方案2：使用@Lazy延迟加载
@Service
public class OrderService {
    
    private final UserService userService;
    
    public OrderService(@Lazy UserService userService) {
        this.userService = userService;
    }
}

// 方案3：重构代码，消除循环依赖（推荐）
// 将公共逻辑抽取到第三个Service
@Service
public class CommonService {
    // 公共逻辑
}

@Service
public class OrderService {
    @Autowired
    private CommonService commonService;
}

@Service
public class UserService {
    @Autowired
    private CommonService commonService;
}
```

**项目实例：** 医疗平台重构代码，消除循环依赖

---

### 23. 生产事故：内存泄漏导致OOM
**场景：** 应用运行一段时间后，内存持续增长，最终OOM

**排查过程：**
```bash
# 1. 查看堆内存使用
jmap -heap <pid>

# 2. 导出堆转储文件
jmap -dump:format=b,file=heap.hprof <pid>

# 3. 使用MAT分析
# 发现ThreadLocal未清理
```

**问题代码：**
```java
@Component
public class UserContext {
    
    private static final ThreadLocal<User> USER_HOLDER = new ThreadLocal<>();
    
    public static void set(User user) {
        USER_HOLDER.set(user);
    }
    
    public static User get() {
        return USER_HOLDER.get();
    }
    
    // 忘记清理
}

@Component
public class AuthInterceptor implements HandlerInterceptor {
    
    @Override
    public boolean preHandle(HttpServletRequest request, 
                            HttpServletResponse response, 
                            Object handler) {
        User user = getUserFromToken(request);
        UserContext.set(user);  // 设置用户信息
        return true;
    }
    
    // 没有清理ThreadLocal
}
```

**问题原因：**
- ThreadLocal未清理
- Tomcat线程池复用线程，ThreadLocal一直存在
- 内存泄漏

**解决方案：**
```java
@Component
public class UserContext {
    
    private static final ThreadLocal<User> USER_HOLDER = new ThreadLocal<>();
    
    public static void set(User user) {
        USER_HOLDER.set(user);
    }
    
    public static User get() {
        return USER_HOLDER.get();
    }
    
    // 添加清理方法
    public static void remove() {
        USER_HOLDER.remove();
    }
}

@Component
public class AuthInterceptor implements HandlerInterceptor {
    
    @Override
    public boolean preHandle(HttpServletRequest request, 
                            HttpServletResponse response, 
                            Object handler) {
        User user = getUserFromToken(request);
        UserContext.set(user);
        return true;
    }
    
    @Override
    public void afterCompletion(HttpServletRequest request, 
                               HttpServletResponse response, 
                               Object handler, Exception ex) {
        // 清理ThreadLocal
        UserContext.remove();
    }
}
```

**项目实例：** 医疗平台添加ThreadLocal清理逻辑，解决内存泄漏

---

## 八、面试准备清单

### 必须掌握
- [ ] IOC/DI原理
- [ ] Bean生命周期
- [ ] AOP原理及应用
- [ ] 事务传播机制
- [ ] @Transactional失效场景
- [ ] Spring Boot自动配置原理
- [ ] Spring MVC请求流程

### 加分项
- [ ] 自定义Starter
- [ ] 统一异常处理
- [ ] 参数校验
- [ ] 接口幂等性
- [ ] 接口限流
- [ ] 拦截器vs过滤器

### 项目经验准备（重点）
准备3-5个具体场景，能讲清楚：
1. **背景**：什么业务场景
2. **方案**：如何设计的，为什么这样设计
3. **难点**：遇到什么问题，如何解决
4. **结果**：优化效果，具体数据

**示例：**
> "在医疗平台中，我们使用AOP实现操作日志。通过自定义@OperationLog注解，在切面中记录用户操作、IP、参数、耗时等信息。优化后，日志记录对业务代码零侵入，所有敏感操作都有审计记录。"

### 常见追问
- "Spring Boot如何实现自动配置？" → @EnableAutoConfiguration + spring.factories
- "事务什么时候会失效？" → 准备5种失效场景
- "如何解决循环依赖？" → 三级缓存 + 重构代码
- "遇到过内存泄漏吗？" → ThreadLocal未清理

---

## 九、面试技巧

### 回答问题的套路
1. **先说结论**：直接回答问题
2. **再说原理**：简要说明原理
3. **举例说明**：结合项目经验
4. **总结优化**：说明优化点

**示例：**
> **问：如何实现接口幂等性？**
> 
> **答：**
> 1. **结论**：我们使用Token机制实现接口幂等性
> 2. **原理**：前端先获取幂等Token，提交时携带Token，后端通过Redis的SETNX保证Token只能使用一次
> 3. **举例**：在电商平台订单创建接口中，用户点击提交按钮时，先获取Token，然后携带Token创建订单，防止重复提交
> 4. **优化**：优化后，重复订单从100单/天降到0

### 主动引导话题
- "在这个项目中，我还遇到了一个有意思的问题..."
- "针对这个场景，我们做了一些优化..."
- "这让我想到了另一个类似的场景..."

### 数据说话
- "优化后，接口RT从500ms降到50ms"
- "日志记录对业务代码零侵入"
- "重复订单从100单/天降到0"

---

**Spring框架面试题全部完成！共23道题，涵盖Spring Core、AOP、事务、Spring Boot、Spring MVC、项目场景、生产事故等核心知识点。**

