# AutoMedia 落地 Graph Engineering 实施方案（修正版，对齐 backup repo 现状）

**日期**：2026-08-30（修正版，在 2026-08-29 v2 基础上修正）｜ **作者**：default profile ｜ **读者**：code profile / coding agent
**代码基座**：`renanzai40/AutoMedia_BackUp@main`（backup/main 现为 `e584b39`，2026-08-30 拉取；本文全部文件路径以此 repo 为准，实测核对过）
**背景**：Graph Engineering（arXiv:2608.21156）核心 = 任务组织 / Agent协调 / 运行时状态管理 三维图化。AutoMedia 值得吸收的核心价值 = **把已有 Gate 引擎显式化为任务图 + 补全运行时状态可恢复**。

---

## 背景：Graph Engineering 是什么 + 本项目现状 + 差距

### Graph Engineering 是什么（30 秒）
> 继 Prompt → Context → Harness → Loop 之后的**下一代 Agent 工程范式**（来源 arXiv:2608.21156 奠基综述）。核心 = 把单 Agent 无法承担的复杂任务，**用显式的"图"来组织三件事**：
> - **Task Organization（任务组织）**：复杂目标 → 子任务图（依赖/顺序/并行/验证）
> - **Agent Coordination（Agent 协调）**：任务 → 异构 Agent 的团队/委派/通信
> - **Runtime State Management（运行时状态管理）**：进度/来源/故障可追踪、可定位、可恢复
>
> 一句话：**把隐藏在上下文和控制逻辑里的关系，外显为可操作的图**，获得单 Agent 做不到的"系统智能"。

### AutoMedia 项目现状（已实测 backup，2026-08-30）
AutoMedia 是**多 Track 内容生产系统**（Content OS）：一个 Topic 经**文案 Track（CW→G0-G6）与视频 Track（V0-V7）双分支 + 生命周期 L1-L4** 多 Gate 强制门控产出全平台内容。
它**已经"半图化"**（非零起点）：
- ✅ **Gate 引擎已代码化**：`pipelines/gate_engine.py`（顺序执行器）+ `pipelines/runner.py`（**22 个 Gate**、MD5 记录，`_AUTO_GATE_NAMES` 为线性 list）
- ✅ **运行时回滚已有雏形**：`pipelines/rollback_types.py`（ProjectAction / RollbackResult / history log）
- ✅ **任务配置载体已存在**：`core/workflow.py`（Workflow YAML：platforms/mode/gates modifiers）
- ✅ **平台子管线已存在**：`gates/sub_pipelines/`（wechat/twitter/newsletter/bilibili）
- ✅ **产线验证齐备**：`scenarios/journeys/*.yaml`（short-video/repurpose/video_only/social-thread...）

### 距离 Graph Engineering 的差距（缺什么）
| 维度 | 现状 | 差距 |
|---|---|---|
| **Task Organization** | Gate 列表顺序执行（`_AUTO_GATE_NAMES` 是**线性链表**，22 项）| **未显式化成分支/并行的 DAG**——copy/video 两 Track 只是概念并行，代码层是纯顺序 |
| **Agent Coordination** | 平台子管线 + 多脚本存在 | Agent/脚本/资源的配合为隐式，未成"能力图" |
| **Runtime State** | `--resume-from` 已实现（runner/CLI/MCP 三入口）、`PipelineHistoryHook` 逐 Gate 写 `history.db`、MD5 有记录 | **续跑能力已有，缺「自动续跑 + 失败定位」**——需手动传 `--resume-from`，未自动发现最后 passed Gate；失败不反查下游影响 |
| **System Evolution** | 无 | 高阶目标，本次不做 |

> **最核心差距**：AutoMedia 已有 Gate 引擎 + 回滚雏形 + **Gate 粒度续跑（`--resume-from`）已实现**，但 Gate 列表是"线性链表"而非"图"、续跑需手动指定、失败不自动定位。落地 = 把顺序执行升级为显式 DAG + 补**自动**续跑与失败定位，直接治"重做是最大成本"。

---

## 0. ⚠️ 重要前提（先澄清，避免空谈）

