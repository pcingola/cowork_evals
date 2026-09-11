# cowork_evals

## Summary

The command. One executable, seven verbs, two backends. It is the whole surface a consumer
repository sees; the boundary behind it is [library.md](library.md).

- **The backend is required on every verb but `prune`, `docs` and `init`** and has no
  default. Which backend proves what is [approaches.md](approaches.md).
- **The path is the scope.** One path argument decides whether a case, a skill, a plugin or a
  whole tree runs. There is no separate sweep command.
- **A verb names its object only when that object is not an eval.** `run` runs evals, which
  is what this command is. `test` runs pytest, so it says so. `setup`, `check` and `prune`
  act on a backend and carry no object at all. `docs` and `init` act on neither: they read
  what the package ships and write into the working directory.
- **Options are named.** Nothing is forwarded raw to `claude plugin eval`. `test` is the one
  verb that takes a raw tail, because pytest is the only thing behind it.
- **`run` verifies and never builds.** A failed preflight exits 3 and names the command that
  fixes it.
- **The exit code is the CLI's.** No backend's code reaches an operator unchanged. `test` is
  the one exception, and it returns pytest's.

The venv backend has no flag on any verb. `--venv` is an unknown option and `argparse` exits
2. Its design stays in [staged_runtime.md](staged_runtime.md), and a plan that builds it adds
the flag.

What of this command is built is the status table in
[running_evals.md](running_evals.md).

## Synopsis

```
cowork_evals run   (--docker | --cowork) <path> [options]
cowork_evals test  --docker <path> [--build-missing] [--dry-run] [-- PYTEST_ARGS]
cowork_evals setup --docker
cowork_evals check (--docker | --cowork | --all)
cowork_evals prune [--docker] [--logs] [--older-than DAYS] [--out DIR]
cowork_evals docs  [<name>]
cowork_evals init
cowork_evals --version
```

`setup` takes `--docker` alone. It is the only backend with anything to build, and there is
no `setup --all`.

`prune`, `docs` and `init` are the three verbs that take no backend. `prune` requires at
least one selection flag, and none is a usage error. `docs` and `init` take no backend
because neither reaches one: `docs` reads the shipped tree, and `init` writes files.

## The path is the scope

`run` takes one path. What that path points at decides what runs.

| Path points at                      | Runs                            | Scope name in the log directory |
| ----------------------------------- | ------------------------------- | ------------------------------- |
| a case directory                    | that case                       | `<plugin>-<skill>-<case>`       |
| `evals/<skill>/`                    | that skill's cases              | `<plugin>-<skill>`              |
| `evals/`                            | that plugin's whole suite       | `<plugin>`                      |
| a directory holding several plugins | each plugin in turn, gated once | `all`                           |
| anything else inside one root       | that plugin's whole suite       | `<plugin>`                      |

The last row is the plugin root itself, a `skills/` directory, and any other path inside one
root. The run is that plugin's, and the scope name says so.

The plugin root is the parent of `evals/`, and it is accepted only when it holds
`.claude-plugin/plugin.json`. A sweep finds plugins by that file with a sibling `evals/`, not
by a fixed glob, so a directory carrying a manifest and no `evals/` is not swept.

The plugin name in a scope name is `.claude-plugin/plugin.json`'s `name`, and the folder
basename when that file names none. Every character outside `[A-Za-z0-9._-]` becomes `-`. Two
plugins in one sweep whose manifests carry the same name get two directories, the second
suffixed `-2`, so neither result document overwrites the other and the gate reads both.

A multi-plugin path is a usage error on `--cowork`. There is no sweep on that backend, for
the reason in [running_evals.md](running_evals.md).

A case's `plugins: ["../../.."]` frontmatter states the plugin root a second time. The case
validator checks that the two resolve to the same directory, because the harness reads the
frontmatter and the CoWork backend resolves the path. See
[eval_format.md](eval_format.md).

## Options on run

Named options only. No raw argument tail is forwarded to `claude plugin eval`: that harness
runs on one backend of two, so a pass-through would be silently ignored on the other.

