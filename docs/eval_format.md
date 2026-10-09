# Eval case format

## Summary

A case is a directory: a `prompt.md` carrying frontmatter and the prompt body, a `graders/`
directory, an optional `case.yaml` and an optional `checks/` directory. This file is the
authoring contract for every one of them, on both backends: the tree, the file names, every
`prompt.md` and `case.yaml` key, the keys every grader takes, MCP mocks, what the validator
refuses, and the traps that fail silently. The format is `claude plugin eval`'s own, so a case
needs no adapter to run under that harness.

Each grader type's fields, and the harness limits a case cannot fix, are
[plugin_eval.md](plugin_eval.md). Checks are [checks.md](checks.md). Which backend honours
which field is [approaches.md](approaches.md). How a run decides pass and fail is
[running_evals.md](running_evals.md).

Four rules here belong to `cowork_evals` and not to the harness: the `<skill>` layer under
`evals/`, the two addressability keys, the reserved tag, and the `checks/` directory, which
the harness neither reads nor knows is there. Everything else is the harness.

## The tree

One eval directory per skill, inside the plugin, in the repository that owns the plugin.

```
<plugin>/.claude-plugin/plugin.json               # what makes <plugin> a plugin root
<plugin>/evals/<skill>/<case>/prompt.md
<plugin>/evals/<skill>/<case>/graders/<name>.md
<plugin>/evals/<skill>/<case>/checks/<name>.py    # optional, assertions as Python
<plugin>/evals/<skill>/<case>/case.yaml           # optional, context.* only
<plugin>/evals/plugin/<case>/                     # a case that crosses skills
<plugin>/evals/mocks/<server>/<tool>.md           # MCP tool mocks shared by every case
```

`<plugin>` is any directory holding `.claude-plugin/plugin.json`. Its place in the repository
is free. `evals/` is the harness default, so nothing is configured.

A case is a directory holding `prompt.md`. Discovery under `evals/` is recursive: a grouping
directory that is not a case is searched through, not run. Discovery does not recurse into a
case directory, so its `graders/`, `checks/` and fixtures are not cases. Cases run in
lexicographic directory order.

A directory directly under `evals/` is a skill name, `plugin` or `mocks`, and the validator
refuses anything else. A skill name is a directory under `<plugin>/skills/`, so a tree naming
a skill the plugin lacks is refused rather than run against nothing. A skill with no eval
directory is reported as missing coverage and fails nothing, unless the run passes
`--require-coverage`. One directory per skill is what makes `--tag` selection match the tree.

Fixtures live inside the case that uses them. `context.add_dirs` refuses any entry outside the
case directory, and any entry inside its `checks/`.

## Addressability

Two frontmatter keys make a case addressable, and both are checked.

| Key       | Value                                         | Rule                                                                                         |
| --------- | --------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `tags`    | `[<skill>]`, plus `no-cowork` where required  | Names the case's own `<skill>` directory. `--tag <skill>` is the reliable per-skill selector |
| `plugins` | `["../../.."]` from `evals/<skill>/<case>/`   | Resolves from the case directory to the plugin root, whatever the plugin is called           |

`--case` globs the case name. The name is the `name` key, which can differ from the directory
name.

## The reserved tag

`no-cowork` is the one reserved tag. A case carrying it declares that a live CoWork session
cannot run it. It lives in `tags:`, beside the `<skill>` tag, so `--tag <skill>` still selects
the case. A case carries it if and only if it has one of these sources:

| Source                                                                    | Written in               | Why a session cannot honour it                     |
| ------------------------------------------------------------------------- | ------------------------ | -------------------------------------------------- |
| `max_turns`, `model`, `allowed_tools`, `append_system_prompt` or `env`    | `prompt.md` frontmatter  | [approaches.md](approaches.md), key by key         |
| Any `context.*` key                                                       | `case.yaml`              | Nothing stages files into the VM                   |
| A `mocks/` directory on the case's chain of parent directories            | `evals/mocks/`, a grouping directory, or the case | The MCP servers in a session are the real ones |

Writing a key is the source. Leaving it at its default is not, because a default is not a
request. The tag is declared on each case and not on a directory, so a plugin whose
`evals/mocks/` covers every case tags every case.

The validator checks both directions, and each exits 3 in `run`'s preflight.

