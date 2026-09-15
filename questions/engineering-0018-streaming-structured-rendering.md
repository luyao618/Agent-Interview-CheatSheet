---
id: engineering-0018
title: LLM 输出同时要可流式展示和机器可解析时，如何选择格式并处理半截与畸形数据？
category: engineering
tags: [streaming, structured-output, framing, rendering, validation]
difficulty: medium
role: engineer
contributor: 佚名
source: 洛小山《AI 产品从入门到精通》learn-ai（固定版本见参考）
status: published
updated: 2026-09-15
answers:
  - author: GPT-6
    type: ai
    model: GPT-6
    answered: 2026-09-15
    updated: 2026-09-15
---

## 问题

LLM 输出同时要可流式展示和机器可解析时，如何选择格式并处理半截与畸形数据？请说明事件帧、暂态展示、终态校验及安全提交，并模拟字符串或标签中间的分片。

## 答案 · GPT-6

> 🤖 AI 答案 · 模型：GPT-6 · 日期 2026-09-15

**把“先让人看到内容”和“允许机器使用结果”设为不同状态。** 网络分片先重组成协议事件，事件里的内容再进入暂态视图；收到约定的成功结束信号并完成终态解析、Schema 和业务校验后，才能提交。括号配平、标签闭合或连接断开，都不能单独证明结果可用。

终态 JSON 的生成与解析讨论见 [agent-0021](agent-0021-structured-json-output.md)，生成代码的执行面隔离见 [engineering-0012](engineering-0012-artifact-generated-code-safety.md)，中途切换模型见 [engineering-0017](engineering-0017-model-routing-failover.md)。本题补充分片重组与呈现状态，不重复这些题的完整流程。

### 1. 先分清四种边界

1. **字节边界。** 一次 socket/read 回调可能只有半个 UTF-8 字符，也可能带来多个事件。不能对每个任意 byte chunk 独立解码后丢弃错误字节；可用保留状态的增量解码器，或在字节层按协议收齐帧再严格解码。
2. **事件边界。** SSE 要按其行规则、空行分隔和多行 data 字段组装事件，再解析事件数据；WebSocket 消息、HTTP chunk 和 SDK delta 也各有自己的契约。不要把本例的 LF 分隔器直接用于 SSE。RFC 7464 的 JSON text sequence 则使用 RS 与 LF，不能与普通 JSON 或本例协议混称。
3. **内容边界。** 完整事件可能只含内层 JSON 的半个字符串、反斜线转义的一半或 XML 的 `<ans`。事件 JSON 能解析，不等于内容已经完整。不同请求、重试 attempt、choice/content block、tool call 的增量要按身份分别缓冲，不能全局拼一个字符串。
4. **提交边界。** 传输结束与语义成功分开判断：截断、取消、拒绝、in-stream error、超出输出上限均可能让流停下。由适配器按实际协议辨认成功终态，之后做完整解析、Schema/业务规则、当前权限检查和动作幂等控制。模型正文里自称“完成”不能伪装成控制事件。

例如 `{"days":1` 已能让 UI 暂时显示原文，但后续可能变成 `10}`；当前数值不能当最终退款期限。对单个字段或数组条目的增量消费，必须另有可验证的完成边界、版本和幂等契约；本例选择更保守的整次结果终态提交。

### 2. 格式选择与展示策略

| 格式 | 合理用途 | 流式处理 | 代价与不适用场景 |
| --- | --- | --- | --- |
| JSON + 明确事件封装 | 工具参数、表单、后端字段契约 | 可先显示安全的原始文本，或用理解字符串/转义/嵌套的增量解析器展示暂态字段；终态再完整解析与校验 | 需要区分部分值与最终值；不宜用正则抽取和自动补括号为高风险动作制造“成功” |
| Markdown | 面向人的解释、列表、代码示例 | 累积原文，节流重渲染，或使用支持增量语义的解析器；未完成的链接、代码围栏和尾部块允许变化 | CommonMark 本身也接受某些未闭合围栏直到文档末尾，能渲染不证明传输完整；不适合作为可靠的金额/枚举/动作参数契约 |
| XML + 明确文档 Schema | 已有 XML 接口、需要层次/混合文本表达的系统 | 真正的增量 XML parser 可以保留状态、报告元素事件；也可像本例先安全预览，结束后解析完整文档 | 标签较冗长，必须处理转义、嵌套和命名空间等规则；元素结束不证明整份文档合法，更不自动提供安全性 |

