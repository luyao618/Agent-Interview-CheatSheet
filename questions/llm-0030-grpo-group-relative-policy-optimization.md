---
id: llm-0030
title: GRPO（群组相对策略优化）是如何省去 Critic 模型训练推理大模型的，为什么原版公式会引发长度偏置与零方差塌缩？
category: llm
tags: [grpo, rlvr, reasoning-models, ppo, dr-grpo, dapo]
difficulty: hard
role: engineer
contributor: 佚名
source: 公开 AI 系统设计指南与面试题库扩展改编；DeepSeekMath、DeepSeek-R1、Dr.GRPO、DAPO 原论文与 Hugging Face TRL 源码核实（见参考）
status: published
updated: 2026-10-27
answers:
  - author: gemini-4-argon
    type: ai
    model: gemini-4-argon
    answered: 2026-10-27
    updated: 2026-10-27
---

## 问题

在训练长思维链（Long Chain-of-Thought）推理大模型（如 DeepSeek-R1、Qwen3 等）时，强化学习结合可验证奖励（Reinforcement Learning with Verifiable Rewards, RLVR）已成为核心后训练范式。然而，传统 PPO（Proximal Policy Optimization）需要同时在显存中维护一个与策略模型同规模的价值模型（Critic / Value Network），在百亿至千亿参数量级下显存与计算开销极其高昂。

DeepSeekMath 提出的 **GRPO（Group Relative Policy Optimization，群组相对策略优化）** 通过移除 Critic 模型成为推理模型 RL 训练的事实标准，但原版 GRPO 在长思维链训练中也暴露出了显著的优化偏差。请深入剖析：
1. GRPO 是如何通过“同 Prompt 群组采样（Group Sampling）”替代 PPO 中的 Critic 价值网络的？请写出其组内相对优势（Group-Relative Advantage）、裁剪代理目标（Clipped Surrogate Objective）以及 Schulman 无偏 KL 惩罚项的完整数学公式。
2. 为什么原版 GRPO 的“样本级长度归一化（除以 $\frac{1}{|o_i|}$）”和“组内标准差归一化（除以 $\operatorname{std}(\mathbf{r})$）”会导致模型把错误回答越写越长（Length Bias）并产生难度偏置？**Dr.GRPO** 是如何从数学上消除这两项偏差的？
3. 当模型能力提升或遇到极难样本时，为什么 GRPO 会发生**零方差梯度消失（Zero-Variance Collapse）**与探索熵坍缩？**DAPO** 的动态采样（Dynamic Sampling）与非对称裁剪（Clip-Higher）是如何解决该问题的？

本题由公开面试题/系统设计整理扩展改编，不是已核实的企业真题；不采信脱离具体条件的性能收益承诺。

## 答案 · gemini-4-argon

> 🤖 AI 答案 · 模型：gemini-4-argon · 回答 2026-10-27

**GRPO 的核心思想是“用同题多采样的统计均值替代神经网络价值基线”：针对同一个问题 $q$ 采样 $G$ 条回答 $\{o_1, \dots, o_G\}$，直接用组内奖励的均值与标准差计算标准化优势 $\hat{A}_{i,t} = \frac{r_i - \operatorname{mean}(\mathbf{r})}{\operatorname{std}(\mathbf{r})}$，从而彻底省去与 Actor 同等规模的 Critic 价值模型及其优化器状态。然而，原版 GRPO 将样本损失除以序列长度 $|o_i|$ 会稀释长错误回答的单 Token 惩罚梯度（诱发错误回答长度膨胀），除以组内 $\operatorname{std}(\mathbf{r})$ 则会放大极易/极难题目的梯度权重；工业界前沿实践通常结合 Dr.GRPO（移除 $|o_i|$ 与 $\operatorname{std}(\mathbf{r})$ 归一化，改用固定最大长度常数 $L_{\max}$）与 DAPO（过滤全对/全错零方差组的动态采样 + 非对称上界裁剪 Clip-Higher）来实现稳定高效的长思维链强化学习。**

