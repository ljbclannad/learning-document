# LLM（Large Language Model，大语言模型）

[TOC]

## 1. 一张全景图

大语言模型通常是以 Transformer 为主体、通过海量文本上的“预测下一个 token”任务训练出的神经网络。它根据输入上下文输出下一个 token 的概率分布，再按某种策略逐个生成 token。

```text
文本 -> tokenizer -> token IDs -> token/位置表示
     -> 多层 Transformer -> 下一个 token 的概率分布 -> 解码 -> 文本
```

“语言流畅”不等于“事实正确”。模型从训练数据中学习统计模式与表征，不是带版本、来源和权限的事实数据库；对私有或易变知识，参见 [[RAG|RAG]]。

## 2. Tokenization：文本如何变成模型输入

模型接收的不是字符或单词，而是一串整数 token ID。一个 tokenizer 包含词表、切分规则、规范化规则和特殊 token 定义；训练与推理必须使用完全一致的版本。

典型流程：

1. **规范化（可选）**：如 Unicode 规范化或处理不可见字符。规范化越激进，越可能丢失大小写、符号等信息。
2. **预分词**：按空格、标点、数字或正则规则粗分片段。
3. **子词切分**：将片段编码为子词或字节级 token。
4. **特殊 token 注入**：按模型要求加入 BOS、EOS、PAD 或对话模板标记。

token 数不等于字数或单词数；语言、数字、空格和标点都会影响它。上下文限制、推理延迟和 API 成本通常按 token 计算。

### 2.1 常见 token 化方案

| 方案 | 特点 | 典型问题 |
| --- | --- | --- |
| Word | 一词一 token | 词表膨胀，未登录词（OOV）严重。 |
| Character | 一字符一 token | 覆盖稳定，但序列较长。 |
| 子词（BPE、WordPiece、Unigram） | 在词表大小与序列长度间折中 | 行为依赖具体训练规则。 |
| Byte-level BPE | 以 UTF-8 字节为基础，几乎可编码任意文本 | 对人类不直观，中文可能占多个字节。 |

### 2.2 BPE 的核心直觉

BPE 从较小的基本符号出发，反复把语料中高频相邻符号对合并为新 token，直到达到目标词表规模。高频词干或片段会变成更长的 token，低频词则保留为较小片段，从而避免纯词级词表的 OOV 问题。

训练产物是词表（token <-> ID）和按优先级排列的 merge 规则。编码新文本时不再重新统计频率，而是按已学习的 merge 顺序合并。并列频率的处理、预分词和边界标记都会影响最终词表，因此 tokenizer 版本必须锁定。

Byte-level BPE 先将文本转为 UTF-8 bytes，再在字节序列上应用 BPE。某些实现会将不可打印 byte 映射为可显示字符，因此调试时常见的 `Ġ`、`Ċ` 只是空格或换行等字节的显示表示；它们不是模型理解出的特殊语义。

### 2.3 特殊 token 与对话模板

特殊 token 是训练协议的一部分。BOS/EOS 指定序列边界，PAD 用于 batch 对齐，某些模型还定义角色边界、工具调用或图像占位 token。错误的 chat template、padding side、BOS/EOS 设置即使不会报错，也可能明显改变模型行为。

## 3. 从数据到训练样本

原始数据可为连续文本、指令—回答对或多轮 messages。经过 tokenizer 和数据整理后，常见字段包括：

```text
input_ids:       token ID 序列
attention_mask:  哪些位置是有效 token
labels:          计算损失的目标；忽略位置通常标为 -100
```

对 decoder-only 的因果语言模型，训练目标是预测下一个 token；实现通常由模型内部完成一位偏移。指令微调（SFT）中，常将 system/user 提示部分的 labels 置为 `-100`，只对 assistant 的目标回答计算损失。具体边界必须和所用对话模板一致。

### 3.1 Padding、packing 与长文本

- **动态 padding**：每个 batch 对齐到本批最长样本，通常比固定长度省显存。
- **packing**：把多个短样本拼入长序列，提升 token 利用率；要正确处理样本边界和 loss mask。
- **截断**：简单可靠，但可能丢掉任务关键部分；应记录被截断比例。
- **滑动窗口与 stride**：长文本切窗时保留相邻窗口重叠。它适用于长文训练或 perplexity 评估，但会带来重复 token；使用 packing 时往往不需要。

训练成本更接近“每次更新处理了多少 token”，而不是样本条数：

