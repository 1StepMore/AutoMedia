# Production-matrix 验证证据 — 2026-11-20（Windows code 侧）

> 证据性质：本机（Windows 10.0.26300 x64，code 侧）真跑记录。
> run record 是本机临时区（gitignored），本文件 + manifest.json 是入库中转。
> 复跑命令 + commit sha + 时间 + 每格结论 + 失败格错误类，齐备（matrix-verdict-policy §4）。

## 环境

- commit：`40d09587abc000ea9dee97e921e776cb2686acf0`（main，PR #585 squash 后）
- 解释器：Windows 原生 Python 3.13.5（editable 安装，`pip install -e .`）
- LLM：本机既有 OpenAI 兼容端点，**全部经环境变量注入子进程**（`AUTOMEDIA_LLM_PROVIDER/BASE_URL/MODEL/REASONING_MODEL`，
  值取自本机 `~/.automedia/model_config.yaml`，无厂商硬编码、无密钥入库）；
  验证沙箱 seed 的 `provider: openai/model: gpt-4o-mini` 缺 base_url 时子进程会打到不可达端点
  （`Request timed out`）——**必须**按 `docs/dev/run-with-real-llm.md` §三 注入 env 四件套。
- 依赖实测：ffmpeg ✓ / edge-tts ✓（真合成 12.8KB mp3）/ hyperframes ✓ / chrome ✓；
  **缺**：bun、whisper CLI、comfyui（服务不可达）；remotion 引擎在 WSL(Ubuntu) 找 node workspace 失败（确定性）。
- 本机解释器上 `automedia validate run --all`：**162 场景全部 confidence=real，无 fake**。

## 判据命令与读数

```
$ python -m automedia validate matrix            # main@40d09587
  mcp:   declared=64 covered=63 missing=0 phantom=0 boundary_only=1
  cli:   declared=21 covered=21 missing=0 phantom=0 boundary_only=0
  gates: declared=33 covered=31 missing=0 phantom=0 boundary_only=0
  modes: declared=9  covered=9  missing=0 phantom=0 boundary_only=0
  # G4/G5 = 设计性 unreachable（不在任何 preset/命令路径），不计入 missing

$ python -m automedia validate run --all
  # validation-runs/20261120-014835-290077（18:52Z 完成，~65 min，真模型）
  passed: 129 / failed: 16 / unconfigured: 13 / partial-pass: 3 / recovered: 1
  hard-safety violations: 0（10 条 hard 场景全 passed）

$ python scripts/nightly_gap.py                  # 三轨机器判定
  文本轨 ✓ / 图文轨 ✓ / 视频轨 ✓（沿用 20261117/18 证据目录，8 个真模型 cost_log 项目）
```

## 失败 16 条的错误类归因（全部真跑，confidence=real）

### A. POSIX 工具结构性阻塞（Windows 侧不可跑；仓约定 suite 跑 Linux，`test_cli_leaves` 在 Windows 主动 skip）

场景步骤用 `find`/`ls`/bash-PATH（MSYS 与 python 的 `/tmp` 解析不同、bash 子进程 PATH 无 automedia）：

- text-only-journey、image-carousel-journey、social-thread-journey、auto-journey、qa-only-journey、
  repurpose-journey（draft 定位步）、e2e-topic-to-article、produce-article、produce-subtitle(定位步)、
  rollback-behavior（`automedia rollback` 经 bash 找不到命令，exit 127）、
  agent-user-lifecycle-journey（doctor 因本机缺 bun/whisper/comfyui exit 1 + POSIX 步）
- **质量结论不因步骤阻塞而缺失**：这些场景的管线步在本机多为 passed（如 text-only-journey 管线 74.8s
  全门 ✓，text-with-cover-journey attempt2 管线全 ✓），红的是产物定位步的 POSIX 语义。
- 复跑判定：换 Linux/WSL 侧即可判这些格；本机判 = blocked:env（不调低断言换绿）。

### B. 模型质量红（确定性内容门 vs 模型，2 attempts 内）

- text-with-cover-journey + produce-cover：attempt1 G0（hook-claims 禁语）3 次重写耗尽 → partial；
  **attempt2 管线步 passed**（模型产出合规）→ pass(retry)，首跑失败证据保留在
  `validation-runs/20261120-014835-290077`。attempt2 剩余红步 = A 类定位步。
- repurpose-journey：P2TwitterGate 长度门 3 次重试后 8/18 条 tweet 仍超 280 字 → attempt2 结果见补记。
- produce-carousel：图片全平（`body_*.png` stddev 0.0）→ 无 comfyui 时图像引擎退化为平色填充，
  按 matrix-ownership「图片必须过 Vision QA」判 **blocked:missing-dep(comfyui)**，不计覆盖率。

