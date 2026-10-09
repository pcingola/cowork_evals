---
name: cowork-evals
description: "Writes and runs CoWork plugin evals, and runs a plugin's pytest suite on the CoWork runtime. TRIGGER when: writing or fixing an eval case, grader, check or plugin test, configuring cowork_evals.yaml, or running cowork_evals. NOT for skill authoring."
---

# cowork_evals

`cowork_evals` runs evals of CoWork skills and plugins, and runs a plugin's own pytest suite on
the CoWork runtime. It is an installed Python package. Evals live in this repository, not in
the package.

`cowork_evals docs` prints the documentation directory and every document name.
`cowork_evals docs <name>` prints the path of one document. That document is the authority for
everything below.

| Question                                               | Read                                      |
| ------------------------------------------------------ | ----------------------------------------- |
| Which cases to write, and which assertion answers what | `docs eval_design`                        |
| How to write a case, field by field                    | `docs eval_format`                        |
| Every verb, option and exit code                       | `docs cli`                                |
| Which backend proves what, and its cost                | `docs approaches`                         |
| Pass and fail, the logs, what a run costs              | `docs running_evals`                      |
| The runtime a plugin's code gets                       | `docs runtime`                            |
| `test`, and the runtime a suite gets                   | `docs cowork_test`                        |
| An assertion no grader type can express                | `docs checks`                             |
| Every grader field the format is silent on             | `docs claude_code/plugin_eval_reference`  |
| What `panel` shows, and the records behind it          | `docs panel`                              |

## Workflow

1. `cowork_evals check --all`, then `setup --docker` and `login --docker` for what it reports
   missing.
2. Write the case: the tree, `prompt.md` and one file per grader, below. Add `checks/` for an
   assertion no grader type can express.
3. `cowork_evals run --docker <case> --dry-run`. It validates the tree and spends nothing.
4. `cowork_evals run --docker <case>`. On a failure, read the kept run, below.
5. Run the skill's directory, then the plugin's `evals/`.
6. `--ablation with-without` to show the plugin makes a difference.
7. `cowork_evals run --cowork <path>` against the real application.
8. `cowork_evals panel <path>` to find a case that never ran on a backend.

## The command

```bash
cowork_evals check --all                       # what each backend still needs
cowork_evals setup --docker                    # build the images
cowork_evals login --docker                    # log in once, in a container
cowork_evals run  --docker <path>              # an eval: a model, graders, a verdict
cowork_evals test --docker <path>/tests        # pytest on the CoWork runtime, no model
cowork_evals ask  --cowork "<prompt>"          # one prompt to a live session, and its answer
cowork_evals panel <path>                      # every case, and what each backend last said
cowork_evals docs [<name>]                     # where the documentation is
cowork_evals init                              # write the config, the skills, and a CLAUDE.md block
cowork_evals prune --docker                    # delete what setup built
```

`--docker` runs Claude Code in a container that reproduces the CoWork image. Use it to iterate.
`--cowork` drives the real desktop application. It needs macOS and a configured profile, and it
takes the keyboard for the length of the run. A modal asks for the keyboard once per
invocation, before the first plugin. `--dry-run` prints what would run, spends nothing, and
shows no modal.

The path sets the scope. A case directory runs that case, `evals/<skill>/` runs that skill,
`evals/` runs the plugin, and a directory holding several plugins runs each in turn.

`panel` takes the same path and spends nothing. It prints one row per case from the records
earlier runs left: the latest outcome on each backend, its age, and whether the case files
changed since. A case that never ran says so, which shows a gap in coverage without running
anything.

`ask` is not an eval. The `cowork-ask` skill covers it.

## The tree

```
<plugin>/.claude-plugin/plugin.json       # what makes <plugin> a plugin root
<plugin>/skills/<skill>/SKILL.md
<plugin>/evals/<skill>/<case>/prompt.md
<plugin>/evals/<skill>/<case>/graders/<name>.md
<plugin>/evals/<skill>/<case>/checks/<name>.py  # optional, assertions as Python
<plugin>/evals/<skill>/<case>/case.yaml   # optional, context.* only
<plugin>/evals/plugin/<case>/             # a case that crosses skills
<plugin>/evals/mocks/<server>/<tool>.md   # MCP tool mocks shared by every case
```

A directory directly under `evals/` is a skill name, `plugin` or `mocks`, and nothing else. The
validator enforces this in both directions. Fixtures live inside the case that uses them.

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