| Option                   | `--docker` | `--cowork`                             |
| ------------------------ | ---------- | -------------------------------------- |
| `--runs N`               | yes        | yes, replacing each case's own         |
| `--timeout-seconds N`    | refused    | yes, as each run's `run_timeout`       |
| `--model M`              | yes        | refused, the session decides           |
| `--judge-model M`        | yes        | yes, for judged graders                |
| `--allow-tools T...`     | yes        | refused, the session decides           |
| `--max-cost-usd N`       | yes        | refused, the driver's `max_runs` binds |
| `--keep-traces`          | yes        | yes                                    |
| `--tag T`, `--case GLOB` | yes        | yes                                    |
| `--out DIR`              | yes        | yes                                    |
| `--require-coverage`     | yes        | yes                                    |
| `--build-missing`        | yes        | refused, nothing to build              |
| `--dry-run`              | yes        | yes                                    |

`--timeout-seconds N` is refused on the Docker backend because `claude plugin eval` has no
timeout flag to map it onto. Only the CoWork backend sets a per-case `run_timeout` itself.

`--require-coverage` reads the tree and not a backend, so no backend refuses it. It is off by
default.

`--keep-traces` is on by default and `--no-keep-traces` turns it off, which is what puts each
run's transcript, final assistant message and workspace under the run's log directory. Both
backends honour it and both leave the same three names, so no backend refuses it. What is
kept, where it is read from and what is thrown away is
[running_evals.md](running_evals.md). It is the one option of the three states: untyped is the
file's value, and both `--keep-traces` and `--no-keep-traces` beat the file. `False` is a
value an operator typed and not a default, which is why the refusal table cannot read it as
untyped and why the option carries both forms.

`--out DIR` replaces the whole `logs/evals` root, so the run directory is
`<out>/<stamp>-<scope>`. It is accepted on `prune` too, which otherwise resolves
`<cwd>/logs/evals`. `--older-than DAYS` is a `prune` flag only: `run` prunes at a fixed 30
days.

Defaults come from the `eval:` section of `cowork_evals.yaml`, in
[running_evals.md](running_evals.md), which also says which underlying flag each option maps
to and why that flag is pinned. An option beats the file, and the file beats the built-in
default; the ladder is [library.md](library.md). Two pinned flags have no option:
`--threshold`, because the gate decides, and `--ablation`, because a baseline arm changes
which graders are scored. `eval.max_cost_total_usd` has no option either; it bounds the
invocation rather than a run.

An option the chosen backend cannot honour is refused at parse time. That is an operator
mistake, so it is a usage error. A *case* that needs a field the backend cannot honour is
reported skipped and fails the gate. The two are different and are never conflated.

`--dry-run` exits 0 without running anything and without creating a run directory. What it
prints differs per backend, because only one of them builds a command line.

| Backend    | Prints                                                                        |
| ---------- | ------------------------------------------------------------------------------- |
| `--docker` | the `docker run` command line, one argument per line, `--keep-temp` and the `TMPDIR` behind it included |
| `--cowork` | one line per case with its run count, its timeout and its skips, then the rate ceiling arithmetic |

The skips are the point of the CoWork dry run: a skipped case fails the gate, so an operator
reads which ones before spending. Pruning of old run directories happens before the exit, so
an unattended dry run still reclaims space. The tests assert over both, so the option surface,
the backend mapping and the target's position ahead of the variadic flags are covered without
a live run.

## Preflight

`run` verifies its backend and never builds. An eval run already costs minutes and money, and
a run that silently spends ten more building an image is not readable in a log.

| Backend    | Requires                                                             | Fails when                                                  |
| ---------- | -------------------------------------------------------------------- | ----------------------------------------------------------- |
| `--docker` | a Docker or Rancher daemon, the image at the current digest, and the container login | the daemon is down, the image is absent or stale, or there is no login |
| `--docker`, with `docker.auth_env` set | the daemon and the image, and no login | the daemon is down, or the image is absent or stale |
| `--cowork` | macOS, `claude` on `PATH`, a `cowork_evals.yaml` naming a profile, a readable sessions root under it, an Accessibility grant, and the suite inside the driver's `max_runs` | the grant is missing, so there is no headless route and no CI, or `claude` is absent, or no profile is configured, or the suite would exceed the ceiling |
| `test`     | a Docker or Rancher daemon, the eval image, and the test image over it        | the daemon is down, or either image is absent or stale |

The desktop application itself is not probed. What the backend reads is the profile directory
the application writes sessions into, and an unreadable one is the condition that matters. See
[cowork_desktop.md](cowork_desktop.md).

`test` has a preflight of its own because it starts a container. It never reads the container
login: there is no model call in that path. It is not a backend, and the row is here because
it is selected the way one is. See [cowork_test.md](cowork_test.md).

A failed preflight exits 3 and prints one line naming the command that fixes it:

