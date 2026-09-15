---
id: engineering-0023
title: Agent 核心越来越大时，怎样选择模块或插件边界并把架构约束变成可检查规则？
category: engineering
tags: [module-boundaries, dependency-inversion, plugins, architecture-tests, tool-output]
difficulty: medium
role: engineer
contributor: 佚名
source: 洛小山《AI 产品从入门到精通》learn-ai（固定版本见参考）
status: published
updated: 2026-09-16
answers:
  - author: GPT-6
    type: ai
    model: GPT-6
    answered: 2026-09-16
    updated: 2026-09-16
---

## 问题

Agent 核心越来越大时，怎样选择模块或插件边界并把架构约束变成可检查规则？以工具输出截断为例，比较候选模块的依赖方向、公共类型、组合入口和测试成本，并证明规则能检出一次违规改动。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-16

**边界要围绕变化原因、依赖方向和独立验证能力来定，再用工具守住这些约束。** 不能看到 core 变大就按文件数拆包，也不能把一个大模块改名为十个相互依赖的插件就认为完成了治理。

[agent-0002](agent-0002-agent-architecture-components.md) 介绍 Agent 组件职责，本题补充源码依赖的落地规则；如何核对上游架构事实见 [engineering-0022](engineering-0022-source-evidence-architecture-review.md)。下面的模块名、依赖图和截断策略均是原创教学设计，不是任何上游已经采用的架构，也没有实测维护成本收益。

### 1. 先定义“截断”属于哪种需求

工具返回的原始结果、模型上下文里的结果、终端预览，不应默认共用一份被截断的字符串。先问：是防工具输出无限增长、控制模型 Token 预算，还是仅让终端预览短一点？前者涉及执行器/存储资源上限，模型预算需要具体 tokenizer 与消息格式，展示预览则由展示需求决定。截断不应破坏 JSON 等机器协议或丢失可追溯的原始结果。

本例只处理**已完整取得的工具文本的展示预览**，原文保留；不给采集、存储、模型输入或流式协议作保证。对于同一需求，比较如下：

| 候选位置 | 依赖与公共类型 | 测试成本及适用边界 |
| --- | --- | --- |
| CLI/终端适配层的私有函数 | CLI 掌握宽度和渲染规则，不让 runtime 反向引用 CLI 类型 | 只有一个界面且规则随终端变化时最省事；多入口都要相同语义时会重复，不适合让服务端借用终端组件 |
| runtime/core 内部 | 所有经过 runtime 的调用容易统一，但核心开始拥有省略号、显示宽度等展示策略 | 初期功能很小时合理；若依赖会话、模型客户端才能测试一个字符串函数，说明耦合过重。仅为“调用方便”放 core 不够充分 |
| 无 I/O 的 policy 模块，由组合入口注入 | policy 只依赖小公共值类型；runtime 依赖 policy 的契约，不导入具体实现；CLI 创建并连接二者 | 多入口共用稳定规则时可独立做纯函数测试；多一个接口和装配点，单一短函数且不会复用时可能不值得拆 |
| 可注册的策略插件 | 宿主依赖契约，组合入口/注册器选择实现；需额外明确版本、优先级、失败与资源策略 | 独立发布、多实现选择或第三方扩展时有价值；固定两个内部函数通常直接注入就够，插件化还增加发现、兼容和加载测试 |

先尝试现有领域模块里的内聚功能，再决定是否新建模块；只有独立版本、依赖分发或所有权确有需求，才升级成独立包/crate。模块边界、安装包边界和进程边界是三个选择，不能互相替代。

### 2. 让组合入口掌握具体实现，让公共类型保持小而稳定

假设 CLI 和服务端将共用本例预览语义，选择纯 policy + 显式注入。图中的箭头表示**源码允许的 import 方向**，不是运行时调用顺序：

```text
                 cli（组合入口）
                 /      |      \
            runtime   policy   adapters
                 \      |      /
                     contracts

runtime、policy、adapters 互不 import；向下的边允许但不要求全部出现。
```

