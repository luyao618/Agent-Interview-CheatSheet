---
id: agent-0026
title: 常见的 Multi-Agent 协作模式有哪些
category: agent
tags: [multi-agent, orchestration, supervisor, pipeline, collaboration]
difficulty: medium
role: engineer
contributor: 佚名
source: 未知
status: published
updated: 2026-06-28
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-06-28
    updated: 2026-06-28
---

## 问题

常见的 Multi-Agent 协作模式有哪些？请说明各自的适用场景与取舍。

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-28

核心结论：Multi-Agent 协作模式本质是回答两个问题——**谁决定下一步（控制结构）**与**信息怎么流动（通信结构）**。主流模式可归为下面几类，工程中常组合使用。

**一、按控制结构分**

1. **Supervisor / 编排者–执行者（Orchestrator-Worker）**：一个主管 Agent 拆解任务、把子任务派给专精的 worker，再汇总结果。控制集中、易调试、最常用。
2. **Hierarchical（分层）**：主管之下再设子主管，形成树状组织，适合超大任务的层层分解。
3. **Network / 去中心化对等（Peer-to-peer）**：Agent 平等、按需互相调用，无中心调度，灵活但易失控、难收敛。

**二、按工作流形态分**

4. **Sequential / 流水线（Pipeline）**：上游输出即下游输入，串行接力，如「检索→写作→审校」。
5. **Parallel / 并行（Map-Reduce）**：同一任务分发给多个 Agent 并行处理，再由汇总者合并，适合可拆分、求多样性的工作。
6. **Debate / Reflection（辩论–反思）**：多 Agent 提方案并互相批判，或「生成者 + 评审者」迭代，用于提升正确性与质量。
7. **Group Chat / Blackboard（群聊–黑板）**：所有 Agent 读写共享上下文，由一个 speaker-selector 决定谁发言，灵活但 token 成本高。

```
Supervisor（集中控制）
       ┌── Supervisor ──┐
       ▼       ▼        ▼
   workerA  workerB  workerC
       └───────┼────────┘
               ▼
             汇总
```

```
Pipeline（串行接力）
  检索 Agent ──► 写作 Agent ──► 审校 Agent
```

**三、选型要点**

- 任务可清晰拆解、需可控 → Supervisor / Pipeline。
- 需多视角校验、提质 → Debate / Reflection。
- 探索性、角色边界模糊 → Network / Group Chat。
- 原则：能用单 Agent 解决就别上多 Agent；一旦上了，就**保持每个角色窄而清晰**，并严控通信轮数与 token 成本。

## 延伸 / 追问

**追问：多 Agent 系统主要的失败模式与成本陷阱是什么？**

四个高频坑：① **上下文失真**——子任务在多次消息传递中被压缩/改写，信息逐跳丢失，导致最终结果跑偏；缓解办法是传结构化数据而非自由文本，并让 worker 回传时带证据来源。② **协调死循环/震荡**——Network 或 Debate 模式下 Agent 互相甩锅或反复推翻，迟迟不收敛；需设最大轮数、仲裁者或显式停止条件。③ **token 成本爆炸**——每个 Agent 都带完整上下文，群聊模式尤甚，N 个 Agent 近似 N 倍开销；可用共享黑板 + 按需检索、压缩历史来控量。④ **错误放大**——上游 Agent 的幻觉被下游当作事实继续加工；需在关键节点加校验/评审 Agent 或人工审批。一句话：多 Agent 的复杂度主要不在「单体能力」，而在**编排、通信与可观测性**。

## 参考

- Anthropic，*Building Effective Agents*（编排者-执行者、并行、评估-优化等模式）：https://www.anthropic.com/research/building-effective-agents
- LangGraph Docs，*Multi-agent Systems*（Supervisor / Network / Hierarchical）：https://langchain-ai.github.io/langgraph/concepts/multi_agent/
- Wu et al., *AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation*, 2023：https://arxiv.org/abs/2308.08155
