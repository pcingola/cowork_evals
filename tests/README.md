# tests

Tests for this repository's own code. Python 3.10 under `.venv`, run by `scripts/test.sh`.
Scope as each piece is built: the environments, the configuration file, the harness
argument list, the container image and its parity probe, the test image over it, the CoWork
driver, the CLI's option surface and backend mapping, the result gate, the case validator
and the CoWork grader. The table below lists the files that exist today.

These are not evals. An eval needs a model in the loop. If a failure can be caught by
pytest, it is not an eval.

A hand-written case tree under `tests/data/cases/`, `tests/data/validate/` and
`tests/data/cli/`, a hand-written session document under `tests/data/documents/`, a
hand-written result document under `tests/data/results/` and a recorded judge reply under
`tests/data/judge/` are input on disk, not stand-ins. The reader, the graders, the validator,
the gate and the vote counting that parse them are the real ones.

A harness sandbox is written by the test rather than kept under `tests/data/`, because a
sandbox is a directory tree with modes on it and a checkout does not carry a mode-000
directory. `unit/test_traces.py` builds one in `tmp_path` in the layout
[../docs/claude_code/plugin_eval_reference.md](../docs/claude_code/plugin_eval_reference.md)
records, and a CoWork session directory beside it in the layout
[../docs/cowork_desktop.md](../docs/cowork_desktop.md) records. The collector that reads
either is the real one.

## Two tiers

| Tier        | Lives in             | Selection        | Needs                                              | Cost                              |
| ----------- | -------------------- | ---------------- | -------------------------------------------------- | --------------------------------- |
| Unit        | `tests/unit/`        | the default      | the two built environments, nothing else           | under a second, spends nothing    |
| Integration | `tests/integration/` | `-m integration` | a real CoWork profile, or a daemon and the built images | a VM boot and a permanent session, or an eval run |

The directory is the tier. `tests/integration/conftest.py` marks everything under it
`integration`, so a new file there cannot be left unmarked and cannot land in the default
selection by accident.

```sh
scripts/test.sh                                # unit
scripts/test.sh -m integration                 # every real-system test, the live run included
scripts/test.sh -m "integration and not live"  # the real-system tests that spend nothing
```

Run the integration tier at the end of a plan, and after a merge into `main`. The
deselection is in `pyproject.toml`.

No test is skipped, in either tier. A selected test runs and either passes or fails. An
unbuilt environment, an unconfigured profile and an empty profile are failures, not skips.
A skipped test reports as a pass and hides the thing it was written to catch.

| File                              | Covers                                                     | Exists |
| --------------------------------- | ---------------------------------------------------------- | ------ |
| `unit/test_environments.py`       | Both interpreters, the two requirements files, the scripts | yes    |
| `unit/test_config.py`             | `cowork_evals.yaml`, its three sections, and the `Config`  | yes    |
| `unit/test_cowork.py`             | The CoWork driver: reading, refusing, submitting, waiting  | yes    |
| `unit/test_harness.py`            | The `claude plugin eval` argument list                     | yes    |
| `unit/test_docker.py`             | The image digest, and the build, login and run argument lists | yes |
| `unit/test_parity.py`             | Recorded container probes against the image inventory      | yes    |
| `unit/test_cases.py`              | The case reader over hand-written case trees               | yes    |
| `unit/test_grader.py`             | The four structural graders over hand-written session documents | yes |
| `unit/test_judge.py`              | The composed text, and vote counting over recorded reply documents | yes |
| `unit/test_results.py`            | The v1 result document, field by field                     | yes    |
| `unit/test_cowork_backend.py`     | The skip rule, `plan()`, and the document a skipped suite writes | yes |
| `unit/test_pytest_image.py`       | The test image digest, and the build and run argument lists | yes    |
| `unit/test_validate.py`           | The case validator and the coverage report over hand-written trees | yes |
| `unit/test_logs.py`               | The run directory, `env.txt`, `latest`, pruning and the tee | yes    |
| `unit/test_traces.py`             | What is kept out of a run on either backend, over sandboxes and session directories written by the test | yes |
| `unit/test_gate.py`               | The gate over hand-written result documents                | yes    |
| `unit/test_preflight.py`          | Each backend's unmet conditions, and the rate ceiling      | yes    |
| `unit/test_cli.py`                | The parser, the refusals, the verbs and the exit codes     | yes    |
| `unit/test_cli_docs_init.py`      | The `docs` and `init` verbs: what they print and what they write | yes |
| `unit/test_resources.py`          | The shipped documentation and data, the two reference rules, and the skill against the documents it condenses | yes |
| `integration/test_cowork.py`      | The same driver against a real profile and a real run      | yes    |
| `integration/test_docker.py`      | The built image, its mounts, its sandbox and one real eval run | yes |
| `integration/test_judge.py`       | The judge against the real `claude -p`                     | yes    |
| `integration/test_cowork_backend.py` | The backend against a real profile, and one real suite   | yes    |
| `integration/test_pytest_image.py` | The built test image, its exit codes, and what it writes | yes    |
| `integration/test_cli.py`         | The command against the real backends, through the executable | yes |

