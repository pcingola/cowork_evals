# CoWork backend

## Summary

The layer over the CoWork driver. It reads the same case tree as the container backend,
submits each case's prompt body through the driver, grades the session document that comes
back, and writes the same `aggregate-result.json` v1 document into the same log directory. It
is reached as `cowork_evals run --cowork <path>`.

- **The split from the driver is one question**: does the statement need to know what a case
  is? Yes, and it is here. No, and it is in [cowork_driver.md](cowork_driver.md), which holds
  the transport and nothing else.
- **It does not call `claude plugin eval`.** That harness must load a plugin, and only Claude
  Code knows how. The case format is shared with it. The execution is not.
- **Grading is total.** Nothing in the grading layer raises: an unknown grader type, an
  uncompilable pattern and an unreadable file are each a failed grader carrying the reason.
- **A produced file means a file under `outputs/`.** That is the one place a produced file is
  readable from the host, and it is what a kept run's `workspace/` is copied from.
- **Nothing under the profile is written.** The traces are copied out of a session directory,
  never moved, and the session is left exactly as the application left it.
- **Skips are recorded, never silent**, and the gate fails a run that reports one.
- **The plugin under test is not loaded.** A case path selects which cases run, not which code
  runs.
- **The suite ceiling is refused before the first submission**, not one case at a time.

Which part of the case format survives this route is [approaches.md](approaches.md), the
key-by-key skip rule is [running_evals.md](running_evals.md), the case format itself is
[eval_format.md](eval_format.md), and the command over it is [cli.md](cli.md). What of this is
built is the status table in [running_evals.md](running_evals.md).

## Grading the session document

The CoWork backend evaluates a case's graders, defined in
[eval_format.md](eval_format.md), against the session document defined in
[cowork_driver.md](cowork_driver.md). It takes that document and the case directory, runs on
the host inside the `cowork_evals` process, and returns one result per grader. It prints nothing, exits nothing and decides no pass or fail. It submits
nothing, so it re-runs over a stored session document for free.

| Grader        | Read from                                    |
| ------------- | -------------------------------------------- |
| `regex`       | The resolved target below                    |
| `tool_used`   | `tool_calls`, matched on name and on the JSON-encoded input |
| `tool_order`  | `tool_calls`, in call order, because `before` and `after` each take an `input_match` |
| `file_exists` | The produced-file list below, as a glob      |
| `llm`         | a judge call on `focus`, 2 of 3              |
| `baseline`    | a judge call against `baseline_file`, 2 of 3 |

Grader targets map onto the session document as `last_message` to `final_text`, `trace` to
`turns` and `tool_calls`, `files` to the produced-file list, and `{source: file, path}` to
that path under `<session_dir>/outputs/`, which is the one place a produced file is readable
from the host. `mock_calls` has no equivalent here, because the MCP servers are the real
ones.

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

The model is `--judge-model` where one was given and `eval.judge_model` otherwise. The
signed-in `claude` on `PATH` is the one credential route, which is why [cli.md](cli.md) makes
it part of the `--cowork` preflight. `CLAUDE_CODE_WALNUT_SPIRE` is not exported: it gates
`claude plugin eval`, and this is `claude -p`.

An `llm` grader whose file focus turns out to be an image is a grader skip, not a failure:
the harness shows the judge the image, and one text call cannot. It is detected from the
file's bytes, as the harness detects it, so it is decided after the run rather than by the
skip rule. Any other binary is a failed grader naming what the file is.

## What the result document says that the reference does not

Both backends write the same v1 `aggregate-result.json`, so one gate covers both. The
contract is additive-only, which is what permits these. Nothing else here departs from
[claude_code/plugin_eval_reference.md](claude_code/plugin_eval_reference.md).

| Field                              | On                | Is                                                      |
| ---------------------------------- | ----------------- | --------------------------------------------------------- |
| `skipped`, `skipReason`            | a case            | Why the case submitted nothing. `arms.with` is empty     |
| `skipped`, `skipReason`            | a grader result   | Why that grader was not scored                           |
| `cowork.sessionDir`                | a run             | The session, which is what re-grades a stored run without submitting again, and where the run's artefacts are copied from |
| `cowork.timeoutSeconds`            | a run             | The timeout that run ran under, which is the override where one was given. It is the one place an effective value is recorded |
| `scored`                           | a grader result   | `not skipped`, widening the reference's `not withOnly` to the one other exclusion this backend has |

