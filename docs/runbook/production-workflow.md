# 日常生产流程

本文档描述 AutoMedia 在日常生产中的标准操作流程。

## 每日生产节奏

AutoMedia 每日按以下节奏执行:

| 时间 | 操作 | 工具 |
|------|------|------|
| 08:00 | 热点采集 (4 平台 + Tavily + AIHOT) | `automedia cron run pool-collect` |
| 08:05 | 语义审核 + 黑名单过滤 | `automedia cron run pool-score` |
| 08:30 | 推送 TOP6 话题到飞书 | `automedia cron run topic-push` |
| 09:00 | 运营选话题, 启动生产 | `automedia run --topic "..." --brand ...` |
| 09:30 | 全系统健康检查 | `automedia cron check-health` |
| 全天 | 发布确认 + 归档 | `automedia archive <project-id>` |

## 生产前检查

### 1. 环境就绪

```bash
# 检查依赖
automedia doctor

# 检查配置
ls -la .automedia/
cat .automedia/config.yaml

# 检查话题池
automedia pool list --status pending --db .automedia/pool.db
```

### 2. 网络连通性

```bash
# 确认 LLM API 可用
curl -s -o /dev/null -w "%{http_code}" https://api.openai.com/v1/models

# 确认来源 URL 可访问 (G0 Gate 需要)
curl -s -o /dev/null -w "%{http_code}" https://example.com
```

### 3. 磁盘空间

```bash
df -h /mnt/d/AutoMedia/projects/
# 确保至少 10GB 可用 (视频项目需要)
```

## 启动生产

### 方式 A: CLI 手动运行 (推荐)

```bash
automedia run --topic "AI 视频生成工具对比: 2026 年最新格局" --brand my-brand
```

### 方式 B: Python SDK

```python
from automedia import run_full_pipeline

result = run_full_pipeline(
    topic="AI 视频生成工具对比: 2026 年最新格局",
    brand="my-brand",
    mode="auto",
)

if result.status == "success":
    print(f"项目目录: {result.project_dir}")
    for asset in result.assets:
        print(f"  [{asset.type}] {asset.path}")
else:
    print(f"失败: {result.error}")
    for log in result.gates_log:
        if log.status != "passed":
            print(f"  Gate {log.gate_name}: {log.status} ({log.error})")
```

### 方式 C: MCP (AI Agent)

Agent 调用 `select_topic` 选题, 然后调用 `run_pipeline` 生产。

## 生产监视

### 实时查看

```bash
# 查看项目目录变化
watch -n 5 ls -la 20260707_*/

# 查看 pipeline_md5.json
cat 20260707_*/pipeline_md5.json
```

### 查看 Gate 状态

运行 `automedia run` 时 CLI 输出包含每个 Gate 的状态:

```
Pipeline finished: success
  Project ID : abc123def456
  Project dir: /mnt/d/AutoMedia/projects/20260707_ai-video-tools
  Duration   : 342.5s

  Gates executed: 18
    ✓ pre-gate (0.32s)
    ✓ G0 (12.50s)
    ✓ G1 (8.20s)
    ✓ G2 (5.10s)
    ✓ G3 (3.40s)
    ✓ G4 (2.10s)
    ✓ G5 (1.80s)
    ✓ V0 (0.90s)
    ✓ V1 (45.60s)
    ✓ V2 (30.20s)
    ✓ V3 (15.80s)
    ✓ V4 (10.50s)
    ✓ V5 (2.30s)
    ✓ V6 (60.10s)
    ✓ V7 (5.40s)
    ✓ L1 (0.50s)
    ✓ L2 (1.20s)
    ✓ L3 (0.80s)

  Assets produced: 7
    - [article] 01_content/drafts/wechat/wechat_draft.html
    - [image] 02_images/cover/cover.png
    - [video] 03_video/video_final.mp4
    - [subtitle] 03_subtitle/subtitle.srt
    - [audio] 03_video/tts_audio.mp3
    - [report] 04_review/qa_report.json
    - [log] 05_publish/publish_log.json
```

### 失败处理

如果 Pipeline 显示 `status="partial"` 或 `status="failed"`:

1. 查看错误消息定位失败 Gate
2. 查阅 `docs/runbook/gate-failure-modes.md` 获取修复步骤
3. 修复问题后使用 `--resume-from` 从失败 Gate 恢复:

```bash
automedia run --topic "..." --brand my-brand --resume-from G3
```

## 生产后操作

### 1. 检查产出

```bash
# 检查各目录
ls R 20260707_*/
ls 20260707_*/01_content/drafts/
ls 20260707_*/02_images/cover/
ls 20260707_*/03_video/
```

### 2. 验证文件完整性

```bash
# 检查 MD5 记录
cat 20260707_*/pipeline_md5.json

# 验证关键文件
ffprobe 20260707_*/03_video/video_final.mp4
file 20260707_*/02_images/cover/*.png
```

### 3. 发布

发布通过平台 adapter 自动或手动完成。如果配置了自动发布:

```bash
# 检查发布日志
cat 20260707_*/05_publish/publish_log.json
```

### 4. 归档

确认内容已成功发布后:

```bash
# 归档 (需要 status 为 published)
automedia archive <project-id>

# 或强制归档
automedia archive <project-id> --force
```

归档后项目目录添加 `_archived` 后缀。

## 周常维护

### 清理话题池

每周清理过期话题:

```bash
automedia pool prune --days 14 --db .automedia/pool.db
```

### 检查磁盘使用

```bash
du -sh /mnt/d/AutoMedia/projects/*_archived/
# 已归档项目可考虑移至冷存储
```

### 更新品牌配置

需要时修改 `~/.automedia/brand-profile.yaml`:

- 调整 CTA 策略
- 更新禁止词列表
- 修改品牌名称或调性

### 检查 cron 日志

```bash
tail -100 /var/log/automedia/cron.log
```

确认过去一周所有 job 正常执行。

## 异常处理

### Gate 反复失败

如果某个 Gate 反复失败, 参考 `gate-failure-modes.md` 进行诊断。如果修复后仍然失败:

1. 检查 LLM provider 是否正常 (G0, G1 等 LLM 相关 Gate)
2. 检查外部依赖是否正常 (V1 依赖 ComfyUI, V2 依赖 Whisper)
3. 临时切换到较低的门控阈值 (通过 overrides/rules)

### 磁盘空间不足

```bash
# 查找大文件
find . -type f -size +100M
# 清理已归档项目的临时文件 (保留 00_project_info.json 即可)
```

### API 限流

如果遇到 LLM API 限流:

1. 检查 `model_config.yaml` 中的 `rate_limit` 配置
2. Vision QA 会自动降级到像素亮度法 (输出中标注"降级")
3. 考虑更换 provider 或增加限流窗口

### Pipeline 中途中断

```bash
# 查看已完成的 Gate
cat 20260707_*/pipeline_md5.json | python -m json.tool

# 从中断点恢复
automedia run --topic "..." --brand my-brand --resume-from G3
```