| Key                                                     | Is                                                    |
| ------------------------------------------------------- | ----------------------------------------------------- |
| `name`                                                  | Required                                              |
| `tags`                                                  | Required. Names the case's own directory              |
| `plugins`                                               | Required. The relative path up to the plugin root     |
| `description`                                           | For humans. Not read at run time                      |
| `runs`, `max_turns`, `timeout_seconds`                  | Defaults 3, 10, 300. Caps 50, 200, 3600               |
| `model`, `allowed_tools`, `append_system_prompt`, `env` | Execution. Every `env` key starts with `EVAL_`        |

Any other key is an error. `context.*` goes in `case.yaml`, which needs
`schema_version: "1.1"` and `name`.

`--tag` is the only reliable per-skill selector. `--case` globs the case name, which is the
`name` key when the case writes one. From `evals/<skill>/<case>/`, `plugins` is `../../..`
whatever the plugin is called.

## The no-cowork tag

`no-cowork` is the one reserved tag. A case carrying it is not submitted on `--cowork`, and is
counted, not failed. On `--docker` it is an ordinary tag, and `--tag <skill>` still selects the
case.

A case carries it if and only if it writes `max_turns`, `model`, `allowed_tools`,
`append_system_prompt` or `env`, writes any `context.*` key in `case.yaml`, or sits under a
`mocks/` directory, including a suite-wide `evals/mocks/` several levels above it. The
validator exits 3 on a case that needs the tag and lacks it, and on a case that carries it and
needs nothing. There is no `skip:` field, and the tag is not one.

## Graders

One grader per file under `graders/`: frontmatter, then the rubric or pattern. Structural
graders are deterministic. Judged graders call a model. Both decide the exit code. Prefer a
structural one.

| Type          | Takes                                                                     | Class      |
| ------------- | ------------------------------------------------------------------------- | ---------- |
| `regex`       | `pattern`, `flags`, `match: contains \| not_contains \| count:N`, `target` | structural |
| `tool_used`   | `tool`, `input_match`, `min` (default 1), `max` (default unlimited)       | structural |
| `tool_order`  | `before`, `after`                                                         | structural |
| `file_exists` | `path` as a glob over created files, `exists` (default true)              | structural |
| `llm`         | `criteria`, `focus`. A judge model votes 2 of 3                           | judged     |
| `baseline`    | `baseline_file`, `criteria`                                               | judged     |

Only `regex` and `llm` choose their input: `regex` with `target`, `llm` with `focus`. The values
are `last_message` (default), `trace`, `files`, `{source: file, path}` and `mock_calls`.

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

## Checks

A check is your own Python in the case's `checks/` directory. It asserts what no grader type
can, such as the contents of a file the run wrote. It runs on the host after the run is
graded, on either backend. Its verdict is a grader result, so a failed check fails the run.

```python
# evals/<skill>/<case>/checks/assertions.py
import openpyxl

from cowork_evals.checks import Result, Run, check


@check
def totals_add_up(run: Run) -> None:
    book = openpyxl.load_workbook(run.file("totals.xlsx"))
    assert book.active["D10"].value == 4200
```

`run.judge` sends files to a model, so a PDF, an image or a spreadsheet can be judged:

```python
@check
def the_deck_is_readable(run: Run) -> Result:
    subprocess.run(["soffice", "--convert-to", "png", run.file("deck.pptx")], cwd=run.scratch)
    return run.judge("Every slide carries a title, and no text is clipped.", run.scratch)
```

`None` or `True` passes, `False` fails, a `Result` decides, and an exception fails the check
with its message. The check's name is `<file stem>.<function name>`. `run` carries
`workspace`, `last_message`, `trace`, `case_dir`, `run_dir`, `scratch` and `index`, plus
`file(name)` and `judge(prompt, *paths)`. Write into `run.scratch`, never into `run.workspace`.

A check runs on the host, not in the session, so it imports what your own repository declares.
`cowork_evals docs checks` has the rest.

## Traps

Each one fails silently.

- A grader file without `---` delimiters is a note and is ignored. The case runs with fewer
  graders than it appears to have.
- A prompt that names the skill under test measures the name. A CoWork session without the
  skill refuses the name and produces nothing. Ask for the outcome instead.
- `max: 0` alone never passes, because `min` stays 1. A must-not-call assertion is
  `min: 0, max: 0`.
- `file_exists` sees only files created during the run, not files the agent modified. Grade
  the contents, or assert a `tool_used` on `Edit`.
- `target` on an `llm` grader is ignored. The key is `focus`, and the grader judges
  `last_message` while it appears to judge a file.
- `llm` graders refuse binaries. A `.pptx` is a ZIP. Render it to an image, or write text.
- `context.add_dirs` refuses every entry outside its own case directory: the eval directory, a
  sibling case, the plugin root and the case's own `graders/`.
- `target: trace` is not portable. Each backend renders the transcript its own way, so a
  `regex` over it can pass on one and fail on the other.
