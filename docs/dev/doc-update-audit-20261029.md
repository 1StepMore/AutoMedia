# AutoMedia 文档更新审计报告

> **审计日期**：2026-10-29
> **审计对象**：AutoMedia `main` 分支（HEAD `9063f89`，版本 1.12.0）下全部 62 个 markdown 文档（`docs/` 60 个 + README.md + AGENTS.md），另核 CHANGELOG.md、pyproject.toml、`.opencode/skills/`。
> **方法**：① 双模式运行 `scripts/check-doc-consistency.py`（默认 + `--check-user-docs`）；② 脚本内省全部 68 个 MCP 工具的真实函数签名，与 AGENTS.md §9 参数表逐行比对；③ `gate_plan.py`/`dag.py`/`failure_modes.py`/`cli/commands/` 等代码实况与各文档声明逐条交叉核对；④ 数字断言全库 grep。所有结论附 `文件:行号` 证据。
> **性质**：只读审计 + 更新建议，未改动任何被审文档。

---

## 一、总体结论

**门禁内的数字全部是绿的**：`check-doc-consistency.py` 两种模式均通过——68 工具 / 19 命令 / 160 场景 / 33 门 / 26 DAG 节点，与代码实况一致；README/AGENTS/index 的尺寸下界断言（68,000+ LOC 等）全部仍成立；版本 1.12.0 与 CHANGELOG 一致；doc-inventory.md 于 2026-10-29 刚再生成。

**漂移全部集中在门禁覆盖不到的地方**，按危害排序是五类：

1. **参数表**：AGENTS.md §9 有 22/68 个工具的参数与真实签名不符（门禁只校验工具名成员和计数，不校验参数）。
2. **结构声明**：AGENTS.md §3 与 agent-reference §Directory Layout 的目录树缺 5 个真实模块，其中 agent-reference 还列着一个已不存在的模块。
3. **preset 组成与示例输出**：两份 user 文档仍描述 2026-08 之前的 22 道 auto 门（含 G4/G5/L1-L4），现 auto preset 是 16 道。
4. **技能与索引清单**：AGENTS.md/agent-reference 的技能清单落后于 `.opencode/skills/` 实况，且声称的 `.claude`/`.codex` 同步副本已断。
5. **非门禁扫描文件里的数字**：`agent-troubleshooting.md` 写着 "65 tools"（该文件不在门禁默认扫描集内，同样的断言若写在 AGENTS.md 里早就红了）。

---

## 二、高优先级：事实性错误（会直接误导 agent / 用户）

### H1. AGENTS.md §9 MCP 参数表 — 22/68 个工具参数过期

方法：内省 `create_server()` 全部 68 个注册工具的处理函数签名，与 §9 表格逐行比对（46 个一致，22 个漂移）。要点：

| 工具 | 表中写的 | 实际签名（多/不同的参数） |
|:--|:--|:--|
| `run_pipeline` | topic, brand, mode, tenant_id, resume_from | 另有 **auto_resume, decision_mode, director, platforms, project_id, source_path, source_url, workflow** 共 13 参 |
| `add_pool_topic` / `pool_add_topic` | topic, category, source | **title**, category, **pool_db_path**（`tools/topics.py`） |
| `add_cron_schedule` | schedule, command | **name, expression**, brand, category, count, platform, mode（`cron_tools.py`） |
| `remove_cron_schedule` | schedule_id | **name** |
| `list_cron_schedules` | —（无参） | mode, platform |
| `search_assets` | query, brand, limit, filters | query, brand, limit, **lang, stage, tags, type**（无 filters） |
| `add_brand` | name, industry, target_audience | 另有 **aliases, blocked_words, brand_identity, cta_principles, tone_guidelines** |
| `approve_gate` / `reject_gate` / `get_pending_approvals` | （无 project_id） | 三者均缺 **project_id**；approve 另有 modifications |
| `publish_content` | project_id, platform, mode | 另有 **account_id, base_dir** |
| `analyze_content` | project_id | 另有 **base_dir** |
| `run_pipeline_from_strategy` / `run_brand_strategy` / `evaluate_content_quality` | （无 pattern/platform） | 均另有 **pattern**；前两者另有 **platform**；strategy 另有 workflow |
| `research_topics` | category, count, trending | category, count, **pattern, trending_data** |
| `get_pipeline_progress` | project_id | 另有 **since_index** |
| `localize_output` | project_dir, target_langs | 另有 **source_lang** |
| `run_validation_scenario` / `run_validation_suite` / `get_validation_report` | （无 context/runs_root） | 前两者另有 **context**，后者另有 **runs_root** |

