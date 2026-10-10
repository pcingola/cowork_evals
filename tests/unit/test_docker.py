"""The container backend's digest and its argument lists. docs/docker.md.

Nothing here starts a container or reaches a daemon. A function that starts one is
covered in tests/integration/test_docker.py.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from cowork_evals.config import Config, DockerSection
from cowork_evals.docker import (
    CONTAINER_EXTRA_CA,
    CONTAINER_HOME,
    CONTAINER_KEEP_FILE,
    CONTAINER_LOGS,
    CONTAINER_PLUGIN,
    CONTAINER_WORK,
    COWORK_ENV,
    DATA,
    DOCKERFILE,
    EXTRA_CA_SECRET,
    KEEP_FILE,
    Condition,
    Credentials,
    Docker,
    DockerError,
    Image,
    OAuth,
    host_zone,
    images_argv,
    parse_images,
    remedy,
    remove_image_argv,
)

# The zone `docker image ls` printed in the recorded listing below.
EDT = timezone(timedelta(hours=-4))
CA = "NODE_EXTRA_CA_CERTS=/usr/local/share/ca-certificates/extra_ca.crt"


def build_arg(argv: list[str], flag: str) -> str:
    """The value that follows `flag`. Fails the test when the flag is absent."""
    return argv[argv.index(flag) + 1]


def backend(**values) -> Docker:
    """A backend over one written `docker:` section. There is no other route in."""
    return Docker(Config(docker=DockerSection(**values)))


def mounts(argv: list[str]) -> list[str]:
    return [argv[i + 1] for i, value in enumerate(argv) if value == "-v"]


# The digest, and the tag over it.


def test_the_tag_names_a_twelve_hex_digest():
    assert re.fullmatch(r"cowork-evals:[0-9a-f]{12}", backend().tag)


@pytest.mark.parametrize(
    ("other", "equal"),
    [
        ({}, True),
        ({"platform": "linux/amd64"}, False),
        ({"claude_code_version": "2.1.260"}, False),
        # The lists are read on every run, so changing one needs no rebuild.
        ({"keep_env": (*DockerSection().keep_env, "ACME")}, True),
    ],
)
def test_the_digest_covers_the_build_inputs_and_nothing_else(other: dict, equal: bool):
    base = {"platform": "linux/arm64", "claude_code_version": "2.1.259"}
    assert (backend(**base).digest == backend(**{**base, **other}).digest) is equal


# The build argument list.


def test_build_argv_is_the_documented_list():
    docker = backend()
    assert docker.build_argv() == [
        "docker",
        "build",
        "--platform",
        "linux/arm64",
        "-f",
        str(DOCKERFILE),
        "--build-arg",
        "CLAUDE_CODE_VERSION=2.1.265",
        "--build-arg",
        "CONTAINER_HOME=/tmp/eval-home",
        "--build-arg",
        "CONTAINER_WORK=/work",
        "--build-arg",
        "CONTAINER_PLUGIN=/work/plugin",
        "--build-arg",
        "CONTAINER_LOGS=/work/logs",
        "--build-arg",
        "CONTAINER_EXTRA_CA=/usr/local/share/ca-certificates/extra_ca.crt",
        "-t",
        docker.tag,
        str(DATA),
    ]


def test_the_dockerfile_holds_no_container_path_of_its_own():
    """A literal reintroduced there is a path the image creates and this package never uses."""
    dockerfile = DOCKERFILE.read_text()
    for path in (CONTAINER_HOME, CONTAINER_WORK, CONTAINER_PLUGIN, CONTAINER_LOGS):
        assert path not in dockerfile, f"{path} is written in the Dockerfile as well"
    assert CONTAINER_EXTRA_CA not in dockerfile


def test_the_secret_id_the_dockerfile_mounts_is_the_one_build_argv_passes():
    """The one string still written on both sides. It is not a build argument."""
    assert f"--mount=type=secret,id={EXTRA_CA_SECRET}" in DOCKERFILE.read_text()


def test_no_cache_is_off_unless_asked():
    assert "--no-cache" not in backend().build_argv()
    assert "--no-cache" in backend().build_argv(no_cache=True)


def test_a_configured_extra_ca_is_a_build_secret_and_node_trusts_it(plugin, tmp_path, run_options):
    ca = tmp_path / "root_ca.pem"
    ca.write_text("-----BEGIN CERTIFICATE-----\n")
    docker = backend(extra_ca_file=ca)
    assert build_arg(docker.build_argv(), "--secret") == f"id=extra_ca,src={ca}"
    assert CA in docker.login_argv()
    assert CA in docker.run_argv(plugin, tmp_path, run_options)


@pytest.mark.parametrize("absent", [False, True])
def test_no_extra_ca_when_the_file_names_none_or_it_is_not_on_disk(tmp_path, absent: bool):
    docker = backend(extra_ca_file=tmp_path / "absent.pem" if absent else None)
    assert "--secret" not in docker.build_argv()
    assert CA not in docker.login_argv()


# The login argument list.


def test_login_argv_mounts_the_two_credential_paths_read_write(tmp_path):
    argv = backend(login_dir=tmp_path / "login").login_argv()
    assert mounts(argv) == [
        f"{tmp_path}/login/.claude:/tmp/eval-home/.claude:rw",
        f"{tmp_path}/login/.claude.json:/tmp/eval-home/.claude.json:rw",
    ]


def test_login_argv_is_interactive_and_goes_straight_to_the_login():
    """Bare `claude` lands in the first-run wizard on a fresh configuration directory."""
    docker = backend()
    argv = docker.login_argv()
    assert argv[:4] == ["docker", "run", "--rm", "-it"]
    assert argv[-5:] == [docker.tag, "claude", "auth", "login", "--claudeai"]
    assert build_arg(argv, "--user") == f"{os.getuid()}:{os.getgid()}"
    assert f"HOME={CONTAINER_HOME}" in argv


# The run argument list.


@pytest.fixture
def plugin(tmp_path):
    """A plugin root with one case under it, on disk. Nothing here starts a container."""
    root = tmp_path / "smoke"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text("{}")
    (root / "evals" / "plugin" / "python-version").mkdir(parents=True)
    return root


@pytest.mark.parametrize(
    ("relative", "target"),
    [
        ("evals/plugin/python-version", "/work/plugin/evals/plugin/python-version"),
        ("", "/work/plugin"),
    ],
)
def test_the_container_side_target_is_relative_to_the_plugin_root(
    plugin, tmp_path, run_options, relative: str, target: str
):
    assert target in backend().run_argv(plugin / relative, tmp_path, run_options)


def test_the_harness_follows_the_tag_and_writes_into_the_log_mount(plugin, tmp_path, run_options):
    docker = backend()
    argv = docker.run_argv(plugin, tmp_path, run_options)
    assert argv[argv.index(docker.tag) + 1] == "claude"
    assert build_arg(argv, "--output-dir") == "/work/logs"


def test_run_argv_mounts_the_documented_table(plugin, tmp_path, run_options):
    """The one credential route, the plugin, the logs and the keep file. Nothing else."""
    logs = tmp_path / "logs"
    logs.mkdir()
    argv = backend(login_dir=tmp_path / "login").run_argv(plugin, logs, run_options)
    assert mounts(argv) == [
        f"{tmp_path}/login/.claude:/tmp/eval-home/.claude:rw",
        f"{tmp_path}/login/.claude.json:/tmp/eval-home/.claude.json:rw",
        f"{plugin.resolve()}:/work/plugin:ro",
        f"{logs.resolve()}:/work/logs:rw",
        f"{logs.resolve()}/keep_env.txt:/etc/cowork_evals/keep_env.txt:ro",
    ]


@pytest.mark.parametrize("keep", [True, False])
def test_a_kept_trace_puts_the_harness_tmpdir_in_the_log_mount(
    plugin, tmp_path, run_options, keep: bool
):
    """The log mount is the only writable host path, so a kept sandbox has to land there."""
    argv = backend().run_argv(plugin, tmp_path, replace(run_options, keep_traces=keep))
    assert ("--keep-temp" in argv) is keep
    assert [value for value in argv if value.startswith("TMPDIR=")] == (
        ["TMPDIR=/work/logs/tmp"] if keep else []
    )


# Environment passthrough. docs/docker.md.
#
# `monkeypatch.setenv` sets a real variable in this process, which is the environment the
# backend reads. Nothing here stands in for the read.

# A name no machine sets, so an absent one is absent because nothing set it.
PROBE = "COWORK_EVALS_TEST_PROBE"
VALUE = "probe-value-not-a-secret"


def forwarded(argv: list[str]) -> list[str]:
    """Every `--env` value in the list, which is where a forwarded variable lands."""
    return [argv[i + 1] for i, value in enumerate(argv) if value == "--env"]


def test_run_preamble_carries_the_forwarded_name_and_value(monkeypatch):
    monkeypatch.setenv(PROBE, VALUE)
    argv = backend(env_passthrough=[PROBE]).run_preamble()
    assert f"{PROBE}={VALUE}" in forwarded(argv)


def test_run_preamble_is_the_documented_list(tmp_path):
    """`TZ` is the host's zone, written only when the host has one."""
    zone = host_zone()
    assert backend(login_dir=tmp_path / "login").run_preamble() == [
        "docker",
        "run",
        "--rm",
        "--platform",
        "linux/arm64",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--env",
        "HOME=/tmp/eval-home",
        "--env",
        "CLAUDE_CODE_WALNUT_SPIRE=1",
        *(["--env", f"TZ={zone}"] if zone is not None else []),
        "--security-opt",
        "seccomp=unconfined",
        "--security-opt",
        "systempaths=unconfined",
        "-v",
        f"{tmp_path}/login/.claude:/tmp/eval-home/.claude:rw",
        "-v",
        f"{tmp_path}/login/.claude.json:/tmp/eval-home/.claude.json:rw",
    ]


