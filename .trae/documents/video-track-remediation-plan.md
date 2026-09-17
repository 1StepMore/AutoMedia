# AutoMedia 视频轨接通 + 依赖/鉴权/测试修复实施计划（v2 — 自查修订版）

> 依据：本轮任务 1–4（源自 `docs/dev/project-health-assessment-20260917.md` §七）
> 用户指令：「做 1-4。复杂任务先 plan 后 implement」
> 验收：现有测试不回归 + 每项改动新增针对性测试

---

## 〇、范围（严格限定）

**本轮做**：① 补视频产出链路 ② `openai` 依赖加上界 ③ MCP 传输层鉴权 ④ `tests/test_pool_db.py` 的 22 项 Windows 失败
**本轮不做**（仅在本轮结束时报告，见 §十一）：`runner.py` 拆分、架构倒置、宽 `except` 治理、未跟踪文档收敛、journey 行号漂移、`docs/doc-inventory.md` 的依赖提交顺序问题

---

## 一、Context — 必须先纠正的三个既有认知（本轮实测）

| # | 发现 | 证据 |
|:--|:--|:--|
| **A** | **上轮的「V 门条件化跳过」在真实运行路径上是死代码** | `gates/_context.py:206-212` 的 `__contains__` 对**任何已声明 dataclass 字段恒返回 True**（`:175-177` 判据 = `key in type(self).__dataclass_fields__`）；`gates/_result.py:225` 用 `any(key in gate_context ...)` → 生产路径（`runner.py:1270` 传 `GateContext`）**恒返回 None**，永不跳过。仅测试传普通 dict 时生效 |
| **B** | **故现网行为比"未接通"更糟** | 当 `hyperframes_available=True`（`runner.py:1306`：用户装了 hyperframes 或 ffmpeg）而媒体链路未接通时，V 门**不跳过，而是拿空默认值跑真实判定并失败**（V1 `entries=[]` 全 fail、V2 `transcription=""` 长度不足、V6 四项恒失败）。门 docstring 声称的 "honest skip" 并未实现 |
| **C** | **媒体产出的位置是错的** | `_finalize_pipeline`（`runner.py:1390`）由 `runner.py:1035` 在**所有门之后**调用 → 即便补上生产者，V 门与 H0 仍看不到产物。**H0 人工复核当前也是在"还没有视频"的状态下进行的** |

### V 门输入可产出性复核（逐门实测）

| 门 | 必需输入 | 判定 | 依据 |
|:--|:--|:--|:--|
| V2 `pre_send_whisper` | `transcription`+`audio_path` | ✅ 可产出 | `AudioPipeline.generate_tts`（`audio_pipeline.py:134`）+ `transcribe_audio`（`:208`） |
| V5 `mp3_vs_srt` | `whisper_text`+`srt_text` | ✅ 可产出 | 同上 + `generate_srt`（`:296`）落盘读回 |
| V7 `six_step_hard` | `required_files`/`file_sizes`/`md5_records` | ✅ 可产出 | `hooks/md5_tracker.py:21 _compute_md5` 已有，需结构适配 |
| V6 `subtitle_render` | `avg_brightness`/`contrast`/`opacity`/`pixel_valid` | ❌ 不可诚实产出 | `opacity` 无法从已合成帧反推（alpha 已烘焙）、`contrast` 无字段定义、`pixel_valid` 无判据 |
| V0 `lint` | `lint_result` | ❌ | 全仓无 lint 执行器/解析器（仅 `templates/hyperframes/package.json:6` 的 npm 脚本） |
| V1 `vision_qa` | `entries` | ❌ | 无抽帧实现、无 `qa_passed` 裁决器、无帧命名约定 |
| V3 `content_semantic` | `source_keywords`+`content_keywords`+`source_texts` |  | 仅标题级朴素切分（`pool/collector.py:284`），无法诚实支撑 80% 覆盖率判据 |
| V4 `tts_brand_asset` | `voice_id`+`segments`(含 `voice_params`) | ❌ | TTS 引擎只返回路径，`voice_params` 全仓零生产者 |

