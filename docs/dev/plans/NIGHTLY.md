> **本文件是本仓唯一权威的「不眠计划」文档**（=【冻结区】DoD/验收命令 + 【活区】差距矩阵/队列/账本）。
> 历史上的镜像文件 `docs/NIGHTLY.md` 已删除；旧引用一律指向本文件。

# NIGHTLY.md — AutoMedia · 「不眠计划」执行面

> **两个区，物理分开，权限不同**：
> - **【冻结区】**（完成定义 + 验收命令）：由 code profile 维护。**coding agent 只读、只跑，不得修改。**
> - **【活区】**（差距矩阵 / 下一步队列 / 摩擦账本 / 修订请求）：由 **coding agent 维护**。
>
> L1 总纲：`Hermes-Workspace/00-Records/dev-assets/NIGHTLY-PLAN-L1.md`
> 冻结区要改 → 只能往活区的「修订请求」写，等 owner / code profile 裁定；期间按原样执行。

---

## 【冻结区】完成定义（DoD）

**生产单元 = 轨（3 条）**。一条轨达标 = **至少 1 次真模型端到端跑通，且产物落在持久目录**。

| 轨 | 覆盖模式 | 达标判据（机械化） |
|:---|:---|:---|
| **文本轨** | `text_only`（+ `text_with_cover`） | `01_content/drafts/` 有 ≥1 个 **≥500B** 的 md，且 `cost_log.jsonl` **非空**（真模型调用记录） |
| **图文轨** | `image-carousel`（+ `social-thread`） | `01_content/drafts/` 有 ≥1 个 **≥500B** 的 md **且** `cost_log.jsonl` **非空**（继承文本轨两条）**+** `02_images/` 有 ≥1 个 **≥1KB** 的真图片 |
| **视频轨** | `video_only` / `short-video` | `01_content/drafts/` 有 ≥1 个 **≥500B** 的 md **且** `cost_log.jsonl` **非空**（继承文本轨两条）**+** `03_video/` 有 ≥1 个 **≥10KB** 的真视频 **+** 该项目存在 gate-report 且 `failed=0 / errored=0` **+** 有诚实生产者的门（**V2/V5/V7**）必须真跑且 `pass` **+** 所有 `skipped` 必须落在已登记能力债集合（**V0/V1/V3/V4/V6**，登记见 #193）内 → 任何**新增 skip**（不在这五门内）＝退步，判 ❌ |

> **为何把「同上」逐字展开**（2026-10-12，issue #195 的根因）：判据表用「同上 +」表达继承，实现却从未继承——`image_ok` / `video_ok` 各自只判自己的产物大小，`cost_log.jsonl` 非空与 md ≥500B 这两条**两轨都没有**。于是「没有真模型记录、只有一张图」的阶段目录会被判「图文轨达标」，与 §抗作弊 那条「没有它就不算真跑」直接冲突。**「同上」是文档承诺，不是实现约束**，所以此处逐字展开；实现侧另由 `scripts/nightly_gap.py::_text_evidence_ok()` 单点收敛，两轨不可能再各漏一半。

**两条附加硬要求**（都是踩出来的，不是猜的）：

1. **产物必须落在持久目录**（repo 内的项目目录），**不许落在 `/tmp`**。理由：唯一一次真跑（journey）产物就落在 `/tmp/automedia/journey-projects/`，重启即失——那不是产出，是临时文件。
2. **HITL 不许阻塞**：非交互运行必须返回 `awaiting_hitl` + 专用退出码，**不许无限等待人工**。理由：不眠计划跑在没人看着的夜里，阻塞 = 当晚白跑。

**⚠️ 抗作弊**：`cost_log.jsonl` 非空是「真模型」的唯一机械凭据——**没有它就不算真跑**，无论正文写得多好。理由：假产出是本计划要修的痼疾（AutoInfo 曾在零语料域照样落盘 101–113 字节空壳并计入"已产出"）。

> **视频轨口径（2026-10-07 owner 裁定，采纳「带能力债的达标」）**：见 issue #181（分歧）与 #193（能力债登记）。
> 核心：判据必须能区分「门跑了并 pass」与「门被 skip」——只看文件大小的判据会造成假绿；同时不得为「让门不 skip」而造数据，故五门以登记能力债的形式明面挂着。

### 「完成」的裁决是人工保留行