> **AutoMedia_BackUp 是一棵成熟的 Python 产品代码库，且已经"半图化"**：
> - `src/automedia/pipelines/gate_engine.py` = Gate 引擎（已存在）
> - `src/automedia/pipelines/runner.py` = 全管线执行器（已有 `_AUTO_GATE_NAMES`：pre-gate→CW→G0-G6→V0-V7→H0→L1-L4，**22 个 Gate**，含 MD5 recording）
> - `src/automedia/pipelines/rollback_types.py` = **已实现运行时状态/回滚**（`ProjectAction`/`RollbackResult`/history log）
> - `src/automedia/pipelines/runner.py` **已实现 Gate 粒度续跑**：`resume_from` 参数（runner/CLI `--resume-from`/MCP `run_pipeline` 三入口）+ `_verify_resume_integrity()`（校验 resume 点前所有 Gate 的 MD5）+ `PipelineHistoryHook`（逐 Gate 写 `{gate_name}:started/completed/failed` 到 `history.db`）
> - `src/automedia/core/workflow.py` = Workflow YAML 配置（platforms/mode/gates modifiers/prompts/media/schedule）
> - `scenarios/journeys/*.yaml` = 各产线工作流的验证场景（repurpose/short-video/video_only/social-thread...）
>
> **所以本方案不是"从零建图"，而是在已有 `pipelines/`、`rollback_types.py` 与 `resume_from` 之上，做三件事的精准补强**：任务图显式化、自动续跑与失败定位、可观测性。

---

## 1. 现状盘点（已核实，非推断）

| 组件（backup 真实路径）| 现状 | 对应 Graph Engineering 概念 |
|---|---|---|
| `pipelines/gate_engine.py` | "sequential pipeline executor"，顺序跑 Gate 列表，按 failure_mode STOP/继续 | 任务图**执行器**（但只表达线性链，未表达分支/并行）|
| `pipelines/runner.py` | `_AUTO_GATE_NAMES` 顺序列表（**22 项**）+ MD5 recording | 任务的**隐式线性图** |
| `pipelines/rollback_types.py` | `ProjectAction`（run_started/gate_passed/gate_failed/rolled_back/published）+ history | 运行时状态**管理已有雏形**（project 级 status）|
| `pipelines/runner.py` `resume_from` | `--resume-from`/MCP `run_pipeline` 三入口 + `_verify_resume_integrity` MD5 校验 + `PipelineHistoryHook` 逐 Gate 写 `history.db` | 运行时状态**续跑能力已实现**（缺自动发现续跑点 + 失败反查下游）|
| `core/workflow.py` | Workflow YAML（platforms/mode/gates include/exclude/override_failure_mode）| **任务图配置载体已存在**（gate modifiers 已是灵活性）|
| `gates/sub_pipelines/{p1_wechat,p2_twitter,p3_newsletter,p4_bilibili}.py` | 平台级子管线 | **Agent 协调的分支**（已存在）|
| `hooks/pipeline_history.py` | 管线历史钩子 | 状态**来源记录** |
| `manifests/schemas/*.json` | 产物 schema | 产物结构 |
| `scenarios/journeys/*.yaml` | 各工作流验证场景 | **验收环境已齐备** |

**结论**：AutoMedia 在"Task Organization & Runtime State"上已有约 80% 基础。缺的是——**① runner 的 Gate 列表（22 项）是"线性顺序"，没有显式的分支/并行表达（DAG vs 链表）；② 续跑能力已存在（`--resume-from` + `PipelineHistoryHook` 逐 Gate 记录），但止于"手动指定续跑点"，未做到"自动发现最后 passed Gate + 失败反查下游"；③ 缺一张统一的运行状态视图可审计一次 production 到底过了哪些 Gate。**

---

## 2. 落地方案（3 步，全部落进现有文件，不新增重型依赖）

> 全部改动遵守 Backup-First 铁律（改前 /tmp/audit_backup_<date>_taskX/），并回归现有 scenarios。

### P0：把 runner 的"线性 Gate 列表"升级为"显式 DAG"（Task Organization 落地）

**现状**：`runner.py` 用 `_AUTO_GATE_NAMES: list[str]`（线性顺序，22 项）。**这是"链表"，不是"图"**。全 Auto 模式虽然两 Track 概念上并行，但代码层面 Gate 是纯顺序执行。

**改动**（改 `pipelines/runner.py` + `pipelines/gate_engine.py`）：
1. 把 Gate 列表从"list"改为**"DAG 结构"**（`dataclass`，不引外部库）：
   ```python
   # pipelines/dag.py (新增，或直接放 runner)
   @dataclass
   class GateNode:
       name: str
       track: str            # "copy" | "video" | "lifecycle" | "qa"
       depends_on: tuple[str, ...]   # 该 Gate 前必须完成的 Gate
       failure_mode: str     # existing: STOP / continue
       async_parallel: bool = False  # 是否可与其它 track 并行
   ```
2. `_AUTO_GATE_NAMES` → 重构为 `AUTO_GATE_DAG`：表达**文案分支（CW→G0-G6）与视频分支（V0-V7）是并行根**，生命周期 L1-L4 是汇合点。`gate_engine` 按 DAG 拓扑遍历（也可先保持顺序执行，但**结构上显式表达并行分支**）。
3. **导出可视化**：加 `runner.py --export-dag` → 输出 `pipeline_graph.md/.dot`（含每次 production 实际走的 Gate 路径）。**这是对外讲"壹目贯维=多 Track 并行、22 Gate 质量门控系统"的图**（product 卖点直接受益）。