**本轮接通 V2/V5/V7；V0/V1/V3/V4/V6 保持 `skipped`**（修好发现 A 之后此状态才真正生效）。**绝不为"让门不跳过"而写假数据。**

---

## 二、任务 1 — 补视频产出链路

### 2.1 位置问题与方案对比

媒体产出必须落在 **CW 之后、V 门之前**（内容由 CW 门产出，V 门校验媒体）。

| 方案 | 做法 | 优点 | 代价 | 判定 |
|:--|:--|:--|:--|:--|
| **A. 新增「媒体产出门」** | 加 `MG` 门插进 5 个预设的 V 门之前 | 概念整齐（CW 是"产出的门"先例） | **11 处登记义务、7 处被现有测试拦下**：`FEATURE_TIERS`（`features/__init__.py:45-88`，漏登记会 `ImportError` 导入即炸）、`test_runner.py:152` 精确列表、`test_dag.py:48-53/187-192`、`test_standards.py:118`(`len==33`)、`coverage-audit.json` 重生成（CI 字节 drift）、5 处文档门数 + `test_doc_reality.py`、`failure_modes.py` + `test_failure_modes.py` | ❌ 否决 |
| **B. 两段 `engine.run()`** | runner 拆两段，中间产出 | 引擎零改动 | regeneration 跨段断裂（V5 是 `retry` 门，level 2 需重跑 CW）；`success`/`results`/pause 状态手工拼接 | ❌ 否决 |
| **C. 引擎新增可选 `media_stage` 回调（采用）** | `GateEngine` 加一个可选回调，在**第一个 V 门之前**调用；runner 在 `_finalize_pipeline` 再幂等兜底一次 | 引擎改动极小；**默认 None ⇒ 现有 4,726 测试零行为变更**；**零登记义务**（文档数字/DAG/features/STANDARDS/baseline 全不变）；单次 run 语义完整 | 需在 `_run` 内注入判定位；需保证幂等 | ✅ **采用** |

**方案 C 的关键性质**：回调触发点"第一个 V 门之前"在 5 个含 V 门的预设里恰好等价于"文本轨门之后"（`auto`/`short-video`/`repurpose`：CW 之后；`video_only`：无文本门故即循环开头；`qa_only`：G 门之后），因此它对所有模式天然正确。

### 2.2 修改项（4 处，可独立验证）

#### 修改 1（必要前提）：让"是否产出过"成为可判定的 —— 新增 `was_written()`，**不动 `__contains__`**

**`src/automedia/gates/_context.py`**
- 新增"显式写入登记"：在 `__setitem__` 的 dataclass 字段分支里把键名记入 `self.extra["_explicit_keys"]`（集合）。
- 新增方法 `was_written(key: str) -> bool`：返回该键是否被显式写入过（走 `_resolve` 别名）。
- **`__contains__` 一个字符都不改** ← 与 v1 计划的关键差异：避免改动核心数据结构的语义（v1 曾计划改 `__contains__`，虽已穷尽核实无依赖点，但"新增方法"比"改语义"风险更低且无需任何迁移审计）。
- 只认 `__setitem__`，不认构造参数：V 门所需的 8 个键在生产路径**从不由构造参数写入**（`runner.py:1270` 只传 topic/brand/project_id/project_dir/config/tenant_id/lang_config/mode/force_provenance/brand_profile/correlation_id），而生产者一律用 `ctx[key] = value` → 语义单一、无"值 == 默认值"边界。

**`src/automedia/gates/_result.py`**
- `missing_input_result` 的判据改为"**全部必需键都未被显式写入 ⇒ skipped**"，用 duck-typing 探测：

  ```python
  probe = getattr(gate_context, "was_written", None)
  written = probe if callable(probe) else (lambda k: k in gate_context)  # 普通 dict 语义不变
  if any(written(k) for k in required_keys):
      return None
  ```

- docstring 同步：保留"存在性而非真值性"的原有论证，并把"存在性"精确定义为"被生产者显式写入"。

