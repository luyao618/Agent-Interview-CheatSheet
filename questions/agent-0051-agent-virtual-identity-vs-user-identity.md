---
id: agent-0051
title: Agent 对外办事时，应使用虚拟身份还是用户本人身份？
category: agent
tags: [identity, authorization, trust, privacy, external-actions]
difficulty: hard
role: both
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

Agent 对外办事（调用第三方系统、发邮件、下单、改配置等）时，应该使用一个独立的**虚拟身份**，还是直接用**用户本人身份**？从信任、权限、审计、可撤销授权与第三方接受度的角度分析，并说明如何按场景选型。

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-08-06

一句话结论：默认让 Agent 持有**自己的独立身份**，再通过**受限的委托授权（on-behalf-of）**代表用户办事；只有当第三方无法识别「代理」这一角色、且必须以用户名义时，才退回用户身份，并收窄到最小权限、可撤销、可审计。关键是把「是谁在做」（Agent 虚拟身份）和「代表谁、经谁授权」（用户委托）拆成两件事。

**三种身份模式**

1. **纯用户身份（impersonation）**：Agent 直接用用户凭证/会话。优点：第三方零改造、无缝复用既有权限。缺点：无法区分「人做的」还是「Agent 做的」，审计混淆；权限无法单独收窄，凭证一旦泄露即全量沦陷；难以精细撤销。
2. **纯虚拟身份（独立主体）**：Agent 是独立 principal，有自己的账户/凭证/权限域。优点：责任清晰、可独立授权与吊销、爆炸半径小。缺点：需第三方支持「服务账户/机器身份」，且要单独建权。
3. **委托身份（推荐）**：Agent 用自己身份，携带用户签发、限定 scope/时长/资源的委托令牌；行为记录为「Agent X 代表 User Y」。兼顾兼容性与可控性。

```
用户 ── 授权(scope, 有效期) ──► Agent(虚拟身份) ── 携委托令牌 ──► 第三方
  ▲                                    │
  └────────── 可随时撤销/审计 ◄─────────┘
   审计日志：actor=Agent, on_behalf_of=User, scope=...
```

**评估维度**

- **责任归属**：出事能否定位到「是人还是 Agent」。
- **最小权限**：能否只给这次任务所需 scope，而非用户全量权限。
- **可撤销性**：吊销 Agent 授权不应影响用户本人登录。
- **审计**：日志须同时留 actor 与 on_behalf_of。
- **隐私**：虚拟身份可避免把用户 PII 暴露给第三方。
- **第三方接受度**：对方是否认这套委托/机器身份。

**按场景选型**

- 高风险、需留痕可撤销（转账、发邮件、改配置）→ 委托身份 + 关键动作二次确认。
- 对方只认真人、低敏感（查公开信息）→ 可临时用用户身份，但仍收窄权限与时效。
- Agent 自有资源（它自己的存储/队列/沙箱）→ 纯虚拟身份，与用户完全解耦。

## 延伸 / 追问

**追问：委托授权具体用什么技术落地？**

主流是 OAuth 2.0 委托模型：用户对 Agent 做一次 consent，颁发限定 scope 的 access/refresh token；跨系统再调用时用 Token Exchange（RFC 8693）把「用户令牌」换成「Agent 代表用户、scope 更窄」的令牌，令牌里用 `act` / `may_act` claim 记录代理链。要点：短时效 + refresh、按资源给最小 scope、每个 Agent 独立 `client_id` 便于单独吊销与限流、审计日志同时记 `sub`（用户）与 actor（Agent）。企业内可叠加 mTLS / SPIFFE 给 Agent 一个机器身份，再用 OBO 换委托令牌。切忌把长期用户凭证直接塞给 Agent。

## 参考

- IETF，*OAuth 2.0 Token Exchange (RFC 8693)*（`act`/`may_act` 代理链 claim）：https://www.rfc-editor.org/rfc/rfc8693
- Microsoft，*Microsoft identity platform and OAuth 2.0 On-Behalf-Of flow*：https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-on-behalf-of-flow
- SPIFFE，*Turtles all the way down: Workload identity overview*：https://spiffe.io/docs/latest/spiffe-about/overview/
