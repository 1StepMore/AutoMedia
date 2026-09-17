# 内容质量门 · 2026 竞品坐标图 + 候选狭缝分析

> **日期**：2026-09-15
> **方法**：一手来源优先（厂商官网 / 融资公告 / GitHub API 镜像 `ungh.cc`）；第三方式估算一律标注 `[3P est]`；查不到写 `not public`，不臆测。
> **目的**：核对 9-02《automedia-business-validation》的竞品结论是否仍成立，并据此产出**候选狭缝清单 + 可证伪判据**。
> **性质**：分析，不含实现路径。决策由发起人拍板。

---

## 0. 结论摘要（先说最不舒服的）

1. **9-02 的两条核心结论在 2026 年被证伪**：
   - 「**质量门控是空白**」→ **错**。已有①企业级十余家（Writer/Acrolinx→Markup AI/Slate/Lytho/Blee/Templafy/Aprimo/CrawlQ/BrandMythos/…）②开源 MCP 质量门 8 个 ③freemium 内容管线（Pipepost $8–49/月）。
   - 「**无人串成完整流水线**」→ **错**。`preetharaj/ContentOps-MCP` = "Notion → QA Gate → WordPress"；`Pipepost` = 草稿→审计→多平台发布→社交分发。
2. **门控的"检查项"本身已经商品化**：SEO / 可读性 / AI 味检测 / 事实核查 / AI 检测，在 ≥4 个开源库里被公开并克隆。**门控技术不能作为护城河。**
3. **真正弱覆盖的轴是「私有部署」**：全类目里只有 Writer（单租户/VPC）、Credo AI（自托管）、Modulos（私有云）明确支持；Blee/Slate/Lytho/Grammarly/BrandMythos 都不支持，Aprimo 已**退役**本地部署。→ 这是唯一的"结构性空位"。
4. **MCP 已是头部标配、不是壁垒**：Writer / Markup AI(原 Acrolinx) / Templafy / Aprimo 都有官方 MCP server。
5. **AutoMedia 的可辩护空间很窄**，且**不在"通用质量门"**——那正是 Writer 的主场。候选狭缝见 §5，**没有一个通过全部四条硬判据**，需用客户验证来裁剪。

---

## 1. 竞品坐标图

### 1.1 企业级内容治理（有预算、销售主导）

> 价格标 `[vendor]` = 厂商官网公布（2026-09-15 访问）；`[3P est]` = 第三方估算，仅作方向参考。

