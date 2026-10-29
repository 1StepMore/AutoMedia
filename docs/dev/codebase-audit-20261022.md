# AutoMedia 代码库审计报告 —— 架构 · 代码美学 · 信号诚实性

> **审计日期**：2026-10-22
> **审计对象**：AutoMedia `main` 分支（HEAD `5370cb1`）
> **审计方法**：全部结论基于**实跑命令或代码核对**，逐条标注证据（`文件:行号` / 实测输出）。本报告只给结论与证据，不含实现方案与排期；实施建议见 §九。
> **审计性质**：一次性快照，非持续门禁。
> **与既有文档的关系**：
> - `docs/dev/capability-gap-assessment-20260915.md` —— 能力缺口视角（面向交付）
> - `docs/dev/project-health-assessment-20260917.md` —— 工程健康度视角（面向可维护性与风险）
> - `docs/dev/remediation-report-20260917.md` —— 上两者的整改回执
> - `docs/dev/deep-module-rfc-001.md` —— 已落地的深模块重构提案（`pipelines/runner.py` 摩擦区扫描）
>
> 本报告是**架构 / 代码美学 / 信号诚实性**视角，复核既有报告结论并明确标注「**已知** / **新增**」（见 §八）。既有报告已覆盖的结论本文不重复论证，只补证据与增量。

---

## 一、结论摘要

**一句话结论：这是一个「工程纪律显著强于产品接线完整度」的项目——它的门禁体系在 2026-09 被诊断为未接线后，选择了「诚实地说 skipped」而不是「写假数据」，这个选择本身是对的，但它把问题从「会失败」变成了「永远不失败」，而所有对外的 headline 数字（33 道质量门、62,461 LOC、4,580 测试）都没有跟着调整。**

对一个以「质检流水线」为核心价值的产品，**信号不诚实是比缺功能更贵的缺陷**：它让下游（无论是人类还是 agent）误以为「这里已经验证过了」。

| 判断 | 结论 | 一句话依据 |
|:--|:--|:--|
| 静态卫生 | ✅ 优秀 | `ruff check .` 全绿；`mypy` 260 文件零问题；`src/` 内 0 个 TODO/FIXME/HACK |
| 测试**正确性** | ✅ 通过 | 实跑 `pytest`：**5,317 通过 / 2 跳过 / 0 失败**（见 §二） |
| 测试**信号强度** | ⚠️ 严重削弱 | 208 个 e2e 测试**在任何 CI 作业与任何 Make 目标下都不被收集**；`make test-e2e` 收集 0 个测试并 exit 0 |
| 文档**门禁** | ✅ 机制健全 | `scripts/check-doc-consistency.py` 实跑 exit 0：68 tools / 19 CLI / 149 scenarios 全部对得上 |
| 文档**数字** | ⚠️ 漂移 | README 的 LOC / 文件数 / 测试函数数三条数字全部过期；该门禁只覆盖 tool/command/scenario 计数，**LOC 类断言无门禁** |
| 门禁**接线** | ❌ 结构性缺口 | V0/V1/V3/V4/V6 的输入字段**全仓零生产者**（2026-09-17 已诊断，未修复）；V7 的 MD5 校验**构造性恒真** |
| 编排层**形状** | ⚠️ 方向反了 | `runner.py` 2,213 行 / 34 函数 / 23 个参数 / 53 个 lazy import —— 是「深坑」而非「深模块」 |
| 领域层**形状** | ✅ 大体优秀 | `prompts/`（104 行接口 → 4,573 行模板）、`engines/`、`accounts/`、`asset_library/` 是教科书级深模块 |
| **可复现性** | ⚠️ 局部不可复现 | `resume_from` 只切门列表、不回灌状态，用占位符替代真实草稿 |

**最危险的状态不是「有缺陷」，而是「静默地看起来能用」**——这个判断与 2026-09-17 健康度报告的 P0-1 结论一致，但**根因已经变了**：那时是「门会失败」，现在是「门不会失败」。

---

## 二、实测度量事实

以下数据均为本次审计实跑所得，非引用既有文档。

| 指标 | 实测值 | 采集方式 |
|:--|:--|:--|
| 核心源码 | **67,997 行 / 261 个 `.py`**（`src/automedia/`） | `find src/automedia -name '*.py'` |
| 全仓源码（排 `.venv/.git/build/dist/pkg`） | **596 文件 / 166,011 行** | 同上 |
| 门禁 | **33 个已注册 gate / 43 文件 / 13,667 行** | `gates/` 目录统计 |
| MCP 工具 | **68** | `grep -c "^    mcp.tool(" src/automedia/mcp/server.py` |
| CLI 命令 | **19** | `scripts/check-doc-consistency.py` 派生计数 |
| 场景库 | **149** | `find scenarios -name '*.yaml'` |
| 测试函数 / 文件 | **5,218 / 289** | `grep -rhE '^\s*(async )?def test_' tests/` |
| **测试实跑** | **5,317 通过 / 2 跳过 / 0 失败 / 0 报错** | `pytest -q --tb=line`（100% 进度已确认） |
| 静态检查 | `ruff check .` → **All checks passed**；`mypy src/automedia/` → **no issues found in 260 source files** | 实跑 |
| 文档门禁 | **exit 0，全绿**（68 tools / 19 CLI / 149 scenarios 对齐） | `python scripts/check-doc-consistency.py` |
| 模块级 import 环 | **1**（`engines.implementations` 自指，`__init__` 内部引用） | AST 分析 |
| `src/` 内 TODO/FIXME/HACK | **0** | grep |
| 密钥泄露 | **无**（`.env` / `*_credentials.*` / `*.zip` 均未入库） | `git ls-files` 核验 |

> **测试耗时注记**：完整套件实跑约 **25 分钟**（5,319 个用例）。`pre-commit` 的 pytest 钩子为 `python3 -m pytest tests/ -x -q`（`pass_filenames: false`），即**每次提交都跑全量**。这是反馈回路成本的实测基线。

---

## 三、这个项目在做什么：概念模型

AutoMedia 不是「AI 写稿工具」，而是**把内容生产的验收标准编译成可执行门禁（gate）的生产流水线**。它的核心资产不是生成能力，而是**判定能力**——33 道 gate 把「什么叫合格内容」写成代码，再用 9 种 mode 把它们编排成不同形态的产线。

