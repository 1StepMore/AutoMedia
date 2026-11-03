/**
 * guards.ts —— 组件入参守卫（缺参数宁可渲染前炸，别静默降级成空画面）。
 *
 * 为什么单独一层：Remotion 里 `props.x` 缺失时多半是 `undefined` 进到 style，
 * 画面只是"看起来有点怪"，排查要花十几分钟；抛错能一次性定位到调用点。
 */
import { FORBIDDEN_COLORS } from "./theme";

export function requireText(value: string | undefined, name: string): string {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`[kit] 缺少必填文本参数 \`${name}\`（收到 ${JSON.stringify(value)}）`);
  }
  return value;
}

export function requireArray<T>(value: readonly T[] | undefined, name: string): readonly T[] {
  if (!Array.isArray(value) || value.length === 0) {
    throw new Error(`[kit] 缺少必填数组参数 \`${name}\`（不能为空）`);
  }
  return value;
}

export function requireRange(value: number | undefined, name: string, min: number, max: number): number {
  if (typeof value !== "number" || Number.isNaN(value)) {
    throw new Error(`[kit] 参数 \`${name}\` 必须是数字（收到 ${JSON.stringify(value)}）`);
  }
  if (value < min || value > max) {
    throw new Error(`[kit] 参数 \`${name}\` 超出允许范围 [${min}, ${max}]（收到 ${value}）`);
  }
  return value;
}

/** 采样缓动曲线峰值，超限即抛 —— 数字类组件绝不允许显示"比事实更大"的值 */
export const assertMaxOvershoot = (
  easing: (input: number) => number,
  name: string,
  maxOvershoot: number,
): ((input: number) => number) => {
  let peak = 0;
  for (let i = 0; i <= 500; i += 1) peak = Math.max(peak, easing(i / 500));
  const over = peak - 1;
  if (over > maxOvershoot + 1e-9) {
    throw new Error(
      `[kit] ${name} 过冲 ${(over * 100).toFixed(2)}% > 上限 ${(maxOvershoot * 100).toFixed(2)}%：` +
        "数字会短暂显示错误值。要弹性请用 EASE_ELASTIC（实测过冲 1.25%）。",
    );
  }
  return easing;
};

/** 禁色检查：品牌只允许纸白/墨黑/钴蓝同族，第二色相一律拦在渲染前。 */
export function assertBrandColor(value: string, name = "color"): string {
  const v = value.trim().toLowerCase();
  const hit = FORBIDDEN_COLORS.find((c) => c.toLowerCase() === v);
  if (hit) {
    throw new Error(
      `[kit] \`${name}\` 用了禁色 ${value} —— 品牌禁用金/绿/棕/浅蓝/靛蓝，请改用 COLORS.* token`
    );
  }
  return value;
}
