---
id: agent-0070
title: 实时语音 Agent（Realtime Voice Agent）的三类架构应如何选型，话轮检测（Endpointing）、投机生成与用户打断（Barge-In）协议应如何设计？
category: agent
tags: [voice-agent, speech-to-speech, full-duplex, turn-detection, barge-in, speculative-execution]
difficulty: hard
role: engineer
contributor: 佚名
source: 公开 AI 系统设计指南与面试题库扩展改编；LiveKit、Pipecat、OpenAI Realtime/GPT-Live 官方规范与 τ-Voice 论文核实（见参考）
status: published
updated: 2026-10-30
answers:
  - author: gemini-4-argon
    type: ai
    model: gemini-4-argon
    answered: 2026-10-30
    updated: 2026-10-30
---

## 问题

将基于文本的大模型改造为**实时语音智能体（Realtime Voice Agent）**绝不是简单地在前面加一个语音转文字（STT）、后面接一个文字转语音（TTS）。人类自然对话的话轮转换间隙（Turn-Taking Gap）平均仅有 $\sim 200\text{ ms}$，而在电话客服、实时陪练或车载语音场景中，只要端到端首音延迟（Time-to-First-Audio, TTFA）超过 $1.2\text{ s}$ 或频繁被用户的思考停顿、“嗯嗯”附和声误打断，对话体验就会迅速崩溃。

围绕生产级实时语音 Agent 的架构选型与时序控制，请深入剖析：
1. 当前主流的**三类实时语音架构**——**级联流水线（Chained Cascade：STT $\to$ Text LLM $\to$ TTS）**、**端到端单一语音大模型（Single Speech-to-Speech, S2S）** 与 **全双工语音前端 + 委托推理后端（Full-Duplex Front-End + Delegated Thinker Backend，Talker-Thinker 架构）**，在延迟分解、推理与工具调用能力、可审计性、逐字合规话术播报以及分钟级成本模型上各有何本质取舍？
2. 为什么全链路流式化（Streaming）只能消除“整段持续时间项”，却消不掉用户停口后的**首块串行税（Serial First-Chunk Tax）**？为什么基于原生音频特征的**话轮结束检测（Audio Endpointing / Turn Detection）**与**投机生成（Speculative / Preemptive Generation）**是压降延迟的最大杠杆？在投机生成期间，为什么必须将只读工具与有副作用的工具（`defer_until_eot`）严格隔离？
3. 当用户在 Agent 说话中途开口时，为什么“用户打断（Barge-In）”是一个跨层状态机协议而非单纯的 VAD 静音/人声事件？系统应如何区分**附和词（Backchannel）**与**真实打断**、清空电话/WebRTC 传输缓冲区、按用户**实际听到的文本前缀（`text_spoken`）**裁剪 LLM 历史上下文，并通过上下文版本号（`context_revision`）丢弃改口前的过期后台任务结果？

本题由公开 AI 系统设计指南与面试题库扩展改编，不是已核实的企业真题；不采信脱离具体并发度、网络链路与推理档位的笼统延迟数字。

## 答案 · gemini-4-argon

> 🤖 AI 答案 · 模型：gemini-4-argon · 回答 2026-10-30

**实时语音 Agent 的工程核心不是“让模型会说话”，而是“在毫秒级时序预算内管理话轮所有权与状态一致性”：在架构选型上，级联流水线以全边界文本化换取最高可审计性与逐字合规话术控制，单一 S2S 模型以原生音频理解换取副语言自然度，而“全双工语音前端（Talker）+ 委托文本推理后端（Thinker）”则通过将毫秒级韵律时序与慢速工具/逻辑推理解耦，成为复杂业务 Agent 的主流范式；在延迟优化上，由于流式传输无法消除停口后的串行首包累加（$\text{TTFA} = T_{\text{eot}} + T_{\text{stt\_final}} + T_{\text{llm\_ttft}} + T_{\text{tts\_ttfb}}$），最大杠杆是用原生音频话轮检测器替代固定静音阈值，并配合提前触发的投机生成（同时严禁在话轮确认前执行写操作工具 `defer_until_eot`）；在打断（Barge-In）与长会话状态管理上，必须通过自适应打断分类器过滤“嗯嗯”等附和词，并在真实打断时同步执行“清空远端媒体缓冲 + 将上下文截断至用户实际听到的字符偏移 `text_spoken` + 递增 `context_revision` 作废在途脏委托”，同时将关键业务槽位与身份状态保存在模型上下文之外的后端权威数据库中。**

