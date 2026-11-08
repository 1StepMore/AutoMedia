# Expectations Index — 指针与映射

> Owner 拍板 D3（2026-11-08，场景数 2026-11-09 随 #424 退役别名场景同步为 158）：期望/验收工件的**唯一事实源 = `scenarios/`**（158 场景；schema 权威 = `scenarios/STANDARDS.md`）。
> 本目录**不复制任何场景正文**，只放指针与映射；`scenarios/` 内容改动无需同步本文件（指针按路径/命令解析）。
> 改期望只有 Owner 显式指令可触发；Tester 不得为使套件变绿而改期望或产品代码（根 AGENTS.md §0 / constitution）。

## 指针

| 工件 | 唯一事实源 | 访问方式 |
|---|---|---|
| 验收场景库（158 场景） | `scenarios/`（yaml） | `automedia validate list` / `automedia validate matrix` |
| Schema 权威 | `scenarios/STANDARDS.md` | 文档（onboarding 见 `scenarios/README.md`） |
| 预飞基线 | `scenarios/baseline/` | `automedia validate report` / `automedia validate diff` |
| 可执行 E2E 载体 | `tests/test_e2e/`（pytest，marker `e2e`） | `pytest tests/test_e2e -m e2e`（默认 addopts 排除 e2e，须显式 `-m e2e`） |
| 用户旅程文档 | `docs/user/` | User 角色黑盒来源 |

## 离散检查点

治理验收的离散检查点（CP-01–CP-06）见 [checkpoints.md](checkpoints.md)。

## 版本

v1（2026-11-08，治理 P3 建立）。Tester 返回 JSON 的 `expectations_ref` 引用本文件 + 版本号。
