#!/usr/bin/env python3
"""Generate index.md (the human-facing directory page) from index.json.

Run from the repo root:  python3 scripts/gen_index.py
The directory page is a snapshot of index.json — re-run this after adding or
editing questions so the two stay in sync.

Behavior notes:
- Categories with zero questions are omitted from both the overview table and
  the body sections (no body section => no anchor => listing them in the
  overview would create dead links). They reappear automatically once they
  have at least one question.
- Section anchors are computed with GitHub's heading-slug rules (lowercased,
  emoji / punctuation stripped, spaces -> hyphens, CJK kept) so the overview
  table's "查看 ↓" links resolve on GitHub.
"""

import json
import os
import unicodedata

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_JSON = os.path.join(REPO_ROOT, "index.json")
INDEX_MD = os.path.join(REPO_ROOT, "index.md")

DIFF_BADGE = {"easy": "🟢 入门", "medium": "🟡 进阶", "hard": "🔴 困难"}
EMOJI = {
    "llm": "🧠",
    "agent": "🤖",
    "rag": "🔍",
    "engineering": "⚙️",
    "product": "📦",
}
TOP_TITLE = "📚 AI 面试题库 · 目录"
CAPABILITY_PATHS = [
    ("L0", "AI-native 基础判断", "判断 AI 适用边界、任务价值与人与系统的责任边界。"),
    ("L1", "模型与知识基础", "理解模型能力、Prompt/Context、模型选择、推理与成本边界。"),
    ("L2", "AI 应用构建", "构建 Agent、RAG、Tool Calling/MCP、Memory、Workflow 与人工接管。"),
    ("L3", "生产化与治理", "覆盖 Evaluation、Observability、Reliability、Security、Privacy 与 Cost。"),
    ("L4", "产品交付与业务闭环", "完成需求发现、优先级、体验设计、指标、实验、合规与落地。"),
]
DEV_PATHS = [
    ("L0", "AI-native 基础判断", "[Agent vs workflow](questions/agent-0008-agent-vs-workflow.md)", "[为什么不能只调大模型 API](questions/agent-0035-why-not-just-call-llm-api.md)"),
    ("L1", "模型与知识基础", "[Prompt vs context engineering](questions/agent-0019-prompt-vs-context-engineering.md)", "[工具调用与 JSON 输出](questions/agent-0021-structured-json-output.md)"),
    ("L2", "AI 应用构建", "[RAG pipeline 全流程](questions/rag-0023-rag-pipeline-full-flow.md)", "[Skill / token 优化](questions/agent-0001-skill-token-optimization.md)"),
    ("L3", "生产化与治理", "[AI 应用监控](questions/engineering-0006-ai-app-monitoring.md)", "[人手动接管与权限边界](questions/agent-0042-human-handoff-when-user-unavailable.md)"),
]
PM_PATHS = [
    ("L0", "AI 场景判断", "[AI 场景优先级](questions/product-0001-ai-scenario-prioritization.md)", "[AI 需求拆解](questions/product-0002-ai-prd-requirements.md)"),
    ("L1", "模型与知识基础", "[模型选型与能力边界](questions/llm-0002-open-source-vs-closed-source-models.md)", "[Prompt / Context engineering](questions/agent-0019-prompt-vs-context-engineering.md)"),
    ("L2", "AI 应用构建", "[RAG pipeline 全流程](questions/rag-0023-rag-pipeline-full-flow.md)", "[Function Calling 工具链](questions/agent-0004-function-calling-design.md)"),
    ("L3", "生产化与治理", "[AI 产品指标](questions/product-0003-ai-product-metrics.md)", "[失败恢复体验](questions/product-0004-ai-ux-failure-recovery.md)"),
    ("L4", "产品交付与业务闭环", "[上线评测闭环](questions/product-0006-ai-product-iteration-loop.md)", "[AI 需求拆解](questions/product-0002-ai-prd-requirements.md)"),
]


def gh_anchor(text):
    """Approximate GitHub's heading-slug algorithm.

    Lowercase, drop everything that is not a letter or number (emoji,
    punctuation, combining marks), turn spaces into hyphens, keep '-'/'_'.
    CJK characters are letters, so they survive.
    """
    out = []
    for ch in text.lower():
        if ch in " \t":
            out.append("-")
        elif ch in "-_":
            out.append(ch)
        elif unicodedata.category(ch)[0] in ("L", "N"):
            out.append(ch)
    return "".join(out)


