# Running evals

## Summary

`cowork_evals run` takes one path into a case tree and one backend, runs every case the path
selects, and reaches a single pass or fail over the whole invocation. This file is what the
command does with that tree: which pieces of the system are built, the `claude plugin eval`
flags it pins, which case a backend is told it cannot run, what each run leaves on disk, the
conditions that fail an invocation, and what a suite may cost.

- **This file carries the build status of the whole system.** No other file carries one; they
  link here.
- **Flags are pinned, not defaulted.** Every flag in the pinned list has a harness default
  this repository cannot accept.
- **This package decides pass and fail, not the harness.** It reads the result document, so one
  verdict covers both backends. Structural graders decide; judged graders are printed.
- **A skip fails the run**, so a backend cannot go green by honouring nothing. A case the
  backend was told it cannot run is counted instead.
- **Every invocation keeps everything it printed**, with every run's transcript in it.
- **Nothing here runs on CI.** A person runs the sweep and reads the summary.

The command surface is [cli.md](cli.md) and the packaging boundary is
[library.md](library.md). A case is written once, in the format at
[eval_format.md](eval_format.md), and runs on either backend. Which backend honours which part
of it is [approaches.md](approaches.md). The harness is [plugin_eval.md](plugin_eval.md). Do
not restate any of them here.

## Status

| Piece                                         | Built    | Designed in                          |
| --------------------------------------------- | -------- | ------------------------------------ |
| The 3.10 mirror, as a development script      | yes      | [environments.md](environments.md)   |
| The `cowork_evals` package, as a distribution | yes      | [library.md](library.md)             |
| The `cowork_evals` executable and its verbs   | yes      | [cli.md](cli.md)                     |
| `cowork_evals.yaml` and the `Config` over it  | yes      | [library.md](library.md)             |
| The pinned harness argument list              | yes      | this file                            |
| The run traces, on both backends              | yes      | this file                            |
| Pass and fail                                 | yes      | this file                            |
| The baseline arm, and the verdict over its delta | yes   | this file                            |
| The case validator                            | yes      | [eval_format.md](eval_format.md)     |
| The case history, and the `panel` verb over it | yes     | [panel.md](panel.md)                 |
| The check layer, over what a run produced     | yes      | [checks.md](checks.md)               |
| The container backend and its Dockerfile      | yes      | [docker.md](docker.md)               |
| `scripts/parity.sh` and `tests/unit/test_parity.py` | yes | [docker.md](docker.md)             |
| The CoWork driver                             | yes      | [cowork_driver.md](cowork_driver.md) |
| The CoWork backend over it                    | yes      | [cowork_backend.md](cowork_backend.md) |
| `plugins/smoke/`, the fixture both backends fire | yes   | `plugins/README.md`                  |
| The test image, `cowork-evals-test:<digest>`  | yes      | [cowork_test.md](cowork_test.md)     |
| The `test` verb over it                       | yes      | [cowork_test.md](cowork_test.md)     |
| A 3.10 and import check over code under test  | no       | nowhere, and it is not designed      |
| The venv backend and the runtime it stages    | deferred | [staged_runtime.md](staged_runtime.md) |

`deferred` means the design stands and the developer decided not to build it. Nothing in the
command surface reaches it.

## The cases a run selects

The case tree, the frontmatter and the graders are [eval_format.md](eval_format.md). What a
given path selects is [cli.md](cli.md). Both backends discover cases exactly as the harness
does, so nothing here configures discovery.

There is no marketplace-wide suite. The harness loads one plugin per run, so a cross-plugin
case is not expressible. A path holding several plugins runs every plugin's suite in turn,
each its own harness invocation, decided once.

There is no sweep on CoWork. One case there costs a VM boot plus a full agentic run and counts
against the driver's `max_runs` ceiling, so a sweep is a smoke set named case by case. That is
why [cli.md](cli.md) makes a multi-plugin path a usage error on `--cowork`.

The CoWork backend does not call `claude plugin eval`. It reads the same case tree, submits
each case's prompt body through the driver, grades the session document with the CoWork
grader, and writes the same `aggregate-result.json`. A case runs as many times as it wrote
`runs`, and once when it wrote none. Of the settings behind the pinned flags below it reads
`eval.judge_model`, for judged graders, and `eval.keep_traces`, which decides whether the run's
artefacts are collected. The rest configure the CLI, and the CLI is not in the path. See
[cowork_backend.md](cowork_backend.md).

