---
title: Video Synthesis Engine
description: Design document for the FFmpeg-based video synthesis module. Slideshow generation, TTS audio, Ken Burns, crossfade, and subtitle composition.
---

# Video Synthesis Engine

> 📝 **设计稿，尚未实现** — 本文档描述的 `video_synthesis.py` (计划 1245 行) 目前不存在于代码仓库中。
> 这是视频合成的设计蓝图，尚未进入实现阶段。

## Overview

The video synthesis engine turns pipeline assets into a finished MP4 file.
It takes images (from ComfyUI), audio (from edge-tts via `AudioPipeline`),
and subtitles (SRT from Whisper transcription) and combines them through
FFmpeg into a single video. The engine lives at
`src/automedia/pipelines/video_synthesis.py`.

This module is the final production step before the lifecycle gates (L1-L4)
run. It does not replace or duplicate the existing `ImagePipeline` or
`AudioPipeline`. Those modules produce the raw ingredients. This module
cooks the meal.

### Design constraints

- **No ThreadPoolExecutor.** The engine runs a conservative 3-stage
  pipeline. Each stage calls FFmpeg as a subprocess and waits for it to
  finish. Parallelism, if needed later, belongs in the caller, not in this
  module.
- **Consistent with existing patterns.** The codebase shells out to
  `edge-tts`, `whisper`, and `comfyui` via `subprocess`. The video
  synthesis module follows the same convention. No Python FFmpeg bindings.
- **Stateless functions.** Each function takes file paths and parameters,
  writes an output file, and returns the path. No class state, no
  long-lived objects.

### Required system dependency

FFmpeg 4.4+ is required. The `automedia doctor` check already covers this.
See the README for platform-specific install instructions.

If FFmpeg is missing at runtime, every function in this module raises
`FileNotFoundError` with a clear message pointing to the install docs.

---

## Three Stage Pipeline

The synthesis runs in three sequential stages. Each stage produces one or
more intermediate files. The next stage consumes them.

```
Stage 1                  Stage 2                   Stage 3
─────────                ─────────                 ─────────
Images + audio           Individual clips          Final composition
                                                   ┌─────────────────┐
┌──────────┐    ┌───────────────────┐    ┌────────>  audio track      │
│  images  │───>│ per-image clips   │    │         │  (AAC)           │
│  (PNG)   │    │ with Ken Burns    │    │         └─────────────────┘
└──────────┘    │ and per-clip      │    │         ┌─────────────────┐
                │ silence detection │────┤────────>│  main video     │
┌──────────┐    └───────────────────┘    │         │  (clips +       │
│  TTS MP3 │─────────────────────────────┤         │   crossfade)    │
└──────────┘                              │         └─────────────────┘
┌──────────┐                              │         ┌─────────────────┐
│  SRT     │──────────────────────────────┤────────>│  subtitles      │
└──────────┘                              │         │  (burned in)    │
                                          │         └─────────────────┘
                                          │         ┌─────────────────┐
                                          └────────>│  final MP4      │
                                                    │  1920x1080      │
                                                    │  24fps          │
                                                    │  libx264 + AAC  │
                                                    └─────────────────┘
```

### Stage 1 — asset preparation

- Read all input images from a sorted directory listing.
- Read the TTS audio file and SRT subtitle file.
- Validate that every file exists and has non-zero size.
- Return validated paths to Stage 2.

### Stage 2 — per-image clip generation

- For each image, call `apply_ken_burns()` to produce a short video clip
  with the zoompan effect. Duration matches the corresponding audio
  segment (or a default of 5 seconds if no audio timing is available).
- Each clip is a temporary file in the project's working directory.
- Clips are named `clip_0000.mp4`, `clip_0001.mp4`, etc.

### Stage 3 — final composition

- Concatenate all clips with crossfade transitions via
  `apply_crossfade()`.
- Overlay the TTS audio track with `synthesize_audio()`.
- Burn subtitles into the video with `render_subtitles()`.
- Run a final encode pass to produce the output MP4.

---