```
image cowork-evals:<digest> is absent: run cowork_evals setup --docker
```

`--build-missing` builds the container image instead of failing. It is off by default and
exists for unattended use. A missing container login still fails the preflight, because that
login is interactive. On `test` it builds the test image, and the eval image first when that
is absent too.

`docker.auth_env` is what makes the container backend unattended end to end: it names the
variables that carry a provider credential into the container, and the login is then neither
required nor mounted. Which route a configuration selects, and what each carries, is
[docker.md](docker.md).

`run` also refuses three things a backend cannot report. Each happens before anything is
created and before anything is deleted, so exit 2 and exit 3 leave the log root untouched.

| Refusal                                                    | Exits |
| ---------------------------------------------------------- | ----- |
| A case that violates the format, in any selected plugin root | 3   |
| An uncovered skill, under `--require-coverage`             | 3     |
| A selection that matches no case at all                    | 2     |

`run` validates every selected plugin root, not only the target, so a malformed sibling case
blocks a single-case run. There is no option to skip validation. The rules are
[eval_format.md](eval_format.md).

A skill under `skills/` with no directory of that name under `evals/` is always reported.
`--require-coverage` turns that report into a preflight failure. Coverage is not a rule of the
format, which is why it is a flag and not a violation.

A selection matching no case at all is an operator mistake: a mistyped `--tag` must not read
as a pass, and the refusal catches it before a container starts. One plugin of a sweep
matching none is normal under `--tag` and is not a failure.

The order is preflight, then validation, then the selection count, then pruning, then the
`--dry-run` exit.

`--dry-run` skips the preflight and keeps everything after it. Nothing behind the preflight
is reached by a dry run: the image tag is a hash of local files, the container argument list
is built without asking the daemon, and the `--cowork` plan reads the case tree and the
configuration. A dry run therefore validates a case on a machine with no daemon, no image, no
credential and no profile, and a malformed case still exits 3. The ceiling belongs to the
preflight, and a dry run on `--cowork` prints the same arithmetic instead of refusing on it.

That is what makes `run --dry-run` the way to check a case without spending anything. There
is no separate validate verb.

A dry run reports the code the run would reach, so it is not always 0.

| On         | Exits 1 when                                                        |
| ---------- | -------------------------------------------------------------------- |
| `--cowork` | every selected case is skipped, so the suite plans no submission     |
| `--docker` | never. The harness decides its skips at run time, and a dry run cannot know them |

A skipped case fails the gate, so a suite that is dead on CoWork would fail a real run. A dry
run that exited 0 on it would pass a portability check in CI while the run went red. An empty
selection is a different thing and is refused earlier, with exit 2.

`claude` is a `--cowork` precondition because the judge behind an `llm` or `baseline` grader
is `claude -p`, and because `claudeVersion` in the result document is the host
`claude --version`. The signed-in CLI is the one credential route; there is no second one.

Host spend on `--cowork` is the judge alone. The CoWork session itself is billed to the
signed-in account and is not observable from the host, so `--max-cost-usd` is refused there
and the ceiling that binds is the driver's `max_runs`. See
[cowork_driver.md](cowork_driver.md).

## test

`test` runs a consumer's pytest suite inside the CoWork image. No model, no harness, no case
tree, no grader, no result document and no gate. The mechanism is
[cowork_test.md](cowork_test.md), and it is not restated here.

| Option            | Is                                                                  |
| ----------------- | --------------------------------------------------------------------- |
| `--docker`        | the only backend. There is no `test --cowork`                       |
| `<path>`          | a path inside one plugin root. A path covering several is a usage error, because pytest takes one rootdir |
| `--build-missing` | build the test image, and the eval image first when that is absent too |
| `--dry-run`       | print the container argument list, one argument per line, and return 0 |
| `-- PYTEST_ARGS`  | the pytest tail                                                     |

It takes no other option. Every option it does not carry configures a harness run, and `test`
runs no harness.

The pytest tail begins at `--`. Every token after it reaches pytest in order and unmodified,
and this command claims none of them: `-- --dry-run` is pytest's argument and never this
verb's. A raw tail is forbidden on `run`, because the harness runs on two backends and a
pass-through would be silently ignored on the other. It is allowed here because pytest is the
only thing behind this verb.

`test` creates nothing on the host: no run directory, no `env.txt`, no `latest`, no pruning
and no gate. Those five exist for `aggregate-result.json`, which pytest does not produce. It
validates no case and reads no `evals/` either, so a malformed case never blocks a test run.

