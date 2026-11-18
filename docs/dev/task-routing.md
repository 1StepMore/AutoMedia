# 判活按标签，不问编号（跨仓契约）

> **副本声明**：本文件在 `AutoInfo` / `e2e-test-suite` / `AutoMedia-repo` 各有一份逐字相同的副本。
> 真身 = `99-Tools/methodology/task-routing.md`；校验 `python3 99-Tools/check_matrix_policy_sync.py`。

## 1. 编号是数据，规矩是逻辑

派活**不许**靠「把 issue/PR 编号写进提示词」。编号会变、会被合并、会被重开；规矩不变。
agent 落地后自己按 GitHub 标签判断这个活该不该做、能不能做。

## 2. 可做名单（唯一判据）

```
agent-ready ∧ 无任何 owner:* 标签 ∧ 无 status:claimed ∧ 未被任何 open PR 认领（标题 #N / close|fix|resolve #N）
```

- 想加活 ⇒ 先开 issue 并写清执行契约：**基线 sha / 分支名 / DoD 命令 / 边界（不许动什么）/ 卡住怎么办**。缺一条就别打 `agent-ready`。
- 名单外的活**不做**；看到但没人派的活，记下来问，不自己开工。

## 3. `owner:*` 是例外，不是默认（尺度：最大化 agent 自主权）

**不标 `owner:*` = 任一侧可做**。这是默认值，不是遗漏，也不是「待定」。
只有「**换一侧根本做不了**」才标：

| 标签 | 什么时候标 | 反例（不该标） |
|:--|:--|:--|
| `owner:code-auto` | 重依赖模态（视频/音频/图片渲染、ffmpeg/Chrome/ffprobe）、需要本机独有运行时或产物读取能力 | 纯文本处理、纯代码改动、CI 能验证的活 |
| `owner:human-agent` | Windows 原生问题（本机 WSL 复现不了）、需要 owner 的账号额度/凭据/付费资源/对外动作 | 任何可以在这台机器上跑通的活 |

宁可少标：标错方向的代价是「两边都不做」，比「两边都做」更贵。

## 4. 状态标签（不是归属）

| 标签 | 含义 | 谁改 |
|:--|:--|:--|
| `status:claimed` | 已认领、在做 | 认领方立刻打，防镜像重领 |
| `blocked:env` | 缺能力/依赖，等另一台机器 | 判阻塞方打；**判阻塞方不得自关 issue** |
| `needs-real-verification` | 产物已出，等内容级读数 | 复验方给读数后才关门 |

## 5. 判绿标准

产物类格子按 `docs/dev/matrix-verdict-policy.md`：**真产出 + 内容断言**，不许 skip、不许结构通过冒充。
