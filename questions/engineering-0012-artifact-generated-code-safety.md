---
id: engineering-0012
title: Artifact 模式下让浏览器或数据库执行 Agent 生成代码，安全边界怎么设计？
category: engineering
tags: [artifact, generated-code, sql, browser-security, sandbox]
difficulty: hard
role: engineer
contributor: 佚名
source: 《深入理解 AI Agent：设计原理与工程实践》第 5 章
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

Artifact 模式下，Agent 生成 SQL 交给数据库执行、生成 HTML/JS 交给浏览器渲染、生成可视化代码在页面跑。这些「生成即执行」的产物如何设定安全边界，防止破坏性操作、XSS、数据泄露和资源滥用？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 回答 2026-08-06

**核心前提：把 Agent 生成的代码当「不可信输入」，而不是「我们自己写的代码」。** 它可能被 prompt injection 操纵、也可能自身有缺陷。所以安全不是「相信模型不作恶」，而是**用执行环境的机制强制约束**——按 artifact 类型分别设边界，且默认最小权限。

```
Agent 生成 artifact
   │  按类型走不同的执行边界
   ├─ SQL      → 只读副本/受限账号 + 参数化 + 语句白名单 + LIMIT/超时
   ├─ HTML/JS  → 沙箱 iframe(sandbox) + CSP + 无同源/无凭证 + 输出转义
   ├─ 可视化   → 只喂数据不喂能力：库白名单，禁 eval/网络/DOM 逃逸
   └─ 通用     → 资源限额 + 审计 + 人工确认高风险
```

**按类型的边界：**

1. **SQL（防破坏性 + 防泄露）。** 用**独立只读账号连只读副本**跑分析类查询，从权限层面根除 `DROP/DELETE/UPDATE`；写操作单独走审批。语句层：**参数化**、`SELECT` 白名单、强制 `LIMIT` + 查询超时防全表扫描/资源滥用，行级权限（RLS）限制可见数据防越权读。别把用户/agent 文本直接拼进 SQL。

2. **HTML/JS（防 XSS + 防泄露）。** 在**沙箱 `iframe`**（`sandbox` 属性，去掉 `allow-same-origin`）里渲染，配 **CSP**（禁内联/外联脚本、限 `connect-src` 防数据外传）；渲染环境**不带用户 cookie/凭证、与主站隔离源**，即使注入了恶意 JS 也偷不到 session、发不出请求。对插值内容做**上下文相关转义**。

3. **可视化代码（只给数据，不给能力）。** 用受限运行时：库/API 白名单，禁 `eval`、禁 `fetch`/网络、禁访问外层 DOM 与全局对象；代码只被允许「拿传入的数据画图」，够不到能力面。

4. **通用护栏。** CPU/内存/时长/输出大小限额（防死循环、挖矿、巨量返回）；全程审计「谁生成了什么、执行了什么、访问了什么」；不可逆/高权限动作前移为**执行前人工确认**。

**两条贯穿原则：**
- **在执行边界强制，而非在 prompt 里叮嘱。** 「请不要 DROP 表」是软约束，只读账号才是硬约束——模型被注入也绕不过权限与沙箱。
- **默认拒绝、按需授权。** 起点是最小权限沙箱，需要更多能力（写库、联网）走显式审批与收窄 scope，而不是先给全权限再补漏。

**一句话：** artifact 安全靠**「把生成代码当不可信 + 按类型用执行环境的机制硬性隔离」**——SQL 走只读受限账号 + 参数化 + 白名单，HTML/JS 走沙箱 iframe + CSP + 无凭证隔离源，可视化只喂数据不喂能力，再叠加资源限额、审计与高风险人工确认。

## 延伸 / 追问

**追问：这些 artifact 常要读真实业务数据才有用，「隔离」和「能访问数据」怎么两全？**

关键是**分离「计算隔离」与「数据授权」**：沙箱管代码能做什么，数据层管它能看到什么，两者独立收窄。做法：① **数据经受控通道流入，而非沙箱自己去取**——由后端按调用者身份查好、脱敏后把结果集喂进沙箱，沙箱本身**无 DB 连接、无网络**，从根上断掉「拿到数据后外传」。② **以调用者身份授权，不以 agent 身份**——查询走用户的权限（RLS/列级权限），agent 不能读用户本无权看的数据；避免 agent 变成越权提数的通道。③ **敏感数据默认脱敏/最小化**——只投喂本次可视化/分析必需的字段与行，PII 打码或聚合，即便渲染侧被 XSS 也没有原始敏感值可偷。④ **出口管控兜底**——沙箱 CSP 限 `connect-src`、后端对返回体量与目的地做 DLP。这样「能用真实数据出图」和「数据出不去、越不了权」并行不悖：数据进得来是因为后端授权并脱敏，出不去是因为沙箱无网 + CSP + 出口 DLP。

## 参考

- OWASP, *Cross Site Scripting Prevention Cheat Sheet*：https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html
- OWASP, *SQL Injection Prevention Cheat Sheet*：https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
- MDN, *The iframe sandbox attribute* 与 *Content Security Policy (CSP)*：https://developer.mozilla.org/en-US/docs/Web/HTML/Element/iframe#sandbox
