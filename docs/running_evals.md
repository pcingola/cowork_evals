# Running evals

## Summary

`cowork_evals run` takes one path into a case tree and one backend, runs every case the path
selects, and reaches one pass or fail over the whole invocation. This file covers the settings
a run passes to the harness, the tool grant, pass and fail, ablation, what each run leaves on
disk, and what a run costs. The options are [cli.md](cli.md). The case format is
[eval_format.md](eval_format.md). Which backend honours which part of a case is
[approaches.md](approaches.md).

- `cowork_evals` decides pass and fail, not the harness. One verdict covers both backends.
  Every grader decides, structural and judged alike.
- A skip fails the run. A case the backend is told it cannot run is counted instead.
- Every invocation keeps everything it printed, with every run's transcript, passing runs
  included.

## The cases a run selects

A path holding several plugins runs every plugin's suite in turn, each its own harness
invocation, and is decided once. The harness loads one plugin per run, so a case that crosses
plugins cannot be written.

There is no sweep on CoWork. One case there costs a VM boot and a full agent run and counts
against `cowork.max_runs`, so a CoWork run is a smoke set named case by case. A path covering
several plugins exits 2 on `--cowork`.

The CoWork backend does not call `claude plugin eval`. It reads the same case tree, submits
each case's prompt body, grades the session with its own grader, and writes the same
`aggregate-result.json`. Of the settings below it reads `eval.judge_model` and
`eval.keep_traces`.

### On CoWork

A backend reads the keys the case file wrote, never the merged defaults.

| In the case file                                        | On CoWork                                                                    |
| ------------------------------------------------------- | ---------------------------------------------------------------------------- |
| No `runs` key                                           | Runs once                                                                    |
| `runs: N`, written out                                  | Runs N times                                                                 |
| `timeout_seconds`, written out                          | That case's driver timeout                                                   |
| `arm: with-only` or `arm: both` on a grader             | Honoured. One arm runs, it is the with-arm, and every grader is scored in it |
| `max_turns`, written out                                | The case carries `no-cowork`, and is counted                                 |
| `model`, `allowed_tools`, `append_system_prompt`, `env` | The case carries `no-cowork`, and is counted                                 |
| `context.*`, or a `mocks/` directory the case uses      | The case carries `no-cowork`, and is counted                                 |
| `target` or `focus` of `mock_calls` on a grader         | That grader is skipped, and the case still runs                              |

A declared case and a grader skip are different. A declared case submits nothing, is out of
every aggregate, and fails nothing. A grader skip runs the case and fails the run.

An `llm` grader whose focus turns out to be an image is skipped on CoWork, and fails the run
like every other skip.

## The settings a run passes

| Setting             | Default                  | Command-line option    | Is                                          |
| ------------------- | ------------------------ | ---------------------- | ------------------------------------------- |
| `eval.model`        | `sonnet`                 | `--model`              | the model under test                        |
| `eval.judge_model`  | `haiku`                  | `--judge-model`        | the judge for `llm` and `baseline` graders  |
| `eval.judge_votes`  | 3                        |                        | votes per judged grader. The majority is its result |
| `eval.ablation`     | `none`                   | `--ablation`           | one arm, or the with and without arms       |
| `eval.delta_threshold` | 0                     | `--delta-threshold`    | the lowest passing delta, on two arms       |
| `eval.max_cost_usd` | 5                        | `--max-cost-usd`       | the ceiling over one plugin's suite         |
| `eval.allow_tools`  | the session mirror below | `--allow-tools`        | the tool grant                              |
| `eval.keep_traces`  | true                     | `--[no-]keep-traces`   | keep every run's artefacts                  |

The harness threshold is pinned to 0 and cannot be changed, so `cowork_evals` decides pass and
fail. The number a two-arm run is decided on is `eval.delta_threshold`.

### The tool grant

The default is what a CoWork session can do, in the container's tool names:

```
Bash Read Glob Grep Write Edit WebFetch Skill
```

A session grants nothing and asks nothing. It writes files, shells out, reaches the network and
reads a skill off its mount. A session's `mcp__workspace__bash` is the container's `Bash`, and
its `mcp__workspace__web_fetch` is `WebFetch`.

A case cannot grant itself `Bash`, `Write`, `Edit`, `WebFetch` or an MCP tool. The operator
grant is the only route, and a case that is not granted a tool loses it without a loud failure.
`eval.allow_tools` and `--allow-tools` replace the default and do not add to it, so a
replacement names every tool it still wants.

