# tests

Tests for this repository's own code. Python 3.10 under `.venv`, run by `scripts/test.sh`.
Scope as each piece is built: the environments, the configuration file, the harness
argument list, the container image and its parity probe, the test image over it, the CoWork
driver, the CLI's option surface and backend mapping, the pass and fail decision, the case
validator, the CoWork grader and the panel over the case history. The table below lists every
test file.

These are not evals. An eval needs a model in the loop. If a failure can be caught by
pytest, it is not an eval.

A hand-written case tree under `tests/data/cases/`, `tests/data/validate/`,
`tests/data/checks/` and `tests/data/cli/`, a hand-written session directory under
`tests/data/cowork/`, a hand-written session document under `tests/data/documents/`, a
hand-written result document under `tests/data/results/`, a hand-written history file under
`tests/data/history/`, a recorded container probe under `tests/data/docker/`, and a recorded
judge reply, PNG or PDF under `tests/data/judge/` are input on disk, not mocks. The reader,
the graders, the validator, the verdict, the panel, the parity check, the vote counting and
the check judge that read them are the real ones.

A check file under `tests/data/checks/` is input on disk too, and it is the one fixture that
is executed rather than parsed: the loader that imports it is the real one, and the file is
the author's code a consumer would write. The collected run directory beside it is copied into
`tmp_path` before anything runs, because a check writes `scratch/` and the layer writes
`checks.jsonl` beside the three collected names.

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

| File                                 | Covers |
| ------------------------------------ | ------ |
| `conftest.py`                        | The fixtures both tiers use: `repository`, `working_directory`, `plugin` |
| `unit/conftest.py`                   | The builders and recorded documents more than one unit file reads |
| `unit/test_environments.py`          | Both interpreters, the two requirements files, the scripts |
| `unit/test_config.py`                | `cowork_evals.yaml`, its sections, and the `Config` |
| `unit/test_cowork.py`                | The CoWork driver: reading, refusing, submitting, waiting |
| `unit/test_harness.py`               | The `claude plugin eval` argument list |
| `unit/test_docker.py`                | The image digest, and the build, login and run argument lists |
| `unit/test_parity.py`                | Recorded container probes against the image inventory |
| `unit/test_cases.py`                 | The case reader over hand-written case trees |
| `unit/test_grader.py`                | The structural graders over hand-written session documents |
| `unit/test_judge.py`                 | The composed text, and vote counting over recorded reply documents |
| `unit/test_results.py`               | The v1 result document, field by field |
| `unit/test_cowork_backend.py`        | What a session cannot run, `plan()`, and the document a declared suite writes |
| `unit/test_pytest_image.py`          | The test image digest, and the build and run argument lists |
| `unit/test_validate.py`              | The case validator and the coverage report over hand-written trees |
| `unit/test_logs.py`                  | The run directory, `env.txt`, `latest`, pruning and the tee |
| `unit/test_traces.py`                | What is kept out of a run on either backend, and the two validity checks over the kept trace, over sandboxes and session directories written by the test |
| `unit/test_checks.py`                | The check layer: discovery, the loader, execution, and what it appends to the document, over hand-written case trees and run directories |
| `unit/test_verdict.py`               | Pass and fail over hand-written result documents |
| `unit/test_panel.py`                 | The history store, the record, the join to the case tree, and the renders |
| `unit/test_preflight.py`             | Each backend's unmet conditions, and the rate ceiling |
| `unit/test_cli.py`                   | The parser, the refusals, the verbs, `docs` and `init` included, and the exit codes |
| `unit/test_resources.py`             | The shipped documentation and data, the two reference rules, and the skill against the documents it condenses |
| `integration/conftest.py`            | The `integration` marker, and the `keyboard`, `attended` and `images` fixtures |
| `integration/test_cowork.py`         | The same driver against a real profile and a real run |
| `integration/test_docker.py`         | The built image, its mounts, its sandbox and real eval runs |
| `integration/test_judge.py`          | The judge against the real `claude -p`, and the check judge over a real PNG and a real PDF |
| `integration/test_cowork_backend.py` | The backend against a real profile, and one real suite |
| `integration/test_pytest_image.py`   | The built test image, its exit codes, and what it writes |
| `integration/test_cli.py`            | The command against the real backends, through the executable, `panel` over the history a real run left, and `ask` against a live session |

One file per unit under test, named after the unit and not after the scenario. A unit tested
in both tiers keeps its name in both directories, which is why `pyproject.toml` sets
`--import-mode=importlib`: two files may share a basename, and neither directory carries an
`__init__.py`. Fixtures go under `tests/data/`, `tests/conftest.py` holds what both
tiers share, and `tests/unit/conftest.py` holds what more than one unit file reads. No test
in the default selection starts a live eval run, a container or a CoWork session: it asserts
over recorded output, and `--dry-run` is how the command line is asserted over without
spending money.

One test per requirement. A behaviour stated in `docs/`, `README.md` or this file is asserted
by one test, in the tier that can reach it, and a second test of it is deleted.