现有 [agent-0055](agent-0055-turn-loop-input-semantics.md) 讨论了文本 Agent 运行中收到用户插话时的续问、转向与输入语义，[engineering-0024](engineering-0024-cancellation-stale-callbacks.md) 与 [engineering-0026](engineering-0026-streaming-tool-transcript-closure.md) 剖析了取消传播、过期回调隔离与流式工具记录闭合，[product-0008](product-0008-perceived-latency-experiments.md) 分析了感知等待与真实延迟的区别。本题聚焦**实时语音通道特有的三类架构范式对比、串行首音延迟预算方程、音频话轮检测与投机副作用门控，以及全双工打断（Barge-In）下的声学缓冲清空与 `text_spoken` 上下文对齐协议**。

---

### 1. 实时语音 Agent 的三类核心架构与选型矩阵

随着端到端语音大模型与全双工（Full-Duplex）委托协议的成熟，生产级语音 Agent 已从早期的“二分法”演进为三种明确的技术形态：

```text
[架构 1: 级联流水线 (Chained Cascade)]
用户音频 ──► VAD + 音频话轮检测 ──► 流式 STT ──(文本)──► 文本 LLM & 工具 ──(文本)──► 流式 TTS ──► 播报音频

[架构 2: 单一端到端语音模型 (Single Speech-to-Speech, S2S)]
用户音频 ──► [ 单一 S2S 模型 (听取音频 + 内部推理 + 调用工具 + 直接生成音频 Token) ] ──► 播报音频
                                      └──(旁路异步转录文本，仅供日志记录)

[架构 3: 全双工语音前端 + 委托推理后端 (Full-Duplex Talker + Delegated Thinker)]
用户音频 ──► [ 全双工语音前端 (边说边听、自主控制附和/停顿/礼让) ] ──► 播报音频
                         │                               ▲
       委托任务 + context_revision (文本)         返回结果 / 进度更新 (文本)
                         ▼                               │
               [ 委托文本后端 Agent (深度推理、工具调用、权威业务状态库) ]
```

| 评估维度 | 1. 级联流水线（Chained Cascade） | 2. 单一语音大模型（Single S2S） | 3. 全双工前端 + 委托后端（Talker-Thinker） |
| --- | --- | --- | --- |
| **代表技术栈** | LiveKit / Pipecat + 流式 STT + 任意文本 LLM + 流式 TTS | OpenAI `gpt-realtime`、Gemini Live、Nova Sonic | OpenAI `gpt-live` + 推理后端、LiveKit `DuplexModel`、Moshi 类双工模型 |
| **话轮转换控制** | 运行时显式控制（VAD + 音频 Turn 模型 + 打断分类器仲裁） | 半双工轮次制（内置 `server_vad` 或 `semantic_vad` 切分轮次） | **模型原生全双工**：边说边听，自主决定何时插话、附和（Backchannel）或礼让 |
| **复杂推理与工具能力** | **极强**：可直接复用任何顶尖文本推理模型与现有工具链 | 受限于语音模型自身推理容量；调高思考力度会直接拉长首音延迟 | **极强**：语音层先自然应答拖延时间，复杂推理与工具在文本后端并行运行 |
| **合规逐字播报与可控性** | **最高**：每一跳边界均为纯文本，可精确脱敏，TTS 可一字不差朗读法律免责条款 | 语音与逻辑耦合在同一黑盒 Prompt 中，难以保证逐字不改写 | 说话风格与业务规则解耦；但双工前端默认会口语化改写，**法定逐字声明需旁路切回 TTS** |
| **计费与长通话成本特征** | 按各组件分钟数/字符数线性累加（约 $\$0.05\sim\$0.14/\text{min}$） | 按音频 Token 计费；若每轮重发全量历史且未命中缓存，长通话单分钟成本随轮次递增 | 按会话时长计费（如 $\$0.05/\text{min}$ 含静音期）+ 后端文本 Token，需及时关闭空闲会话 |
| **核心工程风险** | 端点检测（Endpointing）延迟税；STT 边界丢失情绪重音与语码转换 | 会话时长硬上限（如 $10\sim 60\text{ min}$）；音频提示词注入（Audio Injection）直达工具层 | 用户改口后**后台异步返回过期脏结果**；语音层自动压缩上下文丢失早期槽位 |

