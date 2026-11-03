/**
 * chart.tsx —— 柱状图（spring 弹起 + 数字跟随）
 *
 * 清洗要点：颜色由调用方传（原版就这样，表扬），但**过一层禁色检查**；
 * 空数组 / maxValue<=0 直接 return null（原版已修，保留）。
 */
import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, SIZES, cssFamily } from "./theme";
import { assertBrandColor, requireArray, requireRange } from "./guards";

export type Bar = { readonly label: string; readonly value: number; readonly maxValue: number; readonly color?: string };

export const SBarChart: React.FC<{
  bars: readonly Bar[];
  width?: number;
  height?: number;
  barWidth?: number;
  barGap?: number;
  /** 每根柱之间的入场间隔（帧） */
  stagger?: number;
  fontSize?: number;
}> = ({ bars, width = SIZES.canvas.width - SIZES.marginX * 2, height = 420, barWidth, barGap = 36, stagger = 8, fontSize = SIZES.bodyMin }) => {
  const list = requireArray(bars, "bars");
  requireRange(height, "height", 80, SIZES.canvas.height);
  requireRange(fontSize, "fontSize", SIZES.bodyMin, 160);

  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const max = Math.max(...list.map((b) => b.maxValue));
  if (max <= 0) return null;

  // 柱宽默认**撑满可用宽**（旧版写死 96px，三根只占 43% 画面，s4 用起来像缩在中间）
  const n = list.length;
  const fill = barWidth ?? Math.floor((width - barGap * (n - 1)) / n);
  const usedRatio = (fill * n + barGap * (n - 1)) / width;
  if (usedRatio < SIZES.barMinWidthRatio) {
    throw new Error(
      `[kit] SBarChart 占宽 ${(usedRatio * 100).toFixed(0)}% < 下限 ${(SIZES.barMinWidthRatio * 100).toFixed(0)}%` +
        `（${n} 根 × ${fill}px + gap ${barGap}，可用宽 ${width}）—— 请去掉写死的 barWidth 或减少 gap`,
    );
  }

  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: barGap, width }}>
      {list.map((bar, i) => {
        const color = assertBrandColor(bar.color ?? COLORS.ink, `bars[${i}].color`);
        const sp = spring({
          frame: Math.max(0, frame - stagger * i),
          fps,
          config: { damping: 14, stiffness: 90 },
        });
        const h = interpolate(sp, [0, 1], [0, (bar.value / max) * height]);
        const shown = Math.round(interpolate(sp, [0, 1], [0, bar.value]));
        return (
          <div key={i} style={{ width: fill, display: "flex", flexDirection: "column" }}>
            {/* 柱区固定高：柱子从底往上长，数值标签永远贴在**自己柱子的顶端**（不再随列排版漂） */}
            <div style={{ height, display: "flex", alignItems: "flex-end" }}>
              <div style={{ position: "relative", width: "100%", height: h, backgroundColor: color, borderRadius: 4 }}>
                <div
                  style={{
                    position: "absolute",
                    left: 0,
                    right: 0,
                    bottom: "100%",
                    marginBottom: 10,
                    textAlign: "center",
                    fontSize,
                    color,
                    fontFamily: cssFamily("mono"),
                    fontWeight: 400,
                    fontVariantNumeric: "tabular-nums",
                  }}
                >
                  {shown}
                </div>
              </div>
            </div>
            <div
              style={{
                marginTop: 14,
                textAlign: "center",
                fontSize: SIZES.bodyMin,
                color: COLORS.paper,
                fontFamily: cssFamily("body"),
                fontWeight: 400,
              }}
            >
              {bar.label}
            </div>
          </div>
        );
      })}
    </div>
  );
};
