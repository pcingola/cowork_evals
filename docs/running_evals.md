# Running evals

## Summary

The eval system behind the command: what is built, the pinned harness flags, the gate, the
logs, the cadence and the cost. This file is the design. It is true whether or not a given
piece is built yet.

- **This file carries the build status of the whole system.** No other file carries one; they
  link here.
- **Flags are pinned, not defaulted.** Every flag in the pinned list would bite at its
  default.
- **The gate decides pass and fail, not the harness.** It reads the result document, so one
  gate covers both backends. Structural graders gate; judged graders are printed.
- **A skip fails the gate**, so a backend cannot go green by honouring nothing.
- **Every invocation keeps everything it printed**, in one directory per invocation, and
  every run's transcript with it.
- **Nothing here runs on CI.** A person runs the sweep and reads the summary.

The command surface is [cli.md](cli.md) and the packaging boundary is
[library.md](library.md). A case is written once, in the format at
[eval_format.md](eval_format.md), and runs on either backend. Which backend honours which part
of it is [approaches.md](approaches.md). The harness is [plugin_eval.md](plugin_eval.md). Do
not restate any of them here.

## Status

| Piece                                         | Built    | Designed in                                  |
| --------------------------------------------- | -------- | -------------------------------------------- |
| The 3.10 mirror, as a development script      | yes      | [environments.md](environments.md)           |
| The `cowork_evals` package, as a distribution | yes      | [library.md](library.md)                     |
| The `cowork_evals` executable and its verbs   | yes      | [cli.md](cli.md)                             |
| `cowork_evals.yaml` and the `Config` over it  | yes      | [library.md](library.md)                     |
| The pinned harness argument list              | yes      | this file                                    |
| The run traces, kept under the log directory, on both backends | yes | this file                    |
| The gate                                      | yes      | this file                                    |
| The case validator                            | yes      | [eval_format.md](eval_format.md)             |
| The 3.10 and import check over code under test | no      | nowhere. Not designed, and no plan builds it |
| The container backend and its Dockerfile      | yes      | [docker.md](docker.md)                       |
| `scripts/parity.sh` and `tests/unit/test_parity.py` | yes | [docker.md](docker.md)                     |
| The CoWork driver                             | yes      | [cowork_driver.md](cowork_driver.md)         |
| The CoWork backend over it                    | yes      | [cowork_backend.md](cowork_backend.md)       |
| `plugins/smoke/`, the fixture both backends fire | yes   | `plugins/README.md` |
| The test image, `cowork-evals-test:<digest>`  | yes      | [cowork_test.md](cowork_test.md)             |
| The `test` verb over it                       | yes      | [cowork_test.md](cowork_test.md)             |
| The venv backend and the runtime it stages    | deferred | [staged_runtime.md](staged_runtime.md)       |

`deferred` means the design stands and the developer decided not to build it. Nothing in the
command surface reaches it.

## The cases it runs

The case tree, the frontmatter and the graders are [eval_format.md](eval_format.md). What a
given path selects is [cli.md](cli.md). The backends discover cases exactly as the harness
does, so nothing here configures discovery.

There is no marketplace-wide suite. The harness loads one plugin per run, so a cross-plugin
case is not expressible. A path holding several plugins means every plugin's suite in turn,
each its own harness invocation, gated once.

There is no sweep on CoWork. One case there costs a VM boot plus a full agentic run and counts
against the driver's `max_runs` ceiling, so a sweep is a smoke set named case by case. That is
why [cli.md](cli.md) makes a multi-plugin path a usage error on `--cowork`.

The CoWork backend does not call `claude plugin eval`. It reads the same case tree, submits
each case's prompt body through the driver, grades the session document with the CoWork
grader, and writes the same `aggregate-result.json`. A case runs as many times as it wrote
`runs`, and once when it wrote none. Of the pinned flags below it uses only
`eval.judge_model`, for judged graders. The rest configure the CLI, and the CLI is not in the
path. See [cowork_backend.md](cowork_backend.md).

### What counts as a case the backend cannot honour

A backend reads the keys the case file writes, never the merged defaults. `runs: 3` is the
default for every case, so treating a default as a request would skip every case on CoWork and
leave the gate permanently red.

