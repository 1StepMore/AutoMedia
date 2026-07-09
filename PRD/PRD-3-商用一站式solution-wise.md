## PRD-3: AutoMedia 商用一站式 solution-wise — 产品需求文档

> **版本**: v1.0 | **状态**: 草案 | **作者**: 产品团队 | **日期**: 2026-07-07
> **目标读者**: 实现工程师团队 + PM + 商业决策者 | **关联文档**: PRD-1-AutoMedia通用化.md, PRD-2-Omni三件套集成.md
> **核心定位**: 在 PRD-1(通用化产能后端)和 PRD-2(Omni adapter)之上, 新增决策层+资产库+SOP+商业化逻辑, 实现用户只给一个 idea, 系统 deliver 全套

---

## 0 引言

### 0.1 项目背景

AutoMedia 经过两个 PRD 的演进, 已经建立起明确的分层能力:

**PRD-1 通用化之后**, AutoMedia 已从 Hermes Agent 强耦合的内容生产系统, 解耦为三层(库 -> CLI -> MCP)通用的后端服务。任何 AI agent 都可以通过 `pipeline.run_full_pipeline(topic, brand)` 调用完整的 4 模态生产流水线, 经过 14 道 Gate, 产出从文案到视频的全套内容。详见 PRD-1 第 4 章架构设计和第 5 章 SDK API 设计。

**PRD-2 Omni 集成之后**, AutoMedia 获得了按需 adapter 工具包: OPP 将客户 DOCX/PPTX/PDF brief 提取为 MD, OL 实现多语言翻译, ORF 将内容回填为交付格式。Omni 以旁路 adapter 形式存在, 不进入自媒体生产主链。详见 PRD-2 第 4 章集成架构设计。

**当前阶段的核心缺口**: AutoMedia 目前是"生产执行层"——它擅长在给定 topic + brand 后执行生产, 但它不具备以下能力:
- 从零构建品牌定位、市场调研、竞品分析
- 智能判断用户处于"从 0 到 1"还是"从 1 到 N"阶段, 分流到不同分析路径
- 把分析结论沉淀为可复用的资产库, 供后续生产调用
- 输出标准化的运营执行 SOP
- 支持多租户、团队协作、审计日志等商用场景

本 PRD 解决的是"再加一层决策 + 资产 + SOP, 让 idea 到交付形成完整闭环"。

### 0.2 引用 source-wise 文档的双模式设计

本文档的节点设计和双模式架构参考 `/mnt/d/贯维/AutoMedia/solution-wise/出海品牌内容策略与生产 AI Agent 全周期标准化流程.docx`。该文档定义了核心的双模式入口分流设计:

- **Build 模式(0 到 1)**: 用户只有一个品牌 idea 或新产品概念, 系统从零构建品牌定位、市场调研、客群划定、竞品分析、策略推导、资产库规划、内容生产到执行 SOP。
- **Scale 模式(1 到 N)**: 用户已有在运营品牌, 系统基于既有品牌现状做健康度诊断、市场再验证、客群深化、竞品动态追踪、资产审计、策略优化、执行升级。

两种模式在阶段 0(情境识别)通过智能问卷分流, 在阶段 2(策略推导)汇合, 之后的阶段 3(内容工厂)和阶段 4(落地执行)共用同一套机制。

### 0.3 本 PRD 范围

本 PRD 只覆盖"目标 3: 商用一站式 solution-wise 决策层"。与 PRD-1 和 PRD-2 的边界如下:

| 关联 PRD | 关系 | 边界说明 |
|----------|------|---------|
| PRD-1 通用化 | 下层依赖 | PRD-1 的 `pipeline.run_full_pipeline()`, Gate 体系, 配置体系, tenant_id 预留是本 PRD 的 Production Layer。本 PRD 不替换下层, 只在其上叠加 Decision Layer 和 Orchestration Layer |
| PRD-2 Omni 集成 | 可选依赖 | PRD-3 的 Asset Library 可接收 Omni 的产出(如 OPP 提取的 MD), 但不强制依赖 Omni。Omni 的 adapter 机制仍然是独立的 |
| PRD-3 本 PRD | 独立 | 决策层 OVER AutoMedia + Omni 之上, 不修改下层任何 Gate 逻辑、管线编排、生产时序 |

### 0.4 三层 sandwich 概览

```
┌──────────────────────────────────────────────────────────────────┐
│                Decision Layer (决策层) — PRD-3 新增                  │
│  诊断 Agent  品牌定位 Agent  调研 Agent  客群 Agent  竞品 Agent     │
│  策略推导 Agent  资产规划 Agent                                    │
│  输出: Brief / Brand DNA / Persona Map / Competitor Matrix /      │
│        Strategy Doc / Asset Blueprint                              │
├──────────────────────────────────────────────────────────────────┤
│             Orchestration Layer (编排层) — PRD-3 新增               │
│  HITL Framework / Asset Library / SOP Runner / License Check      │
│  节点配置 YAML / 开源 preset / 商用 per-tenant config             │
├──────────────────────────────────────────────────────────────────┤
│              Production Layer (生产层) — PRD-1 + PRD-2              │
│  PRD-1: Pipeline.run_full_pipeline() / 14 Gates / CLI/MCP/SDK    │
│  PRD-2: Omni Adapter (OPP/OL/ORF 可选旁路)                        │
└──────────────────────────────────────────────────────────────────┘
```

决策层负责"想", 编排层负责"管", 生产层负责"做"。三者职责清晰, 层间通过结构化 artifact 契约通信。

---

## 1 目标与非目标

### 1.1 目标

| # | 目标 | 衡量标准 | 时间 |
|---|------|---------|------|
| G1 | Decision Layer 完整可用 | Build 模式和 Scale 模式各 4-5 个 Agent 可在用户输入 idea 后自动输出结构化 Brief / Brand DNA / 市场报告 / Persona Map / 竞品分析 | M1 完成时 |
| G2 | Asset Library 开源版上线 | ~/.automedia/asset-library/ 文件树 + SQLite metadata + Chroma vector index 可存储和检索品牌资产; `asset_library.ingest_artifacts()` 和 `search_asset_library()` 接口可用 | M1 完成时 |
| G3 | HITL Framework + 2 presets 可用 | 开源版提供 automated.yaml 和 semi-automated.yaml 两个预设; 每个节点可按 type(决策/偏好/执行)配置 human 或 agent | M2 完成时 |
| G4 | SOP Runner 自动生成执行手册 | 阶段 4 完成后, 系统自动输出《出海内容运营执行手册》, 含每日/每周任务清单、A/B 测试机制、复盘模板、数据追踪 | M5 完成时 |
| G5 | 商业版多租户 + 团队协作 | 商用版支持多租户隔离、团队 workspace、角色权限(RBAC)、审计日志; 开源版 tenant_id="default" 单租户 | M4 完成时 |
| G6 | open-core 边界清晰 | 开源版 pip install automedia 可用(不含团队合作/多租户/SAML SSO/Web UI); 商用版 license check 机制到位 | M3 完成时 |
| G7 | Decision Layer 输出不绕过 Production Layer | 所有决策结论必须转为 production pipeline 的结构化输入(Brief / Strategy Doc / Persona Map / Asset Specs), 不得直发 platform | 贯穿全周期 |

### 1.2 非目标

| # | 非目标 | 理由 |
|---|--------|------|
| NG1 | 不替代品牌咨询师做战略决策 | Decision Layer 提供 AI 协助的分析建议, 最终战略决策由人做出。LLM 的建议仅供参考 |
| NG2 | 不重新设计 PRD-1 的 Pipeline 和 Gate 体系 | Production Layer 已经是成熟资产。本 PRD 在其上叠加, 不修改下层任何逻辑 |
| NG3 | 不重新设计 PRD-2 的 Omni adapter 架构 | Omni 仍然是旁路 adapter, 本 PRD 只让 Asset Library 可接收 Omni 产出 |
| NG4 | 不构建 SaaS Web UI(第一阶段) | 商用版 Web UI 是 M4 范围, M1-M3 全部基于 CLI/YAML 配置 |
| NG5 | 不覆盖全行业 brand taxonomy | 内置通用出海品牌模板; 行业特定 taxonomy 通过 overrides 机制扩展 |
| NG6 | 不做 multi-tier 服务设计 | 本 PRD 只设计第一阶段的商用路径(open-core + license check), 不做 tiered pricing 的 infrastructure |
| NG7 | 不引入实时协作编辑 | 团队协作为异步共享 workspace + 审计日志, 非实时协同编辑 |
| NG8 | Audit Log 不 cover Production Layer Gate 内部 | 审计日志覆盖决策节点操作和团队管理行为, Gate 内部日志由 PRD-1 的 pipeline_md5.json 管理 |

---

## 2 用户与场景

### 2.1 三类核心用户

#### (a) Build 模式用户: 出海新品牌从 0 到 1

**画像**: 创业者、产品经理、品牌运营负责人。手头有一个品牌 idea 或产品概念, 需要从零搭建品牌体系和内容策略。

