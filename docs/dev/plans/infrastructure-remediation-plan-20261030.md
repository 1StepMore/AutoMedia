# 基础设施整改计划（Infrastructure Remediation Plan）

> **日期**：2026-10-30
> **来源**：[infrastructure-audit-20261030.md](../infrastructure-audit-20261030.md)（Agent 双角色视角的有效性审计）
> **性质**：计划文档，供逐项批准与分批执行。**不含日期排期**（时间节点由发起人定）。
> **红线声明**：本计划全部动作**不增减** 33 门 / 20 适配器 / Omni Triad（简报 §六）。涉及"对外改名"（T3-1）、"新增 MCP 工具"（T3-7）与"修改 mcp_allowlist.yaml"（A9，红线 3）的项单独标注为批准点，未经批准不执行；其余均为 bug 修复、文档刷新与死代码标注，不触红线。
> **评审记录**：2026-10-30 执行前评审修订——① 验收命令修正（`automedia validate run` 无 `--affected` flag，改用 `scripts/validation_run_affected.py`）；② doc-inventory `--check` 实测已恢复绿色，T0-1 改为"入库后收尾再生成"；③ T2-2 前置核查发现 allowlist 不读沙箱环境变量（回归风险）且错配修复触红线 3，增设批准点 A9；④ T2-3 补错误码文档联动；⑤ 裁决项 8→9。

---

## 零、总体判断：这不是一条复杂执行路径

审计给出的 11 条建议若作为一个整体看是复杂的，但按**风险等级与审批需求**分解后是：

```
Track 0 收尾（卫生，无审批）──┐
Track 1 文档真实性（无审批）──┼── 三条轨道互相独立、可并行、可独立验收
Track 2 小代码修复（bug 级）──┘
Track 3 裁决项 ×9 ──────────── 每项独立批准；不批准 = 维持现状并记录，不阻塞任何轨道
```

写 plan 的必要性来自三点：① 简报红线要求"触及现有能力的改动逐项批准"——本计划就是批准载体（见 §四 批准点汇总表）；② 修复横跨代码/文档/流程/命名，必须分批验收才符合 ADR-005 原子提交纪律；③ 本仓库的既有教训（RFC-001 差点撞 90 天 CI 红线）证明写下来的裁决才会被执行。

---

## 一、Track 0：收尾批次（无审批需要，约半天）

| # | 任务 | 依据 | 验收 |
|---|---|---|---|
| T0-1 | 再生成 `docs/doc-inventory.md`——**必须排在 T0-5 之后、作为 Track 0 最后一步**（新增入库文件会改变 tracked 清单；2026-10-30 实测当前 `--check` 已绿） | 审计 §5.3 | 入库后重跑 `python scripts/doc_inventory.py --check` exit 0 |
| T0-2 | README 两处 "10 MUST/MUST NOT / 10 agent constraints" 改 9（`README.md:319,573`） | 审计矩阵#35 | doc gate 绿；grep 无 "10 MUST" |
| T0-3 | glossary "67 tools"→68、门清单指针 `runner.py`→`gate_plan.py`；user-introduction "65 个工具"→68 | 审计矩阵#45 | 抽查一致 |
| T0-4 | `pkg-AutoMedia.zip`、`pkg-AutoMedia/` 裁决：删除或入 `.gitignore`（**删除属破坏性动作，执行前向发起人确认内容**） | 审计 §5.3 | git status 无此二项 |
| T0-5 | 三份 dated 报告（codebase-audit-20261022 / project-analysis-20261029 / doc-update-audit-20261029）与本审计、本计划入库 | doc-update-audit L3 惯例 | git tracked + inventory 再生成覆盖 |
| T0-6 | `pytest -m redline` 表述对齐（**推荐不新增 CI 步骤**：3 个 enforcement 测试已随默认套件在 PR 跑、`test_e2e/test_red_lines.py` 已随 nightly e2e 跑，README:717 作为本地命令是准确的；仅需随 T0-2 修正计数措辞） | 审计矩阵#35 | README 措辞与执行实况一致 |
| T0-7 | 发现链补口：`llms.txt` 与 MCP getting-started resource 挂 docs/skills 四篇链接 | 审计矩阵#46 | 纯 MCP 客户端路径可发现 |

> 已完成项（无需再做）：`.gitignore:18` 已反排除 development-brief-v2；H5/H6 preset 文档漂移已修；doc gate 主路径实跑绿。

