/**
 * decor.tsx —— 装饰/质感层（渐变光带 / 颗粒 / 渐变背景 / 粒子）
 *
 * 清洗要点：
 *   · 旧 `SandGrain` 默认是暖棕色（会抢品牌主色相）⇒ 改名 **GrainOverlay**，
 *     只允许墨黑 / 纸白两种颗粒，alpha 上限 0.08（见 theme.ts 的 MOTION.grainMaxAlpha）
 *   · 旧 `AbstractGradientBackground` 用 `baseHue` 自由色相 ⇒ 第二色相违反品牌
 *     ⇒ 改成**只接受 token 名**的渐变（paper→paper2 或 inkDeep→ink）
 *   · 粒子沿用逐帧 sin/cos（禁 CSS keyframes，Remotion 里必错）
 */
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { COLORS, MOTION, SIZES, cssFamily, type ColorToken } from "./theme";
import { assertBrandColor, requireRange } from "./guards";

/* ─── 渐变光带（s2 过渡/分隔用）────────────────────────────────────────────── */
export const SVGGradientBand: React.FC<{
  width?: number;
  height?: number;
  rectHeight?: number;
  from?: string;
  to?: string;
}> = ({ width = SIZES.canvas.width - SIZES.marginX * 2, height = 24, rectHeight = 3, from = COLORS.ink, to = COLORS.inkLight }) => {
  assertBrandColor(from, "from");
  assertBrandColor(to, "to");
  const gid = React.useId().replace(/:/g, "");
  const frame = useCurrentFrame();
  const grow = interpolate(frame, [0, 20], [0, 1], { extrapolateRight: "clamp" });
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      <defs>
        <linearGradient id={gid} x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor={from} stopOpacity={0} />
          <stop offset="50%" stopColor={from} stopOpacity={0.85} />
          <stop offset="100%" stopColor={to} stopOpacity={0.9} />
        </linearGradient>
      </defs>
      <rect
        x={0}
        y={(height - rectHeight) / 2}
        width={width * grow}
        height={rectHeight}
        rx={rectHeight / 2}
        fill={`url(#${gid})`}
      />
    </svg>
  );
};

/* ─── 颗粒质感（原 SandGrain）───────────────────────────────────────────────
 * 确定性伪随机（同一 seed 每次重渲染完全一致）—— 视频里抖动必须可复现。
 */
const rand = (seed: number) => {
  const x = Math.sin(seed * 127.1 + 311.7) * 43758.5453123;
  return x - Math.floor(x);
};

export const GrainOverlay: React.FC<{
  count?: number;
  /** 只能 paper 或 inkDeep */
  tone?: ColorToken;
  /** 上限 MOTION.grainMaxAlpha（0.08） */
  alpha?: number;
  seed?: number;
}> = ({ count = 24, tone = "paper", alpha = MOTION.grainMaxAlpha, seed = 7 }) => {
  requireRange(count, "count", 0, 400);
  requireRange(alpha, "alpha", 0, MOTION.grainMaxAlpha);
  if (tone !== "paper" && tone !== "inkDeep") {
    throw new Error(`[kit] GrainOverlay.tone 只能 paper / inkDeep（收到 ${tone}）`);
  }
  if (count === 0) return null;
  return (
    <AbsoluteFill style={{ pointerEvents: "none", overflow: "hidden" }}>
      {Array.from({ length: count }, (_, i) => {
        const r = (k: number) => rand(seed * 1000 + i * 37 + k);
        const size = 2 + r(0) * 5;
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: `${r(1) * 100}%`,
              top: `${r(2) * 100}%`,
              width: size,
              height: size,
              borderRadius: "50%",
              backgroundColor: COLORS[tone],
              opacity: alpha * (0.4 + r(3) * 0.6),
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

/* ─── 渐变背景（只吃 token，不做自由色相）────────────────────────────────────
 * 旧版整屏线性渐变 inkDeep→ink，实测**高饱和像素占 98.6%** —— 背景把主色相吃干了，
 * 前景文字反而失去对比。现在：底是实色墨黑，只有一团**有限直径**的钴蓝光晕，
 * 强度受 MOTION.gradientIntensityMax(0.6) 上限约束（默认 0.45），高饱和面积 ≈ 35%。
 */
const withAlpha = (hex: string, alpha: number): string => {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${Number(alpha.toFixed(3))})`;
};

export const AbstractGradientBackground: React.FC<{
  /** 底色（默认墨黑） */
  from?: ColorToken;
  /** 光晕色（默认钴蓝） */
  to?: ColorToken;
  /** 光晕强度上限 MOTION.gradientIntensityMax；默认 0.45 */
  intensity?: number;
  children?: React.ReactNode;
}> = ({ from = "inkDeep", to = "ink", intensity = 0.45, children }) => {
  requireRange(intensity, "intensity", 0, MOTION.gradientIntensityMax);
  const frame = useCurrentFrame();
  const drift = interpolate(frame, [0, 300], [0, 6], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ backgroundColor: COLORS[from], pointerEvents: "none" }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at ${50 + drift}% 40%, ${withAlpha(COLORS[to], intensity)} 0%, ${withAlpha(
            COLORS[to],
            intensity * 0.35,
          )} 34%, ${withAlpha(COLORS[to], 0)} 58%)`,
        }}
      />
      {children}
    </AbsoluteFill>
  );
};

/* ─── 粒子（逐帧 sin/cos，禁 CSS 动画）────────────────────────────────────── */
export const ParticleBackground: React.FC<{
  count?: number;
  color?: string;
  seed?: number;
}> = ({ count = 12, color = COLORS.inkLight, seed = 3 }) => {
  requireRange(count, "count", 0, 120);
  assertBrandColor(color, "color");
  const frame = useCurrentFrame();
  if (count === 0) return null;
  return (
    <AbsoluteFill style={{ pointerEvents: "none", overflow: "hidden" }}>
      {Array.from({ length: count }, (_, i) => {
        const baseX = rand(seed + i) * 100;
        const baseY = rand(seed + i * 1.7) * 100;
        const speed = 0.012 + rand(seed + i * 2.3) * 0.014;
        const amplitude = 4 + rand(seed + i * 3.1) * 8;
        const x = Math.max(0, Math.min(100, baseX + Math.sin(frame * speed + i) * amplitude));
        const y = Math.max(0, Math.min(100, baseY + Math.cos(frame * speed * 0.7 + i) * amplitude));
        const twinkle = interpolate(Math.sin(frame * speed * 3 + i), [-1, 1], [0.35, 1]);
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: `${x}%`,
              top: `${y}%`,
              width: 3 + rand(seed + i * 4.7) * 3,
              height: 3 + rand(seed + i * 4.7) * 3,
              borderRadius: "50%",
              backgroundColor: color,
              opacity: 0.28 * twinkle,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

/* ─── 场内编号（等宽，压右下角）────────────────────────────────────────────── */
export const FrameIndex: React.FC<{ value: string }> = ({ value }) => (
  <div
    style={{
      position: "absolute",
      right: SIZES.marginX,
      bottom: SIZES.marginY,
      fontFamily: cssFamily("mono"),
      fontSize: 28,
      color: COLORS.inkFaint,
      letterSpacing: 2,
    }}
  >
    {value}
  </div>
);
