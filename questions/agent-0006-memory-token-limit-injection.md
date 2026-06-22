---
id: agent-0006
title: Agent 如何处理 token 限制并把短期/长期记忆注入提示词
category: agent
tags: [agent, memory, token-limit, context-injection, summarization]
difficulty: medium
role: engineer
contributor: 佚名
source: 京东
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

Agent 不只回答当前问题，还要有记忆：如何处理 token 限制，并把短期 / 长期记忆注入提示词？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

核心矛盾：上下文窗口有限且越长越贵越慢，但 Agent 需要跨多轮、跨会话「记得住」。解法是**分层记忆 + 预算化注入**——把不同时效的记忆放到不同存储，每轮按 token 预算动态挑选最相关的片段拼进 prompt，而不是把全部历史塞进去。

**记忆分层**

| 层 | 存什么 | 存哪 | 注入方式 |
| --- | --- | --- | --- |
| 短期 | 当前任务的近几轮对话 / 动作轨迹 | 上下文窗口本身 | 原文保留 + 滚动摘要 |
| 长期 | 跨会话的事实、偏好、历史经验 | 向量库 / KV / 文档 | 按需检索召回 |

**短期记忆：窗口管理 + 摘要压缩**
快满时不能简单截断（会丢早期关键信息）。常用三招组合：① **滑动窗口**保留最近 N 轮原文；② **滚动摘要**——把滑出窗口的旧对话用 LLM 压成「记忆笔记」，新摘要在旧摘要基础上增量更新；③ **要点抽取**——把关键决策 / 约束 / 中间结论结构化存成 facts，避免被摘要稀释。系统提示与任务目标始终钉在最前，不参与淘汰。

**长期记忆：检索召回**
写入时把事件 / 事实 embedding 入库（带 metadata：时间、来源、类型）。每轮用当前 query 做向量检索（必要时叠加关键词 / 时间过滤 + rerank），只召回 top-k 相关记忆。这样长期记忆规模可以无限增长，但每轮只付 top-k 的 token 成本。

**注入：按预算拼 prompt**

```
        token 预算 = 模型上限 − 留给输出的余量
  ┌────────────────────────────────────────────┐
  │ System / 角色 / 工具定义        (固定, 最高优先)  │
  │ 长期记忆: 向量检索 top-k 相关片段   (按相关度截断)  │
  │ 短期记忆: 滚动摘要 + 关键 facts    (压缩历史)      │
  │ 近 N 轮原文对话                  (最新, 全保留)   │
  │ 当前用户 query                                  │
  └────────────────────────────────────────────┘
      预算不够 → 先砍长期低分项, 再压短期摘要, 最后裁最旧轮次
```

优先级从高到低：系统/工具 > 当前 query > 近几轮原文 > 关键 facts > 检索到的长期记忆。超预算时**从低优先级、低相关度开始裁**，并对每段记忆估算 token、留足输出余量。

**工程要点**：① 检索召回要带相关度门槛，宁缺毋滥，避免无关记忆污染上下文、诱发幻觉；② 摘要本身会丢信息，关键约束应结构化存储而非只靠摘要；③ 记忆要可写可更新（事实变化时覆盖 / 失效旧记忆），并做去重；④ 全程记录注入了哪些记忆，便于调试与回放。一句话：**短期靠压缩、长期靠检索、注入靠预算与优先级**。

## 延伸 / 追问

**追问：什么时候触发摘要压缩？怎么避免「重要信息被摘要丢掉」？**

触发时机一般用阈值而非每轮都压：当上下文已用 token 超过窗口的某个水位（如 70%–80%），或对话轮数超过 N，就把最旧的、已滑出保留窗口的几轮折叠成摘要；增量更新而非全量重算，省成本也更稳定。防丢信息的关键是**分离「可摘要」与「不可摘要」**：任务目标、硬约束、已确认的关键决策、用户明确偏好这类高价值信息，单独抽成结构化 facts 长期保留（甚至钉在系统提示里），不参与有损摘要；只对寒暄、过程性试探这类低价值内容做压缩。再加一层兜底——长期记忆库保存原始轨迹，摘要丢了还能按需检索回来。

## 参考

- LangChain Docs，*Memory / How to add memory*：https://python.langchain.com/docs/how_to/chatbots_memory/
- LangGraph Docs，*Memory（short-term & long-term）*：https://langchain-ai.github.io/langgraph/concepts/memory/
- MemGPT / Letta，*Towards LLMs as Operating Systems*（分层记忆与上下文分页）：https://arxiv.org/abs/2310.08560
- Anthropic Engineering，*Building Effective Agents*：https://www.anthropic.com/engineering/building-effective-agents