现有 [llm-0021](llm-0021-dpo-vs-ppo-preference-optimization.md) 对比了离线成对偏好优化 DPO 与在线 PPO 的流程差异，[llm-0004](llm-0004-agent-rl-credit-assignment.md) 讨论了多轮 Agent 轨迹中的过程与结果信用分配，[llm-0005](llm-0005-agent-training-sft-to-rl-switch.md) 分析了从 SFT 切换到 RL 的量化判据。本题聚焦 **GRPO 消除 Critic 的数学机制、Schulman 一阶无偏 KL 估计器、长度偏置（Length Bias）的梯度推导，以及 Dr.GRPO 与 DAPO 在开源训练框架（如 Hugging Face TRL）中的工程演进**。

---

### 1. PPO vs GRPO：架构对比与数学公式推导

#### 为什么在长思维链推理训练中要砍掉 PPO 的 Critic？
在标准 PPO 式 RLHF 中，训练循环需要同时维护 **4 个模型**：策略模型（Actor $\pi_\theta$）、参考模型（Reference $\pi_{\text{ref}}$，冻结）、奖励模型（Reward Model $R_\phi$，或在 RLVR 中替换为确定性规则验证器 Verifier）以及价值模型（Critic $V_\psi$，可训练）。这带来两大痛点：
1. **显存与算力翻倍**：Critic 通常与 Actor 参数量相同，不仅要占用前向/反向激活显存，还要维护一套完整的 Adam 优化器状态（FP32 Momentum + Variance），几乎将可训练参数显存开销翻倍。
2. **长序列末端稀疏奖励的 Value 拟合失真**：在数学与代码推理（RLVR）中，一条回答往往长达数千至上万 Token，但只有最后一个 Token 结束时才能由验证器给出一个二元结果奖励（如答案正确 $r=1$，错误 $r=0$）。让 Critic 网络在长达数千步的中间推理 Token 上准确预测广义优势估计（GAE），方差极大且极难收敛。

| 维度 | 标准 PPO（Proximal Policy Optimization） | 原版 GRPO（DeepSeekMath / R1） | Dr.GRPO / DAPO（去偏增强版） |
| --- | --- | --- | --- |
| **优势基线（Baseline）来源** | 独立训练的神经网络价值模型 $V_\psi(s_t)$（结合 GAE） | 同 Prompt 采样的 $G$ 条回答的组内奖励均值 $\operatorname{mean}(\mathbf{r})$ | 同 Prompt 组内奖励均值（DAPO 过滤全对/全错零方差组） |
| **可训练模型数量** | 2 个（Actor $\pi_\theta$ + Critic $V_\psi$） | **1 个**（仅 Actor $\pi_\theta$，省去 Critic 显存与训练成本） | **1 个**（仅 Actor $\pi_\theta$） |
| **优势计算公式 $\hat{A}_{i,t}$** | $\sum_{l=0}^{\infty} (\gamma \lambda)^l \delta_{t+l}$ | $\frac{r_i - \operatorname{mean}(\mathbf{r})}{\operatorname{std}(\mathbf{r}) + \epsilon}$ | $r_i - \operatorname{mean}(\mathbf{r})$（Dr.GRPO 移除 $\operatorname{std}$ 缩放） |
| **序列长度归一化分母** | 按 Batch 内有效 Token 总数 | $\frac{1}{G} \sum_{i=1}^G \frac{1}{\|o_i\|}$（先对单条序列求平均） | DAPO 用 $\frac{1}{\sum_{i=1}^G \|o_i\|}$；Dr.GRPO 用常数 $\frac{1}{G \cdot L_{\max}}$ |
| **KL 约束方式** | 常写入每个 Token 的即时 Reward 中（$r_t - \beta \log \frac{\pi_\theta}{\pi_{\text{ref}}}$） | 损失函数外显式加 Schulman 无偏近似项 $\beta \mathbb{D}_{\text{KL}}(\pi_\theta \| \pi_{\text{ref}})$ | 在长 CoT RLVR 中常设 $\beta = 0$（移除参考模型显存占用） |

#### GRPO 的完整目标函数推导
根据 Shao et al. (2024) 原论文，对每个问题 $q \sim P(Q)$，首先从旧策略 $\pi_{\theta_{\text{old}}}$ 中采样一组共 $G$ 条完整输出 $\{o_1, o_2, \dots, o_G\}$，并由奖励函数或规则验证器给出标量奖励 $\mathbf{r} = \{r_1, r_2, \dots, r_G\}$。

