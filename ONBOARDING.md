# AutoMedia Onboarding

One document, two readers. **AutoMedia is agent-oriented**: an AI agent does
the work, and a human directs it at specific checkpoints. Every step below has
an agent column (what the agent executes) and a human column (where a person
is needed). Humans who prefer terminals can simply follow the agent column.

| Step | Agent (executable) | Human at the keyboard |
|---|---|---|
| 0. Identify system | run the detection command | nothing |
| 1. Pick capability tier | propose a tier from the table | **decide** what AutoMedia will produce |
| 2. Install dependencies | run installs, verify with `automedia doctor` | approve installs (`doctor --fix` asks) |
| 3. Configure | run `automedia onboard start`, write YAML | **provide LLM API key**, answer brand questions |
| 4. First run | `automedia run --topic … --mode …` | watch, then review the draft |
| 5. Direct (HITL) | surface pending approvals | **approve/reject at H0**, decide publishing |

Install-command details per OS: run `automedia doctor --install-missing`.
Hardware floors and remote-engine setup:
[docs/user/hardware-and-remote-engines.md](docs/user/hardware-and-remote-engines.md).

---

## Step 0 — Identify the system

Agent, run this first and branch on the result:

```bash
python3 -c "import platform; print(platform.system(), platform.release())"
```

| Result | Meaning | Watch out for |
|---|---|---|
| `Linux` + release containing `microsoft` | **WSL** | A `google-chrome` on PATH may be an exec shim to Windows-side Chrome — it cannot run headless. `automedia doctor` detects this and prints the fix (install a Linux Chromium, or `hyperframes browser ensure`). See [windows-deployment](docs/user/windows-deployment.md). |
| `Linux` (bare) | native Linux | smoothest path — all tooling works |
| `Darwin` | **macOS** | install FFmpeg/Chrome via Homebrew; no other branch |
| `Windows` | native Windows | FFmpeg/edge-tts need manual PATH setup; or use WSL2/Docker (recommended in the Windows guide) |

Fallback: if Python itself is missing or < 3.11, that is a **human task** —
install Python 3.11+ first (winget / apt / brew), then continue.

---

## Step 1 — Choose the capability tier (this decides the dependencies)

The dependency list is **not fixed**: it follows the pipeline `mode`. Do not
install everything "just in case".

| Tier | Modes you can run | External tools needed | pip install |
|---|---|---|---|
| **Text** | `text_only`, `qa_only`, `social-thread`, `repurpose` | none | `pip install -e ".[openai,rich]"` |
| **Image** | + `text_with_cover`, `image-carousel` | ComfyUI (local or remote) — or nothing (Pillow `local` fallback) | same |
| **Video** | + `video_only`, `short-video`, `auto` | `ffmpeg`, `bun`, `hyperframes`, headless Chrome, `edge-tts` CLI, Whisper | `pip install -e ".[all]"` |
| **Omni** | + document triad (extract/localize/format) | none extra (heavy wheels: torch ≈ 2 GB) | add `.[omni]` or the narrow `omni-core`/`omni-pdf` |

Judgment: **when in doubt, start at the Text tier.** It needs only Python and
an LLM key, and it exercises the full gate pipeline. Upgrade the tier later —
nothing in the config is wasted.

---

## Step 2 — Install dependencies

Agent, per tier:

```bash
# 1) Python package (tier extra):
pip install -e ".[openai,rich]"        # Text tier (anthropic extra if that is your provider)
pip install -e ".[all]"                # Video tier (adds mcp, omni, …)

# 2) External tools — print per-OS install commands for whatever is missing:
automedia doctor --install-missing
# or install interactively (asks before each command):
automedia doctor --fix
```

Verification & fallbacks — every media engine has a degraded path, so a
missing tool degrades quality, it does not have to stop you:

| Missing tool | Consequence | Fallback |
|---|---|---|
| ComfyUI | no generated images | `local` Pillow engine renders text images (`engines.image.chain: [comfyui, local]` is the default) |
| hyperframes / Chrome | no HTML-motion video | ffmpeg slideshow fallback (static frames) |
| edge-tts CLI / Piper | no narration | video renders silent; fix by installing either TTS |
| Whisper | no source-audio transcription | only matters when ingesting audio/video sources |
| LLM key | **hard stop** | no fallback — it is the one true requirement |

Exit-code honesty: `automedia doctor` exits 1 when **any** row is missing,
even tools your tier never uses. Read the table; the exit code is the strict
view, the tier table above is the honest minimum.

---

## Step 3 — Configure

One command walks all 8 config steps (writes plain YAML under `~/.automedia/`,
re-runnable per step with `--step <name>`):

```bash
automedia onboard start
# non-interactive minimal alternative:
automedia init --template minimal
```

