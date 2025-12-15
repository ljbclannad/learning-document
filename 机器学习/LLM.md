# LLM(Large Language Model)

# 1. 数据准备阶段

## 1.1 tokenization

1. LLM 的输入最终是一个 id 序列（整数数组）。所以 token 化要提供两样东西：文本 -> tokens -> token_ids，token_ids -> tokens -> 文本（解码）。

2. 核心目标：在“词表大小、序列长度、表达能力、跨语言鲁棒性、可训练性”之间做工程权衡。

3. Token 化的一般流水线（概念顺序）
    1. 规范化（Normalization，可选但常见），把“视觉上相似/等价”的文本统一一下，降低歧义与词表膨胀。常见操作：
        - Unicode 规范化（NFC/NFKC 等）
        - 全角/半角统一
        - 大小写处理（LLM多数保留大小写，不会强制 lower）
        - 去掉/替换不可见字符（零宽空格等）
        - 注意：规范化越激进，越可能损失信息（比如大小写、特殊符号），所以很多现代 tokenizer 选择“轻规范化”。
    2. 预分词（Pre-tokenization），把文本先粗切成片段（例如按空格、标点、数字边界），让后面的 BPE/Unigram 在“片段内”做子词学习。
        - GPT 系常见：用正则把空格、字母、数字、符号分组（你会看到 token 里经常带一个前置空格）
        - BERT 系（WordPiece）常见：按空格 + 标点拆分
        - 预分词的差异会直接导致：同样的 BPE 规则，切出来也不一样。
    3. 子词切分（Subword tokenization）
        - 在预分词片段内部，把字符串变成 token 序列（子词/字节/字符的组合）。

    4. 特殊符号注入（Special tokens）
        - 为了让模型“知道结构”，会加上特殊 token：
            - BOS/EOS（句子起止）
            - PAD（补齐 batch）
            - UNK（未知，一般 BPE/字节方案很少用）
            - SEP/CLS（BERT 类）
            - 以及对话模板相关的 <|system|> <|user|> <|assistant|> 等
        - 这一步在训练与推理时都极其关键：同样的文本，不同的 special token 方案，模型行为会变。

4. 三个你必须形成“肌肉记忆”的指标
	1.	词表大小（vocab size）
        - 大词表：单 token 信息量更大、序列更短，但 embedding 矩阵更大、稀有 token 学不好。
        - 小词表：更通用、覆盖好，但序列更长、注意力更贵（Transformer 计算量跟长度强相关）。
    2. 序列长度（sequence length）
        - Token 化的“压缩率”直接影响上下文窗口能塞多少内容，也影响推理成本。
    3. 可逆性 & 稳定性
        - 训练语料和线上输入必须用同一 tokenizer 版本；Tokenizer 改一点点，embedding 对应的 id 就全变了（灾难级）。

5. 常见 token 化流派（建立地图）
    - Word（按词）：词表爆炸、OOV（未登录词）严重，基本被淘汰
    - Character（按字符）：无 OOV，但序列太长
    - Subword（子词：BPE / WordPiece / Unigram）：工业主流
    - Byte-level（字节级 BPE）：对任意字符集天然覆盖，GPT 系常见，几乎不需要 UNK

6. 你在工程里会踩的坑（提前打疫苗）
    - “token 数 ≠ 字符数 ≠ 单词数”：中英文、数字、空格都会影响 token 数；成本评估别用字数估。
    - 空格很重要：很多 tokenizer 把“前置空格”编码进 token；同一句话前面多一个空格，token 序列可能不同。
    - 版本锁死：训练用 tokenizer A，线上千万别换 tokenizer B（哪怕词表大小一样也不行）。
    - 特殊 token 对齐：padding side、是否加 BOS/EOS、chat template 都会影响输出质量与长度。

## 1.2 BPE

### 1.2.1 BPE基础

