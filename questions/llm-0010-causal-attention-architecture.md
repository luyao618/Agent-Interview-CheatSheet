---
id: llm-0010
title: Self-Attention 如何建立 Token 关系，因果掩码与 encoder、decoder 的用途有什么关系？
category: llm
tags: [self-attention, transformer, causal-mask, encoder-decoder, complexity]
difficulty: medium
role: engineer
contributor: 佚名
source: 洛小山《AI 产品从入门到精通》learn-ai（固定版本见参考）
status: published
updated: 2026-09-15
answers:
  - author: GPT-6
    type: ai
    model: GPT-6
    answered: 2026-09-15
    updated: 2026-09-15
---

## 问题

Self-Attention 如何建立 Token 关系，因果掩码与 encoder、decoder 的用途有什么关系？请解释 Q/K/V、缩放、多头与并行训练，并用三 Token 矩阵说明 causal prefill 与逐步 decode 的联系和复杂度边界。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-15

**Self-Attention 根据当前输入的 Q 与 K 计算位置之间的匹配权重，再用这些权重聚合 V，形成依赖上下文的新表示。** 因果 mask 决定哪些位置之间允许传递信息；encoder 常用双向可见性来编码已知输入，生成式 decoder 则限制目标序列只能依赖已有前缀。可见性、训练目标和执行阶段必须一起解释，不能从“用了 Attention”直接推断模型用途或调用费用。

### 1. 从 Q/K/V 到输出：关系由当前输入动态计算

设输入表示 `X` 的形状为 `n × d_model`。单头 self-attention 使用学习到的投影：

```text
Q = X W_Q     形状 n × d_k
K = X W_K     形状 n × d_k
V = X W_V     形状 n × d_v
S = Q K^T / sqrt(d_k)          形状 n × n
A = row_softmax(S + M)        形状 n × n
Y = A V                      形状 n × d_v
```

Q 表示当前位置用于查询的特征，K 表示各位置用于匹配的特征，V 是实际参与加权汇总的内容；这些是便于理解的分工，不是人工给每个维度指定的固定语义。`A[i,j]` 表示位置 `i` 的 query 对位置 `j` 的 value 分配多少权重，softmax 沿 **key 所在的列**逐行计算。这里的概率分布覆盖输入位置，**不是词表中下一 token 的输出概率**；后者还需要模型后续计算与输出头。

为什么除以 `sqrt(d_k)`？若 q、k 的各分量独立、零均值且方差为 1，点积的方差随 `d_k` 增长。缩放可控制分数尺度，减轻 softmax 过度饱和和梯度过小的问题。这是原论文解释缩放的假设，不是说实际训练后的 q、k 必然满足独立同分布。`W_Q/W_K/W_V` 是参数，`Q/K/V/A` 则随输入而变，不能把注意力矩阵当作固定的模型权重表。

多头机制使用不同的投影得到多个 `head_r`，分别做注意力，再计算 `Concat(head₁,…,headₕ) W_O`，让不同表示子空间的信息得到组合。常见实现把总宽度分给各头，而非每个头都保留完整宽度；头数增加不自动等于能力线性增加，也不能预先断定某个头必然负责“语法”或“因果”。在全可见、无位置项的 self-attention 中，重排输入也会相应重排输出；典型 Transformer 另加位置机制表达顺序，并配有残差、归一化和 FFN。

### 2. 因果 mask、encoder 和 decoder

对位置从左到右排列的序列，采用**加性 mask**：`M[i,j]=0` 当 `j≤i`，否则为 `-∞`。它在 softmax **之前**加入，让未来位置的权重变为 0，剩余可见位置重新归一化。这里允许看自身：输入位置 `i` 的表示用于预测下一个 token，监督标签需对齐为 `x_(i+1)`；看到 `x_i` 不等于偷看该目标。

| 架构 / 注意力类型 | Q、K、V 来源与可见性 | 适用条件与代价 |
| --- | --- | --- |
| Encoder-only，如原始 BERT 的双向编码 | 同一输入产生 Q/K/V；有效输入位置通常可彼此看见 | 适合完整文本的分类、抽取和匹配；可以预训练后迁移，但原始 MLM 用法并不是直接逐 token 续写的聊天生成器 |
| Decoder-only 的 causal self-attention | 同一序列产生 Q/K/V，每个 query 只看自身及左侧 | 适合开放式自回归生成，已知前缀可缓存；后续 token 选择有依赖，不能把自由生成当成一次并行分类所有未来位置 |
| Encoder-decoder | encoder 双向编码源文本；decoder 对目标前缀做 causal self-attention，并用 decoder 的 Q 对 encoder 的 K/V 做 cross-attention | 适合翻译、摘要等有明确输入/输出序列的任务；源文本只需编码一次，但增加了 encoder 和跨序列交互的计算与部署结构 |

