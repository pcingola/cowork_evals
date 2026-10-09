# `tests/unit/test_verdict.py`

Assessment for [`../plan_tests.md`](../plan_tests.md). Model names refer to [`../plan_models.md`](../plan_models.md).

| Test | Verdict | Requirement | What to do |
| ---- | ------- | ----------- | ---------- |
| `run_directory` (helper) | OK | none (fixture builder) | Copies files from `tests/data/results/` and builds no dict. |
| `with_trace` (helper) | FIX | none (fixture builder) | It does `json.loads`, then `run["tracePath"] = ...`, then `json.dumps` on a dict. Parse the file into a result document model, replace `trace_path` on each with-arm run, and serialise it from the model. **needs model `ResultDocument`**, whose `CaseEntry` and `RunEntry` replace `results.CaseResult` and `results.Run` and both read and write. Fields it touches: `cases[].arms.with[].tracePath`. |
| `collected` (helper) | OK | none | Writes a trace file in the layout `traces.py` leaves. |
| `judge` (helper) | OK | none | Thin wrapper around `decide` with default counts. |
| `failures`, `notes` (helpers) | OK | none | Filter lines by tag. |
| `outcomes` (helper) | OK | none | Projects `CaseOutcome` to `(name, outcome)`. |
| `test_a_passing_document_passes` | OK | running_evals.md "Pass and fail", row "Otherwise" | Keep. |
| `test_the_summary_is_the_last_line` | DELETE | running_evals.md "The last line" | `test_picked_and_ran_differing_is_not_a_failure` asserts the full `lines[-1]` literal on the same `pass` fixture with other counts, and `test_the_last_line_carries_the_five_counts` asserts it on another fixture. |
| `test_the_text_is_one_line_per_entry` | DELETE | none | Asserts that `Verdict.text` joins lines with `\n`. That is implementation shape, and no doc states it. |
| `test_an_empty_document_passes` | OK | running_evals.md "Pass and fail", row "`casesTotal` is 0" | Keep. |
| `test_every_structural_grader_failure_is_a_failure` | FIX | running_evals.md "Pass and fail", row 1 | Merge with `test_every_judged_grader_failure_is_a_failure` and `test_a_failed_check_fails_the_run_like_a_structural_grader` into one test parametrised over (fixture, expected FAIL lines): `structural_failures`, `judged_failure`, `check_failure`. Each case asserts `not passed`, the exact failure lines and `notes == []`. |
| `test_every_judged_grader_failure_is_a_failure` | FIX | running_evals.md "Pass and fail", row 1 | Becomes the `judged_failure` case of the parametrised test above. |
| `test_a_failed_check_fails_the_run_like_a_structural_grader` | FIX | running_evals.md "Pass and fail", row 1; checks.md "The verdict and the harness table" | Becomes the `check_failure` case of the parametrised test above. |
| `test_a_grader_result_is_joined_to_its_definition_by_name` | OK | running_evals.md "Pass and fail", row "naming no grader"; run_pipeline.md "The verdict" | Keep. |
| `test_a_declared_case_is_counted_and_the_suite_passes` | OK | running_evals.md "Pass and fail", row "declared `no-cowork`"; "The last line" | Keep. |
| `test_a_skipped_case_fails_with_its_reason` | OK | running_evals.md "Pass and fail", row "case or grader reported skipped" | Keep. |
| `test_a_skipped_grader_and_an_unscored_one_each_fail` | OK | running_evals.md "Pass and fail", rows "skipped" and "`scored: false` on a one-arm run" | Keep. It is the one-arm test of `scored: false`. |
| `test_partial_fails_whatever_the_reason_says` | OK | running_evals.md "Pass and fail", row "`partial: true`" | Keep. |
| `test_a_run_carrying_an_error_fails_under_an_otherwise_passing_document` | OK | running_evals.md "Pass and fail", row "A run carrying `error`" | Keep. |
| `test_a_missing_document_is_a_failure_naming_the_path` | FIX | running_evals.md "Pass and fail", row "missing, unparsable, or another `schemaVersion`" | Merge with the unparsable test, the wrong-schema test and `test_a_document_that_cannot_be_read_records_no_outcome` into one test parametrised over (fixture, expected line prefix): `None`, `unparsable`, `wrong_schema`. Each case asserts `not passed`, the line prefix and `outcomes == ()`. |
| `test_an_unparsable_document_is_a_failure_naming_the_path` | FIX | same as above | Becomes the `unparsable` case of the parametrised test above. |
| `test_a_document_of_another_schema_version_is_a_failure` | FIX | same as above | Becomes the `wrong_schema` case of the parametrised test above. |
| `test_an_unknown_field_is_ignored` | OK | run_pipeline.md "The verdict" (reads `schemaVersion: 1`, tolerates unknown fields) | Keep. It replaces a string in the file and touches no dict. |
| `test_an_extra_line_is_a_failure_the_caller_already_had` | OK | running_evals.md "Pass and fail", row "sweep stopped by `eval.max_cost_total_usd`" | Keep. |
| `test_two_plugins_are_gated_once` | OK | running_evals.md "Pass and fail" ("decides once for the whole invocation"); "The last line" | Keep. |
| `test_two_passing_plugins_are_one_pass` | DELETE | same as above | `test_two_plugins_are_gated_once` already proves one decision over two documents, plus the mean score and the pass count. This adds only an all-pass variant. |
| `test_a_structural_failure_names_the_run_artefacts` | FIX | running_evals.md "The last line" (`[artifacts: <dir>]` on a failed grader, note or errored run) | Merge with the judged, errored, denial and check-scratch artefact tests into one test parametrised over (fixture, case dir): `structural_failures`/`every-structural`, `judged_failure`/`judged`, `run_error`/`timed-out`, `mode_denial`/`tool-denied`, `check_failure`/`checked-file`. Each case asserts that the first failure line ends with `[artifacts: smoke/traces/<case>/run-1]`. Uses `with_trace` once that helper is typed. |
| `test_a_judged_failure_names_them_too` | FIX | same as above | Becomes the `judged_failure` case of the parametrised test above. |
| `test_an_errored_run_names_them` | FIX | same as above | Becomes the `run_error` case of the parametrised test above. Replace `any(... in line)` with an exact `endswith` on the error line. |
| `test_a_denial_line_names_the_directory_holding_the_trace` | FIX | same as above | Becomes the `mode_denial` case of the parametrised test above. |
| `test_a_failed_check_names_the_directory_holding_its_scratch` | DELETE | same as above | Its last two asserts check the `scratch/` and `checks.jsonl` the test itself just created, so they are tautological. Its `endswith` is covered by the `check_failure` case of the parametrised test above. |
| `test_a_document_whose_trace_was_not_collected_names_nothing` | FIX | running_evals.md "The last line" ("when it is on disk") | Merge with `test_a_document_carrying_no_trace_path_names_nothing` into one test parametrised over the `tracePath` state: absent, or naming a directory that does not exist. Each case asserts that the line ends `no match for Alex`. Uses `with_trace` through `ResultDocument`. |
| `test_a_document_carrying_no_trace_path_names_nothing` | FIX | same as above | Becomes the "absent" case of the parametrised test above. |
| `test_a_one_arm_document_carries_no_delta_on_the_summary_line` | DELETE | running_evals.md "The last line" | `test_picked_and_ran_differing_is_not_a_failure` and `test_the_last_line_carries_the_five_counts` assert the full one-arm summary literal, which has no delta. |
| `test_a_delta_above_the_threshold_passes_and_the_mean_is_on_the_line` | OK | running_evals.md "Ablation"; "The last line" (mean delta) | Keep. Its `quiet-case` has delta 0, so it covers the at-threshold case too. |
| `test_a_delta_below_the_threshold_fails_and_the_line_names_both_scores` | OK | running_evals.md "Pass and fail", row "delta is below `eval.delta_threshold`"; "Ablation" | Keep. |
| `test_a_delta_at_the_threshold_passes` | DELETE | running_evals.md "Ablation" | The same call on the same fixture as `test_a_delta_above_the_threshold_passes_and_the_mean_is_on_the_line`, with a weaker assertion. |
| `test_a_raised_threshold_fails_the_case_that_changed_nothing` | OK | running_evals.md "Pass and fail" / "Ablation" (`eval.delta_threshold`) | Keep. |
| `test_a_two_arm_case_whose_baseline_arm_ran_nothing_fails` | FIX | running_evals.md "Ablation" (two-arm case with no delta, two reasons); "The last line" (`mean delta none`) | Merge with `test_a_two_arm_case_graded_under_different_rules_fails_and_says_so` into one test parametrised over (fixture, expected FAIL line): `two_arm_no_baseline`, `two_arm_skipped_paid`. Each case also asserts that `lines[-1]` ends `mean delta none`. |
| `test_a_two_arm_case_graded_under_different_rules_fails_and_says_so` | FIX | same as above | Becomes the `two_arm_skipped_paid` case of the parametrised test above. |
| `test_an_unscored_grader_fails_one_arm_and_is_an_indicator_on_two` | FIX | running_evals.md "Pass and fail", row "`scored: false` on a two-arm run" | Drop the one-arm half, which repeats `test_a_skipped_grader_and_an_unscored_one_each_fail` on the same fixture. Keep the two-arm half (`passed` and the exact `NOTE` line). |
| `test_a_case_whose_graders_are_all_with_only_is_scored_normally` | OK | running_evals.md "Ablation" ("all with-only ... arrives with `scored: true`") | Keep. |
| `test_a_mode_denial_fails_a_document_whose_graders_all_passed` | FIX | running_evals.md "A run that never had the tool" | Merge with `test_a_tool_that_was_never_offered_fails_the_same_way` into one test parametrised over (fixture, expected FAIL line): `mode_denial`, `tool_not_offered`. |
| `test_a_tool_that_was_never_offered_fails_the_same_way` | FIX | same as above | Becomes the `tool_not_offered` case of the parametrised test above. |
| `test_a_document_carrying_neither_field_passes` | DELETE | running_evals.md "A run that never had the tool" | Byte-identical in effect to `test_a_passing_document_passes`: same fixture, same assertion. |
| `test_the_last_line_carries_the_five_counts` | OK | running_evals.md "The last line" | Keep. It also proves that `passed` is not `casesPassed`, because this fixture's `casesPassed` is 1 and the line says 0 passed. |
| `test_the_pass_count_is_not_read_back_from_the_document` | DELETE | running_evals.md "The last line" (`passed` is not `casesPassed`) | Same fixture and same `0 passed` as `test_the_last_line_carries_the_five_counts`. Its first assert reads the fixture as a dict and checks the fixture, not the code. |
| `test_the_last_line_says_when_a_sweep_stopped_early` | OK | running_evals.md "The last line" (`stopped early`) | Keep. |
| `test_picked_and_ran_differing_is_not_a_failure` | OK | running_evals.md "The last line" ("Neither count is checked against the other") | Keep. |
| `test_a_passing_case_is_recorded_as_a_pass` | FIX | case_history.md "Summary" (`outcome` is the word the verdict reached); panel.md "The records", `outcome` | Merge with the fail, declared, judged-alone, two-arm and below-threshold outcome tests into one test parametrised over (fixture, delta_threshold, expected `outcomes`): `pass`, `structural_failures`, `declared_case`, `judged_failure`, `two_arm`, `two_arm_below_threshold`. Drop the incidental `failures(...)` asserts, which repeat the pass/fail tests. |
| `test_a_failing_case_is_recorded_as_a_fail_beside_its_lines` | FIX | same as above | Becomes a case of the parametrised outcome test above. |
| `test_a_declared_case_is_recorded_as_declared` | FIX | same as above | Becomes a case of the parametrised outcome test above. |
| `test_a_judged_failure_alone_is_a_fail` | FIX | same as above | Becomes a case of the parametrised outcome test above. Its summary-line assert repeats `test_the_last_line_carries_the_five_counts`; drop it. |
| `test_a_two_arm_document_records_one_outcome_per_case` | FIX | same as above | Becomes a case of the parametrised outcome test above. |
| `test_a_two_arm_case_below_the_threshold_is_recorded_as_a_fail` | FIX | same as above | Becomes a case of the parametrised outcome test above, with threshold 0. The fixture's delta is -0.25, so the `delta_threshold=0.5` override is not needed. |
| `test_an_outcome_carries_the_pair_that_identifies_the_case` | OK | panel.md "The records" (`case`, `dir`) | Keep. |
| `test_a_document_that_cannot_be_read_records_no_outcome` | DELETE | case_history.md "Summary" | Its `outcomes == ()` assert is folded into the parametrised missing/unparsable/wrong-schema test. |
| `test_a_failed_advisory_check_is_a_note_and_fails_nothing` | FIX | running_evals.md "Pass and fail" (a note is a failed advisory check, never exit 1); run_pipeline.md "The verdict" (join by name to learn the type) | Replace the `json.loads` and `definition["type"] = ADVISORY_TYPE` dict mutation with a new hand-written fixture `tests/data/results/check_advisory_failure.json`: a copy of `check_failure.json` whose check definition has `"type": "check-advisory"`. Keep the three asserts. Remove the `ADVISORY_TYPE` import, which nothing else uses. |

Keep the file and do not merge or delete it: it is the one file for `verdict.py`. Line counts: `tests/unit/test_verdict.py` 572 lines, `src/cowork_evals/verdict.py` 532 lines; the test file is longer than its unit, and the merges above bring it under.
