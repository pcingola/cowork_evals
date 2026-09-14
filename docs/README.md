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

Read them in this order.

**The system**

| File                                   | Covers                                                            |
| -------------------------------------- | ----------------------------------------------------------------- |
| [`library.md`](library.md)             | The boundary: what ships, how it installs, the one configuration file, where state lives |
| [`cli.md`](cli.md)                     | The `cowork_evals` command: every verb, its options, what it refuses, exit codes |
| [`approaches.md`](approaches.md)       | The two backends: what each proves, what each costs, which part of a case each honours |
| [`eval_format.md`](eval_format.md)     | The authoring contract: the case tree, frontmatter, graders, what the validator refuses |
| [`eval_design.md`](eval_design.md)     | Which cases a skill needs, which grader answers what, and the interview that decides |
| [`running_evals.md`](running_evals.md) | What a run does with a case tree: build status, pinned flags, pass and fail, logs, cost |
| [`cowork_test.md`](cowork_test.md)     | `cowork_evals test`: a consumer's pytest suite on the CoWork runtime, no model |

**The mechanisms under it**

| File                                     | Covers                                                          |
| ---------------------------------------- | --------------------------------------------------------------- |
| [`docker.md`](docker.md)                 | The container that reproduces the CoWork image: OS, tooling, pins, credentials, parity |
| [`cowork_driver.md`](cowork_driver.md)   | Driving the desktop application: the API, the sequence, the session document |
| [`cowork_backend.md`](cowork_backend.md) | The layer over the driver: grading a session document, the judge, the result document |
| [`environments.md`](environments.md)     | The two Python environments, and the three requirements files behind them |
| [`panel.md`](panel.md)                   | The per-case history a run appends, and the panel that renders it |
| [`checks.md`](checks.md)                 | Writing a check: a Python assertion over the files a run produced |

**Measured, not built here**

| File                                     | Covers                                                          |
| ---------------------------------------- | --------------------------------------------------------------- |
| [`runtime.md`](runtime.md)               | What a CoWork session provides: the image inventory, and what the host hands a skill |
| [`cowork_desktop.md`](cowork_desktop.md) | The desktop application as probed: deep links, session filesystem, authorizations |

**From outside, and one design that was not built**

| File                                     | Covers                                                          |
| ---------------------------------------- | --------------------------------------------------------------- |
| [`plugin_eval.md`](plugin_eval.md)       | `claude plugin eval`: availability, flags, the limits a case author cannot work around |
| [`claude_code/`](claude_code/README.md)  | The vendored harness reference, and the smoke plugin that proves the harness works |
| [`staged_runtime.md`](staged_runtime.md) | Designed and not built: the staged 3.10 runtime and the venv backend over it |

## How the files divide

Each split below is decided by one question, and that question holds for every statement
already on either side.

**The command, or the run.** Does the statement describe what you type? Yes, and it is in
[`cli.md`](cli.md): the verbs, the options, what a verb refuses, the exit codes. No, and it is
in [`running_evals.md`](running_evals.md), which holds what the command does with a case tree
whichever backend it chose.

**The run, or the other thing the command runs.** Does the statement concern a verdict over
cases? Yes, and it is in `running_evals.md`. No, and it is in
[`cowork_test.md`](cowork_test.md), which returns pytest's exit code and produces no result
document.

**The run, or a mechanism.** A mechanism file holds how one thing works and everything
measured about it: [`docker.md`](docker.md) the container, [`cowork_driver.md`](cowork_driver.md)
the desktop driver, [`environments.md`](environments.md) the two Python environments,
[`panel.md`](panel.md) the history, [`checks.md`](checks.md) the layer that runs a consumer's
own Python over what a run produced. A fact measured during a run belongs with the mechanism
it binds, not with the run.

**The format, or the design.** Does the statement depend on what the skill under test does? No,
and it is in [`eval_format.md`](eval_format.md). Yes, and it is in
[`eval_design.md`](eval_design.md). The format is checked by the validator, and the design is
checked by nothing, which is why it is written down.

**The driver, or the backend over it.** Does the statement need to know what a case is? Yes,
and it is in [`cowork_backend.md`](cowork_backend.md). No, and it is in
[`cowork_driver.md`](cowork_driver.md), which holds the transport and nothing else.

**A mechanism, or a measurement.** Does this repository build the thing? No, and what was
probed about it is in [`runtime.md`](runtime.md) for the session image and
[`cowork_desktop.md`](cowork_desktop.md) for the desktop application. A mechanism file cites a
value from either and never restates it, so `cowork_driver.md` states the driver's design and
links the application shape it reads.

**The case, or the harness.** Can a case author work around the limit by editing a case? Yes,
and it is in [`eval_format.md`](eval_format.md), the contract a case is written to. No, and it
is in [`plugin_eval.md`](plugin_eval.md), which describes a Claude Code command this
repository does not own and carries the CLI version it was written against.

**Where a check goes, or how to write one.** `eval_format.md` places the `checks/` directory in
the case tree. [`checks.md`](checks.md) is the instructions for writing the Python inside it.

**A setting's home.** [`library.md`](library.md) owns the configuration file: its four
sections, the precedence ladder and the one route from the environment. What a setting does is
stated with the mechanism it configures.

Build status is the one fact that goes the other way. Every piece has a row in
`running_evals.md`'s status table whatever mechanism it belongs to, and the files whose
subjects have a row link there.

The three requirements files are measurements too and are not here: they are package data at
`src/cowork_evals/data/`, and [`environments.md`](environments.md) owns the split between them.

Writing rules are in `CLAUDE.md`. The public repository rule is in `README.md`, and it applies
to every file here.