**风险面**：`__contains__` 语义零变更；`_result.py` 的改动只影响 V 门路径（8 个调用点），且 8 门的既有"缺输入 ⇒ skipped"测试均传 `execute({})`（普通 dict）→ **断言不翻转**。

#### 修改 2：`GateEngine` 新增可选 `media_stage` 回调

**`src/automedia/pipelines/gate_engine.py`**
- `__init__` 加 keyword-only 参数 `media_stage: Callable[[GateContext | dict[str, Any]], None] | None = None`（默认 `None`）。
- `_run` 门循环内（`gate = self._gates[_gate_loop_idx]`、`gate_name` 求出之后）插入：

  ```python
  if (
      self._media_stage is not None
      and not _media_stage_done
      and gate_name.startswith("V")
  ):
      _media_stage_done = True
      self._invoke_media_stage(gate_context)
  ```

- 新增私有 `_invoke_media_stage`：`try/except Exception` → `log.warning`（**产出失败绝不让门循环崩溃**；失败表现为 V 门随后 skipped）。
- `_media_stage_done` 是 `_run` 的局部变量（每次 run 独立）。
- **不改** `run` / `run_with_results` 的公开签名；`GateEngine(gates)` 的单参构造在全部测试中继续有效。

#### 修改 3：`runner.py` 新增 `_produce_media_assets`（搬移 + 扩展）

新增模块级函数 `_produce_media_assets(gate_context) -> None`，所需一切（`content`/`topic`/`brand`/`project_dir`/`config`）从 ctx 取 → 可直接作为回调。

- **幂等**：入口若 `gate_context.get("_media_stage_done")` 为真则立即返回；出口写 `gate_context["_media_stage_done"] = True`。
- 按模式（把 `_finalize_pipeline` 现有两段搬来 + 扩展）：

| 模式 | 动作 |
|:--|:--|
| `image-carousel` | 搬 `runner.py:1408-1431`（`carousel_images`） |
| `text_with_cover` | 搬 `runner.py:1433-1455`（`cover_image`） |
| `auto` / `video_only` / `short-video` | **新增**媒体链路（下） |

- **媒体链路（新增）**，内容来源优先级：`content`（且非 `[content skipped in ...]` placeholder）→ `source_content`（源材料，`runner.py:1337` 已有生产者）→ **都不满足则不产出**（诚实：无内容可配音）。产物按**两组**独立写入（不搞"全或无"的过度耦合）：

  | 组 | 产出步骤 | 写入的 ctx 键 | 对应的门 |
  |:--|:--|:--|:--|
  | 音频组 | `shutil.which("edge-tts")` + `shutil.which("whisper")` 均可用 → `AudioPipeline.generate_tts` → `transcribe_audio` → `generate_srt` → 读回 SRT | `audio_path`、`transcription`、`whisper_text`、`srt_text`、`subtitles_path` | V2、V5 |
  | 视频组 | 音频组成立 + 图片（`generate_fallback_frame`）+ `resolve_engine("video")` 可用 → `_collect_video_assets` + `render` | `video_path` | —（供 `_VIDEO_PRODUCING_MODES` 降级判定与 H0 复核） |
  | 产物组 | 上述实际产出的文件 | `required_files`、`file_sizes`、`md5_records`（`{path: {"expected": md5, "actual": md5}}`，用 `md5_tracker._compute_md5`） | V7 |

- **明确不写**：`entries`/`lint_result`/`source_keywords`/`content_keywords`/`source_texts`/`segments`/**`voice_id`**/`avg_brightness`/`contrast`/`opacity`/`pixel_valid`（不可诚实产出 → 保持 skipped，见 §一 表）。
  > **实施修订（v2.1）**：`voice_id` 从"音频组写入"中移除。V4 的必需键是 `voice_id` **+** `segments`，只写前者会让 `missing_input_result` 判定"有输入"→ 门拿空 `segments` 跑真实判定 → 失败停机，而 `voice_params` 在仓库内没有生产者。少写一个键才是诚实的。
