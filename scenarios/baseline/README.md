# Baseline

`2026-08-14-preflight.json` is the committed baseline run record of the
validation library against the current product on a clean env (no
`AUTOMEDIA_LLM_API_KEY`). Originally the W2-T4 pre-flight baseline (11
scenarios), it was regenerated as a full-suite baseline (2026-09-01, 105
scenarios: 78 passed / 27 unconfigured / 0 failed) after the 9 hard-safety
scenarios landed (Red Line 8 archive refusal, `get_config` secret redaction,
and the 7 fail-closed control boundary probes). A hard scenario whose run
status is not `passed` blocks the suite, so this record's
`hard_safety_violations: []` / `blocked: false` is the green guarantee. The
`validate diff` / `validate matrix` tooling resolves THIS file as the default
baseline.

## Lost RED baseline (recorded — not recoverable)

The original RED pre-flight baseline no longer exists. The 2026-09-01
regeneration overwrote it in place with
`json.dump(r, open('scenarios/baseline/2026-08-14-preflight.json', 'w'))` — a
non-exclusive write that truncated the prior RED record. There is no copy to
restore: the loss is permanent (gap R-10). Under the honesty rule "RED first —
a GREEN with no recorded RED is suspect", the current all-GREEN baseline must
not be read as if that earlier RED had been preserved. Every regeneration now
goes through `automedia.validation.persist.persist_baseline`, whose
`O_CREAT|O_EXCL` write refuses to overwrite, so this cannot recur.

## Regeneration (refuses to overwrite)

Regeneration runs the whole library and writes a NEW baseline file with
exclusive create. Point `baseline_path` at a new name each time; an existing
path raises `PersistError` ("refusing to overwrite") and is left untouched:

```
env -u AUTOMEDIA_LLM_API_KEY AUTOMEDIA_PROJECTS_DIR=/tmp/automedia/baseline-projects \
  python3 -c "from automedia.mcp.server import create_server; from automedia.validation.baseline import regenerate_baseline; regenerate_baseline(create_server(), baseline_path='scenarios/baseline/<new-name>.json')"
```

`regenerate_baseline` runs with `save=False` and writes only the single
committed copy — `validation-runs/` stays gitignored. The committed
`2026-08-14-preflight.json` is therefore immutable: it can only be replaced by
a deliberate, human-visible action outside this tool (e.g. `git rm` + a new
committed file), never by a regeneration over the top of it.
