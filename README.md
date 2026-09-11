# CoWork Evals

Run evals for Claude CoWork skills and plugins, and run a plugin's own Python tests on the
CoWork runtime.

## Summary

Four problems stand between a CoWork skill and a test suite. This is what this package does
about each.

| Problem                                                                                   | How this solves it                                                                        |
| ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| CoWork has no scriptable entry point, so a skill can only be exercised by a person clicking | Two backends execute a case from the command line: Claude Code inside a container that reproduces the CoWork image, and the real desktop application driven directly |
| A container is not the product, and the product cannot be run on every commit             | Both. Docker is the iteration loop and the pre-release gate. CoWork is the confirmation on the real stack, run by a person on purpose, and never a commit gate |
| Two backends would mean two eval formats and two sets of results                          | One format, `claude plugin eval`'s own. The same case tree runs on both, both write the same result document, and one gate reads it |
| A CoWork session is Python 3.10 with a fixed wheel set, so a plugin's tests passing on a laptop prove nothing about the session | `cowork_evals test` runs the plugin's own pytest suite inside that runtime, with no model in the loop |

A case asserts what a unit test cannot reach: the answer text, which tools ran and in what
order, which files the agent created, and a rubric a judge model votes on. The four structural
graders are deterministic and carry the gate. The two judged ones are printed.

The CoWork backend honours a subset of the format, because it drives a live session rather
than the harness. [`docs/approaches.md`](docs/approaches.md) says which subset, what each
backend proves, and what each costs to run.

Evals are not written here. This is a library, installed by the repository that owns the
plugins under test. That repository writes the cases and the tests, and points this one at
them.

## Install

Python 3.10 or later. The package is not on PyPI yet, so it installs from this repository.

```bash
uv add --dev "cowork-evals @ git+https://github.com/pcingola/cowork_evals"
```

```bash
pip install "cowork-evals @ git+https://github.com/pcingola/cowork_evals"
```

```bash
uv tool install "cowork-evals @ git+https://github.com/pcingola/cowork_evals"
```

The last line installs the command on its own, outside any project.

Those three track the default branch. Appending `@<reference>`, a tag, a branch or a commit,
pins instead. Pin in a repository that gates CI on evals: `run` decides pass and fail, so a
change to the gate or the skip rules moves that verdict without the consumer's cases changing.
`cowork_evals --version` prints what is installed, and every run records it in `env.txt`.

The distribution is `cowork-evals`. The command it installs is `cowork_evals`.

Then, in the repository that owns the plugins:

```bash
cowork_evals init    # cowork_evals.yaml, the eval-authoring skill, and a CLAUDE.md block
cowork_evals docs    # where the documentation went, and every document name
```

`init` overwrites nothing. It reports every target it kept.

That means upgrading this package does not refresh what `init` already wrote. The skill is
the one where that matters, because it carries the case format and a stale copy teaches an
out-of-date one. After an upgrade, delete it and run `init` again:

```bash
rm .claude/skills/cowork-evals/SKILL.md && cowork_evals init
```

## What you need

| Backend                    | You need                                                       |
| -------------------------- | ---------------------------------------------------------------- |
| The container, `--docker`  | Docker or Rancher Desktop running, the images, and one credential route. `setup --docker` makes all three |
| CoWork, `--cowork`         | macOS, `claude` on `PATH`, CoWork signed in, the profile named in `cowork_evals.yaml`, and the macOS Accessibility grant |

`cowork_evals check --all` reports what each backend is still missing, and names the command
that supplies it.

The container takes one of two credential routes, and `docker.auth_env` in
`cowork_evals.yaml` is what picks it.

| `docker.auth_env`  | The route is                                                | Needs a browser |
| ------------------ | ----------------------------------------------------------- | --------------- |
| empty, the default | a login this package owns, made once by `setup --docker`    | yes, once       |
| naming variables   | those variables, forwarded into the container by name        | no              |

The second route is how a run reaches Bedrock, Vertex, Foundry or a gateway, and it is what
makes the container backend unattended end to end:

```yaml
docker:
  auth_env: [CLAUDE_CODE_USE_BEDROCK, AWS_BEARER_TOKEN_BEDROCK, ANTHROPIC_BEDROCK_BASE_URL, AWS_REGION]
```

Only the names go in the file. Each is emitted as `--env <NAME>` with no value, so Docker
takes the value from the `cowork_evals` process's own environment and no credential reaches an
argument list, a `--dry-run` listing, `run.log` or `docker inspect`. On that route the login is
neither required nor mounted, `setup --docker` makes none, and `check --docker` does not report
one. Both routes are [`docs/docker.md`](docs/docker.md).

