https://nacos.io/docs/latest/manual/admin/deployment/deployment-standalone/?spm=5238cd80.381747ab.0.0.66446753QouFUW#2-docker%E9%83%A8%E7%BD%B2
# 1. 架构
整体架构分为用户层、业务层、内核层和插件，用户层主要解决用户使用的易用性问题，业务层主要解决服务发现和配置管理的功能问题，内核层解决分布式系统一致性、存储、高可用等核心问题，插件解决扩展性问题。
![[Pasted image 20250104153013.png]]

# 2. 配置管理
Nacos 配置中心是一个支持动态配置管理的工具，主要用于集中式管理和分发配置，帮助分布式系统实现统一的配置管理。以下是 Nacos 配置中心的详细原理：

---

### 1. **核心概念**

- **Data ID**：
    - 配置的唯一标识，用于区分不同的配置文件。
- **Group**：
    - 配置分组，用于对配置进行逻辑分组管理。
- **Namespace**：
    - 用于隔离不同的租户或环境（如开发、测试、生产）。

这些概念组合在一起，构成了 Nacos 配置的层次化管理结构。

---

### 2. **配置管理的核心流程**

#### （1）**配置发布**

- **发布流程**：
    - 配置管理员通过 Nacos 控制台、HTTP API 或 SDK 上传配置内容。
    - 配置的元信息（如 Data ID、Group、Namespace）与内容一同存储在 Nacos Server 的持久化存储（如 MySQL）中。

#### （2）**配置订阅**

- **订阅者行为**：
    - 应用程序通过 Nacos SDK 或 HTTP API 订阅配置。
    - 订阅者指定 Data ID 和 Group，向 Nacos Server 注册监听器。

---

### 3. **配置分发与实时推送**

#### （1）**长轮询机制**

- Nacos 使用 **长轮询** 实现配置变更的实时推送。
- **流程**：
    1. 客户端发送 HTTP 请求，轮询指定配置的版本。
    2. Nacos Server 持久化存储中配置发生变更时，立即返回最新配置。
    3. 若未发生变更，连接保持至超时时间（默认为 30 秒），然后返回空响应，客户端重新发起请求。
- **优点**：
    - 简单高效，避免频繁的短轮询请求。
    - 支持大规模分布式应用场景。

#### （2）**推送通知**

- 在配置变更时，Nacos Server 主动通知所有订阅客户端。
- 客户端通过监听器回调机制接收并更新配置。

---

### 4. **数据一致性**

- Nacos 配置中心通过 **Raft 协议** 保证多节点配置数据的一致性。
    - 配置数据变更由 Leader 节点处理并同步到 Follower 节点。
    - 多数派确认后，变更才被提交，保证一致性。

---

### 5. **配置持久化**

- 配置数据存储在 **MySQL 数据库** 中，Nacos Server 启动时会加载所有持久化配置。
- 配置变更实时写入 MySQL，确保数据可靠性。

---

### 6. **版本控制**

- Nacos 支持配置的版本管理和回滚：
    - 每次配置更新时，自动生成新版本。
    - 用户可以查看历史版本，并将配置回滚到指定版本。

---

### 7. **灰度发布**

- Nacos 支持 **灰度配置发布**：
    - 配置管理者可以指定部分客户端接收新配置，用于功能验证。
    - 灰度成功后，逐步推广到所有客户端。

---

### 8. **多租户隔离**

- **Namespace** 提供逻辑隔离，用于不同租户或环境的配置隔离。
- 每个 Namespace 的配置独立管理，不会互相影响。

---

### 9. **高可用与集群部署**

- Nacos 支持多节点集群部署，确保配置中心的高可用性。
- 配置数据通过 Raft 协议在集群内同步，避免单点故障。

---

### 10. **扩展与自定义**

- Nacos 支持扩展存储方式，用户可以通过插件实现自定义存储（如使用 Redis、PostgreSQL）。
- 提供 SPI 接口，可以扩展功能模块，如自定义通知机制。

---

### 配置中心的整体工作流程示意：

1. **发布配置**：管理员通过界面或 API 发布配置到 Nacos。
2. **持久化存储**：配置存储在 MySQL 等数据库中。
3. **客户端订阅**：应用客户端通过 Data ID 和 Group 订阅配置。
4. **实时同步**：Nacos 使用长轮询或推送通知机制，将最新配置推送给客户端。
5. **动态更新**：客户端接收新配置并应用到系统中。

---

通过这些原理，Nacos 配置中心实现了分布式系统中配置管理的集中化、实时性和高可用性，为大规模应用提供了高效的配置服务支持。

# 3. 长轮询
Nacos 的 **长轮询机制** 是其配置中心实现实时配置推送的关键技术之一。它通过客户端与服务端之间的长时间 HTTP 连接，实现配置的实时变更感知，避免频繁的短轮询造成的系统资源浪费。以下是 Nacos 长轮询机制的详细原理和实现过程：

---

## 1. **核心思想**

