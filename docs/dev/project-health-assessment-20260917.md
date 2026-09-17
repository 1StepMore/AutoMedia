# AutoMedia 项目健康度评估报告

> **评估日期**：2026-09-17
> **评估对象**：AutoMedia v1.6.0（分支 `main`，HEAD `b11b132`）
> **评估方法**：全部结论基于**实跑命令或代码核对**，逐条标注证据（`文件:行号` / 实测输出）。不含实现路径，不含改进排期。
> **评估性质**：一次性快照，非持续门禁。文档数字声明（68 MCP 工具 / 19 CLI 命令 / 142 场景）由 `scripts/check-doc-consistency.py` 机器校验，本报告不复述其工作。
> **与既有文档的关系**：`capability-gap-assessment-20260915.md` 是**能力缺口**视角（面向交付），本报告是**工程健康度**视角（面向可维护性与风险），并对前者列出的 P0 逐条做了**代码级复核**。

---

## 一、结论摘要

**综合健康度：7.6 / 10 —— 工程化水准高，产品完整度拖后腿。**

这是一个**工程纪律显著强于其产品完成度**的项目。CI / 测试 / 文档一致性 / 静态检查这条"质量流水线"的成熟度高于同规模项目的常见水平；但**能力层的接线完整度**存在结构性缺口——**视频与音频轨在代码里是"写好了但没接上电"**：门被装进预设，而门所需输入的**生产者全仓不存在**。

| 判断 | 结论 | 一句话依据 |
|:--|:--|:--|
| 代码"干不干净" | ✅ 干净 | `ruff check src/automedia/` 零告警 |
| 测试"可不可信" | ✅ 可信 | 实测 4695 通过 / 覆盖率 80% |
| 文档"准不准" | ✅ 准 | 数字声明有 CI 阻塞门，实跑 exit 0 |
| 功能"能不能用" | ️ **文本轨可用，视频轨不可用** | V0–V7 的输入字段零生产者 |
| 对外"能不能装" | ❌ **Windows 上装不起来** | `fcntl` 硬依赖 + 零 Windows CI |

**最危险的状态不是"有缺陷"，而是"静默地看起来能用"**——见 §四 P0-1。

---

## 二、实测度量事实

以下数据均为本次评估实跑所得，非引用既有文档。

| 指标 | 实测值 | 采集方式 |
|:--|:--|:--|
| 源码规模 | **63,797 行 / 254 个 .py**（非空行 53,783） | 文件系统统计 |
| 测试规模 | 66,626 行 / 289 个 .py / **4,726 个 `def test_`** | 文件系统统计 |
| 测试 : 源码比 | **1.24 : 1** | 计算 |
| 场景库 | 144 个 yaml/json（文档口径 142 场景） | 文件系统统计 |
| 实测测试结果 | **4695 通过 / 65 失败 / 22 报错 / 8 跳过**（348s） | `pytest -m "not e2e"` 实跑 |
| 实测覆盖率 | **80%**（21,246 语句 / 4,335 未覆盖） | `--cov=src/automedia` 实跑 |
| ruff（CI 口径） | **All checks passed** | `ruff check src/automedia/ --ignore E501,E402,N806,E741` |
| ruff（全仓无过滤） | 1,137 告警（`ANN201` 326、`ANN401` 268、`S108` 77） | `ruff check . --statistics` |
| 文档一致性门 | **exit 0，全绿**（仅 1 条 informational） | `python scripts/check-doc-consistency.py` 实跑 |
| CI 工作流 | 9 个（nightly / SBOM / trivy / checkov / gitleaks / publish / docs …） | `.github/workflows/` |
| **CI 平台覆盖** | **20/20 job 全为 `ubuntu-latest`，零 Windows / macOS** | grep `runs-on:` |
| 密钥泄露 | **无**：`.env`、`*_credentials.*`、`*.zip` 均未入库 | `git ls-files` 核验 |
| `TODO/FIXME/HACK` | **12 处**（5.4 万行代码） | grep |
| 裸 `except:` | **0 处** | grep |
| 宽 `except Exception` | 144 处 | grep |
| `# type: ignore` | 63 处 | grep |
| 测试 Mock 用量 | 1,286 处 `Mock(` / 989 处 `monkeypatch` | grep |
| 版本一致性 | `_version.py` = 1.6.0 = CHANGELOG 最新条目 | 文件核对 |
| 例外：非阻塞静态项 | CI 中 `interrogate` / `vulture` / 全仓 `mypy` / `deptry` 均 `continue-on-error: true` | `ci.yml:45-53,62-67` |