`nightly_gap.py` 退出 0 **只代表「机器可判的差距归零」，不等于项目完成**。

本仓已有同源机制：`automedia validate sign` —— **"Record the director's sign-off on a run"**，
把导演签收做成**独立的人工动作**（追加进 `signed.txt`），与机器跑分物理分开。

**照此办理**：

| 判据 | 谁判 |
|:---|:---|
| 三轨差距归零（`nightly_gap.py` exit 0） | **机器**（agent 跑） |
| 连续 2 轮不新增「挡住 DoD」的项 | **机器**（agent 跑） |
| **「本计划完成 / 产出没问题」总裁决** | **owner / director（人工保留）** |

**硬规矩**：coding agent **不得**在任何报告、提交信息、PR 描述或文档里宣布
「三轨打通」「AutoMedia 产出 OK」之类的**总裁决**。它只能说「差距矩阵归零，证据在此」。

---

## 【冻结区】验收命令

**必须用 `.venv/bin/*` 解释器**（仓库自己的 venv）。退出码不得被 `tail`/管道吞掉
（用 `cmd > /tmp/x 2>&1; echo $?` 取）。

```bash
cd <repo>

# —— 唯一判据入口：差距矩阵 ——
.venv/bin/python scripts/nightly_gap.py --json-out nightly/gap.json --md-out nightly/gap.md
# exit 0 = 三轨达标 / 1 = 仍有差距 / 2 = 环境或用法错误（需人介入，不是差距）

# —— 验证矩阵原文（人读 + 逐场景定位）——
.venv/bin/automedia --json validate matrix      # 机读
.venv/bin/automedia validate matrix             # 人读

# —— 覆盖审计（门/模式/CLI/MCP 的 declared vs covered）——
.venv/bin/automedia validate coverage

# —— 执行侧（这些是"怎么做"，不是判据）——
.venv/bin/automedia run --mode <mode> --topic <topic>
```

---

## 【活区】当前差距矩阵（基线 2026-09-30）

### 2026-10-21 夜间复跑（在最新 main `df483ea` 上）

批跑（02:00，systemd `nightly-gap.service`，网关进程树外）：`.venv/bin/python scripts/nightly_gap.py` **exit 0 —— 三轨全达标（机器可判部分完成）**（`nightly/gap.json`：`gap: []`、`passing_units: 3`）。

- 文本轨 ✅ 31 个 · 图文轨 ✅ 6 个 · **视频轨 ✅ 1 个**（证据 `20261018_每周一次内容复盘小团队反救火手册`）。
- 项目目录 **57** 个（`cost_log.jsonl` 非空 = 真跑过：**33** 个）；`bench: main@df483ea`。
- 视频轨能力债照登记：**V0/V1/V3/V4/V6 无诚实生产者（#193）**，不计入达标、不静默忽略（`gap.json` 的 `capability_debt` 字段）。
- 验证矩阵（自动生成）：场景 **147** 条 `{passed 107, unconfigured 31, partial-pass 3, None 2, recovered 1, failed 3}`；hard 10 条全过（`hard_not_passed: []`）；门 `missing=4` / `unreachable=2`（旧账，不挡 DoD）—— 与 2026-10-19 逐项一致 ⇒ **无退步**。
- 回归护栏：无新增「挡住 DoD」项。**最终裁决仍由 owner 保留。**

### 2026-10-20 夜间复跑（在最新 main `df483ea` 上）

批跑（02:00，systemd `nightly-gap.service`，进程树外）：`.venv/bin/python scripts/nightly_gap.py` **exit 0 —— 三轨全达标（机器可判部分完成）**（`nightly/gap.json`：`gap: []`、`passing_units: 3`）。

- 文本轨 ✅ 31 个 · 图文轨 ✅ 6 个 · 视频轨 ✅ 1 个（证据 `20261018_每周一次内容复盘小团队反救火手册`，与 2026-10-19 同一证据）。
- 视频轨证据的 gate-report：`passed [V2,V5,V7]` · `failed []` · `errored []` · `debt_skipped [V0,V1,V3,V4,V6]` ⇒ 空生产者五门仍按 #193 登记为**能力债**（`gap.json` 的 `capability_debt` 字段），不计入达标、也不静默忽略。
- 验证矩阵（自动生成）：场景 **147** 条 `{passed 107, unconfigured 31, partial-pass 3, None 2, recovered 1, failed 3}`；hard 10 全过；门 `missing=4` / `unreachable=2`（L1–L4 / G4-G5 旧账，不挡 DoD）；与 2026-10-19 逐项一致 ⇒ 无退步。
- 同步基点：main `df483ea`（由 `58f28a4` 快进）。
- 回归护栏：无新增「挡住 DoD」项。**最终裁决仍由 owner 保留。**