| The case                                     | Rule                 |
| -------------------------------------------- | -------------------- |
| Has a source and no `no-cowork`              | `no-cowork-missing`  |
| Carries `no-cowork` and has no source        | `no-cowork-unneeded` |

The second direction keeps the tag from becoming a way to switch a case off. There is no
`skip:` field in a case tree.

On `--docker` the tag is an ordinary tag. On `--cowork` the case is not submitted and is
counted, not failed. There is no `no-docker` tag. See [running_evals.md](running_evals.md).

## prompt.md

Frontmatter, then the prompt body.

```markdown
---
name: one-paragraph
description: The skill fires, and the answer is one paragraph.
tags: [summarize]
plugins: ["../../.."]
runs: 3
---

Summarize `notes/standup.md` in one paragraph.
```

| Key                                  | Is                                                          |
| ------------------------------------ | ----------------------------------------------------------- |
| `name`                               | Required                                                    |
| `tags`, `plugins`                    | Required. Addressability, above                             |
| `description`                        | For humans. Not read at run time and not in the results     |
| `runs`                               | Runs per arm. Default 3, cap 50. `--runs` overrides          |
| `max_turns`                          | Default 10, cap 200. An exhausted cap is a run error         |
| `timeout_seconds`                    | Default 300, cap 3600. The run is killed at the cap          |
| `model`                              | The agent's model. `--model` overrides it                    |
| `allowed_tools`                      | Tools the case wants. Read-only tools are granted. Any other tool also needs `eval.allow_tools` |
| `append_system_prompt`               | Appended to the agent's system prompt                        |
| `env`                                | Extra environment. Every key matches `EVAL_[A-Z0-9_]*`       |
| `schema_version`, `expected_outcome` | Accepted by the harness. Not used                            |

Any other key is an error, and `context.*` cannot be set from `prompt.md`. The harness also
accepts `artifact_publish` and `growthbook_overrides`, and the validator refuses both.

The harness refuses a case with an unknown `prompt.md` key at load, before any model call, and
then writes no result document for the whole suite. An unknown top-level key in `case.yaml` is
ignored.

The body is the prompt, sent as written. An `@path` mention in it is not expanded into a file.
A case that needs a file read grants a tool for it.

Each case file is at most 1 MiB. A case has at most 256 grader files.

## case.yaml

Optional. It carries only `context.*`, and needs `schema_version: "1.1"` and `name`. No other
top-level key is written there.

| Key                       | Is                                                                                                        |
| ------------------------- | --------------------------------------------------------------------------------------------------------- |
| `context.add_dirs`        | Directories the agent may read, read-only. Each entry stays inside its own case directory                 |
| `context.history_file`    | A `.jsonl` transcript to resume from. The prompt becomes the next user turn                               |
| `context.scaffold_script` | Runs on no backend. `--no-scaffold` is pinned on `--docker`, and nothing stages files into the VM on `--cowork`. Ship a fixture inside the case and grant it with `context.add_dirs` instead |

`context.add_dirs` refuses the eval directory, a sibling case, the plugin root, the case's own
`graders/` and the case's own `checks/`. Every other directory inside the case is granted, so
do not put there anything the agent must not read. A `.claude/skills` or `.claude/agents`
inside an added directory is not loaded.

When both files exist, `case.yaml` is the base and `prompt.md` frontmatter overrides it.

## Graders

One grader per file under `graders/`: frontmatter, then the rubric or pattern.

| Type          | Takes                                                                       | Class      |
| ------------- | --------------------------------------------------------------------------- | ---------- |
| `regex`       | `pattern`, `flags`, `match: contains \| not_contains \| count:N`, `target`  | structural |
| `tool_used`   | `tool`, `input_match`, `min` (default 1), `max` (default unlimited)         | structural |
| `tool_order`  | `before`, `after`                                                           | structural |
| `file_exists` | `path`, a glob over files the agent created, `exists` (default true)        | structural |
| `llm`         | `criteria`, `focus`. A judge model votes 2 of 3                             | judged     |
| `baseline`    | `baseline_file`, `criteria`                                                 | judged     |