### C. 视频渲染引擎配置错位（本机可修，env 覆盖）

- produce-audio / produce-video / produce-subtitle：音频真产出（edge-tts narration 落盘成功），
  但 video 链解析到 **remotion**（用户 `~/.automedia/engines.yaml` 的 default），其 WSL node workspace
  缺失 → 确定性失败 → short-video 欠视频 → V1/V3/V6 skip → 惯例降级 partial → exit 1。
  修法（produce-audio.yaml 头部已写明）：`AUTOMEDIA_ENGINES_VIDEO_DEFAULT=hyperframes`
  （hyperframes available=True）→ 本机 batch3 复跑读数见补记。

### D. 设计性 partial-pass（需要 director 复核，按指南永不报绿）

- partial-pass-cli-contract / partial-pass-omni-extraction / partial-pass-progress-surface：
  场景自身以 min_passing/pass_ratio 锚定 partial-pass 政策本身，状态即其设计结果。

### E. unconfigured 13 条 = env 状态（不是 verdict）

- masterkey×6（AUTOMEDIA_MASTER_KEY，合成 key 即可跑）→ batch3 已跑，读数见补记
- dep-doctor-missing-ffmpeg（EXPECT_MISSING_FFMPEG 行为开关）→ batch3 已跑
- llm-unavailable-error-quality（EXPECT_LLM_UNAVAILABLE 行为开关）→ batch3 已跑
- short-video-journey / video-only-journey（EXPECT_VIDEO_ENGINE 声明 + 视频引擎真可用）→ batch3
- format-output-contract / orf-format-output-happy（EXPECT_ORF：ORF 适配器未安装 → 真缺口）

## 补记（batch 2/3 复跑）

### attempt 2（每格第 2 次尝试，首跑失败证据保留于 20261120-014835-290077）

| 场景 | attempt2 读数 | 结论 |
|:--|:--|:--|
| text-with-cover-journey | `validation-runs/20261120-025918-471584`：**管线步 passed**（G0 合规），仅 POSIX find 步红 | 管线质量 pass(retry)；场景状态 blocked:env（POSIX） |
| produce-cover | `validation-runs/20261120-030045-983983`：**管线步 exit 0**（cover 真产出），定位/属性步红（MSYS env.exe 与 python 的 /tmp 解析错位） | 管线质量 pass(retry)；场景状态 blocked:env（路径语义） |
| repurpose-journey | `validation-runs/20261120-032339-486100`：**管线步 passed（3/4）**——P2 长度门本次合规；仅 find 步红 | 管线质量 pass(retry)；场景状态 blocked:env（POSIX） |

### 图文轨 · 图片格 Vision QA（matrix-ownership：图片必须过 Vision QA）

- cover（produce-cover attempt2 真产物，1920×1080 RGB，126KB，stddev 31.1 非平色）：
  **Vision QA = FAIL**——标题文字渲染为豆腐块（CJK 字形缺失），判定 quality 红；
  根因 = 本机渲染链缺 CJK 字体依赖（blocked:missing-dep(cjk-font)）。
  证据图如实入库：`image-track/cover/cover.png`（sha256 前缀 ea4b89af1f7af84d）。
- 工具说明：visual-judge 子代理在本 harness 不可用（provider 缺失），按交付协议回退为
  agent 亲自读图判定；判定与证据如上，未降级口径。

### batch 3（masterkey / EXPECT 行为开关 / 视频链修复）

**masterkey 批（合成 key + 沙箱隔离仓，全部真跑通过）**：
connect-account-masterkey ✓ / disconnect-account-masterkey ✓ / disconnect-account-positive ✓ /
get-account-health-masterkey ✓ / get-account-health-positive ✓ / account-list-cli-behavior ✓ /
dep-doctor-missing-ffmpeg ✓（EXPECT_MISSING_FFMPEG 行为开关，模拟缺 ffmpeg 的 doctor 读数）。
run records：`validation-runs/20261120-0326xx~0327xx`。

**llm-unavailable-error-quality**：该场景的 EXPECT_LLM_UNAVAILABLE 是给「LLM 已知不可达」的
机器声明的旗标（场景描述原文）；本机 LLM 可达，诚实状态 = unconfigured。
本机强行置旗标产生的一轮红（20261120-032912）是**误用旗标的产物**，不作为缺陷证据——
真实断言（LLM 不可达时必须回结构化 LLM_ERROR + 恢复指引）在没有端点的机器上由旗标机器判。

