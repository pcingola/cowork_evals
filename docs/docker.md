# Docker

## Summary

A container that reproduces the CoWork image, so an eval run exercises the OS, the
architecture, LibreOffice, ImageMagick, pandoc, tesseract, the CLI utilities and the font
stack, not only the Python interpreter and its wheels.

- **Jammy is the base**, and almost every recorded version is the version jammy ships. Four
  components come from upstream instead, each with one source.
- **One image, one tag.** `cowork-evals:<digest>`, where the digest covers every build input.
  There is no `latest`.
- **Two credential routes, and one rule picks which.** `docker.auth_env` names variables and
  the route is those variables; it names none and the route is a login this package owns,
  mounted read-write. Never the developer's own `~/.claude`.
- **Read-only everywhere except the log directory** and the two credential paths.
- **Granting `Bash` turns on the OS sandbox**, so the container needs bubblewrap and two
  `--security-opt` values.
- **Parity is how the image is proved.** `scripts/parity.sh` runs one probe inside the
  container and compares what it wrote against [runtime.md](runtime.md).
- **This package is never installed into the image.** The `cowork_evals` process stays on the
  host and builds the argument lists.

The image inventory this container has to match is [runtime.md](runtime.md). The eval system
around it is [running_evals.md](running_evals.md) and the command that reaches it is
[cli.md](cli.md).

What of this is built is the status table in [running_evals.md](running_evals.md).
`cowork_evals setup --docker` builds the image and `cowork_evals run --docker` runs through
it. `scripts/image.sh` and `scripts/login.sh` stay as development tasks for this repository.
A failed check names the command a consumer runs, which is `cowork_evals setup --docker` for
both an absent image and an absent login, and never a script under `scripts/`. On the
environment route there is no login, so that condition is not reported at all.

## Configuration

The `docker:` section of `cowork_evals.yaml`. The file, and the ladder over it, is
[library.md](library.md).

| Key                    | Default                        | Is                                                  |
| ---------------------- | ------------------------------ | ---------------------------------------------------- |
| `platform`             | `linux/arm64`                  | The build and run platform. In the image digest      |
| `claude_code_version`  | `2.1.265`                      | The npm version of the CLI installed. In the digest  |
| `login_dir`            | `~/.cache/cowork_evals/claude` | Where the login this package owns is kept            |
| `extra_ca_file`        | none                           | An extra root CA for a host whose network inspects TLS |
| `auth_env`             | empty                          | The variable names the environment credential route forwards |

## Usage

```bash
cowork_evals setup --docker                                   # build for docker.platform
cowork_evals check --docker                                   # daemon, image digest, credential
cowork_evals run --docker path/to/plugin/evals/<skill>        # one skill, in the container
cowork_evals run --docker path/to/repo                        # every plugin, in the container

scripts/image.sh                                              # development: build for docker.platform
scripts/image.sh --check                                      # development: the digest is present, no writes
scripts/login.sh                                              # development: log in once, in a container
scripts/login.sh --check                                      # development: a login is present, no writes
scripts/parity.sh                                             # development: probe the image, compare
```

`run --docker` takes the same path argument and the same options as every other backend and
writes the same logs. `--dry-run` prints the `docker run` argument list one argument per line
and starts nothing. See [cli.md](cli.md).

`scripts/image.sh` and `scripts/parity.sh` are development tasks for this repository and are
not part of the command. `parity.sh` is how the image is proved to match
[runtime.md](runtime.md) before a release.

## Why the image can be close

The CoWork image is Ubuntu 22.04.5 (jammy), and every recorded non-Python version is the
version jammy ships: pandoc 2.9.2.1, tesseract 4.1.1, ImageMagick 6.9.11-60, ffmpeg 4.4.2,
poppler-utils 22.02.0, ghostscript 9.55.0, qpdf 10.6.3, git 2.34.1, OpenJDK 11.0.31,
Python 3.10.12. `apt-get install` from jammy therefore reproduces them, up to the point
releases jammy has taken since the capture: the measurement below found one, Java at
11.0.32.

Four things do not come from jammy apt, and each has one source:

