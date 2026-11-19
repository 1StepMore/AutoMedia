# 交叉审计的产物中转（MUST · 2026-11-19）

> 协议真身（workspace 根）：`99-Tools/methodology/cross-audit-evidence-protocol.md`。本文件是本仓落点，不复制协议正文。

质量通过（quality pass）不能靠口头认定，必须**产物入库 + git 中转**：
两侧机器（code 侧 WSL / 主人侧 Windows）不共享磁盘，**唯一共用通道是 GitHub 仓库**，
所以产物必须跟着本仓走 git，审计方才读得到。

## 三类产物

| 类别 | 落点 | 入库 |
|:--|:--|:--|
| 一次性中间件、调试残片 | `.scratch/` 或系统临时目录 | ✗ |
| 矩阵/验收产物（要交叉审的）| `docs/dev/validation-evidence/<矩阵名>/<run-date>/` + 更新 `manifest.json` | ✓ |
| 大媒体（>5MB/文件、>50MB/轮）| 同上，但只入代理件（首段/抽帧/波形）+ 读数 + sha256 + 复跑命令 | ✓ 代理件 |

**``validation-runs/`` 是本机临时区，不是交付通道** —— 放那里的产物对方机器读不到，不得当作交叉审依据。

## 硬规则

- `manifest.json` 里 `quality.verdict=pass` 必须带 `quality.evidence`，且该文件存在非空；否则**按 fail 计**。
- 每格只保留最新一轮；历史轮次靠 `manifest.json` 的 `produced_at` 追溯，不堆副本。
- 自检：`python3 99-Tools/check_evidence_committed.py <repo>`，**exit 0 才可宣称质量通过**。

## 交叉审分工

code 侧（视频 / 音频模态）产的格 → 主人侧 harness 审；主人侧产的格 → code 侧审。
审计结论**写回 `manifest.json` 并提交**：没有提交就没有通过，聊天里的"看过了"不算。

## 本仓矩阵

`production-matrix`（`automedia validate matrix`）