| In the case file                                        | On CoWork                                                                    |
| ------------------------------------------------------- | ---------------------------------------------------------------------------- |
| No `runs` key                                           | Runs once                                                                    |
| `runs: N`, written out                                  | Runs N times                                                                 |
| `timeout_seconds`, written out                          | That case's driver `run_timeout`                                             |
| `arm: with-only` or `arm: both` on a grader             | Honoured. One arm runs, it is the with-arm, and every grader is scored in it |
| `max_turns`, written out                                | Skipped                                                                      |
| `model`, `allowed_tools`, `append_system_prompt`, `env` | Skipped                                                                      |
| `context.*`, or a `mocks/` directory the case uses      | Skipped                                                                      |
| `target` or `focus` of `mock_calls` on a grader         | That grader is skipped, and the case still runs                              |

A grader skip and a case skip are not one thing. A case skip submits nothing. A grader skip
runs the case and drops that grader from the score, so the case does not fail for a grader
that was never asked.

The rule is the same for both backends: an explicit key is honoured when the backend's fixed
behaviour already satisfies it, and skipped otherwise. Which key each backend can honour is
[approaches.md](approaches.md). A skip is written into the result document with its reason and
fails the gate, so a backend cannot go green by honouring nothing.

## Pinned flags

Every flag below is pinned because its default would otherwise bite. What each flag does, and
the harness behaviour behind it, is in [plugin_eval.md](plugin_eval.md). Which of them a
command-line option overrides is [cli.md](cli.md).

| Flag                                         | Pinned to                      | Configuration key, and its default |
| -------------------------------------------- | ------------------------------ | ---------------------------------- |
| `--model`                                    | the configured model           | `eval.model`, `sonnet`             |
| `--judge-model`                              | the configured judge           | `eval.judge_model`, `haiku`        |
| `--ablation`                                 | `none`                         | none                               |
| `--threshold`                                | `0`, so the local gate decides | none                               |
| `--max-cost-usd`                             | the configured ceiling         | `eval.max_cost_usd`, 5             |
| `--output-dir`                               | the run's log directory        | none                               |
| `--allow-tools`                              | the configured grant           | `eval.allow_tools`, `[Bash]`       |
| `--keep-temp`                                | on, when the run keeps its traces | `eval.keep_traces`, true        |
| `--no-publish`, `--no-scaffold`, `--verbose` | always                         | none                               |

The target goes before every variadic flag: `--tag` and `--allow-tools` swallow a trailing
target.

`--ablation` and `--threshold` have no command-line option and cannot be overridden.
`--threshold 0` is what hands pass and fail to the gate below.

`eval.keep_traces` is the one key in this table that is not only a flag. It decides this flag
on the container backend, and it decides whether a run's artefacts are collected on both. The
CoWork backend runs no command line, so there is nothing to pin there and the key still binds.
See below.

### The baseline arm, and `arm:` on a grader

`--ablation with-without` runs every case twice. The with-arm loads the plugin under test. The
without-arm loads no plugin. The score delta between them is the evidence that the plugin
changed behaviour, rather than the model answering well on its own.

A `tool_used: Skill` grader cannot pass in the without-arm, because no plugin is loaded and no
skill can fire. The harness therefore drops such a grader from the score in both arms, so the
two arms are compared on the same graders. It still reports it, as an indicator carrying
`withOnly: true` and `scored: false`.

`arm:` on a grader is the case author's control over that.

| Value                                  | Scores in                                                               |
| -------------------------------------- | ----------------------------------------------------------------------- |
| `with-only`                            | The with-arm only                                                       |
| `both`                                 | Every arm that runs                                                     |
| Absent, on a `tool_used: Skill` grader | The with-arm only. That is the harness default for this one grader shape |
| Absent, on anything else               | Every arm that runs                                                     |

A case whose graders are all with-only is the exception. There is nothing left to compare, so
the harness scores them normally in both arms.

`--ablation none` runs one arm, and that arm is the with-arm. Nothing is dropped from the
score, so a `tool_used: Skill` grader is scored and the gate reads it. That is why it is
pinned. `arm:` then satisfies itself whichever value it carries, and a case sets it only to
stay portable to a suite that does run the baseline arm.

A baseline arm is an investigation, run by calling the harness by hand, and it is not a run of
this command. It doubles the agent runs, and the table in
[plugin_eval.md](plugin_eval.md) counts them.

`--allow-tools` is pinned because a case cannot grant itself `Bash`, `Write`, `Edit`,
`WebFetch` or an MCP tool. The operator grant is the only route, and an ungranted case loses
the tool rather than failing loudly. `Bash` is the default because a skill that shells out
needs it. Widen it through `eval.allow_tools` or `--allow-tools`, which replace the value
rather than adding to it, so the widened value has to name `Bash` again.

