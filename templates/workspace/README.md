# AI 题典 · 学习主页模板

`html/index.html` 是静态学习入口，保留常驻导航并在右侧打开现有单题 HTML。它不依赖框架、CDN、运行时接口或额外服务。全部题目元数据在生成时内嵌；使用与单题页相同的本地回答记录。

## 文件与生成

- `index.html`：开始页、题库、我的回答、题目阅读区与手机导航容器。
- `sidebar.html`：桌面常驻导航与手机抽屉共用的结构。
- `workspace.css`：主页和全局导航的样式。
- `workspace.js`：路由、搜索/筛选、分页、阅读队列、本地记录与 Markdown 导出。
- `icons.svg`：主页内嵌图标。
- `../brand.svg`：书页与问号品牌图标，共用于导航和全部页面的 favicon。

修改后在项目根目录执行：

```sh
.venv/bin/python scripts/gen_html.py
.venv/bin/python scripts/gen_html.py --check
.venv/bin/python -m unittest discover -s scripts/tests -v
```

题目正文和单题布局继续维护在 `questions/` 与 `templates/question/`，无需在主页复制一份答案。分类数量、标题、角色、难度、关键词和关联文件由 `index.json` 生成。

## 使用与路由

- `index.html#home`：开始，继续最近题目，分类入口与推荐起点。
- `index.html#questions`：全部题目，每页 12 题。
- `index.html#questions?category=rag&difficulty=easy`：可分享的筛选状态。
- `index.html#answers`：有非空回答的题目，按记录时间排序；搜索匹配题目及回答文字。
- `index.html#question/agent-0025`：打开指定题目。

题库搜索匹配标题、编号、方向和 tags；工程师 / 产品经理筛选都包含 `role: both`。随机选题限定在当前筛选范围，并优先选择没有回答的题目。上一题 / 下一题沿进入时的筛选结果移动，返回列表保留条件；直接打开题目路由时使用同方向题集。

阅读区用独立 HTML 展示题目，因此单题文件仍可以直接打开。切换阅读区时使用 `location.replace`，避免 iframe 自己再添加一条浏览器历史；修改导航时务必检查浏览器后退 / 前进。

## 本地记录

- 作答正文沿用 `agent-interview:<题目 ID>:answer:v2`，兼容早期样稿的回答。
- 最近打开的题目保存在 `agent-interview:workspace:v1`。
- 当前标签页的题目队列保存在 sessionStorage 的 `agent-interview:workspace:queue:v1`。
- “已记录回答”只统计非空回答，不表示已经掌握题目。
- 导出为 Markdown 包含题目标题、ID、方向、记录日期和完整回答，不包含参考答案。

单题保存后通过同源 storage 事件及通知刷新主页计数。嵌入页通知只接受当前阅读窗口、相同 origin 和已知题目身份；切换信息只允许目录中的文件。用户文字以普通文本呈现，不作为 HTML 执行。

`file://` 可以离线使用，但浏览器对文件页本地存储的共享范围存在差异。需要稳定地在主页汇总回答时，建议通过 README 中的本地 HTTP 服务或静态站点使用；换 origin 不会自动迁移记录。

## 修改后的浏览检查

1. 搜索中文、英文或编号；组合方向、难度、角色、作答状态；检查无结果、重置、分页与随机范围。
2. 从筛选结果进入题目并作答，检查计数及“我的回答”；切换下一题、返回列表、后退 / 前进，再次打开确认记录仍在。
3. 点击题目正文里的关联题，确认左侧状态与右侧题目同步。
4. 导出 Markdown，核对记录内容；无回答时导出按钮不可用。
5. 在手机宽度打开导航，选择页面、按 Escape 关闭，检查焦点恢复与横向溢出。
6. 确认答案仍默认收起，单题独立打开、图片查看与打印仍正常。

合成 composition 事件可以验证搜索在组合输入期间等待，但不能代替真实操作系统输入法测试。

首页底部展示项目仓库链接，以及 Star / PR 入口；它们在新标签页打开 GitHub，保留当前作答位置。品牌展示为“AI 题典”，原仓库 URL 与既有本地记录键保持兼容。
