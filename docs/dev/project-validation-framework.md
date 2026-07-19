# Project Validation Framework

> 不是"又一个需要维护的文档"。
> 是把 founder 的 expectations 嵌入到每次代码变更验证流程中的**薄胶水层**。

**定位**：连接 `founder-expectations.md`（标准）和 `evaluation-matrix-principles.md`（测量工具）的决策层。
**核心机制**：每次修改代码 → 查影响映射表 → 只验证受影响的 expectations → 记录结果。

---

## 1. 标准 ↔ 测量映射

| D3 阶段 | 相关 Expectations | 对应 Evaluation Matrix 维度 | 验证方式 |
|---------|------------------|---------------------------|---------|
| Phase 1: Setup (F01-F10) | F02/F03/F06/F07 | Documentation + Production Readiness | CI + Agent |
| Phase 2: Input (F11-F16) | F11/F12/F16 | E2E Integration | Agent True Test |
| Phase 3: Run & Monitor (F17-F22) | F17/F18/F19/F20/F21 | E2E Integration + Robustness | CI + Agent |
| Phase 4: Review (F23-F28) | F24/F25/F26/F27/F28 | E2E Integration | Agent + Human |
| Phase 5: Publish (F29-F35) | F29/F30/F31/F34/F35 | E2E Integration | CI + Agent |
| Phase 6: Repeat (F36-F39) | F36/F37 | Production Readiness | CI |
| Phase 7: Monitor (F40-F43) | F42/F43 | Agent Readiness | CI |
| Phase 8: Iterate (F44-F48) | F44/F45/F46/F47/F48 | Design | Code Review |

---

## 2. 影响映射表（框架"活着"的关键）

Agent 改完代码后，**根据改的文件自动知道要验证什么**。