这是全项目被读得最多的一张表（AGENTS.md 是 agent 第一入口），且 `project_id`、`pattern`/`platform` 这类缺失参数正是 hitl 决策与多平台流程的关键入参。

### H2. AGENTS.md §10 — 列出不存在的 `account refresh` 子命令

§10 写 `automedia account` 含 "connect, list, health, disconnect, **refresh**"；`src/automedia/cli/commands/account.py` 实际只有 connect / list / health / disconnect 四个子命令。讽刺的是 `docs/user/cli-reference.md` 在这一条上反而是对的。

### H3. `docs/dev/agent-reference.md` — 结构声明五处过期

- **§Directory Layout 列出不存在的模块**：`platform/`（ADR-003 改名后 `src/automedia/platform` 已不存在，平台逻辑在 `adapters/platforms/`）。
- **hooks/ 行整行过期**：写 "protocol, **md5_tracker, metrics**"——md5_tracker 已移至 `core/md5_tracker.py`，metrics 已随 #321 删除；实际 `hooks/` = protocol, cost_tracker, pipeline_history。
- **缺 5 个真实模块**：`effects/`、`engines/`、`features/`、`templates/`、`validation/`（后两个恰是 §11 验证层与 §9 引擎工具的载体）。
- **"62,461 LOC"**（第 11 行）精确数字过期（现 71,608）；注意它**逃过了门禁**——size 正则只匹配带 `+` 的下界断言。
- **§Common Task Patterns 两处指引失效**："Add a New Gate" 第 5 步仍写 "gate lists in `automedia/pipelines/runner.py`（`_AUTO_GATE_NAMES` 等）"——#314 之后唯一权威是 `pipelines/gate_plan.py`（`MODE_GATE_NAMES`），AGENTS.md §4 自己已写对；"Add a New MCP Tool" 仍指在 `server.py` 定义 handler——ADR-004 分解后 handler 在 `mcp/tools/*`，server.py 只负责注册。

### H4. AGENTS.md §3 目录树 — 缺 5 个模块

与 H3 同源：`src/automedia/` 实有 22 个子包，§3 树缺 `effects/`、`engines/`、`features/`、`templates/`、`validation/`。`engines/`（媒体引擎，`health_engine` 工具的后端）与 `validation/`（整个验证层）缺失影响最大。

### H5. `docs/user/omni-integration.md:15` — "auto 模式跑 22 道门" 已不成立

原文 "In `auto` mode the full pipeline runs 22 gates: pre-gate, CW, **G0-G6**, V0-V7, H0, **L1-L4**"。`gate_plan.py` 实测：auto preset = **16 道**（pre-gate, CW, G0-G3, **G6**, V0-V7, H0）；G4/G5 与 L1-L4 不在任何 preset（AGENTS.md §4 是对的）。这是 2026-08-30（ADR-006 时代）的旧 preset 组成。

### H6. `docs/user/production-workflow.md:189-209` — 示例输出是旧 preset 的快照

示例显示 "Gates executed: **21**"，逐行列出 **G4 (2.10s)、G5 (1.80s)、L1-L4**，且**没有 G6 和 H0**——与现 auto preset（16 道、必含 G6/H0）双向不符。示例输出应按当前真实输出重画。

### H7. `docs/dev/agent-troubleshooting.md:205` — "the 65 tools listed in AGENTS.md section 9"

实际 68。该文件不在门禁默认扫描集（README/AGENTS/index/doc-inventory 之外），同样的断言写在被扫描文件里会立刻被拦。

### H8. `docs/user/cli-reference.md` — 两处关键缺漏