The Docker backend exports `CLAUDE_CODE_WALNUT_SPIRE`, the early-access enablement variable,
so no developer sets it by hand. It is a constant in `harness.py` and not a configuration key.
See [plugin_eval.md](plugin_eval.md).

`--json` is never passed, for the reason in [plugin_eval.md](plugin_eval.md).

### Keeping the traces

A failing case has to be readable after the fact. The failure line names the grader and the
reason, and nothing else survives on its own: the harness deletes each run's sandbox, and a
CoWork session is a directory in a profile nobody thinks to open. A slow suite is 15 to 30
minutes, so a failure that cannot be read is a failure nobody investigates.

Every run of either backend keeps the same three artefacts, under the same names, whether it
passed or failed:

| Artefact           | Is                                                                |
| ------------------ | ------------------------------------------------------------------ |
| `trace.jsonl`      | The transcript                                                     |
| `last_message.txt` | The final assistant message, which is what a `last_message` grader read |
| `workspace/`       | The agent's working directory                                      |

One layout, so a case is read the same way whichever backend produced it, and a run on one
can be held against a run on the other. A passing run is what a failing one is read against,
so keeping less for one than for the other would drop half of every comparison: which of three
runs failed is not known before the run.

What differs is only where the three are read from, and whether they are moved or copied:

| Backend    | The artefacts are in                                | And are | Because                                                     |
| ---------- | ---------------------------------------------------- | ------- | ------------------------------------------------------------ |
| `--docker` | the sandbox `--keep-temp` kept, on the host          | moved   | A sandbox is a throwaway directory, and moving empties it   |
| `--cowork` | the CoWork session directory                         | copied  | A session is the account's own record, and is never written |

`--keep-temp` is pinned on for the container backend. The sandbox it keeps is created under
the harness's `TMPDIR`, which that backend points at the run's log mount. That is what puts it
on the host: the container is started with `--rm`, and the default `/tmp` inside it goes with
the container. See [docker.md](docker.md). The rest of a sandbox is removed: the child's
configuration directory, its npm logs, its node compile cache and its sockets. None of it says
anything about the run, and it is 40 times the size of what is kept.

Nothing under a CoWork profile is written, moved or removed. The driver's rule holds here:
[cowork_driver.md](cowork_driver.md).

### The two transcript formats

`trace.jsonl` is the transcript the backend that produced it wrote, and neither is rewritten.
One name, two formats. They are close, and a reader that assumes one of them on both is
wrong.

| | `--docker` | `--cowork` |
| ----------------------- | ------------------------------------------ | ------------------------------------- |
| Written by              | `claude plugin eval`, into the run sandbox | the CoWork application, into the session |
| The record shapes are in | [claude_code/plugin_eval_reference.md](claude_code/plugin_eval_reference.md) | [cowork_desktop.md](cowork_desktop.md) |
| Read here by            | `traces.last_message`                      | `cowork.final_text`                    |

What they share is the shape a reader needs: one JSON object per line, a `type`, and a
`message` of `{role, content}` on a turn, where `content` is a string or a list of blocks and
a tool call and its result are a `tool_use` and a `tool_result` block paired by id. That is
why one `last_message.txt` means the same thing on both.

Three differences matter:

- **Only a harness trace ends in a `result` record**, and that record carries the final
  message verbatim. A session transcript has none, so the final message there is the last
  assistant text block. Each is read by whatever already parses that format, and neither
  format is parsed twice.
- **A session transcript carries an open set of record types**, listed and dated in
  [cowork_desktop.md](cowork_desktop.md), and only `user` and `assistant` carry a `message`.
  A reader takes turns from those two and ignores the rest.
- **A harness trace carries the run's own envelope.** Types observed on the smoke case,
  snapshot 2026-09-10, CLI 2.1.265: `system`, `assistant`, `user`, `rate_limit_event` and
  `result`. Nothing else records this set, which is why it is measured here. A session's is
  not restated here, because that file owns it.

No rendering of either is written. Each format is the one the thing that produced it writes,
and a rendering here would be a third format to keep true.

### When it cannot be done

A collection problem is a warning on stderr and never a failed run. A sandbox that was not
kept, a session the driver never reached, a trace that will not read and a result document
that will not parse are each one line saying so, and the run keeps whatever verdict it
already had. A run that already carries an `error` says nothing: the error is why there is
nothing to collect, and the gate prints it.

Collection runs whether or not the backend raised, because a run that left no result document
still left sandboxes behind, and a kept sandbox is read-only until something unseals it.