```
选题(pre-gate) → 写稿(CW) → 改稿(G0-G3,G6) → 媒体(V0-V7) → 人审(H0)
                                                            ↓
                                    生命周期(L1-L4) ← 分发(D1-D7) / 复用(P1-P4)
```

三个入口（SDK / CLI / MCP）**全部收敛到同一个 `run_full_pipeline()`**——这是本项目在架构上做得最对的一件事，没有分叉，没有各自的实现。

**「氛围编程」（vibe coding）视角的隐含命题**：这个仓库里，AI agent 是主要消费者。agent 读 exit code、读 gate report、读配置、读目录结构、读文档数字，然后据此做决策。因此本项目的「美学」标准不只是行数或优雅，而是——

> **这份代码对人（人或 agent）呈现的信号，可信吗？**

本报告 §六 的绝大多数缺陷，都可以用这句话统一描述。

---

## 四、设计理念：宣言 vs 落地

项目自己写了方法论（`docs/dev/七阶段AI开发流程-用CodingAgent交付成品的方法论.md`）。把它和代码逐条对照：

| 宣言（原文摘录） | 落地情况 | 证据 |
|:--|:--|:--|
| **"Own Your Process"** —— 把任何 coding agent 包进一套可控流程，而不是依赖某个特定框架 | ✅ **真做到了** | 无内置 scheduler；外部 crond 调 `automedia cron run --due`；`cron/schedule.py` 手写 5 字段 cron 求值器，**刻意不依赖 `croniter`** |
| **"Deep Modules：小接口 + 大实现"** | ⚠️ **一半** | ✅ `prompts/`(104→4,573 行)、`engines/`、`accounts/`、`asset_library/`；❌ `runner.py` 是「大实现 + 大接口」，见 §五 |
| **"AX 优先：UX 可以后续优化，AX 必须起步就设计"** | ⚠️ **文档层优秀，运行层失守** | ✅ AGENTS.md 作为唯一地图、llms.txt 索引、门禁自动注册；❌ e2e 从不运行、V 门永不生效 |
| 诚实标记分歧 | ✅ **少见的好品味** | `AdapterRegistry.is_stub` **默认 `True`**；HITL `on_timeout` **默认 reject**（fail-closed）；`detectors/adapters.py` 宁可 `raise` 也不编造 |
| 三入口同源 | ✅ | `run_full_pipeline` 单一实现，21 处调用点 |
| 六层配置合并 | ✅ 实现完整 | `config_loader.py:325` 六层 + 显式 `overrides=` + env-over-dotenv 优先级 |

**最值得保护的设计**：`missing_input_result()` —— 门的输入不存在时，它**明确报告 `skipped` 而不是 `pass`**。这是整个仓库里最有价值的一个契约，2026-09 的整改正是把它做成了「一等状态」。

**问题不在这个契约，而在它没有被聚合**：项目有成熟的 `declared → preset-reachable → command-reachable → scenario-covered` 四分法（`validation/coverage.py:136`），**唯独缺「输入可达性」这一维**，而运行时其实已经采集到了（`GateContext.was_written(key)` 就是 `missing_input_result` 的底层依据）。

---

## 五、基础设施地图：深模块与浅模块

### 5.1 真正深的模块（小接口 / 大实现）

| 模块 | 公开接口 | 隐藏实现 | 评价 |
|:--|:--|:--|:--|
| `prompts/` | 1 个 `load_prompt()`（**104 行**） | 64 个 `.j2` / **4,573 行** / 4 层覆盖链 | **全项目最佳**，接口宽:实现量 ≈ 1:44，且与 `core/overrides.py` 语义对称 |
| `engines/` | 4 个 ABC + `resolve_engine()` | 2,183 行 / 4 个具体引擎 | 教科书级；`check_available()/run()` 两个方法藏住 subprocess 与 HTTP |
| `accounts/` | `AccountStore` / `AuthFlowEngine` | 1,632 行，AES-256-GCM + OAuth2 + 会话刷新 | 全仓最深的凭据层 |
| `asset_library/` | 1 个 `search()` | SQLite + Chroma + 混合排序 | 一次调用藏两个存储 + 一次 merge |
| `adapters/base.py` | 1 个抽象 `publish()` | 5 个默认方法 + 20 个平台 | 接口收得极紧；`AutomationLevel` 覆盖 20 个平台默认值 |
| `cron/schedule.py` | 5 字段 cron 求值 | 零依赖手写 | 有意且正确的取舍 |

### 5.2 薄 / 空转 / 过度切分的模块

| 模块 | 规模 | 问题 |
|:--|:--|:--|
| `features/` | 256 行 / 1 文件 | 自己的 docstring 承认：**「This module is a MARKER: it never blocks execution itself… Enforcement call sites are added separately (plan todo 17)」** → 当前是**零调用点的死重量** |
| `decision/` | 6 文件 / 308 行 | 名为「决策层」，实为 1 个 dataclass + 2 个几乎相同的日志器（`audit.py` vs `review_audit.py` 只差文件名与载荷）。**无任何决策引擎** |
| `hitl/executor.py` | 内存 `dict` | 名为 executor，实为 `self._pending: dict[str, Any]`，**进程重启即丢**，不构成持久化层 |
| `omni/base.py` | **18 行** | 一个 `name` property + `validate_env()`，抽象近乎空转 |
| `detectors/adapters.py` | 61 行 | 有 API key 也**从不发起网络请求**，永远 raise |
| `manifests/` | 731 行 | 命名误导——README 称其为「内置 YAML defaults」，实际是 schema 代码，`defaults.yaml` 在别处 |

### 5.3 过大的模块（「深坑」而非深模块）

```
runner.py            2,213 行   34 函数   53 个函数内 lazy import   23 个参数(2 位置 + 21 关键字)
gate_engine.py       1,773 行   _run() 单函数约 520 行
llm_client.py        1,335 行   25+ 私有函数 + global 可变状态
mcp/server.py        1,288 行   68 个手写 mcp.tool(...) 注册
gates/humanizer.py     966 行
gates/fact_check.py    880 行
```

**Ousterhout 意义上这不是深模块**：深模块的前提是「复杂度被接口吸收」。`runner.py` 是「大实现 + 大接口」——23 个参数意味着接口没有变小，只是把变化点堆进了一个文件。它是 god object 的现代变体，而非 deep module。

### 5.4 门禁家族的形状

