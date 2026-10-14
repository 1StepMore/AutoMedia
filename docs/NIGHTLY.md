# NIGHTLY.md —— AutoMedia 不眠计划（冻结区 / DoD）

> **本文件是 `00-Records/dev-assets/NIGHTLY-PLAN-L1.md` §2.2（AutoMedia 段）在**仓库内**的镜像**，
> 目的是让在本仓干活的 agent 能直接看到自己项目的完成定义（冻结区纪律）。
> **权威来源仍是总纲**；两者冲突时以总纲为准，并立刻回来同步本文件。
> 口径修订只能由 owner 裁定；**agent 不得修改本文件的 DoD 文字，只能在活区写「修订请求」**。
> 镜像落库时间：2026-10-12（来源：总纲 §2.2，含 owner 2026-10-07 视频轨口径修订）。

## 生产单元 = 模式类（3 类）

底层模式 9 个：`auto` / `text_only` / `text_with_cover` / `video_only` / `qa_only` /
`image-carousel` / `social-thread` / `short-video` / `repurpose`；本阶段归并成 3 类。

| 类 | 覆盖模式 | 达标判据 |
|:---|:---|:---|
| **文本轨** | `text_only`（+ `text_with_cover`） | 一次真模型端到端：`Pipeline finished: success` + exit 0；产出物齐（draft 实质内容非模板 / 门控报告 md+html+json 自包含 / pipeline_md5.json）；cost_log 有真模型记录 |
| **图文轨** | `image-carousel`（+ `social-thread`） | 同上 + **图片产物真实生成**（张数、尺寸、与文案的对应关系） |
| **视频轨** | `video_only` / `short-video` | 同上 + **视频文件真实生成** + **该项目有 gate-report 且 `failed=0 / errored=0`** + **有诚实生产者的门（V2/V5/V7）真跑且 `pass`** + **无诚实生产者的门（V0/V1/V3/V4/V6）允许 `skipped`，但须登记为能力债**（AutoMedia #193）→ **任何新增 skip（不在这五门内）＝退步，该轨判 ❌** |

### 视频轨口径修订（owner 2026-10-07 裁定，采纳「带能力债的达标」）

原表述「V 门（V0–V7）真实执行并给结论（不是 `skipped`）」**不可满足**——V0/V1/V3/V4/V6 五门在仓库里
**没有诚实生产者**（逐门证据见 AutoMedia #193，来源 `.trae/documents/video-track-remediation-plan.md` §一），
硬要不 skip 就只能造数据，违反 L1 红线「不得为让门不 skip 而写假数据」。修订后：判据必须能区分
「门跑了并 pass」与「门被 skip」；无生产者的门以**登记能力债**的形式明面挂着（`gap.json` 的
`capability_debt` 字段），不计入达标但不许静默忽略。分歧原始记录：AutoMedia #181。

## 两条附加硬要求

- **产物必须落在持久目录**，不许落在 `/tmp`（当前唯一一次真跑的产物就在 `/tmp/automedia/journey-projects/…`，重启即失）
- **HITL 不许阻塞**：非交互运行必须返回 `awaiting_hitl` + 专用退出码，不许无限等待人工

## 环境前置（2026-10-03 起，code profile 已落地）

| 能力 | 现状 | 夜跑应如何对待 |
|:---|:---|:---|
| 图像引擎 | ✅ 本机 **ComfyUI** `127.0.0.1:8188`，systemd user service `comfyui.service`（enabled+active，崩了自动拉起）；模型 SD1.5 `v1-5-pruned-emaonly.safetensors` + `RealESRGAN_x4plus.pth` | 图文轨**不再算环境缺口**：可直接跑 `automedia run --mode image-carousel`。若 8188 探活失败 → 先 `systemctl --user restart comfyui` 再跑；仍失败才记「需人介入」 |
| 视频引擎 | ✅ **hyperframes 已装且实测可渲染**（v0.7.20）——专用目录 `/home/renanzai/hyperframes-cli/node_modules/hyperframes` + 全局命令 `~/bin/hyperframes`；渲染需 **Linux** Chrome（`~/.cache/ms-playwright/chromium-1234/chrome-linux64/chrome`）；本机部署配置在 `~/.automedia/config.yaml`（cli_command + chrome_path + timeout 900） | 视频轨**不再算环境缺口**：真跑 `video_only`/`short-video`。**V 门口径按上文 owner 2026-10-07 修订**（有生产者的门必须真跑；无生产者的五门允许 skip 但须登记能力债） |
| 出图质量口径 | 2026-10-03 修复：原生分辨率（长边 512）+ ESRGAN 放大，实测 42.8s/张、封面可用；细看仍有 SD1.5 级瑕疵 | 「够封面用」是当前基线；抬到「付费级」需能力取舍（SDXL / hires-fix），**等 owner 定基线**，夜跑不得自行改口径 |

## 本仓差距产物的 schema 提醒（给收集方）

- 产物路径：`nightly/gap.json` + `nightly/gap.md`（`nightly/` 已 gitignore）
- **本仓 `gap.json` 的 schema 与其他两家不同**：顶层是 `schema / project / generated_at / total_units / passing_units`
  —— **没有 `gap_units` 字段**，不要套用 AutoInfo/Omni 的口径去读它。
- 写入形态：脚本只在结尾一次性落盘；跑批层（`e2e-test-suite/scripts/nightly_batch.sh`）负责「逐通道落账 + 中断可查」，
  本仓脚本不需要（也不应该）为跑批层做额外改造。