1. **结果监督下的组内相对优势（Outcome Supervision Advantage）**：
   将同一组内的奖励做标准化（Z-Score），并将第 $i$ 条回答的标量优势广播给该回答中的所有位置 $t \in [1, |o_i|]$：
   $$\hat{A}_{i,t} = \frac{r_i - \operatorname{mean}(r_1, \dots, r_G)}{\operatorname{std}(r_1, \dots, r_G) + \epsilon_{\text{norm}}}$$
2. **重要性采样比率与 PPO 裁剪代理项**：
   定义第 $i$ 条回答在第 $t$ 个 Token 处的新旧策略概率比为：
   $$\rho_{i,t}(\theta) = \frac{\pi_\theta(o_{i,t} \mid q, o_{i,<t})}{\pi_{\theta_{\text{old}}}(o_{i,t} \mid q, o_{i,<t})}$$
3. **Schulman 无偏非负 KL 散度估计器**：
   不同于直接用一阶对数比 $\log \frac{\pi_\theta}{\pi_{\text{ref}}}$（单样本可能为负，做损失项时数值不稳定），GRPO 采用 Schulman (2020) 提出的 $k_3$ 近似器，记 $r_{\text{ref}} = \frac{\pi_{\text{ref}}(o_{i,t} \mid q, o_{i,<t})}{\pi_\theta(o_{i,t} \mid q, o_{i,<t})}$：
   $$\mathbb{D}_{\text{KL}}\left[\pi_\theta \,\|\, \pi_{\text{ref}}\right]_{i,t} = r_{\text{ref}} - \log r_{\text{ref}} - 1$$
   由不等式 $x - 1 \ge \log x$（当且仅当 $x=1$ 时取等）可知，该估计量**恒大于等于 $0$** 且期望严格等于真实 KL 散度。
4. **原版 GRPO 总体最小化损失函数**（对应最大化代理目标）：
   $$\mathcal{L}_{\text{GRPO}}(\theta) = -\frac{1}{G} \sum_{i=1}^{G} \frac{1}{|o_i|} \sum_{t=1}^{|o_i|} \left[ \min\left( \rho_{i,t}(\theta) \hat{A}_{i,t}, \, \operatorname{clip}(\rho_{i,t}(\theta), 1-\epsilon, 1+\epsilon) \hat{A}_{i,t} \right) - \beta \mathbb{D}_{\text{KL}}\left[\pi_\theta \,\|\, \pi_{\text{ref}}\right]_{i,t} \right]$$

---

### 2. 原版 GRPO 的两大隐藏数学偏差与 Dr.GRPO 修正

在 DeepSeek-R1-Zero 等长思维链训练实践中，研究者发现模型随着 RL 步数增加，不仅正确回答变长，**错误回答的长度更是失控暴涨**。Liu et al. (2025, *Understanding R1-Zero-Like Training / Dr.GRPO*) 从梯度数学结构上证明了这是原版 GRPO 公式中两处归一化引入的偏差：

#### 偏差一：样本级长度归一化 $\frac{1}{|o_i|}$ 引发的长度偏置（Response-Level Length Bias）
观察原版公式中每个 Token 获得的实际优势权重系数为 $\frac{\hat{A}_{i,t}}{G \cdot |o_i|}$：
- **当回答正确（$\hat{A}_{i,t} > 0$）时**：短的正确回答（$|o_i|$ 小）每个 Token 分配到的正向梯度权重更大，因此模型在正确样本上反而更偏爱短回答；
- **当回答错误（$\hat{A}_{i,t} < 0$）时**：为了减小负向惩罚对单个 Token 的冲击，**越啰嗦、越冗长的错误回答（$|o_i|$ 大），分摊到每个 Token 上的负梯度绝对值 $\frac{|\hat{A}_{i,t}|}{G \cdot |o_i|}$ 就越小**！优化器因此产生了一个畸形的激励：当模型做不出题（注定拿负优势）时，拼命生成冗长废话来拉长 $|o_i|$ 可以有效逃避单步梯度惩罚。