- 依赖探测用 `shutil.which`（`shutil` 已在 runner 导入），先探测后调用，避免靠异常兜底。

#### 修改 4：接线与 finalize 收敛

- `_setup_and_run_engine`（`runner.py:1363`）构造 `GateEngine(...)` 时传 `media_stage=_produce_media_assets`。
- `_finalize_pipeline`（`:1390`）：删除已搬走的 3 段，改为**开头幂等调用一次 `_produce_media_assets`** —— 覆盖"无 V 门的模式"与"门提前 stop 返回"两条路径，行为与现状等价。保留 `video_produced` 降级判定（`:1489-1499`）与报告生成。

**行为变化（如实告知）**：
- 配好引擎后，`short-video`/`auto`（CW 写了内容）与 `video_only`（给了 `--source`）会**真正产出媒体**，V2/V5/V7 首次真实校验 → 真实缺陷会**停机**（正确行为）。
- `video_only` 首次拥有一条可走通的真实路径：**用户提供源材料即可产出视频**（此前该模式只能拿 `[content skipped]` 占位符）。
- 未配引擎：音频组因缺命令不写键 → V2/V5 跳过；视频组不成立 → `video_path` 不写 → 视频模式降级 `partial`（上轮已实现，本轮才真正生效）。

### 2.3 验收边界（诚实声明）

**本机环境实测：`edge-tts` / `whisper` / `ffmpeg` / `ffprobe` / `hyperframes` 全部不存在**。因此：

| 可验证 | 方式 |
|:--|:--|
| 缺依赖 ⇒ 不写键 ⇒ V2/V5/V7 skipped ⇒ 视频模式 partial | **本机真跑**（多模式实跑 + 断言具体 `status` 与门状态） |
| 完整链路 ⇒ 键全部写入 ⇒ V 门不跳过且真实判定 | **mock 引擎**（假 TTS/ASR/SRT/图片/视频产出临时文件）+ 断言 ctx 键与门结果 |
| 真实媒体产出（真 mp3/mp4） | **本机不可验证**，需在有依赖的环境执行；本轮不以"真实产出"作为完成判据 |

---

## 三、任务 2 — `openai` 依赖加上界

`pyproject.toml:51`：`openai = ["openai>=2.45.0"]` → `["openai>=2.45.0,<3"]`
依据：`litellm` 的约束是 `openai>=2.20.0,<3.0.0`；实测本机被升到 3.14.1 造成冲突。
验证：`pip check`（应无 litellm/openai 冲突）+ `python -c "import openai; print(openai.__version__)"`。
**不擅自**给 `anthropic`/`rich` 加上界（无冲突证据）。

---

## 四、任务 3 — MCP 传输层鉴权

### 4.1 实机结论（本轮已实测，非推断）

| 问题 | 实测结论 |
|:--|:--|
| streamable-http + Bearer token 能否落地 | ✅ **能**。自写 `TokenVerifier` + `AuthSettings` 端到端跑通：无 token / 错 token → **401**，正确 token → **200** |
| stdio 形态下能做的最强校验 | ❌ 仅"客户端自报的 `clientInfo.name`"（`InitializeRequestParams` 只含 `task/meta/protocolVersion/capabilities/clientInfo`），客户端任意编造 → **不构成鉴权** |
| 能否挂在 `_instrument_tool_dispatch` | ✅ 可以，但无请求上下文时必须默认放行（`srv.call_tool` 直调时 `context.request_context` 抛 `ValueError`） |
| `lifespan` 能否做启动期校验 | ✅ stdio 下会被调用（`lowlevel/server.py:663`，与传输无关） |

装配契约（`mcp==1.28.0`）：`token_verifier` 与 `auth` **必须成对**否则 `ValueError`（`fastmcp/server.py:218-224`）；`AuthSettings.issuer_url` 必填 `AnyHttpUrl`；`TokenVerifier` 协议只要求 `async verify_token(token) -> AccessToken | None`。

### 4.2 方案对比