| Component        | Recorded | jammy apt | Source                                                             |
| ---------------- | -------- | --------- | ------------------------------------------------------------------ |
| LibreOffice      | 26.2.5.2 | 7.3       | `LibreOffice_26.2.5_Linux_<arch>_deb.tar.gz`, upstream archive     |
| Node.js          | 22.23.2  | 12        | NodeSource `node_22.x`, pinned to `22.23.2-1nodesource1`           |
| pip              | 25.3     | 22.0.2    | `pip install --upgrade pip==25.3`                                  |
| uv               | 0.12.3   | absent    | The Astral installer, pinned to 0.12.3                             |

Both upstream sources are present for aarch64 and carry the recorded versions, checked
2026-09-08. The upstream release is named `26.2.5` in the path and the file name, and
`soffice --version` reports the fourth component: 26.2.5.2.

## The Python pins

The requirements files, and the split between them, are
[environments.md](environments.md). This image reads one of the three,
`requirements_installable.txt`. In the image the pins come from two places, not one.

| Pins | Source                                        |
| ---- | --------------------------------------------- |
| 127  | `pip install -r requirements_installable.txt` |
| 9    | apt, as Ubuntu system packages                |

The nine live in `/usr/lib/python3/dist-packages` and are not on PyPI at those versions.
`command-not-found==0.3` and `unattended-upgrades==0.1` are egg versions carried inside apt
packages, unrelated to the deb version, which is the evidence that the recorded freeze came
from a system interpreter. `pip install -r requirements.txt` fails on them and must never
be run.

| Pin                          | apt package           | jammy deb version   |
| ---------------------------- | --------------------- | ------------------- |
| `command-not-found==0.3`     | `command-not-found`   | 22.04.0             |
| `dbus-python==1.2.18`        | `python3-dbus`        | 1.2.18-3build1      |
| `distro-info==1.1+ubuntu0.2` | `python3-distro-info` | 1.1ubuntu0.2        |
| `pipx==1.0.0`                | `pipx`                | 1.0.0-1             |
| `PyGObject==3.42.1`          | `python3-gi`          | 3.42.1-0ubuntu1     |
| `pyinotify==0.9.6`           | `python3-pyinotify`   | 0.9.6-1.3           |
| `python-apt==2.4.0+ubuntu4.1`| `python3-apt`         | 2.4.0ubuntu4.1      |
| `ufw==0.36.1`                | `ufw`                 | 0.36.1-4ubuntu0.1   |
| `unattended-upgrades==0.1`   | `unattended-upgrades` | 2.8ubuntu1          |

`pip freeze` inside the built image reports every pin, because pip sees `dist-packages`.
That is the fidelity gain over the mirror, which cannot hold the nine.

This image carries no pytest, so the inventory stays exact and the parity section below is
unchanged by it. The image that does carry pytest is one layer over this one, and is
[cowork_test.md](cowork_test.md).

Measured on `ubuntu:22.04` `linux/arm64` on 2026-09-03, a snapshot: apt installs the nine
above, `python3 -V` reports 3.10.12, and `pip freeze` reports all nine at the recorded pin
strings exactly. Jammy's python3.10 carries no `EXTERNALLY-MANAGED` marker, so pip installs
into the system interpreter without a flag.

## unoserver and the UNO bindings

`unoserver==3.7` is one of the 127 pins and needs `import uno` from the interpreter it runs
under. Jammy's `python3-uno` is 1:7.3.7, tied to the `libreoffice` 1:7.3.7 it ships with, so
it cannot supply the bindings against 26.2.
The upstream deb set installs pyuno under its own `program` directory, so the image puts
that directory on `PYTHONPATH`.

Parity checks `import uno` and `unoserver --version`, because document conversion is the
capability the container exists to prove. A `soffice --version` check alone passes while
conversion is broken.

## Architecture

The recorded image is `aarch64`. `--platform linux/arm64` matches it natively on an ARM Mac
and needs qemu emulation elsewhere, which is correct but several times slower.

The build takes `--platform` from `docker.platform`, default `linux/arm64`. The parity report
records the platform actually used, so an x86 run is never mistaken for an aarch64 one.

The upstream LibreOffice archive is named by the kernel architecture, not by Docker's, and
spells `amd64` two ways. The Dockerfile maps `TARGETARCH` to both.

