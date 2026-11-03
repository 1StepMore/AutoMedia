---
title: Restricted Hardware & Remote Engines
description: Minimum hardware per capability, degradation switches, and pointing engines at remote machines — for 4 GB laptops, WSL, and low-bandwidth setups.
---

# Restricted Hardware & Remote Engines

AutoMedia's full dependency list (Bun, Chrome, ComfyUI, Whisper, hyperframes, …)
is what the **video-capable** configuration needs. You do not need all of it.
This page tells you, for each capability tier, what the machine really needs,
which switches degrade gracefully, and which engines can be pointed at a
remote machine instead of running locally.

Related pages: [Windows Deployment](windows-deployment.md) (WSL2/Docker/native),
[Deployment](deployment.md), [CLI reference](cli-reference.md) (`automedia doctor`).

---

## 1. What actually triggers each engine

Engines are not all loaded at once. The pipeline only resolves an engine when
the selected **mode** asks for that media track
(`src/automedia/pipelines/runner.py`, media stage dispatch):

| Mode | Image engine | TTS | ASR | Video engine |
|---|---|---|---|---|
| `text_only`, `qa_only`, `social-thread`, `repurpose` | — | — | — | — |
| `text_with_cover` | one cover image | — | — | — |
| `image-carousel` | one image per slide | — | — | — |
| `video_only`, `short-video` | (frame rendering) | ✓ | ✓ | ✓ |
| `auto` | ✓ (when platforms want multimedia) | ✓ | ✓ | ✓ |

TTS and ASR live inside the video track (`AudioPipeline`), so a text-only
setup never touches Whisper or Piper at all.

The primary switch is therefore **the mode itself**
(`AUTOMEDIA_DEFAULT_MODE` env or the top-level `mode` key in
`.automedia/config.yaml`). Choosing a text mode is the single biggest
hardware saving available.

> Note: the `pipeline.{text,image,video,audio}.enabled` keys written by
> `automedia onboard start --step pipeline` are currently **onboarding/display metadata** —
> the runtime gates media production on the mode, not on those flags. Do not
> rely on them to disable a track.

---

## 2. Minimum hardware per capability tier

| Tier | Modes | Hardware floor | External tools | pip extras |
|---|---|---|---|---|
| **Text** | `text_only`, `qa_only`, `social-thread`, `repurpose` | 4 GB RAM, any CPU, online | none | `.[openai,rich]` (or your provider extra) |
| **Image** | `text_with_cover`, `image-carousel` | + ~1 GB disk | ComfyUI (local **or remote**) — or nothing: the `local` Pillow fallback needs no extra tool | `.[openai,rich]` |
| **Video** | `video_only`, `short-video`, `auto` | 8 GB RAM, 4 cores, ~10 GB disk | `ffmpeg`, `bun`, `hyperframes` CLI, headless Chrome, `edge-tts` CLI (or Piper), Whisper (`faster-whisper` extra) | `.[all]` minus omni |
| **Omni** | document triad (extract/localize/format) | + 2 GB disk for torch (`omni-ml`) | none | `.[omni]` |

Notes:

- **Image tier without ComfyUI**: the image engine chain defaults to
  `[comfyui, local]` (`engines.image.chain`). The `local` engine renders
  text-based images with Pillow — a core dependency, zero external tools. On a
  machine with no ComfyUI, set `engines.image.default: local` and skip ComfyUI
  entirely.
- **Video tier without hyperframes**: `HyperFramesVideoEngine` falls back to an
  ffmpeg slideshow (`_FALLBACK_FRAMERATE = 0.5`) when the hyperframes CLI or
  Chrome is unavailable. The output is a static-frame video — real motion
  requires hyperframes + Chrome.
- **ASR model size**: `faster-whisper` defaults to the `tiny` model
  (`DEFAULT_MODEL` in `asr_faster_whisper.py`; override with
  `AUTOMEDIA_FASTER_WHISPER_MODEL`), which runs comfortably on CPU in 4 GB.
  Stay at `tiny`/`base` on restricted machines — avoid `small` and up.
- **Omni-ml** pulls PyTorch (~2 GB download). On low bandwidth, install
  `.[omni-core]` / `.[omni-pdf]` only, and accept reduced semantic search.

---

## 3. Degradation switches (ordered by impact)

1. **Mode** — `AUTOMEDIA_DEFAULT_MODE=text_only` runs the whole pipeline with
   zero media dependencies (see the tier table above).
2. **Image chain** — `engines.image.chain: [local]` (skip ComfyUI) or
   `[comfyui, local]` (default; Pillow picks up when ComfyUI is unreachable).