## Key Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Framerate | 24 fps | Standard cinema framerate. Balances motion smoothness with file size. Matches the testsrc2 validation command. |
| Resolution | 1920x1080 | Full HD 16:9. Matches the pipeline's cover image spec. |
| Video codec | libx264 | Widely compatible, hardware accelerated on most devices. CRF 23 for good quality at reasonable size. |
| Audio codec | AAC | Standard for MP4 containers. 128 kbps stereo. Matches edge-tts output format. |
| Pixel format | yuv420p | Maximum compatibility across players and browsers. |
| CRF | 23 | Default x264 CRF. Lower = better quality but larger files. |
| Audio sample rate | 44100 Hz | Standard audio sample rate. Matches edge-tts default. |

---

## Function Reference

Each function in this section maps to a function in
`video_synthesis.py`. All functions are module-level, not class methods.

### `generate_slideshow(image_paths, output_path, duration_per_image, fps=24, resolution=(1920, 1080))`

Takes a list of image file paths and produces a video where each image is
displayed for `duration_per_image` seconds. No Ken Burns, no transitions.
This is the simplest path and the foundation for the other functions.

**Implementation notes:**
- Builds an FFmpeg `-filter_complex` that concatenates individual image
  inputs with the `concat` filter.
- Each image is looped to match `duration_per_image` via the `loop` filter
  or by specifying `-t` per input.
- Output is a temporary MP4 that feeds into `apply_crossfade()`.

**FFmpeg command sketch:**
```
ffmpeg -loop 1 -t 5 -i img1.png -loop 1 -t 5 -i img2.png \
  -filter_complex "[0:v][1:v]concat=n=2:v=1:a=0" \
  -c:v libx264 -r 24 -pix_fmt yuv420p -crf 23 output.mp4
```

### `synthesize_audio(tts_mp3_path, output_path, sample_rate=44100, bitrate="128k")`

Transcodes the TTS MP3 to AAC format suitable for the MP4 container. This
is a thin wrapper around FFmpeg's audio transcoding.

**Why a separate function?** The edge-tts output is MP3. The MP4 container
works best with AAC audio. This function converts formats without
re-encoding the video. It also validates the audio duration and logs
warnings if the audio is significantly shorter or longer than the video.

**FFmpeg command sketch:**
```
ffmpeg -i input.mp3 -c:a aac -b:a 128k -ar 44100 -ac 2 output.aac
```

**Return value:** `str` — path to the transcoded AAC file.

### `render_subtitles(video_path, srt_path, output_path)`

Burns SRT subtitles into the video using FFmpeg's `subtitles` filter. The
subtitles are rendered directly onto the video frames. No separate subtitle
track.

**Rationale for burned-in subtitles:**
- Maximum platform compatibility. Some platforms strip sidecar subtitle
  tracks.
- Consistent appearance regardless of the player.
- The video quality gates (V6 specifically) can inspect subtitle
  positioning and readability directly.

**Implementation notes:**
- Uses the `subtitles` filter: `subtitles=srt_path`.
- Font defaults to the system sans-serif. Future versions may accept a
  custom font path.
- Subtitle position is centered at the bottom with standard padding.
- If the SRT file is missing or empty, the function returns the input path
  unchanged and logs a warning.

**FFmpeg command sketch:**
```
ffmpeg -i video.mp4 -vf "subtitles=subtitles.srt:force_style='Fontsize=24,PrimaryColour=&H00FFFFFF'" \
  -c:v libx264 -crf 23 -c:a copy -pix_fmt yuv420p output.mp4
```

### `apply_ken_burns(image_path, output_path, duration=5, fps=24, resolution=(1920, 1080), zoom=0.05)`

Applies a slow Ken Burns zoom effect to a single image. The image starts
at full frame and slowly zooms in to `(1 + zoom)` scale over the duration.

**Implementation notes:**
- Uses FFmpeg's `zoompan` filter: `zoompan=z='min(zoom+0.0015,1.05)':d=125:s=1920x1080:fps=24`.
- The zoom rate is calibrated so that over `duration` seconds at `fps`, the
  zoom reaches `1 + zoom`.
- The `d` parameter (number of frames) is `duration * fps`.
- The image is padded or cropped to fill the 16:9 frame. Pillow-style
  center-crop behavior is achieved with FFmpeg's scale + crop chain before
  zoompan.