### 2026-10-19 夜间复跑（在最新 main `1f6714e` 上）

批跑（02:00，systemd `nightly-gap.service`，进程树外）：`.venv/bin/python scripts/nightly_gap.py` **exit 0 —— 三轨全达标（机器可判部分完成）**（`nightly/gap.json`：`gap: []`、`passing_units: 3`）。

- 文本轨 ✅ 31 个 · 图文轨 ✅ 6 个 · **视频轨 ✅ 1 个**（证据 `20261018_每周一次内容复盘小团队反救火手册`）。
- 视频轨证据逐条对照冻结判据：draft **1,110B** ≥500B ✓ · `cost_log.jsonl` **2 行** ✓ · `03_video/output.mp4` **7,867,543B** ≥10KB ✓ · gate-report `failed=0 / errored=0` ✓ · **V2/V5/V7 真跑且 pass** ✓ · 其余 skip（V0/V1/V3/V4/V6）全部落在已登记能力债（#193）内 ✓。
- 该证据产自 **PR #238（`fix/236-brand-name-instruction`）分支的验收跑**（G3 `brand_name_present` 补生成侧指令后通过）。冻结判据只看产物与 gate-report，故本轮判定成立；但 **main 上该修复未合并** ⇒ 在 main 重跑同题仍可能被 G3 间歇拦住（同一品牌 `w3t1-validation-brand` 实测 4 跑 2 真 2 假）⇒ **建议合并 #238 以在 main 上固化**。
- 补记（2026-10-19）：**#238 已合并入 main**（squash `4851660`，随 **v1.8.15** 发布）⇒ 上条「main 上该修复未合并」已闭环。
- 验证矩阵（自动生成）：场景 **147** 条 `{passed 107, unconfigured 31, partial-pass 3, None 2, recovered 1, failed 3}`；hard 10 全过；门 `missing=4` / `unreachable=2`（旧账，不挡 DoD）；与 2026-10-18 逐项一致 ⇒ 无退步。
- 回归护栏：无新增「挡住 DoD」项。**最终裁决仍由 owner 保留。**

### 2026-10-15 夜间复跑（在最新 main `d179702` 上）

- 批跑（02:00，systemd）：`nightly_gap.py` **exit 1** —— 文本轨 ✅ 26 / 图文轨 ✅ 3 / **视频轨 ❌ 0**；当时快照：项目目录 45 个（2026-10-18 实测 55，以 `nightly_gap.py` 产物为准）、`cost_log` 非空 28 个、场景 144 条（2026-10-18 实有 147，以 `automedia validate matrix` 产物为准）；本轮场景结果 `passed 106 / unconfigured 31 / partial-pass 3 / None 3 / recovered 1`；hard 10 全过；门 `missing=4 unreachable=2`。
- **本轮按 L1 §4「执行」真跑视频轨**（`--mode short-video`，真模型 AMD `DeepSeek-V4.1-Flash`，产物落 repo 内持久目录，品牌 `w3t1-validation-brand`）：**3 跑**，门序列三跑一致 —— `pre-gate ✓ / CW ✓ / G0 ✓ / G1 ✓ / G2 ✓ / **G3 ✗**` → `status=partial`，**下游 `G6/H0/V0–V7` 未执行**。
- **复跑差距（05:10，把本轮真跑计入）：文本轨 27 / 图文轨 4 / 视频轨 0**，`exit 1`。图文轨 3 → 4 就是本项目：真 draft 5,953B + `cost_log.jsonl` 8 行 + 2,117,596B 真图（ComfyUI）+ 556,992B 配音 + 7,807,842B 真视频（hyperframes）。
- **本轮闭合的环境缺口（两处，环境层，产品代码未动）**：
  - `whisper` 不在 PATH（产品按 `runner.py:1990` 的 `shutil.which` 解析）→ 媒体阶段 `pipeline.media_stage.tools_missing missing=['whisper']`，音频/视频/V 门输入**全不产**。修：`~/bin/whisper` → `~/mamba/envs/whisper/bin/whisper`（`~/bin` 在 PATH 且先于各 venv 的 bin）。
  - 修好 `whisper` 后媒体阶段走到 TTS 并失败（`edge-tts … returned non-zero exit status 1`）：经 PATH 解析到的是 hermes venv **7.2.7** → 直接跑 `WSServerHandshakeError: 403`（0 字节）；本仓 `.venv` 的 **7.3.1** 同一文本合成出 **26,064B** mp3。修：`~/bin/edge-tts` → 本仓 `.venv/bin/edge-tts`。
  - **修好后媒体链路端到端真出片（实测日志）**：`pipeline.media_stage.audio_track_produced`（`narration.mp3` 556,992B + `narration.srt` 2,668B）→ ComfyUI 出图 2,117,596B → `hyperframes render succeeded` → `pipeline.video_produced`（`03_video/output.mp4` **7,807,842B**，用时约 60s）。
