# cowork_evals

## Summary

`cowork_evals` is the one executable this package installs, and this file is its whole
surface: every verb, its options, what each backend refuses, and the exit codes. It runs an
eval suite against a plugin tree on either of two backends, runs a plugin's own pytest suite
on the CoWork runtime, submits one prompt to a live CoWork session, and manages the container
images, the container login, the run directories and the history. What each backend proves is
[approaches.md](approaches.md). Pass, fail and the run directory are
[running_evals.md](running_evals.md).

## Synopsis

```
cowork_evals run   (--docker | --cowork) <path> [options]
cowork_evals ask   --cowork <prompt> [--timeout-seconds N] [--json] [--dry-run]
cowork_evals ask   --cowork --session <dir> [--json]
cowork_evals test  --docker <path> [--build-missing] [--dry-run] [-- PYTEST_ARGS]
cowork_evals setup --docker
cowork_evals login --docker [--check | --force]
cowork_evals check (--docker | --cowork | --all)
cowork_evals prune [--docker] [--logs] [--history] [--older-than DAYS] [--out DIR]
cowork_evals panel <path> [--markdown FILE] [--json FILE] [--removed]
cowork_evals docs  [<name>]
cowork_evals init
cowork_evals --version
```

- The backend is required on every verb except `prune`, `panel`, `docs` and `init`. It has no
  default.
- `setup`, `login` and `test` take `--docker` only. `ask` takes `--cowork` only. A backend a
  verb does not carry is an unknown option, exit 2.
- The path is the scope. One path decides whether a case, a skill, a plugin or a whole tree
  runs. There is no sweep verb.
- Options are named. Nothing is forwarded raw to `claude plugin eval`. `test` is the one verb
  with a raw tail, and the tail goes to pytest.

## The path is the scope

| Path points at                      | Runs                      | Scope name in the log directory |
| ----------------------------------- | ------------------------- | ------------------------------- |
| a case directory                    | that case                 | `<plugin>-<skill>-<case>`       |
| `evals/<skill>/`                    | that skill's cases        | `<plugin>-<skill>`              |
| `evals/`                            | that plugin's whole suite | `<plugin>`                      |
| a directory holding several plugins | each plugin in turn       | `all`                           |
| anything else inside one root       | that plugin's whole suite | `<plugin>`                      |

The last row covers the plugin root itself, a `skills/` directory, and any other path inside
one root.

The plugin root is the nearest directory at or above the path that holds
`.claude-plugin/plugin.json`. A sweep finds a plugin by that file plus a sibling `evals/`, so a
directory with a manifest and no `evals/` is not swept.

The plugin name is the manifest's `name`, else the folder name. Each character outside
`[A-Za-z0-9._-]` becomes `-`. Two plugins with one name in one sweep get two directories, the
second suffixed `-2`, and the verdict reads both.

A multi-plugin path on `--cowork` exits 2. There is no sweep on that backend.

A case's `plugins: ["../../.."]` states the plugin root a second time, and the validator checks
that the two resolve to the same directory. See [eval_format.md](eval_format.md).

## Options on run

| Option                   | `--docker` | `--cowork`                           |
| ------------------------ | ---------- | ------------------------------------ |
| `--runs N`               | yes        | yes. Replaces each case's own `runs` |
| `--timeout-seconds N`    | refused, the harness has no timeout flag | yes. Each run's driver timeout |
| `--model M`              | yes        | refused. The session decides         |
| `--judge-model M`        | yes        | yes. For judged graders and checks   |
| `--allow-tools T...`     | yes        | refused. The session decides         |
| `--max-cost-usd N`       | yes        | refused. Session spend is not visible to the host |
| `--ablation MODE`        | yes        | refused. One arm only                |
| `--delta-threshold N`    | yes        | refused. No delta                    |
| `--[no-]keep-traces`     | yes        | yes                                  |
| `--tag T`, `--case GLOB` | yes        | yes                                  |
| `--out DIR`              | yes        | yes                                  |
| `--require-coverage`     | yes        | yes                                  |
| `--build-missing`        | yes        | refused. Nothing to build            |
| `--dry-run`              | yes        | yes                                  |

A refused option is a usage error, exit 2. A case that needs a field the backend cannot honour
carries the `no-cowork` tag instead, is not submitted, and is counted. See
[eval_format.md](eval_format.md).

Defaults come from `eval:` in `cowork_evals.yaml`. An option beats the file, and the file beats
the built-in default. An option's value is checked by its setting's own rule before the file is
read, so `--delta-threshold 5` exits 2 whatever the file says, and the message names the
option. `--runs` takes the case format's cap, 50.

