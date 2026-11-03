/**
 * text.tsx —— 文字类组件（字幕卡 / 段角标 / 标题 / 词级高亮 / 打字机）
 *
 * 全部改自归档工程的 `src/effects-v9.tsx`，清洗内容：
 *   · 色值 → 只用 `theme.ts` 的 COLORS token（旧版金/绿/棕/浅蓝/靛蓝全禁）
 *   · 字体 → 库里品牌字体，且**显式 400 起**（中文可变字体默认落在 200，会极细）
 *   · 尺寸 → 读 SIZES（主标题 ≥84 / 辅助 ≥44 / 首个文字 top ≥300）
 *   · 缺必填参数直接抛错，不静默降级
 *
 * ⚠️ 成片**默认不烧字幕**（2026-10-21 定）。`SubtitleCard` 只作可选资产：
 *    要用必须显式传 `bottom`（默认 320），且底边不得越过 SIZES.subtitleBottomMax。
 */
import React, { useLayoutEffect, useRef, useState } from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, SIZES, cssFamily } from "./theme";
import { requireArray, requireRange, requireText, assertBrandColor } from "./guards";

const EASE_OUT = (t: number) => 1 - Math.pow(1 - t, 3); // 单调、不过冲

/* ─── 字幕卡 ───────────────────────────────────────────────────────────── */
export type Sentence = { readonly text: string; readonly start: number; readonly duration: number };

export const SubtitleCard: React.FC<{
  sentences: readonly Sentence[];
  /** 距画布底边（px）。默认 320；底边 ≤1660 ⇒ bottom ≥260 */
  bottom?: number;
  fontSize?: number;
}> = ({ sentences, bottom = 320, fontSize = SIZES.bodyMin }) => {
  const list = requireArray(sentences, "sentences");
  requireRange(bottom, "bottom", SIZES.canvas.height - SIZES.subtitleBottomMax, 900);
  requireRange(fontSize, "fontSize", SIZES.bodyMin, 96);

  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const current = list.find((s) => frame >= s.start && frame < s.start + s.duration);
  if (!current) return null;

  const rel = frame - current.start;
  const pop = spring({ frame: rel, fps, config: { damping: 16, stiffness: 140 } });
  const enter = interpolate(rel, [0, 18], [0, 1], { extrapolateRight: "clamp", easing: EASE_OUT });
  const outStart = Math.max(10, Math.floor(current.duration * 0.85));
  const leave = interpolate(rel, [outStart, current.duration], [1, 0], { extrapolateRight: "clamp" });

  return (
    <div
      style={{
        position: "absolute",
        bottom,
        left: SIZES.marginX,
        right: SIZES.marginX,
        display: "flex",
        justifyContent: "center",
        opacity: Math.min(enter, leave),
        transform: `scale(${interpolate(pop, [0, 1], [0.94, 1])})`,
        zIndex: 25,
      }}
    >
      <div
        style={{
          background: "rgba(12,12,12,0.78)",
          backdropFilter: "blur(8px)",
          border: `1px solid ${COLORS.inkFaint}`,
          borderRadius: 12,
          padding: "16px 28px",
          maxWidth: "100%",
        }}
      >
        <span
          style={{
            fontSize,
            color: COLORS.paper,
            fontFamily: cssFamily("body"),
            fontWeight: 400,
            letterSpacing: 1,
            lineHeight: 1.4,
          }}
        >
          {current.text}
        </span>
      </div>
    </div>
  );
};

/* ─── 段角标「01/06 · 钩子」───────────────────────────────────────────────── */
export const SectionBadge: React.FC<{ index: number; total: number; label: string }> = ({
  index,
  total,
  label,
}) => {
  requireText(label, "label");
  requireRange(total, "total", 1, 99);
  requireRange(index, "index", 0, total - 1);
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 18], [0, 0.72], { extrapolateRight: "clamp" });
  const pad = String(total).length;
  return (
    <div
      style={{
        position: "absolute",
        top: SIZES.marginY,
        left: SIZES.marginX,
        zIndex: 23,
        fontSize: 34,
        color: COLORS.paper,
        fontFamily: cssFamily("mono"),
        fontWeight: 400,
        letterSpacing: 2,
        opacity,
      }}
    >
      {String(index + 1).padStart(pad, "0")}/{String(total).padStart(pad, "0")} · {label}
    </div>
  );
};

