# 离散检查点（治理验收 CP-01–CP-06）

> 落盘自指导方针 02稿 §8.2，按本仓拍板决议回填实值（D2/D3/D4/D5）。状态列已在治理 P4（2026-11-08）回填，
> 三态硬性：PASS / SKIPPED-<编号原因> / PENDING-<前置>；禁止 DONE、应该没问题等模糊态。

| CP | 检查点「应发生的状态变化」 | 判定方式 | 状态 |
|---|---|---|---|
| CP-01 | 根 AGENTS.md 存在、≤200 行、含 §0 安全 + tiebreaker + 角色路由 + 命令 | C3 checker + 人工 | PASS（128 行；C3 绿；§0 四要素齐） |
| CP-02 | 四份契约五要素齐全、≤30 行；薄适配器指针非复本 | C4 checker | PASS（契约 18–27 行、五要素非空；适配器部分 SKIPPED-Owner-D4，本仓不建适配器，指针校验不适用） |
| CP-03 | 回填后无残留 `{{}}`；docs/dev/doc-inventory.md 有 AUTO-GENERATED 头且与 docs 树一致 | C5 + C6 checker | PASS（C5 零残留；C6 drift check 绿 `c83db01c`） |
| CP-04 | 一致性校验 CI gate 生效：故意制造断链 → checker 必须非零退出 | 确定性注入 | PASS（实测注入一个不存在的 docs 路径引用 → exit=1，C1+C7 双捕获精确到行 → 还原 exit=0；本次回填 CP 状态时执行者自己写入的探针路径字面量又被 C1 拦下——门禁自证的活案例） |
| CP-05 | `gh aw compile --strict` 全通过；`.lock.yml` permissions 最小集 | 逐份复核 | SKIPPED-D3（Owner D5 拍板不引入 gh-aw；不得宣称该能力生效） |
| CP-06 | 20 个代表性真实用法小样本验收可跑；0% 覆盖已显式登记 | §5.3/§5.5 | PASS（validation 层 162 场景 ≥ 20 样本要求；E2E 基线 28 场景 27 绿——1 失败为本机真实用户配置残留键 `master`/`azure`，系 test_real_config_regression 的设计探测对象，非本次改动引入；A14 登记 GAP-NONE） |