### A case the backend is told it cannot run

A backend reads the keys the case file wrote, never the merged defaults. `runs: 3` is the
harness default for every case, so treating a default as a request would declare every case on
CoWork unrunnable and leave every run empty.

| In the case file                                        | On CoWork                                                                    |
| ------------------------------------------------------- | ---------------------------------------------------------------------------- |
| No `runs` key                                           | Runs once                                                                    |
| `runs: N`, written out                                  | Runs N times                                                                 |
| `timeout_seconds`, written out                          | That case's driver `run_timeout`                                             |
| `arm: with-only` or `arm: both` on a grader             | Honoured. One arm runs, it is the with-arm, and every grader is scored in it |
| `max_turns`, written out                                | The case declares `no-cowork`, and is counted                                |
| `model`, `allowed_tools`, `append_system_prompt`, `env` | The case declares `no-cowork`, and is counted                                |
| `context.*`, or a `mocks/` directory the case uses      | The case declares `no-cowork`, and is counted                                |
| `target` or `focus` of `mock_calls` on a grader         | That grader is skipped, and the case still runs                              |

A declared case and a grader skip are not one thing. A declared case submits nothing, is out
of every aggregate, and fails nothing. A grader skip runs the case and drops that grader from
the score, so the case does not fail for a grader that was never asked.

The rule is the same for both backends: an explicit key is honoured when the backend's fixed
behaviour already satisfies it. Which key each backend can honour is
[approaches.md](approaches.md). What the CoWork backend cannot honour is written into the case
as the `no-cowork` tag, which the validator enforces in both directions, and the tag is
[eval_format.md](eval_format.md). The backend reads the tag and submits nothing for that case;
it decides no case skip of its own.

One skip on that backend is decided after a run: an `llm` grader whose focus turns out to be
an image, which is read from the file's bytes. It fails the run like every other skip. See
[cowork_backend.md](cowork_backend.md).

## Pinned flags

Every flag below is pinned because its default would otherwise bite. What each flag does, and
the harness behaviour behind it, is in [plugin_eval.md](plugin_eval.md). Which of them a
command-line option overrides is [cli.md](cli.md).

| Flag                                         | Pinned to                         | Configuration key, and its default           |
| -------------------------------------------- | --------------------------------- | -------------------------------------------- |
| `--model`                                    | the configured model              | `eval.model`, `sonnet`                       |
| `--judge-model`                              | the configured judge              | `eval.judge_model`, `haiku`                  |
| `--ablation`                                 | the configured arm                | `eval.ablation`, `none`                      |
| `--threshold`                                | `0`, so this package decides      | none                                         |
| `--max-cost-usd`                             | the configured ceiling            | `eval.max_cost_usd`, 5                       |
| `--output-dir`                               | the run's log directory           | none                                         |
| `--allow-tools`                              | the configured grant              | `eval.allow_tools`, the session mirror below |
| `--keep-temp`                                | on, when the run keeps its traces | `eval.keep_traces`, true                     |
| `--no-publish`, `--no-scaffold`, `--verbose` | always                            | none                                         |

The target goes before every variadic flag: `--tag` and `--allow-tools` swallow a trailing
target.

`--threshold` has no command-line option and cannot be overridden. `--threshold 0` is what
hands pass and fail to this package. The number a two-arm run is decided on is
`eval.delta_threshold`, which the verdict reads and which reaches no command line.

`eval.keep_traces` is the one key in this table that is not only a flag. It decides this flag
on the container backend, and it decides whether a run's artefacts are collected on both. The
CoWork backend runs no command line, so there is nothing to pin there and the key still binds.

The container backend exports `CLAUDE_CODE_WALNUT_SPIRE`, the early-access enablement
variable, so no developer sets it by hand. It is a constant in `harness.py` and not a
configuration key. `--json` is never passed. Both are [plugin_eval.md](plugin_eval.md).

### The tool grant

The default is what a CoWork session can do, in the container's tool names:

```
Bash Read Glob Grep Write Edit WebFetch Skill
```

A session grants nothing and asks nothing. It writes files, shells out, reaches the network and
reads a skill off its mount, all measured in [cowork_desktop.md](cowork_desktop.md). The
container backend exists to run the same case the same way, so a tool a session has and a
container run is denied makes that run measure this package's configuration rather than the
plugin. The names differ because the two are different programs: a session's
`mcp__workspace__bash` is the container's `Bash`, and its `mcp__workspace__web_fetch` is
`WebFetch`.

