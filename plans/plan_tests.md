# plan_tests

Review every test in `tests/`, decide for each test case whether it is deleted, fixed or kept,
and then carry out those decisions.

The decisions are recorded one table per test file under [`plan_tests/`](plan_tests), and the typed models in [`plan_models.md`](plan_models.md). Nothing is deleted or
rewritten until the developer has approved the table for that file.

## Rules a test must meet

| Rule | A test that breaks it |
| ---- | --------------------- |
| It checks a requirement of this system: a behaviour stated in `docs/`, `README.md` or a `tests/README.md` row. | Tests no stated behaviour. |
| It checks this repository's code, not the standard library or a dependency. | Loads JSON or YAML and asserts the loaded value equals what is in the file. Asserts that `json`, `pathlib`, `argparse`, `yaml` or Pydantic do their job. |
| It checks behaviour, not the shape of an implementation. | Asserts a private helper's return for one branch, the order of keys, the exact wording of a docstring, or a value the test itself computed with the code under test. |
| It is the only test of its requirement. | Repeats a requirement another test already checks. Several near-identical tests where one parametrised test would do. |
| All data is typed. Structured data is a dataclass or a Pydantic model, in the package and in the tests. JSON is parsed into a model when it is read and serialised from a model when it is written. | Builds, edits or reads a `dict[str, Any]` record, such as `run["score"] = 0.0`, or writes a fixture document as a dict literal. |
| It obeys `CLAUDE.md` and `tests/README.md`: no mock, no skip, a missing integration precondition fails. | Uses any of those. |

Test code is shorter than the code it tests. This holds for the whole suite and for each
test file against its unit.

## Verdicts

| Verdict | Meaning |
| ------- | ------- |
| `DELETE` | The test breaks the first four rules and cannot be repaired into a useful test. It is removed. |
| `FIX` | The test checks a real requirement but breaks a rule. The description says exactly what changes: the model it builds instead of a dict, the tests it merges with, the assertion it replaces. |
| `OK` | The test meets every rule and stays unchanged. |

A shared helper or fixture in a test file gets a verdict too. A helper that only builds dicts is
`FIX`, and is replaced by building the typed models.

## Phase 1: assess each test file

One subagent per test file. Subagents run in parallel, and each one only reads; none of them edits
this file or any test.

What a subagent does:

1. It reads `CLAUDE.md`, `tests/README.md`, the rules above, the test file, the source module
   or modules the file tests, and the `docs/` files that state that module's behaviour.
2. It returns one table row per test function, per parametrised case where the cases differ in
   kind, and per helper or fixture, with these columns: `Test`, `Verdict`, `Requirement` (the
   `docs/` file and section it checks, or `none`), and `What to do`.
3. A `FIX` row names the typed model it needs. Where that model does not exist yet in
   `src/cowork_evals/`, the row says `needs model <Name>` and lists the fields the test
   touches.
4. Its last line says whether the file should be merged into another file or deleted
   outright.

The orchestrating session writes each returned table to its file under `plan_tests/` and ticks
the box. One box is ticked at a time.

### Unit tier

- [x] [`tests/unit/test_cases.py`](plan_tests/unit_test_cases.md)
- [x] [`tests/unit/test_checks.py`](plan_tests/unit_test_checks.md)
- [x] [`tests/unit/test_cli.py`](plan_tests/unit_test_cli.md)
- [x] [`tests/unit/test_cli_docs_init.py`](plan_tests/unit_test_cli_docs_init.md)
- [x] [`tests/unit/test_config.py`](plan_tests/unit_test_config.md)
- [x] [`tests/unit/test_cowork.py`](plan_tests/unit_test_cowork.md)
- [x] [`tests/unit/test_cowork_backend.py`](plan_tests/unit_test_cowork_backend.md)
- [x] [`tests/unit/test_docker.py`](plan_tests/unit_test_docker.md)
- [x] [`tests/unit/test_environments.py`](plan_tests/unit_test_environments.md)
- [x] [`tests/unit/test_grader.py`](plan_tests/unit_test_grader.md)
- [x] [`tests/unit/test_harness.py`](plan_tests/unit_test_harness.md)
- [x] [`tests/unit/test_judge.py`](plan_tests/unit_test_judge.md)
- [x] [`tests/unit/test_logs.py`](plan_tests/unit_test_logs.md)
- [x] [`tests/unit/test_panel.py`](plan_tests/unit_test_panel.md)
- [x] [`tests/unit/test_parity.py`](plan_tests/unit_test_parity.md)
- [x] [`tests/unit/test_preflight.py`](plan_tests/unit_test_preflight.md)
- [x] [`tests/unit/test_pytest_image.py`](plan_tests/unit_test_pytest_image.md)
- [x] [`tests/unit/test_resources.py`](plan_tests/unit_test_resources.md)
- [x] [`tests/unit/test_results.py`](plan_tests/unit_test_results.md)
- [x] [`tests/unit/test_traces.py`](plan_tests/unit_test_traces.md)
- [x] [`tests/unit/test_validate.py`](plan_tests/unit_test_validate.md)
- [x] [`tests/unit/test_verdict.py`](plan_tests/unit_test_verdict.md)