`Read`, `Glob` and `Grep` are named on purpose: a run granted only `Bash` was offered no `Glob`
and no `Grep`. The default does not include `WebSearch`, which no session was measured using.
A bare `WebFetch` says nothing about which domains a run can reach. The harness restricts
network access to the domains a `WebFetch(domain:...)` grant names.

A plugin's own MCP tools are named `mcp__plugin_<plugin>_<server>__<tool>`. No default names
them. Add them to the grant.

A grant is not a capability. A narrower grant does not by itself take a tool away: a grant
without `Write` still created a file, through `Bash` and `Edit`. A denial comes from a grant
with no tool that can do the work.

## Pass and fail

The verdict reads every `<plugin>/aggregate-result.json` under the run directory and decides
once for the whole invocation.

| Condition                                                                    | Result          |
| ---------------------------------------------------------------------------- | --------------- |
| Any `regex`, `tool_used`, `tool_order`, `file_exists`, `llm`, `baseline` or check failed | exit 1 |
| Any case or grader reported skipped                                          | exit 1          |
| A grader reported `scored: false` on a one-arm run                           | exit 1          |
| A grader reported `scored: false` on a two-arm run                           | printed only, as an indicator, when it did not fire |
| A case's delta is below `eval.delta_threshold`, on two arms                  | exit 1          |
| A case carries no delta, on two arms                                         | exit 1          |
| A case declared `no-cowork`, on `--cowork`                                   | exit 0, counted |
| `partial: true`, for any reason                                              | exit 1          |
| A run carrying `error`, on either backend                                    | exit 1          |
| A run the permission mode refused a tool, on `--docker`                      | exit 1          |
| A run never offered a tool the grant named, on `--docker`                    | exit 1          |
| A sweep stopped by `eval.max_cost_total_usd`                                 | exit 1          |
| A result document missing, unparsable, or of another `schemaVersion`         | exit 1          |
| A grader result naming no grader the case defines                            | exit 1          |
| A document whose `casesTotal` is 0                                           | exit 0          |
| Otherwise                                                                    | exit 0          |

`partial: true` comes from `cost_ceiling`, `auth_failed` or `interrupted`. Each fails.

A harness run carries `error` when it timed out, hit the turn cap or exited non-zero. It is
still graded on what it produced, and it still fails. On CoWork, `error` is a case the driver
could not run or collect.

An empty document passes, so a `--tag` sweep that matches nothing in one plugin is green. A
selection that matches no case anywhere exits 2 before the run.

A skill that reads an environment variable outside `docker.session_env`,
`docker.env_passthrough` and `docker.keep_env` gets an empty string in a Docker run, as in a
session, and its case fails. See [runtime.md](runtime.md).

Every printed line starts `FAIL` or `NOTE`. A note never causes exit 1. A note is a failed
advisory check or a with-only indicator that did not fire.

### A run that never had the tool

A run scored without a tool the case was granted is not a fact about the plugin. Two
conditions catch it, read from the kept trace on `--docker`.

| The tool was                            | The trace holds                        | The run carries  |
| --------------------------------------- | -------------------------------------- | ---------------- |
| granted, and the call refused           | a `permission_denied` record naming it | `deniedTools`    |
| granted, and never offered to the model | an `init` tool list missing it         | `unofferedTools` |
| never granted                           | nothing                                | neither          |

Only `decision_reason_type: mode` counts as a denial. A denial the plugin's own hook wrote is
the plugin's behaviour, and it does not fail the run. The rule matches the reason, never the
tool name. A grant written as `WebFetch(domain:example.com)` is compared on the part before
`(`. The `init` list is longer than the grant, so a name in it is not permission to call it.

Both conditions start from the grant. A tool nobody granted is never offered and never tried,
and neither condition catches it. That includes a plugin's own MCP tools and `WebSearch`. A
green suite does not prove that each run had the tools its case needed.

Both conditions need a kept trace. `--no-keep-traces` and `eval.keep_traces: false` disable both
without a warning. Neither can fire on CoWork.

## Ablation

`--ablation with-without` runs every case twice. The with-arm loads the plugin. The
without-arm loads no plugin. Each case is decided on its own delta, `score - scoreWithout`,
never on a suite average. A case below `eval.delta_threshold` fails on a line naming both
scores and the delta.

It doubles the cost, it is off by default, and it is `--docker` only. `--ablation` and
`--delta-threshold` exit 2 on `--cowork`.

