# 强制机制

> **状态：历史参考（2026-07-15）**
>
> 原有的 RL9 / D0 决策溯源强制机制已在 D3 Gap Closure 中移除
> （约 9,500 行代码删除）。本文档现在记录剩余活跃的强制机制，
> 并作为已移除架构的历史参考。

---

## 一、现行强制机制

### RL8 — 归档约束（HARD，自动化）

`archive_project` MCP 工具和 `automedia archive` CLI 命令在项目状态
不是 `"published"` 时拒绝归档，除非显式传入 `--force` 参数。
这是 Red Line 8 的核心约束——只有用户本人可以强制归档。

- **位置：** `automedia/mcp/server.py`（MCP 工具）、
  `automedia/cli/commands/archive.py`（CLI 命令）
- **工作原理：** 执行归档前检查项目状态，非 published 状态且无
  `--force` 标志时直接拒绝
- **绕过方式：** `--force` / `force=True`（仅限用户操作，代理不得使用）

### Pre-Commit 钩子（SOFT，自动化）

`.pre-commit-config.yaml` 配置了 ruff、mypy、conventional commits
等检查，每次 `git commit` 时自动运行。可以用 `--no-verify` 跳过，
但 GitHub CI 仍会拦截未通过的检查。

- **位置：** `.pre-commit-config.yaml`
- **工作原理：** pre-commit 框架在 commit 前执行所有钩子
- **绕过方式：** `git commit --no-verify`（但有 CI 兜底）

### 关卡失败模式（SOFT，自动化）

每个流水线关卡定义 `_failure_mode` 属性：

- **`"stop"`**：关卡失败时直接终止整个流水线
- **`"retry"`**：关卡失败时自动重试（触发内容重新生成）

定义在 `automedia/gates/failure_modes.py`，详见
`docs/runbook/gate-failure-modes.md`。

### H0 人工审核关卡（SOFT，自动化）

`H0HumanReviewGate` 在发布前暂停流水线，等待人工审批。
若配置了 `auto_publish=True` 则自动跳过。

- **位置：** `automedia/gates/h0_human_review.py`
- **CLI：** `automedia hitl approve <project_id> H0`
- **绕过方式：** `--skip-review` 标志或 `auto_publish=True` 配置

### Red Lines（纪律约束，非自动化）

除 RL8（已自动化）和 RL9（已移除）外，其余红线的执行依赖
开发者自律和代码审查。

| RL | 约束内容 | 执行方式 |
|----|----------|----------|
| RL1 | 不得用 `--force` 归档非 published 项目 | **自动化**（同 RL8） |
| RL2 | 不得将真实生产数据、话题池内容或凭据提交到 git | 开发者自律 |
| RL3 | 不得擅自修改 `mcp_allowlist.yaml` | 开发者自律 |
| RL4 | 测试必须使用 `tests/fixtures/synth/` 中的合成数据 | 开发者自律 |
| RL5 | 归档项目必须使用 `automedia archive` 命令，禁止手动操作目录 | 开发者自律 |
| RL6 | 遵守关卡命名规范：G0-G5、V0-V7、L1-L4、H0、CW、pre-gate | 开发者自律 |
| RL7 | 新建关卡时必须添加到 `failure_modes.py` | 开发者自律 |
| RL8 | 运行 pre-commit 检查后才能提交 | Pre-commit 钩子（自动化） |
| RL9 | 尊重 GateHook 只读契约——观察但不修改 | 开发者自律 |
| ~~RL9（旧）~~ | ~~决策层必须在流水线前运行~~ | **已移除** |

> 注：以上 RL 编号为本文档内部编号，对应 AGENTS.md 第 5 节的 9 条约束。
> 原 RL9（决策溯源）已移除，旧编号留空以示历史。

---

## 二、已移除架构（历史记录）

### RL9 / D0 决策溯源关卡

