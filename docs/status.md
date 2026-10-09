# Status

## Summary

Which pieces of the system are built. This file carries the build status of the whole system,
and no other file carries one: they link here.

| Piece                                         | Built    | Designed in                          |
| --------------------------------------------- | -------- | ------------------------------------ |
| The 3.10 mirror, as a development script      | yes      | [environments.md](environments.md)   |
| The `cowork_evals` package, as a distribution | yes      | [library.md](library.md)             |
| The `cowork_evals` executable and its verbs   | yes      | [cli.md](cli.md)                     |
| `cowork_evals.yaml` and the `Config` over it  | yes      | [library.md](library.md)             |
| The pinned harness argument list              | yes      | [run_pipeline.md](run_pipeline.md)   |
| The run traces, on both backends              | yes      | [run_pipeline.md](run_pipeline.md)   |
| Pass and fail                                 | yes      | [running_evals.md](running_evals.md) |
| The baseline arm, and the verdict over its delta | yes   | [running_evals.md](running_evals.md) |
| The case validator                            | yes      | [eval_format.md](eval_format.md)     |
| The case history, and the `panel` verb over it | yes     | [case_history.md](case_history.md)   |
| The check layer, over what a run produced     | yes      | [checks.md](checks.md)               |
| The container backend and its Dockerfile      | yes      | [docker.md](docker.md)               |
| `scripts/parity.sh` and `tests/unit/test_parity.py` | yes | [docker.md](docker.md)             |
| The CoWork driver                             | yes      | [cowork_driver.md](cowork_driver.md) |
| The CoWork backend over it                    | yes      | [cowork_backend.md](cowork_backend.md) |
| `plugins/smoke/`, the fixture both backends fire | yes   | `plugins/README.md`                  |
| The test image, `cowork-evals-test:<digest>`  | yes      | [docker.md](docker.md)               |
| The `test` verb over it                       | yes      | [cowork_test.md](cowork_test.md)     |
| A 3.10 and import check over code under test  | no       | nowhere, and it is not designed      |
| The venv backend and the runtime it stages    | deferred | [staged_runtime.md](staged_runtime.md) |

`deferred` means the design stands and the developer decided not to build it. Nothing in the
command surface reaches it.