---

## 三、十二维度评分

| # | 维度 | 评分 | 依据 |
|:--|:--|:--:|:--|
| 1 | 构建与 CI/CD | **9.0** | 9 条流水线；安全扫描在 nightly 转为阻塞；release-please 自动发版 |
| 2 | 测试工程 | **8.5** | 4,726 测试 / 80% 覆盖率 / hypothesis 属性测试 / 独立场景验证层 |
| 3 | 静态检查与类型 | **8.0** | ruff（src）全绿；7 个模块 mypy strict 且 CI **阻塞**锁定该成果 |
| 4 | 文档与文档门禁 | **9.0** | 60 篇 docs + 自生成 inventory + 数字漂移 CI 门 + 网关式 link/identifier 检查 |
| 5 | 架构与分层 | **6.5** | 分层方向基本正确，但存在 `core → pipelines/adapters` 倒置 + 3 个上帝模块 |
| 6 | 平台可移植性 | **3.5** | `fcntl` 硬依赖 + POSIX 权限断言 + 零 Windows CI，却声明 OS Independent |
| 7 | 安全 | **6.5** | 凭证管理扎实（AES-256-GCM / OAuth2），但 MCP 无鉴权 + allowlist 过宽 |
| 8 | 依赖与许可 | **7.5** | 有 `uv.lock` / SBOM / deptry；AGPL 的 PyMuPDF 已在 `pyproject.toml:59` 显式标注 |
| 9 | 功能完整度 | **5.5** | 文本轨闭环；**视频/音频轨未接线**（详见 P0-1） |
| 10 | 可维护性 | **7.0** | 门解耦、自动注册是加分项；144 宽 `except`、4 套 agent 配置重复是减分项 |
| 11 | 可观测性 | **8.0** | structlog JSON、correlation id 贯穿 MCP 响应、`cost_log.jsonl`、gate-report |
| 12 | 发布与版本治理 | **8.5** | semver 1.6.0、CHANGELOG 由 release-please 生成、与 `_version.py` 一致 |

**加权说明**：维度 9（功能完整度）与 6（平台可移植性）直接决定"能否对外交付"，因此综合分被显著压低——工程质量分（维度 1–4、11–12 均值约 **8.6**）与产品分（维度 6、9 均值 **4.5**）之间的落差，是本项目的核心特征。

---

## 四、缺陷与风险（按严重度）

### P0-1 视频/音频轨结构性未接线 —— 与刚修复的 L 门同性质

**事实**：V0–V7 门被装进 `auto` / `video_only` / `short-video` / `repurpose` / `qa_only` 五个预设（`src/automedia/pipelines/runner.py:37-84,114-153`），但它们读取的上下文字段在**全仓 `src/` 范围内零生产者**：

| 字段 | 读取方 | 生产者数量 |
|:--|:--|:--:|
| `audio_path` | `gates/pre_send_whisper.py:153` | **0** |
| `transcription` | `gates/pre_send_whisper.py:152` | **0** |
| `avg_brightness` | `gates/subtitle_render.py:132` | **0** |
| `entries` | `gates/vision_qa.py:154` | **0** |
| `video_path` / `subtitle_path` | V 门族 | **0** |

门取到的是硬编码默认空值（`""` / `0` / `[]`）。这意味着 V 门**要么恒失败、要么空洞地通过——两种情况下都没有在验证真实视频**。

**佐证**：`AudioPipeline` 是孤立模块，仅被 `pipelines/__init__.py:25` 的惰性导出表引用，**无任何生产调用者**；对照 `ImagePipeline` 在 `runner.py:1401` 被真实调用，证明"有实现"与"已接线"是两件事。

