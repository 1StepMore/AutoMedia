## PRD-1: AutoMedia 通用化 — 产品需求文档

> **版本**: v1.0 | **状态**: 草案 | **作者**: 产品团队 | **日期**: 2026-07-07
> **目标读者**: 实现工程师团队 + PM | **关联文档**: PRD-2 Omni 集成(独立), PRD-3 商用一站式(独立)

---

## 0 引言

本章说明项目背景、当前痛点、本 PRD 的覆盖边界及与兄弟 PRD 的关系。

AutoMedia 是壹目贯维(OneStepMore)打造的一个端到端 AI 内容生产流水线,每日 2 话题 x 5 平台(微信/知乎/小红书/抖音/B站) x 4 模态(文/图/视/音)全自动生产,经过 14+ 道强制 Gate, 累计交付 30+ 项目。该系统通过 skill 体系、cron 调度器、subprocess sandbox 和 subagent 委派机制串联全部生产逻辑。从热点采集到多平台发布,整个流程在无人值守状态下每日稳定运行。

这个系统经历了从半自动到全自动、从单模态到多模态、从单一平台到五平台并发的演进过程。当前的生产能力是经过近三个月生产验证的成果,其核心价值在于三个体系的融合:内容生产编排(选题到门控到并行 Track 到多平台适配)、质量门控体系(14 道自动化 Gate,每道都有失败模式和修复流程)、以及模块化驱动架构。

**当前痛点**:

- **运行时环境强耦合**: Python 脚本路径和项目目录均基于特定 WSL 路径硬编码, 无法脱离原环境运行。这意味着任何想使用 AutoMedia 的第三方用户都必须先复现相同的目录结构和环境配置, 这是一个很高的准入门槛。
- **路径硬编码**: 所有脚本引用、项目目录、hook 路径均基于 WSL 绝对路径, 部署到新环境需全局替换。这不仅限制了部署位置, 也给版本控制和团队协作带来了困难。
- **调度器绑定**: cron 调度由内置 scheduler 管理, 其 `jobs.json` 格式与 grace period 机制是专有的。脱离原环境后, 每日的定时采集、推送、健康检查都需要重新实现。
- **LLM Provider 绑定**: LLM 调用通过单一 API 通道, 未预留通用 OpenAI/Anthropic 兼容接口。这导致模型选择受限, 用户无法切换到自己喜欢的 LLM provider。
- **品牌硬编码**: "壹目贯维"品牌名、CTA 规则、禁止词均嵌入脚本和文档, 无法切换品牌。如果想用同一套系统运营另一个品牌, 需要逐个文件修改, 极易遗漏。

**本 PRD 范围**: 仅覆盖"目标 1: 通用化"——将 AutoMedia 改造为可被任意 AI agent / Python SDK / 无 agent 最终用户统一调用的三层(库 -> CLI -> MCP)后端。PRD-2(Omni 集成)和 PRD-3(商用一站式)是本 PRD 之后的独立路线图, 本 PRD 不涉及。三个 PRD 按阶段推进, 每个 PRD 的交付物都是下一个 PRD 的前提条件。

---

## 1 目标与非目标

本章定义 5 个 SMART 目标和 6 个明确的 non-goals, 划定本轮通用化改造的边界。SMART 目标要求具体(Specific)、可衡量(Measurable)、可达成(Achievable)、相关(Relevant)、有时限(Time-bound)。Non-goals 明确告诉团队什么不在本轮范围内, 避免范围蔓延。

### 1.1 目标

| # | 目标 | 衡量标准 | 时间 |
| G1 | AutoMedia 独立运行 | AutoMedia 全流水线在裸 Python 3.11+ 环境中完整运行一次, 14 道 Gate 按原顺序/依赖/阻断逻辑全部执行通过 | M1 完成时 |
| G2 | 三层入口(库/CLI/MCP)全部可用 | `pip install automedia` 后可通过 `import automedia`、`automedia run` CLI、MCP client 三种方式调用 pipeline | M3 完成时 |
| G3 | 配置体系支持任意品牌/平台 | brand-profile.yaml 切换品牌后, 生产内容 CTA/禁止词/品牌名全部更新; platform-adapter 注册新平台后发布引擎识别新目标 | M4 完成时 |
| G4 | 通用调度器 | 每日 08:00/08:05/08:30/09:30 四个 job 在新调度方案上稳定运行 7 天无漏跑 | M2 完成时 |

### 1.2 非目标

| # | 非目标 | 理由 |
|---|--------|------|
| NG1 | 不替换 ComfyUI / HyperFrames / Whisper / edge-tts / FFmpeg 等工程依赖 | 这些是 prerequisites, AutoMedia 库 assumes 已安装 |
| NG2 | 不引入 Omni 一站式界面 | 那是 PRD-2 的范围 |
| NG3 | 不构建 SaaS / 多租户 Web 平台 | 那是 PRD-3 的范围, 本 PRD 只做 tenant_id 字段预留 |
| NG4 | 不重新设计 Gate 逻辑本身 | 14 道 Gate 的检查内容和阻断条件是已有资产, 本 PRD 只做封装和保留 |
| NG5 | 不改动 HyperFrames HTML+GSAP -> MP4 视频方案 | 该方案已验证为唯一视频生产路径 |
| NG6 | 不新增内容生产平台(如 Instagram/X/YouTube) | platform-adapter 注册表结构预留, 具体 adapter 实现由后续迭代完成 |
| NG7 | 不与任何既有项目做数据或配置迁移 | AutoMedia 作为独立系统从零运行, 不迁移既有项目的数据、配置或 pool.db 内容 |
| NG8 | 不强制要求部署环境连接飞书/微信等 IM 平台 | 飞书/微信 adapter 默认禁用, 仅按需启用; 系统在无 IM 配置时仍可本地运行 |

---

## 2 用户与使用场景

本章定义 3 类目标用户, 每类给出 2-3 个典型使用场景, 指导功能需求的优先级分配。

### 2.1 第一类: 通用 MCP Client Agent

**画像**: 运行 Claude、OpenCode、Cline 等 MCP client 的 AI agent, 需要通过 MCP 协议调用内容生产流水线。

**场景 1 — 话题选择与生产启动**: Agent 通过 MCP tool `select_topic` 浏览话题池, 调用 `run_pipeline` 启动双话题全链路生产, 通过 `get_pipeline_status` 轮询进度。

**场景 2 — 资产获取与归档**: Agent 在生产完成后调用 `get_project_assets` 获取交付物列表, 用户确认后通过 `archive_project` 归档。

**场景 3 — 多 agent 协作**: Agent A 负责选题, Agent B 负责生产, Agent C 负责发布, 三者通过 MCP server 共享状态和产物。每个 agent 只调用自己职责范围内的 MCP tool, 避免单 agent 权限过大。

**场景 4 — 批量生产**: 运营团队在早会上确定当天 5 个话题, 通过脚本批量调用 `run_pipeline` 五次, 各自生成不同品牌的内容。MCP server 的并发处理能力支撑多 pipeline 同时运行。

### 2.2 第二类: Python SDK 开发者

**画像**: 需要在自有 Python 脚本或 Web 后端中嵌入 AutoMedia 生产能力的开发者。

**场景 1 — 自动化流水线集成**: 开发者编写 `automedia.run_full_pipeline(topic="...", brand="...")` 嵌入每日生产任务, 通过 GateHook 接收每个门控的通过/失败事件。

**场景 2 — 定制化品牌适配**: 多品牌运营方通过切换 `brand-profile.yaml` 配置, 在同一套代码中为不同品牌运行不同 CTA/禁止词/风格的流水线。

**场景 3 — 自定义发布 adapter**: 开发者继承 `BasePlatformAdapter` 实现自有平台的发布逻辑, 通过 `register_adapter()` 注入流水线。

### 2.3 第三类: 无 Agent 最终用户

