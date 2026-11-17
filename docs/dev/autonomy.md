# 自驱契约（AutoMedia）

> 面向：任何被 owner 指派到这个仓的 agent / harness —— 不管它跑在 owner 的 Windows harness、本机 Hermes，还是未来某个 contributor 的机器。
> 目标：**读 AGENTS.md → 读本文 → 跑 selfcheck → 就能自主推进**，不需要任何人来口头交代「现在该干什么」。

## 0. 三分钟上手

```bash
python3 scripts/agent/autonomy.py selfcheck      # 这台机器 + 这个 clone 能不能自驱？缺什么直接说
python3 scripts/agent/autonomy.py status         # 现在该不该我干（有租约按租约，没租约按缺省时段）
python3 scripts/agent/autonomy.py next -n 3      # 拿下一批可开工的
python3 scripts/agent/autonomy.py claim 461 --branch fix/461-x   # 认领（写标签 + 留认领评论）
```

`status` / `gate` 返回 **exit 3 = 现在不该你干**（不是错误）。拿到 3 就干净退出，不许「就跑一点点」。

## 0.5 先声明「我在哪一侧」（每台机器一次）

工具里所有 `--lane` / `--owner` 的缺省值是**本机侧**（`owner:code-auto`）。如果你跑在
owner 自己的 harness 上，先在本机声明立场，否则 `gate` 会返回 **exit 3**（"不是你的班"），
看起来像"轮不到我"而实际只是缺省值站错了边：

```bash
mkdir -p .agents/autonomy && echo owner:human-agent > .agents/autonomy/lane
```

`.agents/autonomy/` 已 gitignored，这个声明只影响本机、不会传染给另一台机器。
临时的等价写法：`AUTONOMY_LANE=owner:human-agent python3 scripts/agent/autonomy.py gate`

## 1. 两套状态，别混

| 状态 | 存在哪 | 谁看得见 | 用途 |
|:--|:--|:--|:--|
| **授权（lease）** | `.agents/autonomy/lease.json`（本机，gitignored） | 只有这台机器 | owner 说「交给你了」才存在；带目标 + 到期时间 |
| **认领（claim）** | GitHub 标签 `status:claimed` + `owner:*` + 认领评论 | 所有机器所有人 | 谁在做这一单，全局唯一真相 |

- owner 说「交给你了，做到 22:00，目标是 X」⇒ `autonomy.py start --goal X --until 22:00`
- 到期**自动失效**，不需要 owner 再喊停；中途收回 ⇒ `stop --reason owner-reclaim`
- 没有租约时按缺省时段：工作日 09:00–23:00 归 `owner:code-auto`，工作日 23:00–09:00 + 周末全天归 `owner:human-agent`。两侧不同时动手。

## 2. 什么算「可开工」

```
agent-ready ∧ 无任何 owner:* 标签 ∧ 无 status:claimed ∧ 没有被任何 open PR 认领（标题 #N / close|fix|resolve #N）
排序：bug 优先，同类按编号升序（老单先做，避免烂尾）
```

**不许做名单外的活。** 想加活 ⇒ 先开 issue 并写清执行契约：基线 sha / 分支名 / DoD 命令 / 边界（不许动什么）/ 卡住怎么办。缺一条就别打 `agent-ready`。

## 3. 六类极端阻塞（只有这六类可以停手问人）

| # | 类别 | 判据 |
|:--|:--|:--|
| E1 | 单向门 | 不可逆或超出授权：删数据、改生产配置、对外发布、花钱、动 main、动别人的分支 |
| E2 | 判据缺失 | 目标没定义「做到什么算完」，任何一步都无法判断对错 |
| E3 | 真取舍 | 两条以上路线都成立且**没有客观依据**分优劣（方向/口径，不是实现细节） |
| E4 | 外部断供 | key 失效、权限丢失、上游下线、额度耗尽，且无权修复 |
| E5 | 规则冲突 | 与 owner 刚定的规则或本仓红线直接冲突 |
| E6 | 打转 | 同一目标连续 2 次尝试，结论与证据集完全相同 |
| E7 | 目标达成 | 当前目标判据已达标（`autonomy.py goal` ⇒ `ACHIEVED`），继续干必须先有新目标 |

**不算阻塞**（自己判）：能查文档/重试/换实现；测试红但根因可定位；两条实现路线（选一条+写理由）；命名/目录/拆函数/挑库；缺时间缺 token（换免费档）；issue 契约不完整（自己补并留痕）。