def test_a_name_the_host_does_not_set_is_never_forwarded_as_an_empty_string(monkeypatch):
    """The preflight refuses it first. This is the rule held where it would be broken."""
    monkeypatch.delenv(PROBE, raising=False)
    with pytest.raises(DockerError) as raised:
        backend(env_passthrough=[PROBE]).run_preamble()
    assert PROBE in str(raised.value)


def test_a_value_is_read_once_and_not_again_at_container_start(monkeypatch):
    """`check` reads the host, and the argument list uses what it read."""
    monkeypatch.setenv(PROBE, VALUE)
    docker = backend(env_passthrough=[PROBE])
    assert docker.check_environment() == []
    monkeypatch.setenv(PROBE, "a-different-value")
    assert f"{PROBE}={VALUE}" in forwarded(docker.run_preamble())


@pytest.mark.parametrize("value", [None, ""])
def test_an_absent_or_empty_name_is_one_unmet_condition_naming_it(monkeypatch, value):
    """An empty string is not a value."""
    if value is None:
        monkeypatch.delenv(PROBE, raising=False)
    else:
        monkeypatch.setenv(PROBE, value)
    unmet = backend(env_passthrough=[PROBE]).check_environment()
    assert [line.condition for line in unmet] == [Condition.ENVIRONMENT]
    assert PROBE in unmet[0].message