A CoWork run also takes the keyboard. Each case activates the application and sends Return to
the frontmost window, so the machine is not yours while a suite runs, and there is no headless
route and no CI. A container run costs none of that, and runs the code in your checkout rather
than the code deployed to the account. The whole comparison is
[`docs/approaches.md`](docs/approaches.md).

## Quickstart

Three parts: install the package and build a backend, write and run an eval, and run a
plugin's own pytest suite on the CoWork runtime.

Everything below is the container backend on its default credential route, which needs no
setting in `cowork_evals.yaml`: every key has a built-in default, only the CoWork backend
requires one, and `docker.auth_env` above is the one a Bedrock, Vertex, Foundry or gateway
credential needs. `init` is still the first step, because it also installs the eval-authoring
skill and the `CLAUDE.md` block that tell a Claude Code session in your repository how any of
this works. Every name is the example's own. The plugin is `notes`, it sits at `plugins/notes`,
and it has one skill, `summarize`. Substitute yours throughout.

### 1. Install

Install the package as above, then build the container backend:

```bash
cowork_evals init             # the config, the skill, and the CLAUDE.md block
cowork_evals setup --docker   # two images, and one interactive login. Minutes, and once only
cowork_evals check --docker   # exits 0 when the backend is ready
```

With `docker.auth_env` set, `setup --docker` builds the two images and makes no login, so it
needs no terminal and no browser.

### 2. Evals

A case is a directory:

```
plugins/notes/.claude-plugin/plugin.json
plugins/notes/skills/summarize/SKILL.md
plugins/notes/evals/summarize/one-paragraph/prompt.md
plugins/notes/evals/summarize/one-paragraph/graders/skill-fired.md
plugins/notes/evals/summarize/one-paragraph/graders/one-paragraph.md
```

The layer under `evals/` is a skill directory name, `plugin` for a case that crosses skills,
or `mocks`. Nothing else.

`prompt.md` is frontmatter, then the prompt the agent receives:

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

`tags` names the case's own directory, so it is `summarize` here. `plugins` counts up to the
plugin root, three levels from a case at this depth, and that count is the same for every case
whatever the plugin is called. Both keys are required and both are checked.

A grader is one file under `graders/`. This one asserts the skill fired:

```markdown
---
type: tool_used
tool: Skill
input_match: '"skill"\s*:\s*"(?:[\w-]+:)?summarize"'
---
```

This one asserts the shape of the answer:

```markdown
---
type: regex
target: last_message
pattern: '\n\s*\n'
match: not_contains
---
```

Both are structural, so both decide the exit code. A grader file without the `---` delimiters
is read as a note and is silently ignored.

Run it:

```bash
cowork_evals run --docker plugins/notes/evals/summarize/one-paragraph
```

The path is the scope. It selects a case, a skill's cases at `evals/summarize/`, a plugin's
whole suite at `evals/`, or every plugin under a directory holding several. `--dry-run` prints
the command line and spends nothing.

The exit code is the gate's:

| Exit | Means                                                            |
| ---- | ---------------------------------------------------------------- |
| 0    | the gate passed                                                  |
| 1    | a structural grader failed, or a case or grader was skipped      |
| 2    | usage error                                                      |
| 3    | the preflight failed. Nothing ran, and the message names the fix |

The invocation keeps everything it printed, and every run's transcript with it:

```
logs/evals/latest/
  gate.txt                       # one line per finding, each carrying FAIL or NOTE
  run.log                        # everything the invocation printed
  notes/report.html              # the harness's own report
  notes/aggregate-result.json    # what the gate read
  notes/traces/<case>/run-<n>/   # trace.jsonl, last_message.txt and the agent's workspace
```

Every run of either backend leaves those three, under the same names, whether it passed or
failed. A failing run is read against a passing one, and a `--docker` run against a `--cowork`
one. A failing line names the directory holding the run behind it, so a failure is read
without running the suite again. `--no-keep-traces` turns that off.

Then widen it:

| To                                     | Add                                                                 |
| -------------------------------------- | ------------------------------------------------------------------- |
| Run the plugin's whole suite           | point at `plugins/notes/evals`                                      |
| Select one skill across a sweep        | `--tag summarize`                                                   |
| Give the agent more than `Bash`        | `--allow-tools`, which replaces the grant and so names `Bash` again |
| Run the same cases on the real product | `--cowork`, after `cowork.profile` is set in `cowork_evals.yaml`    |

### 3. Tests

`cowork_evals test` is the other half, and it is not an eval. It runs the plugin's own pytest
suite inside the CoWork image: Python 3.10, the image wheel set, no model, no case tree, no
grader and no gate. That is what says a plugin's Python behaves in a session, which a suite
passing against a laptop's own wheels does not.

```bash
cowork_evals test --docker plugins/notes/tests
cowork_evals test --docker plugins/notes/tests -- -k parser -x
```

