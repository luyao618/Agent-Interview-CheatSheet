---
id: engineering-0027
title: 多层 Agent 配置如何确定有效值，整项替换、字段合并和强制策略分别应如何设计？
category: engineering
tags: [configuration, precedence, schema, provenance, policy, dry-run]
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

多层 Agent 配置如何确定有效值，整项替换、字段合并和强制策略分别应如何设计？请推演 Profile、Home 与 spawn 同时修改配置的结果，解释丢失字段、显式空值和最终生效来源。

## 答案 · GPT-6

把配置解析当成一次可解释的编译：先确定允许读取的层与应用顺序，按字段声明的规则求出候选值，再施加强制约束，校验完整有效配置，最后由 dry-run 展示结果及来源。**层的优先级、合并操作和策略权限必须分别定义**；“后写的赢”只有在明确它替换的是一个字段、一个对象还是一个带 ID 的条目后才有意义。

本题使用原创教学顺序 `Defaults < Profile < Home < spawn`，这些是合成输入的标签，不指向机器上的用户目录。真实产品可能还有组织、项目、环境变量或 CLI 层，而且不同字段的优先级未必相同；应查相应版本的解析入口、调用链和 schema。课程把多个产品作为学习线索，不能把它们拼成一套通用优先级。强制策略的信任边界可结合 [agent-0054](agent-0054-self-improving-agent-trust-root-boundary.md) 阅读。

### 1. 解析流程要留下什么证据

对固定输入和固定解析版本，建议得到确定的结果：**选择层 → 解析语法 → 校验每层可写字段 → 按顺序合并 → 强制策略约束 → 完整配置校验 → dry-run / 生效**。在读配置时记录实际选中的文件或参数、内容摘要及 schema/策略版本；本例只用固定层名，不实现文件发现。对未知字段、错误类型、重复 JSON key 应报错，避免拼写错误被忽略，或较低层的非法配置被较高层覆盖后藏起来。

完整校验必须晚于组合：允许每个覆盖层只写部分字段，不代表最终可以缺少必填字段。另一方面，schema 中的 `default` 也不自动定义补值时机。JSON Schema 2020-12 把它放在元数据关键词中；应用应显式决定默认值何时加入。本例只在最底层加入一次 Defaults，整项替换丢失的字段不会在最后偷偷补回来。

来源追踪至少回答“候选值是谁写的、谁覆盖了它、哪些字段因替换而删除、什么策略又收紧了它”。只记录最终值或只标记最后一层，无法解释跨字段结果。dry-run 可列出解析顺序、有效值、字段来源、覆盖/删除/限制动作及错误位置。生产输出应掩码秘密和敏感 prompt，来源摘要也不应被当成来源认证；本例所有值均为合成数据。

### 2. 合并规则和强制约束分别声明

| 字段/输入 | 本例的合并与 schema 规则 | 缺省或显式空值的含义 |
| --- | --- | --- |
| `agent` 对象 | 用两种模式比较：整项替换，或仅对 `model/max_tokens/timeout_s` 三个已声明字段合并 | 整项缺省则不改；`{}` 在字段合并下不改，在替换下清掉整项；`null` 非法 |
| `tools` 数组 | 后层整数组替换，允许的语法名称为 read/write/search；不拼接、不自动去重 | 缺省继承；`[]` 明确无工具；`null` 非法；重复值报错 |
| `greeting` | 标量替换，类型为 string 或 null | 缺省继承；`null` 明确关闭问候；`""` 是显式空文本 |
| `persona` | 只对本例 schema 声明的 `prompt/tone` 字段合并 | `prompt: ""` 明确清空，缺省继承；不能借 persona 写入任意运行时字段 |
| `agent.max_tokens/timeout_s` | 本例要求正整数，不隐式转换 string、bool 或 float；单位分别是 token 配置数与秒 | `0` 是非法值，不当成“没有提供”；`null` 也不是默认值 |
| `approval` | 用户层可请求 always/never，最后接受可信强制策略检查 | 空字符串、null、bool 都非法；省略时继承 |