长轮询是一种模拟服务端主动推送的机制，客户端发起请求后，如果没有新的配置更新，服务端会保持连接一段时间（默认 30 秒），直到：

- 配置发生变更，立即返回更新内容。
- 超时时间到达，返回空响应，客户端重新发起请求。

---

## 2. **长轮询的详细流程**

### **客户端实现**

客户端通过定期发送请求订阅配置的变更信息，核心代码位于 Nacos 客户端 SDK 的 `ClientWorker` 类中。

#### **1）发起长轮询请求**

```java
public void checkUpdateConfig() {
    List<String> changedConfigs = pollingServer();
    for (String config : changedConfigs) {
        notifyListeners(config); // 通知监听器更新配置
    }
}
```

客户端会轮询服务端获取变更的配置内容，并在检测到配置更新时触发监听器更新。

#### **2）与服务端通信**

客户端使用 HTTP 请求传递订阅的配置信息和其 MD5 值。

- 请求参数：
    - `dataId`：配置唯一标识。
    - `group`：配置组。
    - `tenant`：命名空间标识。
    - `md5`：客户端保存的配置内容的哈希值。

```http
GET /nacos/v1/cs/configs/listener
Content-Type: application/x-www-form-urlencoded

dataId=testData&group=testGroup&tenant=testTenant&md5=5d41402abc4b2a76b9719d911017c592
```

---

### **服务端实现**

服务端接收客户端的长轮询请求，并根据配置的变化与否决定响应时间和内容。核心代码位于 Nacos 服务端的 `ConfigServletInner` 和 `ConfigService` 类中。

#### **1）接收请求**

服务端在接收到请求后，提取客户端传递的 MD5 值，并与当前配置的 MD5 值进行对比。

```java
public void doPollingConfig(HttpServletRequest request, HttpServletResponse response) {
    String clientMd5 = request.getParameter("md5");
    String serverMd5 = getServerMd5(dataId, group);
    if (!clientMd5.equals(serverMd5)) {
        // 返回最新配置
        response.getWriter().write(getConfigContent(dataId, group));
    } else {
        // 等待配置更新或超时
        waitForUpdate();
    }
}
```

#### **2）等待更新**

如果配置没有发生变化，服务端进入等待状态。`waitForUpdate` 方法会挂起线程直到以下条件之一满足：

- 配置发生变化。
- 等待超时时间（默认为 30 秒）到达。

```java
public void waitForUpdate() {
    synchronized (this) {
        try {
            this.wait(30000); // 挂起线程 30 秒
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
```

#### **3）推送变更**

当配置变更时，服务端会立即中断挂起的线程，向客户端返回最新的配置内容。

```java
public void notifyConfigChange() {
    synchronized (this) {
        this.notifyAll(); // 唤醒所有等待线程
    }
}
```

---

## 3. **长轮询的特点**

### **优点**

1. **高效**：
    
    - 避免频繁短轮询造成的高网络开销。
    - 服务端主动通知变更，提高响应速度。
2. **实时性**：
    
    - 配置变更后，服务端立即返回变更内容，客户端能快速感知。
3. **简单性**：
    
    - 不需要复杂的协议，只依赖 HTTP 连接实现。

### **缺点**

1. **连接开销**：
    
    - 服务端需要为每个客户端维护一个长时间的连接，当客户端数量巨大时，会占用大量线程资源。
2. **延迟问题**：
    
    - 在超时即将到达时，服务端可能因为还未检测到配置变更而返回空结果，导致客户端需要重新发起请求。

---

## 4. **长轮询和短轮询的对比**

|特性|长轮询|短轮询|
|---|---|---|
|网络开销|低|高|
|实时性|高|低|
|实现复杂度|较高（需维护连接和超时机制）|低|
|服务端压力|较高（需维护更多连接）|较低|

---

## 5. **源码中的长轮询关键点**

### **客户端核心代码**

```java
public class ClientWorker {
    public void checkUpdateConfig() {
        List<String> changedConfigs = pollingServer();
        for (String config : changedConfigs) {
            notifyListeners(config); // 通知监听器更新配置
        }
    }
}
```

### **服务端核心代码**

```java
public class ConfigServletInner {
    public void doPollingConfig(HttpServletRequest request, HttpServletResponse response) {
        String clientMd5 = request.getParameter("md5");
        String serverMd5 = getServerMd5(dataId, group);
        if (!clientMd5.equals(serverMd5)) {
            response.getWriter().write(getConfigContent(dataId, group));
        } else {
            waitForUpdate();
        }
    }
}
```

---

Nacos 的长轮询机制结合了服务端的高效等待和客户端的实时性要求，是动态配置中心的一种经典实现。

# 4. 服务端和客户端的职责
在 Nacos 的长轮询机制中，**服务端**和**客户端**的角色和职责如下：

---

## **1. 服务端（Nacos Server）**

Nacos Server 是整个配置管理系统的核心部分，主要负责管理配置的存储、分发、同步以及与客户端的通信。

