# CoWork backend

## Summary

`cowork_evals run --cowork <path>` runs an eval suite using the CoWork desktop application,
and this file is the code that does it. It reads the same case tree the container backend
reads, sends each case's prompt to a real CoWork session through the driver, grades what the
session wrote, and writes the same `aggregate-result.json` v1 document into the same log
directory. It never calls `claude plugin eval`: that harness has to load a plugin, and only
Claude Code knows how. The case format is shared with the harness. The execution is not.

The split from the driver is one question: does the statement need to know what a case is?
Yes, and it is here. No, and it is in [cowork_driver.md](cowork_driver.md) and
[cowork_driver_internals.md](cowork_driver_internals.md), which hold the transport and nothing
else.

Which part of the case format survives this route is [approaches.md](approaches.md), the
key-by-key rule is [running_evals.md](running_evals.md), the case format itself is
[eval_format.md](eval_format.md), and the command over it is [cli.md](cli.md). What of this
is built is [status.md](status.md).

## What a suite does

The backend decides the whole suite before it submits anything, then runs it.

| Stage         | Does                                                                                                       |
| ------------- | ------------------------------------------------------------------------------------------------------------ |
| Plan          | For each selected case: whether it runs here, how many times, under what timeout, and which graders are skipped |
| Ceiling       | Sum the planned submissions, add the driver's `recent()`, and refuse the whole suite when the total is above `max_runs` |
| Run           | Each case in turn, each run of a case in turn                                                              |
| Write         | One `aggregate-result.json`, and the run's artefacts under `traces/`                                       |

`--dry-run --cowork` prints the plan and the ceiling arithmetic and submits nothing. It is
the same plan the run uses, not a second derivation of it. See [cli.md](cli.md).

Cases run in sequence, and so do the runs of one case. There is one desktop application and
one composer.

A target covering more than one plugin root is a usage error, not a sweep. See
[running_evals.md](running_evals.md) for why, and [cli.md](cli.md) for the exit code.

The backend names no run directory, writes no `latest` symlink, writes no `env.txt`, prunes
nothing, prints nothing and decides no pass or fail. The command does all of that.

### How often, and for how long

| Setting     | Resolved from, in order                                                           |
| ----------- | ----------------------------------------------------------------------------------- |
| Run count   | `--runs`, then the case's own `runs` key, then once                               |
| Run timeout | `--timeout-seconds`, then the case's own `timeout_seconds` key, then `cowork.run_timeout` |

A key the case left to its default is not a request. The backend reads the keys the case
file wrote and never a merged value, which is why every case on this backend is not declared
unrunnable by its inherited `runs: 3`. The full key-by-key rule is
[running_evals.md](running_evals.md).

### What a driver failure does to a run

A `CoWorkError` is that run's error, and the suite continues with the next run.

One code is collected rather than discarded. Code 7 is a run timeout: it carries the session
directory, the CoWork session keeps running inside the VM, and the run is graded on what it
produced up to that point, with the timeout recorded as the run's `error`. That is what the
harness does with a timeout. A `collect` that then raises code 8, meaning the session wrote
no assistant text before the timeout, leaves the run with the timeout as its error, score 0
and no graders.

### The plugin under test is not loaded

The deep link carries a prompt. It does not install a plugin, and nothing on the host writes
into the VM's configuration, so a CoWork run exercises the plugin set already deployed to the
signed-in account.

A case path selects which cases run. It does not select which code runs. A local edit to a
skill is invisible to this backend until it is deployed. Nothing checks it, because it is not
verifiable from the host.

## What this backend does not run, and what it does not score

Two different things, and the result document keeps them apart.

| Thing          | Decided by                        | Effect                                                              |
| -------------- | --------------------------------- | --------------------------------------------------------------------- |
| A declared case | the case's own `no-cowork` tag    | Nothing is submitted, the case is counted, `arms.with` is empty, and it fails nothing |
| A grader skip  | this backend, or the judge        | The case runs, that grader is dropped from the score, and the run fails |

Skips are recorded, never silent. A grader with no equivalent here is written into the result
document as skipped with the reason, and a run that reports a skip fails, so a suite cannot go
green on CoWork by grading nothing. This backend decides no case skip at all.

What a live session cannot honour is written into the case as the `no-cowork` tag, and the
validator holds the case and this backend to one derivation of that fact, so a case the
validator passed is never one the backend then refuses. The backend reads the tag rather than
deciding anything, and the reasons behind it are what `declaredReason` carries.