**画像**: 不运行任何 AI agent, 仅通过命令行或简单配置使用 AutoMedia 的手动操作者。

**场景 1 — 一键生产**: 用户执行 `automedia run --topic "AI 视频生成新进展" --brand my-brand`, 等待流水线完成后在项目目录获取全部产物。

**场景 2 — 定时生产**: 用户通过系统 crontab 或 systemd timer 配置 `automedia run --topic-pool`, 每日自动采集/评分/生产/发布。

**场景 3 — 项目审计**: 用户执行 `automedia list-projects --status published` 查看历史项目, 或 `automedia get-assets <project-id> --format json` 获取产物清单。这对于内容排期和发布复盘非常有用。

**场景 4 — 手动归档**: 用户在使用 CLI 完成内容生产后, 确认内容无误, 执行 `automedia archive --project <id> --force` 完成归档。注意 `--force` 参数是必需参数, 防止误操作。

---

## 3 功能需求

本章按 P0/P1/P2 三级优先级, 以表格形式定义全部功能需求。P0 为必须交付, P1 为重要但不阻塞发布, P2 为锦上添花。

### 3.1 P0 — 必须交付

| ID | 名称 | 用户故事 | 验收标准 | 优先级 |
|----|------|---------|---------|--------|
| F-001 | 三层入口封装 | 作为一个 Python 包, 我希望通过 `import automedia` 调用核心流水线, 因为我是 SDK 用户 | `pip install automedia` 后可用 `from automedia import Pipeline` 创建实例并调用 `pipeline.run()` | P0 |
| F-002 | CLI 入口 | 作为无 agent 用户, 我希望通过终端命令直接运行流水线, 因为我习惯命令行操作 | `automedia run --topic "..." --brand my-brand` 执行完整流水线; `automedia --help` 列出全部子命令 | P0 |
| F-003 | MCP Server 入口 | 作为 MCP client agent, 我希望通过 MCP 协议调用 AutoMedia, 因为我的 agent 支持标准 MCP tool | MCP server 启动后暴露 select_topic / run_pipeline / get_pipeline_status / list_projects / get_project_assets / archive_project / list_topic_pool / register_platform_adapter 等 8 个 tool | P0 |
| F-004 | 黑盒 pipeline.run() 主入口 | 作为一个开发者, 我调用 `pipeline.run(topic, brand)` 就能启动完整流水线, 不需要了解内部 Gate 细节 | `pipeline.run()` 接收 topic 和 brand 参数, 返回 PipelineResult(status, project_dir, assets, gates_log); 内部顺序执行 14 道 Gate | P0 |
| F-005 | 配置体系 — model_config.yaml | 作为运营者, 我希望通过 YAML 配置 LLM 模型参数, 不硬编码 Provider | model_config.yaml 支持 OpenAI 兼容格式 / Anthropic / 自定义 endpoint; 运行时切换 model 后所有 LLM 调用指向新 provider | P0 |
| F-006 | 配置体系 — brand-profile.yaml | 作为多品牌运营者, 我希望每个品牌有独立的品牌 DNA/CTA/禁止词配置 | brand-profile.yaml 包含 brand_name / cta_principles / blocked_words / tone_guidelines; 切换 brand 后全链路使用新品牌配置 | P0 |
| F-007 | 配置体系 — platform adapters 注册表 | 作为开发者, 我希望通过注册 adapter 的方式来新增/替换发布平台 | `BasePlatformAdapter` 抽象类定义 publish(project_dir) -> PublishResult; registry 支持 `register_adapter("wechat", WechatAdapter())` 和 `list_adapters()` | P0 |
| F-008 | 配置体系 — 内置默认 + 用户覆盖双层 | 作为用户, 我希望库自带默认配置开箱即用, 同时允许我覆盖部分配置 | 库内置 `defaults.yaml`; 项目级 `.automedia/` 覆盖; 用户级 `~/.automedia/overrides/` 覆盖; 环境变量 `AUTOMEDIA_*` 最高优先级 | P0 |
| F-009 | Gate hooks (只读观察者) | 作为监控开发者, 我希望在每个 Gate 执行前后获得通知, 但不允许我修改 Gate 内部状态 | GateHook Protocol 定义 `before_gate(gate_name, context)`, `after_gate(gate_name, context, result)`, `on_gate_failed(gate_name, context, exception)` 三个方法; 全部返回 None | P0 |
| F-010 | 通用调度器 | 作为运维人员, 我希望通过通用调度器实现每日定时生产 | 调度器支持每日 08:00/08:05/08:30/09:30 四个 job; 每个 job 有 name / schedule / command / depends_on / on_failure 定义; pre-flight 4 步健康检查保留 | P0 |
| F-011 | 状态与产物元数据管理 | 作为审计者, 我希望每个项目的状态和每个 Gate 产物 MD5 都被记录 | pool.db (SQLite) 管理话题池状态; project_dir 存储项目文件; pipeline_md5.json 记录每个 Gate 产物的 MD5; 三者状态一致 | P0 |
| F-012 | 架构解耦点全数拆分 | 作为重构工程师, 我希望有一个清单追踪所有架构耦合点, 确保无遗漏 | 耦合点清单列出全部 20+ 项(路径硬编码 / 环境依赖 / 调度器绑定 / LLM Provider 绑定 / etc), 每项标明解耦状态 | P0 |
| F-013 | 14 道 Gate 与失败模式知识库封装 | 作为新开发者, 我希望 Gate 和其失败模式一起封装到新系统, 不丢失生产经验 | 每个 Gate 在代码中附带 failure_mode 知识条目; `pipeline_md5.json` 记录; 已有 QA 检查项全部保留 | P0 |
| F-014 | 4 模态管线保留 | 作为内容创作者, 我希望文字/图片/视频/语音 4 条管线在解耦后功能不变 | 文案管线调用 LLM+humanizer+copy-review+brand-cta; 图片管线调用 ComfyUI+Vision QA; 视频管线调用 HyperFrames; 语音管线调用 edge-tts+Whisper; 全部可独立运行 | P0 |
| F-015 | 多平台发布引擎解耦 | 作为发布管理员, 我希望发布逻辑是与核心流水线解耦的独立模块 | `PublishEngine` 类接收 project_dir + platform_list, 遍历已注册 adapter 按序发布; 发布结果写入 publish_log.json | P0 |
| F-017 | `automedia init` CLI 命令 | 作为新用户, 我希望通过一个命令初始化项目骨架、配置和 pool.db, 快速开始使用 | `automedia init` 创建项目目录结构, 生成默认 `~/.automedia/` 配置目录(含 defaults.yaml / model_config.yaml / brand-profile.yaml / adapters/registry.yaml), 初始化 pool.db, 并打印下一步指引 | P0 |

### 3.2 P1 — 重要功能
| ID | 名称 | 用户故事 | 验收标准 | 优先级 |
|----|------|---------|---------|--------|
| F-101 | 话题池管理 CLI | 作为运营者, 我希望通过 CLI 管理话题池, 无需手动操作 SQLite | `automedia pool list --status pending`, `automedia pool add --topic "..."`, `automedia pool prune` 三个子命令 | P1 |
| F-102 | 生产指标记录 | 作为管理者, 我希望每次生产的关键耗时/门控通过率被记录, 用于持续改进 | `production_metrics.json` 记录每个阶段耗时、每个 Gate 通过/重试次数、总耗时; metrics 可通过 `automedia metrics <project-id>` 查看 | P1 |
| F-103 | Pipeline 断点续跑 | 作为运维人员, 我希望流水线在 Gate 失败修复后可从失败点恢复, 而非从头开始 | `pipeline.run(resume_from=<gate_name>)` 跳过已通过的 Gate, 从指定 Gate 恢复; 依赖 pipeline_md5.json 判断完成状态 | P1 |
| F-104 | overrides 子系统 — rules | 作为高级用户, 我希望通过 `~/.automedia/overrides/rules/*.yaml` 自定义规则 | rules 目录下每个 YAML 文件定义额外的 Gate 规则; 覆盖系统自动加载并合并到 Gate 检查中 | P1 |
| F-105 | overrides 子系统 — prompts | 作为 prompt 工程师, 我希望通过 `~/.automedia/overrides/prompts/*.j2` 自定义 LLM 提示词模板 | prompts 目录下的 Jinja2 模板覆盖内置 prompt; 支持变量注入(brand_name, topic, platform) | P1 |
| F-106 | 平台 adapter 模板生成 | 作为新平台接入者, 我希望通过 CLI 生成 adapter 模板代码, 减少重复工作 | `automedia adapter create --name youtube` 生成 `adapters/youtube.py` 模板文件, 包含 BasePlatformAdapter 的桩代码 | P1 |

