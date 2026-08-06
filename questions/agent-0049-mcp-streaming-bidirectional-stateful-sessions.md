---
id: agent-0049
title: MCP 未来要支持流式输出、双向通信和有状态会话，该怎么扩展？
category: agent
tags: [mcp, tools, streaming, stateful-session, protocol-design]
difficulty: hard
role: engineer
contributor: 佚名
source: 《深入理解 AI Agent：设计原理与工程实践》第 4 章
status: published
updated: 2026-08-06
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-08-06
    updated: 2026-08-06
---

## 问题

现有 MCP 以「一次请求 → 一次结果」的工具调用为主。要支持流式输出（长任务边跑边返回）、双向通信（服务端反过来问客户端 / 触发采样）、有状态会话（跨多次调用保持上下文），协议该怎么扩展？要处理哪些问题（取消、状态、权限、兼容性）？

## 答案 · Claude-Opus-4.8

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 回答 2026-08-06

**先厘清 MCP 的底子。** MCP 基于 **JSON-RPC 2.0**，传输可走 stdio 或 Streamable HTTP（含 SSE），本身已支持**双向**（server 可发起 `sampling`/`elicitation`）与**通知**。所以"扩展"多数不是从零发明，而是**在既有 request/response + notification + 能力协商上补齐语义**，且必须保持向后兼容。

```
Client ⇄ Server（JSON-RPC 双向）
  request ──► ◄── response（含 progressToken 关联）
        ◄── notifications/progress（流式分片，边跑边推）
        ◄── server→client：sampling / elicitation（反问）
  notifications/cancelled ──►（取消长任务）
  会话：Mcp-Session-Id 贯穿多次调用（有状态）
```

**四块怎么落地：**

1. **流式输出。** 用 **progress notification**（带 `progressToken`）把长任务的中间结果/进度分片推给客户端，最终仍以一个 response 收口。要点：分片要能按 token 关联到原请求、可乱序重组、明确"结束"标记；边界是 JSON-RPC 无内建背压，需约定分片大小/频率与丢弃策略。

2. **双向通信。** 复用 server→client 的 `sampling`（让服务端借客户端的模型推理）与 `elicitation`（向用户/客户端要缺失信息）。关键是**权限与信任**：server 反过来发起请求会放大攻击面（恶意 server 诱导采样/索要数据），必须客户端侧审批、按能力白名单、限制可请求范围。

3. **有状态会话。** Streamable HTTP 用 **`Mcp-Session-Id`** 标识会话，让多次调用共享上下文。工程上要处理：会话 TTL 与显式关闭、服务端重启后的**状态恢复/失效**、水平扩展下的**会话亲和或外部状态存储**、以及"有状态"带来的资源泄漏——无状态调用更好扩容，有状态是便利与运维成本的权衡。

4. **取消 / 中断。** 用 **`notifications/cancelled`** 携带原请求 id 让长任务可被叫停；服务端需真正中止副作用（而非只丢结果），并约定取消后的清理与幂等。

**贯穿三条工程原则：**

- **能力协商 + 版本化**：新特性一律走 `initialize` 的 capabilities 声明与 `protocolVersion`，双方按交集工作——这是**向后兼容**的根：老客户端不声明就退回一次性调用，不被新语义打断。
- **安全默认关**：流式/双向/有状态都扩大攻击面（注入、越权采样、会话劫持），默认最小权限、显式授权、审计。
- **可降级**：任何长连接/会话都要能优雅退化为无状态请求，网络中断可重连续跑（幂等 + 断点）。

**一句话：** 别另造协议——**在 JSON-RPC 双向 + 通知 + 能力协商之上，用 progress 做流式、sampling/elicitation 做双向、session-id 做有状态、cancelled 做中断**，并用能力协商 + 版本化守住兼容，用最小权限守住安全。

## 延伸 / 追问

**追问：有状态会话最诱人也最危险，什么时候值得引入，怎么控制它带来的复杂度？**

判据是**"跨调用的上下文是否昂贵到必须复用"**。值得引入的典型：一次建立代价高的连接/句柄（数据库事务、浏览器会话、已鉴权的长连接）、或需要在多步间累积的服务端状态（一个进行中的构建、一段交互流程）。不值得就别上——无状态调用天然易扩容、易重试、无泄漏，多数工具应保持无状态。控制复杂度的做法：① **状态外置**——把会话状态存到 Redis 等外部存储而非进程内存，让服务端可无状态水平扩展、可重启恢复；② **显式生命周期**——会话必须有创建、TTL、心跳续期、显式/超时关闭，杜绝悬挂会话吃资源；③ **失效可恢复**——server 重启或会话过期时返回明确错误码，客户端能重建会话并从断点续跑（依赖幂等）；④ **会话即权限边界**——绑定鉴权主体与最小 scope，防会话劫持横向越权。本质是把"有状态"当成一项有明确成本的能力按需启用，而非默认形态。

## 参考

- Model Context Protocol, *Specification*（JSON-RPC、transports、capabilities）：https://modelcontextprotocol.io/specification
- Model Context Protocol, *Streamable HTTP transport & Sessions*：https://modelcontextprotocol.io/docs/concepts/transports
- Anthropic Engineering, *Building Effective Agents*：https://www.anthropic.com/engineering/building-effective-agents
