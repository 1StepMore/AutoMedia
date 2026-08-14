# Baseline

`2026-08-14-preflight.json` is the pre-flight baseline (W2-T4): the first run
record of the validation library against the current product on a clean env
(no `AUTOMEDIA_LLM_API_KEY`). The W4-T4 diff computes against this record —
later waves turn its RED/unconfigured rows GREEN. Regenerate it with:

```
env -u AUTOMEDIA_LLM_API_KEY AUTOMEDIA_PROJECTS_DIR=/tmp/automedia/baseline-projects \
  .venv/bin/python /tmp/opencode/baseline_run.py
```

(`save=False`, cwd `/tmp/automedia/baseline-cwd`; only this tracked copy is
committed — `validation-runs/` stays gitignored.)
