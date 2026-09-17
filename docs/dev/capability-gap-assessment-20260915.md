# AutoMedia 能力盘点与缺口评估（面向"私有部署 + 服务优先"）

> **日期**：2026-09-15
> **方法**：全部结论基于实跑或代码核对，标注证据（文件:行 / 命令）。不含实现路径。
> **用途**：作为《开发报告》的输入；供后续 plan（Prometheus）引用。
> **方向前提**（已定）：私有部署 + 服务优先，目标 = 把「选题→文本生产→门控报告→中英多平台发布」闭环做到**能对真实客户交付**。

---

## 0. P0 执行结果（2026-09-15 晚，已执行）

| 项 | 结果 | 证据 |
|:--|:--|:--|
| P0-1 G4 停死 | **已修复** | 从 `_TEXT_ONLY/_TEXT_WITH_COVER/_IMAGE_CAROUSEL/_SOCIAL_THREAD` 四个文本预设移出 G4(微信清单)与 G5(HTML 硬门)。二者是**输出格式门**，要求微信/HTML 包装，而文本预设只产 Markdown → 必失败。回归：`test_runner.py`/`test_e2e/test_full_pipeline.py`/`test_wechat_checklist.py`/`test_html_hard.py`/`test_e2e/test_synth_fixtures.py` 全绿 |
| P0-2 LLM 接入 | **已完成** | `~/.automedia/model_config.yaml` 指向 AMD Radeon Cloud（`DeepSeek-V4.1-Flash`，OpenAI 兼容）；`automedia doctor` → `llm_api ✓` |
| P0-3 实跑 text_only → success | **未达成（外部阻塞）** | 修复后机器已能推进：实跑 `CW ✅(65.8s) → G0 ✅(带源材料) → G1 ✅ → G2 命中 429 限流`，900s 超时；复测 provider 返回 `503 no_available_workers` |

**结论**：**文本轨的机器现在能跑通了**——G4/G5 不再是障碍（这是本次修的真实缺陷）；**唯一剩余阻塞是所提供 LLM 端点（AMD 免费版）的容量/可用性**（429 限流 + 503 无 worker）。这是环境/基础设施问题，非代码问题。

**剩余待办**：换用可靠 provider，或降低门控的 LLM 调用量；随后即可完成"一次 success 的实跑"。

---

## 0b. P0 更新（2026-09-15 夜）

- **LLM 已解决**：provider 的模型清单是 `DeepSeek-V4-Flash` / `DeepSeek-V4-Flash-Vision-Exp` / `Qwen3.8-Flash-Next` / `Qwen3.8-27B` / `MiniCPM5-2B` / `MinerU2.5-Pro`。所给的 `DeepSeek-V4.1-Flash` **不存在**（故返回 503）；`Qwen3.8-Flash-Next` 是**推理模型**（`content` 常为空，不适用）；改用 **`DeepSeek-V4-Flash`**（非推理、~5s/次、支持 `json_object`）后正常。
- **实跑进展**：`text_only` 已能推进到 **7/11 门**：`CW✅ G0✅ G1✅ G2✅ G3✅ G6✅ H0✅ → L1❌`（真 LLM，带源材料）。
- **新发现（同类缺陷，未修）**：**L1–L4 四道生命周期门全部依赖"发布/归档/平台拆分/翻译"产物，而生产流水线从不产出这些产物**（`publish_log` 全仓无生产者）→ 任何真实 `text_only` 跑都会在 L1 停死。实测 L1/L2/L3/L4 在真实上下文下全 fail。**与 G4/G5 同一性质：预设里含了"输入不存在的门"；测试用 `_mock_results` 掩盖了它。**
- **需要决策（属"触及现有能力"，按红线需逐项批准）**：
  - **A**：与 G4/G5 一致——把 L1–L4 移出四个文本预设（它们属于发布/生命周期阶段）；
  - **B**：让 L1–L4 条件化——产物不存在时跳过（保留能力，改动门本身 + 测试）；
  - **C**：让流水线产出这些产物（更大）。

