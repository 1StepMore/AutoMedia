# AutoMedia 基础设施有效性审计（Agent 双角色视角）

> **审计日期**：2026-10-30
> **审计对象**：`main` 分支 HEAD `f880a28` + 工作区未提交的文档修复批次（以磁盘当前内容为准）
> **分析方法**：五路并行代码盘点（gates/DAG、hooks/HITL/decision、validation、skills/docs、MCP/CLI/子系统）+ 关键结论亲自复核 + 实跑 `check-doc-consistency.py`（exit 0）与 `check_rfc_aging.py`（exit 0）；与 `codebase-audit-20261022.md`、`project-analysis-20261029.md`、`doc-update-audit-20261029.md` 三份既有报告交叉核对。所有结论附 `文件:行号` 证据。
> **性质**：只读分析快照 + 有效性判定，不含实施排期。
> **派生计数（实跑所得）**：68 MCP 工具 / 19 CLI 命令 / 160 场景 / 71,608 core LOC / 271 文件 / 5,464 测试函数 / 1,046 tracked files。

---

## 一、分析框架：两种角色 × 四条判据 × 三档判定

### 1.1 两种角色的定义（本审计的透镜）

项目的设计理念是 **Agent 优先**：直接执行者默认是 AI agent，人类是导演（`founder-expectations.md` F 系列；`project-analysis-20261029.md` §2.1）。落到基础设施上就是两个消费视角：

- **Agent as a user（代理即用户）**：agent 通过 MCP/CLI/SDK *操作*管线生产内容——它消费的是 MCP 工具面、AGENTS.md 入口文档、docs/skills 操作手册、gates 的执行与报告面、HITL 暂停/恢复机制、hooks 观测面。评价标准是"agent 能否可靠地用它完成一次生产并诚实获知结果"。
- **Agent as a tester（代理即测试员）**：agent 通过验证层*检验*系统自身——它消费的是 160 个场景、5 状态证据契约、coverage/matrix/diff、文档一致性门禁、红线测试。评价标准是"agent 能否用它产生可信的证据，并拦住真实回归"。
- 人类导演通过 agent 间接介入（H0、signed.txt），故"人类是导演"的落地质量也归入本审计。

### 1.2 有效性判据

| 判据 | 含义 |
|---|---|
| ① 接线 | 存在真实可达的执行路径（不是只被 import 或只被文档提及） |
| ② 消费 | 上述两角色之一会在真实工作流中用到它的产出 |
| ③ 诚实 | 失败/未配置/跳过会被如实报告（fail-honest），不被折叠成假绿 |
| ④ 准确 | 文档声明与代码现实一致（或偏差被门禁拦截） |

### 1.3 判定三档 + 一个重要区分

- **有效**：四判据全满足。
- **部分有效**：接线但消费面窄 / 断言浅 / 文档漂移 / 有诚实缺口。
- **无效**：结构性不可达（死代码）、结构性永不触发（断线）、或消费它必然被误导。
- **⚠️ 区分**："无效" ≠ "该删"。`AutoMedia-development-brief-v2.md` §四/§六 明确：现有能力不得减少、重构须有商业理由。因此本报告把无效项再分为两类：**死重**（从未接线，可裁决回收）与**有意休眠**（开放核/外部化等设计决策，问题只在"agent 可发现性"）。

---

## 二、总览矩阵