| 厂商 | 定位 | 买家 | 价格 / ACV | 融资 / 估值 | 差异化 | MCP / 私有部署 |
|:--|:--|:--|:--|:--|:--|:--|
| **Writer** | Agentic 内容平台 + 治理 | F500 / 受监管 | Starter $29/席/月 `[vendor]`；企业 custom；中位 ACV ~$33.8K `[3P est]`；大单 $500K–1M+ `[3P est]` | **$326M / $1.9B**；ARR ~$47M(2024)→~$220M(2025) est；**NRR 209%→~160%** | 自研 Palmyra 模型；生成时强制品牌词表 | **有 MCP**；企业版**单租户/VPC/自托管** |
| **Acrolinx → Markup AI** | 企业内容合规/风格治理 | F2000 技术/金融/医疗 | 旧 Acrolinx 报价制；新 Markup AI **$249 / $999/月** `[vendor]`；旧企业估 $120K–588K/yr `[3P est]` | **$27.5M**（2025-09，GENUI+EMH） | 术语/风格治理血统 + "Content Guardian Agents" | **有 MCP**（hosted + GitHub）；API-first；Azure |
| **Slate** | AI 内容治理 + AEO | 营销/SEO，≥1,000 页 | Growth **$499** / Scale **$999** / Agency **$2,000**/月 `[vendor]`；创始人称 ACV $10–25K | **not public**（2025 成立） | 治理与 AI 搜索可见度绑定 | 无 MCP / 无自托管 |
| **Lytho** | 创意工作流 + 品牌合规 + DAM | 中大型企业内部创意 | **报价制**；`[3P est]` ~$569/user | **$24.1M**，Level Equity；并购 DivvyHQ | 创意全流程内嵌 AI 审阅 | 无 MCP / 无自托管 |
| **Blee** | AI-first 营销合规 | 法务/合规 + 品牌（金融/保险） | **报价制** | **$27M**（2026-09，Fin Capital+SMBC） | 按客户训练的规则 + 50 州/UK/EU 规则库 | 云 only；**未声明自托管** |
| **Templafy** | 文档 + 品牌治理 | 多国/多品牌，M365 中心 | **$40/user/月，min $400** `[vendor]` | ~**$241M** 融资；估值 ~$328.9M | 治理嵌进 Word/PPT/Outlook | **有 MCP**；自带 LLM |
| **Aprimo** | 内容运营 + DAM + AI 治理 | 超大 F500 CPG/制药/金融 | **报价制**；`[3P est]` $20K–100K+/yr，大型 7 位 | **not public**（Marlin Equity 2016, $90M） | MRM+DAM+AI Content Studio 全栈 | **有 MCP**；**Azure SaaS only，本地已退役** |
| **CrawlQ Studio** | BRAND Score / SCORCH | 内容/品牌/研究，EU，价格敏感 | **€29 → $149/月**，终身 $79 `[vendor]` | ~$350K seed（Quantamix, 2021） | 5 维 BRAND Score + **像素级视觉合规（SCORCH）** | EU 托管；**无自托管** |
| **BrandMythos** | AI 品牌治理 / 品牌 DNA | 代理 + 内部团队喂 agent | Free / **$199 / $499/月** `[vendor]` | not public | 品牌规则导出成 agent 可读文件 | MCP **roadmap**；云 |
| **Holistic AI / Credo AI / Modulos** | AI 治理（组合/模型级） | 企业 AI/风险团队 | 报价制；Credo `[3P est]` $30K–150K+/yr | Holistic $35M / Credo ~$41.3M | 模型/组合级风险与合规 | Credo **自托管**；Modulos **私有云/VPC** |
| **Grammarly**（地板） | 写作助手 + 团队风格 | 个人→SMB | Pro **$12/月** `[vendor]`；Business 并入 Enterprise | ~$700M 收入；$13B 估值 | 4,000 万日活的低价锚 | 云 only；无自托管 |

**价格阶梯**：自助地板 `$12–500/月` → **断档** → 销售门控 `$20K–1M+/yr`。
**结构性空位**：`$15K–40K ACV` 的中端受监管买家——头部最低消费 $50K+ 且常不支持自托管。

### 1.2 开源 / MCP 内容质量门（直接对标"形态 A+B"）

> 数据来源：GitHub 仓库页 + `ungh.cc` 镜像字段（stars/forks/pushedAt/contributors/releases）；LICENSE 以 HTTP 抓取验证。

| 仓库 | ★ | Fork | 最后 push | 许可 | 语言 | 检查类型 | 接口 | 变现 |
|:--|--:|--:|:--|:--|:--|:--|:--|:--|
| `eric-tramel/slop-guard` | **164** | 12 | 2026-07-09 | MIT | Python | 规则化"AI 味"打分（24 规则/200+ 启发式） | MCP + CLI + CI 阈值 | 无（个人 OSS） |
| `sharonds/checkapp` | 4 | 0 | 2026-06-29 | MIT | TS(Bun) | 9 skill（抄袭/AI 检测/SEO/事实/语气/法律） | CLI+MCP+CI+API+Dashboard | 无（BYOK） |
| `veldica/publishready-mcp` | 2 | 0 | 2026-04-28 | MIT | TS | 确定性写作分析（无可读性/修订杠杆） | MCP(16) + CLI | 厂商主页 + hosted |
| `preetharaj/ContentOps-MCP` | 1 | 0 | 2026-05-27 | MIT | Python | 11 agent（SEO/链接/品牌/可读性） | MCP 编排 + UI，自托管 | roadmap 托管 |
| `Alvi-808/content-qa-mcp` | 1 | 0 | **2026-09-03** | MIT | JS | 可读性/AI 味/SEO，findings 带 fix | MCP stdio | 无 |
| `EditorialOS/The-Gate` | 0 | 0 | 2026-07-06 | **无 LICENSE** | TS | LLM 评分（8 准则 1–5 分 + 依据） | REST + OpenAPI | 关联 VPS 专有 |
| `EditorialOS/The-Gate-VPS` | 0 | 0 | 2026-07-12 | **专有** | JS | 多租户 MCP `runGate`/scorecard | MCP Streamable-HTTP，hosted **按客户发 key** | **有**（专有） |
| `DistinctlyDeveloped/stylemcp` | 0 | 0 | 2026-03-04 | README 称 MIT（**无 LICENSE 文件**） | TS | YAML 风格包校验/改写 | REST+MCP(7)+CLI+Action | **有**（billing/hosted） |

