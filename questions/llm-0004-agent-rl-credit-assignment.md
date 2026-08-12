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

用 RL 对多轮 Agent 做后训练时，奖励通常只在轨迹末尾给一个「任务成功 / 失败」的稀疏信号，中间可能有十几次工具调用。如何把最终成败归因到具体某一次工具调用决策上？过程奖励、结果奖励、轨迹回放、反事实评估各自适用在什么场景？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-08-12

先把问题说准：这是 RL 的 **temporal credit assignment**——一条长度 N 的轨迹只在末尾拿到一个结果奖励，要摊回每一次 tool call 决策。真正的难点是**成功轨迹里混着废动作，失败轨迹里混着好动作**；均摊会同时强化噪声、惩罚正确。

```
s0 ─a1→ s1 ─a2→ s2 ─ … ─aN→ sN    R ∈ {0,1}
              ↑ 哪一步该背锅 / 该记功？
 ├ 均摊  A_t = R − b(组内均值)          便宜、低偏、方差大
 ├ critic A_t = r + γV(s_{t+1}) − V(s_t)  稠密、V 难拟合
 └ 反事实 A_t = V̂(s_{t+1}) − V̂(s_t)，V̂ 由 s 处 K 次重 rollout 的成功率估
```

**一、先做对工程前提，否则任何归因都是噪声**

- **loss mask**：tool 返回的 token 是环境产物、不是模型动作，必须从 loss 里屏蔽，只对模型自己生成的 thought / tool_call / final answer 计梯度。漏掉这条，等于逼模型去「预测」检索结果。
- **确定性回放**：每次调用的入参与返回落盘，重放时命中缓存。环境带随机性或副作用时，同一步两次 rollout 结果不同，反事实差值里全是环境方差。
- **归因粒度**：以「一次 tool call = 一个 decision step」为单位，而非 token；token 级在长轨迹上信噪比太低。

**二、三档方案，按环境能否重置来选**

1. **轨迹级均摊 + 组基线（GRPO / RLOO 类）**：同一 prompt 采 G 条轨迹，用组内均值当 baseline，整条轨迹共享一个 advantage。不需要 PRM，不引入可被 hack 的中间信号，靠采样量把噪声洗掉；代价是样本效率低，长轨迹尤甚。**默认起点。**
2. **rollout 估计的反事实 credit（Math-Shepherd / VinePPO 思路）**：从 s_t 重采 K 条后续，用成功率估 V̂(s_t)，取相邻差值作步级 advantage——哪一步把成功率打下去，锅就在哪一步。这是**过程监督的自动标注**，不用人标；前提是环境能从任意中间状态重启（snapshot / 只读沙箱 / 缓存重放），成本 N×K 倍推理。适合可回放的工具链。
3. **PRM / LLM-as-critic**：训过程奖励模型，或让强模型读失败轨迹标「第一处决定性错误」。便宜、可扩，但**是启发式而非测量**：critic 有位置偏置（爱怪最后一步）、随策略漂移而 OOD、且会被优化过程 hack。只当**候选定位器**，抽样交给反事实重跑或人工核验后再进训练集。

**三、reward shaping 要克制**

只加**可验证**的过程信号：JSON schema 合法、代码编译通过、检索命中标注证据、步数超限惩罚。加「看起来合理」这类主观分，模型会学出刷分动作（无意义调用、凑格式）。shaping 权重要小，结果奖励必须始终占主导。

**落地顺序：先把 tool 返回 mask 掉、把回放做确定，默认用组基线的轨迹级 advantage；环境可 snapshot 再上 rollout 反事实做步级 credit；LLM critic 只做定位，不直接当奖励。**

## 延伸 / 追问

**追问：如果工具有副作用（下单、写库），环境没法回滚做反事实 rollout，怎么办？**

四条路，按代价排：① **影子环境**——训练期把写操作换成 mock / 状态机模拟，读操作走录制的真实响应，用真实日志校准保真度；这是唯一能保住步级归因的做法。② **混合 advantage**——只对可回放的读操作做反事实，写操作退回轨迹级均摊，两者拼在一起。③ **离线反事实**——从历史日志里捞共享前缀 s_t 的不同分支当自然实验，比较分支成功率，省掉重跑；但分支不是随机分配的，存在 confounding，只能当弱证据。④ **缩短 horizon**——按 sub-goal 切段，只在段边界评判（层次化 RL），把十几步的归因压成几段；再不行就用学出来的 critic 拿稠密但有偏的估计顶上。

## 参考

- Shao et al., *DeepSeekMath: Pushing the Limits of Mathematical Reasoning (GRPO)*, 2024：https://arxiv.org/abs/2402.03300
- Wang et al., *Math-Shepherd: Verify and Reinforce LLMs Step-by-step without Human Annotations*, 2024：https://arxiv.org/abs/2312.08935
- Kazemnejad et al., *VinePPO: Refining Credit Assignment in RL Training of LLMs*, 2024：https://arxiv.org/abs/2410.01679
- Lightman et al., *Let's Verify Step by Step*, 2023：https://arxiv.org/abs/2305.20050
- Zhou et al., *ArCHer: Training Language Model Agents via Hierarchical Multi-Turn RL*, 2024：https://arxiv.org/abs/2402.19446
- Foerster et al., *Counterfactual Multi-Agent Policy Gradients (COMA)*, 2017：https://arxiv.org/abs/1705.08926
