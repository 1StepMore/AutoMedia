# 矩阵判定口径（跨仓契约）

> **副本声明**：本文件在 `AutoInfo` / `e2e-test-suite` / `AutoMedia-repo` 各有一份**逐字相同**的副本。
> 真身 = `99-Tools/methodology/matrix-verdict-policy.md`。改动须三份同步；
> 校验：`python3 99-Tools/check_matrix_policy_sync.py`（不一致 ⇒ EXIT=1）。
> 为什么不做成指针：这份口径必须在每个仓里**不开外链就能读到**（agent 在各自 worktree 里落地即用）。

## 1. 一格 = 一次真产出

- **绿** = 本次真生成产物存在，且过该格式的结构断言（AutoInfo 的 L1+L2+L3 / e2e 的 artifact assertions P0+P1 / AutoMedia 的轨判据或 V 门）。
- **禁止**：用 mock/模板路径、用 `skip`、用"上次跑过"冒充本次绿。产出存在但内容不合格 ⇒ 红（`quality`），不是绿。

## 2. 抖动处理（owner 2026-11-19 定）

产物由大模型生成，"一格不绿就重跑整批"不合理。规则：

- 每格**最多 2 次尝试**。
- 第 2 次通过 ⇒ 记 `pass(retry)`，**并保留首跑失败证据**（错误类 + 日志路径），不许静默吞掉。
- 两次都失败 ⇒ 判红，按三档定性：`deterministic`（缺 key / 缺外部依赖 / 格式不支持 / 配置错）、`transient`（超时 / 429 / 连接断 / 模型抖动）、`quality`（有产物但不合格）。
- **只重跑红格与新增格**，禁止因个别格重跑整批。
- 每份矩阵报告必须单列：总格数 / 绿 / 红 / skip / **flaky 数与比例**。
- **flaky 比例 > 10% ⇒ 停止刷绿**，按系统性问题查根因；不许调低断言来换绿。

## 3. skip ≠ pass

skip 必须带原因；环境类 skip 计入 gap；语料缺失类可豁免计入 gap，但**仍要在报告里显示**，不许从分母里消失。

## 4. 报告必须自带证据

命令 · commit sha · 时间 · 每格 reached · 失败格错误类。缺任一项 ⇒ 报告不算交付。
