# Docker

## Summary

This file is the Docker container that stands in for a CoWork session, and the container
backend runs every eval inside it. Reproducing Python and its wheels is not enough: a skill
calls LibreOffice, ImageMagick, pandoc and tesseract, and those come from the OS. So the
container reproduces the CoWork image itself: the OS, the architecture, the document and media
tooling, the CLI utilities, the font stack and the full pin set. An eval run against it
exercises the same versions a session does. The inventory it has to match is
[runtime.md](runtime.md).

- **Jammy is the base**, and almost every recorded version is the version jammy ships. Four
  components come from upstream instead, each with one source.
- **One image, one tag.** `cowork-evals:<digest>`, where the digest covers every build input.
  There is no `latest`.
- **Two credential routes**, and `docker.credential` chooses: a login this package owns,
  mounted read-write, or Bedrock, forwarded from the host. Never the developer's own
  `~/.claude`, and never an API key.
- **Named host variables are forwarded**, and their values reach the container's environment
  and no artefact.
- **Read-only everywhere except the log directory** and the two credential paths.
- **Granting `Bash` turns on the OS sandbox**, so the container needs bubblewrap, socat and
  two `--security-opt` values.
- **Parity is how the image is proved.** `scripts/parity.sh` runs one probe inside the
  container and compares what it wrote against [runtime.md](runtime.md).
- **This package is never installed into the image.** The `cowork_evals` process stays on the
  host and builds the argument lists.

The eval system around it is [running_evals.md](running_evals.md), the command that reaches it
is [cli.md](cli.md), and what of this is built is that file's status table.

## Configuration

The `docker:` section of `cowork_evals.yaml`. The file, and the ladder over it, is
[library.md](library.md).

| Key                    | Default                        | Is                                                  |
| ---------------------- | ------------------------------ | ---------------------------------------------------- |
| `platform`             | `linux/arm64`                  | The build and run platform. In the image digest      |
| `claude_code_version`  | `2.1.265`                      | The npm version of the CLI installed. In the digest  |
| `credential`           | `login`                        | How Claude Code in the container authenticates: `login` or `bedrock` |
| `login_dir`            | `~/.cache/cowork_evals/claude` | Where the login this package owns is kept. Read under `login` only |
| `extra_ca_file`        | none                           | An extra root CA for a host whose network inspects TLS |
| `env_passthrough`      | empty                          | Host variable names forwarded into the run container   |

## Usage

```bash
cowork_evals setup --docker                                   # build for docker.platform
cowork_evals login --docker                                   # log in once, in a container
cowork_evals login --docker --check                           # a login is present, no writes
cowork_evals check --docker                                   # daemon, image digest, credential
cowork_evals run --docker path/to/plugin/evals/<skill>        # one skill, in the container
cowork_evals run --docker path/to/repo                        # every plugin, in the container

scripts/image.sh                                              # development: build for docker.platform
scripts/image.sh --check                                      # development: the digest is present, no writes
scripts/image.sh --recreate                                   # development: build with --no-cache
scripts/login.sh                                              # development: the login verb, wrapped
scripts/parity.sh                                             # development: probe the image, compare
```

`run --docker` takes the same path argument and the same options as every other backend and
writes the same logs. `--dry-run` prints the container argument list and starts nothing. See
[cli.md](cli.md).

The scripts above are development tasks for this repository and are not part of the command.
`image.sh` and `login.sh` each wrap the verb that does the work, and `parity.sh` proves the
image against [runtime.md](runtime.md) before a release. A failed check names the verb a
consumer runs and never a script under `scripts/`.

## Why the image can be close

The CoWork image is Ubuntu 22.04.5 (jammy), and every recorded non-Python version is the
version jammy ships: pandoc 2.9.2.1, tesseract 4.1.1, ImageMagick 6.9.11-60, ffmpeg 4.4.2,
poppler-utils 22.02.0, ghostscript 9.55.0, qpdf 10.6.3, git 2.34.1, OpenJDK 11.0.31,
Python 3.10.12. `apt-get install` from jammy reproduces them, up to the point releases jammy
has taken since the inventory was captured.