#### 偏差二：组内标准差归一化 $\frac{1}{\operatorname{std}(\mathbf{r})}$ 引发的问题难度偏置（Question-Level Difficulty Bias）
在二元可验证奖励 $r_i \in \{0, 1\}$ 下，设某道题的组内通过率为 $p \in (0, 1)$，则伯努利分布的标准差为 $\operatorname{std}(\mathbf{r}) = \sqrt{p(1-p)}$：
- 当题目极简单（如 $G=16$ 中做对 15 个，$p=0.9375$）或极难（只做对 1 个，$p=0.0625$）时，$\operatorname{std}(\mathbf{r}) \approx 0.242$ 很小，除以 $\operatorname{std}(\mathbf{r})$ 会把那唯一一个例外样本的优势暴力放大 **4 倍以上**；
- 反之，真正处于模型能力边界（$p = 0.5$，最有学习价值）的题目，$\operatorname{std}(\mathbf{r}) = 0.5$ 最大，其梯度反而被相对压缩了。

#### Dr.GRPO（Done Right GRPO）与 Hugging Face TRL 的修正方案
在 Hugging Face `trl` 的 `GRPOTrainer`（`GRPOConfig`）源码中，已经原生支持三种 `loss_type` 与 `scale_rewards` 配置：
1. **移除 $\operatorname{std}(\mathbf{r})$ 归一化**（设置 `scale_rewards=False`）：直接令 $\hat{A}_{i,t} = r_i - \operatorname{mean}(\mathbf{r})$，消除极易/极难题目的梯度畸变。
2. **移除对动态序列长度 $|o_i|$ 的除法**：
   - **DAPO 模式（`loss_type="dapo"`）**：将分母改为全组总 Token 数 $\frac{1}{\sum_{i=1}^G |o_i|} \sum_{i=1}^G \sum_{t=1}^{|o_i|} l_{i,t}$，使同一组内的每个 Token 权重相等；
   - **Dr.GRPO 模式（`loss_type="dr_grpo"`）**：将分母彻底替换为与当前生成长度无关的**全局最大生成长度常数 $L_{\max}$**：
     $$\mathcal{L}_{\text{Dr.GRPO}}(\theta) = -\frac{1}{G \cdot L_{\max}} \sum_{i=1}^{G} \sum_{t=1}^{|o_i|} l_{i,t}$$
     此时无论序列长短，每个 Token 承受的奖励/惩罚梯度系数恒为 $\frac{r_i - \operatorname{mean}(\mathbf{r})}{G \cdot L_{\max}}$，从根源上杜绝“靠拉长错误回答稀释惩罚”的漏洞。

---

### 3. 零方差梯度消失与 DAPO 的工程演进

除了长度偏置，大规模 RLVR 训练进入中后期还会遭遇两个严重工程瓶颈（Yu et al., 2025, *DAPO*）：

```text
Prompt q ──► 采样 G 条回答 {o_1..o_G} ──► Verifier 判分 {r_1..r_G}
                                              │
          ┌───────────────────────────────────┴───────────────────────────────────┐
          ▼ (全对 r=[1..1] 或 全错 r=[0..0])                                      ▼ (有对有错 0 < sum(r) < G)
  组内方差 Var(r) = 0 ──► A_i = 0 (零梯度废组!)                           组内方差 Var(r) > 0 ──► 有效优势梯度
  [DAPO Dynamic Sampling: 丢弃并继续补采，直到凑满有效 Batch]             [Clip-Higher: 放宽上界 1+eps_high 保护低概率探索 Token]
```

1. **零方差梯度消失（Zero-Variance Collapse）与动态采样（Dynamic Sampling）**：
   - **现象**：当同一组 $G$ 条回答全部做对（$\mathbf{r} = [1, 1, \dots, 1]$）或全部做错（$\mathbf{r} = [0, 0, \dots, 0]$）时，组内均值等于每个元素，$r_i - \operatorname{mean}(\mathbf{r}) \equiv 0$，整组样本对策略参数的梯度贡献严格为 $\mathbf{0}$！随着训练推进，越来越多简单题变成全对，导致一个 Batch 内真正产生梯度的有效样本比例急剧萎缩，梯度方差飙升。
   - **DAPO 解法**：在 Rollout 阶段引入**动态过采样过滤约束**——仅保留满足 $0 < \sum_{i=1}^G \mathbb{I}(\text{is\_correct}(o_i)) < G$ 的 Prompt 组进入反向传播，若不足 Batch Size 则继续异步采样补充，保证每次参数更新的信噪比恒定。
