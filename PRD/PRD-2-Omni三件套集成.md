## PRD-2: AutoMedia 与 Omni 三件套集成 — 产品需求文档

> **版本**: v1.0 | **状态**: 草案 | **作者**: 产品团队 | **日期**: 2026-07-07
> **目标读者**: 实现工程师团队 + PM | **关联文档**: PRD-1-AutoMedia通用化.md(同一目录), PRD-3 商用一站式(独立)
> **核心定位**: Omni 仅是按需调用的 adapter 工具库, 自媒体多模态生产主链不经过 Omni

---

## 0 引言

### 0.1 项目背景

AutoMedia 经过 PRD-1 通用化改造后, 已从 Hermes Agent 强耦合的内容生产系统解耦为三层(库 -> CLI -> MCP)通用的后端服务。PRD-1 定义了完整的选题 -> research -> 4 模态并行生产 -> 多平台发布的流水线, 14 道 Gate 门控体系, 以及 brand-profile / model_config / platform-adapter 等配置体系。

然而, AutoMedia 目前缺少对"非自媒体生产场景"的支持。当客户交付的是海外 DOCX/PPTX/PDF 格式的 brief 文件, 或者需要把 AutoMedia 产出的中文内容做成多语言 DOCX/PPTX 交付品, AutoMedia 现有管线无法处理这种"文档本地化"需求。这正是 Omni 三件套(OPP / OL / ORF)填补的空缺。

Omni 三件套(Omni Pre-Processor, Omni Localizer, Omni Re-Formatter)是壹目贯维已独立开发的文档本地化工具链:
- **OPP**: 文档内容提取器, 将 DOCX/PPTX/PDF 等格式提取为结构化 Markdown + XLIFF + manifest.json + skeleton.zip
- **OL**: 多语言翻译器, 以 LLM 驱动 MD/XLIFF 翻译, 自带质量门控与模型池故障转移
- **ORF**: 格式回填器, 将翻译后的 XLIFF 回填为 DOCX/PPTX 等交付格式

AutoMedia PRD-1 已定义通用化三层入口, 本 PRD 解决"Omni 三件套如何接入 AutoMedia 作为按需 adapter 工具包"的问题。

### 0.2 当前痛点

- **0 现状无 Omni 集成**: AutoMedia 每日生产内容全中文, 无流程接收海外客户的 DOCX/PPTX brief, 无能力产出多语言交付品。当客户提供英文 brief 时, 需要人力手动转成中文 Markdown 再喂给 agent
- **客户交付格式单一**: AutoMedia 产出为 MD + HTML + MP4 + 图片, 无法回填为客户要求的 DOCX/PPTX 交付格式。品牌客户需要的不是 MD 文件, 而是可直接使用的 DOCX/PPTX 文档
- **海外生产能力缺失**: 虽然 AutoMedia 所有 LLM 调用已可切换至英文 model, 但缺少"英文 brief 入 -> 英文内容出 -> 英文 DOCX 交付"的整条管线
- **知识库杂格式资料利用率为零**: 客户积累了大量的 DOCX/PPTX/PDF 格式的行业资料, 无法自动化转成 MD 进入知识库, 这些资料当前全部沉睡在文件服务器上

### 0.3 本 PRD 范围

本 PRD 只覆盖"目标 2: Omni 集成", 与 PRD-1(通用化)和 PRD-3(商用一站式)的边界如下:

| 关联 PRD | 关系 | 边界说明 |
|----------|------|---------|
| PRD-1 通用化 | 前置依赖 | PRD-1 交付的三层入口(库/CLI/MCP)和配置体系是 Omni adapter 的宿主环境。PRD-2 在 PRD-1 完成后开始实现 |
| PRD-3 商用一站式 | 后续迭代 | PRD-3 会在 PRD-2 基础上构建 Web UI / 多租户 / SaaS 层, PRD-2 不做 UI |

### 0.4 关键定位判断(用户已确认)

**Omni 仅是按需调用的 adapter 工具库, 自媒体主链不经过 Omni。**

这一定位是整个 PRD-2 的设计基石, 全文必须贯彻:
- AutoMedia 自媒体生产链(选题 -> research -> 4 模态并行 -> 发布)完全独立运行, 不依赖任何 Omni 组件
- Omni 在以下两个旁路节点可选接入: (1) research 阶段之前, OPP 把客户 brief 转为 MD 供 agent 读; (2) publish 阶段之后, OL+ORF 把成品转为多语言 DOCX/PPTX 交付
- AutoMedia 不因 Omni 集成而改变任何 Gate 逻辑、管线编排、生产时序
- Omni 组件使用独立的 LLM 配置, 不共享 AutoMedia 的 model_config.yaml

---

## 1 目标与非目标

### 1.1 目标

| # | 目标 | 衡量标准 | 时间 |
|---|------|---------|------|
| G1 | Omni adapter 子系统可用 | `automedia/omni/` 子模块封装 OPP/OL/ORF 三方调用, 单元测试覆盖率 >= 80% | M1 完成时 |
| G2 | 三种集成模式全部实现 | (i) 默认转发 MCP 工具 extract_brief / localize_content / format_output 可用; (ii) 可选并列模式下 4 个 MCP server 同时启动且 host agent 可透明调用; (iii) `from automedia.omni import OPPAdapter` 直接 import 可工作 | M2 完成时 |
| G3 | OPP 自动调用 + OL/ORF 手动调用两条路径打通 | 客户 brief 文件被 topic-pool 收录后自动 extract_brief_adaptive(file) -> MD; 用户执行 `automedia omni localize --project <id> --target-langs en,ja` 产出多语言 DOCX/PPTX | M2 完成时 |
| G4 | EN 到 ZH 默认多语管道可用 | `brand-profile.yaml` 配置 default_lang=en 后, pipeline 启动时按 default_lang 选 TTS voice / Whisper lang pack / LLM 翻译 target_lang, 产出英文内容 | M3 完成时 |
| G5 | XLIFF 回填 DOCX/PPTX 端到端验证通过 | 任一 DOCX 文件经 OPP -> OL -> ORF 全链路后, 回填的 DOCX 与原文件结构一致、文本翻译正确、图片位置保留 | M3 完成时 |

### 1.2 非目标

| # | 非目标 | 理由 |
|---|--------|------|
| NG1 | 不把 Omni 嵌入 AutoMedia 自媒体生产主链 | 定位已确认: Omni 是旁路 adapter, 主链不经过 Omni |
| NG2 | 不构建 Omni 一站式 Web UI | 那是 PRD-3 的范围, 本 PRD 只做 adapter 层接入 |
| NG3 | 不覆盖全语言多语生产 | 主打 EN 到 ZH, 预留 JA/KO/ES/FR/AR 扩展接口, 具体实现由后续迭代完成 |
| NG4 | 不修改 OPP/OL/ORF 自身源码 | Omni 三件套作为独立 PyPI 包引入, AutoMedia 不做 fork 或 patch |
| NG5 | 不重新设计 OL 的 LLM 配置体系 | OL 有独立的 llm_pool(default.yaml/local.yaml), AutoMedia 不强制接管 OL 配置, 两条流水互不交叉 |
| NG6 | 不将 ORF 回填能力等同自媒体发布 | ORF 产物是 DOCX/PPTX 文件交付, 不是 API 发布到微信/知乎等平台 |

---

## 2 用户与场景