### **职责**

1. **存储配置**
    
    - 管理配置数据（包括 `Data ID`、`Group` 和 `Namespace` 等）。
    - 配置数据默认存储在持久化存储（如 MySQL）中。
2. **处理客户端请求**
    
    - 接收客户端的配置发布、订阅和轮询请求。
    - 对比客户端提交的配置版本（MD5 值）与服务端当前版本，决定是否返回最新配置。
3. **通知客户端**
    
    - 当配置发生变更时，通知所有订阅了该配置的客户端。
4. **高可用和一致性**
    
    - 支持集群模式，通过 **Raft 协议** 保证数据一致性。
    - 支持动态扩展和容灾。

### **服务端关键组件**

- **Controller 层**：如 `ConfigController`，用于接收 HTTP 请求。
- **Service 层**：如 `ConfigService`，处理配置的核心逻辑。
- **持久化层**：如 `PersistService`，负责与数据库交互。

---

## **2. 客户端**

Nacos 客户端是分布式系统的组成部分，运行在微服务的实例中，通过 SDK 实现与 Nacos Server 的通信。

### **职责**

1. **订阅配置**
    
    - 客户端通过指定 `Data ID`、`Group` 和 `Namespace` 向服务端注册监听器。
2. **检测配置更新**
    
    - 使用 **长轮询机制** 定期向服务端发送请求，检查配置是否发生变化。
3. **本地缓存**
    
    - 客户端会缓存服务端下发的配置数据，当网络异常或服务端不可用时，从本地缓存加载配置。
4. **监听配置变更**
    
    - 在检测到配置变更时，通过回调函数或监听器通知业务代码，动态应用新配置。

### **客户端关键组件**

- **Nacos SDK**：
    
    - 提供标准接口供用户调用。
    - 负责配置的订阅与轮询逻辑（如 `ClientWorker` 类）。
- **监听器**：
    
    - 用户实现的接口，用于接收和处理配置变更通知。

---

## **3. 服务端与客户端的交互流程**

### **配置订阅**

1. **客户端**发送订阅请求：
    
    - 客户端指定需要订阅的配置（如 `Data ID`、`Group`），并附带当前配置的版本（MD5 值）。
2. **服务端**接收请求：
    
    - 检查客户端版本是否与服务端一致。
    - 若不一致，则返回最新配置。
3. **长轮询等待**：
    
    - 如果配置没有发生变化，服务端挂起请求，等待配置变更或超时。
4. **配置变更通知**：
    
    - 服务端检测到配置变更后，立即返回最新配置给客户端。
    - 客户端回调监听器，应用新配置。

---

### **发布配置**

1. **客户端**或管理员发布配置：
    
    - 管理员通过 Nacos 控制台或 API 发布配置到服务端。
2. **服务端**存储配置：
    
    - 持久化到数据库，并通知订阅该配置的所有客户端。
3. **客户端**接收通知：
    
    - 客户端通过长轮询或 WebSocket 接收变更，更新本地缓存并应用新配置。

---

## **4. 总结对比**

|功能|服务端（Nacos Server）|客户端（Nacos SDK）|
|---|---|---|
|**职责**|管理配置存储、处理请求、通知客户端|订阅配置、检测更新、应用配置|
|**主要组件**|`ConfigController`、`ConfigService`、`PersistService`|`ClientWorker`、监听器|
|**存储位置**|持久化存储（如 MySQL）|本地缓存|
|**通信方式**|HTTP 长轮询、推送机制|HTTP 请求|
|**触发方式**|处理客户端请求或监听配置变更事件|定期轮询服务端检测配置变更|

通过服务端和客户端的协作，Nacos 实现了动态配置的实时推送和高效管理。

# 5. nacos的灰度发布
Nacos 的 **灰度发布** 是指将配置的更新逐步推广到部分服务实例或客户端，而不是一次性推送给所有订阅者。灰度发布的目的是在分布式系统中进行风险控制，通过小范围测试验证新配置的稳定性，再逐步覆盖到全量实例。

以下是 Nacos 灰度发布的详细原理、流程及实现方式：

---

## **1. 灰度发布的核心思想**

- **逐步推广**：将配置变更首先推送给部分服务实例，测试通过后再推广到所有实例。
- **精准控制**：通过条件过滤、标签匹配等方式选择特定的服务实例接收配置。
- **动态调整**：允许随时调整灰度发布范围，避免全量发布带来的风险。

---

## **2. 灰度发布的实现方式**

### **1）配置的标签和条件匹配**

Nacos 允许通过 **标签（Label）** 或 **元数据（Metadata）** 实现灰度控制：

- **标签**：为每个配置或服务实例添加特定的标签，用于区分不同的实例群体。
- **条件匹配**：通过条件规则，选择需要接收新配置的实例。

例如：

- 配置发布时附加一个标签 `environment=test`。
- 仅推送配置到元数据中包含 `test` 的服务实例。

---