**场景 B-1 — 品牌从零到一全流程**: 创始人王先生输入"我们做一个面向东南亚市场的护肤品牌, 核心卖点是天然成分"。系统启动 Build 模式, 依次完成品牌定位(输出品牌屋)、市场调研(东南亚护肤品市场报告)、客群划定(4 个 Buyer Persona)、竞品分析(5 个竞品 SWOT)、内容策略(30 天内容日历), 最后调用 PRD-1 Pipeline 生产第一批 10 条内容并发布到 TikTok/Instagram。

**场景 B-2 — 产品概念快速验证**: 产品经理输入"一款 AI 驱动的个人健身教练 App, 目标市场北美"。系统在 2 小时内输出《市场可行性报告》《竞品功能矩阵》《目标用户画像》《内容营销策略建议》。用户根据报告决定是否继续投入。

#### (b) Scale 模式用户: 既有品牌 1 到 N 优化扩张

**画像**: 品牌总监、增长负责人、内容运营主管。品牌已在运营, 需要诊断健康度、优化策略、扩大内容产能。

**场景 S-1 — 品牌健康度年度审计**: 运营总监输入品牌名称"壹目贯维"和现有内容渠道(微信公众号+知乎+小红书+抖音+B站)。系统启动 Scale 模式, 审计品牌认知度/一致性/竞争力, 输出《品牌健康度报告》, 识别出"品牌 CTA 在不同平台不一致"问题, 给出定位刷新建议和 90 天优化计划。

**场景 S-2 — 品类扩张与内容策略升级**: 品牌从"AI 内容工具"扩展到"AI 视频生成+AI 设计"两条产品线。系统做市场再验证(新品类市场规模/竞争格局)、客群深化(现有用户聚类+新客群 Persona)、现有内容资产审计(300 篇文章+100 个视频自动打标评级), 输出《资产优化清单》和《策略升级路径图》。

#### (c) 商用版定制用户: MCN/代理团队等付费客户

**画像**: MCN 机构运营、海外营销代理、多品牌代运营团队。需要管理多个品牌/客户, 要求团队协作、权限管理、审计日志。

**场景 C-1 — 多品牌代运营工作台**: 代理机构同时服务 5 个出海品牌(3C/美妆/家居/食品/金融)。每个品牌有独立的 brand-profile、资产库、生产流水线。团队 10 人按角色(策略师/内容编辑/视频剪辑/发布运营)分配权限。系统提供统一的 workspace, 审计日志追踪每个成员的操作。

**场景 C-2 — 客户交付品自动生成**: MCN 机构为客户完成一期内容生产后, 系统自动生成《交付报告》, 包含内容清单、发布链接、KPI 指标、A/B 测试结果。报告通过飞书/邮件自动推送给客户。

**场景 C-3 — 团队共享资产库**: 5 人内容团队共用一个资产库。策略师上传品牌文档, 编辑调用资产库中的品牌 DNA 写文案, 设计师下载品牌色板做封面图。系统记录每次资产调用, 支持版本回溯。

---

## 3 双模式与节点分类框架

### 3.1 核心抽象: 思维链固定, 每节点由"人做"还是"agent 做"决定

整个 solution-wise 流程的思维链是固定的——从阶段 0 到阶段 4, 每个节点都要经过, 不能跳过。可变的是每个节点的执行者: 可以是 human(HITL), 也可以是 agent(自动)。

这个抽象是 PRD-3 的设计基石:
- 思维链固定 = 流程确定, 节点确定, 依赖关系确定
- 执行者可配置 = 每节点独立控制 human 还是 agent
- 开源版提供 2 个 preset, 商用版提供 per-node 自助配置

### 3.2 节点三类分类

| 类别 | 定义 | 示例 | 开源全自动 | 开源半自动 | 商用可调 |
|------|------|------|-----------|-----------|---------|
| **决策类** | 需要人类判断、策略决策的节点。LLM 提供建议, 但最终决策需 human 确认 | 品牌定位审核、策略选择、Persona 确认 | agent(LLM 建议+自动决策) | **human** | human/agent 可选 |
| **生产偏好类** | 涉及品牌美学、语调、创意的节点。human 可能有偏好, agent 也可胜任 | 封面图风格选择、文案语调微调、视频场景模式 | agent | **human** | human/agent 可选 |
| **执行类** | 纯执行性质, 无需人类判断 | pipeline.run_full_pipeline、文件归档、MD5 校验 | agent | agent | human/agent 可选 |

### 3.3 开源版 2 个 preset

开源版内置两个预设配置, 用户在首次初始化时选择。后续可通过 `~/.automedia/hitl/overrides/*.yaml` 微调:

**全自动 preset (automated.yaml)**: 仅阶段 0 的初始输入为 human, 其余所有节点 agent 自动执行。适用于完全信任 AI、追求速度的用户。

**半自动 preset (semi-automated.yaml)**: 所有决策类节点 + 生产偏好类节点强制 HITL, 执行类节点 agent 自动。适用于需要把控质量、愿意投入人力的用户。

### 3.4 商用版 per-node 配置

商用版用户在 Web UI 或 YAML editor 中, 对每个节点自助配置 human 还是 agent。配置保存在租户级 `hitl-config.yaml` 中, 不受 preset 覆盖。商用版新增商用特有节点的可配置(如团队审核流、多 tenant 节点等)。

### 3.5 全周期节点分类总表(概要)

| 阶段 | 节点数 | 决策类 | 偏好类 | 执行类 |
|------|--------|--------|--------|--------|
| 0 情境识别与资产盘点 | 4 | 3 | 0 | 1 |
| 1-B Build 分析引擎 | 4 | 2 | 2 | 0 |
| 1-S Scale 分析引擎 | 5 | 3 | 2 | 0 |
| 2 策略推导与优化 | 3 | 2 | 1 | 0 |
| 2.5 资产库规划/重构 | 3 | 1 | 1 | 1 |
| 3 推广方案与内容工厂 | 4 | 0 | 1 | 3 |
| 4 落地执行与 SOP | 4 | 0 | 0 | 4 |

**总计: 27 个节点**。完整分类见第 6 章。

---

## 4 功能需求

### 4.1 P0 — 必须交付

#### 模块 1: Diagnostic 模块(阶段 0)

| ID | 名称 | 用户故事 | 验收标准 |
|----|------|---------|---------|
| F3-001 | 情境识别智能问卷 | 作为新用户, 我第一次使用时系统自动引导我完成品牌情境问卷, 而不是让我填 YAML | 问卷包含 6-8 个问题(品牌有无/目标市场/核心挑战等), 输出结构化 Brief 或品牌现状画像 |
| F3-002 | 资产自动盘点 | 作为既有品牌用户, 我提供品牌名称后系统自动扫描现有内容资产 | 扫描 ~/.automedia/asset-library/ 和 project 目录, 输出《现有内容资产清单》(文件数/类型/标签分布) |
| F3-003 | Build/Scale 分流 | 系统根据问卷结果自动判断进入 Build 或 Scale 模式 | 用户选择"从零开始" -> Build 模式; 选择"已有品牌" -> Scale 模式; 支持手动 override |

#### 模块 2: Build-Mode 分析引擎(阶段 1-B)

| ID | 名称 | 用户故事 | 验收标准 |
|----|------|---------|---------|
| F3-004 | 品牌定位 Agent | 作为初创品牌用户, 我希望 AI 帮我提炼品牌 DNA 和定位, 而不是我写万字品牌书 | 输出品牌屋(brand DNA / vision / mission / values / personality / tone of voice / 多语言口号), 含跨文化适应性说明 |
| F3-005 | 市场调研 Agent | 我希望了解目标市场的规模、消费者行为和合规要求 | 调用搜索 API(Tavily/SerpAPI), 输出目标市场规模、消费者画像、内容偏好、文化雷区、合规要求; 信息来源可追溯 |
| F3-006 | 客群划定 Agent | 我希望精确知道我的目标客户是谁, 而不是泛泛的"年轻人" | 输出 3-5 个 Buyer Persona, 每个含 demographics / psychographics / pain points / content resonance map |
| F3-007 | 竞品分析 Agent | 我想知道竞品在做什么, 哪里是蓝海 | 输出 5 个竞品的 SWOT、内容标杆拆解、差异化空白推荐; 竞品社媒内容自动抓取分析 |

#### 模块 3: Scale-Mode 分析引擎(阶段 1-S)

| ID | 名称 | 用户故事 | 验收标准 |
|----|------|---------|---------|
| F3-008 | 品牌健康度诊断 | 作为既有品牌运营者, 我想知道我的品牌是否健康、一致、有竞争力 | 输出《品牌健康度报告》, 含认知度/一致性/竞争力三维评分, 定位刷新建议 |
| F3-009 | 市场再验证 | 我想知道品类趋势变化和新的市场机会 | 重新分析品类趋势, 识别细分市场或相邻市场机会; 输出《新机会扫描报告》 |
| F3-010 | 客群深化 | 我想了解现有客户特征, 找到可拓展的新客群 | 聚类现有客户(基于已有 Persona 或输入), 提炼最佳客户画像, 找出破圈目标 Persona |
| F3-011 | 竞品动态追踪 | 我想知道竞品最近在做什么内容策略调整 | 动态监控竞品内容策略变化(对比上次分析), 寻找蓝海内容空间, 输出反定位建议 |
| F3-012 | 现有内容资产审计 | 我想知道哪些内容值得复用, 哪些需要清理 | 抓取历史内容自动打标, 按表现评级(英雄内容/需更新/无用内容), 输出《资产审计与优化清单》 |

