# AutoMedia 项目审计

> **范围:** 全栈架构、能力映射、自主差距与改进路线图
> **审计日期:** 2026-07-12  
> **代码库:** ~90,000+ LOC · 442+ 个 Python 文件 · 33,619 LOC（automedia/ 核心）  
> **测试:** 2,634 个测试（6 个预存失败）  
> **版本:** 1.0.0+（PRD-4 账户管理已发布）
>
> **状态说明 (2026-07-15):** 本文撰写于 D3 Gap Closure 之前。后续已完成：
> - 决策层（`automedia/decision/` ~3,681 LOC）已移除，代之以 `run_brand_strategy` + `run_pipeline_from_strategy` MCP 工具
> - D0 Gate 已移除
> - `automedia solution` CLI 已移除
> - H0 人工审核门已集成到管线中
> - GateEngine 新增 quality retry + regeneration 多层恢复
> - 本文档中关于已移除组件的引用保留为历史记录，标注 ~~删除线~~

---

## 目录

1. [架构总览](#1-架构总览)
2. [模块能力清单](#2-模块能力清单)
3. [完全自主差距分析](#3-完全自主差距分析)
4. [外部集成成熟度矩阵](#4-外部集成成熟度矩阵)
5. [管线端到端流程审计](#5-管线端到端流程审计)
6. [门系统深度分析](#6-门系统深度分析)
7. [决策层现状](#7-决策层现状)
8. [发布与适配器分析](#8-发布与适配器分析)
9. [基础设施与可观测性](#9-基础设施与可观测性)
10. [测试覆盖分析](#10-测试覆盖分析)
11. [架构债务与 ADR](#11-架构债务与-adr)
12. [优先改进路线图](#12-优先改进路线图)

---

## 1. 架构总览

```
  +------------------------------------------+
  |  任意 MCP 客户端 / SDK / CLI 终端          |
  +-----------+-------------------+-----------+
              |                   |
  +-----------+----+     +--------+-----------+
  |  MCP 服务器      |     |  CLI (typer)     |
  |  (18 个工具)     |     |  (16 个命令)     |
  +-----------+----+     +--------+-----------+
              |                   |
  +-----------+-------------------+------------+
  |      automedia/ Python 包                   |
  |                                             |
  |  核心层      管线层      门系统              |
  |  config_loader  runner     20 个门           |
  |  llm_client    gate_engine base + failure    |
  |  credential    audio        G0-G5(文案)      |
  |  project       image        V0-V7(视频)      |
  |  doctor       language     L1-L4(生命周期)   |
|  overrides                  pre-gate         |
|                                             |
|  适配器层      Omni 层      ~~决策层~~        |
  |  WeChat(真)    OPP(提取)    Diagnostic       |
  |  Zhihu(真)     OL(翻译)     Build(4 代理)    |
  |  Xiaohongshu   ORF(转换)    Scale(5 代理)    |
  |   (存根)                    Strategy(2 代理)  |
  |                                             |
  |  账户层(PRD-4)  池层        资产库            |
  |  AccountStore   PoolDB      SQLite + Chroma  |
  |  AuthFlow       Collector   ingest/search    |
  |  SessionManager Scorer      vector_store     |
  |                Dedup                          |
  |                                             |
  |  HITL 框架     SOP 运行器   租户层            |
  |  NodeExecutor  文档生成     TenantManager    |
  |  approve/skip               RBAC + Audit    |
  +----------------------------------------------+
```

### 三层入口点

| 层 | 调用方式 | 实现 |
|-----|-----------|--------------|
| **SDK** | `from automedia import run_full_pipeline` | `pipelines/runner.py` |
| **CLI** | `automedia <命令>` | `cli/app.py` → `commands/*.py` |
| **MCP** | `python -m automedia.mcp.server` | `mcp/server.py` → `mcp/tools.py` |

所有三层汇聚到同一 `run_full_pipeline()` 实现。

---

## 2. 模块能力清单

### 2.1 核心层 (`core/`)

| 模块 | 文件 | LOC | 状态 | 能力 |
|--------|------|-----|--------|-----------|
| 配置加载 | `config_loader.py` | 223 | ✅ 生产就绪 | 6 层合并（默认 → 项目 → 用户 → 规则 → 提示词 → env/覆盖）。深度递归字典合并。 |
| 项目管理 | `project.py` | 192 | ✅ 生产就绪 | `Project.init()` 自动创建目录结构。Slug 化 + 路径安全。 |
| 凭据加载 | `credential_loader.py` | 289 | ✅ 生产就绪 | 3 层回退链（环境变量 → 钥匙串 → YAML）。自动 `.env` 加载。PRD-4 账户回退桥接。 |
| LLM 客户端 | `llm_client.py` | 361 | ✅ 生产就绪 | 统一 `llm_complete()`/`llm_complete_structured()`。支持任意 OpenAI 兼容端点。指数退避重试。 |
| 系统检查 | `doctor.py` | 266 | ✅ 生产就绪 | 检查 Python/Bun/FFmpeg/Whisper/Edge-TTS/Chrome/ComfyUI + LLM API 连通性。 |
| 覆盖规则 | `overrides.py` | 163 | ✅ 生产就绪 | 加载品牌特定门规则 + 提示词模板。品牌感知过滤。 |
| 日志系统 | `logging.py` | 92 | ✅ 生产就绪 | structlog 配置。Console（开发）或 JSON（生产）格式。 |
| 注册表 | `registry.py` | 83 | ✅ 生产就绪 | 共享单例注册表模式。`__init_subclass__` 自动注册。为测试提供隔离。 |

### 2.2 管线层 (`pipelines/`)

| 模块 | 文件 | LOC | 状态 | 能力 |
|--------|------|-----|--------|-----------|
| 运行器 | `runner.py` | 423 | ✅ 生产就绪 | `run_full_pipeline()` — 所有三个入口点的共享入口点。8 种模式（auto/text_only/text_with_cover/video_only/qa_only/image-carousel/social-thread/short-video）。`resume_from` 支持。 |
| 门引擎 | `gate_engine.py` | 470 | ✅ 生产就绪 | 顺序门执行器。Stop/Retry 故障模式。钩子分发。`PipelineProgress`（线程安全）供 MCP 轮询。 |
| 音频管线 | `audio_pipeline.py` | 448 | ✅ 生产就绪 | edge-tts TTS → Whisper ASR → SRT 生成。品牌名称校对。 |
| 图像管线 | `image_pipeline.py` | 556 | ⚠️ 有回退 | ComfyUI HTTP API 用于封面/正文/备用帧。**静默降级到纯灰色 PIL 占位符**如果没有 ComfyUI 或 httpx。 |
| 语言配置 | `language_config.py` | 106 | ✅ 生产就绪 | TTS 语音/Whisper 语言/CTA/屏蔽词从品牌配置文件中解析。中文默认值。 |

### 2.3 MCP 服务器 (`mcp/`)

| 方面 | 详情 |
|--------|-------|
| **框架** | FastMCP（Python MCP SDK `>=1.0`） |
| **传输方式** | stdio（用于 Claude Desktop/Code、OpenCode、Cline、Codex CLI） |
| **工具** | 18 个（7 个核心工作流 + 1 个存档 + 2 个池 + 4 个 Omni + 4 个账户） |
| **资源** | 5 个（项目、管线状态、池、指标、门信息） |
| **安全性** | 路径允许列表 (`mcp_allowlist.yaml`)。空 = 拒接所有路径。故障关闭。 |
| **并行性** | `run_pipeline` 在后台线程中启动管线。`get_pipeline_progress` 允许代理轮询。 |

### 2.4 CLI 层 (`cli/`)

**16 个命令** 注册在 `cli/app.py` 中：

| 命令 | 功能 | 状态 |
|---------|---------|--------|
| `run` | 执行生产管线 | ✅ |
| `pool` | 话题池管理（列表/添加/评分/附加简介） | ✅ |
| `projects` | 项目浏览（列表/获取/获取资产） | ✅ |
| `adapter` | 平台适配器管理 | ✅ |
| `cron` | 执行定时作业 + 健康检查 | ✅ |
| `account` | 账户 CRUD（连接/列表/健康/断开/刷新） | ✅ |
| `archive` | 存档项目（RL8 强制执行） | ✅ |
| `init` | 初始化配置（交互式/最小化） | ✅ |
| `doctor` | 检查系统依赖 + LLM 连通性 | ✅ |
| `omni` | Omni 操作（提取/翻译/转换） | ✅ |
| `hitl` | HITL 审查操作（审批/拒绝预设） | ✅ |
| `license` | 许可证管理（检查/功能） | ✅ |
| `sop` | SOP 文档生成 | ✅ |
| `tenant` | 多租户管理（创建/列出/删除/邀请/成员/审计） | ✅ |
| ~~`solution`~~ | ~~决策层操作（下一节点/审批节点/完成节点/预检/验证工件）~~ | ~~✅~~ 已移除 |
| `onboard` | 入门向导 | ✅ |

---

## 3. 完全自主差距分析

**核心问题:** AutoMedia 能否端到端自主运行，从话题发现到多平台发布及之后，无需人工干预？

### 3.1 自主评分概览

```
话题收集:           0%  ⚠️ 完全模拟
话题选择:          90%  ✅ 自动化正则过滤 + DB 评分
内容写作:          90%  ✅ 基于 LLM 的一次性生成
内容 QA (G0-G5):   80%  ⚠️ 仅本地启发式，无 LLM 质量评估
音频制作:          90%  ✅ TTS → Whisper → SRT，外部依赖
图像生成:          30%  ❌ ComfyUI 静默 PIL 降级
视频组装:           0%  ❌ 无视频组装管线发现
字幕渲染:          70%  ⚠️ 像素验证存在，渲染取决于外部 Bun
平台发布:          20%  ❌ 2/7 个平台真实，1 个通知器，5 个缺失
多语言:           80%  ⚠️ Omni OL 工作，L4 验证
监控/日志:        80%  ✅ 钩子、MD5、指标正常
租户隔离:          50%  ⚠️ 仅内存，接口干净

总体自主运行时评分: ~45-55%
```

### 3.2 关键差距（阻塞性）

#### 🔴 第 1 层：无法自主创建内容

| # | 差距 | 影响 | 努力 | 细节 |
|---|------|--------|------|---------|
| **1.1** | **无视频生成引擎** | 无视频输出（auto/video_only 模式损坏） | 大（周） | V0-V7 门验证但**不生成**视频。实际的 MP4 渲染取决于外部 HyperFrames（不在本仓库）。需要运行 Runway/Pika/Kling API 或基于 FFmpeg 的组装。 |
| **1.2** | **图像生成的 ComfyUI 降级** | 无 ComfyUI 时为纯灰色占位符（静默失败） | 中（天） | `ImagePipeline` 在 ComfyUI 不可达时，不是重试或警告，而是返回 `(30,30,30)` RGB 图像。管线继续使用垃圾图像。 |
| **1.3** | **话题收集完全是模拟的** | 无法发现真实趋势 | 中（周） | `HotCollector` 中的每个 `_collect_*` 方法都返回硬编码的合成数据。无真正的 Weibo/Zhihu/Douyin/Bilibili/Tavily/AIHOT API 调用。 |
| **1.4** | ~~**决策层是确定性模板**~~ | ~~"策略"输出模板化，无可操作见解~~ | — | ⚠️ **已过时** — 决策层已移除，代之以 LLM 驱动的 `run_brand_strategy` MCP 工具。 |

#### 🔴 第 2 层：无法自主发布

| # | 差距 | 影响 | 努力 | 细节 |
|---|------|--------|------|---------|
| **2.1** | **YouTube 适配器缺失** | 无法发布到最大视频平台 | 中（天） | 在 defaults.yaml 中引用。OAuth2 流已实现但无适配器类。 |
| **2.2** | **TikTok/Douyin 适配器缺失** | 无法发布到中国最大的短视频平台 | 中（天） | 在 defaults.yaml 中声明。零实现。 |
| **2.3** | **Twitter/X 适配器缺失** | 无全球社交发布 | 小（天） | 在 defaults.yaml 中声明。零实现。 |
| **2.4** | **Bilibili/Weibo 适配器缺失** | 无法发布到中国主要视频/微博平台 | 中（天） | 在 L1 模式枚举中提及。零实现。 |
| **2.5** | **小红书发布是存根** | 返回 `"not_implemented"` | 中（天） | 无公开 API。需要 Playwright 浏览器自动化。 |
| **2.6** | **无发布后分析** | 无反馈循环 → 无迭代改进 | 大（周） | 所有适配器的 `get_analytics()` 返回 `"not_implemented"`。阅读/点赞/评论数据不可见。 |
| **2.7** | **无跨平台内容改编** | 相同内容 → 相同格式到每个平台 | 大（周） | 无长文→短文摘要。无平台特定语气适配。 |

#### 🟡 第 3 层：基础设施缺口

| # | 差距 | 影响 | 努力 | 细节 |
|---|------|--------|------|---------|
| **3.1** | **管线门中无 HITL 集成** | ~~门失败时管线以无人工升级路径终止~~ | — | ⚠️ **已过时**。H0 门已集成到管线中（`h0_human_review.py`），GateEngine 支持 approve/reject 生命周期。详见 F28。 |
| **3.2** | **无门级重试+重新检查循环** | G1/G2 一次写入 `modified_content` 未经重新验证 | 中（天） | 门检测问题、重写内容，但不重新运行自身。管线继续可能仍有问题的内容。 |
| **3.3** | **租户/审计仅为内存** | 重启时数据丢失 | 小（天） | `TenantManager._workspaces` 和 `AuditLog._entries` 是字典。注释说"未来的生产迭代应替换为数据库"。 |
| **3.4** | **MCP 服务器单体** | 538 行单体 | 小（天） | ADR-004 已接受但未实现。`mcp/server.py` 需要分解。 |
| **3.5** | **注册中心未统一** | 多个独立注册中心模式 | 小（天） | ADR-001 已接受但未实现。 |
| **3.6** | **适配器未注册** | `AdapterRegistry.list()` 返回空 | 小（小时） | 适配器必须由 MCP 工具或代码显式注册。文章中没有自动发现。 |
| **3.7** | **无内置调度器** | 需要外部 crond | 小（天） | 作业 YAML 定义存在但执行取决于 OS crond。 |

### 3.3 差距严重性排序

要使 AutoMedia 成为一个**无需人工干预即可从开始到结束自主运行**的机器，必须在优先级顺序中解决这些差距：

```
优先级 1（制作 — 能否实际创建内容？）
  ├── 1.1 视频生成引擎        ← 无视频 = 无输出（对于 "auto" 模式）
  ├── 1.3 真实话题收集        ← 模拟数据 = 模拟价值
  └── 1.4 决策层 LLM 集成    ← 模板策略 = 无策略

优先级 2（分发 — 能否自主发布？）
  ├── 2.1 YouTube 适配器      ← 缺失最大视频平台
  ├── 2.2 TikTok/Douyin 适配器 ← 缺失中国最大短视频平台
  ├── 2.5 小红书浏览器自动化 ← 目前存根
  └── 2.6 发布后分析          ← 无反馈循环 = 无改进

优先级 3（内容工程 — 能否智能适配内容？）
  ├── 2.7 跨平台内容改编      ← 每个平台都需要手动适配
  ├── 3.2 门级重试循环        ← 一次写入 = 未经验证的修复
  └── 3.1 管线中的 HITL       ← 失败时无人工升级路径

优先级 4（基础设施 — 基础设施是否支持？）
  ├── 3.3 持久租户/审计       ← 重启时数据丢失
  ├── 3.4 MCP 服务器分解       ← 538 行单体
  └── 3.6 适配器自动注册      ← 注册当前为空
```

---

## 4. 外部集成成熟度矩阵

| 类别 | 集成 | 文件 | 成熟度 | 备注 |
|--------|----------|------|----------|-------|
| **LLM** | OpenAI 兼容 API | `core/llm_client.py` | ✅ 生产就绪 | 支持 DeepSeek、OpenAI、Azure、Ollama 等。 |
| **TTS** | edge-tts (Microsoft Edge TTS) | `pipelines/audio_pipeline.py` | ✅ 生产就绪 | 子进程调用 `edge-tts` CLI。 |
| **ASR** | Whisper (faster-whisper/openai-whisper) | `pipelines/audio_pipeline.py` | ✅ 生产就绪 | 子进程调用 `whisper` CLI。 |
| **图像** | ComfyUI HTTP API | `pipelines/image_pipeline.py` | ⚠️ 有回退 | HTTP POST 到 `localhost:8188/prompt`。**静默降级到 PIL 占位符。** |
| **视频** | HyperFrames (via Bun) | `gates/lint.py`（引用） | ❌ 缺失/存根 | V0 Lint 门验证 HyperFrames 输出。**无实际视频渲染代码存在于仓库中。** |
| **字幕** | PIL 像素亮度 | `gates/subtitle_render.py` | ⚠️ 仅验证 | 不渲染字幕。通过 PIL 验证现有帧。 |
| **微信** | `api.weixin.qq.com/cgi-bin/*` | `adapters/platforms/wechat_publisher.py` | ✅ 生产就绪 | 完整 3 步：令牌 → 草稿 → 发布。 |
| **知乎** | `zhihu.com/api/v4/drafts` | `adapters/platforms/zhihu_publisher.py` | ✅ 生产就绪 | 基于 Cookie 的认证。HTML + Markdown 支持。 |
| **小红书** | 小红书（无公开 API） | `adapters/platforms/xiaohongshu_publisher.py` | ❌ 存根 | 返回 `not_implemented`。需要手动发帖。 |
| **飞书** | 飞书 Webhook | `adapters/platforms/feishu_notifier.py` | ⏭️ 已移除（out of scope） | IM 通知属于 agent 框架责任范围，非 AutoMedia 职责。 |
| **YouTube** | 无适配器 | — | ❌ 缺失 | OAuth2 流就绪但无 YouTube 适配器开发。 |
| **TikTok** | 无适配器 | — | ❌ 缺失 | 在 defaults.yaml 中声明。零代码。 |
| **Twitter/X** | 无适配器 | — | ❌ 缺失 | 在 defaults.yaml 中声明。零代码。 |
| **话题 L1** | Weibo/Zhihu/Douyin/Bilibili（模拟） | `pool/collector.py` | ❌ 模拟 | 无真实 API 调用。合成数据。 |
| **话题 L2** | Tavily AI Search（模拟） | `pool/collector.py` | ❌ 模拟 | 无真实的 Tavily HTTP 客户端。关键字匹配模拟。 |
| **话题 L3** | AIHOT Aggregator（模拟） | `pool/collector.py` | ❌ 模拟 | 合成数据。 |
| **Omni OPP** | 文档提取 | `omni/opp_adapter.py` | ⚠️ 部分 | 需要 `omni-pre-processor` 包 (`>=0.9`)。`detect_format()` 始终返回 `"markdown"`。 |
| **Omni OL** | 本地化/翻译 | `omni/ol_adapter.py` | ⚠️ 部分 | 需要 `omni-localizer` 包 (`>=0.7`)。裁判**始终返回 1.0 分**。 |
| **Omni ORF** | 格式转换 | `omni/orf_adapter.py` | ⚠️ 部分 | 需要 `omni-re-formatter` 包 (`>=0.4`)。`backfill()` 返回输入不变。`apply_xliff()` 是无操作占位符。 |
| **资产库** | ChromaDB 向量搜索 | `asset_library/vector_store.py` | ⚠️ 有回退 | 如果缺少 chromadb 则优雅降级。 |
| **资产库** | sentence-transformers + PyTorch | `asset_library/vector_store.py` | ⚠️ 部分 | 通过 `[omni-ml]` 可选依赖。 |
| **OAuth2** | Google (`accounts.google.com`) | `accounts/auth/oauth2.py` | ✅ 生产就绪 | 完全实现 authorization_code + PKCE。 |
| **OAuth2** | WeChat (`api.weixin.qq.com`) | `accounts/auth/oauth2.py` | ✅ 生产就绪 | client_credentials 流。 |
| **凭证** | python-dotenv | `core/credential_loader.py` | ✅ 生产就绪 | 自动加载 `~/.automedia/.env`。 |
| **凭证** | System keyring | `core/credential_loader.py` | ⚠️ 部分 | 可选。静默跳过。 |
| **凭证** | AES-256-GCM 存储 | `accounts/store.py` | ✅ 生产就绪 | PRD-4 加密。主密钥来自 `AUTOMEDIA_MASTER_KEY`。 |
| **HTTP** | httpx | 遍布多个文件 | ✅ 生产就绪 | 如果没有安装 httpx，每个适配器都会优雅降级。 |
| **系统** | FFmpeg | `core/doctor.py` | ✅ 生产就绪 | 验证系统依赖。 |
| **系统** | Bun (JavaScript 运行时) | `core/doctor.py` | ✅ 生产就绪 | 需要用于 HyperFrames（外部 JS）。 |
| **系统** | Chrome/Chromium (无头) | `core/doctor.py` | ✅ 生产就绪 | 用于视频渲染。 |
| **系统** | ComfyUI (可选) | `core/doctor.py` | ⚠️ 部分 | HTTP 健康检查。如果不运行则降级到 PIL。 |

---

## 5. 管线端到端流程审计

### 5.1 完整流程（`auto` 模式）

```
Topic Selection (人工/预加载)        ← 入口点：select_topic MCP / CLI
  │
  ▼
D0 Gate (出处)                      ← 验证决策层执行了
  │
  ▼
Pre-gate (话题验证)                  ← 正则过滤禁止类别
  │
  ▼
CW Gate (内容写作)                   ← LLM 生成 800-1500 字文章
  │                                  写入 01_content/drafts/*.md
  ▼
G0-G5 Gates (文案 QA)               ← 6 个门：事实检查 → 人性化 → 复制审查
  │                                  → 品牌 CTA → 微信清单 → HTML 严格
  ▼
V0-V7 Gates (视频 QA)               ← 8 个门：Lint → 视觉 → Whisper → 语义
  │                                  → TTS → MP3×SRT → 字幕渲染 → 6 步严格
  ▼
L1-L4 Gates (生命周期)              ← 4 个门：发布日志 → 存档 → 平台 → 翻译
  │
  ▼
Publish Engine                       ← 迭代适配器：验证 → 发布
  WeChat (真实 API)
  Zhihu (真实 API)
  Xiaohongshu (返回 not_implemented)
  Feishu (通知)
  [YouTube] [TikTok] [Twitter] — 缺失
```

### 5.2 每种模式的门

| 模式 | 门 | 当前状态 |
|------|------|---------------|
| `auto` | ~~D0 →~~ pre-gate → CW → G0-G5 → V0-V7 → H0 → L1-L4 | ✅ 顺序结构，V 门验证无输出 |
| `text_only` | ~~D0 →~~ CW → G0-G5 → H0 → L1-L4 | ✅ 功能完整 |
| `video_only` | ~~D0 →~~ V0-V7 → H0 → L1-L4 | ⚠️ V 门验证不存在的内容 |
| `qa_only` | ~~D0 →~~ G0 → G2 → G3 → V1 → V6 | ✅ 适用于现有项目 |

### 5.3 故障模式

| 失败类型 | 处理 | 自主性影响 |
|-----------|-----------|--------------|
| 门 `failure_mode="stop"` | 管线停止，返回 `partial` 状态 | **无恢复** — 需要人工干预 |
| 门 `failure_mode="retry"` | 重试最多 3 次（瞬态异常） | **自动**但有限的尝试 |
| 永久异常 | 立即停止 | **无恢复** — 需要人工 |
| 未知异常 | 停止并传播 | **无恢复** |
| 管道级错误 | 被 `run_full_pipeline()` 捕获 → `PipelineResult(status="failed")` | **无恢复** |
| LLM API 错误 | 最多 3 次重试，然后传播 | **自动**但有限的尝试 |

**当前能力:** GateEngine 已实现多层递增恢复：Level 1 quality-feedback retry（同一 gate 同一内容最多重试 3 次），Level 2 regeneration（重跑 CW + 之后所有 gates 最多 2 轮），HITL 兜底。详见 F24 描述。

### 5.4 关键流程观察

1. **CW 是唯一的 LLM 门** — 只有内容写作使用 LLM。所有质量门都使用正则表达式。无基于 LLM 的质量评估。
2. **G1/G2 是单次写入修复** — 它们修改 `gate_context["content"]`，但管线不重新运行门来验证修复。
3. **管线不循环** — 从 CW → 发布是一条直线。无适配性门循环（"写得不好？重写。"）。
4. **无门级节流** — 门不能决定"暂停等待人工批准"。它们通过或失败。
5. **V 门验证外部输出** — 它们检查由 HyperFrames（外部）渲染的字幕像素。如果 HyperFrames 不运行，门会失败。

---

## 6. 门系统深度分析

### 6.1 所有 20 个门（~~D0 已移除~~）

#### 复制/内容门（G0–G5）

| 门 | 文件 | 故障模式 | 检查 | 本地或 LLM？ | 输出 |
|-----|------|-------------|--------|---------------|--------|
| **pre-gate** | `topic_selection.py` | `stop` | 6 次检查：5 个禁止类别正则 + 话题长度（5-500） | 本地正则 | `passed: bool`, `checks[]` |
| **CW** | `content_writer.py` | `stop` | 话题存在、项目目录、LLM 成功、非空、文件写入 | **LLM** (via `llm_complete`) | `content: str`, `output_path` |
| **G0** | `fact_check.py` | `stop` | 5 步：来源追踪、数字、时间线、引号、实体 | 本地启发式 | `passed`, `checks[]`, `confidence` |
| **G1** | `humanizer.py` | `retry` | 9 类检测（过度副词、空洞开头、模糊主语、填充连接词、过长并列、模板结论） | 本地正则 + 重写 | `passed`, `checks[]`, `modified_content` |
| **G2** | `copy_review.py` | `retry` | 5 轮：清晰度、语气、所以呢？、证据、具体性 | 本地正则 + 重写 | `passed`, `checks[]`, `modified_content` |
| **G3** | `brand_cta.py` | `stop` | 品牌名称存在、CTA 存在、品牌标识、屏蔽词、CTA 方向同步、过渡句 | 本地正则 | `passed`, `checks[]` |
| **G4** | `wechat_checklist.py` | `stop` | 7 次：标题 ≤9、摘要 ≤20、无 Markdown、封面存在、标签 ≥5、正文图片 3-6、敏感词 | 本地正则 | `passed`, `checks[]` |
| **G5** | `html_hard.py` | `stop` | 3 次：标签完整性、无 Markdown 产物、标签计数 ≥5 | 本地正则 | `passed`, `checks[]` |

#### 视频门（V0–V7）

| 门 | 文件 | 故障模式 | 检查 | 输出 |
|-----|------|-------------|--------|--------|
| **V0** | `lint.py` | `stop` | lint_errors=0, warnings ≤10, syntax_valid | 读取 `lint_result` 从上下文 |
| **V1** | `vision_qa.py` | `stop` | mid_frame_valid, end_silence_valid, all_entries_passed, RL6（全覆盖） | 读取 `entries[]` 从上下文 |
| **V2** | `pre_send_whisper.py` | `stop` | whisper_transcription, transcription_length ≥10, md5_integrity, RL7（完整音频） | 读取 `transcription` 从上下文 |
| **V3** | `content_semantic.py` | `stop` | keyword_coverage ≥80%, source_alignment ≥2/3, no_hallucination ≤30% | 读取 keywords 从上下文 |
| **V4** | `tts_brand_asset.py` | `stop` | voice_id_match, speaking_rate（0.5-2.0）, voice_consistency | 读取 `voice_id` 从上下文 |
| **V5** | `mp3_vs_srt.py` | `retry` | whisper_vs_srt_diff ≥80%, srt_not_empty, whisper_not_empty | `SequenceMatcher` diff |
| **V6** | `subtitle_render.py` | `stop` | subtitle_region_brightness ≥50, contrast ≥80, opacity >0, RL5 | 读取像素从上下文 |
| **V7** | `six_step_hard.py` | `stop` | file_exists, file_size_valid, md5_verified, whisper_full, format_valid, duration_valid | 读取文件元数据从上下文 |

#### 生命周期门（L1–L4）

| 门 | 文件 | 故障模式 | 检查 | 输出 |
|-----|------|-------------|--------|--------|
| **L1** | `publish_log_schema.py` | `stop` | 话题存在、内容存在、媒体路径有效、平台有效（枚举：微信/微博/抖音/b站/小红书/youtube/twitter）、版本有效、时间戳有效 | 模式验证 |
| **L2** | `archive_validation.py` | `stop` | archive_status, force_flag, archive_path_exists, archive_metadata_complete, archive_version_valid, output_directory_exists | RL8 强制执行 |
| **L3** | `platform_integrity.py` | `stop` | all_platforms_present, no_platform_splitting, material_integrity, cross_platform_consistency, format_completeness, metadata_integrity | 基于上下文的检查 |
| **L4** | `translation_quality.py` | `stop` | frontmatter_valid, language_match, no_garbled_text, non_empty | YAML 前置元数据 + Unicode 检查 |

### 6.2 门系统关键发现

1. **仅 CW 使用 LLM** — 质量门（G0-G5）依赖纯正则。无语义质量评估。
2. **G1/G2 是单次写入修复** — 无重新验证循环。
3. **V 门验证外部输出** — 不生成媒体。如果外部系统（HyperFrames/ComfyUI）不运行，则门失败。
4. **L1 平台枚举包括缺失的平台** — YouTube、Twitter、Bilibili、Weibo、Douyin 在模式中但无适配器。
5. ~~**无 `human_review` 故障模式** — HITL 框架集成在决策层，而非门引擎。~~ ⚠️ **已过时** — H0 门已集成，支持 `awaiting_hitl` → approve/reject 生命周期。

---

## 7. 决策层现状

> **已移除 (2026-07-15):** 整个 `automedia/decision/` 包（~3,681 LOC）已在 D3 Gap Closure 中删除，
> 代之以 `run_brand_strategy` + `run_pipeline_from_strategy` MCP 工具。
> 本节内容保留为历史记录。

### 7.1 架构

```
决策编排器
  ├── 诊断代理（阶段 0）         ← 路由：构建 vs 规模模式
  ├── 构建模式（阶段 1-B）
  │   ├── 品牌定位代理
  │   ├── 市场研究代理
  │   ├── 受众细分代理
  │   └── 竞争对手分析代理
  ├── 规模模式（阶段 1-S）
  │   ├── 品牌健康诊断代理
  │   ├── 市场重新验证代理
  │   ├── 受众深化代理
  │   ├── 竞争对手追踪代理
  │   └── 内容资产审计代理
  └── 策略引擎（阶段 2）
      ├── 产品优化代理
      └── 内容营销代理
```

### 7.2 当前状态：确定性模板

**关键发现：** 所有 11 个决策代理都是**无 LLM 调用的确定性纯 Python 类**。

| 代理 | 输出 | 实际生成 |
|--------|--------|---------------|
| `DiagnosticAgent` | 模式路由（构建/规模） | `assign_mode()` 检查关键词如 "existing" 的词法逻辑 |
| `BrandPositioningAgent` | 品牌 DNA（愿景、使命、价值观） | `_build_vision()` 返回 `f"To become the most trusted {idea.lower()} ecosystem..."` |
| `MarketResearchAgent` | TAM/SAM/SOM、趋势、差距 | 模板化响应 |
| `AudienceSegmentationAgent` | 3-5 个买家角色 | 角色模板 |
| `CompetitorAnalysisAgent` | 竞争对手 SWOT | SWOT 模板 |
| `BrandHealthDiagnosisAgent` | 现有品牌审计 | 模板化分数和洞察 |
| `MarketRevalidationAgent` | 市场扫描更新 | 模板化趋势 |
| `AudienceDeepeningAgent` | 受众分析 | 模板化聚类 |
| `CompetitorTrackingAgent` | 竞争对手追踪 | 模板化追踪报告 |
| `ContentAssetAuditAgent` | 资产清单 | 模板化审计 |
| `ProductOptimizationAgent` | 产品策略 | 模板化建议 |
| `ContentMarketingAgent` | 内容策略 | 模板化策略 |

**对自主性的影响：** 决策层本应是"生产什么内容以及为什么"的策略中心。相反，它产生问候卡般通用的输出。对于自主操作，这毫无价值——你不能根据模板化 SWOT 做出战略决策。

**预期修复：** 每个代理都需要真正的 LLM 调用来生成其特定领域的相关内容。生产端到端测试设计文档本身指出：*"当前的决策代理是确定性的（无 LLM 调用）"*。

---

## 8. 发布与适配器分析

### 8.1 平台适配器状态

| 平台 | 适配器 | LOC | 认证 | 发布 API | 健康状况 | 分析 | 会话刷新 |
|----------|---------|-----|------|-----------|--------|-----------|----------------|
| **微信** | `WechatPublisher` | 508 | ✅ OAuth2 令牌 | ✅ 草稿 + 发布 | ❌ 未实现 | ❌ 未实现 | ❌ 未实现 |
| **知乎** | `ZhihuPublisher` | 264 | ✅ Cookie | ✅ 草稿 | ❌ 未实现 | ❌ 未实现 | ❌ 未实现 |
| **小红书** | `XiaohongshuPublisher` | 78 | ⚠️ 已存根 | ❌ 未实现 | ❌ 未实现 | ❌ 未实现 | ❌ 未实现 |
| ~~**飞书**~~ | ~~`FeishuNotifier`~~ | ~~147~~ | ⏭️ out of scope | IM 通知属 agent 框架职责 | — | — | — |
| **YouTube** | — | 0 | ⚠️ OAuth2 就绪 | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 |
| **TikTok** | — | 0 | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 |
| **Twitter/X** | — | 0 | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 |
| **Bilibili** | — | 0 | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 |
| **Weibo** | — | 0 | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 |
| **Instagram** | — | 0 | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 |
| **LinkedIn** | — | 0 | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 | ❌ 缺失 |

### 8.2 发布引擎流程

```
PublishEngine.publish_all()
  1. 加载适配器列表从 AdapterRegistry
  2. 对于每个适配器：
     a. 适配器.validate(artifact_dir)
     b. 适配器.publish(artifact_dir, project)
  3. 收集结果
```

如果适配器**未注册**（`AdapterRegistry.list()` 为空），发布引擎不执行任何操作。

### 8.3 关键发布发现

1. **仅 2 个真正的发布目标**（微信、知乎）。~~+ 1 个通知器（飞书）~~（飞书已标记 out of scope）。5+ 个平台有配置条目但零代码。
2. **所有适配器缺失 `check_health()`、`get_analytics()`、`refresh_session()`** — PRD-4 添加了这些方法但基类默认返回 `"not_implemented"`。
3. **适配器不会自动注册** — 必须由 MCP 工具显式注册或手动导入。
4. **小红书需要浏览器自动化** — 无公共 API。Playwright 登录 + Cookie 管理是唯一路径。

---

## 9. 基础设施与可观测性

### 9.1 日志与监控

| 机制 | 实现 | 状态 |
|----------|-------------|--------|
| 结构化日志 | structlog（控制台或 JSON） | ✅ |
| 门指标 | `MetricsHook` → `production_metrics.json` | ✅ |
| MD5 追踪 | `MD5Tracker` → `pipeline_md5.json` | ✅ |
| 管线进度 | `PipelineProgress`（线程安全，MCP 可轮询） | ✅ |
| MCP 资源 | 5 个资源用于项目/管线/池/指标/门信息 | ✅ |
| 系统健康 | `automedia doctor` 检查 CLI 工具、API 连通性 | ✅ |

### 9.2 错误处理与重试

| 层级 | 策略 | 修复状态 |
|-------|----------|--------------|
| 管线级别 | `try/except` 包装 `run_full_pipeline()`，返回 `PipelineResult(status="failed")` | ✅ |
| 门级别 | `failure_mode="stop"`（中断），`failure_mode="retry"`（最多 3 次重试） | ✅ |
| LLM 级别 | 指数退避（tenacity），最多 3 次（RateLimitError、APITimeoutError、APIConnectionError） | ✅ |
| 管线恢复 | `resume_from` 参数 + MD5 完整性验证 | ✅ |
| 静态降级 | ComfyUI → PIL 灰色占位符（**静默**） | ⚠️ |

### 9.3 配置深度

| 层 | 来源 | 示例 |
|------|--------|--------|
| 1. 内置默认值 | `manifests/defaults.yaml` | LLM 提供商、模型、温度 |
| 2. 项目配置 | `.automedia/` | 品牌特定配置 |
| 3. 用户配置 | `~/.automedia/` | 用户全局配置 |
| 4. 覆盖规则 | `~/.automedia/overrides/rules/*.yaml` | 品牌特定门规则 |
| 5. 覆盖提示词 | `~/.automedia/overrides/prompts/*.j2` | 品牌特定 LLM 提示词 |
| 6. 环境变量 | `AUTOMEDIA_*` | 最高优先级覆盖 |

### 9.4 安全模型

| 措施 | 实现 | 状态 |
|----------|-------------|--------|
| MCP 路径允许列表 | `mcp_allowlist.yaml`（空 = 拒绝所有） | ✅ |
| 红线强制执行 | RL4-RL9 在门中实施 | ✅ |
| 凭据加密 | AES-256-GCM 在 `accounts/store.py` 中 | ✅ |
| 凭据防泄漏 | `SessionToken.__repr__` 掩码令牌 | ✅ |
| 无生产数据在测试中 | 所有 fixture 是合成数据 | ✅ |
| 红线 8（存档） | 仅当 `published` 或 `--force` 时存档 | ✅ |

---

## 10. 测试覆盖分析

### 10.1 测试统计

| 指标 | 值 |
|--------|-------|
| 总测试 | 2,634 |
| 失败 | 6 (pre-existing) |
| 测试文件/目录 | 130+ |
| 核心代码行 | 33,619 |
| 标记 | `e2e`、`redline`、`slow` |

### 10.2 按区域测试覆盖

| 测试区域 | 文件 | 覆盖 |
|------------|-------|---------|
| 门测试 | `tests/test_gates/` | ✅ 每个门的单独文件 |
| CLI 测试 | `tests/test_cli/` | ✅ 16 个命令 |
| MCP 测试 | `tests/test_mcp/` | ✅ 服务器 + 工具 |
| 管线测试 | `tests/test_pipeline/` | ✅ 运行器 + 引擎 |
| 池测试 | `tests/test_pool/` | ✅ DB、收集器、评分器、去重 |
| Omni 测试 | `tests/test_omni/` | ✅ 适配器 |
| 决策层测试 | `tests/test_decision_layer/` | ✅ 代理 + 编排器 |
| 端到端测试 | `tests/test_e2e/` | ⚠️ 部分 |
| 强制执行测试 | `tests/test_enforcement/` | ✅ 红线 |
| 钩子测试 | `tests/test_hooks/` | ✅ 协议 + 指标 |
| 适配器测试 | `tests/test_adapters/` | ✅ 平台适配器 |
| 账户测试 | `tests/test_accounts/` | ✅ 191 个 PRD-4 测试 |
| 资产库测试 | `tests/test_asset_library/` | ✅ |
| 医生测试 | `tests/test_doctor/` | ✅ |

### 10.3 测试差距

1. **生产端到端测试（S1–S3）** — `docs/archive/production-e2e-test-design.md` 定义了 S1–S3 测试但** `tests/production/` 目录不存在**。零实现。
2. **集成测试** — 测试使用合成数据。很少有测试调用真实 API 或测试端到端管线使用真实 LLM。
3. **性能测试** — 未找到负载/压力测试。
4. **安全测试** — 未找到渗漏/注入测试。

---

## 11. 架构债务与 ADR

### 11.1 已接受 ADR 但未实施

| ADR | 标题 | 努力 | 影响 |
|-----|-------|------|--------|
| ADR-001 | 单体注册中心统一 | 小（1-2 天） | 门、适配器、Omni 工具之间注册中心模式不一致 |
| ADR-004 | 分解 `mcp/server.py` 单体 | 小（1-2 天） | 538 行 MCP 服务器单体需要分解 |

### 11.2 其他架构问题

| 问题 | 位置 | 影响 | 建议修复 |
|-------|----------|--------|---------------|
| 适配器不自动注册 | `adapters/__init__.py` + `registry.py` | `AdapterRegistry.list()` 返回空；发布引擎不执行任何操作 | 在 `__init__.py` 导入时添加 `register()` 调用 |
| 租户管理器仅内存 | `tenant/manager.py` | 重启时数据丢失 | 迁移到 SQLite（遵循资产 DB 模式） |
| 审计日志仅内存 | `tenant/audit.py` | 重启时审计轨迹丢失 | 迁移到 SQLite |
| ComfyUI 静默降级 | `pipelines/image_pipeline.py` | 在无 ComfyUI 时继续使用垃圾图像 | 添加日志记录、重试、回退通知 |
| 视频验证但无渲染 | 整个 V0-V7 门集 | 管线输出验证但从不生成视频 | 需要 `pipelines/video_assembly.py` |

---

## 12. 优先改进路线图

### 阶段 1：使内容真实（高优先级，阻塞性）

```
1.1 视频生成引擎          [1-2 周]  集成 AI 视频 API（Runway/Pika/Kling）
                                    或基于 FFmpeg 的组装：音频 + 图像 → MP4
1.2 真实话题收集 API      [3-5 天/来源]
                                    用真正的 HTTP 客户端替换 HotCollector 模拟
                                    （微博/知乎/抖音/Bilibili 热搜 API 或爬虫）
~~1.3 决策层 LLM 集成~~       [~~5-7 天~~]   ✅ **已完成** — 决策层移除，`run_brand_strategy` + `run_pipeline_from_strategy` MCP 工具已上线
                                    以获得真正的市场/品牌/受众洞察
1.4 语音克隆/自定义 TTS   [3-5 天]   添加 ElevenLabs/Fish Audio/CosyVoice
                                    超越单一的微软语音
```

### 阶段 2：使发布真实（高优先级，阻塞性）

```
2.1 YouTube 适配器        [3-5 天]   OAuth2 + YouTube Data API v3 视频上传
2.2 TikTok 适配器         [3-5 天]   TikTok 开发者 API OAuth2 + 视频发布
2.3 Twitter/X 适配器      [2-3 天]   Twitter API v2 OAuth2 + 推文/线程
2.4 Bilibili 适配器       [3-5 天]   Bilibili 开放平台 API + 视频上传
2.5 Weibo 适配器          [2-3 天]   微博开放平台 API
2.6 小红书浏览器自动化    [3-5 天]   Playwright 登录 + Cookie 管理 + 内容发布
```

### 阶段 3：使循环真实（中优先级，逐步）

```
3.1 发布后分析            [1-2 周]   从每个平台获取指标。
                                    将数据反馈给决策层。
3.2 跨平台内容改编        [1-2 周]   LLM 驱动摘要。
                                    长文→微博。脚本→推文。
3.3 门级重试循环          [3-5 天]   G1/G2 后重新运行门以验证修复。
                                    添加基于 LLM 的质量门（G6）。
3.4 管线中的 HITL         [3-5 天]   添加 `human_review` 故障模式。
                                    门失败时暂停等待人工批准。
```

### 阶段 4：使基础设施稳固（低优先级，逐步）

```
4.1 持久租户/审计         [1-2 天]   SQLite 后端的 TenantManager + AuditLog
4.2 MCP 服务器分解         [1-2 天]   实施 ADR-004
4.3 注册中心统一           [1-2 天]   实施 ADR-001
4.4 适配器自动注册        [1 天]      在模块导入时自注册
4.5 生产端到端测试         [3-5 天]   实施 S1-S3 测试从设计文档
```

### 路线图摘要

```
立即（下一版本）
  ├── 视频生成（Runway/Pika API 或 FFmpeg 组装）
  ├── 真实话题收集（至少 2 个来源）
  ├── YouTube 适配器（OAuth2 已就绪，需要适配器类）
  ├── 小红书 Playwright 自动化
  └── 决策层 LLM 集成（使策略真实）

下一版本
  ├── TikTok + Twitter 适配器
  ├── 发布后分析（来自每个平台指标）
  ├── LLM 质量门（G6）
  └── 门级重试循环

中期
  ├── 跨平台内容改编
  ├── Bilibili + Weibo 适配器
  └── 语音克隆

长期
  ├── 持久租户/审计
  ├── A/B 测试
  ├── 内容审核
  ├── 团队协作
  └── Web UI 管理仪表板
```

---

## 附录 A：文件清单 — 按区域

| 区域 | 文件 |
|------|-------|
| **核心入口点** | `src/automedia/__init__.py`, `src/automedia/__main__.py`, `src/automedia/_version.py` |
| **核心层** | `config_loader.py`, `project.py`, `credential_loader.py`, `llm_client.py`, `doctor.py`, `overrides.py`, `logging.py`, `registry.py` |
| **管线** | `runner.py`, `gate_engine.py`, `audio_pipeline.py`, `image_pipeline.py`, `language_config.py` |
| **门（20 个，~~+ D0~~ 已移除）** | `base.py`, `failure_modes.py`, `topic_selection.py`, `content_writer.py`, `fact_check.py`, `humanizer.py`, `copy_review.py`, `brand_cta.py`, `wechat_checklist.py`, `html_hard.py`, `lint.py`, `vision_qa.py`, `pre_send_whisper.py`, `content_semantic.py`, `tts_brand_asset.py`, `mp3_vs_srt.py`, `subtitle_render.py`, `six_step_hard.py`, `h0_human_review.py`, `publish_log_schema.py`, `archive_validation.py`, `platform_integrity.py`, `translation_quality.py` |
| **适配器** | `base.py`, `registry.py`, `publish_engine.py`, `platforms/wechat_publisher.py`, `platforms/zhihu_publisher.py`, `platforms/xiaohongshu_publisher.py`, `platforms/feishu_notifier.py` |
| **MCP 服务器** | `server.py`, `tools.py`, `accounts.py`, `allowlist.py`, `resources.py`, `parallel.py`, `mcp_allowlist.yaml`, `_state.py` |
| **CLI** | `app.py`, `commands/run.py`, `commands/pool.py`, `commands/projects.py`, `commands/adapter.py`, `commands/cron.py`, `commands/archive.py`, `commands/init_cmd.py`, `commands/doctor.py`, `commands/omni.py`, `commands/hitl.py`, `commands/license.py`, `commands/sop.py`, `commands/tenant.py`, `commands/onboard.py`, `commands/account.py` |
| **账户（PRD-4）** | `models.py`, `store.py`, `registry.py`, `session.py`, `auth/__init__.py`, `auth/flows.py`, `auth/oauth2.py` |
| **决策层** | `orchestrator.py`, `base.py`, `diagnostic.py`, `build/brand_positioning.py`, `build/market_research.py`, `build/audience_segmentation.py`, `build/competitor_analysis.py`, `scale/health_diagnosis.py`, `scale/market_revalidation.py`, `scale/audience_deepening.py`, `scale/competitor_tracking.py`, `scale/asset_audit.py`, `strategy/product_optimization.py`, `strategy/content_marketing.py`, `preflight.py`, `dependency.py`, `schema_validator.py`, `audit.py`, `gates/d0_gate.py` |
| **HITL** | `config.py`, `executor.py`, `presets/automated.yaml`, `presets/semi-automated.yaml` |
| **Omni** | `opp_adapter.py`, `ol_adapter.py`, `orf_adapter.py`, `config.py`, `allowlist.py`, `artifact_mapping.py`, `md5_integration.py`, `registry.py` |
| **池** | `db.py`, `collector.py`, `scorer.py`, `dedup.py` |
| **资产库** | `db.py`, `vector_store.py`, `search.py`, `ingest.py`, `migrate.py` |
| **钩子** | `protocol.py`, `md5_tracker.py`, `metrics.py` |
| **租户** | `manager.py`, `rbac.py`, `audit.py` |
| **许可证** | `manager.py`, `verifier.py` |
| **SOP** | `runner.py` |
| **定时任务** | `jobs.yaml` |
| **清单** | `defaults.yaml`, `brand_profile_schema.py`, `model_config_schema.py` |

## 附录 B：环境变量参考

| 变量 | 默认值 | 用途 |
|----------|---------|---------|
| `AUTOMEDIA_LLM_PROVIDER` | `deepseek` | LLM 提供商名称 |
| `AUTOMEDIA_LLM_MODEL` | `deepseek-chat` | 模型标识符 |
| `AUTOMEDIA_LLM_BASE_URL` | `https://api.deepseek.com/v1` | API 端点 |
| `AUTOMEDIA_LLM_API_KEY` | （必需） | API 密钥 |
| `AUTOMEDIA_LLM_TEMPERATURE` | 0.7 | 采样温度 |
| `AUTOMEDIA_LLM_MAX_TOKENS` | 2048 | 最大输出令牌 |
| `AUTOMEDIA_DEFAULT_BRAND` | my-brand | 管线品牌 |
| `AUTOMEDIA_DATA_DIR` | ./data | 数据目录 |
| `AUTOMEDIA_OUTPUT_DIR` | ./output | 输出目录 |
| `AUTOMEDIA_PROJECTS_DIR` | （cwd） | 项目根目录覆盖 |
| `AUTOMEDIA_MASTER_KEY` | （必需用于加密） | AES-256 推导密钥 |
| `AUTOMEDIA_LOG_FORMAT` | console | 日志渲染器（console/json） |
| `AUTOMEDIA_LICENSE_KEY` | 无 | 许可证激活 |
| `AUTOMEDIA_DOTENV_PATH` | `~/.automedia/.env` | 自定义 .env 路径 |
| `AUTOMEDIA_MCP_ALLOWLIST_PATH` | （默认捆绑） | MCP 路径允许列表 |
| `AUTOMEDIA_KEYRING_BACKEND` | auto | 钥匙串后端 |
| `AUTOMEDIA_POOL_DB` | ./data/pool.db | SQLite 池路径 |
| `WX_APPID` | （旧版） | 微信应用 ID |
| `WX_APPSECRET` | （旧版） | 微信应用密钥 |
| `ZHIHU_COOKIE` | （旧版） | 知乎 Cookie |
| `XHS_COOKIE` | （旧版） | 小红书 Cookie |
| ~~`FEISHU_WEBHOOK_URL`~~ | ~~（旧版）~~ | ~~飞书 Webhook~~ ⏭️ out of scope |

---

## 附录 C：发布适配器认证要求

| 平台 | 认证类型 | OAuth2 | Cookie | API 密钥 | 浏览器自动 | 备注 |
|----------|-----------|---------|--------|---------|-------------|-------|
| 微信 | `client_credential` | ✅ 服务器到服务器 | ❌ | ❌ | ❌ | 令牌 TTL 2h |
| 知乎 | Cookie | ❌ | ✅ | ❌ | ✅ | 无官方 OAuth |
| 小红书 | Cookie | ❌ | ✅ | ❌ | ✅ | 无公共 API |
| ~~飞书~~ | ~~Webhook URL~~ | ⏭️ out of scope | — | — | — | IM 通知属 agent 框架职责 |
| YouTube | OAuth2 | ✅ authorization_code | ❌ | ❌ | ❌ | 标准 Google OAuth |
| Twitter/X | OAuth2 | ✅ OAuth 2.0 PKCE | ❌ | ❌ | ❌ | Twitter API v2 |
| TikTok | OAuth2 | ✅ authorization_code | ❌ | ❌ | ❌ | TikTok 开发者 OAuth |
| Bilibili | OAuth2 | ✅ authorization_code | ❌ | ❌ | ❌ | Bilibili 开放平台 |
| Weibo | OAuth2 | ✅ authorization_code | ❌ | ❌ | ❌ | 微博开放平台 |
| Instagram | OAuth2 | ✅ authorization_code | ❌ | ❌ | ❌ | Instagram Graph API |
| LinkedIn | OAuth2 | ✅ authorization_code | ❌ | ❌ | ❌ | LinkedIn 营销 API |

---

## 13. 可选引擎抽象层设计方案

> 此节记录 2026-07-12 架构设计决策：将每个模态（TTS、ASR、生图、视频）的引擎实现抽象为可切换接口。设计征求并确认与项目哲学一致（默认开源轻量 → 用户自选）。

### 13.1 设计动机

当前每个模态的引擎是硬编码的：`audio_pipeline.py` 直接 subprocess 调用 edge-tts 和 whisper，`image_pipeline.py` 直接 HTTP 调用 ComfyUI。用户无法在不改代码的情况下切换引擎。

**设计目标：**
- 每个模态定义一个 `BaseEngine` ABC
- 具体实现（EdgeTTSEngine、WhisperASREngine、ComfyUIImageEngine 等）实现该接口
- 用户通过 `defaults.yaml` 的 `engines:` 配置段选择引擎
- 默认值仍是开源轻量方案（edge-tts、Whisper、ComfyUI、HyperFrames）
- 所有引擎必须提供 `check_available()` 验证就绪状态，失败时报错而非无声降级
- OPP/OL/ORF 作为内部文件处理和本地化模块，不受此层影响

### 13.2 架构

```
┌──────────────────────────────────────────────┐
│              Pipeline (无感知具体引擎)          │
│  AudioPipeline  ImagePipeline  [...video]    │
└──────────┬──────────────────────┬────────────┘
           │ resolve_engine()     │ resolve_engine()
           ▼                      ▼
┌──────────────────────────────────────────────┐
│          Engine 解析层                         │
│  resolve_engine("tts", config)  → 引擎实例    │
│  resolve_engine("asr", config)  → 引擎实例    │
│  resolve_engine("image", config)→ 引擎实例    │
│  resolve_engine("video", config)→ 引擎实例    │
└──────────┬──────────────────────┬────────────┘
           │                      │
           ▼                      ▼
┌──────────────────────────────────────────────┐
│        具体引擎实现 (implementations/)         │
│  EdgeTTSEngine  WhisperASREngine              │
│  ComfyUIImageEngine  HyperFramesVideoEngine   │
└──────────────────────────────────────────────┘
```

### 13.3 注册机制 — 采用 GateRegistry 的自动注册模式

三种已有模式的对比：

| 模式 | 例子 | 工作机制 | 选择理由 |
|---------|-------|-------------|------------|
| 手动注册 | `AdapterRegistry.register(WechatPublisher)` | 必须显式调用 | 适合平台适配器（用户直面） |
| 自动注册 | `BaseGate.__init_subclass__` | 定义类即注册 | **引擎采用此模式** |
| 函数式配置 | `llm_client.py` 读 `config["llm"][task_type]` | 运行时取配置 | 配置段设计参考此模式 |

引擎采用 `__init_subclass__` 自动注册，原因：
- 新引擎 = 定义一个类 = 自动被发现
- 无需额外注册步骤（开发者已熟悉此模式）
- 支持第三方引擎：import 即触发注册

```python
class EdgeTTSEngine(BaseTTSEngine):
    engine_name = "edge-tts"     # → 自动注册到 EngineRegistry
    modality = "tts"             # → 按模态分组
```

### 13.4 接口设计 — 每模态一个 ABC

| 抽象类 | 核心方法 | 当前默认实现 | 现有代码来源 |
|----------|------------|--------------|-------------------|
| `BaseTTSEngine` | `synthesize(text, voice, output_path) → str` | `EdgeTTSEngine` | `audio_pipeline.py:52` |
| `BaseASREngine` | `transcribe(audio_path, language) → dict` | `WhisperASREngine` | `audio_pipeline.py:120` |
| `BaseImageEngine` | `generate(prompt, width, height, output_path) → str` | `ComfyUIImageEngine` | `image_pipeline.py:48` |
| `BaseVideoEngine` | `render(assets, output_path) → str` | `HyperFramesVideoEngine` | 新建（当前零代码） |
| `BaseEngine` (公共) | `check_available() → (bool, str)` | — | 共享基础设施 |

公共基类 `BaseEngine` 处理：
- `engine_name` / `modality` 类属性（注册键 + 分组）
- `__init_subclass__` 自动注册到 `EngineRegistry`
- `__init__(engine_config)` 接收引擎级配置
- `check_available()` 验证外部依赖是否就绪
- `validate_config()` 校验配置完整性

### 13.5 引擎注册表 — EngineRegistry

```python
class EngineRegistry(BaseRegistry):
    def list_by_modality(self, modality: str) -> list[str]: ...
    def get_default(self, modality: str, config: dict) -> type: ...

# 内置默认引擎映射（config 未设置时回退）
_DEFAULT_ENGINES = {
    "tts": "edge-tts",
    "asr": "whisper",
    "image": "comfyui",
    "video": "hyperframes",
}
```

### 13.6 配置方案

新增 `defaults.yaml` 配置段：

```yaml
engines:
  tts:
    default: edge-tts
    edge-tts:
      voice: zh-CN-YunxiNeural
    elevenlabs:                           # 预留
      voice: Rachel
      api_key: ""
  asr:
    default: whisper
    whisper:
      model: tiny
      language: zh
  image:
    default: comfyui
    comfyui:
      host: 127.0.0.1
      port: 8188
      timeout: 300
  video:
    default: hyperframes
    hyperframes:
      quality: high
```

**引擎选择流程：**
```
config["engines"]["tts"]["default"] = "edge-tts"
  → EngineRegistry.get("edge-tts") → EdgeTTSEngine 类
  → 注入 config["engines"]["tts"]["edge-tts"] 作为 engine_config
  → check_available() 验证 edge-tts CLI 存在
  → Pipeline 使用 engine.synthesize(...)
```

### 13.7 错误处理 — 无声降级明确废止

当前 `image_pipeline.py` 在 ComfyUI 不可达时返回纯灰色 PIL 占位符——这**必须停止**。

| 场景 | 异常 | 行为 |
|---------|-----------|---------|
| 引擎未注册 | `KeyError` | "没有注册 'foo' 引擎。可用的 TTS 引擎：edge-tts, elevenlabs" |
| 依赖未安装 | `EngineNotFoundError` | "引擎 'whisper' 不可用：'whisper' CLI 未找到。安装：pip install automedia[asr-whisper]" |
| 服务器不可达 | `EngineExecutionError` | "ComfyUI 服务器 127.0.0.1:8188 在 3 次重试后不可达" |
| CLI 返回错误 | `EngineExecutionError` | "edge-tts 失败 (rc=1)：<stderr>" |

`resolve_engine()` 工厂函数确保引擎在首次使用前完成可用性检查。不可用则提早报错，管线在进入实际生产步骤前停止。

### 13.8 管线集成模式

`AudioPipeline` 和 `ImagePipeline` 的修改模式一致：

```python
class AudioPipeline:
    def __init__(self, config=None):
        self._config = config or {}
        self._tts_engine = None    # lazy init

    def _get_tts_engine(self) -> BaseTTSEngine:
        if self._tts_engine is None:
            self._tts_engine = resolve_engine("tts", self._config)
        return self._tts_engine

    def generate_tts(self, text, voice=None, output_path=""):
        engine = self._get_tts_engine()
        return engine.synthesize(text, voice=voice, output_path=output_path)
```

**向后兼容**：无参构造 `AudioPipeline()` → lazy 加载 config → 默认引擎 → 行为完全不变。

### 13.9 目录结构

```
src/automedia/engines/              # 新增包
├── __init__.py                     # resolve_engine() 公共入口
├── base.py                         # BaseEngine + 4 个模态 ABC
├── registry.py                     # EngineRegistry(BaseRegistry) 单例
├── errors.py                       # EngineNotFoundError, EngineExecutionError
└── implementations/                # 具体引擎实现
    ├── __init__.py
    ├── tts_edge.py                 # EdgeTTSEngine
    ├── asr_whisper.py              # WhisperASREngine
    ├── image_comfyui.py            # ComfyUIImageEngine
    └── video_hyperframes.py        # HyperFramesVideoEngine（新建）
```

### 13.10 实施路线图

| 阶段 | 内容 | 并行可能性 | 工作量 |
|-------|---------|-------------|--------|
| **P1 基础设施** | `base.py` + `registry.py` + `errors.py` + `defaults.yaml` 更新 + `config_loader.py` 兼容映射 | 单线 | 1-2 天 |
| **P2 引擎实现** | 4 个引擎：从现有代码提取 + `check_available()` | ✅ 全并行（每引擎独立） | 1-2 天/个 |
| **P3 管线集成** | `AudioPipeline` 和 `ImagePipeline` 改从 config 读引擎 | 单线 | 1-2 天 |
| **P4 可选依赖** | `pyproject.toml` extras + 公共 API 导出 | ✅ 全并行 | 0.5 天 |

### 13.11 与现有模式的对照

| 维度 | 引擎层选择 | 对应现有模式 | 原因 |
|--------|-----------|---------------------|--------|
| 注册 | `__init_subclass__` 自动注册 | `BaseGate` → `GateRegistry` | 零额外步骤，开发者熟悉 |
| 单例 | `EngineRegistry(BaseRegistry)` | `GateRegistry` / `AdapterRegistry` | 复用已有基础设施 |
| 配置 | `config["engines"][modality]` 驱动 | `config["llm"][task_type]` | 一致的用户体验 |
| 错误 | `EngineNotFoundError` 链式 | `LLMError` + `ImportError` | 一致的报错风格 |
| 可选依赖 | `pip install automedia[extras]` | `pip install automedia[openai]` | 复用已有 extras 模式 |
| 接口 | `ABC` + `abstractmethod` | `BasePlatformAdapter(ABC)` | 一致的契约设计 |

---

*此审计基于代码库直接检查、模块级文件阅读和架构分析。配套文档 `docs/archive/coverage-gaps.md`（现标注为被本文替代）提供逐项差距摘要表。§13 记录 2026-07-12 可选引擎抽象层设计方案，与项目"默认开源轻量 + 用户自选"哲学一致。*
