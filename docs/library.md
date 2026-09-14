# Library

## Summary

This repository is a Python package, not a place where evals are written. The repository that
owns the plugins installs this one, points the `cowork_evals` command at its own tree, and
keeps its cases, its configuration and its logs. This file is the boundary between the two: what
the package ships, how a consumer installs and pins it, what the one configuration file holds,
which rule binds which code, and where a run writes what it produces. The command surface is
[cli.md](cli.md), and which parts of it are built is the status table in
[running_evals.md](running_evals.md).

## The two repositories

| Repository   | Owns                                                                                                           |
| ------------ | ---------------------------------------------------------------------------------------------------------------- |
| This one     | The backends, the CLI, the verdict, the case validator, the pinned CoWork wheel set, the image                  |
| The consumer | Its plugins, their `evals/` trees, its `logs/`, its `cowork_evals.yaml`, and the pinned version of this package |

The consumer never runs `claude plugin eval`. That command is an implementation detail of the
Docker backend, and [cli.md](cli.md) is the whole surface a consumer sees.

## Installing

The repository is the distribution. `pyproject.toml` sits at its root and the build backend is
hatchling, so a git reference builds the same wheel `scripts/build.sh` builds. The package is
not on a package index, so a consumer installs from the repository:

```sh
uv add --dev "cowork-evals @ git+https://github.com/pcingola/cowork_evals"
pip install "cowork-evals @ git+https://github.com/pcingola/cowork_evals"
uv tool install "cowork-evals @ git+https://github.com/pcingola/cowork_evals"
```

Each line tracks the default branch. Appending `@<reference>`, a tag, a branch or a commit,
pins instead. The third line installs the command outside any project, which is how a consumer
that runs the command but never imports it holds a pin. `README.md` carries the same three
lines, and no version number is written into either file. Once the package is on an index the
first two become the name alone:

```sh
uv add --dev cowork-evals
pip install cowork-evals
```

Pinning is the consumer's call. `run` decides pass and fail, so a change to the verdict or to
what a backend can run moves a result with no change to the consumer's cases. A repository
that runs evals in CI pins, in its own `pyproject.toml`. One that runs them by hand need not.
The wheel set and the image inventory are measurements of a VM that moves, so a consumer on an
old version mirrors an old VM. See [runtime.md](runtime.md).

The distribution is `cowork-evals` and the command is `cowork_evals`. `[project.scripts]`
provides the executable, and it is the one entry point: there is no second, and no per-backend
executable. `cowork_evals --version` prints the installed distribution version from package
metadata, and every run records that version in `env.txt`, so a log says which version
produced it.

`scripts/build.sh` builds the sdist and the wheel into `dist/`, and checks that the wheel
carries the requirements files, the example configuration, the skills, the two Dockerfiles and
the documentation. `uv publish` sends them, and this repository runs no publishing step of its
own.

## What ships

| Path                                              | Ships | Holds                                                                    |
| ------------------------------------------------- | ----- | -------------------------------------------------------------------------- |
| `src/cowork_evals/`                               | yes   | The CoWork driver, the CLI, both backends, the graders, the judge, the verdict, the validator |
| `src/cowork_evals/data/requirements*.txt`         | yes   | The pins the mirror and the image are built from                         |
| `src/cowork_evals/data/cowork_evals.example.yaml` | yes   | Every key and every default, and what `init` writes                      |
| `src/cowork_evals/data/skills/<name>/SKILL.md`    | yes   | Every shipped skill, one directory each, and what `init` installs        |
| `src/cowork_evals/docker/Dockerfile`              | yes   | What `setup --docker` builds                                             |
| `src/cowork_evals/docker/Dockerfile.pytest`       | yes   | One layer over it, carrying pytest                                       |
| `docs/`                                           | yes   | Every document in this tree, at `cowork_evals/docs/` in the wheel        |
| `scripts/`                                        | no    | Development tasks for this repository only                               |
| `tests/`, `plugins/`, `plans/`                    | no    | Development material                                                     |

Each module under `src/cowork_evals/` states in its own docstring what it holds. A consumer
never sees `scripts/`: those are the tasks that build this repository's environments, run its
tests and lint it, and they are named nowhere in [cli.md](cli.md). See `scripts/README.md`.

The table is enforced by the sdist include list in `pyproject.toml`, which names the package,
`docs/`, `README.md` and `LICENSE` and nothing else. `scripts/build.sh` fails if a development
directory reaches the sdist, if a Dockerfile or a requirements file is missing from the wheel,
or if the two artefacts carry a different number of documents.

