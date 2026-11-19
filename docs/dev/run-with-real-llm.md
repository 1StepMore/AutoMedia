# 真模型怎么跑（本仓实测配方 · 2026-11-19）

> 目的：把「这个项目实际跑起来是什么样」写死，别让下一个接手的 agent 靠猜。
> 规则来源：`AGENTS.md §11b`（假模型 vs 真模型）+ workspace 根 `99-Tools/methodology/cross-audit-evidence-protocol.md §五之二`。

## 一、什么时候必须真模型

| 用途 | fake 可以吗 |
|:--|:--|
| 链路 / 契约 / 门覆盖（`automedia validate matrix` 的 gates 覆盖、schema、工具契约） | ✅ `AUTOMEDIA_FAKE_LLM=1`，run record 记 `confidence=mock` |
| **质量验收**（内容可用性、评分、文案/摘要/翻译质量） | ❌ 必须真模型，fake 的质量结论无效 |
| 对客交付包 | ❌ 必须真模型 |

## 二、环境变量（OpenAI 兼容端点即可）

```bash
export AUTOMEDIA_LLM_PROVIDER=openai
export AUTOMEDIA_LLM_API_KEY=<key>          # 只从环境注入，不许写进仓内文件
export AUTOMEDIA_LLM_BASE_URL=<兼容端点>/v4
export AUTOMEDIA_LLM_MODEL=<模型名>
unset AUTOMEDIA_FAKE_LLM                     # 关键：别让 fake 混进来
```

映射真身：`src/automedia/core/config_loader.py:124-129`（六个 `AUTOMEDIA_LLM_*` → `llm.text_generation.*`）。

## 三、免费额度实测（2026-11-19 本机验证）

智谱 `glm-4-flash`（免费档）走 OpenAI 兼容端点，实测可用，无需付费：

```bash
set -a; . ~/.hermes/.env 2>/dev/null; set +a      # 里面有 ZHIPU_API_KEY
export AUTOMEDIA_LLM_PROVIDER=openai
export AUTOMEDIA_LLM_API_KEY="$ZHIPU_API_KEY"
export AUTOMEDIA_LLM_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
export AUTOMEDIA_LLM_MODEL="glm-4-flash"
```

跑质量类场景（示例）：

```bash
source .venv/bin/activate
automedia validate run --scenario l3-platform-integrity-gate
automedia validate run --scenario l4-translation-quality-gate
```

实测结果（同一配方）：

```
l3-platform-integrity-gate   passed (4/4)  confidence=real
l4-translation-quality-gate  passed (4/4)  confidence=real
```

## 四、没有可用模型时怎么办

1. 先查：`env | grep AUTOMEDIA_LLM`、`~/.hermes/.env`、仓内 `model_config.yaml`；
2. 还没有 ⇒ **向 owner 要**（优先免费额度），在 issue 上标 `blocked:no-llm-key` 并写清要哪种（OpenAI 兼容 key + base_url + 模型名）；
3. **不许**用 fake 冒充真跑，也不许因为没 key 就跳过质量验收 —— 跳过 = 没验证。

## 五、跑完的产物放哪

见 `docs/dev/cross-audit-evidence.md`：要交叉审的产物进 `docs/dev/validation-evidence/`，`validation-runs/` 只是本机临时区（gitignored）。
