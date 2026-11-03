/**
 * fonts.ts —— 字体加载等待 + 中文文本测量 + FontGate 组件
 *
 * 从 fy-code-animation/implementations/remotion-kit/fonts.ts 适配（2026-10-31）。
 * 原作者：Akillll-DuoHe/fy-code-animation（MIT）。
 *
 * 为什么需要：kit 的 theme.ts 定义了 woff2 字体文件，但没有等待加载的机制。
 * 字体没加载完就开始渲染 → 三种静默错误：
 *   1. 字形回退到系统字体（标题突然变细/变粗，观感不一致）
 *   2. 中文可变字体默认落在 wght=200（极细），每处必须显式 400
 *   3. 文字测量不准 → 字幕卡内容溢出/被截
 *
 * 用法（Root.tsx 或 Promo.tsx 最顶层）：
 * ```tsx
 * import { FontGate, fontSpecsFromTheme } from './kit';
 *
 * <FontGate specs={fontSpecsFromTheme()}>
 *   <Promo />
 * </FontGate>
 * ```
 */

import React, { useEffect, useState } from "react";
import { cancelRender, continueRender, delayRender, staticFile } from "remotion";
import { FONTS } from "./theme";

export type FontSpec = {
  family: string;
  file: string;
  weight?: string;
  style?: string;
};

const loads = new Map<string, Promise<void>>();
const gates = new Map<string, { promise: Promise<void>; ready: boolean }>();

function loadFont(spec: FontSpec): Promise<void> {
  const key = JSON.stringify(spec);
  let promise = loads.get(key);
  if (!promise) {
    promise = (async () => {
      const face = new FontFace(
        spec.family,
        `url(${JSON.stringify(staticFile(spec.file))})`,
        { weight: spec.weight ?? "400", style: spec.style ?? "normal" }
      );
      document.fonts.add(await face.load());
      await document.fonts.ready;
    })();
    loads.set(key, promise);
    promise.catch(() => loads.delete(key));
  }
  return promise;
}

/**
 * 等待字体加载完成。挂载一次后不要改 manifest（改了必须 remount）。
 * 返回 true 表示字体已就绪。
 *
 * 原理：delayRender 告诉 Remotion "我还没准备好，别超时"；
 * 字体加载完后 continueRender 放行。
 */
export function useFonts(specs: FontSpec[]): boolean {
  const signature = JSON.stringify(specs);
  const [initial] = useState(() => signature);
  if (initial !== signature) {
    throw new Error(
      "Font manifest changed: remount the font gate with a new key"
    );
  }

  let entry = gates.get(signature);
  if (!entry) {
    const handle = delayRender("local font files");
    const gate = { ready: false, promise: Promise.resolve() };
    gate.promise = Promise.all(specs.map(loadFont))
      .then(() => {
        gate.ready = true;
        continueRender(handle);
      })
      .catch((error: unknown) => {
        cancelRender(error instanceof Error ? error : new Error(String(error)));
      });
    gates.set(signature, gate);
    entry = gate;
  }

  const gate = entry;
  const [ready, setReady] = useState(gate.ready);
  useEffect(() => {
    let active = true;
    gate.promise.then(() => {
      if (active && gate.ready) setReady(true);
    });
    return () => {
      active = false;
    };
  }, [gate]);
  return ready;
}

/**
 * 测量文本宽度（需要浏览器环境）。
 * 注意：只测布局宽度，不验证 cmap 覆盖或可变字体轴。
 */
export function measureCN(text: string, font: string): number {
  if (typeof document === "undefined") {
    throw new Error("font measurement requires browser");
  }
  if (!document.fonts.check(font, text)) {
    throw new Error("font is not ready");
  }
  const ctx = document.createElement("canvas").getContext("2d");
  if (!ctx) throw new Error("Canvas 2D unavailable");
  ctx.font = font;
  return ctx.measureText(text).width;
}

/**
 * 便捷组件：字体加载完成前返回 null（delayRender 保持进程不退出）。
 *
 * 用法：
 * ```tsx
 * <FontGate specs={fontSpecsFromTheme()}>
 *   <Promo />
 * </FontGate>
 * ```
 */
export const FontGate: React.FC<{
  specs: FontSpec[];
  children: React.ReactNode;
}> = ({ specs, children }) => {
  const ready = useFonts(specs);
  if (!ready) return null;
  return <>{children}</>;
};

/**
 * 从 kit 的 FONTS 定义生成 FontSpec 列表。
 *
 * 原理：权重从文件名提取（-400 / -600 / -700），可变字体默认 400。
 * 字体族从文件名前缀推断（newsreader→Newsreader，noto-serif-sc→Noto Serif SC 等）。
 *
 * 注意：FONTS 的 stack 是 CSS fallback 链，不是 1:1 映射到 files。
 * 例如 body 的 stack = ["Hanken Grotesk", "Noto Sans SC", "sans-serif"]，
 * 但 files = ["hanken-grotesk-400.woff2", "hanken-grotesk-600.woff2", "noto-sans-sc-vf-wght100-900.woff2"]
 * → 前两个文件都是 Hanken Grotesk（不同字重），第三个是 Noto Sans SC。
 */
export function fontSpecsFromTheme(): FontSpec[] {
  const parse = (file: string): { family: string; weight: string } => {
    let weight = "400";
    const wm = file.match(/-(\d{3})\.woff2$/);
    if (wm) weight = wm[1];

    let family = "sans-serif";
    if (file.includes("newsreader")) family = "Newsreader";
    else if (file.includes("noto-serif-sc")) family = "Noto Serif SC";
    else if (file.includes("noto-sans-sc")) family = "Noto Sans SC";
    else if (file.includes("hanken-grotesk")) family = "Hanken Grotesk";
    else if (file.includes("dm-mono")) family = "DM Mono";

    return { family, weight };
  };

  const specs: FontSpec[] = [];
  for (const def of Object.values(FONTS)) {
    for (const file of def.files) {
      const { family, weight } = parse(file);
      specs.push({ family, file, weight });
    }
  }
  return specs;
}