**改动文件**：`pipelines/runner.py`（Gate 列表→DAG）、`pipelines/dag.py`（新）、`pipelines/gate_engine.py`（拓扑遍历）
**验收**：`--export-dag` 产出可读 DAG，copy/video 分支明确标并行；跑通 `scenarios/journeys/*.yaml` 全部回归（QA 不降级）。

---

### P1：自动续跑 + 失败定位（Runtime State 落地——补 `resume_from` 的缺口）

**现状**：Gate 粒度续跑**已实现**——`resume_from` 参数贯通 runner/CLI（`--resume-from`）/MCP（`run_pipeline`），`_verify_resume_integrity()` 校验 resume 点前所有 Gate 的 MD5，`PipelineHistoryHook` 逐 Gate 写 `{gate_name}:started/completed/failed` 到 `history.db`。**但缺口在于**：续跑点需**手动指定**，未自动发现「最后 passed Gate」；失败时不会反查下游受影响 Gate。

**改动**（改 `pipelines/runner.py` + `pipelines/gate_engine.py`）：
1. **自动发现续跑点**：runner 启动时若未显式传 `resume_from`，自动读 `history.db` 找到**最后一个 `completed` 的 Gate**，从它下依赖继续，**跳过已通过的**（尤其文案分支已过就不重跑）。显式传入时优先用显式值。
2. **失败定位**：Gate 失败时（`PipelineHistoryHook` 已写 `{gate_name}:failed`），通过 DAG 的 `depends_on` 反查**下游受影响 Gate**，输出「最早无效节点 + 受影响范围」。
3. 复用 `rollback_types.py` 的 `ProjectAction` 与 history log，不新增存储。

**改动文件**：`pipelines/runner.py`（自动续跑点发现）+ `pipelines/gate_engine.py`（失败定位辅助）+ 复用 `rollback_types.py` 的 ProjectAction
**验收**：真实制造一次视频 Track 在 V1 失败 → 不传 `--resume-from` 重跑 → 自动从 v1 续跑，文案分支结果不动。**必须用真实场景，非 mock。**

---

### P2：统一运行状态视图（System State）

**改动**：
1. 新 CLI：`automedia pipeline state <project>` → 输出该项目 DAG 全节点状态（passed/failed/pending + md5 + 时间），一眼看清"文案到哪、视频到哪、过了哪些 Gate"。
2. 复用 `hooks/pipeline_history.py` 已有的 history 数据，做状态聚合展示。

**改动文件**：`src/automedia/cli/`（新增 state 子命令）
**验收**：对一个项目跑 `automedia pipeline state`，5 秒内看清各 Track Gate 状态。

---

## 3. 明确不做（边界）

| ❌ 不做 | 原因 |
|---|---|
| 不引入图数据库 / 外部 DAG 引擎 | dict/custom dataclass 足够；不加重型依赖 |
| 不改 Gate 的**质检语义**（通过标准）| 那是产品级铁律，本次只改"组织方式"（顺序→图）不改判质 |
| 不真并行 TTS/API（除非明确收益）| P0 先表达并行意图；真并发留给以后评估 |
| 不动已交付项目 / 不回填历史 | 守"已交付项目不改进"铁律 |
| 不做 System Evolution（自演化 Gate 顺序）| 高阶目标，先不做 |

---

## 4. 一句产品价值

1. **自动续跑治"重做是最大成本"**（P1：`--resume-from` 已可用，本步补齐"自动发现续跑点 + 失败反查下游"）
2. **DAG 图 = 产线是多组件并行的可视化证据**（P0 --export-dag，对外讲产品的图）
3. **状态可审计**（P2），符合你"真实校验非 mock、来源可追溯"一贯原则

---

*本方案所有文件路径均已实测核对 `renanzai40/AutoMedia_BackUp@main`（commit `e584b39`）。实施前对照 `automedia-production-guard` skill（content profile 工作流约定）与 `src/automedia/` 代码。*
*修正记录（2026-08-30）：Gate 数统一为实测 **22 个**（`_AUTO_GATE_NAMES` 22 项，backup/main 实测）；标注 backup/main 现 commit `e584b39`。P1 重新定界：**Gate 粒度续跑已实现**（`--resume-from` 贯通 runner/CLI/MCP + `_verify_resume_integrity` + `PipelineHistoryHook` 逐 Gate 写 `history.db`），P1 实际缺口 =「自动发现最后 passed Gate 并续跑 + 失败反查下游」，而非"补续跑能力"；改动量较原 P1 缩水约 70%。方案其余部分与实测高度吻合。*