| # | 基础设施 | 角色 | 判定 | 一句话依据 |
|---|---|---|---|---|
| 1 | `gate_plan.py` 单一权威 + DAG 26 节点拓扑钉定 | user+tester | **有效** | runner 以 identity 引用同一对象（`runner.py:60`），`test_dag.py:62-66` 逐 mode 钉死 |
| 2 | 33 门注册面（failure_modes 全覆盖、测试 1:1） | user | **有效** | 33/33 登记（retry 16/stop 17），每门有专门测试（P1-P4 共用一个文件） |
| 3 | V0-V7 fail-honest（`missing_input_result`） | user | **有效** | 8 门全接入；但仅覆盖 V 轨（25 门未用，见 §3.3） |
| 4 | L1-L4 生命周期接线 | user | **有效** | publish/archive/distribute/omni-localize 四条命令各挂一门（wiring 测试齐备） |
| 5 | D1-D7 分发接线 | user | **有效（CLI 轨）** | 仅 `automedia distribute` CLI 触达（`distribute.py:470-482`）；MCP `distribute_content` 不跑 D 门——同名不同义（§3.3） |
| 6 | P1-P4 repurpose 接线 | user | **有效** | `mode="repurpose"` → gate_plan `_REPURPOSE_GATE_NAMES` |
| 7 | G4/G5 | user | **有意休眠** | 无 preset、无硬编码调用点，仅 `gates.include` 配置可达；`gate_plan.py:15-20` 自declared开放核 |
| 8 | GateHook 协议 + CostTracker/PipelineHistoryHook | user | **有效** | 每次 run 硬编码注入（`runner.py:1417-1419`），深拷贝+逐 hook 异常隔离，history.db 有三个活跃下游 |
| 9 | 自定义 hook 注册面 | user | **部分有效** | 仅 Python SDK 可传 `hooks=`；CLI/MCP/YAML 无入口 |
| 10 | H0 → park → resume 主干 + `review_decision` + 审计日志 | user+导演 | **有效** | 三通道审批（stdin/CLI 文件/MCP 内存）+ parked 恢复链完整，有测试 |
| 11 | director-approval 链（`approve_gate`/`reject_gate`/`get_pending_approvals`） | user | **无效（断线）** | `requires_approval` 无任何代码写入 gate_context，3 个 MCP 工具结构性永不触发（§3.3） |
| 12 | `hitl preset --set` | user | **无效（假配置）** | runner 硬编码 preset（`runner.py:1217`），active_preset.yaml 只被展示命令读取 |
| 13 | decision 层（DecisionArtifact/schema_validator/log_force_provenance/NodeProvider/NodeExecutor） | — | **无效（死重）** | 零生产消费者；仅 review_audit 与 pydantic 模型被"借住"活跃 |
| 14 | detectors 框架 | user | **接线但闲置** | 唯一消费点是 humanizer 内一个检测器；registry/GPTZero 占位零调用 |
| 15 | features/（check_tier 开放核标记） | user | **接线但单点** | 全仓唯一执行点 `runner.py:456-460` |
| 16 | asset_library | user | **接线但弱** | 1 个 MCP 工具 + DistributionLog 只写不读；无 CLI 面 |
| 17 | MCP 68 工具注册面 | user | **有效** | server.py 只做注册+仪器化；4 个弃用别名各多一层包装（税） |
| 18 | MCP allowlist | user | **部分有效** | 核心比较正确+空表 fail-closed；但 15 处调用点靠自觉，`analyze_content` 零校验、`distribute_content`/`source_path` fail-open（§3.3） |
| 19 | CLI 19 命令 | user | **有效** | 与 MCP 同源 `run_full_pipeline`；validate 7 子命令、cron `run --due` 均实装 |
| 20 | `automedia distribute`（CLI）vs `distribute_content`（MCP） | user | **无效命名** | 同名能力两种语义（D 门改写 vs PublishEngine 直发），agent 必然踩混淆 |
| 21 | `omni localize` CLI vs `localize_output` MCP | user | **部分有效** | 约 100 行平行实现且已漂移（MCP 有 allowlist 校验+返回 l4_verdicts，CLI 全无） |
| 22 | 配置 6 层 / prompts 4 级 / manifests / engines 7 实现 / pool / cron CLI 链 / effects / accounts | user | **有效** | 各有多处跨包消费（详见 §3.1） |
| 23 | pool 内存态问题 | user | **已修复（改善）** | MCP 路径 `:memory:` 用法已消除（grep 零命中），对比简报时点是净改善 |
| 24 | 验证引擎（5 状态/沙箱/O_EXCL/打码/confidence/trusted） | tester | **有效** | 防伪造机制扎实；unconfigured 在 dispatch 前短路，是状态不是裁决 |
| 25 | 160 场景的执行真实性 | tester | **有效** | 160/160 有真 tool/cli 步骤，0 个纯文件存在性场景 |
| 26 | 场景断言深度 | tester | **部分有效** | ~60%（surface+cli 96 个）是单标记断言；深探针仅 7/160≈4%；`data_has` 零使用 |
| 27 | STANDARDS.md 词表 | tester | **无效（装饰）** | 56 个 standard key 仅 6 个被引用，全部 `gate.*`/`mode.*` 零引用（STANDARDS.md:85-94 自认） |
| 28 | coverage audit 静态半 | tester | **有效** | declared 从源码 AST/正则派生，含 unreachable gates 与输入可达性第 5 维 |
| 29 | coverage audit 证据半 | tester | **部分有效** | 机制真实（按 passed 步骤到达面计），但提交态 0 covered/119 unproven，`validate coverage` exit 1 是常态 |
| 30 | CI 真闸门（validation-affected、missing_hard_count、audit drift check） | tester | **有效** | PR 阻塞式；新面无场景即硬红；`coverage-audit.json` 逐字节比对 |
| 31 | nightly validation-full-suite | tester | **部分有效** | 无凭据环境下 unconfigured 短路 → 几乎恒绿；仅 nightly advisory |
| 32 | 文档门禁（计数+结构断言+链接+标识符+marker） | tester/maintainer | **有效** | 实跑 exit 0；`test_doc_consistency.py` 488 行钉死契约 |
| 33 | doc-inventory 生成物 | maintainer | **有效** | 三方字节级钉定；当前 `--check` 红属修复中间态，需再生成 |
| 34 | RFC 老化检查 | maintainer | **有效** | 实跑 exit 0；RFC-001 于第 77 天被 Accepted（90 天红线内） |
| 35 | 红线测试 | tester | **部分有效** | marker 已注册（`conftest.py:27`），4 个文件有标记用例；但 e2e 红线文件仅 nightly 跑，CI 无 `-m redline` 步骤，README 仍写 "10 MUST/MUST NOT"（AGENTS.md 实为 9 条） |
| 36 | validate sign | 导演 | **部分有效** | 纯文本追加行，无密码学签名、无发布强制——导演裁决目前只是流程约定 |
| 37 | committed baseline 的 RED 证据 | tester | **部分有效** | 原 RED baseline 被覆盖丢失（`baseline/README.md:15-25` 自认 gap R-10）；O_EXCL 已防复发 |
| 38 | validation metrics | tester | **无效（装饰）** | token_usage/error_recovery_time 恒 null，自认无 instrumentation |
| 39 | maintainer skills：issue-triage、pr-review-merge | maintainer | **有效** | 2026-10 实测标注、命令逐条可执行、唯一流程文档 |
| 40 | maintainer skills：validation-runner / deep-modules / doc-sync | maintainer | **部分有效** | 流程有效但数字/路径过时（144 计数、1,617 行旧数、`mcp/tools.py` 死路径） |
| 41 | maintainer skill：project-validation | maintainer | **无效** | 数据源 founder-expectations 已被宣布冻结（"do not refresh"）、48/55 期望数错配、impact_map 指向死路径——教的是一个不再运转的流程 |
| 42 | docs/skills 4 件套 | user | **有效** | 4/4 工具签名与注册表核对全真（仅 2 篇漏列可选参数）；发现链完整 |
| 43 | mcp-setup.md | user | **有效** | 698 行零过时计数，agent-as-user 最佳入门路径 |
| 44 | agent-reference.md | user/maintainer | **有效** | 抽查 3 项断言全过，全仓最准文档（本轮修复后） |
| 45 | glossary / user-introduction | user | **部分有效** | "67/65 工具"计数滞后；glossary 门清单指针仍指向 runner.py 而非 gate_plan.py |
| 46 | llms.txt 对 docs/skills 的发现链 | user | **缺口** | 纯 MCP 客户端（不读仓库文件）看不到 4 篇用户技能 |

