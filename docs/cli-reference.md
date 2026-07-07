# CLI Reference

## 全局

```bash
automedia --help
automedia --version
```

## `automedia run`

执行完整内容生产流水线。

```bash
automedia run --topic "AI 视频生成工具对比" --brand my-brand

# 仅文案模式
automedia run --topic "..." --brand my-brand --mode text_only

# 从指定 Gate 恢复
automedia run --topic "..." --brand my-brand --resume-from G3

# 设置超时
automedia run --topic "..." --brand my-brand --timeout 600
```

### Flags

| Flag | 简写 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--topic` | `-t` | `str` | 必填 | 内容话题 |
| `--brand` | `-b` | `str` | 必填 | 品牌标识 |
| `--mode` | `-m` | `str` | `auto` | 模式: auto, text_only, video_only, qa_only |
| `--resume-from` | | `str \| None` | `None` | 从指定 Gate 恢复 |
| `--timeout` | | `int` | `300` | 超时秒数 |

## `automedia pool`

管理话题池。

```bash
# 列出话题 (可筛选状态)
automedia pool list
automedia pool list --status pending

# 添加话题
automedia pool add --topic "AI 趋势 2026" --url "https://..." --source weibo

# 清理过期话题
automedia pool prune --days 7
```

### Subcommands

| 子命令 | 说明 |
|--------|------|
| `list` | 列出话题, 支持 `--status` 筛选 |
| `add` | 添加新话题, 需要 `--topic` |
| `prune` | 清理 N 天前的过期话题, 默认 7 天 |

### pool list Flags

| Flag | 简写 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--status` | `-s` | `str \| None` | `None` | 按状态筛选 (pending, selected, published) |
| `--db` | | `str \| None` | `None` | pool SQLite 文件路径 |

### pool add Flags

| Flag | 简写 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--topic` | `-t` | `str` | 必填 | 话题标题 |
| `--url` | `-u` | `str` | `""` | 来源 URL |
| `--source` | `-s` | `str` | `""` | 来源平台 |
| `--db` | | `str \| None` | `None` | pool SQLite 文件路径 |

### pool prune Flags

| Flag | 简写 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--days` | `-d` | `int` | `7` | 删除 N 天前的 pending 话题 |
| `--db` | | `str \| None` | `None` | pool SQLite 文件路径 |

## `automedia projects`

查看和管理项目。

```bash
# 列出所有项目
automedia projects list

# 按状态筛选
automedia projects list --status published

# 查看特定项目详情
automedia projects get <project-id>
```

### Subcommands

| 子命令 | 说明 |
|--------|------|
| `list` | 列出项目 |
| `get` | 查看项目详情 (JSON) |

### projects list Flags

| Flag | 简写 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--status` | `-s` | `str \| None` | `None` | 按状态筛选 |
| `--base-dir` | `-d` | `str` | `.` | 扫描项目的根目录 |

### projects get Arguments

| 参数 | 类型 | 说明 |
|------|------|------|
| `project_id` | `str` | 项目 ID (必填) |

## `automedia archive`

归档项目 (红线 8 强制约束)。

```bash
# 正常归档 (状态须为 published)
automedia archive <project-id>

# 强制归档 (跳过 published 检查)
automedia archive <project-id> --force
```

### Arguments

| 参数 | 类型 | 说明 |
|------|------|------|
| `project_id` | `str` | 项目 ID (必填) |

### Flags

| Flag | 简写 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--force` | `-f` | `bool` | `False` | 强制归档, 跳过 published 状态检查 |
| `--base-dir` | `-d` | `str` | `.` | 项目根目录 |

## `automedia adapter`

管理平台适配器。

```bash
# 列出已注册适配器
automedia adapter list

# 创建新适配器模板
automedia adapter create --name youtube
```

### Subcommands

| 子命令 | 说明 |
|--------|------|
| `list` | 列出所有已注册的平台适配器 |
| `create` | 生成新的适配器模板文件 |

### adapter create Flags

| Flag | 简写 | 类型 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--name` | `-n` | `str` | 必填 | 平台名称 (如 youtube) |
| `--output-dir` | `-o` | `str` | `automedia/adapters/platforms` | 输出目录 |

## `automedia cron`

执行定时任务和健康检查。

```bash
# 运行指定 job
automedia cron run <job-name>

# 全系统健康检查
automedia cron check-health
```

### Known Jobs

| Job 名称 | 说明 |
|----------|------|
| `pool-collect` | 采集新话题到池中 |
| `pool-score` | 评分和排序话题 |
| `pool-prune` | 清理过期话题 |
| `publish-check` | 检查待发布内容 |

### cron run Arguments

| 参数 | 类型 | 说明 |
|------|------|------|
| `job_name` | `str` | Job 名称 (必填) |

### cron run Flags

| Flag | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--timeout` | `int` | `120` | Job 超时秒数 |

### cron check-health

执行 4 步健康检查:

1. Python >= 3.11
2. ffmpeg 可用
3. `.automedia/` 配置目录存在
4. `pool.db` 可访问

## `automedia init`

初始化 AutoMedia 配置。

```bash
# 交互式向导
automedia init

# 最小配置 (非交互)
automedia init --template minimal
```

### Flags

| Flag | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--template` | `str \| None` | `None` | 模板模式: `minimal` |

交互式向导提示以下内容:

- LLM provider (`openai` / `anthropic`)
- API base URL
- API key (隐藏输入)

## `automedia doctor`

系统依赖和运行环境健康检查。

```bash
automedia doctor
```

检查项: python, bun, ffmpeg, whisper, edge-tts, comfyui, chrome。缺失项会标红, 但不会阻止运行, 对应 Gate 在执行时报错。
