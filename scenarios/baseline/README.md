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
baseline. Regenerate it with:

```
env -u AUTOMEDIA_LLM_API_KEY AUTOMEDIA_PROJECTS_DIR=/tmp/automedia/baseline-projects \
  python3 -c "import asyncio, json; from automedia.mcp.server import create_server; from automedia.validation.engine import run_validation_suite_async; r = asyncio.run(run_validation_suite_async(create_server(), runs_root='/tmp/automedia/baseline-runs', save=False)); r['baseline'] = True; r['note'] = 'full-suite baseline'; json.dump(r, open('scenarios/baseline/2026-08-14-preflight.json', 'w', encoding='utf-8'), indent=2)"
```

(`save=False`, run from the repo root so the relative output path resolves; only
this tracked copy is committed — `validation-runs/` stays gitignored.)
