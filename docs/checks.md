# Checks

## Summary

A check is a Python function you write that asserts something about the files an eval run
produced. You need one when no grader can make the assertion. `claude plugin eval` defines six
grader types and that list is closed, so an assertion outside it has nowhere to go. The case
that comes up most is a produced file whose contents matter. Take a case whose prompt asks for
a spreadsheet: `file_exists` reports that the file was created and says nothing about the
numbers in it, while `regex` and `llm` read a produced file as text, which a workbook is not. A
check goes in the case's `checks/` directory. It runs on the host after the harness has graded
the run, over the files that run left, and its verdict is appended to the result document as a
grader result, so a failed check fails the case.

## Writing one

Three steps. There is nothing to register and no key to add to any case file.

**1. Make the directory.** `checks/` sits beside the `graders/` the case already has.

```
<plugin>/evals/<skill>/<case>/prompt.md
<plugin>/evals/<skill>/<case>/graders/<name>.md      # the harness's
<plugin>/evals/<skill>/<case>/checks/<name>.py       # yours
```

Keep `graders/`. The harness refuses a case carrying no grader at all, so a case whose only
assertion directory is `checks/` never loads and never runs.

**2. Write the function.** Any file name works. Import the decorator, mark a function with it,
and take one argument.

```python
# evals/spreadsheets/monthly-totals/checks/assertions.py
import openpyxl

from cowork_evals.checks import Run, check


@check
def totals_add_up(run: Run) -> None:
    book = openpyxl.load_workbook(run.file("totals.xlsx"))
    assert book.active["D10"].value == 4200
```

`run.file("totals.xlsx")` is the file the agent produced, as a path. If the assertion holds the
check passes. If it raises, the check fails and the message reaches the failure line.

`openpyxl` is your dependency, not this package's. Add whatever a check imports to your own
project exactly as you would for a unit test. See [library.md](library.md).

**3. Run the case as usual.** No new flag and no new verb.

```sh
cowork_evals run --docker <plugin>/evals/spreadsheets/monthly-totals
```

The harness grades the case, the run's files are collected, and then every `@check` under
`checks/` runs once per run. A failed check fails the case and the command exits 1.

## What a check returns

`@check` takes no arguments. A check's name is `<file stem>.<function name>`, so
`totals_add_up` in `checks/assertions.py` is `assertions.totals_add_up` everywhere a name
appears, and every check has weight 1.

| The function          | The check                               |
| --------------------- | --------------------------------------- |
| returns `None`        | passes                                  |
| returns `True`        | passes                                  |
| returns `False`       | fails                                   |
| returns a `Result`    | is what the `Result` says               |
| raises                | fails, carrying the exception's message |
| returns anything else | fails, naming what it returned          |

`Result` carries two fields, `passed` and `explanation`, and nothing else. Use it when the
reason matters to whoever reads the failure.

```python
from cowork_evals.checks import Result, Run, check


@check
def totals_add_up(run: Run) -> Result:
    book = openpyxl.load_workbook(run.file("totals.xlsx"))
    total = book.active["D10"].value
    return Result(passed=total == 4200, explanation=f"D10 is {total}")
```

`explanation` is what the `FAIL` line prints, what the result document records and what
`checks.jsonl` keeps. A check that raises gets the exception's message there, and its traceback
in `checks.jsonl`.

Nothing a check does can stop the command. Every failure above is a failed check carrying its
reason, and the rest of the suite goes on.

## The Run object

Each check is called with one `Run`. It describes one execution of the case. Every field is
something the collector left under the run directory, so the same fields are there whichever
backend produced the run.

| Field          | Is                                                               |
| -------------- | ---------------------------------------------------------------- |
| `workspace`    | the agent's working directory, as a path                         |
| `last_message` | the final assistant message, as text                             |
| `trace`        | the transcript, as a path. The two backends write two formats    |
| `case_dir`     | the case directory on this host                                  |
| `run_dir`      | the collected run directory, and the judge's working directory   |
| `scratch`      | a directory a check may write into                               |
| `index`        | which run of the case this is, 1-based, as the verdict prints it |

`run.file(name)` resolves one name under `workspace`. A name that resolves to nothing, and a
name that leaves the workspace, each fail the check naming it.

To find out what the agent produced, walk `run.workspace`. There is no list of created files on
the `Run`: the result document carries none on the container backend, and walking the directory
also finds a file the agent modified rather than created, which `file_exists` never sees.

**Write to `run.scratch`, never to `run.workspace`.** The workspace is the record of what the
agent produced. `scratch/` is created before the first check of a run and is shared by every
check of that run.

