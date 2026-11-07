# 离散检查点（治理验收 CP-01–CP-06）

> 落盘自指导方针 02稿 §8.2，按本仓拍板决议回填实值（D2/D3/D4/D5）。状态列在治理 P4 验收时回填，
> 三态硬性：PASS / SKIPPED-<编号原因> / PENDING-<前置>；禁止 DONE、应该没问题等模糊态。

| CP | 检查点「应发生的状态变化」 | 判定方式 | 状态 |
|---|---|---|---|
| CP-01 | 根 AGENTS.md 存在、≤200 行、含 §0 安全 + tiebreaker + 角色路由 + 命令 | C3 checker + 人工 | P4 验收回填 |
| CP-02 | 四份契约五要素齐全、≤30 行；薄适配器指针非复本（本仓 D4 拍板不做适配器 → 后半按 SKIPPED-Owner-D4 处理） | C4 checker | P4 验收回填 |
| CP-03 | 回填后无残留 `{{}}`；docs/dev/doc-inventory.md 有 AUTO-GENERATED 头且与 docs 树一致（本仓既存实现，方针 §6.1 对应物） | C5 + C6 checker | P4 验收回填 |
| CP-04 | 一致性校验 CI gate 生效：故意制造断链 → checker 必须非零退出（本地实测注入+还原） | 确定性注入 | P4 验收回填 |
| CP-05 | `gh aw compile --strict` 全通过；`.lock.yml` permissions 最小集 | 逐份复核 | P4 验收回填（预期 SKIPPED-D3：Owner D5 拍板不引入 gh-aw） |
| CP-06 | 20 个代表性真实用法小样本验收可跑；0% 覆盖已显式登记（本仓：validation 层 162 场景即真实用法样本；A14 已登记无缺口） | §5.3/§5.5 | P4 验收回填 |
