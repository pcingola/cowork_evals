# `tests/unit/test_cli.py`

Assessment for [`../plan_tests.md`](../plan_tests.20261010.md). Model names refer to [`../plan_models.md`](../plan_models.20261010.md).

| Test | Verdict | Requirement | What to do |
| --- | --- | --- | --- |
| `parse` (helper) | OK | none | Keep. |
| `settings` (helper) | OK | none | Keep. |
| `test_run_takes_a_backend_a_path_and_every_option` | DELETE | none | It only checks that argparse stores attributes. The dry-run and refusal tests exercise every option. |
| `test_the_traces_option_is_three_state` | DELETE | none | It checks argparse `BooleanOptionalAction`. The ladder test covers all three states. |
| `test_the_traces_option_reaches_the_harness_options` | DELETE | docs/library.md "The precedence ladder" | Duplicates the `_keeping` ladder test here and the `keep_traces` case of `test_harness.py::test_each_option_resolves_argument_over_file_over_default`. |
| `test_the_same_ladder_decides_it_on_either_backend[docker\|cowork]` | FIX | docs/library.md "The precedence ladder"; docs/cli.md "Options on run" | `_keeping` never reads the backend, so drop the backend parametrisation. Merge with `test_the_delta_threshold_option_beats_the_file` into one parametrised test over (resolver, argv, `EvalSection` field): option beats file, file beats default. |
| `test_run_defaults_every_option_to_nothing` | DELETE | none | It checks argparse defaults. The ladder test proves that an untyped option defers to the file. |
| `test_test_takes_a_path_two_flags_and_a_tail` | DELETE | none | argparse storage. The tail test and the `test` dry-run test cover it. |
| `test_ask_takes_cowork_a_prompt_and_its_four_options` | DELETE | none | argparse storage. The ask verb tests cover the options. |
| `test_ask_takes_no_case_option` | FIX | docs/ask.md "Options" | Move its five argvs into the merged usage-error table (see `test_an_unknown_option_is_a_usage_error`). |
| `test_ask_docker_is_a_usage_error` | FIX | docs/cli.md "Synopsis" | Merge into the usage-error table. |
| `test_ask_with_no_backend_is_a_usage_error` | FIX | docs/cli.md "Synopsis" | Merge into the usage-error table. |
| `test_setup_takes_docker_alone` | DELETE | none | argparse storage. |
| `test_login_takes_docker_alone_and_its_two_reports_are_exclusive` | FIX | docs/cli.md "login" | Delete the three positive parse asserts. Move the three refused argvs into the usage-error table. |
| `test_login_is_the_verb_a_missing_credential_names` | DELETE | docs/cli.md "login" | Duplicates the `CREDENTIAL` case of the merged remedy test in `test_docker.py` (from `test_the_remedy_for_a_missing_login_is_the_login_verb_and_not_the_setup_verb`). It is the `docker` unit, not cli. |
| `test_check_takes_both_backends_and_all` | DELETE | none | argparse storage. The `check` verb tests cover it. |
| `test_prune_takes_any_combination_of_its_selection_flags` | DELETE | none | argparse storage. |
| `test_prune_defaults_to_the_same_age_run_prunes_at` | DELETE | docs/cli.md "prune" (default 30) | Its expected value is `logs.RUN_PRUNE_DAYS`, which comes from the code under test. The merged prune-logs test proves the literal 30 instead. |
| `test_older_than_is_a_prune_flag_only` | FIX | docs/cli.md "Options on run" | Merge into the usage-error table. |
| `test_out_is_on_run_and_prune_and_nowhere_else` | FIX | docs/cli.md "test" | Drop the two positive asserts. Move `test --docker p --out x` into the usage-error table, and assert the code (the current version does not). |
| `test_the_tail_begins_at_the_separator_and_survives_token_for_token` | FIX | docs/cli.md "test" | Merge with the next test into one: `-- -k parser --dry-run --build-missing --tb=short` reaches `pytest_args` unchanged, and `dry_run` and `build_missing` stay False. |
| `test_argparse_claims_no_token_after_the_separator` | FIX | docs/cli.md "test" | Merged into the test above. |
| `test_run_takes_no_raw_tail` | FIX | docs/cli.md "test" | Merge into the usage-error table. |
| `test_a_verb_with_no_backend_is_a_usage_error` | FIX | docs/cli.md "Synopsis" | Merge into the usage-error table. |
| `test_run_with_no_path_is_a_usage_error` | FIX | docs/cli.md "Exit codes" | Merge into the usage-error table. |
| `test_two_backends_at_once_is_a_usage_error` | FIX | docs/cli.md "Synopsis" | Merge into the usage-error table. |
| `test_run_all_is_a_usage_error` | FIX | docs/cli.md "Synopsis" | Merge into the usage-error table. |
| `test_test_cowork_is_a_usage_error` | FIX | docs/cli.md "test" | Merge into the usage-error table. |
| `test_setup_cowork_is_a_usage_error` | FIX | docs/cli.md "setup" | Merge into the usage-error table. |
| `test_venv_is_an_unknown_option_on_every_verb` | FIX | docs/cli.md "Exit codes" | Merge into the usage-error table. |
| `test_an_unknown_option_is_a_usage_error` | FIX | docs/cli.md "Synopsis", "Exit codes" | Becomes the one parametrised usage-error test: `parse(*argv)` raises `SystemExit` with code `USAGE`. It takes every argv that a row of this file moves or merges into the usage-error table, plus `docs --docker` and `init --docker` from `test_cli_docs_init.py::test_neither_verb_accepts_a_backend`. |
| `test_the_cowork_backend_accepts_runs_judge_model_and_timeout_seconds` | FIX | docs/cli.md "Options on run" | It calls only `parse`, so it never checks acceptance. Merge into one parametrised accepted-surface test that asserts `cli.refusal(args) is None and cli.bad_value(args) is None` over each (backend, option) cell marked "yes" in the cli.md table. |
| `test_an_option_the_cowork_backend_refuses_returns_two[5 cases]` | FIX | docs/cli.md "Options on run" | Merge with `test_build_missing_is_refused_on_cowork` and `test_timeout_seconds_is_refused_on_docker` into one parametrised `main` test over (backend, option, value). That gives 7 cases, which is the `REFUSED` table written as literals. |
| `test_the_ablation_options_are_accepted_on_docker` | FIX | docs/cli.md "Options on run" | Parse only. Fold into the accepted-surface test. The unused `tmp_path` goes with it. |
| `test_an_unconfigured_repository_runs_one_arm` | DELETE | docs/cli.md "Options on run" (`--ablation` default `none`) | Duplicates `test_config.py::test_missing_file_yields_the_documented_defaults` (`ablation="none"`) and the `ablation` case of `test_harness.py::test_each_option_resolves_argument_over_file_over_default`. |
| `test_the_delta_threshold_option_beats_the_file` | FIX | docs/library.md "The precedence ladder" | Merge into the ladder test (see `test_the_same_ladder...`). |
| `test_an_unknown_ablation_value_is_refused_by_the_parser` | FIX | docs/cli.md "Exit codes" | Merge into the usage-error table. |
| `test_build_missing_is_refused_on_cowork` | FIX | docs/cli.md "Options on run" | Merge into the refused-option test. |
| `test_either_form_of_the_traces_option_is_accepted_on_both_backends[2]` | FIX | docs/cli.md "Options on run" | Parse only. Fold into the accepted-surface test. |
| `test_a_value_the_file_would_refuse_is_refused_on_the_command_line[5]` | FIX | docs/cli.md "Options on run" (checked by its setting's rule) | Add `--cowork --timeout-seconds -5` ("expected a number at or above zero") as a sixth case, and delete `test_the_cowork_timeout_is_checked_as_its_setting_is`. Each case carries its backend: the five existing cases run on `--docker`, the sixth on `--cowork`. |
| `test_the_option_and_the_file_refuse_the_same_value_for_the_same_reason` | DELETE | none | It tests `config.checked` and `EvalSection`, and asserts exact wording. The file side is the `eval.delta_threshold: 2` case of `test_config.py::test_a_wrongly_typed_value_raises`. The option side is the case above. |
| `test_a_value_the_file_accepts_is_accepted_on_the_command_line[4]` | FIX | docs/cli.md "Options on run" | Fold into the accepted-surface test. |
| `test_the_cowork_timeout_is_checked_as_its_setting_is` | FIX | docs/cli.md "Options on run" | Merged into the refused-value test. |
| `test_an_untyped_option_is_not_checked` | FIX | docs/cli.md "Options on run" | Fold into the accepted-surface test (`run --docker p` with no options, and `check --docker`). |
| `test_a_verb_that_does_not_carry_a_refused_option_refuses_nothing[3]` | FIX | docs/cli.md "check" | Fold into the accepted-surface test. |
| `test_timeout_seconds_is_refused_on_docker` | FIX | docs/cli.md "Options on run" | Merge into the refused-option test. |
| `test_require_coverage_is_accepted_on_both_backends` | FIX | docs/cli.md "Options on run" | Parse only. Fold into the accepted-surface test. |
| `test_the_version_is_the_installed_distribution_version` | FIX | docs/cli.md "Synopsis" (`--version`) | Its expected value is `logs.distribution_version()`, which is the code under test. Compare against `importlib.metadata.version("cowork-evals")`. Adds to docs/cli.md "Synopsis" the sentence: "`--version` prints the installed `cowork-evals` version and exits 0." |
| `test_no_verb_at_all_is_a_usage_error` | OK | docs/cli.md "Exit codes" | Keep. |
| `MARKETPLACE`/`VALIDATE`/`FIRST`/`SECOND`/`SMOKE`/`HISTORY` (constants) | OK | none | Keep. `test_a_violation_blocks...` and the declared-case test rebuild `VALIDATE` and a `cases/tree` path inline. Those tests go, and so do the inline paths. |
| `test_a_sweep_finds_every_plugin_root_below_the_path` | FIX | docs/cli.md "The path is the scope" | It tests `cases.plugin_roots`, so move it to tests/unit/test_cases.py. Merge it with the next two into one parametrised test over (path, expected roots). |
| `test_a_manifest_with_no_evals_sibling_is_not_a_plugin_root` | FIX | docs/cli.md "The path is the scope" | Merged into the test above. |
| `test_a_path_inside_one_root_is_that_root` | FIX | docs/cli.md "The path is the scope" | Merged into the test above. |
| `test_one_root_runs_the_path_as_it_was_typed` | FIX | docs/cli.md "The path is the scope" | Merge with the next test into one parametrised `_targets` test over (path, roots, expected pairs). |
| `test_a_sweep_runs_each_root_whole` | FIX | docs/cli.md "The path is the scope" | Merged into the test above. |
| `test_a_sweep_is_scoped_all_and_a_single_plugin_is_named` | DELETE | docs/cli.md "The path is the scope" | Duplicates the `all` and `evals/` cases of the merged parametrised scope test in `test_logs.py` (`logs.scope_name`). |
| `test_two_plugins_sharing_a_manifest_name_get_two_directories` | DELETE | docs/cli.md "The path is the scope" (`-2` suffix) | Duplicates `test_logs.py::test_two_plugins_sharing_a_name_get_two_directories` (`logs.plugin_dir` suffix). |
| `test_a_multi_plugin_path_is_refused_on_cowork` | FIX | docs/cli.md "The path is the scope" | Merge with the next two into one parametrised `main` test over (argv, message). |
| `test_a_multi_plugin_path_is_refused_on_test` | FIX | docs/cli.md "test" | Merged into the test above. |
| `test_a_path_with_no_plugin_root_above_it_is_a_usage_error` | FIX | docs/cli.md "The path is the scope" | Merged into the test above. |
| `test_a_selection_matching_nothing_anywhere_is_counted_as_zero` | FIX | docs/cli.md "What run refuses" | It asserts private `_selected` per branch. Replace it, the next test and `test_the_refusal_names...` with one parametrised test: `_run(parse("run","--docker",MARKETPLACE,"--tag",T,"--dry-run","--out",tmp),cfg)`. `T=nope` gives `USAGE` and stderr "selects no case under --tag nope". `T=plugin` gives `OK`. |
| `test_one_root_of_a_sweep_matching_nothing_is_not_zero` | FIX | docs/cli.md "What run refuses" | Merged into the test above. |
| `test_the_refusal_names_the_filters_that_matched_nothing` | FIX | docs/cli.md "What run refuses" | It asserts the exact string of private `_filters`. Merged into the test above. |
| `test_an_uncovered_skill_is_printed_and_fails_nothing` | DELETE | docs/cli.md "What run refuses" | Duplicates `test_an_uncovered_skill_prints_once_and_on_one_stream`, which goes through `_run`. |
| `test_require_coverage_turns_the_same_tree_into_a_refusal` | DELETE | docs/cli.md "What run refuses" | Duplicates `test_require_coverage_refuses_once_and_not_on_both_streams`. |
| `test_a_violation_blocks_whatever_the_coverage_flag_says` | DELETE | docs/cli.md "What run refuses" | Duplicates `test_a_dry_run_still_refuses_a_malformed_case`. |
| `test_the_docker_dry_run_prints_the_container_argument_list` | FIX | docs/cli.md "Dry run" | Its expected value comes from `Docker(config).run_argv`, which is the code under test. Merge with `test_the_docker_dry_run_creates_no_run_directory`, `test_the_docker_dry_run_prints_the_forwarded_name_and_not_its_value` and `test_a_dry_run_names_a_configured_variable_the_host_has_not_set` into one test through the executable, as the stdin test runs it (`sys.executable -c "from cowork_evals.cli import console_main; console_main()"`). It writes `FORWARDS` to `tmp_path / "cowork_evals.yaml"` and runs `run --docker FIRST/evals --dry-run --out tmp_path/logs` with `cwd=tmp_path` and `env=` the process environment with `PROBE` set to `PROBE_VALUE` in one case and removed in the other. Assert literals only: exit 0, first stdout line `# shared`, one line ending `:/work/logs:rw` whose host path is under `tmp_path/logs`, the line `PROBE=<not shown>`, `PROBE_VALUE` absent from stdout, `PROBE` absent from stderr, and `tmp_path/logs` absent. The variable reaches the child through `env=`, as the `plan_tests.md` Decisions `monkeypatch` row requires of a test that runs the executable. |
| `test_the_docker_dry_run_creates_no_run_directory` | FIX | docs/cli.md "Dry run" | Merged into the test above. |
| `PROBE`/`PROBE_VALUE`/`FORWARDS` (constants) | OK | none | Keep. They feed the merged test above through `env=` and a written `cowork_evals.yaml`. |
| `test_the_docker_dry_run_prints_the_forwarded_name_and_not_its_value` | FIX | docs/cli.md "Dry run"; docs/docker.md | Merged into the Docker dry-run test (the env-set case). It uses `monkeypatch.setenv`. |
| `test_a_dry_run_names_a_configured_variable_the_host_has_not_set` | FIX | docs/cli.md "Dry run" | Merged into the Docker dry-run test (the env-unset case). It uses `monkeypatch.delenv`. |
| `test_the_cowork_dry_run_prints_a_case_its_skips_and_the_arithmetic` | FIX | docs/cli.md "Dry run" | It calls the sub-helper `_dry_run` with hand-built targets. Go through `cli._run(parse("run", "--cowork", str(SECOND / "evals"), "--dry-run", "--out", str(tmp_path / "logs")), config)`. The literal expected lines stay. They hold only because `tests/data/cli/marketplace/second/skills/writer/` is deleted (`data.md`), so `_validate` prints no `uncovered:` line. |
| `test_the_cowork_dry_run_names_what_each_declared_case_declares` | DELETE | docs/cli.md "Dry run" | Duplicates the merged `_run --dry-run` test here (the `declared/one` case prints `declared:`) and `test_cowork_backend.py::test_a_context_key_in_case_yaml_is_a_reason` and `test_cowork_backend.py::test_the_tag_declares_every_reason_in_one_line` (the declared reasons). |
| `test_the_test_dry_run_prints_the_pytest_container_and_starts_none` | FIX | docs/cli.md "test" | Its expected value comes from `PytestImage(Config.load()).run_argv`, which is the code under test, and it reads the repository's own `cowork_evals.yaml`. Assert literals: exit 0, first line `docker`, one line naming `SMOKE / "tests"` as a mount source, last line `-q`. |
| `test_the_spend_is_summed_over_the_documents_written_so_far` | FIX | docs/running_evals.md "Cost" (`eval.max_cost_total_usd`) | It tests `results.spend`, so move it to tests/unit/test_results.py. Merge it with the next test into one parametrised test over (documents, total). |
| `test_a_directory_with_no_document_has_spent_nothing` | FIX | docs/running_evals.md "Cost" | Merged into the test above. |
| `test_a_ceiling_of_zero_stops_the_sweep_before_the_first_plugin` | OK | docs/running_evals.md "Pass and fail" (sweep stopped by `max_cost_total_usd`) | Keep. |
| `test_check_returns_three_and_names_every_unmet_condition` | FIX | docs/cli.md "check" | It runs the same invocation as `test_a_named_backend_keeps_its_unmet_lines_on_stderr`. Merge the two: code 3, unmet line on stderr, empty stdout. |
| `_plugin` (helper) | FIX | none | It writes a case tree and a `plugin.json` JSON literal at test time. Replace it with two hand-written trees under tests/data/cli/ (`portable/one/`, `declared/one/`), as tests/README.md requires for case trees. |
| `test_a_dry_run_validates_with_no_backend_reachable` | FIX | docs/cli.md "Dry run" | Merge with `test_a_dry_run_of_a_suite_that_declares_every_case_passes` and `test_the_same_suite_is_a_pass_on_docker_too` into one parametrised `_run --dry-run` test over (backend, tree, lines expected on stdout): (`--cowork`, `portable/one`, `1 submissions planned`), (`--cowork`, `declared/one`, `declared: no-cowork: allowed_tools` and `0 submissions planned`), (`--docker`, `declared/one`, none). Every case asserts exit 0 and an empty stderr. Pass `--out tmp_path/logs`. Without it, `_run` prunes the repository's own `logs/evals`. |
| `test_a_dry_run_still_refuses_a_malformed_case` | FIX | docs/cli.md "Dry run", "What run refuses" | Add `--out tmp_path/logs`. Replace `err.strip()` with the literal line `f"{VALIDATE}/broken/evals/greeter/bad-case-yaml/case.yaml: required-key: name is required"` in stderr. |
| `test_a_dry_run_of_a_suite_that_declares_every_case_passes` | FIX | docs/cli.md "Dry run" | Merged into the dry-run test above. |
| `test_the_same_suite_is_a_pass_on_docker_too` | FIX | docs/cli.md "Dry run"; docs/approaches.md | Merged into the dry-run test above. |
| `test_an_uncovered_skill_prints_once_and_on_one_stream` | FIX | docs/cli.md "What run refuses" | Merge with the next test into one parametrised test over (`--require-coverage` or not, exit code, the stream that carries `no eval directory`). Add `--out tmp_path/logs`. |
| `test_require_coverage_refuses_once_and_not_on_both_streams` | FIX | docs/cli.md "What run refuses" | Merged into the test above. |
| `test_check_all_names_every_backend_and_states_a_ready_one` | FIX | docs/cli.md "check" | Replace `preflight.BACKENDS` with the literals `("docker", "cowork")`. |
| `test_a_named_backend_keeps_its_unmet_lines_on_stderr` | FIX | docs/cli.md "check" | Merged into `test_check_returns_three...`. |
| `test_panel_takes_a_path_and_its_three_options` | DELETE | none | argparse storage. |
| `test_panel_takes_no_backend` | FIX | docs/cli.md "panel" | Merge into the usage-error table. |
| `test_panel_prints_one_row_per_case_under_the_path` | FIX | docs/panel.md "The columns"; docs/cli.md "panel" | Replace `list(panel.COLUMNS)` with the literal header. Replace `len(lines) == 6` with the five literal smoke case names. |
| `test_panel_writes_the_two_files_it_is_given` | FIX | docs/panel.md "The renders" | It reads the snapshot as a dict (`json.loads(...)["rows"]`). Parse it with `PanelSnapshot.model_validate_json` and assert `len(snapshot.rows) == 5`. |
| `test_a_panel_path_selecting_no_case_returns_two` | OK | docs/panel.md; docs/cli.md "panel" | Keep. |
| `test_an_unparsable_history_line_warns_and_leaves_the_exit_code_at_zero` | OK | docs/panel.md "The records" | Keep. |
| `test_prune_with_no_selection_flag_returns_two` | OK | docs/cli.md "prune" | Keep. |
| `test_prune_takes_history_beside_the_other_two` | DELETE | none | argparse storage. |
| `test_prune_history_deletes_a_record_under_the_panel_root` | FIX | docs/cli.md "prune"; docs/panel.md "Removing history" | It writes a history record as a dict literal through `panel.append`. Build one `HistoryRecord` with every required field as a literal (`schema_version=1`, `invocation`, `backend="docker"`, `cowork_evals`, `plugin="smoke"`, `case`, `dir="evals/plugin/one"`, `outcome="pass"`, `score=1.0`, `pass_rate=1.0`, `runs=1`, `duration_seconds`, `cost_usd`) and `started_at` 40 days old. `panel.append` takes `Sequence[HistoryRecord]`. |
| `test_prune_logs_deletes_under_the_resolved_root` | FIX | docs/cli.md "prune" | Merge with the next test into one parametrised `main(["prune","--logs","--out",root,*extra])` test over (age in days, `--older-than` or default, removed?). Include 31 days and 29 days under the default, which proves the literal 30. |
| `test_prune_logs_keeps_a_run_inside_the_age` | FIX | docs/cli.md "prune" | Merged into the test above. |
| `test_a_prune_keeps_the_current_digest_of_each_image` | FIX | docs/cli.md "prune" | Merge the three `_stale` tests into one parametrised test over (inventory, current, cutoff, expected). The inventory is a list of `Image(tag, created)`, which replaces the `(str, datetime)` tuples. |
| `test_a_prune_keeps_an_image_built_after_the_cutoff` | FIX | docs/cli.md "prune" | Merged into the test above. |
| `test_a_prune_of_nothing_removes_nothing` | FIX | docs/cli.md "prune" | Merged into the test above. |
| `SESSIONS`/`ONE_TURN`/`TOOL_CALL` (constants) | OK | none | Keep. Add `NO_TRANSCRIPT`, which two tests build inline. |
| `ask_settings` (helper) | OK | none | Keep. |
| `test_each_ask_refusal_returns_two_and_names_what_was_typed[4]` | OK | docs/ask.md "Usage errors" | Keep. |
| `test_a_session_on_disk_prints_the_answer_on_stdout_and_the_footer_on_stderr` | FIX | docs/ask.md "Output" | Merge with the next two into one parametrised `--session` test over (fixture, stdout, footer lines present, footer lines absent). |
| `test_a_footer_line_with_no_value_is_not_printed` | FIX | docs/ask.md "Output" | Same invocation as the test above. Merged. |
| `test_the_footer_names_every_tool_the_session_called` | FIX | docs/ask.md "Output" | Merged into the `--session` test above. |
| `test_json_prints_the_session_document_and_nothing_on_stderr` | FIX | docs/ask.md "Output" | It reads the session document as a dict. Parse stdout with `SessionDocument.model_validate_json` and assert `session_dir` and `final_text` on the model. `_ask_print` takes the `SessionDocument` too. |
| `test_a_session_directory_that_is_not_there_fails_and_says_so` | FIX | docs/ask.md "Exit codes" | Merge with the next test into one parametrised test over (directory, stderr substring), both `FAILED`. |
| `test_a_session_that_produced_no_assistant_text_fails_with_the_drivers_code` | FIX | docs/ask.md "Exit codes" | Merged into the test above. |
| `test_a_dry_run_prints_the_deep_link_carrying_the_encoded_prompt` | FIX | docs/ask.md "Output", "What one ask costs" | Merge with the next two into one test. The config names `profile: /nowhere-at-all` and the run log. Assert the deep-link literal on stdout, the arithmetic on stderr, no `no readable sessions root`, and no `runs.jsonl` written. |
| `test_a_dry_run_writes_no_run_log_entry` | FIX | docs/ask.md "What one ask costs" | Merged into the test above. |
| `test_a_dry_run_needs_no_profile_and_no_backend` | FIX | docs/ask.md "The preflight" | Merged into the test above. |
| `test_a_prompt_of_one_dash_is_read_from_standard_input` | OK | docs/ask.md "Options" | Keep. |
| `test_a_driver_refusal_reaches_the_preflight_code` | FIX | docs/ask.md "Exit codes"; docs/cli.md "Exit codes" (driver codes) | Merge all five `_ask_failure` tests into one parametrised test over (`CoWorkError` code, `session_dir`, exit, stdout, stderr substrings). |
| `test_every_other_driver_code_fails_and_prints_no_session_document` | FIX | docs/ask.md "Exit codes" | Merged into the test above. |
| `test_a_run_timeout_prints_what_the_session_produced_and_still_fails` | FIX | docs/ask.md "Exit codes" (code 7) | Merged into the test above. |
| `test_a_run_timeout_that_produced_no_text_prints_the_collection_failure` | FIX | docs/ask.md "Exit codes" (code 7) | Merged into the test above. |
| `test_a_run_timeout_with_no_session_directory_is_a_plain_failure` | FIX | docs/ask.md "Exit codes" | Merged into the test above. |
| `test_a_forwarded_variable_the_host_has_not_set_refuses_before_anything_is_created` (moved in from `tests/integration/test_cli.py`) | FIX | docs/cli.md "Preflight", "What run refuses"; docs/docker.md "Environment passthrough" | Call `cli._run(parse("run", "--docker", str(FIRST / "evals"), "--out", str(tmp_path / "logs")), settings(tmp_path, FORWARDS))` after `monkeypatch.delenv(PROBE, raising=False)`, which the Decisions `monkeypatch` row allows. Assert `PREFLIGHT_FAILED`, a stderr line naming `PROBE`, and `tmp_path / "logs"` absent. It is the one test of the `run` exit 3 for an unset forwarded name. |

Keep the file. It absorbs `tests/unit/test_cli_docs_init.py` (see that file's assessment) and the unset-forwarded-name test from `tests/integration/test_cli.py`. The `plugin_roots` tests move to tests/unit/test_cases.py and the `results.spend` tests move to tests/unit/test_results.py. Its length against `src/cowork_evals/cli.py` is checked in phase 4.