BPE 一句话：用“最常见的相邻片段合并”把字符串压缩成更大的子词。它本质上是个 贪心的压缩算法：反复统计语料里“相邻符号对（bigram）”出现频率，每次把最常见的一对合并成一个新符号；直到词表达到目标大小。
“符号”一开始可以是：字符（classic BPE / many Word-level BPE）、字节（byte-level BPE，GPT 系最常见）、或者带了空格标记的“预分词片段”。
BPE 的效果：高频片段变成一个 token（序列更短），低频词就拆成更小的片段（避免 OOV）。

1. BPE 解决的核心矛盾：词表大小 vs 序列长度 vs OOV
	•	纯按“词”切：词表爆炸、未登录词（OOV）多。
	•	纯按“字/字符”切：没 OOV，但序列太长，Transformer 计算贵。
	•	BPE：在两者之间做折中
	•	常见词/词干/后缀会被合成大 token（短）
	•	生僻词会被拆成较小 token（覆盖好）

2. Classic BPE 训练流程（最常见讲法）
    1. 输入是什么？
        - 通常不是“整段文本”，而是 word 级别的频次表（从语料统计得到）：
        - 你先做 basic 预分词（比如按空格/标点切出词）
        - 统计每个 word 出现次数 freq(word)
        - 然后把每个 word 表示成“符号序列”

    2. 初始符号怎么表示？
        - 经典做法：字符序列 + 词尾标记（很重要）
        - 例如单词 "low" 变成：l o w </w>
        - </w>（end-of-word）保证 “low” 和 “lower” 的边界信息不会乱串。
        - 如果没有 </w>，你可能把跨词边界的东西学进去，导致解码/切分怪异。

    3. 每一轮做什么？
        - 重复下面步骤直到词表大小到达目标（或 merge 次数达到上限）：
        - 统计所有“相邻符号对”的出现次数（按 word 频次加权）
        - 找到出现次数最高的一对 (A, B)
        - 合并为新符号 AB
        - 在所有 word 的符号序列中，把 A B 替换成 AB
        - 记录这次 merge（非常关键：推理时要按这个顺序应用）

    4. 手推一个经典例子（面试讲得最稳）
        - 语料（假设每个出现 1 次）：
            - low
            - lower
            - newest
            - widest

        - 初始表示
            - low    -> l o w </w>
            - lower  -> l o w e r </w>
            - newest -> n e w e s t </w>
            - widest -> w i d e s t </w>

        - 统计相邻对（只列一些直观高频的）：
            - e s：在 newest、widest 里都有 → 2 次
            - s t：在 newest、widest 里都有 → 2 次
            - l o：在 low、lower 里都有 → 2 次
            - o w：在 low、lower 里都有 → 2 次
            - w </w>：在 low 里 1 次（lower 里不是）→ 1 次

        - 这时最高频可能有并列（2 次的好几个）。真实实现里需要 tie-break 规则（例如字典序/先出现/哈希顺序），不同规则会导致不同词表（但大体相似）。
        - 假设我们先合并 e s：
            - Merge #1: e s -> es
            - newest -> n e w es t </w>
            - widest -> w i d es t </w>

        - 再合并 l o -> lo：
            - Merge #3: l o -> lo
            - low   -> lo w </w>
            - lower -> lo w e r </w>

        - 再合并 lo w -> low：
            - Merge #4: lo w -> low
            - low   -> low </w>
            - lower -> low e r </w>

        - 你会看到规律：BPE 很自然地学到高频后缀 est、高频词干 low。这就是它“自动发现子词结构”的来源（虽然它并不懂语言学，只是在做压缩）。

3. 推理/编码阶段：怎么把新文本切成 token？
    - BPE 训练产物通常是两样：
        - vocab：token -> id（以及反向 id -> token）
        - merges（ranked）：每条 merge 规则及其优先级（顺序）
    - 编码步骤（以一个 word 为例）：
        - 初始把 word 切成最小符号（字符或字节）+ </w>（或用其他边界符）
        - 在当前符号序列里，找到所有相邻对
        - 按 merge rank（越早学到 rank 越小，优先级越高）不断合并，直到不能再合并
    - 关键点：不是“每轮找频率最高的对”，那是训练时做的。推理时你只按训练时学到的 merge 顺序做替换（按 rank）。
    - 实现上常见两种：
        - 简单版：循环扫描、按 rank 找能合并的最优对（慢但好写）
        - 工业版：用优先队列（heap）维护可合并对的最小 rank，局部更新（快）

