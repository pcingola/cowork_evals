# `tests/unit/test_preflight.py`

Assessment for [`../plan_tests.md`](../plan_tests.md). Model names refer to [`../plan_models.md`](../plan_models.md).

| Test | Verdict | Requirement | What to do |
| ---- | ------- | ----------- | ---------- |
| `configured` (helper) | OK | none | Keep. |
| `test_every_backend_returns_a_list_of_lines` | DELETE | none | Asserts return types. |
| `test_checks_all_covers_both_backends_in_order` | DELETE | none | Expected value from `preflight.checks`. `checks_all` has no caller in `src/`; delete it from `preflight.py` with this test. |
| `test_report_all_keeps_the_backend_each_line_belongs_to` | DELETE | `docs/cli.md` "check" | Expected value from code under test; `test_cli.py::test_check_all_names_every_backend_and_states_a_ready_one` covers it. |
| `test_report_all_and_checks_all_never_disagree_about_pass` | DELETE | none | Two internal functions agree; one is dead. |
| `test_the_test_verb_preflight_never_names_the_container_login` | DELETE | `docs/cli.md` "Preflight" (`test` never reads the container login) | Passes trivially on a ready machine. Both `check` methods run the `docker` CLI, so the requirement moves to the integration tier: `integration/test_pytest_image.py::test_check_reports_an_absent_image_and_never_the_credential` builds its absent configuration with an empty login dir under `tmp_path`, asserts `absent.docker.check()` reports `Condition.CREDENTIAL`, and asserts `absent.check()` does not. |
| `test_an_unknown_backend_is_refused` | DELETE | none | No doc states it; the parser refuses first. |
| `test_every_docker_line_names_the_command_that_fixes_it` | DELETE | `docs/cli.md` "Preflight" | Duplicate of `test_docker.py::test_the_remedy_for_*`; empty loop on a ready machine. |
| `test_no_configured_profile_is_one_line_carrying_its_message` | OK | `docs/cli.md` "Preflight" `--cowork` | Keep. |
| `test_an_unreadable_sessions_root_is_one_line_naming_it` | FIX | `docs/cli.md` "Preflight" `--cowork` | Merge with the next test, parametrised over `(sessions root created, expected lines)`. |
| `test_a_readable_sessions_root_reports_nothing` | FIX | same | Merged above. |
| `test_the_platform_is_reported_only_off_macos` | DELETE | `docs/cli.md` "Preflight" `--cowork` | Branches on `sys.platform` (an `if` bypass); the off-macOS branch compares output with itself. The off-macOS line is unreachable on the only platform the CoWork backend runs on without a patch, so it has no test. |
| `run_log` (helper) | FIX | `docs/cowork_driver.md` run log row | Writes run-log lines as dict literals, with outcome `collected`, which the documented outcome set does not hold. Delete it and use the one run-log writer in `tests/unit/conftest.py` (`conftest.md` "run log writer" row), which serialises `RunLogEntry` as its `plan_models.md` row gives, with outcome `submitted`. `test_cowork_backend.py::log` is the other copy it replaces. |
| `test_a_suite_inside_the_ceiling_reports_nothing` | FIX | `docs/cli.md` "Preflight"; `docs/cowork_backend.md` "The ceiling over a suite" | Merge with the next test, parametrised over `(recent, max_runs, expected lines)`. The arithmetic is checked in `test_cowork_backend.py`. |
| `test_a_suite_above_the_ceiling_is_one_line_carrying_the_arithmetic` | FIX | same | Merged above; keeps the literal refusal line. |
| `test_the_ceiling_reads_the_filters_it_is_given` | OK | `docs/cli.md` "Selecting cases"; `docs/cowork_backend.md` "The ceiling over a suite" | Keep. It is the one test that the filters reach the ceiling; the `test_cowork_backend.py` copy, `test_a_tag_filter_and_a_case_glob_reach_discovery`, goes. |
| `PROBE`, `FORWARDS` (constants) | OK | none | Keep. After the deletions below the forwarded-names test is their one user. |
| `test_an_absent_name_is_an_unmet_docker_condition` | DELETE | `docs/docker.md` "Environment passthrough" | Duplicate of `test_docker.py::test_the_conditions_reach_the_whole_check` ("Decisions" row "Unmet passthrough name"). |
| `test_an_empty_name_is_the_same_unmet_condition` | DELETE | same | Duplicate of the empty case of `test_docker.py::test_an_absent_name_is_one_unmet_condition_naming_it`. |
| `test_a_set_name_adds_no_line` | DELETE | same | Duplicate of `test_docker.py::test_a_value_is_read_once_and_not_again_at_container_start`, which asserts `check_environment() == []` for a set name. |
| `test_a_credential_name_is_refused_and_names_the_one_route` | DELETE | same; `docs/cli.md` "Preflight" | Duplicate of `test_docker.py::test_a_credential_name_is_refused_whatever_it_holds` and `::test_no_message_about_a_forwarded_variable_carries_its_value`. |
| `test_the_forwarded_names_are_the_container_backends_alone` | OK | `docs/docker.md` "Environment passthrough" (`env_passthrough` is a `docker:` key) | Keep. `monkeypatch.delenv` removes a real variable from this process, which is what `preflight.checks` reads; it replaces no code. |

Keep the file, cut to the profile, ceiling and forwarded-names tests. Lines: 208 test vs 140 unit (`preflight.py`).