---

## 三、Agent as a user 侧详评

### 3.1 有效：值得保护的承重面

1. **门禁执行面是全仓最稳的一块。** `gate_plan.MODE_GATE_NAMES` 是唯一权威（9 个 mode 的门序声明于 `pipelines/gate_plan.py:34-158`），runner `_MODE_MAP` 是同一对象的别名导出（`runner.py:60`），DAG 26 节点的拓扑序被 `tests/test_runner/test_dag.py:62-66` 逐 mode 钉死。33 门全部登记于 `failure_modes.py`（红线 7 零违规，测试一对一覆盖）。对 agent 用户，这意味着"我看到的门序 = 我会执行的门序"。

2. **fail-honest 信号在 V 轨是完整的。** `missing_input_result`（`gates/_result.py:228-282`）基于"生产者是否显式写出"（`GateContext.was_written`，`_context.py:189-249`）判定，V0-V7 八门全部接入，跳过必带原因，`skip_reason` 由 runner 透传到报告（`runner.py:1812`）。配套 `validation/gate_inputs.py` 的 AST 扫描 + `test_gate_input_reachability.py` 把"哪些门永远拿不到输入"也钉进测试。

3. **L/D/P 轨的独立接线是真实的。** L1 挂发布（`gates/publish_log_wiring.py:102-111`）、L2 挂 `automedia archive`（`cli/commands/archive.py:48-52`）、L3 挂 `automedia distribute`（`distribute.py:161-169`）、L4 挂 omni localize（CLI `omni.py:214-220` 与 MCP `omni.py:187,259`，advisory）；D1-D7 由 `automedia distribute` 逐平台实例化执行（`distribute.py:38-46,470-482`），cron 复用同一命令串；P1-P4 由 `mode="repurpose"` 进入 gate_plan 执行。**没有任何一个门是纯摆设**——最接近的 G4/G5 也是声明式开放核（见 §3.2）。

4. **hooks 体系是三层观测基建中最健康的。** 两个内置 hook 由 runner 无条件注入每次 run（`runner.py:1417-1419`）：`CostTracker` 写 `cost_log.jsonl`，`PipelineHistoryHook` 写 SQLite `history.db`。只读契约有机制保障——`_detached` 递归拷贝（`_context.py:31-40`）+ 逐 hook 异常隔离（`gate_engine.py:383-428`），并有专项测试。`history.db` 有三个活跃下游：`automedia history`、auto_resume 推导续跑点（`state_view.py:146`）、`hitl pending` 判定（`hitl_review.py:48-75`）。

