# LOOP-LOG — AutoMedia validation 循环记录

> **活跃文档（2026-09-07 自 archive 复活）** — 每次迭代循环（打包/验证/修复）的**关键事件、根因、修复、验证结果**必须记录在此。
> 机制对齐 AutoInfo 2026-08-15 规范 + 跨项目循环治理规范（validation-run-governance.md）：每次迭代**开始前**必复查「坑清单」，新坑当天追加（现象 → 根因 → 预防）。
> 历史归档版（2026-08-23 及以前）见 `docs/archived/validation-loop-log-20260823.md`。

## 坑清单（pitfall checklist，迭代前逐条对照）

（2026-09-07 复活。历史坑清单见归档版 `docs/archived/validation-loop-log-20260823.md`；新坑在此追加。）

- **坑 4（2026-09-13，现象→根因→预防）**：CI 全红，但失败源于「新规则落地时未同步既有主体」——3 个 doctor 场景在 error envelope 严格化后 failed。
  根因：新检查/新规则的 PR 只验证了「新东西本身通过」，没有跑既有全集。
  预防：任何改变步骤判定语义的规则，PR 必须同时跑全库（`--all`）**并贴出全部非 passed 场景清单**；不能只跑 affected 子集。已 gate 化：`error_expected` 的语义写进 `scenarios/README.md`（PR 见 issue #11）。
- **坑 5（2026-09-13）**：`test (3.11)` 红，断言「某 env 变量应缺失」却为 True。
  根因：测试模块在 **import 期**写 `os.environ` 且从不清除，pytest 在收集阶段就污染了整个进程；断言 env 缺失的测试因此必挂。
  预防：**禁止模块级 env 写入**，一律用 `monkeypatch`；`tests/conftest.py` 已加 import/collection 期泄漏闸（快照 → 比对 → `pytest.exit(1)`，issue #14 / PR #16）。
- **坑 6（2026-09-13）**：live-HITL 测试单独跑通过、连跑或 CI 偶发 `JSONDecodeError: Expecting value: line 1 column 1 (char 0)`。
  根因：三个独立缺陷叠加——marker 用 `write_text`（先截断后写，读者能看到空文件）、读者「存在即读」不重试、marker 是**固定全局路径**（跨运行/跨会话/并行 worker 互相读到对方的 marker）。
  预防：写侧原子化（临时文件 + `fsync` + `os.replace`）、读侧轮询到可解析非空 JSON、**跨进程共享的临时路径一律 per-run**（issue #15 / #17，PR #18 / #21）。
- **坑 7（2026-09-13）**：新增测试文件导致**排在它后面**的测试失败（committed 场景 `partial-pass-omni-extraction` 由 partial-pass 变 failed）。
  根因：测试真的跑了一次 pipeline 工具却没带隔离 fixture；更隐蔽的是它触发了**进程全局缓存**（`automedia.mcp.allowlist._cached_allowlist`）按 tmp cwd 解析并缓存，污染后续场景的真实路径解析。
  预防：有副作用的测试必须显式带隔离 fixture（重定向 config/projects/db **并 reset 进程级缓存**）；验证时用「小集合组合跑」定位顺序依赖，不要只看单文件绿（issue #13 验证期发现，PR #22）。

## 循环事件（major events，newest on top）

### 2026-09-13 backup/main 同步后发现 main CI 全红 → 6 个 issue → 6 个修复 PR

- 同步 `backup/main`（+30 commits，validation 体系强化）后发现 **CI 自本次 push 起全红**（`test (3.11)` / `checkov` / `validation-affected`），release PR（automedia 1.5.0）被同一批失败卡住。
- 逐条定位根因（全部在本机用真引擎/真测试复现，非看日志猜测）→ 提 5 个 issue：**#11**（doctor 场景缺 `error_expected` opt-in）、**#12**（checkov `CKV_SECRET_6` 命中红队夹具的合成金丝雀）、**#13**（correlation id 从未进 MCP 工具输出，使一个「故意红」的场景把 affected job 永久拖红）、**#14**（测试 import 期 env 泄漏）、**#15**（HITL marker 空文件竞态）；修复 #15 时发现更深一层的 **#17**（marker 固定全局路径）另立 issue。
- 维护者选定 #13 与 #17 均走「根治（选项 A）」：**#13** 把 correlation id 传播进工具输出（故意红场景转绿，PR #22）；**#17** 把 marker 改为 per-run 路径（PR #21）。
- 交付：PR **#16 / #18 / #19 / #20 / #21 / #22**（全部未 merge，按工作流留给维护者）。每个 PR 的验收都由验证侧独立复跑，并包含**纯 main 对照组**——用于区分「既存失败」与「本次引入」（#13 的一个 partial-pass 失败正是靠对照组才被判定为真实污染并打回修）。
- 已 gate 化的预防：import 期 env 泄漏闸（#14）；`error_expected` 语义写进场景文档（#11）；marker 原子写 + per-run 路径 + artifact 路径变量展开（#15 / #17）。

### 2026-09-07 LOOP-LOG 复活 + fix-retro 复盘机制接入

- 归档版（docs/archived/validation-loop-log-20260823.md）复活为活跃文档（docs/dev/），路径与 AutoInfo / omni suite 统一。
- 接入 GStack 工作流实施项 B：每轮修复完成后按 `fix-retro` skill 输出复盘块（5 问），追加到下方「复盘记录」段。

