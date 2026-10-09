# claude plugin eval

## Summary

`claude plugin eval` is Claude Code's own eval harness, shipped inside the `claude` CLI. It
loads one plugin into a fresh isolated `claude -p` session, runs each case several times, and
scores the result with graders. A consumer never invokes it: `cowork_evals run --docker` runs
it, and `--cowork` does not run it at all. The graders it defines are the graders on both
backends.

This file holds each grader type's fields and how each one decides, the ablation arms, the
limits a case cannot fix, and what a run costs. What a case file contains is
[eval_format.md](eval_format.md).

- Only the plugin under test loads. No user or project settings, no `CLAUDE.md`, no other
  plugins, no personal MCP servers.
- Tools need an explicit grant. `Bash`, `Write`, `Edit`, `WebFetch`, `WebSearch` and `mcp__*`
  are outside the read-only set.
- The command is in early access and is not publicly documented. `claude plugin eval --help`
  in the installed build is the authority when this file and the CLI disagree.

## Grader fields

The keys every grader takes, and the values of `target` and `focus`, are
[eval_format.md](eval_format.md#graders). The file body is the pattern for `regex` and the
criteria for `llm` and `baseline`.

| Type          | Fields                                                                                                                                                       | Passes when                                                                                       |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| `regex`       | `pattern`, JavaScript RegExp source. `flags`, from `d g i m s u v y` only. `match`: `contains` (default), `not_contains`, `count:N`. `target`                 | The pattern is found, is not found, or is found exactly N times                                   |
| `tool_used`   | `tool`, the name as the trace shows it. `input_match`, a regex over the JSON-encoded tool input. `min` (default 1). `max` (default unlimited)                 | The number of matching calls is within `min..max`                                                 |
| `tool_order`  | `before`, `after`. Each is a tool name or `{tool, input_match}`                                                                                              | Both were called, and the first matching `before` call precedes the first matching `after` call   |
| `file_exists` | `path`, a glob over created files: `**/` is any depth, `*` is within one segment. `exists` (default true)                                                    | A created file matches, or none does with `exists: false`                                         |
| `llm`         | `criteria`, the rubric, which is the file body. `focus`                                                                                                      | A judge votes PASS in at least 2 of 3 votes                                                       |
| `baseline`    | `baseline_file`, a `.jsonl` trace in the case directory. `criteria`                                                                                          | The judge finds the new trajectory meets the criterion at least as well as the baseline, 2 of 3   |

### regex

There is no inline `(?i)`. Use `flags: i`.

`pattern` is JavaScript RegExp source, so `^` and `$` match the start and end of the whole
target, not of a line, unless `flags` has `m`. This differs from Python, where `$` also matches
before a trailing newline. On Node 25.9.0, over `^\s*(?:blocker|major|minor)\s*$`:

| Target                    | no flags | `m`  |
| ------------------------- | -------- | ---- |
| `blocker`                 | pass     | pass |
| `blocker\n`               | pass     | pass |
| `  minor  `               | pass     | pass |
| `minor.`                  | fail     | fail |
| `The severity is blocker` | fail     | fail |
| `blocker\nmajor`          | fail     | pass |
| `line one\nblocker`       | fail     | pass |

A trailing newline passes because `\s*` consumes it, not because `$` matches before it. A
pattern with no `\s*` over a target that ends in a newline fails.

Over `trace`, quotes and newlines are JSON-escaped: match `\"`, not `"`.

A `regex` over an image always fails. Over another binary it matches only ASCII sequences, and
non-ASCII bytes decode to U+FFFD.

### tool_used

`tool` is the trace name: `Skill`, `Read`, `Edit`, or `mcp__plugin_<plugin>_<server>__<tool>`
for a plugin MCP tool.

A must-not-call assertion is `min: 0, max: 0`. `max: 0` alone never passes, because `min`
stays 1.

The skill fired:

```yaml
type: tool_used
tool: Skill
input_match: '"skill"\s*:\s*"(?:[\w-]+:)?<skill>"'
```

To check that a build or a test passed, have the agent run it and write the outcome to a file,
grade the file, and assert the command ran with `tool_used` and `input_match`. A compound shell
command is denied as a whole, so grant each command form the run uses, such as
`Bash(npm test:*)`.

### file_exists

It sees only files created during the run. A file that already existed, a file a scaffold
created, and a file the agent modified are invisible to it. Grade the contents, or assert a
`tool_used` on `Edit`.

### llm

The judge is a small fast model unless `--judge-model` or `eval.judge_model` names another. It
sees up to 100k characters of the focus, head and tail kept. On `trace` it sees the first and
last 12 messages. Above about 8000 characters its verdicts get noisy: prefer a `regex` over
`{source: file, path}` for a long artifact. Write the rubric as concrete, checkable claims.

`target` on an `llm` grader is ignored. The key is `focus`.

| Focus file                                                      | The judge                                                          |
| --------------------------------------------------------------- | ------------------------------------------------------------------ |
| UTF-8 text                                                      | Reads it. A leading BOM is dropped                                 |
| PNG, JPEG, GIF or WebP, detected from bytes                     | Is shown the image, downscaled. On `--cowork` the grader is a skip |
| `.pptx`, `.docx`, `.xlsx`, PDF, UTF-16, any file with NUL bytes | Is not asked. The grader is refused                                |
| A truncated or corrupt image                                    | Is not asked. The grader fails                                     |

Grade a deck or a diagram by rendering it to an image or by writing its content out as UTF-8
text. The vision judge grades what is visible. To assert that an artifact does not contain
something, use `regex` with `not_contains` over a text rendering. A judge that reads a binary
file itself is `run.judge` in a check: [checks.md](checks.md#asking-a-judge).

### Choosing

- Prefer a structural grader. `llm` and `baseline` vary from run to run, and are noisy on long
  inputs.
- Grade the outcome, a file's contents or the final message, and the mechanism, a `tool_used`
  or `tool_order` on the trace.
- Do not depend on a live third-party response.

## Ablation arms

Under `--ablation with-without` each case runs with the plugin and with no plugin. It is off
by default and runs on `--docker` only. How the delta decides a case is
[running_evals.md](running_evals.md).

`arm` selects which arm scores a grader: `with-only` or `both`. A grader with
`arm: with-only`, and a `tool_used` on `Skill` with no `arm`, is dropped from the without-arm
and is not scored in either arm. It is reported as an indicator. When every grader of a case
is with-only, they are scored normally.

`arm: both` scores a `Skill` grader in both arms, such as a `min: 0, max: 0` must-not-fire
grader. Without ablation nothing is excluded, so a `tool_used: Skill` grader is scored and can
fail the run. A case that never runs under ablation sets `arm` only to stay portable.

## Limits a case cannot fix

Each of these fails silently, and none is fixed by editing the case. The ones a case can fix
are [eval_format.md](eval_format.md#authoring-traps).

- **Only the plugin under test loads.** No user or project settings, no `CLAUDE.md`, no other
  plugins, no personal MCP servers.
- **Tools need an explicit grant.** The effective set is the case's `allowed_tools`
  intersected with the read-only set, unioned with `eval.allow_tools`. `Bash`, `Write`, `Edit`,
  `WebFetch`, `WebSearch` and `mcp__*` are outside the read-only set. A plugin's own MCP tools
  are named `mcp__plugin_<plugin>_<server>__<tool>`. A case writing no `allowed_tools` still
  has `Skill`, and its skill fires and scores under a grant of `Bash` alone. What was measured
  tool by tool is [running_evals.md](running_evals.md).
- **`Monitor`, `EnterWorktree` and `ExitWorktree` are never available.** Granting one is
  reported as not granted.
- **An ungranted tool fails in two ways.** It is offered and refused at the call, which writes
  a `system` record of subtype `permission_denied` carrying `decision_reason_type`, or it is
  not offered at all, which writes nothing. Both are silent to a grader. `cowork_evals` reads
  the kept trace for both and fails the run: [running_evals.md](running_evals.md).
- **Granting `Bash` turns on the OS sandbox.** On a machine with no sandbox backend the run is
  refused rather than run unconfined.
- **The Artifact tool is unavailable in a run.** A skill that ends by publishing cannot be
  exercised past that point.
- **Enterprise managed policy still applies inside a run.** Results on a managed machine differ
  from an unmanaged one by exactly that policy.
- **Network reach is not uniform.** The plugin's own hooks and MCP servers run as the invoking
  user, unconfined, with normal network access. A command in a granted `Bash` call runs under
  the OS sandbox and reaches only the domains a `WebFetch(domain:...)` grant in
  `eval.allow_tools` names.

## Cost

Agent runs are `cases x runs x arms`. Each `llm` or `baseline` grader adds three judge calls.
Structural graders are free.

A 10-case suite at `runs: 3` with the baseline arm on is 60 agent runs before a single judge
call. `eval.ablation` is `none` by default, and `with-without` is asked for one sweep at a time.

Measured over three cases at `runs: 1`, one `llm` grader, under `--ablation with-without`: six
agent runs, 34 s and 0.35 USD. The one-arm number for the same tree is half the agent runs.
The ceilings are [running_evals.md](running_evals.md).
