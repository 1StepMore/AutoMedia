# Harness 运行事实速查（AutoMedia）

> 仓事实真身。通用执行规则（边界 / 权限 / 合并判定）由 Owner 侧维护，不入库。

**解释器**：Windows 原生 .venv_win\Scripts\python.exe（Python 3.12）；WSL 侧 .venv/bin/python。两者都在 .gitignore 里，不要删对方的目录。

**安装**：`make install-dev`（或 pip install -e ".[dev]"）。

**必需环境变量**：AUTOMEDIA_LLM_API_KEY。.env 只认 ~/.automedia/.env 或 $AUTOMEDIA_DOTENV_PATH；仓库根 .env 不读。

**缺 key 症状**：`automedia doctor` 的 llm_api 项红（该探针真发一次请求，不是静态检查）。

**DoD 顺序**：`make lint` → `make typecheck` → `make test` →（依赖或环境变更时）`make doctor`。

**陷阱**：Makefile 全部 target 已走 `$(PYTHON)` 并带解释器 guard（#536 已修，PR #538 合入 main）：解释器无法 import automedia 时 guard 以 exit 2 拦截并给出指引，可用 `make doctor PYTHON=.venv_win/Scripts/python.exe`（Windows）或 `PYTHON=.venv/bin/python`（WSL/Linux）显式覆盖；`.scratch/` 与 `.venv_win/` 已在 .gitignore；无 key 时 live e2e 跑不了，报告里必须写"未跑"，不能写"通过"。

**队列**：`gh issue list -l agent-ready --state open`。

**依赖探针与能力需求**（需求侧 · 跨机器成立；本机结果不入库）

- 探针入口：`make doctor`（等价 `.venv_win/Scripts/python.exe -m automedia doctor` / `.venv/bin/python -m automedia doctor`）。它会真发一次 LLM 请求，不是静态检查。
- 本仓需要哪些能力（由代码决定，与机器无关）：
  - 文本产出/校验 ← 仓库 venv + LLM 凭据（缺 ⇒ 该线记 blocked-no-llm-key，不算 bug）
  - 语音产出 ← 任一可用 TTS 通道（云端 key 或本地 TTS 引擎）；语音校验 ← 音视频探测类工具（时长/码率/可解码）
  - 视频产出 ← 语音产出 + 渲染器链路（hyperframes / remotion + node 运行时）；视频校验 ← 探测类工具 + 浏览器
  - 浏览器链路 ← chrome / chromium / playwright（缺 ⇒ 依赖浏览器的场景记 blocked，不算 bug）
- 判定结果怎么写：本机"有/没有"属**机器事实**，逐机器不同且会过期 ⇒ 写到仓外或已被 gitignore 的 `.scratch/`，
  每轮报告「环境」段带出；**禁止把 ✓/✗ 结果提交进本文件**。本文件只回答"这个仓需要什么"，不回答"这台机器有什么"。

**交接状态机（双机协作）**：issue 状态只由标签表达，两侧共用一套；改标签 = 交棒。

| 标签 | 含义 | 谁迁出 |
|:--|:--|:--|
| `agent-ready` | 契约完整，可开工 | 接活方 ⇒ 换 `status:claimed` |
| `status:claimed` | 已认领、在做 | 在做方 ⇒ 做完换 `needs-real-verification`；缺能力换 `blocked:env` |
| `blocked:env` | 缺能力/依赖，等另一台机器 | 具备该能力的一方；**判阻塞方不得自关** |
| `needs-real-verification` | 产物已出，等内容级读数 | 复验方给读数后关门 |

硬规矩：① 改标签必须同时留一行「可复跑命令 / 期望读数 / sha」；② 每条 issue 要有 `needs:` 行
（能力项名见上一节「依赖探针与能力需求」），**派活按能力匹配，不按人**；③ 只有三种情况需要 Owner 出场：
两侧都不具备该能力 / 判据与治理类改动 / 合并与发版；④ 产物验收只认内容级读数，状态枚举不算通过。
