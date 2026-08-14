# LOOP-LOG — AutoMedia validation 循环记录

> 机制（对齐 AutoInfo 2026-08-15 规范）：每次迭代循环的关键事件、根因、修复、验证结果必须记录在此；
> 每次迭代开始前必复查「坑清单」；新坑当天追加（现象 → 根因 → 预防）。

## 2026-08-15 首轮 validation（fake 确定性模式）

### 结果

首轮（未修正环境）：75 passed / 9 failed / 7 unconfigured（91 场景，125.7s）
修正环境后重跑（20260815-022026）：**83 passed / 1 failed / 7 unconfigured**（152.1s）
- failed 唯一 = text-only-journey（fake-LLM 局限，见坑 #4）
- unconfigured 7 = 环境缺失（见下表）

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