这是典型配置的比较，不是仅凭模型名称判断所有变体。Cross-attention 的矩阵一般为“目标长度 × 源长度”；源文本已知，所以 decoder 可以读取完整源表示，不意味着能读取尚未生成的目标 token。因果 mask 管理的是信息可见性，并不会赋予模型对现实世界因果关系的证明能力。

**BERT 并非没有迁移能力。** 原论文正是“预训练双向表示，再针对下游任务微调”的路线，覆盖问答和语言推断等任务；不能把“它不是按原配置自由续写”误写成“每换任务都得从零训练”。同样，decoder-only 也能做分类或表示任务，架构选择还要结合训练目标和实际评测。

### 3. 三 Token 的可复核矩阵

以下是**人工设定输入的真实数值计算**，不是某个预训练模型的注意力测量。设三个 token 为 T₁/T₂/T₃，`n=3`，`d_model=d_k=d_v=2`，batch=1、单层单头；无 bias、位置项、dropout、残差或 FFN。向量值为无物理单位的示意数值，token 标签也不对应实际 tokenizer。

```text
X = [[1,0], [0,1], [1,1]]
W_Q = W_K = [[1,0], [0,1]]
W_V = [[1,2], [3,4]]
因此 Q = K = X，V = [[1,2], [3,4], [4,6]]。
```

将下列代码保存为 `attention_demo.py`，执行 `python3 attention_demo.py`，仅依赖标准库：

```python
from math import exp, isclose, isfinite, sqrt

def matmul(a, b):
    return [[sum(x * y for x, y in zip(row, col)) for col in zip(*b)] for row in a]

def softmax(row):
    peak = max(row)
    if not isfinite(peak):
        raise ValueError("每个有效 query 至少需要一个可见 key")
    weights = [exp(x - peak) for x in row]
    return [w / sum(weights) for w in weights]

# 人工输入与投影；单层、单头、无 bias/位置项/dropout/残差/FFN。
X = [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
Wq = Wk = [[1.0, 0.0], [0.0, 1.0]]
Wv = [[1.0, 2.0], [3.0, 4.0]]
Q, K, V = matmul(X, Wq), matmul(X, Wk), matmul(X, Wv)
dk = len(Q[0])
S = [[sum(q * k for q, k in zip(qi, kj)) / sqrt(dk) for kj in K] for qi in Q]
M = [[0.0 if j <= i else float("-inf") for j in range(3)] for i in range(3)]
A_full = [softmax(row) for row in S]
A_causal = [softmax([s + m for s, m in zip(row, mask)]) for row, mask in zip(S, M)]
Y = matmul(A_causal, V)
assert all(isclose(sum(row), 1.0) for row in A_causal)
assert all(A_causal[i][j] == 0.0 for i in range(3) for j in range(i + 1, 3))

# 对照路径：顺序追加 token，只缓存本层旧 K/V；当前 query 可见全部已有 key。
cached_k, cached_v, incremental = [], [], []
for xi in X:
    qi, ki, vi = matmul([xi], Wq)[0], matmul([xi], Wk)[0], matmul([xi], Wv)[0]
    cached_k.append(ki)
    cached_v.append(vi)
    scores = [sum(q * k for q, k in zip(qi, kj)) / sqrt(dk) for kj in cached_k]
    incremental.append(matmul([softmax(scores)], cached_v)[0])
max_error = max(abs(a - b) for row_a, row_b in zip(Y, incremental) for a, b in zip(row_a, row_b))
assert max_error < 1e-12

for name, matrix in (("S", S), ("M", M), ("A_full", A_full), ("A_causal", A_causal), ("Y_causal", Y)):
    print(name)
    for row in matrix:
        print("[" + ", ".join(f"{x:.6f}" for x in row) + "]")
print("decode token 3: [" + ", ".join(f"{x:.6f}" for x in incremental[2]) + "]")
print(f"max_abs_error={max_error:.2e}")
try:
    softmax([float("-inf")] * 3)
except ValueError:
    print("all-masked row: rejected")
else:
    raise AssertionError("无可见 key 的行必须显式处理")
```