A `tool_used: Skill` grader cannot pass in the without-arm. The harness drops it from the score
in both arms and reports it as an indicator with `withOnly: true` and `scored: false`. `arm:`
on a grader controls this:

| `arm:`                                 | Scores in                       |
| -------------------------------------- | ------------------------------- |
| `with-only`                            | the with-arm only               |
| `both`                                 | every arm that runs             |
| absent, on a `tool_used: Skill` grader | the with-arm only               |
| absent, on any other grader            | every arm that runs             |

A case whose graders are all with-only is scored normally in both arms, and arrives with
`scored: true`.

| The grader                        | In the with-arm                   | In the without-arm                |
| --------------------------------- | --------------------------------- | --------------------------------- |
| `tool_used: Skill` with no `arm:` | `withOnly: true`, `scored: false` | absent from the grader list       |
| The same grader under `arm: both` | `withOnly: false`, `scored: true` | `withOnly: false`, `scored: true` |
| Every other grader                | `withOnly: false`, `scored: true` | `withOnly: false`, `scored: true` |

Under `--ablation none` one arm runs, it is the with-arm, and every grader is scored. `arm:`
then has no effect, and a case sets it only to stay portable to a two-arm suite. The one-arm
run is what shows the skill fired.

Whether a run was two-arm is `suite.ablation` in the document, never a count of a case's arms.
A two-arm case with no delta fails, with one of two reasons:

| The document                             | The line says                                      |
| ---------------------------------------- | -------------------------------------------------- |
| `arms.without` is empty                  | the baseline arm ran nothing                       |
| a run carries `skippedPaidGraders: true` | a run skipped its paid graders at the cost ceiling |

When a run overran `--max-cost-usd` and skipped its paid graders, the case's
`aggregates.delta` and `aggregates.scoreWithout` are omitted while `score`, `passRate` and
`passRateWithout` stay, and the document's `aggregates.meanDelta` is omitted. `partial` stays
`false`. A paid grader skipped at the ceiling is not a grader skip: it carries `passed: false`,
`scored: true` and `explanation: skipped: cost ceiling`, and no `skipped` flag.

| Where in the document       | Field                                                           | Holds                                  |
| --------------------------- | --------------------------------------------------------------- | -------------------------------------- |
| `suite`                     | `ablation`                                                      | `with-without`                         |
| a case's `arms`             | `with`, `without`                                               | one run list each                      |
| a case's `aggregates`       | `score`, `passRate`, `scoreWithout`, `passRateWithout`, `delta` | `delta` is `score - scoreWithout`      |
| the document's `aggregates` | `meanDelta`                                                     | the mean of the case deltas defined    |

A one-arm document carries `score` and `passRate` alone, and no `arms.without`. A case with
checks has its delta recomputed with the check results. See [checks.md](checks.md).

## The last line

| Count      | Is                                                         |
| ---------- | ---------------------------------------------------------- |
| `found`    | cases under the path, before any filter                    |
| `picked`   | cases `--tag` and `--case` kept                            |
| `ran`      | cases a backend reported running, `casesTotal`             |
| `passed`   | cases with no failure line                                 |
| `declared` | cases carrying `no-cowork` on `--cowork`, printed even at 0 |

Then the mean of each document's `overallScore`. A two-arm run adds the mean delta, or
`mean delta none` when no document carried one. A partial document adds `stopped early` and the
reason.

`ran` is below `picked` when a case was declared, a plugin failed to run, or the sweep stopped
early. Neither count is checked against the other.

`passed` is not the harness's `casesPassed`. That count is every case, because the threshold is
0.

A line about a failed grader, a note or an errored run ends with `[artifacts: <dir>]`, the run
directory below, when it is on disk. A skipped case, a skipped grader and a grader naming no
definition carry none.

## What a run leaves behind

Each invocation gets one directory:

```
logs/evals/<yyyymmdd-hhmmss>-<scope>/
  run.log                        # stdout and stderr of the whole invocation
  verdict.txt                    # the verdict
  env.txt                        # versions, the backend, the image, forwarded variable names
  <plugin>/keep_env.txt          # --docker: the names a Bash call keeps
  <plugin>/aggregate-result.json # the v1 result document
  <plugin>/report.html           # --docker only
  <plugin>/debug.txt             # --docker only
  <plugin>/traces/<case>/run-<n>/
    trace.jsonl                  # the transcript
    last_message.txt             # the final assistant message
    workspace/                   # the agent's working directory
    scratch/                     # only when the case has checks
    checks.jsonl                 # only when the case has checks
logs/evals/latest                # symlink to the newest directory
logs/evals/history/              # one record per case, read by panel
```

