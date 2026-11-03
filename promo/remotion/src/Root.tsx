import React from "react";
import { Composition } from "remotion";
import { DemoFilm18 } from "./DemoFilm18";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      {/* 1篇内容→3平台 demo：1567 帧 = 52.22s × 30fps */}
      <Composition
        id="DemoFilm18"
        component={DemoFilm18}
        durationInFrames={1567}
        fps={30}
        width={1920}
        height={1080}
      />
    </>
  );
};
