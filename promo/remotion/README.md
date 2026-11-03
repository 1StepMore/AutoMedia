# Remotion 线

**是什么**：React + Remotion 4 组合化出片。`src/DemoFilm18.tsx` 是「1篇→3平台」完整 demo（6 场；速度匹配横移接缝 + 镜头推近 + 压印字效 + SVG 颗粒 + 分镜表高亮，声画对齐 52.22s）。`src/kit/` 是自建动效库（主题令牌 / 文字组件 / 图层 / 动画 / 装饰），可复用为新场景。

## 跑
```bash
cd remotion
npm i
npm run studio          # 可视化预览（Remotion Studio）
npm run render          # 出片 -> out/demo.mp4
```
- Node 需 18+。Remotion 会**自动下载匹配版本的 Chrome Headless Shell**（`remotion.config.js` 里 `setBrowserExecutable(null)` 即此意）；若要用本机 chrome，改成绝对路径即可。
- 中文字体：Remotion 走系统 fontconfig；**确保环境装有 Noto Sans SC / Noto Serif SC**（否则中文可能缺字）。`src/kit/fonts.tsx` 有加载工具。

## 关键约定
- `DemoFilm18.tsx` 用 `<Series>` 串 6 场，每场时长 = 旁白分段时长×30fps（235/292/341/173/288/238 帧，合计 1567）→ 音画同步。
- 音频 `public/narration_full.mp3`，用 `staticFile()` 读取。
- ⚠️ JSX 文本里**不能出现裸 `>`**（esbuild 直接报错）；emoji 在 chromium 可能缺字，本 demo 不用 emoji。
- 运动语法与禁则见 `../docs/运动语法-禁则.md`（务必遵守，否则出片会「廉价」）。

## 换内容怎么做
1. 改 `DemoFilm18.tsx` 各场文案/图形；新增场景照抄现有场的 `Shell + stamp + Foot` 结构。
2. 时长变了改 `<Series.Sequence durationInFrames>` 与 `Root.tsx` 的 `durationInFrames`。
3. 换旁白换 `public/narration_full.mp3`，并按新分段改各场时长。