**影响**：`video_only` 模式在 CLI help 中对外列出（`cli/commands/run.py:145-149`），实际不可用。这是当前最大的**"宣称能力 > 实际能力"**项。

**性质判定**：与 `capability-gap-assessment-20260915.md` §0b 描述的 L1–L4 缺陷**完全同构**——预设中包含"输入不存在的门"，且被 `_mock_results` 掩盖。L 门已于 09-15 修复，V 门族**尚未处理**。

---

### P0-2 Windows 完全不可用，但声明 OS Independent

**事实**：`src/automedia/mcp/tools/_shared.py:11` 在模块顶层 `import fcntl`（Unix 专属），并在 `:264` / `:278` 用于 `fcntl.flock`。Windows 上该模块**无法导入**，MCP 服务与 **35 个测试文件在收集阶段即崩溃**。

而 `pyproject.toml:16` 声明 `Operating System :: OS Independent`，`.github/workflows/ci.yml` 的 20 个 job **全部是 `ubuntu-latest`**——该断裂在 CI 中永远不可见。

**影响**：Windows 开发者/客户的首选路径直接失败。在"私有部署优先"的战略前提下，这是实质性障碍，而非瑕疵。

**修复成本**：低。`flock` 仅 2 处调用点，可用 `msvcrt` 分支或 `try/except ImportError` 降级为 no-op（本报告评估时即用该方式取得测试信号）。

---

### P1-1 安全：MCP 无鉴权 + allowlist 过宽

- **MCP 服务无任何传输层鉴权**。全仓 36 处 auth 相关引用**全部属于 `accounts/`**（平台发布凭证），与 MCP 服务本身无关。
- `src/automedia/mcp/mcp_allowlist.yaml:42` 实际启用 `- ./`（整个仓库根）。同文件头部注释写明"empty list blocks all paths (fail-closed)"的设计意图，但**当前默认配置把仓库全开了**。

两者叠加，是私有部署场景中客户安全问询会首先命中的点。

**加分项（需明确肯定）**：凭证本身管理规范——AES-256-GCM 加密 + keyring 后端 + OAuth2/cookie/apikey 三形态；密钥防护有 `.pre-commit-config.yaml:20-34` 的 gitleaks 与自研离线扫描**双保险**，且 `git ls-files` 核验**零真实凭证入库**。

---

### P1-2 架构：底层反向依赖 + 三个上帝模块

- **依赖倒置**：`core/workflow.py:238` 从 `pipelines.runner` 导入 `VALID_MODES`；`core/workflow.py:252-253` 从 `adapters` 导入 `ensure_registered` / `AdapterRegistry`。`core/` 本应是最底层，现依赖了上层。**当前仅 3 条边，属可修量级。**
- **上帝模块**：`pipelines/runner.py`（1560 行）、`pipelines/gate_engine.py`（1449 行）、`mcp/server.py`（1077 行）。`runner.py` 同时承担预设定义、门构造、执行编排、MD5 记账、报告生成五类职责。

**加分项**：分层方向整体正确——`gates/` 不 import `mcp`/`cli`（已核验为空），33 个门之间**无横向 import**（仅 `gates/__init__.py` 做聚合），新增门的改动面收敛。

---

### P1-3 品牌配置到门控的通路仍"半通"

`capability-gap-assessment-20260915.md` §2 记载 4 条通路只通 2 条。本次代码级复核结果：

| 字段 | 状态 | 证据 |
|:--|:--:|:--|
| `brand_name` | ✅ 通 | 门内 `brand_profile.get("brand_name")` |
| `blocked_words` | ✅ 通 | 门内消费 |
| `aliases` | ✅ **已修** | `gates/brand_cta.py:110` 现读 `aliases`（原读错为 `brand_aliases`） |
| `cta_principles` | ❌ **仍为死链** | 被 `manifests/brand_profile_schema.py:48` 定义、`cli/commands/onboard.py:173` 采集、`mcp/tools/brands.py:41` 展示，**但无任何门读取** |

用户填写 `cta_principles` 不产生任何效果——这是"按品牌定制"承诺的一部分，修复成本很低。

---

### P2 级观察项