Four things do not come from jammy apt, and each has one source:

| Component        | Recorded | jammy apt | Source                                                         |
| ---------------- | -------- | --------- | -------------------------------------------------------------- |
| LibreOffice      | 26.2.5.2 | 7.3       | `LibreOffice_26.2.5_Linux_<arch>_deb.tar.gz`, upstream archive |
| Node.js          | 22.23.2  | 12        | NodeSource `node_22.x`, pinned to `22.23.2-1nodesource1`       |
| pip              | 25.3     | 22.0.2    | `pip install --upgrade pip==25.3`                              |
| uv               | 0.12.3   | absent    | The Astral installer, pinned to 0.12.3                         |

Both upstream archives are present for aarch64 and carry the recorded versions. The upstream
LibreOffice release is named `26.2.5` in the path and the file name, and `soffice --version`
reports the fourth component, 26.2.5.2.

Each of the four versions is a Dockerfile `ARG` with a default, not a configuration key. The
Dockerfile is hashed into the image digest, so changing one is a different tag.

## The Python pins

The requirements files, and the split between them, are [environments.md](environments.md).
This image reads one of the three, `requirements_installable.txt`. In the image the pins come
from two places, not one.

| Pins | Source                                       |
| ---- | -------------------------------------------- |
| 127  | `pip install -r requirements_installable.txt` |
| 9    | apt, as Ubuntu system packages               |

The nine live in `/usr/lib/python3/dist-packages` and are not on PyPI at those versions.
`command-not-found==0.3` and `unattended-upgrades==0.1` are egg versions carried inside apt
packages and unrelated to the deb version, which is why the recorded freeze can only have come
from a system interpreter. `pip install -r requirements.txt` fails on them and must never be
run.

| Pin                          | apt package           | jammy deb version |
| ---------------------------- | --------------------- | ----------------- |
| `command-not-found==0.3`     | `command-not-found`   | 22.04.0           |
| `dbus-python==1.2.18`        | `python3-dbus`        | 1.2.18-3build1    |
| `distro-info==1.1+ubuntu0.2` | `python3-distro-info` | 1.1ubuntu0.2      |
| `pipx==1.0.0`                | `pipx`                | 1.0.0-1           |
| `PyGObject==3.42.1`          | `python3-gi`          | 3.42.1-0ubuntu1   |
| `pyinotify==0.9.6`           | `python3-pyinotify`   | 0.9.6-1.3         |
| `python-apt==2.4.0+ubuntu4.1`| `python3-apt`         | 2.4.0ubuntu4.1    |
| `ufw==0.36.1`                | `ufw`                 | 0.36.1-4ubuntu0.1 |
| `unattended-upgrades==0.1`   | `unattended-upgrades` | 2.8ubuntu1        |

`pip freeze` inside the built image reports all 136 pins, because pip sees `dist-packages`.
That is the fidelity gain over the mirror, which cannot hold the nine. Jammy's python3.10
carries no `EXTERNALLY-MANAGED` marker, so pip installs into the system interpreter without a
flag.

This image carries no pytest, so the inventory stays exact. The image that does carry pytest
is one layer over this one, and is [cowork_test.md](cowork_test.md).

## unoserver and the UNO bindings

`unoserver==3.7` is one of the 127 pins and needs `import uno` from the interpreter it runs
under. Jammy's `python3-uno` is 1:7.3.7, tied to the `libreoffice` 1:7.3.7 it ships with, so it
cannot supply the bindings against 26.2. The upstream deb set installs pyuno under its own
`program` directory, so the image puts that directory on `PYTHONPATH`.

Parity checks `import uno` and `unoserver --version`, because document conversion is the
capability the container exists to prove. A `soffice --version` check alone passes while
conversion is broken.

## Architecture