- **唯一剩余结构性卡点 = G3 品牌身份门**：`brand_identity ✗ declared brand identity 'AI内容生产' not found in content`（其余 5 项全 pass）。根因与三选一方案见 **#202**（本轮补第 3、4 次复现 + 正面对照：**G0 不是恒拦**，本轮用过程类题目两跑均 pass）。**修 G3 属判据语义变更，交 owner 裁定**；本轮未改判据/提示词、未改冻结区。
- **口径提醒**：视频轨 DoD 要求 gate-report 里 **V2/V5/V7 真跑且 `pass`**，而 V 门排在 G3 之后 ⇒ **G3 恒拦时该判据结构性不可达**（#202 §影响）。本文件的 ❌ 属**已知阻塞**，不是新增退步。

**2 / 3 条轨未达标。**

| 轨 | 判定 | 证据 |
|:---|:---|:---|
| 文本轨 | ✅ **14 个达标** | `20260822_*` / `20260823_*` 一批：7×2.7–4.8KB 中文正文 + cost_log 真调用（`deepseek-v4-flash`）+ `pipeline_md5.json` |
| 图文轨 | ❌ **0 个** | 全部项目 `02_images/` 为空 |
| 视频轨 | ❌ **0 个** | 全部项目 `03_video/` 为空 |

**项目目录 32 个（2026-10-18 实测 55，以 `nightly_gap.py` 产物为准），其中 `cost_log.jsonl` 非空（= 真跑过）16 个。** `20260914_*` 那批阶段目录全空。

**验证矩阵（自动生成）**：场景数见 `automedia validate matrix` 产物（2026-10-18 实有 147 条）→ `passed 106 / unconfigured 31 / partial-pass 3 / None 3 / recovered 1`；
hard 场景 **10 条全过**；门 `missing=4`（L1–L4）· `unreachable=2`（G4/G5）。

**读法**：文本轨是真的，图文/视频轨是空的。`unconfigured 31` 主要是缺 LLM 密钥的真模型场景——
按 owner 决定（缺密钥先不配），这批**不计入本轮 DoD**，只记账。

### 2026-10-13 夜间复跑（在 main 481ad18 上）

- 批跑基线是 `e310ebb`（旧判据）→ 报「三轨全达标」；同步到 `481ad18` 后重跑 `scripts/nightly_gap.py` → **exit 1**、`gap = ["视频轨"]`、视频轨 `count=0`（`tracks.视频轨.ok=false`、`evidence=[]`）；图文轨证据数同时由 2 降到 1。
- 差异来源：#195/PR#196 的「继承文本证据子句」未进入批跑工作树 ⇒ 缺陷已立案 e2e-test-suite#166（修复在途）。
- ⚠️ **口径提醒：该晚的「三轨全达标记」不可引用**；本小节为重跑后的真实结论。

---

## 【活区】下一步队列

> 策略（L1 §4）：**先纵后横** —— 先把一条轨从头到尾打穿（真模型 + 真产物 + 持久落盘 + 验收），再复制。

