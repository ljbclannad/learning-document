# 千问Embedding + Milvus向量搜索集成文档

## 目录

1. [配置说明](#配置说明)
2. [千问Embedding服务](#千问embedding服务)
3. [Milvus向量搜索服务](#milvus向量搜索服务)
4. [完整使用示例](#完整使用示例)
5. [测试验证](#测试验证)

---

## 1. 配置说明

### 1.1 Maven依赖

```xml
<!-- pom.xml -->
<dependencies>
    <!-- HTTP客户端 -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <!-- JSON处理 -->
    <dependency>
        <groupId>com.alibaba</groupId>
        <artifactId>fastjson</artifactId>
        <version>2.0.43</version>
    </dependency>

    <!-- Milvus客户端 -->
    <dependency>
        <groupId>io.milvus</groupId>
        <artifactId>milvus-sdk-java</artifactId>
        <version>2.3.4</version>
    </dependency>
</dependencies>
```

### 1.2 application.yaml配置

```yaml
# src/main/resources/application.yaml

# 千问Embedding配置
qwen:
  embedding:
    api-key: ${QWEN_API_KEY:sk-your-api-key-here}
    api-url: https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding
    model: text-embedding-v3
    dimension: 1024
    timeout: 30000

# Milvus配置
milvus:
  host: localhost
  port: 19530
  database: default
  collection-name: customer_memories
  vector-dimension: 1024
```

---

## 2. 千问Embedding服务

### 2.1 配置类

```java

package com.sano.slmc.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Data
@Configuration
@ConfigurationProperties(prefix = "qwen.embedding")
public class QwenEmbeddingConfig {
    private String apiKey;
    private String apiUrl;
    private String model = "text-embedding-v3";
    private Integer dimension = 1024;
    private Integer timeout = 30000;
}
```

### 2.2 Embedding服务实现

```java
package com.sano.slmc.business.service.ai;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.sano.slmc.config.QwenEmbeddingConfig;
import lombok.extern.slf4j.Slf4j;
import org.apache.commons.lang3.StringUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * 千问Embedding服务
 * 用于生成文本向量
 */
@Slf4j
@Service
public class QwenEmbeddingService {

    @Autowired
    private QwenEmbeddingConfig config;

    private final RestTemplate restTemplate = new RestTemplate();

    /**
     * 生成查询向量
     * 
     * 输入：用户消息文本
     * 处理：调用千问API，将文本转换为1024维向量
     * 输出：float数组（1024维）
     * 
     * @param text 输入文本
     * @return 向量数组
     */
    public float[] generateQueryEmbedding(String text) {
        if (StringUtils.isBlank(text)) {
            throw new IllegalArgumentException("输入文本不能为空");
        }

        long startTime = System.currentTimeMillis();

        try {
            // 步骤1：构建请求
            Map<String, Object> requestBody = new HashMap<>();
            requestBody.put("model", config.getModel());
            requestBody.put("input", Map.of("texts", List.of(text)));

            // 设置文本类型为查询（用于检索场景）
            Map<String, Object> parameters = new HashMap<>();
            parameters.put("text_type", "query");
            requestBody.put("parameters", parameters);

            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            headers.set("Authorization", "Bearer " + config.getApiKey());

            HttpEntity<String> entity = new HttpEntity<>(
                JSON.toJSONString(requestBody),
                headers
            );

            log.info("生成查询向量: text={}", text.substring(0, Math.min(50, text.length())));

            // 步骤2：调用API
            ResponseEntity<String> response = restTemplate.exchange(
                config.getApiUrl(),
                HttpMethod.POST,
                entity,
                String.class
            );

            // 步骤3：解析响应
            JSONObject jsonResponse = JSON.parseObject(response.getBody());

            // 检查错误
            if (jsonResponse.containsKey("code")) {
                String errorCode = jsonResponse.getString("code");
                String errorMsg = jsonResponse.getString("message");
                throw new RuntimeException("千问API错误: " + errorCode + " - " + errorMsg);
            }

            // 提取向量
            JSONArray embeddings = jsonResponse.getJSONObject("output")
                .getJSONArray("embeddings");

            if (embeddings == null || embeddings.isEmpty()) {
                throw new RuntimeException("API返回的向量为空");
            }

            JSONArray embeddingArray = embeddings.getJSONObject(0)
                .getJSONArray("embedding");

            // 步骤4：转换为float数组
            float[] result = new float[embeddingArray.size()];
            for (int i = 0; i < embeddingArray.size(); i++) {
                result[i] = embeddingArray.getFloatValue(i);
            }

            long duration = System.currentTimeMillis() - startTime;
            log.info("查询向量生成成功: 维度={}, 耗时={}ms", result.length, duration);

            return result;

        } catch (Exception e) {
            log.error("生成查询向量失败: text={}", text, e);
            throw new RuntimeException("向量生成失败: " + e.getMessage(), e);
        }
    }

    /**
     * 生成文档向量（用于存储记忆）
     * 
     * @param text 文档文本
     * @return 向量数组
     */
    public float[] generateDocumentEmbedding(String text) {
        if (StringUtils.isBlank(text)) {
            throw new IllegalArgumentException("输入文本不能为空");
        }

        try {
            Map<String, Object> requestBody = new HashMap<>();
            requestBody.put("model", config.getModel());
            requestBody.put("input", Map.of("texts", List.of(text)));

            // 设置文本类型为文档（用于存储场景）
            Map<String, Object> parameters = new HashMap<>();
            parameters.put("text_type", "document");
            requestBody.put("parameters", parameters);

            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.APPLICATION_JSON);
            headers.set("Authorization", "Bearer " + config.getApiKey());

            HttpEntity<String> entity = new HttpEntity<>(
                JSON.toJSONString(requestBody),
                headers
            );

            log.info("生成文档向量: text={}", text.substring(0, Math.min(50, text.length())));

            ResponseEntity<String> response = restTemplate.exchange(
                config.getApiUrl(),
                HttpMethod.POST,
                entity,
                String.class
            );

            JSONObject jsonResponse = JSON.parseObject(response.getBody());

            if (jsonResponse.containsKey("code")) {
                String errorCode = jsonResponse.getString("code");
                String errorMsg = jsonResponse.getString("message");
                throw new RuntimeException("千问API错误: " + errorCode + " - " + errorMsg);
            }

            JSONArray embeddings = jsonResponse.getJSONObject("output")
                .getJSONArray("embeddings");

            JSONArray embeddingArray = embeddings.getJSONObject(0)
                .getJSONArray("embedding");

            float[] result = new float[embeddingArray.size()];
            for (int i = 0; i < embeddingArray.size(); i++) {
                result[i] = embeddingArray.getFloatValue(i);
            }

            log.info("文档向量生成成功: 维度={}", result.length);

            return result;

        } catch (Exception e) {
            log.error("生成文档向量失败: text={}", text, e);
            throw new RuntimeException("向量生成失败: " + e.getMessage(), e);
        }
    }
}
```

---

## 3. Milvus向量搜索服务

### 3.1 Milvus配置类

```java

package com.sano.slmc.config;

import io.milvus.client.MilvusServiceClient;
import io.milvus.param.ConnectParam;
import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Data
@Configuration
@ConfigurationProperties(prefix = "milvus")
public class MilvusConfig {

    private String host = "localhost";
    private Integer port = 19530;
    private String database = "default";
    private String collectionName = "customer_memories";
    private Integer vectorDimension = 1024;

    @Bean
    public MilvusServiceClient milvusClient() {
        ConnectParam connectParam = ConnectParam.newBuilder()
            .withHost(host)
            .withPort(port)
            .withDatabaseName(database)
            .build();

        return new MilvusServiceClient(connectParam);
    }
}
```

### 3.2 Milvus向量搜索服务

```java

package com.sano.slmc.business.service.ai;

import com.sano.slmc.config.MilvusConfig;
import io.milvus.client.MilvusServiceClient;
import io.milvus.grpc.DataType;
import io.milvus.grpc.SearchResults;
import io.milvus.param.MetricType;
import io.milvus.param.R;
import io.milvus.param.collection.FieldType;
import io.milvus.param.collection.CreateCollectionParam;
import io.milvus.param.dml.InsertParam;
import io.milvus.param.dml.SearchParam;
import io.milvus.response.SearchResultsWrapper;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import javax.annotation.PostConstruct;
import java.util.*;

/**
 * Milvus向量搜索服务
 */
@Slf4j
@Service
public class MilvusVectorService {

    @Autowired
    private MilvusServiceClient milvusClient;

    @Autowired
    private MilvusConfig config;

    /**
     * 初始化：创建Collection（如果不存在）
     */
    @PostConstruct
    public void init() {
        try {
            // 检查Collection是否存在
            R<Boolean> hasCollection = milvusClient.hasCollection(
                io.milvus.param.collection.HasCollectionParam.newBuilder()
                    .withCollectionName(config.getCollectionName())
                    .build()
            );

            if (hasCollection.getData()) {
                log.info("Milvus Collection已存在: {}", config.getCollectionName());
                return;
            }

            // 创建Collection
            createCollection();

        } catch (Exception e) {
            log.error("初始化Milvus失败", e);
        }
    }

    /**
     * 创建Collection
     */
    private void createCollection() {
        // 定义字段
        FieldType memoryIdField = FieldType.newBuilder()
            .withName("memory_id")
            .withDataType(DataType.VarChar)
            .withMaxLength(64)
            .withPrimaryKey(true)
            .build();

        FieldType customerIdField = FieldType.newBuilder()
            .withName("customer_id")
            .withDataType(DataType.VarChar)
            .withMaxLength(64)
            .build();

        FieldType embeddingField = FieldType.newBuilder()
            .withName("embedding")
            .withDataType(DataType.FloatVector)
            .withDimension(config.getVectorDimension())
            .build();

        FieldType createTimeField = FieldType.newBuilder()
            .withName("create_time")
            .withDataType(DataType.Int64)
            .build();

        // 创建Collection
        CreateCollectionParam createParam = CreateCollectionParam.newBuilder()
            .withCollectionName(config.getCollectionName())
            .addFieldType(memoryIdField)
            .addFieldType(customerIdField)
            .addFieldType(embeddingField)
            .addFieldType(createTimeField)
            .build();

        R<Void> response = milvusClient.createCollection(createParam);

        if (response.getStatus() == 0) {
            log.info("Milvus Collection创建成功: {}", config.getCollectionName());

            // 创建索引
            createIndex();

            // 加载Collection
            loadCollection();
        } else {
            log.error("创建Collection失败: {}", response.getMessage());
        }
    }

    /**
     * 创建向量索引
     */
    private void createIndex() {
        Map<String, Object> indexParams = new HashMap<>();
        indexParams.put("metric_type", MetricType.COSINE.name());
        indexParams.put("index_type", "IVF_FLAT");
        indexParams.put("params", "{\"nlist\":1024}");

        R<Void> response = milvusClient.createIndex(
            io.milvus.param.index.CreateIndexParam.newBuilder()
                .withCollectionName(config.getCollectionName())
                .withFieldName("embedding")
                .withIndexType(io.milvus.param.IndexType.IVF_FLAT)
                .withMetricType(MetricType.COSINE)
                .withExtraParam("{\"nlist\":1024}")
                .build()
        );

        if (response.getStatus() == 0) {
            log.info("向量索引创建成功");
        }
    }

    /**
     * 加载Collection到内存
     */
    private void loadCollection() {
        R<Void> response = milvusClient.loadCollection(
            io.milvus.param.collection.LoadCollectionParam.newBuilder()
                .withCollectionName(config.getCollectionName())
                .build()
        );

        if (response.getStatus() == 0) {
            log.info("Collection加载成功");
        }
    }

    /**
     * 插入向量
     * 
     * @param memoryId 记忆ID
     * @param customerId 客户ID
     * @param embedding 向量
     */
    public void insertVector(String memoryId, String customerId, float[] embedding) {
        try {
            List<String> memoryIds = Collections.singletonList(memoryId);
            List<String> customerIds = Collections.singletonList(customerId);
            List<List<Float>> embeddings = Collections.singletonList(toFloatList(embedding));
            List<Long> createTimes = Collections.singletonList(System.currentTimeMillis());

            List<InsertParam.Field> fields = new ArrayList<>();
            fields.add(new InsertParam.Field("memory_id", memoryIds));
            fields.add(new InsertParam.Field("customer_id", customerIds));
            fields.add(new InsertParam.Field("embedding", embeddings));
            fields.add(new InsertParam.Field("create_time", createTimes));

            InsertParam insertParam = InsertParam.newBuilder()
                .withCollectionName(config.getCollectionName())
                .withFields(fields)
                .build();

            R<io.milvus.grpc.MutationResult> response = milvusClient.insert(insertParam);

            if (response.getStatus() == 0) {
                log.info("向量插入成功: memoryId={}, customerId={}", memoryId, customerId);
            } else {
                log.error("向量插入失败: {}", response.getMessage());
            }

        } catch (Exception e) {
            log.error("插入向量失败: memoryId={}", memoryId, e);
            throw new RuntimeException("向量插入失败", e);
        }
    }

    /**
     * 搜索相似向量
     * 
     * 输入：查询向量、客户ID、返回数量
     * 处理：在Milvus中进行向量相似度搜索
     * 输出：最相似的记忆ID列表
     * 
     * @param customerId 客户ID
     * @param queryEmbedding 查询向量
     * @param topK 返回数量
     * @return 记忆ID列表（按相似度降序）
     */
    public List<String> searchSimilarVectors(String customerId, float[] queryEmbedding, int topK) {
        try {
            log.info("开始向量搜索: customerId={}, topK={}", customerId, topK);

            // 步骤1：构建搜索参数
            List<List<Float>> searchVectors = Collections.singletonList(toFloatList(queryEmbedding));

            String expr = String.format("customer_id == '%s'", customerId);

            SearchParam searchParam = SearchParam.newBuilder()
                .withCollectionName(config.getCollectionName())
                .withMetricType(MetricType.COSINE)
                .withTopK(topK)
                .withVectors(searchVectors)
                .withVectorFieldName("embedding")
                .withExpr(expr)
                .withParams("{\"nprobe\":10}")
                .build();

            // 步骤2：执行搜索
            R<SearchResults> response = milvusClient.search(searchParam);

            if (response.getStatus() != 0) {
                log.error("向量搜索失败: {}", response.getMessage());
                return new ArrayList<>();
            }

            // 步骤3：解析结果
            SearchResultsWrapper wrapper = new SearchResultsWrapper(response.getData().getResults());

            List<String> memoryIds = new ArrayList<>();

            for (int i = 0; i < wrapper.getRowRecords(0).size(); i++) {
                String memoryId = (String) wrapper.getIDScore(0).get(i).get("memory_id");
                float score = wrapper.getIDScore(0).get(i).getScore();

                log.info("找到相似记忆: memoryId={}, 相似度={}", memoryId, score);

                // 过滤低相似度结果
                if (score >= 0.7) {
                    memoryIds.add(memoryId);
                }
            }

            log.info("向量搜索完成: 找到{}条相关记忆", memoryIds.size());

            return memoryIds;

        } catch (Exception e) {
            log.error("向量搜索失败: customerId={}", customerId, e);
            return new ArrayList<>();
        }
    }

    /**
     * 删除向量
     */
    public void deleteVector(String memoryId) {
        try {
            String expr = String.format("memory_id == '%s'", memoryId);

            R<io.milvus.grpc.MutationResult> response = milvusClient.delete(
                io.milvus.param.dml.DeleteParam.newBuilder()
                    .withCollectionName(config.getCollectionName())
                    .withExpr(expr)
                    .build()
            );

            if (response.getStatus() == 0) {
                log.info("向量删除成功: memoryId={}", memoryId);
            }

        } catch (Exception e) {
            log.error("删除向量失败: memoryId={}", memoryId, e);
        }
    }

    /**
     * 转换float[]为List<Float>
     */
    private List<Float> toFloatList(float[] array) {
        List<Float> list = new ArrayList<>(array.length);
        for (float value : array) {
            list.add(value);
        }
        return list;
    }
}
```

---

## 4. 完整使用示例

### 4.1 记忆检索服务

```java

package com.sano.slmc.business.service.ai;

import com.sano.slmc.business.mapper.MemoryMapper;
import com.sano.slmc.business.model.ai.Memory;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

/**
 * 记忆检索服务
 * 整合：会话上下文 → 生成向量 → Milvus搜索
 */
@Slf4j
@Service
public class MemoryRetrievalService {

    @Autowired
    private SessionContextService contextService;

    @Autowired
    private QwenEmbeddingService embeddingService;

    @Autowired
    private MilvusVectorService milvusService;

    @Autowired
    private MemoryMapper memoryMapper;

    /**
     * 完整流程：检索相关记忆
     * 
     * @param customerId 客户ID
     * @param groupId 会话ID
     * @param userMessage 用户消息
     * @param topK 返回数量
     * @return 相关记忆列表
     */
    public List<Memory> retrieveRelevantMemories(
            String customerId,
            String groupId,
            String userMessage,
            int topK) {

        try {
            // 步骤1：获取会话上下文
            SessionContext context = contextService.getContext(groupId);
            log.info("【步骤1】获取会话上下文: topic={}, intent={}",
                context.getCurrentTopic(), context.getUserIntent());

            // 步骤2：构建查询文本
            String queryText = buildQueryText(context, userMessage);
            log.info("【步骤2】构建查询文本: {}", queryText);

            // 步骤3：生成查询向量
            log.info("【步骤3】生成查询向量...");
            float[] queryEmbedding = embeddingService.generateQueryEmbedding(queryText);
            log.info("【步骤3】查询向量生成成功: 维度={}", queryEmbedding.length);

            // 步骤4：Milvus向量搜索
            log.info("【步骤4】Milvus向量搜索...");
            List<String> memoryIds = milvusService.searchSimilarVectors(
                customerId,
                queryEmbedding,
                topK
            );

            if (memoryIds.isEmpty()) {
                log.info("【步骤4】未找到相关记忆");
                return new ArrayList<>();
            }

            log.info("【步骤4】找到{}条相关记忆", memoryIds.size());

            // 步骤5：从MySQL获取记忆详情
            log.info("【步骤5】获取记忆详情...");
            List<Memory> memories = memoryMapper.selectBatchIds(memoryIds);
            log.info("【步骤5】记忆详情获取成功: count={}", memories.size());

            return memories;

        } catch (Exception e) {
            log.error("检索记忆失败: customerId={}, message={}", customerId, userMessage, e);
            return new ArrayList<>();
        }
    }

    /**
     * 保存记忆（带向量）
     */
    public String saveMemory(String customerId, String groupId, String content) {
        try {
            log.info("保存记忆: customerId={}, content={}", customerId, content);

            // 1. 生成文档向量
            float[] embedding = embeddingService.generateDocumentEmbedding(content);

            // 2. 保存到MySQL
            Memory memory = new Memory();
            memory.setCustomerId(customerId);
            memory.setGroupId(groupId);
            memory.setContent(content);
            memory.setCreateTime(System.currentTimeMillis());
            memoryMapper.insert(memory);

            String memoryId = memory.getId();

            // 3. 保存向量到Milvus
            milvusService.insertVector(memoryId, customerId, embedding);

            log.info("记忆保存成功: memoryId={}", memoryId);
            return memoryId;

        } catch (Exception e) {
            log.error("保存记忆失败: customerId={}", customerId, e);
            throw new RuntimeException("保存记忆失败", e);
        }
    }

    /**
     * 构建查询文本（结合会话上下文）
     */
    private String buildQueryText(SessionContext context, String userMessage) {
        StringBuilder query = new StringBuilder();

        // 当前话题
        if (context.getCurrentTopic() != null) {
            query.append("话题：").append(context.getCurrentTopic()).append("。");
        }

        // 提取的关键数据
        if (!context.getExtractedData().isEmpty()) {
            query.append("数据：");
            context.getExtractedData().forEach((k, v) ->
                query.append(k).append("=").append(v).append("，")
            );
        }

        // 用户当前消息
        query.append(userMessage);

        return query.toString();
    }
}
```

### 4.2 首次无记忆场景处理

当用户首次进入系统或没有检索到相关记忆时，需要有降级处理策略。

#### 4.2.1 处理策略

```java
package com.sano.slmc.business.service.ai;

import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.Map;

/**
 * 无记忆场景处理服务
 */
@Slf4j
@Service
public class NoMemoryFallbackService {

    /**
     * 获取默认上下文（无记忆时使用）
     * 
     * @param customerId 客户ID
     * @param userMessage 用户消息
     * @return 默认上下文信息
     */
    public Map<String, Object> getDefaultContext(String customerId, String userMessage) {
        Map<String, Object> context = new HashMap<>();
        
        // 1. 基础欢迎信息
        context.put("greeting", "您好！我是您的健康助手，很高兴为您服务。");
        
        // 2. 引导性问题（帮助建立初始记忆）
        context.put("guideQuestions", new String[]{
            "请问您想咨询什么健康问题？",
            "您可以告诉我您的基本健康状况吗？",
            "您最近有什么健康方面的困扰吗？"
        });
        
        // 3. 标记为首次对话
        context.put("isFirstTime", true);
        
        log.info("生成默认上下文: customerId={}", customerId);
        
        return context;
    }

    /**
     * 生成首次对话的系统提示词
     * 
     * @return 系统提示词
     */
    public String getFirstTimeSystemPrompt() {
        return """
            这是用户的首次对话，当前没有历史记忆。
            
            请注意：
            1. 友好地欢迎用户
            2. 主动询问用户的基本信息和需求
            3. 在对话中提取关键信息，为后续建立记忆
            4. 保持耐心和引导性
            
            重点收集的信息：
            - 用户的健康状况
            - 用户的主要关注点
            - 用户的基本数据（年龄、性别等）
            """;
    }
}
```

#### 4.2.2 增强的记忆检索服务

```java
package com.sano.slmc.business.service.ai;

import com.sano.slmc.business.mapper.MemoryMapper;
import com.sano.slmc.business.model.ai.Memory;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * 增强的记忆检索服务（支持无记忆降级）
 */
@Slf4j
@Service
public class EnhancedMemoryRetrievalService {

    @Autowired
    private SessionContextService contextService;

    @Autowired
    private QwenEmbeddingService embeddingService;

    @Autowired
    private MilvusVectorService milvusService;

    @Autowired
    private MemoryMapper memoryMapper;

    @Autowired
    private NoMemoryFallbackService fallbackService;

    /**
     * 检索相关记忆（带降级处理）
     * 
     * @param customerId 客户ID
     * @param groupId 会话ID
     * @param userMessage 用户消息
     * @param topK 返回数量
     * @return 检索结果（包含记忆列表和上下文信息）
     */
    public MemoryRetrievalResult retrieveWithFallback(
            String customerId,
            String groupId,
            String userMessage,
            int topK) {

        MemoryRetrievalResult result = new MemoryRetrievalResult();

        try {
            // 步骤1：尝试检索记忆
            List<Memory> memories = retrieveMemories(customerId, groupId, userMessage, topK);

            if (memories.isEmpty()) {
                // 步骤2：无记忆时的降级处理
                log.info("未找到相关记忆，启用降级策略: customerId={}", customerId);
                
                result.setMemories(new ArrayList<>());
                result.setHasMemory(false);
                result.setFallbackContext(fallbackService.getDefaultContext(customerId, userMessage));
                result.setSystemPrompt(fallbackService.getFirstTimeSystemPrompt());
                result.setShouldCollectInfo(true);
                
            } else {
                // 步骤3：有记忆时的正常处理
                log.info("找到{}条相关记忆", memories.size());
                
                result.setMemories(memories);
                result.setHasMemory(true);
                result.setShouldCollectInfo(false);
            }

            return result;

        } catch (Exception e) {
            log.error("检索记忆失败，使用降级策略: customerId={}", customerId, e);
            
            // 异常时也使用降级策略
            result.setMemories(new ArrayList<>());
            result.setHasMemory(false);
            result.setFallbackContext(fallbackService.getDefaultContext(customerId, userMessage));
            result.setSystemPrompt(fallbackService.getFirstTimeSystemPrompt());
            result.setShouldCollectInfo(true);
            
            return result;
        }
    }

    /**
     * 内部方法：执行记忆检索
     */
    private List<Memory> retrieveMemories(
            String customerId,
            String groupId,
            String userMessage,
            int topK) {

        SessionContext context = contextService.getContext(groupId);
        String queryText = buildQueryText(context, userMessage);
        float[] queryEmbedding = embeddingService.generateQueryEmbedding(queryText);
        
        List<String> memoryIds = milvusService.searchSimilarVectors(
            customerId,
            queryEmbedding,
            topK
        );

        if (memoryIds.isEmpty()) {
            return new ArrayList<>();
        }

        return memoryMapper.selectBatchIds(memoryIds);
    }

    private String buildQueryText(SessionContext context, String userMessage) {
        StringBuilder query = new StringBuilder();

        if (context.getCurrentTopic() != null) {
            query.append("话题：").append(context.getCurrentTopic()).append("。");
        }

        if (!context.getExtractedData().isEmpty()) {
            query.append("数据：");
            context.getExtractedData().forEach((k, v) ->
                query.append(k).append("=").append(v).append("，")
            );
        }

        query.append(userMessage);
        return query.toString();
    }
}

/**
 * 记忆检索结果
 */
@Data
class MemoryRetrievalResult {
    private List<Memory> memories;
    private boolean hasMemory;
    private Map<String, Object> fallbackContext;
    private String systemPrompt;
    private boolean shouldCollectInfo;
}
```

#### 4.2.3 使用示例

```java
@Service
public class ConversationService {

    @Autowired
    private EnhancedMemoryRetrievalService memoryService;

    public String handleUserMessage(String customerId, String groupId, String userMessage) {
        // 检索记忆（带降级）
        MemoryRetrievalResult result = memoryService.retrieveWithFallback(
            customerId,
            groupId,
            userMessage,
            5
        );

        if (result.isHasMemory()) {
            // 场景1：有历史记忆
            return buildResponseWithMemory(result.getMemories(), userMessage);
        } else {
            // 场景2：首次对话，无记忆
            return buildFirstTimeResponse(
                result.getFallbackContext(),
                result.getSystemPrompt(),
                userMessage
            );
        }
    }

    private String buildResponseWithMemory(List<Memory> memories, String userMessage) {
        StringBuilder context = new StringBuilder("相关历史信息：\n");
        memories.forEach(m -> context.append("- ").append(m.getContent()).append("\n"));
        return callLLM(context.toString(), userMessage);
    }

    private String buildFirstTimeResponse(
            Map<String, Object> fallbackContext,
            String systemPrompt,
            String userMessage) {
        
        StringBuilder prompt = new StringBuilder();
        prompt.append(systemPrompt).append("\n\n");
        prompt.append("用户消息：").append(userMessage);
        return callLLM(prompt.toString(), userMessage);
    }

    private String callLLM(String context, String userMessage) {
        // 调用LLM API
        return "LLM生成的回复";
    }
}
```

#### 4.2.4 首次对话的记忆建立

```java
@Service
public class FirstTimeMemoryBuilder {

    @Autowired
    private MemoryRetrievalService memoryService;

    /**
     * 从首次对话中提取并保存关键信息
     */
    public void buildInitialMemories(
            String customerId,
            String groupId,
            String conversation) {

        // 1. 使用LLM提取关键信息
        List<String> keyInfoList = extractKeyInfo(conversation);

        // 2. 为每条关键信息创建记忆
        for (String info : keyInfoList) {
            try {
                memoryService.saveMemory(customerId, groupId, info);
                log.info("保存首次对话记忆: {}", info);
            } catch (Exception e) {
                log.error("保存记忆失败: {}", info, e);
            }
        }

        log.info("首次对话记忆建立完成: customerId={}, 记忆数={}", 
            customerId, keyInfoList.size());
    }

    private List<String> extractKeyInfo(String conversation) {
        // 调用LLM提取关键信息
        return List.of(
            "用户年龄35岁，性别男",
            "用户关注血糖管理",
            "用户有轻度高血压"
        );
    }
}
```