| `TARGETARCH` | Archive directory | File name |
| ------------ | ----------------- | --------- |
| `arm64`      | `aarch64`         | `aarch64` |
| `amd64`      | `x86_64`          | `x86-64`  |

NodeSource and the uv installer detect the architecture themselves and need no mapping.

## The build context

The build context is the package's data directory, the three requirements files and
nothing else, and the Dockerfile is passed with `-f`. This image copies one of the three;
the third is copied by the layer in [cowork_test.md](cowork_test.md), which builds from the
same context. Nothing else is copied into a layer: the plugins and the logs are mounts, made
at run time, and no code from this package is ever installed into the image.

A three-file context needs no `.dockerignore`, transfers nothing, and cannot put a working
tree into a public image layer. See [library.md](library.md).

## A host whose network inspects TLS

Three of the four upstream sources are fetched over HTTPS by the build:
`download.documentfoundation.org`, `deb.nodesource.com` and `astral.sh`. On a host behind
a TLS-inspecting proxy the container has no issuer for any of them and the build fails at
the first fetch. PyPI and the npm registry were not intercepted on the host measured below,
so the pins and the CLI install either way.

The build takes an extra root CA from `docker.extra_ca_file`. It is passed as a BuildKit
secret, never through the build context, and the Dockerfile installs it into the image CA
store. Both the fetches above and the Claude
Code CLI inside the container then trust it: `claude.ai` is intercepted on that host too, so
the login route needs it as much as the build does.

| Layer                     | Reads it from                                    |
| ------------------------- | ------------------------------------------------ |
| `build_argv`              | `--secret id=extra_ca,src=<docker.extra_ca_file>` |
| The Dockerfile            | `/run/secrets/extra_ca`, once, into the CA store |
| `run_argv`, `login_argv`  | `--env NODE_EXTRA_CA_CERTS`, because Node carries its own root store |

`docker.extra_ca_file` unset, or naming a file that is not there, is a host that does not
intercept, and nothing is passed. The certificate itself never enters this repository: the
public repository rule in `README.md` covers it, and a corporate root names the employer.

The image digest does not cover the certificate. It is a property of the host that built the
image, not of the inventory the image reproduces. The path it is installed at is a build
argument and is covered.

Adding a certificate to a host that has already built the image therefore needs
`scripts/image.sh --recreate`. The digest is unchanged, so the tag is unchanged, and BuildKit
does not key a `--mount=type=secret` layer on the secret's contents, so the layer that
installed no certificate is reused and every later fetch fails exactly as it did before.
Measured on 2026-09-09: two builds failed at the LibreOffice fetch with `curl` exit 60, the
certificate correctly named in `cowork_evals.yaml` throughout, and `--recreate` built clean.

## How Docker is driven

The `cowork_evals` process runs the `docker` CLI through `subprocess`. It does not use
`docker-py`, which is the usual way to reach Docker from Python.

| Fact                                                                                   | Consequence                                        |
| -------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| A cross-architecture `--platform` build goes through buildx. buildx is the CLI's builder; `docker-py` drives the daemon's classic builder | The SDK is weakest on the one build this file exists for |
| `docker context` resolves which daemon to talk to and the CLI reads it. `docker-py` takes `DOCKER_HOST`, and Rancher Desktop on its containerd backend exposes no Docker API socket at all | The CLI reaches both daemons [cli.md](cli.md) names |

Using the SDK for `run` and the CLI for `build` would be two mechanisms for one job.

What the SDK gives back is typed errors instead of an exit code, and no argument quoting.
The second is worth little here: `--dry-run` prints the argument list a run would use, so
that list is built either way. See [cli.md](cli.md).

## The Claude Code CLI

The harness is not part of the CoWork image, so it is not in the inventory above. The
container installs it as a global npm package, `@anthropic-ai/claude-code`, at the version
in the `CLAUDE_CODE_VERSION` build argument. `docker.claude_code_version` supplies it,
default 2.1.265. It is in the image digest, so two versions cannot share one tag.

