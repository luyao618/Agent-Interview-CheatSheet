---
id: llm-0024
title: 困惑度 Perplexity 应怎样计算，为什么不能直接用它比较不同聊天模型的能力？
category: llm
tags: [perplexity, evaluation, cross-entropy, sliding-window, tokenization]
difficulty: medium
role: engineer
contributor: 佚名
source: Hugging Face 官方 Perplexity 文档扩展改编；固定版本 loss 源码核实（见参考）
status: published
updated: 2026-10-01
answers:
  - author: GPT-6-Astra
    type: ai
    model: GPT-6-Astra
    answered: 2026-10-01
    updated: 2026-10-01
---

## 问题

团队要比较两个聊天模型：A 的评测报告 PPL 更低，于是有人断言 A 更擅长遵循指令。另一位同事把每个 batch 的 PPL 取算术平均，长文则切成不重叠片段分别计算。

这些结论和实现有哪些问题？请解释 PPL 与交叉熵的关系，给出正确的跨 batch 汇总方式，并说明 tokenizer、label mask、滑动窗口及评测目标如何影响可比性。

本题根据 Hugging Face 官方文档的评测问题独立改编，不是公司面试原题；下方代码是计算口径验证，不是实际模型评测。

## 答案 · GPT-6-Astra

> 🤖 AI 答案 · 模型：GPT-6-Astra · 回答 2026-10-01

**PPL 衡量模型在指定文本与条件上下文下，对实际出现的目标 token 分配概率的能力。** 它是语言建模指标，不是对话质量、事实正确性、工具调用或指令遵循能力的总分。先统一数据与计分口径，再比较数值；不能仅凭较低 PPL 就决定上线哪个聊天模型。

[llm-0008](llm-0008-next-token-training-inference.md) 介绍 next-token 训练与推理，[llm-0007](llm-0007-tokenization-bpe-budget.md) 介绍 tokenization 与预算；本题聚焦评测统计量、计数和比较协议。

### 1. PPL 是平均负对数似然的指数

设 E 为实际参与计分的目标位置集合，N 为其大小。每个目标 token 的条件由评测协议确定，包括前文、窗口截断和边界 token：

```text
NLL_sum = -sum(log p_theta(x_i | context_i) for i in E)
mean_NLL = NLL_sum / N
PPL = exp(mean_NLL)
```

这里 log 使用自然对数；若用以 2 为底的平均负对数，则用 `2 ** mean_NLL_bits`，不能混用底数。标准 one-hot next-token 交叉熵在相同计分位置上的均值与 mean_NLL 一致。

- 模型对每个目标都给概率 1 时，PPL 为 1；真实目标被赋予 0 概率时，NLL 发散。
- 对一个 V 类均匀分布，PPL 为 V；这是特例，不表示任意 PPL 都能解释为模型实际“只考虑了这么多个词”。
- 不应拿包含 label smoothing、额外正则项或不同加权规则的总 training loss 直接取 exp，冒充标准 PPL。
- 评测通常用真实前缀做 teacher forcing，而不是先让模型自由生成，再只给自己生成的内容评分。否则测量对象已经变了。

### 2. 跨 batch 汇总必须按有效目标 token 加权

假设第 b 批平均 NLL 为 L_b，有效计分 token 数为 N_b：

```text
corpus_PPL = exp(sum(L_b * N_b) / sum(N_b))
```

**不能直接平均 batch PPL，也不能在 batch 长度不同的时候无权平均 batch loss。** 不同文档等权的统计可以单独定义，但不是上述 corpus token-level PPL，必须明确命名。

分母不是 batch_size×sequence_length，也不一定等于 attention mask 中 1 的数量。padding、只作上下文的重叠片段、prompt-only 位置都可能不计 loss；应数与 logits 对齐后真正进入交叉熵的 labels。