5. **HITL 主干真实可用。** H0 返回 `awaiting_hitl` → 引擎 park（`status="awaiting_review"`）→ 三条审批通道：CLI 交互 stdin（`--wait-for-review`）、跨进程 CLI `hitl approve/reject`（写 `.hitl_state.json`，读后即删防残留放行，`gate_types.py:357-376`）、同进程 MCP `review_decision`（内存通道 + `decision/review_audit.py` 审计落盘）。决策投递走文件通道可跨进程存活，parked 恢复链（`run --project-id`）闭环完整且有测试。超时默认 fail-closed（未识别的 on_timeout 一律按 reject，`gate_types.py:409`）。

6. **接口面与基础设施子系统多数多路消费、活跃接线**：配置 6 层（13+ 调用点）、prompts 4 级覆盖链（14 个调用点）、engines 7 实现导入即注册、pool（CLI+MCP+resource 五路消费，且 MCP 路径的 `:memory:` 内存池已消除——对比简报时点是净改善）、cron CLI 执行链（`run --due` → `is_schedule_due` → `run_scheduled_pipeline`）、effects（CLI+MCP 双面）、templates→hyperframes 视频引擎、manifests 三族 schema。

### 3.2 有意休眠（设计如此，但 agent 可发现性是真实缺口）

1. **G4/G5**：无 preset、无硬编码调用点，唯一触达方式是 `gates.include` 配置修饰符（`runner.py:399-400` 只校验"已注册"）。`gate_plan.py:15-20` 把这声明为产品决策，简报 §三·补 界定 1 也确认"本次不改动现有门控"。**判定：不算死重**；但对 agent 用户它们是不可发现的能力——`features/` 的 tier 表（`features/__init__.py:53,62`）和 MCP `get_gate_report` 都不会告诉 agent"这个门存在且可被启用"。若开放核要商业化，需要一个"列出全部已注册门及其启用途径"的工具或 resource。
2. **cron 外部化**：MCP 只有 5 个管理工具（增删查测），执行只存在于 CLI `cron run --due`——这是"调度外部化"的既定设计（AGENTS.md §4），但纯 MCP 客户端 agent 无法触发到期任务，只能在 instructions 里被告知去调 CLI。
3. **8 个 manual-stub 适配器**：`is_stub` 默认 True（`registry.py:83`）是 fail-honest 的正面样板——不自动化直到证明可以。判定有效。

### 3.3 无效与危险区（agent 用户视角的真实伤害点）

1. **【最高优先】同名不同义：`automedia distribute` vs `distribute_content`。**
   CLI `distribute` 跑 D1-D7 门（平台化改写，`_PLATFORM_GATES` 映射，`distribute.py:38-46,470-482`）；MCP `distribute_content` 走 `adapters/distribution.py:64` 的 `distribute_to_platforms` → `PublishEngine.publish_all` 直接发布，**完全不经过 D 门**（`tools_distribution.py:98`）。两条路径语义（改写 vs 发布）、副作用（写盘 vs 外呼平台 API）、前置条件完全不同，名字却几乎一样。对 agent 用户这是最危险的一类基建缺陷：工具描述稍有含糊就会把"生成各平台文案"误解成"向 20 个平台发布"。docs/skills/distribution-workflow.md 讲的是 MCP 路径，`automedia distribute` 的 D 门语义只活在 CLI 文档里。