The two transcript formats are [running_evals.md](running_evals.md). A check reading
`run.trace` reads whichever format the backend that produced the run wrote.

## Asking a judge

Some things are not decidable in code: whether a slide is clipped, whether a chart is readable,
whether prose answers the question. `run.judge(prompt, *paths)` asks a model. It runs `claude
-p` three times, takes the majority of the three votes, and returns a `Result`, so a check can
return it straight back.

```python
import subprocess

from cowork_evals.checks import Result, Run, check


@check
def deck_is_readable(run: Run) -> Result:
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "png", run.file("deck.pptx")],
        cwd=run.scratch,
        check=True,
    )
    return run.judge("Every slide carries a title, and no text is clipped.", run.scratch)
```

The judge is handed the paths and the tools to open them, never the file's text, which is what
makes a binary judgeable at all. The `llm` grader works the other way and is unchanged by any
of this.

|                   | The `llm` grader                 | `run.judge`                      |
| ----------------- | -------------------------------- | -------------------------------- |
| Is shown          | the material, as text on stdin   | the paths, and reads them itself |
| Tools             | none                             | `Read`, `Glob`, `Grep`           |
| Working directory | the caller's                     | the run directory                |
| A binary focus    | a grader skip or a failed grader | read like any other file         |
| Defined by        | the harness                      | this package                     |

A path under the run directory reaches the prompt relative to it. A path outside reaches it
absolute, and the argument list carries an `--add-dir` for it. A path that is not there is a
failed check naming it. A call naming no path is a failed check too: there is no default of
everything, because a judge shown the whole run directory is judging the transcript as well as
the artefact.

The grant is those three read-only tools, with no permission mode and no turn cap. On CLI
2.1.270 they alone let a non-interactive `claude -p` read a file in its working directory and
answer on what it says, and the CLI's own default binds the loop. The model resolves through
the one ladder every other judge call resolves through, so `--judge-model` beats
`eval.judge_model`. The layer has no configuration key of its own.

There is no `@transform` decorator and no `run.ask`. Converting a file before asserting on it,
and asking a model something `run.judge` does not answer, are both things a Python function
does: call `subprocess` in the check itself, as the example above does.

## Several files, and helpers

Split checks across as many files under `checks/` as you like. Every `*.py` in the directory is
imported, in path order, and every decorated function in each file is collected in the order
that file defines them. That is the order they run in and the order they appear in the result.

A check file may import a helper module sitting beside it, because the `checks/` directory is
on `sys.path` while the files load.

```python
from helpers import expected_total  # checks/helpers.py, beside this file
```

Import it at the top of the file. The directory comes off `sys.path` once loading is done, so
an import inside a function body runs too late and fails.

A file under `checks/` with no `@check` in it is a helper, and is not an error. A `checks/`
directory in which no file anywhere has a check is: it asserts nothing while looking as if it
does.

Two cases may each have a `checks/assertions.py` without colliding. Each file is loaded under a
module name unique to its own case directory, and a helper one of them imported is dropped
afterwards, so the next case's `helpers.py` is that case's own.

## A worked example

`plugins/smoke/evals/plugin/checked-file` is a case with checks, in this repository, and it
runs. Its `prompt.md` asks the agent to write `written.txt`, its one `file_exists` grader says
the file appeared, and `checks/assertions.py` says what is inside it: one check reads the file
and passes, and one returns a failed `Result`, so the case shows both halves.

`cowork_evals run --docker plugins/smoke --case checked-file --runs 1` prints the harness's own
table green, because the harness's own grader passed, and then the verdict under it. The
failure line is wrapped here and is one line.

```
CASE          SCORE PASS% RUNS COST    NOTES
checked-file  1.00  100%  1    $0.06

FAIL smoke/checked-file: run 1: assertions.the_file_is_a_workbook: the check grader failed:
  written.txt is not a workbook [artifacts: logs/evals/.../smoke/traces/checked-file/run-1]
4 found, 1 picked, 1 ran, 0 passed, 0 declared unrunnable, overall score 0.67
```

The exit code is 1. The two disagree because they are two things: the table is the harness
reporting what it graded, and the line below it is this package deciding the run over
everything that graded it.

`checks.jsonl` in that run directory, verbatim:

```json
{"name": "assertions.the_file_says_written", "passed": true, "explanation": "the check raised nothing", "durationSeconds": 0.0014283749987953342}
{"name": "assertions.the_file_is_a_workbook", "passed": false, "explanation": "written.txt is not a workbook", "durationSeconds": 4.334004188422114e-06}
```

## Where a check runs, and what it may import

