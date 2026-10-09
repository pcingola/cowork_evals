# Approaches

## Summary

An eval runs on one of two backends, and they answer different questions. One case tree runs
on both. Only the flag changes. Both write the same `aggregate-result.json` v1 document into
the same log directory, and one verdict decides pass and fail for both.

| Backend    | Command                            | Runs a case with                                                       | Grades with       | Proves                                                             |
| ---------- | ---------------------------------- | ---------------------------------------------------------------------- | ----------------- | ------------------------------------------------------------------ |
| `--docker` | `cowork_evals run --docker <path>` | `claude plugin eval` in a container that reproduces the CoWork image, Ubuntu 22.04 | the harness       | Skill logic, activation, hook denials, rendering, OCR, fonts, CLIs |
| `--cowork` | `cowork_evals run --cowork <path>` | the real desktop application and its VM                                | the CoWork grader | The deployed stack, end to end                                     |

`cowork_evals test` is not a backend. It runs a plugin's pytest suite on the CoWork runtime,
with no model and no case tree, and returns pytest's exit code instead of a result document.

A consumer never invokes `claude plugin eval` or `docker` directly.

## What each backend honours

The Docker backend runs the harness. The CoWork backend submits a prompt to a live session and
reads what the session wrote, so it honours a subset of the case format.

| Case feature                                            | `--docker`       | `--cowork`                                |
| ------------------------------------------------------- | ---------------- | ----------------------------------------- |
| `prompt.md` body                                        | yes              | yes                                       |
| `regex`, `tool_used`, `tool_order` graders              | yes              | yes                                       |
| `file_exists` grader                                    | any created file | files under `outputs/` only               |
| `llm` and `baseline` graders                            | yes              | yes, by a separate `claude -p` judge. An `llm` grader whose file focus is an image is skipped |
| `runs`, `timeout_seconds`                               | yes              | yes                                       |
| `max_turns`                                             | yes              | no, no turn cap reaches a session         |
| `model`, `allowed_tools`, `append_system_prompt`, `env` | yes              | no, the session decides                   |
| `context.add_dirs`, `context.scaffold_script`           | yes              | no, nothing stages files into the VM      |
| `mocks/`                                                | yes              | no, the MCP servers are the real ones     |
| `checks/`                                               | yes              | yes                                       |
| `arm:` on a grader                                      | live under `--ablation with-without`, inert otherwise | read, inert  |
| `no-cowork` in `tags:`                                  | an ordinary tag  | the case is not submitted, and is counted |
| a grader with `target` or `focus` of `mock_calls`       | yes              | that grader is skipped, the case runs     |

A `checks/` directory works on both backends because a check runs on neither. It is Python on
the host, and it runs after the backend finishes and the run's files are collected. Both
backends collect `last_message.txt`, `trace.jsonl` and `workspace/` under the same names, so
one check reads a Docker run and a CoWork run the same way.

A case that writes any key in a `no` row carries the `no-cowork` tag in its own `tags:`. The
validator enforces this in both directions. A tagged case submits nothing on CoWork and is
counted, never passed and never failed. There is no `no-docker` tag, because no case key is
one the Docker backend cannot honour. A command-line option a backend cannot honour is a usage
error instead, exit 2.

On CoWork, a case reads the keys it wrote, never the defaults. No `runs` key runs once.
`runs: N` runs N times. `timeout_seconds` is the driver's timeout for that case.

A skip fails the run. A declared case is not a skip: it submits nothing and fails nothing.

`arm:` decides which arm scores a grader, so it acts only when a run has two arms. That is
`--ablation with-without` on Docker, off by default, set by `eval.ablation`. Everywhere else
one arm runs, that arm is the with-arm, and `arm:` passes whatever value it carries.

There is no baseline arm on CoWork. A session takes its skills from the profile the
application is running, so a plugin is absent only in a profile it was never installed into.
`--ablation` and `--delta-threshold` exit 2 on `--cowork`. A case that carries `arm:` runs on
both backends and is not skipped.

Two failure conditions are Docker only: a tool refused by the permission mode, and a granted
tool the run was never offered. Both read a harness trace: a `permission_denied` record with
`decision_reason_type: mode`, and the `init` record's tool list. A session has no permission
mode and writes no tool list, so neither condition fires on CoWork.

## Costs and limits

Use Docker for everything except one question: does this work in the product that ships.
Answering that costs the machine for the length of the run. The CoWork costs come from driving
a desktop application that has no scriptable entry point.

| | `--docker` | `--cowork` |
| --- | --- | --- |
| Code under test | the plugin files in the checkout, so an edit is testable at once | the plugin set deployed to the signed-in account. A local edit is invisible until it is deployed |
| Per case | a container start plus the agent run | a VM boot plus the agent run, minutes |
| Headless | yes, runs unattended and in CI | no. Submission is a synthetic Return behind a macOS Accessibility grant. No CI route |
| The machine during the run | free to use | not usable. Each submission activates the application and sends Return to the frontmost window, so a keystroke or a click lands in the session or takes the focus the driver needs. Leave the machine alone until the suite ends |
| The account | a container login this package owns | the live account. A case can reach real mail, and every run leaves a permanent session in the account's history |
| Spend bound | `eval.max_cost_usd` per plugin, `eval.max_cost_total_usd` per invocation | nothing the host can see. `cowork.max_runs` bounds submissions |
| Several plugins at once | yes | exit 2 |
| Case format | all of it | the subset above |
| Depends on | the image definition this package ships | application internals no release promises to keep |

Docker is not CoWork. It has different model routing, no admin-applied enterprise prompt and
no CoWork MCP servers. The container matches the session's interpreter, wheels, document
tooling and fonts, and on an ARM Mac its architecture. The skill files are the ones that ship,
the real model decides activation, and hook denials fire. [runtime.md](runtime.md) has what a
session provides.

## When to run which

| Moment              | Command                                                     |
| ------------------- | ----------------------------------------------------------- |
| `git commit`        | nothing                                                     |
| Writing a case      | `cowork_evals run --docker <plugin>/evals/<skill>/<case>`   |
| Before opening a PR | `cowork_evals run --docker <plugin>/evals`, per plugin      |
| Before a release    | `cowork_evals run --docker <root>`, then a CoWork smoke set |

A CoWork run is a deliberate act before a release, named case by case. Never run it on a
commit.
