# Cron Job 调试指南

AutoMedia 将调度职责完全外部化: 不内置调度器, 由系统 crond 或 systemd timer 调用 `automedia cron run <job>`。

## 架构

```mermaid
flowchart LR
    A[系统 crond] -->|"0 8 * * * automedia cron run hot-collection"| B[CLI]
    B --> C[automedia cron run]
    C --> D[Job handler]
    D --> E[Return code 0/非0]
```

每个 cron job:

- 由外部 crond 按 schedule 触发
- 单次执行, 超时后由 cron 自行终止
- 执行结果通过 cron 的 MAILTO 机制或系统日志 (`/var/log/syslog`) 获取
- 无内置持久化, 依赖外部 cron 的日志

## 调试步骤

### 1. 确认 cron 服务运行中

```bash
systemctl status cron    # Debian/Ubuntu
systemctl status crond   # CentOS/RHEL
```

### 2. 测试 CLI 命令本身

```bash
# 直接运行, 观察输出
automedia cron run pool-collect
automedia cron run pool-score
automedia cron run pool-prune
automedia cron run publish-check
```

### 3. 检查 crontab 配置

```bash
crontab -l
```

预期条目示例:

```cron
# AutoMedia 每日定时任务
0 8 * * * cd /mnt/d/AutoMedia && automedia cron run hot-collection >> /var/log/automedia/cron.log 2>&1
5 8 * * * cd /mnt/d/AutoMedia && automedia cron run semantic-audit >> /var/log/automedia/cron.log 2>&1
30 8 * * * cd /mnt/d/AutoMedia && automedia cron run publish-check >> /var/log/automedia/cron.log 2>&1
30 9 * * * cd /mnt/d/AutoMedia && automedia cron check-health >> /var/log/automedia/cron.log 2>&1
```

### 4. 检查系统 cron 日志

```bash
# Debian/Ubuntu
grep -i "automedia" /var/log/syslog

# CentOS/RHEL
grep -i "automedia" /var/log/cron
```

### 5. 检查应用日志

```bash
cat /var/log/automedia/cron.log
```

如果日志目录不存在, 创建它:

```bash
mkdir -p /var/log/automedia
```

### 6. 运行健康检查

```bash
automedia cron check-health
```

执行 4 步检查:

1. Python >= 3.11
2. ffmpeg 可用
3. `.automedia/` 配置目录存在
4. pool.db 可访问

## 常见问题

### Job 未按时执行

- 确认 crond 服务运行中: `systemctl status cron`
- 确认 crontab 中的 schedule 表达式正确 (注意 cron 使用系统时区)
- 检查 `/var/log/syslog` 中的 cron 条目, 看系统是否尝试执行但失败了
- 确认命令中的 `cd` 路径正确, AutoMedia 依赖工作目录

### Job 执行超时

- `automedia cron run` 默认超时 120 秒, 通过 `--timeout` 调整
- 但外部 cron 超时是独立的, 需要确认 cron 配置
- 在命令中增加 `timeout` 前缀: `timeout 600 automedia cron run pool-collect`

### Grace Period 处理

Hermes cron 原来的 grace period 机制在外部化方案中不再存在。Grace period 语义需要自行实现:

```bash
# 包装脚本示例: 检测上一次执行是否还在运行
LOCKFILE=/tmp/automedia-cron-${JOB_NAME}.lock
if [ -f "$LOCKFILE" ] && [ -d /proc/$(cat $LOCKFILE) ]; then
    echo "Previous job still running, skipping"
    exit 0
fi
echo $$ > "$LOCKFILE"
trap 'rm -f "$LOCKFILE"' EXIT

automedia cron run "$JOB_NAME"
```

### 飞书通知不触发

- 确认 `FEISHU_WEBHOOK_URL` 环境变量已设置
- 测试 webhook: `curl -X POST -H "Content-Type: application/json" -d '{"msg_type":"text","content":{"text":"test"}}' $FEISHU_WEBHOOK_URL`
- 如果使用 systemd timer, 需要在 service 文件中配置 `Environment=`

### 多环境一致性

不同环境的 crontab 语法一致。跨平台注意事项:

- macOS crontab 路径与 Linux 不同, 需要 `PATH=/usr/local/bin:$PATH`
- WSL 中 cron 服务默认未启用, 需 `sudo service cron start`
- Docker 容器中通常使用 `supervisord` 替代 crond

## 故障恢复

```bash
# 1. 检查 cron 服务
systemctl is-active cron

# 2. 查看最近 20 条 cron 日志
grep "automedia" /var/log/syslog | tail -20

# 3. 手动执行 job 确认
automedia cron run hot-collection
echo $?  # 确认返回码

# 4. 恢复 crontab (从备份)
crontab /path/to/backup/crontab.txt
```

## 推荐 crontab 模板

```cron
# ┌───────────── 分 (0-59)
# │ ┌───────────── 时 (0-23)
# │ │ ┌───────────── 日 (1-31)
# │ │ │ ┌───────────── 月 (1-12)
# │ │ │ │ ┌───────────── 周 (0-7, 0=周日)
# │ │ │ │ │
# MAILTO="admin@example.com"
# PATH="/usr/local/bin:/usr/bin:/bin"
#
# AutoMedia 每日定时任务
0 8 * * * cd /mnt/d/AutoMedia && automedia cron run pool-collect >> /var/log/automedia/cron.log 2>&1
5 8 * * * cd /mnt/d/AutoMedia && automedia cron run pool-score >> /var/log/automedia/cron.log 2>&1
30 8 * * * cd /mnt/d/AutoMedia && automedia cron run publish-check >> /var/log/automedia/cron.log 2>&1
30 9 * * * cd /mnt/d/AutoMedia && automedia cron check-health >> /var/log/automedia/cron.log 2>&1
```
