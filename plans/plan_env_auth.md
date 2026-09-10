# plan_env_auth

Add a second credential route to the container backend: the variables that carry a provider
credential, forwarded into the container by name. The login route is unchanged and stays the
default.

Design: [`../docs/docker.md`](../docs/docker.md), under Credentials. The command surface it
touches is [`../docs/cli.md`](../docs/cli.md). The rule it must not weaken is
[`../docs/library.md`](../docs/library.md).

Branch: `feat/env-auth`.

## Why

The container backend has one credential route, an interactive browser login. An operator
whose Claude Code auth is Bedrock, Vertex, Foundry or a gateway holds no such login and cannot
make one, so `run --docker` refuses at the preflight with exit 3 and the whole backend is out
of reach for them.

The decision of 2026-09-08 that there is no API key route is not what blocks this. That
decision is about a key as a setting: nothing here writes one, reads one, or takes one in the
configuration file. Naming a variable and forwarding it is a different mechanism, and it is the
one the CLI already documents for every third-party provider.

## Scope

In:

- One `docker:` key, `auth_env`, holding variable names.
- The run's argument list, the `check` conditions, and the `setup` login step.

Out, and each stated in `docs/docker.md` as not carried:

- A credential *file* route. Profile-based AWS or gcloud auth reads `~/.aws` or a gcloud
  configuration directory, and no mount carries either.
- A model alias translation. A provider that does not resolve `sonnet` needs the full
  identifier in `eval.model`.
- Any host-side check that a named variable is set. Reading the environment is what the
  one-configuration-file rule forbids, so the cost of a typo is a container start.

## The rule

One key decides, and it is derived in one place, `Docker.uses_env_auth`.

| `docker.auth_env`  | The route is                        | `setup --docker` | `check --docker` |
| ------------------ | ----------------------------------- | ---------------- | ---------------- |
| empty, the default | the login, mounted                  | makes it         | reports it       |
| naming a variable  | those variables, forwarded by name  | makes none       | does not report it |

Never both in one run.

## Phases

### 1. The key

- [x] `DockerSection.auth_env`, a tuple of names, defaulting to empty.
- [x] `_names`, its converter, separate from `_tools` so a refusal says which list was
      mistyped.
- [x] The key in `data/cowork_evals.example.yaml`, commented, with the four-variable Bedrock
      set as the example.

### 2. The route

- [x] `Docker.uses_env_auth`, the one derivation of the rule.
- [x] `Docker.auth_env_argv`, emitting `--env <NAME>` with no value.
- [x] `run_preamble` carries one route or the other, never both.
- [x] `check` does not report `CREDENTIAL` on the environment route.
- [x] `cli._setup` makes no login on that route, and says which route it took.
- [x] `login_argv` unchanged, so a developer on that route can still log in on purpose.
- [x] `auth_env` is not in `build_args`, so it does not move the image digest.

### 3. Tests

- [x] The key: read as a tuple, empty is the login route, a bare string raises naming the key.
- [x] The argument list: each name forwarded, no `=` in any forwarded token, the plugin and
      the log directory the only mounts, the enablement variable still passed.
- [x] The digest is unchanged by the key, and `login_argv` is unchanged by it.
- [x] Integration: with a real daemon and image and a `login_dir` holding no login, `check`
      returns nothing unmet on the environment route.

### 4. Documentation

- [x] `docs/docker.md`: the summary line, the configuration table, the Credentials section
      split into the two routes, the Mounts table, and the two things the route does not
      carry.
- [x] `docs/cli.md`: the preflight table, `setup`, `check`.
- [x] `docs/library.md`: why the key does not weaken the one-configuration-file rule.
- [x] `README.md`: the two routes in `What you need`, the quickstart's default route, and the
      configuration paragraph. It is what a consumer reads, so the second route is stated
      there and not only in `docs/`.

### 5. Verification

- [x] `scripts/lint.sh` clean.
- [x] `scripts/test.sh`: 519 passed against 506 on the branch point, and the same 18
      pre-existing failures.
- [x] `tests/integration/test_docker.py -m 'integration and not live'`, against the real
      daemon and the real image: 10 passed.
- [x] `check --docker` on a `login_dir` holding no login: `ready` and 0 on the environment
      route, `no credential` and 3 on the login route.
- [x] `run --docker --dry-run` on the environment route: four names forwarded, no `=` in any
      of them, no login mount, and the plugin and the log directory the only two mounts.
- [ ] One live run through the environment route, against a provider.

## What was not verified here

The last box needs a provider credential, which this branch was written without. Until it is
ticked, the argument list is asserted and proven to be what Docker receives, and the provider
has not answered through it.

The 18 failures `scripts/test.sh` reports are `tests/data/results/` being absent from the
repository. They fail identically on the branch point and are not this plan's.
