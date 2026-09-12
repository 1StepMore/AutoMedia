# LOOP-LOG — AutoMedia validation 循环记录

> **活跃文档（2026-09-07 自 archive 复活）** — 每次迭代循环（打包/验证/修复）的**关键事件、根因、修复、验证结果**必须记录在此。
> 机制对齐 AutoInfo 2026-08-15 规范 + 跨项目循环治理规范（validation-run-governance.md）：每次迭代**开始前**必复查「坑清单」，新坑当天追加（现象 → 根因 → 预防）。
> 历史归档版（2026-08-23 及以前）见 `docs/archived/validation-loop-log-20260823.md`。

## 坑清单（pitfall checklist，迭代前逐条对照）

（2026-09-07 复活。历史坑清单见归档版 `docs/archived/validation-loop-log-20260823.md`；新坑在此追加。）

## 循环事件（major events，newest on top）

### 2026-09-07 LOOP-LOG 复活 + fix-retro 复盘机制接入

- 归档版（docs/archived/validation-loop-log-20260823.md）复活为活跃文档（docs/dev/），路径与 AutoInfo / omni suite 统一。
- 接入 GStack 工作流实施项 B：每轮修复完成后按 `fix-retro` skill 输出复盘块（5 问），追加到下方「复盘记录」段。

## 复盘记录（fix-retro，2026-09-07 起）

> 每轮修复完成后按 `fix-retro` skill 输出复盘块（5 问）追加到此段。目标：不只记坑，沉淀模式——根因分类统计 → 重复模式识别 → 预防措施 → 技能沉淀。复盘块的根因分类基于失败定性协议（validation-run-governance.md §2），不凭印象。

### 复盘模板（首轮复盘在下一轮修复后追加）

```markdown
## 复盘（fix-retro @ YYYY-MM-DD）
**本轮修了什么**:
- issue #NNN: 一句话

**根因分类统计**:
| 类型 | 数量 | 例子 |
|------|------|------|
| 类型错误 | N | ... |
| 边界/空值 | N | ... |
| 环境/配置 | N | ... |
| 依赖/版本 | N | ... |
| 其他 | N | ... |

**模式识别**（重复出现的根因 → 系统性问题）:
- 模式: ...（出现 ≥2 次）
- 系统性解读: ...

**预防措施**（哪些可以 gate 预防而非事后修）:
- ...

**沉淀**（新的 skill/checklist/坑清单条目）:
- ...
```
