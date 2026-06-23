---
id: agent-0024
title: MCP 和 Function Calling 的区别与优势是什么
category: agent
tags: [agent, mcp, function-calling, protocol, interoperability]
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

MCP 和 Function Calling 的区别与优势是什么？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-23

**先纠正一个常见误区：两者不是竞品，而是不同层次。** Function Calling 是**模型层能力**——模型能产出结构化的「调哪个工具、传什么参数」；MCP（Model Context Protocol）是**集成层协议**——规定工具/数据源如何以标准方式暴露给应用，让一份 Server 被任意 MCP 客户端复用。实际系统里二者常**叠加**：MCP Server 把能力以标准接口提供给宿主，宿主再转成 Function Calling 的 tools schema 喂给模型。

**层次定位：**

```
   ┌──────────────── 模型 LLM ────────────────┐
   │  Function Calling: 决策"调哪个+传什么参数"  │  ← 模型层能力
   └──────────────────┬───────────────────────┘
                      │ tool_call(name, args)
   ┌──────────────────▼───────────────────────┐
   │  宿主应用 / MCP Client (适配、鉴权、编排)    │  ← 集成层
   └───┬──────────────┬──────────────┬────────┘
       │ MCP 协议(标准化: tools/resources/prompts)
   ┌───▼───┐     ┌────▼────┐    ┌────▼────┐
   │File MCP│     │ DB MCP  │    │ API MCP │   ← 任意应用可复用的 Server
   └───────┘     └─────────┘    └─────────┘
```

**核心区别：**

| 维度 | Function Calling | MCP |
| --- | --- | --- |
| 层次 | 模型推理能力 | 应用集成协议 |
| 解决什么 | 模型"调得对" | 工具"接得标准、能复用" |
| 复用性 | 每个 App 各写各的 schema/胶水 | 一个 Server 跨 App 通用 |
| 范围 | 单次调用的 name+args | tools/resources/prompts + 连接生命周期 |
| 厂商 | 各家 schema 略有差异 | 统一开放协议 |

**Function Calling 的优势：** 直接、轻量，模型原生支持；少量工具、单一应用时无需引入额外协议，定义 schema 即可用。

**MCP 的优势：** ① **标准化复用**——一次实现 Server，所有兼容客户端（Claude Desktop、IDE、自研 Agent）都能接，告别 N×M 的胶水代码；② **解耦**——工具方与模型方各自演进，新增数据源不改模型侧；③ **能力更全**——不止函数调用，还规范了资源读取（resources）、提示模板（prompts）与传输/鉴权，适合构建可插拔的工具生态。

**一句话：** Function Calling 让模型**会调用**工具；MCP 让工具**被标准化地、可复用地接入**。前者是「调用动作」，后者是「接入规范」——小场景用 Function Calling 足够，要做跨应用、可插拔、长期维护的工具生态就上 MCP，且二者协同而非互斥。

## 延伸 / 追问

**追问：什么时候没必要上 MCP，直接 Function Calling 就够？**

判断点是**复用与维护成本**。当工具只服务单一应用、数量少、变更不频繁，且不需要被其它客户端共享时，直接写 Function Calling 的 tools schema 最省事——引入 MCP 反而多一层 Server/传输/版本协商的开销。反之，当出现这些信号就该上 MCP：同一批工具要被多个 Agent/产品复用（避免 N×M 胶水）、工具由独立团队维护需与模型侧解耦、需要标准化的资源访问与鉴权、或想接入现成的 MCP 生态（社区 Server）。经验法则：**先用 Function Calling 把单点跑通，当"同一个工具被第二个应用要用"时，就是迁移到 MCP 的拐点。**

## 参考

- Anthropic，*Introducing the Model Context Protocol*：https://www.anthropic.com/news/model-context-protocol
- Model Context Protocol 官方文档：https://modelcontextprotocol.io/
- OpenAI Docs，*Function calling*：https://platform.openai.com/docs/guides/function-calling
