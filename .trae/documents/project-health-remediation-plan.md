# AutoMedia 健康度整改实施计划（v2 — 自查修订版）

> 依据：`docs/dev/project-health-assessment-20260917.md` §七
> 用户决策：V 门走「显性化 + 条件化」· 授权收窄 `mcp_allowlist.yaml` · Windows CI 走冒烟 job
> 本轮范围：**P0-2 / P0-1 / P1-3 / P1-1**；不在本轮：P1-2 架构倒置、P2 各项
> 验收标准：**现有测试不回归 + 每项改动必须新增针对性测试**（用户指定）

---

## 一、Context

健康度报告的判断是「工程质量 A 级、产品完整度 C 级，风险在**宣称的能力多于实际接通的能力**」。
本轮处理的四项都属于「静默地看起来能用」或「假声明」类缺陷。

### 代码级复核：把报告的结论精确化（本次实测，非引用报告）

| 报告原述 | 复核后的精确事实 |
|:--|:--|
| V 门读的字段「零生产者」 | `runner.py:1457` **确实写** `gate_context["video_path"]`，但它在 `_finalize_pipeline` 里执行，即**所有门跑完之后** → 门永远看不到 |
| V 门「恒失败或空洞通过」 | 实际是**空洞通过**：无 HyperFrames 时 8 个 V 门返回 `status:"skipped"`（`pre_send_whisper.py:142-148` 等），而 `runner.py:1744-1748` 把 `skipped` 丢弃成 `"passed"`，`gate_report.py:51-55` 的 `_VERDICT_MAP` 也没有 `skipped` |
| 视频轨不可用 | 更强的证据：`_collect_video_assets`（`runner.py:1804`）要求 `audio_path`，而它零生产者 → **视频引擎渲染根本不启动**，`video_path` 实际也从不产生 |
| Windows 不可用 | 仅 3 处 `fcntl` 引用（`_shared.py:11,264,278`），修复面极小 |
| allowlist 过宽 | `mcp_allowlist.yaml:42` 的 `- ./` 生效；文件头注释自称 fail-closed 设计意图 |

---

## 二、对上一版计划的自查修正（重要）

上一版被驳回且无文字反馈，我自查出 4 个实质缺陷，均已修正：

| # | 上一版的缺陷 | 修正 |
|:--|:--|:--|
| **1** | **§6 `cta_principles` 的读取方设计是无效的。** 原设计「principle 文本 ∩ 中文动作词表」——而 onboard 向导的默认值是英文（`onboard.py:163`：`["Include clear CTA", "Use action verbs"]`），交集恒为空 → 判定为「不可校验」→ 永远通过。**默认用户填了照样不产生效果，等于没修。** | **改为「消费者 = CW 内容生产门」**：`gates/content_writer.py:232-237` 现只注入 `voice`，把 `cta_principles` 注入 writer prompt，让原则真正**指导 CTA 撰写**（这本就是 CTA 原则的语义）。CW 是真实门（`content_writer.py:145` `_gate_name="CW"`），故 `test_brands_gov_fields.py` 的「gate consumer」治理规则被真实满足。<br>**同时放弃**在 G3 新增启发式校验：G3 是 `_failure_mode="stop"`，对自由文本原则做机械判定会引入**假停机**，且无诚实映射（详见 §6）。 |
| **2** | **§5 的降级模式清单自相矛盾**：把 `auto` 列为「不降级」却把 `short-video` 列为「降级」，但未给判据。 | 改为**单一可陈述规则**：*预设含 V 门且 `mode != "auto"` 时，无 `video_path` 即降级 `partial`*；`auto` 是显式混合兜底、文本轨本身即合法交付物，故仅告警不降级。理由写进代码注释。 |
| **3** | **§7 漏掉了既有的文档/门禁义务。** 未发现 ① `docs/user/mcp-setup.md:251-262` **当前已与 YAML 不一致**（文档称「只含 `/tmp/automedia/`」，实际有 4 项）；② `docs/doc-inventory.md:52` 记录 `mcp-setup.md` 的**字节数**，改文档必须同步该行，否则 CI 的 `doc_inventory.py --check` 会真失败（非本机 CRLF 假象）。 | 新增「文档同步义务」章节，明确逐行操作；并核实 `check-doc-consistency.py` 的 allowlist **指的是 `doc-identifier-allowlist.txt`，与 MCP 路径白名单无关** → 该门不受本轮影响。 |
| **4** | **§1 的 fcntl 修法未说明「锁本身是冗余的」。** 原方案只说「POSIX flock + Windows no-op」，读者会误以为 Windows 是功能降级；且已发现写的锁加在 **tmp 文件**上（`_shared.py:278`）→ 对并发写者**不构成互斥**，说明该锁从来就没起到宣称的作用。 | 明确写清：写路径已由 `tmp.rename(path)` 原子替换保证读者不见半截 JSON，**该锁在任何平台都是冗余的**，Windows 端 no-op 是如实对齐语义而非降级；并把此判断写进代码注释，供后续维护者复核。 |