A check runs on the host, in this package's process, after the run is graded. It never enters
the container and never enters the CoWork VM, so nothing about the session binds it: not the
interpreter, not the wheel set, not the image. A check file sits under the eval path and is the
one thing there that is not code under test. See [runtime.md](runtime.md).

So a check may import anything your own project declares and shell out to anything the host
has: `openpyxl`, `pypdf`, `soffice`. Those imports are the consumer's dependency, and this
package depends on nothing a check might want. The host is the machine `cowork_evals` ran on,
and a check adds no requirement to it beyond Python 3.10 and what the check imports. What
constrains that machine is the backend, the same way with checks as without. See
[library.md](library.md) and [approaches.md](approaches.md).

## The run directory

A check reads the collected run directory, which is what both backends normalise to, so one
code path serves both. It writes two more names into it.

```
<log root>/<stamp>-<scope>/<plugin>/traces/<case>/run-<n>/
  trace.jsonl
  last_message.txt
  workspace/
  scratch/          # what a check wrote
  checks.jsonl      # one line per check
```

Both sit beside the three the collector left, so the `[artifacts: <dir>]` suffix on a failure
line names all five. The three collected names are [running_evals.md](running_evals.md).

`checks.jsonl` carries one object per check: the name, the verdict, the explanation, the
duration, the traceback where there was one, and for each judge call the whole prompt, the
three replies and the cost. The result document's `evidence` is capped at 2000 characters, and
a person reading a failed judged check needs the whole exchange.

Under `--no-keep-traces`, and under `eval.keep_traces: false`, nothing is collected and there is
no run directory to read. Every check of that case is then a skip, and a skip fails the run: a
suite cannot go green by asserting nothing. See [cli.md](cli.md).

## The preflight

`checks/*.py` is Python, and the only way to know it imports is to import it. `cowork_evals
run` imports every check of every selected plugin root before anything runs, so a syntax error
or a missing import exits 3 before anything spends money. That rule, the one against an empty
`checks/` directory, the one against two checks of a case sharing a name, and the one keeping
`checks/` out of `context.add_dirs` are all in
[eval_format.md](eval_format.md#what-the-validator-enforces).

The panel's `caseDigest` covers each `checks/*.py`, so editing an assertion marks an earlier
result stale. See [panel.md](panel.md).

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
| the document's `costUsd`    | the same, so the panel and `eval.max_cost_total_usd` both see it      |
| the document's `aggregates` | `overallScore` and `overallPassRate`, and `meanDelta` where the harness wrote it, recomputed over the cases |

`casesTotal` and `casesPassed` are untouched. `--threshold` is pinned to 0, so every case counts
as passed there whatever a check said, and this package decides pass and fail. A suite with no
check anywhere leaves the document exactly as the backend wrote it.

A `check` grader result is not judged, so a failed one fails the run exactly as a failed `regex`
grader does, and the line reads `the check grader failed: <explanation>`.

Every arm a case carries is walked, so both arms are scored on the same checks. A check that
can only pass with the plugin loaded fails in the baseline arm. `scoreWithout`,
`passRateWithout`, `delta` and `meanDelta` are recomputed only where the harness wrote them, so
a case the harness found not comparable still carries no delta. A case carrying
`declaredUnrunnable` has no run and produces no check result.

## What it costs

A check that asserts costs nothing. It is a function call on the host.

A check that calls `run.judge` costs three `claude -p` calls at the judge model, per call per
run. Each run of a case runs every check again, so a case at `runs: 3` carrying one judged check
costs nine. Under `--ablation with-without` every check runs in both arms, which doubles that
cost. The harness has already finished when a check runs, so `eval.max_cost_usd` does not
bind that spend; it is added to the document's `costUsd`, which `eval.max_cost_total_usd` reads.
The ceilings are [running_evals.md](running_evals.md).

## Common mistakes

| What you did                                             | What happens                                                                                                                    |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Put `checks/` on a case and deleted its `graders/`       | The case does not load at all. The harness refuses a case with no grader, so the suite writes no result and the command exits 1  |
| Ran with `--no-keep-traces`                              | Every check is a skip, and a skip fails the run. There is nothing collected to check                                            |
| Wrote a `checks/` directory whose files have no `@check` | The preflight refuses the tree with exit 3. A directory that asserts nothing looks like one that asserts something               |
| Imported a helper inside the function body               | `ModuleNotFoundError`. The `checks/` directory is on `sys.path` only while the files load, so import at the top                  |
| Wrote into `run.workspace`                               | You have edited the record of what the agent produced. Write to `run.scratch`                                                   |
| Called `run.judge` on a case at `runs: 3`                | Three judge calls per run, nine in total. Every check runs again for every run of the case                                       |