| 项 | 事实 | 影响评估 |
|:--|:--|:--|
| 144 处宽 `except Exception` | 集中于 `adapters/`、`engines/` 等外部边界 | 有吞掉真实故障的风险（L 门事件即被掩盖过） |
| 1,286 处 Mock / 4,726 测试 | Mock 占测试主体 | 单元级可信；**预设/模式组合级**的 E2E 曾长期失守，现已补 mode journeys + 场景层 |
| 4 套 agent 配置目录 | `.claude/` `.codex/` `.opencode/` `.cursor/` | 4 个共享 skill 文件当前**哈希完全一致（无漂移，值得肯定）**，但为三倍维护成本 |
| 77 处 `S108` | hardcoded temp file，均在 `tests/` | 测试卫生问题 |
| 3 个未跟踪文档 | `docs/dev/capability-gap-assessment-20260915.md` 等 | 应收敛后再提交 |
| 非阻塞静态项 | `interrogate` / `vulture` / 全仓 `mypy` / `deptry` 在 CI 中不阻塞 | 这 4 项的信号当前不构成门禁 |

---

## 五、强项（有证据的"做对了"）

### 1. 自校验的文档体系 —— 最突出的工程亮点

文档中的数字声明不是人写的，而是被脚本派生并比对：`scripts/check-doc-consistency.py` 实跑输出 `Derived counts: 68 MCP tools, 19 CLI commands, 142 scenarios` 后 `exit 0`，且该步骤在 `ci.yml:31-39` 是**阻塞步骤**。`docs/doc-inventory.md` 另有 `--check` 字节级漂移门（`ci.yml:44`）。同规模项目中极少见到把"文档不实"当作构建失败来治理的做法。

### 2. 测试金字塔是真实的

实测覆盖率 80%（CI 门槛 70%），测试代码量（66.6K 行）**超过**源码（63.8K 行）。较难得的是同时存在三层：单元测试（4,726 个）、属性测试（hypothesis）、以及独立的**场景验证层**（142 场景 + `automedia validate` CLI/MCP 入口 + 覆盖率审计）。

### 3. 门控架构解耦良好

见 §四 P1-2 加分项。`BaseGate` 通过 `__init_subclass__` 自动注册（`gates/base.py`），`gates/failure_modes.py` 集中维护每个门的失败原因与修复建议，是"门"这一核心抽象的可维护性支撑。

### 4. 两天前的缺口正在被系统性偿还

`capability-gap-assessment-20260915.md` 列出的 P0，经本次**代码级逐条复核**，多数**已真实修复**：

| 原缺口 | 复核结果 | 证据 |
|:--|:--:|:--|
| 文本预设含 G4/G5/L1–L4 死门 | ✅ 已移出 | `pipelines/runner.py:57-112` 四个文本预设已无 L 门 |
| 失败时退出码仍为 0 | ✅ 已修 | `cli/commands/run.py:114-123` `_is_failure_status`：`partial` 现非零退出 |
| `publish_log` 全仓无生产者 | ✅ 已有生产者 | 新增 `gates/publish_log_wiring.py`，接入 `runner.py:90` 与 `gates/distribution.py:183` |
| 品牌别名死链 | ✅ 已修 | `gates/brand_cta.py:110` |
| 采集端 `PoolDB(":memory:")` | ✅ 已改 | 现解析 `AUTOMEDIA_POOL_DB` → 真实文件路径 |
| 报告丢弃 remediation | ✅ 已修 | gate-report 现有 remediation 列 + 自包含 HTML |
| CLI 无 `--skip-review` | ✅ 已加 | commit `71631f0` |

**这是一条强正向信号：项目具备"发现缺陷 → 记账 → 修复 → 回归"的闭环能力。**

---

## 六、评估方法的局限（诚实声明）

本节记录**本报告未能验证的事项**，避免读者高估结论确定性。

