---
title: Video Engines
description: The two video tracks (Remotion vs HyperFrames), the selection switch, and the WSL dependency guide.
---

# Video Engines

AutoMedia renders video through **two tracks** (the promo kit's 双线设计):

| | Remotion track (`remotion`) | HyperFrames track (`hyperframes`) |
|---|---|---|
| Tech | React + Remotion 4, rendered by Node/Chrome | Deterministic HTML + GSAP (`render(t)`), rendered by the hyperframes CLI + headless Chrome; ffmpeg slideshow fallback |
| Motion ceiling | High — componentized scenes, springs, the full promo kit vocabulary | Medium — one-shot motion grammar (seams / push / stamp), no idle loops |
| Deps | Node 18+ (WSL on Windows), a remotion workspace, Chromium | hyperframes CLI + headless Chrome; ffmpeg fallback needs only ffmpeg |
| Machine fit | Mid — webpack bundling per render | Low — "a browser that opens" is enough |
| Best for | Brand-grade motion, complex scenes, long-term iteration | Fast deterministic batch rendering, restricted machines |
| Reference | `promo/remotion/` (DemoFilm18 + 2.4k-line kit) | `promo/hyperframes/` (compose.html + timeline.json) |

Both tracks share the same **narration-aligned timeline**
(`promo/docs/时间轴-旁白分段对齐法.md`): narration is split at sentence
boundaries, each segment is TTS'd separately, and scene cut points come from
ffprobe-measured durations — a cut always lands on a sentence end.

---

## The selection switch

```yaml
# .automedia/config.yaml
engines:
  video:
    default: hyperframes          # used when the chain is absent
    chain: [remotion, hyperframes]  # first available wins (default)
```

`resolve_engine_chain` walks the chain and skips engines whose
`check_available()` fails, so:

- WSL/Node present + workspace installed → **remotion renders**.
- No Node but hyperframes/ffmpeg present → **hyperframes renders** (or the
  ffmpeg slideshow when even Chrome is missing — static frames, honestly
  reported).
- Neither → the run's gate report carries an explicit
  `video_engine_unavailable` note. Video modes never fail silently.

Force one track by naming it alone:

```yaml
    chain: [remotion]   # or: [hyperframes]
```

### HyperFrames-specific switch

`engines.video.hyperframes.enhanced` (default `true`) toggles the
narration-aligned multi-scene templates. `false` restores the legacy
single-track / evenly-split behaviour.

### Remotion-specific config

```yaml
    remotion:
      project_dir: ~/.automedia/remotion-workspace  # one npm install, reused
      wsl_dist: Ubuntu        # Windows host: distro executing Node ("" = native)
      browser_executable: null  # e.g. ~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome
      fps: 30
      width: 1920
      height: 1080
```

On a Windows host the engine executes Node **inside WSL** (`wsl -d <distro>
--cd <workspace>`); paths are translated (`D:\x` → `/mnt/d/x`) and shell
arguments are quoted. Set `wsl_dist: ""` to force native Node.

---

## WSL dependency guide (China mirrors)

```bash
# inside WSL — npm registry mirror first
npm config set registry https://registry.npmmirror.com

# hyperframes track
npm install -g --prefix ~/.local bun hyperframes \
  --registry=https://registry.npmmirror.com

# headless Chromium (playwright mirror download)
PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright \
  npx playwright install chromium
# → ~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome

# remotion track (workspace)
mkdir -p ~/.automedia/remotion-workspace && cd ~/.automedia/remotion-workspace
npm init -y
npm i remotion @remotion/cli react react-dom typescript \
  --registry=https://registry.npmmirror.com
```

Point the engines at the browser:

```yaml
engines:
  video:
    hyperframes:
      chrome_path: ~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome
    remotion:
      browser_executable: ~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome
```

`ffmpeg` (slideshow fallback + narration probing/concat) comes from the
distro or a static build; see
[hardware-and-remote-engines](hardware-and-remote-engines.md) for the
restricted-hardware tiers.

---

## Acceptance evidence (2026-11-04 E2E, WSL render stack)

Both tracks rendered the same 4-scene narration-aligned storyboard (real
Azure per-segment TTS, ffprobe-measured cut points):

- HyperFrames track: h264 1920×1080 30fps + aac, 21.27s vs narration 21.24s,
  inter-scene frame diff 8.4–13.4/255 (visibly distinct scenes with media).
- Remotion track: same storyboard, rendered by `remotion render` in WSL with
  the playwright Chromium (`--browser-executable`).