The requirements files, the example configuration and the skills are shipped data rather than
documentation, because `setup --docker` and `init` read them at run time on a machine with no
checkout of this repository. The requirements files are measured from a CoWork VM and recorded
once. What they hold, and how they differ, is [environments.md](environments.md).

## The skills

`src/cowork_evals/data/skills/` holds the shipped Claude Code skills, one directory per skill.
They are the shipped files whose reader is a model rather than a person. `cowork_evals init`
copies each of them to `.claude/skills/<name>/SKILL.md` in the consumer's repository, which is
where a Claude Code session picks up a project skill. The directory name is the skill name, so
the two cannot drift, and adding a skill is adding a directory: nothing in the verb names one.

There are two, and the rule that separates them is which question fires them. A question about
a file this repository ships is the first. A question only a running session can settle is the
second.

| Skill          | Fires on                                                                                                                          | Holds                                                                             |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| `cowork-evals` | Which cases a skill needs, writing or fixing a case, a `prompt.md` or a grader, a failing command, the configuration file, plugin code that runs in a session | The interview and the coverage dimensions, the case tree, the addressability keys, the grader types and idioms, the authoring traps, the exit codes and the runtime constraint |
| `cowork-ask`   | A question about what a live CoWork session does, a claim that has to be confirmed in the product, a failing `cowork_evals ask`    | The verb, what one ask costs, and the rule that the session is asked to do the thing and what it did is read back |

`cowork-evals` is a condensed [eval_design.md](eval_design.md),
[eval_format.md](eval_format.md) and [cli.md](cli.md). `cowork-ask` is a condensed
[cli.md](cli.md), [cowork_driver.md](cowork_driver.md) and
[cowork_desktop.md](cowork_desktop.md). Both are condensed because a skill is read into a
context window every time it fires, and the full documents are one `cowork_evals docs` away.

These files and the documents they condense are the one place in this repository where the
same fact is written twice. The rule that keeps them in step is that a skill states no fact of
its own: every rule in it is in a document, the skill carries the short form, and a change to
a rule is made in the document first. A rule that exists only in a skill is a defect.

Where the verb writes the skills, and why upgrading the package does not refresh them, is
[cli.md](cli.md). This repository is not a consumer, so its own `.claude/skills/` is generated
by `scripts/dev_skills.sh` and git-ignored. The shipped copy is the one source.

## Why the documentation ships

A consumer writes cases, writes plugin code and runs the command. The authoring contract is
[eval_format.md](eval_format.md), which cases to write is [eval_design.md](eval_design.md), the
option surface is [cli.md](cli.md), and the wheel set the code under test may import is
[runtime.md](runtime.md). None of that is derivable from the module source, so a consumer
without this tree is reading a command with no reference.

The tree ships whole, so there is no ship list to curate and no decision to take when a
document is added. `docs/claude_code/` is included: it is the authority where
[eval_format.md](eval_format.md) is silent, and a consumer needs the field reference for the
same reason this repository vendored it.

`docs/` sits at the repository root and hatchling places it at `cowork_evals/docs/` in the
wheel, so nothing moves in the checkout. `cowork_evals docs` prints where it landed. See
[cli.md](cli.md).

## The two reference rules

`docs/` ships and the tree around it does not. A reference that crosses that edge names a
different path in the checkout and in the install, so one of the two is always wrong. Both
rules below are enforced by a test.

| Rule | In                    | Is                                                                          |
| ---- | --------------------- | ------------------------------------------------------------------------------ |
| R1   | any file under `src/` | A document is named by its `docs/` path. It is never linked to                 |
| R2   | any file under `docs/`| A target inside `docs/` is linked. A target outside it is named, not linked    |

R1 is why a module docstring reads `docs/eval_format.md` and carries no `](...)`. The module
sits two levels under the repository root in a checkout and one level above the documents in
an install, and no single relative path is correct in both.

R2 keeps `docs/` self-contained. A link from one document to another stays a link, because the
tree moves whole and the relative path holds. `../README.md`, `../CLAUDE.md`, `../scripts/`,
`../tests/` and `../plugins/` are named as repository paths instead: a consumer has none of
them, and this repository's own reader can still find them.

## Package constraints

| Constraint            | Value       | Reason                                                     |
| --------------------- | ----------- | ------------------------------------------------------------ |
| `requires-python`     | `>=3.10`    | The floor a consumer's development environment must clear  |
| `dependencies`        | any         | Nothing about CoWork constrains what this package imports  |
| ruff `target-version` | `py310`     | Matches `requires-python`, so the lint is the floor        |
| `license`             | `MIT`       | A public repository with no license grants nothing         |
| `readme`              | `README.md` | It is the description an index renders                     |