---

## 二、Track 1：文档真实性批次（无审批需要，约 1 天）

| # | 任务 | 依据 |
|---|---|---|
| T1-1 | `docs/user/hitl-framework.md`：修复 4 处幽灵符号（`DiagnosticAgent`/`BaseDecisionAgent`/`decision.orchestrator`，:165,:229,:262,:267）；director-approval 一节显式标注 "reserved: not wired"；preset 一节改为如实描述（`active_preset.yaml` 不影响运行时） | 审计 §3.3.4/5 |
| T1-2 | `docs/user/deployment.md:164`（已删除的 `hooks/metrics.py`）、`docs/dev/developer-guide.md:201`（md5_tracker 位置） | 审计 §3.1.4 末 |
| T1-3 | maintainer skills 刷新：deep-modules 换 RFC-001 §6 重验数字（1,617→2,165、"64 tools"→68）；doc-sync 修 `mcp/tools.py` 死路径（:16,:394）、ADR 计数、DOC MAP 补 agent-reference/doc-inventory/docs/skills；validation-runner 144→160 并补目录清单 | 审计 §4.2.9 |
| T1-4 | 【批准点 A1】`project-validation` skill 处置：**推荐**改写为指向 `automedia validate coverage`/回归飞轮的薄封装；备选移 `docs/archived/`。其现有形态（指向冻结快照 + 死路径）是四技能中唯一"教错流程"的 | 审计 §4.2.10 |
| T1-5 | （可选加固）把 `docs/user/hitl-framework.md`、`docs/glossary.md` 纳入 doc gate 扫描集，覆盖"符号存在性"类漂移 | doc-update-audit §五 盲区表 |

---

## 三、Track 2：小代码修复批次（bug 级，约 1–2 天，红线下）

| # | 任务 | 依据 | 说明 |
|---|---|---|---|
| T2-1 | `core/md5_tracker.py:30,53-54` 与 `omni/md5_integration.py:60,69`：补 `encoding="utf-8"`、改 tmp+rename 原子写，收敛为共用原语 | 审计 §3.3 末 / project-analysis §4.2.1 | **阻碍赚钱判据直接命中**：中文路径（本仓库路径即 `D:\贯维\...`）下 MD5 状态文件随 locale 漂移，损害完整性验证可信度 |
| T2-2 | allowlist 收口：`effects/mcp.py`（analyze_content）补校验；`tools_distribution.py:84-95` 与 `tools/pipeline.py:176-182` fail-open→fail-closed；`tools/setup.py` init_config 补校验；一并处理 `publish_content` 默认参数 fail-closed 可用性缺陷。**前置核查（评审新增）**：allowlist 只认 `AUTOMEDIA_MCP_ALLOWLIST_PATH`，不读沙箱的 `AUTOMEDIA_PROJECTS_DIR/CONFIG_DIR`（`allowlist.py:31,70`）——fail-closed 前先枚举调用这些工具的验证场景与默认路径错配面，确认沙箱内路径不会被误拒；错配修复若需改 `src/automedia/mcp/mcp_allowlist.yaml`，属红线 3，走批准点 A9 | 审计 §3.3.6 / project-analysis §4.3.1 | 安全边界与实际执行一致；fail-closed 后默认路径仍可用；`validation_run_affected.py` 全绿 |
| T2-3 | `mcp/tools/review.py:161-183`：对已结束 run 的 review_decision 返回结构化 STALE/NOT_RUNNING，不再报 `approved: true`；`_hitl_waiters` 在 mark_finished 时摘除。**联动**：新返回语义同 PR 更新 `docs/user/mcp-setup.md` 错误码表与工具 docstring | 审计 §3.3.3 | 消除"对 agent 假成功"；文档与代码同步 |
| T2-4 | `hitl preset --set` 去假化（最小方案）：文档降级为展示用途 + `hitl config` 输出标注"不影响运行时"；运行时读取留待 T3-2 裁决 | 审计 §3.3.4 | 不实现 preset 驱动（那是 T3-2 的一部分） |

**批次验收**：`pytest -x -q` 全量 + 新增针对性测试（T2-1 用中文路径 tmp_path 用例与并发写用例；T2-2 用 allowlist 外路径断言拒绝）；`automedia validate run --affected`（validation-affected 同口径）；doc gate 两模式绿。

---