- **缺 `automedia cron run --due`**：全文 0 处 "due"。这是外部 crond 契约的主调度路径（AGENTS.md §4、`cli/commands/cron.py:51-64`），cli-reference 只写了单作业形式。
- **缺 `automedia mcp` 命令章节**：仅在 Commands Overview 表里出现一行（:41），19 个命令中 18 个有 `##` 章节、唯独 `mcp` 没有。

### H9. README.md 引擎安装段 — 与刚修的 bug 冲突

- `README.md:170-175` 仍推荐 `pip install faster-whisper` 裸装。#332/#338 刚确认 av 19 会移除 faster-whisper 依赖的 `metadata_errors` 参数导致 `TypeError`，`[asr-faster]` extra 因此 pin `av<19`（`pyproject.toml:63-65`）。裸装建议会把用户装进项目自己刚修掉的坑；应改为 `pip install -e ".[asr-faster]"`。
- `[tts-piper]`、`[asr-faster]` 两个 extras 在 README 中完全未提及（agent-reference.md:164-172 已有正确文档，README 反而落后）。
- 安装 extras 表（:243-251）只列 all/dev/mcp/openai/anthropic 5 个；pyproject 实有 12 个（另有 rich、tts-piper、asr-faster、omni-core、omni-pdf、omni-ml、omni——omni 仅在 :104 的 license 提示里顺带出现）。

---

## 三、中优先级：缺漏与不一致

### M1. 技能清单三处不同步

- `.opencode/skills/` 实有 **7** 个技能（另有 **issue-triage.md、pr-review-merge.md**）；AGENTS.md §12 与 agent-reference §Skills 都只列 4 个。
- agent-reference §User-Facing Skills 只列 `brand-strategy.md` 1 个；`docs/skills/` 实有 4 个（`docs/index.md` 反而列全了）。
- agent-reference:200 声称技能"同步副本到 `.claude/skills/` 与 `.codex/skills/`"——两个副本目录实查各只有 5 个文件，**缺 issue-triage、pr-review-merge**，声明的同步约定已断。

### M2. `docs/dev/gate-failure-modes.md` — 漏掉 CW 门

全文 0 处 "CW"（grep 实证）。代码 `failure_modes.py` 注册 33 门含 CW ✓，文档只覆盖 32 门。门禁只校验代码侧 `FAILURE_MODES` 与文档数字断言，不校验这份排障文档的覆盖完整性。

### M3. 双索引互相不一致、且各有漏收

`docs/index.md` 与 agent-reference §Documentation Index 是两份独立维护的索引，内容已经分叉（后者有 override-reference、CHANGELOG、doc-inventory，前者有 skills 表、七阶段、STANDARDS）。两边都**不收录**的在库文档：`user/deployment.md`、`user/windows-deployment.md`、`user/user-introduction.md`、`dev/founder-expectations.md`、`dev/evaluation-matrix-principles.md`、`dev/forward-compat.md`、`dev/project-validation-framework.md`、`dev/validation-loop-log.md`、`dev/plans/NIGHTLY.md`；index.md 还漏 `dev/override-reference.md`。

### M4. `docs/user/api-reference.md` — 缺 5 个公开导出

`automedia/__init__.py` 的 `__all__`（19 个符号）中，**Pipeline、PipelineProgress、DecisionArtifact、PlatformMediaSpec、get_platform_media_spec** 无任何章节（较新的导出未补；`Project`、`sanitize_path` 等老符号核实仍在，无过期内容）。

### M5. `docs/adr/ADR-006` — 机制描述已被后续重构取代，缺状态附录

正文描述 "runner.py 的 `_MODE_MAP` 模块级列表" 与 "22 auto-mode gates"。#314（gate_plan.py 单一权威）、#324/#325（清边、声明序断言）之后：门序权威移出 runner.py，auto preset 缩为 16 道。ADR 是不可变历史，正确做法是加一条 Status 附录注明后续演变（先例：ADR 应记录"实际建成什么"），否则读者会拿 2026-08 的机制理解今天的代码。

### M6. `docs/dev/deep-module-rfc-001.md` — Proposed 已 77 天，90 天红线在即