#### 模块 4: 策略推导模块(阶段 2)

| ID | 名称 | 用户故事 | 验收标准 |
|----|------|---------|---------|
| F3-013 | 产品优化策略 | Build: 基于调研推演理想产品形态; Scale: 基于反馈和退货原因给出迭代建议 | 输出《产品优化建议报告》, 含产品定位调整、功能优先级、本地化卖点包装 |
| F3-014 | 内容营销策略 | Build: 新建核心信息屋与内容支柱体系; Scale: 生成策略升级路径图 | 输出《内容营销策略文档》, 含核心信息屋、内容支柱(3-5 pillars)、渠道矩阵、内容日历框架 |

#### 模块 5: Asset Library 资产库(阶段 2.5)

| ID | 名称 | 用户故事 | 验收标准 |
|----|------|---------|---------|
| F3-015 | 资产库入库标准 | 我希望所有生产后的内容自动进入资产库, 附带完整的元数据 | `asset_library.ingest_artifacts(project_dir, brand)` 自动提取元数据: doc_id / brand_id / type / source_phase / tags / lang / vector_id |
| F3-016 | 资产库检索机制 | 我通过关键词或语义搜索找到历史品牌文档 | `asset_library.search(query, brand, filters)` 支持 SQLite 关键词搜索 + Chroma 语义搜索, 返回结构化结果 |
| F3-017 | 标签体系 | 我希望资产有统一的标签分类, 便于查找和复用 | 内置标签体系: type(strategy/persona/product/content/kol_brief/asset) + 自定义 tags JSON |
| F3-018 | 资产库与 Decision Layer 联动 | 当我运行定位 Agent 时能自动检索已有品牌文档 | `positioning_agent.search_asset_library()` 在 agent 推理前自动检索资产库, 避免重复分析 |

#### 模块 6: Content Factory(阶段 3)

| ID | 名称 | 用户故事 | 验收标准 |
|----|------|---------|---------|
| F3-019 | 调用 PRD-1 Pipeline | 决策层输出策略文档后, 系统自动调用 Production Layer 生产内容 | 调用 `pipeline.run_full_pipeline(topic, brand)`, 结果回填到 Asset Library |
| F3-020 | 内容矩阵与日历 Agent | 我需要 30/60 天内容计划, 适配海外节假日 | 输出 30 天内容日历(markdown+CSV), 含选题/平台/发布日期/状态追踪 |
| F3-021 | 素材与脚本生成 Agent | 我需要多语言短视频脚本和社媒图文 | 调用 AutoMedia 管线批量生产多条内容; 多语言输出走 PRD-2 OL adapter |

#### 模块 7: SOP & Execution 模块(阶段 4)

| ID | 名称 | 用户故事 | 验收标准 |
|----|------|---------|---------|
| F3-022 | 《出海内容运营执行手册》自动生成 | 我希望拿到一份可以直接执行的 SOP 文档 | 输出 execution_handbook.md, 含每日/每周任务清单、审核发布流程、本地化协作指南 |
| F3-023 | A/B 测试机制 | 我想在内容生产中做 A/B 测试 | SOP 中包含 A/B 测试配置方案(标题对比/封面图对比/CTA 对比) |
| F3-024 | 复盘模板 | 我想在每个内容系列结束后做数据复盘 | 输出 progress_report.md 模板, 含 KPI metrics / 内容表现 / 转化追踪 / 下期优化建议 |

#### 模块 8: HITL Framework

| ID | 名称 | 用户故事 | 验收标准 |
|----|------|---------|---------|
| F3-025 | 节点配置系统 | 我想控制哪个节点由人做、哪个由 AI 做 | YAML 配置每个节点的 type / autoset / human/agent, 详见第 7 章 |
| F3-026 | 开源 2 preset | 我不需要精细配置, 选一个预设就行 | automated.yaml 和 semi-automated.yaml 两个文件, 安装时自动提示选择 |
| F3-027 | 商用 per-tenant YAML editor | 作为商用版用户, 我想在 Web UI 中拖拽式配置节点 | Web UI 展示所有节点列表, 每个节点可切换 human/agent 开关 |

#### 模块 9: 商业 License 系统(商用版 P0)

| ID | 名称 | 用户故事 | 验收标准 |
|----|------|---------|---------|
| F3-028 | License check 机制 | 我想确保商用功能只在授权环境下可用 | 产品启动时做 single license check, 不每个节点 nag; license 过期时降级为开源版功能 |
| F3-029 | open-core 功能边界 | 开源用户清楚哪些功能是付费版 | 见第 10 章商业模式与 License |

#### 模块 10: Tenant/团队权限系统(商用版 P0)

| ID | 名称 | 用户故事 | 验收标准 |
|----|------|---------|---------|
| F3-030 | 多租户隔离 | 每个租户的数据完全隔离 | tenant_id 字段在 PRD-1 schema 已预留, 商用版 tenant_id 必填且校验 |
| F3-031 | 团队 workspace | 我的团队成员共享项目和资产库 | 多人可加入同一 workspace, 共享配置/资产库/生产流水线 |
| F3-032 | 角色权限(RBAC) | 不同角色有不同的操作权限 | 角色: admin / strategist / editor / operator / viewer, 每角色有预设权限矩阵 |
| F3-033 | 审计日志 | 所有操作都有记录, 可追溯 | 记录谁在什么时间做了什么操作(create/update/delete/approve/reject) |
| F3-034 | D0 Decision Provenance Gate | Decision Layer 产出必须经过 D0 Gate 校验才能进入 Production Layer | Pipeline 启动时 D0 Gate 检查 `.solution-state.yaml`；缺失或必需节点未完成 → Pipeline STOP with `status="rl9_violation"` |
| F3-035 | HITL Approval Gate | Human 节点未审批时 agent 不能继续执行 | `automedia solution approve-node` 记录审批；`next-node --block-on-hitl` 阻断未审批节点 |
| F3-036 | Artifact Schema Validation | Decision Agent 产出格式必须可验证 | 12 个 JSON Schema 文件；`validate-artifact --schema <name> <path>` 返回 `{valid, errors}` |
| F3-037 | Node Dependency Graph | 执行顺序必须遵守预定义依赖 | `dependency-graph.yaml` 定义 27 节点依赖；`next-node` 检查前置条件 |
| F3-038 | Pre-flight Phase Checks | 阶段转换前必须验证完整性和审批 | `preflight-check --next-phase <n>` 检查 artifact 和审批完整性 |
| F3-039 | Artifact Provenance Metadata | 每个产出需标注来源和校验信息 | 产出 YAML frontmatter 含 artifact_type/node/phase/mode/checksum |

### 4.2 P1 — 重要功能

| ID | 名称 | 验收标准 | 优先级 |
|----|------|---------|--------|
| F3-101 | 品牌定位多语言口号生成 | 定位 Agent 输出 5 种语言的口号(EN/ZH/JA/KO/ES), 附带文化适应性说明 | P1 |
| F3-102 | 竞品社媒自动抓取 | 竞品分析 Agent 自动抓取竞品最近 30 天的社媒内容(TikTok/Instagram/YouTube) | P1 |
| F3-103 | 资产库版本控制 | 每次资产更新保留历史版本, 支持 diff 和回滚 | P1 |
| F3-104 | SOP 模板自定义 | 用户通过 overrides 自定义 execution_handbook.md 模板 | P1 |
| F3-105 | A/B 测试结果自动分析 | 生产完成后系统自动分析 A/B 测试数据, 输出建议 | P1 |
| F3-106 | 商用版 SAML SSO | 企业用户通过 SAML 2.0 登录商用版 | P1 |
| F3-107 | 资产库数据迁移脚本 | sqlite -> postgresql + chroma -> pgvector/Qdrant 一键迁移 | P1 |

### 4.3 P2 — 优化功能

| ID | 名称 | 验收标准 | 优先级 |
|----|------|---------|--------|
| F3-201 | KOL/达人匹配 Agent | 基于品牌定位推荐匹配的 KOL 清单, 含粉丝画像和合作案例 | P2 |
| F3-202 | 内容表现预测 | 基于历史数据预测新内容的预期表现(阅读量/互动率) | P2 |
| F3-203 | SIEM 集成 | 商用版支持 Splunk/ELK 日志导出 | P2 |
| F3-204 | 批量品牌导入 | 通过 CSV/API 批量创建品牌配置和资产库 | P2 |
| F3-205 | 资产库自动标签推荐 | 入库时 AI 自动推荐 tags, 减少人工打标 | P2 |

---

## 5 整体架构

