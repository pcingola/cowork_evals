# Library

## Summary

This repository is not where evals are written. It is a library, distributed as a Python
package. A separate repository owns the plugins and their eval cases, installs this one, and
points it at its own tree.

- **Two repositories.** This one owns the backends, the CLI, the gate, the validator, the
  pinned wheel set and the image. The consumer owns its plugins, its cases and its logs.
- **One configuration file.** `cowork_evals.yaml` in the working directory. Nothing is read
  from the process environment, and there is no `.env`.
- **Two roots.** The installed package holds the code and the pins. The consumer's working
  directory holds the plugins and the logs. Nothing resolves a path under test from the
  package root.
- **Two kinds of code.** This package runs on a laptop and is unconstrained. The code under
  test runs in the CoWork VM and is bound to 3.10 and the image wheel set.
- **Nothing writes into the installed package**, and the container holds none of it.

This file is the boundary. The command surface is [cli.md](cli.md). What of it is built is
the status table in [running_evals.md](running_evals.md).

## The two repositories

| Repository   | Owns                                                                                             |
| ------------ | ------------------------------------------------------------------------------------------------ |
| This one     | The backends, the CLI, the gate, the case validator, the pinned CoWork wheel set, the image      |
| The consumer | Its plugins, their `evals/` trees, its `logs/`, its `cowork_evals.yaml`, and the pinned version of this package |

The consumer never runs `claude plugin eval`. That command is an implementation detail of the
Docker backend, and [cli.md](cli.md) is the whole surface a consumer sees.

## Installing

The repository is the distribution. `pyproject.toml` sits at its root and the backend is
hatchling, so a git reference builds the same wheel `scripts/build.sh` builds. It is not on
a package index yet, so a consumer installs from the repository:

```sh
uv add --dev "cowork-evals @ git+https://github.com/pcingola/cowork_evals"
pip install "cowork-evals @ git+https://github.com/pcingola/cowork_evals"
uv tool install "cowork-evals @ git+https://github.com/pcingola/cowork_evals"
```

Those track the default branch. Appending `@<reference>`, a tag, a branch or a commit, pins
instead. No version is written into either file: a number here goes stale on the next release,
and `README.md` carries the same three lines. The third line installs the command outside any
project, which is how a consumer that runs the command but does not import it holds a pin.

Pinning is the consumer's call and this repository states when it is worth making: `run`
decides pass and fail, so a change to the gate or the skip rules moves that verdict with no
change to the consumer's cases. A repository that gates CI on evals pins. One that runs them
by hand need not. Once the package is on an index they become
the name alone:

```sh
uv add --dev cowork-evals
pip install cowork-evals
```

The distribution is `cowork-evals` and the command is `cowork_evals`. `scripts/build.sh`
builds both artefacts into `dist/` and proves the wheel carries the Dockerfiles and the
requirements files; `uv publish` is what sends them, and this repository runs no publishing
step of its own.

`[project.scripts]` provides the `cowork_evals` executable. It is the one entry point: there
is no second, and no per-backend executable. `cowork_evals --version` prints the installed
distribution version from package metadata, and every run records it in `env.txt`, so a log
says which version produced it.

The consumer pins the version in its own `pyproject.toml`. That is the pin. The wheel set and
the image inventory are measurements of a VM that moves, so a consumer on an old version
mirrors an old VM. See [runtime.md](runtime.md).

## What ships