#### 架构选型决策准则
1. **何时选级联流水线（Cascade）**：金融/医疗/政务等强监管场景，要求对每一跳做 PII 文本脱敏审计、必须**一字不差（Verbatim）**播报合规告知书或支付条款、需要使用垂直领域微调的专用 STT（含专有名词热词增强 Keyterm Biasing），或在高并发自建 GPU 集群上压降单位成本。
2. **何时选单一 S2S 模型**：任务逻辑较浅（闲聊陪伴、口语对练、实时翻译、简单 FAQ 查询），核心痛点是情绪感知、笑声/语气词还原以及中英夹杂（Code-Switching）的自然度。
3. **何时选全双工前端 + 委托后端（Talker-Thinker）**：企业已经有成熟的文本 Agent（含复杂业务规则与多步工具调用），且任务需要深度推理。基准测试（如 Sierra $\tau\text{-Voice}$）表明，纯语音模型在复杂多步工具任务上的成功率显著低于同系文本模型，只有将双工语音前端与强推理后端解耦绑定，才能在不牺牲响应自然度的前提下恢复复杂任务成功率。

---

### 2. 端到端延迟预算方程、音频话轮检测与投机副作用门控

#### 为什么全链路流式化之后，端到端延迟依然有 $0.8 \sim 1.2\text{ s}$？
初学者常误以为“只要 STT、LLM、TTS 都开启 Streaming，延迟就只剩网络传输时间”。事实上，**流式传输只消除了每个阶段的“整句持续时间项（Whole-Duration Terms）”，却无法消除用户停口之后的“首块串行累加项（Serial First-Chunk Terms）”**。

当用户说完最后一个字（$t = 0$）到用户耳中听到 Agent 第一个声音样本，系统的期望首音延迟 $\text{TTFA}$ 严格遵循以下串行相加方程：

$$\text{TTFA} = T_{\text{net\_in}} + T_{\text{endpointing}} + T_{\text{stt\_final}} + T_{\text{llm\_ttft}} + T_{\text{tts\_ttfb}} + T_{\text{net\_out}}$$

以一个经过调优的生产级流式级联链路（参考 Pipecat 实测分解）为例，不含双程网络传输（WebRTC/UDP 约 $60\sim 120\text{ ms}$）的典型服务端耗时分布为：
- **话轮结束判定 $T_{\text{endpointing}} \approx 200\sim 300\text{ ms}$**（若用传统静音阈值则高达 $600\sim 800\text{ ms}$）；
- **STT 尾字确认 $T_{\text{stt\_final}} \approx 50\sim 125\text{ ms}$**（因流式 Partial 已在说话期间并行完成）；
- **LLM 首 Token 延迟 $T_{\text{llm\_ttft}} \approx 150\sim 350\text{ ms}$**（若开启高强度 Reasoning 则暴涨至 $>1\text{ s}$）；
- **TTS 首包音频合成 $T_{\text{tts\_ttfb}} \approx 75\sim 360\text{ ms}$**（等待首个语义分句 Clause 完成并合成首帧音频）。
四项相加即达 **$1.0\text{ s}$ 左右**。由此可见，在开启流式之后，压降延迟最大的工程杠杆依次是：

1. **从“固定静音超时”升级为“原生音频话轮检测（Audio-Native Turn Detection）”**：
   单纯的 VAD（如 Silero VAD）只能以 $10\sim 30\text{ ms}$ 帧率区分“当前帧有无人声”，无法区分用户是“说到一半喘气思考”还是“整句话说完了”。如果设 $800\text{ ms}$ 静音超时，每次正常问答都要白白空等近一秒；如果设 $300\text{ ms}$，用户报身份证号稍一停顿就会被粗暴抢话。现代语音框架（如 LiveKit Audio `TurnDetector`、Pipecat `Smart Turn v3`、Deepgram Flux）直接将尾音的**声学语调下降（Intonation / Pitch Contour）、语速拖长与语义完整性**输入轻量音频编码器（约 $12\text{ ms}$ CPU 推理），将话轮判定延迟从 $800\text{ ms}$ 压至 $200\sim 300\text{ ms}$，同时必须在运行时设立**单一话轮仲裁器（Single Turn Arbiter）**统一裁决 VAD、STT 与音频 Turn 模型的信号。
