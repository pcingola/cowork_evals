# Run pipeline

## Summary

How `cowork_evals run` drives the harness, collects each run, and reads the result documents
into one verdict. What a consumer sees of all of it, the settings, pass and fail, the run
directory and the cost, is [running_evals.md](running_evals.md). This file holds the mechanism
and the decisions behind it.

- **Flags are pinned, not defaulted.** Every flag in the pinned list has a harness default this
  package cannot accept.
- **This package decides pass and fail, not the harness.** The verdict always runs in the
  `cowork_evals` process on the host, over the result document, so one verdict covers both
  backends.
- **Nothing here runs on CI.** A red verdict over cases nobody trusts gets routed around rather
  than fixed, and that holds whatever the cost.

## Pinned flags

What each flag does, and the harness behaviour behind it, is [plugin_eval.md](plugin_eval.md).

| Flag                                         | Pinned to                         | Configuration key, and its default           |
| -------------------------------------------- | --------------------------------- | -------------------------------------------- |
| `--model`                                    | the configured model              | `eval.model`, `sonnet`                       |
| `--judge-model`                              | the configured judge              | `eval.judge_model`, `haiku`                  |
| `--ablation`                                 | the configured arm                | `eval.ablation`, `none`                      |
| `--threshold`                                | `0`, so this package decides      | none                                         |
| `--max-cost-usd`                             | the configured ceiling            | `eval.max_cost_usd`, 5                       |
| `--output-dir`                               | the run's log directory           | none                                         |
| `--allow-tools`                              | the configured grant              | `eval.allow_tools`, the session mirror       |
| `--keep-temp`                                | on, when the run keeps its traces | `eval.keep_traces`, true                     |
| `--no-publish`, `--no-scaffold`, `--verbose` | always                            | none                                         |

The target goes before every variadic flag: `--tag` and `--allow-tools` swallow a trailing
target.

`--threshold 0` hands pass and fail to this package, and it has no command-line option.
`eval.delta_threshold` is read by the verdict and reaches no command line.

`eval.keep_traces` is the one key in the table that is not only a flag. It decides
`--keep-temp` on the container backend, and it decides whether a run's artefacts are collected
on both. The CoWork backend runs no command line, so nothing is pinned there and the key still
binds.