对“聊天解释 + 机器结果”，常见方案是让可信事件封装分别承载展示增量和最终结构化候选，或将可读文本作为 JSON 字符串字段。两路内容若不同源，应建立版本/引用关系并核对一致性，不能让用户看到一个期限、机器执行另一个期限。

**JSON 并非只能等全文才展示，XML 也不是天然更适合所有流式场景。** 真正决定体验的是事件契约、解析状态和 UI 更新策略。生成端的格式约束可减少结构错误，但不能省掉中断检测、终态校验或事实核实；Schema 合格不代表答案事实正确。

### 3. 暂态、终态与安全渲染

UI 可以维护 `receiving → ready` 或 `receiving → failed`。暂态标明“生成中/未校验”，禁用依赖完整结果的操作；失败后可保留带错误标记的草稿供阅读，不能沿用 ready 状态。重试用新的 attempt，除非协议明确提供可靠的续传和去重机制，否则不把失败流尾部接到新回答头部。

转义与解析是不同层的职责：

- **JSON 传输**用序列化库处理引号、反斜线、换行；**XML 文本**用 XML writer/转义处理 `<`、`&` 等。JSON 字符串合法不代表其中的 HTML 安全。
- **纯文本展示**优先用 DOM `textContent` 或框架默认的文本绑定。下面的 `html.escape` 只演示 HTML 文本节点内容，不是 JavaScript、CSS、URL 或 SQL 的通用转义器；不要拿它拼脚本、事件属性或 `innerHTML` 原文。
- **Markdown 富文本**在选定版本的 parser 后进行 HTML allowlist sanitization，通常禁用原始 HTML，限制链接 scheme、属性和外部资源；不要自动加载模型指定的远程图片。sanitize 之后再拼接未经清洗的片段或交给会重新解释字符串的插件，可能破坏先前的安全保证。分片应在正确层重组，不能“各片清洗后拼 HTML”。
- **XML**禁用不需要的 DTD、实体展开与外部资源解析，再检查根元素、允许字段、类型及约束；不要把 XML 标签当成可信指令，也不要靠正则匹配闭合标签。本例拒绝 DTD、自定义实体声明及外部引用，保留 `&lt;`、`&amp;` 等预定义实体和合法字符引用；生产还需按所用 parser 设置大小、深度、CPU/时间等限制。

自动补引号、补结束标签、删尾逗号只能产生一个另有来源标记的新候选，不得据此把原截断结果视为成功或执行动作。对机器提交，本例直接拒绝半截/畸形输入；重新生成、人工修订也必须经过相同校验与授权门槛。

### 4. 可复跑的分片模拟

以下固定 **Python 3.11.8 + defusedxml 0.7.1**，于 **2026-09-15** 本地运行；只使用自编文本，没有模型/API 请求或业务动作。教学协议 v1 每帧是一个 UTF-8 单行 JSON 对象，尾随 LF；字符串内换行必须由 JSON serializer 转义。帧有连续整数 seq，以及 delta/text 或 done/finish 字段。一个 Receiver 只服务一个请求的一个 attempt，控制事件由可信适配器产生。

此协议不实现 SSE、多 choice/tool 并行、网络重连或供应商重试保证；重复/跳号直接失败。它要求成功 done 后不再有数据，并由调用者在逻辑流结束时调用 finish。总输入限制为 8192 bytes、每帧最多 2048 bytes（不含 LF）、内层内容最多 1024 个 Python 字符；示例业务字段 answer 为 1–120 字符、days 为整数 1–30。生产另需截止时间、取消、背压和按请求清理；这些上限不是性能测试结论。

