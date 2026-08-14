# Baseline

`2026-08-14-preflight.json` is the pre-flight baseline (W2-T4): the first run
record of the validation library against the current product on a clean env
(no `AUTOMEDIA_LLM_API_KEY`). The W4-T4 diff computes against this record —
later waves turn its RED/unconfigured rows GREEN. Regenerate it with:

```
env -u AUTOMEDIA_LLM_API_KEY AUTOMEDIA_PROJECTS_DIR=/tmp/automedia/baseline-projects \
  python3 -c "import asyncio, json; from automedia.mcp.server import create_server; from automedia.validation.engine import run_validation_suite_async; r = asyncio.run(run_validation_suite_async(create_server(), runs_root='/tmp/automedia/baseline-runs', save=False)); json.dump(r, open('scenarios/baseline/2026-08-14-preflight.json', 'w', encoding='utf-8'), indent=2)"
```

(`save=False`, run from the repo root so the relative output path resolves; only
this tracked copy is committed — `validation-runs/` stays gitignored.)
