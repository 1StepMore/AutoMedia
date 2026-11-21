# Run summary — 2026-11-22 code-side Windows shift

Bench: main@80fd049f (three PRs merged this shift: #614 #615 #616).

## What landed (each via its own PR, squash, DCO, CI fully green)

- **#614** fix(win32) — #564 rollback-behavior scenario rewritten portable
  (${AUTOMEDIA_PROJECTS_DIR} rooting + runtime env reads, `--yes` flag on
  `automedia rollback`, bare `automedia` → `sys.executable -m automedia` in
  CLIAdapter, Windows-guard portable-module allowlist). DoD: the scenario
  runs 4/4 exit 0 on native Windows. The rollback CLI leaf retired from
  registration_only.yml (T-05).
- **#616** fix(validation) — #566 root cause PROVEN by reproduction (two
  shapes, native Windows): the night harness exported
  `AUTOMEDIA_PROJECTS_DIR='${AUTOMEDIA_PROJECTS_DIR}'`; the sandbox
  caller-env trust branch never expandvars'd caller values, so the literal
  reached scenario steps (one-pass expandvars leaves the embedded reference)
  and the run_pipeline daemon thread (env_lookup). Fix: expand caller values,
  raise SandboxEnvError BEFORE any dir is created when an unresolved
  reference remains. Guard tests ×4. The env-gate skip explains why the
  unset-key rerun could not reproduce.
- **#615** feat(gates) — #609 wiring (owner decision): G4/G5 execute on the
  wechat publish path via `gates/publish_gate_wiring.py` at the L1 layer
  (mcp publish_content / distribute_to_platforms / cron helpers, wechat
  targets only), stop-mode, credential-free. Two run-tested lifecycle
  scenarios claim them; library 163 → 165; **`automedia validate coverage`
  → Gates 33/33, unreachable ∅** (verified on main@80fd049f).
  Consequential fixture/pin updates: distribution-integration +
  publish-log-wiring fixtures checklist-compliant; l1 scenario seed
  compliant; stale pins in test_coverage / test_gate_input_reachability /
  test_w4_surface updated.

## Coverage truth on main (this shift's headline)

```
Gates: declared=33 used=33 covered=33 missing=0 boundary_only=0 phantom=0
missing = 0 (excluding boundary-only, listed above)
```

#566 section — reproduction records: validation-runs/20261122-011900-105499
(experiment A) and validation-runs/20261122-012518-317853 (experiment B, exact
match of the issue's artifact).

## piper vs V5 (the TTS-blocked cells' audio half)

Local piper voice (zh_CN-huayan-medium ONNX via hf-mirror, 63 MB) through the
shipped V5Mp3VsSrt gate over a real 17.5 s narration:

```
V5 passed: True
cue_anchor_coverage True — all 5 cues anchored (worst cue 78% >= 45%)
whisper_vs_srt_diff — observation only: similarity 91.2%
```

piper is ALREADY slot #2 in the default `engines.tts.chain` (azure → piper →
edge-tts); installing `piper-tts` + `AUTOMEDIA_PIPER_MODEL_PATH` is enough —
no Azure key needed for the gate criterion. The previous shift's
blocked:missing-dep(high-bitrate-tts) classification is thereby resolved at
the audio layer.

## Remaining blocks (honest denominators, unchanged in kind)

1. **blocked:llm-endpoint-unstable(win32)** — auto-journey (and any LLM-gated
   real-run cell): the xf-yun spark endpoint's CW requests die with
   APITimeoutError at ~54 s on this machine's network path (6+ occurrences
   today, deterministic signature, 3 attempts per the walk rule; the WSL side
   recorded 0). Only a stable endpoint / better network path fixes it —
   owner resource.
2. **blocked:missing-dep(video-engine)** — short-video-journey /
   video-only-journey honestly unconfigured on win32 (EXPECT-flag contract:
   no working video engine on this machine).
3. **blocked:missing-dep(comfyui / orf / bun)** — image-carousel-journey,
   produce-carousel, agent-user-lifecycle-journey, format-output-contract,
   orf-format-output-happy.
4. **unconfigured(owner-only)** — publish-draft-only-real-adapters (21 real
   platform credentials).
5. **produce-audio** — /tmp-pinned WSL-side cell (portability fix candidate
   for the next shift; on WSL the piper recipe above applies).

Matrix state recorded this shift: 165/165 statused, 150 passed / 5 failed /
6 unconfigured / 3 partial-pass / 1 recovered; hard 10/10; nightly_gap
exit 0; gates 33/33 unreachable=0.
