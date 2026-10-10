# `tests/unit/test_pytest_image.py`

Assessment for [`../plan_tests.md`](../plan_tests.20261010.md). Model names refer to [`../plan_models.md`](../plan_models.20261010.md).

| Test | Verdict | Requirement | What to do |
| ---- | ------- | ----------- | ---------- |
| `build_arg` (helper) | DELETE | none | Copy of the `test_docker.py` helper; unused after the merges. |
| `image` (helper) | OK | none | Keep. |
| `plugin` (fixture) | FIX | `docs/cowork_test.md` "The container" | Near-copy of `integration/test_pytest_image.py::plugin`. Delete it and use the one `plugin` fixture in `tests/conftest.py` (`conftest.md`, `integration_test_pytest_image.md` `plugin` row). The argument lists below use `plugin.resolve()`, so the root's name does not matter. |
| `test_the_digest_is_twelve_hex_characters` | FIX | `docs/docker.md` "The test image" | Merge with the tag and no-`latest` tests: assert `tag == f"cowork-evals-test:{digest}"` and `re.fullmatch(r"cowork-evals-test:[0-9a-f]{12}", tag)`. |
| `test_the_digest_is_stable_across_instances` | DELETE | none | Tests sha256 determinism. |
| `test_a_rebuilt_base_is_a_different_test_tag` | FIX | `docs/docker.md` "The test image" | Merge with the platform test, parametrised over the input that changes. Drop the base-digest assertion (in `test_docker.py`). |
| `test_the_platform_is_in_the_digest` | FIX | same | Merged above. |
| `test_the_digest_hashes_the_base_the_dockerfile_the_pinned_list_and_the_platform` | FIX | `docs/docker.md` "The test image" | Merge with the next test: equality with `digest_of(...)` over the four inputs, then editing any one changes it. The equality uses code under test. This exception to the rule is approved, because no other route reaches the two file inputs without a patch. |
| `test_changing_any_one_of_the_four_changes_the_digest` | FIX | same | Merged above. |
| `test_the_test_digest_is_not_the_base_digest` | DELETE | none | Stated nowhere; implied by the four-inputs test. |
| `test_the_tag_names_the_digest_and_its_own_repository` | FIX | `docs/docker.md` "The test image" | Merged into the twelve-hex test. |
| `test_there_is_no_latest` | DELETE | `docs/docker.md` "The test image" | Proved by the tag equality. |
| `test_build_argv_*` (three tests) | FIX | `docs/docker.md` "The build context", "The test image" | Merge into one test asserting the whole literal build argv. |
| `test_build_argv_carries_no_build_secret` | DELETE | none | Stated only in a docstring. |
| `test_no_cache_is_off_unless_asked` | FIX | `docs/docker.md` (`--recreate` → `--no-cache`) | Second case of the whole-list build test. |
| `test_the_dockerfile_takes_its_base_from_the_build_argument` | OK | `docs/docker.md` "The test image" | Keep. |
| `test_the_dockerfile_installs_the_pinned_list_with_no_deps` | DELETE | `docs/docker.md` "The pinned list" | Greps the Dockerfile; the integration test checks the behaviour. |
| `test_run_argv_mounts_the_plugin_root_read_write`, `test_run_argv_carries_the_platform_the_uid_and_the_home`, `test_the_working_directory_is_the_plugin_root`, `test_the_command_is_pytest_over_the_resolved_target`, `test_run_argv_adds_no_pytest_option_of_its_own`, `test_run_argv_sets_no_pythonpath_and_no_enablement_variable`, `test_run_argv_carries_no_credential_mount_and_no_sandbox_option`, `test_run_argv_points_node_at_nothing_when_no_extra_ca_is_configured` | FIX | `docs/cowork_test.md` "The container"; `docs/docker.md` "The test container" | Merge into one test asserting the whole literal run argv with no extra CA configured. The literal list excludes every option these tests asserted absent. |
| `test_the_container_side_target_is_relative_to_the_plugin_root` | FIX | `docs/cowork_test.md` "The container" | Merge with the tail test, parametrised over `(target, pytest_args, expected tail)`. |
| `test_the_pytest_tail_is_forwarded_verbatim_and_last` | FIX | `docs/cowork_test.md` "What it adds" | Merged above. |
| `test_run_argv_carries_the_extra_ca_environment_when_one_is_configured` | OK | `docs/cowork_test.md` "The container" | Keep. |
| `test_a_target_under_no_plugin_raises` | DELETE | `docs/cli.md` "The path is the scope" | `run_argv` resolves the root through `cases.plugin_root`. `test_cases.py` and `test_cli.py::test_a_path_with_no_plugin_root_above_it_is_a_usage_error` (a case of the parametrised refusal test that `test_a_multi_plugin_path_is_refused_on_cowork` becomes) cover the behaviour, as for the deleted `test_docker.py` copy. |

Keep the file. Lines: 266 test vs 232 unit (`docker/pytest_image.py`); shorter after the merges.
