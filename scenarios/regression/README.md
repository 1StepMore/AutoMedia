# Regression scenarios

This directory holds the regression flywheel (guide §5.2): scenarios that
pin a real bug to its fix. Name them `regression-<issue>` (in the `name:`
field, not the file), mark `regression: true`, and cite the bug in
`regression_issue: "#NN"`. They must stay GREEN forever — a RED regression
scenario IS the bug, re-surfaced. A bug report that cannot name its
scenario here is incomplete (`.github/ISSUE_TEMPLATE/bug_report.yml` makes
the field mandatory).