| Option              | Setting                   | Default                                         |
| ------------------- | ------------------------- | ----------------------------------------------- |
| `--model`           | `eval.model`              | `sonnet`                                        |
| `--judge-model`     | `eval.judge_model`        | `haiku`                                         |
| `--allow-tools`     | `eval.allow_tools`        | `Bash Read Glob Grep Write Edit WebFetch Skill` |
| `--ablation`        | `eval.ablation`           | `none`                                          |
| `--delta-threshold` | `eval.delta_threshold`    | `0`                                             |
| `--max-cost-usd`    | `eval.max_cost_usd`       | 5                                               |
| `--[no-]keep-traces` | `eval.keep_traces`       | true                                            |
| none                | `eval.max_cost_total_usd` | 25                                              |
| none                | `eval.judge_votes`        | 3                                               |

The harness `--threshold` is pinned to 0 and has no option, so this package decides pass and
fail.

`--allow-tools` and `eval.allow_tools` replace the list. They do not add to it, so a
replacement names every tool it still wants. A case cannot grant itself a tool, and a tool that
is not granted is lost without a loud failure. See [running_evals.md](running_evals.md).

`--ablation with-without` runs every case a second time with no plugin loaded, and each case is
decided on the delta between the two scores. `--delta-threshold N` is what that delta must
reach. See [running_evals.md](running_evals.md).

`--keep-traces` is on by default. `--no-keep-traces` turns it off, and either form beats the
file. Off, three outcomes are lost: a tool refused by the permission mode and a granted tool
never offered are not found, and every check becomes a skip, which fails the run. See
[checks.md](checks.md).

`--out DIR` replaces the whole `logs/evals` root. The run directory is then
`<out>/<stamp>-<scope>`. `run` deletes run directories older than 30 days on its own.
`--older-than DAYS` is a `prune` flag only.

### Selecting cases

`--tag T` keeps cases carrying that tag. It is repeatable, and each one widens the selection.
`--case GLOB` takes one glob over the case name, with `*` and `?`. There is no negation and no
list. No option excludes a case: to leave a case out of the usual sweep, give it a tag the usual
sweep does not name.

The last line of a run prints how many cases the path holds, how many the filters kept, how
many ran and how many passed.

### Dry run

`--dry-run` exits 0 without running anything and without creating a run directory.

| Backend    | Prints                                                                      |
| ---------- | --------------------------------------------------------------------------- |
| `--docker` | the `docker run` command line, one argument per line, forwarded values redacted |
| `--cowork` | one line per case: run count, timeout, what it declares, its grader skips, then the rate ceiling arithmetic |

On CoWork, read which cases are declared before spending: a declared case submits nothing.

The order is preflight, validation, the selection count, pruning, then the `--dry-run` exit. A
dry run skips the preflight and keeps everything after it. It therefore validates a case on a
machine with no daemon, no image, no login and no profile, and spends nothing. There is no
separate validate verb. A suite whose every case declares `no-cowork` plans no submission and
passes. An empty selection exits 2, and a malformed case exits 3.

## Preflight

`run` checks its backend and never builds.

| Backend    | Requires                                                             | Fails when                                                  |
| ---------- | -------------------------------------------------------------------- | ----------------------------------------------------------- |
| `--docker` | a Docker or Rancher daemon, the image at its current digest, the container login, each name in `docker.env_passthrough` set and non-empty on the host | the daemon is down, the image is absent or stale, there is no login, a forwarded name is unset or empty, or a forwarded name would carry Claude's own credential |
| `--cowork` | macOS, `claude` on `PATH`, `cowork.profile` in `cowork_evals.yaml`, a readable sessions root under it, the Accessibility grant, the suite within `cowork.max_runs` | the platform is not macOS, `claude` is absent, no profile is configured, the sessions root is unreadable, the grant is missing, or the suite would exceed the ceiling |
| `test`     | a daemon, the eval image, and the test image over it                 | the daemon is down, or an image is absent or stale          |

A forwarded name that is unset or empty is one unmet line per name. A name that would carry
Claude's own credential is refused whatever it holds, and the line names the container login as
the one route. Every line names the variable, never its value.

On `--cowork`, `claude` is needed because the judge behind an `llm` or `baseline` grader is
`claude -p`, and `claudeVersion` in the result document is the host `claude --version`. The
desktop application itself is not probed: the backend reads the profile directory the
application writes sessions into.

`test` never reads the container login, because it makes no model call.

A failed preflight exits 3 and prints one line naming the fix:

```
image cowork-evals:<digest> is absent: run cowork_evals setup --docker
```