1. **打穿图文轨**：`image-carousel` 走一次真跑，让 `02_images/` 出现真图片。它是三轨里离文本轨最近的一条（复用已有正文链路，只多一步出图）。
2. **打穿视频轨**：`video_only`/`short-video` 走一次真跑，让 `03_video/` 出真视频，**并让 V 门（V0–V7）真执行给出结论**（当前 V0/V1/V3/V4/V6 显式 `skipped`）。
→ **2026-10-15 状态：环境侧已打通（`whisper`/`edge-tts` 修好，实测真出片 7,807,842B），结构性卡点只剩 G3 品牌身份门（#202，等 owner 裁定）；V 门排在 G3 之后 ⇒ G3 不裁定则本条不可达。**
3. **持久落盘体检**：确认跑出来的项目落在 repo 内的项目目录，**不是 `/tmp`**。
4. **HITL 不阻塞**：验证非交互运行返回 `awaiting_hitl` + 专用退出码。
5. **（当前唯一未达标轨）打穿视频轨（复跑口径）**：视频轨需要**一次带真模型 cost_log 的 `video_only`（或 `short-video`）端到端跑**，达标需同时满足：`cost_log.jsonl` 非空 + `01_content/drafts/` 有 ≥500B 的 md + `03_video/` 有 ≥10KB 视频 + 该项目 gate-report `failed=0/errored=0` + V2/V5/V7 真跑且 pass（V0/V1/V3/V4/V6 允许 skip 但属已登记能力债 #193）。现有唯一候选 `20261003_turning-blog-posts-into-video-essays` 因缺 `cost_log`/draft 不达标。
  → **2026-10-19 状态：✅ 已闭合**（证据 `20261018_每周一次内容复盘小团队反救火手册`；门序 `pre-gate/CW/G0/G1/G2/G3/G6/V2/V5/V7` 全 pass、`status=success`、真实 `output.mp4` 7,867,543B；main 上固化依赖 PR #238 合并）。

### 已完成（agent 追加）

- 2026-10-13：复跑口径更正 —— 视频轨当前为 ❌（见上「2026-10-13 夜间复跑」小节）。
- 2026-10-15：**图文轨 3 → 4**（`20261014_a-practical-guide-to-weekly-content-reviews-for-small-teams`：真 draft 5,953B + cost_log 8 行 + 2.12MB 真图）→ 队列第 1 项（打穿图文轨）闭合。
- 2026-10-15：**队列第 3 项（持久落盘体检）复核闭合** —— 本轮 3 次真跑的 `00_project_info.json` / `01_content/drafts/` / `03_video/output.mp4` 全落在 **repo 内项目目录**（非 `/tmp`）；产品侧 hyperframes 的临时工程目录仍在 `/tmp/hyperframes_*`，但出片产物落项目目录，符合 DoD 附加硬要求 1。
- 2026-10-19：**视频轨 0 → 1 —— 三轨全达标**（`nightly_gap.py` exit 0；证据见上「2026-10-19 夜间复跑」）。

---

## 【活区】摩擦账本

> 规则（L1 §5）：**不挡住 DoD 的发现，当晚一律不修，只记账**。本阶段摩擦预算 = 0。