### 3.3 P2 — 优化功能

| ID | 名称 | 用户故事 | 验收标准 | 优先级 |
|----|------|---------|---------|--------|
| F-201 | MCP tool 权限分级 | 作为安全管理员, 我希望 MCP tool 根据角色有不同权限 | `archive_project` 需要 `--force` 标记; `run_pipeline` 需要 `select_topic` 前置 | P2 |
| F-202 | 多语言 brand-profile | 作为多语言创作者, 我希望 brand-profile 支持各语言的 CTA 规则 | brand-profile.yaml 可定义 `languages: { zh: {...}, en: {...} }` | P2 |
| F-203 | 生产通知 webhook | 作为外部系统集成者, 我希望生产完成时通过 webhook 通知我的系统 | Pipeline 完成后回调配置的 webhook URL, 携带 project_id / status / assets_url | P2 |
| F-204 | 项目模板系统 | 作为批量生产者, 我希望预定义项目模板, 一键创建标准项目 | `automedia project init --template standard` 创建标准目录结构; 模板定义在 `.automedia/templates/` | P2 |

---

## 4 架构设计

本章给出通用化后的 AutoMedia 整体架构, 包括分层结构、配置加载顺序、三层入口关系、以及三种调用方式的最小示例。

### 4.1 整体架构(ASCII)

```
                    ┌───────────────────────────────────────────────────┐
                    │                   外部调用层                        │
                    │   ┌──────────┐  ┌──────────┐  ┌──────────────┐   │
                    │   │ Any MCP  │  │ Python   │  │ CLI 终端     │   │
                    │   │ Client   │  │ Script   │  │ (无 agent)   │   │
                    │   │ Agent    │  │ SDK      │  │              │   │
                    │   └────┬─────┘  └────┬─────┘  └──────┬───────┘   │
                    └────────┼─────────────┼───────────────┼───────────┘
                             │             │               │
                    ┌────────┼─────────────┼───────────────┼───────────┐
                    │        ▼             ▼               ▼           │
                    │  ┌───────────────────────────────────────────┐   │
                    │  │           MCP Server Layer                │   │
                    │  │  (mcp official Python SDK)               │   │
  │  │  Tools: select_topic, run_pipeline,      │   │
  │  │  get_pipeline_status, list_projects,     │   │
  │  │  get_project_assets, archive_project,    │   │
  │  │  list_topic_pool, register_platform_adapter  │   │
                    │  └────────────────┬──────────────────────────┘   │
                    │                   │                              │
                    │  ┌────────────────┴──────────────────────────┐   │
                    │  │           CLI Layer (typer)               │   │
                    │  │  automedia run / list / pool / adapter    │   │
                    │  └────────────────┬──────────────────────────┘   │
                    │                   │                              │
                    │  ┌────────────────┴──────────────────────────┐   │
                    │  │           automedia/ 核心 Python 包       │   │
                    │  │                                           │   │
                    │  │  ┌─────────┐  ┌──────────┐  ┌─────────┐  │   │
                    │  │  │ core/   │  │pipelines/│  │ gates/  │  │   │
                    │  │  │ config  │  │run_full  │  │ G0-G13  │  │   │
                    │  │  │ loader  │  │_pipeline │  │ +failure│  │   │
                    │  │  │ .run()  │  │ .py      │  │ _modes  │  │   │
                    │  │  └─────────┘  └──────────┘  └─────────┘  │   │
                    │  │                                           │   │
                    │  │  ┌─────────┐  ┌──────────┐  ┌─────────┐  │   │
                    │  │  │adapters/│  │manifests/│  │ hooks/  │  │   │
                    │  │  │platform │  │brand     │  │ GateHook│  │   │
                    │  │  │notifier │  │.yaml     │  │ protocol│  │   │
                    │  │  │publisher│  │model.yaml│  │ .py     │  │   │
                    │  │  └─────────┘  └──────────┘  └─────────┘  │   │
                    │  └───────────────────────────────────────────┘   │
                    │                                                 │
                    │  ┌───────────────────────────────────────────┐   │
                    │  │           外部工程依赖(prerequisites)      │   │
                    │  │  ComfyUI / Chrome Headless / Whisper CPU  │   │
                    │  │  edge-tts CLI / Bun / FFmpeg / mamba env  │   │
                    │  └───────────────────────────────────────────┘   │
                    └─────────────────────────────────────────────────┘
```

### 4.2 分层设计说明

从 ASCII 架构图可以看出, 系统从外到内分为四层, 每层职责清晰:

**外层: 外部调用层**。这一层是用户的接触点, 包括任何 MCP client agent(如 Claude Desktop、OpenCode、Cline)、Python SDK 调用者、以及 CLI 终端用户。三种入口面向不同的用户群体, 但都指向同一个核心。

**中间层 1: MCP Server + CLI 层**。MCP server 基于 mcp official Python SDK 实现, 面向 AI agent 生态。它暴露 8 个标准 tool, 覆盖从选题到归档的完整生命周期。CLI 基于 typer, 面向手动操作者和运维脚本。CLI 的 `run` 子命令也用于 cron 任务的执行入口。这两层不包含业务逻辑, 只做参数解析、校验和结果格式化, 所有实际工作委托给核心 Python 包。

**中间层 2: 核心 Python 包 `automedia/`**。这是系统的核心, 包含六个子包: `core/(配置加载、项目管理、凭证管理)`, `pipelines/(pipeline.run() 编排逻辑)`, `gates/(14 道 Gate 的实现和失败模式知识库)`, `adapters/(平台发布 adapter 和通知 adapter)`, `manifests/(YAML 配置模型定义)`, `hooks/(GateHook 协议和内置钩子)`。六个子包有清晰的依赖方向: core 是基础设施, gates 和 adapters 独立于彼此, pipelines 协调它们。

**最内层: 外部工程依赖**。这些是 AutoMedia 运行时必需的工程工具, 但不是 AutoMedia 代码库的一部分。系统通过 subprocess 调用它们。部署环境需提前安装这些依赖。

**本地部署与 IM 无关性**: 核心 `pipeline.run()` 路径不依赖任何 IM 平台。飞书/微信公众号 adapter 默认禁用, 只有在用户显式设置环境变量并启用 adapter 后才会被调用。因此, 纯本地部署(只配置 LLM provider)即可运行完整内容生产流水线, 无需飞书/微信账号或网络可达性。

### 4.3 配置加载顺序

配置按以下优先级从低到高叠加, 高优先级覆盖低优先级:

```
1. 库内置 defaults.yaml       ← 最底层, 开箱即用的默认值
2. 项目 .automedia/            ← 项目级配置(版本控制)
3. 用户 ~/.automedia/          ← 用户级配置(全局覆盖)
4. 用户 ~/.automedia/overrides/rules/*.yaml    ← 自定义 Gate 规则
5. 用户 ~/.automedia/overrides/prompts/*.j2    ← 自定义 LLM 提示词
6. 环境变量 AUTOMEDIA_*       ← 最高优先级, 部署时注入
```

配置加载器 `automedia/core/config_loader.py` 按上述顺序逐层读取、合并、返回最终配置字典。所有模块通过 `config = ConfigLoader.load()` 获取配置, 不直接读取 YAML 文件。

