# docs/ — 文档 scope

此地何为真：文档树分三层——`docs/user/`（用户手册）、`docs/dev/`（开发与治理）、`docs/adr/`（决策记录，不可变）。

- 索引：`docs/index.md`；生成的文档地图：`docs/dev/doc-inventory.md`（AUTO-GENERATED，禁止手改，CI 漂移阻断）。
- 任何 docs/ 改动后必须重跑 `scripts/doc_inventory.py`（先编辑、后生成）。
- 数值声明被 `scripts/check-doc-consistency.py` 强制与现实一致（含 agent-reference 的 MCP/CLI 表）。
- `docs/dev/agent-era-doc-architecture.md` 的正本在 AutoInfo，本仓副本不改（e2e-test-suite#254）。