| Path                                      | Ships | Holds                                                              |
| ----------------------------------------- | ----- | ------------------------------------------------------------------ |
| `src/cowork_evals/`                       | yes   | The CoWork driver, the CLI, the backends, the gate, the validator  |
| `src/cowork_evals/data/requirements*.txt` | yes   | The pins the mirror and the image are built from                   |
| `src/cowork_evals/config.py`              | yes   | `cowork_evals.yaml`, and the frozen `Config` below                 |
| `src/cowork_evals/harness.py`             | yes   | The `claude plugin eval` argument list                             |
| `src/cowork_evals/cowork.py`              | yes   | The CoWork driver: one prompt in, one session document out         |
| `src/cowork_evals/cases.py`               | yes   | The case reader, backend-neutral. `CaseError` lives here           |
| `src/cowork_evals/grader.py`              | yes   | The four structural graders over a session document                |
| `src/cowork_evals/judge.py`               | yes   | The `claude -p` judge behind `llm` and `baseline`                  |
| `src/cowork_evals/results.py`             | yes   | The v1 `aggregate-result.json` document                            |
| `src/cowork_evals/requirements.py`        | yes   | The pinned requirements reader, and PEP 503 name normalization     |
| `src/cowork_evals/cowork_backend.py`      | yes   | The CoWork backend: the skip rule, `plan` and `run`                |
| `src/cowork_evals/validate.py`            | yes   | The case validator, and the skill coverage report                  |
| `src/cowork_evals/logs.py`                | yes   | The run directory, `env.txt`, `latest`, pruning and the tee        |
| `src/cowork_evals/gate.py`                | yes   | The gate over `aggregate-result.json`                              |
| `src/cowork_evals/preflight.py`           | yes   | Each backend's unmet conditions, for `check` and for `run`         |
| `src/cowork_evals/resources.py`           | yes   | Where the shipped documentation and data are, in either layout     |
| `src/cowork_evals/cli.py`                 | yes   | The parser, the seven verbs, the dispatch and the exit codes       |
| `src/cowork_evals/docker/`                | yes   | The container backend: the digest, the argument lists, build, check and run |
| `src/cowork_evals/docker/Dockerfile`      | yes   | What `setup --docker` builds                                       |
| `src/cowork_evals/docker/Dockerfile.pytest` | yes | One layer over it, carrying pytest                                 |
| `src/cowork_evals/docker/pytest_image.py` | yes   | `PytestImage`: the test image's digest, build, check and run       |
| `src/cowork_evals/docker/probe.py`        | yes   | The parity probe, the one file here that runs inside the container |
| `src/cowork_evals/docker/parity.py`       | yes   | The comparison, run on the host                                    |
| `src/cowork_evals/data/cowork_evals.example.yaml` | yes | Every key and every default, and what `init` writes          |
| `src/cowork_evals/data/skill/SKILL.md`    | yes   | The eval-authoring skill, and what `init` installs                 |
| `docs/`                                   | yes   | Every document in this tree, at `cowork_evals/docs/` in the wheel  |
| `scripts/`                                | no    | Development tasks for this repository only                         |
| `tests/`, `plugins/`, `plans/`            | no    | Development material                                               |

A consumer never sees `scripts/`. Those are the tasks that build this repository's own
environments, run its tests and lint it, and they are named nowhere in [cli.md](cli.md). See
`scripts/README.md`.

The table is enforced by the sdist include list in `pyproject.toml`, which names the package,
`docs/`, `README.md` and `LICENSE` and nothing else. `scripts/build.sh` fails if a development
directory reaches the sdist, if a Dockerfile or a requirements file is missing from the wheel,
or if the two artefacts carry a different number of documents.

The requirements files are shipped data, not documentation, because `setup --docker` reads
them at run time on a machine that has no checkout of this repository. They are measured from
a CoWork VM and recorded once. What they hold, and how they differ, is
[environments.md](environments.md). `cowork_evals.example.yaml` and `SKILL.md` are shipped
data for the same reason: `init` writes both on a machine with no checkout.

## The skill

`src/cowork_evals/data/skill/SKILL.md` is a Claude Code skill, and it is the one shipped file
whose reader is a model rather than a person. `cowork_evals init` copies it to
`.claude/skills/cowork-evals/SKILL.md` in the consumer's repository, which is where a Claude
Code session picks up a project skill. Its frontmatter carries the triggers: writing or fixing
a case, a `prompt.md` or a grader, a failing command, the configuration file, and plugin code
that has to run inside a session.

It holds the case tree, the two addressability keys, the six grader types, the three grader
idioms, the seven authoring traps, the exit codes and the runtime constraint. That is a
condensed [eval_format.md](eval_format.md) and [cli.md](cli.md), and it is condensed on
purpose: a skill is read into a context window every time it fires, and the full documents are
one `cowork_evals docs` away for anything it does not carry.

This file and the documents it condenses are the one place in this repository where the same
fact is written twice. The rule that keeps them from drifting apart is that the skill states
no fact of its own: every rule in it is in a document, the skill carries the short form, and a
change to a rule is made in the document first. A rule that exists only in the skill is a
defect.

Where the verb writes it, and why upgrading the package does not refresh it, is
[cli.md](cli.md).

## Why the documentation ships

A consumer writes cases, writes plugin code and runs the command. The authoring contract is
[eval_format.md](eval_format.md), the option surface is [cli.md](cli.md), and the wheel set
the code under test may import is [runtime.md](runtime.md). None of that is derivable from
the module source, so a consumer without this tree is reading a command with no reference.

The tree ships whole. There is no ship list to curate and no decision to take when a document
is added, and a hand-picked set had already omitted [runtime.md](runtime.md) once.
`docs/claude_code/` is included: it is the authority where [eval_format.md](eval_format.md)
is silent, and a consumer needs the field reference for the same reason this repository
vendored it.

`docs/` sits at the repository root and hatchling places it at `cowork_evals/docs/` in the
wheel, so nothing moves in the checkout. `cowork_evals docs` prints where it landed. See
[cli.md](cli.md).