## 四、Track 3：裁决项（每项独立批准；推荐已给，批准后各自成 PR）

### 批准点汇总表（发起人逐项裁决用）

| 批准点 | 议题 | 推荐 | 批准后工作量 |
|---|---|---|---|
| A1 | project-validation skill：改写 vs 归档 | 改写为 validate 薄封装 | ~2h |
| A2 | distribute 双语义：改名 vs 文档显式化 | **先文档显式化**，改名等真实混淆案例 | 文档 2h / 改名半天+全套文档 |
| A3 | director-approval：接线 vs 明示休眠 | **本轮明示休眠，接线与形态 A 绑定排期** | 休眠 2h / 接线 1–2d |
| A4 | decision 层回收方式 | 导出收敛 + dormant 标注（不物理删除） | ~2h |
| A5 | STANDARDS 词表：裁剪 vs 标注 reserved | 裁剪至实际使用集（schema 权威变更） | ~3h 含场景回归 |
| A6 | 场景深度提升 top-5 清单 | 批准清单后逐场景原子 PR | 每场景 0.5–1d |
| A7 | 阈值变更强制留痕（waiver 门禁） | STANDARDS 增补规则 + validate diff 增 bucket | ~1d |
| A8 | 新增 introspection MCP 工具（list_registered_gates / list_adapters） | **推迟**至开放核商业化时；届时按新增能力流程走（68→70 计数 + 文档表 + doc gate 同步） | 1–2d |
| A9 | 修改 `src/automedia/mcp/mcp_allowlist.yaml`（评审新增：T2-2 的默认目录错配修复可能需要） | **须发起人明确要求**（AGENTS.md 红线 3）；推荐仅当代码侧 fail-closed 造成默认路径不可用时做最小化增补 | ~0.5h |

### 各项要点

- **T3-1（A2）distribute 双语义**：CLI `automedia distribute` 跑 D1-D7 改写门；MCP `distribute_content` 走 PublishEngine 直接发布（`tools_distribution.py:98`）。推荐先做零风险文档显式化：`help_mcp`/instructions/工具描述/`docs/skills/distribution-workflow.md` 首段互相指向并声明"本工具不执行 D 门改写"。改名（A 选项）动对外接口，牵动 AGENTS.md §9 表、mcp-setup、doc_reality 审计，须单独批；按简报"不做猜测性设计"，等真实用户混淆案例再定。
- **T3-2（A3）director-approval**：`requires_approval` 无人写入 gate_context（`runner.py:1217-1221` 丢弃），3 个 MCP 工具结构性永不触发。**推荐本轮明示休眠**（工具描述 + hitl-framework + 结构化返回说明），把"接线"与形态 A（门控产出可交付报告）绑定：接线后的暂停点必须先有"导演能看懂的门级报告"，否则接了也空转。技术路径已预研：runner 写入 preset 的 requires_approval（一处）+ `_gate_requires_approval`（`gate_engine.py:443`）已有读取端 + resume 机制已存在，接线性价比高，缺的是产品前提。
- **T3-3（A4）decision 层**：保留活跃的 `review_audit.py` 与 `decision/pydantic/`；`DecisionArtifact`/`schema_validator`/`log_force_provenance`/`NodeProvider`/`NodeExecutor` 收敛导出 + docstring 标 dormant。物理删除不在本轮（简报红线从严解释）。
- **T3-4（A5）STANDARDS 词表**：56 个 key 仅 6 个被引用。裁剪属 schema 权威文档变更，须导演批。机制上已核实安全：`validation/standards.py` 的 `StandardsRegistry` 是**从 STANDARDS.md 加载词表**的一侧（`validate_standard` 在场景加载时交叉校验），裁掉未被引用的 key 不会破坏任何现有场景；裁剪后跑 `automedia validate list`（全库加载）+ coverage 回归确认。
- **T3-5（A6）场景深度 top-5**（加深不加宽，不触"不加门"红线）：① publish-dry-run 把 20 平台 would_fail 纳入断言；② text_only journey 补 gate_records_pass 断言；③ analyze_content/get_config 补 data_has 输出断言；④ archive 场景补 artifact 断言；⑤ injection 场景扩展到 localize 路径。每场景一个 PR。
- **T3-6（A7）阈值留痕**：STANDARDS.md 增补"场景阈值变更须同 PR 附 baseline diff 或 waiver 行"；`validation/diff.py` 把 threshold 变化列为独立 bucket（小改）。动机：min_chars 800→500 无记录下调（produce-article）正是框架自定义的"需导演裁决"信号，裁决流程必须闭环。
- **T3-7（A8）introspection 面**：让 G4/G5、manual-stub 对纯 MCP agent 可见（开放核可发现性）。新增工具会牵动 68 计数与文档表——文档门禁会强制同 PR 更新，这是机制红利而非障碍；但属新增能力，推迟到有商业触发时。