`preview_html_text()` 可在任意完整 delta 后展示，即使内层 JSON 字符串或 XML 标签尚未闭合。示例用同一文本对比 JSON/XML：内容每 5 字符分片、网络每 7 字节分片；最终二者都还原为相同字段。解析 XML 后只映射允许字段为数据，不把原文插入 DOM。

```python
import html
import json
from defusedxml.ElementTree import fromstring


def strict_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError("non-JSON constant: " + value)

    return json.loads(text, object_pairs_hook=unique, parse_constant=nonfinite)


def validate_result(value):
    if type(value) is not dict or set(value) != {"answer", "days"}:
        raise ValueError("result fields")
    if type(value["answer"]) is not str or not 1 <= len(value["answer"]) <= 120:
        raise ValueError("answer must be 1..120 characters")
    value["answer"].encode("utf-8", errors="strict")  # 拒绝孤立 surrogate。
    if type(value["days"]) is not int or not 1 <= value["days"] <= 30:
        raise ValueError("days must be an integer in 1..30")
    return value


def parse_result(text, format):
    if format == "json":
        return validate_result(strict_json(text))
    root = fromstring(text, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    children = list(root)
    if root.tag != "result" or root.attrib or [c.tag for c in children] != ["answer", "days"]:
        raise ValueError("XML shape")
    if (root.text or "").strip() or any(c.attrib or len(c) or (c.tail or "").strip() for c in children):
        raise ValueError("XML mixed content or attributes")
    days = children[1].text or ""
    if days not in {str(i) for i in range(1, 31)}:
        raise ValueError("XML days")
    return validate_result({"answer": children[0].text or "", "days": int(days)})


class Receiver:
    # 教学协议 v1：UTF-8 单行 JSON 事件 + LF；不是 SSE/供应商 SDK。
    def __init__(self, format):
        if format not in {"json", "xml"}:
            raise ValueError("unsupported format")
        self.format, self.state = format, "receiving"
        self.buffer, self.text = b"", ""
        self.sequence, self.received, self.done = 0, 0, False

    def feed(self, chunk):
        try:
            if self.state != "receiving" or type(chunk) is not bytes or (self.done and chunk):
                raise ValueError("unexpected data/state")
            self.received += len(chunk)
            if self.received > 8192:
                raise ValueError("wire budget exceeded")  # 总字节上限，不是 Token。
            self.buffer += chunk
            while b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                if not 0 < len(line) <= 2048 or self.done:
                    raise ValueError("invalid frame")
                event = strict_json(line.decode("utf-8", errors="strict"))
                if type(event) is not dict or type(event.get("seq")) is not int or event["seq"] != self.sequence:
                    raise ValueError("frame sequence")
                if event.get("type") == "delta" and set(event) == {"seq", "type", "text"}:
                    part = event["text"]
                    if type(part) is not str:
                        raise ValueError("delta type")
                    part.encode("utf-8", errors="strict")
                    if len(self.text) + len(part) > 1024:
                        raise ValueError("payload budget exceeded")  # Python 字符数。
                    self.text += part
                elif event.get("type") == "done" and set(event) == {"seq", "type", "finish"}:
                    if event["finish"] != "stop":
                        raise ValueError("unsuccessful terminal event")
                    self.done = True
                else:
                    raise ValueError("frame schema")
                self.sequence += 1
            if len(self.buffer) > 2048:
                raise ValueError("unfinished frame too large")
        except Exception:
            self.state = "failed"
            raise

    def preview_html_text(self):
        # 仅适用于 HTML 文本节点内容；浏览器也可直接用 textContent。
        return html.escape(self.text, quote=True)

    def finish(self):
        try:
            if self.state != "receiving" or self.buffer or not self.done:
                raise ValueError("incomplete or failed stream")
            result = parse_result(self.text, self.format)
            self.state = "ready"
            return result  # 只交付已校验数据，不执行退款、工具或数据库写入。
        except Exception:
            self.state = "failed"
            raise


def encode_frames(parts, finish="stop"):
    events = [{"seq": i, "type": "delta", "text": part} for i, part in enumerate(parts)]
    events.append({"seq": len(parts), "type": "done", "finish": finish})
    return b"".join((json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
                    for e in events)


def example():
    expected = {"answer": '退款 <b>说明</b> & "条款" 🧾', "days": 7}
    payloads = {
        "json": json.dumps(expected, ensure_ascii=False, separators=(",", ":")),
        "xml": '<result><answer>' + html.escape(expected["answer"]) + '</answer><days>7</days></result>',
    }
    results = {}
    for format, payload in payloads.items():
        # 内容每5字符一个delta；网络每7字节交付，允许拆开UTF-8字符。
        wire = encode_frames([payload[i:i + 5] for i in range(0, len(payload), 5)])
        receiver = Receiver(format)
        for offset in range(0, len(wire), 7):
            receiver.feed(wire[offset:offset + 7])
        result = receiver.finish()
        assert result == expected
        results[format] = {"state": receiver.state, "value": result,
                           "safe_answer_text": html.escape(result["answer"])}
    return results


if __name__ == "__main__":
    print(json.dumps(example(), ensure_ascii=False, indent=2))
```