用户已确认 5 类用例全选: (a) 入站源材料本地化, (b) 出站多语言化, (c) 海外独立多语生产模式, (d) 客户交付格式转换, (e) 知识库化。

### 2.1 用例 A: 入站源材料本地化

客户交付海外 DOCX/PPTX/PDF brief, OPP 提取为 MD 供 agent 读。

**场景 A-1 — 英文 Brief 自动转中文调研**: 客户通过飞书传来一份英文产品 spec.docx (50 页, 含表格和图片)。AutoMedia topic-pool 收录该文件后, 自动调用 OPP extract_document 将其转为 MD + XLIFF, 再调用 OL translate-md 转为中文 MD。research 阶段 agent 直接读取中文内容做事实核查。

**场景 A-2 — 多格式客户资料归一化**: 客户邮件附件包含混合格式(PPTX 提案 + PDF 白皮书 + XLSX 数据表)。OPP batch_extract 一次处理全部, 统一输出为 MD, 存入 topic 的 research_data 目录。

**场景 A-3 — OCR 图片 PDF 提取**: 客户提供的是扫描版 PDF(无文本层)。OPP 的 Tesseract/RapidOCR 引擎自动识别, 输出含 OCR 文本的 MD, agent 无需额外处理。

### 2.2 用例 B: 出站多语言化

AutoMedia 产出中文成品后, OL + ORF 把它做成 DOCX/PPTX 多语言交付品。

**场景 B-1 — 中文自媒体文章转英文 DOCX 交付**: AutoMedia 完成一个中文话题生产后, 用户执行 `automedia omni localize --project 20260707_ai-video --target-langs en,ja,ko`。系统先调用 OL translate-md 把文案 Track 产出的 MD 翻译为英文/日文/韩文, 再调用 ORF apply-md 转为 DOCX, 输出到 `05_publish/en/`, `05_publish/ja/`, `05_publish/ko/`。

**场景 B-2 — 中英文对照 PPTX 交付**: 客户需要一份中英文对照版 PPTX。AutoMedia 产出中文内容后, OL 翻译英文, ORF 将双语文本回填到 PPTX skeleton 中, 保持原有幻灯片布局。

**场景 B-3 — 多语言 SRT 字幕导出**: AutoMedia 视频 Track 产出的 SRT 字幕经 OL translate-xliff 翻译后, ORF 输出多语言 SRT 文件, 直接用于视频的多语版本。

### 2.3 用例 C: 海外独立多语生产模式

纯英文或多语 AutoMedia 模式。

**场景 C-1 — 英文自媒体全链路生产**: brand-profile 配置 `default_lang: en`。pipeline 启动后, research 阶段使用英文搜索源(Tavily 英文), LLM 生成英文文案, TTS 使用英文音色(en-US-JennyNeural), Whisper 用英文语言包, 平台 adapter 输出英文内容至海外平台(预留)。

**场景 C-2 — 日文市场独立生产**: 品牌配置日文 lexicon 资源, pipeline 按 ja 语言包选择 TTS voice(ja-JP-NanamiNeural)和 Whisper ja 模型, 全链路产出日文内容。Brand-profile 的 taxonomy 配置日文 CTA 和禁止词。

### 2.4 用例 D: 客户交付格式转换

Markdown 文章回填为 DOCX/PPTX。

**场景 D-1 — 精选文章合集 DOCX**: 运营每月精选 10 篇公众号文章(MD 格式), 通过 `automedia omni format-output --input monthly_digest.md --target-format docx --output monthly_digest.docx` 生成一份带目录和封面的 DOCX 文档, 用于客户汇报。

**场景 D-2 — 提案 PPTX 自动生成**: 系统读取话题 research_data 中的结构化信息, 通过 ORF apply-md --target-format pptx 生成一份 10 页以内的 PPTX 提案, 包含标题页/摘要/数据分析/结论。

### 2.5 用例 E: 知识库化

客户沉寂的杂格式资料 OPP 一键转 MD 进知识库, OL 也可本地化 MD。

**场景 E-1 — 行业报告知识库批量导入**: 客户有 200+ 份 PDF 行业报告和 DOCX 分析文档, 通过 `automedia omni ingest --dir /data/reports/ --output-dir /data/knowledge-base/` 批量 OPP 提取为 MD, 按主题自动分类入库。

**场景 E-2 — 英文知识库中文化**: 客户英文知识库中的 MD 文件通过 OL translate-md 批量本地化为中文, 结果存入中文知识库分区, 供中文运营团队检索使用。

---

## 3 功能需求

### 3.1 P0 — 必须交付

| ID | 名称 | 用户故事 | 验收标准 | 优先级 |
|----|------|---------|---------|--------|
| F-001 | Omni adapter 子系统 | 作为一个 AutoMedia 维护者, 我希望在 `automedia/omni/` 下有统一的 adapter 封装, 因为我不想在业务代码中直接调用 OPP/OL/ORF 的 API | `automedia/omni/` 目录包含 `__init__.py`, `base.py`, `opp_adapter.py`, `ol_adapter.py`, `orf_adapter.py`, `registry.py`; 每个 adapter 继承 `BaseOmniAdapter` 抽象类 | P0 |
| F-002 | Tool Registry 注册机制 | 作为 adapter 子系统使用者, 我希望每个 Omni 工具通过 tool registry 注册, 支持按名称查找和调用的统一接口 | `OmniToolRegistry` 类实现 `register(name, adapter)`, `get(name) -> BaseOmniAdapter`, `list_tools() -> list[str]`; 注册在包加载时自动完成 | P0 |
| F-003 | 默认转发模式 MCP 工具 | 作为 MCP client agent, 我调用 `extract_brief` 就能提取客户 brief 文档, 不需要知道背后是 OPP | MCP server 暴露 `extract_brief(file_path, source_lang, target_lang) -> {md_content, manifest_json}`, `localize_content(md_content, target_langs) -> {translated_files}`, `format_output(content, target_format) -> {output_path}` 三个工具, 内部调用 OPP/OL/ORF | P0 |
| F-004 | 可选并列模式 4 server 启动 | 作为高级 agent 用户, 我希望同时启动 AutoMedia + OPP + OL + ORF 四个 MCP server, 由 host agent 透明调用 | 启动脚本 `automedia omni start-all` 或 `automedia omni start --mode parallel` 可同时拉起 4 个 MCP server; 每个 server 使用独立端口/transport | P0 |
| F-005 | Python SDK 直接 import | 作为 Python 开发者, 我希望 `from automedia.omni import OPPAdapter` 直接使用 OPP 功能, 不依赖 MCP 通信 | `OPPAdapter.extract(file_path) -> ExtractionResult`, `OLAdapter.translate(content, source_lang, target_lang) -> TranslationResult`, `ORFAdapter.backfill(original_file, xliff_file) -> str(输出路径)` 三个核心方法可直接调用 | P0 |
| F-006 | 自动调用触发: extract_brief_adaptive | 作为系统, 当 topic-pool 收录一个文件类型为 DOCX/PPTX/PDF 的 brief 后, 我希望自动提取为 MD | `topic-pool` 的 `ingest_file()` 方法检测到文件扩展名为 `.docx/.pptx/.pdf/.xlsx/.csv/.json/.xml/.html/.epub/.eml/.msg` 时自动调用 `OPPAdapter.extract()`; 提取结果存入 `topic.research_data`; 失败时写入 warning 不阻断主链 | P0 |
| F-007 | 手动调用触发: CLI subcommand | 作为用户, 我希望通过 CLI 手动调用 Omni 本地化和格式转换 | `automedia omni localize --project <id> --target-langs en,ja` 和 `automedia omni format-output --input <file> --target-format docx` 和 `automedia omni ingest --dir <dir> --output-dir <dir>` 三个子命令可用 | P0 |
| F-008 | 自动调用触发: POST /omni/localize_output | 作为 MCP client agent, 我希望完成生产后通过 MCP 调用 `localize_output` 触发多语言交付 | MCP server 在 produce 完成后可调用 `localize_output(project_id, target_langs)`, 返回每个语言的文件路径列表 | P0 |