runtime 可以在运行时调用注入的 policy 和 tool，但源码不导入具体实现，这就是此处依赖反转的作用。组合入口读配置、选择实现、创建实例并连接它们；业务模块不偷偷查全局容器寻找实现。插件若需要注册，也应在这个边界选择和校验，而不是让 core 在业务执行中到处扫描包。

公共契约承载消费者需要的少量值与行为：例如文本、预算单位、省略字符数和工具调用端口；不要泄露终端对象、供应商 SDK 响应、数据库连接或整个 Agent 状态。这里用 contracts 作双方可依赖的低层模块；接口由使用者需求驱动，不把它发展成包含日志、配置、所有实现的“common 万能包”。

公共类型一旦跨独立版本发布，要说明字段/单位、错误语义、兼容策略和迁移范围。类型注解只表达约定；特别是第三方插件的返回值，仍需类型检查、契约测试或运行时 Schema 验证，不能把一个 Protocol 当安全验证器。

### 3. 一个能独立验证的五模块例子

固定 **Python 3.11.8**；五个模块置于新建的 `demo/` 包，另建空的 `demo/__init__.py`。全部是教学代码，不加入本题库的构建工具。输入为 `A你🙂BC`，预算为 **4 个 Python Unicode code points（含省略号）**，预期预览 `A你🙂…`、省略数 2，原文仍为 `A你🙂BC`。

这里的字符数不是 bytes、grapheme cluster 或 Token；切片仍可能分开组合字符/多码点 emoji。实际界面若按可见字素或终端宽度限长，应换对应 policy；给模型限长则换 tokenizer，不能改个字段名就沿用这个函数。

```python
# demo/contracts.py
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class Preview:
    text: str
    omitted_chars: int

class Tool(Protocol):
    def run(self) -> str: ...

class PreviewPolicy(Protocol):
    def __call__(self, text: str, limit: int) -> Preview: ...
```

```python
# demo/policy.py
from demo.contracts import Preview

def truncate(text: str, limit: int) -> Preview:
    if type(text) is not str:
        raise TypeError("text must be str")
    if type(limit) is not int or limit < 0:
        raise ValueError("limit must be a nonnegative integer")
    if len(text) <= limit:
        return Preview(text, 0)
    kept = max(0, limit - 1)
    return Preview(text[:kept] + ("…" if limit else ""), len(text) - kept)
```

```python
# demo/runtime.py
from demo.contracts import Preview, PreviewPolicy, Tool

def execute(tool: Tool, policy: PreviewPolicy, limit: int) -> tuple[str, Preview]:
    raw = tool.run()
    return raw, policy(raw, limit)
```

```python
# demo/adapters.py
class FixedTool:
    def __init__(self, text: str):
        self.text = text

    def run(self) -> str:
        return self.text
```

```python
# demo/cli.py
from demo.adapters import FixedTool
from demo.policy import truncate
from demo.runtime import execute

def example():
    return execute(FixedTool("A你🙂BC"), truncate, 4)

if __name__ == "__main__":
    print(example()[1])
```

`FixedTool` 以结构满足 Tool Protocol，因此不需要实际 import contracts；规则允许该依赖并不强迫添加。示例 runtime 信任注入对象，未实现第三方返回值校验，也未持久化原文，只在返回元组中保留；生产的持久化/保留期限另由适配器与业务契约负责。HTML/Markdown 等安全渲染仍归展示适配层，截断不能代替转义或清洗。

这样，policy 测试不启动 Agent 或 SDK；runtime 测试用 fake tool/fake policy 验证调用和原文保留；适配器测试验证外部协议到公共类型的映射；组合入口用一次 smoke test 检查实际接线。这里比较的是所需测试环境，未宣称构建时间或故障率下降了多少。

### 4. 用真实 import 图检查约束，并故意破坏它

本例固定 **Import Linter 2.3 + Grimp 3.9**。在 demo 的父目录保存以下 `.importlinter`：

```ini
[importlinter]
root_package = demo
exclude_type_checking_imports = False

[importlinter:contract:direction]
name = Composition owns concrete implementations
type = layers
layers =
    demo.cli
    demo.runtime | demo.policy | demo.adapters
    demo.contracts
```