- A case with `checks/` and no grader does not load. The harness refuses a case with no
  grader, so `checks/` adds to `graders/` and never replaces it.
- `--no-keep-traces` disables every check, because a check reads the collected run. Each
  check is then a skip, and a skip fails the run.
- A file under `checks/` with no `@check` asserts nothing. It is treated as a helper, and only
  a `checks/` directory with no check in any file is reported.
- Every run of a case runs every check again. At `runs: 3`, one judged check makes each of its
  judge calls three times.

## The exit codes

| Exit | Means                                                                                                                                  |
| ---- | -------------------------------------------------------------------------------------------------------------------------------------- |
| 0    | the run passed                                                                                                                         |
| 1    | a grader or a check failed, a case or grader was skipped, a run never had a tool it was granted, or a case's delta was below the threshold |
| 2    | usage error                                                                                                                            |
| 3    | the preflight failed. Nothing ran, and the message names the fix                                                                       |

`run` validates every selected plugin root and imports every `checks/*.py` before it runs
anything. A malformed sibling case therefore blocks a single-case run, and a check file that
does not import exits 3 before anything is spent. Validation cannot be skipped.

`test` returns pytest's exit code unchanged.

## Ablation

A passing suite does not show that the plugin did anything: a model asked for a spreadsheet
builds one whether or not a spreadsheet plugin is loaded.

```bash
cowork_evals run --docker <path> --ablation with-without
cowork_evals run --docker <path> --ablation with-without --delta-threshold 0.2
```

Every case runs twice, with the plugin and with nothing loaded, and is decided on the delta
between the two scores. A case below `--delta-threshold` fails, and so does a case the two arms
cannot be compared on. Ablation doubles the cost, is off by default, and runs on `--docker`
only, because a CoWork session takes its skills from the application's profile.
`eval.ablation` and `eval.delta_threshold` set both in the file.

Under ablation a `tool_used: Skill` grader is not scored in either arm and is reported as an
indicator. The one-arm run is what shows the skill fired. `cowork_evals docs running_evals` has
what ablation changes about pass and fail.

## Reading a failure

Every run leaves its transcript on the host, on both backends, passing runs included. Compare a
failure against a passing run, or against the same case on the other backend, without running
the suite again. The failing line names the directory:

```
FAIL smoke/one-paragraph: run 2: is-one-paragraph: the regex grader failed: pattern not found
  in last_message [artifacts: logs/evals/<stamp>-smoke/smoke/traces/one-paragraph/run-2]
```

| In that directory  | Is                                                                       |
| ------------------ | ------------------------------------------------------------------------ |
| `last_message.txt` | The final assistant message, which a `last_message` grader reads         |
| `trace.jsonl`      | Every turn and every tool call, one JSON object per line                 |
| `workspace/`       | The agent's working directory                                            |
| `scratch/`         | What a check wrote, where the case has checks                            |
| `checks.jsonl`     | One line per check: the verdict, the traceback, the whole judge exchange |

`last_message.txt`, `trace.jsonl` and `workspace/` have the same names on both backends.
`trace.jsonl` is in the format of the backend that wrote it. The two formats are close: a
harness trace ends in a `result` record and a CoWork trace does not.
`cowork_evals docs running_evals` names the document that owns each format.

`--no-keep-traces`, or `eval.keep_traces: false`, keeps nothing. It also disables the two
conditions that read the kept trace and fail a run: a tool refused by the permission mode, and
a granted tool the run was never offered.

## The runtime under test

A CoWork session is Python 3.10 with a fixed wheel set. Each skill, command, agent and hook
under the path passed to `cowork_evals run` imports only what that image carries. It reads only
the environment variables `cowork_evals docs runtime` lists. Every other name is empty in a
session, and a Docker run gives each `Bash` call the same set, so a skill that reads another
name fails on both backends. Read `cowork_evals docs runtime` before adding an import.

A plugin's own pytest suite is not an eval:

```bash
cowork_evals test --docker <plugin>/tests
cowork_evals test --docker <plugin>/tests -- -k parser -x
```

`test` runs the suite inside the CoWork image with no model, case tree, grader or verdict. It
shows whether the plugin's Python behaves in a session, which a pass on a newer local Python
does not. Every token after `--` reaches pytest in order and unchanged.

## Configuration

`cowork_evals.yaml` in the working directory holds every setting: the driver's, each backend's,
the models, the tool grants and the ceilings. The only values read from the process environment
are the variables `docker.env_passthrough` names. They are forwarded into the run container, for
a skill that reads a credential from one. There is no `.env`. A command-line option beats the file, and the file beats
the built-in default.

`cowork_evals init` writes the file with every key and its default. Only the CoWork backend
needs the file: `cowork.profile` is the one key with no default. The profile is an identifier,
so the file is not committed.