## The two reference rules

`docs/` ships and the tree around it does not. A reference that crosses that edge names a
different path in the checkout and in the install, so one of the two is always wrong, and a
link that resolves in a checkout is exactly the link that dangles for a consumer. Both rules
below are enforced by a test.

| Rule | In                    | Is                                                                       |
| ---- | --------------------- | -------------------------------------------------------------------------- |
| R1   | any file under `src/` | A document is named by its `docs/` path. It is never linked to             |
| R2   | any file under `docs/` | A target inside `docs/` is linked. A target outside it is named, not linked |

R1 is why a module docstring reads `docs/eval_format.md` and carries no `](...)`. The module
sits two levels under the repository root in a checkout and one level above the documents in
an install, and no single relative path is correct in both.

R2 keeps `docs/` self-contained. A link from one document to another stays a link, because
the tree moves whole and the relative path holds. `../README.md`, `../CLAUDE.md`,
`../scripts/`, `../tests/` and `../plugins/` are named as repository paths instead: a
consumer has none of them, and this repository's own reader can still find them.

## Package constraints

| Constraint            | Value    | In `pyproject.toml` | Reason                                                        |
| --------------------- | -------- | ------------------- | -------------------------------------------------------------- |
| `requires-python`     | `>=3.10` | yes                 | The floor a consumer's development environment must clear     |
| `dependencies`        | any      | yes                 | Nothing about CoWork constrains what this package imports     |
| ruff `target-version` | `py310`  | yes                 | Matches `requires-python`, so the lint is the floor           |
| `[tool.uv] package`   | removed  | yes                 | Removing it makes uv build a distribution                     |
| `license`             | `MIT`    | yes                 | A public repository with no license grants nothing            |
| `readme`              | `README.md` | yes              | It is the description an index renders                        |

The runtime dependencies are `PyYAML`, which parses `cowork_evals.yaml` and `case.yaml`,
`python-frontmatter`, which splits a `prompt.md` or a grader file into its `---` block and its
body, and `packaging`. Nothing here writes a parser, a glob engine or an HTTP client.

`package = false` was removed in the commit that added `src/cowork_evals/`, and not before,
because `uv sync` fails against a package with no package tree. `[project.scripts]` came in a
later commit and is unrelated to it.

`requires-python` is a floor, so it also sets the interpreter a consumer's development
environment needs. It is `3.10`, the version a CoWork session runs, so one interpreter covers
this package, the mirror and the container. Nothing about CoWork forces that: the package
never runs in a session, and the value is a floor, not a ceiling. It is set there so a
consumer is never made to install a newer interpreter than the runtime it targets.

Three constructs are what 3.10 costs, and each has a replacement in the tree. `except A, B:`
is parenthesized. A `type` alias and a `def f[T]` parameter are a plain assignment and a
`TypeVar`. `PurePath.full_match` is 3.13 and is translated in `grader.py`, pinned against the
3.14 result in `tests/unit/test_grader.py`. `argparse` routes a `--` into a variadic
positional only from 3.13, so `cli.parse_args` splits the tail itself, on every version.

## Where the restrictions are

Two kinds of code, and one of them is unconstrained. This package runs on a laptop and
controls CoWork. The code under test runs inside the CoWork VM, on that VM's interpreter and
that VM's wheels. A rule for one is never applied to the other.

Every row is 3.10, so the interpreter is no longer what separates them. The wheel set is: this
package may import anything it declares, and the code under test may import only what the
image carries.

| Restriction                                  | Binds                              | Written in                         |
| -------------------------------------------- | ---------------------------------- | ---------------------------------- |
| Python 3.10 syntax and standard library      | The code under test                | [runtime.md](runtime.md)           |
| The CoWork wheel set, and nothing outside it | The code under test                | [runtime.md](runtime.md)           |
| Any dependency, at any version               | This package, `scripts/`, `tests/` | [environments.md](environments.md) |
| Python 3.10, and pytest beside the wheel set | A consumer's own `tests/`          | [cowork_test.md](cowork_test.md)   |

The code under test is every file under the path a consumer passes to `cowork_evals run`,
meaning each skill, command, agent and hook in the plugin. It runs on the session interpreter
and imports only what the image carries.

Nothing in this package runs in a session. It drives CoWork from outside, so no CoWork fact
reaches it: not the interpreter version, not the wheel set, not the image.

Enforcing the first two rows on the code under test is a separate check from running an eval.
Whether that check is designed or built is the status table in
[running_evals.md](running_evals.md).

## The two roots