/* ─── 主标题（语义分行 lines[]，禁止词内断行）────────────────────────────────
 * 为什么不再吃单个字符串：旧版靠浏览器折行，实测把「不缺机器」切成「器 不缺机」——
 * 中文没有词边界，CSS 折行只认字宽。所以**行由调用方给**（语义分行），组件只负责：
 *   · 一行一个 div + `white-space: nowrap`（永不词内断）
 *   · 行太长时**在画面上打红框报 OVERFLOW**，不静默裁切也不偷偷缩字号
 * 默认 top = SIZES.titleTop(320)：旧值 296 压线，标题上沿会贴到安全区边缘。
 */
export const MainTitle: React.FC<{
  lines: readonly string[];
  fontSize?: number;
  color?: string;
  top?: number;
  letterSpacing?: number;
  lineHeight?: number;
}> = ({ lines, fontSize = 96, color = COLORS.paper, top = SIZES.titleTop, letterSpacing = 3, lineHeight = 1.15 }) => {
  const list = requireArray(lines, "lines").map((l, i) => requireText(l, `lines[${i}]`));
  requireRange(fontSize, "fontSize", SIZES.titleMin, 220);
  requireRange(top, "top", SIZES.firstTextTopMin, SIZES.uiSafeBottomMax);
  assertBrandColor(color, "color");

  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const pop = spring({ frame, fps, config: { damping: 14, stiffness: 90 } });
  const opacity = interpolate(frame, [0, 20], [0, 1], { extrapolateRight: "clamp", easing: EASE_OUT });
  const box = useRef<HTMLDivElement>(null);
  const [overflow, setOverflow] = useState(false);
  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    // ⚠️ 不能用 el.clientWidth：Remotion 首帧布局未就绪时它是 0，会把正常标题误判成溢出（实测踩过）。
    // 可用宽直接由 token 推出：画布宽 − 左右边距。
    const avail = SIZES.canvas.width - SIZES.marginX * 2;
    let widest = 0;
    Array.from(el.children).forEach((ch) => {
      const h = ch as HTMLElement;
      if (h.dataset.line !== undefined) widest = Math.max(widest, h.scrollWidth);
    });
    setOverflow(widest > avail + 1);
  }, [list.join("\u0000"), fontSize, letterSpacing]);
  return (
    <div
      ref={box}
      style={{
        position: "absolute",
        top,
        left: SIZES.marginX,
        right: SIZES.marginX,
        textAlign: "center",
        fontSize,
        color,
        fontFamily: cssFamily("title"),
        fontWeight: 400,
        letterSpacing,
        lineHeight,
        opacity,
        transform: `scale(${interpolate(pop, [0, 1], [0.92, 1])})`,
        zIndex: 22,
      }}
    >
      {list.map((line, i) => (
        <div key={i} data-line={i} style={{ whiteSpace: "nowrap" }}>
          {line}
        </div>
      ))}
      {overflow ? (
        <div
          style={{
            position: "absolute",
            inset: 0,
            border: "8px solid red",
            color: "red",
            fontFamily: cssFamily("mono"),
            fontSize: 34,
            lineHeight: 1.2,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          OVERFLOW · 该行太长，拆成两行
        </div>
      ) : null}
    </div>
  );
};

/* ─── 多行标题依次入场 ────────────────────────────────────────────────────── */
export const TitleStagger: React.FC<{
  lines: readonly { readonly text: string; readonly delay: number }[];
  fontSize?: number;
  color?: string;
  top?: number;
  letterSpacing?: number;
}> = ({ lines, fontSize = 92, color = COLORS.paper, top = SIZES.titleTop, letterSpacing = 3 }) => {
  const list = requireArray(lines, "lines");
  requireRange(fontSize, "fontSize", SIZES.titleMin, 220);
  requireRange(top, "top", SIZES.firstTextTopMin, SIZES.uiSafeBottomMax);
  assertBrandColor(color, "color");

  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <div style={{ position: "absolute", top, left: SIZES.marginX, right: SIZES.marginX, textAlign: "center", zIndex: 22 }}>
      {list.map((line, i) => {
        const rel = Math.max(0, frame - line.delay);
        const opacity = interpolate(rel, [0, 18], [0, 1], { extrapolateRight: "clamp", easing: EASE_OUT });
        const pop = spring({ frame: rel, fps, config: { damping: 14, stiffness: 100 } });
        return (
          <div
            key={i}
            style={{
              fontSize,
              color,
              fontFamily: cssFamily("title"),
              fontWeight: 400,
              letterSpacing,
              lineHeight: 1.15,
              whiteSpace: "nowrap",
              opacity,
              transform: `translateY(${interpolate(pop, [0, 1], [14, 0])}px)`,
            }}
          >
            {requireText(line?.text, `lines[${i}].text`)}
          </div>
        );
      })}
    </div>
  );
};

