# Inventory — AutoMedia @ 90ed0000ff20c0b67122206ef07c72bbac0a5771   SOURCE=LOCAL

> 盘点阶段 read-only 产出（P1-S2/S3/S4/S5 + P2-S1/S2）。判定维度：数据结构/状态/算法/所有权（[社区] gist）+ 测试/文档/CI 现状。基线 commit `90ed0000`，分支 main，基线时间 2026-11-07 22:08 +0800。工作区状态：仅未跟踪 `hyperframes-remotion-kit-20261103.zip`（不动，记 runlog）。

| ID | 子系统 | 路径 | 类别 | 测试现状 | 文档现状 | CI 覆盖 | 判定依据 | 处置建议(A编号) |
|----|--------|------|------|----------|----------|---------|----------|----------------|
| S-01 | 核心基座（config/runner/md5_tracker） | src/automedia/core/ | 源码 | 有（tests/test_core/） | 有（agent-reference 指针） | 有（lint-typecheck+test 阻断） | py=20；last commit 2026-11-07（高活跃）；pyproject 入口引用 | 保留（无动作） |
| S-02 | 管线编排（gate_plan/dag/runner） | src/automedia/pipelines/ | 源码 | 有（tests/test_pipeline/） | 有（AGENTS.md §4 门序说明） | 有 | py=16；2026-11-06 活跃 | 保留 |
| S-03 | 门禁系统（33 gates） | src/automedia/gates/ | 源码 | 有（tests/test_gates/ + 逐 gate 文件） | 有（gate-failure-modes.md） | 有（validation coverage audit 阻断缺场景门） | py=43；2026-11-06 | 保留 |
| S-04 | CLI（21 命令） | src/automedia/cli/ | 源码 | 有（tests/test_cli/） | 有（docs/user/cli-reference.md） | 有 | py=27；2026-11-06 | 保留 |
| S-05 | MCP 服务（68 工具） | src/automedia/mcp/ | 源码 | 有（tests/test_mcp/） | 有（server.py docstring 被 check-doc-consistency 扫描） | 有 | py=31；2026-11-03 | 保留 |
| S-06 | 媒体引擎 | src/automedia/engines/ | 源码 | 有（tests/test_engines/） | 有（docs/user/video-engines.md 等） | 有 | py=14；2026-11-06 | 保留 |
| S-07 | 验证层（scenario runner/coverage audit） | src/automedia/validation/ | 源码 | 有（tests/test_cli/test_validate.py + CI coverage drift 阻断） | 有（docs/dev/project-validation-framework.md） | 有（validation-affected + coverage audit drift） | py=29；2026-11-05 | 保留 |
| S-08 | 平台账号 | src/automedia/accounts/ | 源码 | 有（tests/test_accounts/） | 有（docs/user/account-management.md） | 有 | py=10；2026-11-04 | 保留 |
| S-09 | 发布适配器 | src/automedia/adapters/ | 源码 | 有（tests/test_adapters/ + test_distribution/） | 有（adapter 注册文档） | 有 | py=27；2026-11-04 | 保留 |
| S-10 | HITL 审批 | src/automedia/hitl/ | 源码 | 有（tests/test_hitl/） | 有（docs/user/hitl-framework.md） | 有 | py=7；2026-10-30 | 保留 |
| S-11 | 决策层 | src/automedia/decision/ | 源码 | 有（tests/test_decision*/） | 有 | 有 | py=6；2026-10-30 | 保留 |
| S-12 | 内容分析 | src/automedia/effects/ | 源码 | 有（test_content_semantic.py 等） | 有 | 有 | py=4；2026-10-30 | 保留 |
| S-13 | 探测器 | src/automedia/detectors/ | 源码 | 有（tests/test_detectors/） | 有 | 有 | py=5；2026-10-16 | 保留 |
| S-14 | 调度（cron） | src/automedia/cron/ | 源码 | 有（tests/test_cron/） | 有（cron-troubleshooting.md） | 有 | py=3；2026-09-28 | 保留 |
| S-15 | 选题池 | src/automedia/pool/ | 源码 | 有（tests/test_pool/） | 有 | 有 | py=5；2026-10-16 | 保留 |
| S-16 | Omni 三件套适配 | src/automedia/omni/ | 源码 | 有（tests/test_omni/，独立 CI job test-omni） | 有（docs/user/omni-integration.md） | 有（test-omni job 阻断） | py=10；2026-10-30 | 保留 |
| S-17 | 品牌档案 schema | src/automedia/manifests/ | 源码 | 有（mypy --strict 阻断 + 测试） | 有 | 有 | py=4；2026-11-06 | 保留 |
| S-18 | 资产库 | src/automedia/asset_library/ | 源码 | 有（tests/test_asset_library/） | 有（docs/user/asset-library.md） | 有（mypy --strict 阻断） | py=6；2026-10-24 | 保留 |
| S-19 | 开核分层标记 | src/automedia/features/ | 源码 | 有 | 有（AGENTS.md §12） | 有 | py=1；2026-10-16 | 保留 |
| S-20 | 渲染模板 | src/automedia/templates/ | 源码 | 有 | 有 | 有 | py=1；2026-11-04 | 保留 |
| S-21 | 提示词 | src/automedia/prompts/ | 源码 | 有 | 有 | 有 | py=1；2026-11-05 | 保留 |
| S-22 | hooks 协议 | src/automedia/hooks/ | 源码 | 有（tests/test_hooks/） | 有（AGENTS.md §4 观察者契约） | 有 | py=4；2026-10-24 | 保留 |
| S-23 | 测试套件 | tests/ | 测试 | — | 有（conftest marker 注册：e2e/redline/slow/smoke/cruel） | 有（test job 3.11 阻断 + windows-smoke + validation-affected） | 321 个 test_*.py / 26 目录；pyproject addopts 默认排除 e2e | 保留（D2 认定为 E2E 载体） |
| S-24 | 验证场景库 | scenarios/ | 文档（验收工件） | 即期望库本体（162 场景 + baseline/ + STANDARDS.md schema 权威） | 有（README+STANDARDS） | 有（coverage-audit drift 逐字节阻断） | 164 个 yaml；Owner D3 认定为期望唯一事实源 | 保留 + A13-C7 指针校验（D3） |
| S-25 | 文档树 | docs/ | 文档 | — | docs/index.md 索引 + user 15 篇 + dev 30 篇 + adr 9 份 + doc-inventory.md（生成） | 有（check-doc-consistency + doc_inventory --check + RFC aging 阻断） | 72 个 md | 保留；A13 扩面（.claude/rules.md 纳入扫描） |
| S-26 | 工程脚本 | scripts/ | CI（工具） | 有（regression_*_check.py 自带断言） | 有（doc-identifier-allowlist.txt） | 有（ci.yml 多步直接调用） | 29 个脚本 | 保留；A13 扩面落点 |
| S-27 | CI/工作流 | .github/ | CI | — | 有（step 注释详尽） | 即 CI 本体 | 11 workflows + CODEOWNERS(* @1stepmore) + dependabot/labeler/release-please | 保留；A13 增加一致性 gate 步骤 |
| S-28 | 部署配置 | deploy/ + Dockerfile | CI | 有（systemd 脚本断言） | 有（windows-deployment/deployment.md） | 有（checkov/trivy/gitleaks 扫描） | systemd/logrotate + Dockerfile | 保留 |
| S-29 | 根配置与入口 | pyproject.toml/.pre-commit-config.yaml/.env.example/README.md/ONBOARDING.md/AGENTS.md | CI（配置） | 有（pre-commit 全仓检查） | 有（README + ONBOARDING + AGENTS.md 200 行） | 有 | 1157 tracked files 汇总 | AGENTS.md 走 A1（D7 瘦身+路由）；其余保留 |
| S-30 | 既有 agent 设施 | .claude/.opencode/.cursor/ | 文档（agent 配置） | — | .claude/{settings.json,rules.md(陈旧),skills×4}；.opencode/skills×6；.cursor/mcp.json | 部分（rules.md 不在任何 checker 扫描面） | P1-S5 逐项登记 | 保留；rules.md 陈旧口径修正 + A13 扩面纳入 |