- **33 个 gate 一类一文件**，共享 `BaseGate` + `_result.build_gate_result` + `missing_input_result` + `helpers.apply_mock_overrides` + `llm_helpers.llm_check_with_fallback` ——**共享基建是到位的**。
- **D1–D7 是同构家族**（非字面复制）：7/7 全部具备 `content_present` → 构造 prompt → `llm_complete` → 输出长度质检 → 存 context → `os.makedirs`+写盘 → 组装结果 六阶段，仅 prompt 文本与长度阈值不同；单文件 265–419 行，合计约 2,300 行。
- **P1–P4 是同一 3 步骨架 ×4**。
- **AST 级字面复制很少**：全仓 ≥8 行的私有函数中仅 1 组完全相同（`_split_into_tweets`：`gates/distribution/d2_twitter.py` == `gates/sub_pipelines/p2_twitter.py`）；`_check_rewrite_quality`(P1/P3)、`_check_no_markdown`+`_MARKDOWN_PATTERNS`(G4/G5)、`_derive_expected`(3 处)、`_build_llm_checks`(G2/G6) 属同类近重复。

---

## 六、缺陷与风险（按严重度）

### P0-1　「33 道质量门」里，5 道永远不执行，1 道的校验构造性恒真

**事实**：V0/V1/V3/V4/V6 读取的 `gate_context` 字段在**全仓 `src/` 内零生产者**。实测（`grep -rnE "\[\"$k\"\] *=" src/automedia/`）：

| Gate | 声明所需输入 | 全仓写入点 | 门内自述 |
|:--|:--|:--|:--|
| V0 `lint` | `lint_result` | **0** | `gates/lint.py:109`：「`lint_result` is produced by the video pipeline」 |
| V1 `vision_qa` | `entries` / `qa_passed` | **0** | `gates/vision_qa.py:131`：「`qa_passed`: bool (result of vision QA)」 |
| V3 `content_semantic` | `source_keywords` / `content_keywords` | **0** | `gates/content_semantic.py:135`：「from 3 source documents」 |
| V4 `tts_brand_asset` | `voice_id` / `segments` | **0** | `gates/tts_brand_asset.py:134`：「`voice_id` + `segments` are produced by the TTS stage」 |
| V6 `subtitle_render` | `avg_brightness` / `contrast` / `pixel_valid` | **0** | `gates/subtitle_render.py:107`：「average pixel brightness in subtitle region」 |
| V2 `pre_send_whisper` | `expected_md5` | **0** | MD5 检查恒自跳过 |
| V7 `six_step_hard` | `expected_format` / `expected_duration_s` | **0** | 这两项检查恒 skip |

**门内注释指名了生产者，而生产者不存在。** 这是「幽灵生产者」——比「还没写」更坏，因为它在代码里看起来是接好的。

**V7 的 MD5 校验是构造性恒真**（`src/automedia/pipelines/runner.py:2178-2181`）：

```python
gate_context["md5_records"] = {
    path: {"expected": _compute_md5(path), "actual": _compute_md5(path)}
    for path in required_files
}
```

`expected` 与 `actual` 是**同一次计算**的两个返回值，永远相等。该检查在真实流水线中**不可能失败**。

**归属**：本项在 `docs/dev/project-health-assessment-20260917.md` §P0-1 与 `docs/dev/remediation-report-20260917.md` 已诊断并整改（第一批，✅ 完成）。整改内容是**让 V 门在输入缺失时返回 `status="skipped"`**——即「显性化」。整改回执同时写明：

> V0 / V1 / V3 / V4 / V6 … ⛔ **仍为 `skipped`**——仓库内没有能诚实产出它们的实现…**刻意不写假数据**

**「刻意不写假数据」是好品味，本报告完全赞同。但整改的净效果是把问题从「会失败」变成了「永远不失败」，而对外的 headline 数字没有跟着调整**（§六 P4-2）。这是本次审计的核心判断：**整改修的是症状（症状的可见性），没修供给链（问题的成因）。**

**附带的正面证据**：`runner.py:1531` 的注释写明 `_produce_media_assets` 是「P0-1 wiring」的一部分——媒体产出的**时序**确实被修好了（此前 `video_path` 只在 `_finalize_pipeline` 写，所有门跑完才有）。但**时序 ≠ 供给**：产出的是文件，V 门要的是 `avg_brightness`/`voice_id`/`lint_result` 这类**测量值**，二者不是一回事。

---

### P0-2　208 个 e2e 测试在**任何** CI 作业与**任何** Make 目标下都不被收集；`make test-e2e` 收集 0 个测试并 exit 0

**事实链**：

1. `pyproject.toml` 的 `[tool.pytest.ini_options] addopts` 含 `-m 'not e2e'`（全局默认）。
2. `grep -rn "e2e" .github/workflows/` → **零命中**：CI 与 nightly 均未覆盖该标记。
3. 实测：

```
$ pytest tests/test_e2e/ --collect-only
no tests collected (208 deselected) in 16.89s      ← EXIT 0

$ pytest tests/test_e2e/ --collect-only -o addopts=""
208 tests collected in 17.08s
```

4. `Makefile` 的 `test-e2e` 目标即 `python -m pytest tests/test_e2e/ -v` → **收集 0 个测试、退出码 0**。

**这是「静默通过」的最纯粹形态**：命令成功、CI 绿、实际什么都没跑。

**归属**：2026-09-17 健康度报告 §209 **已注意到**该排除（「e2e 标记的 211 个测试默认被 `addopts` 排除，本次未启用」），但**未识别出 `make test-e2e` 是空转**，也**未修复**。本报告的新增贡献是这条**可执行的因果链**。

**讽刺之处**：本仓库的 commit 历史里，`nightly.yml:96-101` 有一段明确的自省注释：

> Run even if an earlier step failed… **the job still goes red overall when a scan fails, so security remains blocking for the workflow. Issue #130.**
>
> （背景：#91 事故的根因正是「这种沉默」）

同一个沉默，换了个地方又出现了。

---

### P0-3　`resume_from` 只切门列表、不回灌状态，用占位符替代真实草稿

**事实**（`src/automedia/pipelines/runner.py`）：

- `_select_gates`（:1302-1309）执行 `gate_names = gate_names[idx:]` —— **仅此而已**。
- `_build_pipeline_context`（:1494-1498）：