3. **TTS chain** — `engines.tts.chain: [edge-tts]` uses Microsoft's cloud
   endpoint: no local model, no local CPU. Piper (local `.onnx`) is the
   offline alternative when bandwidth is the constraint instead of CPU.
4. **ASR chain** — ASR only runs inside the video track / source-audio
   ingestion. Text-only setups need nothing here.
5. **Omni extras** — install the narrow extra (`omni-core`, `omni-pdf`)
   instead of `.[omni]`.

All of these live in `.automedia/config.yaml` (merged from
`automedia/manifests/defaults.yaml`). See
`docs/dev/agent-reference.md` for the config-layer precedence.

---

## 4. Remote engines: what can leave the machine today

| Modality | Engine | Local-only or remote-capable | How to point it elsewhere |
|---|---|---|---|
| image | `comfyui` | **remote-capable** | `engines.image.comfyui.{host, port, protocol}` in `.automedia/config.yaml`, or env `AUTOMEDIA_ENGINES_IMAGE_COMFYUI_HOST` / `_PORT` / `_PROTOCOL` |
| image | `local` (Pillow) | local-only (by design — it is the offline fallback) | — |
| tts | `azure` | cloud service — commercial, reliable narration | `AUTOMEDIA_AZURE_SPEECH_KEY` + `AUTOMEDIA_AZURE_SPEECH_REGION` env (or `engines.tts.azure.speech_key/region`); leads the TTS chain when configured |
| tts | `edge-tts` | cloud service (nothing to configure) | requires the `edge-tts` CLI on PATH |
| tts | `piper` | local-only (`.onnx` model on disk) | `AUTOMEDIA_PIPER_MODEL_PATH` / `engines.tts.piper.model_path` |
| asr | `whisper` / `faster-whisper` | local-only | `AUTOMEDIA_FASTER_WHISPER_MODEL` (size name or local CTranslate2 dir) |
| video | `hyperframes` | local-only (CLI + headless Chrome) | — |
| video | ffmpeg fallback | local-only | — |

**Remote ComfyUI example** — the heavy rendering (SD1.5 + upscale) runs on a
GPU box, the orchestrating laptop stays light:

```yaml
# .automedia/config.yaml
engines:
  image:
    default: comfyui
    chain: [comfyui, local]
    comfyui:
      host: 192.168.1.20   # the GPU machine
      port: 8188
      protocol: http
```

or, without touching config files:

```bash
export AUTOMEDIA_ENGINES_IMAGE_COMFYUI_HOST=192.168.1.20
export AUTOMEDIA_ENGINES_IMAGE_COMFYUI_PORT=8188
```

Model files (`upscale_model`, `comfyui_models_path`) live on the ComfyUI
machine; leave them unset locally and `automedia doctor` reports the upscale
model as *unverifiable* rather than *missing*.

### `automedia doctor` and remote engines

The doctor's ComfyUI probe reads the same
`engines.image.comfyui.{host, port, protocol}` config, so a remote ComfyUI is
probed where it actually lives — it is no longer reported missing just
because nothing listens on `127.0.0.1:8188`.

Current doctor exit-code contract: **any** missing row (including the
optional ComfyUI service) makes `automedia doctor` exit 1. Read the table
rather than the exit code when you run a text-only setup on purpose, or
install the listed tools to go green. Relaxing exit codes for
engine-optional rows is a tracked gap (see `docs/dev/gap-register.md`).

### What has no remote path (honest list)

Piper, Whisper/faster-whisper, and hyperframes have no remote endpoint
today. If local CPU/bandwidth cannot fit them, the degradation switches in
§3 are the answer (cloud edge-tts, tiny ASR model, or a text/image mode).
A generic "remote engine proxy" is a tracked gap in
`docs/dev/gap-register.md`, not a current feature.

---

## 5. WSL and low-bandwidth specifics

- **WSL Chrome trap**: a `google-chrome` on the WSL PATH may be an exec shim
  to the Windows-side Chrome, which cannot run headless from WSL. `automedia
  doctor` detects this and prints the remediation (install a Linux Chromium,
  or use hyperframes' bundled headless shell: `hyperframes browser ensure`).
  Details: [Windows Deployment](windows-deployment.md).
- **Model downloads to budget for**: Whisper `base` (~150 MB), Piper voice
  models (~60–120 MB each), SD1.5 + RealESRGAN (multi-GB, lives on the
  ComfyUI host), PyTorch for omni-ml (~2 GB). On a 4G connection, prefer the
  cloud TTS (edge-tts) and skip omni-ml.
- **Verify before running**: `automedia doctor --install-missing` prints
  per-OS install commands for everything missing; `automedia doctor --fix`
  attempts the installs interactively (120 s timeout per tool).