**关键判断**：除 `slop-guard`（164★，占全类目 95%）外，**全类目合计 8★、0 fork、0 release**；全部 2026 年新建、多为单人、多数 ≤18 提交。**这不是"已被占领的市场"，是"正在冒头的长尾"。** 唯一有真实牵引的是**确定性 AI 味检测**这一个子类目。

### 1.3 Freemium MCP 内容管线（低端竞争者）

| 产品 | 做什么 | 价格 |
|:--|:--|:--|
| `Pipepost` (pipepost-mcp) | 草稿→审计→**多平台发布**（Dev.to/Ghost/Hashnode/WordPress/Medium/Substack）+SEO+社交 | **Free / $8 / $19 / $49** |
| `Social Neuron` | 91-tool MCP：ideation→generation→editing→distribution→analytics，**自带 quality gate** | 商业化订阅 |
| `AI-Marketing-OS-MCP` | RSS 采集→草稿→发布(X/LinkedIn/Beehiiv)+Notion | 开源/scaffold |
| 真实 DIY 案例（vapvarun.com） | 13 个 WordPress 站、16 步流水线、**第 14 步 12 项审计门**（不过不放行） | 自建 |

> `Pipepost` 是"发布端"的平价平替：多平台发布 + 内容审计 + SEO，$8–49/月，MIT。

### 1.4 市场规模（口径混乱——这本身是发现）

| 口径 | 2026 规模 | CAGR | 来源 |
|:--|:--|:--|:--|
| AI Governance Platforms | **$0.8B** → $2.38B(2031) | 24.2% | Mordor Intelligence, 2026-08-20 |
| Enterprise AI Governance & Compliance | **$2.55B** → $11.05B(2036) | 15.8% | Future Market Insights, 2026-04-14 |
| AI GRC Software | **$3.8B** → $27.3B(2035) | 24.5% | Globe Market Research, 2026-09-04 |
| AI Content Compliance | **$4.8B**(2025) → $23.4B(2034) | 18.5% | Market Intelo, 2025-08-25 |
| Content Policy Enforcement for AI | $2.8B(2025) → $3.36B(2026) | 20.0% | The Business Research Co., 2026-03-23 |
| AI Governance（另一口径） | **$0.43B** → $4.2B(2033) | 38.5% | Persistence Market Research |

**同一年，"市场"从 $0.43B 到 $4.8B 差 11 倍**，且多数是泛"AI 治理"而非"内容质量门"。→ **不存在一个稳定的"内容质量门"市场口径。** 不要引用单一数字做决策。

**需求侧信号**（较可信）：Forrester 预测 AI 治理软件支出 2024–2030 CAGR **30%**、2030 达 $15.8B（Forrester, 2024-11-13）；EU AI Act 违规罚则最高 6% 年营收（Market Intelo 转述）。

---

## 2. 对 9-02 文档的差异（哪些结论被推翻）

