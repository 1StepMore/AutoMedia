// @ts-check
const { Config } = require("@remotion/cli/config");

// browserExecutable 留空 => Remotion 用自带的 Chrome Headless Shell（自动下载、版本匹配）
// 原先硬编码了本机浏览器路径（已移除），改用 Remotion 自带 Chromium
Config.setBrowserExecutable(null);
Config.setPixelFormat("yuv420p");
Config.setCodec("h264");
Config.setConcurrency(4);

// 2026-10-22: 移除 overrideWebpackConfig 的 node polyfill fallback。
// 原配置把 path/url/process/buffer 指向浏览器 polyfill，但 Remotion 4 已内置处理，
// 且该 fallback 会让 webpack 去解析不存在的 fs.cjs 而整条构建失败。
// src/ 下无任何 Node API 引用（已搜确认），故直接使用 Remotion 默认 webpack 配置。
