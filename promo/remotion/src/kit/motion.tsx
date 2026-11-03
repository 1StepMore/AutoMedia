/**
 * motion.tsx —— 数值与转场组件。
 *
 * 【数字滚动组件的二选一结论（有实测，2026-10-23）】
 * 两版同参数（0→100 / 0.8s / fps 30）各跑一遍数值轨迹：
 *   · animations.tsx 版（bezier 0.34,1.56,0.64,1）：峰值 **110**（过冲 +10）、回落 9 次（非单调）
 *   · effects-v9.tsx 版（bezier 0.16,1,0.3,1）  ：峰值 **100**、0 次回落（单调）
 * 主人裁定（2026-10-23）：**默认 standard 不过冲；弹性仅 opt-in 且过冲 ≤2%**。
 * 原话：「数字是事实，屏幕上闪 110 而事实是 100，就是错数字。」
 *
 * 两条防线：
 *   ① `easing` 默认 EASE_STANDARD（单调）；自定义曲线被 `assertMaxOvershoot` 采样校验，过冲 >2% 抛错。
 *      要弹性用 `EASE_ELASTIC`（控制点与 animations 同族，y1 1.56→1.20，实测峰值 1.0125 = 1.25%）。
 *   ② 显示值再 clamp 到 [start, end] —— 就算曲线过冲，屏幕上也不会出现比事实更大的数。
 */
import React from "react";
import { Easing, interpolate, useCurrentFrame } from "remotion";
import { clockWipe } from "@remotion/transitions/clock-wipe";
import { fade } from "@remotion/transitions/fade";
import { slide } from "@remotion/transitions/slide";
import { COLORS, MOTION, SIZES, cssFamily } from "./theme";
import { assertBrandColor, assertMaxOvershoot, requireRange } from "./guards";

/** 默认：单调、不过冲（峰值 1.0000） */
export const EASE_STANDARD = Easing.bezier(0.16, 1, 0.3, 1);
/** 弹性 opt-in：过冲 1.25%（≤2% 上限）。同族控制点，只把 y1 从 1.56 降到 1.20 */
export const EASE_ELASTIC = Easing.bezier(0.34, 1.2, 0.64, 1);

export const AnimatedCounter: React.FC<{
  end: number;
  start?: number;
  /** 延迟多少帧后开始 */
  delay?: number;
  /** 动画持续帧数 */
  duration?: number;
  /** 缓动曲线；默认 EASE_STANDARD（不过冲）。过冲 >2% 会抛错，弹性请用 EASE_ELASTIC */
  easing?: (input: number) => number;
  /** 小数位，默认 0（整数） */
  decimals?: number;
  prefix?: string;
  suffix?: string;
  fontSize?: number;
  color?: string;
}> = ({
  end,
  start = 0,
  delay = 0,
  duration = 24,
  easing = EASE_STANDARD,
  decimals = 0,
  prefix = "",
  suffix = "",
  fontSize = SIZES.titleMin,
  color = COLORS.paper,
}) => {
  requireRange(duration, "duration", 1, 600);
  requireRange(fontSize, "fontSize", SIZES.bodyMin, 240);
  assertBrandColor(color, "color");
  const curve = assertMaxOvershoot(easing, "counter.easing", MOTION.elasticMaxOvershoot);

  const frame = useCurrentFrame();
  const progress = Math.max(0, Math.min(1, (frame - delay) / duration));
  const eased = interpolate(progress, [0, 1], [0, 1], { easing: curve, extrapolateRight: "clamp" });
  // ② 数字永不超过事实值（过冲只改手感，不改数字）
  const lo = Math.min(start, end);
  const hi = Math.max(start, end);
  const raw = Math.min(hi, Math.max(lo, start + (end - start) * eased));
  const factor = 10 ** decimals;
  const shown = Math.round(raw * factor) / factor;

  if (frame < delay) return null;
  return (
    <span
      style={{
        fontSize,
        color,
        fontFamily: cssFamily("mono"),
        fontWeight: 400,
        fontVariantNumeric: "tabular-nums",
        letterSpacing: 1,
      }}
    >
      {prefix}
      {shown.toFixed(decimals)}
      {suffix}
    </span>
  );
};

/* ─── 转场 ──────────────────────────────────────────────────────────────────
 * 旧版的坑：注释写「第 4 个换成 clockWipe」但实际用 slide-from-top 占位，
 * 而函数返回 `any` —— 调用方永远不知道会拿到什么。现在：
 *   · 每种转场一个具名 key，类型由推断得出（无 any）
 *   · clockWipe **真实现了**（要传画布宽高），名字与行为一致
 *   · 需要新转场就往表里加一行，调用方按名字取
 */
export const transitions = {
  fade: () => fade(),
  "slide-left": () => slide({ direction: "from-left" }),
  "slide-right": () => slide({ direction: "from-right" }),
  "slide-top": () => slide({ direction: "from-top" }),
  "clock-wipe": () => clockWipe({ width: SIZES.canvas.width, height: SIZES.canvas.height }),
} as const;

export type TransitionName = keyof typeof transitions;

/** 按名字取转场（写死名字，拼错编译期就报） */
export const pickTransition = <T extends TransitionName>(name: T) => transitions[name]();

/** 按序号轮换（连续场次不重样）；序号超出自动取模，不再静默变成 fade */
export const pickTransitionByIndex = (index: number): ReturnType<(typeof transitions)["fade"]> => {
  const names = Object.keys(transitions) as TransitionName[];
  const key = names[((index % names.length) + names.length) % names.length];
  // 各 presentation 的泛型参数不同（slide 带 direction），统一按公共接口返回
  return transitions[key]() as ReturnType<(typeof transitions)["fade"]>;
};
