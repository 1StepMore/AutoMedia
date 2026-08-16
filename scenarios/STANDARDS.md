# Agent-Tester Validation: Standards Handbook

This handbook maps every check type a validation scenario step can perform to
the governing standard it must be graded against. Scenario authors cite a
`standard:` key from the `Key` column below on every step; the loader
(`automedia.validation.loader`) rejects any step whose `standard:` is not a
known key here, so this table is the closed vocabulary for what counts as a
valid standard in this framework. Keys are stable and lowercase-hyphenated.

## Standards

| Key | Check type | Standard | Source doc | Clause |
| --- | --- | --- | --- | --- |
| founder-expectations.F01 | artifact_exists | F01 ever-green clause: a clean install must reach a first successful command, and `automedia doctor` must detect missing system deps; an `artifact_exists` proof presumes this baseline holds and the artifact was produced by a real run, never assumed | docs/dev/founder-expectations.md | F01 |
| founder-expectations.F02 | non_empty | F02 First Command: the first surface call must return visible, non-empty output (typer help for the CLI, `health_check`/tool manifest for the MCP server); a `non_empty` check asserts the response carries real content, not a stub | docs/dev/founder-expectations.md | F02 |
| gate.pre-gate | gate_records_pass | pre-gate Topic Selection: topic validated before the pipeline runs; gate record must show passed | docs/dev/gate-failure-modes.md | pre-gate |
| gate.CW | gate_records_pass | CW Content Writing: draft written with inline SEO scoring; project info must record the CW gate pass | README.md | Gate System |
| gate.G0 | gate_records_pass | G0 Fact Check: claims verified against source material; the project info file must record this gate's pass (or a documented stop) for the record to count | docs/dev/gate-failure-modes.md | G0 |
| gate.G1 | gate_records_pass | G1 Humanizer: content must not read as AI-written (9-pattern evaluation); gate record must show passed | docs/dev/gate-failure-modes.md | G1 |
| gate.G2 | gate_records_pass | G2 Copy Review: copy passes the review checklist; gate record must show passed | docs/dev/gate-failure-modes.md | G2 |
| gate.G3 | gate_records_pass | G3 Brand CTA: brand call-to-action and voice requirements met; gate record must show passed | docs/dev/gate-failure-modes.md | G3 |
| gate.G4 | gate_records_pass | G4 WeChat Checklist: WeChat checklist requirements satisfied; gate record must show passed | docs/dev/gate-failure-modes.md | G4 |
| gate.G5 | gate_records_pass | G5 HTML Hard: HTML output passes the hard gate; gate record must show passed | docs/dev/gate-failure-modes.md | G5 |
| gate.G6 | gate_records_pass | G6 Tone Check: tone must match the brand profile; gate record must show passed | docs/dev/gate-failure-modes.md | G6 |
| gate.V0 | gate_records_pass | V0 Lint: video assets pass structural lint; gate record must show passed | docs/dev/gate-failure-modes.md | V0 |
| gate.V1 | gate_records_pass | V1 Vision QA: visual output passes vision quality review; gate record must show passed | docs/dev/gate-failure-modes.md | V1 |
| gate.V2 | gate_records_pass | V2 Pre-Send Whisper: whisper transcription verified before send; gate record must show passed | docs/dev/gate-failure-modes.md | V2 |
| gate.V3 | gate_records_pass | V3 Content Semantic: output semantics match the source material; gate record must show passed | docs/dev/gate-failure-modes.md | V3 |
| gate.V4 | gate_records_pass | V4 TTS Brand Asset: TTS audio uses brand assets; gate record must show passed | docs/dev/gate-failure-modes.md | V4 |
| gate.V5 | gate_records_pass | V5 MP3 vs SRT: audio and subtitle tracks align; gate record must show passed | docs/dev/gate-failure-modes.md | V5 |
| gate.V6 | gate_records_pass | V6 Subtitle Rendering: subtitles rendered correctly; gate record must show passed | docs/dev/gate-failure-modes.md | V6 |
| gate.V7 | gate_records_pass | V7 Six-Step Hard: output satisfies the six-step hard check; gate record must show passed | docs/dev/gate-failure-modes.md | V7 |
| gate.H0 | gate_records_pass | H0 Human Review: content is reviewed and approved (or rejected) by a human; record must show the HITL outcome | docs/dev/gate-failure-modes.md | H0 |
| gate.L1 | gate_records_pass | L1 Publish Log Schema: publish log entry conforms to the schema; gate record must show passed | docs/dev/gate-failure-modes.md | L1 |
| gate.L2 | gate_records_pass | L2 Archive Validation: archive integrity validated; gate record must show passed | docs/dev/gate-failure-modes.md | L2 |
| gate.L3 | gate_records_pass | L3 Platform Integrity: platform records stay consistent; gate record must show passed | docs/dev/gate-failure-modes.md | L3 |
| gate.L4 | gate_records_pass | L4 Translation Quality: translated content meets the quality threshold; gate record must show passed | docs/dev/gate-failure-modes.md | L4 |
| gate.D1 | gate_records_pass | D1 WeChat Distribution: platform-specific rewrite contract satisfied; gate record must show passed | docs/dev/gate-failure-modes.md | D1 |
| gate.D2 | gate_records_pass | D2 Twitter/X Distribution: platform-specific rewrite contract satisfied; gate record must show passed | docs/dev/gate-failure-modes.md | D2 |
| gate.D3 | gate_records_pass | D3 Zhihu Distribution: platform-specific rewrite contract satisfied; gate record must show passed | docs/dev/gate-failure-modes.md | D3 |
| gate.D4 | gate_records_pass | D4 Xiaohongshu Distribution: platform-specific rewrite contract satisfied; gate record must show passed | docs/dev/gate-failure-modes.md | D4 |
| gate.D5 | gate_records_pass | D5 Bilibili Distribution: platform-specific rewrite contract satisfied; gate record must show passed | docs/dev/gate-failure-modes.md | D5 |
| gate.D6 | gate_records_pass | D6 YouTube Distribution: platform-specific rewrite contract satisfied; gate record must show passed | docs/dev/gate-failure-modes.md | D6 |
| gate.D7 | gate_records_pass | D7 TikTok Distribution: platform-specific rewrite contract satisfied; gate record must show passed | docs/dev/gate-failure-modes.md | D7 |
| gate.P1 | gate_records_pass | P1 WeChat Repurpose: repurpose sub-pipeline output produced; gate record must show passed | docs/dev/gate-failure-modes.md | P1 |
| gate.P2 | gate_records_pass | P2 Twitter/X Repurpose: repurpose sub-pipeline output produced; gate record must show passed | docs/dev/gate-failure-modes.md | P2 |
| gate.P3 | gate_records_pass | P3 Newsletter Repurpose: repurpose sub-pipeline output produced; gate record must show passed | docs/dev/gate-failure-modes.md | P3 |
| gate.P4 | gate_records_pass | P4 Bilibili Repurpose: repurpose sub-pipeline output produced; gate record must show passed | docs/dev/gate-failure-modes.md | P4 |
| mode.auto | gate_records_pass | auto mode: full pipeline pre-gate → CW → G0-G6 → V0-V7 → H0 → L1-L4 ran to completion; the project info file records the mode's gate passes | src/automedia/pipelines/runner.py | _MODE_MAP |
| mode.text_only | gate_records_pass | text_only mode: CW → G0-G6 → H0 → L1-L4 ran to completion; the project info file records the mode's gate passes | src/automedia/pipelines/runner.py | _MODE_MAP |
| mode.text_with_cover | gate_records_pass | text_with_cover mode: CW → G0-G6 → H0 → L1-L4 (with cover) ran to completion; the project info file records the mode's gate passes | src/automedia/pipelines/runner.py | _MODE_MAP |
| mode.video_only | gate_records_pass | video_only mode: V0-V7 → L1-L4 ran to completion; the project info file records the mode's gate passes | src/automedia/pipelines/runner.py | _MODE_MAP |
| mode.qa_only | gate_records_pass | qa_only mode: G0, G2, G3, V1, V6 ran to completion; the project info file records the mode's gate passes | src/automedia/pipelines/runner.py | _MODE_MAP |
| mode.image-carousel | gate_records_pass | image-carousel mode: CW → G0-G6 → L1-L4 (image carousel) ran to completion; the project info file records the mode's gate passes | src/automedia/pipelines/runner.py | _MODE_MAP |
| mode.social-thread | gate_records_pass | social-thread mode: CW → G0-G6 → L1-L4 (social thread) ran to completion; the project info file records the mode's gate passes | src/automedia/pipelines/runner.py | _MODE_MAP |
| mode.short-video | gate_records_pass | short-video mode: pre-gate → CW → G0-G6 → V0-V7 → H0 → L1-L4 (short video) ran to completion; the project info file records the mode's gate passes | src/automedia/pipelines/runner.py | _MODE_MAP |
| mode.repurpose | gate_records_pass | repurpose mode: pre-gate → CW → G0-G6 → V0-V7 → H0 → L1-L4 → P1-P4 ran to completion; the project info file records the mode's gate passes | src/automedia/pipelines/runner.py | _MODE_MAP |
| evaluation-matrix.dim1 | quality_spot_check | Dimension 1 Agent Readiness: score against AR1-AR7 (annotations, pre-commit, `__all__`, type coverage, test health); P0 blocks the dimension to 0, P1 caps at 5 | docs/dev/evaluation-matrix-principles.md | dim1 (§1 P0-P5) |
| evaluation-matrix.dim2 | quality_spot_check | Dimension 2 Production Readiness + Observability: score against PR1-PR13 + O1-O4 (deploy, logging, health, resume); P0 blocks to 0, P1 caps at 5 | docs/dev/evaluation-matrix-principles.md | dim2 (§1 P0-P5) |
| evaluation-matrix.dim3 | quality_spot_check | Dimension 3 Documentation (Quality + Accuracy): score against DC1-DC7 + DA1-DA5; stale docs that mislead agents are P0/P1 | docs/dev/evaluation-matrix-principles.md | dim3 (§1 P0-P5) |
| evaluation-matrix.dim4 | quality_spot_check | Dimension 4 Robustness: score against RB1-RB8 (bare excepts, retry, structured logging, validation); P0 blocks to 0, P1 caps at 5 | docs/dev/evaluation-matrix-principles.md | dim4 (§1 P0-P5) |
| evaluation-matrix.dim5 | quality_spot_check | Dimension 5 Design: score against DS1-DS8 (module count, ABC/Protocol, circular imports, deps); P0 blocks to 0, P1 caps at 5 | docs/dev/evaluation-matrix-principles.md | dim5 (§1 P0-P5) |
| evaluation-matrix.dim6 | quality_spot_check | Dimension 6 End-to-End Integration: score against E1-E8 (doctor, help, server start, pipeline runs); any system-level crash is P0 | docs/dev/evaluation-matrix-principles.md | dim6 (§1 P0-P5) |
| evaluation-matrix.dim7 | quality_spot_check | Dimension 7 Security: score against S1-S8 (dependency audit, allowlist, credential encryption, secrets hygiene); a P0 here blocks shipping | docs/dev/evaluation-matrix-principles.md | dim7 (§1 P0-P5) |
| evaluation-matrix.dim8 | quality_spot_check | Dimension 8 Performance & Cost: score against PC1-PC8 (token cost, wall-clock, memory, disk); P0 blocks to 0, P1 caps at 5 | docs/dev/evaluation-matrix-principles.md | dim8 (§1 P0-P5) |
| founder-expectations.true-test | quality_spot_check | §8.3 The True Test: the founder goes from idea to publishable content in one sitting, no docs, no debugging; agent-verifiable T1-T10 checklist, PASS at 9/10 with T3 (topic to `draft.md`) mandatory | docs/dev/founder-expectations.md | §8.3 (T1-T10) |
| cli.doctor | exit_code, stdout | Doctor/CLI contract: `automedia doctor` lists every dependency with an installed/uninstalled status, exits 0 when all are present and 1 only when one is missing (typer.Exit code=1); `--json` output must be machine-readable | src/automedia/cli/commands/doctor.py, docs/user/cli-reference.md | ## automedia doctor (doctor.py:130,185) |
| tool.contract | data_has | Tool return contract: every MCP tool returns a structured dict (PipelineResult for pipeline calls); `data_has` asserts the listed keys exist in the parsed response, and errors follow the structured `{"error": ...}` shape | src/automedia/mcp/server.py, docs/user/api-reference.md | ## PipelineResult (### Return Value) |
| honesty.unconfigured | unconfigured | Honesty rule: a missing credential or precondition is recorded as `unconfigured` with its reason, never silently skipped and never graded GREEN; a suite with unconfigured scenarios cannot reach full sign-off | docs/agent-tester-validation-guide.md | §4.2 |