1. **未在 Linux 上运行测试**。本次实测在 Windows 上完成，且为取得信号做了一项环境改动：因 `fcntl` 缺失，在**系统临时目录**注入了一个 `fcntl` no-op stub（未触碰仓库文件）。因此：

   - **65 个失败 / 22 个报错中，绝大多数已逐条归因为环境产物，而非项目缺陷**：
     - **25 个** `test_validation/*` 的 `assert 'failed' == 'passed'` → 场景通过 `automedia` 控制台脚本调用 CLI，而本次以 `PYTHONPATH` 运行、**未执行 `pip install -e .`**，命令不存在并返回 Windows 码 **9009**（直接证据：`test_validation/test_adapters.py::test_exit_one_is_completed_not_failed` 报 `assert 9009 == 1`）。
     - **22 个** `WinError 32` → SQLite 文件句柄在 teardown 前未关闭，Windows 特有。
     - **13 个** 路径分隔符断言（`/` vs `\`）、**4 个** `0o600` 权限断言、**2 个** symlink 特权（`WinError 1314`）、**1 个** `os.geteuid`、**2 个** shell stub 二进制。
   - **因此，75/4788 的失败率不代表项目质量**。判定以 **Linux CI 为准**，本次未能复现该环境。
   - **真正属于项目问题的仅有**：`fcntl` 硬依赖（P0-2）与 SQLite teardown 在 Windows 下的文件锁（P2 级）。

2. **`automedia doctor` 的 LLM 连通性未验证**（需真实凭证与端点）。`llm_api` 状态为未知，本报告不对"能否真实产出内容"下判断。

3. **e2e 标记的 211 个测试默认被 `pyproject.toml:161` 的 `addopts` 排除**，本次未启用，故端到端路径的覆盖率未纳入 80% 这一数字。

4. **`docs/doc-inventory.md --check` 在本机失败，但并非真实失准**。根因：脚本用 `path.stat().st_size`（**原始字节**）计数（`scripts/doc_inventory.py:92`），而本机为大写换行（CRLF）检出，使计数虚高；叠加工作区中存在 2 个未跟踪文档与 2 个被 `.gitignore` 的 `AutoMedia-*.md`。经核对，**提交态清单与提交态（LF）文件树是一致的，Linux CI 该门应通过**。本报告评估过程中**已还原**该生成文件，未留下改动。

5. **未执行** `vulture`、`interrogate`、全仓 `mypy`、`deptry`、`pip-audit`、`bandit`、`trivy`、`checkov`（多为未安装或需容器/网络）。故维度 10 中"死代码"的判断，依据是人工 import 关系排查而非工具输出。

---

## 七、建议的处置优先级

按**投入产出比**排序，不含排期：

1. **修 `fcntl` 并补 `windows-latest` CI job**（成本最低、收益最大）。否则"OS Independent"是虚假声明，Windows 私有部署直接出局。
2. **对 V 门族做出与 L 门同样的显式决策**：或将其移出 `auto` / `video_only` 等预设（承认视频轨未就绪），或让 `AudioPipeline` 与视频引擎真正产出 `entries` / `audio_path` / `avg_brightness`。**不建议维持现状**——当前形态静默地"看起来能用"，是最难被客户与测试发现的一类缺陷。可先做条件化（产物不存在则跳过），再补生产者。
3. **为 MCP 增加传输层鉴权，并收窄 `mcp_allowlist.yaml` 默认值**。私有部署优先的战略下，这是客户签单前的第一个安全问询点。
4. **补 `cta_principles` 的读取方**。承诺"按品牌定制"的一部分，成本很低。
5. **拆分 `pipelines/runner.py`**。按"预设定义 / 门构造与执行 / 记账与报告"切为 3 块，可显著降低后续改动风险。
6. **收敛 3 个未跟踪文档**，并考虑把 `.claude/` `.codex/` `.opencode/` 三套重复 skill 改为单一源 + 符号链接或生成步骤（当前哈希一致，正是低成本窗口）。

---

## 八、一句话总结

> 这个项目的**工程质量是 A 级**（测试、文档门禁、CI 覆盖在同规模项目中属上游），**产品完整度是 C 级**（视频轨未接线、Windows 不可用），**且它自己知道这件事**——`capability-gap-assessment-20260915.md` 的自我诊断质量高于常见的外部审计。风险不在"代码烂"，而在"**宣称的能力多于实际接通的能力**"。