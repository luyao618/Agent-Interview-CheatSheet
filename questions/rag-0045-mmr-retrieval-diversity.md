---
id: rag-0045
title: 检索结果高度重复时，MMR 如何平衡相关性与多样性，与 HNSW 和 Rerank 有何区别？
category: rag
tags: [mmr, retrieval-diversity, candidate-selection, reranking]
difficulty: medium
role: engineer
contributor: 佚名
source: 公开 RAG 面试整理中的 HNSW vs MMR 话题扩展改编；原论文与 LangChain 源码核实（见参考）
status: published
updated: 2026-09-29
answers:
  - author: GPT-6-Astra
    type: ai
    model: GPT-6-Astra
    answered: 2026-09-29
    updated: 2026-09-29
---

## 问题

RAG 的前五个检索片段都很相关，却几乎重复同一段内容，导致回答漏掉用户要求的其他方面。有人建议换 HNSW 参数，有人建议加 cross-encoder，还有人建议使用 MMR。

MMR 解决的是什么问题？请解释其贪心选择公式、lambda 与候选池大小的影响，用可运行示例说明为什么不能把“多样性”当成质量保证，并设计验收方法。

本题由公开面试整理中的 **HNSW vs MMR** 话题扩展改编，独立撰写答案；不将文件名中的公司标签视为已核实的公司面试出处。

## 答案 · GPT-6-Astra

> 🤖 AI 答案 · 模型：GPT-6-Astra · 回答 2026-09-29

**MMR（Maximal Marginal Relevance）从已经召回的候选中逐个选择：既考虑候选与问题的相关性，也惩罚它与已选内容的相似性。** 它优化的是有限上下文里的相关且不冗余的内容组合，不是新的向量索引，也不会凭空补出候选池里缺失的证据。

现有 [rag-0043](rag-0043-ann-index-metric-selection.md) 讨论索引与近邻召回，[rag-0019](rag-0019-multi-route-recall.md) 讨论多路召回与融合；本题聚焦**候选集合内部的相关性—冗余权衡**。ANN 搜索、融合和多样化可以组合，但不能混为一个步骤。

### 1. 先区分四件事

| 方法 | 主要解决的问题 | 不应承诺的能力 |
| --- | --- | --- |
| HNSW 等 ANN 索引 | 高效找到接近 query 的候选向量 | 不保证前几个候选覆盖不同事实或方面 |
| ID / 内容 hash 去重 | 移除同一对象或完全重复文本 | 不识别所有语义重复；不同版本也不能随意合并 |
| 逐对 cross-encoder rerank | 联合读取 query 与候选，重估相关性 | 普通独立打分没有显式的已选集合冗余惩罚 |
| MMR | 依据相关性及与已选集合的相似性贪心挑选 | 不保证事实正确、全局最优或覆盖全部必需证据 |

“Rerank”是广义术语，MMR 本身也是一种重排序/选择策略；不能说 MMR 与所有 reranker 都互斥。候选融合、相关性重排、MMR 的先后顺序应明确并实测：MMR 选完后再只按相关性截断，可能又把多样性收益丢掉。

### 2. 公式、空集合与 lambda

设候选池为 R、已选集合为 S。对尚未选中的候选 d：

```text
MMR(d | S) = lambda * Rel(query, d)
             - (1 - lambda) * max(Sim(d, s) for s in S)

每轮选取 R \ S 中 MMR 分数最大的候选，加入 S。
```

- `Rel` 衡量问题相关性，`Sim` 衡量与已选内容的冗余。原论文允许两者采用不同度量；常见 embedding 实现二者均采用 cosine similarity。
- 空集合的最大值没有自然定义。**必须明确首项规则**：本文沿用所引 LangChain 实现，先选 query 相似度最高的候选，再计算后续 MMR 分数，包括 lambda 为 0 时。
- `lambda=1`：后续只看相关性，按相同 tie-break 得到纯相关性排序。
- `lambda=0`：首项之后只惩罚与已选集合的相似性；可能选择很不相关但“不像已有内容”的候选。
- 中间值是权衡，不是通用质量保证。lambda 变大提高公式中相关性的权重，但不代表实际回答质量随之单调提高。

惩罚使用的是**与已选集合的最大相似度**，而不是对整个候选池求相似度，也不是对每一对候选先算一个固定分数再排一次。S 每轮变化，后续候选的分数也必须更新。