| 日期 | 发现 | 是否挡住 DoD | 处置 |
|:---|:---|:---|:---|
| 2026-09-30 | 门 `L1–L4` missing、`G4/G5` unreachable（已提 issue #130/#131） | 否 | 记账 |
| 2026-10-13 | 夜跑跑批不同步 main ⇒ 本仓矩阵测于过期判据（当晚「三轨全达标」系假绿） | 是（判据静默失效） | 已立案 e2e-test-suite#166（修复在途）；本仓不改跑批脚本 |
| 2026-10-13 | 本仓同时存在两份冻结区文档：docs/NIGHTLY.md 与 docs/NIGHTLY.html 未入库，与已入库的 docs/dev/plans/NIGHTLY.md 内容分歧 | 否（但会误导读文档的人） | 已立案本仓 #199，等 owner 裁定；本轮不动 |
| 2026-10-13 | 【活区】下一步队列第 2 项仍是 2026-10-07 修订前的措辞（「打穿视频轨…并让 V 门（V0–V7）真执行给出结论（当前 V0/V1/V3/V4/V6 显式 skipped）」），与 owner 2026-10-07 裁定的「允许 skip + 登记能力债」相冲突 | 否 | 本轮不改（L1 §5 摩擦预算=0）；已由本轮新增的队列第 5 项取代，待 owner / 下轮清理 |
| 2026-10-15 | 视频轨 `short-video` 三跑同型卡在 **G3**（`brand_identity`：declared `AI内容生产` not found in content），下游 G6/H0/V 门永不执行 ⇒ 视频轨 DoD 结构性不可达 | **是**（挡视频轨） | 已提 **#202**（10-13）；本轮补两跑复现 + G0 正面对照；**判据语义三选一交 owner 裁定，未自行改判据/提示词** |
| 2026-10-15 | `whisper` 不在 PATH（产品按 `runner.py:1990` 的 `shutil.which` 解析；跑批 preflight 认 `~/mamba/envs/whisper/bin`，产品侧不认）→ 媒体阶段 `tools_missing=['whisper']`，音频/视频/V 门输入全不产 | **是**（挡视频轨） | 环境层已修：`~/bin/whisper` → `~/mamba/envs/whisper/bin/whisper`；实测 `shutil.which('whisper')` = `/home/renanzai/bin/whisper` |
| 2026-10-15 | `edge-tts` 经 PATH 解析到 hermes venv **7.2.7** → 合成 `WSServerHandshakeError: 403`（0 字节），媒体阶段 `media_stage_failed`；本仓 `.venv` 的 **7.3.1** 可用 | **是**（挡视频轨） | 环境层已修：`~/bin/edge-tts` → 本仓 `.venv/bin/edge-tts`；实测 7.3.1 出 26,064B mp3，复跑后媒体链路真出片 |
| 2026-10-15 | 同题重复跑**复用同一项目目录**（`20261014_<slug>`）：`00_project_info.json` 被后跑覆盖（`project_id` 变）、`01_content/drafts/` 并列多份（本轮 4 份）、`cost_log.jsonl` 累积（本轮 3 跑 → 8 行）→ 一个项目目录不再对应单轮证据 | 否 | 记账（如需分轮证据，换题目或让产品按 `project_id` 分目录；不自行改产品） |

---

## 【活区】修订请求

> 认为冻结区某条不合理 → 写这里（附证据）。**不得自行修改冻结区。**

| 日期 | 目标条款 | 理由 + 证据 | 裁定 |
|:---|:---|:---|:---|
| 2026-10-06 | 视频轨 DoD 判据（本文 §【冻结区】完成定义表「视频轨」行）+ 其实现 `scripts/nightly_gap.py`（旧判据见提交 `47f5a9f` 的 `:72`；现行带 gate 证据的实现在提交 `e310ebb` / `9df04b6`） | 判据只看文件大小——`"video_ok": vid_max >= MIN_VIDEO_BYTES`，不读任何 gate 判定——因此一个 **V 门全部 skipped** 的项目，只要 `03_video/` 里有 ≥10KB 文件就会被判达标。这与 L1 §2.2「不得 skipped」冲突：skipped 的门不构成证据。证据：issue #181 记录的项目 `20261003_turning-blog-posts-into-video-essays`，其 gate-report 中 V0/V1/V3/V4/V6 为 skip（8 门 pass 3 / fail 0 / skip 5），而差距矩阵仍判绿。**诚实标注两点**：(1) 该证据项目目录现已不存在，我无法复现；当前 70 个项目里 0 个含 ≥10KB 视频，视频轨今天正确判 ❌（2/3 未达标），故**这不是正在发生的误判**。(2) L1 总纲在仓库外（`Hermes-Workspace/00-Records/dev-assets/NIGHTLY-PLAN-L1.md`），我未能读取 §2.2 原文，上述冲突依据来自 issue #181 的引述。**真正的缺陷是判据本身无法区分「V 门跑过」与「V 门被跳过」**，与当前是否误判无关。建议判据增取 gate 证据（如 gate-report 中至少一个 V 门为 pass）；但这会改动 DoD，属冻结区，按规矩等 owner / code profile 裁定，期间按原样执行。**（2026-10-07 更正两处：(1) 该证据项目目录**存在**且已复核——`03_video/output.mp4` = 5,117,183 B、gate-report 为 V2/V5/V7 `pass` / V0/V1/V3/V4/V6 `skip`，「目录现已不存在」一句有误；(2) L1 §2.2 原文已在仓库外文件读取并同步修订。）** | **已裁定（owner 2026-10-07）：采纳「带能力债的达标」**——冻结区判据已改为「文件 + gate 证据（V2/V5/V7 必须 pass；V0/V1/V3/V4/V6 计为登记能力债，登记见 #193）」；实现见本仓 `scripts/nightly_gap.py`（分支 `fix/181-video-gate-evidence`） |
