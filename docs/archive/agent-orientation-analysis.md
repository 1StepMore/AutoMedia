# AutoMedia 面向 Agent 架构分析

> 生成日期: 2026-07-13
> 分析目的: 评估代码库是否一致地贯彻"面向 Agent 的全自动内容生产"定位，
> 识别并制定移除不合理僵化/硬编码结构的路线图，
> 代之以真正的 LLM 驱动 + Agent 优先模式。

> **状态说明 (2026-07-15):** 本文的分析和建议已被 **D3 Gap Closure** 部分执行。
> ✅ **已实施:** 决策层确定性 Agent 移除 (~9,500 LOC 死代码: tenant/、license/、sop/、platform_drafts/、decision 层的 orchestrator/dependency/preflight/build/scale/strategy)、
> MCP 工具 `run_brand_strategy` + `run_pipeline_from_strategy` 上线、D0 Gate 移除、CLI 状态管理移除。
> ❌ **尚未实施:** G0/G2 门 LLM 化改造、pool/scorer LLM 化、asset_library 简化、hitl/config 精简。
> 如需跟进未实施项，请参考 [D3 Gap Closure Plan](.omo/plans/d3-gap-closure.md) 中的 Future Work 章节。

---

## 目录

1. [核心原则：什么是"面向 Agent"](#1-核心原则)
2. [已确认结论：决策层的重构方案](#2-已确认结论决策层重构方案)
3. [MCP vs Skills vs 混合方案评估](#3-mcp-vs-skills-vs-混合方案评估)
4. [全代码库评估矩阵](#4-全代码库评估矩阵)
5. [各模块详细分析](#5-各模块详细分析)
6. [路线图：推荐的实施顺序](#6-路线图)

---

## 1. 核心原则

### 1.1 "面向 Agent"的定义

一个"面向 Agent"的内容生产系统满足以下条件：

| 原则 | 含义 | 反例 |
|------|------|------|
| **所有接口对所有 Agent 可用** | 所有功能通过 MCP（最通用）或 SDK/CLI（后备）暴露；不依赖特定 Agent 类型 | 将功能限制在"仅 OpenCode"的 skills |
| **LLM 做判断，代码做执行** | AI Agent 的 LLM 或系统的 LLM 客户端负责创造性/判断性任务；确定性代码负责安全/基础设施/编排 | 2,200 LOC 的模板代码冒充"Agent" |
| **无状态优先** | Agent 不需要手动管理状态文件（YAML、JSON 或 SQLite）来跟踪自己的工作流 | `.solution-state.yaml` 状态管理 |
| **可覆盖** | 提示词、规则和阈值可通过配置覆盖，而非硬编码 | 硬编码 SWOT 分析、人物画像名称 |
| **结构化输出** | LLM 调用返回经过验证的模型（Pydantic），而非自由文本 | `llm_complete()` 返回原始字符串供下游脆弱解析 |
| **不限制 Agent** | 无许可/租户/许可限制 | 只有特定用户才能使用该功能 |

### 1.2 这里的"Agent"指的是谁？

AutoMedia 在设计上支持**两类 Agent**：

1. **外部 AI Agent**（OpenCode、Claude Code、Codex CLI、Cline、Hermes Agent 等）——通过 MCP 或 CLI 使用系统。他们可能在自己的 LLM 下运行，也可能委托给 AutoMedia 的 LLM。
2. **内部决策节点**（系统中称为"Agent"）——目前是确定性的 Python 类，应该利用 LLM。

**关键洞察**：当外部 Agent 通过 MCP 使用系统时，内部"Agent"应该调用 LLM，而不是使用模板。否则，外部 Agent 必须*自己*弄清本应由系统提供的内容。

---

## 2. 已确认结论：决策层重构方案

### 2.1 诊断

**决策层（`src/automedia/decision/` - 3,681 LOC）存在根本性的架构缺陷。**

| 问题 | 严重性 | 细节 |
|------|--------|------|
| **没有 LLM 调用** | 🔴致命 | 12 个"Agent"中零个调用`llm_complete()`。全部是 100% 确定性模板代码。 |
| **身份造假** | 🔴致命 | 类名为"BrandPositioningAgent"、"AudienceSegmentationAgent"，但实现是 f-string 拼接字符串。例如，`_build_vision()` 返回"成为最值得信赖的 {idea.lower()} 生态系统"。 |
| **与管道断开** | 🟡严重 | `DecisionOrchestrator` 在 `run_full_pipeline()` 中从未被调用。`decision_mode` 参数传入 GateContext，但仅被 D0 门使用——而该门始终通过。 |
| **引用文件不存在** | 🔴致命 | `dependency.py` 引用了 `solution-wise/process/dependency-graph.yaml`，该文件**不存在于仓库中**。`_load_graph()` 静默返回 `{"nodes": []}`，导致所有节点验证形同虚设。 |
| **资产库集成未接入** | 🟡严重 | 每个 `agent.execute(ctx, None)` 都传入了 `asset_library=None`。构建和规模 agent 都忽略了可用的资产数据。 |
| **CLI 状态管理过度工程** | 🟡严重 | `decision/cli/solution.py`（563 LOC）管理 `.solution-state.yaml`（`complete-node`、`approve-node`、`next-node`...）。Agent 应该管理自己的工作，而不是手动更新 YAML 状态。 |
| **导入保护掩盖问题** | 🟡中等 | `__init__.py` 为每个 agent 使用 try/except 导入，允许完全缺失该模块而不报错。这是"可选附件"的架构信号。 |
| **Mock 分支等于真实分支** | 🔴致命 | `MarketResearchAgent` 的 `if is_mock:` 和 `else:` 分支执行完全相同的代码。注释写着"当真实 API 接入实现后……"——从未实现。 |

### 2.2 重构方案

**不做重构——直接重写。** 用 ~350 LOC + 提示替换 3,681+ LOC。

#### 新架构

```
之前（确定性模板）：
DecisionOrchestrator.run_build_mode()
→ 12 个 agent.execute()     [2,200 LOC 的 f-string 模板]
→ .solution-state.yaml       [563 LOC 的状态管理]
→ D0Gate 验证                [始终通过——引用文件不存在]

之后（LLM 驱动）：
MCP 工具: run_brand_strategy()
→ Jinja2 提示模板（可覆盖）
→ llm_complete_structured() 带 Pydantic 验证
→ 返回带类型的 DecisionStrategy 对象
→ 直接被 run_pipeline() 消费
```

#### 具体替换

| 当前组件 | LOC | 替换方式 | LOC |
|----------|-----|----------|-----|
| `build/` (4 个 agent) | ~683 | 1 个提示 `prompts/brand_strategy.j2` | ~80 |
| `scale/` (5 个 agent) | ~902 | 1 个提示 `prompts/scale_strategy.j2`（可选） | ~60 |
| `strategy/` (2 个 agent) | ~529 | 1 个提示 `prompts/content_strategy.j2` | ~60 |
| `DecisionOrchestrator` | 283 | 简化编排器（调用提示 + 验证） | ~80 |
| `cli/solution.py` | 563 | **移除**——不需要 CLI 状态管理 | 0 |
| `dependency.py` | 77 | **移除**——无依赖图 | 0 |
| `D0Gate` | 119 | 可选：简单验证检查（不是门） | ~20 |
| `preflight.py` | 50 | **移除** | 0 |
| `__init__.py` 链 | ~86 | 简化导出 | ~20 |
| `audit.py` | 32 | 保留 | ~30 |
| `schema_validator.py` | 60 | 保留 | ~30 |
| **总计** | **~3,681+** | **→** | **~380** |

**减少: ~3,300 LOC (90%)。**

#### 新 MCP 工具接口

```python
@mcp.tool()
def run_brand_strategy(
    idea: str,              # 品牌核心理念
    brand: str,             # 品牌名称（可选，留空则 LLM 建议）
    market: str = "",       # 目标市场
    mode: str = "build",    # "build" | "scale"
) -> dict:
    """在单次 LLM 调用中运行完整的品牌策略分析。
    
    使用带 Pydantic response_format 的 llm_complete_structured()。
    返回结构化的品牌 DNA、市场分析、受众画像、竞争矩阵和内容策略。
    提示模板可通过 ~/.automedia/overrides/prompts/brand_strategy.j2 覆盖。
    """

@mcp.tool()
def run_pipeline_from_strategy(
    strategy_id: str,       # run_brand_strategy 返回的 ID
    topic_override: str = "",  # 可选覆盖主题
) -> dict:
    """从保存的策略运行管道。
    
    从策略数据中提取 topic/brand/mode。
    相当于自动化的 convert_to_pipeline_input() + run_full_pipeline()。
    """
```

---

## 3. MCP vs Skills vs 混合方案评估

### 3.1 纠正：Skills 是所有 Agent 都能用的

**用户纠正**：Skills 是纯 Markdown 文件，放在 `.opencode/skills/` 等目录下，**任何 Agent**（OpenCode、Claude Code、Codex CLI、Cline、Hermes Agent）都能读取。之前说"仅 OpenCode"是错误的。任何一个 Agent 只要项目文件系统中有该 skill 文件就能读取。

### 3.2 所以，真实对比

修正后的对比：

| 维度 | **MCP 工具** | **Skills** | **纯 SDK** |
|------|-------------|------------|------------|
| **谁调用 LLM？** | AutoMedia 的 `llm_client` | Agent 自身的 LLM | 调用者自己的代码 |
| **所有 Agent 能用？** | ✅ 是（支持 MCP 的客户端） | ✅ 是（Markdown 文件） | ❌ 仅 Python 开发者 |
| **输出保证？** | ✅ Pydantic 验证 | ❌ 取决于 Agent 理解程度 | ✅ 代码可控 |
| **可测试性？** | ✅ pytest | ❌ 不可自动测试 | ✅ pytest |
| **可被管道调用？** | ✅ `run_pipeline` 可链接 | ❌ Skills 不是可执行接口 | ✅ 可直接调用 |
| **可覆盖性？** | ✅ Jinja2 提示覆盖 | ❌ 硬编码在 skill .md 中 | ✅ 代码层 |
| **灵活性？** | 固定行为 + 覆盖 | Agent 可自由调整但不可预测 | 完全灵活 |

### 3.3 推荐：MCP 工具为主 + Skills 为辅

**MCP 工具**作为主要实现。理由：

1. **通用兼容性** —— 任何 MCP 客户端（Claude Code、OpenCode、Codex CLI、Cline、Hermes Agent）都能原生调用 MCP 工具。Agent 不需要读取 Markdown 并理解如何实现；他们直接调用一个工具。
2. **结构化输出保证** —— `llm_complete_structured()` 带 `response_format=PydanticModel` 确保返回的 JSON 符合预期 schema。Agents 和管道都不会遇到格式错误的输入。
3. **可链接性** —— `run_brand_strategy` → `run_pipeline_from_strategy` 作为 MCP 工具链工作。Agent 无法"链接"skills。
4. **可测试性** —— `pytest` 可以调用 MCP 工具并断言响应。Skills 不能被自动测试。
5. **提示覆盖层** —— 现有的 `~/.automedia/overrides/prompts/*.j2` 系统允许用户在不修改代码的情况下自定义策略提示。Skills 将提示硬编码在 .md 中。

**Skills**作为可选的指导层 —— 一个 `.opencode/skills/brand-strategy.md` 文件，教会 Agent：
- 何时调用 `run_brand_strategy` MCP 工具
- 如何解读结果
- 如何通过覆盖自定义提示
- 什么情况下跳过并使用自己的 LLM

**Decision：MCP 工具作为可执行接口，Skills 作为教学文档，不做非此即彼。**

---

## 4. 全代码库评估矩阵

### 4.1 分类标准

每个模块根据两个维度分类：

| 维度 | 评分 | 含义 |
|------|------|------|
| **Agent 友好度** | 🟢友好 | 任何 MCP 客户端都能无障碍使用。无许可/登录/状态管理障碍 |
| | 🟡摩擦 | Agent 可到达，但需要额外步骤或状态管理 |
| | 🔴不友好 | Agent 不能正常使用或受限 |
| **LLM 适合度** | ✅应调用 LLM | 功能本质上是创造性的（策略、写作、评分），LLM 比确定性代码做得好得多 |
| | ➖保留确定性 | 功能是基础设施性的（配置、I/O、加密、HTTP），确定性代码是正确选择 |
| | ⚠️可 LLM 可确定性 | 功能目前是确定性的，但可受益于 LLM 增强（评分、验证） |

### 4.2 完整矩阵

| 模块 | LOC | %总 | Agent 友好度 | LLM 适合度 | 分类 |
|------|-----|-----|-------------|------------|------|
| **decision/** | 3,681 | 13.4% | 🟡（需 CLI 状态管理） | ✅ **应替换为 LLM** | 🔴应重写 |
| **asset_library/** | 1,605 | 5.8% | 🟢 | ⚠️可受益于 LLM 增强 | 🟡可精简 |
| **pool/** | 904 | 3.3% | 🟢 | ⚠️评分器应调用 LLM | 🟡 scorer 应重构 |
| **tenant/** | 438 | 1.6% | 🔴（限制 Agent） | ➖保留确定性 | 🟡如需可保留 |
| **license/** | 333 | 1.2% | 🔴（限制 Agent） | ➖保留确定性 | 🟡如需可保留 |
| **sop/runner.py** | 245 | 0.9% | 🟢 | ✅ **应替换为 Agent 直接执行** | 🟡可移除 |
| **hitl/** | 344 | 1.3% | 🟢 | ➖ Agent 能做同样的事 | 🟡可精简 |
| **platform_drafts/** | 124 | 0.5% | 🟢 | ➖ | 🔴很可能死代码 |
| **platform/** | 23 | 0.1% | 🟢 | ➖ | 🟢微小的 init，合理 |
| **cli/（非命令）** | ~3,180 | 11.6% | 🟢 | ➖ | 🟡对 Agent 冗余 |
| **gates/（非 CW）** | ~5,832 | 21.2% | 🟢 | ➖ 绝大多数正确确定性 | 🟢绝大多数合理 |
| **pipelines/** | 2,030 | 7.4% | 🟢 | ➖ | 🟢合理 |
| **core/** | 1,752 | 6.4% | 🟢 | ➖ | 🟢合理 |
| **mcp/** | 2,110 | 7.7% | 🟢 | ➖ | 🟢最关键的基础设施 |
| **accounts/** | ~670 | 2.4% | 🟢 | ➖ | 🟢合理 |
| **adapters/** | ~1,220 | 4.4% | 🟢 | ➖ | 🟢合理 |
| **hooks/** | 251 | 0.9% | 🟢 | ➖ | 🟢合理 |
| **omni/** | 1,039 | 3.8% | 🟢 | ➖ | 🟢合理 |
| **manifests/** | ~237 | 0.9% | 🟢 | ➖ | 🟢合理 |

### 4.3 问题模块分层

```
第1层：应重写 —— 明显不符合面向 Agent，应替换为 LLM
    decision/      (3,681 LOC) — 全是冒牌"Agent"，零 LLM 调用

第2层：应重构 —— 当前确定性代码，应改为 LLM 驱动或精简
    pool/scorer.py  — 主题评分应使用 LLM，而非确定性算法
    sop/runner.py   — Agent 可直接执行 SOP，无需框架
    asset_library/  — 过度工程化，可简化

第3层：应精简 —— Agent 友好但过度工程，可安全削减
    hitl/           — Agent 可自己询问用户
    cli/（命令）     — 对 Agent 冗余（MCP 是主要接口）
    platform_drafts/— 很可能死代码

第4层：噪音 —— 不影响 Agent，但因其他原因可改进
    tenant/         — 单用户场景不需要
    license/        — 开源项目不需要自执行许可
```

---

## 5. 各模块详细分析

### 5.1 已经由 LLM 驱动的模块

| 模块 | 文件 | 使用方式 | 属于？ |
|------|------|----------|--------|
| `core/llm_client.py` | `llm_complete()`, `llm_complete_structured()` | 统一 LLM 调用接口，支持重试/结构化输出 | ✅ 正确 |
| `gates/content_writer.py` | `llm_complete()` | 调用 LLM 根据主题和品牌撰写内容 | ✅ 正确 |
| `core/doctor.py` | `llm_complete()` | 健康检查 LLM 连接 | ✅ 正确 |

总共：**3 个文件调用 LLM。** 在 165 个文件中只有 3 个。

### 5.2 正确的确定性基础设施（不应改变）

这些模块正确执行了确定性工作，Agent 不需要干涉：

| 模块 | 理由 |
|------|------|
| `pipelines/gate_engine.py` | 门执行编排——基础设施 |
| `pipelines/audio_pipeline.py` | 包装 ffmpeg/edge-tts/Whisper——系统工作 |
| `pipelines/image_pipeline.py` | 包装 ComfyUI——系统工作 |
| `adapters/` | HTTP API 包装——必要的集成层 |
| `accounts/store.py` | AES-256-GCM 加密——安全所需 |
| `core/config_loader.py` | 6 层配置合并——基础设施 |
| `core/project.py` | 项目目录管理——基础设施 |
| `core/credential_loader.py` | 凭证解析——安全所需 |
| `gates/base.py` + `_context.py` | 门抽象——正确模式 |
| `gates/failure_modes.py` | 故障模式知识库——基础设施 |
| `hooks/` | 只读观察者模式——正确的正交基础设施 |
| `mcp/` | JSON-RPC 传输——最重要的面向 Agent 部分 |
| `omni/` | 包装外部 CLI 工具——必要的系统集成 |
| `pool/db.py` | SQLite CRUD——正确的存储 |

### 5.3 应重构为 LLM 驱动的模块

#### 5.3.1 decision/ —— 应该重写，不应重构

（详见上文第 2 节）

#### 5.3.2 pool/scorer.py + collector.py —— 评分应使用 LLM，收集应使用 Agent

**pool/scorer.py （204 LOC）—— 确定性的**

当前：两个硬编码的公式，使用任意权重（Growth = heat/10*0.30 + correlation*0.40 + freshness*0.30，Business = heat/10*0.10 + correlation*0.60 + freshness*0.30）。相关性通过跨越 40 个关键词的 4 层关键词匹配系统计算。新鲜度是超过 24 小时的线性衰减。

应改为：LLM 根据主题质量、趋势相关性、品牌契合度对主题评分。

**pool/collector.py （374 LOC）—— 自产自销的假数据**

当前：**所有 `_collect_*` 方法返回硬编码的假数据。** 14 个固定主题来自 6 个"来源"（微博、知乎、抖音、Bilibili、Tavily、AIHOT）。文档字符串第 7 行自述："所有数据均为合成数据——零真实 API 调用。"

应改为：AI Agent 访问真实的网站和 API 来发现实际趋势。一个 MCP 工具 `research_topics(category) → [topic_with_brief]` 让 Agent 能够注入真正的趋势。

**pool/dedup.py （102 LOC）—— 保持确定性**

使用 `difflib.SequenceMatcher`，阈值 0.75。对于近似精确的去重足够好。LLM 可以捕获语义重复（"AI视频工具对比" vs "2025年最佳AI视频工具评测"），但成本不成正比。

#### 5.3.3 sop/runner.py —— Agent 比 SOP 框架做得更好

当前：232 LOC + 自定义模板引擎（80 LOC 的 if/for/endif/endfor 解析器）生成包含占位符（"内容产出：N"、"标题 1"、"建议 1"）的通用文档。

应改为：Agent 读取 SOP 文档（Markdown），然后自己执行步骤。Agent 生成真实的内容，而非占位符。

**死代码检查**：仅通过 `automedia sop` CLI 可达。管道、MCP 或 SDK 中均未使用。

#### 5.3.4 asset_library/ —— 过度工程化，可简化

当前：1,605 LOC 用于 SQLite DB + Chroma + 摄取 + 搜索 + 迁移。

应改为：
- Chroma 向量存储配置（~50 LOC）
- 摄取 API（~50 LOC）
- MCP 工具搜索（~30 LOC）

不需要自包含的 SQLite 数据库和迁移模块。Agent 与 MCP 服务器的文件访问已经可以搜索文件系统。

#### 5.3.5 hitl/config.py —— 人机协同配置过度工程

当前：177 LOC 包含三层预设解析（动态/静态/文件系统）、YAML 覆盖合并、关键词节点分类（`_classify()` 函数将 22 个硬编码关键词匹配节点名称——例如 `"diagnosis" in node_name` 会在名为 `"misdiagnosis"` 的节点上产生误报）。

应改为：用简单的 dict 或 YAML 文件替换预设/覆盖机制。如果节点类型已经存在显式类型字段（预设 YAML 中已有 `type: decision`），则 `_classify()` 的回退是多余的。

保留 `protocol.py`（21 LOC）和 `executor.py`（130 LOC）——它们的设计很清晰。

### 5.4 死代码/未使用的模块

这些模块**不暴露给管道、MCP 服务器或 SDK**。它们仅通过隐形的 CLI 命令可达，面向 Agent 的 MCP 客户端无法触及。

| 模块 | LOC | 由谁使用 | 内容 | 建议 |
|------|-----|---------|------|------|
| **tenant/** | 438 | `automedia tenant` 仅 CLI | 基于角色的访问控制，基于邮箱的成员身份，内存审计日志。`check_permission()` 从未在管道/MCP 中调用。 | **移除**——如果 Agent 无法访问，则无法使用。437 LOC 管理假设公司结构的硬编码角色。 |
| **license/** | 333 | `automedia license` 仅 CLI | RSA-SHA256 密钥验证 + 许可功能门控。**`is_commercial_feature_available()` 从未在管道/MCP 中调用。** 整体执行仅为演示。 | **如有必要可移除**——如果不强制实施，则 179 LOC RSA 验证器毫无意义。若以后需连接，则对 Agent 不友好。 |
| **sop/** | 245 | `automedia sop` 仅 CLI | 含占位符模板的自定义模板引擎（`内容产出：N`、`建议 1`）。 | **移除**——Agent 自行生成文档更好。 |
| **platform_drafts/** | 124 | 无 | 两个桩模块，返回 `{"status": "not_implemented"}`。在自己的文档字符串中自述为已弃用。 | **移除**——弃用期早已结束。 |
| **platform/**（shim） | 23 | 引用旧的导入 | 带有 `DeprecationWarning` 的重新导出垫片。 | **清理**——指向真实适配器。 |
| **总计** | **1,163 LOC** | | | **可安全移除** |

**风险**：许可模块包含生产级 RSA 密码学（179 LOC），但只是等待被接入。如果未来某天有人将 `LicenseManager.is_commercial_feature_available()` 接入 `run_full_pipeline()`，每个 MCP 客户端 Agent 都会突然遇到付费墙。

### 5.5 验证门评估（哪些应保持确定性 vs 应调用 LLM）

**19 个门分析得出的关键发现**：

#### TIER 1：强烈建议转为 LLM（当前启发式方式严重不足）

| 门 | LOC | 当前做法 | 问题 |
|----|-----|---------|------|
| **G0 fact_check** | 258 | 子串匹配：`domain in content`、`quote.lower() not in content_lower`、实体子串搜索 | 文档字符串说"5 步验证管道"，但实现是 grep。它检查 URL 域名是否*作为文本出现*，而不是是否被引用。引号检查逐字进行——遗漏了改述。 |
| **G2 copy_review** | 562 | 关键词列表用于语气分析（"therefore" = 专业语气），计数用于证据（`\d+%` 模式），价值词计数用于"那又怎样"分析 | 这 4 种语气各有 3-4 个关键词：`professional: {"therefore", "consequently", "established", "proven"}`。语气分析通过关键词匹配从根本上说是错误的——"因此"可以出现在休闲内容中。证据检查计数百分比符号。 |
| **L4 translation_quality** | 245 | 检查 YAML 前言和 Unicode 替换字符，但**从不检查翻译是否准确或通顺** | 缺少的检查比进行的检查更重要。该闸门断言"没有乱码文本"即翻译质量好——这在语义上是荒谬的。 |

**G0 和 G2 是第 1 优先级**。它们进行语义评估（事实核查、语气、说服力），而字符串匹配/关键词计数从根本上无法做到。当前实现产生了高误报率和漏报率。

#### TIER 2：中等候选——保留确定性但添加 LLM 增强

| 门 | 应保留确定性的部分 | 可受益于 LLM 的部分 |
|----|-------------------|-------------------|
| **pre-gate** 主题选择 | 快速通过/拒绝的关键词拦截 | 语义分类的第二意见（边缘案例） |
| **G3 brand_cta** | 品牌名称存在、阻止词、CTA 存在 | `cta_direction_sync`（语义比较）和 `bridge_sentence`（自然过渡检测） |
| **V3 content_semantic** | 集合运算用于关键词覆盖率（≥80%，≥2/3 源对齐） | **上游关键词提取**（不在门内）和幻觉启发式（未出现在源中的关键词 ≠ 幻觉） |
| **L3 platform_integrity** | 列表成员检查、格式存在性 | `cross_platform_consistency`——当前使用长度比 ±50%，但应检查语义等价性 |

#### TIER 3：保持确定性（LLM 无法提供帮助或确定性更适合）

11 个门应保持确定性：

| 门 | 理由 |
|----|------|
| **G1 humanizer**（551 LOC） | AI 模式检测适用于正则表达式——这些是公式化模式。17 个硬编码关键词类别的重正则非常合适。 |
| **G4 wechat_checklist** | 标题长度、摘要长度、封面存在性、标签计数——均为纯确定性验证 |
| **G5 html_hard** | HTML 标签完整性——解析问题，而非语义问题 |
| **V0 lint** | 纯通过式门——读取预先计算的指标 |
| **V1 vision_qa** | 元数据验证——视觉 QA 发生在上游 |
| **V2 pre_send_whisper** | MD5 完整性检查、空字符串检查——确定性 |
| **V4 tts_brand_asset** | 语音 ID、语速范围 [0.5, 2.0]——参数验证 |
| **V5 mp3_vs_srt** | 两个文本之间的序列匹配器差异（Whisper 转录 vs SRT）——对齐是已解决的问题 |
| **V6 subtitle_render** | 像素级指标（亮度、对比度、不透明度）——LLM 无法看到像素 |
| **V7 six_step_hard** | 文件存在性、大小、MD5——系统级验证 |
| **L1 publish_log_schema** | JSON Schema 验证——确定性 |
| **L2 archive_validation** | 元数据字段检查——确定性 |

**总结**：19 个门中，2 个应转为 LLM（G0、G2），4 个可添加 LLM 增强（pre-gate、G3、V3、L4），11 个应保持确定性。两个视频/生命周期门（L3、G1）有微小的 LLM 机会。

### 5.6 代码库中的硬编码问题

#### 🔴 应使用 LLM（不仅仅是硬编码——逻辑本身就是错误的）

| 位置 | 硬编码内容 | 行 |
|------|------------|-----|
| `decision/build/brand_positioning.py` | 针对愿景/使命/价值观/个性/语气/口号的 6 个硬编码 f 字符串模板。`_build_vision()` = "成为最值得信赖的 {idea.lower()} 生态系统……" | 全文件 |
| `decision/build/audience_segmentation.py` | 3 个人物画像具有硬编码姓名（"Pioneer Pete"、"Creator Carla"、"Strategist Sam"）、年龄范围、收入、位置、兴趣、挑战、痛点和内容偏好映射 | 23-141 |
| `decision/build/competitor_analysis.py` | 5 个硬编码竞争对手，具有预写 SWOT（"AlphaCorp"、"BetaStudio"、"GammaGlobal"、"DeltaLabs"、"EchoInnovate"），每个都有市场份额和差异化差距 | 20-151 |
| `decision/scale/market_revalidation.py` | 行业趋势注册表（saas、ecommerce、fintech、healthcare、education），各 4 个硬编码趋势 | 63-94 |
| `pool/collector.py` | 14 个硬编码主题来自 6 个"来源"（微博、知乎、抖音、Bilibili、Tavily、AIHOT）。所有数据均为合成——零真实 API 调用。 | 全文件 |
| `decision/build/market_research.py` | `if is_mock:` 和 `else:` 分支执行**完全相同的代码**。注释写着"当真实 API 接入实现后……"——从未发生。 | 92-97 |

#### 🟡 应可配置或外部化

| 位置 | 硬编码 | 建议 |
|------|--------|------|
| `gates/content_writer.py:40-72` | 默认作家提示字符串 | 移至 `manifests/default_prompts/` 作为 .j2 |
| `gates/wechat_checklist.py` | 标签 ≥5，正文图片 [3, 6]，8 个敏感词 | 应来自 `brand_profile`/config |
| `gates/copy_review.py` | `_LONG_SENTENCE_THRESHOLD = 35` | 可配置阈值 |
| `gates/lint.py` | `_MAX_WARNINGS = 10` | 可配置阈值 |
| `gates/pre_send_whisper.py` | `_MIN_TRANSCRIPTION_LENGTH = 10` | 可配置阈值 |
| `gates/content_semantic.py` | `_MIN_COVERAGE = 0.80`、`max_hallucination_ratio = 0.30` | 可配置阈值 |
| `gates/tts_brand_asset.py` | `_MIN_RATE = 0.5`、`_MAX_RATE = 2.0` | 应来自 `brand_profile` |
| `gates/mp3_vs_srt.py` | `_MIN_DIFF_RATIO = 0.80` | 可配置阈值 |
| `gates/subtitle_render.py` | `_MIN_BRIGHTNESS = 50`、`_MIN_CONTRAST = 80` | 可配置阈值 |
| `gates/six_step_hard.py` | 2GB 大小限制 | 可配置限制 |
| `gates/platform_integrity.py` | `required_formats = ["mp4", "txt", "json"]`、长度比 50% | 可配置 |
| `gates/wechat_checklist.py` | `title ≤ 9`、`digest ≤ 20` | 来自品牌资料/配置 |
| `hitl/config.py` | 22 个节点分类关键词（`"diagnosis" in node_name`） | 从预设 YAML 中使用显式类型 |

#### 🔴 损坏的引用

| 位置 | 问题 |
|------|------|
| `decision/dependency.py:14-19` | `_GRAPH_PATH` 引用不存在的 `solution-wise/process/dependency-graph.yaml`。静默降级为 `{"nodes": []}`。 |
| `decision/cli/solution.py:29` | `.solution-state.yaml` 管理——563 LOC 的 CLI 用于从不存在的数据源跟踪节点完成情况。 |

#### 🟢 可接受的硬编码

| 位置 | 原因 |
|------|------|
| `manifests/defaults.yaml` | 配置默认值很好 |
| `accounts/auth/oauth2.py` | 安全协议是固定行为 |
| `gates/html_hard.py` | 40+ 配对标签列表——HTML 规范是固定的 |
| `gates/base.py` | 闸门命名约定——实施了 RL6 |
| `hooks/*` | 文件名常量——正确 |

---

## 6. 路线图：推荐实施顺序

### 第 1 阶段：高价值低风险（快速胜利）

| 任务 | LOC 影响 | 风险 |
|------|----------|------|
| 移除 `decision/cli/solution.py` | -563 🟡 | 低——状态管理对 Agent 是反模式 |
| 移除 `decision/dependency.py` | -77 🟡 | 低——引用损坏的文件 |
| 移除 `decision/preflight.py` | -50 🟡 | 低 |
| 移除 `platform_drafts/` + `platform/` 垫片 | -147 🟢 | 低——自述已弃用的死代码 |
| 移除 `sop/runner.py` + 模板 | -245 🟢 | 低——Agent 自行生成文档更好 |
| **阶段 1 小计** | **-1,082 LOC** | |

### 第 2 阶段：核心决策层替换

| 任务 | LOC 影响 | 风险 |
|------|----------|------|
| 添加 `run_brand_strategy` MCP 工具（LLM 驱动的策略） | +150 🔴 | 中——新代码 |
| 移除所有 12 个确定性 agent | -2,200 🔴 | 高——需要提示替代 |
| 重写 `DecisionOrchestrator`（→ 简化编排器 + 提示） | -200 🟡 | 中 |
| 移除 `D0Gate` | -119 🟡 | 低——始终通过（损坏的依赖引用） |
| 添加 `run_pipeline_from_strategy` MCP 工具 | +80 🟡 | 中 |
| 简化 `decision/__init__.py` | -60 🟢 | 低 |
| **阶段 2 小计** | **-2,349 LOC** | |

### 第 3 阶段：Gates 精炼

| 任务 | LOC 影响 | 风险 |
|------|----------|------|
| 将 G0 fact_check 转为 LLM（替换 5 个子串检查为单次调用） | ±0（保留 LOC） | 中——语义替换 |
| 将 G2 copy_review 转为 LLM（替换语气/证据/那又怎样/特异性检查） | ±0（保留 LOC） | 高——最大门 |
| 为 L4 translation_quality 添加 LLM 检查语义准确性 | +50 🟡 | 低——新增功能 |
| 将 17 个硬编码门阈值外部化到配置 | -0 🟢 | 低——重构 |
| **阶段 3 小计** | **+50 LOC**（新增 LLM 检查） | |

### 第 4 阶段：基础设施精简

| 任务 | LOC 影响 | 风险 |
|------|----------|------|
| 移除 `tenant/`（RBAC + 审计内存中） | -438 🟡 | 中——如果多租户需要可能恢复 |
| 移除 `license/`（RSA 验证器未强制） | -333 🟡 | 低——在管道中从未检查 |
| 重写 `pool/scorer.py` 使用 LLM | ±0 🟡 | 中 |
| 精简 `hitl/config.py` 预设/覆盖机制 | -120 🟡 | 低 |
| 简化 `asset_library/`——仅 Chroma 向量存储 + MCP | -1,400 🟡 | 中——需要测试替代方案 |
| 更新 `cli/app.py` 移除已删除命令注册 | -0 🟢 | 低 |
| **阶段 4 小计** | **-2,291 LOC** | |

### 第 5 阶段：可选增强

| 任务 | LOC 影响 | 风险 |
|------|----------|------|
| 添加 `.opencode/skills/brand-strategy.md` | +30 🟢 | 低 |
| 将 `content_writer.py` 默认提示提取到 `manifests/` | -2 🟢 | 低 |
| 添加可选 LLM 深度检查到 pre-gate、G3、V3、L3 | +80 🟢 | 低 |
| **阶段 5 小计** | **+108 LOC** | |

---

## 附录 A：全代码库 LOC 分布

| 模块 | LOC | % | 当前状态 |
|------|-----|---|----------|
| test/ | 38,902 | — | 排除 |
| **gates/** | **5,832** | **21.2%** | 🟡 2/19 应转为 LLM（G0、G2），11/19 正确确定性 |
| **decision/** | **3,681** | **13.4%** | 🔴 应重写——4 个阶段 1-2 中计划 |
| **cli/** | **3,180** | **11.6%** | 🟡 对 Agent 冗余但保留用于人类使用者 |
| **pipelines/** | **2,030** | **7.4%** | 🟢 正确 |
| **mcp/** | **2,110** | **7.7%** | 🟢 最关键的基础设施 |
| **core/** | **1,752** | **6.4%** | 🟢 正确 |
| **asset_library/** | **1,605** | **5.8%** | 🟡 可精简为仅向量存储 |
| **adapters/** | **1,220** | **4.4%** | 🟢 正确 |
| **omni/** | **1,039** | **3.8%** | 🟢 正确 |
| **pool/** | **904** | **3.3%** | 🟡 scorer + collector 应使用 LLM |
| **accounts/** | **670** | **2.4%** | 🟢 正确 |
| **tenant/** | **438** | **1.6%** | 🔴 死代码——建议移除（阶段 4） |
| **hitl/** | **344** | **1.3%** | 🟢 protocol + executor 良好；config 过度工程（阶段 4） |
| **license/** | **333** | **1.2%** | 🔴 死代码——未强制（阶段 4） |
| **hooks/** | **251** | **0.9%** | 🟢 参考实现 |
| **sop/** | **245** | **0.9%** | 🔴 死代码——Agent 做得更好（阶段 1） |
| **manifests/** | **237** | **0.9%** | 🟢 正确 |
| **platform_drafts/** | **124** | **0.5%** | 🔴 死代码——自述已弃用（阶段 1） |
| **platform/** | **23** | **0.1%** | 🟢 需清理但微小 |

**核心包总计：27,474 LOC**
**重构后总计**：~27,474 - 1,082（阶段 1）- 2,349（阶段 2）+ 50（阶段 3）- 2,291（阶段 4）+ 108（阶段 5）= **~21,910 LOC（减少 ~20%）**

**总预期 LOC 减少：~5,564 LOC**

## 附录 B：状态摘要

```
✅ 面向 Agent 合理：      ~14,500 LOC (53%) —— 基础设施、MCP、门（16/19）、适配器、核心
⏳ 需要 LLM 驱动/精简：   ~7,500 LOC (27%) —— 决策层、池评分器/收集器、资产库、CLI
🔴 死代码/不面向 Agent：  ~5,500 LOC (20%) —— 假 agent、租户、许可、SOP、platform_drafts
```

### 关键数字

| 指标 | 当前 | 重构后 | 变化 |
|------|------|--------|------|
| 核心 LOC | 27,474 | ~21,910 | **-5,564（-20%）** |
| 确定性的"Agent" | 12 | 0（用提示替换） | **-12** |
| LLM 调用文件 | 3/165 | ~10/130 | **+7 个 LLM 驱动文件** |
| 调用 LLM 的门 | 1/20 | 3/20（+2 个新） | **G0、G2 转为 LLM；L4 新增** |
| CLI 对 Agent 冗余 | 3,180 LOC | 3,180（保留） | 人类使用者需要 |
| MCP 工具 | 18 | ~22 | **+run_brand_strategy、+run_pipeline_from_strategy、+research_topics** |
| Skills | 0 | ~2 | **+brand-strategy.md、+gate-customization.md** |
