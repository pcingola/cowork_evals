# `tests/unit/test_resources.py`

Assessment for [`../plan_tests.md`](../plan_tests.md). Model names refer to [`../plan_models.md`](../plan_models.md).

| Test | Verdict | Requirement | What to do |
| ---- | ------- | ----------- | ---------- |
| `REPOSITORY`, `LINK` (constants) | OK | none (helpers) | Keep. |
| `EXPECTED_DOCUMENTS` (constant) | DELETE | none | Deleted with `test_the_expected_documents_are_all_listed`. A `>=` check cannot catch a new document. |
| `test_the_documentation_tree_is_found` | DELETE | `docs/cli.md` "docs" | Duplicate of `test_cli.py::test_docs_lists_the_directory_then_every_name` and `test_docs_prints_one_absolute_path`. |
| `test_every_listed_name_resolves_to_a_file` | OK | `docs/cli.md` "docs"; `docs/cli_design.md` "docs" | Keep. |
| `test_the_expected_documents_are_all_listed` | DELETE | none | Hard-coded name set with no stated requirement. |
| `test_a_name_takes_the_extension_or_leaves_it` | DELETE | `docs/cli.md` "docs" | Duplicate of `test_cli.py::test_docs_takes_the_extension_or_leaves_it`. |
| `test_a_nested_document_is_named_by_its_path` | FIX | `docs/cli_design.md` "docs" (a nested document is named by its path; the vendored plugin's cases are not documents) | Merge with `test_a_vendored_plugin_case_is_not_a_document`: the nested name is listed and resolves, and no `eval_smoke/evals` path is listed. |
| `test_an_unknown_name_resolves_to_nothing` | DELETE | `docs/cli.md` "docs" | Duplicate of `test_cli.py::test_an_unknown_name_is_a_usage_error_and_lists_the_names`. |
| `test_a_name_cannot_reach_outside_the_tree[...]` | FIX | `docs/cli.md` "docs", sentence added by this row | Add one sentence to `docs/cli.md` "docs", as the "Decisions" table in `plan_tests.md` says: a name is matched against the listed names and never joined onto the root. Keep the parametrisation. |
| `test_a_vendored_plugin_case_is_not_a_document` | FIX | `docs/cli_design.md` "docs" | Merged into the nested-name test above. |
| `test_the_example_configuration_ships_beside_the_modules` | DELETE | `docs/library.md` "What ships" | Duplicate of the commented-default test below and the `init` tests that move from `test_cli_docs_init.py` into `test_cli.py`. `"cowork:" in text` checks wording. |
| `NOT_A_DEFAULT`, `_uncommented` (helpers) | OK | `docs/library.md` "The four sections" | Keep. |
| `test_every_commented_default_in_the_example_is_the_built_in_default` | FIX | `docs/library.md` "The four sections"; `docs/cli.md` "init" | Keep the assertions. Delete the docstring sentence that tells the `allow_tools` incident. |
| `test_every_shipped_skill_is_a_directory_named_for_it` | FIX | `docs/library.md` "The skills" | Keep the `name: <dir>` check. Delete `startswith("---\n")`, `"TRIGGER" in text` and the hard-coded name list. |
| `test_a_skill_installs_where_claude_code_reads_a_project_skill` | DELETE | `docs/library.md` "The skills" | Duplicate of `test_cli.py::test_init_writes_the_config_the_memory_block_and_every_skill`, which absorbs `test_every_skill_lands_where_claude_code_reads_it`. |
| `test_the_ask_skill_carries_the_measurement_rule` | DELETE | none: `docs/cowork_desktop.md` states the rule, and the test checks that a skill file repeats its words | Asserts wording in a prose file. |
| `test_the_memory_block_carries_its_own_marker` | DELETE | `docs/cli.md` "init" | A constant contains a constant. The `init` tests that move into `test_cli.py` (`test_init_writes_the_config_the_memory_block_and_every_skill`, `test_an_existing_memory_file_is_appended_to`) prove the marker on real output. |
| `test_no_skill_file_sends_the_reader_to_the_documentation` | OK | `docs/library.md` "The skills" | Keep. |
| `REFERENCE` (constant) | OK | none | Keep. |
| `test_every_reference_a_skill_names_is_there` | OK | `docs/library.md` "The skills" | Keep. |
| `test_every_reference_a_skill_holds_is_named_by_its_skill_file` | OK | `docs/library.md` "The skills" | Keep. |
| `test_a_reference_that_shares_a_document_name_is_a_link_to_it` | OK | `docs/library.md` "The skills" (symlink, never a copy) | Keep. |
| `test_every_link_in_a_reference_stays_inside_its_skill` | OK | `docs/library.md` "The skills" | Keep. |
| `FENCE`, `CODE_SPAN`, `_links` (helpers) | OK | none | Keep. |
| `test_r1_no_module_links_out_of_the_package` | OK | `docs/library.md` "The two reference rules" R1 | Keep. |
| `test_r2_no_document_links_out_of_the_tree` | FIX | `docs/library.md` "The two reference rules" R2 | Merge with the test below: one loop collects out-of-tree and dangling targets, assert both empty. |
| `test_r2_every_link_inside_the_tree_resolves` | FIX | `docs/library.md` "The two reference rules" R2 | Merged into the test above. |
| `test_every_document_the_readme_names_exists` | OK | `README.md` "Documentation" | Keep. |

Every `test_cli.py::` name above is a test that moves there from `test_cli_docs_init.py` with the file merge in the "Decisions" table. Keep the file. Lines: 312 test vs 167 unit (`resources.py`); much of it checks repository files (docs, skills) rather than `resources.py`. Phase 4's line check applies to it as to every file.