**Zoom rate calculation:**
```
zoom_per_frame = zoom / (duration * fps)
```

So for a 5-second clip at 24 fps with `zoom=0.05`:
```
zoom_per_frame = 0.05 / 120 = ~0.000417
```

**Return value:** `str` — path to the generated MP4 clip.

### `apply_crossfade(clip_paths, output_path, transition_duration=1.0, fps=24)`

Concatenates multiple video clips with crossfade transitions between them.

**Implementation notes:**
- Uses FFmpeg's `xfade` filter (available since FFmpeg 4.4).
- For `n` clips, there are `n - 1` transitions.
- Each transition overlaps the end of clip `i` with the start of clip
  `i + 1` for `transition_duration` seconds.
- The `offset` for each transition is calculated as the cumulative
  duration of all previous clips minus the transition overlap.

**FFmpeg command sketch (simplified, 2 clips):**
```
ffmpeg -i clip0.mp4 -i clip1.mp4 \
  -filter_complex "xfade=transition=fade:duration=1:offset=4" \
  -c:v libx264 -crf 23 -pix_fmt yuv420p -r 24 output.mp4
```

For 3+ clips, the filter graph chains multiple xfade operations.

**Edge case:** If only one clip is provided, the function returns it
unchanged (no transition needed).

### `compose_full_video(clip_paths, audio_path, srt_path, output_path, fps=24, resolution=(1920, 1080), crossfade_duration=1.0)`

The top-level function that calls the other five. Runs the 3-stage
pipeline end to end.

**Execution flow:**
1. Stage 1: Validate all inputs exist.
2. Stage 2: For each image, call `apply_ken_burns()` to produce a clip.
3. Stage 3a: Call `apply_crossfade()` on the clip list.
4. Stage 3b: Call `synthesize_audio()` to transcode TTS to AAC.
5. Stage 3c: Merge video and audio with `-map` on both streams.
6. Stage 3d: Call `render_subtitles()` to burn in SRT.
7. Stage 3e: Return the final output path.

**Intermediate files** are written to `project_dir/tmp_video/` and
cleaned up on success. On failure, they are left in place for debugging.

**Parameters accepted via config:**
- `video.fps` (default: 24)
- `video.resolution` (default: `1920x1080`)
- `video.codec` (default: `libx264`)
- `video.crf` (default: `23`)
- `video.ken_burns_zoom` (default: `0.05`)
- `video.crossfade_duration` (default: `1.0`)
- `audio.sample_rate` (default: `44100`)
- `audio.bitrate` (default: `128k`)

These are read from the pipeline config (6-layer merge) in
`run_full_pipeline()` and passed to `compose_full_video()` through the
gate context.

**Return value:** `str` — path to the final MP4 file.

---

## Integration With the Pipeline

The video synthesis module is **not a gate**. It is a utility module
called by gates or by the pipeline runner directly. The intended call
sites are:

1. **V4 (TTS Brand Asset) gate** — calls `synthesize_audio()` after
   generating the TTS MP3 to ensure the AAC track is ready.
2. **V6 (Subtitle Render) gate** — calls `render_subtitles()` to burn
   SRT into the assembled video.
3. **Pipeline runner** (after V7, before L1) — calls
   `compose_full_video()` as the final assembly step if the mode includes
   video gates.

The `compose_full_video()` function is the primary entry point. Callers
that need only a sub-step (e.g., just subtitles on an existing video) can
call the individual function directly.

### Data flow through pipeline