**A `mocks/` directory is declared per case, not per directory.** The layer chain runs from
`evals/` down to the case, so a suite-wide `evals/mocks/` reaches every case in the plugin and
every one of those cases carries the tag. That is explicit where a reader is looking, and it
survives the case being moved.

Two grader skips exist, and only two.

| Skip                                              | Decided        |
| ------------------------------------------------- | -------------- |
| `target` or `focus` of `mock_calls`               | before the run |
| An `llm` grader whose `focus` file is an image    | after the run  |

`mock_calls` has no equivalent here, because the MCP servers are the real ones. The image is
detected from the file's bytes, as the harness detects it, so it cannot be known before the
run: the harness shows the judge the image itself, and one text call cannot. Any other binary
is a failed grader naming what the file is.

## Grading the session document

The backend evaluates a case's graders, defined in [eval_format.md](eval_format.md), against
the session document defined in [cowork_driver.md](cowork_driver.md). It runs on the host
inside the `cowork_evals` process and returns one result per grader. It prints nothing, exits
nothing and decides no pass or fail. It submits nothing, so it re-grades a stored session
document for free.

| Grader        | Read from                                                                             |
| ------------- | --------------------------------------------------------------------------------------- |
| `regex`       | The resolved target below                                                             |
| `tool_used`   | `tool_calls`, matched on name and on the JSON-encoded input                           |
| `tool_order`  | `tool_calls`, in call order, because `before` and `after` each take an `input_match`   |
| `file_exists` | The produced-file list below, as a glob                                               |
| `llm`         | A judge call on `focus`, 2 of 3                                                       |
| `baseline`    | A judge call against `baseline_file`, 2 of 3                                          |

Grader targets map onto the session document as `last_message` to `final_text`, `trace` to
`turns` and `tool_calls`, `files` to the produced-file list, and `{source: file, path}` to
that path under `<session_dir>/outputs/`, which is the one place a produced file is readable
from the host.

**The produced-file list is `outputs` with its `outputs/` prefix stripped.** That prefix is
in the session document because the document names files relative to the session directory.
The backend strips it once, and every grader that names a produced file names it relative to
`outputs/`. That is what makes `path: report.md` mean here what it means under the harness,
where the created-file list is relative to the workspace. A `path` that resolves outside
`outputs/` is a failed grader carrying the reason, because the reference confines a file
target to the workspace and `outputs/` is the workspace here.

**`target: trace` renders this backend's way** and is not the harness's `trace.jsonl`: one
JSON object per line, every entry of `turns` followed by every entry of `tool_calls`. A
`regex` grader over `trace` is therefore not portable between backends. Every other target
is.

**A `regex` pattern is a JavaScript RegExp source compiled with Python's `re`.** The two
engines are not the same. The flags `i`, `m` and `s` map onto `re.I`, `re.M` and `re.S`;
`re.ASCII` is added unless the flags carry `u` or `v`, which is what makes `\d` and `\w`
ASCII-only as they are in JavaScript; and `d`, `g` and `y` are ignored, because none of them
changes what a grader reads. A named group, a lookaround or a backreference that both
engines accept behaves the same; a construct only JavaScript has does not compile, and that
is a failed grader naming the error. Every pattern in the format goes through that one
function, `input_match` on `tool_used` and `tool_order` included.

Nothing in the grading layer raises. An unknown grader type, an uncompilable pattern and an
unreadable file are each a failed grader carrying the reason.

## The judge

`llm` and `baseline` are answered by `claude -p --output-format json --model <model>
--strict-mcp-config`, with the rubric, the material and a closing instruction sent as one
text on stdin. Three votes, and the grader passes on two `PASS` answers. A reply that is
neither word is a lost vote and is not a `PASS`; three lost votes are a failed grader naming
the reason. `--strict-mcp-config` keeps the developer's own MCP servers out of a text vote.
The material is truncated head and tail as the harness truncates it.

The model is `--judge-model` where one was given and `eval.judge_model` otherwise. The
signed-in `claude` on `PATH` is the one credential route, which is why [cli.md](cli.md) makes
it part of the `--cowork` preflight. `CLAUDE_CODE_WALNUT_SPIRE` is not exported: it enables
`claude plugin eval`, and this is `claude -p`.

The same three-vote machinery answers a check's `llm` assertion, with an argument list and a
material rule of its own. That is [checks.md](checks.md).

## What the result document says that the reference does not

Both backends write the same v1 `aggregate-result.json`, so one verdict covers both. The
contract is additive-only, which is what permits these. Nothing else here departs from
[claude_code/plugin_eval_reference.md](claude_code/plugin_eval_reference.md).