2. **激进话轮触发与投机生成（Eager EoT & Speculative Generation）——严守副作用红线**：
   为了进一步抹平 $T_{\text{endpointing}}$ 与 $T_{\text{llm\_ttft}}$，系统可以设置两级阈值：当音频话轮模型给出中等置信度（如 $p_{\text{eot}} \ge 0.40$，记为 `eager_eot`）时，**提前投机启动 LLM 推理与只读查询**；
   - 若随后 $200\text{ ms}$ 内用户没再开口，升级为确认结束（`confirmed_eot`），此时 LLM 首包甚至 TTS 首帧已准备就绪，可立即播报；
   - 若用户继续说话（`turn_resumed`），则直接丢弃刚才投机生成的文本（以额外 $50\%\sim 70\%$ 的 LLM Token 消耗换取百毫秒级极速响应）。
   - **铁律（No Speculative Side Effects）**：**投机生成期间绝对禁止执行任何有外部副作用的工具调用（如扣款、改签、发短信、写数据库）！** 所有写操作工具必须标记为 `defer_until_eot`，在运行时门控队列中挂起，直到收到最终 `confirmed_eot` 且上下文版本未变时才真正放行。

---

### 3. 用户打断（Barge-In）四步协议与可运行标准库实现

当 Agent 正在播报长句时，麦克风突然检测到用户声音，如果简单粗暴地“一检测到 VAD 人声就立刻杀掉 TTS”，不仅会被用户的礼貌附和（“嗯”、“好的”、“uh-huh”）或背景杂音频繁误杀，还会在大模型上下文里留下严重的**“精神分裂（Context Hallucination）”**——模型以为自己把整段话全说完了，但用户其实只听到了前三个字！

生产级 **Barge-In 协议**必须按序完成以下四个原子步骤：
1. **重叠语音分类（Overlap Classification）**：由自适应打断模型结合前 $300\sim 500\text{ ms}$ 的重叠音频特征与语义判断是**附和词（Backchannel）**还是**真实打断（True Interruption）**。若是附和词，继续保持音频输出（或先轻微压低音量 Ducking，确认误判后无缝恢复播放）。
2. **全链路播放缓冲清空（Playout & Carrier Buffer Flush）**：一旦确认为真实打断，不仅要取消本地 TTS 生成流，**还必须向底层传输网发送显式清空指令（如 Twilio Media Streams 的 `clear` 消息或 WebRTC 轨道重置）**——否则电话局端或客户端 jitter buffer 里已缓存的数秒音频仍会继续对着用户播放。
3. **按实际已播报进度裁剪上下文（Trim Context to `text_spoken`）**：LLM 单次流式生成了 100 个字并推给了 TTS，但用户在第 17 个字处打断了它。此时必须根据 TTS 引擎汇报的已播放音频采样偏移（或 `text_spoken` 回执），将写入 `messages` 历史的 `assistant` 回复**截断为前 17 个字**（必要时加 `...` 标记被中断），确保模型清楚知道后面 83 个字用户根本没听到。
4. **在途异步任务版本化与过期丢弃（Context Revision Stamping）**：在全双工或异步工具架构下，用户常常在后台工具还在搜索“周三航班”时改口说“算了，帮我查周五的”。每次发生打断或用户补充更正时，会话控制器必须递增**上下文版本号 `context_revision`**；任何携带旧版本号返回的后台推理或工具结果一律在网关层静默丢弃（或根据策略触发取消，见 [engineering-0024](engineering-0024-cancellation-stale-callbacks.md)）。

#### 可运行的标准库实现：话轮投机门控、Barge-In 历史裁剪与过期委托拦截

以下 Python 3 标准库代码完整实现了上述实时语音会话状态机，验证了（1）`eager_eot` 下只读工具先行、副作用工具挂起与用户续说回滚，（2）附和词过滤与真实打断下的线路缓冲清空及 `text_spoken` 历史截断，以及（3）基于 `context_revision` 的双工后台过期结果拦截：