不要用 `value or default` 判断缺省，否则 `[]`、`""`、`0` 和 `false` 会被混在一起。要区分“字段不存在”和“字段存在且值为空”，再由该字段的 schema 决定值是否合法。**本例保留 greeting 的 null 值，不实现 JSON Merge Patch**：RFC 7396 的 null 表示删除对象成员，数组则整项替换，这是另一份明确的契约，不可混用。

| 方案 | 合理用途 | 代价与不适用情况 |
| --- | --- | --- |
| 同名条目整项替换 | 希望上层独立拥有一整份 Agent/插件定义，易于读懂“这一项来自哪里”；可要求每份覆盖条目写全字段 | 局部修改容易丢字段；不适合用户只想改 model 却期待继承其余字段的接口。若允许部分条目，须在最终校验时拒绝缺字段 |
| 按 schema 指定字段合并 | 适合个人偏好或一次性的少量覆盖，未声明字段继续继承 | 来源分散；必须定义对象、数组、删除标记和联合类型的行为。不适合把任意对象递归混合，例如更换 provider 后残留旧 provider 的专有参数 |

强制策略不应只是可以被 spawn 覆盖的普通配置层。它来自用户输入无权修改的控制面，本例采用 `approval=always`、`tools = 请求集合 ∩ {read}`、`max_tokens≤1000`、`timeout_s≤30`。字段合并完成后收紧这些值，并把调整记录到 trace。更严格的 `tools=[]` 或更低预算会保留；多条限制通常应取交集/更小上界，而不能让“最后加载的策略”任意放宽另一条约束。

本例选择**调整并解释**，适合允许使用受限能力继续工作的场景；若调整会改变必须满足的任务需求，也可以拒绝整个计划，返回策略冲突。两种设计都应防止普通层越过强制约束。配置中的 `approval=always` 只是一项要求，真正的执行入口仍须做审批和权限检查；数值上界也不等于真实计费上限或超时机制已经落实。

### 3. 手算 Profile/Home/spawn 的冲突

下表列出全部输入。`model` 的名字仅为 mock 标签，数字是教学配置值，不引用模型价格或能力规格。Defaults 也是一个显式输入层。

| 层（从低到高） | `agent` | 其他字段 |
| --- | --- | --- |
| Defaults | `{model: mock-base, max_tokens: 2048, timeout_s: 30}` | `tools=[read]`，`greeting=hello`，`approval=always`，`persona={prompt: brief, tone: neutral}` |
| Profile | `{model: mock-research, max_tokens: 1200, timeout_s: 20}` | `tools=[read,write]`，`greeting=profile`，`persona={tone: formal}` |
| Home | `{model: mock-fast}` | `tools=[read]`，`greeting=null` |
| spawn | `{timeout_s: 10}` | `tools=[]`，`approval=never`，`persona={prompt: ""}` |

先按 **agent 整项替换**：Profile 提供完整三字段；Home 的一字段对象替换它，删除 Profile 的 `max_tokens=1200` 和 `timeout_s=20`；spawn 再用 `{timeout_s:10}` 替换 Home 对象，删除 `model=mock-fast`。最终 agent 只有 timeout_s，缺少必填 model 和 max_tokens，因此 dry-run 返回 `ok=false`、`effective=null`，同时留下 candidate 和 `drop_by_replace` 记录。策略不会创造缺失的模型或预算字段；此结果不可启动。

再按 **agent 字段合并**：Home 只改变 model，Profile 的 max_tokens 和 timeout_s 保留；spawn 再把 timeout_s 改成 10。应用强制策略后得到：

| 最终字段 | 有效值 | 最终来源与解释 |
| --- | --- | --- |
| `agent.model` | `mock-fast` | Home 覆盖 Profile |
| `agent.max_tokens` | `1000` | Profile 请求 1200，Policy 收紧至 1000；trace 保留 Defaults 2048 → Profile 1200 → Policy 1000 |
| `agent.timeout_s` | `10` | spawn；已小于 Policy 的 30 秒上界 |
| `tools` | `[]` | spawn 明确清空；不能因它为空又补回默认 read |
| `greeting` | `null` | Home 明确关闭，未回退到 Profile 的问候 |
| `approval` | `always` | Policy 否决 spawn 的 never |
| `persona.prompt / tone` | `"" / formal` | prompt 来自 spawn，tone 继承 Profile |