**实际输出：2026-09-15，macOS arm64，Python 3.11.8。** 计算使用 Python 双精度浮点，矩阵仅在显示时舍入到小数点后六位；一致性断言使用未舍入值。

```text
S
[0.707107, 0.000000, 0.707107]
[0.000000, 0.707107, 0.707107]
[0.707107, 0.707107, 1.414214]
M
[0.000000, -inf, -inf]
[0.000000, 0.000000, -inf]
[0.000000, 0.000000, 0.000000]
A_full
[0.401112, 0.197776, 0.401112]
[0.197776, 0.401112, 0.401112]
[0.248255, 0.248255, 0.503490]
A_causal
[1.000000, 0.000000, 0.000000]
[0.330238, 0.669762, 0.000000]
[0.248255, 0.248255, 0.503490]
Y_causal
[1.000000, 2.000000]
[2.339523, 3.339523]
[3.006980, 4.510470]
decode token 3: [3.006980, 4.510470]
max_abs_error=0.00e+00
all-masked row: rejected
```

第一行只能使用 V₁，所以输出恰好为 `[1,2]`。第二行对前两个位置重新归一化，不是把 `A_full` 的第三列简单归零后就结束；第三行本来就没有未来位置，所以两种注意力的第三行一致。有效行的权重和为 1，但全被屏蔽的行没有合法分布：示例主动拒绝，真实批处理应明确处理 padding、无效 query 或错误 mask，不能把 NaN 当作正常结果。

### 4. 为什么训练和 prefill 能并行，decode 仍要逐步推进

训练时有真实输入序列，通过因果 mask 和错开一位的监督标签，可在一次前向中并行计算多个位置的表示与 loss；每个位置仍不能看见自己的未来目标。**“同时计算矩阵”与“允许看未来”是两回事。** teacher forcing 与自由生成的差异见 [llm-0008](llm-0008-next-token-training-inference.md)。

**Prefill** 对已知 prompt 一起计算各位置表示，并通常保存各层的 K/V；prompt 末位置的模型输出可用于选择第一个新 token。**Decode** 在某个新 token 已选出后，将它作为输入，计算新的 Q/K/V，用新 Q 访问缓存的旧 K/V 和当前 K/V，再由后续计算预测下一个 token。KV Cache 保存的是各层 K/V，**不是旧的完整注意力矩阵或已经写好的答案**。

上例用两条路径比较同一个三-token 前缀：一次 causal prefill 计算三行，以及按 T₁、T₂、T₃ 顺序追加的增量计算。第三步只有一个 query，却面对三个 key，得到与 prefill 第三行相同的结果；这也覆盖“先 prefill 前两个 token，再追加第三个”的数学情形。本例第三个 token 是给定输入，并没有运行词表采样或完整模型。

增量路径须按**绝对位置**对齐 mask：第三个 query 能看位置 0、1、2，不能机械地对 `1×3` 矩阵取左上角下三角，只保留第一个 key。真实模型还需保证位置编码、cache 位置和数值配置一致。基本 decode 的后续选择有依赖，优化实现可能一次验证多个候选，参见 [llm-0006：Speculative Decoding](llm-0006-speculative-decoding.md)。

### 5. O(n²) 到底描述什么

以下只讨论**单层、常规 dense 多头注意力**，令总宽度为 `d`、头数为 `h`；固定模型宽度、头数等参数后，再研究序列长度增长。投影和 FFN 的额外计算不能忽略：

| 场景 | 注意力核心运算 | 存储与限定 |
| --- | --- | --- |
| n-token 训练前向 / prefill | QKᵀ 与 AV 约为 `O(n²d)`；因果三角形仍是同一渐近阶 | 朴素显式 A 为 `O(hn²)`；线性投影及宽度成比例的 FFN 另有 `O(nd²)` 运算 |
| 带 KV Cache 的单 token decode，已有可见长度 L | 一个 query 对 L 个 key/value，约 `O(Ld)` | 常规 MHA 每层 K/V cache 为 `O(Ld)`；本步投影/FFN 另有约 `O(d²)`，不能把整次生成说成 O(L) |
| 从长度 n 的前缀继续生成 m 步 | 注意力部分累计约 `O((mn+m²)d)`，再加 prefill | 各步可见长度逐步增长；若不用 cache，反复重算前缀会额外增加工作 |

