# AutoMedia 开发者指南

## 从零搭建

### 前置依赖

AutoMedia 运行时依赖以下外部工具。在安装包之前确保它们已在 `$PATH` 中:

- Python 3.11+
- FFmpeg
- Bun (用于 HyperFrames 渲染)
- edge-tts CLI
- Whisper (OpenAI whisper)
- Chrome/Chromium (无头模式)
- ComfyUI (图片生成)

### 安装

```bash
# 克隆仓库
git clone <repo-url> && cd AutoMedia

# 可编辑模式安装
pip install -e .

# 安装可选依赖
pip install -e ".[mcp]"     # MCP server 支持
pip install -e ".[openai]"  # OpenAI provider
pip install -e ".[anthropic]" # Anthropic provider
pip install -e ".[rich]"    # 富文本 CLI 输出
```

### 初始化

```bash
# 交互式初始化 —— 配置 LLM provider 和 API key
automedia init

# 最小配置 (非交互)
automedia init --template minimal

# 文件结构如下:
# .automedia/
#   config.yaml            # LLM provider, base_url, api_key
```

### 健康检查

```bash
automedia doctor
```

输出示例:

```
Dependency Check:
------------------------------------------------------------
Tool             Installed    Version
------------------------------------------------------------
✓ python         yes          3.11.4
✓ bun            yes          1.1.30
✓ ffmpeg         yes          ffmpeg version 7.0.2
✓ whisper        yes          whisper 20240930
✓ edge-tts       yes          edge-tts 6.1.3
✗ comfyui        no           -
✓ chrome         yes          Google Chrome 126.0.6478.126
------------------------------------------------------------
```

缺失的依赖标记红色, 系统不会阻止运行但对应 Gate 会在执行时报错。

### 运行流水线

```bash
automedia run --topic "AI 视频生成工具对比" --brand my-brand
```

## 架构概览

AutoMedia 采用三层架构:

```
外部调用层
  Any MCP Client / Python SDK / CLI 终端
        |              |              |
        v              v              v
  ┌──────────────────────────────────────┐
  │         MCP Server Layer             │  mcp official Python SDK
  │   select_topic, run_pipeline, ...    │  8 个 tool
  └────────────────┬─────────────────────┘
                   │
  ┌────────────────┴─────────────────────┐
  │         CLI Layer (typer)            │  automedia run / pool / ...
  └────────────────┬─────────────────────┘
                   │
  ┌────────────────┴─────────────────────┐
  │     automedia/ 核心 Python 包         │
  │                                      │
  │  core/      pipelines/    gates/     │
  │  adapters/  manifests/   hooks/      │
  │  pool/      cron/        mcp/        │
  └──────────────────────────────────────┘
```

### 核心子包

| 子包 | 职责 |
|------|------|
| `core/` | 配置加载 (`config_loader.py`)、项目管理 (`project.py`)、凭证管理 (`credential_loader.py`)、健康检查 (`doctor.py`) |
| `pipelines/` | Pipeline 编排 (`runner.py`)、Gate 引擎 (`gate_engine.py`)、音视频管线 |
| `gates/` | 14+ 道 Gate 实现 + 失败模式知识库 (`failure_modes.py`) |
| `adapters/` | 平台发布 adapter 注册表 (`registry.py`) + 基类 (`base.py`) |
| `hooks/` | GateHook Protocol (`protocol.py`)、MD5 追踪 (`md5_tracker.py`) |
| `manifests/` | 内置 YAML 默认配置 (`defaults.yaml`)、schema 定义 |
| `pool/` | 话题池 SQLite 数据库 (`db.py`)、采集/评分/去重 |
| `cron/` | 定时任务 YAML 定义 (`jobs.yaml`) |
| `mcp/` | MCP Server 实现 (`server.py`), stdio 传输 |

### 三层入口共用实现

三层共享同一个 `run_full_pipeline()` 实现, 不重复代码:

```
CLI (typer)  -- parse argv --> call run_full_pipeline() -- print result
MCP Server   -- JSON-RPC  --> call run_full_pipeline() -- return JSON
SDK          -- import    --> call run_full_pipeline() -- return Python object
```

## 开发工作流

### 项目结构

```
automedia/                  # 核心 Python 包
  core/                     # 基础设施
  pipelines/                # Pipeline 编排
  gates/                    # 门控实现
  adapters/                 # 平台适配器
  hooks/                    # GateHook
  manifests/                # 配置文件 schema
  pool/                     # 话题池
  cron/                     # 定时任务
  mcp/                      # MCP Server
  cli/                      # Typer CLI
tests/                      # 测试目录
  test_cli/
  test_mcp/
  test_e2e/
docs/                       # 文档
```

### 运行测试

```bash
# 运行全部测试
pytest

# 带覆盖率
pytest --cov=automedia

# 特定测试文件
pytest tests/test_runner.py

# E2E 红线测试
pytest tests/test_e2e/ -v
```

### 添加新 Gate

1. 在 `automedia/gates/` 下创建新文件, 继承 `BaseGate`
2. 定义 `_gate_name` 和 `_failure_mode` 类属性
3. 实现 `execute(self, gate_context) -> dict` 方法
4. 在 `failure_modes.py` 中添加失败模式条目
5. 在 `tests/` 中添加对应测试

```python
from automedia.gates.base import BaseGate

class MyNewGate(BaseGate):
    _gate_name = "GX"
    _failure_mode = "stop"

    def execute(self, gate_context):
        # 你的逻辑
        return {"passed": True, "gate": self._gate_name}
```

### 添加新 CLI 命令

1. 在 `automedia/cli/commands/` 下创建文件
2. 使用 typer 定义命令
3. 在 `automedia/cli/app.py` 中注册

### Gate 命名规范

| 前缀 | 范围 | 示例 |
|------|------|------|
| G0-G5 | 文案 Gate | 事实核查、去AI味、文案审查、品牌CTA |
| V0-V7 | 视频 Gate | Lint、Vision QA、Whisper、字幕渲染 |
| L1-L3 | 生命周期 Gate | 发布日志、归档验证、平台完整性 |

## 配置层级

配置从低到高六层叠加, 高优先级覆盖低优先级:

1. 内置 `automedia/manifests/defaults.yaml`
2. 项目 `.automedia/` 目录
3. 用户 `~/.automedia/` 目录
4. `~/.automedia/overrides/rules/*.yaml`
5. `~/.automedia/overrides/prompts/*.j2`
6. 环境变量 `AUTOMEDIA_*` + 显式 overrides 参数

## 关键技术决策

- **Gate 阻断**: `failure_mode="stop"` 的 Gate 失败则 Pipeline 立即停止
- **GateHook 只读**: Hook 是观察者, 不能修改 Gate 行为
- **MD5 追踪**: 每个 Gate 产物写入 `pipeline_md5.json`, 红线 7
- **归档红线**: 仅用户 `--force` 可归档, agent 不得归档 (红线 8)
- **调度外部化**: 外部 crond 调用 `automedia cron run`, 无内置调度器