## 复盘记录（fix-retro，2026-09-07 起）

> 每轮修复完成后按 `fix-retro` skill 输出复盘块（5 问）追加到此段。目标：不只记坑，沉淀模式——根因分类统计 → 重复模式识别 → 预防措施 → 技能沉淀。复盘块的根因分类基于失败定性协议（validation-run-governance.md §2），不凭印象。

### 复盘（fix-retro @ 2026-09-13）

**本轮修了什么**（6 条，全部有 issue 号与 PR 号）:
- issue **#11**: 3 个 doctor 场景 deliberately 跑会 exit 1 的命令，却没声明 `error_expected: true` → CI `validation-affected` 红（PR #19）
- issue **#12**: 红队夹具里的合成金丝雀是连续字面量 → checkov `CKV_SECRET_6` 误报，`checkov` job 红（PR #20）
- issue **#13**: correlation id 有绑定、进了 run record，却从未进 MCP 工具输出 → 「故意红」的场景把 affected job 永久拖红，卡住 release（PR #22，产品修复）
- issue **#14**: 测试模块 import 期写 `os.environ` 且不清除 → 污染整个 pytest 进程，打挂 env-gate 测试（PR #16）
- issue **#15**: HITL marker 非原子写 + 读者「存在即读、不重试」 → 空文件竞态（PR #18）
- issue **#17**: HITL marker 是固定全局路径，被 fixture 与两个场景共享 → 跨运行/跨会话/并行污染（PR #21，per-run 根治）

**根因分类统计**（基于失败定性，非印象）:
| 类型 | 数量 | 例子 |
|------|------|------|
| 环境/配置 | 3 | #11 新判定规则未同步既有场景；#12 扫描器对合成夹具误报；#14 import 期 env 泄漏 |
| 边界/空值/竞态 | 1 | #15 读者拿到被截断后的空 marker |
| 设计缺陷（跨运行共享可变状态） | 1 | #17 固定全局 marker 路径 |
| 产品能力缺口 | 1 | #13 关联 id 未传播到工具输出 |

**模式识别**（重复出现的根因 → 系统性问题）:
- **模式 1：新规则/新设施落地时，只验证「新东西本身」，未验证「既有全集」**（出现 3 次：#11 判定语义变更、#12 新增夹具、#17/#15 新增 live-HITL 设施）。
  系统性解读：场景 / 检查 / 夹具三者的约定没有单一权威源，且没有「变更判定语义必须回归全库」的硬性步骤；因此失败以「CI 全红，但很难一眼看出是谁的责任」的形式暴露。
- **模式 2：测试与 harness 共享进程级或文件系统级全局状态**（出现 4 次：#14 import 期 env、#15 全局 marker、#17 全局路径、#13 验证期发现的进程全局 `_cached_allowlist`）。
  系统性解读：pytest 会话内的隐式状态既无 guard 也无 reset 规范。隐式依赖一旦存在，失败的表现形式是「看起来是别人的测试挂了」——本轮 #13 的 partial-pass 失败、以及 #11 被误判为「场景本身坏了」都属此类；只有**对照组**（同一命令跑纯 main）能切开责任。
- **模式 3（源自历史）：「坑清单已记录但未 gate 化 → 原样复发」**。历史坑清单里已有「模块副本同步」「全局临时路径」类记录，本轮仍出现 #15/#17 的全局路径问题；说明「记在文档里」不足以预防，必须变成可执行闸。

**预防措施**（哪些可以 gate 预防而非事后修）:
- **判定语义类规则的迁移检查**：任何修改步骤通过/失败语义的 PR，必须跑全库 `--all` 并在 PR 里贴出所有非 passed 场景 + 逐个解释（gate：PR 模板 + reviewer 检查；#11 的教训）。
- **import/collection 期 env 泄漏闸**（已落，PR #16）：任何模块级 env 写入当场让会话中止并报出变量名与 baseline→now。
- **跨进程共享临时路径约定**（已落，#15/#17）：一律 per-run 目录 + 环境变量传递；`collect_artifacts` 支持变量展开；禁止新增固定全局 scratch 路径。
- **进程全局缓存的测试纪律**（#13 验证期发现）：有副作用的测试必须带隔离 fixture 并 reset 进程级缓存，本次已在 `isolated_env` 中覆盖 `_cached_allowlist`。
- **验证必带对照组**：任何「某 PR 引入失败了吗」的判断，都要跑一次纯 main 的同一命令；没有对照组就不下结论。

**沉淀**（新的 skill/checklist/坑清单条目）:
- 坑清单新增坑 4–7（见上）。
- `opencode-orchestration` skill 新增三条：①新检查的作用域过宽时，子进程会去「修爆炸半径」（改被误报的文件）→ 必须 kill 并重写 brief，让闸对准真实缺陷类；②子进程沙箱禁止 `/tmp` 写入与重型工具链安装 → scratch 放工作目录内、用底层小库替代大工具做验证；③切修复分支前先回 `main`（否则新分支带着上一个修复的提交）。
- 通用工作法：**「验证者独立复跑 + 纯 main 对照组」** 是本轮识别出真实污染（#13）与排除既存失败（#11 的同类扫描）的关键手段；修复者自报不可作为验收依据。
