# Hermes 耦合点清单 & 解耦验证

> **审计目标**: 确认 `automedia/` 新包已从 Hermes Agent v0.17 完全解耦
> **审计日期**: 2026-07-07
> **状态说明**:
> - `resolved` — 耦合点已消除, 新包代码中无对应依赖
> - `isolated` — 耦合点存在但属于部署/调度层面的外部接口, 不影响库代码独立性

---

## 耦合点清单

| # | 耦合点 | 状态 | 新包方案 | Hermes 原引用文件 |
|---|--------|------|---------|-------------------|
| 1 | `skill_view(name='...')` 语法 — 通过 Hermes Agent 的 SkillView API 注册视图函数 | `resolved` | 新包无 `skill_view` 调用。CLI 基于 `typer`, MCP 基于 `mcp` official SDK, 无任何 Hermes Agent 注册逻辑 | `00_核心脚本/*.py` 中的 `@skill_view(...)` 装饰器 |
| 2 | `~/.hermes/skills/productivity/automedia/scripts/` 路径硬编码 — 脚本定位依赖固定 Hermes 安装路径 | `resolved` | 脚本位于 `automedia/` 包内, 通过 `__file__` / `importlib.resources` 定位, 无硬编码绝对路径 | `scripts/` 目录下的所有 shell/Python 入口文件 |
| 3 | `~/.hermes/skills/productivity/automedia/hooks/` 路径硬编码 — gate hook 注册依赖固定 Hermes 安装路径 | `resolved` | Hook 移至 `automedia/hooks/`, 纯 Python `Protocol` 实现, 通过 `GateHook` 接口注册, 无文件系统路径依赖 | `hooks/` 目录下的 hook 脚本 |
| 4 | `/home/renanzai/.hermes/` 绝对路径 — 多处硬编码的用户 Hermes 家目录 | `resolved` | 无任何 `.hermes` 引用。配置路径统一为 `~/.automedia/`(仅加载使用, 不硬编码到代码逻辑), 详见 `config_loader.py` + `credential_loader.py` | `01_核心脚本/*.py` 中的字符串 `/home/renanzai/.hermes/skills/...` |
| 5 | `/mnt/d/Hermes-Workspace/01-Projects/AutoMedia/` 项目路径硬编码 | `resolved` | `Project.init()` (`automedia/core/project.py`) 支持 `base_dir` 参数, 默认为 `os.getcwd()`, 完全配置化 | AutoMedia 旧版 `project_init.py` 中的 `PROJECT_BASE` 常量 |
| 6 | `execute_code` sandbox 依赖 — Hermes Agent 内置的代码沙箱执行环境 | `resolved` | 纯 Python 执行, 无 sandbox。LLM 调用通过可配置 `provider` (`~/.automedia/model_config.yaml`), 所有 Gate 为本地 Python 类 | 旧版 gate 中的 `self.skill.execute_code(...)` 调用 |
| 7 | Hermes cron 调度 — Hermes Agent 内置的 cron job 管理 (jobs.json 格式 + Agent 级调度) | `isolated` | 新包通过 CLI (`automedia cron run <job-name>`) 暴露 cron job, 由外部 crond / systemd timer / K8s CronJob 调度。PRD-1 §6 明确为部署层面职责 | Hermes Agent `cron/` 模块 + `jobs.json` |
| 8 | OpenCode Go API 默认绑定 — LLM 调用强制走 `opencode-go` API, 模型选择受限于其支持的模型列表 | `resolved` | `model_config.yaml` 配置化, 支持 OpenAI / Anthropic 兼容格式。用户可自由切换 provider 和 endpoint。详见 `defaults.yaml` + `credential_loader.resolve_api_key()` | 旧版 `llm_client.py` 中的 `opencode_go` 硬编码 URL |
| 9 | MiniMax API 依赖 — 文本生成、生图、TTS、字幕校对等环节直接调用 MiniMax API | `resolved` | MiniMax 死代码已清理。LLM 调用抽象为可切换 provider, 默认 `provider: ""` 空字符串(用户按需配置)。R4 风险已关闭 | 旧版 `minimax_*.py` 及 `api_client.py` |
| 10 | `skill` 加载路径硬编码 — Hermes Agent 通过固定路径加载技能包 | `resolved` | 新包无 "skill" 概念。功能拆分为 `pipelines/`(编排)、`gates/`(门控)、`adapters/`(平台适配), 均通过 Python import 加载 | Hermes Agent `skill_loader.py` + 旧版 `skills/` 目录 |
| 11 | `sys.path.insert(0, '/home/renanzai/.hermes/skills/...')` hack — 运行时动态修改 Python 模块搜索路径 | `resolved` | 零 `sys.path` 修改。所有内部引用通过 `automedia.` 包内导入, 外部依赖通过 `pyproject.toml` 声明 | 旧版 `__init__.py` / `bootstrap.py` 中的 `sys.path.insert` |
| 12 | Hermes `.env` 依赖 — 凭证通过 Hermes Agent 的 `.env` 文件加载 | `resolved` | 四层凭证加载 (`credential_loader.py`): env var (`AUTOMEDIA_*`) → keyring → `oscreds.yaml` → `credentials.yaml`。无 Hermes `.env` 依赖 | Hermes Agent `dotenv` 加载逻辑 + 旧版 `.env` |
| 13 | Hermes `jobs.json` cron 格式 — 调度任务使用 Hermes 专有的 JSON schema | `isolated` | 外部 cron 直接调用 `automedia cron run <job-name>` CLI。`~/.automedia/cron/jobs.yaml` 使用纯 YAML, 不兼容 `jobs.json`。PRD-1 §6 外部化 | Hermes Agent `jobs.json` 文件 |
| 14 | 飞书/微信公众号 API 硬编码品牌 — adapter 中直接嵌入品牌特定的 API endpoint、AppID、Secret | `resolved` | `wechat_publisher.py` + `feishu_notifier.py` 为通用 stub, 通过 `FEISHU_WEBHOOK_URL` / `WX_APPID` / `WX_APPSECRET` 环境变量配置。注册通过 `AdapterRegistry` 可插拔 | 旧版 `pre_wechat_upload.py` 中的 `WX_APPID = "wx_xxx"` 硬编码 |
| 15 | Hermes Agent `artifacts/` 目录约定 — 产物输出固定到 Hermes 管理的 `artifacts/` 路径 | `resolved` | `Project.init()` 创建标准目录结构 (`01_content/`, `02_images/`, `03_video/` 等), 全部位于 `base_dir` 下, 无 Hermes artifact 约束 | 旧版 `pipeline_orchestrator.py` 中的 `ARTIFACTS_DIR = ...` |
| 16 | Hermes Agent `pipeline_md5.json` 路径硬编码 | `resolved` | MD5 追踪保留(红线 7), 但路径由 `Project.project_dir` 动态确定, 无硬编码。`md5_tracker.py` 通过参数接收路径 | 旧版 `pre_send_whisper_check.py` 中的 `PIPELINE_MD5_PATH` 常量 |
| 17 | Hermes Agent Gate 注册 API (`register_gate`) — Gate 必须通过 Agent API 注册 | `resolved` | Gate 为普通 Python 类, 继承 `BaseGate` (`automedia/gates/base.py`), 通过 `pipeline_orchestrator.py` 的 YAML 配置编排。无 Agent API 依赖 | 旧版 `gate_registry.py` 中的 `register_gate()` |
| 18 | Hermes Agent 运行时自省 — 代码中调用 `hermes.get_current_skill()`, `hermes.get_config()` 等运行时 API | `resolved` | 无任何 `hermes.*` 调用。配置通过 `load_config()` 函数加载, 不依赖 Agent 运行时上下文 | 旧版 gate 中的 `hermes.get_current_skill().config` 等调用 |
| 19 | Hermes Agent 日志格式 — 使用 Hermes 专有的日志 schema | `resolved` | Python 标准 `logging` 模块。无 Hermes 日志格式依赖 | 旧版 `log_config.py` 中的 Hermes JSON 日志格式 |
| 20 | Hermes `model_config.yaml` 位置固定 — 必须位于 `~/.hermes/config/model_config.yaml` | `resolved` | `model_config.yaml` 从 `~/.automedia/` 加载, 路径由 `credential_loader` 统一管理 | Hermes Agent 配置目录约定 |