`--build-missing` builds an absent image instead of failing, when the daemon is reachable. It is
off by default, for unattended use. A missing login still fails, because login is interactive.

A run that submits to CoWork asks for the keyboard once per invocation, in a modal that comes to
the front, before the first plugin. Cancel fires nothing and fails the run with exit 1.
`cowork.consent: none` fires without asking, for an unattended run. A dry run never asks.

### What run refuses

Each refusal happens before anything is created or deleted, so exit 2 and exit 3 leave the log
root untouched.

| Refusal                                                      | Exit |
| ------------------------------------------------------------ | ---- |
| A case that violates the format, in any selected plugin root | 3    |
| An uncovered skill, under `--require-coverage`               | 3    |
| A selection that matches no case at all                      | 2    |

`run` validates every selected plugin root, not only the target, so a malformed sibling case
blocks a single-case run. Validation cannot be skipped. It imports every `checks/*.py`, which
runs the module-level code of each on the host. A check file that does not import exits 3 and
spends nothing. The rules are [eval_format.md](eval_format.md).

A skill under `skills/` with no directory of that name under `evals/` is always reported on
stdout. `--require-coverage` makes it exit 3.

A selection matching no case at all exits 2, so a mistyped `--tag` never reads as a pass. One
plugin of a sweep matching no case under `--tag` is not a failure.

## ask

`ask --cowork "<prompt>"` submits one prompt to a live CoWork session and prints the answer. It
is not an eval. Every option, the output and the exit codes are [ask.md](ask.md).

## test

Runs a plugin's own pytest suite in the CoWork image. No model, no case tree, no verdict. See
[cowork_test.md](cowork_test.md).

| Option            | Is                                                                   |
| ----------------- | -------------------------------------------------------------------- |
| `--docker`        | the only backend. There is no `test --cowork`                        |
| `<path>`          | a path inside one plugin root. A path over several roots exits 2, because pytest takes one rootdir |
| `--build-missing` | build the test image, and the eval image first when that is absent too |
| `--dry-run`       | print the container argument list, one argument per line, and return 0. It prints before the preflight |
| `-- PYTEST_ARGS`  | every token after `--` reaches pytest in order and unchanged         |

`test` takes no other option. `-- --dry-run` is pytest's argument, never this verb's. A raw tail
is refused on `run`.

`test` writes nothing on the host: no run directory, no `env.txt`, no `latest`, no pruning and
no verdict. It validates no case and reads no `evals/`. After the container starts, it returns
pytest's exit code unchanged.

## setup

`setup --docker` builds `cowork-evals:<digest>`, then `cowork-evals-test:<digest>` over it, and
nothing else. An image already at its digest prints `current`, so a second run is a no-op and
exits 0. It does not log in.

There is no `setup --all` and no `setup --cowork`. The desktop application and the
Accessibility grant are set up by hand, and `check --cowork` reports what is missing.

## login

`login --docker` makes the container login this package owns, and builds nothing.

```
cowork_evals login --docker           # log in, or report the login already there
cowork_evals login --docker --check   # report it, write nothing
cowork_evals login --docker --force   # log in again over an existing login
```

| Condition                                  | Does                                         | Exit |
| ------------------------------------------ | -------------------------------------------- | ---- |
| a login is present                         | prints the credentials file as `current`     | 0    |
| no login                                   | starts one interactive container and logs in | 0    |
| `--check` and a login is present           | prints it, writes nothing                    | 0    |
| `--check` and no login                     | names this verb on stderr                    | 3    |
| the daemon is down, or the image is absent | names the command that fixes it              | 3    |
| stdin is not a terminal                    | says so, starts no container                 | 3    |
| the login itself failed                    | the reason on stderr                         | 1    |

There is no headless login and no API key route. The login opens a browser and reads a code
back in its own prompt. Use `--force` when the tokens are present and no longer work, or the
account is wrong. A credentials file with no token is not a login, so `login --docker` starts a
new one over it with no flag.

## check

`check` checks the preflight conditions, writes nothing and never builds. It exits 0 when every
named backend is ready, else 3. The backend is required.

| Form                   | Prints                                                         | Stream                  |
| ---------------------- | -------------------------------------------------------------- | ----------------------- |
| `--docker`, `--cowork` | `ready`, or the unmet lines                                    | stdout, lines on stderr |
| `--all`                | one section per backend, `ready` or its indented unmet lines   | stdout                  |

```
$ cowork_evals check --all
docker: ready
cowork: not ready
  no CoWork profile configured: set cowork.profile in cowork_evals.yaml
```

`check --docker` reports both images and the container login. `check --all` on a machine with no
CoWork reports the missing grant and still covers Docker. `check` never reads the rate ceiling,
because that needs a target.

