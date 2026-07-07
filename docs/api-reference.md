# API Reference

## `run_full_pipeline()`

核心入口函数, 执行完整内容生产流水线。

```python
from automedia import run_full_pipeline

result = run_full_pipeline(
    topic="AI 视频生成工具对比",
    brand="my-brand",
    hooks=None,
    mode="auto",
    resume_from=None,
    config_dir=None,
    tenant_id="default",
)
```

### 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `topic` | `str` | (必填) | 内容话题/主题 |
| `brand` | `str` | (必填) | 品牌标识, 对应 brand-profile.yaml |
| `hooks` | `list[GateHook] \| None` | `None` | GateHook 观察者列表 |
| `mode` | `str` | `"auto"` | 运行模式: `auto`, `text_only`, `video_only`, `qa_only` |
| `resume_from` | `str \| None` | `None` | 从指定 Gate 恢复 (跳过前面的 Gate) |
| `config_dir` | `str \| None` | `None` | 项目 `.automedia/` 配置目录路径 |
| `tenant_id` | `str` | `"default"` | 租户/命名空间标识 |

### mode 可选值

| mode | 执行 Gate | 适用场景 |
|------|-----------|----------|
| `auto` | pre-gate + G0-G5 + V0-V7 + L1-L3 | 全链路生产 |
| `text_only` | G0-G5 + L1-L3 | 仅文案生产 |
| `video_only` | V0-V7 + L1-L3 | 仅视频生产 |
| `qa_only` | G0 + G2 + G3 + V1 + V6 | 仅质量审查 |

### 返回值

返回 `PipelineResult` 对象。

## PipelineResult

```python
@dataclass
class PipelineResult:
    status: Literal["success", "failed", "partial"]
    project_id: str
    project_dir: str
    topic: str
    brand: str
    assets: list[AssetInfo]
    gates_log: list[GateLogEntry]
    start_time: float            # time.monotonic() 起始值
    end_time: float              # time.monotonic() 结束值
    total_duration_s: float      # 总耗时 (秒)
    error: str | None = None
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | `str` | `"success"` 全部通过, `"partial"` 部分失败但未阻断, `"failed"` 异常中止 |
| `project_id` | `str` | 12 字符十六进制唯一 ID |
| `project_dir` | `str` | 项目根目录绝对路径 |
| `assets` | `list[AssetInfo]` | 产出资产列表 |
| `gates_log` | `list[GateLogEntry]` | 每个 Gate 的执行日志 |
| `error` | `str \| None` | 异常信息 (仅 status="failed" 时有值) |

## AssetInfo

```python
@dataclass
class AssetInfo:
    type: str            # 资产类型 (如 "video", "article", "image", "audio")
    path: str            # 资产文件路径
    platform: str = ""   # 所属平台 (如 "wechat")
    md5: str = ""        # 文件 MD5 哈希
```

## GateLogEntry

```python
@dataclass
class GateLogEntry:
    gate_name: str                     # Gate 名称 (如 "G0", "V1")
    status: Literal["passed", "failed", "error"]  # 执行状态
    duration_s: float                  # 执行耗时 (秒)
    error: str | None = None           # 错误信息
```

## GateHook Protocol

```python
from typing import Any, Protocol, runtime_checkable

@runtime_checkable
class GateHook(Protocol):
    def before_gate(self, gate_name: str, context: dict[str, Any]) -> None: ...
    def after_gate(self, gate_name: str, context: dict[str, Any], result: dict[str, Any]) -> None: ...
    def on_gate_failed(self, gate_name: str, context: dict[str, Any], error: Exception) -> None: ...
```

三个方法全部是只读观察者, 必须返回 `None`。不允许修改 Gate 行为或阻断执行。

### `before_gate(gate_name, context)`

Gate 执行前调用。`context` 包含话题、品牌、项目目录等不可变快照。

### `after_gate(gate_name, context, result)`

Gate 执行成功后调用。`result` 包含通过/失败状态、耗时、关键指标。

### `on_gate_failed(gate_name, context, error)`

Gate 抛出异常时调用。注意即使 hook 被调用, Pipeline 仍会按 failure_mode 决策是否停止。

### GateObserver

方便子类化的默认空实现:

```python
from automedia.hooks.protocol import GateObserver