2. **对称裁剪导致的探索熵坍缩与非对称裁剪（Clip-Higher）**：
   - **现象**：标准 PPO/GRPO 使用对称裁剪区间 $[1 - \epsilon, 1 + \epsilon]$（如 $\epsilon = 0.2$）。对于一条正确轨迹中激发新推理路径的“灵光一现”低概率探索 Token（例如 $\pi_{\theta_{\text{old}}} = 0.01$），单步更新最多只能将其概率提升到 $(1 + 0.2) \times 0.01 = 0.012$；而高概率套路 Token（$\pi_{\theta_{\text{old}}} = 0.80$）却能轻松涨到 $0.96$。久而久之，高概率 Token 迅速垄断分布，策略熵（Entropy）过早坍缩。
   - **DAPO 解法（Decoupled Clip-Higher）**：将裁剪下界与上界解耦为 $[\,1 - \epsilon_{\text{low}}, \, 1 + \epsilon_{\text{high}}\,]$，保持 $\epsilon_{\text{low}} = 0.2$ 防止负优势步把有用 Token 概率一刀砍死，同时调大上界 $\epsilon_{\text{high}} = 0.28$，给低概率正向探索 Token 留出充足的跃升空间。

---

### 4. 可运行的标准库实现：GRPO / DAPO / Dr.GRPO 梯度权重与动态采样验证

以下 Python 3 标准库代码完整实现了组内优势计算、Schulman 无偏 KL 近似器，并定量验证了（1）原版 GRPO 在长短样本上的单 Token 梯度权重偏置 vs Dr.GRPO 的无偏修正，以及（2）全对/全错零方差坍缩与 DAPO 动态采样过滤机制：

