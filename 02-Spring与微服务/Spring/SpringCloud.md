# Spring Cloud：组件、调用与治理

> [!info] 文档定位
> 本文覆盖 Spring Cloud 的常用组件、客户端负载均衡和 Sentinel 治理实践。默认面向 Spring Boot 3.x 与较新的 Spring Cloud Release Train；Netflix Ribbon、Hystrix、Spring Cloud Sleuth 和注解式 Stream API 仅用于识别存量项目。

## 目录

- [[#一、组件总览]]：注册发现、调用、配置、网关、链路追踪与消息
- [[#二、Spring Cloud LoadBalancer]]：实例选择、接入方式与扩展
- [[#三、Sentinel：熔断与限流]]：规则配置与工程接入
- [[#四、Sentinel 熔断与降级原理]]：统计、状态转换与降级边界

---

## 一、组件总览

### 1. 服务注册、调用与容错

Eureka 仍可用于服务注册与发现；但 Ribbon、Hystrix 已停止维护，不应作为新项目默认选型。新项目通常使用 Spring Cloud LoadBalancer，并按团队生态选择 Resilience4j 或 Sentinel 实现容错与限流。

#### (1) Eureka（服务注册与发现）

Eureka 是 Netflix 提供的服务注册与发现组件，微服务启动时会向 Eureka Server 注册，其他服务可以从 Eureka 获取服务地址并进行调用。

**使用步骤：**

- 在 `Eureka Server` 中：
    
    ```java
    @SpringBootApplication
    @EnableEurekaServer
    public class EurekaServerApplication {
        public static void main(String[] args) {
            SpringApplication.run(EurekaServerApplication.class, args);
        }
    }
    ```
    
- 在 `Eureka Client` 中：
    
    ```java
    @SpringBootApplication
    @EnableDiscoveryClient
    public class OrderServiceApplication {
        public static void main(String[] args) {
            SpringApplication.run(OrderServiceApplication.class, args);
        }
    }
    ```
    

#### (2) Spring Cloud LoadBalancer（客户端负载均衡）

`@LoadBalanced` 的 `RestTemplate` 示例在较新版本中由 Spring Cloud LoadBalancer 提供支持；它从注册中心获取实例并选择一个实例发起请求。

```java
@Bean
@LoadBalanced
public RestTemplate restTemplate() {
    return new RestTemplate();
}
```

#### (3) OpenFeign（声明式 HTTP 客户端）

Spring Cloud OpenFeign 适合维护既有的声明式客户端；该项目已进入功能完整（feature-complete）状态，新项目应优先评估 Spring Framework 的 HTTP Service Clients。若继续使用 OpenFeign，需显式引入并配置 `spring-cloud-starter-loadbalancer`，同时为下游调用设定连接/读取超时、只对幂等请求启用受控重试，并接入 Micrometer 的指标与链路追踪。

```java
@FeignClient(name = "order-service")
public interface OrderClient {
    @GetMapping("/orders/{orderId}")
    String getOrder(@PathVariable("orderId") String orderId);
}
```

#### (4) 容错：Resilience4j / Sentinel；Hystrix 为历史方案

Hystrix 的以下代码仅用于阅读旧项目。新项目可用 Resilience4j 实现断路器、重试和限流；使用 Spring Cloud Alibaba + Nacos 时，Sentinel 还提供规则动态配置与热点参数限流。

```java
@HystrixCommand(fallbackMethod = "fallback")
public String getOrder(String orderId) {
    return restTemplate.getForObject("http://order-service/orders/" + orderId, String.class);
}
public String fallback(String orderId) {
    return "Service is currently unavailable!";
}
```

---

### 2. Spring Cloud Config（分布式配置中心）

Spring Cloud Config 允许将应用的配置集中管理，通常存储在 Git 或本地文件系统中，所有微服务可以动态拉取最新配置。

#### (1) 创建 Config Server

```java
@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
```

#### (2) 客户端使用 Config

推荐使用 Config Data API，在 `application.yml` 中配置：

```yaml
spring:
  application:
    name: order-service
  config:
    import: optional:configserver:http://localhost:8888
```

`bootstrap.yml` 仍可通过额外的 bootstrap 支持使用，但属于兼容旧项目的方式；不要在同一应用中混用两套加载模型而不明确优先级。

---

### 3. Spring Cloud Gateway（API 网关）

Spring Cloud Gateway 是 Spring 官方推出的 API 网关，它提供了路由、负载均衡、认证、限流等功能。

#### (1) 配置 Gateway

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: order-service
          uri: lb://order-service
          predicates:
            - Path=/orders/**
```

#### (2) 启动 Gateway

```java
@SpringBootApplication
public class ApiGatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiGatewayApplication.class, args);
    }
}
```

---

### 4. Micrometer Tracing（分布式链路追踪）

Spring Boot 3.x 的链路追踪以 Micrometer Tracing 为主，可按所选实现桥接到 Brave 或 OpenTelemetry，并将追踪数据导出到 Zipkin、Tempo 等后端。Spring Cloud Sleuth 3.1 已功能冻结，以下不再把它作为新项目依赖。

#### (1) 引入 Tracing 与 Zipkin 导出器

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-tracing-bridge-brave</artifactId>
</dependency>
<dependency>
    <groupId>io.zipkin.reporter2</groupId>
    <artifactId>zipkin-reporter-brave</artifactId>
</dependency>
```

```yaml
spring:
  application:
    name: order-service
management:
  tracing:
    sampling:
      probability: 1.0 # 生产环境应根据流量和成本设置采样率
  zipkin:
    tracing:
      endpoint: http://localhost:9411/api/v2/spans
```

---

### 5. Spring Cloud Stream（消息驱动）

Spring Cloud Stream 用于构建基于消息的微服务，支持 Kafka、RabbitMQ 等。

#### (1) 创建消息生产者

```java
@Configuration
public class MessageFunctions {
    @Bean
    public Supplier<String> producer() {
        return () -> "hello";
    }

    @Bean
    public Consumer<String> consumer() {
        return msg -> System.out.println("Received message: " + msg);
    }
}
```

#### (2) 配置函数绑定

```yaml
spring:
  cloud:
    function:
      definition: producer;consumer
    stream:
      bindings:
        producer-out-0:
          destination: orders
        consumer-in-0:
          destination: orders
```

较新的 Spring Cloud Stream 使用函数式模型；`@EnableBinding`、`Source`、`Sink`、`@StreamListener` 是 3.x 以前的注解式模型，阅读旧项目时再使用。

---

### 小结

| 组件                     | 作用                                      |
| ------------------------ | ----------------------------------------- |
| **服务注册、调用与容错** | 注册发现可使用 Eureka/Nacos；负载均衡使用 LoadBalancer；容错按生态选择 Resilience4j 或 Sentinel |
| **Spring Cloud Config**  | 分布式配置中心，集中管理微服务配置        |
| **Spring Cloud Gateway** | 统一 API 网关，提供路由、过滤、认证等功能 |
| **Micrometer Tracing**   | 分布式链路追踪，监控微服务间调用链路      |
| **Spring Cloud Stream**  | 消息驱动，支持 Kafka、RabbitMQ 等消息队列 |

---

这些能力可以组合使用，但具体依赖和配置必须与 Spring Boot、Spring Cloud release train、Spring Cloud Alibaba 版本保持兼容。

## 二、Spring Cloud LoadBalancer

Spring Cloud LoadBalancer 是 Spring Cloud 2020+ 中取代 Ribbon 的客户端实例选择组件。它从实例列表中选择目标实例；默认轮询策略并不感知 CPU、连接数或业务负载，因此不能单独保证“均匀分配”或避免过载。生产环境仍应配合健康检查、超时、熔断、限流和容量治理。

---

### 1. 核心概念

Spring Cloud LoadBalancer 作为 **Spring Cloud Commons** 组件的一部分，主要提供以下功能：

1. **动态服务发现**：基于 **Spring Cloud Discovery Client** 获取可用的服务实例。
2. **负载均衡策略**：默认实现是 **轮询（RoundRobinLoadBalancer）**；也可选用 **随机（RandomLoadBalancer）** 或自行扩展策略。
3. **与 RestTemplate、WebClient、Feign 结合**：支持多种方式进行负载均衡调用。
4. **集成 Spring Cloud Gateway**：让网关作为调用方，在转发至后端服务时完成客户端实例选择。

---

### 2. 工作原理

#### (1) 负载均衡的核心组件

Spring Cloud LoadBalancer 主要由以下几个核心组件组成：

- **ServiceInstanceListSupplier**：用于从注册中心（如 Nacos、Eureka）获取可用的服务实例列表。
- **ReactorLoadBalancer**：实现负载均衡策略，决定请求如何分配到不同的服务实例。
- **LoadBalancerClient**：封装负载均衡逻辑，为 `RestTemplate`、`WebClient`、`Feign` 提供支持。

#### (2) 负载均衡流程

1. **服务发现**：`ServiceInstanceListSupplier` 从服务注册中心获取可用实例列表。
2. **选择实例**：`ReactorLoadBalancer` 根据负载均衡策略（如轮询、随机）选择一个实例。
3. **请求转发**：`LoadBalancerClient` 选择实例后，将请求转发到该实例的 IP 和端口。

---

### 3. 在 RestTemplate 中使用 LoadBalancer

在 Spring Cloud 2020+ 版本，RestTemplate 需要使用 `@LoadBalanced` 进行负载均衡。

#### (1) 引入 LoadBalancer 依赖

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

#### (2) 配置 `RestTemplate`

```java
@Configuration
public class LoadBalancerConfig {

    @Bean
    @LoadBalanced  // 启用 Spring Cloud LoadBalancer
    public RestTemplate restTemplate() {
        return new RestTemplate();
    }
}
```

#### (3) 通过 `RestTemplate` 进行服务调用

```java
@Autowired
private RestTemplate restTemplate;

public String getProductInfo(String productId) {
    return restTemplate.getForObject("http://product-service/products/" + productId, String.class);
}
```

- `http://product-service/products/{productId}` 中的 `product-service` 是注册在 Nacos 或 Eureka 的服务名称，`RestTemplate` 通过 LoadBalancer 选择一个实例并进行请求。

---

### 4. 在 WebClient 中使用 LoadBalancer

WebClient 是 Spring 5+ 的非阻塞式 HTTP 客户端，它可以与 LoadBalancer 结合使用。

#### (1) 配置 `WebClient`

```java
@Bean
@LoadBalanced
public WebClient.Builder webClientBuilder() {
    return WebClient.builder();
}
```

#### (2) 通过 WebClient 进行负载均衡调用

```java
@Autowired
private WebClient.Builder webClientBuilder;

public Mono<String> getProduct(String productId) {
    return webClientBuilder.build()
            .get()
            .uri("http://product-service/products/" + productId)
            .retrieve()
            .bodyToMono(String.class);
}
```

---

### 5. 在 OpenFeign 中使用 LoadBalancer

OpenFeign 只有在类路径上存在 `spring-cloud-starter-loadbalancer` 时，才会通过 Spring Cloud LoadBalancer 选择服务实例；仅引入 OpenFeign starter 并不等于已经启用客户端负载均衡。

#### (1) 引入 Feign 依赖

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-openfeign</artifactId>
</dependency>
```

#### (2) 启用 Feign

在 Spring Boot 启动类上添加 `@EnableFeignClients`：

```java
@SpringBootApplication
@EnableDiscoveryClient
@EnableFeignClients
public class ProductServiceApplication {
    public static void main(String[] args) {
        SpringApplication.run(ProductServiceApplication.class, args);
    }
}
```

#### (3) 定义 Feign 客户端

```java
@FeignClient(name = "order-service")
public interface OrderClient {

    @GetMapping("/orders/{id}")
    String getOrder(@PathVariable("id") String id);
}
```

#### (4) 通过 FeignClient 进行调用

```java
@Autowired
private OrderClient orderClient;

public String fetchOrder(String orderId) {
    return orderClient.getOrder(orderId);
}
```

若已引入 LoadBalancer starter，调用 `order-service` 时会由 Spring Cloud LoadBalancer 选择可用实例。上线前还应明确连接/读取超时、重试范围（仅幂等操作）以及 Micrometer 指标和链路追踪。

---

### 6. 自定义负载均衡策略

Spring Cloud LoadBalancer 默认使用 **RoundRobin（轮询）** 策略。可以为特定服务接入 **随机（Random）** 或自定义的 `ReactorLoadBalancer`；“最少连接”不是内置策略，若确有需要，应自行维护所需的连接/负载指标并实现选择逻辑。

#### (1) 自定义 LoadBalancer 规则

创建一个 `LoadBalancerConfiguration` 类：

```java
@Configuration
public class CustomLoadBalancerConfig {

    @Bean
    ReactorLoadBalancer<ServiceInstance> randomLoadBalancer(Environment environment,
                                                            LoadBalancerClientFactory factory) {
        String name = environment.getProperty(LoadBalancerClientFactory.PROPERTY_NAME);
        return new RandomLoadBalancer(factory.getLazyProvider(name, ServiceInstanceListSupplier.class), name);
    }
}
```

#### (2) 将规则绑定到指定服务

```java
@Configuration
@LoadBalancerClient(
        value = "product-service",
        configuration = CustomLoadBalancerConfig.class)
public class ProductServiceLoadBalancerConfiguration {
}
```

`CustomLoadBalancerConfig` 不应被主应用的组件扫描直接扫描到；上述配置只会让 `product-service` 使用随机策略。

---

### 7. Spring Cloud Gateway 结合 LoadBalancer

Spring Cloud Gateway 作为 API 网关，可以在转发到后端服务时使用 LoadBalancer 进行客户端实例选择。

#### (1) Gateway 配置

```yaml
spring:
  cloud:
    gateway:
      routes:
        - id: order-service
          uri: lb://order-service
          predicates:
            - Path=/orders/**
```

- **`lb://order-service`** 表示使用 Spring Cloud LoadBalancer 进行负载均衡。

---

### 8. Spring Cloud LoadBalancer vs Ribbon

Spring Cloud LoadBalancer 取代了 Ribbon，并进行了许多优化：

| **对比项**       | **Ribbon**       | **Spring Cloud LoadBalancer**  |
| ---------------- | ---------------- | ------------------------------ |
| **是否维护**     | 2020 之后被弃用  | 仍在维护                       |
| **负载均衡策略** | 轮询、随机、加权 | 轮询、随机、自定义             |
| **异步支持**     | 不支持           | 原生支持 Reactor 异步          |
| **可扩展性**     | 需要继承 `IRule` | 直接扩展 `ReactorLoadBalancer` |

---

### 小结

- **Spring Cloud LoadBalancer** 是 **Ribbon 的官方替代方案**，支持 **RestTemplate、WebClient、Feign、Spring Cloud Gateway** 等。
- **默认使用轮询策略**，也可使用随机策略或通过 **自定义 `ReactorLoadBalancer`** 实现特定的选择逻辑。
- **相比 Ribbon，LoadBalancer 支持异步编程**，并与 Spring Reactor 深度集成，更适合现代微服务架构。

## 三、Sentinel：熔断与限流

如果项目采用 **Spring Cloud Alibaba + Nacos**，Sentinel 是与该生态集成度很高的治理方案；若更偏向纯 Java 库和代码化配置，也可评估 Resilience4j。选型应看规则动态化、可观测性和团队运维方式，而非将任何一个方案视为绝对默认。

### 1. 为什么选择 Sentinel？

✅ **官方推荐**：Sentinel 是阿里巴巴团队开发的，**Spring Cloud Alibaba** 原生集成了 Sentinel，适配性更好。  
✅ **治理能力完整**：Sentinel 支持熔断降级、限流、热点参数限流和系统保护，尤其适合需要控制台与动态规则的场景。
✅ **可视化控制台**：Sentinel 提供了一个 **Web 控制台**，可以动态调整熔断、限流规则，而不用重启服务。  
✅ **与 Nacos 无缝结合**：可以 **从 Nacos 读取限流规则**，实现动态限流。

---

### 2. 如何在 Spring Cloud Alibaba（Nacos）中使用 Sentinel？

#### （1）引入 Sentinel 依赖

在 `pom.xml` 中添加以下依赖：

```xml
<dependency>
    <groupId>com.alibaba.cloud</groupId>
    <artifactId>spring-cloud-starter-alibaba-sentinel</artifactId>
</dependency>
```

---

#### （2）配置 Sentinel

在 `application.yml` 配置 Sentinel：

```yaml
spring:
  application:
    name: order-service
  cloud:
    nacos:
      discovery:
        server-addr: localhost:8848  # Nacos 服务器地址
    sentinel:
      transport:
        dashboard: localhost:8080  # Sentinel 控制台地址
        port: 8719  # 本地 Sentinel 监听端口
```

> **💡 启动 Sentinel 控制台** 你可以从 [Sentinel GitHub](https://github.com/alibaba/Sentinel) 下载 `sentinel-dashboard.jar`，然后运行：
> 
> ```sh
> java -jar sentinel-dashboard.jar
> ```
> 
> 访问 `http://localhost:8080` 进入 Sentinel 控制台。

---

#### （3）在 FeignClient 上启用 Sentinel

默认情况下，**Spring Cloud OpenFeign** 结合 Sentinel 时，需要手动开启 Sentinel 支持。

##### ① 在 `application.yml` 启用 Feign + Sentinel

```yaml
feign:
  sentinel:
    enabled: true
```

##### ② 定义 FeignClient

```java
@FeignClient(name = "product-service", fallback = ProductFallback.class)
public interface ProductClient {
    @GetMapping("/products/{id}")
    String getProduct(@PathVariable("id") String id);
}
```

##### ③ 创建 `ProductFallback` 降级逻辑

```java
@Component
public class ProductFallback implements ProductClient {
    @Override
    public String getProduct(String id) {
        return "Product service is down. Returning default product.";
    }
}
```

---

#### （4）在 Controller 上使用 Sentinel 熔断

如果你希望在 `RestController` 方法上直接加熔断，可以使用 `@SentinelResource`。

```java
import com.alibaba.csp.sentinel.slots.block.BlockException;

@RestController
@RequestMapping("/orders")
public class OrderController {

    @Autowired
    private ProductClient productClient;

    @GetMapping("/{id}")
    @SentinelResource(
        value = "getOrder",
        fallback = "fallbackGetOrder",
        blockHandler = "handleGetOrderBlocked"
    )
    public String getOrder(@PathVariable("id") String id) {
        return productClient.getProduct(id);
    }

    // 业务方法抛出异常时的降级方法
    public String fallbackGetOrder(String id, Throwable throwable) {
        return "Order Service is temporarily unavailable. Please try again later.";
    }

    // 被 Sentinel 限流或熔断时的处理方法
    public String handleGetOrderBlocked(String id, BlockException exception) {
        return "Too many requests or the service is temporarily blocked.";
    }
}
```

---

### 3. 限流（流控）配置

#### （1）在 Sentinel 控制台添加限流规则

1. 启动 Sentinel 控制台 `http://localhost:8080`
2. 在 **流控规则** 中，添加：
    - 资源名称：`getOrder`
    - 限流模式：**QPS**
    - 限流阈值：**2**
3. 这样，`/orders/{id}` 的请求每秒最多允许 2 个，超过后就会触发限流。

---

### 4. 熔断规则

#### （1）在 Sentinel 控制台添加熔断规则

1. 在 **熔断降级** 规则中，添加：
    - 资源名称：`getOrder`
    - 熔断策略：**失败率**（比如 50%）
    - 熔断时间：**10 秒**
2. 当 `getOrder` 方法的请求失败率超过 50% 时，Sentinel 会直接熔断该接口 10 秒，期间所有请求都不会调用真实的 `product-service`，而是进入降级方法。

---

### 5. Nacos + Sentinel 配置动态化

如果你希望 **将 Sentinel 限流、熔断规则存储在 Nacos**，可以：

```yaml
spring:
  cloud:
    sentinel:
      datasource:
        flow-rule:
          nacos:
            server-addr: localhost:8848
            dataId: sentinel-flow-rules
            groupId: DEFAULT_GROUP
            rule-type: flow
```

然后在 Nacos 的 `sentinel-flow-rules` 配置项中，写入 JSON 格式的限流规则。

---

### 6. Sentinel vs Resilience4j

如果你使用 **Spring Cloud Alibaba**（Nacos），那 **Sentinel** 是最佳选择。但如果你没有使用 Alibaba 生态，建议用 **Resilience4j**。

| 特性         | Sentinel                               | Resilience4j                         |
| ------------ | -------------------------------------- | ------------------------------------ |
| 维护方       | 阿里巴巴                               | resilience4j 社区                    |
| 适用场景     | **Nacos、Dubbo、Spring Cloud Alibaba** | 独立 Java 应用、Spring Boot 应用     |
| 熔断策略     | **慢调用、异常比例、异常数**           | **失败率、慢调用**                   |
| 限流         | **支持**                               | **支持 `RateLimiter` 模块**          |
| 控制台       | **有 Sentinel Dashboard**              | 无官方默认控制台                      |
| 规则动态配置 | 可通过 Nacos 等数据源接入              | 需自行结合配置中心与刷新机制         |

---

### 7. 小结

- **你使用 Spring Cloud Alibaba + Nacos，最佳选择是 Sentinel**
- **Sentinel 适用于熔断、限流、降级、热点流控**
- **FeignClient 可以通过 `fallback` 方式实现服务降级**
- **Sentinel 控制台可以动态配置熔断、限流规则**
- **可以将规则存储到 Nacos，实现动态更新**

---

## 四、Sentinel 熔断与降级原理

### 1. 基本概念

在 **分布式微服务架构** 中，某些服务可能会因为高并发、超时、故障等原因而无法正常工作。**Sentinel** 提供了 **熔断（Circuit Breaker）** 和 **降级（Fallback）** 机制，确保系统的稳定性和高可用性。

#### （1）熔断（Circuit Breaker）

- **目的**：当某个服务的失败率或响应时间超过阈值，Sentinel 会**临时中断请求**，防止系统崩溃。
- **触发条件**：
    - **慢调用比例熔断**（Slow Request Ratio）
    - **异常比例熔断**（Failure Ratio）
    - **异常数熔断**（Exception Count）

#### （2）降级（Fallback）

- **目的**：当一个服务熔断后，Sentinel 会触发**降级策略**，返回**预设的默认值**，而不是直接报错。
- **实现方式**：
    - **本地降级方法**（Fallback Method）
    - **Feign 降级（FeignClient Fallback）**
    - **自定义降级策略**

---

### 2. 熔断机制的工作原理

Sentinel 的熔断策略基于**滑动窗口统计**，它会维护一个时间窗口，并基于窗口内的请求统计数据决定是否开启熔断。

#### （1）滑动窗口（Sliding Window）

- Sentinel 使用 **滑动窗口计数**（Sliding Window Counter）来记录请求状态。
- 窗口内的请求 **成功/失败/慢调用** 统计值会决定熔断是否触发。

> **示例**：
> 
> - 假设滑动窗口大小为 10s，每秒处理 100 个请求。
> - 如果 10s 内失败率达到 50%，就触发熔断。

#### （2）熔断状态转换

Sentinel 熔断器的状态主要有 **3 种**：

1. **关闭状态（Closed）**：
    
    - 初始状态，所有请求正常通过。
    - 如果错误率上升，可能会进入 **打开（Open）** 状态。
2. **打开状态（Open）**：
    
    - 当 **失败率/慢调用比例/异常数** 超过阈值，Sentinel 进入 **熔断状态**。
    - **所有请求都会被拒绝**，直到熔断时间结束。
3. **半开状态（Half-Open）**：
    
    - 熔断结束后，Sentinel 允许**部分请求通过**，测试服务是否恢复正常。
    - 如果恢复成功，进入 **关闭状态（Closed）**。
    - 如果仍然失败，重新进入 **打开状态（Open）**。

---

### 3. 降级机制的工作原理

**降级（Fallback）** 主要是为了保证核心业务的可用性。即使某个服务出现故障，系统也能提供基本功能。

#### （1）降级的触发条件

Sentinel 的降级策略基于 **服务端性能和健康状态**：

- **超时降级**：当接口响应时间过长时，自动降级。
- **异常降级**：如果请求失败率过高，触发降级。
- **自定义规则**：可以在 **Sentinel 控制台** 设定降级策略。

#### （2）降级的实现方式

1. **Feign 降级**
    - 在 FeignClient 上定义 `fallback` 方法。
2. **SentinelResource 降级**
    - 在 `@SentinelResource` 注解中定义降级方法。
3. **全局降级**
    - 通过 Sentinel 配置文件或 Nacos 配置动态调整降级策略。

---

### 4. 熔断和降级的示例

#### （1）Feign + Sentinel 实现熔断降级

依赖、Feign 开关和 `ProductFallback` 的完整代码已在上文「如何在 Spring Cloud Alibaba（Nacos）中使用 Sentinel」给出。本节只强调：`fallback` 用于处理业务调用异常；若需要处理 Sentinel 的限流/熔断拦截，应配置 `blockHandler` 或使用 Sentinel 适配层提供的降级机制。

---

#### （2）`@SentinelResource` 实现熔断

若不使用 Feign，而是直接保护本地资源或调用逻辑，可以使用上文已经给出的 `@SentinelResource` 示例。`fallback` 用于处理业务方法抛出的异常；限流、熔断等 Sentinel block 异常由 `blockHandler` 处理。两类方法的参数都要与原方法匹配，并在末尾分别增加 `Throwable` 或 `BlockException`。

---

#### （3）在 Sentinel 控制台配置熔断

1. 访问 `http://localhost:8080`
2. 在 **熔断规则** 中，添加：
    - 资源名称：`getOrder`
    - 熔断类型：**失败率**
    - 失败率阈值：**50%**
    - 熔断时间：**5 秒**
3. 触发熔断后，Sentinel 会进入 **Open 状态**；后续请求会被拦截并调用 `handleGetOrderBlocked`。熔断恢复窗口结束后，Sentinel 会放行探测请求以判断是否恢复。

---

### 5. Sentinel 熔断和降级 vs Hystrix

| 关键点       | **Sentinel**                 | **Hystrix（已过时）** |
| ------------ | ---------------------------- | --------------------- |
| 维护方       | 阿里巴巴                     | Netflix（已停止维护） |
| 熔断方式     | **失败率、响应时间、异常数** | **失败率、超时**      |
| 限流         | **支持**                     | **不支持**            |
| 热点参数限流 | **支持**                     | **不支持**            |
| 动态规则更新 | **支持（Nacos 配置）**       | **不支持**            |
| 控制台       | **Sentinel Dashboard**       | **Hystrix Dashboard** |

> **🚀 结论：如果使用 Spring Cloud Alibaba（Nacos），最佳选择是 Sentinel！**

---

### 6. 小结

✅ **Sentinel 采用滑动窗口计数** 来统计失败率，决定是否触发熔断。  
✅ **Sentinel 提供 3 种熔断策略**（慢调用熔断、异常比例熔断、异常数熔断）。  
✅ **Sentinel 结合 Feign 可以自动实现熔断和降级**，无需手写大量代码。  
✅ **Sentinel Dashboard 可以动态管理熔断和限流规则**，不用重启服务。  
✅ **相比 Hystrix，Sentinel 提供更强大的限流、热点流控能力**。

---

### 落地建议（高并发场景）
- 注册发现优先用 Spring Cloud LoadBalancer 搭配 Nacos/Eureka，减少 Ribbon 旧依赖。
- 网关统一走 Spring Cloud Gateway，限流过滤器接 Sentinel。
- 配置集中放 Config Server/Git，变更后配合 `bus-refresh` 热推送。
- 链路追踪优先接 Micrometer Tracing；按实现选择 Brave/OpenTelemetry，并导出到 Zipkin、Tempo 等后端，通过 traceId 关联请求链路。
- 熔断、限流规则放入 Nacos 持久化，避免节点重启规则丢失。