| Root         | Is                               | Holds                                      |
| ------------ | -------------------------------- | ------------------------------------------ |
| Package root | the installed distribution       | the code, the pins, the Dockerfile         |
| Project root | the consumer's working directory | the plugins, their `evals/` trees, `logs/` |

Nothing resolves a path under test from the package root. Every such path comes from the
CLI's path argument, and logs come from the working directory.

## What the consumer provides

A tree the CLI can be pointed at, and nothing else. A plugin is discovered by a
`.claude-plugin/plugin.json` with a sibling `evals/` directory, not by a fixed `plugins/*`
glob, because marketplace repositories do not share one layout. The case tree inside `evals/`
is [eval_format.md](eval_format.md), unchanged by which repository holds it.

Options are flags, and their defaults are keys in `cowork_evals.yaml`, in the working
directory, the directory `logs/` is resolved from. That file is the only configuration route:
nothing is read from the process environment, and there is no `.env`.

`docker.auth_env` does not weaken that. It holds variable *names*, so the setting still comes
from the file; the value is a credential rather than a setting, and it is forwarded to the
container by Docker without this package reading it. Nothing in `src/cowork_evals/` reads
`os.environ`. See [docker.md](docker.md).

| Layer                 | Beats           | Is for                         |
| --------------------- | --------------- | ------------------------------ |
| A command-line option | every row below | one run                        |
| `cowork_evals.yaml`   | the default     | a consumer's standing settings |
| The built-in default  | nothing         | a machine that sets nothing    |

The file holds three sections, and a section is named for the thing that reads it. A new
setting goes in the section of whatever reads it, which is the rule the file is kept to.

| Section   | Read by                                                                     | Its keys and defaults are in         |
| --------- | --------------------------------------------------------------------------- | ------------------------------------ |
| `cowork:` | The CoWork driver                                                           | [cowork_driver.md](cowork_driver.md) |
| `eval:`   | The `claude plugin eval` argument list, and the CoWork backend's judge model | [running_evals.md](running_evals.md) |
| `docker:` | The container backend                                                       | [docker.md](docker.md)               |

```yaml
cowork:
  profile: <the Application Support profile directory name>
eval:
  model: sonnet
docker:
  platform: linux/arm64
```

| Rule                                                                                                 |
| ------------------------------------------------------------------------------------------------------ |
| A missing file, a missing section and a missing key each fall back to the built-in default           |
| An unknown key inside a known section is an error, so a typo is never a silent default               |
| A value of the wrong type is an error, wherever the `Config` was built from                          |
| An unknown top level section is ignored, so a later backend adds its own without touching the loader |
| `~` in a path is expanded, and a relative path resolves against the working directory                |

`cowork_evals.yaml` names a profile, which is an identifier, so it is never committed. The
public repository rule in `README.md` applies to every value in it.
`src/cowork_evals/data/cowork_evals.example.yaml` is the template: every key, every default,
and a placeholder for the profile. It is package data rather than a file at the repository
root, because `cowork_evals init` writes it on a machine with no checkout. See
[cli.md](cli.md).

## Where state lives

| Thing           | Path                                      | Written by       |
| --------------- | ----------------------------------------- | ---------------- |
| Container image | tag `cowork-evals:<digest>`               | `setup --docker` |
| Test image      | tag `cowork-evals-test:<digest>`          | `setup --docker` |
| Container login | `docker.login_dir`                        | `setup --docker` |
| Run logs        | `./logs/evals/<yyyymmdd-hhmmss>-<scope>/` | `run`            |

Nothing writes into the installed package, and nothing writes a build product into the
consumer checkout. `test` is the one command whose container writes into the tree it is
pointed at, and what lands there is pytest's own: `.pytest_cache`, `__pycache__` and whatever
the suite writes. See [cowork_test.md](cowork_test.md). The consumer git-ignores `logs/`,
`cowork_evals.yaml` and those, and nothing else.

Each image digest covers every input that changes that image, so a changed input produces a
different tag rather than a stale hit. The first is defined in [docker.md](docker.md) and the
second in [cowork_test.md](cowork_test.md), which hashes the first. A digest that
does not match is a failed preflight, never a silent run against a stale artefact. See
[cli.md](cli.md).

Logs are resolved from the working directory, not from either root, and `--out` overrides
them. A consumer running the CLI from its checkout gets `logs/` in its checkout.

## The container holds none of this package

The image is an execution environment and nothing more: the OS, the interpreter, the wheels,
the document tooling, the fonts and the Claude Code CLI. The `cowork_evals` process stays on
the host, builds the `docker run` argument list, and reads the result document back out of the
mounted log directory. Run naming, pruning and the gate therefore happen in one place for both
backends, and the package is never installed into an image or mounted into a container. See
[docker.md](docker.md).