The container backend exports `CLAUDE_CODE_WALNUT_SPIRE`, the early-access enablement variable,
so no developer sets it by hand. It is a constant in `harness.py`, not a configuration key.
`--json` is never passed. Both are [docker.md](docker.md#the-harness).

On CLI 2.1.265 every granted name reaches the run bare, in the `init` record's tool list, never
in a `Tool(pattern)` shape. The path scoping applied to a bare `Read`, `Glob` or `Grep` is in the
child's permission rules and not in that list. The list is longer than the grant, because
`Task`, `WebSearch` and others are offered without being granted, so the unoffered check reads
it in one direction only. `Read`, `Glob` and `Grep` are in the default grant because on CLI
2.1.265 a run granted only `Bash` offered the model no `Glob` and no `Grep`. A session's tool
use, which the default grant mirrors, is measured in [cowork_desktop.md](cowork_desktop.md).

The CoWork backend does not call `claude plugin eval`. Of the settings behind the pinned flags
it reads `eval.judge_model` and `eval.keep_traces`; the rest configure the CLI, which is not in
its path. See [cowork_backend.md](cowork_backend.md).

## Collection

A failing case has to be readable after the fact. The harness deletes the sandbox of every run
that did not error, and a CoWork session is a directory in a profile nobody opens, so every run
of either backend keeps the same three artefacts under the same names, passing runs included.
A passing run is what a failing one is read against, and which of three runs failed is not
known before the run.

| Backend    | The artefacts are in                        | And are | Because                                                     |
| ---------- | ------------------------------------------- | ------- | ----------------------------------------------------------- |
| `--docker` | the sandbox `--keep-temp` kept, on the host | moved   | A sandbox is a throwaway directory, and moving empties it   |
| `--cowork` | the CoWork session directory                | copied  | A session is the account's own record, and is never written |

The kept sandbox is created under the harness's `TMPDIR`, which the container backend points at
the run's log mount, so it lands on the host and not inside a container started with `--rm`.
See [docker.md](docker.md). The rest of a sandbox is removed: the child's configuration
directory, its npm logs, its node compile cache and its sockets. None of it says anything about
the run, and it is 40 times the size of what is kept. Nothing under a CoWork profile is written,
moved or removed: [cowork_driver.md](cowork_driver.md).

`--keep-temp` leaves a sandbox read-only, with the `home/` and `tmp/` trees the plugin wrote at
mode 000 under `sealed/`, so nothing walks into a tree the workload wrote. `logs.unseal` opens
one so collection can move the workspace out, and the sandbox root is removed once collection is
done.

The three collected names are written once, by `traces.collect`. Only the check layer writes
into a run directory after that, and it writes `scratch/` and `checks.jsonl` and nothing else.
Both happen before the verdict. Each arm's `tracePath` is rewritten to its own collected trace,
so a line about either arm names the right directory.

Collection runs whether or not the backend raised, because a run that left no result document
still left sandboxes, and a kept sandbox is read-only until something unseals it. With traces
off the harness is handed no `--keep-temp` and deletes each sandbox itself. The kept-sandbox
notice the harness prints per sandbox goes to `run.log` and to the terminal, one line per run.

`trace.jsonl` is never rewritten. A harness trace is read by `traces.last_message` and a session
transcript by `cowork.final_text`, so neither format is parsed twice. The harness record shapes
are [claude_code/plugin_eval_reference.md](claude_code/plugin_eval_reference.md), and the
session's are [cowork_desktop.md](cowork_desktop.md). No rendering of either is written, because
it would be a third format to keep true.

## The verdict

It reads every `<plugin>/aggregate-result.json` under the run directory and decides once, so a
sweep is decided once and not once per plugin. It reads `schemaVersion: 1` documents and
tolerates unknown fields; the contract is additive-only.

A run's grader results carry `name`, `passed` and `scored`, never `type`. The verdict joins each
result to the case's grader definition by name to learn its type, which tells an advisory check
from every other grader and which the line names. A `check` grader is this package's own, and
the verdict needs no condition for it.

A backend reads the keys a case file wrote, never the merged defaults: `runs: 3` is the harness
default for every case, and treating a default as a request would declare every case
unrunnable on CoWork. An explicit key is honoured when the backend's fixed behaviour already
satisfies it. The CoWork backend reads the `no-cowork` tag and submits nothing; it decides no
case skip of its own. The image-focus skip is decided after the run, from the file's bytes. See
[cowork_backend.md](cowork_backend.md).

`scored: false` splits on the arm. Treated as a skip on two arms, every two-arm run is red;
ignored on one arm, a real skip goes green in the one-arm run almost everybody runs. The verdict
reads what the document says and never re-derives which graders an arm dropped. It reads the
delta and never re-derives it.

A declared case is counted and neither passes nor fails. The case itself says the backend cannot
run it, the validator holds the case and the backend to the same rule, and the backend reports
it. It is out of `casesTotal`, which is why the last line carries it separately, and it is
printed even at 0 so a reader never has to look for it.

`partial: true` fails whatever `partialReason` says; the verdict reads the flag. An empty
document passes because a `--tag` sweep matches no case in most plugins, and failing on that
would make every filtered sweep red.

A two-arm run that produced no delta did not do what the invocation asked, and passing it would
be the green-on-nothing the arm exists to remove. Whether a run was two-arm is `suite.ablation`,
never a count of arms: a case whose baseline arm ran nothing carries one arm and is a failure.

`passed` on the last line is this package's own count. The harness counts a case as passed at
or above `--threshold`, which is 0 here, so `casesPassed` is every case. A one-arm run adds no
mean delta, because a number always 0 there would read as a plugin that changed nothing.

The `[artifacts: <dir>]` suffix comes from `tracePath` and is printed only when the directory is
on disk. It is on the three lines somebody reads a transcript over. A skipped case, a skipped
grader and a grader naming no definition are not verdicts about what the model produced, and
carry none.

### The tool conditions

Both are read out of the kept trace by `traces.py` and written into the run's entry in the
result document. `deniedTools` and `unofferedTools` are this package's own fields, like
`cowork`, additive-only, and absent when empty, so a healthy document is unchanged.

Only `decision_reason_type: mode` counts. A session has no permission mode, so a mode denial is
the container failing to behave like a session. A hook's denial is the plugin's behaviour, which
a session has too. Narrowing the rule to the tools a grader names would miss every denial that
broke a run through a tool no grader mentions.

A run that kept no trace yields nothing rather than every granted name, which is the same rule
as a trace with no `init` record.

## Logs

One directory per invocation, not one file per plugin: runs are non-deterministic, and a
per-plugin file overwrites the previous run.

`run.log` is captured at the file descriptor level, so a child process inherits it and the
harness's output and the container's both reach the file.

`debug.txt` exists only when the run is given one: `claude --debug-file <path> plugin eval ...
--verbose`. The flag goes before `plugin`, and it must be `--debug-file`: a bare `--debug` there
swallows the subcommand name as its filter. `--verbose` writes to that file only and never to
the terminal. A CoWork run writes neither `report.html` nor `debug.txt`, because both belong to
the harness.

Run-directory retention runs after every refusal and before the `--dry-run` exit, so a refused
invocation deletes nothing and an unattended dry run still reclaims space.

## Cost

`eval.max_cost_total_usd` binds first: five plugins at 5 USD each is 25. It has no command-line
option because it governs an invocation and not a run. Both ceilings are chosen values.

The measured smoke run's numbers are `durationSeconds` and `costUsd` read back from its
`aggregate-result.json`, on CLI 2.1.265, so the wall clock is the harness's own. A full sweep is
not measured here: this repository holds one fixture plugin, so that measurement belongs to a
consumer.

Nothing in this repository runs against its own fixtures on a cadence except the smoke case that
proves the backend reaches a running case.