## 待废弃清单（仅标记不删除；三条件证据）

- **无完全满足三条件的待废弃项**（无引用 + 无 CI 覆盖 + 文档声明废弃，三条件同时满足者为 0）。
- 疑似项 0。
- 备注（不构成待废弃，仅登记）：4 个 deprecated MCP 工具别名（pool_add_topic/batch_run/engine_health/mcp_help）为**代码级**废弃，AGENTS.md 已声明，但仍有引用与测试 → 不满足三条件，属 A11 观察对象之外的正常废弃周期。

## 敏感文件清单（仅路径，不展开内容）

- `.env.example`（模板，良性）
- `deploy/systemd/automedia-mcp.env.template`、`deploy/systemd/automedia-pipeline.env.template`（模板）
- **历史轨迹（登记事实，未读内容）**：`deploy/systemd/automedia-mcp.env` 与 `automedia-pipeline.env` 曾于 2026-07-08（commit 1c8bd858）入库、2026-07-18（commit 25f0fe76「clean up .gitignore, git-tracked artifacts, and systemd config」）清理移除；现 HEAD 不存在。**gitleaks job（fetch-depth: 0 全历史扫描）在基线 90ed0000 的最新 CI 运行全绿** → 未检出密钥模式。Owner 签收建议：确认 2026-07 暴露窗口内部署凭据是否已轮换。
- `scenarios/security/redteam-credential-exfiltration.yaml`（红队测试场景定义，良性）
- `scripts/check-secrets.py` + CI `gitleaks`（守卫，现行有效）
- `.claude/settings.json` 含 `AUTOMEDIA_LLM_API_KEY` 占位值 `sk-your-key-here`（占位符，非真实密钥）
- `src/automedia/core/credential_loader.py`、`src/automedia/accounts/auth/api_key.py`（凭据加载实现，非密文）

