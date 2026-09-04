# AutoMedia 后续开发报告（开发视角）

> **日期**：2026-09-02 · **基于**：商业论证报告（automedia-business-validation-20260902.md）
> **定位**：聚焦开发的路线图——现有 feature 补强 + 新 feature 加入，每项含优先级/任务/验收标准
> **原则**：只列"把质量门控做成可感知卖点 + open-core 变现准备"所需的最小开发集

---

## 现状锚定（开发基线）

| 项 | 现状 | 位置 |
|:---|:-----|:-----|
| 代码规模 | 33,619 LOC（core）/ 442+ 文件 / 2,955 测试 | README |
| API 三层 | SDK / CLI（19 命令）/ MCP（65 工具）| README |
| 质量门控 | 33 gates（G0-G6/V0-V7/L1-L4/CW/D1-D7/P1-P4）| `src/automedia/gates/` |
| 平台适配器 | 20 modules = 19 publish platforms + feishu notifier；11 real publish API + feishu notifier（`is_stub=False`）+ 8 intentional manual stubs（douyin/kuaishou/baijiahao/bilibili/weibo/toutiao/juejin/xiaohongshu）| `src/automedia/adapters/platforms/` |
| 账号管理 | AES-256-GCM 加密存储 + OAuth2/Cookie/API Key | `src/automedia/accounts/` |
| 内容实证 | 95 篇博客（AutoMedia-repo 20260822_* 目录）| 仓库根目录 |
| 部署 | Docker 镜像 `kevinzhow/automedia-pipeline` + devcontainer | README |

---

## 一、现有 feature 补强

### P0-1：Gate Report 输出（把 33 gates 变成可感知交付物）
> **依据**：商业结论——33 gates 是工程护城河但用户看不到；对标 AutoInfo 的 gate 报告思路，让门控"可见"。

**任务**：每次生产流程（`automedia run`）自动生成一份 **gate-report**（Markdown + JSON）：
- 记录：哪道 gate 拦了什么（内容/原因）、每道 gate 判定（pass/fail/review）、耗时
- 输出到项目目录 `05_review/gate-report/gate-report-<timestamp>.{md,json}`
- JSON 版供 agent 消费（MCP 工具 `get_gate_report` 目前尚不存在，为 P0-1 新增规划工具，将在本任务中落地）

**验收标准**：
- [ ] 跑一次完整生产，`05_review/gate-report/` 出现 gate-report（含每道 gate 的判定明细）
- [ ] 被拦条目与 gate 报告可追溯（为什么没过、过哪道时拦的）
- [ ] MCP `get_gate_report` 返回结构化 JSON（新工具，随本任务新增）

### P0-2：Director 模式差异可视化
> **依据**：Reuters 2026——43% 用户接受 AI+人审 vs 12% 纯 AI；人审是 B2B 信任关键。

**任务**：Director 审批界面从"pass/fail"升级为"**差异视图**"：
- 展示：原稿 → 门控修正后（diff 高亮，哪些词被 Humanizer/质量门控改了，为什么）
- 新增 MCP 工具 `review_decision`（目前尚不存在；现有 `approve_gate`/`reject_gate` 指向休眠机制，新工具将随本任务加入）并增加可选 `show_diff=true` 参数

**验收标准**：
- [ ] `show_diff=true` 返回原稿 vs 修正稿的结构化 diff（含修改原因）
- [ ] 人工 approve/reject 后 diff 记录进审计日志

### P1-1：平台适配器真实度审计 + 补齐
> **依据**：README 自称 20 适配器（12 real API + 8 stubs），实测 20 modules = 19 publish platforms + feishu notifier；11 real publish API + feishu notifier（`is_stub=False`）+ 8 intentional manual stubs（douyin/kuaishou/baijiahao/bilibili/weibo/toutiao/juejin/xiaohongshu）——这是"能发抖音吗"的销售答案。

**任务**：
1. **审计**：跑 `automedia adapter list --real` 输出真实可用列表，核对 README 自称的真实适配器数 vs 实际（注：该命令规划于 P1-1，当前 `cli/commands/adapter.py` 尚无筛选参数）
2. **状态盘点**：微信/知乎已完成真实 API；B站/小红书/抖音等维持 intentional manual stubs（F32/F34, founder-expectations.md）。本任务仅为审计 + 状态表更新，不新增适配器开发
3. **标记统一**：每个 stub 适配器加 `is_stub=True` + README 里"真实/手动"状态列清楚

**验收标准**：
- [ ] `automedia adapter list --real` 输出与实际实现一致（消除 README 自称的适配器计数与实际的不一致）
- [ ] README 适配器状态表每行标明：真实自动化 / 手动发布 / 桩

