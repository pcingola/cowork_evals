# Staged runtime: designed, not implemented

## Summary

**Nothing in this file is built.** There is no `--venv` flag on any verb, and no command in
[cli.md](cli.md) reaches any of it. What is described is a third backend that would run
`claude plugin eval` on the developer's own host against a Python 3.10 interpreter carrying the
CoWork wheel set, staged into the plugin directory under test. The developer decided not to
build it, and the file is kept so the design and the measurements behind it are not redone from
scratch if that decision changes. The status row is in [status.md](status.md).

The three things worth keeping from it:

- **A virtual environment is a pointer, not an installation.** Copying one into the plugin
  copies `site-packages` and leaves the interpreter and the standard library behind.
- **The sandbox readable set** that a `Bash` grant turns on, which is why the plugin directory
  is the only place a staged interpreter can go.
- **A `Bash`-granting run is refused on a host that runs a credential process.** Measured, and
  the reason the container backend was built instead.

The mirror it would be built from is [environments.md](environments.md). The sandbox rules it
satisfies are the "How the sandbox works" section of
[claude_code/plugin_eval_reference.md](claude_code/plugin_eval_reference.md).

## Why the mirror is not staged directly

Granting `Bash` in any form turns on Claude Code's OS-level sandbox, seatbelt on macOS and
bubblewrap on Linux. Inside it the readable set is the per-run sandbox, the plugin directory
under test, the case's `context.add_dirs` entries, and the `PATH` directories inside those. The
home directory and its siblings are unreadable.

A virtual environment is a pointer, not an installation. The mirror at `.venv_cowork` holds no
interpreter and no standard library:

| Property          | Value                                                             |
| ----------------- | ----------------------------------------------------------------- |
| `bin/python3`     | symlink to `bin/python`, symlink to the uv interpreter store      |
| `pyvenv.cfg home` | `~/.local/share/uv/python/cpython-3.10.<x>-<platform>/bin`        |
| `sys.base_prefix` | `~/.local/share/uv/python/cpython-3.10.<x>-<platform>`            |
| `os.__file__`     | the same store, under `lib/python3.10/`                           |

Copying `.venv_cowork` into the plugin therefore copies `site-packages` and leaves the
interpreter and the whole standard library under the home directory, where the sandbox cannot
read them.

Staging the interpreter itself removes the pointer. uv installs python-build-standalone, which
is relocatable, so the copy runs from its new path.

## Why the plugin directory is the only place it can go

The readable set above decides every candidate below. Every run is subject to it, because the
pinned grant names `Bash`, and [running_evals.md](running_evals.md) says why.

| Candidate location                          | Usable                                                             |
| ------------------------------------------- | ------------------------------------------------------------------ |
| The plugin directory under test             | Yes. Readable, and `PATH` directories inside it stay readable      |
| `~/.cache/cowork_evals/`, where it is built | No. Under the home directory                                       |
| A `context.add_dirs` entry                  | No. [eval_format.md](eval_format.md) refuses an entry outside the case directory, and the reference refuses one naming anything but a fixture directory |
| An operator `--allow-tools` read grant      | No. Grants a read path, not an exec path into the sandbox          |

## Layout

```
<plugin>/.cowork-runtime/python/bin/python3                     on PATH
<plugin>/.cowork-runtime/python/lib/python3.10/                 standard library
<plugin>/.cowork-runtime/python/lib/python3.10/site-packages/   the CoWork wheels
```

Two sources build it:

| Source                                                  | Copied to                 | Size   |
| ------------------------------------------------------- | ------------------------- | ------ |
| `~/.local/share/uv/python/cpython-3.10.<x>-<platform>/`  | `.cowork-runtime/python/` | 56 MB  |
| `.venv_cowork/lib/python3.10/site-packages/`             | the staged `site-packages/` | 593 MB |

The wheels go into the interpreter's own `site-packages`, not a separate directory reached
through `PYTHONPATH`. `PYTHONPATH` entries are not scanned for `.pth` files, and four pins ship
one: `coloredlogs`, `lazr.restfulclient`, `lazr.uri` and `zope.interface`.

| Marker `.pth` placed in           | Executed at interpreter start |
| --------------------------------- | ----------------------------- |
| a `PYTHONPATH` directory          | no                            |
| the interpreter's `site-packages` | yes                           |

The staged runtime therefore needs `PATH` only. It sets no `PYTHONPATH`.

## What is dropped

`_virtualenv.pth` and `_virtualenv.py` are virtualenv shims. They belong to `.venv_cowork` and
not to an interpreter, so the staging step would remove both after the copy.

The interpreter arrives with its own `pip` and `setuptools`. The merge would leave them in
place. Their versions are not the image's, and [runtime.md](runtime.md) holds the image's.

