---
id: agent-0030
title: MCP、A2A、普通 Function Calling 三者有什么本质区别？工程里怎么选？
category: agent
tags: [agent, mcp, a2a, function-calling, protocol, interoperability]
difficulty: medium
role: engineer
contributor: 佚名
source: 未知
status: published
updated: 2026-06-29
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-06-29
    updated: 2026-06-29
---

## 问题

MCP、A2A、普通 Function Calling 三者有什么本质区别？工程里怎么选？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-29

**一句话定位：三者不是竞品，而是不同层次。** Function Calling 是**模型层能力**（模型决定"调哪个工具、传什么参数"）；MCP 是**Agent↔工具/数据的集成层协议**（标准化地把工具暴露给应用并复用）；A2A（Agent2Agent）是**Agent↔Agent 的协作层协议**（让独立自治的 Agent 互相发现、委派任务、交换结果）。一句话区分调用对象：FC 调的是**函数**，MCP 接的是**工具/资源**，A2A 对接的是**另一个 Agent**。

**分层关系：**

```
        ┌──────── Agent A ────────┐        A2A 协议        ┌──────── Agent B ────────┐
        │  LLM                    │  ←─ 任务委派/结果回传 ─→ │  LLM                    │
        │   │ Function Calling    │   (发现/协商/异步)      │   │ Function Calling    │
        │   ▼ tool_call(name,args)│                        │   ▼                     │
        │  MCP Client             │                        │  MCP Client             │
        └───┬─────────────────────┘                        └─────────────────────────┘
            │ MCP 协议 (tools/resources/prompts + 鉴权/生命周期)
     ┌──────▼──────┐   ┌─────────┐   ┌─────────┐
     │  File MCP   │   │ DB MCP  │   │ API MCP │   ← 任意 Agent 可复用的 Server
     └─────────────┘   └─────────┘   └─────────┘
```

**核心区别对比：**

| 维度 | Function Calling | MCP | A2A |
| --- | --- | --- | --- |
| 层次 | 模型推理能力 | 工具集成协议 | Agent 协作协议 |
| 连接对象 | 进程内函数 | 工具 / 数据源 Server | 另一个自治 Agent |
| 解决什么 | 模型"调得对" | 工具"接得标准、能复用" | 多 Agent"分得清、协作得动" |
| 交互形态 | 单次同步 name+args | 客户端↔Server，含资源/提示/会话 | Agent 间消息，常异步/长任务 |
| 自治性 | 工具无自治，纯执行 | Server 无自治，被动响应 | 对端有自治：自己规划/调工具 |
| 典型实现 | OpenAI/Claude tools schema | Model Context Protocol | Google A2A（Agent Card 发现） |

**关键本质：自治性递增。** FC 末端是哑函数；MCP 末端是被动 Server；A2A 对端是会自己思考、能拒绝或反问的 Agent。所以 A2A 要解决 FC/MCP 不需要的问题：能力发现（Agent Card）、任务生命周期（submitted→working→completed）、长时异步与流式更新、跨组织信任。

**工程选型：**

- **单应用、少量工具** → 只用 **Function Calling**，定义 schema 即可，别过度设计。
- **工具要跨多个 Agent/产品复用，或由独立团队维护** → 上 **MCP**，避免 N×M 胶水，工具方与模型方解耦演进。
- **要把一个独立 Agent（可能跨团队/跨厂商、自带工具与上下文）作为协作方编排** → 用 **A2A**，按能力委派子任务、聚合结果。

**经验法则（自底向上叠加）：** 先 Function Calling 把单点跑通 → 工具要被第二个应用复用时迁到 MCP → 当被调方不再是"工具"而是"另一个会自己干活的 Agent"时引入 A2A。三者常**同时在线**：一个 Agent 内部用 FC 决策、用 MCP 接工具，对外用 A2A 与兄弟 Agent 协作。

## 延伸 / 追问

**追问：A2A 和 MCP 会互相替代吗？怎么判断该用哪个？**

不会，二者正交、常配套。判断点是**被调对象有没有自治性**：如果对端只是"执行你给的指令"的工具/数据源（无自己的规划与决策），用 MCP；如果对端是一个**能自己拆解任务、调自己的工具、可能反问或拒绝**的 Agent，用 A2A。典型组合：主 Agent 通过 A2A 把"做行业调研"委派给研究 Agent，研究 Agent 内部再用 MCP 连搜索/数据库 Server、用 Function Calling 驱动模型决策。一个直觉：MCP 是"我接一个工具来用"，A2A 是"我请一个同事来协作"——前者要的是标准接口与复用，后者要的是发现、信任与长任务协商。

## 参考

- Anthropic，*Introducing the Model Context Protocol*：https://www.anthropic.com/news/model-context-protocol
- Model Context Protocol 官方文档：https://modelcontextprotocol.io/
- Google，*Announcing the Agent2Agent (A2A) Protocol*：https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/
- OpenAI Docs，*Function calling*：https://platform.openai.com/docs/guides/function-calling
