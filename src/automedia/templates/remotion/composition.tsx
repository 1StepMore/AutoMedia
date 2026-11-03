/**
 * AutoMedia Remotion composition — narration-aligned storyboard renderer (#351).
 *
 * Ported from the promo kit's motion grammar (promo/docs/运动语法-禁则.md):
 * velocity-matched seams, camera push, stamp text, hairline grid. The full
 * kit (promo/remotion/src/kit) stays the reference for advanced authoring;
 * this file is the self-contained pipeline template driven by a storyboard.
 *
 * Storyboard shape (written by VideoRemotionEngine._provision):
 *   { fps, width, height, scenes: [{ index, text, title, startFrame, durationFrames, media }] }
 */
import React from "react";
import {
  AbsoluteFill,
  Audio,
  Easing,
  Img,
  interpolate,
  Sequence,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

interface Scene {
  index: number;
  text: string;
  title: string;
  startFrame: number;
  durationFrames: number;
  media: string;
}

interface Storyboard {
  fps: number;
  width: number;
  height: number;
  audio: string;
  scenes: Scene[];
}

const COLORS = {
  bg: "#030a04",
  surface: "#0a1b10",
  text1: "#8cff9a",
  text2: "#4bd17a",
  text3: "#2f8a4d",
  accent: "#00ff88",
  hair: "rgba(140, 255, 154, 0.10)",
  serif: '"Noto Serif SC", serif',
  sans: '"Noto Sans SC", sans-serif',
};

const SEAM = 18; // 速度匹配接缝（帧）：入场带位移、出场在运动中切
const STAMP = 21; // 压印字效（帧）：单次动作

// 压印字效：scale 1.16→1 + blur 4→0（transform/合成器属性，禁 reflow tween）
const stamp = (frame: number, from: number) => {
  const p = interpolate(frame, [from, from + STAMP], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.bezier(0.2, 0, 0.15, 1),
  });
  return {
    opacity: p,
    transform: `scale(${1 + (1 - p) * 0.16})`,
    filter: `blur(${(1 - p) * 4}px)`,
  };
};

const HairGrid: React.FC = () => (
  <div style={{ position: "absolute", inset: 0, display: "flex", opacity: 0.5 }}>
    {Array.from({ length: 13 }).map((_, i) => (
      <i key={i} style={{ flex: 1, borderRight: i < 12 ? `1px solid ${COLORS.hair}` : "none" }} />
    ))}
  </div>
);

const SceneView: React.FC<{ scene: Scene; total: number }> = ({ scene, total }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const local = frame - scene.startFrame;
  const dur = scene.durationFrames;

  // 场景横移：入场从 +220 收进（不从静止入场），结尾向左出画（在运动中切）
  const enter = interpolate(local, [0, SEAM], [220, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
  const exit = interpolate(local, [dur - SEAM, dur], [0, 2140], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.in(Easing.cubic),
  });
  // 镜头推近：每场 scale 1.00→1.04，inOut，不来回
  const cam = interpolate(local, [0, dur], [1.0, 1.04], {
    extrapolateRight: "clamp",
    easing: Easing.inOut(Easing.cubic),
  });
  // spring 入场（标题用，damping ~14）
  const titleSpring = spring({ frame: local - Math.round(SEAM / 2), fps, config: { damping: 14 } });

  return (
    <Sequence from={scene.startFrame} durationInFrames={dur} name={`Scene ${scene.index}`}>
      <AbsoluteFill style={{ backgroundColor: COLORS.bg, overflow: "hidden" }}>
        <div style={{ position: "absolute", inset: 0, transform: `translateX(${enter - exit}px)` }}>
          <div style={{ position: "absolute", inset: 0, transform: `scale(${cam})` }}>
            <div style={{ position: "absolute", inset: 0 }}>
              {scene.media ? (
                <>
                  <Img
                    src={staticFile(scene.media)}
                    style={{
                      position: "absolute",
                      inset: 0,
                      width: "100%",
                      height: "100%",
                      objectFit: "cover",
                      transform: `scale(${1 + (1 - enter / 220) * 0.06})`,
                    }}
                  />
                  <div
                    style={{
                      position: "absolute",
                      inset: 0,
                      background:
                        "linear-gradient(90deg, rgba(3,10,4,0.92) 0%, rgba(3,10,4,0.55) 55%, rgba(3,10,4,0.25) 100%)",
                    }}
                  />
                </>
              ) : (
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    background: `radial-gradient(1200px 600px at 78% 30%, rgba(0,255,136,0.14), transparent 60%), linear-gradient(160deg, ${COLORS.surface} 0%, ${COLORS.bg} 70%)`,
                  }}
                />
              )}
              <HairGrid />
              <div style={{ position: "absolute", left: 150, right: 420, top: 300 }}>
                <div
                  style={{
                    ...stamp(local, Math.round(SEAM / 2)),
                    fontFamily: COLORS.sans,
                    fontSize: 88,
                    fontWeight: 700,
                    color: COLORS.accent,
                    marginBottom: 44,
                    maxWidth: 1250,
                    opacity: titleSpring,
                  }}
                >
                  {scene.title}
                </div>
                <div
                  style={{
                    ...stamp(local, Math.round(SEAM / 2) + 4),
                    fontFamily: COLORS.sans,
                    fontSize: 40,
                    lineHeight: 1.6,
                    color: COLORS.text1,
                    maxWidth: 1200,
                  }}
                >
                  {scene.text}
                </div>
              </div>
              <div
                style={{
                  position: "absolute",
                  left: 150,
                  right: 150,
                  bottom: 72,
                  display: "flex",
                  justifyContent: "space-between",
                  fontFamily: COLORS.sans,
                  fontSize: 24,
                  color: COLORS.text3,
                  letterSpacing: "0.08em",
                  opacity: interpolate(local, [SEAM / 2, SEAM / 2 + 12], [0, 1], {
                    extrapolateLeft: "clamp",
                    extrapolateRight: "clamp",
                  }),
                }}
              >
                <span>AutoMedia</span>
                <span style={{ color: COLORS.accent }}>
                  {String(scene.index).padStart(2, "0")} / {String(total).padStart(2, "0")}
                </span>
              </div>
            </div>
          </div>
        </div>
      </AbsoluteFill>
    </Sequence>
  );
};

export const AutoMediaComposition: React.FC<{ storyboard: Storyboard }> = ({ storyboard }) => {
  return (
    <AbsoluteFill style={{ backgroundColor: COLORS.bg, fontFamily: COLORS.sans }}>
      {storyboard.scenes.map((s) => (
        <SceneView key={s.index} scene={s} total={storyboard.scenes.length} />
      ))}
      {storyboard.audio ? <Audio src={staticFile(storyboard.audio)} /> : null}
    </AbsoluteFill>
  );
};
