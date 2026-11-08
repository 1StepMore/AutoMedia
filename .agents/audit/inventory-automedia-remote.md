# Inventory — AutoMedia @ 90ed0000ff20c0b67122206ef07c72bbac0a5771   SOURCE=REMOTE

> P1-S6 远端取证（与本地报告互斥、不混用）。取证手段：`git remote -v`、`gh api repos/1StepMore/AutoMedia...`、`gh run list`。P1/P2 对远端零写入（未开 PR/issue、未打 tag、未改设置）。

| ID | 子系统 | 路径（远端视角） | 类别 | 测试现状 | 文档现状 | CI 覆盖 | 判定依据 | 处置建议(A编号) |
|----|--------|------|------|----------|----------|---------|----------|----------------|
| R-01 | 远端 origin | github.com/1StepMore/AutoMedia | CI（托管） | 远端 main @ 90ed0000 与本地基线一致 | README/AGENTS.md 在远端 main | CI 11 workflows 已在远端生效 | `git remote -v` + 本地 HEAD = 远端 main（CI run headSha 90ed0000） | A12 推 ops/agent-infra 至 origin |
| R-02 | 备份远端 backup | renanzai40/AutoMedia_BackUp | CI（托管） | — | — | 未知（非交付目标） | `git remote -v`（fetch/push 均为 ssh 别名主机） | 不推送；是否纳入交付待 Owner（沿用 AutoInfo 轮 D1 同类登记） |
| R-03 | rulesets | main-protection（id 25385975） | CI（治理） | — | — | enforcement=**active** | gh api rulesets：规则集 = `pull_request` + `required_status_checks` + `deletion` + `non_fast_forward`，作用于 `refs/heads/main` | 保留；③ 层主锚点（PR 必需+状态检查必需+禁删+禁强推） |
| R-04 | classic 分支保护 | branches/main/protection | CI（治理） | — | — | **未设置**（API 404 "Branch not protected"） | gh api 查询 | 与 R-03 不冲突（rulesets 为主）；无动作 |
| R-05 | CODEOWNERS | .github/CODEOWNERS @ main | CI（治理） | — | — | 生效于 base branch | `*` @1stepmore 全覆盖（本地文件与远端 main 一致） | 保留 |
| R-06 | CI 运行状态 | Actions @ main | CI | 最新 4 次 run 全部 success @ 90ed0000（含 gitleaks 全历史扫描、coverage drift、workflow-semantics） | — | 全绿 | `gh run list --branch main` | PASS 取证（G4-S1 远端证据） |
| R-07 | gh-aw agentic workflow | .github/workflows/*.md → .lock.yml | CI | **不存在**（本地/远端均无 .md workflow） | — | 不适用 | 本地盘点 + 远端 gh-aw 未装 | SKIPPED-D3（Owner D5 拍板） |

## 待废弃清单（仅标记不删除；三条件证据）

- 远端无独立待废弃对象（与本地报告一致：待废弃 0 / 疑似 0）。

## 敏感文件清单（仅路径，不展开内容）

- 与本地报告同一份历史轨迹登记（`.env` 2026-07 清理；gitleaks 全历史扫描现行通过）。远端无新增敏感路径发现。

## 现有 agent 设施清单（远端）

- 与 main 分支一致（AGENTS.md / .claude/ / .opencode/ / .cursor/ / CODEOWNERS 均已入库远端）。
- 无 .github/agents/（Copilot 适配器）、无 .claude/agents/（Claude 适配器）、无 .specify/、无 .agents/ —— 与 Owner 拍板 D4（不做适配器）一致，无需远端动作。

## 前置缺口登记（A14/R-5，远端视角）

| 缺口ID | 类型 | 证据 | 影响的验收项 | 状态 |
|---|---|---|---|---|
| GAP-NONE | 无 | ruleset required_status_checks 已生效；CI 全绿 @ 基线 | 不影响任何验收项 | 无 PENDING |

## 回填参数区（远端）

```
REMOTE_URL=github.com/1StepMore/AutoMedia（origin；fetch=ssh，push=https）
PUSH_TARGET=origin（仅 origin；backup 远端不推送）
PR_BASE=main（ruleset 强制 PR + required status checks → A12 的 PR 将受 checks 门禁约束）
REPO=AutoMedia
```