Not every version runs here. 2.1.259, the version [plugin_eval.md](plugin_eval.md) is
written against, cannot run a Bash-granting case on Linux at all. Its sandbox masks
`<sandbox home>/.aws` six times: five as an empty directory, to block the creation of
`.aws/sso` and the other cache paths under it, and once with `/dev/null`, for the store
itself. `bwrap` applies them in order and dies on the `/dev/null` one with `Can't create
file at <sandbox home>/.aws: Is a directory`, so every sandboxed command exits 1 and the
model reports a broken sandbox rather than the command's output. The path is inside the
sandbox home, which the harness creates fresh per run, so nothing on the host or in the
image changes it. 2.1.265 creates those directories rather than masking a missing one, and
the smoke case passes. Measured 2026-09-08, both versions on the same image.

It is one deliberate delta against [runtime.md](runtime.md), which records corepack and npm
as the only npm globals. Parity does not read npm globals and does not fail on it. No other
global is added.

`bubblewrap` and `socat` are the second and third, and both are harness infrastructure in
the same sense as the CLI above. The harness refuses to start a granted shell tool unless
both are installed, and every case here is pinned `--allow-tools Bash`. Measured 2026-09-08:
without `socat` a run exits 1 with `sandbox is enabled but dependencies are missing: socat
not installed`, and the case is scored 0 rather than errored, so the failure reads as a bad
answer unless the notes column is read. `probe.py` reports both versions and parity fails on
neither.

[runtime.md](runtime.md) records neither, and there is no reason it would. CoWork starts a
fresh VM per session, so the VM is the isolation boundary and Claude Code inside it has no
shell to confine. This backend has no VM: the harness confines the shell inside the
container, so it requires a backend to do it with. On the CoWork backend the harness does
not run at all, so neither tool is in the picture there either.

Both are therefore container-backend-only, and neither is a fidelity claim about the CoWork
image. The one consequence for a consumer: a skill that shells out to `bubblewrap` or
`socat` runs in this container and should not be assumed to run on CoWork.

## Credentials

Two routes, and `docker.auth_env` is the rule that picks one:

| `docker.auth_env` | The route is                                | `setup --docker` | `check --docker` reports a credential |
| ----------------- | ------------------------------------------- | ---------------- | ------------------------------------- |
| empty, the default | the login below, mounted                   | makes it         | yes                                   |
| naming a variable | those variables, forwarded into the container | makes none      | no                                    |

Never both. A run carries the login mounts or the named variables, and the two lists are
built in one place, `Docker.run_preamble`. `Docker.uses_env_auth` derives the rule, and the
three callers that differ read it there.

The login was the only route until 2026-09-10. The decision of 2026-09-08 that there is no
API key route stands for what it decided: nothing here writes a key, reads a key, or takes
one as a setting. The environment route names variables and forwards them, which is a
different thing and is how a run reaches Bedrock, Vertex, Foundry or a gateway.

### The login route

A login this package owns, mounted. A host with no interactive terminal logs in on a host
that has one and carries the two paths below.

The login happens once, in an interactive container that `setup --docker` starts when the
login is absent, and it writes a configuration directory this package owns:

| Host path, under `docker.login_dir` | Holds                                                      |
| ----------------------------------- | ------------------------------------------------------------ |
| `.claude/`                          | the configuration directory, including `.credentials.json` |
| `.claude.json`                      | the CLI state file                                         |

The container carries no browser, so the CLI prints a URL and reads an authorization code
back. That prompt masks its input, so a pasted code is not echoed. Measured 2026-09-08.

The state file is created holding `{}`. An empty file is not an absent one: the CLI parses
it, fails, and exits 1 with `JSON Parse error: Unexpected EOF`. Measured 2026-09-08 on the
image below. `Docker.seed_login_dir()` writes it, and `Docker.login()` calls that before
starting the login container.

A credential file is not a credential either. An OAuth flow that is started and not
finished leaves `.credentials.json` behind carrying `scopes` and `subscriptionType` with
`accessToken` and `refreshToken` both empty. `Docker.has_credential()` therefore reads the
tokens rather than testing that the file is there, and the two callers that gate on it, the
`CREDENTIAL` condition and `scripts/login.sh`, report no login. An expired access token is
still a credential, because the CLI refreshes it: only the absence of both tokens is no
login. Measured 2026-09-09, where presence alone reported a login and every container run
then exited 1 with `Not logged in`.