---

## 0c. P0 完成（2026-09-15 深夜）—— 文本轨实跑 success

- **已执行选项 A**：把 L1–L4 从四个文本预设移出（与 G4/G5 同一处理）。依据：`publish_log`/归档/平台/翻译产物**全仓无生产者**，且无任何其他流程运行 L1–L4（`distribute` 跑 D 门）；实测四门在真实上下文下全 fail，只能靠 `_mock_results` 通过。
- **回归**：`test_runner.py` / `test_e2e/test_full_pipeline.py` / `test_synth_fixtures.py` / `test_wechat_checklist.py` / `test_html_hard.py` 全绿（3 个断言旧设计的测试已同步更新）。
- **实跑（headless，真 LLM `DeepSeek-V4-Flash`）**：`STATUS = success`，`CW✅ G0✅ G1✅ G2✅ G3✅ G6✅ H0✅`（7/7）。
- **产物**：`01_content/drafts/*.md`（完整中文文章）、`05_review/gate-report/*.{md,json}`、`pipeline_md5.json`、`cost_log.jsonl`。
- **✅ 已 ratify（2026-09-15）：选项 A。** L1–L4 验证的是"发布/归档/分发/翻译"下游流程的产物，不属于内容生产；故从生产预设移出，门保留在注册表。**A+（把 L 门接回各自流程：distribute→L3 / archive→L2 / omni localize→L4 / publish→L1）列入开发报告。**
- **仍待处理（非 demo 范围）**：`auto`/`video_only`/`short_video`/`repurpose` 仍含 L1–L4（同类隐患）。
- **附带发现**：CLI `automedia run` 传 progress → H0 会暂停等人工审批（headless 自动跳过）；CLI 无 `--skip-review` 标志。`llm_client` 对不支持 JSON-schema 的 provider 有 `json_object` 回退。

---

## 1. 结论摘要：**尚未就绪，原因是一个真实的阻塞缺陷**

**"文本轨能跑通"目前是假的。** 实跑证据：

```
AUTOMEDIA_FAKE_LLM=1 automedia run --mode text_only
→ 13 门构造成功；CW,G0,G1,G2,G3 ✅；G4 ❌ (stop)；status=partial；退出码 0
```

**根因**：`G4 = wechat_checklist`（`gates/wechat_checklist.py:196`）被放进**通用文本轨**，且 `_failure_mode="stop"`。它无条件要求微信文章的包装：`no_markdown` / `cover_exists` / `tag_count`(≥5) / `body_image_count`(3–6)。而内容写作门**产出的是 Markdown**（`content_writer.py:69` 的 SEO 评分项明确奖励 `heading_structure` H1/H2/H3，落盘 `{ts}_draft.md`）。

**两者互斥**：CW 产 Markdown（含 `#`），G4 禁 Markdown → **任何正常文章都会在 G4 停死**。且 `runner.py` 只在 `text_with_cover` 模式设置 `cover_image`（`:1470`），text_only 不设 → `cover_exists` 也必失败。

→ 因此：**核心文本生产链无法完成。** 这是就绪判定的第一道门，且**不是"接上 LLM 就能好"**。

---

## 2. 能力盘点（子系统 × 现状 × 证据）