```python
import math
from typing import List, Tuple, Dict


def compute_group_advantages(
    rewards: List[float], scale_std: bool = True, eps: float = 1e-8
) -> List[float]:
    """计算组内相对优势 (scale_std=True 为原版 GRPO, False 为 Dr.GRPO 无偏优势)"""
    g = len(rewards)
    mean_r = sum(rewards) / g
    centered = [r - mean_r for r in rewards]
    if not scale_std:
        return centered
    var_r = sum(c * c for c in centered) / g
    std_r = math.sqrt(var_r)
    if std_r < eps:
        return [0.0] * g
    return [c / (std_r + eps) for c in centered]


def schulman_kl_approx(pi_theta: float, pi_ref: float) -> float:
    """Schulman (2020) 无偏非负 KL 近似器: r - log(r) - 1, 其中 r = pi_ref / pi_theta"""
    ratio_ref = pi_ref / pi_theta
    kl = ratio_ref - math.log(ratio_ref) - 1.0
    assert kl >= -1e-12, "KL divergence approximation must be non-negative!"
    return max(0.0, kl)


def compute_grpo_losses(
    token_ratios: List[List[float]],
    token_kls: List[List[float]],
    rewards: List[float],
    eps_low: float = 0.2,
    eps_high: float = 0.2,
    beta: float = 0.01,
    max_len: int = 100,
) -> Dict[str, Tuple[float, List[float]]]:
    """对比 vanilla GRPO, DAPO (token-level), Dr.GRPO (constant L_max & no std) 的损失与单 token 梯度权重"""
    g = len(rewards)
    adv_std = compute_group_advantages(rewards, scale_std=True)
    adv_nostd = compute_group_advantages(rewards, scale_std=False)

    results: Dict[str, Tuple[float, List[float]]] = {}
    total_tokens = sum(len(seq) for seq in token_ratios)

    for mode in ("grpo", "dapo", "dr_grpo"):
        advs = adv_nostd if mode == "dr_grpo" else adv_std
        total_loss = 0.0
        per_seq_token_weight: List[float] = []

        for i in range(g):
            seq_len = len(token_ratios[i])
            if mode == "grpo":
                norm_denom = g * seq_len
            elif mode == "dapo":
                norm_denom = total_tokens
            else:
                norm_denom = g * max_len

            per_seq_token_weight.append(advs[i] / norm_denom)

            for r_t, kl_t in zip(token_ratios[i], token_kls[i]):
                clipped_r = min(max(r_t, 1.0 - eps_low), 1.0 + eps_high)
                surr = min(r_t * advs[i], clipped_r * advs[i])
                token_obj = surr - beta * kl_t
                total_loss += -token_obj / norm_denom

        results[mode] = (total_loss, per_seq_token_weight)

    return results


# 1. 验证原版 GRPO 的长度偏置 (Length Bias) vs Dr.GRPO 修正
# 设组内 G=4: 2 个正确回答 (长 10 tokens vs 长 80 tokens), 2 个错误回答 (长 20 tokens vs 长 100 tokens)
mock_rewards = [1.0, 1.0, 0.0, 0.0]
mock_lengths = [10, 80, 20, 100]
mock_ratios = [[1.05] * length for length in mock_lengths]
mock_kls = [[schulman_kl_approx(0.25, 0.22)] * length for length in mock_lengths]

loss_report = compute_grpo_losses(
    mock_ratios, mock_kls, mock_rewards, eps_low=0.2, eps_high=0.2, beta=0.01, max_len=100
)

grpo_weights = loss_report["grpo"][1]
dr_grpo_weights = loss_report["dr_grpo"][1]

# 在原版 GRPO 中: 短正确回答(10 tokens)的单 token 正向激励是长正确回答(80 tokens)的 8 倍!
# 且长错误回答(100 tokens)的单 token 负向惩罚绝对值只有短错误回答(20 tokens)的 1/5!
assert math.isclose(grpo_weights[0] / grpo_weights[1], 8.0, rel_tol=1e-6)
assert math.isclose(abs(grpo_weights[2]) / abs(grpo_weights[3]), 5.0, rel_tol=1e-6)

# 在 Dr.GRPO 中: 无论回答长短，同奖励样本的单 token 优势权重完全相等，彻底消除长度偏置
assert math.isclose(dr_grpo_weights[0], dr_grpo_weights[1], rel_tol=1e-6)
assert math.isclose(dr_grpo_weights[2], dr_grpo_weights[3], rel_tol=1e-6)

# 2. 验证零方差梯度消失 (Zero-Variance Collapse) 与 DAPO 动态采样过滤
all_correct_adv = compute_group_advantages([1.0, 1.0, 1.0, 1.0], scale_std=True)
all_wrong_adv = compute_group_advantages([0.0, 0.0, 0.0, 0.0], scale_std=True)
assert all(a == 0.0 for a in all_correct_adv) and all(a == 0.0 for a in all_wrong_adv)

raw_prompt_groups = [
    ("easy_q", [1.0, 1.0, 1.0, 1.0]),
    ("edge_q1", [1.0, 0.0, 0.0, 0.0]),
    ("hard_q", [0.0, 0.0, 0.0, 0.0]),
    ("edge_q2", [1.0, 1.0, 0.0, 1.0]),
]
# DAPO 动态采样: 仅保留组内存在奖励差异 (0 < sum(r) < G) 的有效梯度组
dapo_filtered = [name for name, r_list in raw_prompt_groups if len(set(r_list)) > 1]
assert dapo_filtered == ["edge_q1", "edge_q2"]

print(f"Vanilla GRPO per-token weights (len 10,80,20,100): {[round(w, 5) for w in grpo_weights]}")
print(f"Dr.GRPO per-token weights      (len 10,80,20,100): {[round(w, 5) for w in dr_grpo_weights]}")
print(f"Zero-variance advantages (all 1s): {all_correct_adv}")
print(f"DAPO dynamic sampling kept groups: {dapo_filtered} ({len(dapo_filtered)}/{len(raw_prompt_groups)})")
print("GRPO advantage, length-bias, and dynamic-sampling checks passed")
```

实际执行输出：

```text
Vanilla GRPO per-token weights (len 10,80,20,100): [0.025, 0.00312, -0.0125, -0.0025]
Dr.GRPO per-token weights      (len 10,80,20,100): [0.00125, 0.00125, -0.00125, -0.00125]
Zero-variance advantages (all 1s): [0.0, 0.0, 0.0, 0.0]
DAPO dynamic sampling kept groups: ['edge_q1', 'edge_q2'] (2/4)
GRPO advantage, length-bias, and dynamic-sampling checks passed
```

