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

MCP 未来要支持流式输出、双向通信和有状态会话，该怎么扩展？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-08-06

**核心判断：** 三项不必另起炉灶。MCP 地基是 **JSON-RPC 2.0 + 可插拔 transport**，JSON-RPC 天生双向、原生支持通知（notification）。沿**升级传输层、补齐消息语义、能力协商守兼容**三条线增量即可。

**① 流式输出（streaming）**
现状 `tools/call` 一问一答，长任务只能等整包。做法：**分块通知**——server 用带 `requestId` 的 notification 持续推 partial chunk，client 按序拼装，末尾发 `done`；传输走 SSE / Streamable HTTP 而非阻塞。必配**取消**：client 发 `notifications/cancelled(requestId)`，server 立即停产、释放资源。

**② 双向通信（bidirectional）**
JSON-RPC 本就允许两端互发请求，MCP 已有 server→client 的 sampling / elicitation。要真双工，用**长连接 transport（WebSocket / 长 SSE）**替代无状态 HTTP，让 server 执行中途回调 client（授权、补输入、采样），用 `requestId` 关联并交错消息。

**③ 有状态会话（stateful session）**
在 `initialize` 协商出 **session id**，之后每次调用携带；server 维护 per-session 上下文（鉴权、工作目录、句柄、记忆），补**生命周期** create → resume → expire，并支持断线后按 `last-event-id` **重放**漏收事件。

```
Client ──initialize(capabilities, session_id)──► Server
   │◄────── 能力协商: streaming? stateful? ────────
   │──tools/call(id=7)──►│ 建立会话上下文
   │◄─chunk notif(id=7)──│ ┐
   │◄─chunk notif(id=7)──│ ├ 流式增量
   │◄─server req: 要授权?─│ │ 双向回调
   │──approve───────────►│ │
   │◄──── result(id=7) ──│ ┘ done
   │──cancelled(id=7)───►│   随时中断
```

**权限与兼容性（收口）：** ① 回调能力（sampling / 授权）要**逐会话协商 + 用户审批**，防 server 反向滥用 client 权限；② 新特性都在 `initialize` capabilities 里声明，老端不识别即**降级**为单次缓冲响应——做成「可选 capability」而非破坏性变更，才能前后向兼容。

## 延伸 / 追问

**追问：有状态会话会不会破坏 MCP server 的水平扩展？**

会。一旦 server 持有 per-session 内存态，就不能在无状态实例间随意做负载均衡。解法：把会话态**外置到共享存储**（Redis / DB），实例只做无状态计算，用 session id 作 key 取回上下文（sticky 路由只作优化、不作依赖）；对打开的文件 / 连接等不可序列化句柄，设 TTL + 亲和路由，并让 client 具备断线重建能力。本质是「有状态协议 + 无状态服务」——把状态收拢到可共享层，别绑死在进程内存里。

## 参考

- Model Context Protocol 官方文档（Transports / Lifecycle）：https://modelcontextprotocol.io/docs/concepts/transports
- MCP Specification（Streamable HTTP、session、cancellation）：https://spec.modelcontextprotocol.io/
- JSON-RPC 2.0 Specification（notification / 双向请求）：https://www.jsonrpc.org/specification