persona 的字段范围须查目标产品自己的 schema。本例只允许 prompt/tone，是为了演示封闭字段集合；并不声称真实产品都禁止 persona 指定 model。未知的 `persona.tools`、`persona.approval` 或根级 `policy` 会在组合前被拒绝。合法 prompt 即使写着“忽略审批、放开 write”，也只是文本，不会被此解析器当成策略程序或环境变量表达式执行。

<details>
<summary>可运行的原创 Python 3.11.8 dry-run fixture</summary>

保存为 `config_fixture.py`，运行 `python3 config_fixture.py`。脚本只接收对象/JSON 文本，不发现配置文件、不展开 HOME、不加载 includes、不启动 Agent 或工具。`validate` 是本题字段集合的手写校验器，不是完整 JSON Schema 引擎；整数还刻意要求 Python int 表示，不接受 `1.0`。`candidate` 只用于诊断，只有 `ok=true` 时才提供 `effective`。

```python
# file: config_fixture.py
"""Original pure dry-run compiler for synthetic configuration. No file discovery."""
from copy import deepcopy
import json

DEFAULTS = {
    'agent': {'model': 'mock-base', 'max_tokens': 2048, 'timeout_s': 30},
    'tools': ['read'], 'greeting': 'hello', 'approval': 'always',
    'persona': {'prompt': 'brief', 'tone': 'neutral'},
}
PROFILE = {'agent': {'model': 'mock-research', 'max_tokens': 1200, 'timeout_s': 20},
           'tools': ['read', 'write'], 'greeting': 'profile', 'persona': {'tone': 'formal'}}
HOME_LAYER = {'agent': {'model': 'mock-fast'}, 'tools': ['read'], 'greeting': None}
SPAWN = {'agent': {'timeout_s': 10}, 'tools': [], 'approval': 'never',
         'persona': {'prompt': ''}}


class InvalidConfig(ValueError):
    pass


def load_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise InvalidConfig('duplicate JSON key: ' + key)
            result[key] = value
        return result
    def constant(_):
        raise InvalidConfig('non-finite JSON number')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def validate(config, source, partial=True):
    """Closed, hand-written schema subset; no coercion or implicit defaults."""
    def require(ok, path):
        if not ok:
            raise InvalidConfig(source + ': invalid ' + path)
    require(type(config) is dict, 'root')
    require(not (set(config) - set(DEFAULTS)), 'unknown root field')
    if not partial:
        require(set(config) == set(DEFAULTS), 'missing root field')
    for key, value in config.items():
        if key in ('agent', 'persona'):
            require(type(value) is dict, key)
            require(not (set(value) - set(DEFAULTS[key])), key + '.unknown field')
            if not partial:
                require(set(value) == set(DEFAULTS[key]), key + '.missing field')
            for field, item in value.items():
                if field in ('max_tokens', 'timeout_s'):
                    ok = type(item) is int and 1 <= item <= 100000
                elif field == 'tone':
                    ok = item in ('neutral', 'formal', 'casual')
                else:
                    ok = type(item) is str and (field == 'prompt' or bool(item))
                require(ok, key + '.' + field)
        elif key == 'tools':
            require(type(value) is list and all(type(v) is str for v in value), key)
            require(set(value) <= {'read', 'write', 'search'} and len(value) == len(set(value)), key)
        elif key == 'greeting':
            require(value is None or type(value) is str, key)
        elif key == 'approval':
            require(value in ('always', 'never'), key)


def resolve(profile, home_layer, spawn, agent_mode='fields'):
    """Layer names/order and mandatory policy come from trusted host code."""
    if agent_mode not in ('fields', 'replace'):
        raise ValueError('unknown merge mode')
    layers = [('Defaults', deepcopy(DEFAULTS)), ('Profile', deepcopy(profile)),
              ('Home', deepcopy(home_layer)), ('spawn', deepcopy(spawn))]
    plan = dict(kind='dry-run', schema_version=1, policy_version='synthetic-policy-v1',
                agent_mode=agent_mode, effective=None, sources={}, trace=[], errors=[])
    try:
        for source, layer in layers:
            validate(layer, source)  # even invalid values later shadowed are errors
    except InvalidConfig as exc:
        plan.update(ok=False, errors=[str(exc)])
        return plan
    config, sources, trace = {}, plan['sources'], plan['trace']

    def write(path, value, source, action='set'):
        if '.' in path:
            parent, key = path.split('.')
            config.setdefault(parent, {})[key] = deepcopy(value)
        else:
            config[path] = deepcopy(value)
        trace.append(dict(path=path, source=source, action=action, value=deepcopy(value),
                          previous_source=sources.get(path)))
        sources[path] = source

    for source, layer in layers:
        for key, value in layer.items():
            if key in ('agent', 'persona'):
                if key == 'agent' and agent_mode == 'replace':
                    for field, old_value in config.get(key, {}).items():
                        if field not in value:
                            path = key + '.' + field
                            trace.append(dict(path=path, source=source, action='drop_by_replace',
                                              value=deepcopy(old_value), previous_source=sources.pop(path)))
                    config[key] = {}
                for field, item in value.items():
                    write(key + '.' + field, item, source)
            else:
                write(key, value, source)  # arrays, null and empty strings are values

    # Mandatory controls are NOT another user-editable layer. Synthetic constants only.
    def enforce(path, requested, constrained, action):
        if requested != constrained:
            write(path, constrained, 'Policy', action)
        else:
            trace.append(dict(path=path, source='Policy', action='checked', value=deepcopy(constrained)))
    enforce('approval', config['approval'], 'always', 'force')
    enforce('tools', config['tools'], [t for t in config['tools'] if t == 'read'], 'intersection')
    for field, cap in (('max_tokens', 1000), ('timeout_s', 30)):
        if field in config['agent']:
            requested = config['agent'][field]
            enforce('agent.' + field, requested, min(requested, cap), 'cap')
    try:
        validate(config, 'effective', partial=False)
    except InvalidConfig as exc:
        plan.update(ok=False, candidate=config, errors=[str(exc)])
        return plan  # no launchable effective config; defaults are not reinserted
    plan.update(ok=True, effective=config)
    return plan


def demo():
    return {mode: resolve(PROFILE, HOME_LAYER, SPAWN, mode) for mode in ('fields', 'replace')}


if __name__ == '__main__':
    print(json.dumps(demo(), ensure_ascii=False, indent=2, allow_nan=False))
```

