// ─────────────────────────────────────────────────────────────
// animations.tsx — A-G 代码样片动画移植（341 风格库）
// 来源：341 种代码动画风格提示词 · UP主俯仰观照开源
// 原始参考：Canvas 2D → Remotion React TSX 移植
// 移植原则：保留动画逻辑和视觉规则，用 React DOM 替代 Canvas 绘图
// 确定性随机：复用 decor.tsx 的 rand(seed)，与原 _公共函数.js 的 rng(seed) 同算法
// ─────────────────────────────────────────────────────────────

import React, { useRef } from "react";
import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  Easing,
} from "remotion";
import { rand } from "./decor";

// ─────────────────────────────────────────────────────────────
// A1 · 字雨 (Character Rain)
// 原始：Canvas 2D 函数 S.A1，字从上方落下，触底堆积
// 移植：用 absolutely-positioned span 元素，按帧计算位置
// ─────────────────────────────────────────────────────────────

const CHARS_A1 = [
  "智", "能", "自", "动", "化", "流", "程", "数", "据", "算",
  "法", "模", "型", "训", "练", "推", "理", "映", "射", "函",
  "数", "闭", "包", "链", "表", "队", "列", "树", "图", "态",
];

interface DropA1 {
  txt: string;
  size: number;
  x: number;
  y: number;
  v: number;
}

interface PileA1 {
  txt: string;
  size: number;
  x: number;
  y: number;
}

/**
 * A1 字雨动画组件
 * @param seed 随机种子，相同种子每次渲染结果一致
 */
export const CharacterRain: React.FC<{ seed?: number }> = ({ seed = 42 }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const t = frame / fps;

  const stateRef = useRef<{
    drops: DropA1[];
    pile: PileA1[];
    r: () => number;
  } | null>(null);

  if (!stateRef.current) {
    const r = rand(seed);
    const base = Math.min(width, height) / 17;
    const drops: DropA1[] = [];
    for (let i = 0; i < 26; i++) {
      const k = [0.55, 0.7, 0.9, 1.2, 1.7][Math.floor(r() * 5)];
      drops.push({
        txt: CHARS_A1[Math.floor(r() * CHARS_A1.length)],
        size: base * k,
        x: r() * width * 0.92 - width * 0.04,
        y: -r() * height * 1.2,
        v: (height / 300) * (36 + base * k * 3.2),
      });
    }
    stateRef.current = { drops, pile: [], r };
  }

  const state = stateRef.current;
  const dt = Math.min(t - (stateRef.current.lastT ?? t), 0.05);
  state.lastT = t;

  const ground = height - 10 - Math.min(state.pile.length, 60) * height * 0.004;

  // 更新掉落物位置
  const updatedDrops = state.drops.map((d) => {
    const newY = d.y + d.v * dt;
    if (newY >= ground) {
      state.pile.push({
        txt: d.txt,
        size: d.size * 0.9,
        x: d.x,
        y: ground + state.r() * 8,
      });
      const k = [0.55, 0.7, 0.9, 1.2, 1.7][Math.floor(state.r() * 5)];
      return {
        txt: CHARS_A1[Math.floor(state.r() * CHARS_A1.length)],
        size: d.size,
        x: state.r() * width * 0.92 - width * 0.04,
        y: -d.size * 2,
        v: d.v,
      };
    }
    return { ...d, y: newY };
  });
  state.drops = updatedDrops;
  if (state.pile.length > 70) state.pile.splice(0, 8);

  const SERIF = "'Newsreader', 'Noto Serif SC', serif";

  return (
    <AbsoluteFill
      style={{
        background: `linear-gradient(to bottom, #0b0e15, #050608)`,
        fontFamily: SERIF,
      }}
    >
      {/* 堆积文字 */}
      {state.pile.map((p, i) => (
        <span
          key={`pile-${i}`}
          style={{
            position: "absolute",
            left: p.x,
            top: p.y,
            fontSize: p.size,
            color: `rgba(150, 164, 190, 0.32)`,
            userSelect: "none",
          }}
        >
          {p.txt}
        </span>
      ))}
      {/* 掉落文字 */}
      {state.drops.map((d, i) => (
        <span
          key={`drop-${i}`}
          style={{
            position: "absolute",
            left: d.x,
            top: d.y,
            fontSize: d.size,
            color: `rgba(214, 224, 242, ${0.25 + (d.size / (Math.min(width, height) / 17)) * 0.35})`,
            userSelect: "none",
          }}
        >
          {d.txt}
        </span>
      ))}
      {/* 底部光晕 */}
      <div
        style={{
          position: "absolute",
          left: `${width * 0.5 - 7}`,
          top: `${height - 14 - 7}`,
          width: 14,
          height: 14,
          borderRadius: "50%",
          background: `rgba(241, 178, 92, ${0.55 + 0.35 * (Math.sin(t * 5) > 0 ? 1 : 0.2)})`,
          boxShadow: `0 0 28px rgba(241, 178, 92, 0.6)`,
          filter: "blur(2px)",
        }}
      />
    </AbsoluteFill>
  );
};