---

## 三、实施项

### 1. P0-2 — 解除 `fcntl` 硬依赖

**改** `src/automedia/mcp/tools/_shared.py`

- 删除顶层 `import fcntl`（`:11`）；抽出模块内私有 `_file_lock(fh, *, exclusive: bool)` 上下文管理器，包裹 `:264` / `:278` 两个调用点：
  - POSIX：`fcntl.flock(LOCK_SH / LOCK_EX)`
  - Windows：显式 no-op
- **注释必须写明**（依据自查 #4）：写路径的原子性来自 `tmp.rename(path)`，锁在两种平台上都不提供额外保证；Windows 分支不是降级。
- **不采用** `msvcrt.locking`：需 `seek(0)` + 字节区间，对 0 字节文件行为微妙，本机无法验证 Windows 语义，收益不抵风险。

**改** `pyproject.toml`：补 `Operating System :: Microsoft :: Windows` / `:: MacOS` classifier，使 `OS Independent` 不再是空头声明。

---

### 2. P0-2 — `windows-latest` 冒烟 CI job

**改** `.github/workflows/ci.yml`（新增 job，不动现有 20 个）

```yaml
  test-windows-smoke:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v7
        with: { python-version: "3.11" }
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Import smoke (POSIX-only modules must not break import)
        run: python -c "import automedia.mcp.server; import automedia.mcp.tools; import automedia.pipelines.runner; print('imports OK')"
      - name: Windows-safe test subset
        run: python -m pytest <Windows-green 子集> -q --tb=short
```

- `<Windows-green 子集>` **实施时在本机 Windows 实跑候选文件挑全绿者**（候选：`tests/test_mcp/`、`tests/test_brand_cta.py`、新增的 fcntl 测试）。
- 刻意排除已知 Windows 环境性失败（`WinError 32` SQLite teardown、路径分隔符、`0o600`、symlink、shell stub 二进制）→ 属独立后续任务。
- **不加** `continue-on-error`：否则修了等于没修。
- 若 `.[dev]` 在 Windows 装不上，退为 `.[mcp]` + `pytest`（实施时确认）。

---

### 3. P0-1 — 让 `skipped` 成为一等状态（显性化）

| 文件 | 改动 |
|:--|:--|
| `pipelines/gate_engine.py:107` | `GateLogEntry.status` Literal 扩为 `"passed"｜"failed"｜"error"｜"skipped"` |
| `pipelines/runner.py:1744-1748` | `_build_gates_log` 读 `r.get("status")`，为 `"skipped"` 时记 `"skipped"` |
| `pipelines/gate_report.py:51-55` | `_VERDICT_MAP` 增 `"skipped": "skip"` |
| `pipelines/gate_report.py:447-453 / 229-231 / 319-321` | summary 增 `skipped` 计数；Markdown 与 HTML 摘要行同步 |
| `cli/output_format.py:193` | `_failing_gate` 由 `!= "passed"` 改为 `in ("failed", "error")` —— **否则 skipped 被误报为失败门** |
| `cli/commands/run.py:390` | 图标三态化（passed `✓` / skipped `–` / else ``） |

