# 矩阵归属（模态分工）

> owner 2026-11-19 定：**视频 / 语音 / 图片 = code profile（本机 code 侧）**；**文本 = owner 侧 agent / harness**。
> 判定口径见 `docs/dev/matrix-verdict-policy.md`（跨仓契约，勿只改本仓副本）。

## 三条内容轨的归属

判定源码：`scripts/nightly_gap.py`（`文本轨` / `图文轨` / `视频轨`，见 `TRACK_STATE_KEYS`）。

| 轨 | 判据（摘要） | Owner |
|:--|:--|:--|
| 文本轨 | 文本产物存在且合规 | **owner 侧** |
| 图文轨 · 文字部分 | 文本轨两条 + 图片存在 | **owner 侧** |
| 图文轨 · **图片**（封面图/配图） | 图片存在且过 **Vision QA**（不许只看尺寸/体积） | **code** |
| 视频轨 | 文本轨两条 + `03_video/` 有 ≥10KB 视频，**V 门真跑**（#414 / `validation/gate_inputs.py` 静态可达性口径，只看文件大小会假绿） | **code** |

## 验证层矩阵（`automedia validate matrix`）

- 静态半边（四面）：mcp 63/64、cli 21/21、**gates 27/33（缺 4）**、modes 9/9 —— 全局共用，不按模态拆。
- 断言半边：跟随最近一次 run 记录（`validation-runs/<stamp>/scenarios.json`）。`last=-` 多数表示该场景不在最新记录里，**不是 bug**。
- 命令：`automedia validate matrix --runs-root validation-runs`

## 硬规矩

- 视频轨不许用「文件体积达标」代替 V 门真跑（#181 教训）。
- 图片必须过 Vision QA 才能算绿（内容不对但尺寸合规 = 红，`quality` 档）。
- 报告必须记录 commit sha + 命令；与代码不一致时以重跑为准。
