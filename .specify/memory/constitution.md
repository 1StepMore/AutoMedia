# AutoMedia Constitution — 不可违背原则

> 来源：Owner 拍板 D6（2026-11-08）——以根 AGENTS.md §5「Agent Constraints (Red Lines)」为底稿汇编，只做结构化，**不改语义**。
> 权威版本 = 根 AGENTS.md §5；两处不一致时以 AGENTS.md §5 为准，本文件视为失效待修（Maintainer 角色提请 Owner 修订）。
> 命名消歧：本文件治理 **Agent 行为红线**；产品管线门（G0-G6 / V0-V7 / L1-L4 / D1-D7 / P1-P4，见根 AGENTS.md §4）是另一套系统，与本文件编号无关。
> 裁决顺序：安全与密钥条款（根 AGENTS.md §0）高于一切 → 本文件 → 角色契约 → 目录 scope → 根 AGENTS.md 默认值。

## Non-negotiable principles（applied to every task; enforced by the test suite）

1. **MUST NOT** archive projects using `--force`. Only the user may force-archive (Red Line 8). The MCP `archive_project` tool enforces this — it refuses unless status is `"published"` or `force=True`.
2. **MUST NOT** commit real production data, topic pool contents, or credentials to git.
3. **MUST NOT** modify `automedia/mcp/mcp_allowlist.yaml` without explicit user request.
4. **MUST** use synthetic test fixtures from `tests/fixtures/synth/` for testing. Zero production data in tests.
5. **MUST** use `automedia archive` command for archiving projects — never manual directory operations.
6. **MUST** follow the gate naming convention: G0-G6 (copy/content gates), V0-V7 (video/quality gates), L1-L4 (lifecycle gates), D1-D7 (distribution gates), P1-P4 (sub-pipeline repurpose gates). Additional gates include H0, pre-gate, and CW.
7. **MUST** add new gates to `automedia/gates/failure_modes.py` when creating them.
8. **MUST NOT** skip pre-commit checks. Run `pre-commit run --all-files` before committing.
9. **MUST** respect the GateHook readonly contract — hooks observe but never mutate.

## Expectations layer

期望/验收工件唯一事实源 = `scenarios/`（索引：`.agents/expectations/INDEX.md`）。**只有 Owner 的显式指令可改期望**；Tester 不得通过改产品代码或改期望使套件变绿。

## Sign-off

constitution 文本待 Owner 终审认可（治理 G4 签收项）。