The recorded image is `aarch64`. `--platform linux/arm64` matches it natively on an ARM Mac and
needs qemu emulation elsewhere, which is correct but several times slower.

The build takes `--platform` from `docker.platform`, default `linux/arm64`. The parity report
records the platform the probe actually ran on, so an x86 run is never read as an aarch64 one.

The upstream LibreOffice archive is named by the kernel architecture, not by Docker's, and
spells `amd64` two ways. The Dockerfile maps `TARGETARCH`, which buildx sets from `--platform`,
to both.

| `TARGETARCH` | Archive directory | File name |
| ------------ | ----------------- | --------- |
| `arm64`      | `aarch64`         | `aarch64` |
| `amd64`      | `x86_64`          | `x86-64`  |

NodeSource and the uv installer detect the architecture themselves and need no mapping.

## The build context

The build context is the package's data directory, `src/cowork_evals/data/`, and the Dockerfile
is passed with `-f`. That directory holds the three requirements files, the example
configuration file and the shipped skills, and nothing else. This image copies one file out of
it, `requirements_installable.txt`; the layer in [cowork_test.md](cowork_test.md) builds from
the same context and copies `requirements_test.txt`.

No source tree is in the context, so no `.dockerignore` is needed and a working tree cannot
reach a public image layer. See [library.md](library.md). The plugin and the logs are mounts,
made at run time, and no code from this package is ever installed into the image.

## A host whose network inspects TLS

Three of the four upstream sources are fetched over HTTPS by the build:
`download.documentfoundation.org`, `deb.nodesource.com` and `astral.sh`. On a host behind a
TLS-inspecting proxy the container has no issuer for any of them and the build fails at the
first fetch with `curl` exit 60.

The build takes an extra root CA from `docker.extra_ca_file`. It is passed as a BuildKit secret,
never through the build context, and the Dockerfile installs it into the image CA store. Both
the fetches above and the Claude Code CLI inside the container then trust it, which the login
route needs when `claude.ai` is intercepted on the same host.

| Layer                    | Reads it from                                                        |
| ------------------------ | -------------------------------------------------------------------- |
| `build_argv`             | `--secret id=extra_ca,src=<docker.extra_ca_file>`                    |
| The Dockerfile           | `/run/secrets/extra_ca`, once, into the CA store                     |
| `run_argv`, `login_argv` | `--env NODE_EXTRA_CA_CERTS`, because Node carries its own root store |

`docker.extra_ca_file` unset, or naming a file that is not there, is a host that does not
intercept, and nothing is passed. The certificate itself never enters this repository: the
public repository rule in `README.md` covers it, and a corporate root names the employer.

The image digest does not cover the certificate. It is a property of the host that built the
image, not of the inventory the image reproduces. The path it is installed at is a build
argument and is covered.

Adding a certificate to a host that has already built the image therefore needs
`scripts/image.sh --recreate`. The digest is unchanged, so the tag is unchanged, and BuildKit
does not key a `--mount=type=secret` layer on the secret's contents. Without `--no-cache` the
layer that installed no certificate is reused and every later fetch fails exactly as before.

## How Docker is driven

The `cowork_evals` process runs the `docker` CLI through `subprocess`. It does not use
`docker-py`.

| Fact                                                                                                                                                                            | Consequence                                              |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| A cross-architecture `--platform` build goes through buildx. buildx is the CLI's builder; `docker-py` drives the daemon's classic builder                                        | The SDK is weakest on the one build this file exists for |
| `docker context` resolves which daemon to talk to and the CLI reads it. `docker-py` takes `DOCKER_HOST`, and Rancher Desktop on its containerd backend exposes no Docker API socket | The CLI reaches both daemons [cli.md](cli.md) names       |

Using the SDK for `run` and the CLI for `build` would be two mechanisms for one job. What the
SDK gives back is typed errors instead of an exit code, and no argument quoting. `--dry-run`
prints the argument list a run would use, so that list is built either way.

## The Claude Code CLI

