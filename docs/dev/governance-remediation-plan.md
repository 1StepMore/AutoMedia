# AutoMedia 治理整改方案（可执行版）

> 基线 commit `214e81b` · 编制日期 2026-11-06 · 修订 r2（2026-11-06）
> 适用环境：Windows 本地 + WSL(Linux) 双栈，多 harness/Agent 协作
> 状态标记：`[已验证]` 有命令输出或文件证据 · `[待验证]` 需 WSL 侧执行 · `[人工]` 需人工确认
>
> **r2 修订**：修正 A1–A5 五处硬伤、B2 编号错位、第三份红线全文、§6 未定义证据编号；新增 B6 接线批次。逐条清单见文末「修订记录」。

---

## 0. 如何使用本文档

- 每条整改项有唯一 ID（`B0-1`、`B1-3`…），可直接用作 commit message 前缀：`fix(governance): B0-1 sync gate range in claude rules`
- 每项含四栏：**位置 / 现状 / 改法 / 验证**。「验证」栏的命令可直接粘贴执行。
- **批次内可并行，批次间必须串行。** B0 不清零，B1 的门禁一上线就是红的。
- 本方案**只描述改动，不包含已完成的改动**。开工前仓库应为干净的 `214e81b`。

---

## 1. 结论

现有治理机制在**执行层健康**（398 行 CI、10 个 pre-commit hook、13 组 ruff 规则），在**治理知识层不健康**：红线存在两个事实源且已双向漂移，入口文件有一半不在任何门禁扫描范围内，三处缺文件时门禁静默通过，CODEOWNERS 路径指向不存在的目录且无任何执法。

在双栈环境下，还有三类额外错配：**工作区字节不可信**（实测 6 个文件 `i/lf w/crlf` 而 `git status` 全静默）、**`make` 在 Windows 不存在**（Makefile 也无 render target）、**`write_text` 全仓 35 个调用点无一传 `newline=`**。

因此整改策略是：**不逐个修补已知缺陷，而是建立让缺陷无法出现的机制**。四类机制：单一事实源（B1）、fail-closed 门禁（B2）、blob 层哈希（B3）、平台无关性静态闸（B4）。

---

## 2. 前提与已确证事实

这些事实是全部整改决策的依据。每条都有证据，开工前不必重新求证。

| # | 事实 | 证据 | 影响的批次 |
|---|---|---|---|
| F1 | 门命名五处两个答案：`AGENTS.md:51`/`docs/index.md:23`/`docs/glossary.md:5` 为 **G0-G6**，`.claude/rules.md:15`/`redlines.py:28` 为 **G0-G5** | `grep -n "G0-G" AGENTS.md .claude/rules.md docs/index.md docs/glossary.md` | B0, B1 |
| F2 | `redlines.py:20` docstring 自称 `sourced from AGENTS.md §5.`，但 `:28` 与 `AGENTS.md:51` 不符 | 自证矛盾，无需外部权威 | B1 |
| F3 | `tests/test_mcp/test_redlines.py:26/:32` 只断 `total == len(redlines)` 和 `total >= 8`，从不校验内容 | 5 passed 但内容已漂移 | B1, B2 |
| F4 | `.claude/rules.md` 不在 `check-doc-consistency.py:96-103` 的 6 项 `_DEFAULT_DOC_FILES` 内 | 缺失时连 WARNING 都不打，静默 exit 0 | B2 |
| F5 | `check-doc-consistency.py:1129-1132` 文件缺失只 `print(WARNING)` 后 `continue` | fail-open | B2 |
| F6 | `.github/CODEOWNERS:5` 写 `/automedia/`，该目录不存在（真实为 `src/automedia/`）；`:2` 的 `* @1stepmore` 兜底使「有规则」与「有专门规则」不可区分 | `ls -d automedia` → No such file；`grep -rln CODEOWNERS tests/ scripts/` → 零命中 | B0, B5 |
| F7 | 工作区有 6 个文件 `i/lf w/crlf`，`git status` 全静默 | `git ls-files --eol \| grep w/crlf`；`threshold-snapshot.json` worktree 2744 / blob 2644 | B3, B4 |
| F8 | `write_text(` 全仓 35 个调用点，**35 个全部未传 `newline=`**，其中 2 个写提交态产物 | AST 扫描；`doc_inventory.py:223`、`snapshot_scenario_thresholds.py:137` | B3 |
| F9 | `coverage-audit.json` 提交态无法由代码复现：`generated_at` 为 `""` 且键序与代码相反 | 56 键中仅 `scenario_count`/`generated_at` 位置互换；H2 逐字节等式 23605 == 23605 | B3 |
| F10 | `make` 在 Windows 不存在；Makefile 70 行 14 个 target 中**无 render** | `make --version` → command not found；真实文档入口是 `mkdocs build --strict` | B4 |
| F11 | `validation_affected.py:128/:145/:169` 用 `str(path.relative_to())`，Windows 输出反斜杠 | 实测 `surface\accounts\...yaml`；喂给 ubuntu CI → `selected` 空 → `sys.exit(1)` | B4 |
| F12 | pre-commit 5 个 local hook 用 `entry: python3` + `language: system`，本机 `python3` 无 `automedia`/`yaml` | `ModuleNotFoundError`，5 个 hook 全红 | B5 |
| F13 | `mcp_allowlist.yaml:42` 的 `/tmp/automedia/` 在 Windows `realpath` → `D:\tmp\automedia`；对应测试已被 `ci.yml:289` deselect（测试本身已有 win32 skipif） | 已知必失败项靠 deselect 掩盖 | B5 |
| F14 | 全仓 `git ls-files -s` 中 `mode 120000` 计数为 0 | 软链风险为零，不需要防护 | — |
| F15 | 提交态 `i/crlf` = 0（1134 `i/lf`、6 `i/lf w/crlf`、13 `i/none`、3 `i/-text`） | commit 侧 LF 基线是守住的 | B3, B4 |

---

## 3. 批次总览

| 批次 | 主题 | 条目 | 退出条件 |
|---|---|---|---|
| **B0** | 清零 | 5 | 三处矛盾消失；`pytest tests/test_mcp/test_redlines.py` 仍 5 passed |
| **B1** | 红线单一事实源 | 9 | `redlines.yaml` 是条文唯一事实源；`docs/dev/redlines.md` 已签入；两份 harness 入口 + `developer-guide.md` 只含 ID 与短摘要（不复制条文） |
| **B2** | 门禁 fail-closed | 4 | 删任一入口文件 → 脚本非零退出；扫描集 = 默认集 ∪ `entries.yaml` |
| **B3** | 哈希与生成 | 5 | oid 哈希跨 OS 同值；提交态可逐字节复现 |
| **B4** | 平台无关性 | 4 | 反斜杠路径消失；`.editorconfig` 就位；生成物无绝对路径；AST 静态闸转绿 |
| **B5** | 收尾 | 4 | pre-commit 在 Windows 可跑；凭据无硬编码；CODEOWNERS 覆盖 4 类已跟踪 harness 目录 |
| **B6** | 接线与执法 | 3 | 5 个门禁在 CI 执行；其中 4 个在 pre-commit 可跑；`consensus.lock` 已生成 |

**顺序不可颠倒。** B0 必须在 B1 之前，否则 B1 的门禁上线即红。`ci.yml:56-63` 的注释记录过一次同类事故：检查上线即红，随后有人加 `continue-on-error`，133 个测试被永久 advisory。

---

## 4. 批次 B0–B1

### B0 清零

目标：把磁盘上**已经存在**的矛盾改对，使后续门禁有干净的基线。这一步不新增任何机制。

#### B0-1 修正 `.claude/rules.md` 的门命名

- **位置**：`.claude/rules.md:15`
- **现状**：`- **MUST** follow gate naming: G0-G5 (copy), V0-V7 (video), L1-L4 (lifecycle)`
- **改法**：`G0-G5` → `G0-G6`，并补全缺失的类别：

```markdown
- **MUST** follow gate naming: G0-G6 (copy/content), V0-V7 (video/quality), L1-L4 (lifecycle), D1-D7 (distribution), P1-P4 (repurpose)
```

- **验证**：

```bash
grep -n "G0-G6" .claude/rules.md   # 必须有输出
grep -n "G0-G5" .claude/rules.md   # 必须无输出
```

#### B0-2 修正 `redlines.py` 的门命名

- **位置**：`src/automedia/mcp/tools/redlines.py:28`
- **现状**：`"MUST follow gate naming convention: G0-G5, V0-V7, L1-L4, H0, pre-gate, CW",`
- **改法**：`G0-G5` → `G0-G6`
- **验证**：

```bash
grep -n "G0-G6" src/automedia/mcp/tools/redlines.py
pytest tests/test_mcp/test_redlines.py -q    # 仍须 5 passed
```

#### B0-3 修正 CODEOWNERS 路径

- **位置**：`.github/CODEOWNERS:5`
- **现状**：`/automedia/ @1stepmore`
- **改法**：`/src/automedia/ @1stepmore`
- **验证**：

```bash
grep -n "src/automedia" .github/CODEOWNERS
ls -d src/automedia          # 路径必须真实存在
ls -d automedia 2>/dev/null  # 必须报 No such file
```

#### B0-4 修正 `.claude/rules.md` 的数值与路径

| 行 | 现状 | 改法 | 依据 |
|---|---|---|---|
| `:7` | `(50 tools)` | `(68 tools)` | `check-doc-consistency.py` 派生值 |
| `:8` | `(12 commands)` | `(21 commands)` | 同上 |
| `:22` | `mypy src/automedia/` | `mypy src/automedia/ --ignore-missing-imports` | 与 `Makefile:43`、`AGENTS.md:67` 一致 |
| `:28` | `` `automedia/` `` | `` `src/automedia/` `` | 真实包路径 |
| `:29` | `tests/ — Test suite (~2,634, 6 pre-existing failures)` | `tests/ — Test suite` | 「6 个已知失败」无法验证，删除 |

- **验证**：

```bash
grep -n "68 tools\|21 commands" .claude/rules.md
grep -n "ignore-missing-imports" .claude/rules.md
grep -n "2,634" .claude/rules.md   # 必须无输出
```

#### B0-5 摘除错误的红线编号（全仓 live 文档）