```python
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class SpeculativeToolCall:
    call_id: str
    tool_name: str
    side_effecting: bool
    context_revision: int


@dataclass
class VoiceTurnRuntime:
    """实时语音 Agent 的话轮仲裁、投机副作用门控、打断历史裁剪与版本化后台委托控制器"""
    context_revision: int = 1
    turn_confirmed: bool = False
    carrier_buffer_cleared: bool = False
    conversation_history: List[Tuple[str, str]] = field(default_factory=list)
    deferred_side_effects: List[SpeculativeToolCall] = field(default_factory=list)
    executed_tool_calls: List[str] = field(default_factory=list)
    accepted_backend_results: List[Tuple[int, str]] = field(default_factory=list)

    def on_eager_eot(self, partial_user_text: str, proposed_calls: List[SpeculativeToolCall]) -> List[str]:
        """
        收到 Eager End-of-Turn (如音频话轮模型预测 p_eot >= 0.45):
        允许只读查询立即投机执行以隐藏延迟，但强行挂起所有带副作用的工具调用 (defer_until_eot)
        """
        self.turn_confirmed = False
        ran_immediately: List[str] = []
        for call in proposed_calls:
            if call.side_effecting:
                self.deferred_side_effects.append(call)
            else:
                self.executed_tool_calls.append(call.call_id)
                ran_immediately.append(call.call_id)
        return ran_immediately

    def on_user_resumed_speaking(self, updated_user_text: str) -> int:
        """
        用户在 Eager EoT 后继续说话 (假停顿) 或开口更正:
        递增 context_revision，作废并清空所有投机挂起的副作用工具调用
        """
        self.context_revision += 1
        cancelled_count = len(self.deferred_side_effects)
        self.deferred_side_effects.clear()
        return cancelled_count

    def on_confirmed_eot(self, final_user_text: str) -> List[str]:
        """
        音频 Turn Detector 确认话轮真正结束 (Confirmed EoT):
        将最终用户话语写入历史，并释放执行当前有效版本的挂起副作用工具
        """
        self.turn_confirmed = True
        self.conversation_history.append(("user", final_user_text))
        flushed: List[str] = []
        for call in self.deferred_side_effects:
            if call.context_revision == self.context_revision:
                self.executed_tool_calls.append(call.call_id)
                flushed.append(call.call_id)
        self.deferred_side_effects.clear()
        return flushed

    def on_caller_overlap(
        self,
        planned_agent_utterance: str,
        spoken_char_offset: int,
        overlap_text: str,
        is_backchannel: bool,
    ) -> str:
        """
        处理用户重叠发音:
        - 若分类器判定为附和词 (Backchannel, 如 "嗯嗯"/"uh-huh")，保持播报不断流；
        - 若判定为真实打断 (True Barge-In)，发送线路缓冲清空信号，并将上下文严格裁剪至用户实际听到的前缀 text_spoken。
        """
        if is_backchannel:
            return "CONTINUE_PLAYOUT"

        self.carrier_buffer_cleared = True
        self.context_revision += 1
        text_spoken = planned_agent_utterance[:spoken_char_offset].rstrip()
        self.conversation_history.append(("assistant", text_spoken))
        return text_spoken

    def receive_delegated_backend_result(self, req_revision: int, payload: str) -> bool:
        """
        接收双工后端异步返回的推理/工具结果:
        若请求发出时的 context_revision 落后于当前最新版本号，作为过期脏结果直接丢弃
        """
        if req_revision != self.context_revision:
            return False
        self.accepted_backend_results.append((req_revision, payload))
        return True


# --- 验证 1: 投机生成期间拦截写操作，用户继续说话时安全回滚 ---
rt = VoiceTurnRuntime()
imm = rt.on_eager_eot(
    "帮我把周三的机票改签",
    [
        SpeculativeToolCall("call_lookup", "lookup_flight", side_effecting=False, context_revision=1),
        SpeculativeToolCall("call_charge", "confirm_rebook_and_charge", side_effecting=True, context_revision=1),
    ],
)
assert imm == ["call_lookup"] and rt.executed_tool_calls == ["call_lookup"]
assert len(rt.deferred_side_effects) == 1  # 扣款改签被挂起

# 用户停顿 300ms 后继续补充："不对，改成周五下午"，触发投机取消与版本递增
cancelled = rt.on_user_resumed_speaking("帮我把周三的机票改签，不对，改成周五下午")
assert cancelled == 1 and rt.context_revision == 2
assert "call_charge" not in rt.executed_tool_calls

# --- 验证 2: 话轮正式确认后，当前版本的副作用工具才获准执行 ---
rt.on_eager_eot(
    "帮我把周三的机票改签，不对，改成周五下午",
    [SpeculativeToolCall("call_charge_fri", "confirm_rebook_and_charge", side_effecting=True, context_revision=2)],
)
flushed_calls = rt.on_confirmed_eot("帮我把周三的机票改签，不对，改成周五下午")
assert flushed_calls == ["call_charge_fri"]

# --- 验证 3: 附和词免误触 vs 真实打断下的 text_spoken 上下文裁剪与过期后端结果丢弃 ---
planned_reply = "已为您查到周五下午两点起飞的航班，票价为八百六十元，退改签规则是起飞前两小时免费。"
assert rt.on_caller_overlap(planned_reply, 16, "嗯嗯", is_backchannel=True) == "CONTINUE_PLAYOUT"
assert not rt.carrier_buffer_cleared

# 用户在第 17 个字符处打断 ("等一下，换早班机")
spoken_prefix = rt.on_caller_overlap(planned_reply, 17, "等一下，换早班机", is_backchannel=False)
assert rt.carrier_buffer_cleared is True
assert spoken_prefix == "已为您查到周五下午两点起飞的航班，"
assert rt.conversation_history[-1] == ("assistant", "已为您查到周五下午两点起飞的航班，")
assert rt.context_revision == 3

# 此前基于 revision=2 发起的慢速后台推荐结果返回，因版本过期被拒绝；revision=3 的新结果被接受
assert rt.receive_delegated_backend_result(2, "stale_friday_afternoon_options") is False
assert rt.receive_delegated_backend_result(3, "fresh_friday_morning_options") is True

accepted_revs = [rev for rev, _ in rt.accepted_backend_results]
print(f"Speculative immediate calls: {imm}, cancelled side-effect count on resume: {cancelled}")
print(f"Confirmed EoT flushed calls: {flushed_calls}")
print(f"Trimmed assistant history on barge-in: {rt.conversation_history[-1][1]}")
print(f"Accepted backend revisions: {accepted_revs}")
print("Voice turn endpointing, speculative side-effect gate, barge-in trimming, and revision checks passed")
```