4. 为什么 GPT 系喜欢 Byte-level BPE？
    - Classic BPE 仍可能遇到 UNK（比如遇到奇怪字符、emoji、罕见符号等），除非你的初始符号集覆盖所有 Unicode。
    - Byte-level BPE 的骚操作：先把文本变成 UTF-8 bytes（0–255），把每个 byte 当成初始符号，然后跑 BPE merge。
    - 好处：理论上对任意文本都可编码（几乎不需要 UNK），多语言/符号更鲁棒，词表大小可控（初始 256 个符号 + merges）
    - GPT-2 还做了一步“byte→unicode 映射”（把 0–255 映射到可打印字符集合），方便把 byte token 存成字符串形式（便于 merges.txt / vocab.json）。

5. BPE 和 WordPiece / Unigram 的差别（你学 BPE 后必须能区分）
    - BPE：合并规则由“最频繁相邻对”贪心产生（压缩视角）
    - WordPiece（BERT 常见）：目标更像“让训练数据的似然更大”（但工程上也很像 BPE 的合并过程），并且常用 ## 表示“非词首子词”
    - Unigram（SentencePiece 常见）：先给一个很大的候选子词集合，然后“删掉最不重要的”，用概率模型选最优切分（更像统计建模）
    - BPE 是“拼积木：越常一起出现就粘起来”；Unigram 是“砍树枝：保留最有用的子词”。

6. 工程细节：你真做 tokenizer 会遇到的坑
    1. tie-break（并列频次怎么选）
        - 同频次的 pair 很多，选择策略会影响词表细节。
        - 工业实现会固定规则保证可复现，否则训练一次词表一次样。

    2. 边界标记/空格策略
        - classic BPE 用 </w> 防止跨词串联
        - GPT 系更常把“空格”编码进 token（比如 token 里带前导空格），这样模型更容易学到“词边界”

    3. 预分词决定上限
        - 预分词切得越碎，BPE 只能在碎片内合并；切得越粗，BPE 搜索空间大但训练更慢，也可能把奇怪片段合成一个 token。

    4. 版本一致性是铁律
        - Tokenizer 的 vocab + merges + normalization + pretokenization + special tokens 任何一项变了，token id 序列就变，模型就像突然“换了字典”。

### 1.2.1 Byte-level BPE 的完整流程（regex 预分词 → bytes 映射 → merges 应用 → decode）以及为什么 GPT 的 token 里会出现奇怪字符（Ġ、Ċ 之类）

1. 总览：Byte-level BPE 的“数据形态变化”。一段文本 "Hello world\n" 进入 tokenizer，大概经历：
    1. 文本字符串（Unicode）
    2. regex 预分词得到若干片段（仍是字符串）
    3. 每个片段转 UTF-8 bytes（0–255 的字节序列）
    4. bytes→unicode 映射（把每个 byte 映射成一个“安全可打印”的 Unicode 字符）
    5. 在这些“伪字符”上跑 BPE merges（合并得到子词 token）
    6. token → id（查 vocab）
    7. 解码反向：id → token → 伪字符 → bytes → UTF-8 → 原文本

关键：Byte-level BPE 的“最小原子”不是字符、也不是词，而是 byte。所以它几乎不需要 UNK（任何文本都能变成 bytes）。

2. Regex 预分词：先切片，再在片内做 BPE
    1. 典型 regex 长什么样（GPT-2 家族）
        - 经典 GPT-2 的预分词 regex（核心思想）是把文本分成几类片段：
            - 英文字母序列（可带一个前导空格）
            - 数字序列（可带一个前导空格）
            - 标点/符号序列（可带一个前导空格）
            - 纯空白（空格、换行等）
        - 你会看到一种很“有意为之”的设计：很多规则前面写了一个可选空格  ?。这导致切出来的片段常常是 " world"（前面带空格），而不是 " " 和 "world" 分开。
        - 因为英语里空格极高频。把“空格 + 单词”作为整体更容易被合并成一个 token（更短、更省算力）。这也是你经常见到 token 里有“空格痕迹”的根源之一。

