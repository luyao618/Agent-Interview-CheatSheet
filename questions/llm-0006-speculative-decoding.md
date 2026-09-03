---
id: llm-0006
title: 什么是 Speculative Decoding？它如何在不改变输出分布的前提下加速 LLM 推理？
category: llm
tags: [speculative-decoding, inference, latency, serving]
difficulty: hard
role: engineer
contributor: 佚名
source: Leviathan et al., ICML 2023
status: published
updated: 2026-09-03
answers:
  - author: GPT-5
    type: ai
    model: GPT-5
    answered: 2026-09-03
    updated: 2026-09-03
---

## 问题

什么是 Speculative Decoding？它如何加速 LLM 自回归生成，同时保持与目标模型单独解码相同的输出分布？在什么场景下收益有限？

## 答案 · GPT-5

> 🤖 AI 答案 · 模型：GPT-5 · 日期 2026-09-03

自回归解码的瓶颈是：目标模型（target model）通常每次 forward 只生成一个 token，后一个 token 又依赖前一个，无法跨时间步直接并行。**Speculative Decoding（投机解码）**增加一个更小、更快的 draft model，让它先连续提出一段候选 token，再让 target model 用一次 forward **并行计算这段候选各位置的概率分布**。只要一轮能接受多个候选，就减少了昂贵的 target model 串行调用次数。

关键不是简单地「小模型生成、大模型打分」；直接接受高分候选会改变 target model 的输出分布。论文把保证 exact decoding 的校正过程称为 **speculative sampling**。设某个位置上 draft 的实际采样分布为 `q`，target 的目标分布为 `p`：

1. draft 从 `q` 依次采样 `γ` 个候选；target 对整段候选并行计算每个位置的 `p`。
2. 按顺序检查候选 `x`，以 `min(1, p(x) / q(x))` 的概率接受。这里 `q(x) > 0`，因为 `x` 是从 `q` 采出的。
3. 第一次拒绝时，丢弃它后面的 draft 候选，并从修正分布 `norm(max(0, p - q))` 采样当前 token。
4. 如果 `γ` 个候选全部接受，再额外从 target 的下一位置分布采样一个 token。

单个位置上，候选被接受所贡献的概率质量是
`q(x) * min(1, p(x) / q(x)) = min(q(x), p(x))`；拒绝分支再补上 `(p(x) - q(x))` 的正部。两部分相加恰好是 `p(x)`，所以逐位置执行后，最终序列分布与 target-only sampling 一致。这不是把普通的 rejection sampling 换个名字：该校正规则和「全部接受后多采一个 target token」共同构成论文所说的 speculative sampling。

**为什么会更快：**大模型推理常受 memory bandwidth 限制，每次 forward 都要读取大量权重。验证一段 token 虽增加计算量，却能在一次 target 调用中摊薄权重读取和调度成本；draft 又比 target 便宜。收益取决于每轮平均接受的 token 数能否覆盖 draft 生成、target 验证和通信开销，而不是固定倍数。Leviathan 等人在 T5-XXL 相对标准 T5X 的特定实验中报告约 **2×–3×** 加速，这只是论文实验结果，不是通用 SLA。

**exact 的前提：**`p` 和 `q` 必须定义在同一 token 空间，并且分别是目标采样策略和 draft proposal 本轮真正使用的归一化分布。`q` 可以与 `p` 不同；但使用 temperature、top-k 或 top-p 后，接受率和残差必须基于变换后的实际 `p`、`q` 计算。若实现拿未变换的 logits 计算比值、误认 draft 使用了不同于实际情况的 `q`，或为了性能跳过校正，就不再能声称输出分布严格不变。Greedy verification 可以保持 greedy target 的确定性结果，但不能代替随机采样场景中的上述校正。

**收益有限或可能变慢的场景：**

- draft 与 target 分布差异大，acceptance rate 低，大部分候选被拒绝；
- draft 本身过大、跨设备通信昂贵，或 `γ` 过长导致无效验证计算过多；
- 输出很短，初始化和额外调度成本来不及摊薄，TTFT 通常也不会因投机阶段明显改善；
- 超大 batch 已把硬件算力吃满，系统从 memory-bound 变为 compute-bound，额外 draft/verification FLOPs 会侵蚀吞吐；
- 业务更关心总吞吐而非单请求 TPOT，投机解码降低延迟却未必提高每美元 tokens/s。

工程评估时至少同时看 acceptance rate、每次 target 调用产出的 token 数、TTFT、TPOT、端到端吞吐和单位 token 成本，不能只看某个离线接受率。

## 延伸 / 追问

**追问：draft model 越大、一次 draft 的 token 越多，是否一定越快？**

不一定。更大的 draft 往往更接近 target、接受率更高，但它自己的串行生成成本也更高；更长的 `γ` 能提高单轮最多产出的 token 数，却会放大首次拒绝后被丢弃的验证计算。实际应在目标 batch、硬件和 sampling 配置上联合搜索 draft 大小与 `γ`，以端到端 TPOT / 吞吐为目标，并持续监控接受长度分布，而不是单独最大化 acceptance rate。

## 参考

- Leviathan, Kalman, Matias, *Fast Inference from Transformers via Speculative Decoding*, ICML 2023（PMLR）：https://proceedings.mlr.press/v202/leviathan23a.html
- Leviathan, Kalman, Matias, *Fast Inference from Transformers via Speculative Decoding*, arXiv：https://arxiv.org/abs/2211.17192