The harness is not part of the CoWork image, so it is not in the inventory. The container
installs it as a global npm package, `@anthropic-ai/claude-code`, at the version in the
`CLAUDE_CODE_VERSION` build argument. `docker.claude_code_version` supplies it, default 2.1.265.
It is in the image digest, so two versions cannot share one tag.

Not every version runs here. 2.1.259, the version [plugin_eval.md](plugin_eval.md) is written
against, cannot run a Bash-granting case on Linux at all. It masks `<sandbox home>/.aws` as both
a directory and `/dev/null`, and `bwrap` dies on the second with `Can't create file at <sandbox
home>/.aws: Is a directory`. Every sandboxed command then exits 1 and the model reports a broken
sandbox rather than the command's output. The path is inside the sandbox home, which the harness
creates fresh per run, so nothing on the host or in the image changes it. 2.1.265 creates those
directories instead of masking a missing one.

The CLI is one deliberate delta against [runtime.md](runtime.md), which records corepack and npm
as the only npm globals. Parity does not read npm globals and does not fail on it. No other
global is added.

`bubblewrap` and `socat` are the second and third delta, and both are harness infrastructure in
the same sense as the CLI. The harness refuses to start a granted shell tool unless both are
installed, and the pinned grant names `Bash`. Without `socat` a run exits 1 with `sandbox is
enabled but dependencies are missing: socat not installed`, and the case is scored 0 rather than
errored, so the failure reads as a bad answer unless the notes column is read. `probe.py` reports
both versions and parity fails on neither.

[runtime.md](runtime.md) records neither. CoWork starts a fresh VM per session, so the VM is the
isolation boundary and Claude Code inside it has no shell to confine. This backend has no VM:
the harness confines the shell inside the container, so it requires a backend to do it with. On
the CoWork backend the harness does not run at all.

Both are therefore container-backend-only, and neither is a fidelity claim about the CoWork
image. The one consequence for a consumer: a skill that shells out to `bubblewrap` or `socat`
runs in this container and should not be assumed to run on CoWork.

## Credentials

Two routes, and `docker.credential` chooses between them. One question decides which one a
host uses: **how does Claude Code already authenticate on this host?** Through claude.ai, and
it is `login`. Through Bedrock, and it is `bedrock`. There is no API key route, by the
developer's decision.

| `docker.credential` | The container gets                          | The host needs                                     |
| ------------------- | -------------------------------------------- | -------------------------------------------------- |
| `login`, default    | the two paths below, mounted read-write     | an interactive terminal, once                       |
| `bedrock`           | four `--env` values and no mount            | the four variables set and non-empty at run time    |

Exactly one route is checked, never both. A host on `bedrock` is never asked for a login, and
a host on `login` is never asked for the four variables. Either way an unmet condition is a
failed preflight, so it exits 3 and names the fix. See [cli.md](cli.md).

Neither route puts Claude's own credential in `docker.env_passthrough`. That list is for a
credential the skill under test reads, and it refuses every name either route owns.

`CLAUDE_CODE_WALNUT_SPIRE` is neither route's and is passed in with `--env` on both, because
the process inside the container is `claude plugin eval` itself with no wrapper in the way. A
shell opened in the container by hand must export it. See [plugin_eval.md](plugin_eval.md).

### The login route

A login this package owns, mounted. A host with no interactive terminal logs in on a host that
has one and carries the two paths below.

| Host path, under `docker.login_dir` | Holds                                                      |
| ----------------------------------- | ---------------------------------------------------------- |
| `.claude/`                          | the configuration directory, including `.credentials.json` |
| `.claude.json`                      | the CLI state file                                         |

The login happens once, in an interactive container that `login --docker` starts. It runs
`claude auth login --claudeai` rather than bare `claude`, which would land in the first-run
configuration wizard on a fresh configuration directory. `setup --docker` builds images and
never starts it: an image is a build product and a credential is not, which is the distinction
`prune --docker` already makes when it leaves the login alone.

The container carries no browser, so the CLI prints a URL and reads an authorization code back.
That prompt masks its input, so a pasted code is not echoed.