- **位置**：9 个文档文件、15 行；`docs/archived/**` 是历史证据，`docs/adr/**` 是不可回写的决策记录，两者都不改
- **现状**：`(Red Line 8)` 在 live 文档里被 15 行引用，但 `docs/dev/developer-guide.md:406-421` 的 RL8 是「pre-commit」，与「archive --force」不是同一条——编号本身就是错的。只改 `AGENTS.md`（3 行）与 `.claude/rules.md`（1 行）会留下 11 行悬空引用。
- **改法**：把文档中的 `Red Line 8` 替换为不带编号的描述 `the archive-force rule`；稳定 ID 在 B1 引入。B1-6/B1-7 会整段替换 `AGENTS.md` §5 与 `.claude/rules.md`，这两处届时自然消失；本步先保证文档里没有错误编号。

```bash
git grep -l "Red Line 8" -- AGENTS.md .claude/rules.md README.md 'docs/**' \
  ':!docs/adr/**' ':!docs/archived/**' ':!docs/dev/governance-remediation-plan.md' \
  | xargs -r sed -i 's/Red Line 8/the archive-force rule/g'
```

> **不要扫 `src/`、`tests/`、`scenarios/`、`CHANGELOG.md`**：那里还有 56 行是运行时标签、测试断言和场景描述。
> `tests/test_mcp/test_instructions.py:118` 与 `tests/test_mcp/test_mcp_server.py:590` 直接断言
> `"Red Line 8" in result`；`src/automedia/mcp/tools/projects.py:151` 把它写进用户可见错误。
> 重命名它是**行为可见**的单独变更，必须同时改断言，不属于 B0-5。

- **验证**：

```bash
git grep -n "Red Line 8" -- AGENTS.md .claude/rules.md README.md 'docs/**' \
  ':!docs/adr/**' ':!docs/archived/**' ':!docs/dev/governance-remediation-plan.md'
# 必须无输出
git grep -n "the archive-force rule" -- AGENTS.md README.md docs/dev docs/skills docs/user
# 应覆盖 9 个文件、15 行（docs/adr 不改）
```

---

### B1 红线单一事实源

目标：红线的**条文**只有一处定义（`redlines.yaml`），其余全部是渲染产物（`docs/dev/redlines.md`）或「ID + 短摘要」索引。摘要不复制约束正文，因此它不是第二事实源——改条文仍然只改 YAML。消除 F1 与 F2。

#### B1-1 新建 governance 包

- **位置**：`src/automedia/governance/__init__.py`（新建）
- **内容**：

```python
"""Governance data and derived artifacts.

``redlines.yaml`` is the single source of truth for agent red lines.
It is a COMPILER INPUT, not a distribution format — see
``docs/dev/governance-remediation-plan.md`` §B1.
"""

from __future__ import annotations

__all__: list[str] = []
```

- **验证**：`python -c "import automedia.governance"`

#### B1-2 新建 `redlines.yaml`

- **位置**：`src/automedia/governance/redlines.yaml`（新建）
- **规格**：9 条，每条含 `id` / `text` / `rationale`。**ID 与顺序无关**，这是消除「第 1 条自称第 8 条」的关键。

```yaml
# Single source of truth for agent red lines.
# NEVER parse this file from a harness — read docs/dev/redlines.md instead.
version: 1

redlines:
  - id: RL-ARCHIVE-FORCE
    text: "MUST NOT archive projects using --force. Only the user may force-archive."
    rationale: "The MCP archive_project tool enforces this — it refuses unless status is 'published' or force=True."

  - id: RL-NO-PROD-DATA
    text: "MUST NOT commit real production data, topic pool contents, or credentials to git."
    rationale: "Synthetic fixtures only; see RL-SYNTH-FIXTURES."

  - id: RL-ALLOWLIST
    text: "MUST NOT modify src/automedia/mcp/mcp_allowlist.yaml without explicit user request."
    rationale: "The allowlist is a security boundary, not a convenience file."

  - id: RL-SYNTH-FIXTURES
    text: "MUST use synthetic test fixtures from tests/fixtures/synth/ for testing."
    rationale: "Zero production data in tests."

  - id: RL-ARCHIVE-CMD
    text: "MUST use the automedia archive command for archiving projects — never manual directory operations."
    rationale: "Manual moves bypass md5 tracking and status transitions."

  - id: RL-GATE-NAMING
    text: "MUST follow the gate naming convention: G0-G6, V0-V7, L1-L4, D1-D7, P1-P4; plus H0, pre-gate, CW."
    rationale: "Gate names are referenced by gate_plan.py, dag.py and 33 gate classes."

  - id: RL-FAILURE-MODES
    text: "MUST add new gates to automedia/gates/failure_modes.py when creating them."
    rationale: "An unregistered gate defaults to an undefined failure mode."

  - id: RL-PRECOMMIT
    text: "MUST NOT skip pre-commit checks. Run pre-commit run --all-files before committing."
    rationale: "The hooks are the local half of the CI gate set."

  - id: RL-HOOK-READONLY
    text: "MUST respect the GateHook readonly contract — hooks observe but never mutate."
    rationale: "See automedia/hooks/protocol.py."
```

- **验证**：

```bash
python -c "
import yaml, pathlib
d = yaml.safe_load(pathlib.Path('src/automedia/governance/redlines.yaml').read_text(encoding='utf-8'))
ids = [r['id'] for r in d['redlines']]
assert len(ids) == 9, len(ids)
assert len(set(ids)) == 9, 'duplicate ids'
print('OK', ids)
"
```

#### B1-3 改造 `redlines.py` 从 YAML 读取

- **位置**：`src/automedia/mcp/tools/redlines.py:22-33`（整段替换）
- **现状**：9 条硬编码字符串列表
- **改法**：

```python
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from automedia.mcp.tools._shared import success_response

__all__ = ["get_redlines"]

_SOURCE = Path(__file__).resolve().parents[2] / "governance" / "redlines.yaml"


@lru_cache(maxsize=1)
def _load() -> tuple[dict[str, Any], ...]:
    """Load the single source of truth. Raises if absent — never degrades."""
    if not _SOURCE.is_file():
        raise FileNotFoundError(f"redlines source missing: {_SOURCE}")
    doc = yaml.safe_load(_SOURCE.read_text(encoding="utf-8"))
    return tuple(doc["redlines"])


def get_redlines() -> dict[str, Any]:
    """Return the list of agent red-line constraints.

    Entries are sourced from ``governance/redlines.yaml`` — the single
    source of truth. This tool performs no independent copy.
    """
    entries = [
        {"id": r["id"], "text": r["text"], "rationale": r["rationale"]}
        for r in _load()
    ]
    return success_response({"redlines": entries, "total": len(entries)})
```

> **注意**：返回值结构从 `list[str]` 变为 `list[dict]`。这会破坏 `tests/test_mcp/test_redlines.py` 的现有断言（它检查 `isinstance(x, str)` 和 `MUST` 前缀）。B1-8 同步更新测试。

- **验证**：

```bash
python -c "from automedia.mcp.tools.redlines import get_redlines; r=get_redlines(); print(r['total'])"
# 必须输出 9
```

> **信封形状**：`success_response(data)` 返回 `{"success": True, **data}`，没有嵌套的 `"data"` 键（`mcp_error.py:103-112`）。因此调用方一律用 `result["total"]` / `result["redlines"]`，不是 `result["data"][...]`。

#### B1-4 新建渲染脚本

- **位置**：`scripts/render_redlines.py`（新建）
- **用途**：从 YAML 生成 `docs/dev/redlines.md`。这是**唯一**允许的生成路径。
- **规格**：

```python
#!/usr/bin/env python3
"""Render governance/redlines.yaml -> docs/dev/redlines.md.

MANUAL-ONLY regeneration, CI-CHECKED drift (same pattern as doc_inventory.py).
Usage:
    python scripts/render_redlines.py            # write
    python scripts/render_redlines.py --check    # verify, exit 1 on drift
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "src" / "automedia" / "governance" / "redlines.yaml"
OUTPUT = REPO_ROOT / "docs" / "dev" / "redlines.md"

HEADER = """<!-- AUTO-GENERATED from src/automedia/governance/redlines.yaml -->
<!-- Do not edit by hand. Regenerate: python scripts/render_redlines.py -->

# Agent Red Lines

This file is the **distribution format** for agent red lines. The source of
truth is `src/automedia/governance/redlines.yaml`, which is a compiler input —
harnesses read this Markdown, never the YAML.

| ID | Constraint |
|---|---|
"""


def render() -> str:
    doc = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    rows = [f"| `{r['id']}` | {r['text']} |" for r in doc["redlines"]]
    return HEADER + "\n".join(rows) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify only")
    args = parser.parse_args(argv)

    generated = render()
    if args.check:
        if not OUTPUT.is_file():
            print(f"FAIL: {OUTPUT.relative_to(REPO_ROOT).as_posix()} missing")
            return 1
        committed = OUTPUT.read_text(encoding="utf-8")
        if committed != generated:
            print("FAIL: docs/dev/redlines.md drifted from redlines.yaml")
            print("      Regenerate: python scripts/render_redlines.py")
            return 1
        print("OK: redlines.md matches redlines.yaml")
        return 0

    OUTPUT.write_text(generated, encoding="utf-8", newline="\n")
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

> 注意 `newline="\n"` —— 这是 F8 的直接应用。B4-1 的静态闸会检查它。

- **验证**：

```bash
python scripts/render_redlines.py
python scripts/render_redlines.py --check   # 必须 OK
```

#### B1-5 签入渲染产物

- **位置**：`docs/dev/redlines.md`（新建，由 B1-4 生成）
- **必须签入的理由**：没有 Python 的 harness（纯环境型 devcontainer、只读 documents 的 harness）需要能读红线。若不签入，R01 对这类 harness 就是空的。
- **验证**：

```bash
git add docs/dev/redlines.md
python scripts/render_redlines.py --check
```

#### B1-6 改造 `AGENTS.md` §5 为 ID 索引

- **位置**：`AGENTS.md:44-58`（整节替换）
- **现状**：9 条完整条文 + 一句「These constraints are enforced by the test suite」（与 `docs/dev/developer-guide.md:406` 的「Discipline Constraints, Not Automated」矛盾）
- **改法**：

```markdown
## 5. Agent Constraints (Red Lines) — MUST OBEY

Source of truth: `src/automedia/governance/redlines.yaml`.
Rendered copy: [docs/dev/redlines.md](docs/dev/redlines.md).

