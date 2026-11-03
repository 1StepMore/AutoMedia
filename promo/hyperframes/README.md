# HyperFrames 线（确定性代码渲染）

**是什么**：一份 `compose.html`（纯 JS 的确定性 `render(t)` + `window.__seek(t)` + `window.__DUR`），用 puppeteer 逐帧截图，再用 ffmpeg 合成。**无 CDN、无框架依赖**，浏览器能开到就能跑。

## 跑
```bash
cd hyperframes
npm i
export CHROME_PATH=/path/to/chrome        # 本机 chrome / chromium 可执行文件，本包不附带
node render_frames.js                      # 生成 frames/f_00000.jpg ...
# 合成：
ffmpeg -y -framerate 30 -i frames/f_%05d.jpg -i narration_full.mp3 \
  -c:v libx264 -pix_fmt yuv420p -crf 20 -r 30 -c:a aac -b:a 160k -shortest demo-hyperframes.mp4
```

## 关键约定
- `compose.html` 顶部 `const DUR=52.22;` = 总时长（秒）；`window.__DUR` 暴露给渲染脚本；`window.__seek(t)` 把画面设到第 t 秒（确定性，逐帧可复现）。
- 字体：`@font-face` 引用同目录 `NotoSansSC-VF.ttf`（已附带，Noto Sans SC，OFL 许可）。换字体改 `compose.html` 第 4 行即可。
- 尺寸：1920×1080；帧率由 `FPS` 环境变量控制（默认 30）。
- 时间轴：见 `timeline.json`（6 段旁白 + 起止秒），compose.html 的场景切点与之一致 → 音画同步。

## 换内容怎么做
1. 改 `compose.html` 里的文案/配色/版式（都在 HTML+CSS 里）。
2. 文案变了就重算 `DUR` 与各场景起止（见 `../docs/时间轴-旁白分段对齐法.md`）。
3. 旁白：把 `narration_full.mp3` 换成新音频（长度要与 `DUR` 对齐）。