@pytest.mark.parametrize("held", [True, False])
@pytest.mark.parametrize(
    "name",
    [
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "CLAUDE_CODE_USE_BEDROCK",
        "AWS_BEARER_TOKEN_BEDROCK",
        "ANTHROPIC_BEDROCK_BASE_URL",
        "AWS_REGION",
    ],
)
def test_a_credential_name_is_refused_whatever_it_holds(monkeypatch, name: str, held: bool):
    if held:
        monkeypatch.setenv(name, VALUE)
    else:
        monkeypatch.delenv(name, raising=False)
    unmet = backend(env_passthrough=[name]).check_environment()
    assert [line.condition for line in unmet] == [Condition.ENV_CREDENTIAL]
    assert name in unmet[0].message
    assert "cowork_evals login --docker" in unmet[0].message


def test_no_message_about_a_forwarded_variable_carries_its_value(monkeypatch):
    monkeypatch.setenv(PROBE, VALUE)
    monkeypatch.setenv("ANTHROPIC_API_KEY", VALUE)
    unmet = backend(env_passthrough=[PROBE, "ANTHROPIC_API_KEY"]).check_environment()
    assert VALUE not in " ".join(line.message for line in unmet)


def test_the_conditions_reach_the_whole_check(monkeypatch):
    """`check --docker` reports them, so a developer sees them without starting a run."""
    monkeypatch.delenv(PROBE, raising=False)
    unmet = backend(env_passthrough=[PROBE]).check()
    assert Condition.ENVIRONMENT in [line.condition for line in unmet]


