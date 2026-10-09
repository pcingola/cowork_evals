# Environments

## Summary

Code in this repository runs in two different places, and each place has a different set of
packages available to it. The tooling that drives an eval runs on a laptop and may import
anything. Code destined for a skill runs inside a CoWork session and may import only what the
session image carries. This file owns the two Python environments that keep those apart,
`.venv` and the optional `.venv_cowork` mirror, and the split between the three requirements
files under `src/cowork_evals/data/` that the mirror and the container are built from.

- `.venv` is repository tooling. It runs `scripts/` and `tests/`, never a CoWork session, and
  its dependencies are unconstrained. `scripts/venv.sh` builds it, and `scripts/init.sh` calls
  that on clone.
- `.venv_cowork` is the CoWork mirror. It pins the wheel set a session provides, and nothing
  else. Nothing in the package reads it and only `scripts/cowork_run.sh` uses it, so `init.sh`
  does not build it and no test requires it. Build it with `scripts/cowork_venv.sh` when you
  need it, and that script verifies it.
- Both are Python 3.10.12, the exact interpreter a session runs. The wheel set is what
  separates them, not the interpreter.
- Both are development environments. Neither is shipped, and `cowork_evals setup` creates
  neither.
- The mirror reproduces the interpreter and the wheels only. Not the OS, not the architecture,
  not the document tooling or the font stack. The container does; see [docker.md](docker.md).

| Environment   | Path           | Python  | Built by                    | Runs                                 |
| ------------- | -------------- | ------- | --------------------------- | ------------------------------------ |
| Repo tooling  | `.venv`        | 3.10.12 | `venv.sh`, on clone         | `scripts/`, `tests/`                 |
| CoWork mirror | `.venv_cowork` | 3.10.12 | `cowork_venv.sh`, on demand | Code that must behave like a session |

The mirror costs 604 MB, and the interpreter is not a reason to build it: both environments are
the same one. Build it when an import has to be checked against a session's packages without a
container. `cowork_evals test --docker` answers the same question against the real image, and
that route is [cowork_test.md](cowork_test.md).

`.python-version` holds the interpreter version, and it is the only place on the development
side that does. `scripts/venv.sh`, `scripts/cowork_venv.sh` and `scripts/build.sh` all read it,
so no two of them can disagree. `docker/parity.py` carries the same version a second time,
because it ships in the wheel and cannot read a checkout file; `tests/unit/test_environments.py`
asserts the two agree.

## Building it

```bash
scripts/init.sh                # .venv, on clone
scripts/venv.sh                # .venv, after a pyproject.toml change
scripts/venv.sh --check        # verify the lock is current, no writes
scripts/cowork_venv.sh         # the mirror, after a requirements change
scripts/cowork_venv.sh --check # verify the mirror, no writes
```

`scripts/cowork_venv.sh` owns the mirror. Shell, not Python: it builds the environment the 3.10
code runs under and does not run under it. Verifying it calls `.venv` through `uv run` for the
PEP 503 name normalization in `cowork_evals.requirements`. That is the one implementation of it:
the mirror, the container parity comparison and the tests all read a pinned requirements file
through it, so no two of them can disagree on what `foo__bar` normalizes to.

| Invocation   | Does                                                            |
| ------------ | --------------------------------------------------------------- |
| (no args)    | Create the mirror if absent, sync it, exit 0 if already correct |
| `--recreate` | Delete and rebuild from scratch                                 |
| `--check`    | Verify only, no writes, non-zero exit on drift                  |

`--check` verifies four things: the interpreter reports the pinned version, every pin in
`requirements_installable.txt` is installed at its exact version, nothing else is installed
except the test-only packages below, and each direct test-only package is installed. Without
that last one a newly added test-only package is never installed by a plain sync: it is not a
pin, so it cannot be missing, and it is on the allowed-extras list, so it is not an extra.

## Running under the mirror

```bash
scripts/cowork_run.sh python3 path/to/x.py
scripts/cowork_run.sh pytest tests/
```

