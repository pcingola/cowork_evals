# The checks layer

## Summary

How `cowork_evals` runs a case's `checks/` and writes the verdicts into the result document.
What a check author writes, and what a check may do, is [checks.md](checks.md). This file is
the part of the layer a consumer never touches: the result document it rewrites, how it loads
the check files, the judge's grant, and the fixture that exercises it.

## What reaches the result document

The layer rewrites the plugin's `aggregate-result.json` after the backend wrote it. These are
the changes, and nothing else in the document moves.

| Where                       | What                                                                  |
| --------------------------- | --------------------------------------------------------------------- |
| the case's `graders[]`      | one definition per check, `{name, type: check, weight: 1, config: {}}` |
| the run's `graders[]`       | one result per check, in the shape every grader result has            |
| the run's `score`, `passed` | recomputed over every scored result, the checks included              |
| the case's `aggregates`     | `score` and `passRate`, and on two arms `scoreWithout`, `passRateWithout` and `delta` where the harness wrote them, recomputed over the runs |
| the run's `judgeCostUsd`    | plus what a check judge spent                                         |
| the document's `costUsd`    | the same, so `panel` and `eval.max_cost_total_usd` both see it         |
| the document's `aggregates` | `overallScore` and `overallPassRate`, and `meanDelta` where the harness wrote it, recomputed over the cases |

`casesTotal` and `casesPassed` are untouched. `--threshold` is pinned to 0, so every case counts
as passed there whatever a check said, and the verdict decides pass and fail. A suite with no
check anywhere leaves the document exactly as the backend wrote it.

Every arm a case carries is walked. `scoreWithout`, `passRateWithout`, `delta` and `meanDelta`
are recomputed only where the harness wrote them, so a case the harness found not comparable
still carries no delta. A case carrying `declaredUnrunnable` has no run and produces no check
result.

## Loading the check files

Every `*.py` under a case's `checks/` is executed under a module name unique to its case
directory, so two cases each holding `checks/assertions.py` do not collide in `sys.modules`. The
case's `checks/` directory is on `sys.path` while its files load and is removed afterwards. A
helper module a case imported leaves `sys.modules` with it, so the next case's `helpers.py` is
that case's own. The loader is `src/cowork_evals/checks.py`.

## The judge's grant

`run.judge` grants `Read`, `Glob` and `Grep`, with no permission mode and no turn cap. On CLI
2.1.270 those three alone let a non-interactive `claude -p` read a file in its working directory
and answer on what it says, and the CLI's own default bounds the loop. The model resolves
through the same ladder as every other judge call.

## The fixture

`plugins/smoke/evals/plugin/checked-file` is a case with checks, and it runs. Its `prompt.md`
asks the agent to write `written.txt`, its one `file_exists` grader says the file appeared, and
`checks/assertions.py` says what is inside it: one check reads the file and passes, and one
returns a failed `Result`, so the case shows both halves.

`cowork_evals run --docker plugins/smoke --case checked-file --runs 1` prints the harness's own
table green, because the harness's grader passed, then a `FAIL` line for the failed check, and
exits 1. [checks.md](checks.md#the-verdict-and-the-harness-table) shows that output.