def main():
    with open(INDEX_JSON, encoding="utf-8") as f:
        data = json.load(f)

    cats = sorted(data["categories"], key=lambda c: c.get("sort", 0))
    questions = data["questions"]

    by_cat = {}
    for q in questions:
        by_cat.setdefault(q["category"], []).append(q)
    for cid in by_cat:
        by_cat[cid].sort(key=lambda q: q["id"])

    # Only categories that actually have questions get listed / sectioned.
    visible_cats = [c for c in cats if by_cat.get(c["id"])]

    total = len(questions)
    top_anchor = gh_anchor(TOP_TITLE)

    lines = [
        f"# {TOP_TITLE}",
        "",
        "> 按**分类 + 序号**排列，点击题目标题即可跳转到对应题解。",
        "",
        f"**题目总数：{total}** ｜ 索引来源：[`index.json`](index.json)",
        "",
        "## 按能力路径浏览",
        "",
        "> 题目按技术分类归档；能力路径用于 Developer 与 PM 的跨分类学习，不改变既有题目 ID 或链接。",
        "",
        "| 层级 | 能力 | 说明 |",
        "| :---: | :--- | :--- |",
    ]
    for level, name, description in CAPABILITY_PATHS:
        lines.append(f"| **{level}** | **{name}** | {description} |")
    lines += [
        "",
        "### Developer 路径（入口 → 目标）",
        "",
        "| 层级 | 能力 | 入口 | 目标 |",
        "| :---: | :--- | :--- | :--- |",
    ]
    for level, name, entry, target in DEV_PATHS:
        lines.append(f"| **{level}** | {name} | {entry} | {target} |")
    lines += [
        "",
        "### PM 路径（入口 → 目标）",
        "",
        "| 层级 | 能力 | 入口 | 目标 |",
        "| :---: | :--- | :--- | :--- |",
    ]
    for level, name, entry, target in PM_PATHS:
        lines.append(f"| **{level}** | {name} | {entry} | {target} |")
    lines += [
        "",
        "**共同入口**：[`agent-0008`](questions/agent-0008-agent-vs-workflow.md) / [`agent-0035`](questions/agent-0035-why-not-just-call-llm-api.md) / [`agent-0019`](questions/agent-0019-prompt-vs-context-engineering.md) / [`product-0001`](questions/product-0001-ai-scenario-prioritization.md) / [`product-0003`](questions/product-0003-ai-product-metrics.md)，用来建立 AI 适用边界和业务落地的共同起点。",
        "",
        "**Agent 内容映射**：[`agent-0008`](questions/agent-0008-agent-vs-workflow.md)、[`agent-0035`](questions/agent-0035-why-not-just-call-llm-api.md)、[`agent-0019`](questions/agent-0019-prompt-vs-context-engineering.md)、[`agent-0021`](questions/agent-0021-structured-json-output.md) 作为 L0/L1/L2 的串联入口；[`agent-0042`](questions/agent-0042-human-handoff-when-user-unavailable.md)、[`agent-0051`](questions/agent-0051-agent-virtual-identity-vs-user-identity.md)、[`agent-0054`](questions/agent-0054-self-improving-agent-trust-root-boundary.md) 聚焦 L3 与权责边界治理。",
        "",
        "## 分类总览",
        "",
        "| 分类 | 数量 | 快速跳转 |",
        "| :--- | :---: | :--- |",
    ]
    for c in visible_cats:
        cid = c["id"]
        emoji = EMOJI.get(cid, "📂")
        heading = f"{emoji} {c['label']}"
        count = len(by_cat[cid])
        lines.append(f"| {emoji} {c['label']} | {count} | [查看 ↓](#{gh_anchor(heading)}) |")
    lines += ["", "---", ""]

    for c in visible_cats:
        cid = c["id"]
        items = by_cat[cid]
        emoji = EMOJI.get(cid, "📂")
        heading = f"{emoji} {c['label']}"
        lines += [
            f"## {heading}",
            "",
            f"<sub>分类 ID：`{cid}` ｜ 共 {len(items)} 题</sub>",
            "",
            "| # | 题目 | 难度 |",
            "| :---: | :--- | :---: |",
        ]
        for i, q in enumerate(items, 1):
            title = q["title"].replace("|", "\\|")
            diff = DIFF_BADGE.get(q.get("difficulty", ""), q.get("difficulty", ""))
            lines.append(f"| {i} | [{title}](questions/{q['file']}) | {diff} |")
        lines += [
            "",
            f'<div align="right"><a href="#{top_anchor}">↑ 返回顶部</a></div>',
            "",
        ]

    lines += [
        "---",
        "",
        "<sub>本目录由 `scripts/gen_index.py` 从 `index.json` 自动生成；新增题目后请重跑该脚本以保持同步。</sub>",
        "",
    ]

    with open(INDEX_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Wrote {INDEX_MD}: {total} questions, {len(visible_cats)} categories")


if __name__ == "__main__":
    main()