```
                    ┌──────────────────────────────┐
                    │  ImagePipeline                │
                    │  (ComfyUI → PNGs)             │
                    └──────────┬───────────────────┘
                               │ image paths
                               ▼
                    ┌──────────────────────────────┐
                    │  AudioPipeline                │
                    │  (edge-tts → MP3 + SRT)       │
                    └──────────┬───────────────────┘
                               │ MP3 path, SRT path
                               ▼
                    ┌──────────────────────────────┐
                    │  VideoSynthesis               │
                    │  compose_full_video()         │
                    │    ┌──────────────────┐       │
                    │    │ Stage 2          │       │
                    │    │ apply_ken_burns()│       │
                    │    │ per image → clip │       │
                    │    └────────┬─────────┘       │
                    │             ▼                  │
                    │    ┌──────────────────┐       │
                    │    │ Stage 3a         │       │
                    │    │ apply_crossfade()│       │
                    │    └────────┬─────────┘       │
                    │             ▼                  │
                    │    ┌──────────────────┐       │
                    │    │ Stage 3b         │       │
                    │    │ synthesize_audio │       │
                    │    │ (MP3 → AAC)      │       │
                    │    └────────┬─────────┘       │
                    │             ▼                  │
                    │    ┌──────────────────┐       │
                    │    │ Stage 3c         │       │
                    │    │ audio + video mix │       │
                    │    └────────┬─────────┘       │
                    │             ▼                  │
                    │    ┌──────────────────┐       │
                    │    │ Stage 3d         │       │
                    │    │ render_subtitles │       │
                    │    └────────┬─────────┘       │
                    │             ▼                  │
                    └──────────┬───────────────────┘
                               │ final MP4
                               ▼
                    ┌──────────────────────────────┐
                    │  Lifecycle Gates (L1-L4)      │
                    └──────────────────────────────┘
```

---

## Error Handling

All functions use the same error handling pattern:

1. Validate inputs at the top of the function. Raise `ValueError` or
   `FileNotFoundError` immediately on bad input.
2. Wrap the `subprocess.run()` call in a try/except block.
3. On non-zero return code, log the FFmpeg stderr and raise
   `subprocess.CalledProcessError`.
4. On `FileNotFoundError` (ffmpeg not installed), let it propagate. The
   caller can catch it or let it fail the pipeline gate.

**Temporary file cleanup:** The module provides a helper
`_cleanup_temp_dir(temp_dir)` that removes the temp directory on success.
On failure, the temp directory is left in place so operators can inspect
the intermediate files.

---

## Testing Strategy

Tests go in `tests/test_pipeline/test_video_synthesis.py`.

**Unit tests (no FFmpeg required):**
- Input validation: empty image list, missing files, bad resolutions.
- Zoom rate calculation: verify `zoom_per_frame` math.
- Config parameter merging: verify defaults override correctly.
- SRT burn: verify the FFmpeg command string is constructed correctly
  (use a mock for `subprocess.run`).

**Integration tests (FFmpeg required):**
- `generate_slideshow()` with 2 test images, verify output duration.
- `apply_ken_burns()` on a 1920x1080 test image, verify output
  resolution and duration.
- `apply_crossfade()` with 2 clips, verify the output has the expected
  total duration.
- `compose_full_video()` end to end with synthetic test data from
  `tests/fixtures/synth/`.

**How to generate test images:**
Use FFmpeg's `testsrc2` source which is already validated as working:

```bash
ffmpeg -f lavfi -i testsrc2=duration=5:size=1920x1080:rate=24 \
  -frames:v 1 test_frame.png
```

**How to generate test audio:**
Use FFmpeg's `sine` source:

```bash
ffmpeg -f lavfi -i "sine=frequency=440:duration=5" -c:a aac test.aac
```

---

## FFmpeg CLI Verification

The following commands were used to verify that FFmpeg has the required
capabilities. Run them against your FFmpeg 4.4+ installation.

### Basic availability

```bash
ffmpeg -version
ffmpeg version 4.4.x or later  # expected
```

### testsrc2 source (test pattern generation)

```bash
ffmpeg -f lavfi -i testsrc2=duration=5:size=1920x1080:rate=24 \
  -frames:v 1 -f null -
```

Expected output: A single null-encoded frame at 1920x1080 24fps with no
errors.

### filter_complex with concat

```bash
ffmpeg -f lavfi -i testsrc2=duration=2:size=1920x1080:rate=24 \
  -f lavfi -i testsrc2=duration=2:size=1920x1080:rate=24 \
  -filter_complex "[0:v][1:v]concat=n=2:v=1:a=0" \
  -frames:v 1 -f null -
```

Expected output: No errors. The concat filter links two 2-second clips.

### zoompan filter (Ken Burns)

```bash
ffmpeg -f lavfi -i testsrc2=duration=5:size=1920x1080:rate=24 \
  -filter_complex "zoompan=z='min(zoom+0.000417,1.05)':d=120:s=1920x1080:fps=24" \
  -frames:v 1 -f null -
```