// ─────────────────────────────────────────────────────────────
// A2 · 光标打字 (Cursor Typing)
// 原始：Canvas 2D 函数 S.A2，文字逐字打出，光标闪烁
// 移植：用 span 元素，按时间轴计算当前应显示的文字
// ─────────────────────────────────────────────────────────────

/**
 * A2 光标打字动画组件
 * @param text 要打出的文字
 * @param seed 随机种子（暂未使用，保留参数一致性）
 */
export const CursorTyping: React.FC<{
  text?: string;
  seed?: number;
}> = ({ text = "我其实一直想跟你说", seed = 42 }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const t = frame / fps;

  // 构建时间轴：打字 → 等待 → 删除 → 等待 → 打字 → ...
  const buildTimeline = () => {
    let tt = 0;
    let str = "";
    const st: { t: number; str: string }[] = [];
    const ops: [string, string | number][] = [
      ["type", text],
      ["wait", 1.1],
      ["del", 6],
      ["wait", 0.5],
      ["type", "没事。"],
      ["wait", 1.6],
      ["del", 3],
      ["wait", 0.4],
      ["type", "……"],
      ["wait", 1.6],
      ["clear", ""],
    ];
    for (const [k, v] of ops) {
      if (k === "type") {
        for (const ch of v as string) {
          tt += 0.17;
          str += ch;
          st.push({ t: tt, str });
        }
      } else if (k === "wait") {
        tt += v as number;
      } else if (k === "del") {
        for (let i = 0; i < v as number; i++) {
          tt += 0.07;
          str = str.slice(0, -1);
          st.push({ t: tt, str });
        }
      } else {
        tt += 0.4;
        str = "";
        st.push({ t: tt, str });
      }
    }
    return { timeline: st, len: tt + 0.8 };
  };

  const { timeline, len } = buildTimeline();
  const tm = t % len;

  // 找到当前帧对应的文字
  let i = 0;
  while (i + 1 < timeline.length && timeline[i + 1].t <= tm) i++;
  const currentStr = timeline[i].str;
  const since = tm - timeline[i].t;

  const fontSize = Math.min(width / 10.5, height / 7);
  const x0 = width * 0.1;
  const y0 = height * 0.5;
  const cursorOn = since < 0.45 || Math.floor(tm * 1.8) % 2 === 0;

  const SERIF = "'Newsreader', 'Noto Serif SC', serif";

  return (
    <AbsoluteFill
      style={{
        background: "#0b0b0c",
        fontFamily: SERIF,
      }}
    >
      <span
        style={{
          position: "absolute",
          left: x0,
          top: y0 - fontSize * 0.5,
          fontSize,
          fontWeight: 500,
          color: "#ece8df",
          whiteSpace: "nowrap",
          userSelect: "none",
        }}
      >
        {currentStr}
        {/* 光标 */}
        {cursorOn && (
          <span
            style={{
              display: "inline-block",
              width: Math.max(2, fontSize * 0.07),
              height: fontSize * 1.1,
              background: "#f1b25c",
              verticalAlign: "middle",
              marginLeft: fontSize * 0.12,
              boxShadow: `0 0 ${fontSize * 0.9} rgba(241, 178, 92, 0.18)`,
            }}
          />
        )}
      </span>
    </AbsoluteFill>
  );
};