Status: Proposed 自 2026-08-13。`scripts/check_rfc_aging.py` 的 `PROPOSED_MAX_AGE_DAYS = 90`，即 **2026-11-11 起 CI 会直接失败**。需要在到期前裁决：采纳 / 否决 / 升级为 ADR（其内容引用的 runner 摩擦区也已被 #314 部分改变，裁决时应一并更新）。

---

## 四、低优先级

| # | 项 | 说明 |
|:--|:--|:--|
| L1 | 尺寸数字刷新 | AGENTS.md（as-of 2026-10-24）/ README:16 / docs/index.md:16 的 68,000+/165,000+/600+/5,200+/290+ 均为合法下界但已明显落后，现值 **71,608 core LOC / 271 文件、172,456 总 LOC / 629 文件、5,454 测试 / 308 文件、1,045 tracked files**。刷新后应同步更新 as-of 日期。 |
| L2 | 两个小错 | README:30 "33 quality gates" 的枚举恰好数出 32 项——漏了 **H0**（docs/index.md:23 枚举正确）；AGENTS.md §1 称 `pip install -e ".[dev]"` 为 "full capability"，实为 `.[all]`（dev 不含 omni 系 extras）。 |
| L3 | 三个游离于 git 之外的文档 | ① `codebase-audit-20261022.md`、`project-analysis-20261029.md` 未入库，索引与 inventory 均不可见——建议按库里 dated 报告惯例入库（本报告同理）；② `docs/dev/AutoMedia-development-brief-v2.md` 被 `.gitignore:16` 的 `AutoMedia-*.md` 模式**误伤**（该模式本意应是根目录草稿文件），文档既不能入库也不出现在任何清单——需要加 `!docs/dev/AutoMedia-development-brief-v2.md` 反排除或改名。 |
| L4 | `docs/dev/plans/NIGHTLY.md` | 活区最后复跑记录停在 2026-10-21，而 nightly workflow 每天在跑（jobs：full-test / lockfile-drift / validation-full-suite / check-publish-credentials 均在）。 |
| L5 | 时点快照类**不应**更新 | `founder-expectations.md`（59 tools / 71 scenarios 等为当时的期望值）、`codebase-audit-20261022.md`（149 scenarios）、`docs/archived/*` 全部——历史记录惯例，改了反而破坏证据链。 |

---

## 五、为什么门禁没拦住——盲区清单与可门禁化建议

`check-doc-consistency.py` 目前拦得住的：数字计数（tools/commands/scenarios）、尺寸下界、AGENTS 链接、三文件标识符、inventory 标记、工具表成员、doc↔reality（表成员 + gate/adapter 计数）。本次发现的漂移全部落在以下盲区：

| 盲区 | 本次踩中的实例 | 可门禁化方式（按成本排序） |
|:--|:--|:--|
| "N tools" 等数字断言只扫 4 个默认文件 | agent-troubleshooting:205 "65 tools" | 把 `docs/dev/agent-troubleshooting.md`（及 mcp 模块 docstring 之外的常引文档）加入 `_DEFAULT_DOC_FILES` |
| §9/README 表只校验**成员**不校验**参数** | H1 全部 22 项 | `doc_reality_audit()` 已能取工具 schema/签名，增加参数列比对（比对逻辑与本次审计脚本相同，可直接固化） |
| 目录树/模块清单无校验 | H3/H4（缺 5 模块 + 幽灵 platform/） | `ls src/automedia` 与两处树 diff 的轻量断言 |
| CLI 子命令/flag 级无校验 | H2（refresh）、H8（--due、mcp 章节） | 对 §10 表与 cli-reference 的子命令枚举做 membership 校验（typer `list_commands` 已有现成派生函数） |
| preset 组成、示例输出无校验 | H5/H6 | 至少在 omni-integration/production-workflow 引用 gate 数处改为引用 `gate_plan` 派生值；示例输出加注释"以真实运行为准" |
| 技能清单无校验 | M1 | `.opencode/skills/*.md` 文件名集合 vs AGENTS §12 / agent-reference 清单 + 三副本目录一致性断言 |
| 无 `+` 的精确数字逃过 size 正则 | agent-reference "62,461 LOC" | 正则增加 `([\d,]{4,}) LOC`（无加号）的告警级匹配，或干脆删掉精确值改为下界 |