## 现有 agent 设施清单（保留/合并/适配 → D4）

| 设施 | 路径 | 状态摘要 | 处置 |
|---|---|---|---|
| 根 AGENTS.md | AGENTS.md | 200 行顶格；红线 §5 强；**无角色路由表/无 tiebreaker/无 §0 安全优先链** | A1 改造（D7：外移 §9/§10 表 + 增路由/tiebreaker/安全链），D4 合并原则=保留红线主体 |
| Claude Code 配置 | .claude/settings.json（mcpServers+占位 key）、.claude/rules.md（**陈旧：50 tools/12 commands/G0-G5，现真值 68/21/G0-G6，无 checker 覆盖**）、.claude/skills/×4（维护者技能，md 格式） | rules.md 是 context rot 现行案例 | 保留；rules.md 口径修正 + 纳入 A13 扫描面（校准清单记录） |
| OpenCode 技能 | .opencode/skills/×6（含 issue-triage/pr-review-merge 等 2 份 local-only） | AGENTS.md §12 声明 | 保留 |
| Cursor 配置 | .cursor/mcp.json | MCP 指向本仓 server | 保留 |
| CODEOWNERS | .github/CODEOWNERS（`*` @1stepmore 全覆盖） | ③ 层就位 | 保留 |
| 用户技能 | docs/skills/×4（brand-strategy/pipeline-workflow/batch-workflow/distribution-workflow） | AGENTS.md §12 声明 | 保留 |
| 验证场景库 | scenarios/（162 场景 + STANDARDS.md + baseline） | 事实上的期望库 | D3 认定为期望唯一事实源；A13-C7 指针校验 |

## 前置缺口登记（A14/R-5）

| 缺口ID | 类型(无测试命令\|无E2E基线\|无CI) | 证据 | 影响的验收项 | 状态(PENDING-<前置>) |
|---|---|---|---|---|
| GAP-NONE | 无（三类前置缺口均不成立） | BUILD/TEST/LINT/E2E 四命令全部取证成功（.github/workflows/ci.yml + pyproject.toml [tool.pytest.ini_options] + tests/conftest.py markers）；E2E 基线存在（tests/test_e2e/ + scenarios/baseline/）；CI 完整（11 workflows） | 不影响任何验收项 | 无 PENDING |

> 附带登记（非缺口）：gh-aw 未安装——不属三类前置缺口，且 Owner 拍板 D5 已将 A6 定为 SKIPPED-D3，无验收项受影响。

## 回填参数区

```
BUILD_CMD=pip install -e ".[dev]"          # 证据：ci.yml 各 job "Install dependencies" 步骤；AGENTS.md §2
TEST_CMD=python -m pytest -q --tb=short     # 证据：ci.yml test job Pytest 步骤（阻断形态另带 --cov=src/automedia --cov-branch --cov-fail-under=70，3.11 阻断）
LINT_CMD=ruff check src/automedia/ --ignore E501,E402,N806,E741   # 证据：ci.yml Ruff 步骤（阻断）；另阻断项：mypy --strict ×7 模块、check-doc-consistency.py、doc_inventory.py --check、check-workflow-semantics.py、check_rfc_aging.py
E2E_CMD=python -m pytest tests/test_e2e -m e2e -q   # 证据：tests/test_e2e/ + conftest marker "e2e" + pyproject addopts 默认 "-m 'not e2e'"（须显式覆盖）
E2E_RUNNER=pytest+markers                    # Owner D2 拍板认定（V13 结案）：现有体系并轨，不引入 Gherkin/Playwright
REPO=AutoMedia
```
