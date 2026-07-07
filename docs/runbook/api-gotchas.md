# API 常见陷阱

本文档记录 AutoMedia API 使用中容易踩的坑, 源自原 SKILL.md 和日常开发中的经验教训。

## 路径与目录

### `Project.init()` 的 topic 参数会被 slugify

```python
# topic 会经过 slugify: 转小写, 去除非 ASCII, 连字符化
p = Project.init("Hello World 项目启动")  # 目录名: 20260707_hello-world
```

中文被完全去除, 所以目录名可能比预期短。如果 slug 结果为空, 抛出 `ValueError`。

**陷阱:** 不要假设 `project_dir` 中保留 topic 的原始中文内容。

### `sanitize_path()` 拒绝路径遍历

```python
from automedia.core.project import sanitize_path

sanitize_path("../etc")   # ValueError: Path must not contain '..'
sanitize_path("~/config") # ValueError: Path must not contain '~'
sanitize_path("a//b")     # ValueError: Path must not contain '//'
```

这是安全措施, 防止 topic 参数被用于路径遍历攻击。

## 配置加载

### 配置合并是浅层+递归混合

`deep_merge()` 对字典值递归合并, 但对列表直接覆盖。这意味着:

```yaml
# defaults.yaml
blocked_words:
  - 投资
  - 金融

# brand-profile.yaml
blocked_words:
  - 政治
```

结果: `blocked_words` 只有 `["政治"]`, 不会与默认值合并。

**解决方案:** 如果要追加列表项, 在 overrides 中列出完整的列表。

### 环境变量覆盖规则

`AUTOMEDIA_LLM_API_KEY=sk-xxx` 会解析为:

```python
{"llm": {"api": {"key": "sk-xxx"}}}
```

即, 下划线分割的每一段成为嵌套层级。这可能导致意外的嵌套深度:

```
AUTOMEDIA_FOO_BAR_BAZ=val  →  {"foo": {"bar": {"baz": "val"}}}
```

**陷阱:** 变量名中不要使用多余的下划线, 否则会产生预期外的嵌套结构。

## Pipeline 执行

### `run_full_pipeline()` 不会抛异常

所有异常被捕获并放入 `PipelineResult.error` 字段, 状态设为 `"failed"`。这是设计决定的, 让调用方统一检查 `result.status` 而不是 try/except。

```python
result = run_full_pipeline(topic, brand)
if result.status == "failed":
    print(f"Error: {result.error}")  # 不要 try/except
```

**陷阱:** 如果你忘记检查 `result.status`, 可能误以为 Pipeline 成功完成。

### `resume_from` 使用 Gate 名称, 不是数字

```python
# 正确
run_full_pipeline(topic, brand, resume_from="G3")

# 错误 (不会报错但不会按预期工作)
run_full_pipeline(topic, brand, resume_from="3")
```

`resume_from` 的值必须在当前 mode 的 gate 列表中存在, 否则抛出 `ValueError`。

### mode 影响 gate 列表

不同 mode 执行不同 Gate 子集:

| mode | 包含 Gate |
|------|-----------|
| `auto` | pre-gate, G0-G5, V0-V7, L1-L3 |
| `text_only` | G0-G5, L1-L3 |
| `video_only` | V0-V7, L1-L3 |
| `qa_only` | G0, G2, G3, V1, V6 |

**陷阱:** `qa_only` 只执行 5 个 Gate, 远少于全流水线的 18 个 Gate。不要用 `qa_only` 的结果判断整个流水线是否正常。

## Gate 开发

### Gate 必须定义 `_gate_name` 和 `_failure_mode`

缺失任一属性会在运行时抛 `NotImplementedError`:

```python
class MyGate(BaseGate):
    # 缺少 _gate_name → NotImplementedError
    # 缺少 _failure_mode → NotImplementedError
    pass
```

Gate 通过 `__init_subclass__` 自动注册, 所以这两个属性是类级别的, 不需要 `__init__`。

### Gate 名称不能重复

如果两个 Gate 类定义了相同的 `_gate_name`, 注册时抛出 `KeyError`:

```
KeyError: "Gate 'G0' is already registered by <class '...'>"
```

### `failure_mode` 有两种值

- `"stop"`: Gate 失败则 Pipeline 立即停止, 返回 `status="partial"`
- `"rewrite"`: Gate 失败但 Pipeline 继续执行 (用于可重试的门控)

### execute() 必须返回 dict

返回的 dict 会被追加到 `gate_context` 中传递给下游 Gate。至少应包含:

```python
return {"passed": True, "gate": self._gate_name}
```

如果返回值中没有 `"gate"` 键, 日志中的 Gate 名称会显示 `"unknown"`。

## GateHook

### Hook 不能修改任何东西

`GateHook` 是 `Protocol`, 三个方法的返回值类型都是 `None`。如果 hook 尝试修改 `context` 或 `result`, 修改不会在 Gate 之间传播 (context 是普通 dict, 修改对 Gate 可见, 但这违反约定)。

```python
class BadHook:
    def before_gate(self, gate_name, context):
        context["topic"] = "hacked"  # 技术上可以, 但违反约定
```

**设计原则:** Hook 是观察者, 不是拦截器。如需要自定义阻断逻辑, 用 overrides/rules 而非 hook。

### MD5 记录的文件必须可读

`record_md5()` 会计算文件的 MD5。如果文件不存在或不可读, 静默忽略 (OSError 被捕获)。但你不会收到警告, 需要手动确认 `pipeline_md5.json` 中是否已有记录。

## MCP Server

### `run_pipeline` 的 `resume_from` 空字符串和 None 不同

MCP server 将空字符串转为 `None`:

```python
resume_from = resume_from or None  # "" → None
```

所以如果你从 MCP 传入空字符串, 等价于从头开始。

### allowlist 为空时所有路径都允许

```yaml
# mcp_allowlist.yaml 不存在或为空
```

此时 `check_path_allowed()` 返回 `True`, 所有路径都通过。这不是安全配置, 生产环境请配置 allowlist。

### 归档操作的 Red Line 8

`archive_project()` 检查项目状态是否为 `"published"`。如果不是且未设置 `force=True`, 返回 `{"archived": False, "error": "..."}`。这不是异常, 是预期行为。不要把这个返回值当作 bug。

## 测试

### 测试中的 Gate 注册顺序

Gate 在模块导入时通过 `__init_subclass__` 自动注册。测试中如果多次导入 gate 模块, 已经注册的同名 Gate 会抛出 `KeyError`。

**解决方案:** 在测试之间调用 `_registry._gates.clear()` (注意是私有属性) 或使用隔离的注册表实例。

### 使用 `run_with_results()` 获取全量结果

`run()` 在 stop-mode Gate 失败时提前返回。如果需要完整的 Gate 执行列表 (包括失败后未执行的 Gate 也需要记录), 使用 `run_with_results()`。

## 其他

### `automedia doctor` 不阻止运行

缺失依赖标记为红色但不会退出。这可能导致 Pipeline 在运行中间某一步失败。例如 ComfyUI 不可用时 V1 Vision QA 会失败。

### pool.db 默认使用内存数据库

如果不指定 `--db` 参数, 话题池默认创建在 `:memory:`。这意味着数据只在当前进程存活, 重启后丢失。生产环境始终指定 `--db`:

```bash
automedia pool list --db /path/to/pool.db
```

### 项目目录包含日期前缀

`Project.init()` 创建的目录格式为 `{YYYYMMDD}_{slug}`。同一天同一话题多次运行会产生相同的目录名, 导致冲突。确保话题有区分度。