### 5.1 三层 Sandwich ASCII 架构图

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                               DECISION LAYER (决策层)                              │
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                    Diagnostic Agent (阶段 0)                               │   │
│  │  智能问卷 → Build/Scale 分流 → 资产自动盘点                                │   │
│  └────────────────────────┬─────────────────────────────────────────────────┘   │
│                           │                                                     │
│            ┌──────────────┴──────────────┐                                    │
│            ▼                              ▼                                    │
│  ┌────────────────────┐      ┌────────────────────────────┐                    │
│  │ Build 分析引擎      │      │ Scale 分析引擎              │                    │
│  │ (阶段 1-B)          │      │ (阶段 1-S)                  │                    │
│  │                     │      │                             │                    │
│  │ brand_positioning   │      │ brand_health_diagnosis      │                    │
│  │ market_research     │      │ market_revalidation         │                    │
│  │ audience_seg        │      │ audience_deepening          │                    │
│  │ competitor_analysis │      │ competitor_tracking         │                    │
│  └────────┬───────────┘      │ content_asset_audit         │                    │
│           │                  └────────┬────────────────────┘                    │
│           └──────────────┬────────────┘                                       │
│                          ▼                                                     │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                Strategy Engine (阶段 2) 双模式汇合                          │   │
│  │  产品优化策略  +  内容营销策略                                            │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                          │                                                     │
│                          ▼                                                     │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │              Asset Library Planning (阶段 2.5)                           │   │
│  │  标签体系 / 入库标准 / 复用机制 / 蓝图输出                                │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│  输出 Artifacts: Brief | Brand DNA | Market Report | Persona Map |               │
│   Competitor Matrix | Strategy Doc | Asset Blueprint | Content Calendar          │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│                          ORCHESTRATION LAYER (编排层)                             │
│                                                                                  │
│  ┌─────────────────────┐  ┌─────────────────┐  ┌────────────────────────────┐  │
│  │  HITL Framework     │  │  Asset Library   │  │  SOP Runner                │  │
│  │                     │  │                  │  │                            │  │
│  │  node_config.yaml   │  │  ingest          │  │  execution_handbook.md     │  │
│  │  automated.yaml     │  │  search          │  │  daily_task_list           │  │
│  │  semi-automated.yaml│  │  version         │  │  ab_test_runner            │  │
│  │  per-tenant config  │  │  migrate         │  │  progress_report.md        │  │
│  └─────────────────────┘  └─────────────────┘  └────────────────────────────┘  │
│                                                                                  │
│  ┌─────────────────────┐  ┌─────────────────┐  ┌────────────────────────────┐  │
│  │  License Check      │  │  Tenant System   │  │  Audit Log                 │  │
│  │  (商用版)            │  │  (商用版)         │  │  (商用版)                   │  │
│  └─────────────────────┘  └─────────────────┘  └────────────────────────────┘  │
│                                                                                  │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│                          PRODUCTION LAYER (生产层)                                │
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                    PRD-1: AutoMedia 通用化                                 │   │
│  │                                                                          │   │
│  │  ┌──────────────────────────────────────────────────────────────────┐   │   │
│  │  │  Pipeline.run_full_pipeline(topic, brand)                       │   │   │
│  │  │  14 Gates | 4 Tracks (文/图/视/音) | Multi-platform publish      │   │   │
│  │  │  GateHook Protocol | Overrides | Config System                    │   │   │
│  │  └──────────────────────────────────────────────────────────────────┘   │   │
│  │                                                                          │   │
│  │  入口: SDK (from automedia import Pipeline)                             │   │
│  │        CLI (automedia run --topic ... --brand ...)                       │   │
│  │        MCP (select_topic / run_pipeline / ...)                           │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
│  ┌──────────────────────────────────────────────────────────────────────────┐   │
│  │                    PRD-2: Omni Adapter (可选旁路)                          │   │
│  │                                                                          │   │
│  │  OPP (brief提取) → OL (多语翻译) → ORF (格式回填)                        │   │
│  │  3 modes: Proxy / Parallel / SDK                                         │   │
│  └──────────────────────────────────────────────────────────────────────────┘   │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 与下层接口契约

Decision Layer 产出的结构化 artifacts 是传给 Production Layer 的唯一契约:

| Decision Layer 产出 | 格式 | 传给 Production Layer 的用途 | 对应 PRD-1 组件 |
|--------------------|------|---------------------------|----------------|
| **Brand Brief** | YAML (brand-profile.yaml 格式) | 作为 pipeline.run() 的 brand 参数 | Config → brand-profile.yaml |
| **Strategy Doc** | YAML (含内容支柱/选题方向) | topic 生成依据, 内容日历输入 | Pipeline → topic |
| **Persona Map** | YAML (3-5 个 Persona 定义) | 文案生成 tone/perspective 参考 | Gate → brand-cta-review |
| **Asset Specifications** | YAML (媒体规格/尺寸/风格) | 图片/视频生产参数 | Pipeline → image/video pipelines |
| **Content Calendar** | CSV/MD (30 天选题排期) | 批量生产触发 | Scheduler → cron jobs |

接口原则: Decision Layer 输出必须经过 Ground Truth 验证(LLM 自检 + 用户可选 HITL 确认), 然后转为 Production Layer 的标准输入格式, 最后调用 PRD-1 的 `pipeline.run_full_pipeline()`。决策结论不得跳过 Production Layer 直发 platform(见红线第 9 条)。

### 5.3 Asset Library 与 Pipeline 的联动

```
Decision Layer
    │
    ├── positioning_agent.search_asset_library(brand)  ← 复用已有品牌文档
    │
    ▼
pipeline.run_full_pipeline(topic, brand)
    │
    ▼
asset_library.ingest_artifacts(project_dir, brand)    ← 产出回填
    │
    ▼
SOP Runner.read_asset_library(brand)                  ← 资产审计报告参考
```

### 5.4 强制机制层（Enforcement Layer — Chapter 5-A）

> **来源**: Metis Delta Analysis + Momus UNCONDITIONAL APPROVAL (ses_0bcd93c9cffeGR9cYPOAUj6xut)
> **背景**: 由于 PRD-3 采用 agent-agnostic 架构（不构建自研 Agent 框架），强制力从传统的"Python 沙箱（物理强制）"降为"文档/技能/CLI（自愿遵守）"。本章节定义 6 个强制机制恢复 enforcement，核心是 D0 Gate（HARD）将 RL9 合规检查从"自愿"升级为"Pipeline 阻断"。

#### 5.4.1 6 个强制提案

| 提案 | 名称 | 强制级别 | 简要说明 |
|------|------|----------|---------|
| A | D0 Decision Provenance Gate | **HARD**（Pipeline STOP） | `Pipeline.run_full_pipeline()` 首 Gate 检查 `.solution-state.yaml`，缺失或必需节点未完成 → STOP with `status="rl9_violation"` |
| B | HITL Approval Gate | SOFT/MEDIUM（CLI advisory） | `approve-node` / `next-node --block-on-hitl` CLI 记录 human 审批；未审批的 human 节点阻断 next-node |
| C | Artifact Schema Validation | SOFT（CLI 可选） | 12 个 JSON Schema 覆盖所有 Decision 产出类型；`validate-artifact --schema <name> <path>` CLI 验证 |
| D | Node Dependency Graph | MEDIUM（next-node 强制） | `dependency-graph.yaml` 定义 27 节点依赖；`next-node` 检查前置条件 |
| E | Pre-flight Phase Boundary Checks | SOFT（CLI advisory） | `preflight-check --next-phase <n>` 检查阶段转换前 artifact 和审批完整性 |
| F | Artifact Provenance Metadata | SOFTEST（文档规范） | 产出 YAML frontmatter 含 node / phase / mode / agent / checksum |

#### 5.4.2 D0 Gate 与 .solution-state.yaml

D0 Gate 作为所有 Pipeline mode 的第一个 Gate 执行，验证 Decision Layer 已完成必需的决策节点：

```
Pipeline 入口 → D0 Gate → [其余 18 Gate] → 发布
                  │
                  ├─ .solution-state.yaml 缺失 → STOP (rl9_violation)
                  ├─ 必需节点未完成 → STOP + 列出缺失节点
                  ├─ 全部通过 → 注入 provenance metadata → 继续
                  └─ --force-provenance --confirm-bypass-rl9 → 跳过 + 三层审计
```

- **Build 模式必需节点**（11 个）: brand_questionnaire, assign_mode, review_confirm_mode, brand_positioning, market_research, audience_segmentation, competitor_analysis, product_optimization_strategy, content_marketing_strategy, asset_blueprint_planning, content_calendar_generation
- **Scale 模式必需节点**（12 个）: brand_questionnaire, assign_mode, review_confirm_mode, brand_health_diagnosis, market_revalidation, audience_deepening, competitor_tracking, content_asset_audit, product_optimization_strategy, content_marketing_strategy, asset_blueprint_planning, content_calendar_generation

详见实施计划 §3.5-§3.12。

---

## 6 双模式详细节点分类表

下表列出 solution-wise 全周期的全部 27 个节点。类别列: **决策** / **偏好** / **执行**。开源默认列: **a** = 全自动(agent), **h** = 半自动(human)。商用可调列: **Y** = 用户可配置 human/agent, **N** = 固定不可调。