`env.txt` names forwarded variables, never their values. `<n>` starts at 1 and is the number
the verdict prints as `run N`. A second case of the same name in one plugin is suffixed `-2`,
as is a second plugin of one name. Under `--ablation with-without`, the baseline arm's runs are
under `traces/<case>/without/run-<n>/`, so `traces/<case>/run-*` is the with-arm alone.

Every run keeps `trace.jsonl`, `last_message.txt` and `workspace/` under the same names on both
backends, passing runs included. Compare a failing run against a passing run, or against the
same case on the other backend. On CoWork the files are copied from the session directory,
which is still named in the document as `cowork.sessionDir`. Nothing in the CoWork profile is
written, moved or removed.

Read the collected `workspace/`, not a kept sandbox. A script you write over a run's files does
not reach the verdict and fails nothing. To make an assertion decide the run, write it as a
check. See [checks.md](checks.md).

`--out DIR` replaces `logs/evals`. `<scope>` is named from the path argument. Run directories
older than 30 days are deleted at the start of every run, after every refusal and before the
`--dry-run` exit. The age is read from the directory name. History records outlive run
directories. See [panel.md](panel.md).

A collection problem is a warning on stderr. It never fails a run on its own. A run that
already carries an `error` gets no warning.

`--no-keep-traces` or `eval.keep_traces: false` keeps nothing. It also disables the two tool
conditions above and every check, and a disabled check is a skip that fails the run.

A smoke case on `--docker` keeps 12 KB per run. A CoWork run keeps the size of its `outputs/`.

### The two transcript formats

`trace.jsonl` is in the format of the backend that wrote it, unchanged.

|                     | `--docker`                    | `--cowork`                         |
| ------------------- | ----------------------------- | ---------------------------------- |
| Written by          | `claude plugin eval`          | the CoWork application             |
| Ends in             | a `result` record holding the final message | no `result` record. The final message is the last assistant text block |
| Record types        | `system`, `assistant`, `user`, `rate_limit_event`, `result` | an open set. Only `user` and `assistant` carry a `message` |

Both are one JSON object per line, each with a `type`. A turn carries `message` as
`{role, content}`. `content` is a string or a list of blocks, and a tool call and its result are
`tool_use` and `tool_result` blocks paired by id. Read turns from `user` and `assistant` and
ignore the rest. A `regex` over `target: trace` can pass on one backend and fail on the other.

## When to run, and CI

An eval is not a commit-time check. `git commit` runs nothing. Which command runs at which
moment is [approaches.md](approaches.md).

This package ships no hook, no PR job and no workflow. Automate a sweep only when all four of
these hold:

| Condition                                                              | Read from                                                                 |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Every skill under test has at least one case                           | the `evals/` tree, reported by `run` and enforced by `--require-coverage` |
| The graders carry the verdict, with a measured flake rate              | `logs/evals/*/`, and `flake` in `panel`                                   |
| The cost and wall-clock time of a full sweep are measured and accepted | the cost section below                                                    |
| A credential and a pinned CLI on a runner have an owner                | a decision                                                                |

## Cost

| Ceiling                   | Default (USD) | Binds                | Set by                |
| ------------------------- | ------------- | -------------------- | --------------------- |
| `eval.max_cost_usd`       | 5             | one plugin's suite   | `--max-cost-usd`      |
| `eval.max_cost_total_usd` | 25            | the whole invocation | the key only          |

Both are chosen values, not measured ones.

The total is the sum of `costUsd` over each plugin's result document. It is checked before every
plugin of a sweep, the first included, so a ceiling of 0 stops before anything is spent. A
sweep stopped by the ceiling fails.

A check's judge spend is outside `eval.max_cost_usd`, because it runs after the harness. It is
added to `costUsd`, so the total binds it at the next plugin.

On `--cowork` the host sees only judge spend. The session is billed to the account.
`cowork.max_runs` bounds submissions instead.

A smoke case at `runs: 1` on `--docker` with `sonnet` and the `haiku` judge took 8 s and cost
0.057 USD, read from its `aggregate-result.json`. That excludes the image build and the
container start. Ablation doubles the cost. `runs: N` multiplies it by N, checks included.
What a suite costs in model calls is [plugin_eval.md](plugin_eval.md).
