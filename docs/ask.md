# ask

## Summary

`cowork_evals ask --cowork` submits one prompt to a real CoWork session, waits, and prints the
answer. It runs no eval: no case tree, no grader, no result document, no verdict and no run
directory. It answers a question about what a live session actually does by asking one.

The submission is one call of the driver in [cowork_driver.md](cowork_driver.md). What the
application writes, and what a session does when asked, are
[cowork_desktop.md](cowork_desktop.md). What each backend honours is
[approaches.md](approaches.md), and what a session may import is [runtime.md](runtime.md).

```bash
cowork_evals ask --cowork "Reply with the single word: ready"
cowork_evals ask --cowork --dry-run "..."      # the deep link and the ceiling. Spends nothing
cowork_evals ask --cowork --json "..."         # the session document instead of the text
cowork_evals ask --cowork --session <dir>      # a session already on disk. Submits nothing
```

## Options

| Option                | Is                                                              |
| --------------------- | --------------------------------------------------------------- |
| `--cowork`            | The only backend. There is no `ask --docker`                    |
| `<prompt>`            | The prompt. `-` reads it from standard input                    |
| `--session <dir>`     | Print a session already on disk. Submits nothing, costs nothing |
| `--timeout-seconds N` | This run's timeout. It replaces `cowork.run_timeout`            |
| `--json`              | Print the session document instead of the text                  |
| `--dry-run`           | Print the deep link and the ceiling arithmetic. Submits nothing |

`ask` takes no other option. `--runs`, `--tag`, `--case`, `--out` and `--require-coverage`
configure a suite and belong to `run`.

## Output

| Form        | Standard output          | Standard error                                                      |
| ----------- | ------------------------ | ------------------------------------------------------------------- |
| default     | The final assistant text | The footer: `session`, `assistant turns`, `tools`, `outputs`, `log` |
| `--json`    | The session document     | Nothing                                                             |
| `--dry-run` | The deep link            | Planned submissions, submissions in the last 24 hours, `max_runs`   |

A redirect of standard output captures the answer alone:
`cowork_evals ask --cowork "..." > answer.txt`. A footer line with an empty value is not
printed, so a session that called no tool has no `tools` line. `--json` prints no footer,
because every footer value is a field of the document it printed.

The session document, key by key, and each `tool_calls` entry, are in
[cowork_driver.md](cowork_driver.md). A claim about a tool is checked against a call's `input`
and `result`, not against `final_text`.

`ask` writes nothing on the host: no run directory, no `latest`, no `env.txt` and no pruning.
The session directory in the profile is the permanent record. Read it again with
`--session <dir>`, never by asking again.

## What one ask costs

One ask costs a VM boot, one submission against `cowork.max_runs`, and the keyboard for the
length of the run, because the submission is a synthetic Return to the frontmost window. A
cold VM boot is about 45 seconds; see [cowork_desktop.md](cowork_desktop.md).

The rate ceiling is the driver's `cowork.max_runs`, checked before the submission and counted
from the run log. `ask` has no second ceiling. `--dry-run` prints the arithmetic instead of
spending against it.

## The preflight

A submission verifies these before it asks for the keyboard. `--dry-run` skips the preflight.
`--session` verifies nothing, so it reads an archived session on a machine that has no CoWork.

| Condition                     | The unmet line says                                                       |
| ----------------------------- | ------------------------------------------------------------------------- |
| macOS                         | The platform                                                              |
| `claude` on `PATH`            | Install the Claude Code CLI                                               |
| `cowork.profile` is set       | Set `cowork.profile` in `cowork_evals.yaml`                               |
| A readable sessions root      | Check `cowork.profile`, and open CoWork once on this profile              |
| The Accessibility grant       | Grant it to the terminal application in System Settings, Privacy and Security, Accessibility |

The rate ceiling is checked by the driver, not by the preflight. A refusal on it is driver
code 2, which also exits 3.

## check --cowork

`cowork_evals check --cowork` verifies the same conditions, writes nothing and never builds.
It prints `ready` on standard output, or the unmet lines on standard error, and exits 0 when
ready and 3 otherwise. `check --all` prints one section per backend, each named, on standard
output. `check` never reads the rate ceiling.

```
$ cowork_evals check --all
docker: ready
cowork: not ready
  no CoWork profile configured: set cowork.profile in cowork_evals.yaml
```

`check` cannot report every authorization a submission needs. The others are in
[cowork_desktop.md](cowork_desktop.md).

## The keyboard

A submission asks for the keyboard once, in a modal in front of every window, before it
fires. The modal has no default button, so a Return typed elsewhere does not dismiss it.
Cancel fires nothing and exits 3. With no answer, the modal proceeds after
`cowork.consent_timeout` seconds. `cowork.consent: none` fires without asking. `--dry-run`
and `--session` never ask. The rest of the keyboard handling is in
[cowork_driver.md](cowork_driver.md).

## Usage errors

Each exits 2, with a message naming what was typed.

| Typed                                | Refused because                      |
| ------------------------------------ | ------------------------------------ |
| Neither a prompt nor `--session`     | There is nothing to print            |
| A prompt and `--session` together    | The session is either new or on disk |
| `--timeout-seconds` with `--session` | Nothing waits                        |
| `--dry-run` with `--session`         | Nothing would be submitted           |

## Exit codes

| Code | Means                                                                              |
| ---- | ---------------------------------------------------------------------------------- |
| 0    | A session document was printed                                                     |
| 1    | The driver raised codes 3 to 9, or a `--session` directory is not there            |
| 2    | A usage error                                                                      |
| 3    | The CoWork preflight is unmet, or the driver refused before submitting (code 2)    |
| 130  | Interrupted                                                                        |

The message on standard error starts with the driver code. The failure taxonomy in
[cowork_driver.md](cowork_driver.md) says what each code means and what to do. `run --cowork`
maps driver code 2 to exit 3 the same way.

On a run timeout, driver code 7, the session keeps running in the VM. `ask` collects what the
session produced up to the timeout, prints it, and still exits 1. Read it again later with
`--session <dir>`.