### 3.2 P1 — 重要功能

| ID | 名称 | 用户故事 | 验收标准 | 优先级 |
|----|------|---------|---------|--------|
| F-101 | OPP 失败回退路径 | 作为用户, 当 OPP 提取失败时, 我不希望生产阻断, 而是能手动提供 brief | OPP 提取失败时 pipeline 写入 warning 到 gate log, 不阻断 topic-pool 流程; 用户可通过 `automedia pool attach-brief --topic <id> --md-file <path>` 手动注入 MD | P1 |
| F-102 | OL 翻译质量门控集成 | 作为运营者, 我希望 OL 翻译产出经过 AutoMedia 的 Gate 才能进入交付目录 | OL 翻译完成后, 其输出的 MD 文件经过一个轻量"翻译门控"(检查 YAML frontmatter 完整性 / source_lang 和 target_lang 正确 / 无乱码), 通过后才写入 `05_publish/{lang}/` | P1 |
| F-103 | 海外多语 brand-profile 扩展 | 作为多语创作者, 我希望 brand-profile 支持各语言的 CTA 规则、禁止词、TTS 音色配置 | brand-profile.yaml 新增 `languages:` 字段支持 `en: {cta: "...", blocked_words: [...], tts_voice: "en-US-JennyNeural", whisper_lang: "en"}, zh: {...}, ja: {...}` | P1 |
| F-104 | ORF 产物 MD5 写入 pipeline_md5.json | 作为审计者, 我希望 ORF 回填的 DOCX/PPTX 文件的 MD5 也被记录追踪 | ORF 输出文件后, 其 MD5 写入 `{project_dir}/pipeline_md5.json`, 字段路径 `omni_outputs.{lang}.{format}.md5` | P1 |
| F-105 | Omni 工具路径 allowlist | 作为安全管理员, 我希望 Omni 工具读写文件受路径 allowlist 限制 | `omni_adapter` 加载时读取 `~/.automedia/omni_allowlist.yaml`, 所有文件操作路径必须在 allowlist 内 | P1 |

### 3.3 P2 — 优化功能

| ID | 名称 | 用户故事 | 验收标准 | 优先级 |
|----|------|---------|---------|--------|
| F-201 | XLIFF 翻译进度可观测 | 作为运营者, 我希望查看 OL 翻译 XLIFF 的进度和统计 | `automedia omni translate-status --task <id>` 返回已翻译/总数/警告数 | P2 |
| F-202 | 知识库自动分类 | 作为知识库管理者, 我希望 OPP 批量提取 MD 后自动按主题分类 | `automedia omni ingest --classify` 在提取后调用 LLM 给每篇 MD 打标签, 按标签归类存储 | P2 |
| F-203 | ORF 布局溢出检测 | 作为交付质检者, 我希望 ORF 回填后检测是否存在文本溢出/截断 | ORF 完成回填后运行 AI layout overflow detection(ORF 内置), 结果写入交付报告 | P2 |
| F-204 | 多语 SRT 字幕自动配音 | 作为视频创作者, 我希望多语 SRT 配合 TTS 生成多语配音版本 | OL 翻译 SRT 后, AutoMedia 调用 edge-tts 按目标语言音色生成配音, 与 SRT 合成多语视频 | P2 |

---

## 4 架构设计

### 4.1 集成架构(ASCII)

```
                         ┌─────────────────────────────────────────────────────────┐
                         │                    AutoMedia 主流程                        │
                         │  (自媒体生产链: Omni 不介入)                               │
                         │                                                          │
                         │   选题 ──> research ──> 4 模态并行 ──> Gate 链 ──> 发布  │
                         │     │                     │                   │          │
                         │     │ (Omni 旁路A)        │    (Omni 旁路B)   │          │
                         └─────┼─────────────────────┼───────────────────┼──────────┘
                               │                     │                   │
                    ┌──────────▼──────────┐  ┌───────▼───────────────────▼───────┐
                    │  Omni Adapter 层     │  │  Omni Adapter 层                   │
                    │  (automedia/omni/)   │  │  (automedia/omni/)                 │
                    │                     │  │                                     │
                    │  ┌───────────────┐  │  │  ┌───────────────┐  ┌───────────┐  │
                    │  │ OPPAdapter    │  │  │  │ OLAdapter     │  │ ORFAdapter│  │
                    │  │ extract()     │  │  │  │ translate()   │  │ backfill()│  │
                    │  └───────┬───────┘  │  │  └───────┬───────┘  └─────┬─────┘  │
                    └──────────┼──────────┘  └──────────┼─────────────────┼────────┘
                               │                        │                 │
                    ┌──────────▼──────────┐  ┌──────────▼─────────────────▼────────┐
                    │     OPP MCP         │  │     OL MCP          ORF MCP          │
                    │     Server          │  │     Server          Server           │
                    │  extract_document   │  │  translate_md_text  apply_md         │
                    │  batch_extract      │  │  translate_xliff    apply_xliff      │
                    │  detect_format      │  │  judge_text         batch_convert    │
                    └─────────────────────┘  └──────────────────────────────────────┘
                               │                        │
                    ┌──────────▼────────────────────────▼──────────────────────────┐
                    │              Omni 工具库(PyPI 包)                             │
                    │  opp (pip install opp)                                       │
                    │  ol  (pip install omni-localizer)                            │
                    │  orf (pip install omni-re-formatter)                         │
                    └─────────────────────────────────────────────────────────────┘

                         ┌─────────────────────────────────────────────────────────┐
                         │            三种集成模式(详见第 5 章)                       │
                         │  (i) 默认转发: AutoMedia MCP 内部封装的 client 调 Omni   │
                         │  (ii) 可选并列: 4 个独立 MCP server 同时启动              │
                         │  (iii) Python SDK: from automedia.omni import XXXAdapter │
                         └─────────────────────────────────────────────────────────┘
```

### 4.2 旁路架构原则

从 ASCII 图可以看出, Omni 在 AutoMedia 架构中处于旁路位置:

**旁路 A — OPP 注入点(research 阶段前)**: 当 topic-pool 收录的 brief 文件是二进制文档格式(DOCX/PPTX/PDF 等)时, `extract_brief_adaptive()` 自动调用 `OPPAdapter.extract()` 转为 MD, 存入 `topic.research_data`。research 阶段 agent 读取 MD 而非原始文件。

**旁路 B — OL + ORF 注入点(publish 阶段后)**: AutoMedia 完成多模态生产后(所有 Gate 通过, 发布完成), 如果用户需要多语言交付, 通过 `localize_output` 调用 `OLAdapter.translate()` 翻译文案 Track 的 MD 产出, 再通过 `ORFAdapter.backfill()` 回填为 DOCX/PPTX 文件, 输出到 `05_publish/{lang}/` 目录。

**两条旁路都不会进入自媒体生产主链**: 不修改任何 Gate 逻辑, 不改变生产时序, 不占用生产资源。

