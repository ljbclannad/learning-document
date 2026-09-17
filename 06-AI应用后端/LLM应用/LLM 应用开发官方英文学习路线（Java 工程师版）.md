# LLM 应用开发官方英文学习路线（Java 工程师版）

# 第一部分：LLM 基础（Foundation）

## 1. OpenAI Developers ⭐⭐⭐⭐⭐

### 定位

LLM API 学习第一站。

几乎所有的大模型 API（Chat、Embedding、Function Calling、Agent）都可以在这里学习。

### 官网

https://developers.openai.com/

### API

https://platform.openai.com/docs/api-reference

### Cookbook

https://cookbook.openai.com/

### 推荐阅读

- Quickstart
- Models
- Responses API
- Function Calling
- Structured Outputs
- Embeddings
- Agents SDK
- Streaming
- MCP

学习重点：

- Prompt
- Token
- Context Window
- Tool Calling
- Structured Output
- Agent

## 2. Anthropic Documentation ⭐⭐⭐⭐⭐

### 定位

Prompt Engineering 最佳实践。

### 官网

https://docs.anthropic.com/

### 推荐阅读

- Prompt Engineering
- Long Context
- Tool Use
- JSON Output
- Streaming
- MCP

学习重点：

- Prompt Design
- Thinking Model
- Long Context
- Tool Use

# 第二部分：Java LLM 开发

## 3. Spring AI ⭐⭐⭐⭐⭐

### 定位

Java 官方 AI 框架。

Java 工程师几乎必学。

### 官网

https://docs.spring.io/spring-ai/reference/

### GitHub

https://github.com/spring-projects/spring-ai

### 推荐阅读

- ChatClient
- Prompt
- Advisors
- Tool Calling
- MCP
- VectorStore
- Memory
- RAG

学习重点：

- Spring Boot 接入 LLM
- ChatClient
- RAG
- MCP
- Tool Calling

# 第三部分：LLM Application Framework

## 4. LangChain ⭐⭐⭐⭐⭐

### 官网

https://docs.langchain.com/

### GitHub

https://github.com/langchain-ai/langchain

学习：

- Prompt
- Memory
- Tool
- Agent
- Retriever
- RAG

重点英语词汇：

Prompt

Runnable

Retriever

OutputParser

Memory

Tool

Chain

## 5. LangGraph ⭐⭐⭐⭐⭐

### 官网

https://langchain-ai.github.io/langgraph/

### GitHub

https://github.com/langchain-ai/langgraph

学习：

- StateGraph
- Node
- Edge
- Checkpoint
- Multi-Agent
- Human in the Loop

重点英语：

Workflow

Checkpoint

State

Transition

Node

Edge

Supervisor

# 第四部分：模型生态（Model Ecosystem）

## 6. Hugging Face ⭐⭐⭐⭐⭐

### 官网

https://huggingface.co/docs

### Models

https://huggingface.co/models

### Datasets

https://huggingface.co/datasets

学习：

- Models
- Transformers
- Tokenizer
- Dataset
- PEFT
- Sentence Transformers

重点英语：

Checkpoint

Tokenizer

Embedding

Fine-tuning

Dataset

Inference

Pipeline

# 第五部分：RAG（Retrieval-Augmented Generation）

## LlamaIndex

官网

https://docs.llamaindex.ai/

GitHub

https://github.com/run-llama/llama_index

学习：

- Document Loader
- Index
- Retriever
- Query Engine
- RAG Pipeline

重点英语：

Retriever

Chunk

Node

Index

Similarity Search

Metadata

# 第六部分：向量数据库（Vector Database）

## Milvus

官网

https://milvus.io/

文档

https://milvus.io/docs

GitHub

https://github.com/milvus-io/milvus

学习：

- Collection
- Index
- Search
- HNSW
- IVF
- Scalar Filter

重点英语：

Vector

Collection

Segment

Partition

Similarity Search

ANN

## pgvector

官网

https://github.com/pgvector/pgvector

学习：

- PostgreSQL Vector
- HNSW
- IVFFlat
- Embedding Storage

重点英语：

Extension

Operator

Distance

Cosine Similarity

Index

## Qdrant

官网

https://qdrant.tech/

文档

https://qdrant.tech/documentation/

GitHub

https://github.com/qdrant/qdrant

学习：

- Collection
- Payload
- Filter
- Snapshot
- Hybrid Search

重点英语：

Payload

Snapshot

Replica

Shard

Filter

# 第七部分：MCP（Model Context Protocol）

官网

https://modelcontextprotocol.io/

GitHub

https://github.com/modelcontextprotocol

学习：

- MCP Architecture
- Server
- Client
- Tool
- Resource
- Prompt

重点英语：

Protocol

Transport

Resource

Capability

Tool

Schema

# 第八部分：Agent

## OpenAI Agents SDK

https://openai.github.io/openai-agents-python/

学习：

- Agent
- Handoff
- Guardrails
- Tool

## LangGraph

https://langchain-ai.github.io/langgraph/

学习：

- Multi-Agent
- Workflow
- Checkpoint
- State Machine

# 第九部分：推理框架（Inference Engine）

## vLLM

官网

https://docs.vllm.ai/

GitHub

https://github.com/vllm-project/vllm

学习：

- Continuous Batching
- KV Cache
- Tensor Parallel
- OpenAI Compatible API

重点英语：

Scheduler

Batching

Prefill

Decode

KV Cache

Throughput

Latency

## SGLang

官网

https://docs.sglang.ai/

GitHub

https://github.com/sgl-project/sglang

学习：

- Structured Generation
- Runtime
- Scheduler
- Serving

重点英语：

Serving

Runtime

Grammar

Scheduler

# 第十部分：评测（Evaluation）

## LangSmith

官网

https://docs.smith.langchain.com/

学习：

- Trace
- Evaluation
- Dataset
- Experiment
- Monitoring

重点英语：

Trace

Run

Feedback

Evaluation

Monitoring

# 第十一部分：部署（Deployment）

## Ollama

官网

https://ollama.com/

GitHub

https://github.com/ollama/ollama

学习：

- Model Pull
- Local Deployment
- REST API

重点英语：

Serve

Pull

Model Manifest

Quantization

## Open WebUI

官网

https://docs.openwebui.com/

GitHub

https://github.com/open-webui/open-webui

学习：

- Local Chat
- Model Management
- RAG
- User Management

重点英语：

Workspace

Pipeline

Knowledge Base

Workspace

# 第十二部分：行业动态

## OpenAI Blog

https://openai.com/news/

关注：

- 新模型
- API
- Benchmark
- Agent

## Anthropic News

https://www.anthropic.com/news

关注：

- Claude
- MCP
- Prompt Engineering
- Research

# 推荐学习顺序

```
OpenAI
│
Anthropic
│
Spring AI
│
LangChain
│
LangGraph
│
Hugging Face
│
LlamaIndex
│
Vector Database
│
MCP
│
Agent
│
vLLM
│
LangSmith
│
Ollama
│
Open WebUI
│
OpenAI Blog
│
Anthropic News
```

---

