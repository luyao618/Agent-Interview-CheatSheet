---
id: agent-0018
title: 有哪些 RAG/Agent 评测维度
category: agent
tags: [agent, evaluation, rag, metrics, task-success]
difficulty: medium
role: engineer
contributor: 佚名
source: 快手
status: published
updated: 2026-06-22
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-06-22
    updated: 2026-06-22
---

## 问题

有哪些 RAG / Agent 评测维度？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

评测要分层看：RAG 关注「检索 + 生成」两段质量，Agent 在此之上再加「多步执行 + 工具 + 成本 + 安全」。一个总览框架：

```
                 端到端：任务完成率 / 用户满意度
                          ▲
   ┌──────────────────────┼──────────────────────┐
   │ RAG 段                │ Agent 段              │
   │ ① 检索质量            │ ④ 任务完成            │
   │ ② 生成质量            │ ⑤ 工具调用            │
   │ ③ 忠实度/引用         │ ⑥ 效率(步数/成本)     │
   └──────────────────────┴──────────────────────┘
                  ⑦ 鲁棒性 / 安全（横切所有层）
```

**① 检索质量（RAG 的地基）**：召回相关文档的能力。指标 recall@k、precision@k、MRR、nDCG、hit rate、context relevance。检索差，后面再强也救不回来（garbage in）。

**② 生成质量**：答案是否正确、完整、相关。answer correctness / relevance、completeness，可用参考答案对比或 LLM-as-judge 打分。

**③ 忠实度与可溯源（RAG 特有）**：答案是否**只**基于检索到的上下文、有没有幻觉、引用是否对得上。faithfulness / groundedness、citation accuracy——这是 RAG 区别于普通 QA 的核心维度。

**④ 任务完成率（Agent 的北极星）**：端到端把任务办成没有。task success rate、goal completion，常需在真实/仿真环境跑用例集（如 WebArena、τ-bench）判定，而非只看单轮输出。

**⑤ 工具调用正确性**：该不该调、调哪个、参数对不对、错误能否恢复。tool-selection accuracy、参数有效性、API 调用成功率、错误处理能力。

**⑥ 效率 / 成本**：达成目标的代价。步数（steps / turns）、token 与 \$ 成本、端到端延迟、是否陷入冗余循环。两个 Agent 都成功，但一个 3 步一个 30 步，工程价值差很多。

**⑦ 鲁棒性与安全（横切）**：抗扰动（改写/噪声/对抗输入）、prompt 注入与越狱防御、敏感数据不泄露、高风险动作有护栏、可观测可回放。

**方法论**：① 离线固定评测集 + 自动指标做回归；② LLM-as-judge 补主观维度（相关性、忠实度），但要校准、防偏差；③ 关键场景人工评估兜底；④ 线上看真实任务成功率与用户反馈。一句话：**RAG 重「检索准 + 不编造」，Agent 重「办成事 + 少花钱 + 不闯祸」。**

## 延伸 / 追问

**追问：只有一个最终答案、没有标注的中间步骤，怎么评 Agent 的多步过程？**

两条路。**结果导向**：只验最终状态——任务环境里检查目标是否达成（如数据库记录已更新、文件已生成），用可编程的成功判据，不关心路径，适合有明确终态的任务。**过程导向**：把轨迹（thought-action-observation）喂给 LLM-as-judge 或规则检查，评估每步工具选择、参数、是否绕弯/重复，定位「在哪一步崩的」。实践中两者结合：先用结果判成败，再对失败轨迹做过程归因找瓶颈；缺标注时可用「参考轨迹」或更强模型生成的轨迹作软基准，并辅以人工抽检校准 judge。

## 参考

- Ragas，*Metrics*（faithfulness / answer & context relevance）：https://docs.ragas.io/en/stable/concepts/metrics/
- TruLens，*RAG Triad*（context relevance / groundedness / answer relevance）：https://www.trulens.org/getting_started/core_concepts/rag_triad/
- τ-bench，*A Benchmark for Tool-Agent-User Interaction*：https://arxiv.org/abs/2406.12045