### 4.4 三层入口共用实现

三层入口共享同一个 `pipeline.run()` 实现, 不重复代码:

```
CLI (typer)  ──>  parse argv ──>  call pipeline.run() ──>  print result
MCP Server   ──>  JSON-RPC  ──>  call pipeline.run() ──>  return JSON
SDK          ──>  import    ──>  call pipeline.run() ──>  return Python object
```

核心函数签名在 `automedia/pipelines/runner.py` 中定义一次, CLI 和 MCP server 仅做参数解析和结果序列化的薄封装。这种设计保证了无论从哪个入口调用, 生产逻辑完全一致, 避免了入口不同导致行为差异的问题。这也是"黑盒"原则的具体体现: 调用者不感知内部 Gate 细节, 内部实现可以独立演进。

以 `pipeline.run()` 为中心的设计还有一个好处: 单元测试只需要覆盖这一个核心路径。CLI 层的测试只需要验证参数解析是否正确传递, MCP 层的测试只需要验证 JSON-RPC 参数是否正确映射, 核心逻辑的测试全部集中在 runner 模块。

### 4.5 最小调用示例

**SDK 调用最小示例:**

```python
from automedia import Pipeline

pipeline = Pipeline(config_dir="~/.automedia/")
result = pipeline.run(
    topic="AI 视频生成工具对比: 2026 年最新格局",
    brand="my-brand"
)

print(f"状态: {result.status}")          # success / failed / partial
print(f"项目目录: {result.project_dir}")
print(f"产物: {result.assets}")           # [{"type": "video", "path": "..."}, ...]
print(f"Gate 日志: {result.gates_log}")   # [{"gate": "G0", "status": "passed", "duration_s": 12}, ...]
```

**CLI 最小示例:**

```bash
# 运行完整流水线
automedia run --topic "AI 视频生成工具对比" --brand my-brand

# 列出项目
automedia list-projects --status published

# 查看话题池
automedia pool list --limit 10
```

**MCP tool 调用 JSON-RPC 示例:**

```json
// 请求: 运行流水线
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "run_pipeline",
    "arguments": {
      "topic": "AI 视频生成工具对比: 2026 年最新格局",
      "brand": "my-brand",
      "mode": "auto"
    }
  },
  "id": 1
}

// 响应
{
  "jsonrpc": "2.0",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{
          \"project_id\": \"20260707_ai-video-tools\",
          \"status\": \"success\",
          \"project_dir\": \"/mnt/d/AutoMedia/projects/20260707_ai-video-tools/\",
          \"gates_passed\": 14,
          \"gates_failed\": 0,
          \"assets\": [
            {\"type\": \"video\", \"path\": \"03_video/video_final.mp4\"},
            {\"type\": \"article\", \"path\": \"01_content/drafts/wechat/wechat_draft.html\"}
          ]
        }"
      }
    ]
  },
  "id": 1
}
```

---

## 5 SDK API 设计(P0)

本章详细定义 `automedia` 包的核心 API, 包括 `run_full_pipeline` 签名、GateHook Protocol、配置加载流程和一段展示全流程的伪代码。SDK API 的受众是 Python 开发者, 设计原则是"简单调用、内聚逻辑、可观测不可干预"。开发者只需要传入话题和品牌名称, 系统自动处理配置加载、Gate 编排、多模态生产和发布。如果开发者需要监控生产过程, 通过 GateHook 接收事件通知; 如果开发者需要自定义行为, 通过配置文件和 overrides 机制实现, 而不是通过 API 参数暴露内部细节。

### 5.1 核心函数签名

```python
def run_full_pipeline(
    topic: str,
    brand: str,
    *,
    hooks: Optional[list[GateHook]] = None,
    mode: Literal["auto", "text_only", "video_only", "qa_only"] = "auto",
    resume_from: Optional[str] = None,
    config_dir: Optional[str] = None,
    tenant_id: str = "default"
) -> PipelineResult:
    """
    执行完整内容生产流水线。

    Args:
        topic: 话题标题。
        brand: 品牌标识符, 对应 brand-profile.yaml 中的品牌名。
        hooks: GateHook 观察者列表。每个 hook 接收 Gate 事件但不可修改 Gate 行为。
        mode: 运行模式。auto=全链路, text_only=仅文案, video_only=仅视频, qa_only=仅 QA。
        resume_from: 从指定 Gate 名称恢复运行(跳过已完成的 Gate)。
        config_dir: 配置目录。默认使用 ~/.automedia/。
        tenant_id: 租户 ID。单租户默认 "default"。

    Returns:
        PipelineResult 包含状态、项目目录、产物列表、Gate 日志。
    """
```

```python
@dataclass
class PipelineResult:
    status: Literal["success", "failed", "partial"]
    project_id: str
    project_dir: str
    topic: str
    brand: str
    assets: list[AssetInfo]
    gates_log: list[GateLogEntry]
    start_time: str            # ISO 8601
    end_time: str              # ISO 8601
    total_duration_s: float
    error: Optional[str] = None

@dataclass
class AssetInfo:
    type: str                  # "video" / "article" / "image" / "audio" / "subtitle"
    path: str                  # 相对 project_dir 的路径
    platform: Optional[str]    # 所属平台(如 "wechat")
    md5: str                   # 文件 MD5

@dataclass
class GateLogEntry:
    gate_name: str             # 如 "G0", "G1", "V0"
    status: str                # "passed" / "failed" / "skipped"
    duration_s: float
    error: Optional[str] = None
```

### 5.2 GateHook Protocol

GateHook 是**只读观察者**模式, 不允许修改 Gate 执行流程。三个方法全部返回 `None`, 不接收 `bool` 返回值:

```python
from typing import Protocol, Any

class GateHook(Protocol):
    """
    Gate 生命周期观察者。
    所有方法必须返回 None。不允许返回 bool 来阻止或放行 Gate。
    """

    def before_gate(self, gate_name: str, context: dict[str, Any]) -> None:
        """
        Gate 执行前调用。
        context 包含当前话题、品牌、项目目录等不可变快照。
        """
        ...

    def after_gate(self, gate_name: str, context: dict[str, Any], result: dict[str, Any]) -> None:
        """
        Gate 执行成功后调用。
        result 包含通过/失败状态、耗时、关键指标。
        """
        ...

    def on_gate_failed(self, gate_name: str, context: dict[str, Any], exception: Exception) -> None:
        """
        Gate 执行失败(抛出异常)时调用。
        注意: 即使 hook 被调用, Pipeline 仍会 STOP。
        """
        ...
```