Structural graders are deterministic. Judged graders call a model. A failure of either class
fails the run. Prefer a structural grader. Each type's fields and pass condition are
[plugin_eval.md](plugin_eval.md#grader-fields).

The keys every grader takes:

| Key      | Is                                                                                                  |
| -------- | --------------------------------------------------------------------------------------------------- |
| `type`   | Required. One of the six types                                                                      |
| `name`   | Defaults to the file name without `.md`. Names are unique within a case                             |
| `weight` | Above 0, default 1. Changes the harness summary, not pass or fail. There is no `weight: 0`: delete the grader, or use `arm` |
| `arm`    | `with-only` or `both`. Matters only under `--ablation with-without`. See [plugin_eval.md](plugin_eval.md#ablation-arms) |

An unknown key inside a grader is an error. A grader that throws fails.

Only two graders choose what they look at, and they use different keys: `regex` uses `target`,
`llm` uses `focus`. `tool_used` and `tool_order` always read the trace, `file_exists` always
reads the created file list, and `baseline` always compares against `baseline_file`. `target`
on an `llm` grader is ignored, and the grader judges `last_message`.

| Value of `target` or `focus` | Is                                                                                      |
| ---------------------------- | --------------------------------------------------------------------------------------- |
| `last_message`               | The final assistant text. The default                                                   |
| `trace`                      | The whole session as JSON lines. Not portable between backends                          |
| `files`                      | The paths of files the agent created, not their contents                                |
| `{source: file, path: P}`    | The contents of one workspace file after the run, at most 10 MiB, inside the workspace  |
| `mock_calls`                 | Calls to mocked MCP tools. A grader on it is skipped on `--cowork`, where the servers are real |

The skill fired:

```markdown
---
type: tool_used
tool: Skill
input_match: '"skill"\s*:\s*"(?:[\w-]+:)?<skill>"'
---
```

The answer is one paragraph:

```markdown
---
type: regex
target: last_message
pattern: '\n\s*\n'
match: not_contains
---
```

The skill must not fire:

```markdown
---
type: tool_used
tool: Skill
input_match: '"skill"\s*:\s*"(?:[\w-]+:)?<skill>"'
min: 0
max: 0
---
```

## MCP mocks

A plugin whose skills call MCP tools runs against mocks when a `mocks/` directory exists. Every
case under a `mocks/` carries `no-cowork`.

| Path                                  | Scope                                             |
| ------------------------------------- | ------------------------------------------------- |
| `evals/mocks/<server>/<tool>.md`      | Every case                                        |
| `<group>/mocks/<server>/<tool>.md`    | Every case under that grouping directory          |
| `<case>/mocks/<server>/<tool>.md`     | One case                                          |

The layers add up, and the innermost wins per tool. `<server>` is the server name in the
plugin's `.mcp.json`, or `plugin_<plugin>_<server>` when two plugins under test declare the
same name. When a mock exists the real server never starts, its mocked tools are allowed, and
every other tool on that server is denied. Directory and file names use letters, digits, `_`
and `-` only.

| Mock file                          | Does                                                                                                                       |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| No frontmatter                     | Returns the body as the tool result. `{{input.x}}` inserts an input field. `{{file:fixtures/{input.x}.json}}` inserts a file beside the mock |
| `error: true`                      | Returns the body as a tool error                                                                                           |
| `expect:`                          | Maps a dotted input path (`labels.0` indexes an array) to a type name, a `/regex/`, a literal, or a list of literals. A call that violates it aborts the run with score 0 |
| `type: agent`                      | The body instructs a small model that plays the server for the run. `abort_when:` lists the only conditions under which it may abort |
| `_server.md` with `tools: [...]`   | One agent plays several tools. Put an `expect:` on the tool's own `<tool>.md`                                               |
| `_tools.json`                      | A saved `tools/list` response, for real descriptions and schemas                                                           |

The `expect:` regex dialect has literals, `.`, escapes, character classes, `* + ? {m,n}` on a
single atom, `^`, `$`, and the `i` and `s` flags. It has no groups, alternation, backreferences
or lookaround. Use a list of literals for alternatives.

An agent mock cannot serve a tool whose output a plugin `PostToolUse` hook rewrites. Use a
fixed mock for that tool.

Each live agent answer is saved under the results directory as
`mock-recordings/<server>/<tool>-<key>.json`. A recording copied into `.replay/<server>/`
beside the `mocks/` that defines the responder answers that exact call with no model call.
Editing the mock or a fixture it includes invalidates its recordings. Commit `.replay/` with
the suite.

## checks/

Optional. Each file holds assertions written as Python, run on the host after the run is
graded, on either backend. How to write one is [checks.md](checks.md). This section is the part
of it that binds a case file.

| Fact                                                | Is                                                     |
| --------------------------------------------------- | ------------------------------------------------------ |
| A check's name                                      | `<file stem>.<function name>`                          |
| A check's weight                                    | 1                                                      |
| The result                                          | a grader result of `type: check`, in the same document |
| A failed check                                      | fails the run, as a failed structural grader does      |
| A file under `checks/` carrying no `@check`         | a helper, and no violation                             |
| A `checks/` directory carrying no `@check` at all   | a violation                                            |

A check file is host code. It is the one thing under the eval path that is not code under
test, so the session's wheel set does not bind it. Its imports are the consumer's own
dependencies. See [checks.md](checks.md#where-a-check-runs-and-what-it-may-import).

## What the validator enforces

`cowork_evals run` validates every selected plugin root before it runs anything, and imports
every `checks/*.py`. A violation exits 3. It validates the whole root and not only the target,
so a malformed sibling case blocks a single-case run. It cannot be skipped. See
[cli.md](cli.md).

| Rule                                                                                         |
| -------------------------------------------------------------------------------------------- |
| A directory directly under `evals/` is `plugin`, `mocks`, or a directory under `<plugin>/skills/` |
| `name`, `tags` and `plugins` are present in `prompt.md`                                      |
| `tags` names the case's own `<skill>` directory                                              |
| `plugins` resolves, from the case directory, to the plugin root                              |
| Every `prompt.md` frontmatter key is in the table above                                      |
| `runs` is at most 50, `max_turns` at most 200, `timeout_seconds` at most 3600                |
| Every `env` key starts with `EVAL_`                                                          |
| `case.yaml` carries `schema_version: "1.1"` and `name`, and no key outside `context.*`        |
| Every `context.add_dirs` entry resolves inside its own case directory                        |
| No `context.add_dirs` entry resolves under the case's own `checks/`                          |
| Every grader has a listed `type` and a `weight` above 0                                      |
| Every file under `graders/` carries a `---` block                                            |
| Every file under `checks/` imports                                                           |
| A `checks/` directory carries at least one `@check` function                                 |
| No two checks of one case share a name                                                       |
| A case a CoWork session cannot run carries `no-cowork`                                       |
| A case carrying `no-cowork` is one a CoWork session cannot run                               |

## Authoring traps

Each of these fails silently, and each is fixed by editing the case. The traps a case cannot
fix are [plugin_eval.md](plugin_eval.md#limits-a-case-cannot-fix).

- **A grader file needs `---` frontmatter delimiters.** Without them it is a note and is
  ignored, so the case runs with fewer graders than it appears to have.
- **A prompt that names the skill it is testing measures the name.** A CoWork session that
  does not have the skill refuses the name and produces nothing. Ask for the outcome the
  skill exists to produce.
- **`min: 0, max: 0` is how a must-not-call assertion is written.** `max: 0` alone never
  passes, because `min` stays 1.
- **`file_exists` sees only files created during the run.** A file the agent modified is
  invisible to it. Grade the contents, or assert a `tool_used` on `Edit`.
- **`llm` graders refuse binaries.** A `.pptx` is a ZIP. Render it to an image, or write text.
  An image file is shown to the judge as an image, except on `--cowork`, where an image focus
  is a grader skip.
- **`context.add_dirs` must stay inside the case directory.** Naming the eval directory, a
  sibling case, the plugin root, the case's own `graders/` or its own `checks/` refuses the
  run. Every other directory inside the case is granted, so a directory holding anything the
  agent under test must not read does not belong in the case.
- **`target: trace` is not portable between backends.** Each renders the transcript its own
  way, so a `regex` over it can pass on one and fail on the other. Every other target reads
  the same on both.
- **A `target` on an `llm` grader is ignored.** That key is `focus`, and the grader judges
  `last_message` while it appears to judge a file.
- **A case carrying `checks/` and no grader does not load.** The harness refuses a case with
  no grader, so `checks/` adds to a case's `graders/` and never replaces it.
- **`--no-keep-traces` disables every check.** A check reads the collected run. With nothing
  collected each check is a skip, and a skip fails the run.
- **A `checks/` file with no `@check` asserts nothing.** It is treated as a helper, and only a
  `checks/` directory with no check in any file is reported.
- **Each run of a case runs every check again.** A case at `runs: 3` carrying one judged check
  makes each of its judge calls three times.
