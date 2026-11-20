# 真模型怎么跑（与厂商无关 · 2026-11-19）

> 目的：让**任何**接手本仓的 agent / harness 都知道「这个项目要真模型时怎么跑」，且**不依赖某一台机器、不依赖某个厂商、不写死免费额度**。
> 规则来源：`AGENTS.md §11b`（假模型 vs 真模型）+ workspace 方法论 `cross-audit-evidence-protocol.md §五之二`。

## 一、什么时候必须真模型

| 用途 | fake 可以吗 |
|:--|:--|
| 链路 / 契约 / 门覆盖（`automedia validate matrix` 的 gates 覆盖、schema、工具契约） | ✅ `AUTOMEDIA_FAKE_LLM=1`，run record 记 `confidence=mock` |
| **质量验收**（内容可用性、评分、文案/摘要/翻译质量） | ❌ 必须真模型，fake 的质量结论无效 |
| 对客交付包 | ❌ 必须真模型 |

## 二、缺模型时的取用阶梯（按顺序，不许跳步）

1. **本 harness 自带的默认大模型** —— 判据：它能否**暴露 OpenAI 兼容端点**，或能否把 `base_url`/`key`/`model` **注入产品子进程的环境变量**；两者都不行即判不可用，走下一步（不要假设它应该能用）。
2. **本机环境里已有的端点/凭据** —— 只要 **OpenAI 兼容**就行，按本机既有约定只读使用，不改仓库、不写死厂商。
3. **问屏幕前的人类** —— 说明要什么形态：`base_url` + `key` + `模型名`；在 issue 上标 `blocked:no-llm-key` 等人给。

> **免费还是付费，由屏幕前那个人决定**，不由 agent 决定，也不由"某台机器上能免费用"决定。
> 本文件**不写任何厂商名、不写任何免费额度** —— 那是运行记录，不是项目约定。

## 三、本仓接受的接入形态（OpenAI 兼容即可）

```bash
export AUTOMEDIA_LLM_PROVIDER=openai
export AUTOMEDIA_LLM_API_KEY=<由人提供，或本机已有>     # 只从环境注入，不许写进仓内文件
export AUTOMEDIA_LLM_BASE_URL=<端点路径，按提供方规定>   # 形如 https://<host>/v1 或 /v4
export AUTOMEDIA_LLM_MODEL=<模型名>
export AUTOMEDIA_LLM_MAX_TOKENS=8192                    # 推理模型会把默认 2048 预算烧在 reasoning 上
export AUTOMEDIA_LLM_TIMEOUT=180                        # 慢端点内容级 completion 常 >60s 默认超时
unset AUTOMEDIA_FAKE_LLM                                # 关键：别让 fake 混进质量验收
```

映射真身：`src/automedia/core/config_loader.py:124-129`（六个 `AUTOMEDIA_LLM_*` → `llm.text_generation.*`）。
具体填什么由**提供方**决定，仓内不给默认值、不推荐任何厂商。

## 四、跑质量类场景

```bash
source .venv/bin/activate
automedia validate run --scenario l3-platform-integrity-gate
automedia validate run --scenario l4-translation-quality-gate
```

判定看 run record 的 `confidence`：`real` 才算真跑；`mock` 只说明链路通了。

## 五、一次运行记录（示例，不构成约定）

历史上本仓跑出过这样的读数，记录在此只为说明「只要有一个 OpenAI 兼容端点，这两个门的真模型路径就能跑通」：

```
l3-platform-integrity-gate   passed (4/4)  confidence=real
l4-translation-quality-gate  passed (4/4)  confidence=real
```

它不指定任何厂商，也不构成对免费额度的依赖。

## 六、跑完的产物放哪

要交叉审的产物 ⇒ `docs/dev/validation-evidence/`（必须 commit）；`validation-runs/` 只是本机临时区（gitignored），**不是交付通道**。详见 `docs/dev/cross-audit-evidence.md`。