Both are mounted into the container home, read-write: the CLI refreshes its token and
rewrites its state file on every start. They are the only host paths a run mounts besides
the plugin and the log directory, and the container keeps nothing else.

A first launch in a fresh configuration directory does not block a non-interactive run.
Measured 2026-09-08 on the image below: `claude -p` in a container with an empty `$HOME`
reaches the credential check and exits 1 with `Not logged in`, rather than stopping on a
first-run prompt. So the run mounts the configuration directory alone, and the login step
seeds no state file beside it.

- Never bake a credential into an image layer.
- Never mount the host `~/.claude` or `~/.claude.json`. That is the developer's own live
  session, inside a container that runs author-supplied prompts. The directory above is a
  separate login this package owns and can revoke on its own.
- A claude.ai login can publish a report. `--no-publish` is pinned, so none is published.
  See [running_evals.md](running_evals.md).

No login is a failed preflight, so it exits 3 and names the command that fixes it. See
[cli.md](cli.md). On the environment route it is not a condition, so it exits 0.

`CLAUDE_CODE_WALNUT_SPIRE` is passed in with `--env`, because the process inside the
container is `claude plugin eval` itself with no wrapper in the way. A shell opened in the
container by hand must export it. See [plugin_eval.md](plugin_eval.md).

### The environment route

`docker.auth_env` names variables. Each is emitted as `--env <NAME>`, with no `=` and no
value, so Docker takes the value from the `cowork_evals` process's own environment and the
credential reaches the child without entering an argument list, a `--dry-run` listing,
`run.log` or `docker inspect`.

```yaml
docker:
  auth_env: [CLAUDE_CODE_USE_BEDROCK, AWS_BEARER_TOKEN_BEDROCK, ANTHROPIC_BEDROCK_BASE_URL, AWS_REGION]
```

Those four are one operator's Bedrock set and are not a list this package knows. Which
variables a provider needs is the CLI's, and the harness reference states which of them reach
a run: the provider selectors, `AWS_*`, gcloud configuration, `ANTHROPIC_API_KEY`,
`ANTHROPIC_BASE_URL` and the proxy variables all pass through. See
[claude_code/plugin_eval_reference.md](claude_code/plugin_eval_reference.md).

Only names go in the file. A value never does, and the public repository rule in `README.md`
covers this key like any other.

| Property                                             | Why                                                                 |
| ---------------------------------------------------- | -------------------------------------------------------------------- |
| The value is never read on the host                   | Nothing in this package reads the process environment, and this key does not change that. The file names a variable; Docker moves it. See [library.md](library.md) |
| An unset name forwards nothing                       | `--env NAME` on a name this process does not hold passes nothing, and the CLI in the container then refuses with its own provider error |
| Presence is not a preflight condition                | Checking it would mean reading the environment. A typo therefore costs a container start, not a wrong pass |
| The login is neither required nor mounted            | `check --docker` does not report it and `setup --docker` does not make it |
| The enablement variable still goes in                | It is a constant, not a setting, and a third-party provider or a gateway cannot receive the server-side enablement at all. See [plugin_eval.md](plugin_eval.md) |
| No report is published                               | Publishing is never available on Bedrock, Vertex, Foundry or key auth. `--no-publish` is pinned, so nothing changes |

Two things this route does not carry. Neither is designed and neither is built.

- **A credential file.** Profile-based AWS or gcloud auth reads `~/.aws` or a gcloud
  configuration directory, and no mount here carries either. A run on this route
  authenticates through variables alone.
- **A model alias.** `eval.model` and `eval.judge_model` default to `sonnet` and `haiku`, and
  a provider that does not resolve an alias needs the full model identifier in those two
  keys. Nothing here translates one.

## Mounts

| Host path                     | Container path       | Mode | Why                                            |
| ----------------------------- | -------------------- | ---- | ---------------------------------------------- |
| the plugin root               | `/work/plugin`       | ro   | The plugin under test                          |
| the run's log dir             | `/work/logs`         | rw   | The only path the run may write outside `/tmp` |
| `<login_dir>/.claude/`        | `$HOME/.claude`      | rw   | The login, above. Login route only             |
| `<login_dir>/.claude.json`    | `$HOME/.claude.json` | rw   | The login, above. Login route only             |