2. **director-approval 链是给 agent 的"假门"。** MCP 工具 `approve_gate`/`reject_gate`/`get_pending_approvals`（`mcp/tools/approval.py:27-150`）依赖 `pause_on_approval` + `requires_approval` + `GateEngine.resume()` + `_approval_events`，但全仓**没有任何代码把 `requires_approval` 写进 gate_context**——runner 构建 hitl_config 时只取 `{name, autoset}` 两个字段（`runner.py:1217-1221`），director preset 里的 `requires_approval: True` 被丢弃。结果：`pause_on_approval=True` 永远等不到暂停点，`get_pending_approvals` 恒返回空列表。代码与文档双方都自认 dormant（`mcp/tools/review.py:3`、`hitl-framework.md:65-66`）。**伤害**：agent 读完工具描述会合理地以为"我可以审批门级产出"，实际上这条路一次都没通过。
3. **`review_decision` 的"活审批"场景是空集，且会对已结束的 run 报成功。** MCP 的 `run_pipeline`/`run_batch` 硬编码 `block_on_hitl=False`（`mcp/tools/pipeline.py:246,326`），本进程永远不会停在 H0 上等待——于是同进程内存审批通道唯一能命中的是 parked run 遗留在 `_hitl_waiters` 里的永不清理条目（`mark_finished` 不摘除），命中后返回 `{"approved": True}` 但对已结束的 run 无任何效果（`review.py:161-183` 无 is_running 校验）。`mcp/instructions.py:249-251` 声称 parked run "NOT reachable this way"，与实际行为（能命中、报成功、无效果）不符——对 agent 是诚实缺口。
4. **`hitl preset --set` 是假配置。** runner 硬编码 `"director" if director else "automated"`（`runner.py:1217`）；`active_preset.yaml` 只被 `hitl config` 展示和 onboard 检查读取。文档（`hitl-framework.md:110-121,216`）暗示 preset 选择驱动运行时行为，且文档中 director 节点表与 `director.py` 实际节点名对不上。
5. **decision 层 308 行基本是死基础设施。** `DecisionArtifact`（`decision/base.py`）零生产者零消费者；`schema_validator.validate_artifact` 零消费者（`manifests/schemas/*.json` 七个文件全靠它一个读者）；`log_force_provenance` 零消费者（`runner.py:712` 已注明 deprecated）；`NodeProvider` 协议无实现；`NodeExecutor` 零调用点。活跃的只有两个"借住"模块：`review_audit.py`（MCP 审批审计）与 `decision/pydantic/`（4 个 MCP 工具的结构化输出）——它们与"决策层"本义无关。**还连带污染文档**：`hitl-framework.md:165,229,262,267` 引用了不存在的 `DiagnosticAgent`/`BaseDecisionAgent`/`decision.orchestrator`——这是文档门禁的盲区（该文档不在扫描集，且"符号存在性"只在 AGENTS/README/index 上跑）。
6. **MCP allowlist 是"自觉执行"模式，存在已证实的缺口。** 核心比较函数正确（双侧 realpath、空表 fail-closed，`allowlist.py:145-181`），但 `_require_allowed` 的 15 处调用点全靠人工逐个添加：`analyze_content`（`effects/mcp.py:39-43`）接受任意 `base_dir` 零校验（实测 allowlist 外目录返回完整统计，project-analysis-20261029 §4.3.1，本轮复核缺口仍在）；`distribute_content`（`tools_distribution.py:84-95`）与 `run_pipeline` 的 `source_path`（`tools/pipeline.py:176-182`）fail-open——校验失败仅告警后继续；`init_config` 接受任意目录写。6 个 MCP resource 整体豁免。对 agent 用户而言"路径沙箱"的安全声明与实际执行不符。
7. **CLI/MCP 双实现已开始漂移。** `omni localize`（CLI `omni.py:145-258`）与 `localize_output`（MCP `omni.py:150-330`）是同一"扫 drafts→翻译→L4→写 06_publish"循环的两份约 100 行平行实现：MCP 版先做 allowlist 校验并返回 `l4_verdicts`，CLI 版两者皆无。改 L4 行为必须改两处，且今天两处行为已经不同。
8. **deprecated 别名是三层税。** 4 个弃用别名各为"wrapper+实现"两层，`server.py:353-379` 另有 3 个仅进 `__all__` 的历史兼容 wrapper——第三层纯冗余。
9. **hooks 的自定义注册只有 SDK 一条路。** CLI/MCP/YAML 均无入口（`defaults.yaml` 的 gate_engine 段无 hooks 键）——对一个 MCP 优先的项目，最主流的用户路径用不上这套协议；`CostTracker` 的 `cost_log.jsonl` 无任何读端（无查询命令/工具），写而未读。

---

## 四、Agent as a tester 侧详评

### 4.1 有效：验证层是真闸门，不是橡皮图章

1. **执行层 100% 真实。** 160 个场景全部有 ≥1 个真 tool/cli 步骤（tool 步=进程内调用真 FastMCP 实例 `adapters.py:158-174`，cli 步=子进程 `adapters.py:195-262`），0 个纯文件存在性场景。364 个步骤中 cli 213 / tool 134 / file 17。
2. **防伪造机制扎实**：O_EXCL 不可变 run 目录（`persist.py:94-131`）、每 run 一次性沙箱（`AUTOMEDIA_CONFIG_DIR/PROJECTS_DIR` 指向 temp，`engine.py:359-368`）、秘密打码（`engine.py:148-173`）、artifact 越界拒绝、`confidence: real|mock`（mock 不计 coverage）、`trusted: false` 永不算 Proved、hard 场景非 passed → suite `blocked`（`engine.py:549-555`）。error_boundary 探针期望错误、全成功反而 fail。
3. **CI 有三个真闸门**：PR 阻塞式 `validation-affected`（`ci.yml:318-343`，failed→exit 1，unconfigured-only→exit 0 的诚实策略钉在脚本 docstring）；`missing_hard_count` 检查（`ci.yml:135-158`，新增 MCP/CLI/mode 面无场景即硬红）；committed `coverage-audit.json` 逐字节 drift check（`ci.yml:160-186`）。
4. **塔尖场景真能拦回归**：`produce-video` 的 ffprobe 探针（≥30s、≥1080p）能拦"8 秒幻灯片"级造假；`security/redteam-prompt-injection-topic` 断言副作用文件未产生；`archive-refusal`（hard）钉死红线 8 的 fail-closed 契约。**该层产生过真实负结果**：`validation-runs/20261027-183426` 抓到 produce-article RED（observed 724 < min 800）。
5. **文档门禁是 maintainer 侧最强资产**：`check-doc-consistency.py` 在计数断言（68 工具/19 命令/160 场景）之外，本轮已补齐四类结构断言——工具参数表、目录树、CLI 枚举、技能清单（`scan_tool_params`/`scan_module_tree`/`scan_cli_sections`/`scan_cli_enumerations`/`scan_skill_list`），`tests/test_doc_consistency.py` 488 行钉死全部契约，实跑 exit 0。RFC 老化检查（blocking，`ci.yml:49`）已在第 77 天裁决 RFC-001 前发挥作用。
6. **maintainer skills 中 issue-triage 与 pr-review-merge 是最新最准的**（2026-10-18 实测标注、含本仓库特有陷阱、命令逐条可执行），`mcp-setup.md`（698 行，68 工具清单与注册表逐一吻合）是 agent-as-user 的最佳入门路径。

