# `tests/unit/test_parity.py`

Assessment for [`../plan_tests.md`](../plan_tests.md). Model names refer to [`../plan_models.md`](../plan_models.md).

| Test | Verdict | Requirement | What to do |
| ---- | ------- | ----------- | ---------- |
| `probed` (helper) | FIX | `docs/docker.md` "Parity" | Parse the probe JSON with `ProbeDocument.model_validate_json` and pass the model to `compare()` and `report()`, which change to take it. `ProbeDocument`, `OsRelease`, `ToolProbe`, `UnoProbe` and `Platform` are as their `plan_models.md` rows give. `compare` touches `pip_freeze`, `npm_globals`, `node_path`, `tools` (`present`, `version`, `output`), `uno` (`imports`, `error`), `font_families`, `os_release` (`ID`, `VERSION_ID`) and `architecture`; `report` also touches `os_release.PRETTY_NAME`. `ProbeDocument` lives in `parity.py`, which parses the file with it. `probe.py` stays standard library and writes plain JSON. |
| `test_a_clean_probe_has_no_failures` | FIX | `docs/docker.md` "Parity" delta table, last row (the font family count is printed and does not fail); "Measurements" (non-Python deltas: none) | Absorb `test_a_build_suffix_in_the_tool_line_is_not_a_difference`: assert `probed("probe_clean") == ([], ["font families: 114, expected 118"])`. The whole literal holds no `tool version differs:` note, so the ImageMagick build suffix is covered. Uses `ProbeDocument` through `probed`. |
| `test_a_missing_pin_fails` | FIX | `docs/docker.md` delta table, "A pin is missing or at a different version" | Merge the seven failure tests into one, parametrised over `(fixture, expected failures literal)`. |
| `test_a_moved_pin_fails` | FIX | same row | Merge into the parametrised failure test. |
| `test_a_missing_npm_package_fails` | FIX | delta table, "A package of the second npm tree is missing or at a different version" | Merge into the parametrised failure test. |
| `test_a_moved_npm_package_fails` | FIX | same row | Merge into the parametrised failure test. |
| `test_a_node_path_that_does_not_name_the_tree_fails` | FIX | delta table, "`NODE_PATH` does not name the second npm tree" | Merge into the parametrised failure test. |
| `test_a_tool_recorded_as_absent_being_present_fails` | FIX | delta table, "A tool recorded as not present is present" | Merge into the parametrised failure test. |
| `test_import_uno_failing_fails` | FIX | delta table, "`import uno` fails" | Merge into the parametrised failure test. |
| `test_an_extra_package_is_printed_and_does_not_fail` | FIX | delta table, "A package is installed that is not a pin" | Merge the four notes tests into one, parametrised over `(fixture, expected note literal)`, asserting `failures == []` and the note in `notes`. Add a fifth case for the delta row "A tool recorded with a version is absent", which no test covers today: `(probe_tool_absent, "tool absent: pandoc, expected 2.9.2.1")`. Phase 4 writes `tests/data/docker/probe_tool_absent.json` as `probe_clean.json` with `tools.pandoc.present` false and `version` and `output` null. |
| `test_a_differing_tool_version_is_printed_and_does_not_fail` | FIX | delta table, "A non-Python tool version differs" | Merge into the parametrised notes test. |
| `test_an_extra_npm_package_is_printed_and_does_not_fail` | FIX | delta table, "The second npm tree holds a package not recorded" | Merge into the parametrised notes test. |
| `test_a_tool_with_no_recorded_version_is_printed_when_it_is_absent` | FIX | delta table, "A tool recorded present with no version is absent" | Merge into the parametrised notes test. |
| `test_every_tool_the_probe_probes_is_in_one_of_the_three_tables` | FIX | `docs/docker.md` "Parity": every probed tool is in exactly one of the three tables | It checks the union only. Also assert `EXPECTED_VERSIONS`, `ABSENT` and `PRESENT` are pairwise disjoint. |
| `test_a_build_suffix_in_the_tool_line_is_not_a_difference` | DELETE | none (a code comment only) | One branch for one tool. The clean-probe test covers it. |
| `test_the_platform_the_probe_ran_on_is_reported` | OK | `docs/docker.md` "Parity" delta table, last row (the architecture is reported with the run) | Keep. |
| `test_the_exit_code_is_one_on_a_failure` | OK | delta table, Result column "exit 1" | Keep. |

Keep the file. Lines: 118 test vs 207 unit (`docker/parity.py`).
