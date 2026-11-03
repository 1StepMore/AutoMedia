# Remotion 组件 kit（12 组件 + 帧数校验 + 字体门 + 341 风格库）

`stacks/remotion/kit` ｜ 适用栈：**仅 Remotion**（HyperFrames 用不了） ｜ 含下级共 13 个文件 ｜ 96 KB

归档工程 `effects-v9.tsx` 的 12 个组件清洗版，可直接拷进 Remotion 项目用。

**HyperFrames 版已撤回（主人 2026-10-23）**：主栈已改为 Remotion，再维护 HTML+GSAP 第二套是纯浪费；
kit 的验收标准从「双栈」降为 **Remotion 单栈**。别再加 HF 版。

## 文件分工

| 文件 | 放什么 |
|:--|:--|
| `theme.ts` | **生成物**（勿手改）：色/字/尺寸 token，真身在 `_tokens/brand-tokens.json` |
| `guards.ts` | 入参守卫 + 禁色拦截 + 缓动过冲校验（缺参数渲染前就炸，不静默降级） |
| `text.tsx` | SubtitleCard / SectionBadge / MainTitle / TitleStagger / WordHighlight / Typewriter |
| `motion.tsx` | AnimatedCounter（默认不过冲）/ EASE_ELASTIC / pickTransition（typed，含真 clockWipe） |
| `decor.tsx` | SVGGradientBand / GrainOverlay / AbstractGradientBackground / ParticleBackground / FrameIndex |
| `chart.tsx` | SBarChart |
| `timecode.ts` | `assertTotalFrames`（Σ场次 − Σ过渡，差一帧抛错） |
| `index.ts` | 统一导出 |
| `fonts.tsx` | 字体加载等待（useFonts / measureCN / FontGate）—— woff2 没加载完不渲染，防静默回退系统字体 |

## 组件 props（关键默认值）

| 组件 | 用途 | 必填 | 默认/约束 |
|:--|:--|:--|:--|
| `MainTitle` | 多行大标题（**语义分行，行内不断字**） | `lines: string[]` | `fontSize=96`、`top=320`、每行 `nowrap`；行太长画面上打红框报 OVERFLOW |
| `TitleStagger` | 多行标题依次入场 | `lines[{text,delay}]` | `fontSize=92`、`top=320` |
| `SubtitleCard` | 字幕卡（默认不烧） | `sentences[{text,start,duration}]` | `bottom=320`（范围 260–900，260=1920−1660 安全线） |
| `SectionBadge` | 段角标「01/06 · 钩子」 | `index,total,label` | `top=100,left=80`，自动补零 |
| `WordHighlight` | 词级高亮（底色左→右铺开） | `text,highlight` | `highlightColor=inkLight`、`fontSize=44` |
| `Typewriter` | 打字机 + 光标 | `text` | `charsPerFrame=0.5` |
| `AnimatedCounter` | 数字滚动（**默认不过冲**） | `end` | `easing=EASE_STANDARD`；弹性用 `EASE_ELASTIC`（过冲 1.25%，>2% 抛错）；显示值 clamp 在 `[start,end]` |
| `pickTransition(name)` | 按名字取转场（类型安全） | `name` | `fade / slide-left / slide-right / slide-top / clock-wipe` |
| `pickTransitionByIndex(i)` | 按序号轮换 | `i` | 5 种循环，越界取模 |
| `SVGGradientBand` | 渐变光带（分隔/过渡） | — | `ink → inkLight`，入场从左生长 |
| `GrainOverlay` | 颗粒质感（原 SandGrain） | — | `tone=paper`、`alpha≤0.08`、确定性伪随机 |
| `AbstractGradientBackground` | 墨黑底 + 钴蓝光晕 | — | `intensity=0.45`（上限 `MOTION.gradientIntensityMax`）；高饱和面积 ≈35%，不再整屏渐变 |
| `ParticleBackground` | 粒子（逐帧 sin/cos） | — | `count=12`、`color=inkLight` |
| `SBarChart` | 柱状图（spring + 数字跟随） | `bars[{label,value,maxValue}]` | 柱宽**自动撑满**（占宽 ≥70%，不够抛错）；数值标签贴柱顶 |
| `assertTotalFrames` | 总帧数校验 | `expected,segments,transitions` | 差一帧抛错 |

## 相对原版改了什么（都有验收）