| 子系统 | 现状 | 证据 | 状态 |
|:--|:--|:--|:--:|
| 三层入口（SDK/CLI 19/MCP 68） | 真实 | 实跑 `automedia run`；`--help` exit 0 | ✅ |
| 门控引擎（顺序/重试/回退/HITL 暂停） | 真实、健壮 | 实跑 13 门按序执行；`gate_engine.py` | ✅ |
| 文本生产 CW | 真实（真调 LLM + 写 `.md`） | 实跑产出 `01_content/drafts/*.md` | ✅ |
| 文本轨 G0–G3 | 可用 | 实跑通过 | ✅ |
| **文本轨 G4（微信清单）** | **在通用文本轨里，必失败** | `wechat_checklist.py:196`；实跑 G4 ❌ | ❌ **阻塞** |
| 文本轨 G5/G6/H0/L1–L4 | 未验证到（被 G4 挡住） | 实跑未到达 | ⚠️ |
| 视频轨 V0–V7 | **未接线**：门只读上游 key，但全项目**无任何生产者** | `entries/transcription/avg_brightness/...` 0 处赋值；`audio_path` 0 生产者 | ❌ |
| AudioPipeline | 真实但**孤立**（无导入者） | `pipelines/__init__.py` 仅导出 | ❌ |
| 采集端 | `HotCollector` = 关键词层 + **LLM 编题层** + seed | `collector.py:210-277` | ⚠️ 半真 |
| 采集端持久化 | MCP 路径 `PoolDB(":memory:")` | `mcp/tools/topics.py:64/271/316` | ❌ |
| 采集调度 | `jobs.yaml` 有模板，**无 scheduler 消费** | `cron/jobs.yaml`；`pipeline_schedules: []` | ❌ |
| 分发适配器 | 11 真实 API（含**微信/知乎**）+ feishu + 8 有意 stub | 各 publisher 真实 HTTP | ✅ |
| D 门 | 只重写内容，**不发布**；发布走 PublishEngine | `cli/commands/distribute.py` | ⚠️ 语义混淆 |
| 报告层 | 每 run 产 `gate-report.{md,json}`，但**丢弃 remediation**、无客户级呈现 | `gate_report.py:143-151`；实跑报告"Blocked by: no reason recorded" | ⚠️ 缺交付形态 |
| 配置（6 层） | 真实，但 gate 阈值/规则**硬编码 Python** | `overrides.py` 仅 include/exclude/failure_mode | ⚠️ |
| 品牌配置 → 门控 | 通路存在但**只通 2/4**：`brand_name`✓ `blocked_words`✓ `aliases`✗ `cta_principles`✗ | `brand_cta.py:110`（读 `brand_aliases`，schema 是 `aliases`）；`cta_principles` 无 gate 读取 | ⚠️ |
| 凭证库 | AES-256-GCM + OAuth2/Cookie/APIKey | `accounts/` | ✅ |
| HITL / Director | 真实（H0 暂停 + approve/reject） | `gate_engine.py` | ✅ |
| Omni Triad（多语言） | 真实，但依赖**外部包** `omni-localizer` 等 | `pyproject.toml:57`；`ol_adapter.py` | ⚠️ 非自有 IP |
| 资产库 | SQLite + Chroma | `asset_library/` | ✅ |
| 退出码（无人值守） | **失败时退出码 0**（仅 `status=="failed"` 抛 1；halt 时为 `partial`） | `cli/commands/run.py:341`；实跑 `EXIT=0` | ❌ |
| MCP 鉴权 | 无 | `evaluation-2026-09-06.md` | ⚠️ |
| 配置 schema 校验 | 无（merged dict 直接使用） | 同上 | ⚠️ |
| 异常处理 | 156 处宽 `except Exception` | 同上 | ⚠️ |
| 测试 | 4,594 函数 / 248 文件（数量真实） | `grep -rE "def test_"` | ✅（但 V 门用 `_mock_results` 掩盖未接线） |

---

## 3. 关键缺陷（P0，阻塞"能交付"）

| # | 缺陷 | 影响 | 证据 |
|:--|:--|:--|:--|
| ~~P0-1~~ | ~~文本轨含 G4（微信门），必停死~~ **已修复（见 §0）** | 从文本预设移出 G4/G5 | `tests/test_runner.py` |
| **P0-2** | **LLM 端点不可达** | 真跑时卡在 CW | `automedia doctor` = `llm_api ✗`；实跑卡 CW |
| **P0-3** | **退出码不反映失败** | 无人值守无法检测失败（形态 C） | `run.py:341`；实跑 `EXIT=0` |
| **P0-4** | **采集端不落盘/无调度/`:memory:`** | "选题→生产"断成两截 | `topics.py:64`；`jobs.yaml` |
| **P0-5** | **报告无 remediation / 非交付形态** | 客户看不到"怎么改"（付费理由载体） | `gate_report.py:143-151` |
| P1-1 | 品牌配置只通 2/4（别名死链、cta 不读） | "按品牌定制"名不副实 | `brand_cta.py:110` |
| P1-2 | 视频轨未接线 | 视频能力=0 | §2 |
| P1-3 | 门控硬编码，无可配置标准 | 形态 B 需重构 | `overrides.py` |
| P2 | MCP 无鉴权 / 配置无 schema 校验 / 156 宽 except | 生产稳健性 | `evaluation-2026-09-06.md` |