3. UTF-8 bytes：把 Unicode 文本变成 0–255 的字节流
- 对每个预分词片段 piece：
    - 用 UTF-8 编码：piece.encode("utf-8")
    - 得到字节序列，比如：
        - " "（空格） → byte 32
        - "\n"（换行） → byte 10
        - "你" → UTF-8 bytes 可能是 3 个 byte（中文通常 3 个）
    - 这一步就是 Byte-level 的“底座”：再怪的字符也能落到 bytes 上。

4. bytes → unicode 映射：Ġ、Ċ 等怪字符从哪来？
    1. 为什么要做这个映射？
        - BPE 合并规则通常用“字符串”来表达和存储（vocab.json、merges.txt 这种）。
        - 但 raw bytes 里有大量 不可打印字符 / 控制字符 / 空白字符（比如 0、10、13、32），直接放进文本文件、JSON、正则处理会非常痛苦，甚至会被编辑器/解析器吞掉或改写。
        - 所以 GPT-2 家族做了个聪明但有点邪门的工程技巧：把每个 byte (0–255) 映射成一个 唯一的、可打印的 Unicode 字符，保证：1 byte ↔ 1 unicode 字符（可逆），这些字符尽量不包含真正的空白/控制符，存文件安全

    2. Ġ 和 Ċ 的含义（最常见的两个）
        - 在这套映射里，经常会出现：
            - Ġ（U+0120）：常用来表示 空格 byte 32
            - Ċ（U+010A）：常用来表示 换行 byte 10

        - 所以你看到的不是“模型学会了爱尔兰语字母”，而是：
            - “这个 token 里包含一个空格/换行 byte”
            - 只是 tokenizer 用一个“可打印符号”把它显示出来了

    3. 为什么不同模型的“怪字符”不完全一样？
        - 映射表是实现细节，不同 tokenizer 可能：
            - 用同一套 GPT-2 映射（很多会这样）
            - 或者用别的可逆表示
            - 或者干脆不把 bytes 映射成 unicode，而是内部直接操作 bytes（例如一些更现代的实现）
        - 但你在调试里看到 Ġ/Ċ，基本都指向“byte-level + 可打印映射”这条路线。

5. BPE merges 应用：在“伪字符序列”上合并
    1. 把一个片段转成“伪字符”后，例如：
        - 片段 " world"
        - 前导空格 byte 32 → Ġ
        - "world" 的各字母 bytes → 映射成对应字符
        - 得到类似 "Ġworld"（这是概念表示）
        - 然后在这个“字符序列”上应用 merges：
            - ("Ġ", "w") -> "Ġw"
            - ("Ġw", "o") -> "Ġwo"
            - ("Ġwo", "r") -> "Ġwor"
            - ……
        - 真实 merges 会更复杂，但思路一样：相邻对合并。

    2. 推理时怎么合并（关键点）
        - 推理/编码阶段不会再统计频率了，只会：
            - 从当前符号序列里找“可合并的相邻对”
            - 按 merges 的 rank（越早学到 rank 越小，优先级越高）不断合并
            - 直到没有任何相邻对出现在 merges 表里
        - 最后得到若干子词 token（每个 token 是一个字符串，例如 "Ġworld"、"hello"、"Ċ" 或更长组合）。

    3. 为什么常见 token 形态是：Ġword
        - 因为预分词把空格往后粘、映射把空格显示成 Ġ、BPE 又很乐意把高频片段“Ġ + word”整体合并。
        - 于是你调试 token 时，第二个词开始经常长这样：
            - Hello → "Hello"
            - world → "Ġworld"

    4. token → id：查 vocab
        - 把 BPE 合并出来的“token 字符串”，还要用 vocab 映射成整数 id：
            - id = vocab[token]
        - 到这里就得到模型输入的 input_ids 了。