The plugin root is the nearest ancestor of the path argument holding
`.claude-plugin/plugin.json`, and the target the harness is given inside the container is
that path relative to it, under `/work/plugin`. A path with no plugin root above it is an
error.

The last two rows are the login route's. On the environment route a run mounts the plugin and
the log directory and nothing else, and the credential arrives as a forwarded variable.

Read-only everywhere except the log directory and the two credential paths. A case that
writes into the consumer's checkout is a defect and must fail rather than succeed quietly.
`--output-dir` points at `/work/logs`, so the harness's own output does not land in the
plugin directory and the read-only mount does not fail a correct run.

The container holds nothing from this package. The `cowork_evals` process stays on the host,
builds this argument list, names the run directory, writes the `latest` symlink, prunes old
runs, records `env.txt` and runs the gate over the result document the container leaves
behind. One place does all of that for both backends. See [library.md](library.md).

Only the run's own log directory is mounted, not the whole log root, because the host owns
every other path under it.

The container runs with the host user's numeric uid and gid, so log files are not
root-owned. That uid has no passwd entry, so `HOME` is set explicitly to a writable path
under `/tmp`, created in the image world-writable.

A uid with no passwd entry is the one thing here that can stop the CLI: Node's
`os.userInfo()` raises rather than returning a stub. It does not on the image measured
below, so `--user <uid>:<gid>` is what the backend passes and the documented fallback, root
plus a `chown -R` of `/work/logs` on the way out, is not used.

Nothing is staged into the container to supply an interpreter: system `python3` is already
3.10 with the full pin set. The 3.10 mirror in [environments.md](environments.md) is a
development environment on the host and is neither mounted nor built here.

## The Bash sandbox

Granting `Bash` turns on the OS sandbox, and a host with no sandbox backend refuses the run
rather than running unconfined. See [plugin_eval.md](plugin_eval.md).

The image installs `bubblewrap`, 0.6.1 in jammy, and the container runs with two
`--security-opt` values. Both are needed, and each was found by a different failure.

| Option                    | Without it                                                                        |
| ------------------------- | ---------------------------------------------------------------------------------- |
| `seccomp=unconfined`      | `bwrap: No permissions to create new namespace`. The default profile filters the unprivileged user namespace calls |
| `systempaths=unconfined`  | `bwrap: Can't mount proc on /newroot/proc: Operation not permitted`                 |

The second is the one a bare `bwrap` invocation does not reach. Docker masks entries under
`/proc` by default, and the kernel refuses a fresh procfs mount to a process whose own
`/proc` is covered that way. The harness mounts one, so every sandboxed command fails while
`bwrap --ro-bind / / --unshare-user --unshare-pid true` still succeeds.
`tests/integration/test_docker.py` therefore asserts the `--proc` mount as well as the bare
invocation. Measured 2026-09-08.

The documented fallback, `--cap-add SYS_ADMIN --security-opt apparmor=unconfined`, is not
used: measured on the same date it fails earlier still, with `bwrap: pivot_root: Operation
not permitted`.

A container that cannot grant `Bash` cannot run a case that shells out, which is most of
them.

## Image tagging

The image is tagged `cowork-evals:<digest>`, where `<digest>` is the first 12 characters of
the sha256 of the Dockerfile, `requirements.txt`, `requirements_installable.txt`, every
build argument and the resolved `docker.platform`. Without the platform an `arm64` and an `amd64` image share one tag.

The build arguments are `Docker.build_args`: the resolved `docker.claude_code_version` and
the five container paths, which are `CONTAINER_HOME`, `CONTAINER_WORK`, `CONTAINER_PLUGIN`,
`CONTAINER_LOGS` and `CONTAINER_EXTRA_CA` in `docker/__init__.py`. The Dockerfile writes
none of the five for itself, so a path cannot be changed in Python and left uncreated in the
image. Every build input is in the digest, so two CLI versions cannot share one tag and no
change can be served from a stale image.

There is no `latest` tag. Nothing reads one: `run` and `check` resolve the digest tag, and a
`latest` left behind by an older build points at an image no command would choose.

## Parity

`scripts/parity.sh` is the development task: it runs one probe inside the container, with
the probe bind-mounted read-only, then compares what the probe wrote. It checks the OS
release, the architecture, every version in the runtime tables, `import uno`, the font
family count, and the full `pip freeze`.