The runtime dependencies are `PyYAML`, which parses `cowork_evals.yaml` and `case.yaml`,
`python-frontmatter`, which splits a `prompt.md` or a grader file into its `---` block and its
body, and `packaging`, which normalizes a requirement name. Nothing here writes a parser, a
glob engine or an HTTP client.

`requires-python` is a floor, so it also sets the interpreter a consumer's development
environment needs. It is `3.10`, the version a CoWork session runs, so one interpreter covers
this package, the mirror and the container. Nothing about CoWork forces that: the package never
runs in a session. It is set there so a consumer is never made to install a newer interpreter
than the runtime it targets.

Three constructs are what the 3.10 floor costs, and each has a replacement in the tree.

| Not available on 3.10                                             | Replaced by                                                                          |
| ------------------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| A `type` alias and a `def f[T]` type parameter                    | A plain assignment and a `TypeVar`                                                   |
| `PurePath.full_match`, which is 3.13                              | `_full_match` in `grader.py`, pinned against the 3.14 result in `tests/unit/test_grader.py` |
| `argparse` routing a `--` tail into a variadic positional, 3.13   | `cli.parse_args`, which splits the tail itself on every version                      |

## Where the restrictions are

Where the code runs is what decides what binds it, and nothing else. This package runs on a
laptop and controls CoWork. The code under test runs inside the CoWork VM, on that VM's
interpreter and that VM's wheels. A rule for one is never applied to the other, and a file's
place in the tree decides neither.

Every row below is 3.10, so the interpreter does not separate them. The wheel set does: this
package may import anything it declares, and the code under test may import only what the image
carries.

| Restriction                                  | Binds                              | Written in                         |
| -------------------------------------------- | ---------------------------------- | ---------------------------------- |
| Python 3.10 syntax and standard library      | The code under test                | [runtime.md](runtime.md)           |
| The CoWork wheel set, and nothing outside it | The code under test                | [runtime.md](runtime.md)           |
| Any dependency, at any version               | This package, `scripts/`, `tests/` | [environments.md](environments.md) |
| Python 3.10, and pytest beside the wheel set | A consumer's own `tests/`          | [cowork_test.md](cowork_test.md)   |
| Any dependency the consumer declares         | A case's `checks/*.py`             | [checks.md](checks.md)             |

The code under test is every file under the path a consumer passes to `cowork_evals run`,
meaning each skill, command, agent and hook in the plugin.

A case's `checks/*.py` is the one exception. It sits under the same path and is not code under
test: the run is over and graded before a check starts, and a check reads what that run left on
the host, in this package's process. Nothing about the session binds it, and what it imports is
the consumer's own dependency, declared in the consumer's project. This package depends on
nothing a check might want.

Nothing in this package runs in a session. It drives CoWork from outside, so no CoWork fact
reaches it: not the interpreter version, not the wheel set, not the image.

Enforcing the first two rows on the code under test is a separate check from running an eval.
Whether that check is designed or built is the status table in
[running_evals.md](running_evals.md).

## The two roots

| Root         | Is                               | Holds                                      |
| ------------ | -------------------------------- | ------------------------------------------ |
| Package root | the installed distribution       | the code, the pins, the Dockerfiles        |
| Project root | the consumer's working directory | the plugins, their `evals/` trees, `logs/` |

Nothing resolves a path under test from the package root. Every such path comes from the CLI's
path argument, and logs come from the working directory.

## What the consumer provides

A tree the CLI can be pointed at, and nothing else. A plugin is discovered by a
`.claude-plugin/plugin.json` with a sibling `evals/` directory, not by a fixed `plugins/*`
glob, because marketplace repositories do not share one layout. The case tree inside `evals/`
is [eval_format.md](eval_format.md), unchanged by which repository holds it.

Options are flags, and their defaults are keys in `cowork_evals.yaml`, in the working
directory, the directory `logs/` is resolved from. That file is the only configuration route:
nothing is read from the process environment except the variables it names, and there is no
`.env`.

### The one route from the environment

`docker.env_passthrough` is a list of variable names. What each one holds is not configuration
and is never read as any: it is forwarded into the run container and used nowhere here. A run
stays reproducible from the file, because the file still says which names a run carried, and a
name that is not there carries nothing.

| Rule                                                             | Holds because                                                              |
| ------------------------------------------------------------------ | ---------------------------------------------------------------------------- |
| A named variable absent or empty on the host fails the preflight | A missing precondition fails. An empty string is not a value               |
| A name that would carry Claude's own credential is refused       | `docker.credential` is the one route for that, whatever the variable holds |

It exists so a skill whose whole job is calling an API can be evaluated at all. Without it such
a skill fails every eval for a reason that has nothing to do with the skill. The setting, the
two conditions and what a forwarded value reaches are [docker.md](docker.md).