## prune

Deletes what this command created and nothing else. At least one selection flag is required,
and the flags combine.

| Flag                | Deletes                                                                  |
| ------------------- | ------------------------------------------------------------------------ |
| `--docker`          | `cowork-evals:*` and `cowork-evals-test:*` images, except the current digest of each |
| `--logs`            | run directories under the log root                                       |
| `--history`         | records under `panel.root`, and files and directories left empty         |
| `--older-than DAYS` | limits each selection. Default 30                                        |
| `--out DIR`         | the log root `--logs` reads. It does not move `--history`                |

An image is selected by its creation date and a run directory by the stamp in its name, never by
a modification time. `prune --docker` leaves the container login alone. See
[panel.md](panel.md) for history.

## panel

`panel <path>` prints one row per case from the records earlier runs left. It reaches no
backend, spends nothing and takes no backend flag.

| Option            | Is                                                        |
| ----------------- | --------------------------------------------------------- |
| `<path>`          | the scope, resolved as `run` resolves it                  |
| `--markdown FILE` | write the same rows as a Markdown table                   |
| `--json FILE`     | write the same rows as JSON                               |
| `--removed`       | add a row for history whose case is no longer in the tree |

There is no `--tag` and no `--case`. The columns, the exit codes and the records are
[panel.md](panel.md).

## docs

`cowork_evals docs` prints the directory this documentation is installed in, then every
document name. `cowork_evals docs <name>` prints one document's path, and exits 2 on an unknown
name.

## init

`init` writes what a consumer repository needs into the working directory. It takes no backend
and no option.

| Target                                | Is                                                          | Owner    | When it exists                                   |
| ------------------------------------- | ----------------------------------------------------------- | -------- | ------------------------------------------------ |
| `cowork_evals.yaml`                   | every key and its default, and a placeholder for `cowork.profile` | consumer | kept exactly as it is                     |
| `.claude/skills/cowork-evals/`        | the eval skill                                              | package  | deleted whole, then copied again                 |
| `.claude/skills/cowork-ask/`          | the ask skill                                               | package  | deleted whole, then copied again                 |
| `.claude/skills/cowork-skill-author/` | the skill-authoring skill                                   | package  | deleted whole, then copied again                 |
| `CLAUDE.md`                           | a block naming the command and the runtime constraint       | consumer | kept when it carries the block, else appended to |

Each skill directory is copied whole, except `__pycache__`. A link at a skill's target is
removed, not followed. An edit to a shipped skill does not survive the next `init`. A skill
directory the package does not ship is never touched, and a consumer skill with the name of a
shipped skill is replaced. The block's heading is its marker, so an edited block is never
appended twice.

| Condition                                 | Prints                                                        | Exit |
| ----------------------------------------- | ------------------------------------------------------------- | ---- |
| any run                                   | one `wrote`, `replaced`, `kept` or `appended` line per target | 0    |
| a source is missing from the installation | one line saying so, on stderr, and nothing is written         | 3    |

`cowork_evals.yaml` names a profile, which is an identifier. Add it to the repository's ignore
list.

After upgrading `cowork-evals`, run `init` again. It replaces every shipped skill, including
files a skill no longer carries. Every key has a built-in default, so an old
`cowork_evals.yaml` keeps working. A skill a release removes stays in `.claude/skills/` until
you delete it.

## Exit codes

| Code | Means                                                                                                    |
| ---- | -------------------------------------------------------------------------------------------------------- |
| 0    | the run passed, or the verb succeeded                                                                    |
| 1    | the run failed, or the driver raised on `ask`. The conditions are in [running_evals.md](running_evals.md) |
| 2    | usage error: unknown option, an option the backend refuses, a value its setting refuses, no verb, no path, an empty selection |
| 3    | preflight or validation failed. Nothing ran and nothing was written                                      |
| 130  | interrupted                                                                                              |

`run` and `ask` are the two verbs that return 1. `test` returns pytest's code once the container
starts. [cowork_test.md](cowork_test.md) lists those.

When `claude plugin eval` stops with partial results, the result document carries
`partial: true`, and the run exits 1.

On `--cowork`, the driver's own error codes become:

| Driver code                              | Becomes                                                           |
| ---------------------------------------- | ----------------------------------------------------------------- |
| 2, for configuration or the rate ceiling | checked in the preflight, before any case: exit 3                 |
| 3 to 9, raised while running a case      | that case is an error in the result document, and the run exits 1 |
| no raise                                 | the case is graded normally                                       |

The failing line starts with the driver code. [cowork_driver.md](cowork_driver.md#failure-taxonomy)
says what each code means and what to do.
