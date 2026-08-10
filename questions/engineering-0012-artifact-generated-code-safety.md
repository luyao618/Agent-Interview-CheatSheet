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
updated: 2026-08-10
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-08-10
    updated: 2026-08-10
---

## 问题

Artifact 模式下，Agent 会生成 SQL / HTML / JS / 可视化代码，直接交给浏览器渲染或数据库执行。这类代码一旦落地执行，就可能带来破坏性操作（DROP/DELETE 表）、XSS、数据泄露（跨租户读、外传）和资源滥用（全表扫描、死循环）。安全边界该怎么设计？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 回答 2026-08-10

**一句话原则：不要相信 Agent 生成的代码，把执行面当成攻击者控制的输入。** 约束必须落在运行时/宿主的强制层，而不是 prompt 里的"请不要 DROP 表"。Artifact 有两条执行面——浏览器渲染 HTML/JS/可视化、数据库跑 SQL——威胁与护栏各不相同。

```
        Agent 生成 artifact 代码（不可信）
                    │
        ┌───────────▼───────────┐
        │   宿主强制层 / Policy    │ ← 约束在这里，不在 prompt
        └─────┬────────────┬─────┘
              │            │
     HTML/JS/可视化        SQL
       （浏览器）        （数据库）
              │            │
  沙箱 iframe+独立域   只读副本+只读角色
  +CSP 收口出站       +AST 白名单(仅 SELECT)
  +postMessage 单通道 +租户/RLS/列脱敏
  +超时销毁+资源限额  +timeout/LIMIT/行数上限
              │            │
       防 XSS/外传    防破坏/越权/资源滥用
```

**浏览器面（HTML / JS / 可视化）——防 XSS 与数据外传：**

1. **独立源隔离。** artifact 一律在**沙箱 iframe** 渲染：`sandbox="allow-scripts"` 但**不给 allow-same-origin**，并托管在**独立沙箱域名**（非主站 origin）。这样脚本读不到主站 DOM、cookie、localStorage 与 token，即便被诱导也偷不走会话。
2. **CSP 收口出站。** `default-src 'none'`，只放必要的 `connect-src / img-src` 白名单，掐断 `fetch` 到攻击者域名的外传通道；禁 top-navigation、禁向外站提交 form。
3. **单通道通信。** 父子只走 `postMessage`，父窗口对消息做 schema 校验，绝不 `eval` / `innerHTML` 直插子窗口内容。
4. **资源限额。** 通用 HTML/DOM 渲染仍在 **sandbox iframe / 独立进程**里（Worker 摸不到 DOM，不能渲染 HTML）；只把 **CPU-heavy / 不可信计算**丢进 **Web Worker**（Canvas 场景可选 OffscreenCanvas）。统一加**超时销毁 iframe/worker** + 消息与内存兜底，长跑 / 死循环 / 挖矿直接 kill。

**数据库面（SQL）——防破坏性操作与越权读：**

1. **只读身份。** 连**只读副本**、用**只读角色**（DB 层 `REVOKE` 掉 INSERT/UPDATE/DELETE/DDL），靠权限而非语义判断兜底。
2. **语句白名单。** SQL parser 解析 AST，只放行单条 `SELECT`，拒绝多语句、`DROP/DELETE/TRUNCATE`、`;` 拼接与注释绕过。
3. **租户与列级隔离。** 强制注入 `WHERE tenant_id = ?` / 行级安全（RLS），PII 列脱敏，杜绝跨租户 `SELECT *`。
4. **成本护栏。** `statement_timeout` + 强制 `LIMIT` + 返回行数上限，防全表扫描 / 笛卡尔积拖垮库。

**两面通用：** deny-by-default 能力最小化 + 出口 DLP（敏感数据禁出网/禁返回）+ 全程审计留痕。核心：**把"别干坏事"从模型的自觉，变成执行面强制的边界。**

## 延伸 / 追问

**追问：用户可能保存并分享 artifact，或 Agent 把被 prompt injection 污染的 HTML/SQL 当 artifact 执行，运行时沙箱之外还该防什么？**

① **存储型 XSS 视角**：artifact 是"可保存/分享的持久内容"，等同 UGC——渲染永远走沙箱 iframe，绝不直插主站；分享链接走独立域名，拿不到主站 session。② **可信边界**：注入常来自 RAG 网页、上一步工具结果等不可信数据，它们能污染生成的 SQL/JS，但**不能**升级权限——能力授予的决策权在 policy 层，不在被污染的模型自述。③ **出口兜底**：即便 SQL 被诱导写成越权查询，只读角色 + RLS + 行数上限让它读不到别人的数据、也拖不垮库；即便 JS 想外传，CSP `connect-src` 白名单让它连不出去。④ **人在环**：写库、连外部、返回大量敏感行等高风险动作显式审批、留痕、异常告警。核心：假设模型会被操纵，多层兜底，而非指望它永远干净。

## 参考

- OWASP, *Top 10 for LLM Applications*（LLM01 Prompt Injection / LLM02 Insecure Output Handling）：https://owasp.org/www-project-top-10-for-large-language-model-applications/
- MDN, *`<iframe>` sandbox 属性*：https://developer.mozilla.org/en-US/docs/Web/HTML/Element/iframe#sandbox
- MDN, *Content Security Policy (CSP)*：https://developer.mozilla.org/en-US/docs/Web/HTTP/CSP
- PostgreSQL, *Row Security Policies*：https://www.postgresql.org/docs/current/ddl-rowsecurity.html