`--allow-tools` is pinned because a case cannot grant itself `Bash`, `Write`, `Edit`,
`WebFetch` or an MCP tool. The operator grant is the only route, and an ungranted case loses the
tool rather than failing loudly. `eval.allow_tools` and `--allow-tools` replace the value rather
than adding to it, so any replacement names every tool it still wants.

`Read`, `Glob` and `Grep` are named although they are read-only tools the harness grants by a
route of its own. Naming them is not a no-op: on CLI 2.1.265 a run granted only `Bash` offered
the model no `Glob` and no `Grep`.

Two things this default is not. It is not `WebSearch`, which no session was measured using. And
a bare `WebFetch` says nothing about which domains a run can reach: the harness restricts
network access to the domains a `WebFetch(domain:...)` grant names, and that has not been
measured here.

On CLI 2.1.265 every granted name reaches the run bare, in the `init` record's tool list, never
in a `Tool(pattern)` shape; the path scoping applied to a bare `Read`, `Glob` or `Grep` is in
the child's permission rules and not in that list. That list is longer than the grant, because
`Task`, `WebSearch` and others are offered without being granted, so a name in it is not
permission to call it. The check below therefore reads it in one direction only: a granted name
absent from it was never offered.

A grant is not a capability. A narrower grant does not by itself take a tool away from a case
that did not ask for one: a grant of everything but `Write` still created a file, through `Bash`
and `Edit`. What produces a denial is a grant carrying no tool that can do the work.

### The baseline arm, and `arm:` on a grader

`--ablation with-without` runs every case twice. The with-arm loads the plugin under test. The
without-arm loads no plugin. The score delta between them is the evidence that the plugin
changed behaviour, rather than the model answering well on its own.

A `tool_used: Skill` grader cannot pass in the without-arm, because no plugin is loaded and no
skill can fire. The harness therefore drops such a grader from the score in both arms, so the
two arms are compared on the same graders. It still reports it, as an indicator carrying
`withOnly: true` and `scored: false`. `arm:` on a grader is the case author's control over
that.

| Value                                  | Scores in                                                               |
| -------------------------------------- | ----------------------------------------------------------------------- |
| `with-only`                            | The with-arm only                                                       |
| `both`                                 | Every arm that runs                                                     |
| Absent, on a `tool_used: Skill` grader | The with-arm only. That is the harness default for this one grader shape |
| Absent, on anything else               | Every arm that runs                                                     |

A case whose graders are all with-only is the exception. There is nothing left to compare, so
the harness scores them normally in both arms.

`--ablation none` runs one arm, and that arm is the with-arm. Nothing is dropped from the score,
so a `tool_used: Skill` grader is scored and the verdict reads it. `arm:` then satisfies itself
whichever value it carries, and a case sets it only to stay portable to a suite that does run
the baseline arm.

| Setting                | Values                 | Default | Read by                  |
| ---------------------- | ---------------------- | ------- | ------------------------ |
| `eval.ablation`        | `none`, `with-without` | `none`  | the harness command line |
| `eval.delta_threshold` | a number from 0 to 1   | `0`     | the verdict, below       |

The arm is off by default because it runs every case twice and so costs twice as much, and
because it stops scoring the one grader that says the skill fired at all. Both are the
container backend's: the CoWork backend runs one arm, for the reason in
[cowork_backend.md](cowork_backend.md), so `--ablation` and `--delta-threshold` are both a
usage error on `--cowork`. What a two-arm suite costs in model calls is
[plugin_eval.md](plugin_eval.md).

### What a two-arm document holds

| Where                       | Field                                                           | Holds                                                            |
| --------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------ |
| `suite`                     | `ablation`                                                      | `with-without`                                                   |
| a case's `arms`             | `with`, `without`                                               | one run list each. The second arm's key is `without`             |
| a case's `aggregates`       | `score`, `passRate`, `scoreWithout`, `passRateWithout`, `delta` | `delta` is `score - scoreWithout`, and the document works it out  |
| the document's `aggregates` | `meanDelta`                                                     | the mean of the case deltas that are defined                     |

The delta is read and never re-derived. A one-arm document carries `score` and `passRate`
alone, and no `arms.without`.