| 9-02 结论 | 2026-09 实际 | 判定 |
|:--|:--|:--|
| 质量门控是空白 | 企业级 12+ 家；开源 8 个；freemium 管线多个 | ❌ 推翻 |
| 无人串成完整流水线 | ContentOps-MCP、Pipepost 已串 | ❌ 推翻 |
| 质量门控 = 工程护城河 | 检查项已在 ≥4 开源库被克隆；唯一有牵引的是确定性 slop 检测 | ⚠️ 降级为"集成/运维"角度的弱优势 |
| 33 gates 是资产 | 门控是硬编码 Python（已核）；不能配置客户标准 | ⚠️ 与"可配置标准"愿景冲突 |
| Writer 只是"企业级" | Writer 已带 MCP + 单租户/自托管，且横跨内容+治理 | ⚠️ 低估 |
| 出海优先（国内价格地板低） | 中端受监管 $15–40K ACV 是最空的位置，多在国内/跨境的受监管行业 | ⚠️ 方向需校正 |
| Jasper 营收→估值 | 估值错误（$55M 是营收，实际 ~$1.2B） | ❌ 事实错 |

---

## 3. AutoMedia 真实资产盘点（代码已核，供狭缝评分）

**真能用的**：
- 文本轨 13 门（CW/G0–G6/H0/L1–L4）真实；真调 LLM、真写文件。
- 11 个**真实 API** 平台适配器，**含微信 + 知乎**（西方 OSS/freemium 均不覆盖）。
- MCP-native（68 tools）；Director/HITL；AES-256-GCM 凭证库；6 层配置。
- MIT、纯 Python、**可自托管**（无需厂商云）。

**弱的 / 缺的**：
- 视频链未接线（V 门无生产者）；采集端半真（LLM 编题 + 可选 Tavily）。
- 门控硬编码，**无"可配置标准"抽象**（无 ruleset loader）。
- 无客户级可交付报告（gate_report 丢弃 remediation）。
- 无用户、无付费证据；本机 LLM 端点不可达（demo 阻塞）。

---

## 4. 候选狭缝清单（按四条硬判据打分）

> 四判据：①**有预算**（已有人付钱）②**替代贵/差** ③**你能服务**（现有资产可做）④**在位者不屑做 + 你有优势**。缺一条即不是狭缝。

| # | 候选狭缝 | ① 预算 | ② 替代贵/差 | ③ 你能服务 | ④ 在位者不屑 + 你有优势 | 综合 |
|:--|:--|:--:|:--:|:--:|:--:|:--:|
| A | **受监管行业 + 私有部署内容质量门**（数据不出境） | ✓ $50K+ | ✓ 头部云 only / 报价制 | △ 文本门可用，缺报告层 | △ 私有部署是最空轴；但需补"可配置标准" | **中** |
| B | **中文/跨境团队的多平台"发布前门 + 分发"** | ? 国内地板低 | ✓ 手动多平台很痛 | ✓ 微信/知乎+7 全球真适配 | ✓ 西方 OSS 不覆盖中文平台 | **中** |
| C | 给内容 agent 的**可调用质量门（MCP）** | ✗ 开源免费 | ✗ | ✓ | ✗ 开源已密集 | **低** |
| D | **通用内容质量门 + 可交付合规报告** | △ 企业买 Writer | △ | △ | ✗ Writer/Markup/Slate 主场 | **低** |

**判断**：**唯一同时"在位者覆盖弱 + 你有资产"的方向是 A 与 B 的交集**——即「**私有部署 + 中文/跨境**」的内容质量与分发门。C/D 不建议。

---

## 5. 每条候选的"胜负判据"（可证伪）

### 候选 A：受监管 + 私有部署内容质量门
- **假设**：至少一个受监管组织（区域银行/保险/医疗/制造业，200–2,000 人）愿为"可自托管、数据不出境的内容发布前门"支付 **$15–40K/yr**，且不愿用云版 Writer/Acrolinx。
- **证实条件**：3–5 个此类组织中有 ≥1 个签署 LOI / 意向价。
- **证伪条件**：全部表示"我们用现有的云工具/人工审即可"，或坚持免费开源 → A 不成立。
- **要问的问题**：现在怎么保证内容合规？谁审？数据能不能出公司？愿为"自托管"多付多少？