| ID | Constraint |
|---|---|
| `RL-ARCHIVE-FORCE` | Never `--force` archive; only the user may. |
| `RL-NO-PROD-DATA` | No production data, topic pool contents, or credentials in git. |
| `RL-ALLOWLIST` | Do not edit `mcp_allowlist.yaml` without explicit user request. |
| `RL-SYNTH-FIXTURES` | Synthetic fixtures only (`tests/fixtures/synth/`). |
| `RL-ARCHIVE-CMD` | Use `automedia archive`, never manual directory moves. |
| `RL-GATE-NAMING` | G0-G6, V0-V7, L1-L4, D1-D7, P1-P4; plus H0, pre-gate, CW. |
| `RL-FAILURE-MODES` | Register new gates in `automedia/gates/failure_modes.py`. |
| `RL-PRECOMMIT` | Never skip pre-commit; run `pre-commit run --all-files`. |
| `RL-HOOK-READONLY` | GateHook observes, never mutates. |

Enforcement: the ID set is checked by
`tests/test_governance/test_redlines_source_of_truth.py` (B1-8), and every
tracked harness entry file is required to be in the scan set by
`scripts/check-doc-consistency.py` (B2-4). The constraints themselves remain
discipline, reviewed in PR. See
[docs/dev/developer-guide.md §Red Lines](docs/dev/developer-guide.md#red-lines-discipline-constraints-not-automated).
```

- **验证**：

```bash
grep -c "RL-" AGENTS.md          # 应为 9
grep -n "Red Line 8" AGENTS.md   # 必须无输出
python scripts/check-doc-consistency.py   # 必须 exit 0
```

#### B1-7 改造 `.claude/rules.md` 为 ID 索引

- **位置**：`.claude/rules.md:11-15`
- **改法**：

```markdown
## Agent Constraints

Full text: `docs/dev/redlines.md`. Source: `src/automedia/governance/redlines.yaml`.

- `RL-ARCHIVE-FORCE` — never `--force` archive
- `RL-NO-PROD-DATA` — no production data or credentials in git
- `RL-SYNTH-FIXTURES` — synthetic fixtures only
- `RL-GATE-NAMING` — G0-G6, V0-V7, L1-L4, D1-D7, P1-P4

(remaining IDs: `RL-ALLOWLIST`, `RL-ARCHIVE-CMD`, `RL-FAILURE-MODES`, `RL-PRECOMMIT`, `RL-HOOK-READONLY`)
```

> 这里保留**摘要 + ID**，不复制全文。摘要可以短，但 ID 必须全，否则 B2 的扫描会漏。实际上 `.claude/rules.md` 在 B2 之后会被纳入扫描，任何数值/型号漂移都会被抓住。

- **验证**：

```bash
# `grep -c` counts LINES containing "RL-", not distinct IDs: 4 bullets +
# 1 "(remaining IDs: ...)" line = 5. Count unique IDs instead.
grep -o 'RL-[A-Z][A-Z0-9-]*' .claude/rules.md | sort -u | wc -l   # 应为 9
grep -n "G0-G5" .claude/rules.md  # 必须无输出
```

#### B1-8 新增事实源一致性测试

- **位置**：`tests/test_governance/__init__.py`、`tests/test_governance/test_redlines_source_of_truth.py`（新建）
- **注意**：`tests/` 根目录**没有** `__init__.py`（`test_mcp`/`test_gates`/`test_core` 有，`test_cli` 没有，仓库本身不一致）。新目录按 `test_mcp` 的做法加 `__init__.py`，但不宣称这是仓库约定。
- **规格**：

```python
"""Red lines must come from one place. See governance-remediation-plan.md §B1."""

from __future__ import annotations

import pytest
import yaml
from pathlib import Path

from automedia.mcp.tools.redlines import get_redlines

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "src" / "automedia" / "governance" / "redlines.yaml"


def test_get_redlines_matches_yaml_exactly() -> None:
    """Tool output must be the YAML, verbatim — no independent copy."""
    doc = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    expected = {r["id"]: r["text"] for r in doc["redlines"]}
    actual = {r["id"]: r["text"] for r in get_redlines()["redlines"]}
    assert actual == expected


def test_redline_ids_are_unique() -> None:
    doc = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    ids = [r["id"] for r in doc["redlines"]]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("entry", ["AGENTS.md", ".claude/rules.md"])
def test_every_entry_references_only_known_ids(entry: str) -> None:
    """Entry files may not invent IDs that the YAML does not define."""
    doc = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    known = {r["id"] for r in doc["redlines"]}
    text = (REPO_ROOT / entry).read_text(encoding="utf-8")
    cited = set(__import__("re").findall(r"RL-[A-Z-]+", text))
    assert cited <= known, f"{entry} cites unknown ids: {cited - known}"
```

- **验证**：

```bash
pytest tests/test_governance/ -q
pytest tests/test_mcp/test_redlines.py -q   # 需同步更新断言，见下
```

> `tests/test_mcp/test_redlines.py` 因返回结构变化会红。需同步改为：`assert result["total"] == 9` 且 `assert all(isinstance(r, dict) and r["text"].startswith("MUST") for r in result["redlines"])`。**保留结构断言，追加内容断言**——不要删除旧测试，它守的是工具面契约。

#### B1-9 收编 `developer-guide.md` 的第三份红线全文

- **位置**：`docs/dev/developer-guide.md:406-421`
- **现状**：这是第三份红线全文，编号 RL1–RL9；RL8 是「pre-commit」，与 README/AGENTS 的「archive --force」冲突。B0-5 只摘掉引用处的编号，这张表仍是独立副本。
- **改法**：整表替换为指向唯一事实源的 ID 索引。保留标题原文，避免既有 anchor 失效。

```markdown
### Red Lines (Discipline Constraints, Not Automated)

Source of truth: [`src/automedia/governance/redlines.yaml`](../../src/automedia/governance/redlines.yaml).
Rendered copy: [`docs/dev/redlines.md`](redlines.md). The full text is not
duplicated here — the rendered table is the only distribution format.

Enforcement: `RL-ARCHIVE-FORCE` is enforced by the `archive_project` MCP tool
and `automedia archive` CLI; `RL-PRECOMMIT` by the pre-commit hooks. The rest
are discipline constraints reviewed in PR.
```

- **验证**：

```bash
grep -nE '^\| RL[0-9]' docs/dev/developer-guide.md   # 必须无输出
grep -n "RL-ARCHIVE-FORCE" docs/dev/developer-guide.md  # 必须有输出
```

---

## 5. 批次 B2–B6

下表是速查；逐项规格见各表格下方。批次间依赖已由 §3 给出。

### B2 门禁 fail-closed（4 项）

| ID | 位置 | 改法 |
|---|---|---|
| B2-1 | `src/automedia/governance/entries.yaml`（新建） | 显式列出 2 个**已跟踪**入口文件；与 `_DEFAULT_DOC_FILES` 取并集，不是替换 |
| B2-2 | `scripts/check-doc-consistency.py:1123` | `files = list(dict.fromkeys([*_DEFAULT_DOC_FILES, *entry_files]))` |
| B2-3 | 同上 `:1127-1132` | `print(WARNING); continue` → 收集缺失项，末尾 `sys.exit(1)` |
| B2-4 | 同上脚本（新增） | 元断言：已跟踪 harness 根下的红线文件 ⊆ 扫描集，否则 `GOV203` |

#### B2-1 新建 `entries.yaml`

- **位置**：`src/automedia/governance/entries.yaml`（新建）
- **关键设计**：这份清单**不是**替换 `_DEFAULT_DOC_FILES`，而是与之**取并集**。两者语义不同——前者是「复述红线的 harness 入口文件」，后者是「含数值声明的文件」（README、`docs/index.md` 等）。混为一谈会导致 `README.md` 被当成红线入口，或 `.claude/rules.md` 被漏掉。
- **只列已跟踪文件**：`.opencode/skills/issue-triage.md` 与 `pr-review-merge.md` 在 `.gitignore:41-46` 内，CI 里根本不存在；把它们写进 manifest 会让 `_load_entry_files` 的 `is_file()` 检查在干净 clone 上直接失败。它们由本地 harness 自行维护。

```yaml
# Agent entry points that restate red lines, tool counts, or gate names.
# Every path here MUST be scanned by scripts/check-doc-consistency.py;
# missing one is a silent coverage hole. Union with _DEFAULT_DOC_FILES.
version: 1

entries:
  - path: AGENTS.md
    restates: [redlines, tool_count, command_count, gate_naming]
  - path: .claude/rules.md
    restates: [redlines, tool_count, command_count, gate_naming]

# Not listed on purpose — listing any of these would make a fresh clone fail
# GOV202, because they are not in the git index:
#   .omo/**                             historical evidence archive
#   .opencode/skills/issue-triage.md    gitignored, local-only maintainer skill
#   .opencode/skills/pr-review-merge.md gitignored, local-only maintainer skill
#   .trae/**                            gitignored
#   .workbuddy/**                       gitignored
#   CHANGELOG.md                        release notes, no live claims
```

- **验证**：

```bash
python -c "
import yaml, pathlib
d = yaml.safe_load(pathlib.Path('src/automedia/governance/entries.yaml').read_text(encoding='utf-8'))
for e in d['entries']:
    assert pathlib.Path(e['path']).is_file(), e['path']
print('OK', [e['path'] for e in d['entries']])
"
```

#### B2-2 扫描集改为并集

- **位置**：`scripts/check-doc-consistency.py:1123`
- **现状**：`files = list(_DEFAULT_DOC_FILES)`
- **改法**：

```python
    entry_files = _load_entry_files()          # 新函数，读 entries.yaml
    files = list(dict.fromkeys([*_DEFAULT_DOC_FILES, *entry_files]))
```

并在模块级新增（脚本当前只在 `:889` 局部 `import yaml`，需提升到模块级；B2-4 还需 `import subprocess`）：

```python
import subprocess

import yaml

_ENTRIES = REPO_ROOT / "src" / "automedia" / "governance" / "entries.yaml"


def _load_entry_files() -> tuple[str, ...]:
    """Entry points that restate red lines. Fails loud if the list is gone."""
    if not _ENTRIES.is_file():
        raise SystemExit(f"GOV202 entries manifest missing: {_ENTRIES}")
    doc = yaml.safe_load(_ENTRIES.read_text(encoding="utf-8"))
    return tuple(e["path"] for e in doc["entries"])
```

- **验证**：

```bash
python scripts/check-doc-consistency.py && echo "union loaded"
```

#### B2-3 fail-closed

- **位置**：`scripts/check-doc-consistency.py:1127-1132`
- **现状**：

```python
    all_findings: list[Finding] = []
    for rel in files:
        path = REPO_ROOT / rel
        if not path.exists():
            print(f"WARNING: {rel} not found — skipped")
            continue
```

- **改法**：

```python
    all_findings: list[Finding] = []
    missing: list[str] = []
    for rel in files:
        path = REPO_ROOT / rel
        if not path.exists():
            missing.append(rel)
            continue
```

并在扫描循环结束后、返回之前插入：

```python
    if missing:
        for rel in missing:
            print(f"GOV202 required entry file missing: {rel}")
        print("      A missing entry file is a coverage hole, not a warning.")
        return 1
```

- **验证**（这一步必须做，它同时是 N07 负向用例）：

```bash
cp .claude/rules.md /tmp/rules.bak
rm .claude/rules.md
python scripts/check-doc-consistency.py; echo "EXIT=$?"   # 必须非 0 且含 GOV202
cp /tmp/rules.bak .claude/rules.md
python scripts/check-doc-consistency.py; echo "EXIT=$?"   # 必须回 0
```

> 改前行为对照：`rm` 之后脚本**连 WARNING 都不打**（`.claude/rules.md` 根本不在 `files` 里），静默 exit 0。这是比 fail-open 更严重的一档。

#### B2-4 元断言：已跟踪 harness 入口 ⊆ 扫描集

- **位置**：`scripts/check-doc-consistency.py`（新增函数，在 B2-3 的缺失检查之后调用）
- **目的**：防止有人新增一个 harness 入口文件却忘了登记。
- **收窄范围（r2）**：只扫**已跟踪的 harness 根**。仓库里含 `MUST NOT|Red Line` 的 `*.md` 有 21 个，其中 18 个是历史方案、归档文档或用户文档，本来就不该被扫描；用全仓 `*.md` 会让 `GOV203` 上线即红。`.trae/` 与 `.workbuddy/` 在 `.gitignore` 内，`git grep` 看不到，也无法从 CI 治理。

```python
# Tracked harness roots only. Gitignored dirs (.trae/, .workbuddy/) are
# invisible to git grep and cannot be governed from CI.
_ENTRY_ROOTS = ("AGENTS.md", ".claude/", ".codex/", ".cursor/", ".opencode/")


def _uncovered_entry_files(scanned: set[str]) -> list[str]:
    """Tracked harness entry files that restate red lines but are not scanned."""
    roots = [r for r in _ENTRY_ROOTS if (REPO_ROOT / r).exists()]
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "grep", "-lE",
         r"MUST NOT|Red Line|RL-[A-Z][A-Z0-9-]+", "--", *roots],
        capture_output=True,
        text=True,
    )
    # git grep exits 1 for "no match" -- clean, not an error.
    if result.returncode not in (0, 1):
        raise SystemExit(f"GOV204 git grep failed: {result.stderr.strip()}")
    on_disk = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return sorted(on_disk - scanned)