| The grader                        | In the with-arm                   | In the without-arm                |
| --------------------------------- | --------------------------------- | --------------------------------- |
| `tool_used: Skill` with no `arm:` | `withOnly: true`, `scored: false` | absent from the grader list       |
| The same grader under `arm: both` | `withOnly: false`, `scored: true` | `withOnly: false`, `scored: true` |
| Every other grader                | `withOnly: false`, `scored: true` | `withOnly: false`, `scored: true` |

Two arms can be graded under different rules, and then the document carries no delta. A run
that overran `--max-cost-usd` and had its paid graders skipped is one such case: that run
carries `skippedPaidGraders: true`, the case's `aggregates.delta` and `aggregates.scoreWithout`
are both omitted while `score`, `passRate` and `passRateWithout` stay, and the document's
`aggregates.meanDelta` is omitted. `partial` stays `false`, and there is no `partialReason`.

A paid grader skipped at the ceiling is not a grader skip. It carries `passed: false`,
`scored: true` and `explanation: skipped: cost ceiling`, and no `skipped` flag at all.

## What a run leaves behind

A failing case has to be readable after the fact. The failure line names the grader and the
reason, and nothing else survives on its own: the harness deletes the sandbox of every run that
did not error, and a CoWork session is a directory in a profile nobody thinks to open.

Every run of either backend keeps the same three artefacts, under the same names, whether it
passed or failed:

| Artefact           | Is                                                                     |
| ------------------ | ------------------------------------------------------------------------ |
| `trace.jsonl`      | The transcript                                                         |
| `last_message.txt` | The final assistant message, which is what a `last_message` grader read |
| `workspace/`       | The agent's working directory                                          |

A case carrying checks leaves two more, `scratch/` and `checks.jsonl`, written by the layer
that runs them. Both are [checks.md](checks.md).

One layout, so a case is read the same way whichever backend produced it, and a run on one
can be held against a run on the other. A passing run is what a failing one is read against,
and which of three runs failed is not known before the run.

What differs is where the three are read from, and whether they are moved or copied:

| Backend    | The artefacts are in                        | And are | Because                                                     |
| ---------- | --------------------------------------------- | ------- | ------------------------------------------------------------ |
| `--docker` | the sandbox `--keep-temp` kept, on the host | moved   | A sandbox is a throwaway directory, and moving empties it   |
| `--cowork` | the CoWork session directory                | copied  | A session is the account's own record, and is never written |

`--keep-temp` is pinned on for the container backend. The sandbox it keeps is created under
the harness's `TMPDIR`, which that backend points at the run's log mount, so it lands on the
host rather than inside a container started with `--rm`. See [docker.md](docker.md). The rest
of a sandbox is removed: the child's configuration directory, its npm logs, its node compile
cache and its sockets. None of it says anything about the run, and it is 40 times the size of
what is kept. Nothing under a CoWork profile is written, moved or removed:
[cowork_driver.md](cowork_driver.md).

### The layout a checker reads

A consumer who wants to know what an eval produced, such as whether the `.pptx` a skill wrote
will open, writes their own script over the files a run left. That script is theirs:
[library.md](library.md). One directory per run:

```
<log root>/<yyyymmdd-hhmmss>-<scope>/<plugin>/traces/<case>/run-<n>/
  trace.jsonl
  last_message.txt
  workspace/
  scratch/          # only where the case carries checks
  checks.jsonl      # the same
```

`<n>` is 1-based and is the number the verdict line prints as `run N`. A second case of the
same name inside one plugin is suffixed `-2`, as a second plugin of one name is. A failure
line about that run names the directory as `[artifacts: <dir>]`.

The with-arm's path is the path above. Under `--ablation with-without` the baseline arm's runs
go in a directory of their own, named for the arm, between the case and the run:

```
<log root>/<yyyymmdd-hhmmss>-<scope>/<plugin>/traces/<case>/without/run-<n>/
```

`traces/<case>/run-*` therefore still selects the with-arm alone in a two-arm run. Both arms
keep the same three names, and each arm's `tracePath` is rewritten to its own collected trace,
so a failing delta is read as two transcripts and a line about either arm names the right
directory.

The three collected names are written once, by `traces.collect`. Only the check layer writes
into a run directory after that, and it writes `scratch/` and `checks.jsonl` and nothing else.
Both happen before the verdict is reached.