layers 从上往下列；同一行的 `|` 表示相互独立，不能随手换成允许同级互依赖的 `:`。这个固定版本会检查静态 import 的间接路径，不能经 utils/helper 绕过规则。类型检查分支也明确计入：公共 DTO 为了某个类型注解反向依赖 runtime，同样是架构耦合。配置依据见固定版本的 [layer/同级独立契约](https://github.com/seddonym/import-linter/blob/a115aa69899d03e540d55b85d336d0cb1e5c6e00/docs/contract_types.rst#L106-L318) 与 [TYPE_CHECKING 选项](https://github.com/seddonym/import-linter/blob/a115aa69899d03e540d55b85d336d0cb1e5c6e00/docs/usage.rst#L43-L62)。

```sh
# 在新建 demo 包的父目录，使用安装了固定依赖的 Python 环境
python -m demo.cli
lint-imports --no-cache
```

实际基线输出 `Preview(text='A你🙂…', omitted_chars=2)`；Import Linter 分析 **6 文件、5 依赖**，报告 `1 kept, 0 broken`、退出码 0。这里的 6 包含空 `__init__.py`，不是“拆成六个包所以架构更好”。随后每次从全新临时目录复制基线，只加入对应违规边再运行同一命令：

| 改动 | 应检出的规则/路径 | 实际结果 |
| --- | --- | --- |
| runtime 加 `import demo.adapters` | 不能绕过组合入口选择具体 adapter | 退出 1；报告 runtime → adapters |
| runtime 导入 helper，helper 导入 adapters | 同级独立也约束间接依赖 | 退出 1；报告 runtime → helper → adapters |
| contracts 加 `import demo.runtime` | 公共类型不得反向依赖上层 | 退出 1；报告 contracts → runtime |
| 上一条 import 放进 `if TYPE_CHECKING:` | 不用仅类型引用掩盖反向耦合 | 退出 1；仍报告 contracts → runtime |

非零退出必须确认为 **契约 BROKEN**，而非找不到包、配置解析失败或环境报错；不能仅断言“进程失败了”就算反例测试成功。CI 可在固定依赖环境运行基线检查、纯函数/契约测试和接线 smoke test，让违规阻断变更；本题只运行了这些本地例子，未替上游或本仓库配置实际 CI。

**静态规则有遗漏范围：** 在本例 runtime 中改用 `importlib.import_module("demo.adapters")`，此固定工具组合仍报告通过，没有生成那条动态边。这是实测限制，不是获准这样写。需限制动态加载只能从组合入口发生，并按语言实际用法补 AST/lint 或加载注册表测试；不能把一次静态通过写成“系统不存在反向依赖”。默认规则也不会自动拒绝全部未登记模块；需要封闭清单时，可用带 containers 的 exhaustive layer 契约，新增模块必须更新所有权和规则，而非无期限添加 ignore。

Python 的 import 图也不是完整部署依赖图。跨语言或编译型项目还需核对 package/build graph、feature/target、生成代码、FFI 和 re-export；公共 API 是否泄露底层类型需另外检查。测试只跑默认 feature，并不能证明所有构建变体符合约束。指标可观察跨边界变更、循环依赖、测试所需环境、构建受影响范围，再决定拆分是否值得。

### 5. 插件提供替换点，安全隔离另有边界

插件契约至少明确：发现/注册地点、版本与能力声明、输入输出类型、异常、超时/取消、资源预算、调用顺序/冲突与生命周期。多个插件都能给预览时，要决定唯一选择还是有序组合，不能依赖恰好出现的加载顺序；不兼容应可诊断地拒绝，不能悄悄调用另一份实现。

固定 **pluggy 1.6.0** 的 [PluginManager.register](https://github.com/pytest-dev/pluggy/blob/fd08ab5f811a9b2fa9124ae8cbbd393221151e2c/src/pluggy/_manager.py#L122-L172) 检查和登记 hook，[普通 hook 分派](https://github.com/pytest-dev/pluggy/blob/fd08ab5f811a9b2fa9124ae8cbbd393221151e2c/src/pluggy/_callers.py#L76-L130) 直接调用 `hook_impl.function(*args)`。接口/注册校验不提供进程、文件或网络隔离；同进程插件可能修改共享状态、抛异常或阻塞宿主。本文不把这个插件库用作 sandbox。

不可信扩展若需要隔离，应另选受控进程/容器或远端执行边界，以受限 IPC、最小权限、资源上限和可确认的终止/回收来约束。模块分层负责源码耦合，协议负责协作，隔离负责能力边界，三者要分别验证；具体证据方法见 [engineering-0022](engineering-0022-source-evidence-architecture-review.md)。

## 延伸 / 追问

**只有一个很小的截断函数，还需要创建新包吗？** 不需要。若只服务一个终端且变化原因相同，放适配层私有函数并独立测试就足够。先建立代码边界；等出现真实复用、独立依赖或发布需求，再考虑公共模块/包，而不是用包数作为目标。

**为了 type hint，把 runtime 类型挪到 common 就行了吗？** 只有该类型确实是跨边界稳定契约才适合下沉。若它携带模型 SDK、会话全量状态或可变服务对象，只是把上层耦合改了名字。改成消费者需要的值/端口，并用反向依赖规则和 API/契约测试限制泄露。

**规则全绿，但插件卡住 Agent，说明规则没价值吗？** 说明检查范围不同。import 规则不证明时限、错误恢复、资源使用或隔离；要按插件契约补故障测试。对于不可信代码，不能把同进程超时等待当成已终止插件，需要真实执行边界和资源回收证据。

## 常见误区

- “包越多，架构越好”：包数和目录数不表示内聚、依赖稳定或可维护；碎片化也可能增加迁移和接线成本。
- “代码搬出 core 就算解耦”：如果新模块继续导入 core 的状态和具体实现，依赖仍然反向。
- “禁止 import 就禁止了运行时调用”：依赖注入允许调用具体对象，但源码依赖仍指向契约。
- “插件接口就是安全隔离”：接口匹配不限制进程能力、资源或输出内容。
- “静态图通过就覆盖整个架构”：动态加载、未登记模块、生成代码和构建变体必须另定规则与证据。

## 参考

- 洛小山，《AI 产品从入门到精通》learn-ai，固定 commit `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/codex-01.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-01.html)、[slides/codex-31.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-31.html)、[slides/dsh-1.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-1.html)、[slides/12-1.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/12-1.html)。仅作题目来源；不搬运 AGPL 课件，不将其上游包数量、lint 启用或维护收益视为本例事实。
- David Seddon，Import Linter **v2.3 / `a115aa69899d03e540d55b85d336d0cb1e5c6e00`**，正文链接为固定文档；[layers 实现](https://github.com/seddonym/import-linter/blob/a115aa69899d03e540d55b85d336d0cb1e5c6e00/src/importlinter/contracts/layers.py)、[缓存选项](https://github.com/seddonym/import-linter/blob/a115aa69899d03e540d55b85d336d0cb1e5c6e00/docs/caching.rst)、[BSD-2-Clause LICENSE](https://github.com/seddonym/import-linter/blob/a115aa69899d03e540d55b85d336d0cb1e5c6e00/LICENSE)。实验另固定 Grimp 3.9，完整依赖见验证记录。
- pytest-dev，pluggy **1.6.0 / `fd08ab5f811a9b2fa9124ae8cbbd393221151e2c`**，正文链接为注册/调用源码，[MIT LICENSE](https://github.com/pytest-dev/pluggy/blob/fd08ab5f811a9b2fa9124ae8cbbd393221151e2c/LICENSE)。这里只借一手源码说明插件调用机制，不证明任何实际部署的隔离措施。
- 本文源码核对与本地实验日期为 **2026-09-16**。截断输入、依赖图和违规变体均为自编；没有生产容量、实际 CI 启用或维护成效数据，也未修改题库索引生成工具。
