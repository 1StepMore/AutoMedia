import React from "react";
import {
  AbsoluteFill,
  Img,
  OffthreadVideo,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
} from "remotion";

/**
 * layers.tsx —— 「影像层」：实拍 / 纹理 / 动态叠加
 *
 * 自包含设计（不 import kit 的 theme/guards）：这个文件要能被**整份拷进任意
 * Remotion 项目**而不带依赖，模板包与 kit 用的是同一份实现。
 * 品牌色默认值写死为 inkDeep #0C0C0C，调用方可覆盖。
 *
 * 为什么单独一层（2026-10-23 沈阳片复盘 P0-1）：
 *   纯色底 + 字 + 几何动效 = 信息图，不是片子。观众感到的「高级感」来自
 *   **信息密度 × 材质真实度 × 光影层次**，而 Remotion 侧此前只有第一条。
 *
 * 三条硬规矩：
 *   ① 实拍不「铺满 + 上面压字」——必须分区控光（一侧压暗给文字，一侧留亮给影像）
 *      + 缓慢单向推近（1.0 → ≤1.08），否则就是贴图感；
 *   ② overlays/*.webm 没有 alpha（VP9 透明通道实测丢失，解出来 alpha 恒 255），
 *      不许指望透明背景：发光型用 mix-blend-mode: screen，压暗型用 multiply；
 *   ③ 全部确定性：位移/漂移都由 frame 推导，禁 Math.random / Date.now。
 */

export type BlendMode = "screen" | "multiply" | "overlay" | "soft-light" | "normal";
type Side = "left" | "right" | "top" | "bottom";

const sideAngle: Record<Side, number> = { left: 90, right: 270, top: 180, bottom: 0 };

/** 品牌 inkDeep —— 影像层统一压暗色（与 kit theme.COLORS.inkDeep 同值，此处刻意不依赖） */
const DEFAULT_TINT = "#0C0C0C";
/** 颗粒透明度上限，与 kit theme.MOTION.grainMaxAlpha 同值：超过会吃掉文字对比度 */
const GRAIN_MAX_ALPHA = 0.08;

const requireRange = (value: number, name: string, min: number, max: number): number => {
  if (typeof value !== "number" || Number.isNaN(value) || value < min || value > max) {
    throw new Error(`[layers] 参数 ${name} 必须在 [${min}, ${max}]，收到 ${value}`);
  }
  return value;
};

/** 把 #06090F 这类 hex 转成 "6,9,15"（给 rgba 用） */
const rgb = (hex: string): string => {
  const h = hex.replace("#", "").trim();
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const n = parseInt(full, 16);
  if (Number.isNaN(n)) throw new Error(`[layers] 颜色格式不对：${hex}`);
  return `${(n >> 16) & 255},${(n >> 8) & 255},${n & 255}`;
};

/**
 * PhotoBackdrop —— 实拍底 + 分区控光 + 缓慢推近
 *
 * 用法（素材路径来自 assets.generated.ts，别手拼字符串）：
 *   <PhotoBackdrop src={find("sy-skyline-01.jpg")!.path} darkSide="left" pushTo={1.08} />
 */
export const PhotoBackdrop: React.FC<{
  /** public/ 下相对路径（assets.generated 的 .path） */
  src: string;
  /** 压暗哪一侧给文字留位置；默认 left */
  darkSide?: Side;
  /** 压暗端不透明度，默认 .9（对应 HF 的 linear-gradient(90deg, .90 → 0)） */
  darkAlpha?: number;
  /** 缓慢推近的终点倍率，默认 1.08；上限 1.12（再大就像抖动） */
  pushTo?: number;
  /** 整层不透明度（换场时可做淡入淡出），默认 1 */
  opacity?: number;
  /** object-position，默认 "50% 42%"（竖版裁 9:16 时用这个保住主体） */
  focus?: string;
  /** 景深虚化 px，默认 0；背景该「退后」时给 2–6 */
  blur?: number;
  /** 底部再压一道，保证页脚区不撞亮部；默认 0.55 */
  bottomFade?: number;
  /** 统一色相用的深底色，默认 brand inkDeep；实际只在压暗侧出现 */
  tint?: string;
  /** 是否保留一点色彩（默认 1 = 原色；影像线允许，信息层另由钴蓝承担） */
  saturation?: number;
}> = ({
  src,
  darkSide = "left",
  darkAlpha = 0.9,
  pushTo = 1.08,
  opacity = 1,
  focus = "50% 42%",
  blur = 0,
  bottomFade = 0.55,
  tint = DEFAULT_TINT,
  saturation = 1,
}) => {
  if (!src || typeof src !== "string") {
    throw new Error(`[layers] PhotoBackdrop 缺少 src（收到 ${JSON.stringify(src)}）`);
  }
  requireRange(darkAlpha, "darkAlpha", 0, 1);
  requireRange(pushTo, "pushTo", 1, 1.12);

  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  // 单向推近：全片一次，不来回（来回 = 呼吸灯，廉价）
  const scale = interpolate(frame, [0, durationInFrames], [1, pushTo], {
    extrapolateRight: "clamp",
  });
  const c = rgb(tint);
  const ang = sideAngle[darkSide];

  return (
    <AbsoluteFill style={{ opacity, overflow: "hidden", backgroundColor: tint }}>
      <Img
        src={staticFile(src)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          objectPosition: focus,
          transform: `scale(${scale})`,
          filter: `${blur > 0 ? `blur(${blur}px) ` : ""}saturate(${saturation})`,
        }}
      />
      {/* 分区控光：压暗一端 .90 → 0，文字永远落在暗侧 */}
      <AbsoluteFill
        style={{
          background: `linear-gradient(${ang}deg, rgba(${c},${darkAlpha}) 0%, rgba(${c},${
            darkAlpha * 0.45
          }) 42%, rgba(${c},0) 72%)`,
        }}
      />
      {/* 底部压暗：页脚/字幕区不撞亮部 */}
      {bottomFade > 0 && (
        <AbsoluteFill
          style={{
            background: `linear-gradient(0deg, rgba(${c},${bottomFade}) 0%, rgba(${c},0) 26%)`,
          }}
        />
      )}
    </AbsoluteFill>
  );
};