`Rel` 与 `Sim` 的尺度会影响有效权衡。直接把未校准的 cross-encoder logit 与 cosine 相减，同一个 lambda 不一定还有原来的含义；应校准或明确统一约定，并在验证集调参。cosine 也可能为负，不能默认它永远是 0–1 或概率。

### 3. 候选数、输出数和预算是不同参数

先召回 F 条候选，再选 k 条给后续上下文。某些 vector store 接口把 F 称为 `fetch_k`，但名称、默认值与支持情况要以实际接口为准，底层 MMR 函数本身不负责检索。

- **F 太小**：其他方面根本没被召回，MMR 无从选择。把 k 调大也不能弥补候选缺失。
- **F 变大**：可能增加有效证据，也会增加噪声、检索成本和 MMR 计算量；不保证回答变好。
- **k 不是 token 预算**：不同 chunk 长度不同。最终仍需检查预算、完整证据及引用位置，不能选完再随意截断到半条证据。
- **过滤与版本边界优先**：先确定可访问且符合业务范围的候选；MMR 不能替代 ACL、租户隔离、版本规则或硬性相关性门槛。

若预先获得 query 相关性，且两两相似度计算成本为 O(d)，维护每个候选当前最大冗余并增量更新，可以把选择阶段做到 O(Fkd) 量级。简单实现每轮重新比较候选与所有已选项，可能累积到 O(Fk²d)；预计算完整相似度矩阵则有 O(F²) 存储代价。不能不定义 F、k、d 就笼统宣称“MMR 一定 O(k²)”。

### 4. 可运行例子：避免重复，也要防止跑题

下面是人为设定的相关性与对称冗余分数，不声称来自真实 embedding。A/B 表示高度重复证据，C 表示相关的另一角度，D 表示低相关、低冗余的跑题内容；ID 顺序用于确定性平局处理。

```python
from math import isfinite

relevance = {"A": 0.95, "B": 0.94, "C": 0.80, "D": 0.10}
pair = {
    ("A", "B"): 0.99, ("A", "C"): 0.20, ("A", "D"): 0.00,
    ("B", "C"): 0.25, ("B", "D"): 0.05, ("C", "D"): 0.10,
}


def similarity(a, b):
    return 1.0 if a == b else pair[tuple(sorted((a, b)))]


def select_mmr(candidates, k, weight):
    if not isfinite(weight) or not 0 <= weight <= 1:
        raise ValueError("weight must be finite and in [0, 1]")
    # 本例用稳定 ID 去重；真实 chunk 的身份与版本规则需另行定义。
    remaining = sorted(set(candidates))
    if k <= 0 or not remaining:
        return []
    first = min(remaining, key=lambda x: (-relevance[x], x))
    chosen = [first]
    remaining.remove(first)
    while remaining and len(chosen) < k:
        def score(x):
            redundancy = max(similarity(x, s) for s in chosen)
            return weight * relevance[x] - (1 - weight) * redundancy
        best = min(remaining, key=lambda x: (-score(x), x))
        chosen.append(best)
        remaining.remove(best)
    return chosen


pool = list(relevance)
assert select_mmr(pool, 2, 1.0) == ["A", "B"]
assert select_mmr(pool, 2, 0.5) == ["A", "C"]
assert select_mmr(pool, 2, 0.0) == ["A", "D"]  # 极端多样性会跑题
assert select_mmr(["A", "B"], 2, 0.5) == ["A", "B"]  # 召不回 C 就选不到
assert select_mmr([], 2, 0.5) == []
assert select_mmr(pool, 0, 0.5) == []
assert select_mmr(["A", "A", "B"], 9, 0.5) == ["A", "B"]
# 构造状态更新检查：选入 E 后，C 与 E 高度重复，应改选 F。
relevance.update({"E": 0.79, "F": 0.70})
pair.update({("A", "E"): 0.10, ("A", "F"): 0.10,
             ("C", "E"): 0.95, ("C", "F"): 0.10,
             ("E", "F"): 0.10})
# 此池的第二项是 E；选入 E 后，C 受惩罚，第三项应为 F。
assert select_mmr(["A", "C", "E", "F"], 3, 0.5) == ["A", "E", "F"]
try:
    select_mmr(pool, 2, 1.1)
except ValueError:
    pass
else:
    raise AssertionError("invalid weight accepted")
print("relevance-only:", select_mmr(pool, 2, 1.0))
print("balanced:", select_mmr(pool, 2, 0.5))
print("diversity-only after seed:", select_mmr(pool, 2, 0.0))
print("MMR checks passed")
```