### Integration tier

- [x] [`tests/integration/test_cli.py`](plan_tests/integration_test_cli.md)
- [x] [`tests/integration/test_cowork.py`](plan_tests/integration_test_cowork.md)
- [x] [`tests/integration/test_cowork_backend.py`](plan_tests/integration_test_cowork_backend.md)
- [x] [`tests/integration/test_docker.py`](plan_tests/integration_test_docker.md)
- [x] [`tests/integration/test_judge.py`](plan_tests/integration_test_judge.md)
- [x] [`tests/integration/test_pytest_image.py`](plan_tests/integration_test_pytest_image.md)

### Shared code and fixtures

- [x] [`tests/conftest.py`](plan_tests/conftest.md)
- [x] [`tests/integration/conftest.py`](plan_tests/integration_conftest.md)
- [x] [`tests/data/`](plan_tests/data.md): every fixture that no test still needs after phase 1 is listed for deletion; every fixture document written as raw JSON is checked against the typed model that will parse it

## Phase 2: approve the decisions

- [x] The developer reviews each file's table under [`plan_tests/`](plan_tests), one file at a time, and approves or changes each row.
- [x] The typed models every `FIX` row needs are collected into one list in [`plan_models.md`](plan_models.md). Each model gets its fields, its module in `src/cowork_evals/`, and the modules that will use it.

## Phase 3: type the package

The tests cannot use typed data while the package hands them dicts. The package comes first.

Each box below is one commit and passes `./scripts/test.sh` and `./scripts/lint.sh`. A test that
the box's change breaks is changed in the same commit only as far as reading the model needs
(`doc["cases"]` becomes `doc.cases`). Its row in `plan_tests/` is applied in phase 4. Each model
has the fields, types, keys and extra-key policy [`plan_models.md`](plan_models.md) gives it, and
writes exactly the keys and values the module writes today, except where `plan_models.md` or the
"Decisions" table says otherwise.

- [x] Add `pydantic` to `dependencies` in `pyproject.toml`.
- [x] `cases.py`: `PluginManifest`, `PromptFrontmatter`, `CaseYaml`, `CaseContext`, `GraderConfig` and its six configs, `FileTarget`.
- [x] `grader.py`: `GraderResult` as `plan_models.md` gives it, and the graders read the typed configs.
- [x] `cowork.py`: `SessionDocument`, `Turn`, `ToolCall`, `RunLogEntry`, `SessionRecord`, `AuditRecord`, `Message`, `ContentBlock`. `docs/cowork_driver_internals.md` "The API" says `run` and `collect` return a `SessionDocument`, serialised with `model_dump_json()`, and `history` returns one `RunLogEntry` per line, oldest first.
- [x] `judge.py`: `JudgeOutput`, `JudgeVerdict`, and the typed `LlmGraderConfig` and `BaselineGraderConfig`.
- [x] `results.py`: `ResultDocument`, `SuiteInfo`, `PluginRef`, `SuiteAggregates`, `CaseEntry`, `Arms`, `CaseAggregates`, `GraderDefinition`, `RunEntry`, `CoWorkRef`. `results.Run` and `results.CaseResult` are removed.
- [ ] `cowork_backend.py` reads and writes `ResultDocument` and `SessionDocument`.
- [ ] `traces.py`: `TraceRecord`, and the result document read and rewritten as `ResultDocument`.
- [ ] `checks.py`: `Outcome` and `JudgeCall` as `plan_models.md` gives them, and the result document read and rewritten as `ResultDocument`.
- [ ] `verdict.py` reads `ResultDocument`.
- [ ] `panel.py`: `HistoryRecord`, `PanelSnapshot`, `Row`, `Cell`, and the result document read as `ResultDocument`.
- [ ] `logs.py`: `RunEnvironment`.
- [ ] `config.py`: `Config.dump(path)`, with `Config.load(path) == config` for every `Config` the tests build.
- [ ] `docker/__init__.py`: `Unmet`, `Image`, `Credentials`, `OAuth`. `preflight.py` and `docker/pytest_image.py` take `Unmet`.
- [ ] `docker/parity.py`: `ProbeDocument`, `Platform`, `OsRelease`, `ToolProbe`, `UnoProbe`. `docker/probe.py` is unchanged.
- [ ] `cli.py` reads each model above where it reads the record today.

