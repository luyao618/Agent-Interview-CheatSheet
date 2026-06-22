---
id: agent-0009
title: Agent 与 RPA 有什么差别
category: agent
tags: [agent, rpa, automation, autonomy, llm]
difficulty: easy
role: both
contributor: 佚名
source: 淘天/阿里
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

Agent 与 RPA 有什么差别？

## 答案

> 🤖 AI 答案 · 模型：Claude-Opus-4.8 · 日期 2026-06-22

**一句话区分：** RPA 是**按人录制/编排好的固定规则，确定性地重放操作**（点这个按钮、抠那个字段、填这张表）；Agent 是以 **LLM 为大脑、靠语义理解在运行时动态决策**下一步怎么走。RPA 擅长"照剧本演"，Agent 擅长"没剧本也能临场判断"。

**两种自动化的工作方式：**

```
RPA（规则驱动 · 确定性重放）
  录制/编排好的脚本 ─► 步骤1 ─► 步骤2 ─► 步骤3 ─► 输出
   （定位 UI 元素 / 固定字段 / if-else 分支都人写死）
   界面一改、字段一变 ─► 脚本就断

Agent（语义驱动 · 运行时决策）
  目标 ─►┌─ LLM 理解语境 ─► 决定动作 ─► 调工具 ─► 看结果 ─┐
         └◄──────────── 回灌，再决定下一步 ◄────────────┘
              非结构化输入也能懂，遇到变化能自适应
```

**关键差异维度：**

| 维度 | RPA | Agent |
| --- | --- | --- |
| 驱动方式 | 预设规则 / 录制脚本 | LLM 语义理解 + 动态决策 |
| 处理输入 | 结构化、格式固定 | 非结构化也能懂（文本/图像/语音） |
| 应对变化 | 脆弱，界面/流程一变就断 | 自适应，靠理解而非坐标 |
| 决策能力 | 只能走预定义分支 | 能临场判断、推理、回溯 |
| 异常处理 | 命中未编排分支即失败 | 可重试、换路径、求助 |
| 可预测/可控 | 强，确定性、易审计 | 较弱，需护栏与停止条件 |
| 成本/延迟 | 低且稳定 | 较高（多轮 LLM 调用） |

**本质差别落在两点：**

1. **是否理解语义。** RPA 不"懂"业务，它只认坐标、字段名、固定格式；输入稍微变形（换个版式的发票、口语化的工单）就抓瞎。Agent 用 LLM 真正理解内容，能处理非结构化、多模态、措辞多变的输入。
2. **控制流由谁决定。** RPA 的路径是人提前写死的有限分支；Agent 的路径是模型运行时生成的——调哪个工具、是否重试、何时收尾都由模型自己判断。这也是 Agent"脆弱性低、但可控性也低"的根源。

**各自适用场景：**

- **选 RPA**：流程**高度标准化、规则清晰、输入格式稳定、追求确定性与合规**。如跨系统搬数据、定时对账、批量填表、固定报表导出。这类活儿用 RPA 又快又稳，没必要上 Agent。
- **选 Agent**：输入**非结构化、流程多变、需要理解和临场决策**。如客服工单分流与作答、从杂乱文档抽取并核对信息、自主排障。

**工程现实——常是二者结合（IPA / Agentic RPA）：** 不是非此即彼。主流做法是 **Agent 负责"理解与决策"，RPA 负责"稳定执行"**：让 LLM 读懂非结构化输入、判断该做什么，再调用成熟的 RPA 脚本去可靠地点按钮、填表单、操作老系统。这样既拿到 Agent 的灵活性，又保留 RPA 的确定性与可审计性。一句话：**RPA 是"手脚"（确定性执行），Agent 是"大脑"（语义理解+决策），能规则化的交给 RPA，需要理解与判断的才交给 Agent。**

## 延伸 / 追问

**追问：能不能直接用 Agent 替代现有的 RPA？**

多数场景**不建议整体替换，而是分工与增强**。RPA 在"标准化、确定性、合规可审计、低延迟低成本"这些维度上仍是最优解，把稳定的批量操作交给 LLM 反而引入不确定性、更高成本和更难审计的风险。更务实的演进是**用 Agent 补 RPA 的短板**：① 入口处用 LLM 理解非结构化输入（邮件、工单、合同、截图），把它结构化后再喂给 RPA；② 让 Agent 做动态编排和异常兜底——当 RPA 因界面变更或意外分支断掉时，由 Agent 判断如何重试或换路径，而非直接失败；③ 高风险动作仍走固定脚本并加人工审批。本质上 **Agent 提供"理解 + 决策"，RPA 提供"可靠执行"**，二者叠加成 Intelligent/Agentic Automation，比单纯替换更稳、更省。

## 参考

- Anthropic Engineering，*Building Effective Agents*：https://www.anthropic.com/engineering/building-effective-agents
- UiPath，*Robotic Process Automation (RPA)*：https://www.uipath.com/rpa/robotic-process-automation
- IBM，*RPA vs. AI Agents*：https://www.ibm.com/think/topics/rpa-vs-ai-agents