// ─────────────────────────────────────────────────────────────
// B1 · 流动的丝线 (Flowing Silk Lines)
// 原始：Canvas 2D 函数 S.B1，多条正弦波叠加的丝线流动
// 移植：用 SVG path 绘制，每帧更新 d 属性
// ─────────────────────────────────────────────────────────────

/**
 * B1 流动丝线动画组件
 * @param seed 随机种子
 * @param lineCount 丝线数量（默认 6）
 * @param amplitude 振幅倍率（默认 1.0）
 */
export const FlowingLines: React.FC<{
  seed?: number;
  lineCount?: number;
  amplitude?: number;
}> = ({ seed = 42, lineCount = 6, amplitude = 1.0 }) => {
  const frame = useCurrentFrame();
  const { width, height, fps } = useVideoConfig();
  const t = frame / fps;

  const r = useRef(rand(seed));
  if (!r.current.lines) {
    r.current.lines = Array.from({ length: lineCount }, (_, i) => ({
      phase: r.current() * Math.PI * 2,
      freq: 0.5 + r.current() * 1.5,
      amp: (0.03 + r.current() * 0.08) * height * amplitude,
      offset: (i / lineCount) * height,
      hue: 200 + r.current() * 60,
    }));
  }

  const lines = r.current.lines;
  const colors = [
    "rgba(120, 160, 220, 0.6)",
    "rgba(180, 140, 220, 0.5)",
    "rgba(220, 180, 140, 0.5)",
    "rgba(140, 200, 180, 0.5)",
    "rgba(200, 160, 200, 0.4)",
    "rgba(160, 200, 220, 0.5)",
  ];

  return (
    <AbsoluteFill
      style={{
        background: "linear-gradient(to bottom, #1a1a2e, #0f0f1a)",
      }}
    >
      <svg
        width={width}
        height={height}
        style={{ position: "absolute", top: 0, left: 0 }}
      >
        {lines.map((line, i) => {
          const points: string[] = [];
          const steps = 60;
          for (let s = 0; s <= steps; s++) {
            const x = (s / steps) * width;
            const nx = s / steps;
            const y =
              line.offset +
              Math.sin(nx * Math.PI * line.freq + line.phase + t * 2) * line.amp +
              Math.sin(nx * Math.PI * line.freq * 2 + line.phase + t * 3) * line.amp * 0.3;
            points.push(`${x},${y}`);
          }
          return (
            <path
              key={i}
              d={`M ${points.join(" L ")}`}
              fill="none"
              stroke={colors[i % colors.length]}
              strokeWidth={1.5}
              strokeLinecap="round"
            />
          );
        })}
      </svg>
    </AbsoluteFill>
  );
};

// ─────────────────────────────────────────────────────────────
// 导出：按编号查找动画组件
// ─────────────────────────────────────────────────────────────

export const ANIMATIONS = {
  "A1": CharacterRain,
  "A2": CursorTyping,
  "B1": FlowingLines,
} as const;

export type AnimationId = keyof typeof ANIMATIONS;

/**
 * 按编号获取动画组件
 * @param id 动画编号（如 "A1", "A2", "B1"）
 */
export const getAnimation = (id: string) => {
  return ANIMATIONS[id as AnimationId] ?? null;
};