| # | 阶段 | 节点 | 类别 | 全自动默认 | 半自动默认 | 商用可调 |
|---|------|------|------|-----------|-----------|---------|
| 1 | 0 情境识别 | Brand questionnaire 品牌问卷填写 | 决策 | h(人填) | h(人填) | Y |
| 2 | 0.c 识别分支 | Assign mode 模式分配(Build/Scale) | 决策 | a | a | Y |
| 3 | 0.c 识别分支 | Asset auto-inventory 资产自动盘点 | 执行 | a | a | Y |
| 4 | 0.c 识别分支 | Review & confirm mode 模式确认 | 决策 | a | h | Y |
| 5 | 1-B Build | Brand positioning agent 品牌定位 | 决策 | a | h | Y |
| 6 | 1-B Build | Market research agent 市场调研 | 决策 | a | h | Y |
| 7 | 1-B Build | Audience segmentation agent 客群划定 | 偏好 | a | h | Y |
| 8 | 1-B Build | Competitor analysis agent 竞品分析 | 偏好 | a | h | Y |
| 9 | 1-S Scale | Brand health diagnosis 品牌健康度诊断 | 决策 | a | h | Y |
| 10 | 1-S Scale | Market revalidation 市场再验证 | 决策 | a | h | Y |
| 11 | 1-S Scale | Audience deepening 客群深化 | 偏好 | a | h | Y |
| 12 | 1-S Scale | Competitor dynamic tracking 竞品动态追踪 | 偏好 | a | h | Y |
| 13 | 1-S Scale | Content asset audit 现有内容资产审计 | 执行 | a | a | Y |
| 14 | 2 策略 | Product optimization strategy 产品优化策略 | 决策 | a | h | Y |
| 15 | 2 策略 | Content marketing strategy 内容营销策略 | 决策 | a | h | Y |
| 16 | 2 策略 | Review & approve strategy 策略审核确认 | 决策 | a | h | Y |
| 17 | 2.5 资产库 | Asset blueprint planning 资产蓝图规划 | 决策 | a | h | Y |
| 18 | 2.5 资产库 | Tag taxonomy setup 标签体系设定 | 偏好 | a | h | Y |
| 19 | 2.5 资产库 | Asset library initial ingest 资产库初始入库 | 执行 | a | a | Y |
| 20 | 3 内容工厂 | Content calendar generation 内容日历生成 | 偏好 | a | h | Y |
| 21 | 3 内容工厂 | Pipeline execution 流水线执行(调用 PRD-1) | 执行 | a | a | Y |
| 22 | 3 内容工厂 | Asset ingestion 产出回收入库 | 执行 | a | a | Y |
| 23 | 3 内容工厂 | KOL brief generation KOL 简报生成(可选) | 执行 | a | a | Y |
| 24 | 4 SOP | Execution handbook generation 执行手册生成 | 执行 | a | a | Y |
| 25 | 4 SOP | Daily/weekly task list 每日/每周任务清单 | 执行 | a | a | Y |
| 26 | 4 SOP | A/B test mechanism setup A/B 测试配置 | 执行 | a | a | Y |
| 27 | 4 SOP | Review template & data tracking 复盘模板 | 执行 | a | a | Y |

**节点设计说明**:
- 节点 1(Brand questionnaire)全自动和半自动都标记为 human, 因为初始输入必须由人完成, agent 无法替代
- 节点 2(Assign mode)全自动和半自动都标记为 agent, 因为模式分配逻辑基于问卷结果做确定性的规则判断, 不需要人类参与
- Scale 模式独有的节点(9-13)在 Build 模式下不执行, 反之亦然
- 商用版用户可以改变任何标记为 Y 的节点配置, 包括将执行类节点改为 human

---

## 7 HITL Framework 设计

### 7.1 节点配置 YAML 结构

HITL Framework 的核心是一个 YAML 配置文件, 定义每个节点的执行者。开源版内置两个 preset 文件:

**automated.yaml (全自动预设)**:

```yaml
# ~/.automedia/hitl/automated.yaml
# 全自动 preset: 仅初始输入 human, 其余 agent 全做

version: "1.0"
preset_name: "automated"
description: "全自动模式 - 仅品牌问卷由人填写, 其余全部 agent 自动执行"

nodes:
  brand_questionnaire:
    type: decision
    executor: human          # 初始输入必须 human
    
  assign_mode:
    type: decision
    executor: agent          # 规则分流, agent 可自动完成

  asset_auto_inventory:
    type: execution
    executor: agent

  brand_positioning:
    type: decision
    executor: agent          # 全自动: agent 自动决策

  market_research:
    type: decision
    executor: agent

  audience_segmentation:
    type: preference
    executor: agent

  competitor_analysis:
    type: preference
    executor: agent

  # ... 其余节点同样 agent
  product_optimization_strategy:
    type: decision
    executor: agent

  content_marketing_strategy:
    type: decision
    executor: agent

  asset_blueprint_planning:
    type: decision
    executor: agent

  pipeline_execution:
    type: execution
    executor: agent

  execution_handbook_generation:
    type: execution
    executor: agent
```

**semi-automated.yaml (半自动预设)**:

```yaml
# ~/.automedia/hitl/semi-automated.yaml
# 半自动 preset: 决策类 + 生产偏好类节点强制 HITL, 执行类 agent 自动

version: "1.0"
preset_name: "semi-automated"
description: "半自动模式 - 决策和偏好节点由人确认, 执行节点由 agent 自动"

nodes:
  brand_questionnaire:
    type: decision
    executor: human

  assign_mode:
    type: decision
    executor: agent          # 规则分流, agent 可自动完成

  asset_auto_inventory:
    type: execution
    executor: agent

  brand_positioning:
    type: decision
    executor: human          # 半自动: 决策类 human

  market_research:
    type: decision
    executor: human

  audience_segmentation:
    type: preference
    executor: human          # 半自动: 偏好类 human

  competitor_analysis:
    type: preference
    executor: human

  brand_health_diagnosis:
    type: decision
    executor: human

  market_revalidation:
    type: decision
    executor: human

  audience_deepening:
    type: preference
    executor: human

  competitor_tracking:
    type: preference
    executor: human

  content_asset_audit:
    type: execution
    executor: agent          # 执行类自动

  product_optimization_strategy:
    type: decision
    executor: human

  content_marketing_strategy:
    type: decision
    executor: human

  review_approve_strategy:
    type: decision
    executor: human

  asset_blueprint_planning:
    type: decision
    executor: human

  tag_taxonomy_setup:
    type: preference
    executor: human

  asset_library_initial_ingest:
    type: execution
    executor: agent

  content_calendar_generation:
    type: preference
    executor: human

  pipeline_execution:
    type: execution
    executor: agent

  execution_handbook_generation:
    type: execution
    executor: agent
```

### 7.2 原则: agent 不能 skip 任何节点, human 可 skip

- **agent 不能 skip**: 如果一个节点配置为 agent 执行, agent 必须生成该节点的产出(可以为空或 N/A, 但不能跳过)。这条原则确保思维链的完整性。
- **human 可 skip**: 如果一个节点配置为 human, human 可以选择跳过(accept agent 建议)或 override。跳过时节点产出使用 agent 的默认建议, 并在日志中标注 `human_skipped`。

### 7.3 开源版配置方案

开源版在首次初始化时询问用户选择 preset:
- 选择 automated: 复制 `automated.yaml` 到 `~/.automedia/hitl/config.yaml`
- 选择 semi-automated: 复制 `semi-automated.yaml` 到 `~/.automedia/hitl/config.yaml`

用户可在 `~/.automedia/hitl/overrides/*.yaml` 中逐个节点覆盖配置。系统启动时按 preset -> overrides 顺序合并。

### 7.4 商用版 per-tenant YAML editor

商用版提供 Web UI (或 CLI: `automedia hitl config --edit`), 展示所有 27 个节点的交互式配置面板:
- 每个节点显示名称、类别(决策/偏好/执行)、当前配置(human/agent)
- 点击开关切换
- 变更实时保存到租户级 `hitl-config.yaml`
- 提供"恢复开源预设"按钮

---

## 8 Asset Library 设计

### 8.1 开源版: Markdown 文件树 + SQLite metadata + Chroma vector index

**文件结构**:

```
~/.automedia/asset-library/
  {brand}/
    content/
      {doc_id}.md                        # 资产内容(Markdown 格式)
      {doc_id}_metadata.json             # 单独元数据(可选补充)
    index.sqlite                         # SQLite 元数据库
    vectors/
      chroma/                            # Chroma 向量索引目录
```

**SQLite Schema**:

```sql
CREATE TABLE assets (
    doc_id TEXT PRIMARY KEY,              -- 唯一 ID, 格式: {brand}_{type}_{phase}_{timestamp}
    brand_id TEXT NOT NULL,               -- 品牌标识符, 对应 brand-profile 的 brand_name
    type TEXT NOT NULL,                   -- strategy | persona | product | content | kol_brief | asset
    source_phase TEXT NOT NULL,           -- phase0 | phase1b | phase1s | phase2 | phase2.5 | phase3 | phase4
    title TEXT,                           -- 资产标题
    tags JSON DEFAULT '[]',               -- 自定义标签数组 JSON
    lang TEXT DEFAULT 'zh',               -- 语言代码
    file_path TEXT NOT NULL,              -- content/{doc_id}.md 的相对路径
    vector_id TEXT,                       -- Chroma embedding ID, 可为 NULL
    source_project_id TEXT,               -- 来源项目 ID(如果是生产阶段产出)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    checksum TEXT                         -- MD5 校验
);

CREATE INDEX idx_assets_brand ON assets(brand_id);
CREATE INDEX idx_assets_type ON assets(type);
CREATE INDEX idx_assets_phase ON assets(source_phase);
CREATE INDEX idx_assets_lang ON assets(lang);
```

