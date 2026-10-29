# AutoMedia 项目理解与问题分析报告

> **分析日期**:2026-10-29
> **分析对象**:AutoMedia `main` 分支(HEAD `9063f89`)
> **分析方法**:代码实读(管线/门禁/引擎、MCP/CLI/配置/安全、测试/文档/CI 三条线)+ 与 `docs/dev/codebase-audit-20261022.md` 等既有报告交叉核对。所有结论标注 `文件:行号` 证据。
> **校订**:2026-10-29 于同一 HEAD `9063f89` 逐条复核。计数类断言已改为 git 跟踪树的实测值;引错的文件/行号已对齐;被推翻的结论(并发用量统计互踩、`publish_content` fail-open、`features/` 零调用点、弃用别名"名字交叉")已替换为实测结论并保留推翻理由,便于读者判断可信度。
> **基线**:本报告是对 **HEAD `9063f89`** 的快照,所有 `文件:行号` 均指该 commit 的内容。复核时 `src/` 与 HEAD 无差异(故代码引用可直接核对);`docs/`、`scripts/`、`AGENTS.md`、`README.md` 在工作区另有未提交改动,若按工作区文件核对会出现行号偏移。
> **性质**:只读分析快照,不含实施建议排期。

---

## 一、这个项目是做什么的

AutoMedia 是一个**自动化内容生产流水线**:给定一个选题,自动完成写稿 → 质量核验 → 配音 → 视频生成 → 字幕渲染 → 多平台分发的全流程。核心规模(均按 git 跟踪树实测):

| 维度 | 数值 |
|:--|:--|
| 核心源码 | 71,608 行 / 271 文件(`src/automedia/`,git 跟踪) |
| 全仓源码 | 172,456 行 / 629 文件 |
| 测试 | 5,454 个测试函数 / 308 文件(git 跟踪树实测;README 宣称 5,200+/290+,为下界断言,一致) |
| 质量门禁 | 33 个(pre-gate、CW、G0-G6、V0-V7、H0、L1-L4、D1-D7、P1-P4) |
| 接口 | MCP 68 工具 / CLI 19 命令 / SDK,三者收敛到同一 `run_full_pipeline()` |
| 平台适配 | 20 个适配器模块 = 11 个真实 API 自动化 + 1 个飞书通知器 + 8 个有意的 manual-stub |

> **口径说明**:以上 LOC / 文件数 / 测试数取自 **HEAD `9063f89` 的 git 树**(`git show HEAD:<path>` 逐文件统计),与 `scripts/check-doc-consistency.py` 的 `compute_repo_stats()` 口径一致。工作区磁盘上另有 2 个未跟踪测试(如被 `*secret*` 忽略的 `tests/test_check_secrets.py`),故 `find` 口径会得到 5,456/309;对外数字以跟踪树为准,否则同一 commit 在不同机器上会报不同值。本报告所有 `文件:行号` 引用同样基于 HEAD `9063f89`(核对时 `src/` 工作区与 HEAD 无差异)。

关键认知:**它的核心资产不是"生成能力"(那是 LLM 的事),而是"判定能力"**——33 道 gate 把"什么叫合格内容"写成可执行代码,再用 9 种 mode(`auto`/`text_only`/`video_only`/`repurpose` 等)编排成不同形态的产线。

---

## 二、设计理念

### 2.1 宣言层(项目自己写的理念)

来源:`docs/dev/founder-expectations.md`(创始人验收期望,F01-F45)、`docs/dev/七阶段AI开发流程-用CodingAgent交付成品的方法论.md`、AGENTS.md。

