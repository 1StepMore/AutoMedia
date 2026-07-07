# MCP Server Setup

AutoMedia 提供 MCP (Model Context Protocol) server, 允许任何 MCP client (Claude Desktop, OpenCode, Cline) 通过标准工具调用接口使用 AutoMedia 流水线。

## 安装

```bash
pip install automedia[mcp]
```

## 启动

MCP server 使用 stdio 传输, 通过标准输入输出与 MCP client 通信:

```bash
python -m automedia.mcp.server
```

查看已注册工具:

```bash
python -m automedia.mcp.server --show-tools
```

输出如下:

```
Registered MCP tools:
  - archive_project
  - get_pipeline_status
  - get_project_assets
  - list_projects
  - list_topic_pool
  - register_omni_adapter
  - run_pipeline
  - select_topic
```

## 可用 Tool

| Tool | 说明 |
|------|------|
| `select_topic` | 从话题池选择最高分话题 |
| `run_pipeline` | 执行完整生产流水线 |
| `get_pipeline_status` | 查询项目进度 |
| `list_projects` | 列出所有项目 |
| `get_project_assets` | 获取项目资产清单 |
| `archive_project` | 归档项目 (红线 8 约束) |
| `list_topic_pool` | 查看话题池 |
| `register_omni_adapter` | 注册平台适配器 |

## MCP Client 配置

### Claude Desktop

编辑 `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "automedia": {
      "command": "python",
      "args": ["-m", "automedia.mcp.server"],
      "env": {
        "AUTOMEDIA_LLM_API_KEY": "sk-xxx"
      }
    }
  }
}
```

### OpenCode

编辑 `opencode.json` 或项目级配置文件:

```json
{
  "mcpServers": {
    "automedia": {
      "command": "python",
      "args": ["-m", "automedia.mcp.server"]
    }
  }
}
```

或通过 `~/.config/opencode/mcp.json`:

```json
{
  "servers": {
    "automedia": {
      "command": "python",
      "args": ["-m", "automedia.mcp.server"],
      "env": {}
    }
  }
}
```

### Cline

编辑 VSCode 扩展配置或 `~/.config/cline/mcp.json`:

```json
{
  "mcpServers": {
    "automedia": {
      "command": "python",
      "args": ["-m", "automedia.mcp.server"]
    }
  }
}
```

## 路径 Allowlist

MCP server 的文件访问受 allowlist 限制。配置文件位于:

```
~/.automedia/mcp_allowlist.yaml
```

示例:

```yaml
allowed_directories:
  - "/mnt/d/AutoMedia/projects/"
  - "/tmp/automedia/"
```

如果 allowlist 为空, 所有路径都允许访问 (宽松模式)。建议生产环境配置明确的 allowlist。

## 环境变量

MCP server 支持以下环境变量:

| 变量 | 说明 |
|------|------|
| `AUTOMEDIA_LLM_API_KEY` | LLM API 密钥 |
| `AUTOMEDIA_LLM_BASE_URL` | 自定义 API endpoint |
| `FEISHU_WEBHOOK_URL` | 飞书通知 webhook |
| `WX_APPID` | 微信公众号 AppID |
| `WX_APPSECRET` | 微信公众号 AppSecret |

## 安全提醒

- `archive_project` tool 遵循红线 8: 仅当项目状态为 `published` 或 `force=True` 时才能归档
- 路径 allowlist 防止恶意 agent 读取项目目录外的文件
- 建议为 MCP server 使用专用的 API key 和环境变量
- 所有文件操作默认只读 (路径检查但不修改)

## 示例: Python 中直接调用 MCP 工具

```python
from automedia.mcp import (
    select_topic,
    run_pipeline,
    list_projects,
    archive_project,
)

# 选题
topic = select_topic(category="tech")
if topic.get("selected"):
    print(f"Selected: {topic['selected']['title']}")

# 运行流水线
result = run_pipeline(topic=topic, brand="my-brand")
print(f"Status: {result['status']}")

# 列出项目
projects = list_projects(base_dir=".")
print(f"Found {projects['count']} projects")

# 归档 (需用户确认)
result = archive_project(project_id="abc123def456", force=True)
```
