# Agent-Tester Validation: Standards Handbook

This handbook maps every check type a validation scenario step can perform to
the governing standard it must be graded against. Scenario authors cite a
`standard:` key from the `Key` column below on every step; the loader
(`automedia.validation.loader`) rejects any step whose `standard:` is not a
known key here, so this table is the closed vocabulary for what counts as a
valid standard in this framework. Keys are stable and lowercase-hyphenated.

## Standards
| Key | Check type | Standard | Source doc | Clause | Status |
| --- | --- | --- | --- | --- | --- |
| founder-expectations.F01 | artifact_exists | F01 ever-green clause: a clean install must reach a first successful command, and `automedia doctor` must detect missing system deps; an `artifact_exists` proof presumes this baseline holds and the artifact was produced by a real run, never assumed | docs/dev/founder-expectations.md | F01 | referenced |
| founder-expectations.F02 | non_empty | F02 First Command: the first surface call must return visible, non-empty output (typer help for the CLI, `health_check`/tool manifest for the MCP server); a `non_empty` check asserts the response carries real content, not a stub | docs/dev/founder-expectations.md | F02 | referenced |
| evaluation-matrix.dim7 | quality_spot_check | Dimension 7 Security: score against S1-S8 (dependency audit, allowlist, credential encryption, secrets hygiene); a P0 here blocks shipping | docs/dev/evaluation-matrix-principles.md | ## 10. Security | referenced |
| founder-expectations.true-test | quality_spot_check | §8.3 The True Test: the founder goes from idea to publishable content in one sitting, no docs, no debugging; agent-verifiable T1-T10 checklist, PASS at 9/10 with T3 (topic to `draft.md`) mandatory | docs/dev/founder-expectations.md | §8.3 (T1-T10) | referenced |
| cli.doctor | exit_code, stdout | Doctor/CLI contract: `automedia doctor` lists every dependency with an installed/uninstalled status, exits 0 when all are present and 1 only when one is missing (typer.Exit code=1); `--json` output must be machine-readable | src/automedia/cli/commands/doctor.py, docs/user/cli-reference.md | ## `automedia doctor` | referenced |
| tool.contract | data_has | Tool return contract: every MCP tool returns a structured dict (PipelineResult for pipeline calls); `data_has` asserts the listed keys exist in the parsed response, and errors follow the structured `{"error": ...}` shape | src/automedia/mcp/server.py, docs/user/api-reference.md | ## PipelineResult (### Return Value) | referenced |
| artifact.glob-exists | artifact.glob-exists | A declared `artifact_glob` pattern must match at least one file under the step's artifact root; a glob that matches nothing is a failed artifact observation, never a silent pass | scenarios/README.md | Artifact glob assertions | referenced |
| media.video | media.video | A produced video artifact must exist, be decodable by `ffprobe`, carry a video stream, and satisfy the declared duration/bitrate/codec/frame-size thresholds | scenarios/README.md | Media assertions | referenced |
| media.audio | media.audio | A produced audio artifact must exist, be decodable by `ffprobe`, carry an audio stream, and satisfy the declared duration/bitrate/codec thresholds (image dimensions are ignored) | scenarios/README.md | Media assertions | referenced |
| media.image | media.image | A produced still image must be readable by Pillow, meet the declared width/height minimums, and satisfy `non_uniform` when the image must not be a flat fill | scenarios/README.md | Media assertions | referenced |
| media.carousel | media.carousel | A carousel artifact set must match `artifact_glob`, meet `min_count`, and have every image readable with consistent dimensions when `same_size` is declared | scenarios/README.md | Media assertions | referenced |
| text.article | text.article | A text/Markdown artifact must meet the declared paragraph, character, and heading thresholds measured by the read-only text probe | scenarios/README.md | Text assertions | referenced |
| subtitle.srt | subtitle.srt | An SRT artifact must contain the declared minimum cue count, non-overlapping cue timing when `monotonic` is asserted, and end within the referenced media duration when `within` is declared | scenarios/README.md | Subtitle assertions | referenced |
| quality.keyword-coverage | quality.keyword-coverage | The concatenated text of the declared artifacts must contain the required keywords at or above `min_ratio`; missing keywords are reported with the observed ratio | scenarios/README.md | Keyword coverage assertions | referenced |
| text.similarity | text.similarity | Produced text must match a declared reference file by normalized character-bigram similarity at or above `min_ratio`; the observed ratio is reported with the reference path | scenarios/README.md | Text similarity assertions | referenced |

> **Vocabulary status (plan A5, 2026-10-30):** this table now carries
> exactly the keys cited by the scenario library (15 keys, each marked
> `referenced`) — the vocabulary IS the citation set, pinned both ways by
> `test_real_handbook_matches_cited_keys`.  The 41 previously
> defined-unreferenced rows (every `gate.*`, `mode.*`, the other
> `evaluation-matrix.dim*`, `honesty.unconfigured`, and the reserved
> check-type keys) were retired to git history: zero scenarios cited
> them, and gate/mode coverage is declared per-scenario through the
> `proves_gates:` / `proves_modes:` headers (bound to the presets by the
> #99 reachability guard), not through standard-key citation.  Re-add a
> key only together with the first scenario that cites it.