---

## 解耦验证摘要

### 代码层面 (resolved: 17/20)

- **Hermes 关键字**: `grep -r "hermes\|\.hermes\|skill_view\|execute_code" automedia/` → **0 匹配** ✅
- **硬编码绝对路径**: 无 `/home/renanzai/`, `/mnt/d/Hermes-Workspace/`, `~/.hermes/` 路径 ✅
- **sys.path hack**: 无 `sys.path.insert` 调用 ✅
- **Hermes SDK 依赖**: `pyproject.toml` 无 `hermes-agent` 或 `hermes-sdk` ✅
- **MiniMax 死代码**: `grep -ri "minimax" automedia/` → **0 匹配** ✅

### 部署层面 (isolated: 3/20)

以下 3 项为外部接口, 属于部署职责而非库代码问题:

| # | 耦合点 | 外部化方案 | 负责方 |
|---|--------|-----------|--------|
| 7 | Hermes cron 调度 | `automedia cron run` CLI + 系统 crond / systemd timer | 运维/部署 |
| 13 | jobs.json cron 格式 | `~/.automedia/cron/jobs.yaml` + 外部 cron 调用 | 运维/部署 |
| — | 以上两项合计 | 见 PRD-1 §6 外部调度架构 | — |

---

## 遗留风险

| 风险 | 描述 | 缓解 |
|------|------|------|
| R4 (PRD-1) | MiniMax 历史代码未清理干净 | 已通过全仓库搜检消除, `automedia/` 中零匹配 |
| 配置迁移 | 旧 Hermes `model_config.yaml` 用户需手动复制到 `~/.automedia/` | 文档需标注迁移步骤, M4 里程碑处理 |

---

*清单版本: v1.0 · 对应 PRD-1 M1 退出标准*
