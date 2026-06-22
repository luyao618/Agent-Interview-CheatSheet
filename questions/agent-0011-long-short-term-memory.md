---
id: agent-0011
title: Agent 的 long-term memory 与 short-term memory 如何设计
category: agent
tags: [agent, memory, long-term, short-term, vector-store]
difficulty: medium
role: engineer
contributor: 佚名
source: 淘天/阿里
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

Agent 的 long-term memory（长期记忆）与 short-term memory（短期记忆）如何设计？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

核心思路：**按「时效 + 容量 + 访问成本」分层**。短期记忆服务「当前这一任务」，住在上下文窗口里、容量小但即时可见；长期记忆服务「跨会话沉淀」，住在外部存储、容量近乎无限但需检索召回。两层各管一段生命周期，靠**写入 / 检索 / 遗忘**三条策略联动。

**分层设计**

| 维度 | 短期记忆 | 长期记忆 |
| --- | --- | --- |
| 角色 | 当前任务的工作记忆 | 跨会话的经验 / 事实库 |
| 载体 | 上下文窗口 + 滚动摘要 | 向量库 / KV / 文档 / 知识图谱 |
| 容量 | 受 token 上限约束 | 近乎无限 |
| 访问 | 直接在 prompt 里，零检索 | 按需向量检索召回 |
| 时效 | 会话结束即失效 | 持久，可更新 / 失效 |

```
   感知输入 ──► 短期记忆(工作区) ──► LLM 决策 ──► 行动
                  │  ▲                          │
        固化重要信息│  │ 检索召回 top-k           │ 轨迹回写
                  ▼  │                          ▼
              ┌─────────────────────────────────────┐
              │  长期记忆：向量库 / KV / 文档(带 metadata) │
              └─────────────────────────────────────┘
```

**短期记忆设计**：保留最近 N 轮原文 + 系统提示/任务目标钉在最前；窗口接近水位（70%–80%）时，把滑出的旧对话用 LLM 增量压成「滚动摘要」，关键决策 / 约束单独抽成结构化 facts，避免被有损摘要稀释。

**长期记忆设计**：三件事——
- **写入（remember）**：不是什么都存。把「用户偏好、稳定事实、任务结论、可复用经验」筛出来，embedding + metadata（时间、来源、类型、置信度）入库；写时做去重与冲突合并。
- **检索（recall）**：每轮用当前 query 向量检索，叠加关键词 / 时间 / 类型过滤，再 rerank，只取 top-k 且过相关度门槛——**宁缺毋滥**，无关记忆会污染上下文、诱发幻觉。
- **遗忘（forget）**：靠 TTL 过期、LRU/低命中淘汰、事实变更时覆盖失效旧值、敏感信息主动删除。遗忘不是丢失，而是控制信噪比与成本。

**两层的衔接**：短期里反复出现或被明确标记重要的内容 → 固化进长期；长期检索回来的片段 → 临时注入短期参与本轮推理。注入时按 token 预算分配：系统/工具 > 当前 query > 近 N 轮原文 > 关键 facts > 长期召回，超预算从低优先级、低相关度开始裁。

**工程要点**：① 记忆要可写、可更新、可删除，别只追加不维护；② 摘要会丢信息，硬约束走结构化存储而非摘要；③ 全程记录注入了哪些记忆，便于调试回放；④ 隐私合规——长期库要支持按用户删除。一句话：**短期靠压缩管「当下」，长期靠检索 + 遗忘管「沉淀」，两层用写入/召回打通**。

## 延伸 / 追问

**追问：什么样的信息才值得写进长期记忆？写多了会怎样？**

判据是「**跨会话复用价值 × 稳定性**」：用户长期偏好、确定的事实（如账号配置）、任务的最终结论、可迁移的经验值得写；而寒暄、一次性中间过程、易变的临时状态不该进长期库。写太多有三害：① 检索时近义噪声变多，top-k 被无关项挤占，召回精度下降；② 存储与 embedding 成本线性上涨；③ 旧的、过期的事实若不失效，会和新事实冲突、误导决策。实践上加一道「写入闸门」——重要性打分过阈值才落库，配合去重、TTL 与冲突时「新值覆盖旧值」，让长期记忆保持高信噪比而不是无限堆积。

## 参考

- LangGraph Docs，*Memory（short-term & long-term）*：https://langchain-ai.github.io/langgraph/concepts/memory/
- MemGPT / Letta，*Towards LLMs as Operating Systems*（分层记忆与上下文分页）：https://arxiv.org/abs/2310.08560
- Generative Agents，*Interactive Simulacra of Human Behavior*（记忆写入 / 检索 / 反思）：https://arxiv.org/abs/2304.03442
- LangChain Docs，*Memory / How to add memory*：https://python.langchain.com/docs/how_to/chatbots_memory/