### **2）灰度配置发布流程**

#### **服务端实现**

灰度发布在 Nacos 的服务端通过过滤订阅者列表实现，关键逻辑如下：

1. **发布配置时添加标签**
    
    - 发布配置时，指定灰度的条件（如实例元数据、标签等）。
    - 灰度条件与订阅者的元数据进行匹配，筛选出目标客户端。
2. **筛选订阅者**
    
    - 服务端在推送配置时，通过灰度条件过滤订阅者，仅将配置推送给符合条件的客户端。
3. **推送变更**
    
    - 符合灰度条件的客户端通过长轮询或实时推送机制接收新配置。

#### **客户端实现**

客户端在订阅配置时，带上自身的元数据（如标签、环境等），供服务端进行匹配。

---

### **3）灰度配置发布的关键接口**

#### **配置发布接口**

服务端支持通过 HTTP API 或控制台发布配置时附加标签信息。

**示例 API**：

```http
POST /nacos/v1/cs/configs
Content-Type: application/x-www-form-urlencoded

dataId=testData
group=testGroup
content=grayReleaseContent
tenant=default
labels=environment=test,region=us
```

#### **订阅接口**

客户端在订阅时，可附加自身的标签或元数据供服务端进行筛选。

**示例**：

```java
nacosConfigService.addListener("testData", "testGroup", new Listener() {
    @Override
    public void receiveConfigInfo(String config) {
        System.out.println("Received config: " + config);
    }
}, Collections.singletonMap("environment", "test"));
```

---

## **3. 灰度发布的主要场景**

### **1）环境隔离**

- 在多环境（开发、测试、生产）场景中，可以通过标签 `environment` 区分配置发布范围。
- 测试环境先验证配置稳定性，再推广到生产环境。

### **2）区域灰度**

- 为不同地域（如 `region=us`、`region=eu`）的实例设置不同的配置。
- 允许在某个区域内先行验证配置的正确性。

### **3）服务实例的版本控制**

- 通过实例元数据（如 `version=v1`）区分不同的版本。
- 新配置仅推送给特定版本的实例，逐步验证后再覆盖全量。

---

## **4. 灰度发布的源码实现**

### **1）服务端筛选逻辑**

灰度发布的核心是服务端的订阅者筛选逻辑，在推送配置前对订阅者进行过滤。

- **关键类**：`ConfigService`
- **核心方法**：`notifyConfigChange`

```java
public void notifyConfigChange(String dataId, String group, Map<String, String> labels) {
    List<Subscriber> subscribers = getSubscribers(dataId, group);
    for (Subscriber subscriber : subscribers) {
        if (matchLabels(subscriber.getLabels(), labels)) {
            pushConfigToSubscriber(subscriber, dataId, group);
        }
    }
}
```

- **标签匹配逻辑**：

```java
private boolean matchLabels(Map<String, String> subscriberLabels, Map<String, String> configLabels) {
    for (Map.Entry<String, String> entry : configLabels.entrySet()) {
        if (!entry.getValue().equals(subscriberLabels.get(entry.getKey()))) {
            return false;
        }
    }
    return true;
}
```

---

### **2）客户端元数据上报**

客户端订阅配置时，通过长轮询请求附加自身的元数据。

- **请求示例**：

```http
GET /nacos/v1/cs/configs/listener
Content-Type: application/x-www-form-urlencoded

dataId=testData
group=testGroup
labels=environment=test,region=us
```

- **服务端解析**： 服务端解析客户端的元数据，并根据配置的标签信息进行筛选。

---

## **5. 灰度发布的最佳实践**

### **1）渐进式发布**

- 将配置划分为多个阶段，先小范围试验，再逐步扩大覆盖范围。
- 使用不同的标签标记实例（如 `beta`、`stable`）。

### **2）监控与回滚**

- 配置变更后监控服务状态，确保灰度发布的稳定性。
- 出现问题时，快速回滚到上一个版本。

### **3）结合 Canary 流量控制**

- 灰度发布可与流量控制结合，将少量流量引导到灰度实例，逐步扩大流量比例。

---

## **6. 总结**

Nacos 的灰度发布通过标签和条件匹配机制实现，核心特性包括：

1. **标签过滤**：发布配置时附加标签，仅推送给符合条件的订阅者。
2. **动态调整**：灰度范围可随时调整，逐步推广配置。
3. **风险控制**：通过分阶段发布降低配置变更的风险。

这种机制特别适用于多环境、多区域和大规模分布式系统的配置管理场景，有效提高了系统的灵活性和稳定性。

# 6.nacos的心跳检测及下线通知
Nacos 的 **心跳检测** 和 **通知客户端** 是服务发现与健康检查的重要组成部分，保证了服务实例的动态性和实时性。以下是它们的实现原理和关键逻辑：

---

## **1. 心跳检测的实现**

Nacos 的心跳检测用于监控服务实例的存活状态，确保服务注册表中的服务信息是实时有效的。

