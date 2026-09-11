# claude plugin eval

## Summary

Claude Code's own eval harness. It loads one plugin into a fresh isolated `claude -p` session,
runs each case several times, and scores the result with graders. This repository does not own
it, and a consumer never invokes it.

- **Early access, enabled per organization.** A gated build prints that and exits 1. The
  command exists either way.
- **Only the plugin under test loads.** No user or project settings, no `CLAUDE.md`, no other
  plugins, no personal MCP servers.
- **Tools are gated.** `Bash`, `Write`, `Edit`, `WebFetch`, `WebSearch` and `mcp__*` need an
  explicit operator grant.
- **Its defaults would bite**, which is why [running_evals.md](running_evals.md) pins a flag
  list rather than accepting them.
- **The limits in this file cannot be fixed by editing a case.** The ones that can are in
  [eval_format.md](eval_format.md).

What a case file contains is [eval_format.md](eval_format.md), which is the authoring contract
for both backends, including the CoWork one that does not use this harness.

Written against CLI 2.1.259. The container backend installs 2.1.265, because 2.1.259 cannot
run a Bash-granting case on Linux: [docker.md](docker.md) records the failure. Nothing this
file states was re-checked against 2.1.265. The command is in early access and is not
publicly documented, so `claude plugin eval --help` in your own build is the authority when
this and the CLI disagree.

This file is a summary. Anthropic's own full reference is vendored at
[`claude_code/`](claude_code/) and is the authority for any detail this omits. It was
extracted from CLI 2.1.252, seven patch versions behind the 2.1.259 this is written
against. That gap has not been re-checked. `docs/claude_code/eval_smoke/` is a runnable
plugin, written here, that proves the harness works.

## Availability

Enabled per organization. When it is not enabled, the command prints that it is in early
access and exits 1. The command exists either way; a gated build is not a missing feature.

Enablement is the `tengu_walnut_spire` per-organization rollout flag. Enabled first-party
clients pick it up after `claude update` and a fresh session.

**Clients that cannot fetch server-side flags must set `CLAUDE_CODE_WALNUT_SPIRE=1`.** That
covers Bedrock, Vertex, Foundry, any client with a custom `ANTHROPIC_BASE_URL`, and any
client with `DISABLE_TELEMETRY`, `DO_NOT_TRACK`, `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC`
or `DISABLE_GROWTHBOOK` set. It needs CLI 2.1.207 or later.

Every backend that calls this command exports it, so no developer sets anything by hand:

```sh
export CLAUDE_CODE_WALNUT_SPIRE=1
```

It cannot be committed to a repository's `.claude/settings.json` `env`: only allowlisted
variables apply from project settings, this one is not allowlisted, and `claude plugin ...`
run from a shell or CI does not pass trust anyway. Set it in the shell, in CI, in
`~/.claude/settings.json` under `env`, or in managed settings.

Self-test from an empty directory:

| Output                | Means            |
| --------------------- | ---------------- |
| `early access`        | Not enabled here |
| `No eval cases found` | Enabled          |

## The cases it reads

Cases live under the plugin's eval directory, `evals/` by default. `--eval-dir` and the
manifest's `experimental.evals` move it, and this repository moves neither. The file format
is [eval_format.md](eval_format.md).

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

The target is a path, an installed plugin name, or `name@marketplace`. Put it before
`--tag`, `--allow-tools` and `--json`: those are variadic and will swallow a trailing
target.

Exit codes: 0 every case at or above the threshold (default 1.0); 1 below threshold, load
error, no cases, bad options; 2 partial, meaning the cost ceiling was hit or the credential
was rejected; 130 interrupted; 143 terminated.

## Flags worth pinning

| Flag              | Why                                                                                                                                                  |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--model`         | `ANTHROPIC_MODEL` is not inherited by the agent under test. Unpinned, a model rollout reads as a regression                                          |
| `--judge-model`   | Same, for the graders                                                                                                                                |
| `--ablation none` | The default runs a no-plugin baseline arm whenever the plugin resolves, doubling cost and demoting `tool_used: Skill` graders to unscored indicators |
| `--threshold 0`   | Let a local gate decide pass and fail, so structural and judged graders can be separated                                                             |
| `--max-cost-usd`  | Spend backstop. Hitting it exits 2 with partial results                                                                                              |
| `--output-dir`    | Puts `aggregate-result.json` and `report.html` in a log directory rather than under the plugin                                                       |
| `--no-publish`    | The HTML report is otherwise published to claude.ai                                                                                                  |
| `--no-scaffold`   | `context.scaffold_script` runs author-supplied shell as the invoking user                                                                            |
| `--keep-temp`     | Without it every passing run's sandbox is deleted, and its `trace.jsonl` with it. There is then nothing to read after a failure                     |

Do not pass `--json`. It silences progress lines, per-case grader lines, notices and the
summary table, and an errored run's sandbox is not kept. `--output-dir` gives the same
document with none of that loss.

A run's sandbox is created under `TMPDIR`, so where a kept sandbox lands is the caller's to
choose. That is how the container backend gets one onto the host:
[docker.md](docker.md). A kept sandbox is left read-only, with the two trees the plugin under
test wrote at mode 000 under `sealed/`, and `out/trace.jsonl` readable beside them. Measured
2026-09-10 against the CLI the image installs.

## Limits a case author has to know

Each of these has a silent failure mode, and none of them can be fixed by editing the case.
The ones that can are in [eval_format.md](eval_format.md).

- **Only the plugin under test loads.** No user or project settings, no `CLAUDE.md`, no
  other plugins, no personal MCP servers.
- **Tools are gated.** Effective tools are the case's `allowed_tools` intersected with the
  read-only set, unioned with the operator's `--allow-tools`. `Bash`, `Write`, `Edit`,
  `WebFetch`, `WebSearch` and `mcp__*` need an explicit grant. A plugin's own MCP tools are
  named `mcp__plugin_<plugin>_<server>__<tool>`.
- **Granting `Bash` turns on the OS sandbox.** On a machine with no sandbox backend the run
  is refused rather than run unconfined.
- **The Artifact tool is unavailable in a run.** A skill that ends by publishing cannot be
  exercised past that point.
- **Enterprise managed policy still applies inside a run.** Results on a managed machine
  differ from an unmanaged one by exactly that policy.
- **The network is not blocked.** The per-run sandbox is a fresh workspace, `HOME` and
  `CLAUDE_CONFIG_DIR`, not an OS-level network jail.

## Proving the harness works

`docs/claude_code/eval_smoke/run.sh` is a throwaway plugin with two skills, three cases and
four grader types. It calls `claude plugin eval` directly, with no wrapper from this
repository, so it separates a harness problem from a runner problem.

## Cost

Agent runs are `cases x runs x arms`. Each `llm` or `baseline` grader adds three judge
calls. Structural graders are free.

A 10-case suite at `runs: 3` with the baseline arm on is 60 agent runs before a single judge
call. That is why `--ablation none` is the default in this repository and `with-without` is
a manual investigation tool.
