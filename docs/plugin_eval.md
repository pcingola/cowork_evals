# claude plugin eval

## Summary

`claude plugin eval` is Claude Code's own eval harness, shipped inside the `claude` CLI. It
loads one plugin into a fresh isolated `claude -p` session, runs each case several times, and
scores the result with graders. This repository does not own it, and a consumer never invokes
it: the container backend runs it, and the CoWork backend does not run it at all. This file
records what the harness does, so that a case author knows which failures come from the harness
and cannot be fixed by editing a case.

- **Early access, enabled per organization.** A build without early access prints that and
  exits 1. The command exists either way.
- **Only the plugin under test loads.** No user or project settings, no `CLAUDE.md`, no other
  plugins, no personal MCP servers.
- **Tools need an explicit grant.** `Bash`, `Write`, `Edit`, `WebFetch`, `WebSearch` and
  `mcp__*` are outside the read-only set.
- **Its defaults are wrong for this repository**, which is why
  [running_evals.md](running_evals.md) pins a flag list rather than accepting them.

What a case file contains is [eval_format.md](eval_format.md), the authoring contract for both
backends. A limit a case author can work around is there; the ones here cannot be worked around.

Written against CLI 2.1.259. The container backend installs 2.1.265, because 2.1.259 cannot run
a Bash-granting case on Linux: [docker.md](docker.md) records the failure. The command is in
early access and is not publicly documented, so `claude plugin eval --help` in your own build is
the authority when this file and the CLI disagree.

This file is a summary. Anthropic's own full reference is vendored at
[`claude_code/`](claude_code/README.md), which is the authority for any detail omitted here and
records which CLI version the vendored copies came from. `docs/claude_code/eval_smoke/` is a
runnable plugin, written here, that proves the harness works.

## Availability

Enabled per organization. When it is not enabled, the command prints that it is in early access
and exits 1. The command exists either way; a build without early access is not a missing
feature.

Enablement is the `tengu_walnut_spire` per-organization rollout flag. Enabled first-party
clients pick it up after `claude update` and a fresh session.

**A client that cannot fetch server-side flags must set `CLAUDE_CODE_WALNUT_SPIRE=1`.** That
covers Bedrock, Vertex, Foundry, any client with a custom `ANTHROPIC_BASE_URL`, and any client
with `DISABLE_TELEMETRY`, `DO_NOT_TRACK`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC` or
`DISABLE_GROWTHBOOK` set. It needs CLI 2.1.207 or later.

The container backend sets it inside the container, so a consumer sets nothing by hand:

```sh
export CLAUDE_CODE_WALNUT_SPIRE=1
```

It cannot be committed to a repository's `.claude/settings.json` `env`. Only allowlisted
variables apply from project settings, this one is not allowlisted, and `claude plugin ...` run
from a shell or CI does not pass trust anyway. Set it in the shell, in CI, in
`~/.claude/settings.json` under `env`, or in managed settings.

Self-test from an empty directory:

| Output                | Means            |
| --------------------- | ---------------- |
| `early access`        | Not enabled here |
| `No eval cases found` | Enabled          |

## The cases it reads

Cases live under the plugin's eval directory, `evals/` by default. `--eval-dir` and the
manifest's `experimental.evals` move it, and this repository moves neither. The file format is
[eval_format.md](eval_format.md).

Left alone the CLI writes `aggregate-result.json` and `report.html` to
`<eval dir>/results/<timestamp>/`, inside the consumer's checkout. Every backend here pins
`--output-dir` at the run's log directory instead, so nothing is written under a plugin. See
[running_evals.md](running_evals.md).

## Running

```
claude plugin eval [target] [--case glob] [--tag t...] [--runs n] [--model m]
                   [--judge-model m] [--max-cost-usd usd] [--eval-dir dir]
                   [--output-dir dir] [--json [file]] [--threshold 0..1]
                   [--allow-tools t...] [--scaffold|--no-scaffold]
                   [--ablation none|with-without] [--mocks record|off]
                   [--keep-temp] [--verbose] [--report path]
                   [--publish-report|--no-publish]
