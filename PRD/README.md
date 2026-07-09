# AutoMedia PRD 文档集

> **用途**: 把"AutoMedia 自媒体自动化生产系统从 Hermes 强耦合版本走向三层通用化 + Omni 集成 + 商用一站式 solution-wise"的产品需求完整定义。

---

## 文档索引

| 文档 | 范围 | 阅读对象 |
|------|------|---------|
| [PRD-1-AutoMedia通用化.md](./PRD-1-AutoMedia通用化.md) | 解耦 Hermes, 暴露给任意 AI agent / Python SDK / 无 agent 用户 (库→CLI→MCP 三层) | 后端工程师 / 架构师 |
| [PRD-2-Omni三件套集成.md](./PRD-2-Omni三件套集成.md) | OPP / OL / ORF 三件套作为按需调用的 adapter 工具包接入 AutoMedia | 集成工程师 / 本地化 PM |
| [PRD-3-商用一站式solution-wise.md](./PRD-3-商用一站式solution-wise.md) | 在前两 PRD 之上加决策层 + 资产库 + SOP + open-core 商业模式 | 产品经理 / 商业团队 |
| [产品分析文档.md](./产品分析文档.md) | 竞品对比 / 技术选型 / 风险评估 / 里程碑 / KPI / 定价模型 | 决策者 / 投资人 / PMO |

> **PRD-1 实施计划** (按 Sisyphus 约定) 存放于 [../.omo/plans/PRD-1-implementation-plan.md](../.omo/plans/PRD-1-implementation-plan.md) — 69 个原子任务、11 周 4 wave、8 Red Line enforcement、合成 fixture E2E、gitignore 双层防御。

---

## 阅读顺序建议

- **新员工/工程师**: PRD-1 → PRD-1 实施计划（`.omo/plans/PRD-1-implementation-plan.md`）→ PRD-2 → PRD-3 → 分析文档
- **实施工程师开始 M1**: `.omo/plans/PRD-1-implementation-plan.md` + PRD-1 配合读
- **决策者/PM**: 分析文档 → PRD-3 → PRD-1 (按需 Prd-2)
- **本企业全线商业化客户**: 仅 PRD-3 + 分析文档(对客户不可见全部下层)

---

## 三份 PRD 的依赖关系

```
                PRD-1 通用化
                    │
                    │  (解耦后层为三层)
                    ▼
                PRD-2 Omni 集成
                    │
                    │  (Omni 作为 adapter, 不进主链)
                    ▼
                PRD-3 商用一站式
              (Decision Layer + Asset Library + SOP)
                    │
                    ▼
                  产品分析
  (竞品/选型/风险/里程碑/KPI/定价)
```

PRD-1 是基础, PRD-2 建立在 PRD-1 解耦后层之上, PRD-3 建立在前两份之上。

---

## 红线 (8 条 + 1 条)

红线贯穿三份 PRD 在所有阶段不可妥协:

1. **14 道 Gate 编排逻辑不可绕过**
2. **HyperFrames HTML+GSAP→MP4 视频方案唯一**
3. **飞书 / 微信公众号 API 必须作为可配置 adapter 保留**
4. **强制工序 humanizer → copy-review → brand-cta 不得跳过**
5. **A/V 同步铁律**: 每句语音存在时间内仅有该句文字字幕
6. **全量 QA (非抽样) 原则**: 逐 Entry Vision + 末尾静音段 + 全量 Whisper
7. **MD5 追踪机制**: 每个 Gate 产物 MD5 写入 pipeline_md5.json
8. **Agent 不得 archive 项目** (仅用户 --force 可绕过)
9. **(PRD-3 新增) Decision Layer 不得绕过 Production Layer Gate**, 决策结论必须转成 pipeline 输入, 不能直发平台

---

## 决策记录 (用户面对面 Q&A 确认)

整理于 2026-07-07 Sisyphus 与用户三轮问答:

| 编号 | 问题 | 用户选择 |
|------|------|---------|
| A1 | 通用化产物形态 | 三层兼顾 库→CLI→MCP |
| A2 | 目标 agent 边界 | MCP + Python SDK + 无 agent (全路径) |
| A3 | skill 资产处理 | 双层 内置默认 + 用户覆盖 |
| A4 | 品牌/平台可配 | 品牌任意 + 平台任意 |
| A5 | Gate 解耦粒度 | 黑盒 pipeline + 用户 hooks (选项 C) |
| B1 | Omni 用途 | 全选 + 知识库化 |
| B2 | Omni 管线位置 | 按需调用(主链不接) |
| B3 | 语言方向 | EN↔ZH 主打 + 预留多语 |
| B4 | Omni 集成架构 | 双层 默认转发 + 可选并列 |
| B5 | 翻译 LLM | AutoMedia 与 OL 各自独立 llm_pool |
| C1 | 商业模式 | open-core (开源基础+商业版定制) |
| C2 | solution-wise 定位 | 生产为主 + 与上层联动 |
| C3 | 决策能力抽象 | 思维链固定, 每节点 human or agent |
| C4 | 半自动 preset | 决策+偏好节点全 HITL |
| C5 | 资产库 | 双层 (开源 SQLite+Chroma / 商用 PostgreSQL+pgvector) |
| C6 | 客户租户 | 单租户现设计, schema 预留 tenant_id |
| D1 | PRD 切片 | 三份子 PRD |
| D2 | 部署形态 | 集成为主, PRD-1 必给 Hermes cron 替代 |
| D3 | LLM Provider | 贯穿全链可配置 |
| D4 | PRD 范围 | 仅产品需求, 旁附分析文档 |
| D5 | 红线 | 8 项全保留 + 1 条 PRD-3 新增 |

---

## 修改记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-07-07 | 三份 PRD 初稿 + 分析文档初稿, 决策经三轮用户Q&A 确认 |
| v1.1 | 2026-07-07 | PRD-1 实施计划 1049 行就位 (Metis 起草, Momus v1-v4 共 4 轮评审, UNCONDITIONAL PASS) |
| v1.2 | 2026-07-07 | 实施计划按 Sisyphus 约定迁移至 `.omo/plans/PRD-1-implementation-plan.md` (与 Omni 三个仓库的约定一致) |