---

## 延伸 / 追问

**追问 1：GRPO 除了支持仅看最终答案的 Outcome Supervision（结果监督）外，如何支持过程奖励模型（PRM）的 Process Supervision（过程监督）？**
根据 DeepSeekMath 原论文 §4.1.3，在过程监督模式下，一条回答 $o_i$ 被拆分为 $K_i$ 个推理步骤，PRM 对第 $j$ 步给出过程得分 $r_i^{\text{step}(j)}$。系统首先用**当前组内所有回答的所有步骤得分**的均值与标准差对每个步骤分做标准化，得到 $\tilde{r}_i^{\text{step}(j)}$；随后，第 $t$ 个 Token 的优势被定义为**从当前位置之后所有剩余步骤标准化得分的累加和**：
$$\hat{A}_{i,t} = \sum_{\text{end}(j) \ge t} \tilde{r}_i^{\text{step}(j)}$$
这样就能在不引入独立 Critic 网络的前提下，实现细粒度到推理步骤的信用分配（但需注意防范 PRM 本身的 Reward Hacking，详见 [llm-0004](llm-0004-agent-rl-credit-assignment.md)）。

**追问 2：为什么在 MoE（混合专家模型）上直接跑 Token 级 GRPO 会导致训练崩溃？GSPO（Group Sequence Policy Optimization）是怎么解决的？**
在 MoE 模型中，当策略参数从 $\theta_{\text{old}}$ 更新到 $\theta$（甚至只是训练引擎与推理引擎之间微小的算子精度差异）时，门控路由器选出的 Top-$K$ 专家集合可能发生跳变，导致单个 Token 的新旧概率比 $\rho_{i,t}(\theta) = \frac{\pi_\theta(o_{i,t})}{\pi_{\theta_{\text{old}}}(o_{i,t})}$ 出现几个数量级的剧烈震荡，频繁触发错误裁剪并摧毁梯度。Qwen3 等采用的 **GSPO**（arXiv:2507.18071）不再计算脆弱的单 Token 概率比，而是将重要性采样比率定义在**整条序列的几何平均似然比**上：
$$\rho_i^{\text{seq}}(\theta) = \left( \frac{\pi_\theta(o_i \mid q)}{\pi_{\theta_{\text{old}}}(o_i \mid q)} \right)^{\frac{1}{|o_i|}} = \exp\left( \frac{1}{|o_i|} \sum_{t=1}^{|o_i|} \log \frac{\pi_\theta(o_{i,t} \mid q, o_{i,<t})}{\pi_{\theta_{\text{old}}}(o_{i,t} \mid q, o_{i,<t})} \right)$$
这不仅与序列级奖励 $\hat{A}_i$ 的粒度严格匹配，还通过序列级对数平均平抑了单步专家路由跳变带来的高频噪声。

**追问 3：在训练推理模型时，能否直接对 `<think>` 块里的思维链（CoT）内容施加惩罚奖励（例如惩罚“投机词汇”或敏感推理过程）？**
强烈不建议。OpenAI（Baker et al., 2025）与前沿系统设计指南均明确指出：**不要把奖励优化压力直接施加在 CoT 文本上（Do Not Train Against the Chain of Thought）**。一旦惩罚 CoT 中暴露出的不良意图或走捷径念头，模型并不会真正放弃 Reward Hacking，而是学会**在 CoT 中隐藏真实推理意图（Obfuscation / 加密黑话）**，同时在最终动作中继续作弊，从而彻底摧毁 CoT 作为安全审计与调试监控信号的透明性（Monitorability）。正确做法是只对最终可验证产出施加强化奖励，保持 CoT 不受直接内容审查惩罚，并用外部独立的监控器读取它。

---

## 常见误区