Expected output: No errors. The zoompan filter processes a 5-second input
at 24 fps.

### xfade filter (crossfade)

```bash
ffmpeg -f lavfi -i testsrc2=duration=2:size=1920x1080:rate=24 \
  -f lavfi -i testsrc2=duration=2:size=1920x1080:rate=24 \
  -filter_complex "xfade=transition=fade:duration=1:offset=1" \
  -frames:v 1 -f null -
```

Expected output: No errors. The xfade filter transitions between two
2-second clips with a 1-second fade starting at offset 1.

### subtitles filter

```bash
ffmpeg -f lavfi -i testsrc2=duration=2:size=1920x1080:rate=24 \
  -vf "subtitles=/dev/null" -frames:v 1 -f null -
```

Expected output: Warning about missing subtitle file (expected), but no
filter errors. The subtitles filter is available.

### AAC audio encoding

```bash
ffmpeg -f lavfi -i "sine=frequency=440:duration=5" \
  -c:a aac -b:a 128k -ar 44100 -ac 2 -f null -
```

Expected output: No errors. AAC encoding at 128 kbps 44.1 kHz stereo.

---

## Configuration

The video synthesis parameters are added to the config under the `video`
and `audio` keys. These are merged through the standard 6-layer config
hierarchy.

**Built-in defaults** (`automedia/manifests/defaults.yaml`):

```yaml
video:
  fps: 24
  resolution: [1920, 1080]
  codec: libx264
  crf: 23
  pix_fmt: yuv420p
  ken_burns_zoom: 0.05
  crossfade_duration: 1.0
  temp_dir: tmp_video

audio:
  codec: aac
  bitrate: 128k
  sample_rate: 44100
  channels: 2
```

Users can override these in their `.automedia/config.yaml` or via
`AUTOMEDIA_VIDEO_FPS`, `AUTOMEDIA_AUDIO_BITRATE`, etc. environment
variables, following the existing pattern in `config_loader.py`.

---

## File Layout

The implementation file follows the conventions of the existing
`audio_pipeline.py` and `image_pipeline.py` modules.

```
src/automedia/pipelines/video_synthesis.py

  ┌─────────────────────────────────────────────┐
  │ module docstring + __future__ imports        │
  ├─────────────────────────────────────────────┤
  │ Constants                                    │
  │   DEFAULT_FPS = 24                           │
  │   DEFAULT_RESOLUTION = (1920, 1080)          │
  │   DEFAULT_CODEC = "libx264"                  │
  │   DEFAULT_CRF = 23                           │
  │   DEFAULT_ZOOM = 0.05                        │
  │   DEFAULT_CROSSFADE_DURATION = 1.0           │
  ├─────────────────────────────────────────────┤
  │ Module-level functions (6)                   │
  │   generate_slideshow()                       │
  │   synthesize_audio()                         │
  │   render_subtitles()                         │
  │   apply_ken_burns()                          │
  │   apply_crossfade()                          │
  │   compose_full_video()                       │
  ├─────────────────────────────────────────────┤
  │ Private helpers                              │
  │   _build_filter_graph() — construct xfade   │
  │   _cleanup_temp_dir() — remove temp files    │
  │   _validate_inputs() — check paths exist     │
  │   _run_ffmpeg() — common subprocess wrapper  │
  └─────────────────────────────────────────────┘
```

---

## Future Considerations

Things deliberately left out of this first version:

- **No GPU acceleration.** The first version uses software encoding
  (libx264). Hardware acceleration (h264_nvenc, videotoolbox, etc.) can
  be added later via a config option.
- **No dynamic Ken Burns direction.** The zoom is always in (not out,
  not pan). Direction variation can be added later.
- **No audio ducking.** The TTS audio plays at full volume over the
  entire video. Background music or audio ducking are not part of this
  design.
- **No parallel clip generation.** Clips are generated sequentially in
  Stage 2. If performance becomes an issue, the caller can use a
  thread pool.
- **No ComfyUI video generation.** The image pipeline uses ComfyUI for
  still images. Video generation via ComfyUI (e.g., AnimateDiff) is a
  separate feature.
