# 给 Agent 的使用说明（本资产包怎么消费）

你是要使用这套「内容 → 多平台视频」能力的 Agent。按下面顺序做：

## 1. 先判断要哪条线
- 要**轻量、无框架、确定性**（纯 HTML/JS，机器差也能跑）：用 `hyperframes/`。
- 要**高质量 motion、可组合新场景**（React/Remotion）：用 `remotion/`。
- 两条线产出同一个「同分镜/同旁白/同时长」的片；见 `两条线怎么选.md`。

## 2. 装依赖（不要假设环境已有）
- 公共：需要 `ffmpeg`、以及一个 chrome/chromium 可执行文件。
- hyperframes：`cd hyperframes && npm i`（装 puppeteer-core）。
- remotion：`cd remotion && npm i`（装 remotion 等）；Node 18+。
- 中文字体：装 Noto Sans SC（hyperframes 已自带 ttf；remotion 走系统字体，需自行确保）。

## 3. 需要问人类（end user）的点 —— 不要自己瞎猜
- chrome 可执行文件路径（`CHROME_PATH`）。
- 是否已装 Node/ffmpeg（没有就引导安装）。
- 旁白：用哪段文案、什么音色（本项目用 Azure TTS，见 `tts.md`）。

## 4. 跑完自检
- `ffprobe demo.mp4`：确认 30fps、1920×1080、时长 ≈ 52.22s、有 aac 音轨。
- 抽帧看：多场景、有素材、不是单张文字卡。
- 音画同步：翻到每个场景切点，旁白句子与画面切换应对齐。

## 5. 本包**不含**什么（别去找）
- 不含 node_modules、不含构建产物 frames/。
- 不含任何账号/密钥/凭据。
- 不含本机绝对路径（脚本用 `__dirname`/环境变量）。