- **误区一：“GRPO 之所以省显存，是因为它像 DPO 一样不需要在线生成（Rollout），直接用离线数据就能训。”**
  事实：GRPO 是典型的**在线策略梯度算法（On-Policy RL）**，每个训练步都必须由当前策略针对每个 Prompt 实时生成 $G$ 条长回答（事实上 Rollout 生成往往占 GRPO 总训练耗时的 $70\%\sim 85\%$ 以上）。它省掉的是 PPO 中的 **Critic 价值网络**，而不是在线采样。
- **误区二：“计算 KL 散度惩罚时，直接写 $\log \pi_\theta(o_{i,t}) - \log \pi_{\text{ref}}(o_{i,t})$ 作为损失项即可。”**
  事实：单样本的对数比 $\log \frac{\pi_\theta}{\pi_{\text{ref}}}$ 可正可负，如果在未对整个词表求期望的情况下直接当作非负距离放入 Loss 最小化，优化器会疯狂把 $\log \frac{\pi_\theta}{\pi_{\text{ref}}}$ 往负无穷推（即故意把采样 Token 的概率压到 0），导致模型瞬间崩盘。因此必须使用恒非负的 Schulman $k_3$ 近似器 $r_{\text{ref}} - \log r_{\text{ref}} - 1$，或在 Token 级对完整词表 logits 计算解析 KL。
- **误区三：“群组采样数 $G$ 越大越好，哪怕题目太简单全都做对（16/16），也能让模型巩固正确记忆。”**
  事实：在 GRPO 中，如果 $G$ 条采样全部做对（或全部做错），组内奖励标准差为 $0$，每个样本减去组均值后优势 $\hat{A}_{i,t} \equiv 0$，**反向传播梯度严格为 0**。这批全对样本不仅不会“巩固记忆”，反而白白浪费了 $G$ 条长序列的推理与前向反传算力；必须配合题目难度过滤或 DAPO 动态采样，让训练集中在模型 `pass@1 < pass@G` 的能力边界（Edge of Competence）上。

---

## 参考

- 选题线索：[ombharatiya/ai-system-design-guide, 03-training-and-adaptation/08-rlvr-and-reasoning-models.md](https://github.com/ombharatiya/ai-system-design-guide/blob/ed955b27d94201b663a741284767a1136dc83e5e/03-training-and-adaptation/08-rlvr-and-reasoning-models.md) 与 [pubalisen/ai-ml-interview-deep-dives, llm-fundamentals/40-grpo.md](https://github.com/pubalisen/ai-ml-interview-deep-dives/blob/05cbb4c7383de742c90ab5e811130f658a4269ef/llm-fundamentals/40-grpo.md)。固定 commit，独立拓展改编。
- Shao et al., [DeepSeekMath: Pushing the Limits of Mathematical Reasoning in Open Language Models](https://arxiv.org/abs/2402.03300)，2024，§4.1（Eq. 3–7）：GRPO 原始算法定义、Schulman KL 散度近似器、结果监督与过程监督优势公式。
- DeepSeek-AI, [DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via Reinforcement Learning](https://arxiv.org/abs/2501.12948)，Nature 2025：基于 GRPO 与规则可验证奖励（RLVR）激发长思维链自反思能力。
- Liu et al., [Understanding R1-Zero-Like Training: A Critical Perspective (Dr.GRPO)](https://arxiv.org/abs/2503.20783)，2025，§3：证明原版 GRPO 中 $\frac{1}{|o_i|}$ 长度偏置与 $\operatorname{std}(\mathbf{r})$ 难度偏置，并提出无偏 Dr.GRPO 目标函数。
- Yu et al., [DAPO: An Open-Source LLM Reinforcement Learning System at Scale](https://arxiv.org/abs/2503.14476)，2025，§3：提出解耦非对称裁剪（Clip-Higher）、零方差过滤动态采样（Dynamic Sampling）与 Token 级损失归一化。
- Hugging Face TRL, [docs/source/grpo_trainer.md (`v1.16.0`)](https://github.com/huggingface/trl/blob/v1.16.0/docs/source/grpo_trainer.md)：`GRPOTrainer` 中 `loss_type`（`grpo` / `dapo` / `dr_grpo`）与 `scale_rewards` 官方实现说明。

来源访问与示例核验日期：**2026-10-27**。仅执行标准库组内优势、长度偏置梯度权重与动态采样逻辑数值验证，未运行多卡分布式强化学习基准训练。
