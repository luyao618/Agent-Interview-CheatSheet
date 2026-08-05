---
id: agent-0042
title: Agent 需要人工接管但用户不在线或指令模糊时，系统该怎么设计
category: agent
tags: [human-in-the-loop, handoff, autonomy, fallback, safety]
difficulty: medium
role: engineer
contributor: 佚名
source: 《深入理解 AI Agent：设计原理与工程实践》第 1 章
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

当 Agent 判断需要人工接管（信息不足、遇到高风险动作、或指令模糊无法决策），但用户此刻不在线、或迟迟不回复时，系统该怎么设计？如何优雅地移交控制、决定等待还是降级、避免傻等或乱来？

## 答案 · Claude-Opus-4.8

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 回答 2026-08-05

**核心矛盾：** 触发 handoff 是因为「继续做有风险」，但接管方缺席又让「一直等」变成另一种风险（任务过期、资源占用、上下游阻塞）。所以设计目标不是「等到人」，而是**在人缺席的窗口里，把系统停在一个安全、可恢复、信息完整的状态**，等人回来能一键续跑。

**决策的第一步：给「待人动作」按可逆性 + 时效性分档，而不是一律阻塞。**

```
需要人工接管
   │
   ▼ 这一步是什么性质？
   ├─ 不可逆 / 高风险（转账、删库、外发）
   │     → 硬冻结：绝不代做，挂起等审批，超时也只能放弃
   ├─ 可逆 / 低风险且能推进（拉数据、起草稿、跑只读预演）
   │     → 降级继续：做安全子集，产出「待确认」草稿，不落终态
   └─ 纯信息缺口（指令模糊、缺参数）
         → 先自救：查上下文/默认值/历史偏好，仍不定才升级
```

落到四种可切换策略：**等待**（park：挂起到「等待人工」态，持久化现场后多渠道异步通知，而非占线程 busy-wait）、**降级继续**（safe subset：只做可逆低风险且无害的部分——预取数据、起草稿、dry-run 估影响，把待拍板动作留在门口）、**冻结**（freeze：高风险无法推进时停在 checkpoint、释放资源）、**兜底默认**（safe default：最终超时仍无人，走**预先约定**的默认——低危放行、高危放弃并回滚，而非「先做了再说」）。

**超时机制是关键，且要分层。**

```
t0 触发 handoff ─► 持久化现场 + 首次通知
   │
   ├─ 软超时 T1：升级通知（换渠道 / @上级 / 提醒）
   ├─ 硬超时 T2：执行预设安全默认（放行低危 / 放弃高危并回滚）
   └─ 全程：任务状态 = 「等待人工」，可被外部查询与手动续跑
```

用**绝对截止时间 + 幂等续跑**，而非 sleep 死等；超时到点由调度器（而非 Agent 自旋）触发下一档动作。

**指令模糊要先自救再升级：** 缺参数先查上下文、历史偏好、合理默认；能列「候选选项 + 各自后果」就把选择题而非问答题抛给人，降低人回复成本。只有「二选一都有实质代价且无默认」时才真正阻塞。

**信息收集 + 恢复执行：** handoff 时打包「为什么停、缺什么、我已做了什么、建议怎么办」一起推给人，人一句话即可续；用 checkpoint + 幂等保证「解冻后从断点继续，不重复已完成的副作用」。

**一句话：** 别设计成「傻等一个人」——**按可逆性决定能不能代劳，用分层超时决定等多久，用持久化现场 + 安全默认决定人不来时怎么收场**，让每一次 handoff 都停在「安全、可查询、可一键续跑」的状态。

## 延伸 / 追问

**追问：多个任务同时卡在「等待人工」，怎么避免通知风暴又不漏掉紧急的？**

按**风险 × 时效**给待办排序并聚合，而不是逐条 @人。做法：① 归并同类请求，一条摘要通知列出 N 个待确认项，支持批量放行/驳回；② 按 deadline 紧迫度和不可逆性排优先级，高危临期的单独高优推送、低危的进批处理队列；③ 通知带「一键续跑 / 一键放弃」的结构化操作入口，降低人处理成本；④ 每个待办仍各自计时、各自走分层超时，互不阻塞——避免一个人的缺席拖垮整条流水线。核心是把「N 次打断」压成「一次分诊」，让人只在真正越线时被叫醒。

## 参考

- Anthropic Engineering，*Building Effective Agents*（human-in-the-loop 与可控性）：https://www.anthropic.com/engineering/building-effective-agents
- LangGraph Docs，*Human-in-the-loop*（interrupt / resume 与断点续跑）：https://langchain-ai.github.io/langgraph/concepts/human_in_the_loop/
- OWASP，*Top 10 for LLM Applications*（LLM08 Excessive Agency）：https://owasp.org/www-project-top-10-for-large-language-model-applications/