/* ─── 词级高亮（背景色从左往右铺开）────────────────────────────────────────
 * 出处声明：思路参考 remotion-dev/skills 里的 word-highlight 示例
 *   · 仓库 https://github.com/remotion-dev/skills  · 维护者 JonnyBurger（Remotion 作者）
 *   · 参考 commit 6c67adcd9cdbe6eb84d76342da89b225f9161cb2（2026-10-22）
 *   · 该仓库**未声明任何 LICENSE**（GitHub API license=null）⇒ 代码不可复制。
 *     所以本实现是 **clean-room 重写**：不用它的 scaleX 色块法，
 *     改用 background-size 百分比推进（实现不同，效果等价）。
 */
export const WordHighlight: React.FC<{
  text: string;
  highlight: string;
  delay?: number;
  duration?: number;
  highlightColor?: string;
  textColor?: string;
  fontSize?: number;
}> = ({
  text,
  highlight,
  delay = 0,
  duration = 18,
  highlightColor = COLORS.inkLight,
  textColor = COLORS.paper,
  fontSize = SIZES.bodyMin,
}) => {
  requireText(text, "text");
  requireText(highlight, "highlight");
  requireRange(fontSize, "fontSize", SIZES.bodyMin, 160);
  assertBrandColor(highlightColor, "highlightColor");
  assertBrandColor(textColor, "textColor");

  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const progress = spring({ fps, frame, config: { damping: 200 }, delay, durationInFrames: duration });
  const fill = Math.max(0, Math.min(1, progress)) * 100;
  const at = text.indexOf(highlight);

  const word = (
    <span
      style={{
        backgroundImage: `linear-gradient(${highlightColor}, ${highlightColor})`,
        backgroundRepeat: "no-repeat",
        backgroundSize: `${fill}% 100%`,
        backgroundPosition: "left center",
        color: at >= 0 ? COLORS.inkDeep : textColor,
        padding: "0 0.12em",
        borderRadius: "0.14em",
      }}
    >
      {highlight}
    </span>
  );

  return (
    <span style={{ fontSize, fontFamily: cssFamily("body"), fontWeight: 400, color: textColor, lineHeight: 1.5 }}>
      {at < 0 ? (
        <>
          {text}
          {/* 高亮词不在句子里时把词单独渲染在后面，避免"静默不高亮" */}
          {" "}
          {word}
        </>
      ) : (
        <>
          {text.slice(0, at)}
          {word}
          {text.slice(at + highlight.length)}
        </>
      )}
    </span>
  );
};

/* ─── 打字机 ────────────────────────────────────────────────────────────────
 * 出处声明：思路参考 remotion-dev/skills 的 typewriter 示例
 *   · 仓库 https://github.com/remotion-dev/skills  · 维护者 JonnyBurger（Remotion 作者）
 *   · 参考 commit 6c67adcd9cdbe6eb84d76342da89b225f9161cb2（2026-10-22）
 *   · 该仓库**未声明任何 LICENSE**（GitHub API license=null）⇒ 代码不可复制
 *   —— 本实现 clean-room 重写：字符切片 + 光标用 opacity 阶梯，不复制其代码。
 */
export const Typewriter: React.FC<{
  text: string;
  charsPerFrame?: number;
  cursorBlinkFrames?: number;
  fontSize?: number;
  color?: string;
}> = ({ text, charsPerFrame = 0.5, cursorBlinkFrames = 16, fontSize = SIZES.bodyMin, color = COLORS.paper }) => {
  requireText(text, "text");
  requireRange(charsPerFrame, "charsPerFrame", 0.05, 10);
  requireRange(fontSize, "fontSize", SIZES.bodyMin, 160);
  assertBrandColor(color, "color");

  const frame = useCurrentFrame();
  const shown = Math.min(text.length, Math.floor(frame * charsPerFrame));
  const cursorOn = Math.floor(frame / (cursorBlinkFrames / 2)) % 2 === 0;
  return (
    <span style={{ fontSize, color, fontFamily: cssFamily("mono"), fontWeight: 400, lineHeight: 1.5 }}>
      {text.slice(0, shown)}
      <span style={{ opacity: cursorOn ? 1 : 0, color: COLORS.inkLight }}>▌</span>
    </span>
  );
};
