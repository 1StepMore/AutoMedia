# 2026-11-21 production-matrix evidence — code-side Windows shift (auto agent)

> 判活：owner:human-agent 周末在班（周六全天归主人侧）。所有跑数 confidence=real（spark-x2.6 真模型，无 fake）。
> 环境：Windows 原生 `.venv_win`（Python 3.12）+ WSL `.venv`（Python 3.14，POSIX 格补跑侧）；
> LLM = 本机已有 OpenAI 兼容端点（spark-x2.6 推理模型，单模型），key 经环境层注入（不读凭据文件）。

## 本班四件事（全部落地）

### 1. 三个产品修复合入 main（各一 PR，hook 全绿）

| PR | 内容 | 判据 |
|---|---|---|
| #605 `fix(win32)` | ol_adapter `$HOME` 感知（Windows `Path.home()` 无视 HOME 的存量 bug）+ video_hyperframes/reg208 POSIX-only 属性 win32 mypy 标注 + reg208 解释器候选常量化（测试去机器状态化） | 本地 pre-commit 套件（含全量 pytest hook）在 Windows exit 0；两个失败点在干净 HEAD 复现过（平台债，非回归） |
| #606 `fix(llm)` | `AUTOMEDIA_LLM_TIMEOUT` → `llm.text_generation.timeout` 映射（.env.example 与 agent-reference 早就文档化了它，代码从未接；通用下划线切分把它送到没人读的 `llm.timeout`） | 回归测试 63/63；CW 门内容级 completion 实测 106-214s，60s 默认超时必挂（timeout 是唯一没有 env 覆盖面的 LLM 旋钮） |
| #608 `fix(gates)` | B站 prompt 硬性要求逐字 `[TIMESTAMP]` 字面格式（正例+反例），P4 scene_markers 质量重试从不收敛变可收敛（与 #595/#600 同类：prompt 对齐门契约，口径只紧不松） | repurpose-journey attempt2 真模型 passed 4/4（attempt1 证据保留：`validation-runs/20261121-054407-329683`，P2/G2 重试自愈、P4 两连红） |

### 2. Owner 点名的 6 条 journey 复跑（G1 #595 / G2 #600 修复后首跑）：**5 绿 1 blocked**

| 场景 | 读数 | 侧 | run record |
|---|---|---|---|
| text-only-journey | passed 5/5（CW 213.6s、G0 112.5s、G1 73.9s、G2 110.2s 全真跑绿） | WSL | `20261121-050312-914983` |
| social-thread-journey | passed 4/4 | WSL | `20261121-051742-569346` |
| repurpose-journey | passed 4/4（pass(retry)：attempt1 P4 scene_markers 两连红 → #608 修复 → attempt2 收敛） | WSL | `20261121-061259-249978`（首跑失败证据 054407） |
| e2e-topic-to-article | passed 5/5 | WSL | `20261121-062332-745210` |
| text-with-cover-journey | passed 4/4（封面真产出） | WSL | `20261121-063331-660053` |
| auto-journey | **blocked**：V5 cue #44 ASR 锚点覆盖 33% < 45%（字幕保真红，非环境），3 次重试瞬败（输入不变）→ level2 整条重生成循环跑不进 1500s 步超时 | WSL×2 + Win×1 | `20261121-070015-953493` / `-073115-394069` / `-070243-682810` |

**结论（分清已修好 vs 残留）**：G1 官话词 / G2 长句修复在这 5 条真模型链上成立——G0-G6 内容门全绿，G2 偶发长句由重试自愈（attempt 内 2 次尝试内收敛，符合口径 §2）。残留 = auto-journey 的 V5 字幕-旁白保真（内容类红，非上轮 G1/G2 类），需要 narration/SRT 保真根因调查或 Owner 对 V5 锚点阈值的标定决策。

**诊断记录（Windows 侧 CW ~54s APITimeoutError）**：Windows validate 沙箱内 4 次、WSL 0 次、同机直连探针 0 次（24.3s/126.7s 成功）+ 直接 CLI 管线成功——判端点 transient（机理未定，与沙箱子进程环境的相关性未证实）。缓解：WSL 侧跑管线类场景 + #606 的 timeout 映射。

### 3. 断言半边补格（只重跑红格，未整批重跑——口径 §2）

本班新绿（全部 confidence=real）：

