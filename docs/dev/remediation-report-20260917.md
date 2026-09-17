# AutoMedia 整改执行报告（2026-09-17）

> **依据**：`docs/dev/project-health-assessment-20260917.md` §七「建议的处置优先级」
> **范围**：两批整改 —— 第一批为健康度报告的 P0/P1 项，第二批为用户指定的第 1–4 项
> **性质**：执行记录（做了什么、证据是什么、什么没做），不含排期
> **基线**：分支 `main`，HEAD `b11b132`

---

## 一、概览

| 批次 | 项目 | 状态 |
|:--|:--|:--|
| 第一批 | P0-2 解除 `fcntl` 硬依赖 + Windows 冒烟 CI | ✅ 完成 |
| 第一批 | P0-1 V 门显性化（`skipped` 成为一等状态）+ 按输入缺失条件化 | ✅ 完成 |
| 第一批 | P1-1 收窄 `mcp_allowlist.yaml` | ✅ 完成 |
| 第一批 | P1-3 给 `cta_principles` 接上真实消费者（CW 门） | ✅ 完成 |
| 第二批 | 1. 补视频产出链路（让 V 门拿到真实输入） | ✅ 完成（边界见 §六） |
| 第二批 | 2. `openai` 依赖加上界 | ✅ 完成 |
| 第二批 | 3. MCP 传输层鉴权 | ✅ 完成 |
| 第二批 | 4. `tests/test_pool_db.py` 的 22 项 Windows 失败 | ✅ 完成（该文件 0 errors） |

**改动规模**：57 个已跟踪文件（+1717 / −214），另有 5 个新增文件（1 个源码模块 + 4 个测试文件）。
按目录：`src/` 22 文件（+744/−115）· `tests/` 18 文件（+645/−31）· `scenarios/` 9 文件（+143/−53）· `docs/` 4 文件（+75/−14）。

---

## 二、第一批：健康度评估的 P0/P1

### P0-2 — 解除 `fcntl` 硬依赖 + Windows 冒烟 CI

| 改动 | 文件 |
|:--|:--|
| 顶层 `import fcntl` → 可选导入；抽出 `_file_lock()` 上下文管理器（POSIX `flock` / Windows no-op）；写路径改用 `os.replace` | `src/automedia/mcp/tools/_shared.py` |
| 补 `Operating System :: Microsoft :: Windows` / `:: MacOS` classifier | `pyproject.toml` |
| 新增 `test-windows-smoke` job（`windows-latest`，无 `continue-on-error`），含导入冒烟 + CLI help 冒烟 + 经本机筛选的 Windows 全绿子集 | `.github/workflows/ci.yml` |
| 新增跨平台锁的回归测试 | `tests/test_mcp/test_shared_file_lock.py` |

**关键事实**：修复前 Windows 上 `automedia.mcp` 整个包**无法导入**（本轮用 `git worktree` 拉 HEAD 复现：`ModuleNotFoundError: No module named 'fcntl'`）。

### P0-1 — `skipped` 成为一等状态 + V 门条件化

| 改动 | 文件 |
|:--|:--|
| `GateLogEntry.status` 扩为 `passed｜failed｜error｜skipped`；`_build_gates_log` 保留 `skipped` | `pipelines/gate_engine.py`、`pipelines/runner.py` |
| gate-report 的 verdict 映射增 `skip`，summary 增 `skipped` 计数（Markdown + HTML） | `pipelines/gate_report.py` |
| `_failing_gate` 只认 `failed`/`error`（不把跳过误报为失败门） | `cli/output_format.py` |
| 运行摘要图标三态化（`✓` / `⊘` / `✗`） | `cli/commands/run.py` |
| V0–V7 八个门在"必需输入未产出"时返回 `status="skipped"` | `gates/_result.py` + 8 个 V 门 |

### P1-1 — 收窄 MCP 路径白名单

删除 `mcp_allowlist.yaml` 中生效的 `- ./`（整仓读写），保留 `/tmp/automedia/`、`./data/`、`./output/`、`./projects/`；文件头注明"整仓访问需显式取消注释"；同步 `docs/user/mcp-setup.md`。

### P1-3 — `cta_principles` 接上消费者

`cta_principles` 此前被 schema 定义、被 onboard 采集、被 MCP 展示，但**无任何门读取**。现注入 CW（内容写作门）的 prompt，让原则真正指导 CTA 撰写；`add_brand` MCP 工具补该参数。

---

## 三、第二批：第 1–4 项

### 1. 补视频产出链路

**问题**：V0–V7 读取的 `gate_context` 字段在全仓 `src/` 内零生产者；且唯一写 `video_path` 的代码位于 `_finalize_pipeline`——它在**所有门跑完之后**执行，因此 V 门（以及 H0 人工复核）永远看不到媒体产物。