```text
tokens_per_micro_step ≈ micro_batch_size × sequence_length
effective_batch ≈ micro_batch_size × gradient_accumulation × data_parallel_world_size
```

先确定任务所需序列长度，再在硬件上找到不溢出的 micro batch，最后通过梯度累积调整有效 batch。有效 batch、学习率和序列长度应作为一组实验变量记录，而非孤立调参。

## 4. Embedding：ID 如何成为向量

Token embedding 是一个可训练矩阵 E，形状为 `vocab_size × hidden_size`。输入 token ID `t` 时，模型取出第 `t` 行向量 `E[t]`。这只是 Transformer 的输入表示，不等同于 RAG 使用的句向量。

常见表示包括：

- **token embedding**：把 token ID 映射为向量；
- **位置信息**：绝对位置 embedding 或 RoPE 等相对/旋转位置编码，使模型感知顺序；
- **输出投影（LM head）**：把隐藏状态映射回词表大小以预测下一个 token。许多模型与输入 embedding 共享权重（weight tying）。

检索 embedding 则将整段文本编码为一个固定长度向量，通常由专门优化的 embedding 模型产生。文档与查询必须使用同一模型、同一指令前缀和归一化策略；余弦相似度、点积或欧氏距离的意义也取决于这些约定。详情见 [[RAG#4. 召回（Retrieval）|RAG 召回]]。

## 5. Transformer：模型怎样利用上下文

一个 Transformer block 通常由多头注意力、前馈网络、残差连接和归一化组成，多层堆叠后形成更抽象的表示。

### 5.1 Self-attention

每个 token 的表示会投影为 Query（Q）、Key（K）和 Value（V）。注意力使用 Q 与所有 K 的相似度计算权重，再对 V 加权求和：

```text
Attention(Q, K, V) = softmax(QK^T / sqrt(d_k)) V
```

因果语言模型使用 causal mask：当前位置只能关注自己及之前的 token，不能看到未来 token。多头注意力让模型并行学习不同类型的关联，例如指代、语法、局部搭配或远距离依赖。

注意力机制不意味着模型能无损“读取”整段上下文。上下文越长，成本、位置泛化、干扰信息和关键证据被忽略的风险都需要通过实际任务验证。

### 5.2 前馈网络、残差与归一化

注意力负责在 token 之间交换信息；前馈网络（MLP/FFN）则在每个位置独立进行非线性特征变换。残差连接为深层网络保留信息和梯度通路，LayerNorm/RMSNorm 有助于稳定训练。架构细节会因模型而异，但这四个组件构成理解 Transformer 的基本地图。

## 6. 训练、微调与推理

### 6.1 预训练与微调

预训练通常以海量文本的 next-token prediction 为目标；微调则在较小、任务相关的数据上继续优化。SFT 用于学习指令遵循和任务格式；LoRA 等参数高效微调方法通过训练少量附加参数降低资源需求。

微调并非知识库更新的默认答案：它难以精确删除或引用单条事实，且可能过拟合小数据。开始训练前应先有清晰任务、数据划分、基线、独立测试集和回滚方案。

### 6.2 解码与采样

模型每一步输出词表概率分布。贪心解码选择最高概率 token，稳定但可能保守；temperature 调整分布尖锐程度；top-p 或 top-k 只在部分候选中采样以控制随机性。对结构化输出、工具参数和高风险结论，通常应降低随机性，并结合 schema 校验和确定性规则。

### 6.3 常见工程误区

1. 将字符数当 token 数估算成本或上下文。
2. 更换 tokenizer、词表或 chat template，却继续使用旧模型权重或旧训练数据。
3. 将 padding token 计入 loss，或错误 mask 掉应学习的 assistant 回答。
4. 只因训练 loss 下降就认为模型变好；必须看独立评测和业务指标。
5. 把模型输出当作事实或执行授权；应使用 RAG、工具、校验与权限边界。

## 7. 学习与排障顺序

遇到效果问题，先检查数据格式、对话模板、token 截断和 labels mask，再检查评测集是否泄漏或覆盖不足，最后才调整模型、学习率或 LoRA 配置。训练过程至少记录数据版本、tokenizer、模型版本、超参数、随机种子、指标、成本和代表性失败样本。

对于 AI 应用工程，更完整的学习路线见 [[06-AI应用后端/机器学习/从 Agent 到机器学习：学习路径|从 Agent 到机器学习：学习路径]]。