Every token after `--` reaches pytest in order and unmodified, and the command returns
pytest's exit code unchanged. The path is one plugin root's; a path covering several is a
usage error, because pytest takes one rootdir. It writes no run directory and reads no
`evals/`, so a malformed case never blocks a test run.

The format, field by field, is [`docs/eval_format.md`](docs/eval_format.md). Every option and
every exit code is [`docs/cli.md`](docs/cli.md). What the gate reads, and what a run costs, is
[`docs/running_evals.md`](docs/running_evals.md). The runtime your pytest suite gets is
[`docs/cowork_test.md`](docs/cowork_test.md). Which backend to reach for, and what each one
costs to run, is [`docs/approaches.md`](docs/approaches.md).

## The command

```bash
cowork_evals init                    # the config, the skill, and the CLAUDE.md block
cowork_evals setup --docker          # build the container images, and log in once if the route needs it
cowork_evals check --all             # what each backend still needs, one line per backend
cowork_evals run  --docker path/to/plugin          # an eval: a model, graders, a gate
cowork_evals test --docker path/to/plugin/tests    # pytest on the CoWork runtime, no model
cowork_evals docs [name]             # where the documentation is, or one document's path
cowork_evals prune --docker          # delete what setup built
```

`run` grades what a model produced and exits non-zero when the gate fails. `test` runs no model,
runs your own pytest suite inside the CoWork runtime, and returns pytest's exit code unchanged.

Every option has a default in `cowork_evals.yaml`, in the working directory. That file is the
only configuration route: nothing is read from the process environment, and there is no `.env`.
`cowork_evals init` writes it with every key and every default. Runs write to `logs/` under the
working directory.

`docker.auth_env` holds variable names and no value, so the setting still comes from the file.
The credential itself is a value rather than a setting, and Docker moves it into the container
without this package reading it.

## The skill

`cowork_evals init` installs a Claude Code skill at `.claude/skills/cowork-evals/SKILL.md`, and
a session in your repository picks it up from there. It fires on writing or fixing a case, a
`prompt.md` or a grader, on a failing `cowork_evals` command, on the configuration file, and
on plugin code that has to run inside a CoWork session.

It carries the case tree, the two required frontmatter keys, the six grader types, three
copy-paste grader idioms, the seven authoring traps, the exit codes and the 3.10 runtime
constraint. It is the short form of the two documents below, and it sends a reader to
`cowork_evals docs` for everything it does not carry.

The file is yours once `init` writes it. Edit it, commit it, and refresh it after an upgrade
with the two commands above. What it holds and why it is a copy is
[`docs/library.md`](docs/library.md); where `init` puts it is [`docs/cli.md`](docs/cli.md).

## Documentation

This tree ships inside the package. `cowork_evals docs` prints the directory it landed in and
every document name, and `cowork_evals docs <name>` prints one document's path, so a consumer
reads the same files without this repository checked out.

| Document                                         | Covers                                             |
| ------------------------------------------------ | ---------------------------------------------------- |
| [`docs/cli.md`](docs/cli.md)                     | The whole command surface: verbs, options, exit codes |
| [`docs/eval_format.md`](docs/eval_format.md)     | How to write a case: tree, frontmatter, graders    |
| [`docs/approaches.md`](docs/approaches.md)       | The two backends, and what each one proves         |
| [`docs/running_evals.md`](docs/running_evals.md) | The run: what is built today, the gate, logs, cost |
| [`docs/cowork_test.md`](docs/cowork_test.md)     | `test`, and the runtime your suite gets            |
| [`docs/runtime.md`](docs/runtime.md)             | What a CoWork session provides, and what your plugin code may import |
| [`docs/library.md`](docs/library.md)             | What ships, what it writes, and where              |
| [`docs/README.md`](docs/README.md)               | Everything else, in reading order                  |

The name `cowork_evals docs` takes is the path inside the tree without the extension, so
`cowork_evals docs eval_format` prints the second row's file.

## License

MIT. See [`LICENSE`](LICENSE).

## Public repository

Anyone can read this repository. Before committing any file, check that it carries no
username, email address, home directory path, host name, tenant identifier, employer name,
account identifier or session identifier. This covers test fixtures, log excerpts and
Dockerfiles, not only prose.

Record a measured local fact with a placeholder: a path as `<profile>` or `~/...`, and an
account as the environment variable that supplies it. A measured fact that cannot be written
without an identifier does not go in the repository.

## Contributing

[`scripts/README.md`](scripts/README.md) is the task index: the first clone, the tests, the
lint and the build. [`CLAUDE.md`](CLAUDE.md) holds the working rules and the writing rules.
Each directory has a `README.md` that indexes it and owns the rules for it.