# The login this package owns. docs/docker.md, "Credentials".


@pytest.mark.parametrize(
    ("document", "login"),
    [
        (None, False),
        (Credentials(claude_ai_oauth=OAuth(access_token="tok", refresh_token="ref")), True),
        # The CLI refreshes an expired token, so an expiry in the past is still a login.
        (
            Credentials(claude_ai_oauth=OAuth(access_token="", refresh_token="ref", expires_at=0)),
            True,
        ),
        (
            Credentials(
                claude_ai_oauth=OAuth(
                    access_token="",
                    refresh_token="",
                    expires_at=0,
                    scopes=["user:inference"],
                    subscription_type="max",
                )
            ),
            False,
        ),
        ("", False),
        (Credentials(), False),
    ],
)
def test_a_login_is_a_credential_file_holding_a_token(
    tmp_path, document: Credentials | str | None, login: bool
):
    docker = backend(login_dir=tmp_path / "login")
    if document is not None:
        docker.claude_dir.mkdir(parents=True)
        if isinstance(document, Credentials):
            document = document.model_dump_json(by_alias=True, exclude_none=True)
        docker.credentials_file.write_text(document, encoding="utf-8")
    assert docker.has_credential() is login


@pytest.mark.parametrize(
    ("prior", "after"), [(None, "{}"), ("", "{}"), ('{"kept": true}', '{"kept": true}')]
)
def test_seed_login_dir_writes_a_state_file_the_cli_will_accept(
    tmp_path, prior: str | None, after: str
):
    """An empty `.claude.json` is not an absent one: the CLI exits 1 on it."""
    docker = backend(login_dir=tmp_path / "login")
    if prior is not None:
        docker.claude_dir.mkdir(parents=True)
        docker.state_file.write_text(prior)
    docker.seed_login_dir()
    assert docker.claude_dir.is_dir()
    assert docker.state_file.read_text() == after


# The remedy. Every caller reads it here, and it names what a consumer runs.


@pytest.mark.parametrize(
    ("condition", "fix"),
    [
        (Condition.IMAGE, "run cowork_evals setup --docker"),
        # An image is a build product and a credential is not, so one command does not fix both.
        (Condition.CREDENTIAL, "run cowork_evals login --docker"),
        (Condition.DAEMON, "start Docker Desktop or Rancher Desktop"),
    ],
)
def test_each_condition_names_its_one_remedy(condition: Condition, fix: str):
    assert remedy(condition) == fix


def test_no_remedy_names_a_development_script():
    """A consumer never sees `scripts/`. docs/library.md."""
    assert not [condition for condition in Condition if "scripts/" in remedy(condition)]


# The image inventory, for `prune --docker`. Both argument lists are asserted here, with
# no daemon: this module is the one place a `docker` argument list is built.