### 8.2 商用版: PostgreSQL + pgvector 或 Qdrant

商用版将 SQLite 替换为 PostgreSQL + pgvector(或独立 Qdrant):

```sql
-- 商用版 PostgreSQL schema (扩展自开源版)
CREATE TABLE assets (
    doc_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id TEXT NOT NULL,              -- 商用版 tenant_id 必填
    brand_id TEXT NOT NULL,
    type TEXT NOT NULL,
    source_phase TEXT NOT NULL,
    title TEXT,
    tags JSONB DEFAULT '[]',
    lang TEXT DEFAULT 'zh',
    content_text TEXT,                    -- Markdown 全文存储(方便全文搜索)
    vector_id TEXT,
    source_project_id TEXT,
    created_by TEXT,                      -- 创建者用户 ID
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    checksum TEXT,
    UNIQUE(tenant_id, doc_id)
);

-- pgvector 支持
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE asset_embeddings (
    doc_id UUID REFERENCES assets(doc_id) ON DELETE CASCADE,
    embedding vector(1536),              -- 嵌入维度(根据模型调整)
    model_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 全文搜索索引
CREATE INDEX idx_assets_fulltext ON assets USING GIN(to_tsvector('simple', content_text));
```

### 8.3 数据迁移脚本

开源版到商用版的迁移工具:

```bash
automedia asset-library migrate \
  --from sqlite+chroma \
  --to postgresql+pgvector \
  --pg-uri "postgresql://user:pass@host:5432/automedia"
```

迁移逻辑:
1. 读取 SQLite 所有 asset 记录
2. 为每条记录添加 tenant_id="default" (迁移后用户可调整)
3. 批量写入 PostgreSQL
4. 从 Chroma 导出所有 embedding, 批量写入 pgvector
5. 校验: 开源版 doc_id <-> 商用版 doc_id mapping 确保一致
6. 输出迁移报告(成功数/失败数/校验和)

### 8.4 与 AutoMedia Pipeline 的联动: ingest

Pipeline 完成后自动回填 Asset Library:

```python
# 自动调用(在 pipeline.run() 完成后)
from automedia.asset_library import AssetLibrary

def on_pipeline_complete(result: PipelineResult):
    library = AssetLibrary(brand=result.brand)
    library.ingest_artifacts(
        project_dir=result.project_dir,
        brand=result.brand,
        artifacts=result.assets
    )
    # ingest_artifacts 会:
    # 1. 遍历 result.assets, 读取每个文件
    # 2. 提取元数据(type/source_phase/tags/lang)
    # 3. 写入 content/{doc_id}.md
    # 4. 写入 SQLite index
    # 5. 调用 Chroma 计算 embedding
    # 6. 返回 IngestResult(success_count, fail_count, doc_ids)
```

### 8.5 与 Decision Layer 的联动: search

Decision Layer Agent 在推理前的自动检索:

```python
# positioning_agent 内部调用
def search_asset_library(brand: str, query: str) -> list[AssetDoc]:
    library = AssetLibrary(brand=brand)
    results = library.search(
        query=query,
        filters={"type": ["strategy", "persona"]}
    )
    # 搜索逻辑:
    # 1. SQLite LIKE 搜索标题和 tags 关键词
    # 2. Chroma 语义搜索(如果 vector_id 存在)
    # 3. 合并结果, 按 relevance 排序
    # 4. 返回前 5 条
    return results
```

---

## 9 SOP Runner & Delivery

### 9.1 SOP 自动生成

阶段 4 完成后, SOP Runner 自动输出执行手册:

```bash
~/.automedia/sop/{brand}/execution_handbook.md
```

执行手册内容结构:

```markdown
# {brand} 出海内容运营执行手册

## 品牌速览
- 品牌定位: {positioning}
- 目标市场: {markets}
- 核心客群: {personas}

## 每日任务清单
- [ ] 09:00 检查内容日历今日选题
- [ ] 09:30 运行今日 Pipeline (automedia run --topic ...)
- [ ] 10:00 审核 Gate 日志, 处理失败项
- [ ] 14:00 检查发布状态
- [ ] 17:00 汇总当日数据到 progress_report

## 每周任务清单
- [ ] 周一: 回顾上周内容表现, 调整本周策略
- [ ] 周三: A/B 测试结果分析
- [ ] 周五: 内容日历滚动更新(加 7 天新选题)
- [ ] 周五: 资产库健康检查

## A/B 测试配置
- 测试维度: 标题 / 封面图 / CTA / 发布时间
- 样本量: 每个变量 >= 100 次曝光
- 置信度: >= 95%

## 复盘模板
参见 progress_report.md

## 数据追踪
- 渠道: {platforms}
- 核心 KPI: 阅读量 / 互动率 / 转化率 / SOV
```

### 9.2 Scheduler 与 PRD-1 cron 的关系

PRD-1 第 6 章已定义通用调度器方案(外部 cron + CLI)。SOP Runner 在其之上生成**日常任务清单**, 但不替代调度器执行:

- PRD-1 scheduler: 执行定时 job(热点采集/推送/健康检查)
- SOP Runner: 生成任务清单供人类运营者执行, 或由 agent 调度 PRD-1 pipeline

SOP Runner 输出每日 YAML 任务文件, 可直接被 PRD-1 scheduler 消费:

```yaml
# ~/.automedia/sop/{brand}/daily_tasks/2026-07-08.yaml
tasks:
  - time: "09:30"
    action: run_pipeline
    params:
      topic: "今日选题1"
      brand: "{brand}"
  - time: "14:00"
    action: check_publish_status
    params:
      project_id: auto
```

### 9.3 复盘模板

```markdown
# {series_name} 系列内容复盘报告

## 基本信息
- 周期: {start_date} ~ {end_date}
- 内容总数: {total_pieces}
- 覆盖平台: {platforms}

## KPI 指标
| 指标 | 实际值 | 目标值 | 达成率 |
|------|--------|--------|--------|
| 总阅读量 | | | |
| 平均互动率 | | | |
| 新增关注 | | | |
| 转化数 | | | |

## A/B 测试结果
| 测试维度 | 方案A | 方案B | 胜出方 | 置信度 |
|---------|-------|-------|--------|--------|
| 标题 | | | | |

## 内容表现 Top 3
1. {title} - {views} - 分析: {insight}
2. {title} - {views} - 分析: {insight}
3. {title} - {views} - 分析: {insight}

## 下期优化建议
1. {recommendation}
2. {recommendation}
```

---

## 10 商业模式与 License

### 10.1 Open-core 边界

| 功能 | 开源版 | 商业版 |
|------|--------|--------|
| Decision Layer Agent(Build + Scale) | 全部 9 个 agent | 全部 9 个 agent |
| Asset Library 开源版(SQLite+Chroma) | 支持 | 支持 |
| Asset Library 商用版(PostgreSQL+pgvector) | 不支持 | 支持 |
| HITL Framework + 2 presets | 支持 | 支持 |
| Per-node HITL YAML 配置 | 支持(通过 YAML 覆写) | 支持(且提供 Web UI) |
| Per-tenant 节点配置 | 不支持 | 支持 |
| Pipeline.run_full_pipeline (PRD-1) | 支持 | 支持 |
| Omni adapter (PRD-2) | 支持 | 支持 |
| SOP Runner + 复盘模板 | 支持(CLI 输出) | 支持(含 Web UI 展示) |
| **团队合作(多人共享 workspace)** | **不支持** | **支持** |
| **审计日志** | **不支持** | **支持** |
| **多租户隔离** | **不支持**(单 tenant default) | **支持** |
| **角色权限(RBAC)** | **不支持**(单用户) | **支持** |
| **定制化 Web UI** | **不支持**(仅 CLI/YAML) | **支持** |
| **SAML SSO** | **不支持** | **支持** |
| **SIEM 集成(Splunk/ELK)** | **不支持** | **支持** |
| **SLA 支持** | 社区支持 | 商业支持 |

### 10.2 License check 机制

```python
# automedia/license.py (伪代码)
class LicenseManager:
    def __init__(self):
        self.license_path = Path("~/.automedia/license.key").expanduser()
        
    def check(self) -> LicenseStatus:
        """产品启动时执行一次 license check, 不每个节点 nag"""
        if not self.license_path.exists():
            return LicenseStatus.OS_COMMUNITY  # 开源版
        
        key = self.license_path.read_text().strip()
        result = self._verify_key(key)  # 在线/离线验证
        
        if result.valid:
            return LicenseStatus.COMMERCIAL
        elif result.expired:
            print("License 已过期, 降级为开源版功能")
            return LicenseStatus.OS_COMMUNITY
        else:
            print("License 无效, 降级为开源版功能")
            return LicenseStatus.OS_COMMUNITY
    
    def _verify_key(self, key: str) -> VerifyResult:
        """离线验证: RSA 签名验证 + 有效期检查
           在线验证(可选): 调用 license server"""
        # 实现 RSA 签名验证, 防伪造
        # key 格式: base64(tenant_id|expiry_date|features|signature)
```