### 4.3 Adapter 抽象设计

每个 Omni 工具被 AutoMedia 适配层包装, 通过 tool registry 注册:

```python
# automedia/omni/base.py
from abc import ABC, abstractmethod

class BaseOmniAdapter(ABC):
    """Omni 工具适配器基类"""

    @abstractmethod
    def name(self) -> str:
        """适配器名称, 用于 registry 查找"""
        ...

    @abstractmethod
    def validate_env(self) -> bool:
        """检查运行环境(依赖包/MCP server 可达性等)"""
        ...

# automedia/omni/registry.py
class OmniToolRegistry:
    """Omni 工具注册中心"""

    _adapters: dict[str, BaseOmniAdapter] = {}

    @classmethod
    def register(cls, adapter: BaseOmniAdapter) -> None:
        cls._adapters[adapter.name()] = adapter

    @classmethod
    def get(cls, name: str) -> BaseOmniAdapter:
        if name not in cls._adapters:
            raise KeyError(f"Omni adapter '{name}' not registered")
        return cls._adapters[name]

    @classmethod
    def list_tools(cls) -> list[str]:
        return list(cls._adapters.keys())
```

### 4.4 配置开关

Omni 集成通过 `~/.automedia/omni_config.yaml` 控制:

```yaml
# ~/.automedia/omni_config.yaml

# 集成模式: "proxy"(默认转发) | "parallel"(可选并列) | "sdk"(Python SDK)
integration_mode: "proxy"

# OPP 配置
opp:
  enabled: true
  # proxy 模式下使用的 MCP server 配置
  mcp_server_command: "uvx opp-mcp-server"
  mcp_allowed_dirs: ["/mnt/d/AutoMedia/projects/", "/mnt/d/AutoMedia/briefs/"]
  # sdk 模式下直接 pip install 的包名
  package: "opp"

# OL 配置
ol:
  enabled: true
  mcp_server_command: "ol-mcp"
  package: "omni-localizer"
  # OL 独立的配置文件路径(不共享 AutoMedia model_config.yaml)
  config_path: "~/.automedia/omni/ol_config.yaml"

# ORF 配置
orf:
  enabled: true
  mcp_server_command: "orf-mcp-server"
  package: "omni-re-formatter"

# 自动调用触发
auto_triggers:
  # 入站 brief 文件自动提取
  extract_brief_on_ingest: true
  # 支持的自动提取大小上限(MB), 超过则提示手动调用
  max_auto_extract_mb: 50
  # 生产完成后是否自动触发多语言本地化(默认 false, 手动触发)
  auto_localize_on_complete: false
  default_target_langs: ["en"]
```

---

## 5 三种集成模式详解

### 5.1 模式(i): 默认转发(Proxy)

**工作原理**: AutoMedia 主 MCP Server 内部封装 MCP client, 在 `extract_brief` / `localize_content` / `format_output` 三个工具的实现中, 内部调用 OPP/OL/ORF 各自的 MCP server(或 CLI)。host agent 只与 AutoMedia MCP server 通信, 不感知背后有 3 个独立服务。

```
Host Agent (Claude/OpenCode/Cline)
    │
    ▼   (只连一个 MCP server)
AutoMedia MCP Server
    │
    ├── extract_brief(file)
    │       └── [内部] MCP client -> OPP MCP Server -> return MD
    │
    ├── localize_content(md, langs)
    │       └── [内部] MCP client -> OL MCP Server -> return translated MD
    │
    └── format_output(content, fmt)
            └── [内部] subprocess -> ORF CLI -> return output path
```

**配置开关**: `omni_config.yaml` 中 `integration_mode: "proxy"`。

**性能特征**: 增加一层 MCP 序列化/反序列化, 每次 Omni 调用增加约 50-200ms 延迟(基本可忽略)。MCP client 与 Omni server 通过 stdio 通信, 无网络开销。

**对 host agent 的接口暴露**: 3 个 AutoMedia MCP tool(`extract_brief`, `localize_content`, `format_output`)。Host agent 不需要知道 Omni 存在。

### 5.2 模式(ii): 可选并列(Parallel)

**工作原理**: 同时启动 4 个独立的 MCP server(AutoMedia + OPP + OL + ORF), 每个 server 使用独立的 transport(stdio 或 TCP 不同端口)。Host agent 的 MCP client 配置中注册全部 4 个 server, agent 根据任务类型透明调用相应的 tool。

```
Host Agent (支持多 MCP server 的 client)
    │
    ├── AutoMedia MCP Server  (tools: run_pipeline, select_topic, ...)
    ├── OPP MCP Server        (tools: extract_document, batch_extract, ...)
    ├── OL MCP Server         (tools: translate_md_text, translate_xliff, ...)
    └── ORF MCP Server        (tools: apply_md, apply_xliff, batch_convert, ...)
```

**配置开关**: `omni_config.yaml` 中 `integration_mode: "parallel"`。启动命令 `automedia omni start-all` 或 `automedia omni start --mode parallel`。

**性能特征**: 零转发延迟(agent 直连 Omni server), 但 host agent 需维护 4 个 MCP 连接。适用于高级用户和需要精细控制 Omni 调用参数的场景。

**对 host agent 的接口暴露**: 4 个 server 共 20+ 个 MCP tool。Agent 可直接调用 OPP 的 `extract_document`(此时不需要经过 AutoMedia 封装)。

### 5.3 模式(iii): Python SDK 直接 import

**工作原理**: AutoMedia 的 `automedia/omni/` adapter 直接在 Python 进程中 import OPP/OL/ORF 的 Python 包, 调用其 Python API, 不走 MCP 通信。

```python
from automedia.omni import OPPAdapter, OLAdapter, ORFAdapter

# OPP 直接提取
opp = OPPAdapter()
result = opp.extract("brief.docx")
# result.md_content, result.manifest

# OL 直接翻译
ol = OLAdapter(config_path="~/.automedia/omni/ol_config.yaml")
translated = ol.translate(result.md_content, source_lang="en", target_lang="zh")

# ORF 直接回填
orf = ORFAdapter()
output_path = orf.backfill(
    original_file="brief.docx",
    xliff_file=translated.xliff_path,
    output_dir="./output/"
)
```

**配置开关**: `omni_config.yaml` 中 `integration_mode: "sdk"`。要求 OPP/OL/ORF 已 pip install 在同一 Python 环境中。

**性能特征**: 零序列化开销, 同一进程内调用, 延迟最低。适用于批量处理和高吞吐场景。但 Omni 包版本冲突风险高于前两种模式。

**对 host agent 的接口暴露**: 不直接暴露给 host agent(需通过 AutoMedia MCP tool 间接暴露, 或由用户自行编写 Python 脚本)。

### 5.4 三种模式对比