| 改动 | 文件 |
|:--|:--|
| `GateContext.was_written()`：区分"字段被生产者显式写出"与"仍是声明默认值" | `gates/_context.py` |
| `missing_input_result` 判据改用它（此前用 `key in ctx`，对已声明字段恒真 → **条件化是死代码**，见 §五） | `gates/_result.py` |
| `GateEngine` 新增可选 `media_stage` 回调，**在第一个 V 门之前**触发一次（默认 `None` ⇒ 既有调用方零行为变更） | `pipelines/gate_engine.py` |
| 新增媒体产出阶段：音频轨（TTS → 转写 → SRT）、图片、视频渲染、V7 产物清单；`_finalize_pipeline` 收敛为幂等兜底 | `pipelines/runner.py` |
| 新增测试：媒体产出 12 项 + 回调时机 5 项 + `was_written` 13 项 | `tests/test_media_production.py`、`tests/test_gate_engine.py`、`tests/test_gates/test_context_explicit_keys.py` |

**内容来源优先级**：CW 产出的 `content` → 源材料 `source_content` → 都没有则不产出。
**诚实边界**：只接通仓库内**已有实现能诚实产出**的输入；不可诚实产出的输入一律不写（详见 §六）。

### 2. `openai` 依赖加上界

`openai>=2.45.0` → `openai>=2.45.0,<3`（与 `litellm` 的 `openai<3.0.0` 约束一致）。
**依据**：实测环境中 `pip install -e ".[dev]"` 曾把 `openai` 升到 3.14.1，与 `litellm 1.84.0` 冲突（`pip check` 报 `litellm 1.84.0 has requirement openai<3.0.0,>=2.20.0, but you have openai 3.14.1`）。加界后 3.x 被排除、2.x 可选（已用 `packaging` 逐版本核对）。

### 3. MCP 传输层鉴权

| 改动 | 文件 |
|:--|:--|
| 新增传输层模块：`resolve_transport_config()` / `_EnvTokenVerifier` / `fastmcp_transport_kwargs()` | `src/automedia/mcp/transport.py`（新增） |
| `create_server()` / `main()` 按传输形态注入（stdio 默认不注入任何鉴权） | `src/automedia/mcp/server.py` |
| 文档 + 部署模板 + 环境变量样例 | `docs/user/mcp-setup.md`、`docs/user/deployment.md`、`deploy/systemd/automedia-mcp.env.template`、`.env.example` |
| 新增测试 15 项 | `tests/test_mcp/test_transport_auth.py`（新增） |

**安全姿态（fail-closed）**：`AUTOMEDIA_MCP_TRANSPORT=streamable-http` 而未设置 `AUTOMEDIA_MCP_AUTH_TOKEN` 时**拒绝启动**；默认仅监听 `127.0.0.1`；token 比较为常量时间。
**为什么 stdio 不做鉴权**：stdio 的 `initialize` 握手只携带客户端自报的 `clientInfo`，没有任何可校验的凭证——在那里做校验只是"看起来有鉴权"。

### 4. `tests/test_pool_db.py` 的 22 项 Windows 失败

**根因**：`pool` fixture 使用 `return PoolDB(db_path)`，**从不关闭连接**；Windows 上打开的 SQLite 句柄锁定 `.db` 文件，使 `db_path` fixture 的 teardown `os.unlink` 抛 `PermissionError [WinError 32]`。22 项失败**全部发生在 teardown**，测试体本身无问题（对照组：唯一显式关闭连接的 `test_context_manager` 一直是绿的）。
**改动**：`pool` fixture 改 `yield` + `finally: close()`；2 处测试体内裸建连接补显式 `close()`；新增 1 项"关闭后文件可删且无 WAL sidecar 残留"的回归断言。生产代码 `pool/db.py` 未改动（它本就提供 `close()`/上下文管理器）。
**结果**：该文件 `23 passed + 22 errors` → **24 passed, 0 errors**；并纳入 `test-windows-smoke` 子集以扩大 Windows 覆盖面。

---

## 四、验证证据

