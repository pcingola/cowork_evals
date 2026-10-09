# Command design

## Summary

The decisions behind the `cowork_evals` command surface. The surface itself, every verb,
option and exit code, is [cli.md](cli.md). What of it is built is [status.md](status.md).

- A verb names its object only when that object is not an eval. `run` runs evals, which is what
  this command is. `test` runs pytest and `ask` submits one prompt, so both say so.
- `--venv` is an unknown option on every verb, and `argparse` exits 2. The venv backend's design
  is [staged_runtime.md](staged_runtime.md), and a plan that builds it adds the flag.
- `setup` and `login` take `--docker` alone: the container is the only backend with something to
  build, and the CoWork backend reaches a desktop application that is already signed in. `ask`
  takes `--cowork` alone: it reaches a live session, and a container has none.

## run

An option a backend cannot honour is refused at parse time. A case that needs a field the
backend cannot honour declares it with a tag and is counted. The two are never conflated.

`--timeout-seconds` is refused on the container backend because `claude plugin eval` has no
timeout flag to map it onto.

An option's value is checked by its setting's own converter, before the configuration file is
read, so the message names the option and not the key.

Three settings have no option. `--threshold` is pinned, because this package decides.
`eval.max_cost_total_usd` bounds the whole invocation and not one run. `--delta-threshold` is
the other way round: an option over a setting that maps to no harness flag, because the
verdict reads it.

No option excludes a case, and none is added. Excluding one would mean invoking the harness once
per case, and both the log layout and the pass and fail rules read one result document per
plugin. The flags behind `--tag` and `--case` are `claude plugin eval --case` and `--tag`, in
[claude_code/plugin_eval_reference.md](claude_code/plugin_eval_reference.md).

What the invocation selected is printed, not inferred.

A dry run skips the preflight because nothing behind the preflight is reached: the image tag is
a hash of local files, the container argument list is built without asking the daemon, and the
`--cowork` plan reads the case tree and the configuration.

Coverage is not a rule of the format, which is why it is a flag and not a violation.

The validation imports every `checks/*.py`, because a check file is Python and the only way to
know it imports is to import it.

`test` has a preflight of its own because it starts a container. It is not a backend, and its
row sits in the preflight table because it is selected the way one is.

## test

A raw tail is refused on `run`, because the harness runs on two backends and a pass-through
would be silently ignored on the other. It is allowed on `test` because pytest is the only
thing behind the verb.

`test` creates no run directory, `env.txt`, `latest`, pruning or verdict. Those five exist for
`aggregate-result.json`, which pytest does not produce.

`test --dry-run` prints before the preflight, unlike `run --dry-run`, which prunes the log root
and so must not act behind a failed one. A dry run here does nothing beyond printing.

## setup and login

`setup` does not log in. An image is a build product and a credential is not, which is the
same distinction `prune --docker` makes when it leaves the login alone. A machine whose login
was revoked needs `login --docker`, not a second pass over two current images. Each eval run
gets a fresh container from one of the images, so there is no long-lived container to create.
Where each artefact lives, and how the digest is computed, is [library.md](library.md) and
[docker.md](docker.md).

`login` reads two of the conditions `check --docker` reports, the daemon and the image, because
the login container needs them. The credential is what it is about to make, and
`docker.env_passthrough` reaches a run and not this container.

Stdin that is not a terminal is refused by `login` itself and not left to `docker run -it`,
whose message says nothing about what the operator has to do. See [docker.md](docker.md).

## check

A named backend is a refusal: the operator asked about that one, and an unmet condition stops
them. `--all` is a report, so a ready backend is stated, every line says which backend it
belongs to, and the whole report goes to one stream in backend order.

## prune

`run` prunes log directories older than 30 days on its own, so `prune --logs` is for reclaiming
space on purpose. `prune --docker` leaves the container login alone because it is a credential,
and deleting it forces an interactive login. Selection never reads a modification time, which a
later read moves.

## panel

There is no `--tag` and no `--case`. The verb exists to show what has never run, and a filter
hides exactly those rows. There is no exit code that means the panel is red: `run` already exits
on the verdict, and a second code deciding the same thing from older data would disagree with
it.

## docs

`docs` reads the filesystem, writes nothing, needs no configuration and reaches no backend. With
a name it prints one absolute path and nothing else, so a script can use it.

A name is the path inside the tree without the extension, so a nested document is
`claude_code/plugin_eval_reference`. Two directories hold a `README.md`, so a bare basename
would not identify one. The tree carries one worked example as a real plugin, at
`claude_code/eval_smoke/`. Its `prompt.md` and graders are cases, not documents, so they are
not listed. They still ship.

| Condition                        | Prints                                  | Exit |
| -------------------------------- | --------------------------------------- | ---- |
| no argument                      | the directory, then every name          | 0    |
| a known name                     | one absolute path                       | 0    |
| an unknown name                  | the refusal, then every name, on stderr | 2    |
| a package built without the tree | one line saying so, on stderr           | 3    |

Where the tree sits differs between an install and a checkout. That rule, and the two reference
rules that follow from it, are in [library.md](library.md).

## init

A target the package owns is replaced on every run. A target that holds the consumer's own
values is written only when it is absent. The skills are whatever the package ships, one
directory each under `src/cowork_evals/data/skills/`. Which skill fires on what is
[library.md](library.md).

## Exit codes

Code 1 is one code because it is one thing to an operator: the verb reached its backend and the
work did not succeed.

No backend's code reaches an operator unchanged, except pytest's on `test`. Exit 3 means nothing
ran and nothing was written on every path: the CoWork rate ceiling is checked in the preflight,
and pruning happens behind every refusal.

`claude plugin eval` exits 2 on partial results, and the Docker backend turns that into a
`partial: true` result document. See [docker.md](docker.md#the-harness).

The CoWork driver's taxonomy, codes 2 to 9, is carried by a raised `CoWorkError` and never by an
exit code. Driver code 2 is configuration or the rate ceiling, which is the preflight class, so
it maps to 3 on both `run --cowork` and `ask`.
