---
name: cowork-evals
description: Write and run evals for Claude CoWork skills and plugins with the cowork_evals command, and run a plugin's own pytest suite on the CoWork runtime. TRIGGER when writing or fixing an eval case, a prompt.md or a grader under an evals/ directory, when a cowork_evals command fails, when configuring cowork_evals.yaml, or when writing plugin code that has to run inside a CoWork session.
---

# cowork_evals

`cowork_evals` runs evals against Claude CoWork skills and plugins, and runs a plugin's own
Python tests on the CoWork runtime. It is installed as a Python package. Evals are written in
this repository, not in the package.

Run `cowork_evals docs` first. It prints the directory holding the shipped documentation and
every document name. `cowork_evals docs <name>` prints one absolute path, and reading that
file is the authority for anything below.

| Question                                | Read                     |
| --------------------------------------- | ------------------------ |
| How to write a case, field by field     | `docs eval_format`       |
| Every verb, option and exit code        | `docs cli`               |
| Which backend proves what, and its cost | `docs approaches`        |
| The gate, the logs, what a run costs    | `docs running_evals`     |
| The runtime a plugin's code gets        | `docs runtime`           |
| `test`, and the runtime a suite gets    | `docs cowork_test`       |
| Every grader field the format is silent on | `docs claude_code/plugin_eval_reference` |

## The command

```bash
cowork_evals check --all                       # what each backend still needs
cowork_evals setup --docker                    # build the images, and log in once
cowork_evals run  --docker <path>              # an eval: a model, graders, a gate
cowork_evals test --docker <path>/tests        # pytest on the CoWork runtime, no model
cowork_evals docs [<name>]                     # where the documentation is
cowork_evals init                              # write the config, this skill, and a CLAUDE.md block
cowork_evals prune --docker                    # delete what setup built
```

`--docker` runs Claude Code in a container that reproduces the CoWork image. `--cowork` drives
the real desktop application, needs macOS and a configured profile, and takes the keyboard for
the length of the run. Prefer `--docker` for iteration.

The path is the scope: a case directory runs that case, `evals/<skill>/` runs that skill,
`evals/` runs the plugin, and a directory holding several plugins runs each in turn.
`--dry-run` prints what would run and spends nothing.

## The tree

```
<plugin>/.claude-plugin/plugin.json       # what makes <plugin> a plugin root
<plugin>/skills/<skill>/SKILL.md
<plugin>/evals/<skill>/<case>/prompt.md
<plugin>/evals/<skill>/<case>/graders/<name>.md
<plugin>/evals/<skill>/<case>/case.yaml   # optional, context.* only
<plugin>/evals/plugin/<case>/             # a case that crosses skills
<plugin>/evals/mocks/<server>/<tool>.md   # shared MCP stand-ins
```

A directory directly under `evals/` is a skill name, `plugin`, or `mocks`. Nothing else. The
validator enforces it in both directions.

Fixtures live inside the case that uses them.

## prompt.md

Frontmatter, then the prompt the agent receives.

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

`tags` and `plugins` are both required and both checked.

- `tags` names the case's own directory. `--tag` is the only reliable per-skill selector.
  `--case` globs the case name, which is the `name` key when the case writes one.
- `plugins` counts up to the plugin root. From `evals/<skill>/<case>/` that is `../../..`,
  and the count is the same whatever the plugin is called.

| Key                                                     | Is                                                    |
| ------------------------------------------------------- | ----------------------------------------------------- |
| `name`                                                  | Required                                              |
| `description`                                           | For humans. Not read at run time                      |
| `tags`, `plugins`                                       | Required, above                                       |
| `runs`, `max_turns`, `timeout_seconds`                  | Defaults 3, 10, 300. Caps 50, 200, 3600               |
| `model`, `allowed_tools`, `append_system_prompt`, `env` | Execution. Every `env` key starts with `EVAL_`        |

Any other key is an error. `context.*` goes in `case.yaml`, which needs
`schema_version: "1.1"` and `name`.

## Graders

One grader per file under `graders/`, frontmatter then the rubric or pattern. Structural
graders are deterministic and decide the exit code. Judged graders call a model and are
printed. Prefer a structural one.