Turning it off is `--no-keep-traces` or `eval.keep_traces: false`, on either backend. The
command line beats the file, as it does for every other option: [library.md](library.md).
Off, nothing is created and nothing is collected, and the harness deletes each sandbox as it
always did.

A measured cost, snapshot 2026-09-10, for the smoke case on the container backend: 12 KB per
run, and 60 KB for a whole two-run suite including `run.log`, `report.html`, `debug.txt` and
both workspaces. A CoWork run's cost is the size of its `outputs/`, which is whatever the case
made the session produce. The `⚠ kept ...` notice the harness prints per sandbox goes to
`run.log` and to the terminal, one line per run.

## The gate

The gate decides pass and fail, not the harness. It reads the result document, so one gate
covers both backends, and it always runs in the `cowork_evals` process on the host.

| Condition                                                            | Result       |
| -------------------------------------------------------------------- | ------------ |
| Any `regex`, `tool_used`, `tool_order` or `file_exists` grader failed | exit 1       |
| Any case or grader reported skipped, or a grader reported `scored: false` | exit 1   |
| `partial: true`, whatever `partialReason` says                       | exit 1       |
| A run carrying `error`, on either backend                            | exit 1       |
| A sweep stopped by `eval.max_cost_total_usd`                         | exit 1       |
| A results document is missing, unparsable, or of another `schemaVersion` | exit 1   |
| A grader result naming no grader the case defines                    | exit 1       |
| Any `llm` or `baseline` grader failed                                | printed only |
| A document whose `aggregates.casesTotal` is 0                        | exit 0       |
| Otherwise                                                            | exit 0       |

Structural graders gate because a judged grader over a non-deterministic agent is a flaky
gate. A skip gates so that a backend cannot go green by honouring nothing. `scored: false` is
a skip here: `--ablation none` drops no grader from the score, so a grader that was not scored
was not asked.

`partial: true` gates whatever the reason. The harness names `cost_ceiling` and `auth_failed`,
and `interrupted` is a third; the gate reads the flag and not the reason.

A run carrying `error` gates on every backend, not only on CoWork. There it is a case the
driver could not run or collect. On the harness it is a run that timed out, hit the turn cap
or exited non-zero, each of which is still graded on what it produced, so the score alone does
not catch it.

An empty document passes. A `--tag` sweep matches no case in most plugins, and failing on that
would make every filtered sweep red. A selection matching no case *anywhere* is refused before
the run instead, with exit 2. See [cli.md](cli.md).

Every line the gate prints carries `FAIL` or `NOTE`, so a judged failure is never read as the
cause of exit 1. The last line is the case counts and the overall score, summed and averaged
across every plugin in the run directory.

A line about what one run produced ends with `[artifacts: <dir>]`, naming the directory
holding that run's transcript. It is on a failed structural grader, a failed judged grader and
an errored run, which are the three lines somebody goes and reads a transcript over. A skipped
case, a skipped grader and a grader naming no definition carry none: none of them is a verdict
about what the model produced, and there is no transcript behind them.

The directory comes from the run's `tracePath` and is printed only when it is on disk, so a
document written before this was built, and a run whose trace was not collected, read exactly
as they did before. `traces.py` rewrites that field to the trace it collected on both backends,
so the line says the same thing whichever one produced the run. A CoWork run's session
directory is still in `cowork.sessionDir`.

The gate reads every `<plugin>/aggregate-result.json` under the run directory and decides once
for the whole invocation, so a sweep gates once and not once per plugin.

It reads the `with` arm only. A run's grader results carry `name`, `passed` and `scored`,
never `type`, so the gate joins each result to that case's grader definition by name to learn
which of the two classes it is in.

The gate reads `schemaVersion: 1` documents and tolerates unknown fields. The contract is
additive-only.

## Logs

Every invocation keeps everything it printed, in one directory per invocation. Not one file
per plugin: runs are non-deterministic, and a per-plugin file overwrites the previous run.

```
logs/evals/<yyyymmdd-hhmmss>-<scope>/
  run.log                        # stdout and stderr of the whole invocation, tee'd live
  gate.txt                       # the gate's output
  env.txt                        # cowork_evals --version, claude --version, python3 -V,
                                 #   the backend, and the image on the container backend
  <plugin>/aggregate-result.json # the v1 result document
  <plugin>/report.html           # the self-contained HTML report
  <plugin>/debug.txt             # claude --debug-file output
  <plugin>/traces/<case>/run-<n>/trace.jsonl       # the run's transcript
  <plugin>/traces/<case>/run-<n>/last_message.txt  # its final assistant message
  <plugin>/traces/<case>/run-<n>/workspace/        # the agent's working directory
logs/evals/latest                # symlink to the newest directory
```

