---
id: agent-0041
title: 如何为 Agent 工具调用设计动态风险评估，而不是只按工具名分级
category: agent
tags: [tool-use, guardrails, risk-assessment, authorization, human-in-the-loop]
difficulty: hard
role: engineer
contributor: 佚名
source: 《深入理解 AI Agent：设计原理与工程实践》第 1、4 章
status: published
updated: 2026-08-05
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-08-05
    updated: 2026-08-05
---

## 问题

如何为 Agent 工具调用设计动态风险评估，而不是只按工具名分级？同一个工具在不同参数、对象、权限、环境下风险差异很大，怎样做参数级的风险分类、审批、dry-run、回滚与审计？

## 答案 · Claude-Opus-4.8

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 回答 2026-08-05

**为什么工具名分级不够：** 风险的载体是**这一次具体调用**，而不是工具类别。`db.execute("SELECT …")` 与 `db.execute("DROP TABLE users")` 同名不同命；`delete(path=/tmp/x)` 与 `delete(path=/)` 天差地别。把 `db.execute` 整体标成「高危」要么误杀只读查询、逼人反复审批（审批疲劳），要么为放行查询而降级、给删库开了后门。**风险 = f(动作, 对象, 范围, 环境, 可逆性)**，只有把参数纳入才能算准。

**核心做法：把风险变成一次调用级的打分函数。**

```
tool_call(name, args, ctx)
   │
   ▼ 解析出风险因子（不看工具名，看这次调用）
   ├─ 动作类型：读 / 写 / 删 / 外发 / 转账（副作用与可逆性）
   ├─ 对象敏感度：生产 vs 测试、PII、金额大小、path 是否命中根/通配
   ├─ 影响范围：命中 1 行 vs 全表、单文件 vs 递归目录
   ├─ 环境与权限：prod/staging、调用者授权、数据是否来自不可信来源
   └─ 可逆性：有无备份 / 事务 / 回滚点
   ▼ 打分 score = Σ w_i·factor_i  →  分档
   ├─ low    → 直接放行
   ├─ medium → 先 dry-run + 二次校验
   └─ high   → human-in-the-loop 审批，拒则中止
```

**四个落地组件：**

1. **参数级分类器。** 用规则/policy（OPA、JSON-Schema 断言、正则/AST 解析 SQL 与路径）从 `args` 抽因子；规则覆盖不了的模糊场景再交 LLM 打辅助分。规则优先，快、可解释、可测试。

2. **dry-run 预演。** 高危动作先「只算不改」估影响面：SQL 优先用**不执行语句**的 `EXPLAIN`（非 `EXPLAIN ANALYZE`）、同谓词 `SELECT COUNT(*)` 或数据库原生 preview；文件删除先列清单、转账先返回预览。切忌把「执行 DML 再 rollback」当成无副作用——`EXPLAIN ANALYZE` 会真正执行，事务回滚也消不掉 sequence 自增、trigger、外部调用等非事务副作用，还可能持锁。把预估影响回给评分与审批，让「删 3 行」和「删 30 万行」走不同路径。

3. **回滚与恢复设计。** 写操作包在事务里，或先做快照/软删除（标记而非物理删），保留 undo 令牌与 TTL。不可逆的外部副作用（转账、发邮件）无法真正回滚：用**前置审批降低发生概率**，再叠加 idempotency key、额度/目标 allowlist、延迟提交（可撤回窗口），以及退款/撤回等 compensating action 与对账 reconciliation 兜底——审批不等于回滚，也不能作为唯一恢复手段。

4. **结构化审计。** 每次留痕：调用方、工具、参数、算出的 score 与命中因子、判定（放行/审批/拒）、dry-run 结果、执行结果。既供事后追溯与合规，也回流做**阈值调优**（漏放行→加权重，误拦→降权重）与异常检测（短时高频删除→熔断）。

**一句话：** 别问「这是什么工具」，要问「这一次要对谁、做多大、可不可逆、能不能撤」——**按调用打分、按分档设闸、用 dry-run 估影响、用回滚兜底、用审计闭环**，才能既不误杀只读、又拦住删库。

## 延伸 / 追问

**追问：动态评分怎么防「越权」与「审批疲劳」两头失衡？**

两个失衡同源于阈值与因子没校准。防越权：评分层与执行层**分离**——评分再低，删库/转账等出口动作仍由代码层的权限闸兜底，模型骗得过分类器也绕不过 RBAC 与沙箱；对来自 RAG/网页/上一步工具结果的参数额外加权，堵间接注入提权。治疗审批疲劳：把「工具级审批」下沉为「风险级审批」，只有真正越线的调用才打断人；同类调用可**一次授权、范围内批量放行**，但授权必须限定 scope（action / object / environment / max impact）并带 TTL，且每次调用仍重新评分——避免「staging 写操作免审」滑成过宽授权。用审计数据持续回归阈值，把噪声审批压下去。核心是让「拦截率」既覆盖真实高危、又不淹没在低风险噪声里。

## 参考

- Anthropic Engineering，*Building Effective Agents*：https://www.anthropic.com/engineering/building-effective-agents
- OWASP，*Top 10 for LLM Applications*（LLM01 Prompt Injection / Excessive Agency）：https://owasp.org/www-project-top-10-for-large-language-model-applications/
- Open Policy Agent，*Policy-based control (Rego)*：https://www.openpolicyagent.org/docs/latest/