`test --dry-run` prints before the preflight, unlike `run --dry-run`, which prunes the log
root and so must not act behind a failed one. A dry run here does nothing at all beyond
printing, so there is nothing for a preflight to guard.

## setup

| Command          | Builds                                                                                                     | Idempotent                   |
| ---------------- | ------------------------------------------------------------------------------------------------------------ | ---------------------------- |
| `setup --docker` | `cowork-evals:<digest>`, then `cowork-evals-test:<digest>` over it, then the container login if one is needed | prints `current` and exits 0 |

`setup --docker` builds two images. Each run gets a fresh container from one of them, so there
is no long-lived container to create. When no container login exists, it then starts one
interactive container to log in. That step needs a terminal and a browser. See
[docker.md](docker.md) and [cowork_test.md](cowork_test.md).

With `docker.auth_env` set it builds the two images, states the route it took and makes no
login. The images are the whole of what it builds there, so it needs no terminal and no
browser.

There is no `setup --cowork`. The desktop application and the Accessibility grant are
installed and granted by hand, and `check --cowork` reports what is missing.

Where each artefact lives, and how the digest is computed, is [library.md](library.md).

## check

`check` verifies the same conditions as the preflight table above, writes nothing, and never
builds. It exits 0 when every named backend is ready and 3 otherwise, listing each unmet
condition and its fix. The backend is required, so `check` with none is a usage error.

`check --docker` reports both images and the container login. The login is unmet for `run` and
is not read by `test`'s preflight, and `check` reports the condition either way. With
`docker.auth_env` set there is no login on that route, so the condition is not reported at
all and a machine that never logged in reports `ready`.

`check --all` covers `--docker` and `--cowork`, so it reports the Accessibility grant on a
machine that has no CoWork installed rather than failing the whole invocation. It returns 0 on
a machine where both are ready.

The two forms print differently, and the split is which of the two the output is.

| Form                              | Prints                                                   | Stream |
| --------------------------------- | -------------------------------------------------------- | ------ |
| `--docker`, `--cowork`            | `ready`, or the unmet lines alone                        | stdout, then stderr for the lines |
| `--all`                           | one section per backend, each named, then `ready` or its indented unmet lines | stdout |

A named backend is a refusal: the operator asked about that one, and an unmet condition is
what stops them. `--all` is a report, so a ready backend is stated rather than silent, every
line says which backend it belongs to, and the whole thing goes to one stream in backend
order.

```
$ cowork_evals check --all
docker: ready
cowork: not ready
  no CoWork profile configured: set cowork.profile in cowork_evals.yaml
```

The exit code does not change with the form: 0 when nothing is unmet, 3 otherwise.

`check` never reads the rate ceiling. That condition needs a target and `check` takes none, so
it is `run`'s alone.

## prune

Deletes artefacts this CLI created and nothing else.

| Flag                | Deletes                                                                             |
| ------------------- | ------------------------------------------------------------------------------------- |
| `--docker`          | images tagged `cowork-evals:*` and `cowork-evals-test:*`, except the current digest of each |
| `--logs`            | run directories under the resolved log root                                         |
| `--older-than DAYS` | restricts every selection above. Default 30                                         |
| `--out DIR`         | the log root `--logs` resolves, replacing `<cwd>/logs/evals`                        |

At least one selection flag is required. `prune` with none is a usage error. The two are not
exclusive: pruning images and logs in one invocation is ordinary.

An image is selected by its creation date and a run directory by the stamp in its name, never
by a modification time, which a later read moves.

`run` prunes log directories older than 30 days on its own, so `prune --logs` is for
reclaiming space on purpose. `prune --docker` leaves the container login alone: it is a
credential, not a build product, and deleting it forces an interactive login.

## docs

`docs` prints where the documentation this package ships landed. It reads the filesystem,
writes nothing, needs no configuration and reaches no backend.

```
cowork_evals docs            # the directory, then every document name
cowork_evals docs cli        # the path of one document
cowork_evals docs cli.md     # the same document. The extension is optional
```

With no argument the first line is the directory holding the tree and every line after it is
a document name. With a name it prints one absolute path and nothing else, which is what
makes it usable from a script and from an agent that will then read the file.

A name is the path inside the tree without the extension, so a nested document is
`claude_code/plugin_eval_reference`. Two directories hold a `README.md`, so a bare basename
would not identify one.

The tree carries one worked example as a real plugin, at `claude_code/eval_smoke/`. Its
`prompt.md` and its graders are cases, not documents, so they are not listed. They still
ship, and `docs claude_code/README` says what they are.