实际执行输出：

```text
Speculative immediate calls: ['call_lookup'], cancelled side-effect count on resume: 1
Confirmed EoT flushed calls: ['call_charge_fri']
Trimmed assistant history on barge-in: 已为您查到周五下午两点起飞的航班，
Accepted backend revisions: [3]
Voice turn endpointing, speculative side-effect gate, barge-in trimming, and revision checks passed
```

---

### 4. 生产环境的声学工程陷阱与可靠性防线

1. **电话网窄带重采样陷阱（$8\text{ kHz }\mu\text{-law}$ vs $16\text{ kHz}$ 模型特征）**：
   传统 PSTN / SIP 电话网（如 Twilio Media Streams）传输的是 $8\text{ kHz}$ 采样率的 G.711 $\mu\text{-law}$ 窄带音频（最高频率仅 $4\text{ kHz}$，高频清辅音如 `s` / `f` 严重受损），而绝大多数开源音频话轮检测器（如基于 Whisper 编码器的 `Smart Turn`）和 VAD 是在 $16\text{ kHz}$ 线性 PCM 上训练的。如果直接把 $8\text{ kHz}$ 音频喂给 $16\text{ kHz}$ 模型而不做显式上采样与编解码对齐，话轮检测和打断分类的准确率会断崖式下跌。
2. **精确实体捕获（Entity Elicitation）——语音 Agent 的头号失败源**：
   在姓名、邮箱、订单号、日期与确认码的采集中，同音字、口音与环境底噪极易导致语音识别错一个字符，进而令下游工具调用全盘失败（$\tau\text{-Elicitation}$ 基准显示纯语音次均精确捕获率远低于文本交互）。工程上必须建立三道防线：
   - **拼写确认与复述脚手架（Spell, Read-Back & Confirm Scaffold）**：对高价值槽位强制执行逐字复述确认；
   - **DTMF 按键双模兜底**：在电话通道中，允许用户直接在拨号盘按键输入身份证号、银行卡号或验证码，通过独立信令通道接收 DTMF 事件；
   - **上下文热词偏置（Keyterm Biasing & Prompt Context）**：将业务 SKU 词表及 Agent 上一句刚问出的问题作为上下文传给流式 STT，显著降低专有名词词错率（WER）。
