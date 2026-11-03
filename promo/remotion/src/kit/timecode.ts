/**
 * timecode.ts —— 总帧数校验（本库自写，不引外部依赖）。
 *
 * 来源说明：原 n-segment 骨架依赖归档工程里的 `../src/timecode`（外部文件），
 * 那里唯一有价值的就是「总帧数对不对」这 30 行；既然只有一个用途，
 * 就自己写一份放进库，不为一个骨架把外部依赖拖进来。
 *
 * Remotion 的 `TransitionSeries` 语义：相邻场次之间会**重叠**过渡时长，
 * 所以 总帧数 = Σ场次帧数 − Σ过渡帧数。算错就会出现「最后一帧黑掉」或「结尾被截」。
 */

export type Segment = { readonly frames: number; readonly name?: string };
export type TransitionSpec = { readonly durationInFrames: number };

export const framesOfSeconds = (seconds: number, fps: number): number => Math.round(seconds * fps);

/** 按 TransitionSeries 语义算总帧数（不校验，只算） */
export function totalFrames(segments: readonly Segment[], transitions: readonly TransitionSpec[]): number {
  const sum = segments.reduce((acc, s) => acc + s.frames, 0);
  const overlap = transitions.reduce((acc, t) => acc + t.durationInFrames, 0);
  return sum - overlap;
}

/**
 * 断言总帧数等于期望值。
 * @param expected 你声明的 durationInFrames
 * @throws 差一帧也抛错 —— 差一帧在成片里就是结尾黑屏/末字被切
 */
export function assertTotalFrames(
  expected: number,
  segments: readonly Segment[],
  transitions: readonly TransitionSpec[]
): number {
  if (!Array.isArray(segments) || segments.length === 0) {
    throw new Error("[timecode] segments 不能为空");
  }
  if (transitions.length > segments.length - 1) {
    throw new Error(
      `[timecode] 过渡数 ${transitions.length} 超过场次数-1（${segments.length - 1}）`
    );
  }
  const actual = totalFrames(segments, transitions);
  if (actual !== expected) {
    const detail = segments
      .map((s, i) => `${i + 1}.${s.name ?? "未命名"}=${s.frames}`)
      .join(" + ");
    throw new Error(
      `[timecode] 总帧数不符：声明 ${expected}，实算 ${actual}（差 ${actual - expected}）。` +
        `场次：${detail}；过渡合计 ${transitions.reduce((a, t) => a + t.durationInFrames, 0)} 帧`
    );
  }
  return actual;
}