实施时核验并同步：`pipelines/state_view.py`、`mcp/tools/pipelines.py`（`get_pipeline_state`）、`cli/commands/history_cmd.py`、`validation/diff.py`。

---

### 4. P0-1 — V 门按输入缺失条件化跳过

**改** 8 个 V 门（`gates/lint.py`、`pre_send_whisper.py`、`content_semantic.py`、`mp3_vs_srt.py`、`six_step_hard.py`、`subtitle_render.py`、`vision_qa.py`、`tts_brand_asset.py`）

- 在既有 `hyperframes_available` 守卫（`pre_send_whisper.py:142`、`subtitle_render.py:122`、`vision_qa.py:146` 等）**之后**追加「输入是否由本流水线产出」守卫：**全部**必需输入为空/缺失时，返回
  `{"passed": True, "gate": "<name>", "status": "skipped", "reason": "<input> not produced by this pipeline"}`。
- **心须交付的具体映射表**（实施第一步先固化，避免漏门）：

  | 门 | 必需上下文键 |
  |:--|:--|
  | V1 `vision_qa` | `entries` |
  | V2 `pre_send_whisper` | `transcription` + `audio_path` |
  | V6 `subtitle_render` | `avg_brightness` + `pixel_valid` |
  | V7 `six_step_hard` | `required_files` / `file_sizes` / `md5_records` |
  | 其余 4 门 | 实施时逐个确认（`_gate_name` → 键） |

- 判据统一为「**全部**输入缺失才跳过」，避免误伤合法空值。
- **必须如实说明的后果**：本轮不接生产者（选项 C 已被排除），故 V 门在**所有现有模式下都会跳过**。
  这正是「条件化」的预期诚实状态——比现状「空洞通过」好，比「假停机」好；且未来接入生产者后门会自动生效，无需再改预设。

---

### 5. P0-1 — 视频模式不得静默 `success`

**改** `src/automedia/pipelines/runner.py`（`_finalize_pipeline`，`:1381` 起）

- 规则（自查 #2 修正后的单一判据）：`video_produced = bool(gate_context.get("video_path"))`；
  **当 `mode != "auto"` 且该模式预设含 V 门且 `not video_produced`** → `status` 由 `"success"` 降级为 `"partial"`，
  并 `log.warning("pipeline.video_not_produced", mode=..., hint=...)`。
- 经 `cli/commands/run.py:114-123` 的 `_is_failure_status`，`partial` 现为非零退出 → 无人值守可发现。
- `auto` 例外且**必须在代码注释里写明理由**：它是显式混合兜底，文本轨本身即合法交付物；其 V 门行已在报告/CLI 中显示为 `skip`，属可见。
- 顺带修正 CLI 帮助文案诚实性（`cli/commands/run.py:145-149`）：在 mode 列表后补一句视频模式需已配置视频引擎，否则将标记为 skipped。
- 实施时须找出并更新断言这些模式 `status == "success"` 的既有测试。

---

### 6. P1-3 — 给 `cta_principles` 接上真实消费者（CW 门）

**主改动** `src/automedia/gates/content_writer.py`（`:232-237` 的 `user_message` 组装处）

- 现状只注入 `voice`。新增：
  ```python
  cta_principles = brand_profile.get("cta_principles", [])
  if cta_principles:
      user_message += "\nBrand CTA principles (follow when writing the call-to-action): " + "; ".join(cta_principles)
  ```
- 这就是 CTA 原则的本意——**指导 CTA 怎么写**，且确定性生效（进入 prompt 即生效），无假停机风险。