`withOnly` is always `false`: `ablation` is `none` here and nothing is dropped for an arm.

**The `cowork` key is also what says which backend produced a run.** The harness writes no
such key, so its presence is the rule that decides where one run's artefacts are read from
when the traces are collected: a session directory here, and a kept sandbox there. It is the
key and never its value, because a run the driver could not start carries the key with a null
`sessionDir`. See [running_evals.md](running_evals.md).

`tracePath` is the session's transcript when the document is written, and is rewritten to the
copy under the run's log directory once that copy is made. The session itself is still named,
in `cowork.sessionDir`. That is what makes a gate line say the same thing on both backends.

One behaviour departs as well. `casesPassed` is the reference's rule, a case scoring at or
above `threshold`, minus every skipped case. `threshold` is 0 here, so without that
subtraction a skipped case would count as passed. Nothing reads it to decide anything: the
gate in [running_evals.md](running_evals.md) reads the grader results and `skipped`.

Two fields mean something narrower here than they do under the harness.

| Field           | Here                                                                              |
| --------------- | ----------------------------------------------------------------------------------- |
| `claudeVersion` | The host `claude --version`. No CLI ran this suite, and that version is the judge's |
| `costUsd`       | The judge spend, and nothing else. A CoWork run is billed to the account and is not observable from the host. It is never estimated |

A CoWork run writes `aggregate-result.json` and the run's artefacts under `traces/`. There is
no `report.html` on this backend, and the artefacts carry the same three names the container
backend leaves. The log layout is [running_evals.md](running_evals.md).

Skips are recorded, never silent. A grader with no equivalent, and a case whose frontmatter
writes out a key this backend cannot honour, are both written into the result document as
skipped with the reason. A key the case leaves to its default is not a skip; the rule and
the key-by-key table are in [running_evals.md](running_evals.md). The gate fails a run that
reports a skip, so a suite cannot go green on CoWork by grading nothing.

## The plugin under test is not loaded

The deep link carries a prompt. It does not install a plugin, and nothing on the host writes
into the VM's configuration. A CoWork run therefore exercises the plugin set already
deployed to the signed-in account.

A case path selects which cases run. It does not select which code runs. A local edit to a
skill is invisible to this backend until it is deployed. Nothing checks it, because it is
not verifiable from the host.

## What one suite costs, and what a grader can be told here

A snapshot, captured 2026-09-09, from `tests/integration/test_cowork_backend.py` against
`plugins/smoke/`, whose one case writes `runs: 1`.

| Measured                                    | Value                                        |
| ------------------------------------------- | ---------------------------------------------- |
| Wall clock of one case                      | 6.1 s, the run's `durationSeconds`. It runs from the audit `user` record to the collection, so it excludes the deep link, the settle and the discovery |
| Ceiling entries one suite costs             | One per run. That suite is one case at `runs: 1`, so one entry |
| `costUsd` of that suite                     | 0. The case carries no judged grader, and a CoWork run is not observable from the host |

Two facts about the grader mapping cannot be read from a file, and both were measured
against the sessions in a real profile, with one run fired to provoke what the profile did
not already show.

| Measured                                            | Value | Consequence                                   |
| --------------------------------------------------- | ----- | ----------------------------------------------- |
| A transcript carries a `Skill` `tool_use` record   | yes   | The skill-fired idiom in [eval_format.md](eval_format.md) is gradable here |
| A session writes a produced file under `outputs/`  | yes   | `file_exists`, and a `{source: file, path}` target, are gradable here |

## The ceiling over a suite

The driver refuses one submission at a time, at step 1 of its sequence; see
[cowork_driver.md](cowork_driver.md). The backend refuses a whole suite before the first
submission: it sums each case's effective run count, which is `--runs` where one was given,
the declared `runs` where the case wrote one, and 1 otherwise, adds `recent()`, and raises
code 2 when the total is above `max_runs`. A skipped case submits nothing and costs no
ceiling entry.