Each test file is shorter than its unit: the module of the same name under
`src/cowork_evals/`, with `docker/__init__.py` for `test_docker.py`, `docker/parity.py` for
`test_parity.py`, `docker/pytest_image.py` for `test_pytest_image.py`, and `requirements.py`
with `scripts/*.sh` for `test_environments.py`. `tests/` as a whole is shorter than
`src/cowork_evals/`. A parametrised test, a typed builder or a fixture under `tests/data/` is
how a file stays shorter.

Test code obeys the typed data rule in [../CLAUDE.md](../CLAUDE.md): a recorded document is
read into the package's own model, and an expected value is compared against that model.

The driver asks for the keyboard inside a submission, so a unit test may call `consent`
under `cowork.consent: none` and may never call `run` or `submit` without it. Either one
opens a real modal and then activates the application.

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
already made. Every test in it but one needs no CoWork profile: everything the command builds
above a backend is backend-neutral and is proven on `--docker`, and the option mapping is
proven with `--dry-run --cowork` in the unit tier. Nothing there builds an image or logs in.

The session fixture `images` in `integration/conftest.py` asserts the daemon and both images
once, for this file and for `integration/test_pytest_image.py`.

Its first `live` test fires the `python-version` case of `plugins/smoke/` through the
executable as `cowork_evals run --docker`, and makes every assertion this tier can over that
one run: the whole log layout, `run.log` and the run's collected trace included, the record
the run appended and its row in `cowork_evals panel`, and a forwarded variable whose value
reaches no file the run left. The `run.log` line is the descriptor-level tee proven against a
real child process, and it cannot be reached without one. The test writes a
`cowork_evals.yaml` naming a history root under `tmp_path`, because `--out` does not move the
history and a test left on the default would append to the developer's own tree. See
[../docs/panel.md](../docs/panel.md).

One more fires the `writes-a-file` case under a grant that carries no tool that can create a
file, and asserts that the run fails instead of scoring. One more fires the `checked-file`
case and reads what the check layer left: the `FAIL` line, `checks.jsonl` and `scratch/`. Its
`test` verb test, over a passing and a failing suite, costs a container and no model call, so
it is not `live`.

The one `live` test that needs a profile is `ask`. It reaches a live session and
there is no other way to prove that the verb submits, waits, prints an answer and names a
session that exists. It needs everything `integration/test_cowork.py` needs, and it carries
the same cost: a VM boot, one entry against the rate ceiling, and a permanent session.

### The CoWork backend tier's preconditions

`integration/test_cowork_backend.py` needs everything `integration/test_cowork.py` needs, a
signed-in CoWork, the desktop application running, the macOS Accessibility grant and
`cowork_evals.yaml` naming the active profile, and `claude` on `PATH` as well, because the
judge and `claudeVersion` both need it. A missing precondition fails the test and never
skips it. Both its tests are `live` and fire real CoWork sessions.

`integration/test_judge.py` needs only `claude` on `PATH`. It spends, so it is `live`, but
it starts no CoWork session and costs no ceiling entry.

### The live marker

Twelve integration tests submit a real run. The four CoWork ones each cost a VM boot, count
against the driver's rate ceiling and leave a permanent session in the signed-in account.
The five container ones cost the model calls their case makes, and the three judge ones cost
short `claude -p` calls. All twelve carry `live` as well as `integration`. An integration run
that must not spend selects `-m "integration and not live"`.

The CoWork ones need the macOS Accessibility grant, a signed-in CoWork, the desktop
application already running, and `cowork_evals.yaml` naming the active profile. They fail,
and do not skip, when no profile is configured. Nothing steals focus while one runs. See
[../docs/cowork_desktop.md](../docs/cowork_desktop.md) for the authorizations. Three of them
are in the two CoWork files and the fourth is `ask`, in `integration/test_cli.py`. The five
container ones need a credential route, and fail without one.

The integration tier asks for the keyboard once, before the first test that takes it, through
the session-scoped `keyboard` fixture in `integration/conftest.py`. Two fixtures request it:
`attended`, which every test that submits through the driver reads, and `activate` in
`integration/test_cowork.py`, the one route to `osascript` in a test. A test that takes the
keyboard goes through one of them. A run that selects neither, a Docker-only one for example,
shows no dialog. It needs no CoWork profile. Cancel raises code 2, and every test that takes the
keyboard then errors.

`-m "integration and not live"` takes the keyboard too: the focus test in
`integration/test_cowork.py` activates Finder, and `live` does not select it.

Every CoWork test that fires reads the `attended` fixture in `integration/conftest.py`. It
loads this machine's `cowork_evals.yaml` into a `Config` and returns it with
`cowork.consent: dialog`, so a developer whose own file carries `none` is still warned by a
test run. A missing file or a file that names no profile fails the test. The modal does not
appear a second time, because `keyboard` already asked and consent is once per process. It is
a configuration value, not a seam: the `Config` is what a consumer's file loads to, and no
parameter injects an answer. `ask` reads its configuration from the working directory, so its
test writes the `Config` there with `Config.dump`. The driver's own consent is module state,
which is what makes one ask cover a whole run.

Everything in this repository is 3.10, tests included, and ruff targets `py310`, so a file
here parses on the runtime as well. What still belongs to the code a consumer points the
command at, and to nothing here, is the wheel set: this package imports what it declares, and
the code under test imports only what the image carries. See
[../docs/library.md](../docs/library.md).