---

## 六、建议更新顺序（收益/工作量）

| 批次 | 内容 | 预估 | 理由 |
|:--|:--|:--|:--|
| 1 | AGENTS.md：§9 参数表（H1）、§10 account 行（H2）、§3 目录树（H4）、§12 技能（M1） | ~半天 | agent 第一入口，每个会话都在读 |
| 2 | agent-reference.md：目录树 + 任务模式 + 技能 + 用户技能（H3/M1） | ~半天 | 与 AGENTS.md 同源的权威引用 |
| 3 | user 四件套：omni-integration（H5）、production-workflow（H6）、cli-reference（H8）、agent-troubleshooting（H7） | ~半天 | 面向用户的事实错误 |
| 4 | README：引擎安装段 + extras 表（H9）+ H0 枚举（L2） | ~1 小时 | faster-whisper 裸装建议与刚修的 bug 冲突 |
| 5 | 索引统一（M3）+ api-reference 补 5 个导出（M4）+ gate-failure-modes 补 CW（M2） | ~2 小时 | 结构性缺漏 |
| 6 | ADR-006 状态附录（M5）+ **RFC-001 裁决（M6，11-11 硬期限）** | ~1 小时 | RFC-001 有 CI 红线 |
| 7 | 尺寸刷新（L1）+ 三报告入库 + .gitignore 反排除（L3） | ~1 小时 | 收尾 |

---

## 附：逐文档判定总表

| 文档 | 判定 | 对应发现 |
|:--|:--|:--|
| AGENTS.md | **需更新** | H1、H2、H4、M1、L2 |
| README.md | **需更新** | H9、L2（H0 枚举）、L1 |
| docs/index.md | 建议更新 | M3、L1 |
| docs/doc-inventory.md | 新鲜 | 2026-10-29 刚再生成，标记合法 |
| docs/dev/agent-reference.md | **需更新** | H3、M1 |
| docs/dev/agent-troubleshooting.md | **需更新** | H7 |
| docs/dev/gate-failure-modes.md | 需更新 | M2（漏 CW） |
| docs/dev/deep-module-rfc-001.md | 需**裁决** | M6（90 天线） |
| docs/dev/plans/NIGHTLY.md | 轻微过期 | L4 |
| docs/dev/developer-guide.md | 基本新鲜 | 68/33/26 等断言均正确 |
| docs/dev/override-reference.md、cron-troubleshooting.md、api-gotchas.md、forward-compat.md、evaluation-matrix-principles.md | 未发现硬伤 | — |
| docs/user/cli-reference.md | **需更新** | H8 |
| docs/user/mcp-setup.md | 基本新鲜 | 68 工具、弃用别名、allowlist 均正确 |
| docs/user/api-reference.md | 需更新 | M4 |
| docs/user/omni-integration.md | **需更新** | H5 |
| docs/user/production-workflow.md | **需更新** | H6 |
| docs/user/hitl-framework.md | 基本新鲜 | review_decision 等与代码一致 |
| docs/user/asset-library.md、user-introduction.md、deployment.md、windows-deployment.md | 新鲜 | 未发现漂移 |
| docs/skills/（4 个） | 新鲜 | 工具参数示例核对无误 |
| docs/adr/ADR-001..005、ADR-007 | 新鲜 | — |
| docs/adr/ADR-006 | 建议加附录 | M5 |
| docs/glossary.md | 新鲜 | 26 节点/33 门正确 |
| CHANGELOG.md | 新鲜 | 1.12.0 = `_version.__version__` ✓ |
| founder-expectations、历次 dated 报告、docs/archived/* | 时点记录，不更新 | L5 |
| codebase-audit-20261022 / project-analysis-20261029 / AutoMedia-development-brief-v2 | 未入库问题 | L3 |

**一句话结论**：数字门禁把"计数型说谎"已结构性消灭，但"参数表、目录树、preset 组成、清单类声明"这四类结构性断言仍是手维护的——本次 9 项高优先级漂移全部来自这四类；优先修 AGENTS.md（半天工作量覆盖其中 4 项），并把参数表比对与目录树 diff 固化进 `check-doc-consistency.py`，同类漂移即可永久下线。