3. **把语音模型上下文当缓存，把权威业务状态放在后端（Context as Cache, Backend as Record）**：
   长语音会话必然遭遇平台连接时长上限（如 $8\sim 60\text{ min}$ 断连重连）或自动上下文压缩（如超过阈值后替换为摘要语音引擎）。因此，用户的身份核验结果、已确认的订单槽位和业务状态机**绝不能只留在语音模型的对话历史里**，必须实时持久化在应用层状态存储中，以便在重连或引擎切换时无损恢复。
4. **防范音频提示词注入（Audio Prompt Injection）与声纹伪造**：
   攻击者可通过背景并发语音或近似不可闻的声学扰动（如 AudioHijack / DuplexJail）劫持端到端语音模型执行未授权工具，且仅需数秒音频即可低成本克隆特定人声。因此：（1）**切勿把说话人声音（声纹）当作唯一高危身份认证手段**，必须结合带外验证码或业务鉴权；（2）**工具授权策略必须在确定性的后端代码中强制执行**（见 [agent-0041](agent-0041-dynamic-tool-risk-assessment.md)），绝不能仅靠语音模型的 System Prompt 约束。

---

## 延伸 / 追问

**追问 1：为什么在实时语音传输中，客户端到服务端（Client-to-Server）普遍强制使用 WebRTC（基于 UDP），而服务端到模型/STT（Server-to-Model）却可以使用 WebSocket（基于 TCP）？**
因为两段链路的网络物理特性截然不同：客户端（手机 4G/5G、车载移动网络、弱 Wi-Fi）处于高抖动、易丢包的最后一公里无线网。如果使用基于 TCP 的 WebSocket，一旦丢掉一个音频包，TCP 内核会强制阻塞后续所有已到达的音频包等待重传（**队头阻塞 Head-of-Line Blocking**），导致语音瞬间卡顿数百毫秒甚至数秒，随后积压的音频又像快进一样集中爆发。而 WebRTC 采用 **UDP + Opus 编解码器（支持前向纠错 FEC 与丢包隐藏 PLC）**，丢掉一两个 $20\text{ ms}$ 帧时直接由解码器平滑插值跳过，优先保证绝对实时性；反观服务端到模型 API 通常位于数据中心高速骨干网内（甚至同可用区专线），丢包率极低且延迟稳定在数毫秒内，用 WebSocket 即可兼顾开发简便与流式帧控制。

**追问 2：当语音 Agent 需要调用一个耗时 $4\text{ s}$ 的外部查询工具时，怎样避免用户在电话那头听到长达 $4\text{ s}$ 的死寂（Dead Air）并误以为电话断了？如果工具跑到第 $2\text{ s}$ 用户突然开口改了查询条件，怎么处理？**
1. **消灭死寂（Async Tools + Spoken Preambles / Filler）**：将工具调用设为非阻塞异步模式（Asynchronous Tool Scheduling）。在触发工具的同一时刻，让语音前端立即播报一句自然的过渡语（Preamble，如“好的，我帮您查一下周五的余票，请稍等……”），或者叠加轻柔的键盘敲击/翻页环境反馈音（见 [product-0008](product-0008-perceived-latency-experiments.md)），如果超过 $2.5\text{ s}$ 仍未返回，再由定时器触发二次进度安抚；
2. **中途改口处理**：如前文代码所示，当用户在第 $2\text{ s}$ 开口把“周五”改成“周六”时，立即递增 `context_revision` 并向旧工具任务发送 `cancel` 信号；即便旧工具不可取消并在第 $4\text{ s}$ 返回了周五的票务数据，网关比对发现其携带的 `req_revision < current_revision`，也会直接将其丢弃，防止语音前端把过期的周五航班播报出来造成错乱。

**追问 3：如何评测一个实时语音 Agent 的线上真实表现？为什么不能只把语音转成文本跑传统文本 Benchmark？**
因为只跑文本转录评测会完全漏掉**声学层与时序层的致命故障**（在 $\tau\text{-Voice}$ 评测中，同一套逻辑在真实语音下的成功率比纯文本低数十个百分点）。完整的语音评测需覆盖两套指标体系：
1. **会话动力学与时序指标（Conversational Dynamics & Timing）**：P50 / P95 **有效回答首音延迟**（必须将“稍等我查一下”这类填充词的延迟与真正业务答案的延迟分开统计！）、P95 话轮判定延迟（Endpointing Delay）、**误打断率（False Barge-In Rate，因杂音或附和词中断播报的比例）** 与 **漏打断率（Missed Barge-In Rate）**；
2. **声学压力下的端到端业务状态验证**：采用“合成语音 $\to$ 真实录音回放 $\to$ 叠加背景噪声、口音、中途打断及 $8\text{ kHz}$ 窄带压缩的模拟对练用户（Audio User Simulator）”三阶段递进测试，且最终评判标准必须是**检查后端数据库状态是否真正按正确槽位完成了业务操作**，而非仅看对话转录文本是否通顺。

