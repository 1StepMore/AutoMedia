# docs/ — 文档 scope

此地何为真：文档树分三层——`docs/user/`（用户手册）、`docs/dev/`（开发与治理）、`docs/adr/`（决策记录，不可变）。

- 索引：`docs/index.md`；生成的文档地图：`docs/dev/doc-inventory.md`（AUTO-GENERATED，禁止手改，CI 漂移阻断）。
- 任何 docs/ 改动后必须重跑 `scripts/doc_inventory.py`（先编辑、后生成）。
- 数值声明被 `scripts/check-doc-consistency.py` 强制与现实一致（含 agent-reference 的 MCP/CLI 表）。
- **不要直接改正本，也不要在 AutoInfo 仓动手**：本仓副本（`docs/dev/agent-era-doc-architecture.md`）与正本按 hash-pin 协议保持字节一致（e2e-test-suite#254）。需要改版时，**在本仓开 issue 说明改动点**，由 owner 决定是否走六仓同传。
