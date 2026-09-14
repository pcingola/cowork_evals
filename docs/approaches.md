# Approaches

## Summary

An eval can be run two ways, and they answer different questions. The Docker backend runs the
`claude plugin eval` harness inside a container that reproduces the CoWork image: it is
headless, it costs a container start, and it runs the plugin files in your checkout. The
CoWork backend drives the real desktop application: it is the deployed stack end to end, it
costs a VM boot per case, and it takes the keyboard and the frontmost window, so the machine
is unusable for the length of the run and there is no headless route. One case format serves
both, so the backend changes and the case does not. This file says what each backend proves,
what each costs, and which part of the case format each honours.

Which of the two is built is the status table in [running_evals.md](running_evals.md). A third
backend, Claude Code against a 3.10 mirror on the host, is designed and not built. See
[staged_runtime.md](staged_runtime.md).

| Approach                | Runs on                      | Proves                                                             | Design                               |
| ----------------------- | ---------------------------- | -------------------------------------------------------------------- | ------------------------------------ |
| Claude Code, Docker     | `claude` in the container, Ubuntu 22.04 | Skill logic, activation, hook denials, rendering, OCR, fonts, CLIs | [docker.md](docker.md)     |
| CoWork, driven directly | The real CoWork VM           | The deployed stack, end to end                                      | [cowork_driver.md](cowork_driver.md) |

This is the one copy of that table. `README.md` introduces the same two approaches in prose and
links here.

## One case format, two backends

An eval is written once, in the `claude plugin eval` case format: a `prompt.md` carrying
frontmatter and the prompt body, a `graders/` directory, and an optional `case.yaml`. It is the
only eval format in this repository, and [eval_format.md](eval_format.md) owns it.

The same case tree runs on both approaches. Only the backend changes.

| Approach | Command                            | Executes a case                        | Grades with       |
| -------- | ---------------------------------- | -------------------------------------- | ----------------- |
| Docker   | `cowork_evals run --docker <path>` | `claude plugin eval`, in the container | the harness       |
| CoWork   | `cowork_evals run --cowork <path>` | the desktop driver                     | the CoWork grader |

One executable, one path argument, one backend flag. The full surface is [cli.md](cli.md).

Both backends write the same `aggregate-result.json` v1 document into the same log directory,
so one verdict decides pass and fail identically for both.

`cowork_evals test` is not a third backend. It runs a consumer's pytest suite on the CoWork
runtime, with no model and no case tree, and returns an exit code rather than a result
document. See [cowork_test.md](cowork_test.md).

## What each backend honours

The Docker backend runs the harness. The CoWork backend submits a prompt to a live session and
reads what the session wrote, so it honours a subset of the format.

| Case feature                                            | Docker backend   | CoWork backend                          |
| ------------------------------------------------------- | ---------------- | --------------------------------------- |
| `prompt.md` body                                        | yes              | yes                                     |
| `regex`, `tool_used`, `tool_order` graders              | yes              | yes                                     |
| `file_exists` grader                                    | any created file | files under `outputs/` only             |
| `llm` and `baseline` graders                            | yes              | yes, judged by a separate `claude -p` call. An `llm` grader whose file focus is an image is skipped |
| `runs`, `timeout_seconds`                               | yes              | yes                                     |
| `max_turns`                                             | yes              | no, no turn cap reaches a session       |
| `model`, `allowed_tools`, `append_system_prompt`, `env` | yes              | no, the session decides                 |
| `context.add_dirs`, `context.scaffold_script`           | yes              | no, nothing stages files into the VM    |
| `mocks/`                                                | yes              | no, the MCP servers are the real ones   |
| `checks/`, this package's own                           | yes              | yes                                     |
| `arm:` on a grader                                      | live under `--ablation with-without`, inert otherwise | read, but inert |
| `no-cowork` in `tags:`                                  | one more tag     | the case is not submitted, and is counted |

A `checks/` directory is honoured on both backends, because a check runs on neither of them. It
is Python on the host, and it runs after the backend has finished and the run's files have been
collected. Both backends collect the same three files under the same three names, so one check
reads a Docker run and a CoWork run the same way. See [checks.md](checks.md).

A case that needs any of the four rows this backend answers `no` to says so itself, with the
`no-cowork` tag in its own `tags:`. The tag is [eval_format.md](eval_format.md), and the
validator enforces it in both directions, so this table and the case cannot disagree. There is
no `no-docker` counterpart: nothing names a case key the Docker backend cannot honour.

A session called three tools over four probes with nothing granted to it, which is what
`no, the session decides` above is read from. Those probes are section 5 of
[cowork_desktop.md](cowork_desktop.md).

`arm:` decides which arm scores a grader, so it does something only when a run has two arms.
That is `--ablation with-without` on the Docker backend, which is off by default and is
`eval.ablation`. Everywhere else the flag is `none`, one arm runs, that arm is the with-arm,
and `arm:` satisfies itself whichever value it carries.