**License check 时机**: 仅在 `automedia` 模块启动时(import automedia 或 CLI 入口)做一次 check。不每个节点或每次 pipeline 调用时 nag。

### 10.3 Trial 到 Paid 的转化路径

1. 用户在 GitHub 下载开源版, 通过 CLI 体验完整功能(不含团队协作/多租户)
2. 用户注册商业版(通过 landing page), 获得 14 天试用 license key
3. 试用期: 商用版全部功能可用, 含团队协作/多租户/Web UI
4. 试用到期: license check 检测到期, 自动降级为开源版(数据保留, 功能受限)
5. 用户购买正式 license, key 更新后恢复到商用版

---

## 11 安全与多租户

### 11.1 Tenant ID 字段预留落地

PRD-1 第 8 章已定义 tenant_id 预留, pool.db 的 `topics` 表已有 `tenant_id TEXT DEFAULT 'default'`。本 PRD 在此基础上:

- Asset Library SQLite: assets 表新增 `brand_id` 字段, 通过 brand 间接关联 tenant
- Asset Library PostgreSQL: assets 表直接有 `tenant_id` 字段, 商用版必填
- Pipeline: `pipeline.run()` 的 `tenant_id` 参数从 PRD-1 的 `"default"` 升级为商用时必填校验

### 11.2 商用多租户隔离实现路径

| 隔离层级 | 开源版 | 商业版路径 |
|---------|--------|-----------|
| 数据存储 | 同一 SQLite, `brand_id` 区分 | 同一 PostgreSQL 实例, `tenant_id` 字段隔离; 可选每个 tenant 独立 schema |
| 文件存储 | 同一 `~/.automedia/asset-library/{brand}/` | `~/.automedia/tenants/{tenant_id}/asset-library/{brand}/` |
| 配置 | 单用户 `~/.automedia/` | `~/.automedia/tenants/{tenant_id}/` per-tenant 配置 |
| 用户 | 单用户(本地) | tenant 内多用户, 支持 RBAC |

### 11.3 跨租户数据泄漏防护

- 所有 API 入口增加 `tenant_id` 参数校验
- Asset Library search 强制加 `tenant_id` 或 `brand_id` 过滤
- PostgreSQL 层使用 Row Level Security(RLS):

```sql
ALTER TABLE assets ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON assets
    USING (tenant_id = current_setting('app.tenant_id'));
```

- 商用版集成测试包含跨租户泄漏测试用例

---

## 12 红线

本章列出 8 条不可妥协约束(与 PRD-1 第 9 章完全一致), 再加 1 条本 PRD 专属红线。必须完整复刻, 不得遗漏、更改或弱化。

### 12.1 PRD-1 红线(8 条, 与本 PRD 一致)

1. **14 道 Gate 编排逻辑不可绕过**: 所有 Gate 的依赖关系、并行执行条件、阻断条件必须通过 `pipeline_orchestrator.py` 执行, 任何 API / CLI / MCP 入口都不提供跳过 Gate 的参数。Gate 失败 = Pipeline STOP, 不得静默忽略。

2. **HyperFrames HTML+GSAP -> MP4 视频方案唯一**: 视频生产的唯一路径是 `TTS -> Whisper -> SRT -> outline -> compositions -> hyperframes lint -> bun x hyperframes render -> MP4`。禁止引入 FFmpeg concat 图片序列、MiniMax 视频生成(video-01 / Hailuo-2.3)、或任何替代渲染方案作为主要生产路径。

3. **飞书/微信公众号 API 必须作为可配置 adapter 保留**: 现 `pre_wechat_upload.py` 的 7 步门控和飞书通知逻辑必须封装为可选 adapter。允许用户在 `adapters/registry.yaml` 中 `enabled: false` 禁用, 但**不得删除源代码**。

4. **强制工序 humanizer -> copy-review -> brand-cta 三道不得跳过**: 文案生成后的三道 Gate 顺序固定。brand-cta-review 未通过前禁止调用 TTS。

5. **A/V 同步铁律**: 每句语音存在的时间内, 有且仅有该句的文字作为字幕。SRT 时间轴基于 Whisper ASR 真实时间戳, 不得使用等分法。字幕渲染后必须通过 PIL 像素亮度法验证字幕区域(V6 Gate)。

6. **全量 QA(非抽样)原则**: 所有 QA 检查必须覆盖全量数据, 不得抽样。具体包括: 逐 Entry Vision QA(非 `3 帧/30 秒采样`), 末尾静音段单独检查, 全量 Whisper 音频转写(非 `前 30 秒`)。降级策略必须在 QA 报告中标注 `降级` 字样。

7. **每个 Gate 产物 MD5 写入 pipeline_md5.json 追踪**: 每个 Gate 完成后, 其产物文件的 MD5 哈希必须写入 `{project_dir}/pipeline_md5.json`。Pre-send Gate(V2/Gate5) 必须验证当前文件 MD5 与记录值一致。

8. **Agent 不得 archive 项目(仅用户 --force 可绕过)**: 任何 AI agent(包括 AutoMedia 自身 agent)不得执行项目归档操作。项目归档必须由用户通过 `automedia archive --project <id> --force` 手动触发。

### 12.2 PRD-3 专属红线(第 9 条)

9. **Decision Layer 输出不得跳过 Production Layer Gate**: 决策层的所有产出(品牌定位/策略文档/Persona Map 等)必须经过 Ground Truth 验证(LLM 自检 + 用户可选 HITL 确认), 然后转换为 PRD-1 `pipeline.run_full_pipeline()` 的标准输入格式(Brief / Strategy Doc / Persona Map / Asset Specifications), 最后调用 Production Layer 执行。严禁 Decision Layer 将分析结论直接发布到任何平台, 或绕过 Production Layer 的 14 道 Gate 将内容写入发布目录。违反此规则视为架构违规, 必须回退。

**强制机制**: 本红线由 D0 Decision Provenance Gate（HARD Enforcement）强制执行。D0 Gate 作为 Pipeline 的第一个 Gate，验证 `.solution-state.yaml` 中必需节点是否已完成。若缺失或未完成，Pipeline 立即 STOP 并标记 `status="rl9_violation"`。详见 §5.4.2。

**例外**: 仅 `--force-provenance --confirm-bypass-rl9` 双标志可跳过 D0 Gate，且 bypass 必须触发三层审计（日志文件 + 不可抑制 CLI 警告 + 审计记录）。

---

## 13 里程碑

### M1: Decision Layer SDK + Asset Library 开源版(6 周)

**交付物**:
- Diagnostic Agent (阶段 0): 智能问卷 + Build/Scale 分流 + 资产自动盘点
- Build-Mode 4 Agent: brand_positioning / market_research / audience_segmentation / competitor_analysis
- Scale-Mode 5 Agent: brand_health_diagnosis / market_revalidation / audience_deepening / competitor_tracking / content_asset_audit
- Strategy Engine (阶段 2): 产品优化 + 内容营销策略生成
- Asset Library 开源版: Markdown 文件树 + SQLite schema + Chroma 集成
- `asset_library.ingest_artifacts()` 和 `search_asset_library()` 接口
- Decision Agent 与 Asset Library 的联动(agent 自动检索资产库)

**退出标准**:
- [ ] Build 模式: 输入一个品牌 idea -> 输出完整 Brand DNA / Market Report / 4 Personas / Competitor Matrix
- [ ] Scale 模式: 输入既有品牌 -> 输出 Health Report / Market Scan / Deepened Personas / Competitor Tracking / Asset Audit
- [ ] 策略引擎: 双模式汇合后输出产品优化建议 + 内容营销策略
- [ ] `asset_library.ingest_artifacts()` 正确写入 SQLite + Chroma
- [ ] `asset_library.search()` 返回关键词和语义搜索结果
- [ ] 与 PRD-1 pipeline 的第一次联动: Asset Library 可正确读取 project 产出

### M2: HITL Framework + 2 Presets(3 周)

**交付物**:
- HITL 节点配置 YAML schema
- `automated.yaml` 和 `semi-automated.yaml` 两个 preset 文件
- 配置加载器(按 preset -> overrides 顺序合并)
- `automedia hitl preset --list` 和 `automedia hitl preset --set <name>` CLI 命令
- 用户 overrides 机制: `~/.automedia/hitl/overrides/*.yaml`
- agent 节点执行器: 在 agent 模式下自动调用对应 Decision Agent
- human 节点执行器: 输出等待确认, 用户通过 CLI 确认后可继续

**退出标准**:
- [ ] `automedia hitl preset --set automated` 后全流程 agent 自动执行
- [ ] `automedia hitl preset --set semi-automated` 后决策类节点等待 human 确认
- [ ] `~/.automedia/hitl/overrides/custom.yaml` 正确覆盖单个节点配置
- [ ] agent 不能 skip 任何节点验证: agent 模式下每个节点都有产出
- [ ] human 可 skip 验证: human 模式下跳过后节点使用 agent 默认建议

### M3: Open-core License + 资产库双层迁移工具(2 周)

**交付物**:
- License check 机制(RSA 签名验证)
- open-core 功能边界代码级隔离(商用功能通过 license check 守卫)
- 迁移脚本 `automedia asset-library migrate`
- 迁移测试: 10 个品牌 x 50 条资产从 SQLite+Chroma -> PostgreSQL+pgvector
- 商用版许可证生成器(内部工具)

