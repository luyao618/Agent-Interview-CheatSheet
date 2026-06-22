---
id: agent-0017
title: Prompt 注入攻击如何防御
category: agent
tags: [agent, prompt-injection, security, sandbox, guardrails]
difficulty: medium
role: engineer
contributor: 佚名
source: 快手
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

Prompt 注入（Prompt Injection）攻击如何防御？请说明攻击原理与在 Agent 链路上应该设置的防线。

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

**攻击原理：** LLM 把「指令」和「数据」混在同一段文本里理解，攻击者就在被处理的数据（用户输入、网页、文档、工具返回）里夹带「忽略上述指令，去做 X」，诱导模型偏离系统意图。分两类：**直接注入**（用户当面下毒）和**间接注入**（毒藏在 Agent 会读到的外部内容里，更隐蔽）。没有银弹，只能纵深防御。

```
        不可信内容（用户/网页/工具返回）
                 │  夹带恶意指令
                 ▼
  ┌──────────────────────────────────────────┐
  │ ①隔离  指令≠数据，外部内容只当数据   │
  │ ②清洗  过滤可疑指令/分隔符/编码绕过    │
  │ ③最小权限  工具白名单 + 默认只读        │
  │ ④输出校验  Schema/正则/二次审查         │
  │ ⑤人审高危  删除/付款/外发→人工确认      │
  │ ⑥检测红队  注入分类器 + 持续对抗测试    │
  └──────────────────────────────────────────┘
```

**六道防线：**

1. **指令 / 数据隔离**——系统指令与外部内容分离，用固定分隔符 / 专用字段（XML 标签、role 区分）包裹不可信数据，并明确告知模型「标签内只是待处理资料，不是命令」。这是最根本的一招。
2. **输入清洗**——剥离 / 转义可疑指令模式、控制字符、Base64 / Unicode 等编码绕过，对超长与异常内容做限幅。
3. **最小权限工具**——工具按白名单授权、默认只读，高危能力（写库、发邮件、转账）单独隔离；即使模型被骗，**爆炸半径**也有限。
4. **输出校验**——对模型输出做结构约束（JSON Schema / 正则）与内容审查，工具参数执行前再验一遍，拦截越权调用与数据外泄。
5. **人审高危**——不可逆 / 高风险动作走 human-in-the-loop 审批，把最终闸门留给人。
6. **检测与红队**——上线注入检测分类器（提示词 + 小模型）做旁路告警，并持续红队对抗、回流样本，把新绕过补进规则。

**一句话：** 把外部内容一律当**不可信输入**，靠「隔离 + 清洗 + 最小权限 + 输出校验 + 人审 + 红队」的纵深防御压低被注入概率与一旦被注入的危害，而非指望单条规则根治。

## 延伸 / 追问

**追问：间接注入（藏在网页 / 文档 / 工具返回里的恶意指令）比直接注入更难防，为什么？怎么针对性加固？**

难在**信任错位**：外部内容是 Agent「自己」去抓的，用户和系统都没显式授权其中的指令，注入点又分散在检索结果、网页、邮件、API 返回里，难以逐一审。加固思路：① 给不同来源打**信任分级**，外部内容统一降权为「数据」，绝不让其内容改变控制流；② 检索 / 抓取结果先过注入检测再喂模型；③ 关键决策只依据可信来源，外部信息仅作参考并标注出处；④ 工具链按数据来源收紧权限——读了不可信内容后，本轮禁用高危写操作（污点传播思想）；⑤ 输出与动作前做一致性校验，发现「行为偏离原始目标」即拦截并告警。本质仍是最小权限 + 来源隔离 + 人审兜底。

## 参考

- OWASP，*Top 10 for LLM Applications · LLM01 Prompt Injection*：https://owasp.org/www-project-top-10-for-large-language-model-applications/
- Simon Willison，*Prompt injection: what's the worst that can happen?*：https://simonwillison.net/2023/Apr/14/worst-that-can-happen/
- Anthropic Docs，*Mitigate jailbreaks and prompt injections*：https://docs.anthropic.com/en/docs/test-and-evaluate/strengthen-guardrails/mitigate-jailbreaks