D0 Gate 是流水线的第一道关卡，运行在所有生产关卡之前。
它的职责是检查 `.solution-state.yaml` 文件，确保决策层已经完成
所有必要节点后，才允许流水线继续执行。

**工作原理：**

1. 流水线启动时，D0 Gate 检查项目目录下是否存在
   `.solution-state.yaml` 文件
2. 文件不存在 → 触发 `rl9_violation`，流水线终止
3. 文件存在但缺少必要节点 → 同样终止，并在错误信息中列出缺失节点
4. 所有节点完成 → 标记 `rl9_compliant`，将溯源元数据注入流水线上下文
5. 可通过 `--force-provenance --confirm-bypass-rl9` 绕过（但会写入审计日志）

**依赖图：** D0 Gate 背后是一个27节点的决策依赖图，分为 Build 模式
（11个必需节点）和 Scale 模式（12个必需节点）。节点包括
brand_questionnaire、brand_positioning、market_research 等。

**移除原因：** 这套机制过于臃肿。9,500 行代码维护了一个硬编码的
节点图、模式验证器、依赖解析器和前置检查器。实际上，流水线启动时
用 LLM 驱动的决策判断比固定节点图更灵活、更容易维护。D3 Gap Closure
移除了整个 `automedia/decision/` 包及其关联的 CLI 命令和 SDK 接口。

**已移除的组件：**

- `automedia/gates/d0_gate.py` — D0 关卡实现
- `automedia/decision/` — 整个决策层（编排器、依赖解析、前置检查、
  模式验证、诊断、审计）
- `automedia/cli/commands/solution.py` — 决策层 CLI 命令
- `.solution-state.yaml` 格式文件
- `solution-wise/schemas/` 下的 JSON Schema 文件

```yaml
# .solution-state.yaml — 已移除的格式
mode: build
brand: EcoBrand
completed_nodes:
  - brand_questionnaire
  - brand_positioning
  - market_research
```

---

## 三、流水线关卡完整列表（现行）

| 阶段 | 关卡 | 名称 | 失败模式 |
|------|------|------|----------|
| 前置 | pre-gate | 话题选择验证 | stop |
| 写作 | CW | 内容写作 | stop |
| 文案 | G0 | 事实核查 | stop |
| 文案 | G1 | 人性化改写 | retry |
| 文案 | G2 | 文案审核 | retry |
| 文案 | G3 | 品牌 CTA | stop |
| 文案 | G4 | 微信清单 | stop |
| 文案 | G5 | HTML 硬检查 | stop |
| 视频 | V0 | 代码检查 | stop |
| 视频 | V1 | 视觉问答 | stop |
| 视频 | V2 | 预发送 Whisper | stop |
| 视频 | V3 | 内容语义 | stop |
| 视频 | V4 | TTS 品牌资产 | stop |
| 视频 | V5 | MP3 vs SRT | retry |
| 视频 | V6 | 字幕渲染 | stop |
| 视频 | V7 | 六步硬检查 | stop |
| 审核 | H0 | 人工审核 | stop |
| 生命周期 | L1 | 发布日志 Schema | stop |
| 生命周期 | L2 | 归档验证 | stop |
| 生命周期 | L3 | 平台完整性 | stop |
| 生命周期 | L4 | 翻译质量 | retry |

八种模式（auto / text_only / text_with_cover / video_only / qa_only / image-carousel / social-thread / short-video）选择不同的关卡子集，
定义在 `automedia/pipelines/runner.py` 的 `_MODE_MAP` 中。

---

## 四、参考文档

- **AGENTS.md 第 5 节** — Red Line 约束（9 条必须遵守的规则）
- **docs/dev/agent-troubleshooting.md** — 关卡故障排除
- **docs/runbook/gate-failure-modes.md** — 各关卡的失败处理方式
- **automedia/pipelines/runner.py** — 关卡列表和模式映射
- **automedia/gates/failure_modes.py** — 所有关卡的失败模式定义