### **1.1 心跳检测方式**

#### **客户端心跳上报**

- 客户端定期向 Nacos Server 发送心跳请求，告知服务端自身仍然存活。
- 服务端通过心跳间隔判断服务是否健康，如果心跳超时，则将该实例标记为不可用。

#### **服务端主动探测**

- 服务端可以通过 HTTP/TCP 等协议主动探测服务实例的健康状态。
- 多用于非 Java 客户端或没有集成 Nacos SDK 的场景。

### **1.2 客户端心跳上报逻辑**

1. **核心类：`BeatReactor`**
    
    - `BeatReactor` 是客户端定时发送心跳的组件，内部维护了一个定时任务。
2. **关键代码：心跳发送**
    
    ```java
    public void addBeatInfo(String serviceName, Instance instance) {
        // 构造心跳数据
        BeatInfo beatInfo = new BeatInfo();
        beatInfo.setServiceName(serviceName);
        beatInfo.setIp(instance.getIp());
        beatInfo.setPort(instance.getPort());
        beatInfo.setCluster(instance.getClusterName());
        beatInfo.setPeriod(instance.getMetadata().get("beatInterval"));
    
        // 定期发送心跳请求
        executorService.scheduleAtFixedRate(() -> {
            sendBeat(beatInfo);
        }, 0, beatInfo.getPeriod(), TimeUnit.MILLISECONDS);
    }
    ```
    
3. **发送心跳请求**
    
    ```java
    private void sendBeat(BeatInfo beatInfo) {
        String url = "http://nacos-server/nacos/v1/ns/instance/beat";
        HttpRestResult<Void> result = HttpClient.post(url, beatInfo);
        if (!result.ok()) {
            log.error("Heartbeat failed for service: {}", beatInfo.getServiceName());
        }
    }
    ```
    
4. **心跳请求示例**
    
    ```http
    POST /nacos/v1/ns/instance/beat
    Content-Type: application/json
    
    {
        "serviceName": "example-service",
        "ip": "192.168.1.100",
        "port": 8080,
        "cluster": "DEFAULT",
        "weight": 1.0
    }
```


### **1.3 服务端心跳检测逻辑**

1. **核心类：`ClientBeatProcessor`**
    
    - 处理心跳请求的任务类，更新实例的最后心跳时间。
2. **关键代码：处理心跳**
    
    ```java
    public boolean process(BeatInfo beatInfo) {
        // 更新服务实例的最后心跳时间
        Service service = serviceManager.getService(beatInfo.getServiceName());
        Instance instance = service.getInstance(beatInfo.getIp(), beatInfo.getPort());
        instance.setLastBeat(System.currentTimeMillis());
        return true;
    }
    ```
    
3. **健康状态检测**
    
    - 定时任务检查实例的最后心跳时间是否超时：
        
        ```java
        public void checkInstanceHealth(Service service) {
            long currentTime = System.currentTimeMillis();
            for (Instance instance : service.getInstances()) {
                if (currentTime - instance.getLastBeat() > instance.getHeartbeatTimeout()) {
                    instance.setHealthy(false);
                    log.warn("Instance {}:{} is unhealthy", instance.getIp(), instance.getPort());
                }
            }
        }
        ```
        

---

## **2. 通知客户端的实现**

当服务实例上下线或配置变更时，Nacos 会通过 **长轮询机制** 通知订阅的客户端。

### **2.1 长轮询机制**

1. **客户端订阅服务**
    
    - 客户端通过 HTTP 长轮询向服务端订阅服务列表。
    - 请求示例：
        
        ```http
        GET /nacos/v1/ns/service/listener
        Content-Type: application/x-www-form-urlencoded
        
        serviceName=example-service
        clientIp=192.168.1.100
        md5=5d41402abc4b2a76b9719d911017c592
```
        
2. **服务端接收订阅请求**
    
    - **核心类**：`ServiceManager`
    - **关键代码**：
        
        ```java
        public void addSubscriber(String serviceName, Subscriber subscriber) {
            subscribers.computeIfAbsent(serviceName, k -> new ConcurrentHashMap<>())
                       .put(subscriber.getClientIp(), subscriber);
        }
        ```
        
3. **挂起请求**
    
    - 如果服务没有变化，服务端会挂起请求直到：
        - 服务列表发生变化。
        - 超时时间（默认 30 秒）到达。
    - **关键代码**：
        
        ```java
        public void waitForUpdate(String serviceName, Subscriber subscriber) {
            synchronized (subscriber) {
                try {
                    subscriber.wait(30000); // 等待 30 秒
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }
        ```
        
4. **通知变更**
    
    - 当服务实例发生上下线或健康状态变化时，服务端唤醒挂起的订阅线程。
    - **关键代码**：
        
        ```java
        public void notifySubscribers(String serviceName) {
            Map<String, Subscriber> subscribers = this.subscribers.get(serviceName);
            for (Subscriber subscriber : subscribers.values()) {
                synchronized (subscriber) {
                    subscriber.notifyAll(); // 唤醒线程
                }
            }
        }
        ```
        

