# Synthetic STANDARDS handbook — zero real data

Fixture counterpart of `scenarios/STANDARDS.md` (authored in W2-T1). The
format is pinned by the standards registry (W1-T3): a `## Standards` heading
followed by a Markdown table whose `Key` column holds the standard keys that
scenario steps cite via `standard:`. Key prefixes follow the plan's known
standards sources: founder-expectations F-numbers, evaluation-matrix dims,
gate names, and built-in check specs.

## Standards

| Key | Check type | Standard | Source doc | Clause |
| --- | --- | --- | --- | --- |
| founder-expectations.F01 | artifact_exists | F01 ever-green clause | docs/dev/founder-expectations.md | §8.3 |
| founder-expectations.F02 | non_empty | F02 no-lorem clause | docs/dev/founder-expectations.md | §8.3 |
| evaluation-matrix.dim1 | quality_spot_check | 8-dim matrix P0-P5 | docs/dev/evaluation-matrix-principles.md | §1 |
| evaluation-matrix.dim2 | quality_spot_check | 8-dim matrix P0-P5 | docs/dev/evaluation-matrix-principles.md | §1 |
| gate.G6 | gate_records_pass | gate registry + project info | docs/dev/developer-guide.md | Gate System |
| gate.V0 | gate_records_pass | gate registry + project info | docs/dev/developer-guide.md | Gate System |
| builtin.artifact_exists | artifact_exists | expect contract | docs/agent-tester-validation-guide.md | §2.3 |
| builtin.non_empty | non_empty | expect contract | docs/agent-tester-validation-guide.md | §2.3 |
| builtin.gate_records_pass | gate_records_pass | expect contract | docs/agent-tester-validation-guide.md | §2.3 |
| builtin.exit_code | exit_code | doctor/CLI contract | docs/agent-tester-validation-guide.md | §2.3 |
| builtin.data_has | data_has | tool return contract | docs/agent-tester-validation-guide.md | §2.3 |
| builtin.unconfigured | unconfigured | honesty rule §4 | docs/agent-tester-validation-guide.md | §4 |
| founder-expectations.F01 | artifact_exists | duplicate row — registry dedups | docs/dev/founder-expectations.md | §8.3 |