### 4.2 部分有效：金字塔的中段与塔基

1. **断言深度分层明显。** surface+cli 两大类 96 个场景（60%）是"单次调用 + success/exit_code/stdout 标记"——拦表面崩溃，不拦语义回归。典型：`publish-dry-run-all-platforms` 对 20 平台的 `would_fail` 只进 trace 不进断言（注释自认）。深内容探针（media/text/subtitle/similarity/keyword_coverage/gate_records/min_score）仅 7/160≈4%；`data_has` 声明了却 0 次使用。
2. **阈值被现实磨平而无 waiver 记录。** produce-article 磁盘上的 `min_chars: 500` vs description 写 "≥800"（`production/produce-article.yaml:21,67`），而 10-27 的失败记录正是 "observed 724 < min 800"——门在失败后被下调，没有留下导演裁决的 waiver。这恰是该框架自己定义的"需导演裁决"信号，说明**裁决流程没有闭环**（与 §4.2.5 sign 无强制力互为因果）。
3. **nightly 全库 suite 几乎恒绿。** `env -u AUTOMEDIA_LLM_API_KEY` 下所有需要凭据的场景 unconfigured 短路，`validate run --all` 的 exit 1 只看 failed/blocked（`validate.py:351-352`）——诚实规则让 unconfigured 大声可见，但也意味着 nightly 的"绿"不含多少信息量；承重的凭据链路只有 nightly 的 `validation-draft-publish` canary（无凭据则整 job skip）。
4. **证据半 coverage 提交态全零。** 提交的 `coverage-audit.json` 中 evidence covered=0、unproven=119（提交时无 runs_root）——operator 端 `validate coverage` 的 exit 1 是常态而非信号。机制本身真实（按最新 suite 中 passed 步骤到达的面计），缺的是"有凭据的定期全量 run 产出证据"这个运营前提。
5. **regression 类有一半钉在框架自身。** `regression-336`/`regression-207` 等 meta 场景跑的是 `scripts/regression_*.py` helper——钉的是验证框架能力而非产品面，飞轮有空转段。
6. **红线测试的覆盖是分裂的。** marker 已注册（`conftest.py:27`），4 个文件带 `mark.redline`；但 e2e 红线文件 `tests/test_e2e/test_red_lines.py` 因 pyproject `addopts -m 'not e2e'` 只在 nightly 跑，CI 无 `-m redline` 专用步骤；README:717 仍把 `pytest -m redline` 当作一条可发现命令宣传，而 README:319,:573 仍写 "10 MUST/MUST NOT"（AGENTS.md 实为 9 条）——这条漂移不在任何门禁扫描范围内。
7. **baseline 的 RED 证据已丢失**（gap R-10 自认，`baseline/README.md:15-25`），O_EXCL 防复发已落地；`sign` 是纯文本追加行，无密码学校验、无"未签名不得发布"的技术强制——"人类是导演"目前主要落在流程约定上。
8. **STANDARDS.md 词表与 metrics 是装饰**：56 个 standard key 仅 6 个被引用、全部 `gate.*`/`mode.*` 零引用（`STANDARDS.md:85-94` 自认）——场景的 gate 覆盖实为 `proves_gates` 声明式元数据，不是 gate 执行证明；`validation/metrics.py` 的 token_usage/error_recovery_time 恒 null，自认无 instrumentation。
9. **maintainer skills 的知识过时**（流程有效、证据过期）：validation-runner 的 "144 scenarios"（现 160）与目录清单缺 production/recovery/security；deep-modules 的 watch-list（runner 1,617 行）是 RFC 前旧数（实测 2,165），"MCP (64 tools)" 亦过时；doc-sync 引用已不存在的 `mcp/tools.py`（:16,:394）、ADR 只数到 005（现 007）、DOC MAP 缺 agent-reference/doc-inventory/docs/skills 等后生文档。
10. **project-validation skill 教的是一个不再运转的流程**：其数据源 `founder-expectations.md` 已被 agent-reference:197 宣布为冻结快照（"do not refresh"），期望数 48 vs 实际 55，impact_map 的 pattern 仍指 `mcp/tools.py`，且无任何自动化执行它。四类维护者技能中唯一建议改写或归档的。