**produce-* 视频链（基建修复记录，非抖动重试）**：
- 第 1 次（整库 suite）与第 2 次（batch3a，`AUTOMEDIA_ENGINES_VIDEO_DEFAULT`）失败根因相同：
  内置 `video.chain: [remotion, hyperframes]`（#351）中 remotion 在链解析探活通过、
  执行时才报 WSL node workspace 缺失，且按 deterministic 失败不换引擎。
- 修复：`AUTOMEDIA_ENGINES_VIDEO_CHAIN=hyperframes`（chain 解析器接受字符串，已实测
  resolved=[HyperFramesVideoEngine]）——第 3 次复跑读数见下。
- **produce-audio 第 3 次（基建修复后）：管线步 passed（2/4）**，run record
  `validation-runs/20261120-035240-574185`。真产物齐备（UTC 日期目录
  `Temp/automedia/prod-audio/20261119_播客音频如何提升品牌影响力/`）：
  `03_video/output.mp4` = **41.2s，h264 1920×1080 + aac，~4.9 Mbps（ffprobe 实测，可解码）**；
  `04_audio/narration.mp3` = 41.2s @ 48 kbps；`04_subtitle/narration.srt`。
  管线 V0–V7 门链全过（V1/V3/V6 真跑不再 skip）。剩余红步 = 定位/属性步的
  MSYS env.exe（/tmp→用户 Temp）与 python（/tmp→盘符根）路径语义错位 = blocked:env。
- **视频轨 Vision QA（抽帧亲验，visual-judge 不可用回退）**：主/副标题中文渲染正常
  （frame-0030.png、frame-0900.png 已入库 `video-track/render/`）；但模板**装饰元素**
  存在 tofu 字形（"AutoMedia ☒☒☒"）与截断（"a vibrant digi…"）——记 quality 缺陷，
  主内容合格、装饰不合格，视频轨本机判 = 真跑成立 + 装饰缺陷待修（模板字体回退）。
- **音频格阈值差距（如实记）**：场景自设生产级门槛 ≥60s / ≥128 kbps；真产物 41.2s @ 48 kbps
  （edge-tts 默认码率）→ 该格按场景口径 = quality 红（门槛差异，非链路故障）。
- 对比：**视频渲染链的 CJK 字体正常**（视频轨主文本无 tofu），**封面渲染链缺 CJK 字形**
  ——两条渲染链的字体回退行为不同，封面格的 tofu 是封面模板链的缺陷。
- **produce-video 第 3 次（链修复后）：管线步 passed（2/4）**，run record
  `validation-runs/20261120-041957-327296`；真产物
  `Temp/automedia/prod-video/20261119_短视频时代的品牌内容生产方法/03_video/output.mp4`。
  剩余红步 = 同款 /tmp 路径语义（blocked:env）。
- **produce-subtitle 第 3 次（链修复后）：管线步 passed（exit 0）**，run record
  `validation-runs/20261120-043253-615066`；V2/V4/V5/V7 ✓、V1/V3/V6/H0 ⊘。
  剩余红步 = 同款 /tmp 路径语义（blocked:env）。

## 终局账目（本机可达的诚实边界）

| 判据 | 状态 | 说明 |
|:--|:--|:--|
| 矩阵满格 0 missing | **✓ 达成** | main@40d09587 四面 missing=0（matrix-final.txt） |
| 质量门全绿 | **✓（门级）** | hard-safety 0 违规、10 hard 全过；整库管线级 G/V 门链真跑全绿；162 场景全 confidence=real |
| 每格产出质量 | **部分 + blocked 如实入账** | 文本/图文文字管线级绿；封面图 = quality 红（CJK tofu，blocked:missing-dep(cjk-font)）；视频轨 V 门真跑成立但装饰元素有字形缺陷；音频格低于场景自设 60s/128kbps 门槛 |
| 证据入库 | **✓** | 本目录 + manifest.json（PR 提交）；run records 在本机 validation-runs/（gitignored，stamp 已记录） |

本机 blocked 清单（复跑条件已写明）：POSIX 步类 blocked:env（Linux/WSL 侧可判）、
comfyui 缺失（图片格）、CJK 字体（封面模板链）、remotion WSL workspace（已用
hyperframes 链覆盖绕开）、场景步骤 /tmp 语义错位（MSYS vs python）。

## 诚实声明

- 本机所有跑动均为真模型（confidence=real 全量），fake 未用于任何质量结论。
- 本机无法判绿的格（A/C/D/E 类）均给出错误类、根因与复跑条件，未调低任何断言。
- 视频轨/图文轨图片格的最终绿判定需 hyperframes 渲染真跑 + Vision QA（batch3 后补记）。