There is no baseline arm on CoWork, and none is designed. A session gets its skills from the
profile the desktop application is running, and that tree is the application's to manage, so a
plugin is absent only in a profile it was never installed into and nothing here chooses which
profile is active. `--ablation` and `--delta-threshold` are therefore a usage error on
`--cowork`. A case carrying `arm:` for portability is honoured rather than skipped on both. See
[running_evals.md](running_evals.md).

One pass and fail condition is Docker only. A run that never had a tool the case was granted
fails rather than scoring, and both ways of catching it read a harness trace: a
`permission_denied` record with `decision_reason_type: mode`, and the `init` record's tool
list. A session has no permission mode, is never refused a tool by one, and writes no such
list, so neither is ever found on CoWork and every `--cowork` document is the shape that
passes. One decision still covers both backends. See [running_evals.md](running_evals.md).

A case that writes out a key the CoWork backend cannot honour carries the tag, submits nothing
there and is counted, never passed and never failed. A default is not a request, so a case that
writes no `runs` key runs once rather than declaring anything; the exact rule is in
[running_evals.md](running_evals.md). A command-line option a backend cannot honour is a usage
error instead, and the difference is stated in [cli.md](cli.md).

## Pros and cons

Use Docker for everything except the one question it cannot answer: does this work in the
product that ships. Answering that costs the machine for the length of the run. None of the
CoWork costs is reduced by better engineering. Each is a property of driving a desktop
application that exposes no scriptable entry point.

| | Docker | CoWork |
| ------------------------- | ------------------------------------ | ------------------------------------ |
| Runs the code             | the plugin files in your checkout, so an edit is testable before it is deployed | the plugin set already deployed to the signed in account. A local edit is invisible until it is deployed |
| Per case                  | a container start plus the agent run | a VM boot plus the agent run, so minutes |
| Headless                  | yes, so it runs unattended and in CI | no. The submit step is a synthetic keystroke behind a macOS Accessibility grant, so there is no CI route at all. See [cowork_desktop.md](cowork_desktop.md) |
| Your machine while it runs | yours. A container is not the desktop | not yours. Each submission activates the application and sends Return to the frontmost window, so a keystroke or a click of yours lands in the session or takes the focus the driver needs. Leave the machine alone until the suite ends. See [cowork_driver.md](cowork_driver.md) |
| The account               | what `docker.credential` names: a container login this package owns, or the host's Bedrock credential. See [docker.md](docker.md) | a live account. A case can reach real mail, and every run leaves a permanent session in that account's history. See [cowork_driver.md](cowork_driver.md) |
| What bounds the spend     | `eval.max_cost_usd` over one plugin's suite, and `eval.max_cost_total_usd` over the whole invocation | nothing the host can observe. The driver's `max_runs` ceiling bounds submissions instead |
| Several plugins at once   | yes                                  | a usage error. See [cli.md](cli.md)  |
| The case format           | all of it                            | the subset above                     |
| Couples to                | the image definition in this repository | application internals that no release promises to keep. See [cowork_desktop.md](cowork_desktop.md) |

## Claude Code as a proxy for CoWork

`claude plugin eval` loads one plugin into a fresh isolated session, runs each case, and scores
it with graders. It is the only harness that knows how to load a plugin, so it is the harness
the Docker backend uses. See [plugin_eval.md](plugin_eval.md). It is not part of the command
surface: a consumer never invokes it.

What it gets right: the skill files under test are the ones that ship, activation is decided by
the real model, and hook denials fire.

What it gets wrong: it is not CoWork. Different model routing, no admin-applied enterprise
prompt, and no CoWork MCP servers. See [runtime.md](runtime.md) for the size of that gap.

The container narrows the host half of it: `ubuntu:22.04` with the same interpreter, wheels,
document tooling and fonts, and on an ARM Mac the same architecture. It costs an image build
and a slower run than a bare host would. See [docker.md](docker.md).

## CoWork, driven directly

The most accurate result, because it is the deployed stack. CoWork exposes no scriptable entry
point, so the only route is to drive the desktop application: submit a prompt through its
`claude://` URL scheme, press Return with a synthetic keystroke, and read the transcript, audit
log and outputs the session writes to the host filesystem. See
[cowork_desktop.md](cowork_desktop.md).

**The plugin under test is not loaded by this backend.** A CoWork run exercises the plugin set
already deployed to the signed-in account, so a local edit to a skill is invisible here until it
is deployed. What that means for a case path is [cowork_backend.md](cowork_backend.md).

## Which to use when

This is the cadence a consumer repository follows. It is the one copy;
[running_evals.md](running_evals.md) links here rather than repeating it.

| Moment              | Command                                                      | Enforced by           |
| ------------------- | ------------------------------------------------------------ | --------------------- |
| `git commit`        | nothing                                                      | no hook, by design    |
| Writing a case      | `cowork_evals run --docker <plugin>/evals/<skill>/<case>`     | the author            |
| Before opening a PR | `cowork_evals run --docker <plugin>/evals`, per plugin        | the PR template       |
| Before a release    | `cowork_evals run --docker <root>`, then a CoWork smoke set   | the release checklist |

A CoWork run is a person's deliberate act before a release. It is never run on a commit.

Which of these commands is built is the status table in
[running_evals.md](running_evals.md), and what reaches the container is
[docker.md](docker.md).