---

## 五、跨切面发现：无效的三种成因与三个系统性风险

### 5.1 死重的三种成因模式

| 模式 | 实例 | 判定含义 |
|---|---|---|
| A. PRD 先行、代码未落地 | decision 层、NodeExecutor、detectors 的 B4 闭环占位、director-approval 链 | **未兑现的承诺**：接口面已暴露（3 个 MCP 工具 + 文档），agent 会按文档走一条从未通的路 |
| B. 架构迁移后未回收 | deprecated 别名三层、doc-sync/deep-modules/project-validation 的死路径与旧数、glossary 指针、`server.py:353-379` 冗余 wrapper | **认知税**：不产生错误行为，但持续消耗 agent 的信任与 token |
| C. 有意的开放核/外部化 | G4/G5、cron 外部调度、manual-stub、features/check_tier 单点 | **不是缺陷**，但缺"可发现性"面（列出全部门/适配器及其启用途径的 introspection） |

### 5.2 三个系统性风险

1. **同名不同义 > 死代码。** 对 agent 用户，`distribute` 双语义的危害高于任何一块死重：死代码只是浪费，同名不同义会*主动误导*。同类风险：`review_decision` 对已结束 run 报 `approved: true`。
2. **文档门禁的覆盖面与"最常被读的文档"不重合。** 门禁扫 AGENTS/README/index/doc-inventory（数字+结构），但 hitl-framework（幽灵符号）、glossary/user-introduction（旧计数）、README 的 "10 条红线"、maintainer skills 的旧数都在盲区——doc-update-audit-20261029 §五 的盲区清单本轮已修一半（参数表/目录树/CLI 枚举/技能清单已门禁化），剩余盲区集中在 user/dev 深层文档与 skills 内容。
3. **"导演裁决"是当前最弱的一环。** 硬场景会 blocked、RED 会记录、阈值下调却无 waiver、sign 无强制力、director-approval 断线——形态 A（可交付的合规报告）所依赖的"人审有痕迹、裁决有权威"目前只有 `signed.txt` 一行文本和 review_decisions.log。这与商业定位（卖"保证能力"）之间的落差值得正视。

### 5.3 值得记录的净改善（反应式修复闭环在起作用）

- MCP 路径的 pool `:memory:` 内存态已消除（简报"现状事实"所列问题，今 grep 零命中）。
- doc-update-audit-20261029 的批次修复已在工作区落地且门禁全绿（实跑 exit 0）；H5（16 道门）/H6（示例输出）已验证修正；RFC-001 在 90 天红线内裁决为 Accepted。
- hooks 死代码（MetricsHook）与门序三副本已在 #321/#314 清除（本轮盘点确认无复活）。

---

## 六、建议：把无效转为有效的最小动作（按收益/成本排序，不触碰简报红线）