## Phase 4: apply the test decisions

One box per test file, worked in the order below, and one commit per box. Each commit passes
`./scripts/test.sh` and `./scripts/lint.sh`. A box applies every `DELETE` and `FIX` row of its
file under [`plan_tests/`](plan_tests), the source change a row names, and the `docs/` sentences
its rows add, which the box lists. A test a row moves into another file is written by the box of
the file that receives it and deleted by the box of the file that loses it, and the receiving
file's box comes first. The same holds for a test deleted in favour of one another box writes: that
box comes first, which is why `tests/integration/test_pytest_image.py` precedes
`tests/unit/test_preflight.py` and `tests/integration/test_cli.py` precedes
`tests/integration/test_docker.py`. The "Decisions" table overrides any row it contradicts.

- [ ] [`tests/conftest.py`](plan_tests/conftest.md), and the new `tests/unit/conftest.py` with the shared helpers that file's rows propose.
- [ ] [`tests/integration/conftest.py`](plan_tests/integration_conftest.md), with `Config.dump` users and the `images` fixture.
- [ ] [`tests/data/`](plan_tests/data.md): add every proposed fixture and fix every `FIX` fixture. Deletion of unread fixtures is the last box of this phase.
- [ ] [`tests/unit/test_cases.py`](plan_tests/unit_test_cases.md)
- [ ] [`tests/unit/test_results.py`](plan_tests/unit_test_results.md)
- [ ] [`tests/unit/test_validate.py`](plan_tests/unit_test_validate.md), with the `_check_violations` change and the `duplicate-checks` case the "Decisions" table names.
- [ ] [`tests/unit/test_checks.py`](plan_tests/unit_test_checks.md). Docs: `docs/checks.md` "The Run object" (a missing `last_message.txt` reads as `""`), a new advisory section in `docs/checks.md`, and `docs/checks_layer.md` "What reaches the result document" (a missing or unparseable document gives no warning and is left unchanged).
- [ ] [`tests/unit/test_cowork.py`](plan_tests/unit_test_cowork.md)
- [ ] [`tests/unit/test_cowork_backend.py`](plan_tests/unit_test_cowork_backend.md)
- [ ] [`tests/unit/test_grader.py`](plan_tests/unit_test_grader.md)
- [ ] [`tests/unit/test_judge.py`](plan_tests/unit_test_judge.md), with the `judge.truncate` fix. Docs: `docs/cowork_backend.md` "The judge" (`--json-schema`, `structured_output`, the reasoning in `explanation`).
- [ ] [`tests/unit/test_harness.py`](plan_tests/unit_test_harness.md)
- [ ] [`tests/unit/test_config.py`](plan_tests/unit_test_config.md). Docs: `docs/docker.md` "The three lists" (the variable-name shape refusal).
- [ ] [`tests/unit/test_docker.py`](plan_tests/unit_test_docker.md). Docs: `docs/docker.md` "Environment passthrough" (the Bedrock names in the conditions table).
- [ ] [`tests/unit/test_parity.py`](plan_tests/unit_test_parity.md)
- [ ] [`tests/unit/test_pytest_image.py`](plan_tests/unit_test_pytest_image.md)
- [ ] [`tests/integration/test_pytest_image.py`](plan_tests/integration_test_pytest_image.md)
- [ ] [`tests/unit/test_preflight.py`](plan_tests/unit_test_preflight.md), with `preflight.checks_all` deleted.
- [ ] [`tests/unit/test_logs.py`](plan_tests/unit_test_logs.md). Docs: `docs/running_evals.md` "What a run leaves behind" (the `image` line on `--docker` only, and the `session_env` and `keep_env` lines).
- [ ] [`tests/unit/test_traces.py`](plan_tests/unit_test_traces.md)
- [ ] [`tests/unit/test_verdict.py`](plan_tests/unit_test_verdict.md)
- [ ] [`tests/unit/test_panel.py`](plan_tests/unit_test_panel.md)
- [ ] [`tests/unit/test_environments.py`](plan_tests/unit_test_environments.md)
- [ ] [`tests/unit/test_resources.py`](plan_tests/unit_test_resources.md). Docs: `docs/cli.md` "docs" (the name escape).
- [ ] [`tests/unit/test_cli_docs_init.py`](plan_tests/unit_test_cli_docs_init.md) and [`tests/unit/test_cli.py`](plan_tests/unit_test_cli.md) in one commit, which merges the first file into the second. Docs: `docs/cli.md` "Synopsis" (`--version`).
- [ ] [`tests/integration/test_cowork.py`](plan_tests/integration_test_cowork.md)
- [ ] [`tests/integration/test_cowork_backend.py`](plan_tests/integration_test_cowork_backend.md)
- [ ] [`tests/integration/test_judge.py`](plan_tests/integration_test_judge.md)
- [ ] [`tests/integration/test_cli.py`](plan_tests/integration_test_cli.md)
- [ ] [`tests/integration/test_docker.py`](plan_tests/integration_test_docker.md). Docs: `docs/docker.md` "The mechanism" step 5 (a line that is not a shell name is skipped) and "The Bash sandbox" (the `--proc` mount and the `/run/shm` tmpfs).
- [ ] Delete every fixture under `tests/data/` that `data.md` lists for deletion, and every other file there that no test reads. `grep` for each path under `tests/` returns nothing before it is deleted.
- [ ] Line count. Each test file is shorter than its unit: the module of the same name under `src/cowork_evals/` (`docker/__init__.py` for `test_docker.py`, `docker/parity.py` for `test_parity.py`, `docker/pytest_image.py` for `test_pytest_image.py`), and `requirements.py` with `scripts/*.sh` for `test_environments.py`. `tests/` as a whole is shorter than `src/cowork_evals/`. A file that is longer gets new rows in its `plan_tests/` file, the developer approves them, and they are applied before this box is ticked.
- [ ] `./scripts/test.sh -m integration` passes.

