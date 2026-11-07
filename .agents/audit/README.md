# .agents/audit/ — 治理盘点产物

治理 SOP（`.agents/` 层）的盘点与审计产物入库位置：

- `runlog-automedia.md` / `inventory-automedia-local.md` / `inventory-automedia-remote.md` — 治理 P5 自控制区复制入库（SOURCE=LOCAL/REMOTE 两份互斥）。
- `CALIBRATION.md` — 试点校准清单（方针缺陷/路径偏差逐条记录）。
- 生成的文档地图 = `docs/dev/doc-inventory.md`（AUTO-GENERATED，由 `scripts/doc_inventory.py` 生成，CI 漂移阻断）——本仓以它承担方针 §6.1 generated inventory 职能，不另建副本。

本目录文件由治理执行流程写入；日常开发不手改。
