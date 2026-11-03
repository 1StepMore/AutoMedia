# AutoMedia 视频资产包 · HyperFrames + Remotion 两线

> 交付对象：AutoMedia 项目（1StepMore/AutoMedia）的实现方 / coding agent。
> 目的：把「内容→多平台视频」的两条渲染线的**工作流、模板、运动语法、时间轴方法、复现脚本**一次性交齐。**不含本机环境**（node_modules/账号/绝对路径一律不带）。

## 目录
```
00-README.md                 ← 本文件
01-manifest.json             ← 文件清单 + md5（可校验）
02-verify.py                 ← 完整性校验（python3 02-verify.py，exit 0 即完整）
docs/                        ← 方法论文档（先读这个）
  ├─ 给Agent的使用说明.md      ← Agent 从这里开始
  ├─ 两条线怎么选.md
  ├─ 时间轴-旁白分段对齐法.md
  ├─ 运动语法-禁则.md
  └─ tts.md
hyperframes/                 ← 线1：纯 HTML+JS 确定性渲染（轻）
  ├─ compose.html            ← 真源（render(t)/__seek/__DUR）
  ├─ render_frames.js        ← puppeteer 逐帧（CHROME_PATH 环境变量）
  ├─ narration_full.mp3      ← 旁白（52.22s）
  ├─ timeline.json           ← 6 段旁白起止
  ├─ NotoSansSC-VF.ttf       ← 字体（OFL）
  └─ README.md
remotion/                    ← 线2：React+Remotion（高质量，首选）
  ├─ src/DemoFilm18.tsx      ← 完整 demo 组合（6 场）
  ├─ src/kit/                ← 自建动效库（theme/text/layers/animations…）
  ├─ src/index.ts, Root.tsx  ← 入口（已精简只注册 DemoFilm18）
  ├─ public/narration_full.mp3
  ├─ package.json, tsconfig.json, remotion.config.js
  └─ README.md
reference/                   ← 目标成片（对照「什么算合格」）
```

## 先做什么
1. 读 `docs/给Agent的使用说明.md`（含「哪些要问人类」）。
2. 校验完整性：`python3 02-verify.py`。
3. 选线（`docs/两条线怎么选.md`）→ 按对应 README 跑一遍，对照 `reference/` 看成片。

## 这两条线在本项目里的定位
- 是 **AutoMedia 视频能力的产品化参考实现**：真正的产品化要把它接进 `src/automedia/engines/`（见仓库 issue #351 视频引擎）。
- 本包只是「可跑、可改、可对照」的资产，不是最终产品集成。