```python
if "CW" not in gate_names and not gate_context.get("content", "").strip():
    placeholder = f"[content skipped in {mode} mode]"
    gate_context["content"] = placeholder
    gate_context["draft"] = placeholder
```

  `resume_from="G0"` 时 `CW` 已不在列表内 → 上下文被填入占位符字符串。
- **全流程没有任何一处从 `01_content/drafts/` 回读草稿重建 `GateContext`**（`_build_pipeline_context` 不读盘）。
- `_verify_resume_integrity`（:301-347）只 `log.warning`，**不阻断、不修复**；且其索引基于 `_MODE_MAP[mode]` 而非实际生效的门列表。
- `resume_project_id` 亦**不**自动续跑——它从 `pre-gate` 全量重跑。

**净效果**：`resume_from="G0"` 会让 G0 及其后的门**对着 `"[content skipped in auto mode]"` 这串字符做事实核查、人类化、CTA 校验**。它不报错，它产出垃圾。

**归属**：**新增**（三份既有报告均未提及 `resume_from`）。这是比崩溃更贵的一类缺陷——半实现的 resume 是负资产。

---

### P0-4　`defaults.yaml` 里 3 个配置项从未被读取

**事实**：`src/automedia/manifests/defaults.yaml` 声明 `gate_engine.max_retries` / `retry_delay` / `max_regenerations`，但 `runner.py:1527-1535` 构造引擎时**一个都没传**：

```python
engine = GateEngine(
    gates,
    hooks=all_hooks,
    pause_on_approval=director,
    media_stage=_produce_media_assets,
    wait_for_hitl=wait_for_hitl,
)
```

只有 `hitl_timeout_s` / `hitl_on_timeout` 经 `hitl_config` 生效。

同类问题还有两处：

- **`workflow.prompts` 被 set 后立刻 pop**（`runner.py:806` set，:1211 pop），从未被读取——workflow 的 prompt 覆盖实际不生效（真正生效的是 `OverridesLoader.load_prompts` → `load_prompt`）。
- **`_collect_platform_gate_modifiers` 对当前 `BrandProfile.platforms: list[str]` 恒返回 `None`**（`runner.py:640-644`），配套的 `_filter_gates_for_platform`（:693-763）**是死代码**——README 宣称的「Platform-aware customization」在当前 schema 下不生效。

**归属**：**新增**。

**为什么这条是 P0 而非 P3**：写了但不生效的配置，比没有这个配置**更坏**——它让读者（尤其是 agent）建立错误心智模型，并据此做出「我已经调过 retries 了」的判断。

---

### P1-1　同一事实被存 3–4 份，每份都是未来的不一致源

| 事实 | 副本数 | 位置 | 实测 |
|:--|:--|:--|:--|
| **门执行顺序** | 3 | `_MODE_MAP`（runner.py:159，**权威**）· `AUTO_GATE_DAG`（dag.py:30，26 节点）· `GateRegistry` | DAG **不参与执行**：`topological_order()` 仅被 `cli/commands/pipeline.py:249` 的 export 使用 |
| **failure_mode** | 3 | gate 类 `_failure_mode` ClassVar · DAG 节点字段 · `gates/failure_modes.py`（**该文件根本没有 failure_mode 字段**，只是 662 行叙事文档） | 当前 0 处冲突，但无运行时校验 |
| **平台清单** | 3 | `runner._PLATFORM_CATEGORIES`（21）· `media_spec.PLATFORM_MEDIA_SPECS`（19）· `adapters/registry`（20，含 8 个 stub） | 数量互不相同 |
| **MD5 计算** | 4 | `hooks/md5_tracker.py:21` · `omni/md5_integration.py:33` · `gates/pre_send_whisper.py:76`（内联）· `asset_library/ingest.py:304` | — |
| **目录布局** | 0（无单一源） | 见 P1-2 | — |

**DAG 的性质需要澄清**：`dag.py` 的注释称其「byte-exact 复现 `_MODE_MAP`」——这是对的，但方式近乎同义反复。实测 `topological_order(AUTO_GATE_DAG, _MODE_MAP[m]) == _MODE_MAP[m]` 对全部 9 个 mode 成立，因为算法在「父节点已在子集内」时按输入顺序发射，**它是个恒等映射**。DAG 的真实用途只有三处：CLI `export-dag`、`_compute_affected_downstream` 的下游定位、`state_view` 的轨道元数据。**它是装饰性的**（`docs/dev/agent-reference.md` 称其为「canonical」）。

更值得警惕的是，**这个「装饰性」已经被当作事实对外输出**：`cli/commands/pipeline.py:62` 打印的标题是

> `Gate execution order (canonical, from `AUTO_GATE_DAG` via `topological_order`).`

而 `automedia pipeline export-dag` 的产物正是用户与 agent 用来理解「门为什么按这个顺序跑」的唯一文档。**它标注了错误的权威来源**——排布真在 `_MODE_MAP`（`runner.py:159`），而 DAG 是从它派生的。二者今天碰巧一致，但没有任何机制保证明天仍一致。

**归属**：DAG 装饰性 = **新增**。

---

### P1-2　目录布局没有单一真相源；`05_publish` 与 `06_publish` 语义撞号

`core/project.py` 的 `Project.init()` 只创建 **6 个**目录：

```
01_content/drafts   02_images/cover   03_video   04_subtitle   05_review   06_publish
```

但代码实际写入的位置有 **13 个**：

| 实际路径 | 是否被创建 | 写入方 |
|:--|:--:|:--|
| `04_audio/` | ❌ | `runner.py:2109` |
| `04_distribution/<platform>/` | ❌ | D1–D7（7 处） |
| `04_repurpose/` | ❌ | P 门 |
| `02_images/body`、`02_images/fallback` | ❌ | image pipeline |
| `research_data/` | ❌ | OPP（`omni/artifact_mapping.py`） |
| **`05_publish/{lang}/`** | ❌ | Omni 翻译层（`omni/artifact_mapping.py:12`） |

