# Changelog

## v1.0.0 (2026-07-07)

### 新增

#### 核心库 (Core)

- **三层入口**: Python SDK (`from automedia import run_full_pipeline`), CLI (`automedia`), MCP Server (`python -m automedia.mcp.server`) 三种方式调用流水线
- **配置体系**: 六层优先级配置加载 (`config_loader.py`), 支持内置默认、项目级、用户级、overrides、环境变量
- **项目管理**: `Project.init()` 创建标准目录结构, 自动 slugify 和安全路径校验
- **凭证管理**: 四层凭证加载 (`credential_loader.py`): 环境变量 > keyring > oscreds.yaml > credentials.yaml
- **健康检查**: `Doctor` 类检查 python/bun/ffmpeg/whisper/edge-tts/comfyui/chrome 依赖

#### Pipeline 编排

- **GateEngine**: 顺序执行 Gate 引擎, 支持 "stop" 和 "rewrite" 两种失败模式
- **`run_full_pipeline()`**: 完整流水线执行函数, 支持 mode/resume_from/config_dir/tenant_id 参数
- **三种运行模式**: auto (全链路), text_only (仅文案), video_only (仅视频), qa_only (仅 QA)

#### Gate 系统

- **BaseGate** 抽象基类, 自动注册到 `GateRegistry`
- **文案 Gate (G0-G5)**: 事实核查、Humanizer 去AI味、文案审查、品牌CTA、微信检查、HTML 硬门控
- **视频 Gate (V0-V7)**: Lint、Vision QA、Pre-Send Whisper、内容语义、TTS 品牌资产、MP3 vs SRT、字幕渲染、六步硬门控
- **生命周期 Gate (L1-L3)**: 发布日志 Schema、归档验证、平台完整性
- **失败模式知识库**: `failure_modes.py` 记录每个 Gate 的常见失败原因和修复步骤

#### Hook 系统

- **GateHook Protocol**: 只读观察者模式, `before_gate`, `after_gate`, `on_gate_failed` 三个方法
- **MD5 追踪**: `md5_tracker.py` 记录和验证每个 Gate 产物的 MD5 哈希 (红线 7)

#### CLI

- `automedia run`: 执行流水线, 支持 --mode, --resume-from, --timeout
- `automedia pool`: 话题池管理 (list/add/prune)
- `automedia projects`: 项目列表和详情 (list/get)
- `automedia archive`: 项目归档 (红线 8 强制约束)
- `automedia adapter`: 平台适配器管理 (list/create)
- `automedia cron`: 定时任务执行和健康检查 (run/check-health)
- `automedia init`: 交互式/最小配置初始化
- `automedia doctor`: 依赖和运行环境健康检查

#### MCP Server

- 8 个 MCP tool: select_topic, run_pipeline, get_pipeline_status, list_projects, get_project_assets, archive_project, list_topic_pool, register_platform_adapter
- 路径 allowlist 安全机制
- stdio 传输, 兼容 Claude Desktop / OpenCode / Cline

#### Adapter 系统

- **BasePlatformAdapter**: 抽象基类定义 publish/validate/platform_name
- **AdapterRegistry**: 全局单例注册表, 支持 register/get/list/clear
- **模板生成**: `automedia adapter create` 生成适配器模板代码

#### 话题池

- **PoolDB**: SQLite 话题池 CRUD, 支持 schema 创建和迁移
- **评分和去重**: 基础评分器和去重逻辑

#### 文档

- **开发者指南** (`docs/developer-guide.md`)
- **API 参考** (`docs/api-reference.md`)
- **CLI 参考** (`docs/cli-reference.md`)
- **MCP 设置指南** (`docs/mcp-setup.md`)
- **Runbook**: Gate 失败模式 / Cron 调试 / API 陷阱 / 生产流程

### 变更

- Hermes Agent v0.17 耦合完全拆解, 20 个耦合点全部解决 (17 resolved, 3 isolated)
- `skill_view(name='...')` → 纯 Python 类 + typer CLI
- `execute_code` sandbox → 纯 Python 执行
- Hermes cron → 外部 crond + `automedia cron run`
- `~/.hermes/` → `~/.automedia/` 配置目录
- OpenCode Go 绑定 → 可切换 provider (OpenAI/Anthropic)
- 品牌硬编码 → brand-profile.yaml 配置化
- MiniMax API 依赖 → 完全移除

### 移除

- Hermes Agent 运行时依赖
- `sys.path.insert` hack
- 所有 `/home/renanzai/` 和 `/mnt/d/Hermes-Workspace/` 硬编码路径
- `hermes.*` 运行时 API 调用
- Hermes 专有日志格式和 cron jobs.json

### 技术栈

- Python 3.11+
- Typer (CLI)
- Pydantic 2.x (数据模型)
- PyYAML (配置)
- mcp official Python SDK (MCP Server)
- SQLite3 (话题池)

### 安全

- 路径安全: `sanitize_path()` 拒绝路径遍历 (`..`, `~`, `//`)
- 归档红线: agent 不得归档, 仅用户 `--force` 可绕过
- MCP 路径 allowlist
- 凭证不写入配置文件, 通过环境变量或密钥环加载
- tenant_id 字段预留 (多租户基础)