---

### **2.2 客户端接收通知**

1. **处理返回的服务列表**
    
    - 如果服务列表发生变化，客户端会通过回调函数处理更新。
    
    ```java
    public void updateService(String serviceName, List<Instance> instances) {
        log.info("Received updated service list for {}", serviceName);
        serviceCache.put(serviceName, instances);
    }
    ```
    
2. **更新本地缓存**
    
    - 客户端将新的服务列表存入本地缓存，并触发负载均衡器更新实例列表。

---

## **3. 总结**

|功能|服务端实现|客户端实现|
|---|---|---|
|**心跳检测**|- 接收心跳请求，更新实例状态|- 定期发送心跳请求，告知服务端实例存活|
|**实例健康检查**|- 定时检测心跳超时的实例，标记为不健康|- 无需额外实现，由服务端主动检测|
|**变更通知**|- 通过长轮询挂起订阅请求，实例变更时推送通知|- 通过长轮询接收变更通知，更新本地服务列表|
|**关键机制**|- 心跳处理 (`ClientBeatProcessor`)|- 心跳发送 (`BeatReactor`)|
|**通信方式**|- HTTP API，长轮询机制|- HTTP 长轮询，SDK 内部监听器回调机制|

这种设计保证了 Nacos 的服务状态监控实时性和通知的高效性，适用于分布式系统的动态服务管理场景。

# 7.nacos的服务发现
Nacos 的 **服务发现** 是其核心功能之一，支持动态服务注册与发现。通过服务发现，微服务可以根据服务名获取可用的服务实例列表，而无需手动配置。以下是 Nacos 服务发现的详细原理：

---

## **1. 服务发现的核心组件**

1. **服务注册表（Service Registry）**
    
    - 服务注册表是 Nacos Server 用于存储所有注册服务信息的地方，包括服务名称、实例地址、端口、元数据等。
    - 数据存储在内存中，并通过 Raft 协议同步到集群的所有节点。
2. **服务注册（Service Registration）**
    
    - 服务提供者在启动时将自身的信息注册到 Nacos Server。
3. **服务发现（Service Discovery）**
    
    - 服务消费者通过 Nacos SDK 向 Nacos Server 查询指定服务的可用实例列表。
4. **健康检查（Health Check）**
    
    - 确保注册表中只有健康的服务实例，避免调用无效服务。

---

## **2. 服务发现的整体流程**

### **2.1 服务注册**

1. **服务提供者注册服务实例到 Nacos Server**
    
    - 服务启动后，通过 Nacos SDK 调用注册接口，将服务实例信息（如 IP、端口、元数据等）注册到 Nacos Server。
2. **注册流程**
    
    - **客户端**： 客户端通过 HTTP 请求将服务实例信息发送到 Nacos Server：
        
        ```http
        POST /nacos/v1/ns/instance
        Content-Type: application/x-www-form-urlencoded
        
        serviceName=example-service&ip=192.168.1.100&port=8080&clusterName=DEFAULT
```
        
    - **服务端**： 服务端将注册的实例信息存储到服务注册表中：
        
        ```java
        public void registerInstance(String serviceName, Instance instance) {
            Service service = serviceManager.getOrCreateService(serviceName);
            service.addInstance(instance);
            persistService(serviceName, instance); // 持久化到数据库
        }
        ```
        

---

### **2.2 服务发现**

1. **服务消费者通过服务名查询实例列表**
    
    - 服务消费者通过 Nacos SDK 向 Nacos Server 查询指定服务的可用实例列表。
2. **查询流程**
    
    - **客户端**： 客户端发送 HTTP 请求获取服务实例列表：
        
        ```http
        GET /nacos/v1/ns/instance/list
        Content-Type: application/x-www-form-urlencoded
        
        serviceName=example-service 
```
        
    - **服务端**： 服务端从注册表中获取服务实例列表并返回：
        
        ```java
        public List<Instance> getInstances(String serviceName) {
            Service service = serviceManager.getService(serviceName);
            return service.getHealthyInstances();
        }
        ```
        

---

### **2.3 服务状态维护**

1. **心跳机制**
    
    - 注册的服务实例通过定期发送心跳包，向 Nacos Server 保持在线状态。
    - 如果心跳超时，服务端将该实例标记为不可用。
2. **健康检查**
    
    - Nacos 支持两种健康检查方式：
        - **主动心跳**：客户端定期上报心跳。
        - **服务端探测**：服务端主动探测服务实例的健康状态（如通过 HTTP/TCP）。
3. **实例移除**
    
    - 如果心跳超时或探测失败，Nacos Server 会将该实例从注册表中移除。

---

## **3. 服务发现的核心机制**

### **3.1 数据存储与一致性**

1. **服务注册表**
    
    - 注册表数据存储在内存中。
    - 持久化存储（如 MySQL）用于服务端重启后的数据恢复。
