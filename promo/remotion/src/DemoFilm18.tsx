import React from "react";
import {
  AbsoluteFill,
  Audio,
  Series,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  Easing,
  spring,
} from "remotion";

/* ── tokens（与 kit 同源：钴蓝唯一强调色 / 纸色 / 发丝网格） ── */
const T = {
  deep: "#08090D",
  paper: "#F0EBDE",
  ink: "#1F2BE0",
  inkBright: "#5D6DFF",
  soft: "rgba(240,235,222,0.62)",
  dim: "rgba(240,235,222,0.30)",
  hair: "rgba(240,235,222,0.10)",
  serif: '"Noto Serif SC", serif',
  sans: '"Noto Sans SC", sans-serif',
  W: 1920,
  H: 1080,
  padX: 150,
  footY: 72,
};
const EASE_IN = Easing.bezier(0.4, 0, 1, 1);
const EASE_OUT = Easing.bezier(0.16, 1, 0.3, 1);
const SEAM = 18; // 帧：速度匹配接缝

const R = (f: number, a: number, b: number, ea: any = EASE_OUT) =>
  interpolate(f, [a, b], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ea });

/* 压印字效：缩放 + 模糊 + 字距收拢（全片文字统一语法） */
const stamp = (f: number, a: number, b: number) => {
  const p = R(f, a, b, Easing.bezier(0.2, 0, 0.15, 1));
  return { p, scale: 1 + (1 - p) * 0.16, blur: (1 - p) * 4, ls: (1 - p) * 0.16 };
};

/* 场景外壳：镜头推近 + 横移接缝（禁 crossfade / 禁静止后切 / 禁从静止入场） */
const Shell: React.FC<{ dur: number; noExit?: boolean; children: React.ReactNode }> = ({
  dur,
  noExit,
  children,
}) => {
  const f = useCurrentFrame();
  const enter = R(f, 0, SEAM, EASE_OUT);
  const outP = noExit ? 0 : R(f, dur - SEAM, dur, EASE_IN);
  const x = (1 - enter) * 220 - outP * (T.W + 220);
  const cam = interpolate(f, [0, dur], [1.0, 1.04], { extrapolateRight: "clamp", easing: Easing.inOut(Easing.cubic) });
  return (
    <AbsoluteFill style={{ backgroundColor: T.deep, overflow: "hidden" }}>
      <div style={{ position: "absolute", inset: 0, transform: `scale(${cam})` }}>
        <div style={{ position: "absolute", inset: 0, transform: `translateX(${x}px)` }}>{children}</div>
      </div>
    </AbsoluteFill>
  );
};

/* 发丝网格 */
const HairGrid: React.FC<{ op?: number }> = ({ op = 0.35 }) => (
  <div style={{ position: "absolute", inset: 0, display: "flex", opacity: op }}>
    {Array.from({ length: 13 }).map((_, i) => (
      <i key={i} style={{ flex: 1, borderRight: i < 12 ? `1px solid ${T.hair}` : "none" }} />
    ))}
  </div>
);

/* 片脚：品牌 + 编号 */
const Foot: React.FC<{ idx: number; total: number; op: number }> = ({ idx, total, op }) => (
  <div
    style={{
      position: "absolute",
      bottom: T.footY,
      left: T.padX,
      right: T.padX,
      display: "flex",
      justifyContent: "space-between",
      alignItems: "baseline",
      borderTop: `1px solid ${T.hair}`,
      paddingTop: 22,
      fontFamily: T.sans,
      fontSize: 22,
      color: T.dim,
      letterSpacing: "0.16em",
      opacity: op,
    }}
  >
    <span style={{ color: T.soft, fontWeight: 500 }}>壹目贯维 · 内容自动化</span>
    <span>
      {String(idx).padStart(2, "0")} / {String(total).padStart(2, "0")}
    </span>
  </div>
);