**`05_publish` 是最刺眼的一处**：`omni/artifact_mapping.py:12` 明文规定「**05_publish/{lang}/**: OL translation output」，而发布日志（`gates/publish_log_wiring.py:25`）、cron、asset_library 全部使用 `06_publish/`。同一个「发布」概念，两个编号，且 `05_` 已被 `05_review` 占用。**目录编号是接口的一部分**——agent、用户脚本、`asset_library/ingest.py:269` 的阶段权重表都在依赖它。

**归属**：**新增**。

---

### P2-1　GateHook 的「只读观察者」契约 — 六项中两项已修复，一项描述有误

`AGENTS.md` §4 称 GateHook 为「readonly observers; never mutate or skip gates」。
**核实日期 2026-10-24**：下表按当前代码重新判定（原审计的六条中，前两条已由 #294 修掉，
第三条的描述与当时的代码不符，真正剩下的三项已在本轮处理）。

| 违反点（原始声明） | 当前实测 | 处置 |
|:--|:--|:--|
| hook 收到的是浅拷贝 | ✅ **已修复**。#294 引入 `_detached()` 递归深拷贝（list/dict/tuple/set 全部脱钩）。实测 hook 侧追加 list 元素、改嵌套 dict，原 context 均不变 | 文档更新 |
| hook 抛异常会中断流水线 | ✅ **已修复**。`_dispatch_before/_after/_failed` 三处均 `try/except` + `warning` 日志 | 文档更新 |
| `after_gate` 不代表「成功」 | ⚠️ **原描述有误**。当时的代码在 `fm == "stop"` 且 `passed=False` 时**会**派发 `after_gate`（不是"既不派发也不…"）。真正的缺陷是 docstring 写「completes successfully」，与"门判定失败也走这里"矛盾 | 已改 docstring，明确 `after_gate`=「产出裁决」，`on_gate_failed`=「抛异常」 |
| `run_sub_pipeline` 完全不派发 | ✅ **属实，且更严重**：不仅零派发，还**零调用点、零测试**，231 行死代码 | 已删除 |
| `MetricsHook` 从未接入 | ✅ **属实**。产物与 `05_review/gate-report/` 字段完全重复，且 gate-report 被 MCP `get_gate_report` 读取，`production_metrics.json` **无人读** | 已删除（含 116 行实现 + 50 处测试） |
| `md5_tracker` 根本不是 hook | ✅ **属实**。它是 `core.hashing.compute_md5` 的上层读写封装，被 runner/gates 直接调用 | 已移至 `core/md5_tracker.py` |

**唯一始终正确的部分**：hook 不控制流程。本轮修完后，隔离性、异常安全、语义一致性、
目录归类四项也都守住了。

#### 补充发现：DAG 的「等价性」是同义的，且 28 条边只有 1 条承载数据

审计未涉及。实测（2026-10-24）：

**D-1. 28 条依赖边中只有 1 条有真实数据流。**
静态交叉比对「父门写入的 context key」与「子门读取的 context key」，唯一交集是 `CW→G0`。
其余 27 条（含 `G6 depends_on G5`）是**顺序断言**，不是数据依赖。
因此 `AUTO_GATE_DAG` 应被理解为「执行顺序图」，而非「数据依赖图」——两者的失效模式不同：
删掉一条真数据边会让门读到空值，删掉一条顺序边只会改变执行次序。

**D-2. `topological_order` 的等价性测试是同义的。**
1800 次随机打乱实验（9 modes × 200）：
- 输出**永远**是合法拓扑序（0 次违反依赖约束）
- 但只有 203/1800 等于 `MODE_GATE_NAMES`——因为 tie-break 用的是**输入顺序**

后果举例：`text_with_cover` 输入乱序时会输出 `['G6','CW','G0',...]`。`G6` 的父节点 `G5`
不在任何 preset，被 present-parents 语义忽略，于是 `G6` 立刻"就绪"。**合法但语义荒谬**：
G6 检查的是 CW 产出的内容。已在 `dag.topological_order` 改为**声明顺序 tie-break**，
并添加 `test_g6_never_precedes_cw` 回归锁。

**D-3. 6 条边指向「不在任何 preset」的门 — 已修复。**
原状：`G5→G4`、`G6→G5`、`L2→L1`、`L3→L2`、`L4→L3`、`P1→L4`。

拆成两类后处理不同：

| 边 | 判定 | 处置 |
|:--|:--|:--|
| `G6→G5` | 子门在 preset、父门不在 → **声称永不发生的先后** | 改指 `G3`（copy 轨最后一个真正会跑的门） |
| `P1→L4` | 同上（P1 在 repurpose 跑，L4 只在 `localize` 命令跑） | 改指 `H0`（两条流程真正的交汇点） |
| `G5→G4`、`L2→L1`、`L3→L2`、`L4→L3` | 两端都不在 preset → **命令路径内仍成立** | 保留 |

选择「删边」而非「补 preset」，依据是 D-1：28 条边只有 1 条有真实数据流，
说明这个 DAG 一直是**顺序声明**而非数据依赖，`G6→G5` 更可能是历史残留而非设计。
新增 `TestEdgesMustBeSatisfiable` 守卫：任何「preset 门依赖非 preset 门」的边直接失败。
验证：9 个 mode 的执行顺序**完全未变**，`downstream()` 不再返回永不发生的门。

**D-4. `downstream()` 对外结果包含永不发生的门 — 已修复（随 D-3）。**
原状：`downstream(G4)` 返回 `['G5','G6','H0','L1',...,'P4']`，但 G4/G5/L1-L4 没有 preset 跑，
大半个「下游」永不发生。

修完 D-3 的两条矛盾边后：
- `downstream(G4)` = `['G5']` —— 只剩命令路径内真实的继任者
- `downstream(L1)` = `['L2','L3','L4']` —— 同上
- `downstream(L4)` = `[]` —— 生命周期链的终点不再虚报 P 系列

`_compute_affected_downstream` 的 `intersect with mode gates` 保持原样（它本来就正确）。

---

### P2-2　RFC-001 挂了 70 天「Proposed」，而它要治理的摩擦区反而长了 36%

**事实**：

| 时点 | `runner.py` 行数 | RFC-001 状态 |
|:--|:--|:--|
| 2026-08-13（RFC-001 提交，`e529de2`） | **1,617** | Proposed |
| 2026-10-22（本次审计） | **2,213** | **仍是 Proposed** |

`docs/dev/deep-module-rfc-001.md` 的 git 历史只有 3 个 commit（2 次新增 + 1 次无关的版本号断言），**从未被更新，也从未被关闭**。RFC 正文里记录的形态已经全部过期：

| RFC-001 记录（2026-08-13） | 实测（2026-10-22） | 变化 |
|:--|:--|:--|
| `runner.py` 1,617 行 | 2,213 行 | **+36.8%** |
| 23 个函数 | 34 个函数 | +11 |
| 13 个函数内 lazy import | 53 个 | **×4** |
| 47 个 `run_full_pipeline` 调用方 | 46 个（非测试）/ 21 处（`src/` 内） | 基本未变 |

**RFC 中并列扫描的其它候选同样原地未动**：

| RFC-001 候选 | RFC 记录 | 实测 | 结论 |
|:--|:--|:--|:--|
| `core/config_loader.py` | 266 行 | **411 行**（+54%） | 摩擦区同样变大 |
| `adapters/registry.py` | 89 行 | 90 行 | 未变（RFC 判断「小而浅但不构成摩擦」——**这个判断是对的**） |

**这不是「重构没做」这么简单**——是**摩擦区在等待期间变大了**。RFC-001 记录的形态已经全部过期。

**归属**：**新增**。这一条同时暴露了方法论执行层的缺口：项目有完整的「诊断 → RFC → Issue → 单次可验证提交」流水线（ADR-005），但**流水线上没有「RFC 老化」的检查点**。RFC 停在 `Proposed` 是零成本状态，因此它被零成本地遗忘了 70 天——而摩擦区不需要你批准就会自己长大。

---

### P3-1　门禁家族同构：7 个 D 门 × 6 阶段 + 4 个 P 门 × 3 步

见 §5.4。合计约 2,300 行 D 门 + P 门骨架。差异只在 prompt 文本与阈值——**7 个平台的行为无法被「比较」，只能被「人肉 diff」**。

**归属**：D/P 同构为**新增**；AST 级字面复制（仅 1 组）在此**修正**了「模板 ×7 = 复制粘贴」的通俗说法——它是**同构**，不是**复制**。

---

### P4-1　ADR-006 / ADR-007 存在但不在 mkdocs nav，站点上不可见

`docs/adr/` 下有 7 篇 ADR，`mkdocs.yml` 的 nav 只列到 ADR-005。ADR-006（Graph Engineering DAG）与 ADR-007（Gate Engine Verdict Aggregate）——**恰好是本次审计中两个最关键的架构决策**——在文档站上不可达。

**归属**：**新增**。

---

### P4-2　README 的三条数字全部漂移，而文档门禁只覆盖计数类断言

| 文档声明 | 实测 | 偏差 |
|:--|:--|:--|
| `README.md:16` / `docs/index.md:16`：**62,461 LOC (core)** | 67,997 | **−8.1%** |
| `README.md:16`：**737+ Python files** | 无任何计数规则能得 737（排 build/dist 为 596，含 build/dist 为 799） | 无法复现 |
| `README.md:16`：**4,580 test functions across 247 files** | 5,218 / 289 | 双双过期 |
| `README.md:709`：**~183,000+ LOC across 737+ files** | 166,011（排 build/dist） | — |
| `AGENTS.md:8`：**67,750 LOC / 261 files** | 67,997 / 261 | LOC 差 247，文件数准 |
| `AGENTS.md:8`：**163,015 LOC / 589 files** | 166,011 / 596 | 轻微过期 |

**根因不是没维护，而是门禁的覆盖面太窄**：`scripts/check-doc-consistency.py` 只校验 **MCP 工具数 / CLI 命令数 / 场景数**三类断言（实跑 exit 0，68/19/149 全对齐），**LOC、文件数、测试函数数没有任何断言**。这三类数字恰恰是最容易被写死、也最容易被自动生成的。

**归属**：README 数字漂移为**新增**；「门禁覆盖面偏窄」为**新增**（既有报告称「文档准不准 ✅ 准」，其结论对**被校验的那三类数字**成立）。

---

### P5-1　工作区卫生：仓库根目录堆积 ~103 个测试项目目录

根目录存在 `20260915_test/` … `20261022_integration-test-topic/` 等 **~103 个**测试运行产物目录，另有 `.coverage` / `.hypothesis` / `build` / `dist` / `site` / `logs` / `automedia-package` / `automedia-infrastructure-20260707.zip`。

**好消息**：**全部未被 git 跟踪**（`git ls-files` 实测 0 命中），`.gitignore` 覆盖良好。

**坏消息**：它们物理存在，**agent 的每一次 `ls` / glob / 搜索都要穿过它们**——这是纯粹的 AX 税；且 `20261022_test-topic` 这类命名会污染任何「按日期找项目」的启发式。

**归属**：**新增**。

---

## 七、代码美学与「氛围编程」视角的总评

把代码美学拆成三件事——**信息只有一份、接口隐藏复杂度、信号不说谎**——那么：

**1. 它误解了「深模块」的方向。**
Ousterhout 的深模块是「小接口 + 大实现」，前提是**复杂度被接口吸收**。`prompts/` 是范本（1 个函数藏 4,573 行模板 + 4 层覆盖链）；`runner.py` 是反例（23 个参数 + 53 个 lazy import + 10 份门序字面量，只是把变化堆进了一个文件）。前者让 agent 「记住接口」，后者逼 agent 「记住实现地图」——**这正是本项目方法论 §3.1 想解决的问题，却在自己最核心的编排层上重犯**。

**2. 它把诚实用在了函数级，没用在系统级。**
`missing_input_result` 是个漂亮的设计——单个门知道自己没输入时敢说 `skipped`。但系统层面没有把这件事聚合：报告仍以「33 gates」为标题；`make test-e2e` 仍 exit 0；V7 的 MD5 仍恒真。**局部诚实 + 全局幻觉，比全局不诚实更难发现**——因为前者看起来是设计，后者看起来是疏忽。

**3. 「氛围编程」的第一性原理不是「代码短」，是「agent 能在一个会话内建立正确心智模型」。**
按这个标准，本项目最大的债务不是 2,213 行的 `runner.py`，而是这六条：

| 假信号 | 后果 |
|:--|:--|
| `lint_result` / `voice_id` / `avg_brightness` 等字段「存在」但零生产者 | agent 以为视频轨已被质检 |
| `make test-e2e` exit 0 | agent 以为 e2e 已覆盖 |
| V7 MD5 恒真 | agent 以为产物已校验完整性 |
| `max_retries` 等 3 个配置项「存在」但不生效 | agent 以为已调过重试策略 |
| `resume_from` 静默注入占位符 | agent 以为已从断点续跑 |
| README 的 LOC / 测试数过期 | agent 以为自己读到了当前的规模 |

这六条的共同点是：**它们都会让消费者得出「这里已经验证过了」的结论。** 在 vibe coding 里，agent 是这些信号的主要消费者，它读 exit code、读报告、读配置、读目录。**假信号的成本不是一次调试，而是一整条错误的推理链**——这正是 2026-09-17 报告那句「最危险的状态不是『有缺陷』，而是『静默地看起来能用』」在新语境下的重述。

**4. 品味最好的地方，恰恰是最容易被顺手抹掉的地方。**
`is_stub` 默认 `True`、HITL 超时默认 `reject`、detector 宁可 raise 不编造、「刻意不写假数据」、「外部调度」不做自建 scheduler——这些不是功能，是**判断力的沉淀**。任何一次「大扫除式重构」最容易抹掉的，就是这些看起来「多余」的防御性代码。

---

## 八、与既有报告的交叉核对

### 8.1 已知（2026-09 已诊断，本报告仅补证据）

| 结论 | 首见 | 本报告补充 |
|:--|:--|:--|
| V0–V7 输入字段全仓零生产者 | `project-health-assessment-20260917.md` §P0-1 | 补齐 V0/V1/V2/V3/V4/V6/V7 **逐门**的输入清单与「幽灵生产者」注释位置 |
| 整改选择「显性化为 skipped」而非写假数据 | `remediation-report-20260917.md` 第一批 ✅完成 | 指出该整改的**净效果**是「永不失败」，且 headline 数字未随之调整 |
| L1–L4 产物无生产者 → 移出文本预设 | `capability-gap-assessment-20260915.md` P0-1 | 复核实测一致（`publish_log` 现已由 `gates/publish_log_wiring.py` 补齐） |
| G4/G5 注册但不可达 | 同上 | 复核实测一致；`validation/coverage.py:136` 已把「不可达」做成一等概念 |
| e2e 被 `addopts` 默认排除 | `project-health-assessment-20260917.md` §209（作为「本次未启用」的注记） | **新增因果链**：CI 零覆盖 + `make test-e2e` 空转 exit 0 |

### 8.2 新增（既有报告未覆盖）

| # | 结论 | 严重度 |
|:--|:--|:--|
| 1 | `make test-e2e` 收集 0 个测试并 exit 0；CI 无任何 e2e 作业 | P0-2 |
| 2 | `resume_from` 用占位符替代真实草稿，全流程无回灌 | P0-3 |
| 3 | `gate_engine.max_retries` / `retry_delay` / `max_regenerations` 从未被读取 | P0-4 |
| 4 | `workflow.prompts` 被 set 后 pop；platform gate modifiers 恒为 `None` + 死代码 | P0-4 |
| 5 | V7 的 MD5 校验构造性恒真（`runner.py:2178-2181`） | P0-1 |
| 6 | V2 的 `expected_md5` 全仓零生产者 | P0-1 |
| 7 | stop 门失败时 hook 完全不派发；retry 耗尽却派发 `passed=False` | P2-1 |
| 8 | `GateContext.to_dict()` 浅拷贝 → hook 可改活上下文 | P2-1 |
| 9 | hook 抛异常中断流水线；`run_sub_pipeline` 零派发 | P2-1 |
| 10 | `MetricsHook` 实现完整、有测试，但从未接入 | P2-1 |
| 11 | `05_publish`（Omni）与 `06_publish`（发布日志）语义撞号 | P1-2 |
| 12 | 13 个实际写盘位置中 6 个不在 `Project.init()` 的目录清单内 | P1-2 |
| 13 | `AUTO_GATE_DAG` 不参与执行，`topological_order` 对 9 个 mode 均为恒等映射 | P1-1 |
| 14 | `failure_mode` 存在 3 份副本，`failure_modes.py` 内无该字段 | P1-1 |
| 15 | MD5 计算 4 份实现；平台清单 3 份 | P1-1 |
| 16 | README 的 LOC / 文件数 / 测试函数数三条过期；文档门禁不覆盖此类断言 | P4-2 |
| 17 | ADR-006 / ADR-007 不在 mkdocs nav | P4-1 |
| 18 | `failure_modes.py` 中 D3/D5 的 `docstring_ref` 指向不存在的路径 | P1-1 |
| 19 | 根目录堆积 ~103 个未跟踪的测试项目目录 | P5-1 |
| 20 | RFC-001 挂了 70 天 `Proposed`，其治理目标 `runner.py` 同期增长 36%（1,617 → 2,213 行）；RFC 内的行数/函数/lazy-import 记录全部过期 | P2-2 |

### 8.3 对既有结论的修正

| 既有结论 | 本报告修正 |
|:--|:--|
| 「测试可不可信 ✅ 可信 —— 4695 通过 / 65 失败 / 22 报错」（2026-09-17） | 本次实跑 **5,317 通过 / 2 跳过 / 0 失败 / 0 报错**。当时的失败应为已修复；**当前测试套件是绿的**，本报告不再将其列为缺陷 |
| 「文档准不准 ✅ 准」（2026-09-17） | 对**被门禁校验的**三类数字成立（68/19/149 全对齐）；**LOC / 文件数 / 测试数三类数字无人校验且已漂移** |
| 「D 门是模板 ×7 复制粘贴」（通俗说法） | 精确化：属**同构**（6 阶段骨架 ×7），AST 级字面复制仅 1 组。结论方向不变，但重构收益应按「同构」而非「复制」估算 |

---

## 九、如果只能做六件事

按「信号诚实 → 单一真相源 → 形状 → 文档」的顺序。**信号类修复必须先行**：在假信号被清除之前，任何结构重构的效果都无法度量。

| # | 动作 | 触及 | 为什么这个顺序 |
|:--|:--|:--|:--|
| **1** | 修 e2e：`make test-e2e` 加 `-o addopts=""`（或 `-m e2e`）；nightly 增加 e2e 作业；**加一条元测试——任何测试命令收集到 0 个用例必须失败** | P0-2 | 208 个测试从「不存在」变为「存在」；投入 < 1 小时，收益最大。**元测试的价值超过修 10 个 bug**——它让这类沉默以后无法再发生 |
| **2** | 在 gate report 增加 `skip_reason` 维度，并按 `validation/coverage.py` 既有四分法扩出第五维「输入可达性」，产出「实测有多少门真的会检查东西」 | P0-1 | 复用已在运行时采集的 `was_written()`；把「33 道质量门」变成可审计的数字。**用项目自己的框架补项目自己的洞** |
| **3** | 消除两处「看起来对」的静默错误：V7 的 MD5 改为「生成时记 expected / 校验时算 actual」（或删除该检查）；`resume_from` 要么真从 `01_content/drafts/` 回灌、要么删除，只保留 `resume_project_id` 的 HITL 续跑语义 | P0-1 / P0-3 | 半实现的 resume 是负资产；恒真的校验比没有校验更危险，因为它占着「已验证」的位置 |
| **4** | 抽 `pipelines/gate_plan.py`（mode → 有序门计划，**唯一权威**）+ `core/layout.py`（目录常量，所有写盘必经）；`dag.py` / `state_view.py` / `runner.py` 全部消费它；接通或删除 `gate_engine.*` 配置 | P1-1 / P1-2 / P0-4 | 一次性消掉 4 类「真相副本」，并把 `05_publish`/`06_publish` 这类撞号收进单一常量表 |
| **5** | 抽 `PlatformRewriteGate` + `ArtifactWriter` 基类，收掉 D1–D7 / P1–P4 的同构骨架 | P3-1 | 约 2,300 行 → 约 700 行；7 个平台从「人肉 diff」变成「可比较的配置」 |
| **6** | 给 RFC 流水线加一道**老化检查**：`docs/dev/deep-module-rfc-*.md` 超过 N 天仍为 `Proposed`，或其所记录的行数/函数数已与源码不符，则在 CI 里报出来 | P2-2 | RFC-001 停摆 70 天、其目标文件同期增长 36%，而**没有任何机制发现这件事**。这检查的成本是一个正则，但它保护的是整个「诊断 → 落地」流水线不被零成本状态吞掉 |

**明确不要做的事**：

- **不要合并 `prompts/` / `engines/` / `accounts/` / `asset_library/`** —— 它们已经是本项目的方法论范本，重构应当复制它们，而不是把它们拉平。
- **不要给 `features/` 补执行点**，直到确认 tier 校验是真实需求（它现在是 256 行、零调用点、自述为 MARKER）。
- **不要在修 P0 的同时重构 `runner.py`** —— 信号修复与结构重构必须分两个 PR，否则无法证明哪个改动起了作用（这也正是 `deep-module-rfc-001.md` 的「一次 issue = 一次可验证提交」纪律所要求的）。
- **不要手写新的文档数字** —— 扩展 `scripts/check-doc-consistency.py` 去自动校验 LOC / 文件数 / 测试函数数，或改为从源码生成。
- **不要把 RFC 停在 `Proposed` 当作「已经处理」** —— 这是本仓库目前最容易复发、也最容易被误认为已闭环的状态。

---

## 附录 A：复现命令

本报告全部结论可由以下命令复现（在仓库根目录、`.venv` 环境下执行）。

```bash
# ── 静态检查（全绿）
.venv/bin/ruff check .
.venv/bin/mypy src/automedia/ --ignore-missing-imports

# ── 文档门禁（exit 0；只覆盖 68 tools / 19 CLI / 149 scenarios）
.venv/bin/python scripts/check-doc-consistency.py

# ── P0-2  e2e 静默空转
.venv/bin/python -m pytest tests/test_e2e/ --collect-only              # 0 collected, 208 deselected, exit 0
.venv/bin/python -m pytest tests/test_e2e/ --collect-only -o addopts="" # 208 collected
grep -rn "e2e" .github/workflows/                                       # 零命中

# ── P0-1  V 门输入零生产者
for k in lint_result entries qa_passed avg_brightness contrast pixel_valid \
         voice_id expected_voice_id speaking_rate segments \
         source_keywords content_keywords expected_md5 expected_format; do
  printf '%-22s ' "$k"; grep -rcE "\[\"$k\"\] *=" src/automedia/ --include=*.py \
    | awk -F: '{s+=$2} END{print s" 写入点"}'
done
sed -n '2178,2181p' src/automedia/pipelines/runner.py    # V7 MD5 恒真
sed -n '1494,1498p' src/automedia/pipelines/runner.py    # resume 占位符

# ── P0-4  配置不生效
sed -n '1527,1535p' src/automedia/pipelines/runner.py    # GateEngine 未收 max_retries
grep -n "max_retries\|retry_delay\|max_regenerations" src/automedia/manifests/defaults.yaml

# ── P2-1  hook 派发不对称
sed -n '1023,1026p' src/automedia/pipelines/gate_engine.py   # stop 失败：直接 return，无 _dispatch_*
sed -n '1298p'       src/automedia/pipelines/gate_engine.py   # retry 耗尽：派发 _dispatch_after(passed=False)
grep -c "_dispatch_" src/automedia/pipelines/gate_engine.py  # run_sub_pipeline(1480-1715) 内零派发

# ── P1-2  目录撞号
grep -rn '"05_publish"' src/automedia/ ; grep -rn '"06_publish"' src/automedia/
grep -A10 'subdirs = \[' src/automedia/core/project.py

# ── P4-2  文档数字漂移
grep -n "62,461\|737+\|4,580" README.md docs/index.md
find src/automedia -name '*.py' | wc -l            # 261
find src/automedia -name '*.py' -exec cat {} + | wc -l   # 67,997

# ── P2-2  RFC-001 停摆，摩擦区反而长大
git log --oneline --all -- docs/dev/deep-module-rfc-001.md          # 仅 3 个 commit，从未更新
git show e529de2:src/automedia/pipelines/runner.py | wc -l          # 1,617
wc -l < src/automedia/pipelines/runner.py                            # 2,213（+36.8%）
grep -cE '^\s+(from|import) ' src/automedia/pipelines/runner.py      # 53（RFC 记录 13）
grep -A4 '^\*\*Status:' docs/dev/deep-module-rfc-001.md              # 仍是 Proposed

# ── 规模与形状
find src/automedia -name '*.py' -exec wc -l {} + | sort -rn | head -12
grep -cE '^\s+(from|import) ' src/automedia/pipelines/runner.py   # 53 个 lazy import
grep -rn "mcp.tool(" src/automedia/mcp/server.py | wc -l          # 68
```

---

*本报告为一次性快照，不构成持续门禁。建议将 §六 P0-1～P0-4、§九 第 1 项转为可执行回归场景（见 `docs/skills/validation-runner.md` 的 RED→GREEN 流程），使其成为 CI 阻塞项而非文档承诺。*