- qa-only-journey 4/4（WSL `20261121-073637-034795`）
- produce-article 4/4（WSL `20261121-074433-371623`）
- produce-subtitle 7/7（WSL `20261121-081607-616866`）
- produce-video 4/4（WSL 真 render，hyperframes 链，`20261121-091246-986092`）
- produce-cover 4/4（pass(retry)：attempt1 WSL 图像阶段 1800s 挂死 → attempt2 收敛，`20261121-092159-215735`，首跑证据 084621）
- rollback-behavior 4/4（WSL——#564 平台债在 WSL 侧消除；Windows 侧仍是 POSIX 结构性）
- masterkey 批 5/5（Windows，合成 key `val-shift-20261121-*`，`20261121-073444..073455`）
- publish-draft-only-real-adapters → 诚实 unconfigured（需 21 项真实平台凭据，owner-only）
- llm-unavailable-error-quality → 诚实 unconfigured（本机 LLM 可达，不该设 EXPECT 开关）

视频双 journey（EXPECT_VIDEO_ENGINE=1 + hyperframes）：short-video-journey 与 video-only-journey 均 **V5 瞬败重试循环 → 1500s 步超时**（`20261121-094909-530740` / `20261121-101517-710672`）。与 auto-journey 的 V5 红同源贯通：**edge-tts 48kbps 音频 → faster-whisper 转写噪声 → V5 cue ASR 锚点覆盖跌破 45%**。归类 blocked:missing-dep(high-bitrate-tts)：≥128kbps 的 TTS 通道（Azure key，owner-only，#604 已修 192kbps 默认）是这三格的前置能力。V5 门本身在正确工作（真红，不许放松口径）。

### 4. G4/G5 尝试与撤回（诚实性架构的胜利）

- 尝试：场景真跑门类补 covered 31→33（PR #607，本地 2/2 过）。
- 撤回：仓守卫 `test_proves_gates_reachability` 拒绝——proves_gates 只许声明 preset/命令面可达的门；baseline count（163）与 coverage 数字（31）有测试 pin。**接线前场景不能认领 G4/G5**。
- 去向：issue #609（owner:master）三选一决策——维持 unreachable-by-design / 接线进发布流 / 退役。撤回后 gates 面 = covered 31/33、missing=0、unreachable=[G4,G5]。

## 终态矩阵读数（收口时刷新 → matrix-final.txt）

- 四面：mcp missing=0（boundary_only=1 = run_validation_suite，R-09 递归豁免，allowlist expires 2026-12-31）；cli 21/21；gates missing=0（covered 31/33，unreachable=[G4,G5] 守卫口径）；modes 9/9
- 断言半边：见 matrix-final.txt 场景卡片（每格有 last 状态 + 原因；分母 163 不消失）
- nightly_gap：exit 0（三轨全达标；hard 10/10）

## 本班诚实账（红格与缺依赖，不调口径）

终态 163 格：**148 passed / 7 failed / 3 partial-pass(设计) / 4 unconfigured(有因) / 1 recovered**；0 格无状态。

| 格 | 类 | 原因 |
|---|---|---|
| auto-journey + short-video-journey + video-only-journey | blocked:missing-dep(high-bitrate-tts) ← V5 真红 | 48kbps edge-tts → ASR 噪声 → V5 锚点 <45%（门在正确工作）；≥128kbps TTS = Azure key（owner-only） |
| produce-audio | blocked:missing-dep(high-bitrate-tts) | 48kbps < 128kbps 场景门限（同上源） |
| image-carousel-journey + produce-carousel | blocked:missing-dep(comfyui) | 无 comfyui 图像退化平色，Vision QA 口径不许过 |
| agent-user-lifecycle-journey | blocked:missing-dep(bun/whisper/comfyui) | doctor 全表绿是场景前提 |
| format-output-contract + orf-format-output-happy | blocked:missing-dep(orf-adapter) | ORF 适配器未安装 |
| publish-draft-only-real-adapters | unconfigured | 需 21 项真实平台凭据（owner-only） |
| llm-unavailable-error-quality | unconfigured | 本机 LLM 可达（EXPECT 开关语义=只在 LLM 不可达机器设） |
| partial-pass ×3 | 设计性 partial | 场景自身锚定 partial-pass 政策，永不报绿（指南） |
| init-config-recovery | recovered | 合法终态 |
| rollback-behavior (Windows) | POSIX 结构性 | WSL 已绿（见上）；Windows 定位步仍红 |

## flaky 账（口径 §2）

- G2：2 次首跑红、重试收敛（auto-journey attempt1、repurpose attempt1 内）→ pass(retry) 记录在案
- P2：1 次超长推文 → 重试收敛（repurpose attempt1 内）
- P4：2 连红不收敛 → #608 修复后收敛（产品修复，非 flaky）
- CW 超时：Windows 沙箱 4 次 ~54s（transient，机理未定）、WSL 0 次
- 本班重跑中 flaky（重试内收敛）比例：3/重跑格数≈30 格 ≈ 10% 边缘——已记录，未为换绿调低任何断言