```

调用处：

```python
    uncovered = _uncovered_entry_files(set(files))
    if uncovered:
        for rel in uncovered:
            print(f"GOV203 entry file not scanned: {rel}")
        print("      Add it to src/automedia/governance/entries.yaml.")
        return 1
```

- **验证**：

```bash
python scripts/check-doc-consistency.py; echo "EXIT=$?"   # 必须 0

# 负向（N05）：新增一个 harness 入口并复述红线，必须被元断言抓住。
# `git grep` 只搜索引里的路径 -- 新文件必须先 `git add -N`（intent-to-add），
# 否则它搜不到，N05 会静默 exit 0。这是本方案最容易写出的假验证。
printf 'MUST NOT do X\n' > .claude/extra-rules.md
git add -N .claude/extra-rules.md
python scripts/check-doc-consistency.py; echo "EXIT=$?"   # 必须非 0 且含 GOV203
git reset -q -- .claude/extra-rules.md
rm .claude/extra-rules.md
python scripts/check-doc-consistency.py; echo "EXIT=$?"   # 必须回 0
```

### B3 哈希与生成（5 项）

| ID | 位置 | 改法 |
|---|---|---|
| B3-1 | `src/automedia/governance/consensus.py`（新建） | `H = sha256(sorted(POSIX相对路径, key=utf8编码) 的 f"{path}\0{oid}\n")`，oid 由 `git hash-object --stdin --path=<rel>` 得；空集硬失败 |
| B3-2 | `src/automedia/validation/coverage.py:436-437` | 两句对调（`scenario_count` 在前），提交字节零变化 |
| B3-3 | `scripts/generate_coverage_audit.py`（新建） | `--check` / `--output` / `--blank-generated-at`，写盘 `newline="\n"`；`--check` 固定按空 `generated_at` 渲染 |
| B3-4 | `scripts/doc_inventory.py:223` | `write_text(..., encoding="utf-8", newline="\n")` |
| B3-5 | `scripts/snapshot_scenario_thresholds.py:137` | 同上 |

> 原 B3-6（AST 静态闸）并入 B4-1，不单独计项；B3 的退出条件因此不再包含「AST 静态闸转绿」。

#### B3-1 新建 `consensus.py`

- **位置**：`src/automedia/governance/consensus.py`（新建）
- **核心决策**：哈希对象是 **git blob oid**，不是工作区字节。理由见 §2 的 F7/F15：工作区已有 6 个 `w/crlf` 文件，而 `i/crlf` = 0——`eol=lf` 在 commit 侧把行尾归一化了。对工作区取哈希会让两个 OS 得到两个 H。
- **为什么用 `git hash-object --path=<rel>` 而不是手写归一化**：`--path` 让 git 按该路径的 `.gitattributes` 应用 clean filter，等价于「如果这个文件被 add，它会变成什么 blob」。手写归一化要自己处理 LF、BOM、编码、`*.bat eol=crlf` 特例，每一处都是可能写错的地方。

```python
"""Consensus hash over the governance source set.

H is computed over git BLOBS, not worktree bytes: .gitattributes applies
eol=lf at clean time, so a Windows checkout (which may carry CRLF in the
worktree) and a Linux checkout yield the same oid. Hashing worktree bytes
would split the consensus in two -- see docs/dev/governance-remediation-plan.md.

Sources are an explicit list, never a glob: Windows is case-insensitive and
Linux is not, so the same glob can match different sets on the two platforms.

BOM is REJECTED, not stripped: a BOM is legal UTF-8 but shifts every
line-1 match, and silently removing it hides the committer's intent.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
LOCK = Path(__file__).resolve().parent / "consensus.lock"

# Explicit source set. Order here is irrelevant -- compute() sorts by path.
SOURCE_FILES: tuple[str, ...] = (
    "src/automedia/governance/redlines.yaml",
    "src/automedia/governance/entries.yaml",
    "AGENTS.md",
    ".claude/rules.md",
    ".github/CODEOWNERS",
    ".github/workflows/ci.yml",
)


class ConsensusError(RuntimeError):
    """Raised when the source set is empty or a source cannot be hashed."""


def _blob_oid(rel: str) -> str:
    """Blob oid of the CURRENT worktree content, after the clean filter."""
    path = REPO_ROOT / rel
    if not path.is_file():
        raise ConsensusError(f"consensus source missing: {rel}")
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ConsensusError(f"BOM in consensus source: {rel}")
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "hash-object", "--stdin", f"--path={rel}"],
        input=raw,
        capture_output=True,
    )
    # check=True would leak CalledProcessError; the caller contract is
    # ConsensusError only.
    if result.returncode != 0:
        raise ConsensusError(
            f"git hash-object failed for {rel}: "
            f"{result.stderr.decode('utf-8', 'replace').strip()}"
        )
    return result.stdout.decode().strip()


def compute(source_files: tuple[str, ...] | None = None) -> str:
    """Return the consensus hash. Empty source set is a hard failure."""
    files = SOURCE_FILES if source_files is None else source_files
    if not files:
        raise ConsensusError("consensus source set is empty")
    lines = [f"{rel}\0{_blob_oid(rel)}\n"
             for rel in sorted(files, key=lambda p: p.encode("utf-8"))]
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def check() -> int:
    """CLI entry: compare against consensus.lock, exit 1 on mismatch."""
    if not LOCK.is_file():
        print(f"GOV301 consensus lock missing: {LOCK.name}")
        return 1
    expected = LOCK.read_text(encoding="utf-8").strip()
    actual = compute()
    if actual != expected:
        print(f"GOV301 consensus hash mismatch: lock={expected} computed={actual}")
        return 1
    print(f"OK: consensus {actual[:12]}")
    return 0


def write_lock() -> int:
    """Regenerate consensus.lock. Manual step -- commit the result."""
    actual = compute()
    LOCK.write_text(actual + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {LOCK.name}: {actual}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(write_lock() if "--update" in sys.argv[1:] else check())
```

> `consensus.lock` 是仓库内 CI 资产，不是运行时资源：`check()` 只从源码树运行，因此**不**加入 `pyproject.toml:108` 的 package-data（那里只打包 `**/*.yaml`）。首次落地时先执行 `python -m automedia.governance.consensus --update` 生成并提交。

- **验证**（六条，缺一不算 R03 通过）：

| # | 断言 | 命令 |
|---|---|---|
| ① | 跨 OS 同值：同一 commit 在 Windows 与 WSL 各算一次，H 相等 | 两环境各跑 `python -c "from automedia.governance.consensus import compute; print(compute())"`，`diff` 输出为空 |
| ② | 敏感性：改任一源文件一个字符，H 必变 | 见下 |
| ③ | 排除性：只改源集外产物（`generated_at`），H 不变 | 见下 |
| ④ | 顺序无关：`source_files` 顺序置换，H 不变 | 见下 |
| ⑤ | 可复现：同 OS 重跑 + 真实生成产物后，H 与首次相同（含原 ④(b)） | 见下 |
| ⑥ | 空集失败：`compute(())` 抛 `ConsensusError` | 见下 |

```bash
# 首次基准
python -c "from automedia.governance.consensus import compute; print(compute())" > /tmp/h1

# ② 改一个字符必须变
sed -i 's/AutoMedia/AutoMediX/' AGENTS.md
python -c "from automedia.governance.consensus import compute; print(compute())" > /tmp/h2
diff /tmp/h1 /tmp/h2   # 必须不同
git checkout -- AGENTS.md

# ③ 只改源集外产物（generated_at 是产物字段，源集不含该文件），H 不变
python scripts/generate_coverage_audit.py --output /tmp/cov.json
python -c "from automedia.governance.consensus import compute; print(compute())" > /tmp/h3
diff /tmp/h1 /tmp/h3   # 必须相同

# ④ 顺序无关
python -c "
from automedia.governance.consensus import compute, SOURCE_FILES
forward = compute(SOURCE_FILES)
reverse = compute(tuple(reversed(SOURCE_FILES)))
assert forward == reverse, 'hash depends on source order'
print('OK', forward[:12])
"

# ⑤ 同 OS 可复现（Windows 侧真实生成产物后再跑一次）
python scripts/generate_coverage_audit.py --blank-generated-at
python -c "from automedia.governance.consensus import compute; print(compute())" > /tmp/h5
diff /tmp/h1 /tmp/h5   # 必须相同

# ⑥ 空集必须硬失败，不能退化成 sha256(b"")
python -c "
from automedia.governance.consensus import compute, ConsensusError
try:
    compute(())
except ConsensusError as e:
    print('OK:', e)
else:
    raise SystemExit('FAIL: empty set did not raise')
"
```

#### B3-2 `coverage.py` 键序对调

- **位置**：`src/automedia/validation/coverage.py:434-437`
- **现状**：

```python
    # drift-checked against the committed copy; `generated_at` is the
    # inherently run-specific field the drift check excludes.
    result["generated_at"] = datetime.now(UTC).isoformat()
    result["scenario_count"] = len(scenarios)
```

- **改法**（两句对调，**提交字节零变化**）：

```python
    # drift-checked against the committed copy; `generated_at` is the
    # inherently run-specific field the drift check excludes.
    # Key order matters: the committed artifact has scenario_count BEFORE
    # generated_at. Swapping these two lines makes generate() reproduce the
    # committed bytes exactly -- see governance-remediation-plan.md §B3-2.
    result["scenario_count"] = len(scenarios)
    result["generated_at"] = datetime.now(UTC).isoformat()
```

- **验证**（H2 逐字节等式）：

```bash
python scripts/generate_coverage_audit.py --blank-generated-at --output /tmp/cov-regen.json
python -c "
import hashlib, pathlib, subprocess
a = pathlib.Path('/tmp/cov-regen.json').read_bytes()
b = subprocess.run(['git','-C','.','cat-file','blob','HEAD:scenarios/baseline/coverage-audit.json'],
                   capture_output=True, check=True).stdout
print('len', len(a), len(b))
print('sha', hashlib.sha256(a).hexdigest()[:16], hashlib.sha256(b).hexdigest()[:16])
assert a == b, 'H2 equality broken'
print('OK: byte-identical reproduction')
"
```

> 期望：`len` 均 23605，sha 均 `f4a96cb8…`。若不等，说明键序或尾换行仍未对齐。

#### B3-3 新建生成入口

- **位置**：`scripts/generate_coverage_audit.py`（新建）
- **关键点**：① 无尾换行（提交态以 `}` 结尾）；② `--blank-generated-at` 复现提交态的空串；③ 写盘 `newline="\n"`。

```python
#!/usr/bin/env python3
"""Regenerate scenarios/baseline/coverage-audit.json.

