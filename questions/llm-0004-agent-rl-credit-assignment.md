---
id: llm-0004
title: 多轮 Agent 后训练中，最终成败如何归因到中间工具调用决策？
category: llm
tags: [reinforcement-learning, agent-training, credit-assignment, tool-use, rewards]
difficulty: hard
role: engineer
contributor: 佚名
source: 《深入理解 AI Agent：设计原理与工程实践》第 7 章
status: published
updated: 2026-08-12
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-08-12
    updated: 2026-08-12
---

## 问题

Agent 一条轨迹可能有几十步工具调用，最后只拿到一个「成功 / 失败」信号。这个稀疏的结果奖励如何归因到中间某一步决策？哪一步该被强化、哪一步该被惩罚？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 回答 2026-08-12

这就是 **credit assignment（信用分配）** 问题：轨迹长、奖励稀疏、且**成败常由少数关键步决定**，其余步骤只是陪跑。朴素做法是把最终 reward 均摊给所有步——但这会把**失败轨迹里那些正确的步骤一起惩罚**，也会奖励成功轨迹里的无效绕路，噪声极大、样本效率极低。

```
轨迹: s1 →[搜索]→ s2 →[点错链接]→ s3 →[补救]→ s4 →[提交]→ 失败
                        ↑真正的错因            ↑这步其实是对的
均摊结果奖励：全部 -1  ← 错杀补救步，强化不了正确行为
```

**主流手段（由粗到细）：**

1. **结果奖励 + 优势估计（ORM，最常用基线）。** 只判最终成败，靠 GAE / 值函数把优势分摊到各步；GRPO 这类做法更直接——**同一初始状态采样多条轨迹，用组内平均分做基线**，高于均值的轨迹整体被强化。省去训 critic，但仍是轨迹级粒度。

2. **过程奖励（PRM，步级监督）。** 训一个模型给每步打分（这步是否朝目标前进、工具选得对不对、参数合不合法）。信号密集、收敛快，代价是要步级标注，且 PRM 本身会被 **reward hacking**——模型学会讨好打分器而非把事做成。

3. **反事实 / 消融归因。** 从某步**回放并改写**（换个工具、跳过该步）重跑后续，看成功率变化 = 该步的边际贡献，思路同 Shapley value。归因最准，但重跑成本高，且要求环境**可重置、可复现**。

4. **轨迹回放与对比。** 同一任务成功与失败轨迹对齐比较，定位**首个分叉点**——常常那一步就是错因；据此构造偏好对做 DPO 式训练，比全轨迹打标便宜。

5. **奖励塑形（reward shaping）。** 补中间信号：子目标达成、工具调用格式合法、检索到关键证据、状态距离目标更近。务必用 **potential-based shaping**（保证最优策略不变），否则容易训出「刷中间分但不完成任务」的策略。

**工程上的组合拳：** 以**结果奖励为主**（它才对齐真实目标，不易被 hack），用 shaping / PRM 提供辅助密集信号加速早期收敛，关键步用反事实抽样校验归因是否可信；同时对**格式错误、无效调用、死循环**给即时惩罚——这类局部错误无需长程归因。此外要**区分 Agent 决策失误与环境失败**（API 超时、工具本身报错），否则会把不可控的外部噪声当成策略错误来惩罚。

**一句话：** 结果奖励保证「对齐要做成的事」，过程信号保证「学得动」——**用组内基线降方差、用反事实定位关键步、用 potential-based shaping 补密度，并把环境噪声从策略责任里摘出去**。

## 延伸 / 追问

**追问：过程奖励模型（PRM）容易被 reward hacking，实践中怎么防？**

核心是**别让 PRM 成为唯一目标**。① **主从结构**：最终判据始终是结果奖励 / 可验证的环境状态，PRM 只做辅助项并给较小权重，随训练推进逐步退火到 0。② **可验证优先**：能用规则判的（代码能否跑通、单测是否通过、JSON 是否合法、检索到的事实能否被核对）就用**确定性验证器**，它没法被话术糊弄，比学出来的 PRM 稳得多。③ **KL 约束**：限制策略相对参考模型的偏移，防止钻进 PRM 的分布外盲区。④ **对抗刷新**：定期把当前策略刷出的高分但失败的样本回灌重训 PRM，堵住已被发现的漏洞。⑤ **持续监控背离**：盯 PRM 均分与真实成功率的相关性，**PRM 分涨而成功率不涨就是 hacking 的明确信号**，此时应停训或重标。核心原则：**可验证信号 > 学习出的奖励模型**。

## 参考

- Lightman et al., *Let's Verify Step by Step*, 2023（过程监督 vs 结果监督）：https://arxiv.org/abs/2305.20050
- Shao et al., *DeepSeekMath: GRPO*, 2024（组内基线优势估计）：https://arxiv.org/abs/2402.03300
- Ng et al., *Policy Invariance Under Reward Transformations*, 1999（potential-based shaping）：https://people.eecs.berkeley.edu/~pabbeel/cs287-fa09/readings/NgHaradaRussell-shaping-ICML1999.pdf
- Amodei et al., *Concrete Problems in AI Safety*, 2016（reward hacking）：https://arxiv.org/abs/1606.06565