The state file is created holding `{}`. An empty file is not an absent one: the CLI parses it,
fails, and exits 1 with `JSON Parse error: Unexpected EOF`. `Docker.seed_login_dir()` writes it,
and `Docker.login()` calls that before starting the login container.

A credential file is not a credential either. An OAuth flow that is started and not finished
leaves `.credentials.json` behind with `accessToken` and `refreshToken` both empty.
`Docker.has_credential()` therefore reads the tokens rather than testing that the file is there,
and both callers, the `CREDENTIAL` condition and `login --docker`, report no login. Reading the
file's presence alone would report a login that every container run then exits 1 on, with `Not
logged in`. An expired access token is still a credential, because the CLI refreshes it: only
the absence of both tokens is no login. `login --docker` starts a flow over a hollow file with
no flag, and `--force` is for the other case, a file whose tokens are there and no longer work.

Both paths are mounted into the container home read-write, because the CLI refreshes its token
and rewrites its state file on every start. They are the only host paths a run mounts besides
the plugin and the log directory.

A first launch in a fresh configuration directory does not block a non-interactive run.
`claude -p` in a container with an empty `$HOME` reaches the credential check and exits 1 with
`Not logged in` rather than stopping on a first-run prompt.

- Never bake a credential into an image layer.
- Never mount the host `~/.claude` or `~/.claude.json`. That is the developer's own live
  session, inside a container that runs author-supplied prompts. The directory above is a
  separate login this package owns and can revoke on its own.
- A claude.ai login can publish a report. `--no-publish` is pinned, so none is published. See
  [running_evals.md](running_evals.md).

No login is a failed preflight, so it exits 3 and names the command that fixes it. See
[cli.md](cli.md).

### How long a login lasts

The credentials file carries two lifetimes: an access token that expires 8 hours after the login,
and a refresh token that expires 29 days after it. The CLI refreshes the access token inside the
container and rewrites the mounted file, so an expired access token is not a re-login.

A revocation is, and it can arrive at any time. The CLI clears both tokens when a refresh is
refused, which is the hollow file above, so a revoked login reads as no login and the next run
fails its preflight. Neither lifetime is therefore a guarantee that a login survives to the end
of it.

`login --docker --check` reports the state and starts nothing, and `check --docker` reports it
before a run spends anything on a machine that cannot run.

### The Bedrock route

`docker.credential: bedrock` forwards four host variables into the run container and mounts
neither login path:

| Variable                     |
| ---------------------------- |
| `CLAUDE_CODE_USE_BEDROCK`    |
| `AWS_BEARER_TOKEN_BEDROCK`   |
| `ANTHROPIC_BEDROCK_BASE_URL` |
| `AWS_REGION`                 |

They are Claude Code's own, and the CLI reads them itself: the process in the container is
`claude plugin eval` with no wrapper, so `--env` is what puts them in front of it, exactly as
[plugin_eval.md](plugin_eval.md) records for the enablement variable.

Each one has to be set and non-empty. An absent or empty name is one unmet condition per name,
reported by `check --docker` and refused by `run` before anything is created, on the same
ground as a forwarded name that is not set: an empty string is not a value.

This route makes no login and needs none. `login --docker` refuses under it in both its modes,
and `Docker.login()` raises rather than opening a browser for a credential the route never
reads.

Two things follow from the route and are the developer's to set, not this package's to guard.

- `eval.model` and `eval.judge_model` are names the CLI resolves against Bedrock, so an alias
  such as `sonnet` may have to be an inference profile id. Nothing here has measured which
  aliases resolve, and no check refuses one.
- The host's own credential lifetime is the host's. This package reads the four variables at
  preflight and forwards what it read, and refreshes nothing.

## Environment passthrough

`docker.env_passthrough` is a list of host variable names. `run_preamble` writes
`--env NAME=VALUE` for each one, beside the variables it already writes, so a skill that reads a
credential from the environment can be evaluated. It is the one thing this package reads from
the process environment, and [library.md](library.md) holds the rule and this exception to it.

It is a `docker:` key because the container backend is the only one that starts a process whose
environment this package writes. A CoWork session decides its own environment, and nothing here
reaches inside the VM. See [approaches.md](approaches.md).

```yaml
docker:
  env_passthrough: [ACME_API_KEY]