MANUAL-ONLY regeneration, CI-CHECKED drift (same pattern as doc_inventory.py).
The committed artifact carries ``generated_at: ""`` by convention and ends
WITHOUT a trailing newline; pass --blank-generated-at to reproduce it
byte-for-byte.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from automedia.validation.coverage import coverage_audit

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = REPO_ROOT / "scenarios" / "baseline" / "coverage-audit.json"


def render(blank_generated_at: bool) -> str:
    data = coverage_audit()
    if blank_generated_at:
        data["generated_at"] = ""
    return json.dumps(data, indent=2, ensure_ascii=False)   # no trailing \n


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify only")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--blank-generated-at", action="store_true")
    args = parser.parse_args(argv)

    if args.check:
        # The committed artifact carries generated_at="". Render THAT shape,
        # not the live timestamp -- otherwise --check is red on every run.
        rendered = render(blank_generated_at=True)
        if not args.output.is_file():
            print(f"GOV401 coverage-audit missing: {args.output}")
            return 1
        if args.output.read_text(encoding="utf-8") != rendered:
            print("GOV401 coverage-audit.json drifted from a fresh audit")
            print("      Regenerate: python scripts/generate_coverage_audit.py "
                  "--blank-generated-at")
            return 1
        print("OK: coverage-audit.json matches a fresh audit")
        return 0

    rendered = render(args.blank_generated_at)
    args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- **验证**：见 B3-2 的 H2 等式；另需 `python scripts/generate_coverage_audit.py --check` 回 0。

#### B3-4 给 `doc_inventory.py` 补 `newline`

- **位置**：`scripts/doc_inventory.py:223`
- **现状**：`_OUTPUT.write_text(generated, encoding="utf-8")`
- **改法**：`_OUTPUT.write_text(generated, encoding="utf-8", newline="\n")`
- **为什么现在才暴露**：`--check` 用 `read_text()` 的通用换行把 CRLF 读回 LF，字符串比较仍相等，所以这个缺陷一直看不见。实测：Windows 上默认写 3664 字节，提交态 3592 字节，差 72 = 文件行数。
- **验证**：

```bash
python scripts/doc_inventory.py            # 重写
python -c "
import pathlib
b = pathlib.Path('docs/doc-inventory.md').read_bytes()
assert b'\r\n' not in b, 'CRLF leaked'
print('OK', len(b), 'bytes, no CRLF')
"
python scripts/doc_inventory.py --check    # 必须 OK
```

#### B3-5 给 `snapshot_scenario_thresholds.py` 补 `newline`

- **位置**：`scripts/snapshot_scenario_thresholds.py:137`
- **现状**：`SNAPSHOT_PATH.write_text(rendered, encoding="utf-8")`
- **改法**：加 `newline="\n"`
- **特别说明**：`scenarios/baseline/threshold-snapshot.json` **已经在磁盘上是 CRLF**（worktree 2744 / blob 2644，差 100 = 100 行）。修完代码后重生成一次即可让工作区回到 LF。
- **验证**：

```bash
python scripts/snapshot_scenario_thresholds.py
python -c "
import pathlib
b = pathlib.Path('scenarios/baseline/threshold-snapshot.json').read_bytes()
assert b'\r\n' not in b
print('OK', len(b))
"
git ls-files --eol scenarios/baseline/threshold-snapshot.json   # 应为 i/lf w/lf
```

### B4 平台无关性（4 项）

| ID | 位置 | 改法 |
|---|---|---|
| B4-1 | `scripts/check-os-independence.py`（新建） | 生成物禁含盘符/`/mnt/`/`/home/`/`/Users/`/UNC；禁 `\r`；禁 BOM；AST 检查 `write_text` 的 `newline` |
| B4-2 | `scripts/validation_affected.py:128/:145/:169` | `str(path.relative_to(root))` → `path.relative_to(root).as_posix()` |
| B4-3 | `scripts/validation_run_affected.py:72` | 同上 |
| B4-4 | `.editorconfig`（新建） | `end_of_line = lf`、`insert_final_newline = true`、`charset = utf-8`；顺带消掉 `check_release_scope.py:133` 的死条目 |

#### B4-1 新建 `check-os-independence.py`

- **位置**：`scripts/check-os-independence.py`（新建）
- **职责**：一条脚本承载三件事——生成物 OS 无关、源码不硬编码绝对路径、`write_text` 必须定行尾。CI 与 pre-commit 跑同一份，避免两套逻辑。
- **克制原则**：**不**做「禁止出现反斜杠」这类粗暴规则（会误伤正则、Windows 路径字面量、文档示例）。只查两件事：生成物 OS 无关、`write_text` 是否定行尾。

```python
#!/usr/bin/env python3
"""OS-independence gate: generated artifacts and write paths.

Three checks, one implementation shared by CI and pre-commit:

  1. Generated artifacts must not carry drive letters, /mnt/, /home/,
     /Users/, UNC prefixes, CR, or a BOM.
  2. ``write_text`` on a committed artifact must pin ``newline="\\n"``
     (Windows defaults to CRLF -- see governance-remediation-plan.md §B3).
  3. Ratchet: the repo-wide count of ``write_text`` calls WITHOUT
     ``newline=`` may not grow above the baseline.

Exit 0 = clean. Any finding = exit 1 with a GOV-code line.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Artifacts whose bytes are compared across platforms.
GENERATED_ARTIFACTS: tuple[str, ...] = (
    "docs/doc-inventory.md",
    "docs/dev/redlines.md",
    "scenarios/baseline/coverage-audit.json",
    "scenarios/baseline/threshold-snapshot.json",
)

# Committed artifacts whose writer must pin newline="\n".
ARTIFACT_WRITERS: tuple[str, ...] = (
    "scripts/doc_inventory.py",
    "scripts/snapshot_scenario_thresholds.py",
    "scripts/generate_coverage_audit.py",
    "scripts/render_redlines.py",
)

# Ratchet baseline. Lower it as writers are fixed; never raise it.
# 35 was the pre-B3 count. B3-4 (doc_inventory.py:223) and B3-5
# (snapshot_scenario_thresholds.py:137) fix 2 of them, so by the time this
# gate lands the repo is at 33. B1-4/B3-3 add NEW writers that already pin
# newline="\n" and are not counted. Setting 35 here would leave 2 slots of
# slack for regressions.
BASELINE_MISSING_NEWLINE = 33

_ABS_PATH = re.compile(
    r"(?<![A-Za-z0-9])"              # not part of a word
    r"(?:"
    r"[A-Za-z]:[\\/]"                # drive letter
    r"|/(?:mnt|home|Users)/"         # POSIX absolute roots
    r"|\\\\[A-Za-z0-9_.-]+\\"        # UNC
    r")"
)


def _check_artifacts() -> list[str]:
    findings: list[str] = []
    for rel in GENERATED_ARTIFACTS:
        path = REPO_ROOT / rel
        if not path.is_file():
            findings.append(f"GOV601 generated artifact missing: {rel}")
            continue
        raw = path.read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            findings.append(f"GOV602 BOM in generated artifact: {rel}")
        if b"\r" in raw:
            findings.append(f"GOV603 CR in generated artifact: {rel}")
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(f"GOV604 generated artifact is not UTF-8: {rel}")
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            match = _ABS_PATH.search(line)
            if match:
                findings.append(
                    f"GOV605 absolute path in generated artifact: "
                    f"{rel}:{lineno}: {match.group(0)!r}"
                )
    return findings


def _write_text_calls(path: Path) -> list[ast.Call]:
    """AST, not grep: 11 call sites span multiple lines, so a line match
    would keep flagging a correctly fixed call (newline= on line 2-4)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "write_text"
    ]


def _iter_py(roots: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        base = REPO_ROOT / root
        if base.is_file():
            out.append(base)
        elif base.is_dir():
            out.extend(sorted(base.rglob("*.py")))
    return out


def check_write_text() -> tuple[list[str], int]:
    findings: list[str] = []

    # Committed-artifact writers: blocking, zero tolerance.
    for rel in ARTIFACT_WRITERS:
        path = REPO_ROOT / rel
        if not path.is_file():
            # Fail closed: a deleted writer is a coverage hole, not a pass.
            findings.append(f"GOV608 artifact writer missing: {rel}")
            continue
        for call in _write_text_calls(path):
            if not any(kw.arg == "newline" for kw in call.keywords):
                findings.append(
                    f"GOV606 artifact writer without newline=: {rel}:{call.lineno}"
                )

    # Repo-wide ratchet.
    missing = 0
    for path in _iter_py(("src", "scripts")):
        for call in _write_text_calls(path):
            if not any(kw.arg == "newline" for kw in call.keywords):
                missing += 1
    if missing > BASELINE_MISSING_NEWLINE:
        findings.append(
            f"GOV607 write_text missing newline= grew: "
            f"{missing} > {BASELINE_MISSING_NEWLINE}"
        )
    return findings, missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    findings = _check_artifacts()
    wt_findings, missing = check_write_text()
    findings.extend(wt_findings)

    for finding in findings:
        print(finding)

    if args.verbose:
        print(f"[info] write_text without newline=: {missing} "
              f"(baseline {BASELINE_MISSING_NEWLINE})")

    if findings:
        print(f"FAIL: {len(findings)} OS-independence finding(s)")
        return 1
    print(f"OK: OS-independence clean (write_text baseline {missing})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- **验证**（这是 N16/N17 的实体，必须双向可证伪）：

```bash
# 正向：B3-4/B3-5 修完后必须 0
python scripts/check-os-independence.py; echo "EXIT=$?"