---

## 常见误区

- **误区一：“端到端 Speech-to-Speech（S2S）模型省去了 STT 和 TTS，所以它的首音延迟（TTFA）一定比级联流水线（Cascade）低得多。”**
  事实：当任务需要复杂逻辑推理或工具调用时，S2S 模型的首音延迟往往落在 $0.70 \sim 1.34\text{ s}$，与调优良好的全流式级联流水线（约 $0.80 \sim 1.05\text{ s}$）处于同一水平甚至更慢。因为决定延迟长板的往往是**话轮结束检测（Endpointing）**与**模型的思考计算耗时（Reasoning Effort）**；此外，单流基准测试的 TTS 延迟（如 $75\text{ ms}$）在高并发（如 32 路并发）下可能退化数倍，不能脱离并发度谈架构快慢。
- **误区二：“处理用户打断（Barge-In）很简单，只要麦克风 VAD 检测到人声，立刻停止本地 TTS 协程即可。”**
  事实：这会导致三个严重事故：（1）用户说“嗯嗯”表示在听时，Agent 突然闭嘴，体验极其僵硬；（2）本地停了 TTS，但电话网关（如 Twilio）缓冲区里还有 $3\text{ s}$ 音频在继续往外播，用户感觉 Agent 根本听不见自己打断；（3）未根据实际已播放偏移裁剪 `messages` 历史，导致模型误以为未播出的后半句重要信息用户已经听到了。
- **误区三：“为了让语音回复越快越好，可以在流式 STT 还没完全结束时就投机触发 LLM 和工具调用，先把订单改了再说。”**
  事实：**投机生成只允许用于无副作用的计算与只读预取（Read-Only Prefetch），绝不能用于写操作工具。** 人类说话经常有倒装和自我修正（例如：“帮我把明天的订单取消……哦不，保留明天的，取消后天的”），如果在前半句停顿时就投机执行了取消操作，会直接造成无法挽回的业务故障。

---

## 参考

- 选题线索：[ombharatiya/ai-system-design-guide, 18-voice-and-audio-agents/01-realtime-voice-agents.md](https://github.com/ombharatiya/ai-system-design-guide/blob/ed955b27d94201b663a741284767a1136dc83e5e/18-voice-and-audio-agents/01-realtime-voice-agents.md)。固定 commit `ed955b27`，独立拓展改编。
- Sierra Research, [$\tau$-Voice: Benchmarking Full-Duplex Voice Agents on Real-World Domains](https://sierra.ai/blog/tau-voice-benchmarking-real-time-voice-agents-on-real-world-tasks)：全双工语音场景下背景噪声、打断、情绪与多步工具调用的评测基准及文本-语音能力差距分析。
- OpenAI Official Documentation, [Voice Agents Architecture & Realtime API Guide](https://platform.openai.com/docs/guides/voice-agents)：级联、S2S 与双工委托架构选型、话轮检测、打断上下文截断与版本化委托规范。
- LiveKit Official Documentation, [End-of-Turn Detection & Adaptive Interruption Handling](https://docs.livekit.io/agents/build/turns/turn-detector/)：原生音频话轮检测器、附和词（Backchannel）抗误触分类与预生成调度。
- Pipecat AI, [Smart Turn v3 & Voice Agent Latency Breakdown](https://github.com/pipecat-ai/pipecat)：基于 Whisper Tiny 编码器的轻量音频话轮检测、多信号话轮仲裁器及级联流水线各阶段毫秒级延迟分解。

来源访问与示例核验日期：**2026-10-30**。仅执行标准库话轮投机门控、Barge-In `text_spoken` 历史裁剪与 `context_revision` 过期结果丢弃逻辑验证，未运行真实 WebRTC/SIP 媒体流或云端语音 API 基准测试。