## Phase 5: documentation

- [ ] `tests/README.md`: the file table lists the files that remain, `tests/unit/conftest.py` included. Every test count, test name and fixture name in its tier sections and in "The live marker" matches the tests that remain, and every sentence a `plan_tests/` row changes there is written. It states two rules of this plan: one test per requirement, and each test file shorter than its unit. For typed data it links to `CLAUDE.md`.
- [ ] `CLAUDE.md` working rules: structured data is a dataclass or a Pydantic model in all code in the repository. JSON is parsed into a model when it is read and serialised from one when it is written.

## Decisions

Decided by Claude on 2026-10-09 at the developer's instruction ("decide"). Revised on 2026-10-09 in a review the developer ordered to fix every defect in the plan without asking: the `monkeypatch` row, the second test in "Self-computed digest", and the `_check_violations` sentence come from it. Each line settles one conflict or open point in the assessment tables, and overrides any row it contradicts. [`plan_models.md`](plan_models.md) is the one source for every model's fields and types; a field list in an assessment row names only what that test touches.

| Point | Decision |
| ----- | -------- |
| Extension test | Keep the `test_cli_docs_init.py` copy, which goes through the verb. It moves into `test_cli.py` with the file merge. |
| Unmet passthrough name | Keep `test_docker.py::test_the_conditions_reach_the_whole_check`. The `test_preflight.py` copy goes. |
| Ceiling filters | Keep `test_preflight.py::test_the_ceiling_reads_the_filters_it_is_given`. The `test_cowork_backend.py` copy goes. |
| `max_turns` reason text | `test_cowork_backend.py` asserts the exact text. `test_validate.py` asserts the suffix only. |
| `costUsd` of a declared suite | `test_cowork_backend.py` keeps `costUsd == 0`. |
| Duplicate check names | Keep the rule. It is reachable: an unimportable file `x.y.py` is named `x.y`, the same as check `y` in `x.py`. Phase 4 adds that fixture case under `tests/data/validate/broken/` and the `check-duplicate` pair to the literal list in `test_validate.py`. `test_checks.py::test_a_duplicate_name_within_one_case_is_reported` is deleted. `validate._check_violations` stops returning before the duplicate rule on an import error, so `check-import` and `check-duplicate` are both reported. |
| `tests/conftest.py` | Keep it for fixtures both tiers use (`repository`, `working_directory`, the pytest-image `plugin`). Unit-only helpers go in a new `tests/unit/conftest.py`. `tests/README.md` names both. |
| `results.Run` reuse | `RunEntry` and `CaseEntry` replace `results.Run` and `CaseResult`. One model reads and writes. |
| Snapshot rows | Type `panel.Row` and `Cell` with aliases. No `SnapshotRow`. |
| `SessionDocument.tool_names` | A plain field. A model validator asserts it equals the names of `tool_calls`. The fixtures keep the key. `extra="forbid"`. |
| `SessionDocument.prompt_sha256` | `str \| None`, as `collect` writes it. |
| Result document extras | `extra="allow"`. Unknown keys are read and written back unchanged. |
| Lenient case reader | The validator keeps reading the raw mappings `Case.frontmatter_keys` and `Case.case_yaml_keys`, because a wrong type is its output, not a read error. Every other caller reads the `Case.frontmatter` and `Case.case_yaml` properties, which build `PromptFrontmatter` and `CaseYaml` and raise `CaseError` on a mapping that does not validate. |
| Grader of unknown type | `type: str` and `config: None`. |
| `ProbeDocument` writer | The model lives in `parity.py`. `probe.py` stays standard library and writes plain JSON. |
| `Config.dump` | Add it to `config.py`. Tests use it to write configuration from a `Config`. |
| Audit records | Type them as `AuditRecord`. |
| Advisory checks | Add the advisory section to `docs/checks.md`. |
| Evidence cap | Fix `judge.truncate` so the result is at most 2000 characters, as `docs/checks.md` says. |
| Credential names | Add the Bedrock names to the conditions table in `docs/docker.md` "Environment passthrough". |
| Judge reply shape | Document `--json-schema`, `structured_output` and the reasoning in `explanation` in `docs/cowork_backend.md` "The judge". |
| `env.txt` kept names | Document the `session_env` and `keep_env` lines in `docs/running_evals.md`. They are `RunEnvironment` fields under test. The two DELETE rows become FIX. |
| `env.txt` image line | State in `docs/running_evals.md` that it is written on `--docker` only. |
| Variable-name shape | State the refusal in `docs/docker.md` "The three lists". |
| Name escape in `docs` | Add the sentence to `docs/cli.md` "docs". |
| Non-shell line in the keep file | Add the sentence to `docs/docker.md` "The mechanism" step 5. The row stays FIX. |
| Missing `last_message.txt` | State in `docs/checks.md` "The Run object" that it reads as `""`. Keep the test. |
| Unreadable document in the checks layer | State in `docs/checks_layer.md` "What reaches the result document" that a missing or unparseable document gives no warning and is left unchanged. Keep the test. |
| Self-computed digest | Exception approved for `unit/test_pytest_image.py`'s four-inputs digest test and for `unit/test_docker.py::test_the_script_is_hashed_into_the_digest` with its `digest_over` helper: no other route reaches the file inputs without a patch, and without the second `docs/docker.md` "The mechanism" (the script is in the image digest) has no test. |
| `monkeypatch` | `setenv` and `delenv` set the real process environment that `Docker` and `preflight` read, and replace no code, so they stay. `setattr`, `setitem` and `syspath_prepend` replace code or module state and appear in no test. A test changes its working directory only through the `working_directory` fixture, never `monkeypatch.chdir`. A test that runs the executable passes `env=` to `subprocess.run` instead of `setenv`. |
| `preflight.checks_all` | Delete it. |
| Terminal half of capture | Add the `capfd` assertion on descriptor 1. |
| Code 9 guard | Keep the DELETE. Its reason is that the test parses a document and runs no code. |
| Judge spend through the layer | The unit test of `add_spend` alone. No new paid integration test. |
