// HyperFrames 线：逐帧渲染（puppeteer-core）。不依赖任何本机绝对路径。
// 用法: npm i && CHROME_PATH=/path/to/chrome node render_frames.js
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');
const WORK = __dirname;
const CHROME = process.env.CHROME_PATH;
const FPS = Number(process.env.FPS || 30);
const OUT = process.env.FRAMES_DIR || path.join(WORK, 'frames');
(async () => {
  if (!CHROME || !fs.existsSync(CHROME)) {
    console.error('[X] 请设置 CHROME_PATH 环境变量，指向 chromium/chrome 可执行文件（本包不附带浏览器）');
    process.exit(2);
  }
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await puppeteer.launch({
    headless: 'new', executablePath: CHROME,
    args: ['--no-sandbox','--disable-dev-shm-usage','--disable-gpu','--font-render-hinting=none','--hide-scrollbars'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });
  await page.goto('file://' + path.join(WORK, 'compose.html'), { waitUntil: 'load' });
  await page.waitForFunction('window.__DUR!==undefined', { timeout: 15000 });
  await page.evaluate(() => document.fonts.ready);
  const DUR = await page.evaluate(() => window.__DUR);
  const N = Math.round(DUR * FPS);
  for (let i = 0; i < N; i++) {
    await page.evaluate((t) => window.__seek(t), i / FPS);
    await page.screenshot({ path: path.join(OUT, `f_${String(i).padStart(5,'0')}.jpg`), type: 'jpeg', quality: 90 });
  }
  console.log(`DONE frames=${N} DUR=${DUR} FPS=${FPS}`);
  await browser.close();
})().catch((e) => { console.error('ERR', e && e.message); process.exit(1); });
