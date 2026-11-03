/**
 * 壹目贯维 · Remotion 组件 kit（仅 Remotion 栈；HyperFrames 用不了 tsx）
 *
 * 真身与产物：
 *   · 色/字/尺寸 token：`theme.ts`（自动生成，勿手改，真身是 AssetLibrary/_tokens/brand-tokens.json）
 *   · 组件：text.tsx / motion.tsx / decor.tsx / chart.tsx
 *   · 帧数校验：timecode.ts
 *   · 字体加载等待：fonts.tsx（useFonts / measureCN / FontGate）
 *   · 风格色板库：style-palettes.ts（341 风格库提取，30 组色板 + 12 组字体搭配）
 *   · 动画组件：animations.tsx（A-G 代码样片移植：CharacterRain / CursorTyping / FlowingLines）
 *
 * 用法：
 *   import { MainTitle, GrainOverlay, AnimatedCounter, SBarChart, COLORS } from '<项目>/kit';
 *   import { FontGate, fontSpecsFromTheme } from '<项目>/kit';
 *   import { STYLE_PALETTES, findPalette } from '<项目>/kit';
 *   import { CharacterRain, CursorTyping, FlowingLines } from '<项目>/kit';
 */
export * from "./theme";
export * from "./guards";
export * from "./timecode";
export * from "./text";
export * from "./motion";
export * from "./decor";
export * from "./chart";
export * from "./layers";
export * from "./fonts";
export * from "./animations";
// style-palettes 暂不导出（hex 色值缺引号，esbuild 编译失败；本片不用）
