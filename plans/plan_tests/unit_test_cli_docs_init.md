# `tests/unit/test_cli_docs_init.py`

Assessment for [`../plan_tests.md`](../plan_tests.md). Model names refer to [`../plan_models.md`](../plan_models.md).

| Test | Verdict | Requirement | What to do |
| ---- | ------- | ----------- | ---------- |
| `parse` (helper) | DELETE | none | Duplicates `parse` in `test_cli.py`. |
| `test_docs_takes_no_backend_and_an_optional_name` | DELETE | none | Checks argparse. |
| `test_init_takes_nothing` | DELETE | none | Checks argparse. |
| `test_neither_verb_accepts_a_backend` | FIX | `docs/cli.md` "Synopsis" (a backend a verb does not carry is an unknown option, exit 2) | Move `docs --docker` and `init --docker` into the usage-error table in `test_cli.py` (`test_an_unknown_option_is_a_usage_error`). |
| `test_docs_lists_the_directory_then_every_name` | FIX | `docs/cli_design.md` "docs" | Expected values come from `resources`. Assert `printed[0]` is an absolute existing directory, `printed[1:]` is sorted and contains `"cli"`, `"eval_format"` and `"claude_code/README"`, and `Path(printed[0]) / f"{name}.md"` is a file for every name. |
| `test_docs_prints_one_absolute_path` | OK | `docs/cli_design.md` "docs" | Keep. |
| `test_docs_takes_the_extension_or_leaves_it` | OK | `docs/cli_design.md` "docs" | Keep. It is the one test of the requirement and goes through the verb. It moves into `test_cli.py` with the file merge; the `test_resources.py` copy goes. |
| `test_an_unknown_name_is_a_usage_error_and_lists_the_names` | FIX | `docs/cli_design.md` "docs" | Replace the loop over `resources.documents()` with the three literal names `"cli"`, `"eval_format"` and `"claude_code/README"`; replace exact wording with `"no-such-document" in printed`. Keep exit 2. |
| `_init_in`, `_tree` (helpers) | OK | none | Keep. |
| `test_init_writes_the_config_the_memory_block_and_every_skill` | FIX | `docs/cli.md` "init" | Absorb `test_every_skill_lands_where_claude_code_reads_it` and `test_the_configuration_it_writes_loads`. In an empty `tmp_path`: exit OK, config byte-equal to `EXAMPLE_CONFIG`, `CLAUDE.md` contains `MEMORY_MARKER`, `.claude/skills/` children are `{"cowork-ask","cowork-evals","cowork-skill-author"}`, each tree equals `_tree(resources.SKILLS / name)`. |
| `test_every_skill_lands_where_claude_code_reads_it` | FIX | `docs/cli.md` "init"; `docs/library.md` "The skills" | Merged above. |
| `test_a_skill_directory_is_installed_with_every_file_in_it` | FIX | `docs/cli.md` "init" (copied whole, except `__pycache__`) | Keep the `cli._install` call (no shipped skill reaches the exclusion). Cut the source to `SKILL.md`, `references/format.md`, `scripts/run.py` and `scripts/__pycache__/run.cpython-310.pyc`. Replace both asserts with one: the set of files under the target, read by `rglob` without the `_tree` filter, is `{SKILL.md, references/format.md, scripts/run.py}`. That one assert checks the exclusion, which `_tree` hides. |
| `test_the_configuration_it_writes_loads` | FIX | `docs/cli.md` "init" | Merged above as the byte equality. |
| `test_a_second_run_changes_nothing` | FIX | `docs/cli.md` "init" | Merge with the next test: exit OK, every file byte-unchanged, and stdout of the second run equals the literal lines `kept cowork_evals.yaml`, `replaced .claude/skills/cowork-ask`, `replaced .claude/skills/cowork-evals`, `replaced .claude/skills/cowork-skill-author`, and `kept CLAUDE.md: it already carries the block`. |
| `test_a_second_run_keeps_the_config_and_the_block_and_replaces_every_skill` | FIX | `docs/cli.md` "init" | Merged above. |
| `test_an_upgrade_replaces_a_stale_skill_whole` | OK | `docs/cli.md` "init" | Keep. |
| `test_a_skill_target_that_is_a_link_is_replaced_by_the_copy` | OK | `docs/cli.md` "init" | Keep. |
| `test_an_existing_memory_file_is_appended_to` | OK | `docs/cli.md` "init" | Keep. |
| `test_the_memory_block_is_never_appended_twice` | DELETE | `docs/cli.md` "init" | Covered by the edited-block test and the merged second-run test. |
| `test_an_edited_block_is_still_recognised` | OK | `docs/cli.md` "init" | Keep. |
| `test_an_existing_config_is_left_exactly_as_it_is` | OK | `docs/cli.md` "init" | Keep. |
| `test_init_needs_no_backend_and_no_configuration` | DELETE | `docs/cli.md` "init" | Covered by the merged `init` test and the backend test. |

Merge the file into `tests/unit/test_cli.py`; the unit is `cli.py`. `_init_in` and `_tree` move with it.
