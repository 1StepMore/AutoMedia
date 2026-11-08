# src/automedia — 产品源码 scope

此地何为真：AutoMedia 产品核心包（Python 3.11+，`pip install -e ".[dev]"`）。

- 包结构、入口与逐模块职责：`docs/dev/agent-reference.md` §Directory Layout。
- 门禁编号与顺序唯一权威：`pipelines/gate_plan.py`；新增门先读根 AGENTS.md §5 红线 6/7。
- 本目录受 CI 全量门禁（ruff / mypy（7 个强化模块 strict）/ pytest / 覆盖率阈值）。
- 角色契约与路由见根 AGENTS.md §0；本文件只描述地点，不定义角色。