`cowork_run.sh` puts the mirror first on `PATH`, sets `VIRTUAL_ENV`, then `exec`s the command.
That is what activation does, scoped to one command. It matters for child processes: a script
that shells out to bare `python3` then resolves to 3.10, as it does on the VM.

**Never run `uv run` through it.** uv resolves against the project and will use or create
`.venv`, ignoring `VIRTUAL_ENV`. The command would then run against the dev dependency group
rather than the CoWork wheel set, which is the whole point of the mirror. `cowork_run.sh`
refuses a `uv` command line.

## The test-only packages

The mirror installs `pytest` and `pytest-timeout`, plus their transitive `pluggy`, `iniconfig`,
`exceptiongroup` and `tomli`. The direct two are a list in `cowork_venv.sh`, and the closure is
read from the metadata already installed rather than written by hand, so a pytest release that
gains a dependency does not report that dependency as a package on neither list.

None of them is on the CoWork image. Code under eval must not import one: it would pass here and
fail in a session. They are installed only so pytest can collect and run tests against code that
must behave like a session, under this repository's own pytest configuration, which sets a
timeout.

That list is not `requirements_test.txt`. The mirror runs this repository's suite, so it carries
the plugins that suite configures. The test image runs a consumer's suite unchanged and installs
no pytest plugin at all; see [cowork_test.md](cowork_test.md).

## What the mirror does not reproduce

The interpreter and the wheels, nothing else. Not Ubuntu 22.04, not aarch64, not LibreOffice,
ImageMagick, pandoc, tesseract, or the Ubuntu font stack. Rendering and OCR behaviour still
diverges from a session. See [runtime.md](runtime.md) for what the image holds, and
[docker.md](docker.md) for the container that does reproduce them.

The mirror does not reach an eval case. `scripts/cowork_run.sh` puts it on `PATH` for a command
you run yourself, and that works. Inside a run the OS sandbox that a `Bash` grant turns on cannot
read it, because a virtual environment leaves its interpreter and standard library outside that
sandbox's readable set. A backend that ran the harness on the host would have to stage a
relocatable interpreter into the plugin under test instead. That design is
[staged_runtime.md](staged_runtime.md), and it is not built.

## Three requirements files

| File                           | Is                                                | Pins | Read by                           |
| ------------------------------ | ------------------------------------------------- | ---- | --------------------------------- |
| `requirements.txt`             | The VM `pip freeze`, verbatim                     | 136  | Import checking, parity           |
| `requirements_installable.txt` | The same minus the nine below                     | 127  | The image build, `cowork_venv.sh` |
| `requirements_test.txt`        | pytest and what it needs that the inventory lacks | 5    | The test image layer              |

All three are at `src/cowork_evals/data/` and ship as package data. See [library.md](library.md).

The rule that decides which file a new pin goes in:

| The pin is                                         | Goes in                                                                                     |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| On a CoWork VM, measured                           | `requirements.txt`, and `requirements_installable.txt` unless it will not build on a laptop |
| Not on a CoWork VM, and needed to run pytest there | `requirements_test.txt`                                                                     |
| Neither                                            | Nowhere. It is not a fact about the runtime                                                 |

`requirements_installable.txt` is a subset of `requirements.txt`, and `requirements_test.txt`
names nothing either of the other two pins. `tests/unit/test_environments.py` asserts both: that
`requirements_installable.txt` is `requirements.txt` minus exactly the nine below at identical
versions, and that `requirements_test.txt` and `requirements.txt` share no name. The second
assertion is what keeps the test image's install additive, because that layer installs with
`--no-deps`; see [docker.md](docker.md#the-pinned-list).

The nine are `command-not-found`, `dbus-python`, `distro-info`, `pipx`, `PyGObject`,
`pyinotify`, `python-apt`, `ufw`, `unattended-upgrades`. They are importable in a session, so an
import checker still allows them; they will not build on a laptop, so the mirror omits them.
Which apt package supplies each one in the image is [docker.md](docker.md).
