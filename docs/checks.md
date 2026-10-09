# Checks

## Summary

A check is a Python function in a case's `checks/` directory. It asserts what no grader type
can. `claude plugin eval` defines six grader types and the list is closed. The common case is a
produced file whose contents matter: `file_exists` reports that a spreadsheet was created and
says nothing about the numbers in it, and `regex` and `llm` read a produced file as text, which
a workbook is not.

A check runs on the host after the run is graded, on either backend, once per run, over the
files that run left. Its verdict is a grader result of `type: check`, so a failed check fails
the run and the command exits 1.

## Writing one

There is nothing to register and no key to add to any case file.

1. Make the directory. `checks/` sits beside the case's `graders/`.

   ```
   <plugin>/evals/<skill>/<case>/prompt.md
   <plugin>/evals/<skill>/<case>/graders/<name>.md
   <plugin>/evals/<skill>/<case>/checks/<name>.py
   ```

   Keep `graders/`. The harness refuses a case with no grader, so a case whose only assertion
   directory is `checks/` never loads.

2. Write the function. Any file name works. Import the decorator, mark a function with it, and
   take one argument.

   ```python
   # evals/spreadsheets/monthly-totals/checks/assertions.py
   import openpyxl

   from cowork_evals.checks import Run, check


   @check
   def totals_add_up(run: Run) -> None:
       book = openpyxl.load_workbook(run.file("totals.xlsx"))
       assert book.active["D10"].value == 4200
   ```

   `run.file("totals.xlsx")` is the file the agent produced, as a path. If the assertion holds
   the check passes. If it raises, the check fails and the message reaches the failure line.

3. Run the case as usual, with no new flag and no new verb:
   `cowork_evals run --docker <plugin>/evals/spreadsheets/monthly-totals`. The harness grades
   the case, the run's files are collected, and every `@check` under `checks/` runs once per
   run.

## What a check returns

A check's name is `<file stem>.<function name>`, so `totals_add_up` in `checks/assertions.py`
is `assertions.totals_add_up` everywhere a name appears. Every check has weight 1.

| The function          | The check                               |
| --------------------- | --------------------------------------- |
| returns `None`        | passes                                  |
| returns `True`        | passes                                  |
| returns `False`       | fails                                   |
| returns a `Result`    | is what the `Result` says               |
| raises                | fails, carrying the exception's message |
| returns anything else | fails, naming what it returned          |

`Result` has two fields, `passed` and `explanation`, and nothing else. Return a `Result`
whenever the reason matters to whoever reads the failure.

```python
from cowork_evals.checks import Result, Run, check


@check
def totals_add_up(run: Run) -> Result:
    book = openpyxl.load_workbook(run.file("totals.xlsx"))
    total = book.active["D10"].value
    return Result(passed=total == 4200, explanation=f"D10 is {total}")
```

`explanation` is what the `FAIL` line prints, as `the check grader failed: <explanation>`, what
the result document records, and what `checks.jsonl` keeps. A check that raises gets the
exception's message there, and its traceback in `checks.jsonl`.

A failing check never stops the command. Every failure above is a failed check carrying its
reason, and the rest of the suite goes on.

## The Run object

Each check is called with one `Run`, which describes one execution of the case. Every field is
something left under the run directory, so the same fields are there whichever backend
produced the run.

| Field          | Is                                                               |
| -------------- | ---------------------------------------------------------------- |
| `workspace`    | the agent's working directory, as a path                         |
| `last_message` | the final assistant message, as text                             |
| `trace`        | the transcript, as a path. Each backend writes its own format    |
| `case_dir`     | the case directory on the host                                   |
| `run_dir`      | the collected run directory, and the judge's working directory   |
| `scratch`      | a directory a check may write into                               |
| `index`        | which run of the case this is, 1-based, as the verdict prints it |

`run.file(name)` resolves one name under `workspace`. A name that resolves to nothing, and a
name that leaves the workspace, each fail the check naming it.

There is no list of created files on the `Run`. Walk `run.workspace`, which also finds a file
the agent modified rather than created, which `file_exists` never sees.

Write into `run.scratch`, never into `run.workspace`. The workspace is the record of what the
agent produced. `scratch/` exists before the first check of a run and is shared by every check
of that run.

The two transcript formats are [running_evals.md](running_evals.md). A check reading
`run.trace` reads the format of the backend that produced the run.

## Asking a judge

Some things are not decidable in code: whether a slide is clipped, whether a chart is readable,
whether prose answers the question. `run.judge(prompt, *paths)` asks a model. It runs
`claude -p` three times, takes the majority of the three votes, and returns a `Result`, so a
check can return it directly.

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

The judge is handed the paths and the tools to open them, never the file's text, so a binary
can be judged. The `llm` grader works the other way.

|                   | The `llm` grader                 | `run.judge`                      |
| ----------------- | -------------------------------- | -------------------------------- |
| Is shown          | the material, as text on stdin   | the paths, and reads them itself |
| Tools             | none                             | `Read`, `Glob`, `Grep`           |
| Working directory | the caller's                     | the run directory                |
| A binary focus    | a grader skip or a failed grader | read like any other file         |
| Defined by        | the harness                      | `cowork_evals`                   |

A path under the run directory reaches the prompt relative to it. A path outside it reaches the
prompt absolute and is added with `--add-dir`. A path that does not exist fails the check. A
call naming no path fails the check: there is no default of the whole run directory, because a
judge shown the whole run directory judges the transcript as well as the artifact.

The grant is those three read-only tools, with no permission mode and no turn cap.
`--judge-model` beats `eval.judge_model` for the judge's model. The judge has no configuration
key of its own.