2. **一致性保障**
    
    - Nacos 集群模式通过 **Raft 协议** 确保服务注册表在多节点之间的数据一致性。

---

### **3.2 实例过滤**

1. **健康实例筛选**
    
    - 在返回服务实例列表时，Nacos Server 会过滤掉不健康的实例：
        
        ```java
        public List<Instance> getHealthyInstances() {
            return instances.stream()
                            .filter(Instance::isHealthy)
                            .collect(Collectors.toList());
        }
        ```
        
2. **元数据匹配**
    
    - 支持通过元数据（如标签、区域）筛选实例列表，满足多区域、多版本的部署需求。

---

### **3.3 本地缓存**

1. **客户端缓存**
    
    - 为了减少对服务端的依赖，Nacos 客户端会将服务实例列表缓存到本地。
    - 当服务端不可用时，客户端可以从本地缓存中读取实例列表。
2. **缓存刷新**
    
    - 客户端会定期从服务端拉取最新的服务实例列表，更新本地缓存。

---

## **4. 服务发现的源码分析**

### **4.1 服务注册**

服务端处理服务注册的核心代码：

- **`ServiceManager` 类**
    
    ```java
    public void registerInstance(String serviceName, Instance instance) {
        Service service = getOrCreateService(serviceName);
        service.addInstance(instance);
    }
    ```
    
- **实例添加**
    
    ```java
    public void addInstance(Instance instance) {
        instances.put(instance.getInstanceId(), instance);
    }
    ```
    

---

### **4.2 服务发现**

服务端处理服务发现的核心代码：

- **`ServiceManager` 类**
    
    ```java
    public List<Instance> getInstances(String serviceName) {
        Service service = getService(serviceName);
        return service.getHealthyInstances();
    }
    ```
    

---

### **4.3 客户端缓存**

客户端维护本地缓存的核心代码：

- **`HostReactor` 类**
    
    ```java
    public ServiceInfo getServiceInfo(String serviceName) {
        return serviceInfoMap.get(serviceName);
    }
    ```
    
- **定期拉取最新实例列表**
    
    ```java
    public void refreshServiceInfo(String serviceName) {
        ServiceInfo serviceInfo = pullServiceInfoFromServer(serviceName);
        serviceInfoMap.put(serviceName, serviceInfo);
    }
    ```
    

---

## **5. 服务发现的优化与扩展**

### **5.1 提高可靠性**

1. 部署多节点集群，避免单点故障。
2. 开启客户端本地缓存功能，提升容灾能力。

### **5.2 提升性能**

1. 优化健康检查频率，减少不必要的心跳开销。
2. 对服务实例列表启用标签过滤，减少无关实例的返回。

### **5.3 扩展性**

1. 支持自定义服务发现协议或存储方式。
2. 集成灰度发布，通过元数据筛选实现分区服务发现。

---

## **6. 总结**

Nacos 服务发现通过 **动态服务注册** 和 **实例健康检查**，实现了以下功能：

1. **实时服务注册**：服务启动时自动注册到 Nacos Server。
2. **高效服务发现**：服务消费者实时获取可用实例列表。
3. **可靠性保障**：支持心跳检测、健康检查和客户端本地缓存。
4. **一致性保证**：通过 Raft 协议确保注册表数据一致性。

这种机制非常适合现代微服务架构，特别是在动态和分布式环境下。

# 8.服务发现在微服务架构中的使用
在实际的业务代码中，**服务发现** 的使用体现在服务提供者和服务消费者如何与 Nacos 集成，进行服务注册和动态实例发现。下面从服务提供者和消费者的角度，详细说明服务发现在业务代码中的体现：

---

## **1. 服务提供者（Service Provider）**

服务提供者是指将自身服务注册到 Nacos 的应用实例，使其他服务可以发现和调用它。

### **1.1 注册服务到 Nacos**

在 Spring Cloud Alibaba 或 Dubbo 框架中，服务的注册通常是自动完成的，但可以通过配置和少量代码控制注册行为。

#### **Spring Cloud 示例**

1. **依赖配置**
    
    ```xml
    <dependency>
        <groupId>com.alibaba.cloud</groupId>
        <artifactId>spring-cloud-starter-alibaba-nacos-discovery</artifactId>
    </dependency>
    ```
    
2. **配置文件** 在 `application.yml` 中配置 Nacos 服务注册中心地址：
    
    ```yaml
    spring:
      application:
        name: provider-service  # 服务名
      cloud:
        nacos:
          discovery:
            server-addr: 127.0.0.1:8848
    ```
    
3. **启动类** 启动类上添加 `@EnableDiscoveryClient`，即可将服务注册到 Nacos。
    
    ```java
    @SpringBootApplication
    @EnableDiscoveryClient
    public class ProviderApplication {
        public static void main(String[] args) {
            SpringApplication.run(ProviderApplication.class, args);
        }
    }
    ```
    
