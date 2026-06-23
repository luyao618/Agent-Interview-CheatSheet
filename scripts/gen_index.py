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
