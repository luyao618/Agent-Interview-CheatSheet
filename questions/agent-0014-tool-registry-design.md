---
id: agent-0014
title: 如何设计 Agent 的 tool registry
category: agent
tags: [agent, tool-registry, schema, discovery, scalability]
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

如何设计 Agent 的 tool registry（工具注册中心）？请说明工具如何注册与发现、schema 规范、工具过多时的分组/检索，以及版本与权限管理。

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

**一句话：** tool registry 是 Agent 与工具之间的「服务目录」——把散落的工具按统一 schema **注册**进来，运行期按需**发现/检索**出一个精简候选集喂给模型，并在中间统一管控**版本、权限与可观测**。它解决的核心矛盾是：工具会越来越多，但模型的上下文窗口与选择能力有限。

**整体结构：**

```
  工具实现 ──register──►┌──────────── Tool Registry ────────────┐
 (函数/API/MCP)         │  metadata: name/desc/schema/version    │
                        │  分组: namespace · tags · category     │
                        │  索引: 关键词 + 向量(embedding)        │
                        └───────────────┬───────────────────────┘
                                        │ retrieve(query, ctx)
   用户/任务 ──► Router/检索 ──► 候选工具子集(Top-K) ──► LLM 选择
                                        │
                          权限校验 ◄────┘──► 执行 ──► 结果回灌
```

**1. 注册与统一 schema（基础）。** 每个工具注册时登记一份标准化元数据：`name`（唯一、动词化）、`description`（做什么/何时用/何时别用，模型选型主要依据）、`parameters`（JSON Schema：类型、枚举、`required`）、以及治理字段 `version`、`namespace`、`tags`、`permission`、`owner`。注册方式可声明式（装饰器/配置）或动态接入（MCP server 自描述）。统一 schema 是后续发现、校验、文档生成的契约。

**2. 工具过多时的分组与检索（可扩展性关键）。** 几十上百个工具全塞进 prompt 既爆 token 又拉低选择准确率。分层收敛：
- **静态分组**：按 `namespace`/`category`/`tags` 组织，先按任务域圈定范围。
- **动态检索**：把工具 description 做 embedding，按当前任务语义检索 Top-K 候选，只把这几个的完整 schema 注入上下文（tool RAG）。
- **两段式路由**：先让模型/路由选「工具组」，再在组内选具体工具，降低单次候选规模。

**3. 版本管理。** 工具签名会演进，registry 用语义化版本与别名（`@latest`/`@stable`）管理；schema 破坏性变更升大版本，保留旧版本一段时间灰度，避免线上 Agent 因参数变更突然失败。

**4. 权限与安全。** registry 是统一管控点：按调用方/角色做工具可见性与执行 ACL（敏感工具不进候选集）；对副作用类工具（下单、删库）标注风险级别并挂人工确认；统一记录调用审计与限流。

**一句话收尾：** 好的 tool registry = **统一 schema（注册规范）+ 分组/语义检索（选得准、不爆窗口）+ 版本治理（演进不炸线上）+ 权限审计（安全可控）**。难点不在「存工具」，而在工具规模化后如何**只把对的少数工具喂给模型**。

## 延伸 / 追问

**追问：工具从几个涨到上百个，为什么不能直接把全部工具都塞进 prompt？怎么办？**

两个硬约束：① **上下文成本**——每个工具的 name+description+schema 都占 token，上百个工具的菜单可能吃掉几千 token，既贵又挤占任务空间；② **选择准确率**——候选越多、描述越相近，模型越容易选错或幻觉出不存在的工具，长列表中部还有「lost in the middle」效应。解法是**检索式收敛**：离线把工具 description 向量化建索引，运行期按任务语义检索出 Top-K（如 5~10 个）相关工具，只注入这几个的完整 schema；规模再大就加「先选组、再选工具」的两段式路由，并用 namespace/权限提前裁掉不可见工具。本质是把「让模型从全集里挑」变成「先用检索缩小到小候选集，模型只做最后一跳选择」。

## 参考

- Anthropic Docs，*Model Context Protocol (MCP)*：https://modelcontextprotocol.io/
- OpenAI Docs，*Function calling*：https://platform.openai.com/docs/guides/function-calling
- Liu et al., *Lost in the Middle: How Language Models Use Long Contexts*, 2023：https://arxiv.org/abs/2307.03172