```

Two conditions, both in `Docker.check`, so `check --docker` reports them and `run` exits 3 on
them before anything is created:

| Condition                                          | Because                                                                     |
| -------------------------------------------------- | ----------------------------------------------------------------------------- |
| A named variable is unset or empty on the host     | A missing precondition fails. An empty string is not a value, and a run that forwarded one would look configured and would not be |
| A named variable is one either credential route owns: `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `CLAUDE_CODE_OAUTH_TOKEN` or one of the four Bedrock names above | `docker.credential` is the one route for Claude's own credential, whatever the variable holds |

Each line names the variable and never its value. A value is read once, where the preflight
reads it, and is not read a second time at container start.

### What carries a name, and what carries a value

| Artefact                    | Carries the name | Carries the value |
| --------------------------- | ---------------- | ----------------- |
| `cowork_evals.yaml`         | yes              | no                |
| `env.txt`                   | yes              | no                |
| `run.log`                   | no               | no                |
| `debug.txt`                 | no               | no                |
| `report.html`               | no               | no                |
| `aggregate-result.json`     | no               | no                |
| A preflight line            | yes              | no                |
| `--dry-run` output          | yes              | no                |
| The container's environment | yes              | yes               |

`--dry-run` prints `NAME=<not shown>` and reads no value at all, so the list it prints is safe to
paste into a message and carries every configured name whether or not the host has that name set.

The table holds for the four names the Bedrock route forwards, with one difference in the
first two rows: those names are configured nowhere, so `cowork_evals.yaml` carries
`credential: bedrock` and `env.txt` carries `credential: bedrock`, and neither carries a
Bedrock name. The route says which credential the run used, and the names the route owns are
the four above.

`run.log` is the one artefact this package cannot fully control. It is captured at the file
descriptor level, so whatever the container prints reaches it, and a case whose prompt makes the
agent print a forwarded value puts that value in the log. The limit is stated rather than closed:
the alternative is filtering the log, which would rewrite what a run actually produced.

## Mounts

| Host path                  | Container path       | Mode | Why                                            |
| -------------------------- | -------------------- | ---- | ---------------------------------------------- |
| the plugin root            | `/work/plugin`       | ro   | The plugin under test                          |
| the run's log dir          | `/work/logs`         | rw   | The only path the run may write outside `/tmp` |
| `<login_dir>/.claude/`     | `$HOME/.claude`      | rw   | The login, above                               |
| `<login_dir>/.claude.json` | `$HOME/.claude.json` | rw   | The login, above                               |

There is no mount for the traces. A run keeping them sets `TMPDIR=/work/logs/tmp` instead, so the
sandbox the harness makes is already inside the log mount. The harness creates each run's sandbox
under `TMPDIR`, the container is started with `--rm`, and a sandbox anywhere else goes with the
container. The host side of `/work/logs/tmp` is emptied once the run's artefacts have been taken
out of it, so nothing under that name survives an invocation. What is taken out, and what a
passing run keeps that a failing one does not, is [running_evals.md](running_evals.md).

The plugin root mounted at `/work/plugin` is the one [cli.md](cli.md) resolves from the path
argument, and the target the harness is given inside the container is that path relative to it.

Read-only everywhere except the log directory and the two credential paths. A case that writes
into the consumer's checkout is a defect and must fail rather than succeed quietly.
`--output-dir` points at `/work/logs`, so the harness's own output does not land in the plugin
directory and the read-only mount does not fail a correct run.

Only the run's own log directory is mounted, not the whole log root, because the host owns every
other path under it.