**退出标准**:
- [ ] 无 license key 时: 开源版功能正常, 商用功能返回 `not available`
- [ ] 有效 license key 时: 商用功能可用
- [ ] 过期 license key 时: 自动降级为开源版, 数据保留
- [ ] 迁移脚本成功迁移 500 条资产记录, 校验和一致
- [ ] 迁移后 Chroma embedding 与 pgvector 距离精度差异在 0.01 以内

### M4: 商业版多租户 + 团队协作(8 周)

**交付物**:
- 多租户数据隔离(PostgreSQL RLS + 文件目录隔离)
- 团队 workspace 管理(创建/邀请/退出)
- RBAC 角色权限系统(admin / strategist / editor / operator / viewer)
- 审计日志(操作记录/时间戳/用户/变更前后状态)
- SAML SSO 集成
- 商用版 Web UI (Dashboard / Asset Library 管理 / Node Config)

**退出标准**:
- [ ] 5 个租户各自数据完全隔离, 跨租户查询返回空结果
- [ ] 团队 10 人按角色分配权限, 测试通过全部权限矩阵用例
- [ ] 审计日志正确记录所有 create/update/delete/approve/reject 操作
- [ ] SAML SSO 登录流程端到端通过(Okta / Azure AD)
- [ ] Web UI 展示 Asset Library / HITL config / SOP output

### M5: SOP Runner + 复盘模板(3 周)

**交付物**:
- SOP Runner: 自动生成 `execution_handbook.md`
- 每日任务清单 YAML 生成
- A/B 测试配置模板
- 复盘模板 `progress_report.md` 自动填充
- SOP 模板自定义机制(用户 overrides)

**退出标准**:
- [ ] 阶段 4 完成后, `~/.automedia/sop/{brand}/execution_handbook.md` 自动生成
- [ ] 复盘模板正确引用品牌实际生产数据(KPI/内容列表/Gate 日志)
- [ ] 每日任务 YAML 可直接被 PRD-1 scheduler 解析
- [ ] A/B 测试模板可被用户直接填写和使用

---

## 14 风险与开放问题

| # | 风险 | 影响 | 概率 | 缓解方案 |
|---|------|------|------|---------|
| R1 | **LLM 决策幻觉**: Decision Agent 输出虚假市场数据或不合理品牌定位 | 用户采信错误建议, 品牌战略偏离 | 中 | 所有决策 Agent 输出必须附带信息来源引用; 策略审核节点设为 HITL 默认(human-review); 关键数据(市场规模/竞品信息)做交叉验证 |
| R2 | **Decision Layer 的 slowness 拖长生产链**: 多 Agent 串行推理导致从 idea 到内容交付耗时从 30min 增加到数小时 | 用户等待时间长, 体验下降 | 中 | 阶段 1-B/1-S 的 4-5 个 Agent 设计为并行执行(LangGraph/CrewAI 多 Agent 并行); 策略阶段(阶段 2)完成后才触发 Production Layer; 引入进度条和预估时间 |
| R3 | **商用版客户修改 HITL 自由度逼近红线**: 用户把决策类节点全设为 agent 后未审核直接进入生产, 导致品牌内容质量失控 | 品牌内容与定位偏离, 客户不满意 | 低 | License 协议中明确"商用版 per-node 配置不改变红线约束"; 手册建议决策类节点保持 HITL; 提供"品牌保护模式"开关, 开启后强制关键决策节点 HITL |
| R4 | **资产库向量库爆破性增长**: Chroma/pgvector 存储量随生产量线性增长, 检索性能下降 | 检索变慢, Agent 等待时间长 | 中 | SQLite 内置清理策略(删除 > 1 年未使用资产); 向量索引定期重建; 商用版提供按 tenant 分片和归档策略; 预计算法: 检索时限制 top-K 和 time range |
| R5 | **License check 被社区反弹**: 开源社区不满 license check 机制, fork 项目去除 check | 商业化和 community 双输 | 中 | License check 仅做功能开关, 不含数据收集或电话 home; check 代码开源透明; 提供"完全离线"check 选项(RS A 签名验证, 无需连接服务器); 社区 fork 不可避免, 确保开源版功能完整 |
| R6 | **Decision Agent 处理多语言市场时文化偏差**: 品牌定位和内容策略在海外市场存在文化不敏感 | 品牌声誉受损 | 中 | 内置文化雷区检查模块(阶段 1-B 市场调研 Agent 中); 关键市场内容经过 PRD-1 的 Gate 链(含 brand-cta-review); SOP 手册中标注文化审查流程 |
| R7 | **多租户数据泄漏**: RLS 配置错误或代码漏洞导致 tenant A 数据被 tenant B 看到 | 客户数据泄露, 法律风险 | 低 | 集成测试包含专门的数据隔离测试套件; 代码审查时标注所有 `tenant_id` 相关变更; RLS 策略作为基础设施代码(IaC)管理 |
| R8 | **开源版用户升级到商用版时数据迁移失败**: SQLite+Chroma 迁移到 PostgreSQL+pgvector 过程中数据丢失或损坏 | 用户信任丧失 | 低 | 迁移脚本包含预检查(源数据完整性)和后验证(目标端数据一致性); 迁移过程非破坏性(源数据保留); 提供 rollback 脚本 |

---

## 15 词汇表

| 术语 | 英文 | 定义 |
|------|------|------|
| Build Mode | Build Mode | 从 0 到 1 的品牌构建模式。用户只有一个品牌 idea, 系统从零构建定位、调研、策略、资产库、内容生产和 SOP |
| Scale Mode | Scale Mode | 从 1 到 N 的品牌优化扩张模式。用户已有在运营品牌, 系统做健康诊断、市场再验证、客群深化、竞品追踪、资产审计和策略升级 |
| Decision Layer | Decision Layer | PRD-3 新增的顶层。包含诊断 Agent、分析 Agent、策略 Agent, 产出结构化决策 artifacts, 不处理具体内容生产 |
| Orchestration Layer | Orchestration Layer | PRD-3 新增的中间层。包含 HITL Framework、Asset Library、SOP Runner、License Check, 负责编排和管控 |
| Production Layer | Production Layer | PRD-1 定义的生产层。包含 pipeline.run_full_pipeline()、14 道 Gate、4 模态管线、发布引擎。PRD-3 不修改此层 |
| Asset Library | Asset Library | 内容资产库。开源版: Markdown 文件树 + SQLite + Chroma; 商用版: PostgreSQL + pgvector/Qdrant。存储品牌各阶段的决策产出和生产内容 |
| HITL | Human In The Loop | 人在回路中。指节点由人类执行而非 agent 自动执行。PRD-3 的 HITL Framework 管理每个节点 human/agent 的配置 |
| Node Category | Node Category | 节点分类: 决策类(需人类判断)、生产偏好类(涉及审美/创意)、执行类(纯执行, 无需判断) |
| Preset | Preset | 开源版内置的节点配置预设。automated.yaml(全自动, 仅初始输入 human)和 semi-automated.yaml(半自动, 决策+偏好类 HITL) |
| SOP Runner | SOP Runner | 阶段 4 的模块, 自动生成《出海内容运营执行手册》、每日任务清单、A/B 测试机制和复盘模板 |
| Open-core | Open-core | 商业模式: 核心功能开源(AGPL/类似协议), 商业功能付费(团队协作/多租户/Web UI/SAML SSO/SIEM) |
| License Check | License Check | 商用版功能开关机制。产品启动时做一次 RSA 签名验证, 无效或过期 key 自动降级为开源版 |
| Tenant | Tenant | 租户。商用版最小隔离单元, 每个 tenant 有独立的数据空间、配置、用户和权限体系 |
| Brand Profile | Brand Profile | 品牌配置文件(brand-profile.yaml), 定义品牌 DNA、CTA、禁止词、语言配置等。PRD-1 第 7 章定义格式 |
| Pipeline | Pipeline | PRD-1 定义的 `pipeline.run_full_pipeline()` 核心入口。PRD-3 通过 Asset Library ingest 和 search 与之联动 |

---

> **文档结束** — 编写自检清单:
> - [a] 节点分类表覆盖阶段 0-4 全部 27 个节点(见第 6 章)
> - [b] 红线 8 条 + 1 条 PRD-3 专属(见第 12 章)
> - [c] 三层 sandwich ASCII 架构图(见 0.4 和 5.1)
> - [d] HITL YAML 例配置存在(见 7.1)
> - [e] 资产库双层 schema 给出(SQLite + PostgreSQL 见 8.1/8.2)
> - [f] open-core 边界写清楚(见 10.1)
> - [g] 5 个里程碑有退出标准(见第 13 章)
> - [h] 与 PRD-1 Pipeline.run_full_pipeline 契约一致(tenant_id 参数/brand-profile/等)
> - [i] Decision Layer 不绕过 Production Layer red line(第 12.2 条)
> - [j] 每模块 P0/P1/P2 清晰(见第 4 章)
> - [k] 词汇表 15 条关键术语(见第 15 章)
> - [l] 风险 8 条含缓解方案(见第 14 章)