| 对比维度 | (i) 默认转发(Proxy) | (ii) 可选并列(Parallel) | (iii) Python SDK |
|----------|-------------------|----------------------|-----------------|
| **部署复杂度** | 低: 只配 1 个 MCP server, 内部自动管理 Omni | 高: 需配 4 个 MCP server, 每个有独立配置和凭证 | 中: 需 pip install 3 个包, 在 AutoMedia 进程中运行 |
| **延迟** | 中等: 增加一层 MCP 序列化(50-200ms) | 低: agent 直连 Omni server, 无转发 | 最低: 同进程内调用, 接近 0 额外开销 |
| **调试便利性** | 中等: Omni 调用日志在 AutoMedia server 日志中, 需区分 | 高: 每个 server 有独立日志, 可单独 debug | 高: 同一个 Python 进程, 可加断点直接 debug |
| **可定制性** | 低: 只能使用 AutoMedia 暴露的 3 个封装 tool | 高: agent 可直接调用 Omni 的 20+ 个原生 tool | 最高: Python API 无限制调用, 可组合任意参数 |
| **失败传播** | 隔离: Omni 失败只影响封装 tool, AutoMedia 其他 tool 不受影响 | 隔离: 单个 server 崩溃不影响其他 server | 聚合: Omni import 错误或包版本冲突可能影响 AutoMedia 主进程 |
| **适用用户** | 普通用户, 希望"一键 Omni"不关心底层 | 高级 agent 用户, 需要精细控制 | Python 开发者, 需要批量/自动化集成 |
| **推荐场景** | 默认推荐, 90% 场景适用 | agent 运维 / 多步骤编排 | 批量文档处理 / CI 管道 |

---

## 6 输入/输出 artifacts 一致性设计

### 6.1 OPP 输出到 AutoMedia 内部 schema 映射

OPP 每次提取产生 4 类输出文件, AutoMedia 必须将它们映射到内部 schema:

| OPP 输出 artifact | 格式 | AutoMedia 映射目标 | 映射逻辑 |
|-------------------|------|-------------------|---------|
| `{name}.md` | Markdown(YAML frontmatter 含 source_lang, target_lang) | `topic.research_data.brief_md` 或 `topic.research_data/{name}.md` | 直接复制到 topic 的 research_data 目录; YAML frontmatter 解析后合并入 topic metadata |
| `{name}.xlf` | XLIFF 1.2/2.0 | `topic.research_data/{name}.xlf` | 保留在 research_data 目录, 供后续 OL translate-xliff 使用 |
| `{name}_manifest.json` | JSON(manifest_version, source, extraction, resources, skeleton) | `topic.topic_metadata.setdefault("omni", {})["opp_manifest"]` | 解析 manifest 中的 source.file_path/file_hash_md5/extraction 等字段, merge 到 topic metadata; `source.file_hash_md5` 写入 `pipeline_md5.json.omni_inputs` |
| `{name}.skeleton.zip` | ZIP(DOCX/PPTX 原始结构) | `topic.research_data/{name}.skeleton.zip` | 直接复制保留, 供 ORF apply-xliff 回填使用 |

**伪代码**:

```python
def ingest_opp_output(opp_result_dir: str, topic: Topic) -> None:
    manifest = json.loads(read(f"{opp_result_dir}/{name}_manifest.json"))

    # 1. MD 内容 -> research_data
    md_path = f"{opp_result_dir}/{name}.md"
    topic.research_data["brief_md"] = read(md_path)
    topic.research_data["brief_md_path"] = str(copy_to_research(md_path))

    # 2. manifest metadata -> topic metadata
    src = manifest["source"]
    topic.topic_metadata.setdefault("omni", {})["opp_manifest"] = {
        "original_filename": src["original_filename"],
        "format": src["format"],
        "file_hash_md5": src["file_hash_md5"],
        "extraction_warnings": manifest["extraction"]["warnings"]
    }

    # 3. MD5 写入 pipeline_md5.json
    append_md5_to_pipeline("omni_inputs", src["original_filename"], src["file_hash_md5"])
```

### 6.2 OL 输出到 AutoMedia artifacts 映射

OL 每次翻译产出以下文件, AutoMedia 映射到 `05_publish/{lang}/` 目录:

| OL 输出 artifact | 格式 | AutoMedia 映射目标 | 映射逻辑 |
|------------------|------|-------------------|---------|
| `translated_{name}.md` | Markdown(YAML frontmatter 含 source_lang/target_lang/processor/version) | `05_publish/{target_lang}/{name}.md` | YAML frontmatter 解析后; 文件名按 `{target_lang}_{name}.md` 重命名; 存入 05_publish 目录下以 target_lang 命名的子目录 |
| `translated_{name}.xlf` | XLIFF 1.2(含 `<note from="OL">`) | `05_publish/{target_lang}/{name}.xlf` | 同步存入, 供 ORF 回填使用 |
| warnings(OL 质量门控输出) | 字符串列表 | `pipeline_md5.json.omni_translation_warnings` | 非阻断性警告, 写入元数据而非阻断流程 |

**伪代码**:

```python
def store_ol_output(ol_output_dir: str, target_lang: str, project: Project) -> None:
    publish_dir = project.dir / "05_publish" / target_lang
    publish_dir.mkdir(parents=True, exist_ok=True)

    for file in ol_output_dir.iterdir():
        if file.name.startswith("translated_") and file.suffix == ".md":
            # 解析 YAML frontmatter
            frontmatter = parse_yaml_frontmatter(file)
            assert frontmatter["target_lang"] == target_lang

            # 复制并重命名
            new_name = file.name.replace("translated_", f"{target_lang}_")
            shutil.copy2(file, publish_dir / new_name)

            # 注册到 project assets
            project.register_asset(
                type="translation",
                lang=target_lang,
                path=str(publish_dir / new_name),
                md5=compute_md5(publish_dir / new_name)
            )
```

### 6.3 ORF 输出到 AutoMedia artifacts 映射

| ORF 输出 artifact | 格式 | AutoMedia 映射目标 | 映射逻辑 |
|-------------------|------|-------------------|---------|
| `result.{target_format}` | DOCX/PPTX/EPUB/PDF 等 | `05_publish/{target_lang}/deliverables/{name}.{format}` | 存入 deliverables 子目录, 区分翻译文本和格式文档 |
| 布局溢出报告(可选) | JSON | `pipeline_md5.json.omni_orf_report` | ORF AI layout detection 结果写入元数据 |

### 6.4 完整 artifacts 流程示意

```
客户 brief.docx
    │
    ▼ OPP
[research_data/]
  brief.md           ← 给 agent 读的内容
  brief.xlf          ← 保留 XLIFF
  brief_manifest.json ← 元数据 → topic_metadata
  brief.skeleton.zip ← 保留骨架
    │
    ▼ AutoMedia 生产链路(完全独立, 不依赖 Omni)
[04_gate_pass/]
  ... 自媒体产出 ...
    │
    ▼ OL(用户手动触发或 MCP 调用)
[05_publish/en/]
  en_article.md      ← 英文翻译稿
  en_article.xlf     ← 英文 XLIFF
    │
    ▼ ORF(用户手动触发或 MCP 调用)
[05_publish/en/deliverables/]
  en_article.docx    ← 客户交付品
  en_article.pptx    ← 客户交付品(可选)
```

---

## 7 语言矩阵与多语生产模式

### 7.1 主打语言方向: EN 到 ZH

当前 PRD-2 的默认语言方向是英文到中文双向:

| 方向 | 用例 | Omni 组件 | 备注 |
|------|------|-----------|------|
| EN brief -> ZH MD(入站) | 客户英文 brief -> research 用中文 | OPP + OL | OPP 提取英文 MD, OL translate-md 成中文 |
| ZH 成品 -> EN DOCX(出站) | 中文自媒体文章 -> 英文交付 | OL + ORF | OL translate-md 翻译 MD, ORF apply-md 转 DOCX |
| EN pipeline 全链路(海外模式) | 英文 source -> 英文 publish | 无 Omni | 纯 AutoMedia, default_lang=en |
| ZH pipeline 全链路(国内模式) | 中文 source -> 中文 publish | 无 Omni | 纯 AutoMedia, default_lang=zh |