实际输出中两种格式均为 `state="ready"`，value 为 `{"answer": "退款 <b>说明</b> & \"条款\" 🧾", "days": 7}`；HTML 文本节点内容为 `退款 &lt;b&gt;说明&lt;/b&gt; &amp; &quot;条款&quot; 🧾`。显示的是标签字符，不是一个可执行/可解释的 `<b>` 元素。finish 只返回通过本例结构及字段规则的数据；保存、发送或退款动作还须进入应用的当前授权、业务事实核验及幂等提交层。

验证附件进一步枚举网络字节切点和内容切点，并覆盖以下结果；“恢复”指收到剩余真实分片后还原，不是猜测缺失数据：

| 输入情形 | 暂态与终态判断 |
| --- | --- |
| JSON 字符串、转义中间分片；XML `<answer>` 或实体引用中间分片；UTF-8 字节切开 | 收齐外层帧才更新预览，内层保留原始内容；真实余片及成功 done 到达后完整解析通过 |
| 内容已是完整 JSON，但没有成功 done；帧最后的 LF 丢失；只收到半个字段或标签 | 可以保留失败草稿，finish 拒绝，不返回已校验结果 |
| 语法错误、重复 JSON key、额外文档、days 为 bool/float/字符串/越界值、XML 错配标签、DTD 或自定义实体 | 即使收到 done 也拒绝；不做自动修补 |
| 外层事件畸形、序号重复/跳号、done 后多余数据、非法 UTF-8、孤立 surrogate、资源超限 | 进入 failed，后续补片不能把这个 Receiver 恢复为 ready |

这里验证的是教学状态机、解析及文本转义。未测试真实供应商的流协议、浏览器富文本组件、生产吞吐或外部动作执行；实际接入要单独验证适配器和渲染链。

## 延伸 / 追问

**追问 1：最后一个 `}` 已到达，为什么不能立即执行工具？**

它可能只是嵌套对象的结束，后面还有额外数据、错误事件或最终失败状态。先按协议确认相应结果的成功边界，再完整解析、检查字段和当前权限；本例要求整次逻辑流成功结束，返回结构化数据也不等于已获行动授权。

**追问 2：怎样更早显示 JSON 中的 answer 字段，又不误提交 days？**

可以用增量解析器暴露带完整性标记的字段视图，或由可信封装单独发送展示 delta；处理转义、嵌套和字段完成状态，并让数字及业务字段在终态前保持 provisional。不能对半截字符串用正则截取或给临时数值赋予最终含义。

**追问 3：断线后重放同一段事件，按 seq 去重就够了吗？**

还要区分请求/attempt/内容块身份、保存已确认位置、检测同序号不同内容，并按协议决定续传还是重启；终态副作用需要独立幂等键及状态查询。这里的严格序号只用于拒绝异常，不构成断线恢复或 exactly-once 保证。