</details>

### 4. dry-run 的验证与生效边界

2026-09-16，CPython 3.11.8 上的原创 `test_config.py` **14 个测试通过**。它核对上述两个完整计划和字段来源，完整对象替换的合法情况、缺省/null/空数组/空字符串、空对象在不同模式下的差异、数组替换、各层都不能放宽策略、persona 字段限制与纯文本输入、被覆盖前的非法值、严格类型/范围、重复 JSON key、NaN/Infinity 拒绝、确定性以及输入/返回值无别名污染。

其中一项测试在专属临时目录写入 3 份合成 Profile/Home/spawn JSON，显式读取后运行两种 dry-run，验证文件内容和文件集合没有变化；测试结束确认临时目录已删除。没有读取或修改用户真实 Profile/Home、凭据和运行时配置，也没有调用真实工具。

dry-run 应与真正生效路径共用同一个解析器，执行时绑定已检查的输入、schema、策略版本，避免检查后重新读取一组不同文件。配置或策略在间隙变更时，应重新解析或拒绝过期计划。本文 fixture 没有 apply、热重载或跨进程发布路径，因此只证明本地解析规则及诊断结果；它不证明生产加载原子性、外部策略来源可信、Agent 实际遵守审批、预算被执行或存在安全隔离。Python 中的常量也不是阻止恶意代码修改策略的权限边界。

## 延伸 / 追问

**追问：为什么在整项替换后补齐 Defaults 可能反而有问题？**