### 7.2 多语扩展接口

语言扩展接口通过 `brand-profile.yaml` 的 `languages` 字段暴露:

```yaml
# brand-profile.yaml 多语扩展示例
brand:
  name: "OneStepMore"
  default_lang: zh              # 当前生产默认语言

languages:
  zh:
    label: "中文"
    tts_voice: "zh-CN-YunxiNeural"
    whisper_lang: "zh"
    cta_template: "关注 {brand_name}, 获取更多 AI 内容"
    blocked_words: ["投资情报", "金融分析"]
    date_format: "YYYY年M月D日"

  en:
    label: "English"
    tts_voice: "en-US-JennyNeural"
    whisper_lang: "en"
    cta_template: "Follow {brand_name} for more AI content"
    blocked_words: ["investment advice", "financial analysis"]
    date_format: "MMMM D, YYYY"

  ja:         # 预留
    label: "日本語"
    tts_voice: "ja-JP-NanamiNeural"
    whisper_lang: "ja"
    cta_template: "{brand_name}をフォローして最新AI情報を入手"
    blocked_words: []
    date_format: "YYYY年M月D日"

  ko:         # 预留
    label: "한국어"
    tts_voice: "ko-KR-SunHiNeural"
    whisper_lang: "ko"
    cta_template: "{brand_name}을(를) 팔로우하여 최신 AI 콘텐츠 확인"
    blocked_words: []
    date_format: "YYYY년 M월 D일"
```

### 7.3 海外独立多语生产模式实现路径(用例 C)

用例 C 的场景 C-1(英文全链路)的实现路径:

1. **brand-profile 配置**: `default_lang: en`, `languages.en` 下配置 TTS voice / Whisper lang / CTA / blocked words
2. **pipeline 启动时语言检测**: `Pipeline.run()` 读取 `config.brand.default_lang`, 若为 `en` 则:
   - research 阶段: 使用英文 keyword 调用 Tavily 英文搜索
   - 文案生成: LLM prompt 指定 output language = English
   - TTS: 使用 `en-US-JennyNeural` 而非默认中文音色
   - Whisper: 加载 `tiny.en` 或 `small.en` 模型(更小更快)
   - LLM 字幕校对: 使用英文校对 prompt
   - CTA: 读取 `languages.en.cta_template`
   - 平台 adapter: 预留英文平台(Instagram/X/YouTube)
3. **多语 lexicon 资源**: brand-profile 的 `brand_taxonomy` 配置品牌在各语言中的翻译(品牌名/产品名/口号)。OL 翻译时会读取此 lexicon 确保品牌术语一致性

其他语言(JA/KO/ES/FR/AR)扩展路径相同, 只需在 `languages` 下新增条目并配置对应 TTS/Whisper 资源。当资源不可用时(如小语种 Whisper 模型), pipeline 回退到默认语言配置并输出 warning。

---

## 8 LLM Provider 配置独立性

AutoMedia 主链路的 LLM 配置与 OL 的 LLM 配置完全独立, 两条流水互不交叉。

### 8.1 AutoMedia model_config.yaml(主链路)

```yaml
# ~/.automedia/model_config.yaml
# AutoMedia 自媒体生产链的 LLM 配置
# 用于: 文案生成 / Humanizer / Copy-review / Brand CTA / 字幕校对 / Vision QA

text_generation:
  provider: openai-compatible
  base_url: "https://api.example.com/v1"
  api_key_env: "AUTOMEDIA_LLM_KEY"
  model: "deepseek-v4-flash"
  default_params:
    temperature: 0.7
    max_tokens: 4096

vision:
  provider: openai-compatible
  base_url: "https://api.example.com/v1"
  api_key_env: "AUTOMEDIA_VISION_KEY"
  model: "qwen3.7-plus-vision"

subtitle_proofread:
  provider: openai-compatible
  base_url: "https://api.example.com/v1"
  api_key_env: "AUTOMEDIA_LLM_KEY"
  model: "deepseek-v4-flash"
```

### 8.2 OL 独立配置(ol_pool)

```yaml
# ~/.automedia/omni/ol_config.yaml
# OL 的独立 LLM 池配置
# 用于: MD/XLIFF 翻译 / 质量评判 / 占位符恢复
# 不共享 AutoMedia 的 model_config.yaml

llm_pool:
  translation:
    - provider: "openai"
      model: "glm-4-flash"
      priority: 1
      role: "translation"
      api_key: "${ZHIPU_API_KEY}"
      base_url: "https://open.bigmodel.cn/api/paas/v4"
      timeout: 120.0
    - provider: "openai"
      model: "deepseek-v4-flash"
      priority: 2
      role: "translation"
      api_key: "${OPENCODE_GO_KEY}"
      base_url: "${OPENCODE_GO_BASE_URL}"
      timeout: 120.0

  judging:
    - provider: "openai"
      model: "agnes-2.0-flash"
      priority: 1
      role: "judging"
      api_key: "${AGNES_API_KEY}"
      base_url: "https://apihub.agnes-ai.com/v1"
      timeout: 120.0

  restoration:
    - provider: "openai"
      model: "glm-4-flash"
      priority: 1
      role: "restoration"
      api_key: "${ZHIPU_API_KEY}"
      base_url: "https://open.bigmodel.cn/api/paas/v4"
      timeout: 120.0
```

### 8.3 独立性原则

- AutoMedia 的 model_config.yaml 只控制自媒体生产链(文案/图片/视频/语音)的 LLM 调用
- OL 的 `llm_pool` 只控制翻译服务的 LLM 调用(translation / judging / restoration / profiling 四角色)
- 两个配置文件格式不同(AutoMedia 是扁平的 role -> provider 映射, OL 是角色列表 + 优先级链)
- AutoMedia 不强制接管 OL 配置, 也不要求 OL 使用与 AutoMedia 相同的 provider
- OL 的 api_key 通过 `${ENV_VAR}` 语法从环境变量读取(OAI/Anthropic 兼容格式任意 provider), 不与 AutoMedia 共享密钥

---

## 9 安全与隔离

### 9.1 Omni 工具文件路径 Allowlist

Omni adapter 的所有文件操作受路径 allowlist 限制:

```yaml
# ~/.automedia/omni_allowlist.yaml
allowed_paths:
  - "/mnt/d/AutoMedia/projects/"
  - "/mnt/d/AutoMedia/briefs/"
  - "/mnt/d/AutoMedia/knowledge-base/"
  - "/tmp/automedia/omni/"
read_only_paths:
  - "/mnt/d/AutoMedia/briefs/"     # brief 目录只读
write_paths:
  - "/mnt/d/AutoMedia/projects/"
  - "/tmp/automedia/omni/"
```

OPPAdapter.extract() 读取的源文件必须在 `allowed_paths` 内, ORFAdapter.backfill() 的输出路径必须在 `write_paths` 内。越权访问抛出 `PermissionError`。

### 9.2 Omni 产物 MD5 追踪

所有 OPP/OL/ORF 产物的 MD5 哈希写入 `pipeline_md5.json`:

```json
{
  "omni_inputs": {
    "original_filename": "client_brief.docx",
    "file_hash_md5": "a1b2c3d4e5f6..."
  },
  "omni_extraction": {
    "brief.md": {"md5": "b2c3d4e5f6a7..."},
    "brief.xlf": {"md5": "c3d4e5f6a7b8..."}
  },
  "omni_translation": {
    "en_article.md": {"md5": "d4e5f6a7b8c9..."},
    "en_article.xlf": {"md5": "e5f6a7b8c9d0..."}
  },
  "omni_orf_outputs": {
    "en_article.docx": {"md5": "f6a7b8c9d0e1..."}
  }
}
```