## Lifecycle

The backend would stage `.cowork-runtime/` before the harness starts and remove it when the run
ends. That is the one build product this repository ever proposed to write into a consumer
checkout, and it is not written, because the backend is not built.

The backend would refuse to run when the resulting `python3 -V` is not 3.10. The container needs
no equivalent: its system interpreter is already 3.10. See [docker.md](docker.md).

## Measurements

Conditions: macOS 26.6.2 aarch64, uv 0.11.3, interpreter `cpython-3.10.16-macos-aarch64-none`,
CLI 2.1.260. Every test below ran the staged tree from a directory outside the home, with `PATH`
pointing at `.cowork-runtime/python/bin` and no `PYTHONPATH`.

| Test                                             | Result                                                                    |
| ------------------------------------------------ | ------------------------------------------------------------------------- |
| Interpreter runs from the staged path            | pass. `3.10.16`                                                           |
| `sys.base_prefix` inside the staged tree         | pass                                                                      |
| `os.__file__` inside the staged tree             | pass                                                                      |
| `sys.path` entries under the home directory      | none                                                                      |
| Bare `python3` resolves through `PATH`           | pass. Resolves to the staged `bin/python3`                                |
| Pure-Python wheels import                        | pass. `docx`, `pptx`, `pypdf`                                             |
| Compiled wheels import                           | pass. `numpy`, `pandas`, `lxml`, `PIL`, `cv2`, `onnxruntime`, `matplotlib` |
| Namespace packages import                        | pass. `zope.interface`, `lazr.uri`                                        |
| `.pth` files execute from staged `site-packages` | pass                                                                      |

The compiled wheels are the load-bearing ones. They carry native extensions with embedded
library paths, and they resolve them relative to the staged tree.

## A Bash-granting run is refused on a host that runs a credential process

On CLI 2.1.260 on macOS, a case granted `Bash` fails before the child starts, so no case body
runs and the run costs nothing:

```
a credentials file in this environment (the AWS config / shared credentials file, the GCP
application-default credentials, a kubeconfig, or an Anthropic profile config) could not be
followed (an AWS credential_process / credential_source cannot be excluded from the shell),
so the Bash sandbox cannot exclude the files it points at - a Bash-granting evaluation
cannot run here
```

The harness excludes credential files from the OS sandbox before it grants `Bash`. A
`credential_process` or `credential_source` entry names a command, not a file, so there is
nothing to exclude, and the harness refuses the run rather than leave that entry reachable from
the shell.

Three runs of one throwaway case separate the cause:

| Run                                          | Result                    |
| -------------------------------------------- | ------------------------- |
| `--allow-tools Bash`, mirror first on `PATH` | refused, no child started |
| `--allow-tools Bash`, host `PATH`            | refused, no child started |
| No `--allow-tools`, otherwise identical      | ran, 12 s, 0.06 USD       |

The `Bash` grant alone causes it. Neither the mirror nor `scripts/cowork_run.sh` is involved.

Nothing lifts it on that host:

| Attempt                                                            | Result                                                      |
| ------------------------------------------------------------------ | ------------------------------------------------------------ |
| `AWS_CONFIG_FILE` and `AWS_SHARED_CREDENTIALS_FILE` at empty files | still refused                                               |
| `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB=1`                               | still refused                                               |
| Every `CLAUDE_CODE_*` and `CLAUDECODE` variable unset              | still refused, so nesting inside a session is not the cause |
| `HOME` at an empty directory                                       | refusal gone, run fails `Not logged in`. Plain `claude -p` fails the same way |

The last row is why the host cannot be worked around. The configuration the sandbox cannot
exclude is also the one that authenticates Claude Code there.

It would bind the venv backend, whose grant names `Bash` and which runs the harness on the
developer's host. It does not bind the container backend, which runs the harness inside the
image, where no such configuration exists. Nothing in this repository lifts it: the host's AWS
configuration belongs to the developer.

## What is not measured

One condition remains untested: whether the OS sandbox permits execution from the staged
directory, and not only reading of it. The reference states that the plugin directory and the
`PATH` directories inside it stay readable so that toolchains under the home directory still
run, which is this case. That is the reference's wording and not a measurement.

The test that settles it is a case granting `Bash` whose prompt asks for `python3 -V`,
`which -a python3` and `echo $PATH`, run against a plugin with the runtime already staged. It
did not run on the host it was attempted on, for the reason in the section above. That refusal
is a property of that host and not of this design.

## What it does not reproduce

The interpreter and the wheels, nothing else. It inherits every gap the mirror has, listed under
"What the mirror does not reproduce" in [environments.md](environments.md).
