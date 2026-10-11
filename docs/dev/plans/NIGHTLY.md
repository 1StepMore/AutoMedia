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
| **图文轨** | `image-carousel`（+ `social-thread`） | 同上 **+** `02_images/` 有 ≥1 个 **≥1KB** 的真图片 |
| **视频轨** | `video_only` / `short-video` | 同上 **+** `03_video/` 有 ≥1 个 **≥10KB** 的真视频 **+** 该项目存在 gate-report 且 `failed=0 / errored=0` **+** 有诚实生产者的门（**V2/V5/V7**）必须真跑且 `pass` **+** 所有 `skipped` 必须落在已登记能力债集合（**V0/V1/V3/V4/V6**，登记见 #193）内 → 任何**新增 skip**（不在这五门内）＝退步，判 ❌ |

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

**2 / 3 条轨未达标。**

| 轨 | 判定 | 证据 |
|:---|:---|:---|
| 文本轨 | ✅ **14 个达标** | `20260822_*` / `20260823_*` 一批：7×2.7–4.8KB 中文正文 + cost_log 真调用（`deepseek-v4-flash`）+ `pipeline_md5.json` |
| 图文轨 | ❌ **0 个** | 全部项目 `02_images/` 为空 |
| 视频轨 | ❌ **0 个** | 全部项目 `03_video/` 为空 |

**项目目录 32 个，其中 `cost_log.jsonl` 非空（= 真跑过）16 个。** `20260914_*` 那批阶段目录全空。

**验证矩阵（自动生成）**：场景 144 条 → `passed 106 / unconfigured 31 / partial-pass 3 / None 3 / recovered 1`；
hard 场景 **10 条全过**；门 `missing=4`（L1–L4）· `unreachable=2`（G4/G5）。

**读法**：文本轨是真的，图文/视频轨是空的。`unconfigured 31` 主要是缺 LLM 密钥的真模型场景——
按 owner 决定（缺密钥先不配），这批**不计入本轮 DoD**，只记账。

---

## 【活区】下一步队列

> 策略（L1 §4）：**先纵后横** —— 先把一条轨从头到尾打穿（真模型 + 真产物 + 持久落盘 + 验收），再复制。

1. **打穿图文轨**：`image-carousel` 走一次真跑，让 `02_images/` 出现真图片。它是三轨里离文本轨最近的一条（复用已有正文链路，只多一步出图）。
2. **打穿视频轨**：`video_only`/`short-video` 走一次真跑，让 `03_video/` 出真视频，**并让 V 门（V0–V7）真执行给出结论**（当前 V0/V1/V3/V4/V6 显式 `skipped`）。
3. **持久落盘体检**：确认跑出来的项目落在 repo 内的项目目录，**不是 `/tmp`**。
4. **HITL 不阻塞**：验证非交互运行返回 `awaiting_hitl` + 专用退出码。

### 已完成（agent 追加）

---

## 【活区】摩擦账本

> 规则（L1 §5）：**不挡住 DoD 的发现，当晚一律不修，只记账**。本阶段摩擦预算 = 0。

| 日期 | 发现 | 是否挡住 DoD | 处置 |
|:---|:---|:---|:---|
| 2026-09-30 | 门 `L1–L4` missing、`G4/G5` unreachable（已提 issue #130/#131） | 否 | 记账 |

---

## 【活区】修订请求

> 认为冻结区某条不合理 → 写这里（附证据）。**不得自行修改冻结区。**

| 日期 | 目标条款 | 理由 + 证据 | 裁定 |
|:---|:---|:---|:---|
| 2026-10-06 | 视频轨 DoD 判据（本文 §【冻结区】完成定义表「视频轨」行）+ 其实现 `scripts/nightly_gap.py:72` | 判据只看文件大小——`"video_ok": vid_max >= MIN_VIDEO_BYTES`，不读任何 gate 判定——因此一个 **V 门全部 skipped** 的项目，只要 `03_video/` 里有 ≥10KB 文件就会被判达标。这与 L1 §2.2「不得 skipped」冲突：skipped 的门不构成证据。证据：issue #181 记录的项目 `20261003_turning-blog-posts-into-video-essays`，其 gate-report 中 V0/V1/V3/V4/V6 为 skip（8 门 pass 3 / fail 0 / skip 5），而差距矩阵仍判绿。**诚实标注两点**：(1) 该证据项目目录现已不存在，我无法复现；当前 70 个项目里 0 个含 ≥10KB 视频，视频轨今天正确判 ❌（2/3 未达标），故**这不是正在发生的误判**。(2) L1 总纲在仓库外（`Hermes-Workspace/00-Records/dev-assets/NIGHTLY-PLAN-L1.md`），我未能读取 §2.2 原文，上述冲突依据来自 issue #181 的引述。**真正的缺陷是判据本身无法区分「V 门跑过」与「V 门被跳过」**，与当前是否误判无关。建议判据增取 gate 证据（如 gate-report 中至少一个 V 门为 pass）；但这会改动 DoD，属冻结区，按规矩等 owner / code profile 裁定，期间按原样执行。**（2026-10-07 更正两处：(1) 该证据项目目录**存在**且已复核——`03_video/output.mp4` = 5,117,183 B、gate-report 为 V2/V5/V7 `pass` / V0/V1/V3/V4/V6 `skip`，「目录现已不存在」一句有误；(2) L1 §2.2 原文已在仓库外文件读取并同步修订。）** | **已裁定（owner 2026-10-07）：采纳「带能力债的达标」**——冻结区判据已改为「文件 + gate 证据（V2/V5/V7 必须 pass；V0/V1/V3/V4/V6 计为登记能力债，登记见 #193）」；实现见本仓 `scripts/nightly_gap.py`（分支 `fix/181-video-gate-evidence`） |
