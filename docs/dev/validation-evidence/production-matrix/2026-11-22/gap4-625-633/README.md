# auto-journey 4/4 on win32 — #625 + step3 可移植性（2026-11-22 收口 2）

Bench: main@02eb6c97（含 #631 / #633）。
Owner: human-agent（harness lane）。

## 真跑命令（真模型，无 fake）

```
AUTOMEDIA_LLM_PROVIDER=spark \
AUTOMEDIA_LLM_BASE_URL=https://maas-api.cn-huabei-1.xf-yun.com/v2 \
AUTOMEDIA_LLM_MODEL=spark-x2.6 \
AUTOMEDIA_LLM_TIMEOUT=240 \
python3 -m automedia validate run --scenario auto-journey
```

`Status: passed (4/4 steps passed)` / **exit 0** / 24m39s。
Run record 原文：`scenarios-auto-journey-4of4.json`（`confidence=real` / `trusted=true` / `blocked=false`）。

| step | 名称 | 结果 | 耗时 | 读数 |
|:--|:--|:--|:--|:--|
| 1 | auto pipeline completes | passed | 1206.5s | 16 门跑完，`Assets produced: 1` → `01_content/drafts/20261122_074813_draft.md` |
| 2 | project visible through the shipped surface | passed | 2.8s | `522db6242d98 my-brand Automated content pipelines for solo founders` |
| 3 | non-trivial draft artifact exists | passed | 0.1s | stdout 输出 `..._draft.md`（修复前是 `exit 2` + `找不到文件 - *_draft.md`） |
| 4 | real-LLM quality spot-check answers | passed | 260.8s | 走结构化升级路径：`length@2048 attempt1 → escalated 4096 → stop@4096 attempt2` |

## 两处修复（各自独立 PR）

### #631 — issue #625：结构化输出被 reasoning tokens 吃爆预算
- 根因：`src/automedia/mcp/tools/quality.py:78-81` 的 `llm_complete_structured_safe(...)` 走 `llm.text_generation`（`max_tokens=2048`）；结构化路径在 beta `parse` 抛 `LengthFinishReasonError` 时只降级到 json_object（**同一预算**），截断 JSON 解析失败 → 同预算 repair → `0 provider(s) remaining`。#624 只覆盖普通文本。
- 修法：截断判据（`LengthFinishReasonError` / `finish_reason=length` / `completion_tokens>=budget`）⇒ 2× 预算（≤16000）**只重试一次**；截断时跳过同预算 repair；截断不再污染 beta 缓存；每次 attempt 写 provenance（`get_last_structured_provenance()`）并挂到最终 chain error；重试那次同步放宽墙钟（2× timeout，≤600s）。
- 红线：`manifests/defaults.yaml` 未改、质量门阈值未改、无厂商/model 硬编码、无第二配置入口；空串/返回类型契约不变。
- 真跑证据（本条）：step4 由红转绿，provenance `finish_reason=length attempt=1 truncated=True max_tokens=2048` → `finish_reason=stop attempt=2 max_tokens=4096`。
- QA：accept / NoOne / confidence=real；单测 6 例（含「二次截断必须停止」）；变异检验 M1–M4 均被用例杀死；CI 16/16。
- **已知残余（仅记录）**：G4 chain 末尾 provenance 可能贴上一次性 thread-local 旧值（无功能影响）；G5 beta 截断后 json_object 两次都抛异常时不升级（窄口）。

### #633 — auto-journey step3 的 Windows `find.exe`
- 根因：`src/automedia/validation/adapters.py` 的 `CLIAdapter.run` 把裸 token 交给 `subprocess.run(shell=False)`；Windows `CreateProcess` 搜索顺序 **system32 先于 PATH** ⇒ `find` 命中 `C:\Windows\system32\find.exe`（文本工具）→ `exit 2` + `找不到文件 - *_draft.md`。**改 PATH 无效。**
- 修法：`_POSIX_UTIL_NAMES` + `_resolve_posix_util()`（仅 win32 / 仅白名单 / 含路径分隔符不动 / 剔除 `%SystemRoot%`·`%windir%` 候选 / 无候选诚实回退），只替换 `parts[0]`，其余参数逐字节不变。
- 红线：**`scenarios/` 零改动**，判据强度不变（仍是 `-name "*_draft.md" -size +500c`）。
- 验收：`auto-journey` 4/4 exit 0；验收树 tree `1750bb7dff47ef4423c0ddd4538321f64e1141f6` 与合并树完全一致。
- QA：accept / NoOne / confidence=real；单测 10 例无 skip；**反向验证**（解析器改回恒等函数 ⇒ 同一命令立刻 `exit 2` 复现修复前症状）证明修复确为根因；CI 18/18。

## 归因更正（推翻上一轮的「端点不稳」）

上一轮证据里把 auto-journey step1 写成 `openai: Connection error`（端点不稳）。本轮复核确认**该归因错误**：

1. 失败日志里全是 `HTTP/1.1 200 OK`，无连接错误；
2. 真正的 step1 失败原因是 `src/automedia/validation/sandbox.py:91-99` 的 `_MODEL_CONFIG_SEED` 硬编码 `provider: openai / model: gpt-4o-mini`，只导出 `AUTOMEDIA_LLM_API_KEY` 时会拼出「openai 端点 + spark key」→ 假性 Connection error（已开 **issue #632**，本轮不修）；
3. 对照探针：同端点同模型 `max_tokens=2048` 与 `8192` 均返回 200 + 合法 JSON（38.5s / 48.5s），**Spark 2.6 本身可用**。

## 矩阵读数（main@02eb6c97）

- `python3 scripts/nightly_gap.py` ⇒ **exit 0**，三轨全达标，`units 3/3`、`gap=[]`、真模型 cost_log 非空项目 11 个。
- 场景 165：**151 passed** / 4 failed / 6 unconfigured / 3 partial-pass / 1 recovered（auto-journey 本轮由 failed → passed）。
- 剩余 4 个 failed 全为 `blocked:missing-dep`（comfyui / orf / bun / video-engine），另有 produce-audio 的 /tmp 钉死项；6 个 unconfigured 含 21 平台凭据等 owner-only 项。
