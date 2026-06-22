---
id: agent-0021
title: 如何确保 Agent 返回标准 JSON？如果模型输出多余说明文字，后端如何提取？
category: agent
tags: [agent, structured-output, json, function-calling, parsing]
difficulty: medium
role: engineer
contributor: 佚名
source: 字节跳动
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

如何确保 Agent 返回标准 JSON？如果模型输出多余说明文字，后端如何提取？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

核心思路：**能在生成阶段约束就别在解析阶段补救**。按可靠性从高到低分三层防线，工程上叠加使用。

**第一层 · 生成端约束（首选，从源头保证合法）**

```
        强 ──────────── 可靠性 ──────────── 弱
  约束解码(grammar)  > JSON mode > function call > 纯 prompt
  逐 token 屏蔽非法    平台保证   schema 引导    只靠示范
```

- **约束解码 / Grammar**（vLLM Outlines、llama.cpp GBNF）：按 JSON Schema 编译成状态机，解码时屏蔽所有不合法 token，**结构 100% 合法**，本地模型最稳。
- **JSON mode / Structured Outputs**：OpenAI、Gemini 等原生开关，传 `response_format` + schema，平台保证输出可解析。
- **Function / Tool calling**：把"返回结果"定义成一个带参数 schema 的工具，模型通过 `arguments` 回结构化字段——这既是调用工具的方式，也是拿稳定 JSON 的常用手段。
- **Prompt 兜底**：明确"只输出 JSON、不要解释、不要 ```代码块```"，给 one-shot 示例。最弱，仅作补充。

**第二层 · 校验 + 重试（保证语义正确）**

合法 JSON ≠ 正确：字段缺失、类型错、枚举越界仍会发生。

```
LLM 输出 → 提取 → json.loads → Schema 校验(Pydantic/jsonschema)
   ▲                              │成功→返回
   └────── 带错误信息重试 ◄────────┘失败(≤2~3 次)
```

把校验报错（"price 应为 number"）回灌给模型让它自我修正，比重新生成更省更准；超过重试上限则降级或报警。

**第三层 · 稳健提取（应对混合输出）**

当模型仍夹带"好的，结果如下："等说明文字时，后端按序兜底：

1. 优先剥 ` ```json ... ``` ` 代码块（正则提取 fenced block）；
2. 无围栏则**括号配对扫描**：找第一个 `{` 或 `[`，计数 `{}`/`[]` 深度，取到配对归零处截出完整 JSON，比贪婪正则更抗嵌套；
3. 对截出片段做容错清洗（去尾逗号、单引号转双引号），再 `json.loads`；
4. 仍失败 → 触发第二层重试或返回结构化错误，**绝不**把脏串透传下游。

**一句话总结：** 生成端用 grammar / JSON mode / function calling 从源头锁结构，中间用 Schema 校验 + 带错误重试保语义，末端用代码块剥离 + 括号配对兜底提取——三层叠加才能既稳又准。

## 延伸 / 追问

**追问：为什么约束解码能 100% 保证合法，JSON mode 却仍可能要重试？**

二者作用层级不同。约束解码在**解码循环内部**生效：每生成一个 token 都按 grammar 状态机过滤掉会破坏结构的候选，所以括号、引号、逗号永远配平，**语法层面**不可能出错。但它通常只约束"是合法 JSON / 符合结构"，难以表达全部业务语义（取值范围、字段间依赖、枚举），所以语法对、**语义仍可能错**。JSON mode 多是平台侧的轻保证，部分实现只确保"可被解析"，schema 遵循度依模型而定，复杂 schema 下偶有字段缺失。因此无论哪种，都仍需第二层 Pydantic / jsonschema 做语义校验与带错误重试——约束解码省掉的是"语法重试"，省不掉"语义重试"。

## 参考

- OpenAI Docs，*Structured Outputs*：https://platform.openai.com/docs/guides/structured-outputs
- Outlines，*Structured generation*：https://github.com/dottxt-ai/outlines
- Pydantic，*Models & validation*：https://docs.pydantic.dev/latest/concepts/models/