| 方案 | 做法 | 优点 | 代价 | 判定 |
|:--|:--|:--|:--|:--|
| **A. HTTP transport + Bearer 鉴权（采用）** | `AUTOMEDIA_MCP_TRANSPORT=stdio\|streamable-http`（默认 stdio）+ `AUTOMEDIA_MCP_AUTH_TOKEN`；HTTP 形态注入 `auth` + 自写 `_EnvTokenVerifier`；**HTTP 且未设 token ⇒ 拒绝启动** | 真正回应"传输层鉴权"；stdio 默认零变更；实测可用 | 新代码约 80 行 + 文档 + 部署模板 | ✅ **采用** |
| B. stdio 内启动期校验 + 工具白名单 | `lifespan` 校验 env；`AUTOMEDIA_MCP_TOOL_ALLOWLIST` 限制工具集 | 改动更小 | **不是鉴权**（同进程 env 恒相等），只是"授权收窄" | ❌ 仅作为备选写入文档说明 |

### 4.3 修改项

- **新增** `src/automedia/mcp/transport.py`：`_EnvTokenVerifier`（`secrets.compare_digest` 常量时间比较）、`resolve_transport_config()`（读 `AUTOMEDIA_MCP_TRANSPORT/HOST/PORT/AUTH_TOKEN`；HTTP 无 token ⇒ 抛 `ValueError` 并给配置指引）、`build_fastmcp_kwargs()`（返回 `auth`/`token_verifier`）。
- **改** `src/automedia/mcp/server.py`：
  - `create_server()` **签名保持为空**（52 处测试依赖）；内部按配置注入，stdio（默认）不注入 auth。
  - `main()`（`:1217-1250`）按 transport 分派 `server.run(transport=...)`；HTTP 形态打印监听地址 + "Bearer 鉴权已启用"。
- **文档同步**：`docs/user/mcp-setup.md` 新增"HTTP 部署与鉴权"小节 + 更新 Security Notes（`:302-307`）；`deploy/systemd/automedia-mcp.env.template` 与 `.env.example` 各补 3 个变量。

**安全姿态**：默认仅 `127.0.0.1`；HTTP 无 token fail-closed；token 比较用常量时间；**stdio 默认路径的 68 工具与 52 处测试调用方式完全不变**。

---

## 五、任务 4 — `tests/test_pool_db.py` 的 22 项 Windows 失败

**根因（已实证）**：22 项**全部在 fixture teardown 阶段**失败（`tests/test_pool_db.py:24-25` 的 `os.unlink` 抛 `WinError 32`），测试体全通过。`pool` fixture（`:28-31`）`return PoolDB(db_path)` **从不关闭连接** → Windows 上打开的 SQLite 句柄锁定 `.db`。唯一通过的 `test_context_manager`（`:163-169`）因在 `with` 块内关闭而幸免。

**实证**：`pool` fixture 改 `yield` + `close()` 后错误 **22 → 2**；残余 2 项是测试体内裸建连接的 `test_db_file_created`（`:50`）与 `test_migration_adds_tenant_id_if_missing`（`:146`）。

**改动（仅测试层，`src/` 零改动）**：
- `tests/test_pool_db.py`：`pool` fixture 改 `yield` + `try/finally: close()`；上述 2 处测试体内补显式 `close()`。
- sidecar（`-wal`/`-shm`）清理**仅在实测有残留时**才加（最小改动）。
- `src/automedia/pool/db.py` **不动**（已提供 `close()`/`__enter__`/`__exit__`；加 `__del__` 无效——teardown 的 unlink 早于对象回收，已实证）。

**验证**：`pytest tests/test_pool_db.py -q` 在本机 Windows 全绿；并把该文件加入 `test-windows-smoke` 子集（`.github/workflows/ci.yml`），扩大 Windows 覆盖面。

---

## 六、子任务 → 验证映射（每项可独立完成与验证）