A kept sandbox is not the place to read. `--keep-temp` leaves it read-only, with the `home/`
and `tmp/` trees the plugin under test wrote at mode 000 under `sealed/`, so that nothing walks
into a tree the workload wrote. `logs.unseal` opens one so that collection can move the
workspace out of it, and the sandbox root is removed once collection is done. A checker reads
the collected `workspace/` instead, at the modes the agent left.

A checker's verdict stays outside. It does not reach `aggregate-result.json` and fails nothing:
`cowork_evals run` exits on the conditions below and on no other. A script that does need to
decide the run is a check, in the case's own `checks/` directory, and its verdict reaches the
document like any other grader's. See [checks.md](checks.md).

### The two transcript formats

`trace.jsonl` is the transcript the backend that produced it wrote, and neither is rewritten.
One name, two formats. They are close, and a reader that assumes one of them on both is wrong.

|                          | `--docker`                                 | `--cowork`                               |
| ------------------------ | ------------------------------------------ | ---------------------------------------- |
| Written by               | `claude plugin eval`, into the run sandbox | the CoWork application, into the session |
| The record shapes are in | [claude_code/plugin_eval_reference.md](claude_code/plugin_eval_reference.md) | [cowork_desktop.md](cowork_desktop.md) |
| Read here by             | `traces.last_message`                      | `cowork.final_text`                      |

What they share is the shape a reader needs: one JSON object per line, a `type`, and a
`message` of `{role, content}` on a turn, where `content` is a string or a list of blocks and a
tool call and its result are a `tool_use` and a `tool_result` block paired by id. That is why
one `last_message.txt` means the same thing on both. Three differences matter:

- **Only a harness trace ends in a `result` record**, and that record carries the final
  message verbatim. A session transcript has none, so the final message there is the last
  assistant text block. Each is read by whatever already parses that format, and neither
  format is parsed twice.
- **A session transcript carries an open set of record types**, listed in
  [cowork_desktop.md](cowork_desktop.md), and only `user` and `assistant` carry a `message`.
  A reader takes turns from those two and ignores the rest.
- **A harness trace carries the run's own envelope.** The types observed on the smoke case on
  CLI 2.1.265 are `system`, `assistant`, `user`, `rate_limit_event` and `result`.

No rendering of either is written. One would be a third format to keep true.

### When collection cannot be done

A collection problem is a warning on stderr and never a failed run. A sandbox that was not
kept, a session the driver never reached, a trace that will not read and a result document
that will not parse are each one line saying so, and the run keeps whatever verdict it already
had. A run that already carries an `error` says nothing: the error is why there is nothing to
collect, and the verdict line prints it.

Collection runs whether or not the backend raised, because a run that left no result document
still left sandboxes behind, and a kept sandbox is read-only until something unseals it.

Turning it off is `--no-keep-traces` or `eval.keep_traces: false`, on either backend. Off,
nothing is created and nothing is collected, and the harness deletes each sandbox itself. Off
also gives up every check: a check reads the collected run directory, so each check of that
case is a skip, and a skip fails the run. See [checks.md](checks.md).

A smoke case on the container backend keeps 12 KB per run, beside the `run.log`, `report.html`
and `debug.txt` the invocation writes once. A CoWork run's cost is the size of its `outputs/`,
which is whatever the case made the session produce. The kept-sandbox notice the harness prints
per sandbox goes to `run.log` and to the terminal, one line per run.

## Pass and fail

This package decides pass and fail, not the harness. It reads the result document, so one
verdict covers both backends, and it always runs in the `cowork_evals` process on the host. It
reads every `<plugin>/aggregate-result.json` under the run directory and decides once for the
whole invocation, so a sweep is decided once and not once per plugin.

| Condition                                                            | Result       |
| -------------------------------------------------------------------- | ------------ |
| Any `regex`, `tool_used`, `tool_order`, `file_exists` or `check` grader failed | exit 1 |
| Any case or grader reported skipped                                  | exit 1       |
| A grader reported `scored: false`, on one arm                        | exit 1       |
| A grader reported `scored: false`, on two arms                       | printed only, when it did not fire |
| A case's delta is below `eval.delta_threshold`, on two arms          | exit 1       |
| A case carries no delta, on two arms                                 | exit 1       |
| A case reported `declaredUnrunnable`                                 | exit 0, counted |
| `partial: true`, whatever `partialReason` says                       | exit 1       |
| A run carrying `error`, on either backend                            | exit 1       |
| A run the permission mode refused a tool, on `--docker`              | exit 1       |
| A run never offered a tool the grant named, on `--docker`            | exit 1       |
| A sweep stopped by `eval.max_cost_total_usd`                         | exit 1       |
| A results document is missing, unparsable, or of another `schemaVersion` | exit 1   |
| A grader result naming no grader the case defines                    | exit 1       |
| Any `llm` or `baseline` grader failed                                | printed only |
| A document whose `aggregates.casesTotal` is 0                        | exit 0       |
| Otherwise                                                            | exit 0       |