对于本文引用的 `ForCausalLMLoss` 默认路径，labels 在右侧补 ignore_index 后左移一位，因此原 labels 的首位不参与 next-token 计分。其有效标签数可由 `labels[..., 1:] != -100` 统计，末尾补入的忽略位不计数。**不能机械地用“未 mask 的 labels 数量减 batch_size”**：如果首位本来就是 -100，再减一次会少算。自定义 shift_labels 或模型自己的 loss 实现需要另查契约。

### 3. 长文本为什么需要固定窗口协议？

固定上下文模型无法直接对无限前文条件化。把长文硬切成独立块，会使块开头丢失本来可利用的历史；在无额外 BOS 的普通 causal loss 中，每块首 token 还可能被漏计。

滑动窗口可保留一部分前文，但必须同时处理：

1. **窗口长度和 stride**：记录两者；较小 stride 通常提供更多上下文但更慢，不能保证每个样本 PPL 必然下降。
2. **重叠区只作条件**：已经计过的目标 mask 掉，新目标恰好计一次。mask labels 不等于从输入或 attention 中删除前文。
3. **shift 后再核对目标数**：对每个窗口记录全局目标位置和有效计数，检查既无重复也无漏计；首个文本 token 是否利用 BOS 计分需明确。
4. **文档边界**：拼接文档、插入 EOS、重置上下文会改变条件概率。不能把不同边界策略得到的 PPL 当成同一实验。

引用文档支持滑动窗口原则，但本文不照抄其示例中对每批未 mask 标签统一减 batch_size 的计数方式，而是依据实际 label shift 计算有效位置。

### 4. 可运行的汇总与 label shift 检查

以下概率是人为指定的目标概率，不是 API 或模型输出。示例专门让两批有效 token 数不同，并构造首标签已被忽略的窗口，检查两类常见统计错误。

```python
import math

batches = [[0.5], [0.25, 0.25, 0.25]]
stats = [(-sum(math.log(p) for p in batch), len(batch)) for batch in batches]
total_nll = sum(nll for nll, _ in stats)
total_tokens = sum(n for _, n in stats)
ppl = math.exp(total_nll / total_tokens)
wrong_ppl_mean = sum(math.exp(nll / n) for nll, n in stats) / len(stats)
wrong_loss_mean = math.exp(sum(nll / n for nll, n in stats) / len(stats))
assert math.isclose(ppl, 128 ** 0.25)
assert not math.isclose(ppl, wrong_ppl_mean)
assert not math.isclose(ppl, wrong_loss_mean)
# 相同目标概率重新分批，正确汇总值不变。
flat = [p for batch in batches for p in batch]
assert math.isclose(ppl, math.exp(-sum(map(math.log, flat)) / len(flat)))

IGNORE = -100

def count_targets(rows):
    # 对应标准 causal next-token shift，省略尾部新增的 ignore 位。
    return sum(label != IGNORE for row in rows for label in row[1:])

assert count_targets([[10, 11, 12, 13]]) == 3
window = [[IGNORE, IGNORE, 12, 13]]
assert count_targets(window) == 2
wrong_count = sum(x != IGNORE for row in window for x in row) - len(window)
assert wrong_count == 1  # 首标签早已忽略，不能再按 batch_size 扣一次。
assert count_targets([[10, 11, IGNORE, IGNORE], [IGNORE, 20, 21, IGNORE]]) == 3
assert count_targets([[IGNORE, IGNORE]]) == 0
# 无有效目标时，PPL 应标记为不可计算，而非返回 1 或除零。
assert count_targets([]) == 0
print(f"token-weighted PPL={ppl:.6f}")
print(f"wrong batch-PPL mean={wrong_ppl_mean:.6f}")
print(f"shifted valid targets={count_targets(window)}")
print("PPL aggregation and shift checks passed")
```

实际执行输出：

```text
token-weighted PPL=3.363586
wrong batch-PPL mean=3.000000
shifted valid targets=2
PPL aggregation and shift checks passed
```

这里验证汇总、重分批不变性及有效 label 计数，没有执行模型前向或完整滑窗评测。生产实现还需处理数值精度、零目标批次、非有限 loss、分布式 NLL/计数求和，以及溢出时保留 mean_NLL 等问题。