| Field                                  | On              | Is                                                                                                                     |
| -------------------------------------- | --------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `declaredUnrunnable`, `declaredReason` | a case          | That the case carries `no-cowork`, and what the tag declares. `arms.with` is empty                                     |
| `skipped`, `skipReason`                | a grader result | Why that grader was not scored                                                                                         |
| `cowork.sessionDir`                    | a run           | The session, which is what re-grades a stored run without submitting again, and where the run's artefacts are copied from |
| `cowork.timeoutSeconds`                | a run           | The timeout that run actually ran under. It is the one place an effective value is recorded                            |
| `scored`                               | a grader result | `not skipped`, widening the reference's `not withOnly` to the one other exclusion this backend has                     |

`withOnly` is always `false`: `ablation` is `none` here and nothing is dropped for an arm.

**This backend runs one arm, and that arm is the with-arm.** A session gets its skills from
the profile the desktop application is running, and a plugin is absent only in a profile it
was never installed into, so a baseline arm here would mean a second profile and a restart
between the two. What a session loads and where it loads it from is
[cowork_desktop.md](cowork_desktop.md). So `ablation` and `threshold` are constants in
`results.py` rather than settings, and `--ablation` and `--delta-threshold` are a usage error
on this backend. See [cli.md](cli.md).

**The `cowork` key is also what says which backend produced a run.** The harness writes no
such key, so its presence is the rule that decides where one run's artefacts are read from
when the traces are collected: a session directory here, and a kept sandbox there. It is the
key and never its value, because a run the driver could not start carries the key with a null
`sessionDir`. See [running_evals.md](running_evals.md).

`tracePath` is the session's transcript when the document is written, and is rewritten to the
copy under the run's log directory once that copy is made. The session itself is still named,
in `cowork.sessionDir`. That is what makes a failure line say the same thing on both backends.

**A case carries `declaredUnrunnable` and never `skipped`.** A reader and the verdict both
tell the two apart by the field: a skip fails the run, and a declared case is counted.

One behaviour departs as well. The four aggregates are over the cases this backend ran, so a
declared case is out of `casesTotal`, out of `casesPassed` and out of both means. `threshold`
is 0 here, so a declared case left in `casesTotal` alone would count as passed, and its 0.0
would drag `overallScore` down for a case that never ran. Nothing reads them to decide
anything: the pass and fail rules in [running_evals.md](running_evals.md) read the grader
results, `skipped` and `declaredUnrunnable`.

Two fields mean something narrower here than they do under the harness.

| Field           | Here                                                                                |
| --------------- | ------------------------------------------------------------------------------------- |
| `claudeVersion` | The host `claude --version`. No CLI ran this suite, and that version is the judge's  |
| `costUsd`       | The judge spend, and nothing else. A CoWork run is billed to the account and is not observable from the host. It is never estimated |

A CoWork run writes `aggregate-result.json` and the run's artefacts under `traces/`. There is
no `report.html` on this backend, and the artefacts carry the same three names the container
backend leaves. The traces are copied out of a session directory, never moved, and the
session is left exactly as the application left it. The log layout is
[running_evals.md](running_evals.md).

## What one suite costs

One case of `plugins/smoke/`, `python-version`, at `runs: 1`, through the integration tier.

| Measured                        | Value                                                                                                                                      |
| ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Wall clock of one case          | 6.1 s, the run's `durationSeconds`. It runs from the audit `user` record to the collection, so it excludes the deep link, the settle and the discovery |
| Ceiling entries one suite costs | One per run, so one entry for that selection                                                                                               |
| `costUsd` of that suite         | 0. The case carries no judged grader, and a CoWork run is not observable from the host                                                     |

Two facts about the grader mapping cannot be read from a file. Both are measured against real
sessions.

| Measured                                          | Value | Consequence                                                               |
| ------------------------------------------------- | ----- | --------------------------------------------------------------------------- |
| A transcript carries a `Skill` `tool_use` record  | yes   | The skill-fired idiom in [eval_format.md](eval_format.md) is gradable here |
| A session writes a produced file under `outputs/` | yes   | `file_exists`, and a `{source: file, path}` target, are gradable here      |

## The ceiling over a suite

The driver refuses one submission at a time, at step 1 of its sequence; see
[cowork_driver.md](cowork_driver.md). The backend refuses a whole suite before the first
submission: it sums each case's effective run count, adds the driver's `recent()`, and raises
code 2 when the total is above `max_runs`. A case carrying `no-cowork` submits nothing and
costs no ceiling entry.

The command checks the same three numbers in its preflight, so the backend's own refusal is
the guard behind it rather than the one an operator meets. See [cli.md](cli.md).
