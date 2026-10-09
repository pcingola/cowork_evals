# Documentation

## Summary

This repository is a Python package that runs evals for Claude CoWork skills and plugins. The
repository that owns the plugins installs it, points the `cowork_evals` command at its own
tree, and gets one pass or fail over the cases in that tree. The same command also runs a
plugin's own pytest suite on the CoWork runtime, with no model in the loop. This directory is
the reference for all of it: the command, the format a case is written in, the two backends
that execute a case, the container and the desktop driver under them, and what a real CoWork
session provides. Read the file that covers what you are about to change, and link to it
rather than restating it.

- Evals are not written here. This is a library, installed by the repository that owns the
  plugins under test.
- A case is written once, in one format, and runs on either backend. The backend changes, the
  case does not.
- Every file states what is true of this repository now. A measured fact states the behaviour
  and the conditions it holds under, never the date it was taken on or the incident that
  produced it.
- No file here carries a build status of its own, and no file here links to a plan.
- This tree ships inside the package. `cowork_evals docs` prints where it landed, and a
  reference that leaves this tree is named rather than linked. Both rules are in
  [`library.md`](library.md).

## The files

The files divide by reader. A consumer file holds what a consumer, or the model working for
one, acts on. A shipped skill links it under its own `references/`, so a model reads the same
file a person reads here. A developer file holds how this package is built and why. Each fact
has one home: a developer file links the consumer file and never restates it.

**For a consumer, and linked by a skill**

| File                                     | Covers                                                                   | Linked by                  |
| ---------------------------------------- | ------------------------------------------------------------------------ | -------------------------- |
| [`eval_design.md`](eval_design.md)       | Which cases to write, which assertion answers what, reading the results  | `cowork-evals`             |
| [`eval_format.md`](eval_format.md)       | The case tree, frontmatter, `case.yaml`, mocks, the validator, the authoring traps | `cowork-evals`   |
| [`plugin_eval.md`](plugin_eval.md)       | Every grader type and field, ablation arms, the limits a case cannot fix, cost | `cowork-evals`       |
| [`checks.md`](checks.md)                 | Writing a check: a Python assertion over the files a run produced        | `cowork-evals`             |
| [`cli.md`](cli.md)                       | Every verb, option, refusal and exit code                                | `cowork-evals`             |
| [`running_evals.md`](running_evals.md)   | Selection, settings, pass and fail, ablation, the run directory, transcripts, cost | `cowork-evals`   |
| [`cowork_test.md`](cowork_test.md)       | `cowork_evals test`: a plugin's pytest suite on the CoWork runtime       | `cowork-evals`             |
| [`panel.md`](panel.md)                   | What `panel` shows, and the history records behind it                    | `cowork-evals`             |
| [`approaches.md`](approaches.md)         | What each backend proves, honours and costs                              | `cowork-evals`, `cowork-ask` |
| [`ask.md`](ask.md)                       | `cowork_evals ask`: options, output, cost, preflight, exit codes         | `cowork-evals`, `cowork-ask` |
| [`cowork_driver.md`](cowork_driver.md)   | The submission sequence, the `cowork:` keys, the session document, the failure taxonomy | `cowork-evals`, `cowork-ask` |
| [`cowork_desktop.md`](cowork_desktop.md) | The desktop application as measured: what it writes, how a skill loads, the authorizations | `cowork-evals`, `cowork-ask` |
| [`runtime.md`](runtime.md)               | What a CoWork session provides, and the rules for plugin code            | all three                  |
| `pip_freeze.txt`                         | Every Python package a session has, and its version. A link to the package's `requirements.txt` | all three |

A consumer file links only to consumer files that every skill linking it also links, so each
link resolves in `docs/` and in each skill's `references/`.

**For a developer of this package**

| File                                                       | Covers                                                   | Consumer file it serves |
| ---------------------------------------------------------- | -------------------------------------------------------- | ----------------------- |
| [`library.md`](library.md)                                 | The boundary: what ships, how it installs, the configuration file, the skills | all              |
| [`status.md`](status.md)                                   | Which pieces are built                                   | all                     |
| [`cli_design.md`](cli_design.md)                           | The decisions behind the command surface                 | `cli.md`                |
| [`run_pipeline.md`](run_pipeline.md)                       | How `run` drives the harness, collects runs and decides the verdict | `running_evals.md` |
| [`case_history.md`](case_history.md)                       | How the history store is written, and its shape          | `panel.md`              |
| [`checks_layer.md`](checks_layer.md)                       | How checks are loaded and written into the result document | `checks.md`           |
| [`docker.md`](docker.md)                                   | The container, the harness inside it, the test image, pins, credentials, parity | `plugin_eval.md`, `cowork_test.md`, `runtime.md` |
| [`cowork_driver_internals.md`](cowork_driver_internals.md) | The driver's Python API and the design of each step      | `cowork_driver.md`      |
| [`cowork_backend.md`](cowork_backend.md)                   | The layer over the driver: grading a session document, the judge, the result document | `cowork_driver.md` |
| [`environments.md`](environments.md)                       | The two Python environments, and the three requirements files | `runtime.md`       |
| [`claude_code/`](claude_code/README.md)                    | The vendored harness reference, and the smoke plugin that proves the harness works | `plugin_eval.md` |
| [`staged_runtime.md`](staged_runtime.md)                   | Designed and not built: the staged 3.10 runtime and the venv backend over it | none |

## How the files divide

**A consumer file, or a developer file.** Does a consumer, or the model working for one, act
on the statement? Yes, and it is in a consumer file. No, and it is in a developer file. An
internal name, an implementation and the reason for a decision are developer statements.

**The command, or the run.** Does the statement describe what you type? Yes, and it is in
[`cli.md`](cli.md). No, and it is in [`running_evals.md`](running_evals.md), which holds what
the command does with a case tree whichever backend it chose.

**The run, or the other thing the command runs.** Does the statement concern a verdict over
cases? Yes, and it is in `running_evals.md`. No, and it is in
[`cowork_test.md`](cowork_test.md), which returns pytest's exit code and produces no result
document.

**The driver, or the backend over it.** Does the statement need to know what a case is? Yes,
and it is in [`cowork_backend.md`](cowork_backend.md). No, and it is in
[`cowork_driver.md`](cowork_driver.md) or
[`cowork_driver_internals.md`](cowork_driver_internals.md).

**A mechanism, or a measurement.** Does this repository build the thing? No, and what was
probed about it is in [`runtime.md`](runtime.md) for the session image and
[`cowork_desktop.md`](cowork_desktop.md) for the desktop application. Any other file cites a
value from either and never restates it.

**The case, or the harness.** Can a case author work around the limit by editing a case? Yes,
and it is in [`eval_format.md`](eval_format.md). No, and it is in
[`plugin_eval.md`](plugin_eval.md).

**Where a check goes, or how to write one.** `eval_format.md` places the `checks/` directory in
the case tree. [`checks.md`](checks.md) is how to write the Python inside it.

**A setting's home.** [`library.md`](library.md) owns the configuration file: its sections, the
precedence ladder and the one route from the environment. What a setting does is stated with
the mechanism it configures.

Build status is in [`status.md`](status.md) and nowhere else.

The three requirements files are measurements too and are not here: they are package data at
`src/cowork_evals/data/`, and [`environments.md`](environments.md) owns the split between them.

Writing rules are in `CLAUDE.md`. The public repository rule is in `README.md`, and it applies
to every file here.
