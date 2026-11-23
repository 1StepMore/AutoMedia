# Threshold Waiver Ledger

> **Rule (plan A7, 2026-10-30):** every change to a scenario's numeric
> assertion threshold — the closed field set snapshotted by
> `scripts/snapshot_scenario_thresholds.py` (`min_passing`, `pass_ratio`,
> `expect.min_score`, `expect.artifact_size_min`, `expect.text.min_*`,
> `expect.subtitle.min_cues`, `expect.media.min_*`/`max_duration_s`/
> `min_bitrate_kbps`, `expect.keyword_coverage.min_ratio`,
> `expect.text_similarity.min_ratio`) — MUST append one row to this ledger
> in the same PR, alongside regenerating
> `scenarios/baseline/threshold-snapshot.json`.  Raising a threshold is a
> tightening and needs no waiver by the same rule, but recording it is
> still recommended: the ledger is the director's adjudication trail.
>
> `tests/test_validation/test_threshold_snapshot.py` enforces regeneration;
> the waiver rows are reviewed by humans (they cannot be derived).

| Date | Scenario | Step | Field | Old → New | Reason | Decided by |
|------|----------|------|-------|-----------|--------|------------|
| 2026-10-27 (backfilled 2026-10-30) | produce-article | produce the article | `expect.text.min_chars` | 800 → 500 | The first committed-fixture run measured 724 chars (RED, `validation-runs/20261027-183426-293353`); the threshold was lowered to 500 without a recorded decision. Backfilled here as the honest record — the original adjustment had no waiver (infrastructure-audit-20261030 §4.2.2). | backfilled; original adjudicator unrecorded |
| 2026-11-23 | produce-video | video properties | `expect.media.min_width/min_height` → `min_long_edge/min_short_edge` | per-axis → orientation-agnostic (1920x1080 floor kept) | The scenario asserted landscape 1920x1080 while the product picks orientation from the platform media spec (`runner.py:2004-2016`, #378): a douyin run ships 1080x1920, so the old assertion could never pass for portrait output. Replaced with long-edge ≥1920 / short-edge ≥1080, which keeps the 1080p floor without pinning orientation. No threshold was lowered. | Hermes Agent (code profile) |
