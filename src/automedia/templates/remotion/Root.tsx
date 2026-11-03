/**
 * Remotion root — registers the AutoMedia composition (#351).
 *
 * The storyboard arrives as render inputProps (`--props storyboard.json`);
 * calculateMetadata derives duration/fps/size from it so one composition
 * serves any narration-aligned timeline.
 */
import React from "react";
import { Composition } from "remotion";

import { AutoMediaComposition, type Storyboard } from "./composition";

const fallbackStoryboard: Storyboard = {
  fps: 30,
  width: 1920,
  height: 1080,
  audio: "",
  scenes: [],
};

const totalFrames = (sb: Storyboard): number =>
  sb.scenes.reduce((acc, s) => Math.max(acc, s.startFrame + s.durationFrames), 0) + 18;

export const RemotionRoot: React.FC = () => (
  <Composition
    id="AutoMedia"
    component={AutoMediaComposition}
    durationInFrames={totalFrames(fallbackStoryboard)}
    fps={30}
    width={1920}
    height={1080}
    defaultProps={{ storyboard: fallbackStoryboard }}
    calculateMetadata={({ props }) => {
      const sb = props.storyboard as Storyboard;
      return {
        durationInFrames: Math.max(totalFrames(sb), 1),
        fps: sb.fps || 30,
        width: sb.width || 1920,
        height: sb.height || 1080,
      };
    }}
  />
);