```

The target is a path, an installed plugin name, or `name@marketplace`. Put it before `--tag`,
`--allow-tools` and `--json`: those are variadic and will swallow a trailing target. Every
backend here passes a path.

Exit codes: 0 every case at or above the threshold (default 1.0); 1 below threshold, load
error, no cases, bad options; 2 partial, meaning the cost ceiling was hit or the credential was
rejected; 130 interrupted; 143 terminated.

## Flags worth pinning

| Flag             | Harness default                                           | Behaviour behind it                                                                                                                                                                             |
| ---------------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `--model`        | the case's `execution.model`, else the child's own default | `ANTHROPIC_MODEL` is not inherited by the agent under test. Unpinned, a model rollout reads as a regression                                                                                      |
| `--judge-model`  | a small fast model                                         | The same, for the graders                                                                                                                                                                       |
| `--ablation`     | `none` for a path target, `with-without` for a named plugin | The baseline arm doubles the agent runs and demotes `tool_used: Skill` graders to unscored indicators. Pinning it means a target that is later named rather than pathed does not silently change the score |
| `--threshold`    | `1.0`                                                      | At `0` the harness fails nothing, which is what hands pass and fail to this package                                                                                                              |
| `--max-cost-usd` | no ceiling                                                 | Spend backstop. Hitting it exits 2 with partial results                                                                                                                                         |
| `--output-dir`   | `<eval dir>/results/<timestamp>/`                          | Puts `aggregate-result.json` and `report.html` in a log directory rather than under the plugin                                                                                                   |
| `--no-publish`   | publish attempted when the account can                     | The HTML report is otherwise published to claude.ai                                                                                                                                             |
| `--no-scaffold`  | scaffold off                                               | `context.scaffold_script` is author-supplied shell and runs as the invoking user                                                                                                                |
| `--keep-temp`    | off                                                        | Without it only an errored run's sandbox survives. A run that merely scored low is deleted with its `trace.jsonl`, so there is nothing to read after a failure                                   |
| `--verbose`      | off                                                        | Extra trace logging reaches the debug log only. Nothing extra reaches the terminal                                                                                                               |

Do not pass `--json`. It silences progress lines, per-case grader lines, notices and the summary
table, and an errored run's sandbox is not kept. `--output-dir` gives the same document with
none of that loss.

A run's sandbox is created under `TMPDIR`, so where a kept sandbox lands is the caller's to
choose. That is how the container backend gets one onto the host: [docker.md](docker.md). A kept
sandbox is left read-only, with the two trees the plugin under test wrote at mode 000 under
`sealed/`, and `out/trace.jsonl` readable beside them, against the CLI the image installs.

## Limits a case author has to know

Each of these has a silent failure mode, and none can be fixed by editing the case. The ones
that can are in [eval_format.md](eval_format.md).

- **Only the plugin under test loads.** No user or project settings, no `CLAUDE.md`, no other
  plugins, no personal MCP servers.
- **Tools need an explicit grant.** The effective set is the case's `allowed_tools` intersected
  with the read-only set, unioned with the operator's `--allow-tools`. `Bash`, `Write`, `Edit`,
  `WebFetch`, `WebSearch` and `mcp__*` are outside the read-only set. A plugin's own MCP tools
  are named `mcp__plugin_<plugin>_<server>__<tool>`. On CLI 2.1.265 a case writing no
  `allowed_tools` still has `Skill`, and its skill fires and scores under an operator grant of
  `Bash` alone, so the intersection does not empty the read-only set. What was measured tool by
  tool is [running_evals.md](running_evals.md).
- **`Monitor`, `EnterWorktree` and `ExitWorktree` are never available.** Granting one is
  reported as not granted.
- **An ungranted tool fails in two ways.** It is offered and refused at the call, which writes a
  `system` record of subtype `permission_denied` carrying `decision_reason_type`, or it is not
  offered at all, which writes nothing. Both are silent to a grader.
- **Granting `Bash` turns on the OS sandbox.** On a machine with no sandbox backend the run is
  refused rather than run unconfined.
- **The Artifact tool is unavailable in a run.** A skill that ends by publishing cannot be
  exercised past that point.
- **Enterprise managed policy still applies inside a run.** Results on a managed machine differ
  from an unmanaged one by exactly that policy.
- **Network reach is not uniform.** The plugin's own hooks and MCP servers run as the invoking
  user, unconfined, with normal network access. A command in a granted `Bash` call runs under
  the OS sandbox and reaches only the domains an `--allow-tools "WebFetch(domain:...)"` grant
  names.

## Proving the harness works

`docs/claude_code/eval_smoke/run.sh` is a throwaway plugin with two skills, three cases and four
grader types. It calls `claude plugin eval` directly, with no wrapper from this repository, so
it separates a harness problem from a runner problem.

## Cost

Agent runs are `cases x runs x arms`. Each `llm` or `baseline` grader adds three judge calls.
Structural graders are free.

A 10-case suite at `runs: 3` with the baseline arm on is 60 agent runs before a single judge
call. That is why `eval.ablation` is `none` in this repository and `with-without` is asked for
one sweep at a time. The option is [running_evals.md](running_evals.md).

Measured over `docs/claude_code/eval_smoke/`, three cases at `runs: 1`, one `llm` grader, under
`--ablation with-without`: six agent runs, 34 s and 0.35 USD. The one-arm number for the same
tree is half the agent runs.