### 9.3 失败传播策略

Omni 操作的失败按以下策略传播(OPP 失败不阻断主链):

| Omni 组件 | 失败场景 | 传播策略 |
|-----------|---------|---------|
| OPP | 文档格式不支持 / OCR 失败 / 文件损坏 | **不阻断**: `extract_brief_adaptive()` 写入 warning 到 gate log, 返回空结果; 用户可通过 `automedia pool attach-brief --md-file` 手动提供 MD |
| OL | LLM API 超时 / 翻译质量门控未通过 | **不阻断**: OL 自身有模型池故障转移(primary failure -> backup); 全部失败时写入 warning, 保留原文 MD 不翻译 |
| ORF | 回填失败 / skeleton 不匹配 / 布局溢出 | **不阻断**: ORF 写入 warning, 保留回填前状态; 用户可重新配置参数后重试 |

**总原则**: Omni 是增强功能而非核心功能, 其失败不应影响 AutoMedia 自媒体生产主链的正常运行。

### 9.4 Omni 包版本隔离

由于模式(iii)需要在 AutoMedia 进程中直接 import OPP/OL/ORF, 存在包依赖冲突风险:

- OPP/OL/ORF 声明 `python >= 3.13`, AutoMedia 应与其保持一致
- OL 有可选的 ML 依赖(sentence-transformers / torch), 安装冲突时翻译功能降级为无 TM/glossary 模式(不阻塞)
- AutoMedia 的 `pyproject.toml` 将 OPP/OL/ORF 列为可选依赖组: `pip install automedia[omni]`

---

## 10 红线

本章列出 8 项不可妥协约束, 一字不差来自 PRD-1 第 9 节。Omni 接入不改变任何红线。

1. **14 道 Gate 编排逻辑不可绕过**: 所有 Gate 的依赖关系、并行执行条件、阻断条件必须通过 `pipeline_orchestrator.py`(现 `$ automedia-package/01_核心脚本/pipeline_orchestrator.py`)执行, 任何 API / CLI / MCP 入口都不提供跳过 Gate 的参数。Gate 失败 = Pipeline STOP, 不得静默忽略。

2. **HyperFrames HTML+GSAP -> MP4 视频方案唯一**: 视频生产的唯一路径是 `TTS -> Whisper -> SRT -> outline -> compositions -> hyperframes lint -> bun x hyperframes render -> MP4`。禁止引入 FFmpeg concat 图片序列、MiniMax 视频生成(video-01 / Hailuo-2.3)、或任何替代渲染方案作为主要生产路径。现 `hyperframes-workflow` skill(位于 `$ automedia-package/02_Skills/hyperframes-workflow/SKILL.md`)是生产全链路的唯一参考。

3. **飞书/微信公众号 API 必须作为可配置 adapter 保留**: 现 `pre_wechat_upload.py`(位于 `$ automedia-package/01_核心脚本/pre_wechat_upload.py`)的 7 步门控和飞书通知逻辑必须封装为可选 adapter。允许用户在 `adapters/registry.yaml` 中 `enabled: false` 禁用, 但**不得删除源代码**。其他贡献者可以提交 PR 禁用, 但项目核心维护者不得移除。

4. **强制工序 humanizer -> copy-review -> brand-cta 三道不得跳过**: 文案生成后的三道 Gate 顺序固定: `humanizer`(9 类 AI 写作模式清除) -> `copy-review`(五轮结构审查) -> `brand-cta-review`(零容忍项检查)。brand-cta-review 未通过前禁止调用 TTS。现 `$ automedia-package/01_核心脚本/copy_review_gate.py` 是代码级强制门控实现。

5. **A/V 同步铁律**: 每句语音存在的时间内, 有且仅有该句的文字作为字幕。SRT 时间轴基于 Whisper ASR 真实时间戳, 不得使用等分法。字幕渲染后必须通过 PIL 像素亮度法验证字幕区域(V6 Gate), 确保每帧字幕与实际音频对齐。现 `$ automedia-package/01_核心脚本/validate_srt_timing.py` 是时间轴验证实现。

6. **全量 QA(非抽样)原则**: 所有 QA 检查必须覆盖全量数据, 不得抽样。具体包括: 逐 Entry Vision QA(非 `3 帧/30 秒采样`), 末尾静音段单独检查, 全量 Whisper 音频转写(非 `前 30 秒`)。全量 QA 逻辑参见现 `$ automedia-package/01_核心脚本/full_qa_checker.py`。降级策略(如 Vision API 限流时的像素亮度法)必须在 QA 报告中标注 `降级` 字样。

7. **每个 Gate 产物 MD5 写入 pipeline_md5.json 追踪**: 每个 Gate 完成后, 其产物文件的 MD5 哈希必须写入 `{project_dir}/pipeline_md5.json`。Pre-send Gate(V2/Gate5) 必须验证当前文件 MD5 与记录值一致, 防止 QA 一个文件、发送另一个文件。现 `$ automedia-package/01_核心脚本/pre_send_whisper_check.py` 包含 MD5 校验逻辑。

8. **Agent 不得 archive 项目(仅用户 --force 可绕过)**: 任何 AI agent(包括 AutoMedia 自身 agent)不得执行项目归档操作。项目归档必须由用户通过 `automedia archive --project <id> --force` 手动触发。违反此规则的 agent 行为视为工艺失误, 立即回退。现项目生命周期中 `INV-8` 不变量的强制约束。

**Omni 集成不改变以上任何红线**: OPP 提取在 research 阶段之前发生(早于 G0), OL+ORF 回填在 publish 阶段之后发生(晚于 L3)。Omni 操作不进入任何 Gate 的检查范围, 不影响 Gate 的 MD5/Pipeline STOP/archive 等行为。

---

## 11 里程碑

### M1: Omni Adapter Python SDK(2 周)

**交付物**:
- `automedia/omni/` 目录结构 + 抽象基类 `BaseOmniAdapter`
- `OPPAdapter` 封装(extract / batch_extract / detect_format)
- `OLAdapter` 封装(translate / translate_batch / judge)
- `ORFAdapter` 封装(backfill / apply_md / apply_xliff)
- `OmniToolRegistry` 注册中心
- `~/.automedia/omni_config.yaml` 配置模板
- `~/.automedia/omni_allowlist.yaml` 模板
- OPP/OL/ORF 作为可选 pip 依赖声明(`pip install automedia[omni]`)
- 单元测试覆盖 adapter 核心方法(覆盖率 >= 80%)

**退出标准**:
- [ ] `from automedia.omni import OPPAdapter; OPPAdapter().extract("test.docx")` 返回内容
- [ ] `from automedia.omni import OLAdapter; OLAdapter().translate("# Hello", "en", "zh")` 返回翻译内容
- [ ] `from automedia.omni import ORFAdapter; ORFAdapter().apply_md("test.md", "docx")` 输出 DOCX
- [ ] `pytest tests/omni/ -v` 全部通过
- [ ] `pip install automedia[omni]` 在干净环境中成功安装

### M2: 三种集成模式实现(3 周)