/**
 * TextureOverlay —— 品牌纹理（纸纤维 / 半调 / 网格 / 排线 / 暗角）
 *
 * 纹理自带 alpha 时用 normal 即可；不带 alpha 的（如纸纤维、grain-tile）必须给
 * blend，否则整屏被糊成一张图。
 */
export const TextureOverlay: React.FC<{
  src: string;
  blend?: BlendMode;
  opacity?: number;
  /** 平铺（grain-tile-512 这类小图必须 true；1080×1920 的纹理用 false） */
  repeat?: boolean;
  /** 每 100 帧漂移 px（让静止段也「活着」）；默认 0 */
  drift?: number;
  /** 缩放，默认 1；纸纤维这类可给 1.05 防止边缘露出 */
  scale?: number;
}> = ({ src, blend = "soft-light", opacity = 0.4, repeat = false, drift = 0, scale = 1 }) => {
  if (!src || typeof src !== "string") {
    throw new Error(`[layers] TextureOverlay 缺少 src（收到 ${JSON.stringify(src)}）`);
  }
  requireRange(opacity, "opacity", 0, 1);
  const frame = useCurrentFrame();
  const off = drift * (frame / 100);

  if (repeat) {
    return (
      <AbsoluteFill
        style={{
          backgroundImage: `url(${staticFile(src)})`,
          backgroundRepeat: "repeat",
          backgroundPosition: `${off}px ${off * 1.7}px`,
          mixBlendMode: blend === "normal" ? undefined : blend,
          opacity,
          pointerEvents: "none",
        }}
      />
    );
  }
  return (
    <AbsoluteFill style={{ overflow: "hidden", pointerEvents: "none", opacity }}>
      <Img
        src={staticFile(src)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `scale(${scale}) translate(${off}px, ${off * 0.6}px)`,
          mixBlendMode: blend === "normal" ? undefined : blend,
        }}
      />
    </AbsoluteFill>
  );
};

/**
 * VideoOverlay —— 动态叠加层（overlays/*.webm：颗粒 / 浮尘 / 光漏 / 扫线 / 烟雾 / 暗角）
 *
 * ⚠️ webm 没有 alpha（实测 alpha 恒 255，直接叠会糊一层黑）。
 *    发光型（dust/light-leak/bokeh/halation）→ screen
 *    压暗型（vignette/film-grain）→ multiply 或 overlay
 *
 * 放在场景之上、文字之下（文字要压在颗粒上还是下，取决于 readability 检查）。
 */
export const VideoOverlay: React.FC<{
  src: string;
  blend?: Extract<BlendMode, "screen" | "multiply" | "overlay" | "soft-light">;
  opacity?: number;
  /** 从视频第几帧开始取（默认 0；同一素材在不同场景错开可防「同一段循环」的雷同感） */
  startFrom?: number;
  /** 轻微漂移 px，默认 0 */
  drift?: number;
}> = ({ src, blend = "screen", opacity = 0.35, startFrom = 0, drift = 0 }) => {
  if (!src || typeof src !== "string") {
    throw new Error(`[layers] VideoOverlay 缺少 src（收到 ${JSON.stringify(src)}）`);
  }
  requireRange(opacity, "opacity", 0, 1);
  requireRange(startFrom, "startFrom", 0, 100000);
  const frame = useCurrentFrame();
  const off = drift * (frame / 100);

  return (
    <AbsoluteFill style={{ overflow: "hidden", pointerEvents: "none" }}>
      <OffthreadVideo
        src={staticFile(src)}
        muted
        startFrom={startFrom}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `translate(${off}px, ${off * 0.5}px) scale(1.02)`,
          mixBlendMode: blend,
          opacity,
        }}
      />
    </AbsoluteFill>
  );
};

/**
 * GrainLayer —— 整屏颗粒（静态平铺 + 逐帧位移，确定性）
 *
 * 与 PostFX 的噪点不同：这里用库里 512 平铺图（真实胶片颗粒扫描），
 * 比程序噪点更像「拍出来的」，且省一次 canvas 生成。
 * alpha 上限取 GRAIN_MAX_ALPHA（0.08，与品牌 grainMaxAlpha 同值），超过会把文字对比度吃掉。
 */
export const GrainLayer: React.FC<{ src: string; alpha?: number; speed?: number }> = ({
  src,
  alpha = 0.055,
  speed = 1,
}) => {
  if (!src) throw new Error(`[layers] GrainLayer 缺少 src`);
  requireRange(alpha, "alpha", 0, GRAIN_MAX_ALPHA);
  const frame = useCurrentFrame();
  const x = (frame * 7 * speed) % 512;
  const y = (frame * 13 * speed) % 512;
  return (
    <AbsoluteFill
      style={{
        backgroundImage: `url(${staticFile(src)})`,
        backgroundRepeat: "repeat",
        backgroundPosition: `${x}px ${y}px`,
        mixBlendMode: "soft-light",
        opacity: alpha,
        pointerEvents: "none",
      }}
    />
  );
};