class MyHook(GateObserver):
    def after_gate(self, gate_name, context, result):
        print(f"Gate {gate_name} completed: {result.get('passed')}")
```

### MD5 Tracker Hook

内置的 MD5 记录 Hook:

```python
from automedia.hooks.md5_tracker import record_md5, verify_md5, get_pipeline_md5

# 记录文件 MD5
record_md5(project_dir, "G0", "/path/to/output.txt")

# 验证文件完整性
is_valid = verify_md5(project_dir, "G0", "/path/to/output.txt")

# 读取全部 MD5 记录
all_md5 = get_pipeline_md5(project_dir)
```

## Project

```python
from automedia.core.project import Project

project = Project.init(
    topic_slug="AI 视频生成工具对比",
    brand="my-brand",
    tenant_id="default",
    base_dir=None,   # 默认 os.getcwd()
)
```

### `Project.init()` 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `topic_slug` | `str` | (必填) | 原始话题字符串, 自动 slugify 为目录名 |
| `brand` | `str` | (必填) | 品牌标识, 验证路径安全 |
| `tenant_id` | `str` | `"default"` | 租户标识 |
| `base_dir` | `str \| None` | `None` | 项目父目录, 默认当前工作目录 |

### 创建的目录结构

```
{date}_{slug}/
  00_project_info.json    # 项目元数据
  01_content/drafts/      # 文案草稿
  02_images/cover/        # 封面图片
  03_video/               # 视频文件
  03_subtitle/            # 字幕文件
  04_review/              # 审查记录
  05_publish/             # 发布产物
```

### `Project` 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `project_id` | `str` | uuid4().hex[:12] 短唯一 ID |
| `project_dir` | `str` | 项目根目录绝对路径 |
| `topic` | `str` | 原始话题 |
| `brand` | `str` | 品牌标识 |
| `tenant_id` | `str` | 租户标识 |
| `created_at` | `str` | ISO-8601 创建时间戳 |

## `load_config()`

```python
from automedia.core.config_loader import load_config

config = load_config(
    config_dir=None,   # 项目 .automedia/ 路径, 默认 $CWD/.automedia/
    overrides=None,    # 最高优先级键值对
)
```

返回完全合并的配置字典, 包含六层优先级 (从低到高):

1. 内置 `automedia/manifests/defaults.yaml`
2. 项目 `.automedia/` 目录 YAML
3. 用户 `~/.automedia/` 目录 YAML
4. `~/.automedia/overrides/rules/*.yaml`
5. `~/.automedia/overrides/prompts/*.j2`
6. `AUTOMEDIA_*` 环境变量 + `overrides` 参数

## BaseGate

```python
from automedia.gates.base import BaseGate

class MyGate(BaseGate):
    _gate_name = "GX"           # 唯一 Gate 标识
    _failure_mode = "stop"      # "stop" 阻断流水线, "rewrite" 继续

    def execute(self, gate_context: dict) -> dict:
        # gate_context 包含 topic, brand, project_dir, config 等
        return {"passed": True, "gate": self._gate_name}
```

## GateEngine

```python
from automedia.pipelines.gate_engine import GateEngine

# 构造
engine = GateEngine(gates, hooks=hooks)

# 执行全部 Gate
success, results = engine.run(gate_context)

# 执行并返回全部结果 (即使提前停止)
all_results = engine.run_with_results(gate_context)
```

## GateRegistry

```python
from automedia.gates.base import _registry

# 注册的 Gate 自动通过 __init_subclass__ 注册
_registry.list()              # 返回所有 Gate 名称列表
_registry.get("G0")           # 获取 Gate 类
"G0" in _registry             # 检查是否注册
```

## AdapterRegistry

```python
from automedia.adapters.registry import AdapterRegistry

AdapterRegistry.register(WechatPublisher)
cls = AdapterRegistry.get("wechat")
AdapterRegistry.list()        # 列出所有已注册平台
```

## Doctor

```python
from automedia.core.doctor import Doctor

doctor = Doctor()
results = doctor.check_dependencies()
# 返回 [{"name": "python", "installed": True, "version": "...", "path": "..."}, ...]
```

## `sanitize_path()`

```python
from automedia.core.project import sanitize_path

safe_path = sanitize_path("/valid/path")  # 验证并规范化路径
# 拒绝 "..", "~", "//" 模式
```