**停手前必做**：写一条阻塞记录（类别、证据、试过什么、下一步可选）⇒ **换下一条继续**。单条阻塞不是停整个班次的理由；只有名单里每一条都阻塞才整体停。

## 5. 目标达成之后（E7）—— 别自己找活干

当前目标写在 `docs/dev/goals.md`，其中 `<!-- goal-cmd: … -->` 是**判据命令**，`exit 0 = 达标`。

每班开工先跑：

```bash
python3 scripts/agent/autonomy.py goal          # ACTIVE = 继续推进；ACHIEVED = 达标
```

- `ACTIVE` ⇒ 正常推进当前目标
- `ACHIEVED` ⇒ 按 `docs/dev/goals.md` 的「达标之后做什么」四步走（收租约 → 开 `[goal-achieved]` issue 贴原始输出 → 下一阶段标 `asked-owner` → **停手**），
  然后按那里的**提问模板**问 owner，不要开放式提问
- **不要自己定下一阶段**：目标属方向，是 owner 的；agent 只给候选 + 推荐 + 代价
- **不要达标后继续领活**：那是偏离方向烧 token


## 4. harness 侧必须自己提供的东西（写不进仓）

| 件 | 为什么写不进仓 | 怎么自证 |
|:--|:--|:--|
| `gh` 登录 / token 权限 | 凭据不能入库 | `autonomy.py selfcheck` 打印登录身份 |
| Python ≥3.10 + 项目 venv | 平台相关 | `selfcheck` + 本仓 setup |
| 媒体链依赖（ffmpeg / TTS / 渲染引擎） | 系统级安装 | 本仓门禁 + `make doctor` 类探针 |
| 调度器（cron / 定时 / 常驻） | 每台机器不同 | 只需保证「按租约周期性唤醒」 |
| LLM / TTS 通道与额度 | 账号相关 | 报告里写清用的是哪档 |
| 产物目录（`AUTOMEDIA_PROJECTS_DIR`） | 位置由 agent 决定但必须持久 | `nightly_gap.py` 要用它发现产物 |

## 5. 本仓的达标读数（"矩阵"在哪、怎么读）

**矩阵真身 = `scripts/nightly_gap.py`**（冻结区：agent 只跑、不改）。定义文本在 `docs/NIGHTLY.md`。

```
三条轨，每条都要有真模型端到端跑 + 产物落在持久目录 + 门链通过
  共同前提 最新 gate-report 无 fail/review，跑批 status 不是 partial/failed
  文本轨   cost_log.jsonl 非空 ∧ 01_content/drafts/ 有 ≥1 个 ≥500B 的 md
  图文轨   文本轨两条 ∧ 02_images/ 有 ≥1 个 ≥1KB 的图片
  视频轨   文本轨两条 ∧ 03_video/ 有 ≥1 个 ≥10KB 的视频 ∧ gate-report 里 V1/V2/V5/V7 真跑且 pass
三态：pass / fail / **unverified**（毫无证据）—— unverified **绝不当作 pass**
```

```bash
.venv/bin/python scripts/nightly_gap.py --json-out nightly/gap.json --md-out nightly/gap.md
# exit 0 = 三轨全达标 / 1 = 仍有差距（正常）/ 2 = 用法或环境错（需人介入）
```

**出口径注意（★重要）**：本仓 `gap.json` **没有 `gap_units` 字段**（与 Omni 口径不同），跨仓比较时不要套用别家的字段名 —— 读 `tracks` / 三态计数。

## 6. 交接协议（最容易坏的一环）

- **到点前 30 分钟**：在飞的东西必须变成远端可见形态（分支已 push + PR 已开，或状态标 `blocked-*` 且写清卡点）。
- **不留只在工作树里的改动**：换班期间另一侧可能切分支，未提交内容会丢。
- **接上班 10 分钟**：`gate` 确认在班 → 同步（比对 sha，别看时间）→ 读对方名下的 open PR，避免重复做同一缺口。

## 7. 新仓接入清单（复制这套到任何新项目）

1. 放 `scripts/agent/autonomy.py`（本文件同目录，纯 stdlib，无项目依赖）。
2. 在 `AGENTS.md` 加指针指向本文。
3. 确保标签存在：`agent-ready` / `status:claimed` / `owner:code-auto` / `owner:human-agent` / `owner:merge`（`selfcheck` 会列出缺哪个）。
4. `.gitignore` 加 `.agents/autonomy/`。
5. 跑 `python3 scripts/agent/autonomy.py selfcheck` 直到全绿。