It is a shell script like every other task under `scripts/`, and the comparison runs on the
host. Nothing from this package is installed into the image to do it.

No file under `docs/` is parsed. The pins come from the shipped `requirements.txt`, and the
non-Python versions are a table in `parity.py` that cites [runtime.md](runtime.md). A change
to that file is carried into the table by hand, in the same commit.

| Delta                                          | Result                 | Why                                                            |
| ---------------------------------------------- | ---------------------- | -------------------------------------------------------------- |
| A pin is missing or at a different version     | exit 1                 | It changes what a skill can import                             |
| A package is installed that is not a pin       | printed, does not fail | A transitive dependency of the tooling is not a fidelity break |
| A non-Python tool version differs              | printed, does not fail | A jammy point release moves a patch version and must not block |
| A tool recorded as not present is present      | exit 1                 | A skill can call it here and not in a session                  |
| `import uno` fails                             | exit 1                 | unoserver and headless conversion are broken                   |
| A tool the probe probes that no table records  | exit 1                 | Its result is compared against nothing and read by nobody      |
| A tool recorded present with no version is absent | printed, does not fail | There is no version to compare it against                   |

The tools recorded as not present are `wkhtmltopdf`, `weasyprint`, `exiftool`, `docker` and
the `sqlite3` CLI. The three recorded present with no version are `ssh`, which
[runtime.md](runtime.md) lists without one, and `bwrap` and `socat`, the two deltas above,
which it does not record at all.

Every tool `probe.py` probes is in exactly one of the three tables in `parity.py`. Which
table a new one goes in is decided by what is recorded for it: a version, presence alone, or
absence.

The probe writes one JSON document. `tests/unit/test_parity.py` asserts over recorded copies
of it under `tests/data/docker/`, one per row of the table above, so the tests start no
container.

## What the container still does not reproduce

Stated once so no reader assumes otherwise: the CoWork model routing, the admin-applied
enterprise prompt, the CoWork MCP servers, the `/sessions/<session>` filesystem layout, the
vsock host RPC, and the session lifecycle. It is an image, not the deployed stack. For
those, see [cowork_driver.md](cowork_driver.md).

## Measurements

Taken on one host and true of that host. Each is a snapshot, dated, with the host written as
its OS, architecture and container runtime, never as a machine name. A reader on another
platform re-runs `scripts/parity.sh` and the integration tier rather than assuming these.

| Measurement                       | Value                                                   |
| --------------------------------- | ------------------------------------------------------- |
| Captured on                       | 2026-09-08                                              |
| Host                              | macOS on aarch64, Rancher Desktop, dockerd 29.5.3       |
| Platform built                    | `linux/arm64`, native                                   |
| Image size                        | 3.72 GB                                                 |
| Build time, cold                  | 5 min 30 s, `--no-cache`, native, over a proxy           |
| Build time, warm                  | under a second: the digest is present, so nothing runs  |
| Python pin mismatches             | 0 of 136                                                |
| Extra Python packages             | 0                                                       |
| Non-Python deltas                 | Java 11.0.32 against the recorded 11.0.31, a jammy point release. `socat`, which the inventory does not record, for the shell sandbox |
| Font families in the image        | 111 against the recorded 118                            |
| `import uno` from system python3  | yes                                                     |
| Bash sandbox options needed       | `--security-opt seccomp=unconfined` and `--security-opt systempaths=unconfined`, and `socat` in the image. `bwrap` mounts a procfs under both |
| uid mapping option needed         | `--user <uid>:<gid>`. `claude --version` runs under a uid with no passwd entry |
| Claude Code CLI version installed | 2.1.265. 2.1.259 cannot run a Bash-granting case here   |
| Extra root CA needed              | yes on this host. Three upstream hosts inspect TLS      |

All 136 pins are present at the recorded version, the nine from apt included, so the
fidelity gain over the mirror is real. The two deltas above are printed by
`scripts/parity.sh` and neither fails it.

The font count is 7 families short. The image installs the Noto fallback faces rather than
`fonts-noto-core`, which alone adds 192 families over the record, so the remaining gap is
between one jammy font package and another rather than between two font stacks.