# 负向：删掉 newline= 必须立刻红
sed -i 's/, newline="\\n"//' scripts/doc_inventory.py
python scripts/check-os-independence.py; echo "EXIT=$?"   # 必须非 0 且含 GOV606
git checkout -- scripts/doc_inventory.py
```

#### B4-2 修正 `validation_affected.py` 的路径分隔符

- **位置**：`scripts/validation_affected.py:128`、`:145`、`:169`（三处）
- **现状**：

```python
# :128  _yaml_relpaths
return {str(path.relative_to(root)) for path in directory.rglob("*.yaml")}

# :145  _scan_yamls
entries.append((str(path.relative_to(root)), doc))

# :169  _fallback_set
batch = {str(path.relative_to(root)) for path in root.glob("*.yaml")}
```

- **改法**：三处都改 `.as_posix()`

```python
# :128
return {path.relative_to(root).as_posix() for path in directory.rglob("*.yaml")}

# :145
entries.append((path.relative_to(root).as_posix(), doc))

# :169
batch = {path.relative_to(root).as_posix() for path in root.glob("*.yaml")}
```

- **为什么必须改**：该脚本的 OUTPUT CONTRACT 是「每行一个相对 scenarios 目录的文件路径」。Windows 输出 `surface\accounts\...yaml` 喂给 ubuntu CI 的 `validation_run_affected.py` 后，所有行都匹配不上 → `selected` 为空 → `:96-97` `sys.exit(1) "nothing to run"`。这是 CI 里 `ci.yml:363-365` 的真实管道，不是理论风险。
- **验证**：

```bash
python scripts/validation_affected.py src/automedia/mcp/server.py > /tmp/affected.txt
grep -c '\\' /tmp/affected.txt    # 必须为 0
head -3 /tmp/affected.txt          # 应为 surface/accounts/... 形式
```

#### B4-3 修正 `validation_run_affected.py` 的消费端

- **位置**：`scripts/validation_run_affected.py:72`
- **现状**：与 B4-2 同族的 `str(path.relative_to(scenarios_dir))`
- **改法**：`.as_posix()`
- **验证**：与 B4-2 配对跑完整管道

```bash
python scripts/validation_affected.py src/automedia/mcp/server.py > /tmp/affected.txt

# 直接验证消费端能匹配生产端输出。CI 传的是位置参数，不是 --from-file
# （该脚本没有 --from-file；ci.yml 用 `$(cat /tmp/affected.txt)`）。
python - <<'PY'
import pathlib, sys
sys.path.insert(0, "scripts")
from validation_run_affected import _path_to_name
from automedia.validation.loader import default_scenarios_dir

keys = set(_path_to_name(default_scenarios_dir()))
paths = pathlib.Path("/tmp/affected.txt").read_text(encoding="utf-8").splitlines()
missing = [p for p in paths if p not in keys]
assert not missing, missing[:5]
print("OK", len(paths), "paths map to scenarios")
PY
```

#### B4-4 新建 `.editorconfig`

- **位置**：`.editorconfig`（新建）
- **为什么需要**：工作区有 5 个 `src/` 源码文件是 CRLF，而它们**没有任何代码写入点**（grep 零命中）——是编辑器写的。`.editorconfig` 是给编辑器的**请求**（VS Code 原生支持，Vim/Emacs 需插件），不是强制；强制靠 B4-1 的检测。
- **附带收益**：`check_release_scope.py:133` 的 `INTERNAL_EXACT` 已列 `.editorconfig` 但文件不存在，补上即消掉这个死条目。

```ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true

[*.md]
trim_trailing_whitespace = false

[*.{bat,cmd}]
end_of_line = crlf

[Makefile]
indent_style = tab
```

> `[*.{bat,cmd}]` 的 `crlf` 必须与 `.gitattributes:3` 的 `*.bat text eol=crlf` 一致——两处不一致会让工作区与 blob 的关系变得不可预测。

- **验证**：

```bash
test -f .editorconfig && echo "exists"
grep -n "^root = true$" .editorconfig
grep -n "^end_of_line = lf$" .editorconfig
grep -nE '^\[.+\]$' .editorconfig
```

> **不要用 `configparser` 读它**：`.editorconfig` 的 `root = true` 出现在任何
> section 之前，`configparser` 会抛 `MissingSectionHeaderError`。上面是纯文本断言。

### B5 收尾（4 项）

| ID | 位置 | 改法 |
|---|---|---|
| B5-1 | `.claude/settings.json:7` | `"sk-your-key-here"` → `"${AUTOMEDIA_LLM_API_KEY}"`，与 `.cursor/mcp.json:7` 同形 |
| B5-2 | `src/automedia/mcp/mcp_allowlist.yaml:42` | `/tmp/automedia/` 保留（WSL 用），另加 Windows 条目；或改为 `AUTOMEDIA_MCP_ALLOWLIST_PATH` 文档化 |
| B5-3 | `.pre-commit-config.yaml:40/:61/:67/:82/:89` | `entry: python3 ...` → 显式解释器或 `language: python`，否则 Windows 侧 5 个 hook 全红 |
| B5-4 | `.github/CODEOWNERS` | 补 4 类**已跟踪** harness 目录规则（`.claude/`、`.codex/`、`.cursor/`、`.opencode/`）；`*` 保留为兜底 |

#### B5-1 统一凭据写法

- **位置**：`.claude/settings.json:7`
- **现状**：`"AUTOMEDIA_LLM_API_KEY": "sk-your-key-here"` —— 占位符被提交到仓库，靠 `check-secrets.py` 的 `your-key-here` 豁免规则放过（实测 exit 0）
- **改法**：与 `.cursor/mcp.json:7` 同形，改为环境引用：

```json
"AUTOMEDIA_LLM_API_KEY": "${AUTOMEDIA_LLM_API_KEY}"
```

- **⚠️ 待验证**：`${VAR}` 在 `.cursor/mcp.json` 里是否由 shell 展开、在 `.claude/settings.json` 里是否由 Claude Code 自身展开，两者机制可能不同。**改完必须实测一次 MCP server 能否启动**。若 Claude Code 不展开，退路是删除整个 `env` 块，改在文档里要求用户自行 export。
- **验证**：

```bash
grep -n 'sk-your-key-here' .claude/settings.json    # 必须无输出
grep -n 'AUTOMEDIA_LLM_API_KEY' .claude/settings.json .cursor/mcp.json
# 两处写法必须同形
python -c "import json; json.load(open('.claude/settings.json')); print('valid JSON')"
```

#### B5-2 处理 allowlist 的 POSIX-only 路径

- **位置**：`src/automedia/mcp/mcp_allowlist.yaml:42`
- **现状**：`- /tmp/automedia/`。Windows 上 `os.path.realpath('/tmp/automedia/')` → `D:\tmp\automedia`，与真实临时目录无关；对应测试在 Windows 必失败，已被 `ci.yml:289` 的 `--deselect` 掩盖。
- **改法**（保持行为不变，只消除误导）：

```yaml
  # POSIX only. On Windows this resolves to <drive>:\tmp\automedia which is
  # almost certainly not what you want -- override the whole allowlist with
  # AUTOMEDIA_MCP_ALLOWLIST_PATH (see line 38) or use the relative entries
  # below, which resolve against the server's working directory.
  - /tmp/automedia/
```

> **测试已经分平台，不要重复改**：`tests/test_mcp/test_allowlist_usability.py:22-26` 已有
> `@pytest.mark.skipif(sys.platform == "win32", reason="the shipped /tmp/automedia entry is a POSIX path (ci.yml deselects it too)")`。
> 本项只需 YAML 注释，并删除 `ci.yml:289` 那条现已冗余的 `--deselect`。
>
> 更彻底的做法是把该条从默认 allowlist 移除、改由 `AUTOMEDIA_MCP_ALLOWLIST_PATH` 注入。但那会改变 Linux 默认行为，需要单独评估——本方案**不做**。

- **验证**：

```bash
grep -n "POSIX only" src/automedia/mcp/mcp_allowlist.yaml
pytest tests/test_mcp/test_allowlist_usability.py -q; echo "EXIT=$?"
grep -n "allowlist_usability" .github/workflows/ci.yml   # 必须无 --deselect
```

#### B5-3 修正 pre-commit 的解释器

- **位置**：`.pre-commit-config.yaml:40`、`:61`、`:67`、`:82`、`:89`（5 处）
- **现状**：全部 `entry: python3 ...` + `language: system`。本机 PATH 上的 `python3` 是没有 `pip install -e .` 的系统 Python，实测：

```
python3 -B scripts/check-doc-consistency.py
→ ModuleNotFoundError: No module named 'automedia'
```

换 `.venv-win/Scripts/python.exe` 后 exit 0。也就是说 **Windows 侧 5 个治理 hook 目前全部红在 ImportError，一行检查都没跑**。

- **改法**：`python3` → `python`（5 处），并在文件顶部补说明：

```yaml
# NOTE: hooks use `language: system` + bare `python` on purpose — they must
# run in the developer's activated venv (which has pytest and the package
# installed). Do NOT switch to `language: python`: the isolated pre-commit
# venv only installs the package itself, not pytest.
# Prerequisite: activate the venv before `pre-commit run`.
```

> `python` 在两个 OS 上都存在（Windows venv 内 `python.exe`，WSL venv 内 `python` 指向 3.14），而 `python3` 在 Windows 上只有系统解释器。这是最小改动。
- **验证**：

```bash
# 必须在已激活 venv 的 shell 里跑
pre-commit run check-doc-consistency --all-files; echo "EXIT=$?"
pre-commit run check-rfc-aging --all-files; echo "EXIT=$?"
pre-commit run check-workflow-semantics --all-files; echo "EXIT=$?"
pre-commit run check-secrets --all-files; echo "EXIT=$?"
```

#### B5-4 补全 CODEOWNERS

- **位置**：`.github/CODEOWNERS`（11 行，整份替换）
- **现状**：只有 4 条规则，`/automedia/` 路径错误，4 类已跟踪 harness 目录无 owner
- **改法**：

```
# Fallback only. A new governed path does NOT automatically get an owner --
# CODEOWNERS cannot be discovered from the filesystem, so the rule below is
# not asserted by any gate. Add an explicit rule when adding a harness.
* @1stepmore

