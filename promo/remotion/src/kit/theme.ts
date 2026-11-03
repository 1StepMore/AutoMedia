// ─────────────────────────────────────────────────────────────
// 自动生成，勿手改 —— 真身：AssetLibrary/_tokens/brand-tokens.json
// 真身指纹：b8ef97c3b1e2d3a9（改了真身而不重生成，产物就对不上，门禁会红）
// 重生成：python3 AssetLibrary/_tools/gen_tokens.py
// ─────────────────────────────────────────────────────────────

export const COLORS = {
  "paper": "#F0EBDE",
  "paper2": "#E6E0CE",
  "ink": "#1F2BE0",
  "inkSoft": "#5560E5",
  "inkLight": "#8FA0FF",
  "inkDeep": "#0C0C0C",
  "grid": "rgba(31,43,224,0.10)",
  "inkFaint": "rgba(31,43,224,0.18)",
} as const;

export type ColorToken = keyof typeof COLORS;

export const COLOR_USAGE: Record<ColorToken, string> = {
  "paper": "浅底主色",
  "paper2": "浅底第二层",
  "ink": "钴蓝，唯一彩色，主强调",
  "inkSoft": "同族次亮",
  "inkLight": "深底上的标签/强调",
  "inkDeep": "深底场底 / 深色正文",
  "grid": "网格线",
  "inkFaint": "分隔线",
};

export const FORBIDDEN_COLORS: readonly string[] = ["#FFD700", "#06D6A0", "#8B7355", "#A7C7E7", "#4361EE"];

export const FONTS = {
  "title": {"stack": ["Newsreader", "Noto Serif SC", "serif"], "files": ["newsreader-400.woff2", "noto-serif-sc-vf-wght200-900.woff2"], "weightDefault": 400, "note": "中文可变字体 wght 200–900，默认落在 200（极细）—— 每处必须显式 font-weight:400 起"},
  "body": {"stack": ["Hanken Grotesk", "Noto Sans SC", "sans-serif"], "files": ["hanken-grotesk-400.woff2", "hanken-grotesk-600.woff2", "noto-sans-sc-vf-wght100-900.woff2"], "weightDefault": 400},
  "mono": {"stack": ["DM Mono", "monospace"], "files": ["dm-mono-400.woff2"], "weightDefault": 400},
} as const;

export const SIZES = {
  "canvas": {"width": 1080, "height": 1920},
  "authorCanvas": {"width": 2160, "height": 3840},
  "titleMin": 84,
  "bodyMin": 44,
  "marginX": 80,
  "marginY": 100,
  "firstTextTopMin": 300,
  "uiSafeBottomMax": 1700,
  "subtitleBottomMax": 1660,
  "titleTop": 320,
  "barMinWidthRatio": 0.7,
} as const;

export const MOTION = {
  "grainMaxAlpha": 0.08,
  "subtitleBurnInDefault": false,
  "note": "成片默认不烧字幕（主人 2026-10-21 定）；SubtitleCard 只作可选资产，bottom 默认 ≥300，且底边不得越过 subtitleBottomMax。 数字类动效：默认不过冲；弹性仅 opt-in，且过冲 ≤2%（实测三档贝塞尔峰值见 kit/motion.tsx 注释）。",
  "elasticMaxOvershoot": 0.02,
  "gradientIntensityMax": 0.6,
} as const;


/** 字体栈 → CSS font-family 值（中文优先，回落系统） */
export const cssFamily = (kind: keyof typeof FONTS): string =>
  FONTS[kind].stack
    .map((f) => (/\s/.test(f) ? `"${f}"` : f))
    .join(", ");

/** 取色；未知 token 直接抛错（宁可渲染前炸，也不要静默用错色） */
export const color = (token: ColorToken): string => {
  const c = COLORS[token];
  if (!c) throw new Error(`未知颜色 token: ${token}`);
  return c;
};