### 5. 哪些条件一致，比较才有意义？

| 维度 | 应固定或明确报告的内容 |
| --- | --- |
| 文本与单位 | 同一数据版本、清洗与文档边界；tokenizer、词表、特殊 token 与归一化 |
| 上下文 | 窗口、stride、截断、BOS/EOS、上下文重置规则 |
| 计分位置 | 全文还是仅 assistant 回答；padding、prompt、重叠区域的 mask；有效 token 数 |
| 执行 | checkpoint、模型实现、精度、eval 状态、是否关闭 dropout、loss reduction |
| 统计 | 总 NLL、有效目标数、PPL，以及必要的分领域结果；分布式汇总先求和再取 exp |

**不同 tokenizer 的每 token PPL 不宜直接横比。** 同一文本可能被切成不同数量和粒度的 token，分母与预测单元都变了。可在严格一致的原始文本/编码协议下补充按字节归一化的 NLL 或 bits-per-byte，但也必须说明边界、规范化与编码方式；不能仅从两个 PPL 数字换算，亦不能据此证明聊天能力优劣。

聊天模型只在 assistant token 上计 loss，得到的是指定 prompt/对话上下文条件下的回答 NLL/PPL，不等同于无条件语料语言建模 PPL。模板与 prompt 对齐后可作诊断，但上线仍需独立验收指令遵循、事实正确、工具参数、拒答边界、任务成功率与成本。更低 PPL 也可能来自数据泄漏、领域更匹配或模板口径差异，不能直接解释为通用能力提升。

## 延伸 / 追问

**追问 1：模型 A 的 PPL 更低，但回答任务成功率更差，矛盾吗？**

不矛盾。两种指标的测量对象不同；应检查数据与目标分布是否匹配，并用实际任务实验决定，而非要求所有能力服从同一 PPL 排序。

**追问 2：BERT 可以照搬这一套标准自回归 PPL 吗？**

不能直接照搬。masked LM 的条件与自回归分解不同；逐位置遮盖计算的 pseudo-likelihood/pseudo-perplexity 需要明确独立协议，不能把它当同口径的 causal PPL。

**追问 3：API 只提供 top-k logprobs，能精确计算参考答案 PPL 吗？**

只有能获得每个被评估目标的正确条件 logprob 才能计算。目标不在 top-k 时，不能随便用截断概率或给它补零；还要确认 API 支持参考序列打分，而不是仅报告自由生成 token 的概率。

## 常见误区

- **“PPL 是准确率，越低就代表聊天能力越强。”** 它是指定条件下的概率拟合指标，不是产品总分。
- **“把每批 PPL 平均就得到整份数据的 PPL。”** 应汇总 NLL 与有效 token 数后取指数。
- **“有输入 token 就一定有 loss。”** 输入条件、attention mask 与 loss mask 各有作用，计数还受 label shift 影响。
- **“滑窗的重叠 token 都再算一遍没关系。”** 重复计分会改变权重；应记录全局目标覆盖。
- **“不同 tokenizer 的 PPL 直接排大小即可。”** 预测单位和分母可能不同，缺乏统一比较基础。

## 参考

- Hugging Face Transformers **v4.57.1**，[Perplexity of fixed-length models](https://github.com/huggingface/transformers/blob/v4.57.1/docs/source/en/perplexity.md)：选题依据及定义、tokenization、滑动窗口原则；不将文档中的 GPT-2 数字冒充本题实测。
- 同版本 [loss_utils.py，ForCausalLMLoss](https://github.com/huggingface/transformers/blob/v4.57.1/src/transformers/loss/loss_utils.py)：核实右侧补 ignore_index、labels 左移和交叉熵对齐。本文针对默认 shift 路径，不推断所有模型的 loss 都相同。

来源访问与示例核验日期：**2026-10-01**。没有下载模型权重或运行真实语料 PPL benchmark。