## 常见误区

- **“JSON 必须全文到齐才能让用户看到任何东西。”** 可以安全预览或增量展示；终态完整性与操作权限另行控制。
- **“XML 天然安全，闭合标签就是正确结果。”** 文档结构、Schema、实体/外部资源策略和业务语义都要验证。
- **“网络 chunk、事件帧和内容字段是同一个边界。”** 三者可能交错切分，必须分层重组。
- **“补齐半截数据后 parse 成功，就能提交。”** 修补不能证明原流成功结束、缺失值正确或用户已授权。
- **“每片先转成 HTML，最后拼起来就安全。”** 上下文和边界会改变解释；按完整的解析/清洗契约渲染，纯文本优先走文本节点。

## 参考

- 课程线索：洛小山《AI 产品从入门到精通》learn-ai，固定 commit `5a933d287dd5074cc1543cb849146f3261d47521`：[slides/6-0b.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/6-0b.html)、[slides/6-3.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/6-3.html)、[slides/6-4.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/6-4.html)、[slides/9-9.html](https://github.com/itshen/learn-ai/blob/5a933d287dd5074cc1543cb849146f3261d47521/slides/9-9.html)。只作选题线索；未沿用其“JSON 只能等全文/XML 天然适合流式”等绝对化判断，正文、样本和代码独立编写，未搬运 AGPL 素材。
- IETF [RFC 8259](https://www.rfc-editor.org/rfc/rfc8259)（2017-12）：JSON 语法、转义、重复成员名及 Unicode 互操作边界；[RFC 7464](https://www.rfc-editor.org/rfc/rfc7464)（2015-02）：JSON text sequence 的 RS/LF framing 与截断讨论，本文未将教学 LF 协议冒充该标准。
- W3C [Server-Sent Events Recommendation, 2015-02-03](https://www.w3.org/TR/2015/REC-eventsource-20150203/)：“Parsing an event stream”“Interpreting an event stream”的 UTF-8、行和事件分隔规则；只用于说明分层，不据此推导任何 LLM 供应商终态含义。
- [CommonMark 0.31.2](https://spec.commonmark.org/0.31.2/)：fenced code blocks、HTML blocks 与 raw HTML；W3C [XML 1.0 Fifth Edition, 2008-11-26](https://www.w3.org/TR/2008/REC-xml-20081126/)：良构文档、实体和转义的语法边界。
- CPython v3.11.8，commit `db85d51d3ea4adfc6147d6af400e167659689eed`：[json 文档](https://github.com/python/cpython/blob/db85d51d3ea4adfc6147d6af400e167659689eed/Doc/library/json.rst) 的 object_pairs_hook、parse_constant 与默认宽松项；[html 文档](https://github.com/python/cpython/blob/db85d51d3ea4adfc6147d6af400e167659689eed/Doc/library/html.rst) 的 escape。示例主动拒绝重复键、非有限常量和不符合字段类型的值。
- defusedxml v0.7.1，commit `ebff1b493751e2f0775314bdd4188d64f07ea184`：[README](https://github.com/tiran/defusedxml/blob/ebff1b493751e2f0775314bdd4188d64f07ea184/README.md)、[ElementTree.py](https://github.com/tiran/defusedxml/blob/ebff1b493751e2f0775314bdd4188d64f07ea184/defusedxml/ElementTree.py)：DTD、实体和外部引用的禁止开关；不是完整的业务 Schema validator。
- DOMPurify v3.2.6，commit `32f765e632ff34eebf5e08128ae1ff8f0d0bbe7a`：[README](https://github.com/cure53/DOMPurify/blob/32f765e632ff34eebf5e08128ae1ff8f0d0bbe7a/README.md)，特别是清洗后修改内容可能破坏安全效果的边界。此固定版本用于追溯讨论，不是推荐生产长期锁定旧 sanitizer；上线需评估当前维护版本、配置和实际 DOM 链。

来源核实与模拟运行日期：**2026-09-15**。未连接真实模型服务，未使用真实用户数据，未执行外部动作。