6. Decode：把 id 还原回原始文本（完全可逆）
    1. 反向流程：
        - ids -> tokens（用 id_to_token 查回字符串）
        - 把每个 token 字符串拆成“伪字符”
        - 用 unicode→byte 的逆映射把每个伪字符还原成 byte（0–255）
        - 把 bytes 拼接成一个 byte 数组
        - 用 UTF-8 解码回字符串（必要时处理错误策略）
    
## 1.3 dataset

1. LLM 里的 dataset 到底长什么样
- 你从原始数据（文本/指令/对话/QA）走到训练输入，通常要经历 3 层形态：
    - 原始样本层（raw examples）
        - 纯文本：{"text": "…"}
        - 指令微调：{"instruction": "...", "input": "...", "output": "..."}
        - 对话：{"messages": [{"role":"user","content":"..."}, ...]}
    - token 化后的样本层（tokenized examples）
        - 典型字段：
            - input_ids: [int, int, ...]
            - attention_mask: [0/1, ...]
            - (可选) token_type_ids（多数 decoder-only 不用）
            - labels: 训练目标（语言模型一般是把 input_ids 右移一位；指令微调会把提示部分 mask 掉）
    - batch 层（collate 后）
        - 把一批样本对齐成张量：
            - padding 到同一长度（或用 packing 把多个短样本塞进一个长序列）
            - 生成 batch 的 input_ids/attention_mask/labels

2. batchsize：不要只盯“样本数”，要盯“tokens/step”
    1. LLM 训练的成本主要跟 每一步的 token 数量 相关：
        - tokens_per_step ≈ micro_batch_size × seq_len
        - 真正影响优化的是 effective batch：
        - effective_batch = micro_batch_size × gradient_accumulation_steps × data_parallel_world_size
    2.  micro batch size（你显存能装下的那个）
        - 显存最主要受这几个影响：
            - 模型参数量
            - 序列长度 seq_len（注意 Transformer 注意力是 O(seq_len^2)，长度上去显存/算力都爆）
            - batch size
        - 实操做法（最稳的工程习惯）：
            - 先定 seq_len（比如 1024/2048/4096）
            - 用你的硬件试到 不 OOM 的最大 micro_batch_size
            - 再用 梯度累积 把 effective batch 拉到你想要的规模
    3. 目标 tokens/step 的经验范围（给你个“落地标尺”）
        - 小模型/小数据微调：每步 8k ~ 128k tokens 都常见
        - 更大规模训练：会更大（但那是集群玩法了）
        - 你在单机/单卡做微调，常见组合：
            - seq_len=2048, micro_batch=2 → 4096 tokens/step
            - grad_accum=16 → 65536 tokens/update（这就已经很像样了）

    4. 学习率和 batchsize 是绑定的
        - effective batch 变大，通常学习率也能适当放大（但别机械线性放大，微调更敏感）。    
effective batch 变大，通常学习率也能适当放大（但别机械线性放大，微调更敏感）。
        - 如果你只是想“先跑通”，优先保证 不 OOM + loss 正常下降，再调 batch/lr。

3. stride：它是“滑动窗口重叠”，主要用于长文本切块
    - stride 的语义：当你把一段长文本切成固定长度 max_length 的块时，相邻块之间重叠多少 token。
        - 步长 step = max_length - stride
        - stride 越大 → 重叠越多 → 上下文连续性更好，但训练数据重复更多、训练更慢
        - stride 越小 → 重叠少 → 训练更快，但块与块之间上下文断裂更明显
    - 