There is no `@transform` decorator and no `run.ask`. Convert a file, or ask a model something
`run.judge` does not answer, with `subprocess` inside the check, as the example above does.

## Several files, and helpers

Split checks across as many files under `checks/` as needed. Every `*.py` in the directory is
imported, in path order, and every `@check` function in a file is collected in the order the
file defines them. That is the order they run in and the order they appear in the result.

A check file may import a helper module beside it:

```python
from helpers import expected_total  # checks/helpers.py, beside this file
```

Import it at the top of the file. `checks/` is on `sys.path` only while the files load, so an
import inside a function body runs too late and raises `ModuleNotFoundError`.

A file under `checks/` with no `@check` is a helper, and is not an error. A `checks/` directory
with no `@check` in any file is refused with exit 3: it asserts nothing while it appears to.

Two cases may each hold `checks/assertions.py` and `checks/helpers.py` without colliding. Each
case's helper is that case's own.

## Where a check runs, and what it may import

A check runs on the host, in the `cowork_evals` process, after the run is graded. It never
enters the container or the CoWork VM, so nothing about the session binds it: not the
interpreter, not the wheel set, not the image. A check file sits under the eval path and is the
one thing there that is not code under test. The rules for the code under test are
[runtime.md](runtime.md).

A check may import anything the consumer's own project declares and run anything the host has,
such as `openpyxl`, `pypdf` or `soffice`. Declare those as the consumer's own dependencies,
exactly as for a unit test. The host needs nothing beyond Python 3.10 and what the check
imports. What else constrains that machine is the backend, with checks as without: see
[approaches.md](approaches.md).

## The run directory

A check reads the collected run directory, which has the same layout on both backends, and
writes two more names into it.

```
<log root>/<stamp>-<scope>/<plugin>/traces/<case>/run-<n>/
  trace.jsonl
  last_message.txt
  workspace/
  scratch/          # what a check wrote
  checks.jsonl      # one line per check
```

The `[artifacts: <dir>]` suffix on a failure line names this directory. The three collected
names are [running_evals.md](running_evals.md).

`checks.jsonl` holds one object per check: the name, the verdict, the explanation, the
duration, the traceback where there was one, and for each judge call the whole prompt, the
three replies and the cost. The result document's `evidence` is capped at 2000 characters, so a
failed judged check is read in `checks.jsonl`.

```json
{"name": "assertions.the_file_says_written", "passed": true, "explanation": "the check raised nothing", "durationSeconds": 0.0014}
{"name": "assertions.the_file_is_a_workbook", "passed": false, "explanation": "written.txt is not a workbook", "durationSeconds": 0.0000043}
```

Under `--no-keep-traces`, and under `eval.keep_traces: false`, nothing is collected and there is
no run directory to read. Every check of that case is then a skip, and a skip fails the run. See
[cli.md](cli.md).

## The preflight

`cowork_evals run` imports every check of every selected plugin root before anything runs, so a
syntax error or a missing import exits 3 before anything is spent. Two checks of one case that
share a name exit 3. A `checks/` directory with no `@check` exits 3. A `context.add_dirs` entry
under `checks/` exits 3. The full rule list is
[eval_format.md](eval_format.md#what-the-validator-enforces).

Editing a `checks/*.py` marks the case's earlier result stale in `panel`. See
[panel.md](panel.md).

## The verdict and the harness table

The harness prints its own table first, over the graders it ran, and the verdict follows it.
The table can be green while a check fails the run:

```
CASE          SCORE PASS% RUNS COST    NOTES
checked-file  1.00  100%  1    $0.06

FAIL smoke/checked-file: run 1: assertions.the_file_is_a_workbook: the check grader failed:
  written.txt is not a workbook [artifacts: logs/evals/.../smoke/traces/checked-file/run-1]
```

The failure line is one line, wrapped here. The exit code is 1. The table is what the harness
graded. The line below it decides the run over every grader and every check.

The run's `score` and `passed`, the case's aggregates, and the document's `costUsd` are
recomputed with the checks included. A suite with no check anywhere leaves the result document
exactly as the backend wrote it.

## Ablation

Under `--ablation with-without` every check runs in both arms, so both arms are scored on the
same checks. A check that can only pass with the plugin loaded fails in the baseline arm. A
case the harness found not comparable still carries no delta. A case carrying `no-cowork` on
`--cowork` has no run and produces no check result.

## What it costs

A check that only asserts costs nothing. It is a function call on the host.

A `run.judge` call costs three `claude -p` calls at the judge model, per call per run. Each run
of a case runs every check again, so a case at `runs: 3` carrying one judged check makes nine.
Under `--ablation with-without` every check runs in both arms, which doubles that.
`eval.max_cost_usd` does not bind check spend, because the harness has finished when a check
runs. `eval.max_cost_total_usd` does, because the spend is added to the result document's
`costUsd`. The ceilings are [running_evals.md](running_evals.md).

## Common mistakes

| What was done                                            | What happens                                                                                                                    |
| -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `checks/` added to a case and `graders/` deleted         | The case does not load. The harness refuses a case with no grader, the suite writes no result, and the command exits 1           |
| Run with `--no-keep-traces` or `eval.keep_traces: false` | Nothing is collected, every check is a skip, and a skip fails the run                                                           |
| A `checks/` directory whose files have no `@check`       | The preflight exits 3                                                                                                           |
| A helper imported inside a function body                 | `ModuleNotFoundError`. Import at the top of the file                                                                            |
| A file written into `run.workspace`                      | The record of what the agent produced is changed. Write into `run.scratch`                                                      |
| `run.judge` on a case at `runs: 3`                       | Three judge calls per run, nine in total. Every check runs again for every run of the case                                       |
