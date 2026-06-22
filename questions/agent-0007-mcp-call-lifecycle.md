---
id: agent-0007
title: LLM 用 MCP 调用内部系统接口的完整生命周期，大模型能直接调接口吗
category: agent
tags: [agent, mcp, tool-use, lifecycle, protocol]
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

LLM 决定用 MCP（Model Context Protocol）调用内部系统接口时，整个调用生命周期是什么？大模型能直接调接口吗？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

**先回答第二问：不能。** 大模型本身只是一个「文本进、文本出」的推理引擎，没有网络、文件或进程能力。它「调接口」其实是**输出一个结构化的调用意图**（要调哪个 tool、传什么参数），真正的执行由 **Host/Client** 这一侧的代码代为完成。MCP 正是把这套「模型表达意图 → 宿主代理执行」标准化的协议。

**三个角色：**
- **Host / Client**：Agent 应用（如 IDE、聊天端），内嵌 LLM，负责连接各 MCP Server、把工具清单喂给模型、并代模型执行调用。
- **MCP Server**：内部系统接口的适配层，用 MCP 协议暴露 tools/resources，内部再去调真正的数据库 / 微服务 / API。
- **LLM**：只做决策，产出「调用哪个工具、参数是什么」。

**完整生命周期：**

```
 ① 发现        Client 连接 Server，list_tools 拉回
              工具清单(name/description/JSON Schema)
                       │  注入到模型上下文
                       ▼
 ② 模型选择    LLM 读 query + 工具清单，决策：
              要不要调? 调哪个? 参数填什么? → 输出 tool_call
                       │  (仅是意图，未执行)
                       ▼
 ③ Client 发起 Client 校验/审批参数，按 MCP 协议(JSON-RPC)
              向对应 Server 发 tools/call 请求
                       │
                       ▼
 ④ Server 执行 Server 调真正的内部接口(DB/微服务/HTTP)，
              拿到结果，按协议封装返回 Client
                       │
                       ▼
 ⑤ 结果回灌    Client 把结果作为 tool result 拼回上下文，
              再次调用 LLM → 模型据此继续推理
                       │
            ┌──────────┴──────────┐
         需再调工具(回②循环)      生成最终答复 → 结束
```

要点：**②是模型唯一参与的环节，且只产出意图；③④的真实 I/O 全在宿主侧。** 这条边界正是 MCP 的安全价值——参数校验、权限/审批、超时与错误处理、审计日志都收口在 Client/Server，模型无法绕过宿主直接触达内网接口。多步任务则是②→⑤的循环，直到模型判定无需再调工具。

## 延伸 / 追问

**追问：MCP 和普通 Function Calling 的关系？**

Function Calling 是「模型按 schema 产出结构化调用意图」的**能力**，回答了「模型怎么表达要调工具」；MCP 是一套**协议与传输标准**（基于 JSON-RPC，定义 tools/resources/prompts 的发现与调用），回答了「Client 与外部 Server 之间怎么标准化地连接、发现、调用」。二者是不同层次：MCP 的②本质上仍靠模型的 function calling 产出意图，但①的工具发现、③的跨进程调用、以及一个 Client 同时对接多个 Server 的能力，是 MCP 在 FC 之上补的「即插即用」标准化层——换言之，FC 解决表达，MCP 解决互联互通与复用。

## 参考

- Anthropic，*Introducing the Model Context Protocol*：https://www.anthropic.com/news/model-context-protocol
- Model Context Protocol 官方文档（架构 / 生命周期）：https://modelcontextprotocol.io/docs/concepts/architecture
- MCP Specification（JSON-RPC、tools/call）：https://spec.modelcontextprotocol.io/