Structural graders decide because a judged grader over a non-deterministic agent is a flaky
verdict. A `check` grader is this package's own, not the harness's, and it decides for the same
reason: it is an author's Python over what the run produced, deterministic unless the author
made it otherwise. The verdict needs no condition for it. See [checks.md](checks.md).

Every line printed carries `FAIL` or `NOTE`, so a judged failure is never read as the cause of
exit 1. A run's grader results carry `name`, `passed` and `scored`, never `type`, so the
verdict joins each result to that case's grader definition by name to learn which class it is
in. It reads `schemaVersion: 1` documents and tolerates unknown fields; the contract is
additive-only.

`scored: false` splits on the arm. Too strict and every two-arm run is red; too loose and a
real skip goes green in the one-arm run almost everybody runs.

| The run           | `scored: false` on a grader                                                                                    |
| ----------------- | ---------------------------------------------------------------------------------------------------------------- |
| `--ablation none` | A skip, and it fails the run. Nothing is dropped from the score, so a grader that was not scored was not asked |
| `with-without`    | Expected on a with-only grader. It fails nothing, and it is printed as an indicator when it did not fire       |

A case whose graders are all with-only is the harness's own exception and arrives carrying
`scored: true`. The verdict reads what the document says and never re-derives which graders an
arm dropped.

A declared case is not a skip. The case itself says the backend cannot run it, the validator
holds the case and the backend to the same rule, and the backend reports it rather than
deciding it, so it is counted and neither passes nor fails. It is out of that document's
`casesTotal` as well, which is why the summary line carries it separately.

`partial: true` fails whatever the reason. The harness names `cost_ceiling` and `auth_failed`,
and `interrupted` is a third; the verdict reads the flag and not the reason.

A run carrying `error` fails on every backend. On CoWork it is a case the driver could not run
or collect. On the harness it is a run that timed out, hit the turn cap or exited non-zero,
each of which is still graded on what it produced, so the score alone does not catch it.

An empty document passes. A `--tag` sweep matches no case in most plugins, and failing on that
would make every filtered sweep red. A selection matching no case *anywhere* is refused before
the run instead, with exit 2. See [cli.md](cli.md).

### The delta, on a two-arm run

Per case, and never per suite: a suite average hides the one case the plugin made worse. The
delta is `score - scoreWithout`, the document works it out, and a case below
`eval.delta_threshold` fails on a line naming both scores and the delta.

A two-arm case the document says is not comparable fails as well. A two-arm run that produced
no delta did not do what the invocation asked, and passing it would be the green-on-nothing
the arm exists to remove. The line names which of the two reasons it was:

| The document                             | The line says                                      |
| ---------------------------------------- | ---------------------------------------------------- |
| `arms.without` is empty                  | the baseline arm ran nothing                       |
| A run carries `skippedPaidGraders: true` | a run skipped its paid graders at the cost ceiling |

The failure is the same either way. Every other condition in the table above is unchanged and
reads the with-arm, on one arm and on two.

Whether a run was two-arm is `suite.ablation` in the document, and never a count of the arms a
case carries: a case of a two-arm run whose baseline arm ran nothing carries one arm and is a
failure, not a one-arm case. Under `--ablation none` there is one arm and no delta, and the
verdict is reached exactly as it is without the arm.

### A run that never had the tool

A run scored on what the model wrote without a tool the case was granted is not a fact about
the plugin. Two conditions above catch it, one per way a run loses a tool. Both are read out of
the kept trace by `traces.py` and written into that run's entry in the result document.

| The tool was                                    | The trace holds                        | The field        |
| ----------------------------------------------- | -------------------------------------- | ---------------- |
| Granted, and the call refused                   | a `permission_denied` record naming it | `deniedTools`    |
| Granted, and never offered to the model         | an `init` list missing it              | `unofferedTools` |
| Never granted, so never offered and never tried | nothing                                | neither          |