```yaml
# 文件模式 → 受影响的 D3 expectations → 验证步骤
# 每个 pattern 的 steps 都是 agent 本来就会做的事，
# 只是显式关联到 founder 关心的期望上。

impact_map:

  # ─── Gates ─────────────────────────────────────
  - pattern: "gates/**/*.py"
    affects:
      - "F24 (G1 humanizer — article not AI-sounding)"
      - "F25 (G0 fact check — factual accuracy)"
      - "F26 (G3 brand CTA — brand compliance)"
      - "F27 (V0-V7 video/subtitle quality)"
    steps:
      - "pytest tests/test_gates/ -v"
      - "如果新增 gate → 检查 failure_modes.py 有对应条目"
      - "检查 gate 命名符合 _VALID_GATE_NAME_RE"

  # ─── MCP Tools ─────────────────────────────────
  - pattern: "mcp/tools.py"
    affects:
      - "F05 (list_brands MCP tool — brand discovery)"
      - "F12 (source_path/source_url — input source material)"
      - "F42 (get_config, search_assets — config introspection & search)"
      - "F17 (run_pipeline — one-command run)"
    steps:
      - "如果新增/删除 tool → True Test T7: agent 仍能 operate via MCP"
      - "python -c 'from automedia.mcp.server import create_server'"
      - "检查 mcp_allowlist.yaml 是否需同步更新"

  # ─── MCP Resources / Accounts ──────────────────
  - pattern: "mcp/**/*.py"
    affects:
      - "F05 (brand/account discovery tools)"
      - "F42 (config introspection)"
    steps:
      - "True Test T8:  agent 能否发现 brands 和 config"
      - "检查工具返回的 JSON schema 是否一致"

  # ─── Pipeline Runner ───────────────────────────
  - pattern: "pipelines/runner.py"
    affects:
      - "F07 (pipeline modes — 8 modes)"
      - "F11 (topic → article — core promise)"
      - "F17 (one-command run)"
      - "F21 (pipeline resume)"
    steps:
      - "True Test T3:  topic → draft.md 能走通 (text_only)"
      - "如果改 mode 列表 → 同步 README 和 MCP validation"
      - "True Test T6:  resume 能正常工作"

  # ─── GateEngine ────────────────────────────────
  - pattern: "pipelines/gate_engine.py"
    affects:
      - "F19 (gate failure detail — structured errors)"
      - "F20 (pipeline resilience — stop/retry)"
      - "F24 (auto-recovery — quality retry + regeneration)"
    steps:
      - "检查 failure_mode 行为: stop 终止、retry 重试"
      - "pytest tests/test_pipeline/ -v"

  # ─── Platform Adapters ─────────────────────────
  - pattern: "adapters/platforms/**/*.py"
    affects:
      - "F29 (automation levels — auto/review/manual)"
      - "F30 (WeChat Official Account)"
      - "F31 (Zhihu)"
      - "F34 (multi-platform routing + capability matrix)"
      - "F35 (publish error handling — credential refresh, retry)"
    steps:
      - "pytest tests/test_adapters/ -v"
      - "如果新增平台 → 更新 F34 的平台能力矩阵"
      - "检查 BrandProfile 的 platform 绑定逻辑"

  # ─── Publish Engine ────────────────────────────
  - pattern: "adapters/publish_engine.py"
    affects:
      - "F29 (automation levels filter)"
      - "F34 (partial failure — one platform failure doesn't block others)"
      - "F35 (structured publish errors, credential refresh)"
    steps:
      - "检查 per-platform automation level 逻辑"
      - "检查 platform isolation (失败不级联)"

  # ─── CLI Commands ──────────────────────────────
  - pattern: "cli/commands/**/*.py"
    affects:
      - "F02 (first command — automedia help shows commands)"
      - "F03 (automedia init — project skeleton, interactive wizard)"
      - "F06 (automedia doctor — setup verification)"
      - "F17 (one-command run)"
    steps:
      - "automedia --help 检查命令列表完整性"
      - "如果新增/删除命令 → 同步 cli-reference.md"
      - "检查 --json flag 在全局是否可用"

  # ─── Config Loader ────────────────────────────
  - pattern: "core/config_loader.py"
    affects:
      - "F01 (installation — config layers working)"
      - "F03 (init — config skeleton)"
      - "F04 (API key — env var vs config file priority)"
    steps:
      - "检查 config 层级数仍 >= 4"
      - "检查 .env.example 有新增的环境变量"

  # ─── Accounts ────────────────────────────────
  - pattern: "accounts/**/*.py"
    affects:
      - "F04 (credential management — encrypted store)"
      - "F35 (credential refresh on publish failure)"
    steps:
      - "检查 AES-256-GCM 加密是否仍启用"
      - "pytest tests/ -k account"

  # ─── HITL ────────────────────────────────────
  - pattern: "hitl/**/*.py"
    affects:
      - "F28 (human content review before publish — H0 gate)"
    steps:
      - "检查 HITL 框架与 pipeline 的集成"
      - "cli: automedia hitl approve/reject 仍需工作"

  # ─── Hooks ────────────────────────────────────
  - pattern: "hooks/**/*.py"
    affects:
      - "F43 (pipeline integrity — MD5 checksum tracking)"
    steps:
      - "检查 MD5 tracker 是否仍作为 readonly hook 运作"
      - "True Test T9:  output 目录有 pipeline_md5.json"

  # ─── Cron ─────────────────────────────────────
  - pattern: "cron/**/*.py"
    affects:
      - "F37 (scheduled production — cron MCP tools)"
    steps:
      - "检查 add/list/remove/get_cron_health/test_cron_schedule MCP 工具"
      - "检查 cron config 格式与 runner 同步"
```

### Agent 如何使用这个映射表

```
Agent 改代码
  │
  ├─ 列出修改的文件集合
  ├─ 匹配 impact_map 中的 pattern
  │   ├─ 匹配到 → 执行 affects 列的验证步骤
  │   └─ 未匹配 → 安全，不需额外验证
  ├─ 如果有 expectation 状态变化 → 记录到 §5 评审历史
  └─ 完成
```

**关键设计**：不匹配任何 pattern 的改动不需要验证 → 框架不产生额外负担。
每个 pattern 的验证步骤都是 agent 本来就会做的事（跑测试、检查文档），不是新工作。

---

## 3. 验证节奏

| 层 | 名称 | 验证什么 | 谁 | 频率 | 产出 |
|----|------|---------|-----|------|------|
| **L1** | 变更时验证 | 只验证受影响的 expectations (查映射表) | Agent | 每次修改代码 | 评审历史一行 |
| **L2** | 周期诊断 | Evaluation Matrix 8 维度全量采集 | CI (GitHub Actions) | 每周 | `evaluation-data-{date}.json` |
| **L3** | 季度评审 | D3 全面 review + True Test | Founder + Agent | 每季度 | 评审历史 + action items |