| 子任务 | 完成即验证 |
|:--|:--|
| T2 `openai` 上界 | `pip check` 无冲突；`pyproject.toml` 行变更 |
| T4-1 `pool` fixture 改 yield+close | `pytest tests/test_pool_db.py -q` → 全绿（本机 Windows） |
| T1-1 `was_written()` + `missing_input_result` 改判据 | `pytest tests/test_gates tests/test_lint.py …（8 门）` 全绿 + 新增锁定测试；**真实 GateContext 下未写键的门现在 skipped** |
| T1-2 `GateEngine.media_stage` | `pytest tests/test_gate_engine.py tests/test_runner.py tests/test_e2e/` 全绿（默认 None ⇒ 零变更）+ 新增"调用时机"测试 |
| T1-3 `_produce_media_assets` | 新增测试：幂等 / 缺依赖不写键 / mock 链路写键 |
| T1-4 runner 接线 + finalize 收敛 | 多模式实跑断言具体 `status`；`pytest tests/test_e2e/ tests/test_runner.py` 全绿 |
| T3-1 `transport.py` | 新增测试：默认 stdio / HTTP 无 token 抛错 / token 比对正确与错误 |
| T3-2 server 分派 + 文档 | `pytest tests/test_mcp -q` 全绿（52 处 `create_server()` 调用不变） |

---

## 七、新增测试清单（验收硬性要求）

| # | 文件 | 用例 |
|:--|:--|:--|
| 1 | `tests/test_gates/test_context_explicit_keys.py`（新） | `__setitem__` 后 `was_written` 为真；构造参数写入不算；非字段键（extra）行为；`missing_input_result` 在"部分键已写"时不跳过、在"全部未写"时跳过 |
| 2 | 8 个 V 门测试（增） | **传真实 `GateContext` 实例**（非 dict）+ 未写键 ⇒ `status == "skipped"` ← 回归锁定发现 A |
| 3 | `tests/test_gate_engine.py`（增） | `media_stage` 在第一个 V 门**之前**被调用（用记录调用序的假门）；默认 None 时不调用；回调抛异常时门循环继续 |
| 4 | `tests/test_runner.py`（增） | `_produce_media_assets` 幂等；无内容来源 ⇒ 不写任何 V 键；`shutil.which` 返回 None ⇒ 不写键 |
| 5 | `tests/test_media_production.py`（新） | mock 全链路（TTS/ASR/SRT/图片/视频 → 临时文件）⇒ `audio_path`/`transcription`/`whisper_text`/`srt_text`/`video_path`/V7 三键全部写入；V2/V5/V7 **不再 skipped** |
| 6 | `tests/test_runner.py`（增） | 真实 GateContext + 无媒体 ⇒ `video_only`/`short-video` `status == "partial"`（上轮断言在新判据下仍成立） |
| 7 | `tests/test_mcp/test_transport_auth.py`（新） | `resolve_transport_config()`：默认 stdio；HTTP 无 token ⇒ `ValueError`；`_EnvTokenVerifier` 正确/错误 token；`build_fastmcp_kwargs()` 在 stdio 下返回空 |
| 8 | `tests/test_pool_db.py`（改） | 22 项全绿即修复本身；补 1 条"fixture 关闭连接后 db 文件可删"的回归断言 |

---

## 八、文档同步义务

| 触发 | 动作 |
|:--|:--|
| 改 `docs/user/mcp-setup.md` | 同步 `docs/doc-inventory.md:52` 的字节数 —— 用 **`git ls-files` tracked 集合 + LF 归一化**重建后逐行 diff，**不要**直接跑 `doc_inventory.py` 覆盖（本机有 4 个未跟踪 docs，会让 CI 该门变红） |
| 改 `.env.example` | 无 inventory 义务（不在 `docs/` 内）；MCP 的 3 个新变量由 `transport.py` 直读，不进 6 层合并（避免与 `config_loader` 的 env 层语义混淆） |
| 任何 `docs/` 改动后 | `python scripts/check-doc-consistency.py` 必须 exit 0 |

**已核实不受影响**：门计数（33）、MCP 工具数（68）、CLI 命令数（19）、场景数（142）—— 任务 1 不加门、任务 3 不加工具。

