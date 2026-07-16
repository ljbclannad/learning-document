# 1. SpringCloud的组件
Spring Cloud 是一个微服务架构的完整解决方案，提供了多种组件来帮助开发者构建和管理分布式系统。Spring Cloud 主要包含以下 **五大核心组件**：

> 快速导航  
> - [Spring Cloud Netflix](#1-spring-cloud-netflix服务注册与发现负载均衡熔断等)  
> - [Spring Cloud Config](#2-spring-cloud-config分布式配置中心)  
> - [Spring Cloud Gateway](#3-spring-cloud-gatewayapi-网关)  
> - [Spring Cloud Sleuth](#4-spring-cloud-sleuth分布式链路追踪)  
> - [Spring Cloud Stream](#5-spring-cloud-stream消息驱动)  
> - [Spring Cloud LoadBalancer](#2spring-cloud-loadbalancer-详细解析)  
> - [熔断与限流示例（Sentinel）](#3-熔断和限流示例)  
> - [Sentinel 原理](#4--sentinel-的熔断和降级原理)

---

## **1. Spring Cloud Netflix（服务注册与发现、负载均衡、熔断等）**

Spring Cloud Netflix 是 Spring Cloud 生态中最早的一部分，主要基于 Netflix 开源组件开发，包括以下几个关键组件：

### **(1) Eureka（服务注册与发现）**

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
    

### **(2) Ribbon（客户端负载均衡）**

Ribbon 是一个客户端负载均衡组件，它可以自动从 `Eureka Server` 获取可用的服务实例，并进行轮询或其他策略的负载均衡。

```java
@Bean
@LoadBalanced
public RestTemplate restTemplate() {
    return new RestTemplate();
}
```

### **(3) Feign（声明式 HTTP 客户端）**

Feign 结合了 Ribbon 和 Eureka，使得服务调用更加简单。

```java
@FeignClient(name = "order-service")
public interface OrderClient {
    @GetMapping("/orders/{orderId}")
    String getOrder(@PathVariable("orderId") String orderId);
}
```

### **(4) Hystrix（熔断器）**

Hystrix 通过断路器模式防止服务雪崩。

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

## **2. Spring Cloud Config（分布式配置中心）**

Spring Cloud Config 允许将应用的配置集中管理，通常存储在 Git 或本地文件系统中，所有微服务可以动态拉取最新配置。

### **(1) 创建 Config Server**

```java
@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
```

### **(2) 客户端使用 Config**

在 `bootstrap.yml` 中配置：

```yaml
spring:
  application:
    name: order-service
  cloud:
    config:
      uri: http://localhost:8888
```

---

## **3. Spring Cloud Gateway（API 网关）**

Spring Cloud Gateway 是 Spring 官方推出的 API 网关，它提供了路由、负载均衡、认证、限流等功能。

### **(1) 配置 Gateway**

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

### **(2) 启动 Gateway**

```java
@SpringBootApplication
public class ApiGatewayApplication {
    public static void main(String[] args) {
        SpringApplication.run(ApiGatewayApplication.class, args);
    }
}
```

---

## **4. Spring Cloud Sleuth（分布式链路追踪）**

Spring Cloud Sleuth 用于微服务的链路追踪，通常结合 Zipkin 或 SkyWalking。

### **(1) 引入 Sleuth**

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-sleuth</artifactId>
</dependency>
```

### **(2) 添加 Zipkin 进行可视化**

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-zipkin</artifactId>
</dependency>
```

```yaml
spring:
  zipkin:
    base-url: http://localhost:9411
  sleuth:
    sampler:
      probability: 1.0
```

---

## **5. Spring Cloud Stream（消息驱动）**

Spring Cloud Stream 用于构建基于消息的微服务，支持 Kafka、RabbitMQ 等。

### **(1) 创建消息生产者**

```java
@EnableBinding(Source.class)
public class MessageProducer {
    @Autowired
    private MessageChannel output;

    public void sendMessage(String msg) {
        output.send(MessageBuilder.withPayload(msg).build());
    }
}
```

### **(2) 创建消息消费者**

```java
@EnableBinding(Sink.class)
public class MessageConsumer {
    @StreamListener(Sink.INPUT)
    public void receive(String msg) {
        System.out.println("Received message: " + msg);
    }
}
```

---

## **总结**

| 组件                     | 作用                                      |
| ------------------------ | ----------------------------------------- |
| **Spring Cloud Netflix** | 提供服务注册、发现、负载均衡、熔断等      |
| **Spring Cloud Config**  | 分布式配置中心，集中管理微服务配置        |
| **Spring Cloud Gateway** | 统一 API 网关，提供路由、过滤、认证等功能 |
| **Spring Cloud Sleuth**  | 分布式链路追踪，监控微服务间调用链路      |
| **Spring Cloud Stream**  | 消息驱动，支持 Kafka、RabbitMQ 等消息队列 |

---

这五大组件构成了 Spring Cloud 微服务架构的核心，能够帮助开发者高效地构建分布式系统。如果你想进一步了解或需要代码示例，欢迎随时提问！🚀

# **2.Spring Cloud LoadBalancer 详细解析**

Spring Cloud LoadBalancer 是 Spring Cloud 2020+ 版本中取代 Ribbon 的客户端负载均衡组件，它用于在多个服务实例之间均匀分配请求，提供高可用性、负载均衡能力，并减少服务器过载的风险。

---

## **1. Spring Cloud LoadBalancer 的核心概念**

Spring Cloud LoadBalancer 作为 **Spring Cloud Commons** 组件的一部分，主要提供以下功能：

1. **动态服务发现**：基于 **Spring Cloud Discovery Client** 获取可用的服务实例。
2. **负载均衡策略**：提供 **轮询（Round-Robin）** 和 **随机（Random）** 等默认负载均衡策略，同时支持自定义策略。
3. **与 RestTemplate、WebClient、Feign 结合**：支持多种方式进行负载均衡调用。
4. **无缝集成 Spring Cloud Gateway**：在 API 网关中实现服务端负载均衡。

---

## **2. LoadBalancer 工作原理**

### **(1) 负载均衡的核心组件**

Spring Cloud LoadBalancer 主要由以下几个核心组件组成：

- **ServiceInstanceListSupplier**：用于从注册中心（如 Nacos、Eureka）获取可用的服务实例列表。
- **ReactorLoadBalancer**：实现负载均衡策略，决定请求如何分配到不同的服务实例。
- **LoadBalancerClient**：封装负载均衡逻辑，为 `RestTemplate`、`WebClient`、`Feign` 提供支持。

### **(2) 负载均衡流程**

1. **服务发现**：`ServiceInstanceListSupplier` 从服务注册中心获取可用实例列表。
2. **选择实例**：`ReactorLoadBalancer` 根据负载均衡策略（如轮询、随机）选择一个实例。
3. **请求转发**：`LoadBalancerClient` 选择实例后，将请求转发到该实例的 IP 和端口。

---

## **3. 在 RestTemplate 中使用 LoadBalancer**

在 Spring Cloud 2020+ 版本，RestTemplate 需要使用 `@LoadBalanced` 进行负载均衡。

### **(1) 引入 LoadBalancer 依赖**

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

### **(2) 配置 `RestTemplate`**

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

### **(3) 通过 `RestTemplate` 进行服务调用**

```java
@Autowired
private RestTemplate restTemplate;

public String getProductInfo(String productId) {
    return restTemplate.getForObject("http://product-service/products/" + productId, String.class);
}
```

- `http://product-service/products/{productId}` 中的 `product-service` 是注册在 Nacos 或 Eureka 的服务名称，`RestTemplate` 通过 LoadBalancer 选择一个实例并进行请求。

---

## **4. 在 WebClient 中使用 LoadBalancer**

WebClient 是 Spring 5+ 的非阻塞式 HTTP 客户端，它可以与 LoadBalancer 结合使用。

### **(1) 配置 `WebClient`**

```java
@Bean
@LoadBalanced
public WebClient.Builder webClientBuilder() {
    return WebClient.builder();
}
```

### **(2) 通过 WebClient 进行负载均衡调用**

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

## **5. 在 Feign Client 中使用 LoadBalancer**

Feign 是一个声明式 HTTP 客户端，默认使用 Spring Cloud LoadBalancer 进行负载均衡。

### **(1) 引入 Feign 依赖**

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-openfeign</artifactId>
</dependency>
```

### **(2) 启用 Feign**

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

### **(3) 定义 Feign 客户端**

```java
@FeignClient(name = "order-service")
public interface OrderClient {

    @GetMapping("/orders/{id}")
    String getOrder(@PathVariable("id") String id);
}
```

### **(4) 通过 FeignClient 进行调用**

```java
@Autowired
private OrderClient orderClient;

public String fetchOrder(String orderId) {
    return orderClient.getOrder(orderId);
}
```

**Feign 内部会自动使用 Spring Cloud LoadBalancer 来选择 `order-service` 的可用实例并进行调用**。

---

## **6. 自定义负载均衡策略**

Spring Cloud LoadBalancer 默认使用 **RoundRobin（轮询）** 策略，你可以自定义负载均衡策略，如 **随机（Random）** 或 **最少连接（Least Connection）**。

### **(1) 自定义 LoadBalancer 规则**

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

### **(2) 在 `application.yml` 中指定自定义规则**

```yaml
spring:
  cloud:
    loadbalancer:
      clients:
        product-service:
          hint: customLoadBalancer
```

此时，`product-service` 将使用 **随机（Random）负载均衡策略**。

---

## **7. Spring Cloud Gateway 结合 LoadBalancer**

Spring Cloud Gateway 作为 API 网关，可以使用 LoadBalancer 进行服务端负载均衡。

### **(1) Gateway 配置**

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

## **8. Spring Cloud LoadBalancer vs Ribbon**

Spring Cloud LoadBalancer 取代了 Ribbon，并进行了许多优化：

| **对比项**       | **Ribbon**       | **Spring Cloud LoadBalancer**  |
| ---------------- | ---------------- | ------------------------------ |
| **是否维护**     | 2020 之后被弃用  | 仍在维护                       |
| **负载均衡策略** | 轮询、随机、加权 | 轮询、随机、自定义             |
| **异步支持**     | 不支持           | 原生支持 Reactor 异步          |
| **可扩展性**     | 需要继承 `IRule` | 直接扩展 `ReactorLoadBalancer` |

---

## **总结**

- **Spring Cloud LoadBalancer** 是 **Ribbon 的官方替代方案**，支持 **RestTemplate、WebClient、Feign、Spring Cloud Gateway** 等。
- **默认使用轮询策略**，但可以通过 **自定义 `ReactorLoadBalancer`** 来更改策略，如 **随机、最少连接等**。
- **相比 Ribbon，LoadBalancer 支持异步编程**，并与 Spring Reactor 深度集成，更适合现代微服务架构。

如果你有任何具体的问题或想要更详细的示例，欢迎继续提问！🚀

# 3. 熔断和限流示例
如果你的微服务架构使用的是 **Spring Cloud Alibaba（Cloud-Nacos）**，那么 **最佳的熔断与限流方案** 是 **Sentinel**，原因如下：

### **1. 为什么选择 Sentinel？**

✅ **官方推荐**：Sentinel 是阿里巴巴团队开发的，**Spring Cloud Alibaba** 原生集成了 Sentinel，适配性更好。  
✅ **强大的功能**：Sentinel **不仅支持熔断降级，还支持限流、热点参数限流、系统保护等**，比 Resilience4j 适用场景更广。  
✅ **可视化控制台**：Sentinel 提供了一个 **Web 控制台**，可以动态调整熔断、限流规则，而不用重启服务。  
✅ **与 Nacos 无缝结合**：可以 **从 Nacos 读取限流规则**，实现动态限流。

---

## **2. 如何在 Spring Cloud Alibaba（Nacos）中使用 Sentinel？**

### **（1）引入 Sentinel 依赖**

在 `pom.xml` 中添加以下依赖：

```xml
<dependency>
    <groupId>com.alibaba.cloud</groupId>
    <artifactId>spring-cloud-starter-alibaba-sentinel</artifactId>
</dependency>
```

---

### **（2）配置 Sentinel**

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

### **（3）在 FeignClient 上启用 Sentinel**

默认情况下，**Spring Cloud OpenFeign** 结合 Sentinel 时，需要手动开启 Sentinel 支持。

#### **① 在 `application.yml` 启用 Feign + Sentinel**

```yaml
feign:
  sentinel:
    enabled: true
```

#### **② 定义 FeignClient**

```java
@FeignClient(name = "product-service", fallback = ProductFallback.class)
public interface ProductClient {
    @GetMapping("/products/{id}")
    String getProduct(@PathVariable("id") String id);
}
```

#### **③ 创建 `ProductFallback` 降级逻辑**

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

### **（4）在 Controller 上使用 Sentinel 熔断**

如果你希望在 `RestController` 方法上直接加熔断，可以使用 `@SentinelResource`。

```java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @Autowired
    private ProductClient productClient;

    @GetMapping("/{id}")
    @SentinelResource(value = "getOrder", fallback = "fallbackGetOrder")
    public String getOrder(@PathVariable("id") String id) {
        return productClient.getProduct(id);
    }

    // 降级方法
    public String fallbackGetOrder(String id, Throwable throwable) {
        return "Order Service is temporarily unavailable. Please try again later.";
    }
}
```

---

## **3. 限流（流控）配置**

### **（1）在 Sentinel 控制台添加限流规则**

1. 启动 Sentinel 控制台 `http://localhost:8080`
2. 在 **流控规则** 中，添加：
    - 资源名称：`getOrder`
    - 限流模式：**QPS**
    - 限流阈值：**2**
3. 这样，`/orders/{id}` 的请求每秒最多允许 2 个，超过后就会触发限流。

---

## **4. 熔断规则**

### **（1）在 Sentinel 控制台添加熔断规则**

1. 在 **熔断降级** 规则中，添加：
    - 资源名称：`getOrder`
    - 熔断策略：**失败率**（比如 50%）
    - 熔断时间：**10 秒**
2. 当 `getOrder` 方法的请求失败率超过 50% 时，Sentinel 会直接熔断该接口 10 秒，期间所有请求都不会调用真实的 `product-service`，而是进入降级方法。

---

## **5. Nacos + Sentinel 配置动态化**

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

## **6. Sentinel vs Resilience4j**

如果你使用 **Spring Cloud Alibaba**（Nacos），那 **Sentinel** 是最佳选择。但如果你没有使用 Alibaba 生态，建议用 **Resilience4j**。

| 特性         | Sentinel                               | Resilience4j             |
| ------------ | -------------------------------------- | ------------------------ |
| 维护方       | 阿里巴巴                               | Spring 官方              |
| 适用场景     | **Nacos、Dubbo、Spring Cloud Alibaba** | **Spring Cloud Netflix** |
| 熔断策略     | **响应时间、失败率、流量**             | **失败率、慢调用**       |
| 限流         | **支持**                               | **不支持**               |
| 控制台       | **有**                                 | **无**                   |
| 规则动态配置 | **支持 Nacos 配置**                    | **不支持**               |

---

## **7. 总结**

- **你使用 Spring Cloud Alibaba + Nacos，最佳选择是 Sentinel**
- **Sentinel 适用于熔断、限流、降级、热点流控**
- **FeignClient 可以通过 `fallback` 方式实现服务降级**
- **Sentinel 控制台可以动态配置熔断、限流规则**
- **可以将规则存储到 Nacos，实现动态更新**

---

# 4. # **Sentinel 的熔断和降级原理**

## **1. Sentinel 熔断和降级的基本概念**

在 **分布式微服务架构** 中，某些服务可能会因为高并发、超时、故障等原因而无法正常工作。**Sentinel** 提供了 **熔断（Circuit Breaker）** 和 **降级（Fallback）** 机制，确保系统的稳定性和高可用性。

### **（1）熔断（Circuit Breaker）**

- **目的**：当某个服务的失败率或响应时间超过阈值，Sentinel 会**临时中断请求**，防止系统崩溃。
- **触发条件**：
    - **慢调用比例熔断**（Slow Request Ratio）
    - **异常比例熔断**（Failure Ratio）
    - **异常数熔断**（Exception Count）

### **（2）降级（Fallback）**

- **目的**：当一个服务熔断后，Sentinel 会触发**降级策略**，返回**预设的默认值**，而不是直接报错。
- **实现方式**：
    - **本地降级方法**（Fallback Method）
    - **Feign 降级（FeignClient Fallback）**
    - **自定义降级策略**

---

## **2. Sentinel 熔断机制的工作原理**

Sentinel 的熔断策略基于**滑动窗口统计**，它会维护一个时间窗口，并基于窗口内的请求统计数据决定是否开启熔断。

### **（1）滑动窗口（Sliding Window）**

- Sentinel 使用 **滑动窗口计数**（Sliding Window Counter）来记录请求状态。
- 窗口内的请求 **成功/失败/慢调用** 统计值会决定熔断是否触发。

> **示例**：
> 
> - 假设滑动窗口大小为 10s，每秒处理 100 个请求。
> - 如果 10s 内失败率达到 50%，就触发熔断。

### **（2）熔断状态转换**

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

## **3. Sentinel 降级机制的工作原理**

**降级（Fallback）** 主要是为了保证核心业务的可用性。即使某个服务出现故障，系统也能提供基本功能。

### **（1）降级的触发条件**

Sentinel 的降级策略基于 **服务端性能和健康状态**：

- **超时降级**：当接口响应时间过长时，自动降级。
- **异常降级**：如果请求失败率过高，触发降级。
- **自定义规则**：可以在 **Sentinel 控制台** 设定降级策略。

### **（2）降级的实现方式**

1. **Feign 降级**
    - 在 FeignClient 上定义 `fallback` 方法。
2. **SentinelResource 降级**
    - 在 `@SentinelResource` 注解中定义降级方法。
3. **全局降级**
    - 通过 Sentinel 配置文件或 Nacos 配置动态调整降级策略。

---

## **4. Sentinel 熔断和降级的示例**

### **（1）Feign + Sentinel 实现熔断降级**

#### **① 在 `pom.xml` 中引入 Sentinel 依赖**

```xml
<dependency>
    <groupId>com.alibaba.cloud</groupId>
    <artifactId>spring-cloud-starter-alibaba-sentinel</artifactId>
</dependency>
```

#### **② 在 `application.yml` 中启用 Sentinel**

```yaml
spring:
  application:
    name: order-service
  cloud:
    sentinel:
      transport:
        dashboard: localhost:8080  # Sentinel 控制台地址
        port: 8719  # 本地 Sentinel 监听端口
feign:
  sentinel:
    enabled: true  # 启用 Feign + Sentinel 断路器
```

#### **③ 定义 FeignClient 并绑定降级**

```java
@FeignClient(name = "product-service", fallback = ProductFallback.class)
public interface ProductClient {
    @GetMapping("/products/{id}")
    String getProduct(@PathVariable("id") String id);
}
```

#### **④ 创建 `ProductFallback` 处理熔断后的逻辑**

```java
@Component
public class ProductFallback implements ProductClient {
    @Override
    public String getProduct(String id) {
        return "Product service is down. Returning default product.";
    }
}
```

当 `product-service` 无法访问时，Feign 将自动调用 `ProductFallback`。

---

### **（2）`@SentinelResource` 实现熔断**

如果不使用 Feign，而是通过 **RestTemplate/WebClient** 调用其他服务，可以使用 `@SentinelResource`。

#### **① 在 Controller 方法上加 `@SentinelResource`**

```java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @Autowired
    private ProductClient productClient;

    @GetMapping("/{id}")
    @SentinelResource(value = "getOrder", fallback = "fallbackGetOrder")
    public String getOrder(@PathVariable("id") String id) {
        return productClient.getProduct(id);
    }

    // 降级方法
    public String fallbackGetOrder(String id, Throwable throwable) {
        return "Order Service is temporarily unavailable. Please try again later.";
    }
}
```

**`fallback` 方法** 只会在 **业务异常时** 执行，并不会触发限流。

---

### **（3）在 Sentinel 控制台配置熔断**

1. 访问 `http://localhost:8080`
2. 在 **熔断规则** 中，添加：
    - 资源名称：`getOrder`
    - 熔断类型：**失败率**
    - 失败率阈值：**50%**
    - 熔断时间：**5 秒**
3. 触发熔断后，Sentinel 会进入 **Open 状态**，所有请求都会返回 `fallbackGetOrder` 方法的内容。

---

## **5. Sentinel 熔断和降级 vs Hystrix**

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

## **6. 总结**

✅ **Sentinel 采用滑动窗口计数** 来统计失败率，决定是否触发熔断。  
✅ **Sentinel 提供 3 种熔断策略**（慢调用熔断、异常比例熔断、异常数熔断）。  
✅ **Sentinel 结合 Feign 可以自动实现熔断和降级**，无需手写大量代码。  
✅ **Sentinel Dashboard 可以动态管理熔断和限流规则**，不用重启服务。  
✅ **相比 Hystrix，Sentinel 提供更强大的限流、热点流控能力**。

---

## 落地建议（高并发场景）
- 注册发现优先用 Spring Cloud LoadBalancer 搭配 Nacos/Eureka，减少 Ribbon 旧依赖。
- 网关统一走 Spring Cloud Gateway，限流过滤器接 Sentinel。
- 配置集中放 Config Server/Git，变更后配合 `bus-refresh` 热推送。
- 链路追踪优先接 Sleuth + Zipkin/SkyWalking，问题定位靠 traceId。
- 熔断、限流规则放入 Nacos 持久化，避免节点重启规则丢失。