4. **业务逻辑代码** 编写一个简单的接口供消费者调用：
    
    ```java
    @RestController
    public class ProviderController {
    
        @GetMapping("/hello")
        public String hello(@RequestParam String name) {
            return "Hello, " + name;
        }
    }
    ```
    

服务启动后，`provider-service` 会自动注册到 Nacos，并出现在 Nacos 控制台的服务列表中。

---

## **2. 服务消费者（Service Consumer）**

服务消费者是指调用 Nacos 中注册的服务的应用实例。

### **2.1 从 Nacos 获取服务实例**

#### **Spring Cloud 示例**

1. **依赖配置** 同样添加 Nacos 的依赖：
    
    ```xml
    <dependency>
        <groupId>com.alibaba.cloud</groupId>
        <artifactId>spring-cloud-starter-alibaba-nacos-discovery</artifactId>
    </dependency>
    ```
    
2. **配置文件** 配置服务消费者的应用名和 Nacos 服务发现中心地址：
    
    ```yaml
    spring:
      application:
        name: consumer-service  # 服务名
      cloud:
        nacos:
          discovery:
            server-addr: 127.0.0.1:8848
    ```
    
3. **Feign 客户端调用** 使用 Spring Cloud Feign 进行服务调用：
    
    - 启动类上添加 `@EnableFeignClients`：
        
        ```java
        @SpringBootApplication
        @EnableFeignClients
        public class ConsumerApplication {
            public static void main(String[] args) {
                SpringApplication.run(ConsumerApplication.class, args);
            }
        }
        ```
        
    - 编写 Feign 接口：
        
        ```java
        @FeignClient("provider-service") // 指定服务名
        public interface ProviderClient {
            @GetMapping("/hello")
            String hello(@RequestParam String name);
        }
        ```
        
    - 在业务逻辑中使用：
        
        ```java
        @RestController
        public class ConsumerController {
        
            @Autowired
            private ProviderClient providerClient;
        
            @GetMapping("/hello")
            public String hello(@RequestParam String name) {
                return providerClient.hello(name);
            }
        }
        ```
        

---

### **2.2 使用 Nacos DiscoveryClient**

如果不使用 Feign，可以直接通过 `DiscoveryClient` 获取实例信息并手动调用。

```java
@RestController
public class ConsumerController {

    @Autowired
    private DiscoveryClient discoveryClient;

    @GetMapping("/hello")
    public String hello(@RequestParam String name) {
        // 获取服务实例列表
        List<ServiceInstance> instances = discoveryClient.getInstances("provider-service");

        // 简单负载均衡：选择第一个实例
        ServiceInstance instance = instances.get(0);
        String url = instance.getUri() + "/hello?name=" + name;

        // 使用 RestTemplate 调用服务
        RestTemplate restTemplate = new RestTemplate();
        return restTemplate.getForObject(url, String.class);
    }
}
```

---

## **3. 服务发现的动态性**

Nacos 的服务发现在业务代码中的动态性体现在以下方面：

### **3.1 动态实例感知**

- 当服务实例上下线时，Nacos 会自动通知消费者，消费者无需手动更新服务地址。
- Feign 或 Ribbon 等负载均衡工具会自动调整调用的目标实例。

### **3.2 动态负载均衡**

- 服务消费者可以根据实例权重或健康状态动态调整负载均衡策略。例如：
    
    ```java
    @Bean
    public IRule ribbonRule() {
        return new WeightedResponseTimeRule(); // 按响应时间权重分配流量
    }
    ```
    

### **3.3 多环境支持**

- 通过 `Namespace` 实现多环境隔离，在不同环境中调用不同的服务实例。

---

## **4. 服务发现的控制台可视化**

在 Nacos 控制台中可以直观查看服务发现的效果：

- **服务列表**：显示所有注册的服务及其实例。
- **实例信息**：包括 IP、端口、元数据、健康状态等。
- **调用追踪**：通过日志或链路追踪工具（如 SkyWalking）查看服务之间的调用关系。

---

## **5. 示例代码总结**

### **服务提供者代码**

```java
@RestController
public class ProviderController {

    @GetMapping("/hello")
    public String hello(@RequestParam String name) {
        return "Hello, " + name;
    }
}
```

### **服务消费者代码（Feign 调用）**

```java
@FeignClient("provider-service")
public interface ProviderClient {
    @GetMapping("/hello")
    String hello(@RequestParam String name);
}

@RestController
public class ConsumerController {

    @Autowired
    private ProviderClient providerClient;

    @GetMapping("/hello")
    public String hello(@RequestParam String name) {
        return providerClient.hello(name);
    }
}
```

---

## **6. 总结**

1. **服务提供者**通过 Nacos SDK 或框架集成将服务实例注册到 Nacos。
2. **服务消费者**从 Nacos 动态获取服务实例列表，并通过 Feign、Ribbon、RestTemplate 等工具调用服务。
3. Nacos 的服务发现功能简化了服务调用的配置和维护，提高了分布式系统的动态性和可靠性。