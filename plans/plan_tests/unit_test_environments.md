# `tests/unit/test_environments.py`

Assessment for [`../plan_tests.md`](../plan_tests.md). Model names refer to [`../plan_models.md`](../plan_models.md).

| Test | Verdict | Requirement | What to do |
| ---- | ------- | ----------- | ---------- |
| `pins` (helper) | OK | `docs/environments.md` "Building it" (one PEP 503 reader, `requirements.pins`) | Keep. Returns a name-to-version mapping, not a record. |
| `interpreter` (helper) | DELETE | none | Removed with the merge below; `sys.version_info` in-process gives the same fact. |
| `test_requirements_files_exist` | DELETE | `docs/library.md` "What ships" | Duplicate: the two requirements tests below read all three files and fail if one is missing. |
| `test_requirements_files_resolve_as_package_data` | DELETE | `docs/library.md` "What ships" | Under an editable install this checks `importlib.resources`, not a wheel. `count("==") > 100` is arbitrary. `scripts/build.sh` enforces shipping. |
| `test_installable_is_the_freeze_minus_the_nine` | OK | `docs/environments.md` "Three requirements files" | Keep. |
| `test_the_test_layer_adds_packages_and_moves_none` | OK | `docs/environments.md` "Three requirements files"; `docs/docker.md` "The pinned list" | Keep. |
| `test_the_development_interpreter_is_the_session_interpreter` | OK | `docs/environments.md` "Summary" (`.python-version` and `docker/parity.py` agree) | Keep. |
| `test_repo_venv_is_the_pinned_interpreter` | FIX | `docs/environments.md` "Summary" | Merge with the test below: assert `Path(sys.prefix).resolve() == VENV.resolve()` and `"%d.%d.%d" % sys.version_info[:3] == PINNED`. Drop `.exists()` and the subprocess. |
| `test_tests_run_under_the_repo_venv_not_the_mirror` | FIX | `docs/environments.md` "Summary" | Becomes the merged test above. |
| `test_scripts_readme_carries_a_row_for_every_script` | OK | `scripts/README.md` script table | Keep. |
| `test_login_sh_holds_no_logic_and_execs_the_verb` | DELETE | none (`scripts/README.md` "login.sh holds no logic" is a rule about the script's text, not a behaviour of the system) | It checks script text, which is implementation shape. The behaviour, the `login` verb, is `test_cli.py`'s. |
| `test_every_script_is_executable_and_parses` | FIX | `scripts/README.md` (`lib.sh` is sourced, never executed) | The `if script.name != "lib.sh"` in the loop bypasses an assertion. Parametrise over `*.sh` for `bash -n`, and over the set minus `lib.sh` for the executable bit. No `if` in the body. |

Keep the file; `docs/environments.md` names it. Lines: 155 test vs 34 (`requirements.py`) plus `scripts/*.sh`.
