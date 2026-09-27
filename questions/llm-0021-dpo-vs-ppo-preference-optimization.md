---
id: llm-0021
title: DPO 如何直接学习回答偏好，与 PPO 式 RLHF 的训练流程和适用边界有何不同？
category: llm
tags: [dpo, rlhf, preference-optimization, reference-policy, alignment]
difficulty: medium
role: engineer
contributor: 佚名
source: Devinterview LLM 面试资料第 6 题扩展改编；DPO 原论文核实（见参考）
status: published
updated: 2026-09-26
answers:
  - author: GPT-6-Astra
    type: ai
    model: GPT-6-Astra
    answered: 2026-09-26
    updated: 2026-09-26
---

## 问题

你已有一个 SFT 模型，以及同一 prompt 下的 chosen / rejected 回答对。团队希望让模型更符合用户偏好，但不想先训练独立奖励模型，再搭建 PPO 的在线采样流程。

DPO（Direct Preference Optimization）如何利用这些回答对训练模型？请解释参考策略、序列 log-probability 和 beta 的作用，比较它与 PPO 式 RLHF 的流程，并说明为什么偏好准确率提高不等于事实正确率提高。

本题依据公开面试资料中的预训练与微调问题扩展改编，不是某家公司面试原题。

## 答案 · GPT-6-Astra

> 🤖 AI 答案 · 模型：GPT-6-Astra · 回答 2026-09-26

**DPO 把带 KL 正则的偏好优化问题，改写成回答对上的分类损失，直接更新语言模型；它省掉的是独立奖励模型与训练循环中的在线 rollout，不是偏好数据、参考策略或效果验证。** 以下讨论原论文的标准离线、sigmoid DPO，不把所有后续变体混为一谈。

与 [llm-0005](llm-0005-agent-training-sft-to-rl-switch.md) 的“SFT 何时转 RL”、[llm-0004](llm-0004-agent-rl-credit-assignment.md) 的“多轮轨迹如何分配信用”不同，本题聚焦固定回答对上的偏好目标与 PPO 训练流程差异；SFT 和模板基础见 [llm-0009](llm-0009-base-chat-template-sft.md)。

### 1. 三种训练信号不要混淆

| 方法 | 数据 / 信号 | 主要训练步骤 | 主要边界 |
| --- | --- | --- | --- |
| SFT | prompt 与示范回答 | 最大化示范回答的条件似然 | 不显式利用同一 prompt 下哪条回答更差的比较标签 |
| PPO 式 RLHF | 偏好对训练奖励模型；当前策略生成的回答用于 RL | 训练奖励模型，再采样、计算奖励与 KL 约束、更新策略；常见实现另训练价值模型 | 有在线生成和多模型协作成本，需防奖励投机与训练不稳定 |
| 标准离线 DPO | 固定的 prompt、chosen、rejected 三元组 | 对两条回答计算当前策略与冻结参考策略的 log-probability，反向传播偏好分类损失 | 不在每次训练更新中探索新回答，覆盖受已有数据限制 |

这里的“在线采样”是当前策略在训练期间生成 rollout，不代表必须边服务真实用户边训练。DPO 的偏好标签可来自人或其他评判方式；讨论时应明确反馈来源。它属于偏好对齐方法，不能简单宣称“DPO 已全面取代 RLHF”。

### 2. 优化的是相对参考策略的偏好间隔

设 x 为 prompt，y+ 为 chosen，y- 为 rejected；pi_theta 是待训练策略，pi_ref 是冻结参考策略，通常取训练开始前的 SFT 模型。定义：

```text
s+ = log pi_theta(y+ | x) - log pi_ref(y+ | x)
s- = log pi_theta(y- | x) - log pi_ref(y- | x)
z  = beta * (s+ - s-)
L  = -log sigmoid(z)
```

对训练回答对取平均即得到标准 DPO 损失。它推动 chosen 相对 rejected 的**参考归一化 log-odds 间隔**增大，而不是单独对 chosen 做一次 SFT，也不是要求训练后 chosen 的原始概率必然超过 rejected。

原论文从“最大化预期奖励，同时用 beta 乘 KL 惩罚偏离参考策略”的目标出发。在其假设下，最优策略对应的奖励可写为 `beta * log(pi / pi_ref) + C(x)`。将这个重参数化代入 Bradley–Terry 成对偏好模型，C(x) 在同一 prompt 的比较中抵消，得到上述损失。**策略隐含表达了奖励，不等于训练过一个独立的奖励模型。** 推导中的最优关系也不保证有限数据与有限训练后的模型就是全局最优。

参考策略为“偏好变化”提供锚点。标准配置中它不更新；可用冻结副本计算，或在参考模型、模板和 tokenization 固定后预计算 log-probability。它不是推理时必须额外调用的第二个模型。

beta 在原始目标中控制 KL 正则强度，也在 DPO 的偏好 logit 中作为比例系数。但固定数据训练时，梯度、饱和程度和实际策略漂移共同作用，**不能仅凭 beta 大小断言最终 KL 或质量一定单调变化**。应联合学习率、训练步数及留出集测量调参。

### 3. 一个能检查符号的手算例子

以下是人为指定的序列 log-probability，不是模型实验结果：

| 回答 | 参考策略 log-probability | 当前策略 log-probability | 差值 |
| --- | ---: | ---: | ---: |
| chosen | -12 | -10 | 2 |
| rejected | -11 | -12 | -1 |