The container holds nothing from this package. The `cowork_evals` process stays on the host,
builds this argument list, and does everything around the run that it does for either backend:
the run directory, the `latest` symlink, the prune, `env.txt` and the verdict. See
[library.md](library.md).

The container runs with the host user's numeric uid and gid, so log files are not root-owned. A
kept sandbox is therefore the developer's to read and to delete: the harness leaves it read-only
with its `sealed/` trees at mode 000, and the host chmods them back. That uid has no passwd
entry, so `HOME` is set explicitly to a writable path under `/tmp`, created in the image
world-writable.

A uid with no passwd entry is the one thing here that can stop the CLI: Node's `os.userInfo()`
raises rather than returning a stub. It does not on this image, so `--user <uid>:<gid>` is what
the backend passes, and the documented fallback, root plus a `chown -R` of `/work/logs` on the
way out, is not used.

Nothing is staged into the container to supply an interpreter: system `python3` is already 3.10
with the full pin set. The 3.10 mirror in [environments.md](environments.md) is a development
environment on the host and is neither mounted nor built here.

## The Bash sandbox

Granting `Bash` turns on the OS sandbox, and a host with no sandbox backend refuses the run
rather than running unconfined. See [plugin_eval.md](plugin_eval.md).

The image installs `bubblewrap`, 0.6.1 in jammy, and `socat`. The container runs with two
`--security-opt` values, and both are needed.

| Option                   | Without it                                                                                                        |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| `seccomp=unconfined`     | `bwrap: No permissions to create new namespace`. The default profile filters the unprivileged user namespace calls |
| `systempaths=unconfined` | `bwrap: Can't mount proc on /newroot/proc: Operation not permitted`                                               |

The second is the one a bare `bwrap` invocation does not reach. Docker masks entries under
`/proc` by default, and the kernel refuses a fresh procfs mount to a process whose own `/proc` is
covered that way. The harness mounts one, so every sandboxed command fails while
`bwrap --ro-bind / / --unshare-user --unshare-pid true` still succeeds.
`tests/integration/test_docker.py` therefore asserts the `--proc` mount as well as the bare
invocation.

The image also replaces `/run/shm` with a real directory. Jammy ships it as a symlink to
`/dev/shm`, and bubblewrap mounts a tmpfs there: the symlink resolves against a new root whose
`/dev` is not staged yet, so the mount fails with `ENOENT` and every sandboxed command exits 1
with `bwrap: Can't mount tmpfs on /newroot/run/shm`. A `mkdir -p` alone is a no-op on the
symlink, and a `bwrap` invocation without that mount does not reach the failure.

The documented fallback, `--cap-add SYS_ADMIN --security-opt apparmor=unconfined`, is not used:
it fails earlier still, with `bwrap: pivot_root: Operation not permitted`.

A container that cannot grant `Bash` cannot run a case that shells out, which is most of them.

## Image tagging

The image is tagged `cowork-evals:<digest>`, where `<digest>` is the first 12 characters of the
sha256 of the Dockerfile, `requirements.txt`, `requirements_installable.txt`, every build
argument and the resolved `docker.platform`. Without the platform an `arm64` and an `amd64` image
share one tag.

The build arguments are `Docker.build_args`: the resolved `docker.claude_code_version` and the
five container paths, which are `CONTAINER_HOME`, `CONTAINER_WORK`, `CONTAINER_PLUGIN`,
`CONTAINER_LOGS` and `CONTAINER_EXTRA_CA` in `docker/__init__.py`. The Dockerfile writes none of
the five for itself, so a path cannot be changed in Python and left uncreated in the image. Every
build input is in the digest, so no change can be served from a stale image.

There is no `latest` tag. Nothing reads one: `run` and `check` resolve the digest tag, and a
`latest` left behind by an older build points at an image no command would choose.

## Parity

`scripts/parity.sh` runs one probe inside the container, with the probe bind-mounted read-only,
then compares what the probe wrote. It checks the OS release, the architecture, every version in
the runtime tables, `import uno`, the font family count, and the full `pip freeze`.