Both fields are this repository's own, like `cowork`, and the contract is additive-only.
Neither is written when there is nothing to write, so a healthy document is unchanged.

Only `decision_reason_type: mode` counts as a denial. A session has no permission mode and is
never refused a tool by one, so a mode denial is the container failing to behave like a session
and nothing else. A denial the plugin's own hook wrote is the plugin's behaviour, which a
session has too and which a case testing that hook is asserting over. The rule matches on the
reason and never on the tool name: narrowing it to the tools a grader names would miss every
denial that broke a run through a tool no grader mentions.

A granted name and an offered name are compared on the part before any `(`, because a grant may
be written `WebFetch(domain:example.com)`.

Both conditions need a kept trace, so `--no-keep-traces` and `eval.keep_traces: false` give up
both. Off, the harness is handed no `--keep-temp`, no sandbox reaches the host, and neither
field reaches the result document. A run that kept no trace says nothing about what it had,
which is the same rule as a trace with no `init` record: it yields nothing rather than every
granted name. Nothing warns about it.

Neither condition can fire on CoWork. A session has no permission mode and writes no tool list,
so neither field ever appears there and one decision still covers both backends. See
[approaches.md](approaches.md).

**The bound.** Both checks start from the grant. A tool the case needed and nobody granted is
never offered and never tried, leaves nothing in the trace, and is caught by neither. That is
the case for a plugin's own MCP server, whose tools are named
`mcp__plugin_<plugin>_<server>__<tool>` and which no built-in default can name, and for
`WebSearch`, which the session mirror omits. A green suite is not proof that every run had
everything its case asked for.

### The last line

The last line carries five counts and the overall score:

| Count      | Is                                                        | Counted by            |
| ---------- | ----------------------------------------------------------- | --------------------- |
| `found`    | The cases under the path, before any filter               | this package's reader |
| `picked`   | The cases `--tag` and `--case` kept                       | the same reader       |
| `ran`      | The cases a backend reported running, `casesTotal`        | the backend           |
| `passed`   | The cases that produced no failure line                   | the verdict           |
| `declared` | The cases carrying `no-cowork` on a backend that reads it | the verdict           |

A declared case is why `ran` can be below `picked` on a suite where nothing went wrong. It is
printed even when it is 0, because a count that appears only sometimes is one a reader has to
go and look for. Picked and ran otherwise differ when a plugin failed to run, when the sweep
stopped early, or when the harness picked differently. Both are printed, and neither is checked
against the other.

`passed` is this package's own count and is never `aggregates.casesPassed`. The harness counts
a case as passed at or above `--threshold`, which is pinned to 0 here, so `casesPassed` is every
case always and reading it back would print a pass on the line under a failure.

The score is the mean of each document's `overallScore`. A two-arm run adds the mean delta
beside it, which is the mean of the `meanDelta` of each document that carried one, and reads
`mean delta none` when no document did. A one-arm run adds nothing: there is no delta on one
arm, and a number that is always 0 there would read as a plugin that changed nothing. A
document marked `partial` adds `stopped early` and the reason to the end of the line.

A line about what one run produced ends with `[artifacts: <dir>]`, naming the directory holding
that run's transcript. It is on a failed structural grader, a failed judged grader and an
errored run, which are the three lines somebody goes and reads a transcript over. A skipped
case, a skipped grader and a grader naming no definition carry none: none of them is a verdict
about what the model produced, and there is no transcript behind them.

The directory comes from the run's `tracePath` and is printed only when it is on disk, so a run
whose trace was not collected carries no suffix. `traces.py` rewrites that field to the trace it
collected on both backends. A CoWork run's session directory is still in `cowork.sessionDir`.

## Logs

Every invocation keeps everything it printed, in one directory per invocation. Not one file
per plugin: runs are non-deterministic, and a per-plugin file overwrites the previous run.

```
logs/evals/<yyyymmdd-hhmmss>-<scope>/
  run.log                        # stdout and stderr of the whole invocation, tee'd live
  verdict.txt                    # the verdict
  env.txt                        # cowork_evals --version, claude --version, python3 -V,
                                 #   the backend, the image and the credential route on the
                                 #   container backend, and the forwarded variable names,
                                 #   never a value
  <plugin>/aggregate-result.json # the v1 result document
  <plugin>/report.html           # the self-contained HTML report
  <plugin>/debug.txt             # claude --debug-file output
  <plugin>/traces/<case>/run-<n>/trace.jsonl       # the run's transcript
  <plugin>/traces/<case>/run-<n>/last_message.txt  # its final assistant message
  <plugin>/traces/<case>/run-<n>/workspace/        # the agent's working directory
logs/evals/latest                # symlink to the newest directory
```

