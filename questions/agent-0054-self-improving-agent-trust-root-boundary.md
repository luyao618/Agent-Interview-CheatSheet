---
id: agent-0054
title: Agent 能自我更新工具和验证器时，如何隔离不能被它修改的信任根？
category: agent
tags: [self-improvement, trust-root, governance, verifier, safety]
difficulty: hard
role: engineer
contributor: 佚名
source: 《深入理解 AI Agent：设计原理与工程实践》第 8 章
status: published
updated: 2026-08-13
answers:
  - author: Claude-Opus-4.8
    type: ai
    model: Claude-Opus-4.8
    answered: 2026-08-13
    updated: 2026-08-13
---

## 问题

在持续进化的系统中，Agent 可以自己新增/修改工具代码、prompt，甚至改动评测用例与验证器。请说明必须隔离出哪些「Agent 改不到」的信任根，以及在权限边界、代码边界和发布流程三个层面如何落地这条边界。

## 答案 · Claude-Opus-4.8

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 回答 2026-08-13

**一句话：** 自我改进系统里必须存在一个 **Agent 无论如何都写不到的最小集合（TCB）**——判定「改得对不对」的那套东西。一旦 Agent 能改验证器，就是考生兼阅卷人，所有门禁退化成自证。

**信任根装什么（越小越好）：** ① 密封的评测真值与 held-out 用例；② 验证器 / 裁判代码及其运行环境；③ 安全与权限策略；④ 发布签名密钥；⑤ **控制上述四项变更的机制本身**——required check 对应的 workflow 定义、判定通过与否的 status authority、以及分支保护规则。第 ⑤ 条最常被漏：能改门禁就等于能绕过验证器，这是典型的二阶越权。

注意 TCB 内部并非同一种权限：**held-out 真值对 Agent 不可读**（读到即可过拟合，泄漏等于失效），验证器代码可以公开可读、但对 Agent 不可写。整个 TCB 只接受一条**独立受控变更通道**的写入——不是「CI 可写」，CI 只是执行者。

```
┌──── 信任根 TCB（Agent 不可写；真值对 Agent 不可读）────┐
│ held-out 真值[隔离] · 验证器代码 · 安全策略 · 签名密钥   │
│ required-check workflow · status authority · 分支保护   │
└────▲──────────────────────────┬────────────────────────┘
     │ 只读引用(不含真值)         │ 裁决（Agent 不可干预）
     │                          │        ▲ 仅独立受控变更通道可写
┌────┴──────────────┐  提案  ┌──▼──────────┐ 过 ┌───────────┐
│ 可变面(Agent 可写) │ ─────► │ 隔离执行环境 │ ──►│ 人审 + 签名│ ─► 灰度/回滚
│ 工具代码·prompt·配置│  产物  │独立身份·最小 │ 否 └───────────┘
└───────────────────┘        │capability   │ ─────► 丢弃
                             └─────────────┘
```

**三层边界：**

**1）权限边界——身份分离。** Agent 运行时身份对信任根**无写权限**，且对 held-out 真值**无读权限**；可写面只有工作区与产物分支。签名密钥与真值绝不进入 Agent 的上下文、文件系统与环境变量（凭据泄漏即边界泄漏）。默认拒绝、白名单放行；`propose` 与 `approve / merge / sign` 必须是不同主体，Agent 永远只有前者。门禁配置本身走独立变更通道，**候选分支改不到 workflow、status authority 与分支保护**。

**2）代码边界——评测跑在被测物之外。** 候选代码作为**不可信 artifact** 投递到隔离执行环境：独立 identity、最小 capability、隔离 filesystem / network / secrets 的 worker、容器或 VM。验证器进程**不加载、不 import** 这份不可信模块（否则 monkeypatch 掉断言即可通关），只消费受约束的执行结果与 attestation。注意「跨进程」只是故障隔离、「跨仓库」只是管理便利，都不等于权限隔离——真正给出保证的是身份与 capability 的收窄。验证器同样不读候选侧配置、不调用它注册的工具、不把它自报的日志当作通过依据。

**3）发布流程——单向阀。** 提案（Agent）→ 隔离评测 + 与父版本回归对比 → 高风险人工签核 → 签名打版 → 灰度 → 异常自动回滚。每个版本不可变并留 provenance，线上永不原地热改。

**自检标准（红队式一问）：** 假设 Agent 完全跑偏且握有全部工具权限，**是否存在任何一条路径让它的改动自己通过？** 改测试、改 required check 的 workflow、改分支保护、读到 held-out 真值、拿到密钥、说服自己当裁判——任一条为「是」，信任根就已经漏了。

**残余风险：** 信任根自身也要演进，而这只能靠人：走独立变更通道、双人复核、全量审计。所以 TCB 必须**小到人能读完**——信任根不是越厚越安全，而是越小越可信。

## 延伸 / 追问

**追问：Agent 想新增一个工具或一条评测用例，流程上怎么既不僵化又不破坏信任根？**

按「改的是能力还是判定权」分两条通道。**能力面**（工具代码、prompt、已批准范围内的策略取值）走快通道：从审定模板派生 + 自动评测 + 灰度，可以秒级放行。**信任根面**（评测真值、验证器逻辑、策略本身、密钥）走慢通道：人类作者、双人复核、变更审计，且判定资产尽量 **append-only**——新增用例可以，删除用例或放宽判定必须人工特批并记录理由，否则「删掉挂掉的测试」就是最省力的作弊路径。Agent 可以**建议**新用例，但提交物先进隔离候选池，由人或独立评测方审定，且不得回溯改写既有基线。此外给验证器加一层**元评测**：一组人工构造的「必须被拒」的坏样本，验证器若放行就说明它被改坏了，以此兜住「谁来验证验证器」。一句话：能力可以自动进化，判定权只能人工交接。

## 参考

- NIST CSRC Glossary, *Trusted Computing Base (TCB)*（TCB 的标准定义：承担安全策略实施的保护机制总和）：https://csrc.nist.gov/glossary/term/trusted_computing_base
- Saltzer & Schroeder, *The Protection of Information in Computer Systems*, 1975（least privilege 与 economy of mechanism 两条设计原则，是「TCB 越小越可信」的思想来源，而非该术语出处）：https://web.mit.edu/Saltzer/www/publications/protection/
- SLSA v1.2 Source track（受保护分支的技术控制；Source L4 要求两人复核所有变更）：https://slsa.dev/spec/v1.2/source-requirements
- SLSA v1.2 Build track（provenance 生成于可信控制面、用户构建步骤不可篡改，及 isolation strength）：https://slsa.dev/spec/v1.2/build-requirements