---

## 九、全量验证命令

```powershell
$env:PYTHONPATH="src"
# 聚焦（按 §六 逐项）
python -m pytest tests/test_pool_db.py -q -o addopts=""
python -m pytest tests/test_gate_engine.py tests/test_gates tests/test_runner.py tests/test_e2e -q -o addopts=""
python -m pytest tests/test_lint.py tests/test_vision_qa.py tests/test_pre_send_whisper.py tests/test_content_semantic.py tests/test_tts_brand_asset.py tests/test_mp3_vs_srt.py tests/test_subtitle_render.py tests/test_six_step_hard.py -q -o addopts=""
python -m pytest tests/test_mcp -q -o addopts=""
# 门禁
ruff check src/automedia/ --ignore E501,E402,N806,E741     # 必须 All checks passed
python scripts/check-doc-consistency.py                     # 必须 exit 0
pip check                                                   # 必须无 openai/litellm 冲突
# CI Windows 子集（含新增的 test_pool_db.py，必须全绿）
python -m pytest tests/test_paths.py tests/test_md5_tracker.py tests/test_gate_engine.py tests/test_gate_base.py tests/test_gate_hooks.py tests/test_gate_report.py tests/test_gate_report_html.py tests/test_gate_report_remediation.py tests/test_gates tests/test_pipeline tests/test_runner tests/test_runner.py tests/test_core tests/test_config_loader.py tests/test_cli --ignore=tests/test_cli/test_init_cmd.py --ignore=tests/test_cli/test_security_config_perms.py --ignore=tests/test_cli/test_validate.py tests/test_mcp tests/test_pool_db.py -q -o addopts=""
```

---

## 十、顺序与风险

**执行顺序**：
1. T2（一行）→ T4（独立，先清掉一批红）
2. **T1-1 判据修复（必须最先于 T1-2/3/4）** —— 否则媒体阶段半接通时 V 门会**假失败停机**（比现状更糟）
3. T1-2 → T1-3 → T1-4 同批
4. T3（transport + 鉴权）→ 文档同步 → 全量验证

| 风险 | 应对 |
|:--|:--|
| 判据修复后 V 门首次真正跳过，可能改变既有断言 | §七 #2 已列锁定测试；`video` 模式 partial 断言在上轮已存在（#6 复核） |
| 媒体阶段引入外部命令 | 全部先 `shutil.which` 探测 + 分组独立写入；任一失败仅告警，绝不崩门循环 |
| 真实媒体链路本机不可验证 | 已在 §2.3 明确验收边界；产出正确性由 mock 测试锁定 |
| HTTP transport 新攻击面 | 默认 stdio 不变；HTTP 无 token fail-closed；默认仅监听 127.0.0.1 |
| 依赖上界影响安装 | 只加上界且与 `litellm` 一致；`pip check` 验证 |

---

## 十一、顺带发现（本轮**不做**，仅报告）

1. **`AUTOMEDIA_MCP_ALLOWLIST_PATH` 是"文档承诺但未实现"**：`.env.example:69`、`docs/user/mcp-setup.md:265/281/294`、`deploy/systemd/automedia-mcp.env.template:30`、`mcp_allowlist.yaml:12/37` 都指向这个逃生口，但 `src/` 从无读取代码（`allowlist.py:28` 硬编码模块同级路径）。
2. **`pyproject.toml:67` 的 `"automedia-pipeline[httpx]"` 疑似悬空 extra**（extras 清单无 `httpx`）—— 待核实。
3. `docs/doc-inventory.md` 的 6 行字节陈旧已在上轮修复；提交 4 个未跟踪文档后需重跑生成器。
4. journey 注释里的 `runner.py:NNN` 行号引用陈旧。
5. 8 处 prose 仍写 "passed/failed/pending"（未含 `skipped`）。
6. 报告 §四 P2 各项（144 宽 `except`、77 处 `S108`、4 套 agent 配置、CI 非阻塞静态项）、P1-2（架构倒置、`runner.py` 1597 行）。