1. **Agent 优先(Agent-oriented by default, human-capable by design)**。三类用户中"直接执行者"默认是 AI coding agent:一切能力先做成 MCP 工具,CLI/SDK 是人类兜底;人类是"指挥者"(director),通过 agent 间接下达意图。agent 是测试员,人类是导演——这就是 `automedia validate` 验证层(160 个场景)存在的原因。
2. **三入口同源**。SDK / CLI / MCP 全部委托 `run_full_pipeline()`,没有分叉实现。这是本项目架构上做得最正确的一件事(`src/` 内有 6 处真实调用点:`cli/commands/run.py:335,489`、`cron/runner.py:247`、`mcp/tools/pipeline.py:224,320`、`mcp/tools/strategy.py:220`,全部走同一实现)。
3. **门禁 = 可执行的验收标准**。每道门有 `failure_mode`(`stop` 停线 / `retry` 触发重写),引擎提供四级递增恢复:Level 0 瞬态重试(tenacity)→ Level 1 质量反馈重试 → Level 2 从 CW 重生成 → HITL 人工兜底。
4. **诚实信号(fail-honest)**。`missing_input_result()` 让门在输入不存在时报告 `skipped` 而非 `pass`;`AdapterRegistry.is_stub` 默认 `True`(不自动化直到证明可以);HITL 超时默认 `reject`(fail-closed);detector 宁可 `raise` 不编造;"刻意不写假数据"写进整改回执。
5. **红线制度**。AGENTS.md §5 的 9 条 MUST/MUST NOT(如禁止 agent `--force` 归档、禁止生产数据入库、禁止改 allowlist)由测试套件强制(`pytest -m redline`,实测 22 个标记用例)。注:README 两处仍写"10 条",与 AGENTS.md 的 9 条不一致,且该计数不在文档门禁覆盖范围内(见 §4.5.4)。
6. **单一权威声明**。`pipelines/gate_plan.py`(`MODE_GATE_NAMES`)是 9 个 mode 门序的唯一权威;`dag.py` 只描述依赖边并在 import 时自校验;runner 的 `_MODE_MAP` 只是同一对象的别名导出;测试钉死拓扑序与计划一致(2026-10 由 #314 落地,取代从前的三处副本)。
7. **深模块(Ousterhout)**。`prompts/`(109 行接口藏 4,573 行模板 + 4 层覆盖链)、`engines/`、`accounts/`、`asset_library/` 是范本;配置 6 层合并(内建默认 → 项目 → 用户 → override 规则 → override prompts → 环境变量);调度外部化(不自建 scheduler,外部 crond 调 `automedia cron run --due`)。
8. **文档即代码**。`scripts/check-doc-consistency.py` 从运行中的 server 派生 MCP 工具数、从 typer app 派生 CLI 命令数、从 loader 派生场景数、从 git 跟踪树派生 LOC/文件数/测试数——README/AGENTS.md 里的所有 headline 数字都是**被门禁校验的下界断言**,不允许手工漂移(#280/#308 的产物)。

### 2.2 落地核对(理念 vs 现状)

上述 8 条理念中,1/2/4/5/6/8 已真实落地且机制化;3(四级恢复)完整实现但集中在两个超长函数里(见 §四);7(深模块)呈现两极分化——`prompts/`、`engines/`、`accounts/` 是教科书级,而编排层 `runner.py`(2,165 行)/`gate_engine.py`(1,569 行)是"大实现 + 大接口"的反例。项目自 2026-09 起有完整的"诊断 → 报告 → 整改回执 → 门禁化"循环(health-assessment → remediation-report → audit),**10-22 审计发现的全部 P0 已在一周内修复**(见 §三)。

---

## 三、与既有审计的对照:一周内的修复情况

`docs/dev/codebase-audit-20261022.md`(尚未入库)列出 20 项新增问题。经本轮逐项核对,截至 2026-10-29(HEAD `9063f89`),其 P0 级已全部修复:

| 10-22 审计问题 | 当前状态 | 证据 |
|:--|:--|:--|
| P0-2 e2e 测试不被收集、`make test-e2e` 空转 exit 0 | ✅ 已修 | Makefile `test-e2e` 加 `-o addopts=""`(`Makefile:31-32`);nightly 在 `full-test` 作业内加了专门的 e2e 步骤(`nightly.yml:113-117`,非独立作业);`tests/test_e2e_collection_guard.py` 加了两条元测试钉死"收集数 > 0"与"Makefile 目标清空 addopts" |
| P0-3 `resume_from` 用占位符替代真实草稿 | ✅ 已修 | `runner.py:1328-1343` 从 `01_content/drafts/` 回灌草稿(`pipeline.resume.draft_rehydrated`),缺失时告警;`video_only` 的媒体旁白路径也会避开占位符改用 `source_content`(`_media_narration_text`,`runner.py:1941-1958`) |
| P0-4 `gate_engine.max_retries/retry_delay/max_regenerations` 配置不被读取 | ✅ 已修 | `_engine_retry_settings`(`runner.py:1396-1400`)读取,`runner.py:1419-1424` 传入 GateEngine |
| P0-1 V7 MD5 校验构造性恒真 | ✅ 已修 | `_expected_md5_records`(`runner.py:2017-2021`)只记 expected;`six_step_hard.py:88-91` 校验时从磁盘现算 actual |
| P0-1 V 门输入零生产者 → 恒 skipped | 🔄 结构性缓解 | `#315` 让 gate 报告 `skip_reason` 与输入是否存在(已有);`missing_input_result` 在 V0-V7 全部 8 门接入,但 V1/V3/V4/V6 的输入键在 `_produce_media_assets` 里被**刻意不写**(`runner.py:2032-2036`:「刻意**不写**的键…写了就是假数据」,涉 `entries`/`source_keywords`/`voice_id`/`avg_brightness`),故这几门在真实 run 中仍恒 skipped;"33 gates"的口径问题仍在(见 §4.7) |
| P1-1 门序三处副本 | ✅ 已修 | `#314` 抽出 `gate_plan.py` 单一权威(`runner.py:60` 的 `_MODE_MAP` 是指向同一对象的别名);`#324/#325` 清理 DAG 不可满足边并让声明序成为断言;`tests/test_gate_plan.py:71-75` 钉死拓扑序与计划一致 |
| P1-2 目录布局无单一真相源、`05_publish`/`06_publish` 撞号 | ✅ 已修 | `#312` `core/layout.py` 单一真相源;`05_publish` 仅作为 `LEGACY_PATHS` 别名保留读取路径(`layout.py:102-114`),不再有写入 |
| P2-1 GateHook 只读契约违反 | ✅ 已修 | `#321` 深拷贝上下文(`gates/_context.py:31-40` 的 `_detached` 递归拷贝)、逐 hook 异常隔离(`gate_engine.py:377-429` 的三个 `_dispatch_*`);死代码 `run_sub_pipeline`/`MetricsHook` 已删(grep 零命中) |
| P2-2 RFC-001 老化 70 天无机制 | ✅ 已修 | `#309` `scripts/check_rfc_aging.py` 有 findings 时返回 1 并 `sys.exit(main())`,CI 步骤为阻塞式(`ci.yml:45-49`) |
| P4-2 LOC/文件数/测试数无门禁 | ✅ 已修 | `#308` `scan_size_claims` 已接入文档门禁主路径(`scripts/check-doc-consistency.py:767`) |

**解读**:这个项目的修复节奏是"审计快照 → 一周内批量修复 → 把修复门禁化"。这本身是优点,但也说明其质量保证模式是**反应式**的——靠周期性人工审计驱动,而非持续防线(详见 §5.2)。

---

## 四、现存问题(本轮独立发现与核实)

以下问题均为 2026-10-29 当前代码仍然存在的,按严重度组织。

### 4.1 编排层代码形状(结构性债务)

1. **`GateEngine._run` 517 行、8 层控制流嵌套**(`gate_engine.py:933-1449`,AST 实测缩进最深达 10 级)。外层 while → 失败分支 → 内层质量重试 while → try → except;结果缝合处同样深。异常处理三段式(permanent/transient/Exception)在内层(:1154/:1190/:1223)与外层(:1332/:1357/:1387)**各重复一套**,`error_result` 字典构造出现 6 次(`:1165/:1201/:1235/:1343/:1368/:1399`),`if early_stop: return` 模式 11 处。这是全仓最该拆分的函数。
2. **超长函数与巨型签名**:`_build_pipeline_context` 197 行 / 19 个参数(`runner.py:1171-1367`);`_run_pipeline` 172 行(`runner.py:789-960`,23 个参数);`_select_gates` 4 层配置源叠加(`runner.py:1045-1133`)。
3. **`GateContext` 是 god object**:73 个 dataclass 字段塞进一个 dataclass+dict 双协议类,门级私有键靠 `# type: ignore` 绕过类型检查(`gate_engine.py:846`、`:1482-1486`;`runner.py` 内本身无 `type: ignore`)。V 门的输入契约(生产者必须用 `ctx[k]=v` 显式下标赋值而非字段赋值才能被 `was_written()` 识别)是**无类型强制的隐式约定**——`_result.py:233-259` 自述"skip 判据曾恒真导致条件化成死代码",证明这个双语义已造成过真实 bug。
4. **类型系统被绕过处**:`_build_gates_log` 把 `"awaiting_hitl"` cast 进一个不含该值的 Literal(`GateLogEntry.status` 声明 4 种值,`gate_engine.py:146`;实际出现第 5 种,cast 在 `runner.py:1802`),下游 gate-report 用"未知状态→review"兜底(`gate_report.py:120` 的 `_VERDICT_MAP.get(entry.status, "review")`)。
5. **残留耦合**:只读聚合器 `state_view.py:25` 与 `cli/commands/pipeline.py:28` 仍 import runner 的**私有名** `_MODE_MAP`(应为 `gate_plan.MODE_GATE_NAMES`,且前者拖着整个 runner 的 import 链);`VALID_MODES` 在 `runner.py:76` 与 `gate_plan.py:176` 各一份;`_filter_gates_by_tier` 在一次 run 中最多执行 6 次(`_compose_gate_list` 内的 2 处 × 最多 4 次调用 + `runner.py:1127` + `:1765`,幂等但冗余)。

### 4.2 潜在 bug 与竞态

1. **`md5_tracker` 的编码 bug(对本仓库路径直接相关)**:`core/md5_tracker.py:30` 用 `open(path)` 无 encoding 读、`:53-54` 用 `open(path,"w")` 无 encoding 写且 `ensure_ascii=False`。路径含非 ASCII 时(如 `D:\贯维\AutoMedia\...` 或中文项目名),Windows 下写入编码随 locale(GBK/cp936)漂移,跨环境读取会 `UnicodeDecodeError` 或乱码。此外 `record_md5` 是**无锁的读-改-写 + 非原子写**(无 tmp+rename),并发或中途崩溃可损坏 `pipeline_md5.json`。
   **不是孤立遗漏**:`omni/md5_integration.py:60` 与 `:69` 的 `load_state`/`save_state` 是同一份缺陷的第二个副本(同样无 `encoding=`、同样 `ensure_ascii=False`、同样非原子),写的是同名 `pipeline_md5.json`(`~/.automedia/`)。只修 `md5_tracker` 会留下第二个可损坏的状态文件;应一并修,并考虑把读改写收敛到一个带 tmp+rename 的共用原语。其余写点在 `src/` 内均已显式 `encoding="utf-8"`。
2. **`project_id` 键控的进程级注册表**(并发面比"全局单例"窄得多):`llm_client.py:133` 的 `_usage_tracker` 虽为模块级单例,但内部是 `threading.local()`(`llm_client.py:46-49`)——**每次 run 开头 `reset_usage_tracking()`(`runner.py:822`)只清当前线程**,已实测:A 线程累计 100 token,后台 B 线程 reset 后 A 仍是 100,不会互踩。真正残留的是按 project_id 键控的两处:`_hitl_waiters`(`gate_types.py:40-43`)与 `_engine_registry`(`gate_engine.py:91-92`),二者均有锁保护(`gate_types.py:38`、`gate_engine.py:92`),只有在**同一 project_id 并发 run**(典型是并发 `resume_project_id` 同一项目)时才互相覆盖。
3. **`owes_video` 启发式漏判**(`runner.py:937-942`):仅当调用方显式传 `platforms` 参数时才认定 auto 模式欠视频。注意 `mode` 在此之前已按品牌档案重新派生(`runner.py:987-992`),所以"品牌是多媒体平台但不传 `platforms`"这条路径确实存在:`mode` 变成 `auto`、`owes_video` 为 `False`,无视频产出也报 `success` 而非降级 `partial`——恰是该机制要防的"假绿"残留缺口。
4. **HITL 阻塞语义分叉**:`wait_for_hitl=True` 但 `progress=None` 时,`_resolve_awaiting_hitl`(`gate_engine.py:349-367`)不阻塞、直接单次文件轮询后 park,与 `GateEngine.__init__` 的参数文档"block at a gate returning `awaiting_hitl`"(`gate_engine.py:270-272`)不符。
5. **门配置四层叠加是"每层从 preset 重算"而非增量**(`runner.py:1058/1068/1081/1091` 共 4 次 `_compose_gate_list`):platform modifiers → YAML overrides → workflow gates 逐层重放 include/exclude,**前一层 include 的门会被后一层静默丢掉**。已实测:`text_only` 基础上先 include `G4` 得到 `[…, G4]`,再 include `G5` 后 `G4` 消失。override_failure_mode 又单独再 merge 一轮(`runner.py:1063-1100`),且 `_collect_gate_failure_overrides`(`runner.py:1678-1738`)内部重复加载 brand/YAML。两套合并语义并存,配置组合行为难以推理。
6. **媒体阶段"一次性"有两个真相源**:引擎本地 `_media_stage_done`(`gate_engine.py:948`)与上下文标志 `gate_context["_media_stage_done"]`(`runner.py:2152`)互相独立,`_produce_media_assets` 在 `finally` 里置位——**即使媒体生产中途异常也标记完成**,finalize 的幂等兜底不会重试;正确性依赖"先 engine 后 finalize"的调用顺序(`gate_engine.py:980-988`、`runner.py:1466-1472` 注释自述),顺序一改即破坏。
7. **顶层 catch-all 返回而非抛出**(`runner.py:959-960`):`except Exception` 把编程错误(AttributeError 等)折叠成 `status="failed"` 的正常返回,`error` 字段只有 `str(exc)` 无 traceback(`runner.py` 内 grep `traceback` 零命中)——对 SDK 调用方,bug 与业务失败同形,编程错误被静默产品化。

### 4.3 安全层

1. **路径 allowlist 的强制靠每个工具自觉调用,存在明确缺口**:
    - `analyze_content`(`effects/mcp.py:39-43`)接受任意 `base_dir` 却**零校验**,直接 glob 并读取项目文件——已实测:指向 allowlist 外的 `/tmp/...` 目录仍返回 `status: ok` 与完整统计。这是唯一完全漏网的文件读取工具(其余读盘工具至少调用了一次校验);
    - `distribute_content`(`mcp/tools_distribution.py:84-95`)与 `run_pipeline` 的 `source_path`(`mcp/tools/pipeline.py:176-182`)是 **fail-open**:校验失败仅告警/丢弃后继续执行(实测 `/etc` → 告警后回落默认目录继续);
    - `publish_content`(`mcp/tools/publishing.py:62-67`)的形态相反,但同样有问题:它**先**校验 `base_dir` 再回退,而 `base_dir=""` 时 `_require_allowed("")` 抛 `PermissionError`(属 `OSError`,被 `:182` 捕获),于是默认调用直接返回 `File I/O error: Path '' is not within any allowed directory`——**默认参数下工具不可用**(fail-closed 的可用性缺陷,不是绕过)。叠加出厂 allowlist(`mcp_allowlist.yaml:41-49`)只含 `./projects/`,而默认扫描目录是 `.automedia/output/projects`(`tools/_shared.py:243-248`),即使补上校验也会因为路径不匹配而拒绝;
    - `init_config`(`mcp/tools/setup.py:49-52`)接受任意 `project_dir` 写 `.automedia/` 目录,无校验(任意目录写原语),已实测可在 `/tmp` 下创建 `.automedia/config.yaml`;
    - 6 个 MCP resource(`mcp/resources.py`,注册于 `server.py:1180-1205`)整体豁免 allowlist。
    核心比较函数本身是正确的(双侧 realpath、空表 fail-closed:`allowlist.py:145-171`),问题在**没有集中式文件访问 choke point**,新增工具漏加一行检查不会被发现;`_require_allowed` 在 `src/automedia/mcp` 内共 15 处工具侧调用点(`omni.py:50,184`;`pipeline.py:178,526,580,633`;`projects.py:49,87,127`;`publishing.py:63`;`review.py:91`;`topics.py:62,315,360`;`tools_distribution.py:88`),全部靠人工逐个添加,没有任何机制强制覆盖 68 个工具。
2. **凭据加密的密钥派生过弱**:`accounts/store.py:83` 用无盐、无拉伸的裸 `SHA-256(master_key)` 派生 AES 密钥——对低熵口令可离线单次哈希爆破,标准做法是 PBKDF2/scrypt/argon2。nonce 用法正确(每次 `os.urandom(12)`,`:193`),缺省密钥快速失败正确,但:明文索引 `accounts.index.json` 存无盐指纹(`:100`;短 API key 可离线字典确认);无 KID/密钥迁移路径(换 master key 后所有旧记录 InvalidTag 且无重加密工具);密文文件写入非原子(`:205-206`;对照索引写入 `_save_index_atomic` `:141-149` 是原子的,tmp+rename 只做对了一半)。
3. **`keyring` 被产品代码直接 import**(`core/credential_loader.py:33`)但未在任何 extras 声明——`pyproject.toml` 内 grep `keyring` 零命中,`uv.lock` 内也没有。用户无法 `pip install automedia[keyring]`,装了 base 包的人 keyring 支持静默缺失(只留一条 warning)。

### 4.4 配置层

1. **环境变量的朴素下划线分割**(`config_loader.py:188-195`):`AUTOMEDIA_FOO_BAR_BAZ` → `{"foo":{"bar":{"baz"}}}` 按下划线切分,导致 (a) 任意 `AUTOMEDIA_*` 变量(含 `AUTOMEDIA_MASTER_KEY` 等敏感项)都会漏进合并配置成为嵌套键——已实测 `AUTOMEDIA_MASTER_KEY=x` 在合并结果里生成 `{"master":{"key":"x"}}`(MCP `get_config` 仍会因键名含 `key` 而打码,所以是配置污染而非泄露);(b) **绝大多数真实配置键(如 `content.min_title_length`)无法用环境变量设置**——已实测 `AUTOMEDIA_CONTENT_MIN_TITLE_LENGTH=10` 生成 `{"min":{"title":{"length":"10"}}}` 这个垃圾键,真实的 `content.min_title_length` 仍是默认值;只有 6 个 LLM 键 + tavily 走了手工重映射表(`:141-186`)。这是"看起来通用、实际只对白名单生效"的机制。
2. **Layer 2 吞掉项目目录下所有 YAML**(`config_loader.py:68-82`):`.automedia/` 下每个 yaml 按文件名排序依次 deep_merge,后者赢——文件名不携带优先级语义,排查配置来源需知道 sorted 顺序。
3. **ComfyUI 迁移块用对象身份判别**(`config_loader.py:391-408`):`new_comfyui is default_comfyui` 依赖 deep_merge 的拷贝实现细节(`deep_merge` 用 `base.copy()` 浅拷贝),任何人"优化"deep_merge 都会静默改变迁移语义。
4. 实际心智模型接近 **8 层**:6 层 + Layer 6 内部 `os.environ > .env overlay` 两级 + Layer 2 内部多文件排序。

### 4.5 接口一致性与重复

1. **CLI 与 MCP 存在真实双实现**:`cli/commands/omni.py:146-252`(`omni_localize`,107 行)与 `mcp/tools/omni.py:146-320`(`localize_output`,175 行)是同一个"扫 drafts → OLAdapter 翻译 → L4 门 → 写 06_publish/{lang}/"循环的两份平行实现,且已漂移:MCP 版返回 `l4_verdicts` 列表(`:196-295`)并**先做 allowlist 校验**(`:184`),CLI 版只把失败拼进 `warnings_list`、**完全无校验**。改 L4 行为必须改两处。
2. **分层倒置**:CLI `commands/cron.py:144,405,469,554` 反向 import MCP 层内部模块 `mcp/tools/_shared._read_pipeline_schedules`(下划线私有名,经 `tools/__init__.py:20` 再导出)。
3. **弃用别名是三层薄包装(不是名字交叉)**:`server.py:353-361` 定义一个同名新函数转发到 `tools.add_pool_topic`;注册处 `server.py:635-642` 用新名注册它,`:645-652` 用旧名注册 `tools/topics.py:383-391` 的旧函数——实测两个工具分别指向 `server.add_pool_topic` 与 `tools.topics.pool_add_topic`,**映射本身是对的**,问题是"一个能力三处定义 + 一层无意义转发"。
4. **AGENTS.md 参数表漂移**:`add_pool_topic | topic, category, source` 实际签名是 `title, category, pool_db_path`(`tools/topics.py:334-338`);`add_cron_schedule | schedule, command` 实际是 `name, expression, brand, category, count, platform, mode`(`cron_tools.py:35-43`)。计数类断言有门禁,参数表没有。同类漂移:`AGENTS.md` §5 是 9 条红线,README 两处仍写"10 条"(`README.md:300,554`),也不在门禁覆盖内(门禁只扫 README/AGENTS/index/doc-inventory 的**数字型**断言,不扫参数表与条目数)。
5. **MCP server.py 对 FastMCP 私有 API 的三处依赖**(`_tool_manager._tools` 反向构建注册表、monkey-patch `ToolManager.call_tool` 注入 correlation id,`server.py:431-465,1158-1164`)——上游升级地雷;68 个手写 `mcp.tool(...)` 注册(1,288 行单文件)。

### 4.6 工程卫生

1. **工作区物理污染**:`.gitignore` 覆盖大体到位,但复核时 `git status` 有 5 个未跟踪条目(`docs/dev/` 下 3 份分析文档 + `pkg-AutoMedia/` + `pkg-AutoMedia.zip`)——其中后两者**既未被忽略也未入库**,是真正的脏文件;`docs/dev/` 下的分析文档则应入库或显式忽略。(该计数会随工作进展漂移,写死数字没有意义,故此处只记录构成。)物理堆积方面,根目录有 **15 个按日期命名的测试项目目录**(`20261027_*` 至 `20261029_*`,每个含完整 11 个产物子目录),加上 `projects/` 下 7 个评审项目与回归夹具,全仓共 **24 个含 `00_project_info.json` 的项目目录**;另有 `build/`、`dist/`、`site/`、`logs/`(内容均为 `*.log`,已被忽略,只是视觉噪音)。每次 `ls`/glob/搜索都要穿过它们——纯粹的 agent 体验税,且按日期命名的测试目录会污染"按日期找项目"的启发式。
2. **评审类文档游离于索引之外**:`docs/dev/` 下的 codebase-audit / health-assessment / remediation-report / capability-gap 等文档未被 `docs/index.md` 收录(grep 零命中;`docs/doc-inventory.md` 虽列出其中三份,但那是自动生成的清单,不是导航),且 codebase-audit-20261022.md 尚未入库——项目最有价值的历史诊断对外不可见,入库即面临过期风险(其 §二 的实测数字已是 7 天前)。
3. **依赖上界策略不一致**:部分有上界(`typer<1`、`pydantic<3`、`cryptography<51`),部分裸奔(anthropic、rich、pymupdf、sentence-transformers、torch 无上界);`httpx` 核心 `>=0.27`(`pyproject.toml:34`)与 all extra `>=0.28`(`:74`)floor 不统一;`[tool.uv].constraint-dependencies` 的 anyio CVE 兜底只保护 uv.lock 用户,**pip 用户不受保护**——两种安装方式两种安全水位。
4. **coverage 门禁只在 3.11 生效**:`--cov-fail-under=70` 只跑在 matrix 的 3.11 上,3.12/3.13 的 Pytest 步骤是 `continue-on-error`(`ci.yml:118`);Windows 的 `test-windows-smoke` 作业本身**不是** advisory(作业与步骤都无 `continue-on-error`),但它只跑一个精选子集(`ci.yml:245-274`),不是全量。pre-commit 的 pytest 钩子每次提交跑全量 `pytest tests/ -x -q`(`.pre-commit-config.yaml:61`)——反馈回路成本高。

### 4.7 领域层的死重与同构(继承自 10-22 审计,现状未变)

- `G4`(wechat_checklist, 221 行)/`G5`(html_hard, 229 行)注册、有 DAG 节点(`pipelines/dag.py:87-88`)、有 failure_modes 条目(`gates/failure_modes.py:119-157`),但**无任何 preset 执行它们**(`gate_plan.py:16-21` 明示)——有意的开放核设计,但在 preset 路径上是死实现;
- `features/`(256 行)自述 MARKER,但**并非零调用点**:`_filter_gates_by_tier`(`runner.py:447-473`)会 import 并调用 `check_tier`,当 `AUTOMEDIA_FEATURE_TIER` 设成低于某门所属层级时该门会被真实剔除——开放核的声明式执法是接上的,只是默认无 override 时恒放行;`decision/`(308 行)里 `audit.py` 与 `review_audit.py` 是两份几乎相同的日志器(112 行),但 `decision/pydantic/` 才是被 3 个 MCP 工具实际使用的结构化输出层,不宜整体当作死重;`hitl/executor.py` 的 `_pending` 内存 dict 进程重启即丢;
- D1-D7 同构家族(7 个门,合计 2,273 行,前 3 个检查步骤与尾部的写盘/登记结构基本同形,仅 prompt 文本与阈值不同)、P1-P4 同一 3 步骨架 ×4(每门都是 rewrite → fact-check → humanize)——平台行为只能人肉 diff,不能比较(#287 已消除 D2/P2 的字面复制:`d2_twitter.py:23` 直接复用 `p2_twitter.split_into_tweets`,骨架同构仍在)。

---

## 五、综合评估

### 5.1 优势(值得保护,不要在重构中抹掉)

1. **诚实信号的一等公民设计**:`missing_input_result` → `skipped`、`skip_reason` 报告、`is_stub` 默认 True、HITL 超时默认 reject。这是整个仓库最有价值的契约。
2. **三入口同源 + 单一权威声明**(gate_plan / layout / platforms / 文档数字全部代码派生)。文档数字被门禁锁定后,"README 说谎"这类问题在这仓库已结构性不可能。
3. **深模块范本**:`prompts/`、`engines/`、`accounts/`、`asset_library/` 是小接口大实现的教科书,重构应复制它们而非拉平它们。
4. **红线测试化**(`pytest -m redline`)、**合成数据纪律**(`tests/fixtures/synth/`)、**AGPL 合规提示**、**issue 驱动原子提交**(ADR-005)——工程纪律在同类项目中罕见。

### 5.2 核心风险:质量保证是反应式的

10-22 审计的核心判断("局部诚实 + 全局幻觉")在一周内被大面积修复,证明团队的执行力;但同样一批问题在 2026-09-17 的健康度报告里已有前兆,而**发现它们的都是一次性人工审计快照,不是持续防线**。已建成的防线(文档一致性门禁、0-收集即失败的元测试、RFC 老化检查)方向正确但覆盖面窄——本报告 §四 列出的 allowlist 强制点缺口、`project_id` 注册表覆盖、编码 bug 等,现有任何 CI 检查都无法捕捉。(本轮复核本身也印证了这一点:初稿中"并发用量统计互踩""`publish_content` fail-open""`features/` 零调用点"三条均为读码推断而非实测,复核时被推翻——没有实测的静态审计同样会产出"局部诚实 + 全局幻觉"。)

### 5.3 问题优先级建议(按信号危害排序,仅判断不含排期)

| 优先级 | 问题 | 理由 |
|:--|:--|:--|
| 高 | allowlist 强制点缺口(§4.3.1)与 fail-open | 安全声明的边界与实际执行不符,是最典型的"看起来已验证" |
| 高 | `md5_tracker` + `omni/md5_integration` 编码/原子性(§4.2.1) | 中文路径下当前仓库就会踩,且两处副本写的是同名状态文件;损害 MD5 完整性验证本身的可信度 |
| 中 | `GateEngine._run` 拆分与异常模板去重(§4.1.1) | 最大、最集中的维护摩擦区;RFC-001 停摆期间它又长了 |
| 中 | `owes_video` 漏判、HITL 语义分叉、门配置重算式合并(§4.2.3-5) | 三处"静默地看起来能用"的残留 |
| 中 | CLI/MCP 双实现与分层倒置(§4.5.1-2) | 已经开始漂移,只会更糟 |
| 中 | 凭据 KDF 与索引明文(§4.3.2) | 离线爆破面 |
| 中 | `publish_content` 默认参数不可用(§4.3.1) | 工具在出厂配置下直接返回错误,属可用性缺陷而非安全问题;但会被 README 的能力声明掩盖 |
| 低 | `project_id` 注册表同 id 覆盖(§4.2.2) | 只在并发 resume 同一项目时触发,且有锁保护,危害面远小于初稿判断 |
| 低 | 死重模块、同构家族、工作区卫生、文档索引收录(§4.6-4.7) | 认知税与 AX 税,无功能危害 |

### 5.4 一句话结论

**这是一个把"内容生产的验收标准"编译成 33 道可执行门禁的系统,工程纪律显著强于同类项目,且具备罕见的自我诊断-修复闭环;它当前的主要债务不在功能完整性(一周内刚清完 P0),而在三处:编排层(gate_engine/runner)的形状、安全边界的"自觉执行"模式、以及两处共享状态文件与门配置合并语义的未定义行为——它们共同的特征是"信号看起来都对,直到非 ASCII 路径、默认参数或多层 include/exclude 叠加出现为止"。**

---

## 附录:证据文件索引

| 主题 | 关键文件 |
|:--|:--|
| 管线编排 | `src/automedia/pipelines/runner.py`(2,165 行)、`gate_engine.py`(1,569 行)、`gate_plan.py`、`dag.py`、`state_view.py` |
| 门禁 | `src/automedia/gates/`(43 文件)、`failure_modes.py`、`_context.py`、`_result.py` |
| MCP/CLI | `src/automedia/mcp/server.py`(1,288 行)、`mcp/allowlist.py`、`mcp/tools/`、`cli/app.py`、`cli/commands/` |
| 配置/安全 | `core/config_loader.py`、`core/llm_client.py`、`accounts/store.py`、`core/md5_tracker.py`、`omni/md5_integration.py` |
| 文档门禁 | `scripts/check-doc-consistency.py`(844 行) |
| 既有诊断 | `docs/dev/codebase-audit-20261022.md`、`project-health-assessment-20260917.md`、`remediation-report-20260917.md`、`founder-expectations.md` |