One file per unit under test, named after the unit and not after the scenario. A unit tested
in both tiers keeps its name in both directories, which is why `pyproject.toml` sets
`--import-mode=importlib`: two files may share a basename, and neither directory carries an
`__init__.py`. Fixtures go under `tests/data/`, and `tests/conftest.py` holds what both
tiers share. No test in the default selection starts a live eval run, a container or a
CoWork session: it asserts over recorded output, and `--dry-run` is how the command line is
asserted over without spending money.

A CoWork session fixture is written by hand, never copied from a profile. A copied session
directory carries an account identifier, a profile identifier, a session identifier and the
prompts of a real account, and the public repository rule in [../README.md](../README.md)
covers all four. The record shapes a fixture imitates are in
[../docs/cowork_desktop.md](../docs/cowork_desktop.md).

## No mocks

No mock, fake, stub, patch or injected seam appears anywhere in this repository, and no
production parameter exists to accept one. A test that asserts against a stand-in asserts
against itself.

A hand-written session directory is not a mock. It is input on disk, and the reader that
parses it is the real one: it picks the newest transcript by modification time, pairs a
`tool_use` to its `tool_result` by id, drops an orphan result, excludes a `thinking` block
from turn text, reads `message.content` as either a string or a list, and tolerates a
partial last line. Every expected value in a unit test is a literal, never a value computed
by the code that wrote the fixture.

What a fixture cannot prove is that the application still writes that shape. The record
shapes come from a probe recorded in [../docs/cowork_desktop.md](../docs/cowork_desktop.md),
and a release can change them. The integration tier is what closes that gap:

| Cannot be reached without the application | Paid by |
| ------------------------------------------ | --------- |
| That the reader matches a real profile    | `test_the_reader_handles_every_session_in_a_real_profile`, marked `integration` |
| That the deep link prefills, that the Return submits, that `completed` is written | `test_a_live_run_returns_the_marker`, marked `integration` and `live` |

Everything else is real code over real files: the loader parses YAML written to disk, and
the readers, the discovery, the attribution, the completion signal and the run log all run
against session directories the test writes and then reads back.

### The container tier's preconditions

`integration/test_docker.py` needs a reachable daemon, the image already built by
`scripts/image.sh`, and the login already made by `scripts/login.sh`. Nothing there builds
or logs in: a test that builds its own subject reports a build as a pass, and hides a long
build inside a test run. Three of its tests read the credential, and a missing one fails
them rather than skipping them.

### The test image tier's preconditions

`integration/test_pytest_image.py` needs a reachable daemon, the eval image already built
by `scripts/image.sh`, and the test image already built by `scripts/cowork_pytest.sh`.
Nothing there builds either. It reads no credential and calls no model, so none of its
tests is `live` and none of them spends. It runs `plugins/smoke/tests/`, which
[../plugins/README.md](../plugins/README.md) describes.

### The command tier's preconditions

`integration/test_cli.py` needs a reachable daemon, both images already built, and the login
already made. It needs no CoWork profile: everything the command builds above a backend is
backend-neutral and is proven on `--docker`, and the option mapping is proven with
`--dry-run --cowork` in the unit tier. Nothing there builds an image or logs in.

Its one `live` test fires `plugins/smoke/` through `cowork_evals run --docker` and asserts
the whole log layout over that same run, `run.log` and the run's collected trace included. That log line is the
descriptor-level tee proven against a real child process, and it cannot be reached without
one. Its two `test` verb tests cost a container and no model call, so neither is `live`.

### The CoWork backend tier's preconditions

`integration/test_cowork_backend.py` needs everything `integration/test_cowork.py` needs, a
signed-in CoWork, the desktop application running, the macOS Accessibility grant and
`cowork_evals.yaml` naming the active profile, and `claude` on `PATH` as well, because the
judge and `claudeVersion` both need it. A missing precondition fails the test and never
skips it. Its two `live` tests fire real CoWork sessions; its two others walk the sessions
already in the profile and submit nothing.

`integration/test_judge.py` needs only `claude` on `PATH`. It spends, so it is `live`, but
it starts no CoWork session and costs no ceiling entry.

### The live marker

Eight integration tests submit a real run. The three CoWork ones each cost a VM boot, count
against the driver's rate ceiling and leave a permanent session in the signed-in account.
The three container ones cost the model calls their case makes, and the two judge ones cost
short `claude -p` calls. All eight carry `live` as well as `integration`. An integration run
that must not spend selects `-m "integration and not live"`.

The CoWork ones need the macOS Accessibility grant, a signed-in CoWork, the desktop
application already running, and `cowork_evals.yaml` naming the active profile. They fail,
and do not skip, when no profile is configured. Nothing steals focus while one runs. See
[../docs/cowork_desktop.md](../docs/cowork_desktop.md) for the authorizations. The three
container ones need a credential route, and fail without one.

Everything in this repository is 3.10, tests included, and ruff targets `py310`, so a file
here parses on the runtime as well. What still belongs to the code a consumer points the
command at, and to nothing here, is the wheel set: this package imports what it declares, and
the code under test imports only what the image carries. See
[../docs/library.md](../docs/library.md).