| 改动 | 为什么 |
|:--|:--|
| 色值 → token；禁色抛错 | 原版写死金/绿/棕/浅蓝/靛蓝，与品牌四档冲突 |
| 字体 → 品牌字体 + 显式 400 | 原版写 Source Han/Arial；中文 VF 默认 200 极细 |
| `SandGrain` → `GrainOverlay` | 原版暖棕颗粒 >8% 抢主色相 |
| `MainTitle` 单字符串 → `lines[]` | 中文无词边界，CSS 折行把「不缺机器」切成「器 不缺机」（P0） |
| 标题带 296/299 → 320 | 旧默认压安全区边缘（P1） |
| `SBarChart` 写死柱宽 96px → 撑满 | 三根只占 43% 画面，s4 用起来缩在中间（P1） |
| 渐变更成光晕（intensity 上限 0.6） | 整屏渐变实测高饱和 98.6%，把主色相吃干（P2） |
| 数字滚动：默认不过冲 + 显示值 clamp | 数字是事实，屏幕上闪 110 而事实是 100 就是错数字 |
| `TransitionPicker` → `pickTransition*` | 原版返回 `any`，注释说 clockWipe 实为 slide 占位 |
| 新增 `assertTotalFrames` | 原骨架依赖库外 `../src/timecode`，不为一个骨架拖外部依赖 |

## 验收要求（主人 2026-10-23 追加）

每个组件除了孤立 demo 帧，还要有一张**贴进 s0/s4 场景的实拍帧** —— 孤立 demo 好看不代表进片子成立
（`SBarChart` 的 `fontSize=40` 低于品牌最小 44 就是这样被抓出来的：类型检查全过，真渲才炸）。

## 出处与许可

- 11 个组件：改写自本仓归档工程 `Remotion-Test-归档-20261012`（自有代码）。
- `WordHighlight` / `Typewriter`：思路参考 `https://github.com/remotion-dev/skills`（维护者 JonnyBurger），参考 commit `6c67adcd9cdbe6eb84d76342da89b225f9161cb2`；**该仓库无 LICENSE（license=null）⇒ 代码不可复制**，本实现为 clean-room 重写（高亮用 background-size 推进、打字机用字符切片 + opacity 光标），未复制源码。

**什么时候来这找**：在 Remotion 里要字幕卡、标题、数字滚动、柱状图、颗粒质感、转场时（先看组件表，别自己重写）

## 文件

档位说明：`paid` 可付费投放 ｜ `deliverable` 可对外（CC BY 需署名）｜ `internal` 仅内部试验

| 文件 | 大小 | 规格 | 档 | 授权 | 说明 |
|:--|--:|:--|:--|:--|:--|
| `README.html` | 19 KB |  | `paid` | 自有 |  |
| `animations.tsx` | 12 KB |  | `paid` | 自有 |  |
| `chart.tsx` | 4 KB |  | `paid` | 自有 |  |
| `decor.tsx` | 7 KB |  | `paid` | 自有 |  |
| `fonts.tsx` | 5 KB |  | `paid` | 自有 |  |
| `guards.ts` | 2 KB |  | `paid` | 自有 |  |
| `index.ts` | 1 KB |  | `paid` | 自有 |  |
| `layers.tsx` | 10 KB |  | `paid` | 自有 |  |
| `motion.tsx` | 5 KB |  | `paid` | 自有 |  |
| `style-palettes.ts` | 12 KB |  | `paid` | 自有 |  |
| `text.tsx` | 13 KB |  | `paid` | 自有 |  |
| `theme.ts` | 3 KB |  | `paid` | 自有 |  |
| `timecode.ts` | 2 KB |  | `paid` | 自有 |  |

## 怎么用

- 拷进项目：`cp -r AssetLibrary/stacks/remotion/kit <项目>/kit`
- 组件里：`import {MainTitle, GrainOverlay, AnimatedCounter} from './kit'`
- 标题必须语义分行：`<MainTitle lines={["沈阳的产线", "不缺机器"]} />`（不要塞长句让它自己折）
- 数字要弹性：`easing={EASE_ELASTIC}`（过冲 1.25%）；别自己写贝塞尔，>2% 会抛错
- self-check：`python3 AssetLibrary/_tools/selftest_remotion_kit.py`
- 字体门：Root.tsx 最顶层包 `<FontGate specs={fontSpecsFromTheme()}>`（字体没加载完不渲染）
- import { STYLE_PALETTES, findPalette, CharacterRain, FlowingLines } from '<项目>/kit';

> ⚠️ `theme.ts` 是生成物；改色改字请改 `_tokens/brand-tokens.json` 再跑 `gen_tokens.py`。中文可变字体默认 200 极细 —— 每处显式 `font-weight:400` 起。

---
本文件由 `_tools/build_index.py` 生成。说明改 `_catalog.json`，清单从磁盘扫；**不要手改这里**，改完跑一次生成器。