### P1-2：GitHub 主号恢复 / repo 迁移
> **依据**：商业结论——开源项目第一资产是 GitHub 可见性；主号 suspend 阻断社区。

**任务**：
- 恢复 1StepMore 主号（解决 token 嵌 git URL/.env 被 secret-scan 挂的根因）
- 或正式切换到 backup repo（renanzai40/AutoMedia_BackUp）作为 canonical，README badge 全指向正确地址（当前 badge 指向 `1stepmore/automedia` 可能失效；badge URL 修复另行处理，canonical 决策以 backup repo renanzai40/AutoMedia_BackUp 为准）

**验收标准**：
- [ ] 所有 README badge（CI/license/downloads）指向可用仓库
- [ ] `pip install` / `docker pull` 路径可用

---

## 二、新 feature 加入

### N1：open-core 收费组件预留（对标 GitLab/Supabase）
> **依据**：GitLab FY2026 $955M 收入 +26%；MIT 核心 + 托管收费是被验证的 COSS 模式。

**任务**：在代码中预留**功能分级**（不实现收费逻辑，只打标记）：
- `automedia/features/__init__.py` 定义 `FEATURE_TIERS = {"core": [...], "pro": [...], "enterprise": [...]}`
- Pro 候选：多平台真实发布、高级门控（V7+）、Director 审批面板、Gate 历史 dashboard
- Enterprise 候选：SSO、SLA、专属适配器
- 门控检查：`check_tier("V7")` 返回当前是否可用（免费层默认 core 全开；别名表将 roadmap 风格 id 映射到规范 gate id，如 video-gate-v7→V7）

**验收标准**：
- [ ] `FEATURE_TIERS` 定义存在且覆盖 33 gates 的分级
- [ ] `check_tier()` 函数可用（本地运行默认全开，未来托管版可 gate）

### N2：Agent 生态集成包（定位"agent 原生内容引擎"）
> **依据**：AI Agent 市场 $10.9B→$182.9B CAGR 49.6%；避开 AI 写作红海。

**任务**：
1. `docs/agent-integration/` 教程：如何在 Claude Code / OpenCode / Codex CLI / OpenClaw 里配置 AutoMedia MCP（各客户端 config 示例）
2. `scripts/setup_agent_mcp.sh`：一条命令给当前 agent 客户端装好 AutoMedia MCP 配置
3. README 加"Agent Quickstart"（已有雏形，补全具体 config 片段）

**验收标准**：
- [ ] 教程覆盖 4 个主流 agent 客户端（Claude Code/OpenCode/Codex/OpenClaw）
- [ ] `setup_agent_mcp.sh` 执行后，目标客户端能直接调 AutoMedia MCP 工具

### N3：内容生产案例套件（把 95 篇博客转成可复现案例）(deferred — corpus location TBD)
> **依据**：商业结论——dogfood 证据转成"第三方可信证据"。

**任务**：新增 `examples/` 目录：
- `examples/95-blog-案例/`：README（配置 + 生产流程 + 产物示例）
- 抽 3 篇典型博客的完整生产链路（选题 → 脚本 → 视频 → 发布）作为 reproducible case
- 每例含 gate-report（P0-1 产出）证明质量

**验收标准**：
- [ ] 3 个案例在干净环境可复现（`examples/<case>/README.md` 一步到位的步骤）
- [ ] 每个案例附 gate-report + 最终产物截图/链接

---

## 三、明确不做（启动阶段）

| 不做 | 原因 | 依据 |
|:-----|:-----|:-----|
| 新写作功能 | AI 写作 = commodity，不投入 | 商业结论 |
| 全部 20 适配器真实化 | 抖音/快手无公开 API（结构性限制），投入不值 | douyin_publisher 文档化 rationale |
| 独立托管平台 | 先验证付费意愿，再投基础设施 | 商业结论 |
| 多语言 UI | 非启动阶段核心 | — |

---

## 四、开发顺序与周期估算

```
P0-1 Gate Report ──┐
P0-2 Director diff ─┼── 第 1 周（质量可感知基线）
                   │
P1-1 适配器审计   ──┤
P1-2 GitHub 恢复 ──┼── 第 2 周
                   │
N1 open-core 预留 ──┼── 第 3 周
N2 Agent 集成包  ──┤
N3 案例套件      ──┴── 第 4 周
```

**验收里程碑**：第 4 周末，能用"1 条命令给 agent 客户端装 AutoMedia MCP" + "任一案例复现并产出含 gate-report 的内容"。`FEATURE_TIERS` 已定义，为托管版收费做好准备。
