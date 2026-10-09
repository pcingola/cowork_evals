# The test command

## Summary

`cowork_evals test --docker <path>` runs a plugin's own pytest suite inside a container built
from the CoWork image. The suite runs on the interpreter and the wheel set a session has, not
on the laptop's. It is not an eval: no model, no harness, no case tree, no grader, no result
document and no verdict. pytest collects, runs and reports, and this package supplies the
runtime, one mount and the exit code, unchanged. Use it on code a skill ships, before an eval
is written over it.

```bash
cowork_evals test --docker <plugin>/tests
cowork_evals test --docker <plugin>/tests -- -k parser -x
cowork_evals test --docker <plugin>/tests --dry-run
```

The options are [cli.md](cli.md). What the image carries is [runtime.md](runtime.md).

## What it adds

Nothing, once the container starts.

| Rule                                                                                   |
| -------------------------------------------------------------------------------------- |
| No pytest option is added. Not `-p no:cacheprovider`, not `-q`, not a colour flag       |
| No pytest plugin is installed, `pytest-timeout` included                                |
| No pytest environment variable is set. Not `PYTHONDONTWRITEBYTECODE`, not `PYTHONPATH`  |
| The exit code is pytest's, unchanged                                                    |
| The tail after `--` is forwarded verbatim, after the resolved target                    |

Whatever `pytest <path>` does on a laptop is what it does here, on the CoWork runtime.

There is no timeout. Pass one in the tail when you want one.

## The images

| Tag                          | Is                                          | Built by          |
| ---------------------------- | ------------------------------------------- | ----------------- |
| `cowork-evals:<digest>`      | the CoWork image an eval runs in            | `setup --docker`  |
| `cowork-evals-test:<digest>` | that image plus pytest and its dependencies | `setup --docker`  |

The test layer adds `pytest`, `pluggy`, `iniconfig`, `exceptiongroup` and `tomli`, and moves no
package the session has. The eval image never carries pytest.

`--build-missing` builds the test image, and the eval image first when it is absent.

## The container

One container per invocation, one pytest process in it.

| Host path       | Container path | Mode       |
| --------------- | -------------- | ---------- |
| the plugin root | `/work/plugin` | read-write |

The plugin root is the nearest directory at or above `<path>` holding
`.claude-plugin/plugin.json`, resolved as every verb resolves it. A path covering several plugin
roots exits 2. pytest gets `<path>` relative to the root.

- The working directory is the plugin root, so pytest's rootdir is the plugin root. The
  plugin's own `conftest.py`, `pytest.ini` or `pyproject.toml` there is the one read. How a test
  imports the code it tests is decided by those files.
- The mount is read-write, and the container runs as the host uid and gid. `.pytest_cache`,
  `__pycache__` and a `--junitxml` report land in the tree, owned by you.
- `HOME` is a writable container path.
- The network is on, as in a session. A test that needs the network passes here as it does
  there.
- `PYTHONPATH` is the image's own, which provides `import uno`. Do not override it in the tail.
- No credential is mounted, because there is no model call. No OS sandbox starts, because
  there is no `Bash` grant.
- An extra root CA the image was built with is in the system store. `NODE_EXTRA_CA_CERTS` is
  passed as a run passes it.

`test` writes nothing else on the host: no run directory, no `aggregate-result.json`, no
`env.txt`, no `latest` and no history. It takes no `--out`. It reads no `evals/`, so a malformed
case never blocks it.

## Exit codes

pytest's code, unchanged. Not remapped, not collapsed, not interpreted.

| Code | Means                                    |
| ---- | ---------------------------------------- |
| 0    | every test passed                        |
| 1    | a test failed                            |
| 2    | interrupted, a collection error included |
| 3    | an internal pytest error                 |
| 4    | a pytest usage error                     |
| 5    | no test was collected                    |

`5` stays `5`. A file that does not parse on Python 3.10 is a collection error, code 2. A red
suite is a result, not an error. The command's own codes apply only before the container
starts: 2 for a usage error, 3 for an unreachable daemon or an absent image.

## The one backend

`--docker` is the only backend, and there is no `test --cowork`. CoWork has no route to run a
process that is not an agent turn. The backend flag is still required and has no default.

There is no host run under a local Python 3.10 either. A local 3.10 has the interpreter and the
wheels but not LibreOffice, pandoc, tesseract or the fonts, so a suite can pass there and fail
in a session.

## What the plugin provides

A `tests/` directory in the plugin root, holding a pytest suite. One plugin root carries both
`evals/` and `tests/`.

The suite imports pytest, which a session does not have. That is allowed: the suite never loads
in a session, so the session's wheel set does not bind it. The code under test that the suite
imports is bound by the wheel set.

A junit report, a coverage report and when to run the suite are yours. The pytest tail is the
route to the first two, and the tree is writable.