实际执行输出：

```text
relevance-only: ['A', 'B']
balanced: ['A', 'C']
diversity-only after seed: ['A', 'D']
MMR checks passed
```

这验证的是有限候选上的选择逻辑，没有运行向量库、embedding 模型或回答生成，也没有宣称改进真实业务指标。生产实现还需要处理缺失分数、非有限相似度、向量合法性及 token 预算等边界。

### 5. 怎样验收不是“为了多样而多样”？

1. **固定候选池做消融**：比较 relevance top-k、ID 去重、cross-encoder top-k 与 MMR，尽量保持上下文 token 预算一致；否则无法判断收益来自选集方式还是更多输入。
2. **再检查召回阶段**：单独改变 F 与检索配置，测候选 evidence recall，避免把缺失证据错归因给 MMR。
3. **联合看相关性、冗余和证据覆盖**：记录必需事实是否保留、问题各方面覆盖率、重复比例；仅仅平均相似度变低可能意味着加入了噪声。覆盖应基于标注事实或独立核验，不仅靠 embedding 距离自证。
4. **分场景评估**：综合比较/多角度问题可能受益；精确型号查找、同一法规的完整条文、需要多来源相互印证的任务，过度惩罚相似内容可能有害。相似不等于无价值。
5. **端到端验证**：盲评回答正确性、完整性、引用支持率，以及额外延迟和成本。lambda、F、k 在验证集选择后锁定，再看独立测试集；不把示例的 0.5 当通用最优值。

## 延伸 / 追问

**追问 1：MMR 能保证拿到互不重复且覆盖全部方面的 k 条证据吗？**

不能。它是受相似度定义和候选池限制的贪心启发式；相似度不等于真实事实重合，候选池也可能缺项。必须有证据覆盖验收，硬性必需事实可另设保留约束。

**追问 2：RRF 与 MMR 能不能互相替代？**

RRF 合并多个排序列表的名次信号；MMR 在候选集合里权衡相关性与已选冗余。RRF 可以作为候选融合阶段，但若把 RRF 分数作为 Rel，需重新核对与 Sim 的尺度，不能原样套用 embedding 的 lambda。

**追问 3：为什么重复证据有时应该保留？**

相似文字可能来自独立权威来源、不同版本或互相印证的观测。去重和多样化必须遵循来源、时间与任务语义，不能只因 embedding 接近就删掉关键佐证。

## 常见误区

- **“MMR 是 HNSW 的替代索引。”** 一个主要做候选搜索，一个在候选内选择，层次不同。
- **“lambda 越小越好。”** 更强调低冗余也可能引入跑题内容。
- **“对每个候选算一次分数即可。”** 冗余项依赖变化中的已选集合，必须更新。
- **“MMR 会自动删除所有重复文本。”** 它施加软惩罚，不等于硬去重；候选不足时仍可能选入相似项。
- **“多样化必定减少幻觉。”** 它只改变输入证据组合，需要真实回答与引用验收。

## 参考

- 选题线索：[公开 RAG 面试整理，HNSW vs MMR 小节](https://github.com/PawanKrGunjan/GenerativeAI/blob/8b96818f65a76c2924e71aceb8f0adf371eca633/INTERVIEW/EY.Md#hnsw-vs-mmr-in-the-context-of-rag-retrieval-augmented-generation)。固定 commit；只作为选题线索，不采信其公司归属、泛化性能数字或未经验证的 API 示例。
- Carbonell & Goldstein, *The Use of MMR, Diversity-Based Reranking for Reordering Documents and Producing Summaries*, SIGIR 1998，[原论文](https://www.cs.cmu.edu/~jgc/publication/The_Use_MMR_Diversity_Based_LTMIR_1998.pdf)，第 2 节：相关性与新颖性组合、不同相似度函数、lambda 的边界。
- LangChain，[maximal_marginal_relevance 源码 L112–163](https://github.com/langchain-ai/langchain/blob/d6167c0b0dafb5f3898faa28e01df0b8db5ef76a/libs/core/langchain_core/vectorstores/utils.py#L112-L163)。固定 commit，用于核实先选最高 query 相似度、后续最大冗余惩罚的实现；不等于所有 vector store 的默认配置。

来源访问与示例核验日期：**2026-09-29**。本文不声称执行了真实 RAG 质量或性能实验。
