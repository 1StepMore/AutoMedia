# Harness 运行事实速查（AutoMedia）

> 仓事实真身。通用执行规则（边界 / 权限 / 合并判定）由 Owner 侧维护，不入库。

**解释器**：Windows 原生 .venv_win\Scripts\python.exe（Python 3.12）；WSL 侧 .venv/bin/python。两者都在 .gitignore 里，不要删对方的目录。

**安装**：`make install-dev`（或 pip install -e ".[dev]"）。

**必需环境变量**：AUTOMEDIA_LLM_API_KEY。.env 只认 ~/.automedia/.env 或 $AUTOMEDIA_DOTENV_PATH；仓库根 .env 不读。

**缺 key 症状**：`automedia doctor` 的 llm_api 项红（该探针真发一次请求，不是静态检查）。

**DoD 顺序**：`make lint` → `make typecheck` → `make test` →（依赖或环境变更时）`make doctor`。

**陷阱**：Makefile 的 target 用裸 python（#536 在跟）⇒ 先确认 python -c "import automedia" 能过，否则 make doctor 会报假的 No module named automedia；.scratch/ 与 .venv_win/ 已在 .gitignore；无 key 时 live e2e 跑不了，报告里必须写"未跑"，不能写"通过"。

**队列**：`gh issue list -l agent-ready --state open`。