/* ═══════════════ S1 片头 ═══════════════ */
const S1: React.FC<{ dur: number }> = ({ dur }) => {
  const f = useCurrentFrame();
  const kick = stamp(f, 6, 26);
  const one = stamp(f, 20, 46);
  const arrow = R(f, 44, 78, Easing.inOut(Easing.cubic));
  const three = stamp(f, 70, 98);
  const foot = R(f, 40, 66);
  return (
    <Shell dur={dur} noExit>
      <HairGrid />
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center" }}>
        <div style={{ fontFamily: T.sans, fontSize: 30, letterSpacing: "0.5em", color: T.inkBright, opacity: kick.p, transform: `translateY(${(1 - kick.p) * 16}px)` }}>
          内容自动化 · 演示
        </div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 40, marginTop: 40 }}>
          <div style={{ textAlign: "center", opacity: one.p, transform: `scale(${one.scale})`, filter: one.blur > 0.05 ? `blur(${one.blur}px)` : undefined }}>
            <div style={{ fontFamily: T.serif, fontSize: 300, fontWeight: 900, lineHeight: 0.9, color: T.paper, letterSpacing: `${one.ls}em` }}>1</div>
            <div style={{ fontFamily: T.sans, fontSize: 34, color: T.soft, marginTop: 8, letterSpacing: "0.2em" }}>篇原文</div>
          </div>
          <div style={{ width: 220, height: 3, background: T.hair, position: "relative", transform: `scaleX(${arrow})`, transformOrigin: "left center" }}>
            <div style={{ position: "absolute", right: -3, top: -7, width: 17, height: 17, borderTop: `3px solid ${T.inkBright}`, borderRight: `3px solid ${T.inkBright}`, transform: "rotate(45deg)", opacity: arrow }} />
          </div>
          <div style={{ textAlign: "center", opacity: three.p, transform: `scale(${three.scale})`, filter: three.blur > 0.05 ? `blur(${three.blur}px)` : undefined }}>
            <div style={{ fontFamily: T.serif, fontSize: 300, fontWeight: 900, lineHeight: 0.9, color: T.inkBright, letterSpacing: `${three.ls}em` }}>3</div>
            <div style={{ fontFamily: T.sans, fontSize: 34, color: T.soft, marginTop: 8, letterSpacing: "0.2em" }}>个平台</div>
          </div>
        </div>
        <div style={{ marginTop: 54, fontFamily: T.sans, fontSize: 40, color: T.paper, opacity: R(f, 96, 124) }}>
          同一篇稿，一次生产，三处复用
        </div>
      </div>
      <Foot idx={1} total={6} op={foot} />
    </Shell>
  );
};

