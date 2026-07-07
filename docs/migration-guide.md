# Hermes → AutoMedia 迁移指南

将现有 Hermes Agent 上的 AutoMedia 生产环境迁移到独立 `automedia` 包。

## 迁移清单

### 安装

- [ ] `pip install automedia` (或从源码 `pip install -e .`)
- [ ] 确认 Python >= 3.11
- [ ] 确认外部依赖就位: `automedia doctor`
- [ ] (可选) `pip install automedia[mcp]` 如果使用 MCP

### 配置迁移

- [ ] 复制 `~/.hermes/config/model_config.yaml` 到 `~/.automedia/model_config.yaml`
- [ ] 如有品牌配置, 创建 `~/.automedia/brand-profile.yaml`
- [ ] 如有平台 adapter, 创建 `~/.automedia/adapters/registry.yaml`
- [ ] 迁移自定义 overrides: `~/.hermes/overrides/` → `~/.automedia/overrides/`
- [ ] 检查环境变量: `HERMES_*` → `AUTOMEDIA_*` 前缀
- [ ] 迁移 API 凭证: 从 Hermes `.env` 到 `AUTOMEDIA_*` 环境变量或 `~/.automedia/oscreds.yaml`

### 验证

- [ ] `automedia doctor` 全部绿色
- [ ] `automedia init --template minimal` 生成 `.automedia/config.yaml`
- [ ] `automedia run --topic "测试话题" --brand test --mode qa_only` 运行成功 (QA-only 模式无需外部依赖)
- [ ] `python -c "from automedia import run_full_pipeline; print('OK')"` 导入正常
- [ ] `automedia pool list` 显示话题池 (如已有 pool.db)

### 切换

- [ ] 更新 crontab: 原来调用 Hermes cron 的条目改为调用 `automedia cron run <job>`
- [ ] 更新 systemd timer (如有)
- [ ] 通知团队成员新的 CLI 命令
- [ ] 将 CI/CD 中的 `hermes` 命令替换为 `automedia`

### 回滚

- [ ] 保留旧 Hermes 环境不动 (不卸载)
- [ ] `~/.hermes/skills/productivity/automedia/` 备份保留
- [ ] crontab 中保留旧条目但注释掉
- [ ] 如需回滚: 恢复 crontab 旧条目, 切回 Hermes 环境变量

## 关键差异

| Hermes | AutoMedia |
|--------|-----------|
| `skill_view(name='...')` 注册视图函数 | 纯 Python 类 + typer CLI |
| Hermes cron (内置 scheduler) | 外部 crond + `automedia cron run` |
| `execute_code` sandbox | 纯 Python 执行 |
| `hermes.get_config()` 运行时 API | `load_config()` 函数 |
| `~/.hermes/` 配置目录 | `~/.automedia/` 配置目录 |
| Hermes jobs.json (专有格式) | YAML + 外部 cron |
| Hermes 日志格式 | Python 标准 logging |
| OpenCode Go 默认 LLM 绑定 | 可配置 provider (OpenAI/Anthropic) |
| 品牌硬编码 | brand-profile.yaml 配置化 |
| Hermes agent 耦合路径 | 纯 Python 包, 零 agent 依赖 |

## 常见问题

**Q: 旧项目的 `pipeline_md5.json` 还能用吗?**

A: 格式兼容, 但路径跟随新 `Project.init()` 结构。将旧项目目录放在 `base_dir` 下即可识别。

**Q: Hermes 的飞书通知还能用吗?**

A: 可以。飞书通知已封装为可选 adapter, 配置环境变量 `FEISHU_WEBHOOK_URL` 即可启用。

**Q: 之前的 cron job 历史怎么迁移?**

A: cron 历史在系统日志中, 不依赖 Hermes。复制 crontab 条目并调整命令为 `automedia cron run <job>`。

**Q: 迁移后旧 Hermes 技能包还能运行吗?**

A: 可以, 两者独立。旧 Hermes 环境不受影响, 但建议新项目全部走 automedia。