| Condition                            | Prints                                     | Exit |
| ------------------------------------ | ------------------------------------------ | ---- |
| no argument                          | the directory, then every name             | 0    |
| a known name                         | one absolute path                          | 0    |
| an unknown name                      | the refusal, then every name, on stderr    | 2    |
| a package built without the tree     | one line saying so, on stderr              | 3    |

Where the tree sits differs between an install and a checkout, which is why a document is
found through this verb rather than by a relative path. That rule, and the two reference
rules that follow from it, are in [library.md](library.md).

## init

`init` writes what a consumer repository needs to use this command, into the working
directory. It takes no backend and no option.

| Target                                  | Is                                                          |
| --------------------------------------- | ----------------------------------------------------------- |
| `cowork_evals.yaml`                     | Every key and every default, and a placeholder for `cowork.profile` |
| `.claude/skills/cowork-evals/SKILL.md`  | The eval-authoring skill: the tree, the keys, the graders, the traps |
| `CLAUDE.md`                             | A block naming the command, the `docs` verb and the runtime constraint |

It never overwrites. A target that exists is reported as kept and is left exactly as it is,
so a second run changes nothing and a consumer's own edits survive. `CLAUDE.md` is appended
to when it exists and does not carry the block, and created when it is absent; the block's
own heading is the marker, so an edited block is recognised and never appended twice.

Regenerating a target means deleting it first. That is the operator's act, and there is no
option here that overwrites a file.

### Upgrading the package does not refresh what init wrote

`init` overwrites nothing, so a target written by an older version stays as it is. The skill
is the one where that matters: it carries the case format, and a stale copy teaches an
out-of-date one to every session that reads it. Nothing detects the drift and nothing warns
about it.

After upgrading `cowork-evals`, take the new skill:

```sh
rm .claude/skills/cowork-evals/SKILL.md
cowork_evals init
```

The other two targets hold a consumer's own values, so leaving them alone is right.
`cowork_evals.yaml` gains a key only when a release adds one, and every key has a built-in
default, so an old file keeps working. The `CLAUDE.md` block is prose a consumer edits.

The skill is a copy and not a link, so deleting it is the only way it changes. That is
deliberate: a consumer edits the file after `init` writes it, and a refresh that overwrote
would destroy those edits without asking.

| Condition                                | Prints                                 | Exit |
| ---------------------------------------- | -------------------------------------- | ---- |
| a target was written                     | one `wrote` line per target            | 0    |
| every target was already there           | one `kept` line per target, then a summary | 0    |
| a source is missing from the installation | one line saying so, on stderr          | 3    |

`cowork_evals.yaml` names a profile, which is an identifier. Add it to the repository's
ignore list. See [library.md](library.md).

## Exit codes

| Code | Means                                                                       |
| ---- | --------------------------------------------------------------------------- |
| 0    | the gate passed, or the verb succeeded                                      |
| 1    | the gate failed. The conditions are in [running_evals.md](running_evals.md) |
| 2    | usage error: unknown option, an option the backend refuses, or no path      |
| 3    | preflight failed. Nothing ran and nothing was written                       |
| 130  | interrupted                                                                 |

The exit code is the CLI's, and no backend's code reaches an operator unchanged. `test` is the
one exception: once the container starts it returns pytest's code, unchanged and
uninterpreted, and [cowork_test.md](cowork_test.md) lists those. Every code in the table above
is still reachable on that verb before the container starts, on a parse failure or a failed
preflight.

Exit 3 means nothing ran and nothing was written on every path. The CoWork rate ceiling is
checked in the preflight, and pruning happens behind every refusal, so neither breaks that.

`claude plugin eval` exits 2 on partial results; the Docker backend turns that into a
`partial: true` result document, and the gate turns that into exit 1. See
[plugin_eval.md](plugin_eval.md).

The CoWork driver has its own taxonomy, codes 2 to 8, carried by a raised `CoWorkError` and
never by an exit code. It is in [cowork_driver.md](cowork_driver.md). The `--cowork` backend
maps it:

| Driver code                              | Becomes                                                            |
| ---------------------------------------- | ------------------------------------------------------------------ |
| 2, for configuration or the rate ceiling | Checked in preflight, before any case: exit 3                      |
| 2 to 8, raised while running a case      | That case is an error in the result document, and the gate exits 1 |
| No raise                                 | The case is graded normally                                        |
