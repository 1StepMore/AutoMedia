# 验证证据区（交叉审计中转）

> 协议真身：workspace 根 `99-Tools/methodology/cross-audit-evidence-protocol.md`；本仓规则见 `docs/dev/cross-audit-evidence.md`。

要交叉审的产物放这里（`<matrix>/<run-date>/<domain>/<cell>/`），并更新 `manifest.json`，**必须 commit**。
`validation-runs/` 是本机临时区（gitignored），**不是交付通道**。

- `quality.verdict=pass` 必须带存在的 `quality.evidence`，否则按 fail 计。
- 自检：`python3 99-Tools/check_evidence_committed.py <repo>`
- 大媒体（>5MB/文件、>50MB/轮）只入代理件（首段/抽帧 + 读数 + sha256 + 复跑命令）。