**辅改动** `src/automedia/mcp/tools/brands.py:62-117`：`add_brand` 增 `cta_principles: list[str] | None = None` 参数、写入 `data`、更新 docstring。

**同步测试**（属**有意更新**，非「改测试凑绿」）：
- `tests/test_mcp/test_brands_gov_fields.py:78-93`：`cta_principles` 由「无消费者故不支持」改为「CW 门消费故支持」，并改写两处 docstring 使其继续表达真实规则。

**明确不做**：不在 G3 增启发式校验。理由（自查 #1）：
① onboard 默认原则是英文自由文本，与中文动作词表无交集 → 判定恒通过，是假修复；
② 自由文本原则无诚实机械映射，强行映射会产生假失败；
③ G3 是 `stop` 模式，假失败会直接停流水线。
若用户希望**强制执行**（而非仅指导撰写），应作为独立任务并先定义可校验的原则词表——本次不做。

---

### 7. P1-1 — 收窄 `mcp_allowlist.yaml`（已获用户明确授权）

**改** `src/automedia/mcp/mcp_allowlist.yaml`

- 删除 `:42` 的 `- ./`（仓库根）。保留 `:36` `/tmp/automedia/`、`:38-40` `./data/`、`./output/`、`./projects/`。
- 在文件头注释写明：`./` 默认**不启用**；仅当接受「整仓读写」时取消注释；并指向 `AUTOMEDIA_MCP_ALLOWLIST_PATH` 逃生口。
- **已核实的兼容性**（这些是本轮不必额外处理的部分）：
  - `tests/test_mcp/test_allowlist_usability.py` 只断言「能解析 + ≥1 项 + 含 `/tmp/automedia/`」→ **不受影响**；
  - MCP 侧测试本就用 monkeypatch 覆盖 allowlist 缓存（`tests/test_l2_archive_wiring.py:127-135`、`tests/test_l4_localize_wiring.py:58`），不依赖 `./`。
- **接受的行为权衡**（须如实告知用户）：若用户从仓库根运行 MCP 并把 `base_dir` 指向仓库内任意项目目录，收窄后会被 fail-closed 拒绝；逃生口是 `./data/ ./output/ ./projects/` 三个默认目录或 `AUTOMEDIA_MCP_ALLOWLIST_PATH`。

**必须同步的文档**（自查 #3）：`docs/user/mcp-setup.md:251-262` 当前**已与 YAML 不一致**（称默认只含 `/tmp/automedia/`）。改为列出实际启用的 4 项 + 说明 `./` 为何默认关闭。

---

## 四、新增测试清单（验收硬性要求）

| # | 测试文件 | 用例 |
|:--|:--|:--|
| 1 | `tests/test_mcp/test_shared_file_lock.py`（新） | Windows 分支下 `automedia.mcp.tools._shared` 可导入且 `_read/_write_active_pipelines` 正常工作（用 `sys.modules` 屏蔽 `fcntl` 模拟）；回归锁定 P0-2 |
| 2 | `tests/test_mcp/test_allowlist_usability.py`（增） | 断言默认 allowlist **不含** `./`（等价解析后 ≠ repo root），锁定安全姿态 |
| 3 | `tests/test_gate_report.py` 或既有报告测试（增） | `status="skipped"` 的门 → `GateLogEntry.status == "skipped"`、gate-report verdict == `"skip"`、summary 计入 `skipped` |
| 4 | `tests/test_cli/`（增） | `_failing_gate` 忽略 `skipped` 条目（不把跳过当失败门） |
| 5 | `tests/test_runner.py`（增） | `video_only` 且无 `video_path` → `PipelineResult.status == "partial"`；`auto` 同条件仍为 `"success"` |
| 6 | V 门测试文件（增，每个门一条） | 输入缺失 → `status == "skipped"` 且 `passed is True`；输入齐备 → 走原有真实判定 |
| 7 | `tests/test_content_writer.py` 或 CW 既有测试（增） | `brand_profile` 含 `cta_principles` 时，传给 `llm_complete` 的 user message 包含这些原则；不含时不出现该段 |
| 8 | `tests/test_mcp/test_brands_gov_fields.py`（改） | `add_brand` 接受并回读 `cta_principles`；schema 暴露该字段 |