| 验证项 | 命令 / 方式 | 结果 |
|:--|:--|:--|
| CI Windows 冒烟子集（含新增测试） | 本机按 `ci.yml` 命令实跑 | **exit 0**（全绿） |
| 全量测试 | `pytest tests/ -q` | 77 failed / **0 errors**；失败全部落在既有 Windows 环境产物文件（`test_validation/*` 的 `python3`→9009、路径分隔符、`0o600`、symlink）；**改动与新增的测试文件零失败** |
| 无回归对照 | `git worktree` 拉 HEAD 与当前工作区跑同一最可疑测试 `tests/test_validation/test_hitl_live.py` | 两侧失败数**完全一致**（均 2 项） |
| 静态检查 | `ruff check src/automedia/ --ignore E501,E402,N806,E741` | All checks passed |
| 文档数字门 | `python scripts/check-doc-consistency.py` | exit 0 |
| 文档清单漂移门 | `python scripts/doc_inventory.py --check` | 已按 `git ls-files` tracked 集合 + LF 归一化同步 |
| 格式 | `ruff format --check`（改动文件） | already formatted |
| 新增测试 | 121 项（5 个文件） | 全绿 |
| MCP HTTP 形态 | 实机构造（`AUTOMEDIA_MCP_TRANSPORT=streamable-http`） | `streamable_http_app()` → Starlette、路由 `/mcp`、68 工具、无 token 时拒绝启动 |

---

## 五、本轮纠正的三个既有认知

1. **`missing_input_result` 在生产路径上是死代码**。`GateContext.__contains__` 对**任何已声明 dataclass 字段恒返回 `True`**（字段都有声明默认值），而该函数判据是 `key in gate_context` → 真实运行时永不跳过；只有测试传入普通 `dict` 时才生效。现以 `was_written()` 修正（`__contains__` 语义保持不变）。
2. **媒体产出的位置是错的，不只是"未接通"**。`_finalize_pipeline` 在所有门之后执行 → 即使补上生产者，V 门与 H0 人工复核仍看不到产物（即 H0 此前是在"还没有视频"的状态下进行复核的）。现以 `media_stage` 回调把产出移到第一个 V 门之前。
3. **提交态的文档清单门本就是红的**。`docs/doc-inventory.md` 有 6 行字节数与实际不符（`AGENTS.md`、`README.md`、`docs/dev/founder-expectations.md`、`docs/user/api-reference.md`、`docs/user/cli-reference.md`、`docs/user/mcp-setup.md`），即 `doc_inventory.py --check` 在 HEAD 上会失败——健康度报告 §六.4 关于该门"提交态一致"的结论与此不符。已修复。

---

## 六、诚实的边界与未做项

### 已接通 / 未接通的 V 门输入

| 门 | 输入 | 状态 |
|:--|:--|:--|
| V2 / V5 / V7 | `audio_path`、`transcription`、`whisper_text`、`srt_text`、`subtitles_path`、`required_files`、`file_sizes`、`md5_records` | ✅ 已接通（真实判定） |
| V0 / V1 / V3 / V4 / V6 | `lint_result`、`entries`、关键词、`voice_id`/`segments`、`avg_brightness` 等 | ⛔ **仍为 `skipped`**——仓库内没有能诚实产出它们的实现（无 lint 执行器、无抽帧与视觉 QA 裁决、无可信关键词提取、TTS 引擎不回传 `voice_params`、`opacity` 无法从已合成帧反推）。**刻意不写假数据** |

### 本机无法验证的部分

本机不存在 `edge-tts` / `whisper` / `ffmpeg` / `ffprobe` / `hyperframes`。因此"真实产出媒体文件"这一端到端路径**未在本机验证**：已验证的是"缺依赖 ⇒ 不写任何键 ⇒ V 门 skipped ⇒ 视频模式降级 `partial`"（真跑），以及"链路完整 ⇒ 键全部写入 ⇒ V 门不跳过"（mock 引擎全链路）。产出正确性由测试锁定，实际渲染需在有依赖的环境执行。

### 本轮明确未做（仅记录）

- `runner.py` 拆分（当前约 2100 行）、`core → pipelines/adapters` 架构倒置
- MCP 的工单级细粒度授权、`AUTOMEDIA_MCP_ALLOWLIST_PATH` 的方式实现（该环境变量在文档与部署模板中被承诺，但 `src/` 内无读取代码）
- 144 处宽 `except Exception`、77 处测试硬编码临时路径、4 套 agent 配置收敛
- 8 处 prose 仍写 "passed/failed/pending"（未含 `skipped`）
- journey 场景注释中的 `runner.py:NNN` 行号引用陈旧
- `pyproject.toml` 中 `dev` extra 的 `automedia-pipeline[httpx]` 疑似悬空引用（extras 清单无 `httpx`）

---

## 七、一句话结论

两批整改把健康度报告指出的"静默地看起来能用"逐项转成了**可见状态**：Windows 可安装可测试、V 门不再空洞通过也不再假失败、媒体产出落在正确的位置、MCP 有了真正的传输层鉴权；同时新增了针对性测试与一条 Windows CI 见证作业。**仍然欠缺的是能力本身**——视频/音频轨的输入生产者只在"仓库已有实现"的范围内接通，视觉与音频质量门的完整校验需要新增能力而非修复缺陷。