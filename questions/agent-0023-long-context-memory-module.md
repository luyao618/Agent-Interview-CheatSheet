---
id: agent-0023
title: 超长上下文怎么处理？记忆模块怎么设计
category: agent
tags: [agent, long-context, memory, summarization, retrieval]
difficulty: medium
role: engineer
contributor: 佚名
source: 腾讯
status: published
updated: 2026-06-23
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-06-23
    updated: 2026-06-23
---

## 问题

超长上下文怎么处理？记忆模块怎么设计？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-23

这题考的是**落地**：超长上下文是「**进窗前怎么裁**」的预算问题，记忆模块是「**出窗后存哪、怎么取、何时删**」的存储问题，两者一头一尾接在同一条数据流上。

**一、超长上下文 = token 预算调度**

把上下文窗口当稀缺资源，按优先级排队、按预算裁剪，组装顺序固定：

```
[system + 任务目标]  钉死最前，永不裁
[结构化 facts]       关键约束/数字，精确存
[近 N 轮原文]        高保真，最相关
[更早历史→滚动摘要]   有损压缩，留主线
[外部召回 top-k]     按当前 query 检索注入
        ▲ 超预算时从「低优先级+低相关」开始裁，工具结果先裁冗余字段
```

四招叠加：**滑窗**留近端原文、**摘要**压远端历史、**检索(RAG)**召回长期知识、**裁剪**砍工具返回的噪声。目标不是塞满，而是让窗内**信噪比最高**。

**二、记忆模块 = 分层存储 + 三个动作**

分层（像 OS 分页：热数据在窗内，冷数据在外存），用统一的 **写入 / 召回 / 淘汰** 三动作驱动：

```
       写入 write              召回 recall
  对话/动作 ──┐            ┌── query → 向量检索 ──┐
            ▼            ▼                      ▼
  ┌─────────────────────────────────────────────┐
  │ 工作记忆  Buffer (窗内，近 N 轮)               │ 热
  │ 情景记忆  Vector/Log (历史轨迹，带时间戳)       │
  │ 语义记忆  VectorDB/KG (事实、偏好、文档)        │ 冷
  │ 程序记忆  Prompt/Skill (规则、工具用法)         │
  └─────────────────────────────────────────────┘
            ▲ 淘汰 evict：TTL / 容量上限 / 低分清理
```

- **写入**：判断「值不值得记」——抽取实体/事实/决策，去重，打 tag 与时间戳，分流到对应层；琐碎闲聊不写。
- **召回**：向量相似度 + metadata 过滤 + 时间衰减/重要度混排，必要时 rerank，只注入 top-k；命中小块可回溯父块补全。
- **淘汰**：TTL 过期、容量 LRU、重要度打分清理，避免无限膨胀与陈旧记忆污染召回。

一句话：**超长上下文靠「预算调度（裁+压+检索）」管当下，记忆模块靠「分层存储 + 写/召回/淘汰」管沉淀**，前者决定塞什么进窗、后者决定窗外留什么。

## 延伸 / 追问

**追问：写入和召回都用 LLM，延迟和成本会不会爆？怎么权衡？**

分层异步处理即可：**召回在主链路、写入挪到旁路**。召回必须实时，但可降本——先用廉价向量检索粗筛，只对 top 候选上 rerank，命中加缓存。写入不必同步阻塞回复：先把原始轨迹落盘，摘要/抽取/向量化交给**后台异步**批处理，用小模型甚至规则就能干大半（实体抽取、去重、打分）。再加两道闸：① 写入前判「是否值得记」过滤掉 90% 噪声，少写就少花；② 召回设 token 预算上限，top-k 取 3–5 而非几十。本质是**把贵操作移出关键路径、用小模型和缓存兜底**，让记忆系统的开销与任务价值匹配。

## 参考

- MemGPT / Letta，*Towards LLMs as Operating Systems*（分层记忆与上下文分页）：https://arxiv.org/abs/2310.08560
- LangGraph Docs，*Memory（short-term & long-term / summarization）*：https://langchain-ai.github.io/langgraph/concepts/memory/
- Park et al., *Generative Agents: Interactive Simulacra of Human Behavior*（记忆写入/检索/重要度评分）：https://arxiv.org/abs/2304.03442