It is a shell script like every other task under `scripts/`, and the comparison runs on the host.
Nothing from this package is installed into the image to do it.

No file under `docs/` is parsed. The pins come from the shipped `requirements.txt`, and the
non-Python versions are a table in `parity.py` that cites [runtime.md](runtime.md). A change to
that file is carried into the table by hand, in the same commit.

| Delta                                             | Result                 | Why                                                            |
| ------------------------------------------------- | ---------------------- | -------------------------------------------------------------- |
| A pin is missing or at a different version        | exit 1                 | It changes what a skill can import                             |
| A package is installed that is not a pin          | printed, does not fail | A transitive dependency of the tooling is not a fidelity break |
| A tool recorded as not present is present         | exit 1                 | A skill can call it here and not in a session                  |
| `import uno` fails                                | exit 1                 | unoserver and headless conversion are broken                   |
| A tool the probe probes that no table records     | exit 1                 | Its result is compared against nothing and read by nobody      |
| A non-Python tool version differs                 | printed, does not fail | A jammy point release moves a patch version and must not block |
| A tool recorded with a version is absent          | printed, does not fail | The report names it and the comparison has nothing to do       |
| A tool recorded present with no version is absent | printed, does not fail | There is no version to compare it against                      |
| The font family count, the OS or the architecture differs | printed, does not fail | Each is a condition of the run and is reported with it |

The tools recorded as not present are `wkhtmltopdf`, `weasyprint`, `exiftool`, `docker` and the
`sqlite3` CLI. The three recorded present with no version are `ssh`, which
[runtime.md](runtime.md) lists without one, and `bwrap` and `socat`, the two deltas above, which
it does not record at all.

Every tool `probe.py` probes is in exactly one of the three tables in `parity.py`. Which table a
new one goes in is decided by what is recorded for it: a version, presence alone, or absence.

The probe writes one JSON document. `tests/unit/test_parity.py` asserts over recorded copies of
it under `tests/data/docker/`, one per row of the table above, so the tests start no container.

## What the container does not reproduce

Stated once so no reader assumes otherwise: the CoWork model routing, the admin-applied
enterprise prompt, the CoWork MCP servers, the `/sessions/<session>` filesystem layout, the vsock
host RPC, and the session lifecycle. It is an image, not the deployed stack. For those, see
[cowork_driver.md](cowork_driver.md).

## Measurements

Measured on one host and true of that host. The host is written as its OS, architecture and
container runtime, never as a machine name. A reader on another platform re-runs
`scripts/parity.sh` and the integration tier rather than assuming these.

| Measurement                      | Value                                                                                                                                |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Host                             | macOS on aarch64, Rancher Desktop, dockerd 29.5.3                                                                                    |
| Platform built                   | `linux/arm64`, native                                                                                                                |
| Image size                       | 3.72 GB                                                                                                                              |
| Build time, cold                 | 5 min 30 s, `--no-cache`, native, over a proxy                                                                                       |
| Build time, warm                 | under a second: the digest is present, so nothing runs                                                                               |
| Python pin mismatches            | 0 of 136                                                                                                                             |
| Extra Python packages            | 0                                                                                                                                    |
| Non-Python deltas                | Java 11.0.32 against the recorded 11.0.31, a jammy point release. `socat`, which the inventory does not record, for the shell sandbox |
| Font families in the image       | 111 against the recorded 118                                                                                                         |
| `import uno` from system python3 | yes                                                                                                                                  |
| Extra root CA needed             | yes on this host. Three upstream hosts inspect TLS                                                                                   |

All 136 pins are present at the recorded version, the nine from apt included, so the fidelity
gain over the mirror is real. Both non-Python deltas are printed by `scripts/parity.sh` and
neither fails it.

The font count is 7 families short. The image installs the Noto fallback faces rather than
`fonts-noto-core`, which alone adds 192 families over the record, so the remaining gap is between
one jammy font package and another rather than between two font stacks.