The log root is `logs/evals` under the working directory unless `--out DIR` replaces it whole,
and `<scope>` is named from the path argument. Both are [cli.md](cli.md). Run directories older
than 30 days are deleted at the start of every run, after every refusal and before the
`--dry-run` exit, so a refused invocation deletes nothing and an unattended dry run still
reclaims space. The age is read from the directory name and never from a modification time.

`run.log` is captured at the file descriptor level, so a child process inherits it and the
harness's own output and the container's both reach the file.

A CoWork run writes `<plugin>/aggregate-result.json` and `<plugin>/traces/`. There is no
`report.html` and no `debug.txt` on that backend: the first is the harness's, the second is
`claude --debug-file`, and the harness is in neither path. The debug log exists only when the
run is given one: `claude --debug-file <path> plugin eval ... --verbose`. The flag goes before
`plugin`, and it must be `--debug-file`: a bare `--debug` there swallows the subcommand name as
its filter. `--verbose` writes to that file only and never to the terminal.

A run directory is not the record of what a case did. It is deleted at the retention above,
and what outlives it is one line per case under `logs/evals/history/`, which `cowork_evals
panel` reads. See [panel.md](panel.md).

## Cadence

An eval is not a commit-time check. `git commit` runs nothing, and there is no hook.

Which command runs at which moment is the table in [approaches.md](approaches.md). Who
enforces it is the consumer repository: the author while writing a case, the PR template
before a PR, the release checklist before a release. That cadence is for a consumer
repository. Nothing here runs against this repository's own fixtures except the smoke case
that proves the backend reaches a running case.

## Nothing here runs on CI

No hook, no PR job, no workflow shipped by this package. A person runs the sweep and reads the
summary. The reason is not cost: a red verdict over cases nobody trusts gets routed around
rather than fixed.

A consumer automates it when all four of these hold, and not before:

| Condition                                                             | Read from                                                                |
| ---------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Every skill under test has at least one case                          | the `evals/` tree, reported by `run` and enforced by `--require-coverage` |
| Structural graders carry the verdict, with a measured flake rate      | `logs/evals/*/`                                                          |
| The cost and wall-clock time of a full sweep are measured and accepted | the cost section below                                                   |
| A credential and a pinned CLI on a runner have an owner               | a decision                                                               |

## Cost

[plugin_eval.md](plugin_eval.md) counts the model calls a suite makes. This file sets the
ceilings on what they may cost.

| Ceiling                   | Default | Binds                | Reached through       |
| ------------------------- | ------- | -------------------- | --------------------- |
| `eval.max_cost_usd`       | 5       | one plugin's suite   | `--max-cost-usd`      |
| `eval.max_cost_total_usd` | 25      | the whole invocation | the key only, no flag |

Both are chosen values, not measured ones.

`eval.max_cost_usd` is a harness flag, so a check judge's spend is outside it: the harness has
already finished when a check runs. That spend is added to the document's `costUsd`, so
`eval.max_cost_total_usd` binds it at the next plugin of a sweep. What a check costs is
[checks.md](checks.md).

The total binds first: five plugins at 5 USD each is 25. A sweep sums `costUsd` from each
plugin's result document and checks the total before every plugin, the first included, so a
ceiling of 0 stops it before it spends anything. A sweep that stops on the ceiling is a failure,
never a pass. On `--cowork` that sum is the judge spend alone, because a session is billed to
the account and is not observable from the host; the ceiling that binds there is the driver's
`max_runs`, in the preflight. The total has no command-line option because it governs an
invocation rather than a run, and [cli.md](cli.md) lists only the options a run takes.

One measured run: a smoke case at `runs: 1` on the container backend, on CLI 2.1.265 with
`sonnet` and the `haiku` judge, took 8 s and cost 0.057 USD. Both numbers are `durationSeconds`
and `costUsd` read back from its `aggregate-result.json`, so the wall clock is the harness's own
and excludes the image build and the container start. A full sweep is not measured here: this
repository holds one fixture plugin, so that measurement belongs to a consumer.