它会把“明确删除/省略以替换整项”变成“恢复旧默认”，可能重新开启用户想移除的能力。如果确实要在最后补默认，必须作为一条公开规则，区分删除标记与缺省，并记录 Defaults 的来源；不能同时声称整项替换已丢弃这些字段。

**追问：换一个 provider 时，字段合并怎样避免保留旧 provider 的参数？**

用带 discriminator 的联合 schema，根据 provider 校验允许字段；更换类型时可以整项替换该子对象，或显式迁移兼容字段。把所有对象一律 deep merge 会制造从未经过验证的混合配置。

**追问：用户想要 write，组织策略只允许 read，应该清成空数组还是报错？**

取决于任务是否允许降级。本例取交集并显示调整；若 write 是任务必需能力，应报策略冲突而不是假装任务可完成。无论采用哪种方式，都不能把普通配置层当成策略例外授权。

**追问：dry-run 的来源行写着 Policy，就证明策略可信吗？**

不证明。名称只是解释标签，生产需要验证来源和变更权限，并确保执行网关使用相同或更严格的当前约束。摘要能帮助比对内容，不能替代来源认证；dry-run 成功也不是执行批准。

## 常见误区

- **默认所有配置都是 deep merge。** 先查合并单位和数组规则；同名条目整项替换会丢失未重写的字段。
- **默认 persona 能定义任意字段。** persona 是具体 schema 的一个受限输入面，未知字段应被拒绝；可写 prompt 不等于可改权限策略。
- **把缺省与 null、空数组、空字符串混为一谈。** 是否继承、清空、删除或报错是逐字段契约，不能统一用真假值判断。
- **spawn 优先级最高就能关闭审批。** 普通偏好优先级不能覆盖强制约束；最终配置仍需完整校验和执行层落实。
- **有最终配置 dump 就能解释一切。** 没有覆盖/删除/策略 trace，丢失字段及实际来源仍不可解释；不经脱敏的 dump 还可能泄露敏感输入。

## 参考

来源核对于 2026-09-16。正文、表格、配置和 fixture 独立编写；课程只作为选题线索，具体产品的入口与合并语义未在本文重新审计，不将课程中的源码判断当作通用结论。

- 洛小山《AI 产品从入门到精通》，learn-ai 固定 commit `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/dsh-6.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/dsh-6.html)（Profile/Bundle/Patch 与整项替换线索）、[slides/12-14.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/12-14.html)（AgentDefinition/persona 字段与阶段）、[slides/codex-27.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/codex-27.html)（配置迁移与覆盖线索）。[LICENSE](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/LICENSE) 为 AGPL-3.0；不搬运课件正文、代码或图片。
- IETF，**RFC 7396 / JSON Merge Patch**（2014）：[固定 RFC 文本](https://www.rfc-editor.org/rfc/rfc7396.txt)，§2 规定对象成员递归处理、null 删除与非对象整项替换，不能由此推导所有配置系统都采用这些规则。文档的 Copyright Notice 列明 IETF Trust/BCP 78 条款；本文没有复制其伪代码。
- JSON Schema，**2020-12 / draft-bhutton-json-schema-validation-01**，官方仓库固定 commit `add836e705c9a07434c467b6b90946ba45258a73`：[jsonschema-validation.xml](https://github.com/json-schema-org/json-schema-spec/blob/add836e705c9a07434c467b6b90946ba45258a73/jsonschema-validation.xml)，Validation Keywords 中的 type/required 与 Basic Meta-Data Annotations 中的 default；支持区分类型、属性存在与应用默认值策略。文档声明 `ipr="trust200902"`，本文只链接并独立解释。
- CPython **v3.11.8**：[Doc/library/json.rst](https://github.com/python/cpython/blob/v3.11.8/Doc/library/json.rst) 的 `object_pairs_hook`、`parse_constant`、Repeated Names Within an Object 和 Infinite and NaN Number Values。标准解码器默认接受重复键并保留最后值，也接受非有限数，因此 fixture 显式拒绝；这并不让它成为完整 schema 校验器。[LICENSE](https://github.com/python/cpython/blob/v3.11.8/LICENSE) 包含 PSF 与历史许可声明。