| 优先 | 动作 | 对应问题 | 说明 |
|---|---|---|---|
| 1 | **裁决 distribute 双语义**：给 MCP 工具或 CLI 之一改名（如 MCP 侧改 `publish_content` 语义已有，`distribute_content` 改名或文档首句显式声明"不跑 D 门"），并在 `help_mcp`/instructions 中互相指向 | §3.3.1 | 纯文档/命名级，无能力增减 |
| 2 | **director-approval 三工具裁决**：要么接线（runner 把 preset 的 `requires_approval` 写入 gate_context，一处改动），要么在工具描述与 hitl-framework 中改为 "reserved: not wired"，并让 `review_decision` 对已结束 run 返回结构化 STALE 而非 success | §3.3.2/3 | 一处代码或纯文档即可消除"假门" |
| 3 | **`hitl preset --set` 去假化**：要么让它真正影响 runner（读 active_preset.yaml），要么降级为 `hitl config` 的展示别名 | §3.3.4 | 小改动 |
| 4 | **decision 层回收**：保留 review_audit/pydantic；DecisionArtifact/schema_validator/log_force_provenance/NodeExecutor/NodeProvider 移入 docs/archived/ 或标注 dormant；修 hitl-framework.md 的 4 处幽灵符号 | §3.3.5 | 简报红线是"能力不得减少"——死代码从未是能力，回收不触线 |
| 5 | **allowlist 收口**：给 `analyze_content` 补校验、把 fail-open 两处改 fail-closed、把 `_require_allowed` 收敛为单一 choke point | §3.3.6 | project-analysis §5.3 已列高优先 |
| 6 | **场景深度定向提升**：不为凑数，优先给高频 surface 工具补输出断言（`data_has`/`output_has`），publish-dry-run 把 would_fail 纳入断言；同时裁剪或接线 STANDARDS 零引用词表 | §4.2.1/4.2.8 | 与简报"不增加门控数量"不冲突——这是加深不是加宽 |
| 7 | **阈值变更强制留痕**：场景阈值改动要求同 PR 附 baseline diff 或 waiver 行（可做成 coverage/CI 断言） | §4.2.2 | 把"导演裁决"从约定变门禁 |
| 8 | **maintainer skills 刷新**：deep-modules 换 RFC §6 重验数字；doc-sync 修 `mcp/tools.py` 死路径与 DOC MAP；project-validation 改写为指向 `automedia validate coverage` 的薄封装或归档 | §4.2.9/4.2.10 | 半天级工作量 |
| 9 | **发现链补口**：llms.txt 与 getting-started resource 挂上 docs/skills 四篇链接；考虑 `list_registered_gates`/`list_adapters` 类 introspection 工具，让 G4/G5/manual-stub 对 agent 可见 | §3.2/矩阵#46 | 开放核商业化的前置 |
| 10 | **红线表述统一**：README "10 条"改 9 条（或门禁加红线计数断言）；`pytest -m redline` 纳入某个 CI 步骤或从 README 撤下 | §4.2.6 | 文档级 |
| 11 | **收尾**：重跑 `python scripts/doc_inventory.py`（当前 --check 红属修复中间态）；`pkg-AutoMedia.zip`、`pkg-AutoMedia/` 与三份未跟踪报告做出入库/忽略裁决 | §5.3 | 工作区卫生 |

---

## 附录 A：与既有报告的关系

- `project-analysis-20261029.md`：本审计引用其 §2.1 理念清单、§4.3.1 allowlist 缺口与 §4.2.1 md5_tracker 编码缺陷作为佐证（本轮复核确认 `md5_tracker.py:30,53-54` 无 `encoding=` 且 `ensure_ascii=False` 的缺陷**仍在**，中文路径下 MD5 状态文件可信度问题未解）。
- `doc-update-audit-20261029.md`：其批次修复已在本工作区落地，门禁实跑绿；本审计把它的盲区清单推进到 skills 内容与深层 user/dev 文档。
- `codebase-audit-20261022.md`：其 P0 修复状态已由 project-analysis 核销，本审计未重复。

## 附录 B：证据文件索引

| 主题 | 关键文件 |
|---|---|
| 门禁 | `pipelines/gate_plan.py`、`dag.py`、`gates/failure_modes.py`、`gates/_result.py`、`_context.py`、`gates/distribution/`、`gates/sub_pipelines/` |
| 编排 | `pipelines/runner.py`（hooks 注入 :1417-1419、hitl_config :1217、tier 过滤 :456-460）、`gate_engine.py`（hook 派发 :377-429） |
| HITL/decision | `pipelines/gate_types.py`（:295-437 双通道）、`hitl/`（executor/config/presets）、`decision/`（base/audit/review_audit/schema_validator/pydantic）、`mcp/tools/review.py`、`approval.py` |
| 验证层 | `validation/engine.py`、`loader.py`、`expects.py`、`persist.py`、`coverage.py`、`matrix.py`、`diff.py`、`signoff.py`、`metrics.py`、`gate_inputs.py`、`scenarios/STANDARDS.md`、`scenarios/baseline/` |
| 文档门禁 | `scripts/check-doc-consistency.py`（845 行）、`scripts/doc_inventory.py`、`scripts/check_rfc_aging.py`、`tests/test_doc_consistency.py` |
| 接口面 | `mcp/server.py`、`mcp/tools/`（17 域模块）、`mcp/tools_distribution.py`、`mcp/allowlist.py`、`mcp/mcp/mcp_allowlist.yaml`、`cli/commands/`（19 命令） |
| Skills/docs | `.opencode/skills/`（7 文件）、`docs/skills/`（4 文件）、`.claude/skills/`、`.codex/skills/`、`docs/dev/agent-reference.md`、`docs/user/mcp-setup.md` |
| CI | `.github/workflows/ci.yml`（9 jobs）、`nightly.yml` |

## 附录 C：实跑记录（2026-10-30）

```
$ python scripts/check-doc-consistency.py
Derived counts: 68 MCP tools, 19 CLI commands, 160 scenarios
Derived sizes: 71,608 core LOC / 271 files, 173,017 total LOC / 629 files,
               5,464 test functions / 308 files, 1,046 tracked files
OK: all doc numeric claims match derived counts; doc↔reality audit clean   [exit 0]

$ python scripts/check_rfc_aging.py
OK: no RFC aging findings                                                  [exit 0]
```
