# `tests/unit/test_harness.py`

Assessment for [`../plan_tests.md`](../plan_tests.20261010.md). Model names refer to [`../plan_models.md`](../plan_models.20261010.md).

| Test | Verdict | Requirement | What to do |
| ---- | ------- | ----------- | ---------- |
| `options(**overrides)` (helper) | FIX | none | Replace the kwargs dict with one base `RunOptions(...)` literal and `dataclasses.replace(BASE, **overrides)`. `test_docker.py::run_options` is a near-copy: move the one base `RunOptions` to `tests/unit/conftest.py` for both. |
| `value_after(argv, flag)` (helper) | OK | none | Keep. |
| `test_the_built_in_defaults_apply_when_the_file_carries_no_eval_section` | FIX | `docs/library.md` "The precedence ladder"; `docs/run_pipeline.md` "Pinned flags" | Expected `allow_tools` is computed by the code. Merge into one parametrised `test_each_option_resolves_argument_over_file_over_default`, one case per field (`model`, `judge_model`, `ablation`, `max_cost_usd`, `allow_tools`, `keep_traces`), literal values on all three rungs. Delete this function. |
| `test_the_configured_value_beats_the_default` | FIX | `docs/library.md` "The precedence ladder" | Merge into the ladder test; delete. |
| `test_an_explicit_argument_beats_the_configured_value` | FIX | `docs/library.md` "The precedence ladder" | Merge into the ladder test; delete. |
| `test_an_omitted_config_is_read_from_the_working_directory` | FIX | `docs/library.md` "The two roots" | The ladder test's file rung writes `cowork_evals.yaml` to `tmp_path` with `Config.dump`, from a `Config` carrying the case's file value, and calls `RunOptions.resolve()` under `working_directory`. Delete this function. The cwd read is repeated in `test_config.py`, `test_docker.py` and `test_judge.py`; judged there. |
| `test_the_traces_are_kept_unless_the_file_turns_them_off` | FIX | `docs/run_pipeline.md` "Pinned flags" (`eval.keep_traces`) | The `keep_traces` case of the ladder test; delete. |
| `test_either_form_of_the_traces_argument_beats_the_file` | FIX | `docs/library.md` "The precedence ladder"; `docs/cli.md` "Options on run" (`--[no-]keep-traces`, either form beats the file) | The ladder test carries a second `keep_traces` case: a `False` argument over a `True` file gives `False`. The first case covers a `True` argument over a `False` file. Delete this function. |
| `test_a_whole_cost_is_emitted_without_a_decimal_point` | FIX | `docs/run_pipeline.md` "Pinned flags" (`--max-cost-usd`) | "No decimal point" is stated nowhere. Keep only the values as the `max_cost_usd` case of the ladder test (default `"5"`, file `2.5` → `"2.5"`, argument wins); delete. |
| `test_the_target_comes_before_every_variadic_flag` | OK | `docs/run_pipeline.md` "Pinned flags"; `docs/docker.md` "The command line" | Keep. |
| `test_the_debug_file_goes_before_the_subcommand` | OK | `docs/run_pipeline.md` "Logs" | Keep. Owner of the requirement. |
| `test_every_always_pinned_flag_is_emitted` | FIX | `docs/run_pipeline.md` "Pinned flags" | Every checked value is the default. Use non-default values (`model="opus"`, `judge_model="sonnet"`, `ablation="with-without"`, `max_cost_usd="2.5"`, `allow_tools=("Bash","Write")`) and assert literals. Absorbs the ablation and widened `allow_tools` tests. Keep `--threshold "0"`. |
| `test_json_is_never_emitted` | FIX | `docs/run_pipeline.md` "Pinned flags" (`--json` is never passed) | Add `"--json"` to `test_nothing_unasked_is_emitted`; delete this function. |
| `test_the_threshold_cannot_be_overridden` | DELETE | `docs/run_pipeline.md` "Pinned flags" | `hasattr` asserts dataclass shape; the argv check repeats the pinned-flag test. |
| `test_the_ablation_is_the_resolved_option` | FIX | `docs/run_pipeline.md` "Pinned flags" | Merged into the pinned-flag test; delete. |
| `test_the_ablation_is_off_unless_the_file_or_the_argument_turns_it_on` | FIX | `docs/library.md` "The precedence ladder"; `docs/run_pipeline.md` "Pinned flags" (`eval.ablation`) | The `ablation` case of the ladder test; delete. |
| `test_nothing_unasked_is_emitted` | FIX | `docs/run_pipeline.md` "Pinned flags"; `docs/docker.md` "The command line" | Add `--json`. Otherwise unchanged. |
| `test_keep_temp_is_emitted_when_the_run_keeps_its_traces` | FIX | `docs/run_pipeline.md` "Pinned flags" (`--keep-temp`) | Merge with the next test: parametrise over `keep_traces`, assert `("--keep-temp" in argv) is keep_traces`. |
| `test_keep_temp_is_not_emitted_when_the_traces_are_turned_off` | FIX | `docs/run_pipeline.md` "Pinned flags" | Merged above; delete. |
| `test_the_optional_flags_are_emitted_when_asked` | OK | `docs/cli.md` "Options on run"; `docs/run_pipeline.md` "Pinned flags" | Keep. |
| `test_a_widened_allow_tools_replaces_the_value` | DELETE | `docs/cli.md` "Options on run" (`--allow-tools` replaces the list) | Never exercises `resolve`. The ladder test's `allow_tools` case takes the replace rule: argument `("Read",)` over file `("Bash","Write")` gives `("Read",)`. |

Keep the file. Lines: 164 test vs 136 unit (`harness.py`); the merges bring it under.