**设计决策说明**: 选择只读 C 方案而非允许 hook 阻断 Gate(方案 A)或修改 Gate 参数(方案 B)。理由:
- 14 道 Gate 编排逻辑是不可妥协的硬约束, 允许 hook 阻断会引入绕过路径。
- 如需自定义阻断逻辑, 应通过 overrides/rules/*.yaml 配置, 而非 hook 代码。

### 5.3 配置加载流程

```python
# automedia/core/config_loader.py 伪代码

class ConfigLoader:
    @staticmethod
    def load(config_dir: Optional[str] = None) -> Config:
        config = Config()

        # 1. 内置默认
        config.merge(load_yaml(pkg_resource("automedia/defaults/defaults.yaml")))

        # 2. 项目级 .automedia/
        project_config = find_project_config()  # 从 CWD 向上找 .automedia/
        if project_config:
            config.merge(load_yaml(project_config))

        # 3. 用户级 ~/.automedia/
        user_dir = config_dir or Path("~/.automedia/").expanduser()
        if user_dir.exists():
            config.merge(load_yaml(user_dir / "config.yaml"))
            config.merge(load_yaml(user_dir / "model_config.yaml"))
            config.merge(load_yaml(user_dir / "brand-profile.yaml"))

        # 4. overrides 子系统
        overrides_dir = user_dir / "overrides"
        if overrides_dir.exists():
            for rule_file in sorted(overrides_dir.glob("rules/*.yaml")):
                config.merge(load_yaml(rule_file))
            for prompt_file in overrides_dir.glob("prompts/*.j2"):
                config.register_prompt_template(prompt_file.stem, prompt_file)

        # 5. 环境变量覆盖
        for key, value in os.environ.items():
            if key.startswith("AUTOMEDIA_"):
                config.set_env_override(key.removeprefix("AUTOMEDIA_"), value)

        config.validate()  # 校验必需字段
        return config
```

### 5.4 全流程伪代码

```python
# automedia/pipelines/runner.py — 精简伪代码

def run_full_pipeline(topic, brand, *, hooks=None, mode="auto", resume_from=None, config_dir=None, tenant_id="default"):
    # 1. 加载配置
    config = ConfigLoader.load(config_dir)

    # 2. 初始化项目
    project = Project.init(topic=topic, brand=brand, tenant_id=tenant_id,
                           base_dir=config.get("storage.projects_dir"))
    project.write_info()

    # 3. 初始化 Gate 引擎
    engine = GateEngine(config=config, project=project, hooks=hooks or [])

    # 4. 选择 Track(根据 mode)
    tracks = resolve_tracks(mode)  # ["copy", "video"] 或其中之一

    # 5. 执行文案 Track
    if "copy" in tracks:
        engine.run_gate("G0", gate_fact_check, project.research_data)    # 事实核查
        engine.run_gate("G1", gate_humanizer, project.drafts)            # 去 AI 味
        engine.run_gate("G2", gate_copy_review, project.drafts)          # 结构审查
        engine.run_gate("G3", gate_brand_cta, project.drafts, config.brand)  # 品牌 CTA
        # copy 完成后: 平台差异化
        project.generate_platform_drafts(config.platforms)
        engine.run_gate("G4", gate_wechat_checklist, project.wechat_draft)   # 公众号门控
        engine.run_gate("G5", gate_html_hard, project.wechat_draft)          # HTML 硬门控

    # 6. 执行视频 Track
    if "video" in tracks:
        tts_audio = generate_tts(project.script, config.tts)
        srt = whisper_asr(tts_audio)
        srt = llm_proofread(srt, config.brand)
        project.write_audio_and_subtitle(tts_audio, srt)

        # 交接给 HyperFrames
        hf_result = hyperframes_render(project.hyperframes_dir)
        engine.run_gate("V0", gate_lint, hf_result)                       # Lint
        engine.run_gate("V1", gate_vision_qa, hf_result, project.srt)     # Vision QA
        engine.run_gate("V2", gate_pre_send_whisper, hf_result.video)     # Whisper 验证
        engine.run_gate("V3", gate_content_semantic, hf_result, project)  # 语义匹配
        engine.run_gate("V4", gate_tts_brand_asset, tts_audio)            # TTS 品牌资产
        engine.run_gate("V5", gate_mp3_vs_srt, tts_audio, srt)            # 音频 vs 字幕
        engine.run_gate("V6", gate_subtitle_render, hf_result)            # 字幕渲染
        engine.run_gate("V7", gate_6step_hard, hf_result)                 # 6 步硬约束

    # 7. 生命周期 Gate
    engine.run_gate("L1", gate_publish_log_schema, project.publish_log)
    engine.run_gate("L3", gate_platform_integrity, project.assets)

    # 8. 发布
    if config.get("publish.auto", False):
        publisher = PublishEngine(config.adapters, project)
        publisher.publish_all()

    # 9. 通知
    notifier = Notifier(config.get("notifications", {}))
    notifier.notify_complete(project, result)

    # 10. 返回结果
    return PipelineResult(
        status=engine.overall_status(),
        project_id=project.project_id,
        project_dir=str(project.dir),
        assets=project.list_assets(),
        gates_log=engine.get_log(),
        start_time=project.start_time,
        end_time=datetime.now().isoformat(),
        total_duration_s=(datetime.now() - project.start_dt).total_seconds()
    )
```

---

## 6 调度方案(P0)

本章分析现状, 给出 3 个候选项的对比, 推荐方案, 并定义 cron job schema 和 pre-flight 健康检查方式。

### 6.1 现状

每日需要运行 4 个 job:

| 时间 | Job 名称 | 说明 |
|------|---------|------|
| 08:00 | hot-collection | 4 平台热点采集 + Tavily + AIHOT 三层漏斗 -> 写入 pool.db |
| 08:05 | semantic-audit | 语义审核 + 黑名单更新 |
| 08:30 | topic-push | TOP6 话题推送飞书给用户 |
| 09:30 | watchdog | 健康检查(cron job 四步验证) |

### 6.2 三个候选项对比

| 维度 | A: APScheduler 后台进程 | B: systemd timer | C: 外部 cron + CLI |
|------|------------------------|-----------------|-------------------|
| 实现方式 | Python APScheduler 库, 常驻后台进程 | Linux systemd timer 单元 + service | 系统 crontab `automedia cron` 命令 |
| 依赖 | Python 包 + 进程管理(supervisor/systemd) | systemd (Linux 自带) | crontab (所有 Unix 自带) |
| 持久化 | APScheduler 支持 SQLite job store | systemd timer 无状态 | 外部 cron 无状态 |
| on_failure 处理 | Python 内捕获异常并通知 | 需 systemd 健康检查 + 独立通知脚本 | cron 无内置, 需包装脚本 |
| depends_on 支持 | 内置 job 依赖链 | 需 systemd unit 依赖配置 | 需在 CLI 包装脚本实现 |
| 资源占用 | ~50MB 常驻内存 + 一个进程 | 无常驻(trigger 时启动) | cron daemon 极低 |
| 重启恢复 | 需 supervisor 保活 | systemd 自动 | cron 自动 |
| 多环境一致性 | 所有平台一致 | Linux-only | 所有 Unix 一致 |
| 调试友好度 | `python scheduler.py run-once` | `systemctl list-timers` | `crontab -l` 直观 |
| 实施成本 | 需开发调度器进程 + 管理脚本 | 写 4 个 .timer + .service 单元 | 4 行 crontab 条目 |

### 6.3 推荐方案: C (外部 cron + CLI)

**选型理由**:
1. **零依赖**: crontab 是所有 Unix 系统的原生能力, 不引入新的运行时依赖。AutoMedia 通用化目标之一是降低环境要求, APScheduler 常驻进程与这一目标相悖。
2. **极简运维**: 4 行 crontab 即可表达现有调度需求, 运维人员无需学习 systemd timer 语法或 Python 调度器配置。
3. **失败可见**: cron 的 MAILTO 机制和系统日志(`/var/log/syslog`)天然记录执行结果, 无需额外告警设施。
4. **与 CLI 层天然配合**: `automedia cron run <job-name>` 命令可被任何外部调度器调用, 包括 APScheduler 和 systemd timer 作为未来升级路径。

**实现策略**: `automedia cron` 子命令组接收外部调度器的调用, 自身不运行调度循环。

### 6.4 Cron Job Schema

每个 job 在 `~/.automedia/cron/jobs.yaml` 中定义:

```yaml
jobs:
  - name: hot-collection
    schedule: "0 8 * * *"
    command: "automedia pool collect"          # 对应 CLI 子命令
    depends_on: []                             # 无前置依赖
    on_failure: "log"                          # 默认只记录日志; 可选 notify-feishu(需启用 FeishuNotifier)
    timeout_s: 600
    description: "4 平台热点采集 + Tavily + AIHOT"

  - name: semantic-audit
    schedule: "5 8 * * *"
    command: "automedia pool audit"
    depends_on: ["hot-collection"]             # 依赖采集完成
    on_failure: "log"                          # 默认只记录日志; 可选 notify-feishu(需启用 FeishuNotifier)
    timeout_s: 300

  - name: topic-push
    schedule: "30 8 * * *"
    command: "automedia pool push-top6"
    depends_on: ["semantic-audit"]
    on_failure: "log"                          # 默认只记录日志; 可选 notify-feishu(需启用 FeishuNotifier)
    timeout_s: 120

  - name: watchdog
    schedule: "30 9 * * *"
    command: "automedia cron check-health"
    depends_on: []
    on_failure: "log"                          # 默认只记录日志; 可选 notify-feishu(需启用 FeishuNotifier)
    timeout_s: 60
```

### 6.5 Pre-flight 4 步健康检查保留

Watchdog 的四步健康检查实现为 `automedia cron check-health` 命令:

```
Step 1: Job Schema 验证
    -> 检查 ~/.automedia/cron/jobs.yaml 格式正确
    -> 每个 job 有 name / schedule / command / on_failure

Step 2: 执行层验证
    -> automedia --version 返回正常
    -> 依赖的 CLI 工具可用(edge-tts, whisper, bun, ffmpeg)

Step 3: 业务副作用验证
    -> pool.db 可读写
    -> 项目目录可写入
    -> 若 FeishuNotifier 已启用(FEISHU_WEBHOOK_URL 已设置), 则检查飞书通知 API 可达; 否则跳过此项

Step 4: 手动跑验证
    -> 执行 automedia cron run watchdog --dry-run
    -> 打印各步骤检查结果, 不修改状态
```

---

## 7 配置体系设计

本章详述 model_config.yaml、brand-profile.yaml、platform-adapter 注册表、overrides 子系统的文件格式和字段说明。

### 7.1 model_config.yaml

位于 `~/.automedia/model_config.yaml`, 定义所有 LLM 调用配置:

```yaml
# LLM 文本生成(文案/Humanizer/Copy-review 等)
text_generation:
  provider: openai-compatible    # openai-compatible | anthropic | custom
  base_url: "https://api.example.com/v1"
  api_key_env: "AUTOMEDIA_LLM_KEY"  # 从环境变量读取 API key
  model: "deepseek-v4-flash"
  default_params:
    temperature: 0.7
    max_tokens: 4096
    top_p: 0.9

# Vision QA(图片/视频帧审核)
vision:
  provider: openai-compatible
  base_url: "https://api.example.com/v1"
  api_key_env: "AUTOMEDIA_VISION_KEY"
  model: "qwen3.7-plus-vision"
  rate_limit:
    max_calls_per_window: 360     # 全量 QA 限频 450 次/5h 窗口
    window_seconds: 18000
    fallback_mode: "pixel_luminance"  # API 限流时降级为像素亮度法

# 字幕校对(LLM 校对 SRT 文本)
subtitle_proofread:
  provider: openai-compatible
  base_url: "https://api.example.com/v1"
  api_key_env: "AUTOMEDIA_LLM_KEY"
  model: "deepseek-v4-flash"
  default_params:
    temperature: 0.3
    max_tokens: 2048
```

**关键设计**: 支持任意 OpenAI 兼容格式的 API, 不绑定 OpenCode Go。`api_key_env` 字段指向环境变量名, 密钥不写入配置文件。

### 7.2 brand-profile.yaml

位于 `~/.automedia/brand-profile.yaml`, 定义品牌身份:

```yaml
brand:
  name: "壹目贯维"
  english_name: "OneStepMore"
  tagline: "AI Speed, Human Touch"
  company: "贯维科技(沈阳)有限公司"

dna:
  positioning: "AI 内容生产公司"          # 品牌定位
  target_audience: "内容创作者、自媒体运营者"
  core_capabilities:                      # 核心能力描述
    - "热点追踪"
    - "文案生成"
    - "多平台发布"
  tone: "专业但不学术, 亲和但不轻浮"

cta_principles:
  structure: ["共情", "品牌身份", "价值主张", "行动引导"]
  bridge_required: true                   # 过渡句是否强制
  bridge_guidelines:
    - "从正文自然过渡到品牌能力"
    - "不得硬转折"
  examples:                               # 参考示例
    - "作为 AI 内容生产从业者..."

blocked_words:                            # 禁止词 / 禁止话题
  - "投资情报"
  - "金融分析"
  - "政策信号追踪"
  - "保证爆款"
  - "点名攻击友商"

brand_name_check:
  required: true                          # 每篇文章必须出现品牌名
  check_scope: ["script", "wechat", "zhihu", "xiaohongshu"]
```

### 7.3 Platform-Adapter 注册表

位于 `~/.automedia/adapters/registry.yaml`, 注册可用发布平台:

```yaml
adapters:
  wechat:
    enabled: false                          # 默认禁用，需用户配置凭证后启用
    module: "automedia.adapters.platforms.wechat_publisher"
    class: "WechatPublisher"
    config:
      appid_env: "WX_APPID"
      appsecret_env: "WX_APPSECRET"
      upload_checklist: true                # 上传前 7 步检查

  zhihu:
    enabled: false                          # 默认禁用，需用户配置凭证后启用
    module: "automedia.adapters.platforms.zhihu_draft"
    class: "ZhihuDraftPublisher"
    config:
      cookie_env: "ZHIHU_COOKIE"

  xiaohongshu:
    enabled: false                          # 默认禁用，需用户配置凭证后启用
    module: "automedia.adapters.platforms.xiaohongshu_publisher"
    class: "XiaohongshuPublisher"
    config:
      # ...

  douyin:
    enabled: false                          # 抖音适配器待实现

  bilibili:
    enabled: false

  # 预留: 国际平台
  # tiktok:     enabled: false
  # instagram:  enabled: false
  # twitter:    enabled: false
  # youtube:    enabled: false
  # linkedin:   enabled: false
```

所有 adapter 必须继承 `BasePlatformAdapter`:

```python
# automedia/adapters/base.py
from abc import ABC, abstractmethod

class BasePlatformAdapter(ABC):
    @abstractmethod
    def publish(self, project_dir: str, asset_paths: list[str]) -> dict:
        """发布到平台, 返回发布结果"""
        ...

    @abstractmethod
    def validate_credentials(self) -> bool:
        """验证凭证是否有效"""
        ...

    @property
    @abstractmethod
    def platform_name(self) -> str:
        ...
```

### 7.4 Overrides 子系统

Overrides 是 AutoMedia 通用化中最灵活的扩展机制。它允许用户在完全不修改 pip 安装包的前提下, 自定义流水线的行为和提示词。这个机制的存在, 使得 AutoMedia 既能作为一个标准的通用框架开箱即用, 又能适应不同品牌、不同行业、不同内容策略的定制需求。

设计理念是"约定大于配置": 系统在启动时自动扫描 overrides 目录, 加载其中的规则和模板。用户不需要修改任何配置文件的路径, 也不需要重写任何代码。只需要把自定义文件放到约定位置, 系统就会自动识别并应用。

位于 `~/.automedia/overrides/`, 允许高级用户在不修改核心代码的前提下自定义行为:

```
~/.automedia/overrides/
  rules/
    custom_gate.yaml          # 自定义 Gate 规则(追加到 Gate 检查中)
    approval_override.yaml    # 覆盖某些默认阻断条件
  prompts/
    humanizer.j2              # 覆盖 Humanizer 的 LLM prompt
    copy_review.j2            # 覆盖 Copy-review 的 LLM prompt
    brand_cta.j2              # 覆盖 Brand CTA 的 LLM prompt
    platform_wechat.j2        # 覆盖微信公众号平台的 prompt 模板
```

示例: 自定义 Gate 规则 `~/.automedia/overrides/rules/additional_checks.yaml`

```yaml
additional_gates:
  - name: "GX_sensitive_image"
    after: "V1"                    # 在 V1 Vision QA 后执行
    check: "custom_sensitive_detector"
    block: true                    # 失败则阻断 Pipeline
```

---

## 8 安全与隔离

本章定义 tenant_id 预留、API 凭证管理、路径注入防护和 MCP server 路径 allowlist。

### 8.1 Tenant ID 预留

所有项目、话题、生产记录预留 `tenant_id` 字段, 单租户模式默认值 `"default"`:

```python
# 数据结构预留
@dataclass
class Project:
    project_id: str
    tenant_id: str = "default"     # 预留字段
    topic: str
    brand: str
    # ...
```

pool.db 的 `topics` 表添加 `tenant_id TEXT DEFAULT 'default'`, 索引 `idx_topics_tenant`。

### 8.2 API 凭证管理

三种凭证存储方式, 按优先级从高到低:

| 方式 | 适用场景 | 示例 |
|------|---------|------|
| 环境变量 | 推荐用于生产部署 | `export AUTOMEDIA_WX_APPSECRET="..."` |
| keyring | 推荐用于开发机(系统密钥环) | `keyring.set_password("automedia", "wx_appsecret", "...")` |
| oscreds.yaml | 兼容遗留配置, 不推荐 | `~/.automedia/oscreds.yaml` (权限 600) |

凭证加载器 `automedia/core/credential_loader.py` 按环境变量 -> keyring -> oscreds.yaml 顺序查找。

### 8.3 项目目录路径注入防护

`pipeline.run(topic=...)` 中 topic 参数可能包含路径遍历攻击字符, 必须净化:

```python
import re

def sanitize_project_slug(topic: str) -> str:
    """将话题转为安全的目录名, 移除路径遍历风险"""
    slug = topic.lower()
    slug = re.sub(r'[^a-z0-9_\u4e00-\u9fff-]', '-', slug)  # 只保留中英数-_
    slug = re.sub(r'-+', '-', slug).strip('-')
    slug = slug[:120]  # 长度限制
    if not slug:
        slug = "untitled"
    return slug
```

### 8.4 MCP Server 路径 Allowlist

MCP server 的文件访问受 allowlist 限制, 防止恶意 agent 读取项目目录外的文件:

```yaml
# ~/.automedia/mcp_allowlist.yaml
allowed_paths:
  - "/mnt/d/AutoMedia/projects/"
  - "/mnt/d/AutoMedia/Pool/pool.db"
  - "/tmp/automedia/"      # 临时文件目录
read_only: true             # MCP 文件操作全部只读
```

MCP server 启动时加载 allowlist, `get_project_assets` 等 tool 返回的路径必须在 allowlist 内, 否则拒绝。

---

## 9 不可妥协约束

本章列出 8 项不可妥协约束。AutoMedia 的实现必须严格遵守以下每一项, 不得遗漏、更改或弱化。

1. **14 道 Gate 编排逻辑不可绕过**: 所有 Gate 的依赖关系、并行执行条件、阻断条件必须通过 `pipeline_orchestrator.py` 执行, 任何 API / CLI / MCP 入口都不提供跳过 Gate 的参数。Gate 失败 = Pipeline STOP, 不得静默忽略。

2. **HyperFrames HTML+GSAP -> MP4 视频方案唯一**: 视频生产的唯一路径是 `TTS -> Whisper -> SRT -> outline -> compositions -> hyperframes lint -> bun x hyperframes render -> MP4`。禁止引入 FFmpeg concat 图片序列、MiniMax 视频生成(video-01 / Hailuo-2.3)、或任何替代渲染方案作为主要生产路径。

3. **飞书/微信公众号 API 必须作为可配置 adapter 保留**: 7 步门控和飞书通知逻辑必须封装为可选 adapter。允许用户在 `adapters/registry.yaml` 中 `enabled: false` 禁用, 但**不得删除源代码**。其他贡献者可以提交 PR 禁用, 但项目核心维护者不得移除。

4. **强制工序 humanizer -> copy-review -> brand-cta 三道不得跳过**: 文案生成后的三道 Gate 顺序固定: `humanizer`(9 类 AI 写作模式清除) -> `copy-review`(五轮结构审查) -> `brand-cta-review`(零容忍项检查)。brand-cta-review 未通过前禁止调用 TTS。该门控在 `gates/copy_review_gate.py` 中实现为代码级强制约束。

5. **A/V 同步铁律**: 每句语音存在的时间内, 有且仅有该句的文字作为字幕。SRT 时间轴基于 Whisper ASR 真实时间戳, 不得使用等分法。字幕渲染后必须通过 PIL 像素亮度法验证字幕区域(V6 Gate), 确保每帧字幕与实际音频对齐。时间轴验证逻辑在 `gates/validate_srt_timing.py` 中实现。

6. **全量 QA(非抽样)原则**: 所有 QA 检查必须覆盖全量数据, 不得抽样。具体包括: 逐 Entry Vision QA(非 `3 帧/30 秒采样`), 末尾静音段单独检查, 全量 Whisper 音频转写(非 `前 30 秒`)。降级策略(如 Vision API 限流时的像素亮度法)必须在 QA 报告中标注 `降级` 字样。

7. **每个 Gate 产物 MD5 写入 pipeline_md5.json 追踪**: 每个 Gate 完成后, 其产物文件的 MD5 哈希必须写入 `{project_dir}/pipeline_md5.json`。Pre-send Gate(V2/Gate5) 必须验证当前文件 MD5 与记录值一致, 防止 QA 一个文件、发送另一个文件。MD5 校验逻辑在 `gates/pre_send_whisper_check.py` 中实现。

8. **Agent 不得 archive 项目(仅用户 --force 可绕过)**: 任何 AI agent(包括 AutoMedia 自身 agent)不得执行项目归档操作。项目归档必须由用户通过 `automedia archive --project <id> --force` 手动触发。违反此规则的 agent 行为视为工艺失误, 立即回退。

---

## 10 里程碑

本章定义 M1-M4 四个里程碑的交付物和退出标准。四个里程碑按"先拆后建"的原则推进: M1 先拆解架构耦合点并建立核心库, M2 构建 CLI 和调度入口, M3 接入 MCP 协议生态, M4 完善配置和文档。每个里程碑都可以独立交付和验收, 不依赖后续里程碑。

### M1: 核心库 + 架构解耦(6 周)

**交付物**:
- `automedia/` Python 包目录结构(含 core/ / pipelines/ / gates/ / adapters/ / manifests/ / hooks/)
- `automedia/core/runner.py` — `pipeline.run()` 主入口
- 14 道 Gate 全部封装为 Python 类(位于 `automedia/gates/`)
- 架构耦合点清单(20+ 项, 全部标记为"已解耦"或"已隔离")
- `pipeline_md5.json` 写入/校验逻辑
- `pool.db` 话题池管理
- 工程依赖检查脚本(`automedia doctor`)

**退出标准**:
- [ ] 在裸 Python 3.11 环境中, `pytest tests/` 全部通过
- [ ] `pipeline.run(topic="test", brand="default")` 在 mock 模式下完整走通 14 道 Gate
- [ ] 架构耦合点清单中所有项的状态为 `resolved` 或 `isolated`
- [ ] 目录结构可被新系统正确识别

### M2: CLI + 调度器(2 周)

**交付物**:
- `automedia` CLI(基于 typer) 全部子命令: `run`, `list-projects`, `get-assets`, `archive`, `pool`, `adapter`, `cron`
- 通用 cron job schema 定义 + 外部调度器支持
- 4 个 cron job 的 `automedia cron run <job-name>` 实现
- Pre-flight 4 步健康检查(`automedia cron check-health`)
- `~/.automedia/cron/jobs.yaml` 模板

**退出标准**:
- [ ] `automedia run --topic "..." --brand "..."` 完成端到端生产
- [ ] `automedia pool list --status pending` 返回话题池数据
- [ ] 4 个 cron job 通过 system crontab 连续运行 7 天无漏跑
- [ ] `automedia cron check-health` 全部 4 步通过

### M3: MCP Server + 7-10 个 Tool(3 周)

**前置条件**: M2 的 7 天 soak test(4 个 cron job 连续运行 7 天无漏跑)必须已通过验收, 确保调度和 CLI 层在生产环境下稳定后, 方可开始 M3 的 MCP Server 开发。

**交付物**:
- `automedia-mcp` 基于 mcp official Python SDK 的 MCP server
- 以下 tool 全部可用:
  1. `select_topic` — 从话题池选择话题并标记
  2. `run_pipeline` — 启动全链路生产
  3. `get_pipeline_status` — 查询正在运行的 pipeline 进度
  4. `list_projects` — 按状态列出项目
  5. `get_project_assets` — 获取指定项目的产物清单
  6. `archive_project` — 归档项目(需 --force)
  7. `list_topic_pool` — 浏览话题池
  8. `register_platform_adapter` — 注册平台/通知 adapter(如新增发布平台或 webhook 通知器)
- MCP server 路径 allowlist
- MCP server 启动脚本 + systemd service 模板

**退出标准**:
- [ ] Claude Desktop / Cline / OpenCode 通过 MCP 协议连接 server 并调用全部 8 个 tool
- [ ] `run_pipeline` tool 返回正确的 PipelineResult JSON
- [ ] `get_pipeline_status` 在运行中 pipeline 上返回进度百分比
- [ ] 路径 allowlist 正确拦截越权访问

### M4: 配置体系 + Overrides + 文档(2 周)

**交付物**:
- `defaults.yaml` 库内置默认配置
- `model_config.yaml` 完整支持 OpenAI/Anthropic 兼容格式
- `brand-profile.yaml` 完整支持品牌 DNA/CTA/禁止词
- `platform-adapter` 注册表 + 微信/知乎 adapter 实现
- overrides 子系统(rules + prompts)
- 凭证管理(env var / keyring / oscreds.yaml)
- 完整用户文档(`docs/` 目录): 安装指南 / CLI 手册 / MCP 配置 / adapter 开发指南
- CHANGELOG.md

**退出标准**:
- [ ] 切换 `brand-profile.yaml` 的 brand 名称后, 全链路内容、CTA、禁止词正确更新
- [ ] 切换 `model_config.yaml` 的 provider 后, 所有 LLM 调用指向新 endpoint
- [ ] `~/.automedia/overrides/rules/custom_gate.yaml` 被正确加载并生效
- [ ] 飞书通知和微信公众号发布在 `enabled: false` 时正常禁用, `enabled: true` 时正常工作

---

## 11 风险与开放问题

本章列出 7 条已知风险和开放问题, 每条附带缓解方案。这些风险来自多个维度: 基础设施层的资源限制、外部 API 的不可靠性、遗留代码的清理风险、设计决策的潜在失误, 以及性能退化风险。团队在实现过程中应持续关注这些风险, 并在每个里程碑评审时更新风险状态。

| # | 风险 | 影响 | 概率 | 缓解方案 |
|---|------|------|------|---------|
| R1 | Chrome headless 资源消耗高, 在低配服务器上可能 OOM | HyperFrames 渲染失败, Pipeline STOP | 中 | 已在 WSL 低内存模式下适配; MCP server 运行前执行 `automedia doctor` 预检可用资源; 文档标注最低 4GB RAM 要求 |
| R2 | Vision API(qwen3.7-plus) 限流导致全量 QA 不可用 | QA 降级为像素亮度法, 精度下降 | 低 | model_config.yaml 内置 `rate_limit` 字段; 限流时自动降级并标注 `降级`; 单日限频 360 次(留 20% 余量) |
| R3 | 微信公众号 API 非幂等, 脏内容上传不可撤销 | 生产环境产生垃圾草稿 | 低 | 保留现 7 步上传门控(现 `pre_wechat_upload.py`); 上传前逐项检查; publish_log 记录草稿 ID 防止重复上传 |
| R4 | MiniMax 历史代码清理不彻底, 死代码被误调用 | 混淆新旧 API | 中 | 耦合点清单中列出全部 MiniMax 引用; 对 `minimax`、`MiniMax-M2.7`、`image-01` 等关键词做全仓库搜检; 死代码删除而非注释 |
| R5 | SDK GateHook 设计失误: hook 返回 None 约束被绕过 | Gate 可被外部 hook 阻断, 违反硬约束 | 低 | Python `Protocol` 类型检查 + `isinstance` 运行时校验; 单元测试验证 hook 返回值必须为 None; CI 阶段添加 mypy 检查 |
| R6 | 多平台 adapter 调用超时导致整体 Pipeline 超时 | 发布阶段阻塞, 用户等待时间长 | 中 | 每个 adapter 有独立 `timeout_s` 配置; PublishEngine 支持超时跳过 + 异步发布; 失败平台记录到 publish_log, 不阻塞其他平台 |
| R7 | 通用化后性能下降(内联调用变为跨进程/跨协议) | 单话题生产耗时从 30min 增加到 45min+ | 中 | 核心路径仍为同进程内调用, 无跨进程开销; MCP 额外序列化/反序列化在毫秒级; M1 阶段设定性能基线, M3 阶段回归测试 |

---

## 12 词汇表

本章定义 PRD 中使用的关键术语, 确保团队对概念有一致理解。使用同一术语表有助于减少沟通歧义, 特别是在跨职能团队(产品、工程、QA)协作时。每个术语都给出了英文对照和精确定义, 设计文档和代码注释中应尽量使用这些标准术语。

| 术语 | 英文 | 定义 |
|------|------|------|
| Gate | Gate | 内容生产流水线中的一道自动化检查门控。每个 Gate 执行特定的质量检查(如事实核查、去 AI 味), 失败则阻断 Pipeline。共 14+ 道。 |
| Hook | GateHook | 只读观察者, 在 Gate 执行前后接收事件通知, 但不可修改 Gate 的执行逻辑或结果。三个方法: before_gate / after_gate / on_gate_failed, 全部返回 None。 |
| Track | Track | 并行的生产轨道。目前有两 Track: 文案 Track(文字内容生成+发布)和视频 Track(TTS+HyperFrames 渲染+QA)。双 Track 在选题后并行执行。 |
| Pipeline | Pipeline | 指从输入(topic + brand)到输出(各平台发布产物)的完整生产链条, 包含 Gate 编排、Track 并行、发布。`pipeline.run()` 是核心入口。 |
| Override | Override | 用户自定义覆盖配置, 位于 `~/.automedia/overrides/`。分为 rules(自定义 Gate 规则)和 prompts(自定义 LLM 提示词模板)两种。 |
| Adapter | Adapter | 可插拔的平台适配器, 实现 `BasePlatformAdapter` 接口。每个 adapter 负责向一个特定发布平台递交内容。支持的平台有微信/知乎/小红书/抖音/B站等。 |
| Pool | Topic Pool | 话题池, 由 SQLite 数据库(pool.db)管理。存储从多源采集的热点话题, 经评分、预审、去重后, 供用户选择进入生产。状态: pending -> selected -> writing -> published -> archived。 |
| Project | Project | 单个话题的生产项目。对应一个目录 `projects/YYYYMMDD_topic-slug/`, 包含项目信息、草稿、图片、视频、审核记录、发布记录。与 pool.db 中的 topic 通过 topic_id 关联(1:1)。 |

---

> **文档结束** — 编写自检清单:
> - [a] 不可妥协约束 8 项全部出现(见第 9 章)
> - [b] ASCII 架构图存在(见 4.1)
> - [c] P0/P1/P2 优先级清晰(见第 3 章)
> - [d] 三层(库/CLI/MCP)都有最小调用示例(见 4.5)
> - [e] GateHook Protocol 伪代码存在(见 5.2)
> - [f] 调度方案 3 选项对比并推荐(见第 6 章)
> - [g] 配置加载顺序明确(见 4.2)
> - [h] 4 个里程碑有退出标准(见第 10 章)
> - [i] 风险至少 5 条(见第 11 章, 共 7 条)
> - [j] 词汇表存在(见第 12 章)
