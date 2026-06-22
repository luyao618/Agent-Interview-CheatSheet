---
id: agent-0004
title: Function Calling 是怎么设计的
category: agent
tags: [agent, function-calling, tool-use, schema, llm]
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

Function Calling 是怎么设计的？请说明工具 schema 的定义、模型如何选择并产出调用、以及参数校验与结果回灌的链路。

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

**一句话：** Function Calling 是给模型一份「带 schema 的工具菜单」，让模型在生成时**结构化地输出"调哪个工具、传什么参数"**，由外部 runtime 真正执行后再把结果回灌给模型——本质是把自然语言意图**对齐到可校验的结构化调用**。

**整体链路：**

```
                  ┌────────── tools schema (name/description/params) ───────────┐
                  ▼                                                              │
 用户请求 ──► LLM 决策 ──► 产出 tool_call(name + JSON args) ──► 参数校验 ──┬─ 不合法 ─► 报错回灌让模型改
                  ▲                                                      └─ 合法 ─► 执行工具
                  │                                                                 │
                  └──────────── 结果回灌(tool result 作为新上下文) ◄────────────────┘
                                       │ 还需调用? 继续循环 : 生成自然语言回答
```

**1. 工具 schema 设计（最关键）。** 每个工具向模型暴露三件事：
- `name`：唯一、动词化（如 `get_weather`），是模型选择的索引。
- `description`：说明**做什么、何时用、何时别用**——这是模型选对工具的主要依据，比参数更重要。
- `parameters`：用 **JSON Schema** 描述入参（类型、枚举、必填 `required`、字段 description）。schema 既是给模型的"填表说明"，也是后续校验的契约。

设计要点：工具数量精简、职责单一、描述无歧义；约束尽量进 schema（用 `enum`、`required`、范围）而非寄望模型自觉。

**2. 模型如何选择与产出调用。** 模型读取 tools 列表后，在一次生成里决定是「直接回答」还是「发起调用」；若调用，则产出 `{name, arguments}`，arguments 是符合该工具 schema 的 JSON。底层多由训练 + 约束解码（constrained/JSON decoding）保证结构合法。支持并行调用的模型可一次产出多个 tool_call。

**3. 参数校验。** 模型产出的 JSON **不可信**，runtime 必须按 schema 二次校验：类型/必填/枚举/边界。失败时不要直接抛给用户，而是**把校验错误作为 tool result 回灌**，让模型自我修正重试——这是稳健性的关键一环。同时对副作用类工具（下单、删库）加权限/确认护栏。

**4. 执行与结果回灌。** 校验通过后由 runtime 执行（查 API、跑代码），把返回**结构化地写回对话**（OpenAI 的 `role:tool`、Anthropic 的 `tool_result`，对应到 `tool_call_id`）。模型基于新结果决定继续调用还是收尾。注意结果要裁剪/摘要，避免超长污染上下文。

**一句话收尾：** Function Calling = **清晰 schema（选得准）+ 结构化产出（调得对）+ 严格校验（容错）+ 结果回灌（能闭环）**。设计好坏八成在 schema 与 description，剩下两成在校验与回灌的工程鲁棒性。

## 延伸 / 追问

**追问：模型产出的参数 JSON 不合法或选错工具，工程上怎么兜底？**

分层兜底：① **结构层**——优先用约束解码/JSON mode 让输出天然合法；解析失败则带着 parser 报错回灌让模型重出，限定重试次数（如 2 次）避免死循环。② **语义层**——按 JSON Schema 校验类型/必填/枚举/范围，错误信息要具体（"`unit` 必须是 celsius/fahrenheit，收到 `C`"）再回灌，模型据此自修。③ **选择层**——工具过多时模型易选错，可精简工具集、用清晰 description 与少量 few-shot 示例，必要时加一层路由先缩小候选。④ **执行层**——工具自身异常（超时、404）也结构化回灌，让模型换参数或换工具；高风险副作用工具加人工确认。核心原则：**把错误当成新的可观测输入喂回循环**，而不是直接失败。

## 参考

- OpenAI Docs，*Function calling*：https://platform.openai.com/docs/guides/function-calling
- Anthropic Docs，*Tool use (function calling)*：https://docs.anthropic.com/en/docs/build-with-claude/tool-use
- JSON Schema 官方规范：https://json-schema.org/
