# GAP Register — the single source of truth for open gaps

**Status: living document.** This register is the *only* place where the
project's current gap state is tracked. The dated audit reports listed in the
[Snapshots ledger](#snapshots-ledger) remain frozen as historical evidence —
they are never refreshed (doc-update-audit-20261029 L5 convention) and their
findings are inherited *here*, deduplicated and re-adjudicated.

When any audit, plan, or issue identifies a gap, add or update a row here
instead of writing a new report. Close rows with evidence (commit, scenario,
command output), not with optimism.

## Row schema

| Field | Meaning |
|---|---|
| ID | Stable identifier; never renumber, retire instead |
| 首见 (origin) | Earliest snapshot/issue that recorded the gap |
| 状态 | `open` · `mitigated`（登记能力债/显式降级，属合规状态） · `dormant`（裁决休眠，有恢复条件） · `resolved`（附证据） · `wont-fix`（裁决不做） |
| 证据 | Commit / file:line / scenario / command that proves the current state |

**Numbers are never stored here.** LOC, test counts, scenario counts and the
like drift; the derived truth lives in `scripts/check-doc-consistency.py`.

---

## GAP-CAP — capability supply

| ID | Gap | 首见 | 状态 | 证据 / 处置 |
|---|---|---|---|---|
| GAP-CAP-1 | V0/V1/V3/V4/V6 have no honest producer inside the repo: the gates report `skipped` with an explicit reason instead of inspecting fabricated inputs. Registered capability debt. | capability-gap-20260915 §2 → health-20260917 P0-1 → codebase-audit-20261022 P0-1 → NIGHTLY #193 | **mitigated**（登记债） | `runner.py` media stage deliberately leaves producer keys unwritten; `_result.py` `missing_input_result` records the skip reason. Ownership: NIGHTLY 三轨 DoD / `scripts/nightly_gap.py`. Full fix lands with the video-engine work (GAP-PROD-1). |
| GAP-CAP-2 | Audio pipeline is an island: TTS/ASR only run inside the video track; no standalone audio artifact mode. | capability-gap-20260915 §2 | **open** | No standalone audio mode exists in `MODE_GATE_NAMES`. |
| GAP-CAP-3 | G4/G5 are registered but intentionally run in no preset (open-core tier boundary). | capability-gap-20260915 §5 | **mitigated**（有意开放核） | `gate_plan.py` header documents the intent. |

## GAP-PROD — productization gaps (user-facing, tracked as GitHub issues)

| ID | Gap | 首见 | 状态 | 证据 / 处置 |
|---|---|---|---|---|
| GAP-PROD-1 | Video engine output quality: single static text-card scene; no multi-scene / real motion / image composition; short-video mode V gates skip silently when no artifact is produced. | issue #351 | **resolved** (2026-11-04) | Both tracks shipped: hyperframes multi-scene motion-grammar templates + narration-aligned timeline (`pipelines/video_timeline.py`, E2E: 4 scenes h264/1080p/30fps/aac 21.27s vs narration 21.24s, frame diff 8.4-13.4); remotion engine (`video_remotion.py`, WSL renderer, engine selection `engines.video.chain: [remotion, hyperframes]`, E2E: 21.87s aac); explicit video_engine_unavailable/render_failed gate-report notes; selection guide docs/user/video-engines.md. |
| GAP-PROD-2 | Agent-facing executable onboarding (system ID, dependency tiers, HITL map, minimal path). | issue #352 | **resolved** (2026-11-04) | `ONBOARDING.md` (root); `automedia onboard` gained a preflight (OS detect + media-tool awareness) and mode→dependency hints in step 3; linked from README / docs/index / agent-reference / AGENTS.md. |
| GAP-PROD-3 | Hard platforms have no publish path: no browser-automation dependency (playwright/patchright), Xiaohongshu adapter is manual-only `not_implemented`; no Easy/Hard capability matrix drives routing/docs. | issue #353 | **resolved** (2026-11-04) | `adapters/platforms/xiaohongshu_browser.py` (Playwright, storage_state session, single-attempt, stops before publish confirmation → `ready_for_confirmation`); `login-capture` feeds the session; live E2E: form filled (title/body/1 image) + screenshot, publish never clicked; `platforms.xiaohongshu.publish_mode: manual\|browser` (default manual); matrix: docs/user/platform-capability-matrix.md. |
| GAP-PROD-4 | Account ops UX: store/auth layers exist (AES-256-GCM, api_key/cookie/oauth2), but no `account add/rotate/remove` surface, no login-state capture flow, no master-key lifecycle doc. | issue #354 | **resolved** (2026-11-04) | `account add/rotate/remove` (+ `registry.rotate_credentials` keeping identity); `login-capture` (from #353 groundwork) captures storage_state; master-key lifecycle documented in docs/user/account-management.md (generation/backup/loss=unrecoverable/rotation=export-reimport); real-store test proves ciphertext-at-rest and no plaintext echo. |
| GAP-PROD-5 | Platform prompts cover 10 platform dirs while 19 publishers exist; weibo/kuaishou/toutiao/baijiahao/juejin/facebook/instagram/medium/reddit/wordpress fall back to the generic Chinese social-media template. | issue #355 | **resolved** (2026-11-04) | 10 platform triplets added under `prompts/platforms/` (content_writer + copy_review_g2 + humanizer_g1); `test_platform_variants_carry_hard_constraint` updated 10 → 20; README/glossary/developer-guide counts synced. |
| GAP-PROD-6 | Commercial TTS provider (Azure et al.) missing; edge-tts free endpoint is flaky (403s), piper is local-only; no provider fallback chain across vendors. | issue #356 | **resolved** (2026-11-04) | `engines/implementations/tts_azure.py` (Speech REST over httpx, no SDK; speech_friendly_text; 401/403/429 explicit errors); `engines.tts.chain: [azure, piper, edge-tts]` skips transparently without credentials; live smoke: eastasia 200 OK, 18.7 KB mp3. |
| GAP-PROD-7 | Restricted-hardware path undocumented; doctor hard-probed `127.0.0.1:8188` and misreported remote ComfyUI; several engine-direct env vars undocumented. | issue #357 | **resolved** (2026-11-04) | `docs/user/hardware-and-remote-engines.md` (tier minimums, degradation switches, remote-engine matrix); doctor now probes `engines.image.comfyui.{host,port,protocol}` (`tests/test_doctor/test_comfyui_endpoint.py`); `.env.example` documents ComfyUI endpoint envs + engine-direct vars. |
| GAP-PROD-8 | No GUI-less human entry point: CLI-only; no wizard-level TUI, no local Web UI. | issue #358 | **resolved** (2026-11-04) | `automedia ui` (FastAPI, [webui] extra, loopback-only single page): config+doctor view, one pipeline run with live PipelineProgress, project results, account metadata (secrets redacted, no auth — documented as local-only). Docs: docs/user/web-ui.md. |
| GAP-PROD-9 | GAP documentation fragmented across dated audits. | issue #359 | **resolved** (2026-11-04) | This register. |
| GAP-PROD-10 | No credential-free demo/sample mode producing a complete sample output for presentations and smoke tests. | issue #360 | **open** | Requires an offline LLM stub path + synthetic fixture content; must respect red line 4 (synthetic data only). |

## GAP-SEC — security

| ID | Gap | 首见 | 状态 | 证据 / 处置 |
|---|---|---|---|---|
| GAP-SEC-1 | MCP file-ops allowlist self-enforced (fail-open risk): call sites were patched to `_require_allowed`, but the default allowlist directory mismatch (A9) remains conditional. | project-analysis-20261029 §4.3.1 → infrastructure-audit-20261030 §3.3.6 / A9 | **open** (A9 remainder) | `tools_distribution.py`, `effects/mcp.py` now enforce; A9 deferred pending the condition that triggers it. |
| GAP-SEC-2 | Credential store KDF is a single SHA-256 over `AUTOMEDIA_MASTER_KEY`; no keyring integration by default; no documented backup/recovery story. | project-analysis-20261029 §4.3 | **open** | `accounts/store.py:13` (SHA-256 → AES-256 key). Master-key lifecycle docs land with GAP-PROD-4. |

## GAP-ARCH — architecture

| ID | Gap | 首见 | 状态 | 证据 / 处置 |
|---|---|---|---|---|
| GAP-ARCH-1 | `runner.py` god-module (~2.3k lines): RFC-001 deep-module split is **Accepted** but not yet executed. | health-20260917 §七-5 → codebase-audit-20261022 §5.3 → project-analysis-20261029 §4.1 → RFC-001 | **open** | `deep-module-rfc-001.md` Status: Accepted (2026-10-29); `check_rfc_aging.py` guards the RFC itself, execution is the remaining work. |
| GAP-ARCH-2 | D/P gates share near-identical scaffolding with the main gates (dedup candidate, blocked by GAP-ARCH-1). | codebase-audit-20261022 P3-1 | **open** | Explicitly deferred ("明示不动") until the runner split. |

## GAP-HITL — director chain

| ID | Gap | 首见 | 状态 | 证据 / 处置 |
|---|---|---|---|---|
| GAP-HITL-1 | `hitl preset --set` writes config the runner never reads: `runner.py` still hardcodes `"director" if director else "automated"`. (T2-4 remainder) | infrastructure-audit-20261030 矩阵#12 | **open** | `runner.py:1218`; doc side annotated "display and onboarding checks only" in hitl-framework.md — runtime wiring pending. |
| GAP-HITL-2 | Director-approval MCP triad (`approve_gate`/`reject_gate`/`get_pending_approvals`) is reserved/not wired — ruled dormant with a resume condition, not a defect. | infrastructure-audit-20261030 矩阵#11 → remediation A3 | **dormant** | `mcp/tools/approval.py` header declares the reservation. |

## GAP-DOC — documentation & gate blind spots

| ID | Gap | 首见 | 状态 | 证据 / 处置 |
|---|---|---|---|---|
| GAP-DOC-1 | Deep user/dev docs and `.opencode` skills content are outside the doc-consistency gate — drift there is caught only by manual audit. | doc-update-audit-20261029 §五 | **open** | §五 checklist absorbed as structural assertions for the *covered* set (`check-doc-consistency.py:594`); extending coverage is the remaining work. |
| GAP-DOC-2 | NIGHTLY.md living section stale (last entry 2026-10-21). | doc-update-audit-20261029 L4 | **open** | Owner task: append a new living-section entry; snapshots stay frozen. |

## GAP-TEST — validation depth

| ID | Gap | 首见 | 状态 | 证据 / 处置 |
|---|---|---|---|---|
| GAP-TEST-1 | Windows platform-failed tests (dozens, incl. chrome-remediation and symlink allowlist tests) fail for OS reasons, not regression reasons; triage/dispatch (skip-if-windows or fix) is open. | infrastructure-audit-20261030 §4.2 | **open** | Reproduced 2026-11-04: `test_doctor.py::test_non_wsl_headless_failure_uses_headless_deps`, `test_mcp` symlink/allowlist tests fail on win32 before any local change. |
| GAP-TEST-2 | Validation layer evidence depth: threshold waivers gate the matrix, but per-scenario assertion depth and coverage evidence remain thin (A6 completed 5 scenarios; the rest follow). | infrastructure-audit-20261030 §4.2 | **open** | Scenario depth work continues under the validation framework. |
| GAP-TEST-3 | `record_md5` cross-process race (T2-1 remainder): per-process write is atomic (tmp+rename), concurrent processes can still interleave. | infrastructure-audit-20261030 T2-1 | **open** | `core/md5_tracker.py` atomicity fixed; cross-process interleaving remains. |

## GAP-OPEN — open-core & boundary discoverability

| ID | Gap | 首见 | 状态 | 证据 / 处置 |
|---|---|---|---|---|
| GAP-OPEN-1 | CLI `distribute` vs MCP `distribute_content` share a name with different semantics (D-gates vs direct PublishEngine); surfaces now declare the boundary, a rename to retire the ambiguity is deferred. | infrastructure-audit-20261030 §3.3.1 → remediation A2 | **open** (rename half) | Doc/boundary declaration shipped (#346); alias retirement pending deprecation window. |
| GAP-OPEN-2 | MCP server introspection (A8) deferred; deprecated-alias layering tax (3 layers per renamed tool) remains until A8 lands. | infrastructure-audit-20261030 §3.3.8, A8 | **dormant** | Resume condition: next MCP surface change. |
| GAP-OPEN-3 | `automedia doctor` exits 1 when *engine-optional* rows (ComfyUI service, upscale model) are missing — strict contract, but hostile to text-only setups on purpose-restricted machines. | 2026-11-04 (hardware docs work) | **open** | `commands/doctor.py:133/197`; documented in hardware-and-remote-engines.md §4; fix = per-row severity or `--mode-aware` flag. |
| GAP-OPEN-4 | No remote-engine proxy for local-only engines (piper / whisper / hyperframes): restricted hardware can only degrade, not delegate. | issue #357 discussion | **open** | ComfyUI (image) is remote-capable today; TTS has a cloud vendor; ASR/video have no remote path. |

## GAP-HYGIENE — workspace hygiene

| ID | Gap | 首见 | 状态 | 证据 / 处置 |
|---|---|---|---|---|
| GAP-HYGIENE-1 | Test-directory sprawl (100+ dirs under `tests/`) and stale-comment drift (e.g. `p3_newsletter.py` claims "no newsletter-specific review prompt" while `prompts/platforms/newsletter/copy_review_g2.j2` exists). | codebase-audit-20261022 P5-1 → project-analysis-20261029 §4.6 | **open** | Counts drift — do not pin numbers here; sweep opportunistically. |

---

## Resolved register (evidence, kept for the audit trail)

Compressed — each row is fully told by its snapshot; listed here so the
deduplication is explicit. See the snapshots for detail.

| Origin item(s) | Resolution evidence |
|---|---|
| capability-gap-20260915 P0-1..P0-5 (LLM wiring, exit codes, collection persistence, report remediation) | Confirmed fixed by health-20260917 remediation-report; exit codes: `run.py:32,152` |
| health-20260917 P0-2 (fcntl/Windows), P1-1 (MCP auth + allowlist), P1-3 (cta_principles dead link) | `remediation-report-20260917.md` two-batch ✅ |
| codebase-audit-20261022 P0-2 (e2e not collected), P0-3 (resume_from placeholder), P0-4 (retry settings dead), V7 MD5 constructive-truth, P2-2 (RFC aging), P4-2 (README numbers) | e2e: `Makefile:32` + nightly.yml step + collection-guard test; resume: `runner.py:1344`; retries: `runner.py:1379,1426`; MD5: `runner.py:2138`; RFC: Accepted + `check_rfc_aging.py`; numbers: doc-consistency gate |
| doc-update-audit-20261029 H1–H9, M1, M2, M6, L2, L3 | Landing batch confirmed green by infrastructure-audit-20261030; doc-consistency exit 0 |
| project-analysis-20261029 §4.2.1 (md5 encoding/atomicity), §4.3.1 (allowlist call sites) | `core/md5_tracker.py:33,56`; `tools_distribution.py:96-98`, `effects/mcp.py:49` |
| infrastructure-audit-20261030 §3.3.3 (review_decision STALE), §3.3.6 (allowlist), 矩阵#23 (pool :memory:), 矩阵#35 (README red lines) | `mcp/tools/review.py:16`; remediation plan Track 2; matrix self-marked |

## Adjudications (contradictions between snapshots, settled)

1. **V-gate narrative.** codebase-audit-20261022 judged "gates that can no
   longer fail" a defect; NIGHTLY/owner rulings (#181/#193/#202) define
   *registered capability debt with explicit skip reasons* as compliant.
   **Ruling: the debt-ledger reading governs** (GAP-CAP-1); the audit's
   framing is historical.
2. **`features/` "dead weight".** codebase-audit-20261022 §5.2 called
   `features/` zero-call-site dead weight; project-analysis-20261029 §4.7
   refuted it (`_filter_gates_by_tier` → `check_tier` is live).
   **Ruling: project-analysis stands**; its correction note is part of the
   evidence chain.
3. **Development brief versions.** `AutoMedia开发简报.md` (v1) and
   `AutoMedia-development-brief-v2.md` coexist; v2 declares itself
   authoritative (canonical copy outside the repo). **Ruling: cite v2 only**;
   v1 stays frozen as history.
4. **Counts.** LOC/test/scenario numbers differ across snapshots (62,461 →
   71,608 over five reports). **Ruling: this register stores no counts**;
   derived values come from `scripts/check-doc-consistency.py`.

## Snapshots ledger (frozen inputs)

| Snapshot | Date | Role in the chain | Living-state ownership |
|---|---|---|---|
| `capability-gap-assessment-20260915.md` | 2026-09-15 | Ancestor capability assessment (private-deploy delivery lens) | → this register |
| `project-health-assessment-20260917.md` | 2026-09-17 | 12-dimension health score; re-audited capability P0s | → this register |
| `codebase-audit-20261022.md` | 2026-10-22 | Architecture/aesthetics/signal-honesty snapshot | → this register |
| `doc-update-audit-20261029.md` | 2026-10-29 | Doc drift audit; §五 became structural assertions | → this register |
| `project-analysis-20261029.md` | 2026-10-29 | Remediation sign-off + new findings | → this register |
| `infrastructure-audit-20261030.md` | 2026-10-30 | Agent-role × effectiveness audit; freshest open items | → this register |
| `AutoMedia-development-brief-v2.md` | 2026-09-15 | Sponsor direction brief (authoritative copy outside repo) | constraints source, not a gap list |
| `AutoMedia开发简报.md` | — | v1, superseded by v2 | frozen, do not cite |
| `plans/infrastructure-remediation-plan-20261030.md` | 2026-10-30 | Execution plan derived from infrastructure-audit §六 | execution log stays in that file |
| `plans/NIGHTLY.md` | living | Three-track DoD + living section (capability-debt consumer) | stays living in that file |

Maintenance rule: a new dated audit may be *written*, but its durable
findings must be merged here in the same change; otherwise the register stops
being the single source of truth.