4. stride 最常见的两个场景
    - 场景 A：评估 perplexity（非常常见）
        - 为了不浪费尾部 token，且保证上下文连贯，会用 sliding window：
            - 例如 max_length=2048, stride=512
            - 让每个窗口都带一部分前文上下文
    - 场景 B：生成 tokenized chunks（不做 packing 时）
        - 你把长文章切成训练块，希望模型既看到全局内容，又别断得太狠：
            - max_length=2048
            - stride=128~512（大约是 5%~25% overlap，比较常见）
    - 训练时 stride 一定需要吗？
        - 不一定。现在很多训练会用 packing（样本拼接）：
            - 把多个短样本拼成一个长序列，几乎不需要 stride
            - 长文章如果本身就超长，要切块时 stride 才更有意义

5. 重要参数清单（你调参时最常碰到的）
    - Tokenizer / 切块相关
        - max_length / model_max_length：单条样本最大长度（决定显存/算力上限）
        - truncation=True：超长就截断（训练时常用）
        - padding：
            - False：不 pad，交给 collator 动态 pad（推荐）
            - "max_length"：固定 pad 到 max_length（吞显存但形状稳定）
        - return_overflowing_tokens=True：让 tokenizer 把长文本切成多个窗口（滑窗）
        - stride：配合 overflowing 使用的重叠长度
        - pad_to_multiple_of=8/16：对齐到 Tensor Core 友好形状（吞吐常能涨）
    - HF Datasets 处理相关
        - dataset.map(batched=True, batch_size=...)：批处理 tokenization，快很多
        - remove_columns=[...]：删掉原始列，节省内存/IO
        - num_proc：多进程 map（CPU 强时很好用）
        - streaming=True：超大数据不落盘，边读边训（IterableDataset）
        - shuffle(seed, buffer_size=...)：streaming 时是“缓冲区洗牌”，不是全量洗牌
    - PyTorch DataLoader 相关
        - batch_size：你给的“样本数”，但真正消耗看 seq_len
        - drop_last=True：避免最后一个 batch 太小导致形状波动
        - num_workers：CPU 并行取数据（一般 2~8 起步，视 CPU/磁盘）
        - pin_memory=True：GPU 训练常开
        - prefetch_factor：worker 预取（吞吐不稳时可以调）
    - collator / labels 相关
        - causal LM（decoder-only）：
            - labels 往往就是 input_ids（内部 loss 会 shift）
            - padding 部分要置 -100（忽略 loss）
        - 指令微调（SFT）：
            - prompt 部分通常也置 -100，只让模型在 answer 部分算 loss
            - 你要非常确定“哪些 token 该学、哪些不该学”
    - 两段最常用的代码模板（带 stride）
        - 长文本滑窗切块（stride 生效）
            - 适合：一篇文章很长，你要切成多个训练窗口。
            - ```python
                def tokenize_sliding(examples):
                    out = tokenizer(
                        examples["text"],
                        max_length=2048,
                        truncation=True,
                        return_overflowing_tokens=True,
                        stride=256,                 # 重叠 256
                        padding=False,
                    )
                    # out 会产生多个窗口：input_ids 是“展开后的多条样本”
                    return out
            ``` 
            - tokenized = raw_ds.map(tokenize_sliding, batched=True, remove_columns=raw_ds.column_names)
        - 经典 CLM chunk（不重叠，更偏 packing 前的准备）
            - ```python
                def tokenize(examples):
                    return tokenizer(examples["text"], truncation=False)
                def group_texts(examples, block_size=2048):
                    # 把一批样本拼接再切块
                    concat = sum(examples["input_ids"], [])
                    total = (len(concat) // block_size) * block_size
                    concat = concat[:total]
                    return {"input_ids": [concat[i:i+block_size] for i in range(0, total, block_size)]}
            ```
        - 一套“不会错”的 batchsize + stride 选择顺序
            - 先定 seq_len（你的模型上下文、任务需要、显存承受范围）
            - 找到最大 micro_batch_size（跑一两个 step，确保不 OOM）
            - 用 grad_accum 拉到你想要的 tokens/update
            - stride：
                - 训练如果用 packing/拼接：stride 通常不重要或 0
                - 长文切块/评估 ppl：优先 128~512，别太大避免重复过多

## 1.4 embdding(向量)