| Type          | Takes                                                                     | Class      |
| ------------- | ------------------------------------------------------------------------- | ---------- |
| `regex`       | `pattern`, `flags`, `match: contains \| not_contains \| count:N`, `target` | structural |
| `tool_used`   | `tool`, `input_match`, `min` (default 1), `max` (default unlimited)       | structural |
| `tool_order`  | `before`, `after`                                                         | structural |
| `file_exists` | `path` as a glob over created files, `exists` (default true)              | structural |
| `llm`         | `criteria`, `focus`. A judge model votes 2 of 3                           | judged     |
| `baseline`    | `baseline_file`, `criteria`                                               | judged     |

Only `regex` and `llm` choose what they look at, and the keys differ: `regex` uses `target`,
`llm` uses `focus`. Values are `last_message` (default), `trace`, `files`,
`{source: file, path}`, `mock_calls`.

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

## Traps

Each has a silent failure mode.

- A grader file without `---` delimiters is read as a note and ignored. The case then runs
  with fewer graders than it appears to have.
- `max: 0` alone can never pass, because `min` stays 1. A must-not-call assertion is
  `min: 0, max: 0`.
- `file_exists` sees only files created during the run. Not scaffold output, and not files
  that were modified.
- `target` on an `llm` grader is ignored. That key is `focus`, and the grader judges
  `last_message` while looking as if it judges a file.
- `llm` graders refuse binaries. A `.pptx` is a ZIP. Render to an image, or write text.
- `context.add_dirs` refuses any entry outside its own case directory, the eval directory,
  a sibling case, the plugin root and the case's own `graders/` included.
- Scaffolds run in an empty working directory, with no credentials and a 2-minute cap.
  Reference resources as `$(dirname "$0")/...`.

## The exit codes

| Exit | Means                                                            |
| ---- | ---------------------------------------------------------------- |
| 0    | the gate passed                                                  |
| 1    | a structural grader failed, or a case or grader was skipped      |
| 2    | usage error                                                      |
| 3    | the preflight failed. Nothing ran, and the message names the fix |

`run` validates every selected plugin root before it runs anything, so a malformed sibling
case blocks a single-case run. There is no option to skip validation.

`test` is the exception: it returns pytest's exit code unchanged.

## Reading a failure

Every run leaves its transcript on the host, on either backend and passing runs included, so
a failure is investigated without running the suite again, against a run that passed and
against the same case on the other backend. A failing line names the directory:

```
FAIL smoke/one-paragraph: run 2: is-one-paragraph: the regex grader failed: pattern not found
  in last_message [artifacts: logs/evals/<stamp>-smoke/smoke/traces/one-paragraph/run-2]
```

| In that directory  | Is                                                                   |
| ------------------ | -------------------------------------------------------------------- |
| `last_message.txt` | The final assistant message, which is what a `last_message` grader read |
| `trace.jsonl`      | Every turn and every tool call, one JSON object per line              |
| `workspace/`       | The agent's working directory                                         |

The three names are the same on `--docker` and `--cowork`. `trace.jsonl` is whatever format
the backend that produced it wrote, and the two are close but not identical: a harness trace
ends in a `result` record and a CoWork one does not. `cowork_evals docs running_evals` has the
table, and it names the document that owns each format. `--no-keep-traces` turns it off, and
`eval.keep_traces: false` does the same from the file.

## The runtime under test

A CoWork session is Python 3.10 with a fixed wheel set. Every file under the path passed to
`cowork_evals run`, meaning each skill, command, agent and hook, imports only what that image
carries. Read `cowork_evals docs runtime` before adding an import to plugin code.

A plugin's own pytest suite is the other half, and it is not an eval:

```bash
cowork_evals test --docker <plugin>/tests
cowork_evals test --docker <plugin>/tests -- -k parser -x
```

Every token after `--` reaches pytest in order and unmodified. It runs the suite inside the
CoWork image with no model, no case tree, no grader and no gate. That is what says a plugin's
Python behaves in a session, which a suite passing on a newer local Python does not.

## Configuration

`cowork_evals.yaml` in the working directory holds every setting: the driver's, each
backend's, the models, the tool grants, the ceilings. Nothing is read from the process
environment, and there is no `.env`. A command-line option beats the file, and the file beats
the built-in default.

`cowork_evals init` writes the file with every key and every default. Only the CoWork backend
requires it: `cowork.profile` is the one key with no default. The file names a profile, which
is an identifier, so it is not committed.