---

## 五、文档同步义务（易漏，必须执行）

| 触发条件 | 动作 |
|:--|:--|
| 编辑 `docs/user/mcp-setup.md`（§7） | 必须同步 `docs/doc-inventory.md:52` 的字节数 `23840` → 新的 **LF 归一化**字节数，并保持行按 `as_posix()` 排序位置不变 |
| 新增 `tests/` 下文件 | **不影响** doc-inventory（只收 `docs/`），但须确认 `interrogate`/`vulture` 步骤仍为 `continue-on-error` 而不阻塞 |
| 任何 `docs/` 改动后 | 重跑 `scripts/doc_inventory.py --check`：本机因 CRLF 必失败（非真实失准），须用「重新生成后逐行 diff」方式确认目标行已一致 |

**已核实不受影响的门**：`scripts/check-doc-consistency.py` 中的 allowlist 指 `scripts/doc-identifier-allowlist.txt`，与 MCP 路径白名单无关；本轮不新增 MCP 工具、不新增 CLI 命令、不新增门 → 数字声明（68/19/142）不变。G3 若不动则 gate 计数不变。

---

## 六、验证命令

```powershell
# 全量基线（Windows）
$env:PYTHONPATH="src;C:\Users\RenAnZai\AppData\Local\Temp\am_stub"
python -m pytest tests/ -q --tb=line -m "not e2e" -o addopts="" --timeout=180 --timeout-method=thread
# 基线：4695 passed / 65 failed / 22 errors / 8 skipped，cov 80%
# 65+22 中绝大多数为环境产物（9009 / WinError 32 / 路径分隔符 / 0o600 / symlink）——不得追打

# §1 完成后去掉 am_stub 路径再跑一次，确认不再需要 fcntl stub

ruff check src/automedia/ --ignore E501,E402,N806,E741        # 必须 All checks passed
$env:PYTHONPATH="src"; python scripts/check-doc-consistency.py  # 必须 exit 0
$env:PYTHONPATH="src"; python scripts/doc_inventory.py --check  # 本机 CRLF 必失败，按 §五 方式核对

# 聚焦回归
python -m pytest tests/test_brand_cta.py tests/test_mcp/ tests/test_runner.py tests/test_content_writer.py -q --tb=short -o addopts=""
```

---

## 七、顺序与风险

**执行顺序**：§1 → §2 → **（§3 + §4 + §5 同一批次，不可拆）** → §6 → §7 → §五 文档同步 → 全量验证

- **§3/§4/§5 必须同批**：只做 §4 会让 V 门「跳过但不可见」，比现状更糟。

| 风险 | 应对 |
|:--|:--|
| `status` Literal 扩容波及报告/CLI/MCP 多处消费 | 已枚举消费点（§3）；先跑全量确认无遗漏 |
| V 门放宽后掩盖真实视频缺陷 | 跳过**必须**同时具备：`status:"skipped"` + 报告可见 + 视频模式降级 `partial`（三者缺一不可） |
| Windows job 首次因依赖/子集选错而红 | 子集只取本机实跑全绿的文件；依赖装不上则退 `.[mcp]` |
| allowlist 收窄破坏用户 dev 流程 | 已在 §7 写明逃生口与三个默认目录；文档同步说明 |
| 改 `docs/` 导致 inventory 门真失败 | 按 §五 逐行核对，用「重新生成 + diff」而非直接提交生成结果 |
| 单次改动过大 | 逐项增量提交，每项后跑聚焦回归；不跳过 pre-commit |