取 beta=0.1，则 z=0.3，损失约 0.5544；模型刚初始化为参考策略时，两个差值均为零，损失约 0.6931。这个回答对上的损失下降，只说明其偏好间隔改善，不说明回答事实正确，也不说明在新 prompt 上效果提高。

另外，间隔变大并不保证 chosen 的绝对概率增加。例如 chosen 的 log-probability 从 -12 降至 -13，rejected 从 -11 降至 -14，二者都降低，但相对参考策略的间隔仍从 0 增至 2。因此验收时不能只看 DPO loss，应同时观察 chosen / rejected 的概率变化与实际生成行为。

### 4. 数据与实现细节决定是否学到了真正的偏好

- **成对可比**：两条回答必须对应相同 prompt、约束和可见信息。不能把不同用户问题的回答随意配成优劣对；平局、标注冲突与缺乏判断依据的样本要有处理策略。
- **标签不等于真理**：标注者或 AI judge 可能偏爱篇幅、措辞、自信语气或迎合。正确但简短的回答可能被标成 rejected，错误但流畅的回答可能被选中；需核验事实、代码测试及标注一致性。
- **序列分数口径一致**：标准 DPO 使用回答 token 的条件 log-probability 之和；prompt 用于条件输入，不作为回答损失，padding 也需 mask。当前与参考策略必须使用一致的模板、分词和回答边界。改成长度均值属于改变目标，不能当无关紧要的实现细节。
- **截断保持标签成立**：截断前的 chosen / rejected 标签，在关键结论被截掉后可能不再有效。先检查长样本和 EOS/结束标记约定，而不是只设 max_length 后直接训练。
- **隔离数据与测试**：按用户、任务来源或模板族分组切分，避免同一问题的近重复落入训练与测试两边。保留独立事实正确性、安全性、拒答合理性及长尾任务评测。

这些是实施检查项，不是声称原论文已经解决所有数据治理问题。

### 5. 什么时候选 DPO，什么时候还需要在线方法？

已有较可靠的 SFT 起点、足够且相关的偏好对，希望先改善回答风格或任务偏好，同时控制训练复杂度时，DPO 是值得建立的基线。相比只训 chosen 的 SFT，应在相同数据划分与资源口径下比较，而不是仅比较训练 loss。

当当前策略经常产生离线数据没有覆盖的新型错误，或任务有可执行环境、验证器及需要探索的多步决策时，固定回答对可能不足。可以重新采样并标注、迭代 DPO，也可以评估在线 RL 等方案；**DPO 并非只能用于风格，在线 RL 也不是必然更好**，选择取决于反馈可靠性、探索需求、环境成本和可验证收益。

上线前至少对照 SFT 基线检查：留出任务成功率、偏好胜率（含平局规则）、事实错误与安全违规、回答长度及拒答率、训练资源成本和推理成本。偏好判定要控制答案顺序与长度偏置。回答变长会增加推理成本，即使 DPO 没有增加推理模型数量。训练更简单不意味着部署结果更可靠。

## 延伸 / 追问

**追问 1：DPO 不训练奖励模型，是否就不存在 reward hacking？**

不是。它仍可能放大有偏偏好标签，学到长度、自信口吻等捷径。没有独立奖励网络不等于优化目标与真实用户价值完全一致，仍需独立评测。

**追问 2：把 rejected 回答删掉，只用 chosen 做 SFT，和 DPO 等价吗？**

不等价。SFT 最大化 chosen 的似然；DPO 利用两条回答的相对差异及参考策略，对当前还分不清优劣的回答对施加相应训练信号。

**追问 3：离线 DPO 是否意味着无需任何模型生成成本？**

不是。构建候选回答对、刷新数据以及生成评测都可能需要采样；省掉的是标准 DPO 参数更新循环里的在线 rollout。训练仍需当前策略的前向/反向计算与参考分数。

## 常见误区

- **“DPO 的 chosen 胜率高，所以幻觉消失了。”** 偏好与事实正确性不是同一个指标。
- **“没有奖励模型，所以没有奖励或偏好假设。”** 重参数化中仍存在隐含奖励与偏好模型假设。
- **“beta 就是 temperature。”** beta 控制训练目标中的正则/比例；生成时的 temperature 控制采样，二者不同。
- **“两条回答长度不同，所以应该直接平均 token 分数。”** 需要明确目标与长度偏置处理，不能静默把标准序列和改成均值。
- **“参考策略每步跟随训练模型更新。”** 这不是本文讨论的冻结参考标准 DPO；变体须单独说明。

## 参考

- 选题线索：Devinterview 的 [LLMs Interview Questions，第 6 题：预训练与微调](https://github.com/Devinterview-io/llms-interview-questions/blob/88a155109e0d8718f2688c331671330b47ed08cd/README.md#6-discuss-the-significance-of-pre-training-and-fine-tuning-in-the-context-of-llms)。本文只据其对偏好对齐的提及扩展题目，独立编写中文问答；不沿用材料中“DPO 已普遍取代 RLHF”等未经限定的判断。
- Rafailov et al., [Direct Preference Optimization: Your Language Model is Secretly a Reward Model](https://arxiv.org/html/2305.18290v3)，2024 修订版，重点为第 3–5 节及附录 A/B：KL 正则目标、偏好模型、目标推导与实现。
- Ouyang et al., [Training language models to follow instructions with human feedback](https://arxiv.org/abs/2203.02155)，2022：SFT、偏好奖励模型与 PPO 式 RLHF 流程背景。其具体实验结果不外推为所有模型和任务的保证。

来源访问与算例核验日期：**2026-09-26**。本文未实际微调模型，不声称测得 DPO 相对 PPO 的成本或效果提升。