The log root is `logs/evals` under the working directory unless `--out DIR` replaces it whole,
and `<scope>` is named from the path argument. Both are [cli.md](cli.md). Run directories
older than 30 days are deleted at the start of every run, after every refusal and before the
`--dry-run` exit, so a refused invocation deletes nothing and an unattended dry run still
reclaims space.

`run.log` is captured at the file descriptor level, so a child process inherits it and the
harness's own output and the container's reach the file.

`traces/` is written by both backends, with the same three names in it, and the rule above
says what goes in each. `<n>` is 1-based and is the same number the gate prints as `run N`. Nothing makes a case name
unique inside a plugin, so a second case of the same name is suffixed `-2`, as a second plugin
of one name is. The run's `tracePath` in
the result document is rewritten to the collected trace, so the field that named it still
names it.

A CoWork run writes `<plugin>/aggregate-result.json` and `<plugin>/traces/`. There is no
`report.html` and no `debug.txt` on that backend: the first is the harness's, the second is
`claude --debug-file`, and the harness is in neither path. `traces/` is written by both, with
the same three names in it. The gate reads only the result document, so it decides identically
for both backends.

The debug log exists only when the run is given one:
`claude --debug-file <path> plugin eval ... --verbose`. The flag goes before `plugin`, and it
must be `--debug-file`: a bare `--debug` there swallows the subcommand name as its filter.
`--verbose` writes to that file only and never to the terminal.

## Cadence

An eval is not a commit-time check. `git commit` runs nothing, and there is no hook.

Which command runs at which moment is the table in [approaches.md](approaches.md). Who
enforces it is the consumer repository: the author while writing a case, the PR template
before a PR, the release checklist before a release.

That cadence is for a consumer repository. Nothing here runs against this repository's own
fixtures except the smoke case that proves the backend reaches a running case.

## Nothing here runs on CI

No hook, no PR job, no workflow shipped by this package. A person runs the sweep and reads the
summary. The reason is not cost: a red gate over cases nobody trusts gets routed around rather
than fixed.

A consumer automates it when all four of these hold, and not before:

| Condition                                                              | Read from         |
| ---------------------------------------------------------------------- | ----------------- |
| Every skill under test has at least one case                           | the `evals/` tree, reported by `run` and enforced by `--require-coverage` |
| Structural graders carry the gate, with a measured flake rate          | `logs/evals/*/`   |
| The cost and wall-clock time of a full sweep are measured and accepted | the table below   |
| A credential and a pinned CLI on a runner have an owner                | a decision        |

## Cost

[plugin_eval.md](plugin_eval.md) counts the model calls a suite makes. This file sets the
ceilings on what they may cost.

| Ceiling                   | Default | Binds                | Reached through       |
| ------------------------- | ------- | -------------------- | --------------------- |
| `eval.max_cost_usd`       | 5       | one plugin's suite   | `--max-cost-usd`      |
| `eval.max_cost_total_usd` | 25      | the whole invocation | the key only, no flag |

The total binds first: five plugins at 5 USD each is 25. A sweep sums `costUsd` from each
plugin's result document and checks the total before every plugin, the first included, so a
ceiling of 0 stops it before it spends anything. A sweep that stops on the ceiling is a
failure, never a pass.

The total has no command-line option because it governs an invocation rather than a run, and
[cli.md](cli.md) lists only the options a run takes.

| Measurement                   | Wall clock       | costUsd          |
| ----------------------------- | ---------------- | ---------------- |
| Smoke case, `runs: 1`, Docker | 8 s              | 0.057            |
| Full sweep, Docker            | not yet measured | not yet measured |

A row reading `not yet measured` has not been run. The ceilings above were chosen, not
measured. The sweep row stays unmeasured here: this repository holds one fixture plugin, so
a sweep measurement belongs to a consumer.

The Docker row is a snapshot, 2026-09-09. It is `durationSeconds` and `costUsd` read from the
`aggregate-result.json` of a passing `cowork_evals run --docker plugins/smoke`, on CLI
2.1.265, `sonnet` and the `haiku` judge. The wall clock is the harness's own, so it excludes
the image build and the container start.

The cost is unchanged from the 2026-09-08 snapshot, which ran the same case through
`Docker.run` rather than through the command. The command adds no model call, so an
unchanged cost is what it should be. The wall clock moved from 3 s to 8 s, and that is the
agent's own variance across runs rather than anything the command added.