### L1: 变更时验证（自动）

嵌入到 agent 的完成条件中。不需要额外 CI 配置，只需要 agent 遵守这个流程。

### L2: CI 诊断（自动）

Evaluation Matrix §12 已经有完整的数据采集脚本（~120 行 bash）。
只需要创建一个 `.github/workflows/validate.yml`：

```yaml
# 每周一跑 evaluation matrix 数据采集
# 对比基线 → 如果有新 P0 出现 → PR comment 告警
# 记录到 .omo/validation-trend.csv
```

不需要人工干预。数据自己会说话。

### L3: 季度评审（唯一需要人工的部分）

Founder 要做的事：
1. 跑一次 True Test（10 条检查，agent 可以代跑 9 条）
2. Review `founder-expectations.md` §3 的 expectations —— 哪些 expectations 还成立、哪些已经过时、哪些需要新增
3. 在评审历史（§5）记录一行

**这是唯一不能自动化的部分**。"Does this project deliver the value I intended?" 只有 founder 自己能回答。

---

## 4. 文档 Freshness 自动检测

```yaml
# 每个文档记录最后验证时间和过时阈值
# Agent 进入项目时自动检查，过时的文档会收到提醒
# 不阻塞开发——只做标记

freshness_checks:
  founder-expectations.md:
    max_age_days: 90        # 季度 review
    last_verified: 2026-07-15
    stale_action: "提醒 founder 做季度评审"

  evaluation-matrix-principles.md:
    max_age_days: 180        # 方法论相对稳定
    last_verified: 2026-07-14
    stale_action: "检查评估标准是否仍适用"

  project-validation-framework.md:
    max_age_days: 180
    last_verified: 2026-07-16  # 创建日期
    stale_action: "检查影响映射表是否覆盖新的代码模块"
```

检查逻辑：
```python
if today - last_verified > max_age_days:
    mark_doc_stale(path)   # 标记为过时
    # 创建 GitHub Issue 提醒
```

---

## 5. 评审历史

每次 L1/L2/L3 验证后，追加一行：

| 日期 | 验证类型 | 修改文件 | 影响 Expectations | True Test | 结论 |
|------|---------|---------|-------------------|-----------|------|
| 2026-07-16 | 框架创建 | - | - | - | 🟢 初始版本 |

**记录规则**：
- **L1**: Agent 完成变更后 → 记录改了什么文件、影响了哪些 expectations、跑了什么验证、结果
- **L2**: CI 跑完后 → 记录 8 维度评分、与基线对比 delta、新出现的 P0/P1
- **L3**: 季度评审后 → 记录评审结论、action items、新的/过时的 expectations

---

## 6. 这个框架不是什么 / 是什么

### ❌ 不是

- ❌ 不是"又一篇要维护的文档"——它是连接已有工作的薄胶水层
- ❌ 不是 `d3-gap-analysis.md` 的替代品——那篇是一次性审计，已完成归档
- ❌ 不增加新工作——影响映射表里的每个验证步骤都是 agent 已经会做的事
- ❌ 不需要人工运营——L1/L2 都是自动的，L3 才是唯一的 founder 投入点

### ✅ 是

- ✅ 是"什么时候验证什么"的决策树
- ✅ 是"改 gate 时记得跑哪个测试"的程序员助手
- ✅ 是把 founder 的抽象期望翻译成具体验证步骤的翻译层
- ✅ 是保证"每次代码变更都不会让项目偏离 founder 期望"的安全网

---

## 7. 相关文档

- [`founder-expectations.md`](founder-expectations.md) — D3: Founder 视角的 48 条期望
- [`evaluation-matrix-principles.md`](evaluation-matrix-principles.md) — 8 维度系统诊断工具包
- [`d3-gap-analysis.md`](../archived/d3-gap-analysis.md) — 一次性差距审计（已归档）
- [`.opencode/skills/project-validation.md`](../../.opencode/skills/project-validation.md) — 规范位置（所有 agent 共享）。Claude Code 使用 `.claude/skills/` 原生副本，Codex CLI 使用 `.codex/skills/` 原生副本