---

## 五、执行顺序与统一验收

1. **顺序**：Track 0 → Track 1 与 Track 2 并行 → Track 3 按批准节奏逐项插入。任何 Track 3 项的"不批准"都不阻塞其他项。
2. **每批统一验收命令组**：`ruff check .` → `mypy src/automedia/ --ignore-missing-imports`（3.11 严格集）→ `pytest -x -q` → `python scripts/check-doc-consistency.py`（涉文档加 `--check-user-docs`）→ 涉场景或涉 MCP 工具行为时 `python scripts/validation_run_affected.py`（CI validation-affected 同口径；**注意** `automedia validate run` 无 `--affected` flag，评审已纠正）。
3. **提交纪律**：ADR-005 issue 驱动原子提交；每任务一个 commit/PR，Track 3 项不与 Track 0-2 混合。
4. **整改自身的可验证性**（用 agent-as-tester 验证整改）：T2 各项附红线级或回归级测试；T3-5/T3-6 的产出物本身是场景与门禁；Track 1 的文档刷新由 scan_identifiers/新增扫描集把关。

## 六、明确不做（本轮）

- 不拆 `GateEngine._run` / `runner` 超长函数——代码形状债，无商业理由不动（简报 §四；project-analysis §5.3 已列为中优先级，留待形态 A 冲刺一并裁决）。
- 不增减门控数量、平台适配数量；不动 D/P 同构家族骨架（#287 已示范按需去重）。
- 不动 SDK 排除边界、`gate_plan` 单一权威、验证层 5 状态语义等已验证有效的结构。
- 不为 G4/G5 建 preset（简报界定 1：出现第二个客户前不做规则集类设计）。
- 不给 CostTracker 建读端——属新增查询能力，暂缓；"写而未读"已在审计矩阵#9 记录，待有成本可见性需求时按新增能力流程裁决。

## 七、执行记录（2026-10-30）

发起人裁决：Track 0–2 全部开始；A1 按推荐（改写）随 Track 1 处理；A2 选"文档显式化"；A3 选"明示休眠"；A4–A7 建议已给出（A7→A6→A5→A4），待确认；A8 推迟、A9 条件触发（未触发）。本机 pre-commit 曾因 WindowsApps `python3` 存根损坏而空转，已修复（复制 python.exe → python3.exe）；全量 pytest 在本机仍有 43 个既有 Windows 环境失败（修复存根前为 211，其中 168 个由坏存根造成），提交以 `SKIP=pytest` 豁免单钩子、其余钩子照跑，43 个失败的修复已立项。

| 批次 | 状态 | 提交 |
|---|---|---|
| 环境修复（python3 存根 + Windows 权限测试） | ✅ | `91a578a` |
| 先前文档批次落地 + 报告入库 + 本计划入库（T0-5） | ✅ | `c00bbed` |
| T0-1/T0-2/T0-3/T0-6/T0-7(llms.txt) + A2 glossary 部分 | ✅ | `fa1e006` |
| T2-1 md5 编码+原子写 | ✅ | `ff8b6f7` |
| T2-3 review_decision STALE + mark_finished 摘除 | ✅ | `d1a3a48` |
| T2-2 allowlist 收口 + 沙箱自备 allowlist | ✅ | `af54d1e` |
| T1-1/T1-2 幽灵符号 + A3 明示休眠 + T0-7 resource | ✅ | `be94da6` |
| T1-4/A1 project-validation skill 改写 | ⬜ 待做 | — |
| T2-1 遗留：record_md5 跨进程读改写竞态（原子写已把损害限定为丢失更新） | ⬜ 记录在案 | — |
| A4–A7（待发起人按建议确认后执行） | ⬜ 待确认 | — |
| A8 introspection 工具 / A9 allowlist 默认目录错配 | ⬜ 推迟/条件 | — |
| 43 个 Windows 既有测试失败修复（已立项） | ⬜ 已立项 | — |
