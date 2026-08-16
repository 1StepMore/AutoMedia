# LOOP-LOG — AutoMedia validation 循环记录

> 机制（对齐 AutoInfo 2026-08-15 规范）：每次迭代循环的关键事件、根因、修复、验证结果必须记录在此；
> 每次迭代开始前必复查「坑清单」；新坑当天追加（现象 → 根因 → 预防）。

## 2026-08-16 第二轮 validation（真 LLM 模式，PR #79/#80 后 100 场景）

### 结果

真 LLM 全量（20260816-184308，100 场景，2008s）：**90 passed / 3 failed / 7 unconfigured**
- 3 failed 全为 PR #79 新增 journey 场景（qa-only / short-video / social-thread）的第 4 步 `real-LLM quality spot-check answers`
- 单独复跑定性：qa-only 88.0s ✅ / short-video 130.9s ✅ / social-thread 第 1-3 次失败、第 4 次 177.2s ✅ → **LLM 时段波动（DeepSeek 间歇性截断 JSON）**，非代码 bug。3 个场景重试后全部转绿（93 passed / 0 failed / 7 unconfigured）
- 证据：直调 `evaluate_content_quality` 工具 3 连发全 OK（26.7s / 20.3s / 17.6s），同一 content 之前失败之后成功——间歇性输出截断（`Invalid JSON: EOF at line 9 column 16, input_value='{"quality_score": 0....n ], "suggestions":'`）
- unconfigured 7 = 与首轮完全一致（masterkey ×4 / WECHAT+ZHIHU / EXPECT_MISSING_FFMPEG+EXPECT_ORF 验证开关），客观缺 env

### 坑清单（迭代前必查！）

新坑 #8（2026-08-16 追加；坑 #1-7 见下方 2026-08-15 首轮清单）：**DeepSeek 间歇性截断 JSON**——`evaluate_content_quality` 等 LLM 工具在波动时段返回截断 JSON（`Invalid JSON: EOF at line 9 column 16, input_value='{"quality_score": 0....'`）；同一 content 直调 3 连发 26.7s/20.3s/17.6s 全 OK 证明是间歇性。全量跑后 3 个 journey spot-check 步骤同批 failed 时优先怀疑时段波动，单独复跑定性后再动代码

## 2026-08-15 首轮 validation（fake 确定性模式）

### 结果

首轮（未修正环境）：75 passed / 9 failed / 7 unconfigured（91 场景，125.7s）
修正环境后重跑（20260815-022026）：**83 passed / 1 failed / 7 unconfigured**（152.1s）
- failed 唯一 = text-only-journey（fake-LLM 局限，见坑 #4）
- unconfigured 7 = 环境缺失（见下表）

真 LLM 模式（20260815-024524，OpenCode Go deepseek-v4-flash）：**81 passed / 2 failed / 8 unconfigured**（347.9s）
- ✅ text-only-journey 转绿（真 LLM 产生 >500c draft）
- ❌ run-brand-strategy-llm / run-pipeline-from-strategy-llm failed = **LLM 时段波动**（log "Invalid JSON: EOF...input_value=''" = DeepSeek 空 content → fallback 救回；单独复跑 passed 24.9s / 94.9s）
- unconfigured：7 环境缺失 + 1 统计口径差异（汇总 8，清单 7）

### 9 个 failed 定性（均非产品代码 bug）

| 场景 | 定性 | 修复 |
|------|------|------|
| distribute/effects/history/mcp/rollback-cli-surface、validate-list-meta、effects-cli-contract（7 个 CLI 场景）| **执行环境：PATH 缺 .venv/bin**——场景 command 是 `automedia ...`（无路径），subprocess 找不到命令 → OSError | runner 必须 `export PATH=$PWD/.venv/bin:$PATH`（修复后全 passed）|
| agent-user-lifecycle-journey | **环境准备：`/tmp/automedia/agent-lifecycle-cwd/` 目录缺失**——`rm -f` 只删文件不建目录，add_pool_topic 打开 db 失败 "unable to open database file" | 跑前 `mkdir -p /tmp/automedia/agent-lifecycle-cwd`（修复后全 passed）|
| text-only-journey（第 3 步）| **fake-LLM 局限**——draft 86b < 500c 断言（fake LLM 给 stub）| 需真 LLM 模式（AUTOMEDIA_LLM_API_KEY + 非 fake）才能全绿 |

### 7 个 unconfigured（环境缺失，如实上报）

- AUTOMEDIA_VALIDATION_EXPECT_MISSING_FFMPEG（dep-doctor-missing-ffmpeg 特殊开关）
- AUTOMEDIA_VALIDATION_EXPECT_ORF（format-output-contract 特殊开关）
- AUTOMEDIA_MASTER_KEY × 4（account masterkey 场景，安全敏感）
- AUTOMEDIA_WECHAT_APPID/SECRET + ZHIHU（publish-draft-only-real-adapters 真实平台）

### 坑清单（迭代前必查！）

1. **CLI 场景需要 automedia 在 PATH**：场景 command 是 `automedia ...` 无路径前缀——跑 validation 前 `export PATH=$PWD/.venv/bin:$PATH`，否则全部 cli 场景 OSError failed
2. **场景硬编码 /tmp 路径需要预先 mkdir**：`/tmp/automedia/agent-lifecycle-cwd/`（lifecycle pool db 父目录）——rm -f 不建目录
3. **AUTOMEDIA_PROJECTS_DIR 必须与场景硬编码路径一致**：text-only-journey 的 run 与验证步骤查 `/tmp/automedia/journey-projects`——runner env 设别的路径会导致 run 写 A、验证查 B 失败
4. **fake-LLM 局限**：fake 模式 draft 产物 ~86b，无法满足 `-size +500c` 类 non-trivial 断言——需真 LLM 的场景在 fake 模式预期 failed（定性记录，非产品 bug）
5. **step detail 为空是引擎特性**：CLI/tool 步骤失败时 `detail` 字段可能空——定性需直接调用底层工具/命令看真实错误（如 add_pool_topic 直调）
6. **`.env` 里 OPENCODE_GO_API_KEY 出现两次**（90/443 行）——`grep | cut` 会拼两行（key 含换行符）→ 连接错误/403；取最后一行定义（`tail -1`）
7. **OpenCode Go 不支持 beta structured parse**（response_format 400 "This response_format type is unavailable now"）——AutoMedia 的 fallback 自动降级 json_object（json_object 直测 OK，无需改代码）；但 DeepSeek reasoning 空 content（#178 类）→ parse 失败 → 依赖 fallback/重试救回（strategy-llm 场景单独复跑可过）