| Sub-step | Writes | Human needed? |
|---|---|---|
| 0 (preflight) | nothing — prints detected OS + missing media tools | no |
| 1 llm | `model_config.yaml` | **yes — the API key** (or set `AUTOMEDIA_LLM_API_KEY`) |
| 2 brand | `brand-profile.yaml` | **yes — voice/CTA taste** |
| 3 pipeline | `config.yaml` (mode + tracks) | decide the tier (Step 1) |
| 4 platforms | `config.yaml` (platforms) | which platforms you actually use |
| 5 hitl | `hitl/active_preset.yaml` | how often a human reviews |
| 6 cron | `cron/overrides.yaml` | optional |
| 7 omni | `omni_config.yaml` | optional |
| 8 prompts | `overrides/prompts/` | optional |

### Enabling the video engine (do not skip this if you chose a Video tier)

The runtime switch for video is the **mode** (`video_only`, `short-video`, or
`auto`), plus the engine being installed:

- mode `video_only` / `short-video`: video track always runs; without
  hyperframes+Chrome you get the ffmpeg static-slideshow fallback, and V gates
  run against that artifact.
- mode `auto`: video is produced only when the target platforms want
  multimedia.
- `automedia run` tells you explicitly when video QA is limited
  ("Install HyperFrames for full video QA, or use --mode text_only") — video
  gates never fail silently; they report `skipped` with the reason in the
  gate report.
- The `pipeline.{text,image,video,audio}.enabled` keys written by this wizard
  are **display/onboarding metadata**; the runtime gates media on the mode.
- Point image generation at a remote ComfyUI with
  `engines.image.comfyui.{host,port,protocol}` — see
  [hardware-and-remote-engines](docs/user/hardware-and-remote-engines.md).

---

## Step 4 — Verify, then first run

```bash
automedia doctor                     # audit (exit 1 = some row missing, see Step 2)
automedia run --topic "your topic" --mode text_only
```

Agent judgment: the first run should be `text_only` even on a Video-tier
machine — it proves LLM + gates + HITL wiring with zero media risk. Then
re-run in the target mode.

| Symptom | Diagnosis | Fallback |
|---|---|---|
| `No API key for provider` | Step 1 not done | set `AUTOMEDIA_LLM_API_KEY` |
| run ends `awaiting_review` | **normal** — a gate paused for the human | Step 5 |
| run ends `partial` with skipped V gates | video artifacts absent (tier/tooling) | read the gate report reasons; upgrade tier or accept text mode |
| ComfyUI row ✗ but images render | Pillow fallback took over | fine — install ComfyUI for generated art |

Project output lands under `AUTOMEDIA_PROJECTS_DIR` (default `projects/`):
drafts, gate reports, media artifacts.

---

## Step 5 — Where the human directs (HITL map)

These are the **only** places AutoMedia stops for a person. Agents: surface
them proactively; humans: this is your whole job description.

| Checkpoint | Why a human | How |
|---|---|---|
| LLM API key | secret entry | paste into env / `automedia onboard start --step llm` |
| Brand profile | taste, tone, CTA principles | `automedia onboard start --step brand` |
| H0 review gate | approve/reject the draft before publishing | `automedia hitl` (CLI) or `review_decision` (MCP) |
| Director-mode approvals | gate-by-gate approval | `approve_gate` / `reject_gate` / `get_pending_approvals` (MCP) |
| Publishing | credentials + automation level per brand | `automedia account connect`, then `automedia distribute` |
| Archiving | red line: `--force` is human-only | `automedia archive` (force requires the human) |

Automation levels per brand decide how much of this still asks: see
[hitl-framework](docs/user/hitl-framework.md).

---

## One-command minimal path (copy-paste)

Agent or human — this produces a real, gate-checked draft with **no media
dependencies and nothing to install except Python**:

```bash
pip install -e ".[openai,rich]"
export AUTOMEDIA_LLM_PROVIDER=deepseek
export AUTOMEDIA_LLM_MODEL=deepseek-chat
export AUTOMEDIA_LLM_API_KEY=sk-your-key-here     # ← the one human secret
export AUTOMEDIA_DEFAULT_MODE=text_only
automedia run --topic "为什么本地小模型适合私有部署" --mode text_only
```

`automedia doctor` before the run is recommended but not required for this
path — the pipeline itself reports anything it genuinely cannot do.

---

## Where to go next

- Agent: [AGENTS.md](AGENTS.md) is your map; [docs/dev/agent-reference.md](docs/dev/agent-reference.md)
  is the deep reference; MCP setup in [docs/user/mcp-setup.md](docs/user/mcp-setup.md).
- Human: workflow guides in [docs/skills/](docs/skills/) (pipeline, batch,
  distribution), CLI reference in [docs/user/cli-reference.md](docs/user/cli-reference.md).
- Restricted hardware / remote engines:
  [docs/user/hardware-and-remote-engines.md](docs/user/hardware-and-remote-engines.md).
- Windows/WSL: [docs/user/windows-deployment.md](docs/user/windows-deployment.md).