### The precedence ladder

| Layer                 | Beats           | Is for                         |
| --------------------- | --------------- | ------------------------------ |
| A command-line option | every row below | one run                        |
| `cowork_evals.yaml`   | the default     | a consumer's standing settings |
| The built-in default  | nothing         | a machine that sets nothing    |

A check belongs to the setting, so the rung a value arrived on decides which value wins and
nothing else. `--delta-threshold 5` is refused exactly as `eval.delta_threshold: 5` is, and one
converter raises both, so the two cannot drift. What the message names is the one difference:
the option an operator typed, or the `<section>.<key>` a file carries, because that is what the
reader has to change. Without this an option is the way around every check the file gets. The
exit code is [cli.md](cli.md).

`--runs` is the one option whose ceiling is not a setting. It replaces each case's own `runs`,
so it takes that key's cap from the case format instead: [eval_format.md](eval_format.md).

### The four sections

A section is named for the thing that reads it. A new setting goes in the section of whatever
reads it, which is the rule the file is kept to.

| Section   | Read by                                                                     | Its keys and defaults are in         |
| --------- | --------------------------------------------------------------------------- | ------------------------------------ |
| `cowork:` | The CoWork driver                                                           | [cowork_driver.md](cowork_driver.md) |
| `eval:`   | The `claude plugin eval` argument list, and the CoWork backend's judge model | [running_evals.md](running_evals.md) |
| `docker:` | The container backend                                                       | [docker.md](docker.md)               |
| `panel:`  | The case history and the panel over it                                      | [panel.md](panel.md)                 |

```yaml
cowork:
  profile: <the Application Support profile directory name>
eval:
  model: sonnet
docker:
  platform: linux/arm64
panel:
  root: logs/evals/history
```

| Loading rule                                                                                         |
| ------------------------------------------------------------------------------------------------------ |
| A missing file, a missing section and a missing key each fall back to the built-in default           |
| A file named explicitly must exist, so a mistyped path is never a silent set of defaults             |
| An unknown key inside a known section is an error, so a typo is never a silent default               |
| A value of the wrong type is an error, wherever the `Config` was built from                          |
| A check belongs to the setting and not to the rung, so an option's value is checked as the file's is |
| An unknown top level section is ignored, so a later backend adds its own without touching the loader |
| `~` in a path is expanded, and a relative path resolves against the working directory                |

`cowork_evals.yaml` names a profile, which is an identifier, so it is never committed. The
public repository rule in `README.md` applies to every value in it.
`src/cowork_evals/data/cowork_evals.example.yaml` is the template: every key, every default,
and a placeholder for the profile. See [cli.md](cli.md).

## Where state lives

| Thing           | Path                                      | Written by       |
| --------------- | ----------------------------------------- | ---------------- |
| Container image | tag `cowork-evals:<digest>`               | `setup --docker` |
| Test image      | tag `cowork-evals-test:<digest>`          | `setup --docker` |
| Container login | `docker.login_dir`                        | `login --docker` |
| Run logs        | `./logs/evals/<yyyymmdd-hhmmss>-<scope>/` | `run`            |
| Case history    | `panel.root`, `./logs/evals/history/`     | `run`            |

Nothing writes into the installed package, and nothing writes a build product into the consumer
checkout. `test` is the one command whose container writes into the tree it is pointed at, and
what lands there is pytest's own: `.pytest_cache`, `__pycache__` and whatever the suite writes.
See [cowork_test.md](cowork_test.md). The consumer git-ignores `logs/`, `cowork_evals.yaml` and
those, and nothing else.

Each image digest covers every input that changes that image, so a changed input produces a
different tag rather than a stale hit. The first is defined in [docker.md](docker.md) and the
second in [cowork_test.md](cowork_test.md), which hashes the first. A digest that does not match
is a failed preflight, never a silent run against a stale artefact. See [cli.md](cli.md).

Logs are resolved from the working directory, not from either root, and `--out` overrides them.
A consumer running the CLI from its checkout gets `logs/` in its checkout.

The case history is the one thing under `logs/` that `--out` does not move. It is resolved from
the working directory like every other path, and `panel.root` is what moves it. See
[panel.md](panel.md).

## The container holds none of this package

The image is an execution environment and nothing more: the OS, the interpreter, the wheels,
the document tooling, the fonts and the Claude Code CLI. The `cowork_evals` process stays on
the host, builds the `docker run` argument list, and reads the result document back out of the
mounted log directory. Run naming, pruning and the verdict therefore happen in one place for
both backends, and the package is never installed into an image or mounted into a container.
See [docker.md](docker.md).