GQA/MQA 会改变 K/V cache 的常数与维度分配，sparse/linear attention 会改变计算结构，不能直接套表。FlashAttention 等 exact kernel 可以通过分块与重计算避免显式存下整张 n×n 权重矩阵，减少 HBM 读写；这不等于将 dense 注意力的算术量变成线性，也不保证端到端耗时恰好按 n² 增长。

**不能由 O(n²) 直接推断 API 账单。** 复杂度是运算随规模变化的描述；费用还取决于实际输入/输出用量、缓存读取/写入费率、模型和服务定价等。延迟也受计算内核、内存带宽、batch、调度、网络影响。不能声称上下文翻倍就必然收四倍钱或慢四倍，计费口径参见 [llm-0007](llm-0007-tokenization-bpe-budget.md)。本题不引用价格或性能基准数字。

## 延伸 / 追问

**追问一：因果 mask 挡住了未来，为什么仍能把全部训练 token 放进同一个矩阵？**

mask 限制每一行的信息来源，矩阵乘法可以并行执行这些受约束的行。只要层间保持正确 mask、标签正确移位，位置 i 的 next-token 预测就不会因并行而访问未来 token；若 mask 或标签错位，则可能发生训练泄漏，loss 很低也不能证明生成能力好。

**追问二：为什么 KV Cache 的单步结果可能和完整 prefill 不一致？**

先在关闭 dropout、固定权重和数值设置的条件下比对，再查 cache 位置、RoPE/位置编号、K/V 追加顺序、截断与 padding、矩形 mask 的对齐。小的浮点误差与系统性漏看 key 是不同问题；上例若第三步只允许看第一个 key，会错误地退化为 V₁。

**追问三：把 decoder 的 causal mask 去掉，就得到了适合分类的 BERT 吗？**

不会自动得到。可见性改变只是一步，BERT 的预训练目标、参数、输入约定和下游适配也不同。可以设计新训练方案，但仅在推理时更换 mask 会改变输入分布，必须重新验证；也不能据此否定 BERT 原有的预训练迁移能力。

## 常见误区

- **“Attention 是 O(n²)，所以 API 费用也按平方涨。”** 运算、显存、延迟和定价是不同口径，必须分别核对。
- **“BERT 只能做训练时那一个任务，没有迁移能力。”** 原始 BERT 就支持预训练后面向多种任务微调。
- **“mask 就是 softmax 后把未来权重乘零。”** 这会破坏行归一化；通常应在 softmax 前屏蔽非法分数。
- **“注意力热图就是模型的因果解释。”** A 是特征聚合权重，不等于现实因果关系或词表答案正确率。

## 参考

内容与数值示例独立编写，learn-ai 仅作学习线索，未移植其 AGPL 正文、代码或图片；矩阵为自编输入的实际计算，不是从课件热图或真实模型复制的结果。

- 洛小山，《AI 产品从入门到精通》learn-ai，固定版本 `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/1-2-gpt.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/1-2-gpt.html)、[slides/algo-2.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/algo-2.html)。
- Vaswani et al., *Attention Is All You Need*, 2017，固定 [arXiv:1706.03762v7 全文](https://arxiv.org/html/1706.03762v7)，§3.1、§3.2、§3.5 及 Table 1：缩放点积、多头、encoder/decoder 可见性、位置与复杂度；访问日期 2026-09-15。
- Devlin et al., *BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding*, NAACL 2019，[ACL Anthology N19-1423](https://aclanthology.org/N19-1423/)，双向预训练与下游微调的一手依据；访问日期 2026-09-15。
- Hugging Face，**Transformers v4.57.1**，固定 commit `8cb5963cc22174954e7dca2c0a3320b7dc2f4edc`：[`src/transformers/models/gpt2/modeling_gpt2.py::eager_attention_forward` L113](https://github.com/huggingface/transformers/blob/8cb5963cc22174954e7dca2c0a3320b7dc2f4edc/src/transformers/models/gpt2/modeling_gpt2.py#L113)，点积、缩放、因果 mask 对齐、softmax 和 V 聚合的实际实现。本题运行标准库数值示例，没有运行 GPT-2 权重。
- Dao et al., *FlashAttention: Fast and Memory-Efficient Exact Attention with IO-Awareness*, 2022，固定 [arXiv:2205.14135v1](https://arxiv.org/abs/2205.14135v1)，用于区分 exact attention 的 I/O 优化与算术复杂度；访问日期 2026-09-15。