/* ═══════════════ S2 输入·一篇原文 ═══════════════ */
const S2: React.FC<{ dur: number }> = ({ dur }) => {
  const f = useCurrentFrame();
  const cardIn = R(f, 6, 40, Easing.bezier(0.25, 0.1, 0.4, 1));
  const sway = Math.sin(cardIn * Math.PI * 2.2) * 14 * (1 - cardIn * 0.7);
  const title = stamp(f, 30, 58);
  const b1 = stamp(f, 62, 84);
  const b2 = stamp(f, 100, 122);
  const b3 = stamp(f, 138, 160);
  const note = R(f, 180, 206);
  const bullet = (p: number, txt: string) => (
    <div style={{ display: "flex", alignItems: "center", gap: 22, marginTop: 26, opacity: p, transform: `translateX(${(1 - p) * -40}px)` }}>
      <span style={{ width: 18, height: 18, background: T.inkBright, flex: "none", transform: "rotate(45deg)" }} />
      <span style={{ fontFamily: T.sans, fontSize: 46, fontWeight: 700, color: T.paper }}>{txt}</span>
    </div>
  );
  return (
    <Shell dur={dur}>
      <HairGrid />
      <div style={{ position: "absolute", inset: 0, padding: `120px ${T.padX}px`, display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <div style={{ fontFamily: T.sans, fontSize: 30, letterSpacing: "0.4em", color: T.inkBright, marginBottom: 26 }}>① 输入 · 一篇原文</div>
        <div
          style={{
            background: "linear-gradient(155deg, rgba(240,235,222,0.10) 0%, rgba(240,235,222,0.04) 60%, rgba(240,235,222,0.02) 100%)",
            border: "1px solid rgba(255,255,255,0.14)",
            borderRadius: 6,
            boxShadow: "0 30px 70px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.12)",
            padding: "54px 64px",
            opacity: cardIn,
            transform: `translateY(${(1 - cardIn) * 120}px) rotate(${sway * 0.06}deg)`,
          }}
        >
          <div style={{ fontFamily: T.serif, fontSize: 84, fontWeight: 900, color: T.paper, opacity: title.p, transform: `scale(${title.scale})`, filter: title.blur > 0.05 ? `blur(${title.blur}px)` : undefined, transformOrigin: "left center", letterSpacing: `${title.ls}em` }}>
            中小企业做内容营销，为什么越做越累？
          </div>
          {bullet(b1.p, "迷信爆款 —— 每条都想涨粉十万")}
          {bullet(b2.p, "迷信日更 —— 发得越多，质量越塌")}
          {bullet(b3.p, "全靠一个人 —— 人一走，账号断更")}
          <div style={{ marginTop: 36, fontFamily: T.sans, fontSize: 34, color: T.inkBright, opacity: note }}>问题不在做得少，在每条都从零硬写。</div>
        </div>
      </div>
      <Foot idx={2} total={6} op={1} />
    </Shell>
  );
};

/* ═══════════════ S3 输出·小红书 ═══════════════ */
const S3: React.FC<{ dur: number }> = ({ dur }) => {
  const f = useCurrentFrame();
  const phoneIn = R(f, 6, 44, Easing.bezier(0.25, 0.1, 0.4, 1));
  const t1 = stamp(f, 34, 60);
  const l1 = stamp(f, 66, 88);
  const l2 = stamp(f, 96, 118);
  const l3 = stamp(f, 126, 148);
  const tags = R(f, 160, 188);
  const pl = (p: number, txt: string) => (
    <div style={{ fontFamily: T.sans, fontSize: 31, lineHeight: 1.5, color: "rgba(240,235,222,0.88)", marginTop: 24, opacity: p, transform: `translateY(${(1 - p) * 14}px)` }}>{txt}</div>
  );
  return (
    <Shell dur={dur}>
      <HairGrid />
      <div style={{ position: "absolute", inset: 0, padding: `110px ${T.padX}px`, display: "flex", alignItems: "center", gap: 120 }}>
        <div style={{ flex: "none" }}>
          <div style={{ fontFamily: T.sans, fontSize: 30, letterSpacing: "0.4em", color: T.inkBright, marginBottom: 20 }}>② 输出 · 小红书笔记</div>
          <div style={{ fontFamily: T.serif, fontSize: 60, fontWeight: 900, color: T.paper, lineHeight: 1.2 }}>一稿多平台，<br /><span style={{ color: T.inkBright }}>顺手就出</span></div>
          <div style={{ marginTop: 26, fontFamily: T.sans, fontSize: 30, color: T.soft, maxWidth: 420, lineHeight: 1.5 }}>标题、正文、话题标签，一次生成。</div>
        </div>
        <div
          style={{
            width: 540,
            height: 820,
            borderRadius: 46,
            border: "10px solid #17324a",
            background: "linear-gradient(170deg,#0c1a16,#08110d)",
            boxShadow: "0 40px 90px rgba(0,0,0,0.6)",
            padding: "44px 40px",
            position: "relative",
            opacity: phoneIn,
            transform: `translateX(${(1 - phoneIn) * 160}px) rotate(${(1 - phoneIn) * 4}deg)`,
          }}
        >
          <div style={{ position: "absolute", top: 18, left: "50%", transform: "translateX(-50%)", width: 150, height: 12, borderRadius: 8, background: "#1e3b2f" }} />
          <div style={{ fontFamily: T.serif, fontSize: 44, fontWeight: 900, lineHeight: 1.28, color: T.paper, marginTop: 22, opacity: t1.p, transform: `scale(${t1.scale})`, filter: t1.blur > 0.05 ? `blur(${t1.blur}px)` : undefined, transformOrigin: "left top" }}>做内容越做越累？因为你一直在“从零硬写”</div>
          {pl(l1.p, "· 坑1：每条都想爆 → 要的是稳定被看见")}
          {pl(l2.p, "· 坑2：迷信日更 → 一周3条精品，胜过7条凑数")}
          {pl(l3.p, "· 坑3：全靠一个人 → 人走就断更")}
          <div style={{ marginTop: 28, fontFamily: T.sans, fontSize: 27, color: "#4fe0a0", lineHeight: 1.5, opacity: tags }}>#内容营销 #中小企业 #自媒体运营 #降本增效</div>
        </div>
      </div>
      <Foot idx={3} total={6} op={1} />
    </Shell>
  );
};

/* ═══════════════ S4 输出·公众号 ═══════════════ */
const S4: React.FC<{ dur: number }> = ({ dur }) => {
  const f = useCurrentFrame();
  const cardIn = R(f, 6, 40, Easing.bezier(0.25, 0.1, 0.4, 1));
  const h = stamp(f, 28, 54);
  const s1 = R(f, 58, 82);
  const s2 = R(f, 86, 110);
  const s3 = R(f, 114, 138);
  const bar = (p: number, no: string, txt: string) => (
    <div style={{ marginTop: 30, opacity: p, transform: `translateX(${(1 - p) * -40}px)`, display: "flex", alignItems: "baseline", gap: 22 }}>
      <span style={{ fontFamily: T.serif, fontSize: 40, fontWeight: 900, color: T.inkBright }}>{no}</span>
      <span style={{ fontFamily: T.sans, fontSize: 42, fontWeight: 700, color: T.paper }}>{txt}</span>
      <span style={{ flex: 1, height: 1, background: T.hair, transform: `scaleX(${p})`, transformOrigin: "left" }} />
    </div>
  );
  return (
    <Shell dur={dur}>
      <HairGrid />
      <div style={{ position: "absolute", inset: 0, padding: `120px ${T.padX}px`, display: "flex", flexDirection: "column", justifyContent: "center" }}>
        <div style={{ fontFamily: T.sans, fontSize: 30, letterSpacing: "0.4em", color: T.inkBright, marginBottom: 26 }}>③ 输出 · 公众号推文</div>
        <div
          style={{
            background: "linear-gradient(155deg, rgba(240,235,222,0.10) 0%, rgba(240,235,222,0.04) 100%)",
            border: "1px solid rgba(255,255,255,0.14)",
            borderRadius: 8,
            boxShadow: "0 30px 70px rgba(0,0,0,0.55)",
            padding: "60px 72px",
            opacity: cardIn,
            transform: `translateY(${(1 - cardIn) * 110}px)`,
          }}
        >
          <div style={{ fontFamily: T.serif, fontSize: 66, fontWeight: 900, color: T.paper, opacity: h.p, transform: `scale(${h.scale})`, filter: h.blur > 0.05 ? `blur(${h.blur}px)` : undefined, transformOrigin: "left center" }}>内容越做越累？不是你不努力，是方法错了</div>
          {bar(s1, "一", "三个坑：爆款 / 日更 / 靠一个人")}
          {bar(s2, "二", "建一条产线：选题库 → 模板 → 复用")}
          {bar(s3, "三", "一次生产，多平台复用三个版本")}
        </div>
      </div>
      <Foot idx={4} total={6} op={1} />
    </Shell>
  );
};

/* ═══════════════ S5 输出·视频号脚本 ═══════════════ */
const S5: React.FC<{ dur: number }> = ({ dur }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const head = stamp(f, 8, 34);
  const ROWS: Array<[string, string, string]> = [
    ["镜1", "老板揉眼睛、桌上堆满文档", "内容天天做，人快累废了，效果还一般？"],
    ["镜2", "屏幕出现“从零硬写”", "问题不在做得少，在每条都在从零硬写。"],
    ["镜3", "三个坑依次弹出", "迷信爆款、迷信日更、全靠一个人。"],
    ["镜4", "流水线动画：选题库 → 模板", "真正省力，是给内容建一条产线。"],
    ["镜5", "一条内容裂成三块", "一条内容，顺手改成三个平台。"],
    ["镜6", "结尾字幕 + 品牌", "内容是复用出来的，不是每条都原创。"],
  ];
  // 行几何：真实高 84 + 间距 12 —— 圆点按同一套几何算，绝不硬编码拍脑袋的行距
  const ROW_H = 84;
  const GAP = 12;
  const H0 = 46; // 首个高亮帧
  const STEP = 30; // 每镜间隔
  const MOVE = 12; // 圆点从上一行移到下一行所用帧，在下一次高亮前完成
  const LEAD = 12; // 行在其高亮前 LEAD 帧淡入 —— 保证圆点移入时该行已可见
  const centerY = (i: number) => i * (ROW_H + GAP) + ROW_H / 2;
  const times = ROWS.map((_, i) => H0 + i * STEP);
  const reveal = (i: number) =>
    Math.max(0, Math.min(1, spring({ frame: Math.max(0, f - (times[i] - LEAD)), fps, config: { damping: 14, stiffness: 120 } })));
  let active = -1;
  for (let i = 0; i < ROWS.length; i++) if (f >= times[i]) active = i;
  const dotY = (): number => {
    if (active < 0) return centerY(0);
    if (active >= ROWS.length - 1) return centerY(ROWS.length - 1);
    const tNext = times[active + 1];
    const ms = tNext - MOVE;
    if (f < ms) return centerY(active);
    const k = R(f, ms, tNext, Easing.inOut(Easing.cubic));
    return centerY(active) + (centerY(active + 1) - centerY(active)) * k;
  };
  const dotIn = R(f, H0 - 16, H0);
  return (
    <Shell dur={dur}>
      <HairGrid />
      <div style={{ position: "absolute", inset: 0, padding: `100px ${T.padX}px` }}>
        <div style={{ fontFamily: T.sans, fontSize: 30, letterSpacing: "0.4em", color: T.inkBright, marginBottom: 28, opacity: head.p }}>④ 输出 · 视频号口播脚本</div>
        <div style={{ position: "relative" }}>
          {/* 播放头圆点：与当前高亮行的居中线同一平面 */}
          <div style={{ position: "absolute", left: -30, top: dotY() - 7, width: 14, height: 14, borderRadius: "50%", background: T.inkBright, boxShadow: `0 0 22px ${T.inkBright}`, opacity: dotIn }} />
          {ROWS.map(([no, cam, vo], i) => {
            const p = reveal(i);
            const isAct = active === i;
            return (
              <div
                key={i}
                style={{
                  height: ROW_H,
                  boxSizing: "border-box",
                  display: "flex",
                  gap: 26,
                  alignItems: "center",
                  padding: "0 30px",
                  borderRadius: 12,
                  border: `1px solid ${isAct ? T.inkBright : T.hair}`,
                  background: isAct ? "rgba(31,43,224,0.16)" : "rgba(240,235,222,0.03)",
                  marginBottom: GAP,
                  opacity: p,
                  transform: `translateX(${(1 - p) * -50}px)`,
                }}
              >
                <span style={{ fontFamily: T.sans, fontWeight: 900, color: T.inkBright, width: 70, flex: "none" }}>{no}</span>
                <span style={{ fontFamily: T.sans, color: T.soft, flex: 1.1, fontSize: 30 }}>{cam}</span>
                <span style={{ fontFamily: T.sans, color: T.paper, flex: 1.7, fontSize: 31, fontWeight: 500 }}>{vo}</span>
              </div>
            );
          })}
        </div>
      </div>
      <Foot idx={5} total={6} op={1} />
    </Shell>
  );
};

/* ═══════════════ S6 片尾 ═══════════════ */
const S6: React.FC<{ dur: number }> = ({ dur }) => {
  const f = useCurrentFrame();
  const hero = stamp(f, 6, 40);
  const line = R(f, 40, 64);
  const brand = R(f, 78, 108);
  return (
    <Shell dur={dur} noExit>
      <HairGrid op={0.25} />
      <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", justifyContent: "center", alignItems: "center", textAlign: "center" }}>
        <div style={{ width: 90, height: 3, background: T.inkBright, transform: `scaleX(${line})`, marginBottom: 40 }} />
        <div style={{ fontFamily: T.serif, fontSize: 150, fontWeight: 900, color: T.paper, opacity: hero.p, transform: `scale(${hero.scale})`, filter: hero.blur > 0.05 ? `blur(${hero.blur}px)` : undefined, letterSpacing: `${hero.ls}em`, lineHeight: 1.05 }}>
          做一次 · <span style={{ color: T.inkBright }}>用三处</span>
        </div>
        <div style={{ marginTop: 44, fontFamily: T.sans, fontSize: 46, color: T.soft, opacity: R(f, 60, 90) }}>把重复活交给流水线，人去做值钱的判断</div>
        <div style={{ marginTop: 64, fontFamily: T.sans, fontSize: 32, color: T.inkBright, letterSpacing: "0.4em", fontWeight: 800, opacity: brand }}>壹目贯维 · 内容自动化</div>
      </div>
      <Foot idx={6} total={6} op={R(f, 70, 96)} />
    </Shell>
  );
};

/* 全局颗粒（SVG 湍流，确定性；按帧微移） */
const Grain: React.FC = () => {
  const f = useCurrentFrame();
  const ox = (f * 5) % 200;
  return (
    <AbsoluteFill style={{ pointerEvents: "none", opacity: 0.06, mixBlendMode: "soft-light" }}>
      <svg width="100%" height="100%">
        <filter id="grain">
          <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves={2} seed={7} stitchTiles="stitch" />
          <feColorMatrix type="saturate" values="0" />
        </filter>
        <rect x={-ox} y={-ox} width="200%" height="200%" filter="url(#grain)" />
      </svg>
    </AbsoluteFill>
  );
};

export const DemoFilm18: React.FC = () => {
  return (
    <AbsoluteFill style={{ backgroundColor: T.deep }}>
      <Audio src={staticFile("narration_full.mp3")} />
      <Series>
        <Series.Sequence durationInFrames={235}><S1 dur={235} /></Series.Sequence>
        <Series.Sequence durationInFrames={292}><S2 dur={292} /></Series.Sequence>
        <Series.Sequence durationInFrames={341}><S3 dur={341} /></Series.Sequence>
        <Series.Sequence durationInFrames={173}><S4 dur={173} /></Series.Sequence>
        <Series.Sequence durationInFrames={288}><S5 dur={288} /></Series.Sequence>
        <Series.Sequence durationInFrames={238}><S6 dur={238} /></Series.Sequence>
      </Series>
      <Grain />
    </AbsoluteFill>
  );
};
