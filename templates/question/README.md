# 单题 HTML 模板

Markdown 是内容来源，`index.json` 是题目索引，`html/` 是可直接打开的生成产物。每个输出 HTML 内嵌 CSS、JavaScript 和图片，不依赖 CDN、服务端接口或运行时 Markdown 渲染器。

## 日常使用

在项目根目录执行：

```sh
.venv/bin/python scripts/gen_html.py
```

新增题目时，先按项目约定补齐 `questions/*.md` 和 `index.json`。生成器会更新 `html/index.html`、所有单题页和记录原文摘要的 `html/manifest.json`。内容没有变化时不重写文件。原文标题、完整题干、答案、署名、代码块、表格、参考资料与常见误区均保留。

- `question.html`：单题结构；`{{name}}` 是构建期占位符。
- `question.css`：统一视觉与移动端、打印样式。
- `question.js`：每题独立的作答记录、展开/收起、图片查看与打印。
- `icons.svg`：内嵌图标。
- `supplements/<题目 ID>.html` / `.js`：可选的独立交互补充，放在参考答案内部。目前只有 ReAct 演示。正文仍从 Markdown 生成。
- `diagrams/`：按 Mermaid 原始内容 SHA-256 命名的静态 SVG 缓存。

生成器识别独立的「延伸 / 追问」「追问」小节，以及混合小节中明确以 `**追问：…**` 标记的项目。每个追答默认收起；没有追答时显示“原文暂未提供追答”，不生成新的内容。

## 构建依赖

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements-html.txt
```

也可使用 `uv venv .venv` 和 `uv pip install --python .venv/bin/python -r scripts/requirements-html.txt`。

现有 SVG 缓存已随项目提供。仅当新增/修改 Mermaid 源码时才需要 Node.js 与 Mermaid CLI：

```sh
npm --prefix scripts/diagram-renderer ci
.venv/bin/python scripts/gen_html.py
```

默认安装会准备 Puppeteer 的浏览器。若要使用已经安装的 Chrome：

```sh
PUPPETEER_SKIP_DOWNLOAD=true npm --prefix scripts/diagram-renderer ci
PUPPETEER_EXECUTABLE_PATH='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' .venv/bin/python scripts/gen_html.py
```

SVG 在本机生成，不上传题目到图像服务。修改生成器中的 Mermaid 渲染主题时，移除需要重新渲染的 SVG 缓存，再执行生成。输出中嵌入的 SVG 会补齐原始尺寸，用于放大查看。

## 验证

```sh
.venv/bin/python scripts/gen_html.py --audit
.venv/bin/python scripts/gen_html.py --check
.venv/bin/python -m unittest discover -s scripts/tests -v
```

检查覆盖所有索引条目、原文/输出的一一对应关系、追问分隔、围栏代码中的伪标题、嵌套 details、原始代码块内容摘要、表格/流程图数量、本地链接、内嵌图片、独立题目身份及默认折叠状态。未知追问格式或缺失资源会让生成失败，不会静默省略。

`--check` 只验证生成产物是否与当前原文和模板一致，不会启动浏览器补画缺失的流程图。新增源文件时若缺少索引登记，或输出目录里有已经不属于索引的 HTML，生成器会提示人工核对，不会擅自删除文件。

## 作答记录

使用 `agent-interview:<题目 ID>:answer:v2` 作为 localStorage key。移动同一站点内的 HTML 路径不会改变记录；不同题目互不覆盖。ReAct 早期样稿的草稿可以继续读取。

数据只属于当前浏览器与站点 origin；换浏览器、域名或端口不会自动迁移。直接用 `file://` 打开时，本地存储范围还受浏览器行为影响。浏览器禁用或写满本地存储时，页面会提示自行复制保存。打印包含当前作答和所有答案，结束打印后恢复展开状态。


## 学习主页集成

`html/index.html` 由 `templates/workspace/` 生成，提供常驻导航、筛选、最近题目和回答导出。单题页可独立打开，也可显示在主页右侧的阅读区；直接打开时顶部有“学习主页”链接。

嵌入阅读区时，单题脚本只向父页面发送加载完成、草稿已保存或题目跳转通知；父页面验证来源窗口、同源关系与题目 ID。回答正文不通过消息传输，主页按原来的每题 localStorage key 读取。题目中的本地关联链接交给主页导航；原文和外部参考资料另开标签页。