---

## 4. 开发工作清单（按依赖排序，锚定"服务优先 + 私有部署"）

> 目标 = **能对真实客户交付一次完整闭环**。范围 = 文本轨（+可选图片轨），不含视频/规则集/计费。

**P0 — 让闭环能跑（先决条件）**
1. **修 G4 在文本轨的位置**：文本轨不应包含微信专属门（或按平台条件化 G4；`_filter_gates_for_platform` 目前是 no-op）。验收：`text_only` 一次跑完 13 门不 halt。
2. **接通 LLM provider**（含回退链）。验收：`automedia doctor` 的 `llm_api` = ✓。
3. **端到端验证**：`text_only` 产出完整 `draft.md` 且全门通过。验收：status=success。

**P1 — 让闭环"能交付"**
4. **报告层补"怎么改"**：把 `FAILURE_MODES.fixes` + `_derive_suggestion` 写进报告；输出客户可读形态（干净 MD/HTML）。验收：报告含"哪不达标/为什么/怎么改"。
5. **采集端三修**：`:memory:`→落盘；选题入库；调度可用（外部 crond 调 CLI）。
6. **退出码修复**：halt/失败返回非 0。验收：cron 能判失败。

**P2 — 打通"分发"（独特优势）**
7. **真实发布 E2E**：≥1 中文平台（微信/知乎）+ ≥1 全球平台（WordPress/Medium）。验收：一条命令产出可访问链接。
8. **服务交付封装**：一次客户交付的输入→输出路径固定、可重复（brand + topic → 内容 + 报告 + 发布）。

**P3 — 稳健性（服务期需要）**
9. 品牌配置修正（别名/cta）；MCP 鉴权；配置 schema 校验；收窄宽 except。

**明确不做（本阶段）**：视频轨、客户/行业规则集（形态 B）、计费、多租户、新增门控/平台、架构重写。

---

## 5. 就绪判定

| 门槛 | 状态 |
|:--|:--|
| 方向明确（私有部署 + 服务优先） | ✅ 已定 |
| 能力盘点完整 | ✅ 本文 |
| 缺口/工作清单完整 | ✅ 本文 |
| **核心链实跑通过（text_only 完整一轮）** | ❌ **未通过（G4 阻塞）** |
| LLM provider 就绪 | ❌ 待接（用户可提供） |

**判定：尚未就绪。** 差的**不是"结论"，是"机器本身没跑通"**——`text_only` 被 G4 停死，且 LLM 未接。

## 6. 剩余的前置准备（就这 2 件，做完即就绪）

1. **修 G4 / 文本轨跑通**（P0-1）+ **接 LLM**（P0-2）→ 实跑一次 `text_only` 到 `status=success`。
2. 确认第 1 步通过后，即可进入：**开发报告 → 开发 → Prometheus plan**。

> 关键：**不要**在"文本轨未跑通"的情况下写开发报告——否则报告建立在"应该能跑"而非"已跑通"上，正是要避免的陷阱。

## 7. 对流程的建议

- 本文即《开发报告》的**能力/缺口输入**。
- 建议顺序：**先做 P0-1/P0-2 并实跑验证（这是唯一的前置缺口）** → 再写开发报告 → 再开发（P1/P2）→ 期间或之后调用 **Prometheus** 写 plan。
- Prometheus 写 plan 时，建议以本文 §4 的 P0–P3 为骨架，§5 的"实跑通过"为验收基线。