# Core package
/src/automedia/ @1stepmore

# Documentation
/docs/ @1stepmore

# CI/CD configuration
/.github/ @1stepmore

# Harness entry points — each needs its own owner so a change to one
# harness's rules is reviewed by whoever owns that harness.
/.claude/ @1stepmore
/.codex/ @1stepmore
/.cursor/ @1stepmore
/.opencode/ @1stepmore
```

> `.trae/`、`.workbuddy/`、`.omo/` 不加：前两者在 `.gitignore:35-36` 内，从不进仓库；`docs/.omo/` 是历史证据归档，不是活跃入口。**不要**声称 B2 会断言这组规则——B2 只断言红线复述文件的扫描覆盖，CODEOWNERS 的正确性仍是人工审查项。
- **验证**：

```bash
grep -c "@1stepmore" .github/CODEOWNERS    # 应为 8（* + 3 + 4）
for d in .claude .codex .cursor .opencode; do
  grep -q "^/$d/" .github/CODEOWNERS && echo "OK $d" || echo "MISSING $d"
done
ls -d src/automedia   # 路径必须真实
```

### B6 接线与执法（3 项）

> 前三批产出的是**脚本**。脚本不被调用就不是门禁。本批把它们接进 CI 与 pre-commit 两条执行链，并生成 `consensus.lock`。本仓已有先例：`scripts/check-secrets.py` 在 `.pre-commit-config.yaml:67` 执行，但 `.github/workflows/ci.yml` 从未调用它（全文只有 338 行的 `secrets.GITHUB_TOKEN`）——只在开发者本机跑、绕得过的检查不是门禁。`render_redlines.py --check` 属于同一类：不接线就等于 N11 不存在。

| ID | 位置 | 改法 |
|---|---|---|
| B6-1 | `.github/workflows/ci.yml` | 新增 `governance` job：跑 `consensus.py`、`check-doc-consistency.py`、`check-os-independence.py`、`render_redlines.py --check`、`generate_coverage_audit.py --check`；fail-closed |
| B6-2 | `.pre-commit-config.yaml` | 追加三个本地 hook：`check-os-independence`、`governance-consensus`、`redlines-render`（`language: system`，`pass_filenames: false`） |
| B6-3 | `src/automedia/governance/consensus.lock` | 首次生成并提交；CI 与 pre-commit 都比对它 |

#### B6-1 CI job

```yaml
  governance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0          # consensus 需要完整 git 对象库
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -e ".[dev]"
      - name: Consensus hash
        run: python -m automedia.governance.consensus
      - name: Doc consistency
        run: python scripts/check-doc-consistency.py
      - name: OS independence
        run: python scripts/check-os-independence.py
      - name: Redlines drift
        run: python scripts/render_redlines.py --check
      - name: Coverage audit drift
        run: python scripts/generate_coverage_audit.py --check
```

- **不设** `continue-on-error`（否则 J1/J2 失效）。
- **验证**：`act -j governance` 或推一个故意失败的分支，确认 job 红且日志首行是 `GOV\d{3}`。

#### B6-2 pre-commit hooks

```yaml
  - repo: local
    hooks:
      - id: governance-consensus
        name: governance consensus hash
        entry: python -m automedia.governance.consensus
        language: system
        pass_filenames: false
      - id: check-os-independence
        name: check OS independence
        entry: python scripts/check-os-independence.py
        language: system
        pass_filenames: false
      - id: redlines-render
        name: redlines.md matches redlines.yaml
        entry: python scripts/render_redlines.py --check
        language: system
        pass_filenames: false