def test_the_image_listing_names_every_repository_it_was_given():
    assert images_argv("cowork-evals", "cowork-evals-test") == [
        "docker",
        "image",
        "ls",
        "--filter",
        "reference=cowork-evals:*",
        "--filter",
        "reference=cowork-evals-test:*",
        "--format",
        "{{.Repository}}:{{.Tag}}\t{{.CreatedAt}}",
    ]


def test_the_image_removal_names_one_tag():
    assert remove_image_argv("cowork-evals:0123456789ab") == [
        "docker",
        "image",
        "rm",
        "cowork-evals:0123456789ab",
    ]


def test_a_recorded_listing_parses_into_tags_and_dates():
    """One recorded `docker image ls` listing, as that command prints it."""
    listing = (
        "cowork-evals-test:0eafee9a4184\t2026-09-09 05:15:58 -0400 EDT\n"
        "cowork-evals:57f48ba2adac\t2026-09-09 04:08:37 -0400 EDT\n"
        "cowork-evals:9e9d75cdfb6e\t2026-09-08 16:47:25 -0400 EDT\n"
    )
    assert parse_images(listing) == [
        Image("cowork-evals-test:0eafee9a4184", datetime(2026, 9, 9, 5, 15, 58, tzinfo=EDT)),
        Image("cowork-evals:57f48ba2adac", datetime(2026, 9, 9, 4, 8, 37, tzinfo=EDT)),
        Image("cowork-evals:9e9d75cdfb6e", datetime(2026, 9, 8, 16, 47, 25, tzinfo=EDT)),
    ]


# The session environment. docs/docker.md, "The session environment".


@pytest.mark.parametrize(
    ("target", "zone"),
    [
        ("/var/db/timezone/zoneinfo/America/New_York", "America/New_York"),
        (None, None),
        ("/etc/elsewhere", None),
    ],
)
def test_the_host_zone_is_the_localtime_target_after_zoneinfo(
    tmp_path, target: str | None, zone: str | None
):
    """A `localtime` that is a regular file gives no zone."""
    localtime = tmp_path / "localtime"
    if target is None:
        localtime.write_text("TZif")
    else:
        localtime.symlink_to(target)
    assert host_zone(localtime) == zone


def test_the_script_reads_the_path_the_keep_file_is_mounted_at():
    assert f"keep_file={CONTAINER_KEEP_FILE}\n" in COWORK_ENV.read_text()


def test_the_dockerfile_installs_the_script_as_the_shell_prefix():
    dockerfile = DOCKERFILE.read_text()
    assert f"COPY {COWORK_ENV.name} /usr/local/bin/cowork-env" in dockerfile
    assert '"CLAUDE_CODE_SHELL_PREFIX": "/usr/local/bin/cowork-env"' in dockerfile


def test_the_keep_file_holds_the_three_lists_one_name_per_line(tmp_path):
    docker = backend(session_env=["HOME", "PATH"], env_passthrough=[PROBE], keep_env=["ACME"])
    written = docker.write_keep_file(tmp_path)
    assert written == tmp_path / KEEP_FILE
    assert written.read_text() == "HOME\nPATH\nCOWORK_EVALS_TEST_PROBE\nACME\n"


def digest_over(docker: Docker, *paths) -> str:
    """`Docker.digest`, recomputed over the given build files."""
    sha = hashlib.sha256()
    for path in paths:
        sha.update(path.read_bytes())
        sha.update(b"\0")
    for name, value in docker.build_args.items():
        sha.update(f"{name}={value}".encode())
        sha.update(b"\0")
    sha.update(docker.platform.encode())
    return sha.hexdigest()[:12]


def test_the_script_is_hashed_into_the_digest():
    """A changed script is a different tag, and never a stale image."""
    docker = backend()
    files = (DOCKERFILE, DATA / "requirements.txt", DATA / "requirements_installable.txt")
    assert docker.digest == digest_over(docker, *files, COWORK_ENV)
    assert docker.digest != digest_over(docker, *files)