### 候选 B：中文/跨境多平台发布前门
- **假设**：出海或跨境团队愿为"一次过门 + 中英平台一键分发"支付订阅（对标 Pipepost $8–49/月上探到团队价 $199–499/月）。
- **证实条件**：3–5 个出海/跨境内容团队中 ≥2 个愿付 ≥$199/月，或 ≥1 个企业价。
- **证伪条件**：他们用 Pipepost/自建脚本 + 免费开源即可，或只愿付 <$50/月 → B 不成立。
- **要问的问题**：现在发一篇到 N 个平台要多久？微信/知乎的发布痛不痛？愿意为省这个时间付多少？

### 共同证伪条件（任一成立即整体重估）
- 目标买家认为"门控检查"是免费的、无差异的（像 slop-guard）。
- 目标买家已在用 Writer/Markup AI 且满意。
- 无法在本机跑通 demo（LLM 端点问题）导致无法演示。

---

## 6. 下一步验证动作（3–5 个目标买家）

| 步 | 动作 | 产出 |
|:--|:--|:--|
| 1 | 先修复 demo 阻塞（可达 LLM 端点），让文本轨 + 选题发现真跑通 | 可演示的 demo |
| 2 | 在 A/B 两类里各找 3–5 个目标买家（区域金融/保险/医疗/制造；出海/跨境内容团队） | 名单 |
| 3 | 用 §5 的问题做访谈（Concierge：用 demo 帮他们跑一篇，观察反应） | 访谈记录 |
| 4 | 记录是否触发证实/证伪条件 | 决策：做 A / 做 B / 重找狭缝 |
| 5 | 仅在证据支持下，才开发对应能力（报告层 / 可配置标准 / 分发） | 开发报告 |

---

## 7. 来源

**企业级**：writer.com/pricing, writer.com（2024-11-12）, TechCrunch（2024-11-12）, Vendr（2026-02）, acrolinx.com/introducing-markup-ai（2025-09-17）, Axios（2025-09-17）, Slator（2025-09-30）, markup.ai/pricing（2026-09-15）, slatehq.com/pricing（2026-09-15）, prism.news/CheckThat, softwarefinder（2026-08-10）, businesswire（2026-09-08）, tech.eu/axios（2026-09-08）, templafy.com/home/pricing（2026-09-15）, aprimo.com/pricing（2026-09-15）, crawlq.ai/pricing（2026-09-15）, brandmythos.com/pricing（2026-09-15）, grammarly.com/plans（2026-09-15）, Future Market Insights（2026-04-14）, Mordor Intelligence（2026-08-20）, Globe Market Research（2026-09-04）, Persistence Market Research, Forrester（2024-11-13）, Market Intelo（2025-08-25）, The Business Research Co./GII（2026-03-23）。

**开源/MCP**：GitHub 仓库页 + `ungh.cc/repos/<owner>/<repo>`（stars/forks/pushedAt/contributors/releases 镜像），LICENSE 以 HTTP 抓取验证（2026-09-15）。仓库：sharonds/checkapp、EditorialOS/The-Gate、EditorialOS/The-Gate-VPS、preetharaj/ContentOps-MCP、Alvi-808/content-qa-mcp、veldica/publishready-mcp、eric-tramel/slop-guard、DistinctlyDeveloped/stylemcp（=3DUNLMTD/stylemcp，同 repo id 1142050870）。

**Freemium/管线**：github.com/MendleM/Pipepost、registry.npmjs.org/pipepost-mcp（2026-04-13）、socialneuron.com/blog（2026-03-18）、vapvarun.com（2026-05-22）、pravinkumar.co（2026-05-08）。

> **诚实声明**：所有价格要么标 `[vendor]`（厂商官网，2026-09-15 访问），要么标 `[3P est]`（第三方聚合器，已注明）；`not public` = 无来源。未把第三方估算当事实。