**交付物**:
- 模式(i)默认转发: AutoMedia MCP server 新增 `extract_brief` / `localize_content` / `format_output` 三个 tool
- 模式(ii)可选并列: `automedia omni start-all` 启动脚本, 4 个 MCP server 各自独立运行
- 模式(iii)Python SDK: 模式(i)实现中已在 SDK 层面完成, 补充文档
- 自动调用触发: `topic-pool.ingest_file()` 集成 `extract_brief_adaptive`
- 手动调用触发: `automedia omni localize` / `format-output` / `ingest` 三个 CLI 子命令
- MCP tool `localize_output` 暴露给 host agent
- 三种模式的切换通过 `omni_config.yaml` 的 `integration_mode` 字段控制

**退出标准**:
- [ ] MCP client 调用 `extract_brief` 后收到 MD 内容
- [ ] `automedia omni start-all` 启动后 4 个 MCP server 均可被 host agent 连接
- [ ] DOCX 文件通过 topic-pool 收录后自动提取为 MD, research 阶段可读
- [ ] `automedia omni localize --project <id> --target-langs en,ja` 产出多语言文件
- [ ] `automedia omni format-output --input article.md --target-format docx` 产出 DOCX
- [ ] 三种模式切换后对应行为正确

### M3: 多语 Pipelines + EN-ZH 默认可用(2 周)

**交付物**:
- `brand-profile.yaml` 多语扩展(`languages` 字段 + TTS voice / Whisper lang / CTA 配置)
- pipeline 启动时按 `default_lang` 选择语言资源(TTS / Whisper / LLM prompt / CTA)
- 英文全链路端到端验证: EN brief -> EN research -> EN 文案 -> EN TTS -> EN 视频 -> EN 发布(门槛)
- XLIFF 回填 DOCX/PPTX 端到端验证: DOCX -> OPP -> OL -> ORF -> DOCX(结构保留, 文本翻译正确)
- Omni 产物 MD5 写入 pipeline_md5.json
- 失败传播策略验证: OPP 失败不阻断主链
- 路径 allowlist 拦截测试

**退出标准**:
- [ ] `brand-profile.yaml` 配置 `default_lang: en` 后, pipeline 产出英文文案 + 英文 TTS + 英文 SRT
- [ ] 任一 DOCX 文件经 OPP -> OL(en->zh) -> ORF 后, 回填 DOCX 结构一致、图片保留、文本翻译正确
- [ ] OPP 提取失败时 pipeline 正常继续, gate log 包含 warning
- [ ] Omni 路径越权访问被正确拦截
- [ ] `pipeline_md5.json` 包含所有 Omni 产物的 MD5

---

## 12 风险与开放问题

| # | 风险 | 影响 | 概率 | 缓解方案 |
|---|------|------|------|---------|
| R1 | OL 主链消费失败(LLM API 全部不可用) | 多语言产出不可用, 但 AutoMedia 主链路不受影响 | 中 | OL 内置模型池故障转移(priority 链); 全部不可用时写入 warning, 原文 MD 作为降级交付品 |
| R2 | ORF 回填反而 break 客户 DOCX watermark/排版 | 客户交付品格式损坏, 品牌形象受损 | 中 | ORF 的 skeleton.zip 机制保留原 DOCX 结构; 回填后做 layout overflow 检测; 关键交付前人工审核 |
| R3 | Omni 版本升级与 AutoMedia 兼容性变化 | OPP/OL/ORF 新版本 API 或输出格式变化导致 adapter 失效 | 低 | 在 pyproject.toml 中锁定主版本号(如 `opp>=0.2,<0.3`); adapter 层做版本检测, 不兼容时告警并回退到 safe mode |
| R4 | 多语扩展 speed bump 成本(TTS/Whisper 资源) | 小语种 TTS 音色不可用或 Whisper 模型精度不足 | 中 | 按语言分优先级: EN/ZH(首发), JA/KO(次发), ES/FR/AR(后续); 资源不可用时降级为默认英语 |
| R5 | OPP 超大文件(>100MB DOCX)处理超时 | 提取时间过长, 影响用户体验 | 低 | OPP 本身有 100MB 默认上限; AutoMedia 在 `omni_config.yaml` 中设 `max_auto_extract_mb: 50`, 超过的提示手动调用 |
| R6 | Python SDK 模式下包依赖冲突(OPP/OL/ORF 各自依赖版本冲突) | 无法安装 automedia[omni] | 低 | 声明可选依赖组, 冲突时用户可选用模式(i)或模式(ii)绕过; CI 中做全依赖安装测试 |
| R7 | XLIFF 回填后客户 DOCX 内嵌图片丢失或偏移 | 交付品图片缺失, 需要重新提取和回填 | 中 | OPP 的 images.json 携带图片位置元数据(含浮動圖片 wp:anchor 偏移); ORF 使用这些元数据精准回填 |

---

## 13 词汇表

| 术语 | 英文 | 定义 |
|------|------|------|
| Omni Triad | Omni Triad | 指 Omni 三件套的统称, 包含 OPP(预处理)、OL(本地化)、ORF(回填)三个组件。三件套独立发布为 PyPI 包 |
| OPP | Omni Pre-Processor | 文档预处理工具。将 DOCX/PPTX/PDF 等多格式文档提取为 Markdown + XLIFF + manifest.json + skeleton.zip |
| OL | Omni Localizer | 本地化翻译工具。以 LLM 驱动 MD/XLIFF 的翻译, 内置质量门控、术语管理、模型池故障转移 |
| ORF | Omni Re-Formatter | 格式回填工具。将翻译后的 XLIFF 回填为原始格式(DOCX/PPTX/EPUB 等)的交付文档 |
| XLIFF | XML Localization Interchange File Format | 业界标准的本地化交换格式(XML-based)。OL 翻译 XLIFF 文件, ORF 从 XLIFF 读取翻译回填 |
| Skeleton.zip | Skeleton ZIP | OPP 从源 DOCX/PPTX 提取的 ZIP 归档, 保留原始 OOXML 结构(不含内容文本), 供 ORF 回填使用 |
| Manifest | Manifest JSON | OPP 每次提取产生的元数据 JSON, 包含来源文件信息、提取统计、图片资源清单、skeleton 路径 |
| Adapter | Adapter | AutoMedia 中的可插拔适配器, 此处指 `BaseOmniAdapter`, 将 OPP/OL/ORF 封装为统一接口 |
| Loose-coupling | Loose Coupling | Omni 与 AutoMedia 的松耦合关系: Omni 是旁路 adapter, 不嵌入主链, 失败不阻断主流程 |
| Optional Injection | Optional Injection | Omni 的调用方式: 非管线必经节点, 用户或系统在特定触发条件下选择调用, 而非每次生产必经 |

---

> **文档结束** — 编写自检清单:
> - [a] 红线 8 项完整出自 PRD-1 第 9 节(见第 10 章)
> - [b] ASCII 集成架构图(见 4.1)
> - [c] 三种集成模式对比表(见 5.4)
> - [d] Artifacts mapping 表(见第 6 章)
> - [e] LLM 独立配置策略明确(见第 8 章)
> - [f] Omni 仅 adapter 工具库定位明确, 不是主链(见 0.4, 4.2)
> - [g] 里程碑 3 个(M1-M3, 见第 11 章)
> - [h] 全文贯彻"按需调用"原则(Omni 非必经节点, 失败不阻断)
> - [i] 不冲突 PRD-1 的 SDK API 与 hooks 设计(Omni 不修改 Gate / Pipeline / GateHook 等现有设计)