```

- **验证**：

```bash
pre-commit run governance-consensus --all-files; echo "EXIT=$?"
pre-commit run check-os-independence --all-files; echo "EXIT=$?"
pre-commit run redlines-render --all-files; echo "EXIT=$?"
```

#### B6-3 生成并提交 lock

```bash
python -m automedia.governance.consensus --update
git add src/automedia/governance/consensus.lock
python -m automedia.governance.consensus; echo "EXIT=$?"   # 必须 0
```

- **验证**：在 CI 的 `governance` job 里比对通过；Windows 侧 `python -m automedia.governance.consensus` 也 exit 0。

> **顺序**：`consensus.lock` 必须与 B6-1/B6-2 同一次提交（或更早）落地。B6-1 job 的第一步就是 `consensus.py` 比对 lock；lock 未提交时它必然红，重演 `ci.yml:56-63` 记录的「上线即红 → 加 `continue-on-error`」事故。

---

## 6. 验收判据

### 6.0 证据编号目录

DoD 与各批次只引用下列编号；**未在此定义的编号不得出现在验收条款中**。

**R — 可复现性/一致性的正向证据**

| 编号 | 断言 | 判定 |
|---|---|---|
| **R01** | 无 Python 的 harness 也能读到红线 | `docs/dev/redlines.md` 已签入、含 9 个 ID、与 yaml 渲染一致（B1-4/B1-5） |
| **R02** | 文档数值与代码一致 | `scripts/check-doc-consistency.py` exit 0（脚本实际打印 `68 MCP tools, 21 CLI commands, 162 scenarios`；node/mode 不是它断言的量） |
| **R03** | consensus 哈希六条 | B3-1 验证表 ①–⑥ 全过（跨 OS、敏感性、排除性、顺序无关、可复现、空集失败） |
| **R04** | 提交态生成物可复现 | 三层证据：`permissions` 无 `write`、`ci.yml` 无裸生成器调用、`coverage-audit.json` 快照 diff 为空 |
| **R05** | CODEOWNERS 显式覆盖 | **人工审查**：每个已跟踪 harness 目录有独立规则；不得只用「文件存在且含路径」作证据（`*` 兜底会骗过它） |

**H — 半自动/人工签署项**

| 编号 | 断言 | 签署方式 |
|---|---|---|
| **H1** | 运行时拒绝行为 | 实跑 `archive --force`（无 force 时应拒绝）、allowlist 越界（应拒绝），记录命令与退出码 |
| **H2** | 提交态逐字节等式 | `coverage-audit.json` 的 fresh 渲染 == `git cat-file blob HEAD:...`，23605 == 23605 |
| **H3** | consensus 源集正确性 | 人工确认 6 个源文件「缺一即漏、多一即噪」；这是安全边界，必须签署 |
| **H4** | `${VAR}` 展开机制 | 实测 Claude Code 与 Cursor 各自是否展开（B5-1）；不展开则改写方案并记录 |
| **H5** | 双 OS 命令签名一致 | 人工复核 J3 的 `exit + sorted(code\|POSIX路径\|行号)` 两边逐字符相等 |

**D — 反斜杠防线**

| 编号 | 断言 |
|---|---|
| **D1** | 归一化函数单测：输入含 `\` 时输出全 `/` |
| **D2a** | 生产端 `validation_affected.py` 输出全 POSIX 相对路径 |
| **D2b** | 消费端 `validation_run_affected.py` 的映射命中 D2a 的每一条 |
| **D2c** | 提交态生成物不含 `\` 或盘符 |
| **D3** | 生成物中无绝对路径 |
| **D4** | 注入 `\` 的负向用例必须红（不是静默通过） |

**N — 19 个负向用例**

| 编号 | 注入 | 预期 |
|---|---|---|
| **N01** | 删除 `AGENTS.md` | `GOV202`，exit 1 |
| **N02** | 删除 `.claude/rules.md` | `GOV202`，exit 1 |
| **N03** | 删除 `entries.yaml` | `GOV202`，exit 1 |
| **N04** | `entries.yaml` 指向不存在的文件 | `GOV202`，exit 1 |
| **N05** | 新增 harness 入口复述红线但未登记（须先 `git add -N`，否则 `git grep` 看不见） | `GOV203`，exit 1 |
| **N06** | 模拟 `git grep` rc=2 | `GOV204`，exit 1 |
| **N07** | 把 `redlines.yaml` 的某个 ID 改名但不改 `AGENTS.md` | `pytest` 红（B1-8 的 `cited <= known`） |
| **N08** | `redlines.yaml` 少一条 | 渲染非零 |
| **N09** | `redlines.yaml` 重复 ID | 渲染非零 |
| **N10** | `redlines.yaml` 条文不以 `MUST` 开头 | 渲染非零 |
| **N11** | 手改 `docs/dev/redlines.md` | `--check` 非零 |
| **N12** | 改源文件一个字符但不更新 lock | `GOV301`，exit 1 |
| **N13** | 删除一个 consensus 源文件 | `ConsensusError`，exit 1 |
| **N14** | 空源集 | `ConsensusError`，不得退化 |
| **N15** | 删除或篡改 `consensus.lock` | `GOV301`，exit 1 |
| **N16** | 提交态产物 `write_text` 缺 `newline="\n"` | AST 闸红 |
| **N17** | 新增未登记产物写入点 | 棘轮计数 +1，红 |
| **N18** | 改 `coverage-audit.json` 一个字节 | `GOV401`，exit 1 |
| **N19** | `doc_inventory`/`snapshot` 产物注入 CRLF | 字节等式红 |

### 6.1 四条判据（缺一不算「门禁在两个 OS 上都生效」）

| 编号 | 判据 | 判定方式 |
|---|---|---|
| **J1** | 正向控制 | 干净树上 Windows 与 WSL 均 exit 0。无 J1，J2 即「恒红」假验证 |
| **J2** | 负向红对原因 | 同一份坏输入两边都红，且红因是 `^GOV\d{3} `、pytest 的 `FAILED` 或 `ConsensusError`，**不是 traceback** |
| **J3** | 双跑签名等价 | `exit + sorted(code\|POSIX路径\|行号)` 两边逐字符相等 |
| **J4** | 回滚锚定 | 回滚整改后负向用例必须转绿 |

### 6.2 四种假验证（不得用作证据）

| 代号 | 形态 | 本仓实证 |
|---|---|---|
| A | 两边都 exit 0 | `check-doc-consistency.py:1129-1132` fail-open，任何边都 0 |
| B | `git status` 干净 | 6 个文件 `i/lf w/crlf`，git 全静默 |
| C | 门禁恒红 | 靠 J1 排除 |
| D | 红在错误原因 | `ModuleNotFoundError` 也是 exit 1，但零检查执行 |

### 6.3 三条元规则（对所有断言生效）

| 编号 | 规则 |
|---|---|
| **M1 可证伪性** | 每条断言必须写明「它在什么注入下会失败」；写不出即视为恒真，删除 |
| **M2 构造与被验异源** | 禁止「用 A 的序/值构造 → 再拿 A 断言」 |
| **M3 基准取不受污染的一层** | 比较基准取 blob 而非工作区、fresh 自然序而非 committed 序 |

### 6.4 DoD（11 条）

1. J1 通过：`check-doc-consistency` + `check-os-independence` + `consensus` + `test_redlines.py` 在 Windows/WSL 均 exit 0
2. J2 通过：N01–N19 每条两边都红，红因与预期一致（`GOV` code / pytest `FAILED` / `ConsensusError`）
3. J3 通过：双跑签名逐条相等（H5 复核）
4. J4 通过：回滚后用例转绿
5. fail-closed 实证：N01/N02/N03/N04 触发 `GOV202 + exit 1`（改前是静默 0）；N07 由 `pytest tests/test_governance/` 红（B1-8 的 `cited <= known`）
6. R03 ①–⑥ 全过，含跨 OS 跨版本（3.11/3.13/3.14）哈希相等
7. R04 三层证据：`permissions` 无 `write`、`ci.yml` 无裸生成器调用、快照 diff 为空
8. 反斜杠防线全过：D1 + D2a/b/c + D3 + D4
9. 人工签署 H1–H5（H1 运行时拒绝行为、H3 源集正确性为强制项）
10. N16/N17 转绿 + 棘轮不增；`i/crlf` = 0
11. H2 逐字节等式成立（23605 == 23605），且 `git diff --exit-code` 为空

### 6.5 判定「不可信」的红线

- 门禁在 CI 带 `continue-on-error: true`
- 断言是「输出非空」而非稳定 code
- 为双跑一致在 Windows 侧加 `\` 兼容分支（应归一化，不应分叉）
- R05 只做「CODEOWNERS 存在且含路径」的静态存在性检查（会被 `*` 兜底欺骗）
- 源集用 glob（两 OS 可能命中不同集合）

---

## 7. 未验证项

| 项 | 原因 | 处置 |
|---|---|---|
| WSL 侧全部命令 | 本机 `wsl.exe` 被 Program Blacklist 拦截 | 待 operator 执行；不得在任何报告中写「已双跑」 |
| `TextIOWrapper(newline="\r\n")` 在 Linux 的行为 | 同上 | 仅有 CPython 文档语义推断 |
| 双 venv 共存 | `.venv` = Linux py3.14.4（`bin/python -> /usr/bin/python3.14`）、`.venv-win` = Windows py3.13.14 | 命令必须显式指定 `$PY`，禁 PATH 解析 |
| 3.14 不在 CI 矩阵 | CI 只覆盖 3.11/3.12/3.13 | 本地结果需在 3.11 复核 |
| 6 个 `w/crlf` 文件的清理 | 不影响仓库（索引 LF），清理只制造无意义 diff | **不清理**，仅在验证脚本中「记录」不断言 |

---

## 8. 附录：本次整改不做什么

明确排除，避免范围蔓延：

- **不**引入 `sort_keys=True`（56 键中仅 2 键需换位，全量重排无收益）
- **不**清理 6 个 `w/crlf` 文件
- **不**为反斜杠加平台兼容分支（应归一化，不应分叉）
- **不**把 `make` 补齐到 Windows（改为 Python 模块作唯一入口）
- **不**删 `coverage-audit.json` 的 git 跟踪（它是 drift 基线）
- **不**重写 `coverage_audit()` 的审计逻辑（能力已存在且跨平台确定性已验证，只缺 CLI 入口）

---

## 9. 修订记录

### r3（2026-11-06）

**评审发现并实测复现的缺陷**

| # | 问题 | 修正位置 |
|---|---|---|
| C1 | N05 是假验证：`git grep` 只搜索引，新建的未跟踪文件搜不到，负向用例静默 exit 0 | B2-4 验证加 `git add -N` / `git reset -q --`；§6.0 N05 加注 |
| C2 | `render_redlines.py --check` 未接入任何执行链 → 手改 `docs/dev/redlines.md`（N11）无门禁可抓 | B6-1 job、B6-2 hooks（新增 `redlines-render`）、§3 B6 退出条件 |
| C3 | `BASELINE_MISSING_NEWLINE = 35` 未扣 B3-4/B3-5 修掉的 2 个写入点，留 2 个回归空位 | B4-1 改为 33，并注明 35 是 pre-B3 计数 |
| C4 | B1-7 用 `grep -c "RL-"` 断言 9：它数的是行（4 bullet + 1 行 remaining = 5），不是 ID | 改为 `grep -o ... \| sort -u \| wc -l` |
| C5 | DoD 第 5 条把 N07 写成 `GOV202`：N07 是 `redlines.yaml` 改名，红在 pytest（B1-8） | 改为 N01/N02/N03/N04 触发 `GOV202`；N07 归 pytest |
| C6 | §6.0 R02 的「26 nodes / 9 modes」不是 `check-doc-consistency.py` 断言的量 | 改为脚本实际打印的 `68 tools / 21 commands / 162 scenarios` |
| C7 | B5-4 写 CODEOWNERS「12 行」，实际 11 行 | 改为 11 |
| C8 | B0-5 的 sweep 覆盖 `docs/adr/ADR-005:42`：ADR 不可回写，且使计数虚高 | 排除 `docs/adr/**`；范围改 9 文件 / 15 行；悬空引用 14 → 11 |
| C9 | B1 的「唯一事实源」只到 ID 层：`AGENTS.md` / `.claude/rules.md` 仍保留手写摘要（含 `G0-G6` 文本），B1-8 只查 ID 子集 | B1 目标与 §3 B1 行软化为「条文唯一 + ID/短摘要索引」 |
| C10 | B6-3 未说明顺序：B6-1 的 job 先跑 consensus，lock 未提交必红 | B6-3 加顺序注记 |
| C11 | B6 缺「脚本存在但不接线」的本仓实证 | B6 引言补 `scripts/check-secrets.py` 仅 pre-commit、CI 未调用的例子 |

### r2（2026-11-06）

**审查发现的硬伤（A 级）**

| # | 问题 | 修正位置 |
|---|---|---|
| A1 | `success_response` 返回 `{"success": True, **data}`，没有 `"data"` 键；原文 `r["data"]["total"]` 会 `KeyError` | B1-3、B1-8 的验证代码改为 `r["total"]` / `r["redlines"]` |
| A2 | B2 速查表编号与正文错位（表说 B2-2 做 fail-closed，正文 B2-3 才是） | B2 表重排为 B2-1 manifest / B2-2 并集 / B2-3 fail-closed / B2-4 元断言 |
| A3 | 只改 `AGENTS.md` 与 `.claude/rules.md`，`developer-guide.md:406` 还有第三份 RL1–RL9 全文，且 RL8 与之冲突 | 新增 B1-9 整表替换；B0-5 扩为全仓 live 文档 sweep |
| A4 | B4-3 的验证用了不存在的 `--from-file` 选项 | 改为断言生产端每条路径都能被 `_path_to_name` 映射 |
| A5 | 用 `configparser` 读 `.editorconfig` 会抛 `MissingSectionHeaderError` | 改为纯文本 `grep` 断言，并加警告 |

**事实更正**

| 原文 | 更正 |
|---|---|
| CI 399 行 | 398 行 |
| `redlines.py:21` | `redlines.py:20` |
| `ci.yml:247` deselect | `ci.yml:289` |
| `AGENTS.md:80` mypy | `AGENTS.md:67` |
| B1 共 8 项 | 9 项（新增 B1-9） |

**规格收紧**

- **B2-1/B2-4**：只列/只扫**已跟踪** harness 根（`AGENTS.md`、`.claude/`、`.codex/`、`.cursor/`、`.opencode/`）。`.trae/`、`.workbuddy/`、两个本地 skill 在 `.gitignore` 内，写进 manifest 会让干净 clone 直接 `GOV202`；全仓 `*.md` 扫描会命中 18 个本不该扫的文档。`git grep` 用 `check=False` 并接受 rc 0/1，否则「无匹配」本身会抛异常。
- **B3-1**：`_blob_oid` 不再用 `check=True`（会泄漏 `CalledProcessError`），统一抛 `ConsensusError`；补 `write_lock()` 与 `__main__`，使 `--update` 可生成 lock；注明 `consensus.lock` 不打包。
- **B3-3**：`--check` 固定 `render(blank_generated_at=True)`；原写法用实时时间戳渲染，导致每次 `--check` 都漂移。
- **B3-6**：并入 B4-1，B3 只剩 5 项，退出条件里的「AST 静态闸转绿」移到 B4。
- **B4-1**：`check_write_text` 遇到缺失的产物写入点时记 `GOV608`，不再 `continue`。
- **B5-2**：测试已有 win32 skipif，只改 YAML 注释并删除 `ci.yml:289` 的冗余 deselect。
- **B5-4**：只补 4 个已跟踪 harness 目录，`@1stepmore` 计数为 8；删除「B2 会断言 CODEOWNERS」的假声明。

**新增**

- **B6 接线与执法**：把三个脚本接进 CI 与 pre-commit，并生成 `consensus.lock`。原方案产出脚本却无调用点，等于没有门禁。
- **6.0 证据编号目录**：定义 R01–R05、H1–H5、D1–D4、N01–N19；DoD 的 11 条只引用已定义编号（`N19a′` → `N16/N17`）。
