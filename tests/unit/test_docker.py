"""The container backend's digest and its argument lists. docs/docker.md.

Nothing here starts a container or reaches a daemon. A function that starts one is
covered in tests/integration/test_docker.py.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone

import pytest

from cowork_evals.config import Config, DockerSection
from cowork_evals.docker import (
    BEDROCK_NAMES,
    CONTAINER_EXTRA_CA,
    CONTAINER_HOME,
    CONTAINER_LOGS,
    CONTAINER_PLUGIN,
    CONTAINER_TMPDIR,
    CONTAINER_WORK,
    CREDENTIAL_NAMES,
    DATA,
    DOCKERFILE,
    EXTRA_CA_SECRET,
    REDACTED,
    Condition,
    Docker,
    DockerError,
    images_argv,
    parse_images,
    plugin_root,
    remedy,
    remove_image_argv,
)
from cowork_evals.harness import RunOptions

# The zone `docker image ls` printed in the recorded listing below.
EDT = timezone(timedelta(hours=-4))


def build_arg(argv: list[str], flag: str) -> str:
    """The value that follows `flag`. Fails the test when the flag is absent."""
    return argv[argv.index(flag) + 1]


def backend(**values) -> Docker:
    """A backend over one written `docker:` section. There is no other route in."""
    return Docker(Config(docker=DockerSection(**values)))


# The digest, and the tag over it.


def test_the_digest_is_twelve_hex_characters():
    assert re.fullmatch(r"[0-9a-f]{12}", backend().digest)


def test_the_digest_is_stable_across_instances():
    first = backend(claude_code_version="2.1.259")
    second = backend(claude_code_version="2.1.259")
    assert first.digest == second.digest


def test_the_platform_is_in_the_digest():
    """Without it an arm64 and an amd64 image share one tag."""
    arm = backend(platform="linux/arm64", claude_code_version="2.1.259")
    amd = backend(platform="linux/amd64", claude_code_version="2.1.259")
    assert arm.digest != amd.digest


def test_the_claude_code_version_is_in_the_digest():
    older = backend(claude_code_version="2.1.259")
    newer = backend(claude_code_version="2.1.260")
    assert older.digest != newer.digest


def test_the_tag_names_the_digest():
    docker = backend()
    assert docker.tag == f"cowork-evals:{docker.digest}"


# The configuration behind it.


def test_the_defaults_are_the_ones_docs_docker_records():
    docker = backend()
    assert docker.platform == "linux/arm64"
    assert docker.claude_code_version == "2.1.265"


def test_the_configuration_is_read_from_the_working_directory_when_none_is_passed(
    working_directory, tmp_path
):
    (tmp_path / "cowork_evals.yaml").write_text(
        "docker:\n  platform: linux/amd64\n", encoding="utf-8"
    )
    with working_directory(tmp_path):
        assert Docker().platform == "linux/amd64"


def test_the_login_dir_defaults_under_the_cache():
    docker = backend()
    assert docker.login_dir == docker.login_dir.home() / ".cache/cowork_evals/claude"
    assert docker.claude_dir == docker.login_dir / ".claude"
    assert docker.state_file == docker.login_dir / ".claude.json"
    assert docker.credentials_file == docker.claude_dir / ".credentials.json"


def test_a_relative_login_dir_is_resolved_before_it_reaches_a_mount(working_directory, tmp_path):
    """`docker -v` takes an absolute path, so `Config`'s path convention is what resolves it."""
    (tmp_path / "cowork_evals.yaml").write_text(
        "docker:\n  login_dir: state/login\n", encoding="utf-8"
    )
    with working_directory(tmp_path):
        docker = Docker()
    assert docker.login_dir == tmp_path / "state" / "login"
    assert docker.credential_argv()[1].startswith(f"{tmp_path}/state/login/.claude:")


# The build argument list.


def test_build_argv_names_the_dockerfile_and_the_data_context():
    argv = backend().build_argv()
    assert argv[:2] == ["docker", "build"]
    assert build_arg(argv, "-f") == str(DOCKERFILE)
    assert argv[-1] == str(DATA), "the context is the package data directory, and comes last"


def test_build_argv_carries_the_platform_the_tag_and_the_build_argument():
    docker = backend(claude_code_version="2.1.259")
    argv = docker.build_argv()
    assert build_arg(argv, "--platform") == "linux/arm64"
    assert build_arg(argv, "--build-arg") == "CLAUDE_CODE_VERSION=2.1.259"
    assert build_arg(argv, "-t") == docker.tag


def test_build_argv_carries_every_container_path_as_a_build_argument():
    """The Dockerfile takes them from here, so the two sides cannot name different paths."""
    argv = backend().build_argv()
    passed = [argv[i + 1] for i, value in enumerate(argv) if value == "--build-arg"]
    assert f"CONTAINER_HOME={CONTAINER_HOME}" in passed
    assert f"CONTAINER_WORK={CONTAINER_WORK}" in passed
    assert f"CONTAINER_PLUGIN={CONTAINER_PLUGIN}" in passed
    assert f"CONTAINER_LOGS={CONTAINER_LOGS}" in passed
    assert f"CONTAINER_EXTRA_CA={CONTAINER_EXTRA_CA}" in passed


def test_the_dockerfile_holds_no_container_path_of_its_own():
    """A literal reintroduced there is a path the image creates and this package never uses."""
    dockerfile = DOCKERFILE.read_text()
    for path in (CONTAINER_HOME, CONTAINER_WORK, CONTAINER_PLUGIN, CONTAINER_LOGS):
        assert path not in dockerfile, f"{path} is written in the Dockerfile as well"
    assert CONTAINER_EXTRA_CA not in dockerfile


def test_the_secret_id_the_dockerfile_mounts_is_the_one_build_argv_passes():
    """The one string still written on both sides. It is not a build argument."""
    assert f"--mount=type=secret,id={EXTRA_CA_SECRET}" in DOCKERFILE.read_text()


def test_build_argv_carries_one_tag_and_no_latest():
    argv = backend().build_argv()
    assert argv.count("-t") == 1
    assert "cowork-evals:latest" not in argv


def test_no_cache_is_off_unless_asked():
    assert "--no-cache" not in backend().build_argv()
    assert "--no-cache" in backend().build_argv(no_cache=True)


def test_the_extra_ca_is_a_build_secret_when_the_file_names_one(tmp_path):
    ca = tmp_path / "root_ca.pem"
    ca.write_text("-----BEGIN CERTIFICATE-----\n")
    argv = backend(extra_ca_file=ca).build_argv()
    assert build_arg(argv, "--secret") == f"id=extra_ca,src={ca}"


def test_there_is_no_extra_ca_when_the_file_names_none():
    assert "--secret" not in backend().build_argv()


def test_an_extra_ca_file_that_is_not_on_disk_is_no_extra_ca(tmp_path):
    assert backend(extra_ca_file=tmp_path / "absent.pem").extra_ca_file is None


# The login argument list.


def test_login_argv_mounts_the_two_credential_paths_read_write():
    docker = backend()
    argv = docker.login_argv()
    mounts = [argv[i + 1] for i, value in enumerate(argv) if value == "-v"]
    assert mounts == [
        f"{docker.claude_dir}:{CONTAINER_HOME}/.claude:rw",
        f"{docker.state_file}:{CONTAINER_HOME}/.claude.json:rw",
    ]


def test_login_argv_mounts_no_plugin_and_no_log_directory():
    argv = backend().login_argv()
    assert "/work/plugin" not in " ".join(argv)
    assert "/work/logs" not in " ".join(argv)


def test_login_argv_is_interactive_and_goes_straight_to_the_login():
    """Bare `claude` lands in the first-run wizard on a fresh configuration directory."""
    docker = backend()
    argv = docker.login_argv()
    assert argv[:4] == ["docker", "run", "--rm", "-it"]
    assert argv[-5:] == [docker.tag, "claude", "auth", "login", "--claudeai"]
    assert build_arg(argv, "--user") == f"{os.getuid()}:{os.getgid()}"
    assert f"HOME={CONTAINER_HOME}" in argv


def test_login_argv_points_node_at_the_extra_ca_when_the_file_names_one(tmp_path):
    ca = tmp_path / "root_ca.pem"
    ca.write_text("-----BEGIN CERTIFICATE-----\n")
    argv = backend(extra_ca_file=ca).login_argv()
    assert f"NODE_EXTRA_CA_CERTS={CONTAINER_EXTRA_CA}" in argv


# The plugin root.


def test_the_plugin_root_is_the_nearest_manifest_above_the_target(tmp_path):
    root = tmp_path / "marketplace" / "smoke"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text("{}")
    case = root / "evals" / "plugin" / "python-version"
    case.mkdir(parents=True)
    assert plugin_root(case) == root.resolve()
    assert plugin_root(root) == root.resolve(), "the root itself is a target the CLI accepts"


def test_a_target_under_no_plugin_raises(tmp_path):
    with pytest.raises(DockerError):
        plugin_root(tmp_path)


# The run argument list.


@pytest.fixture
def plugin(tmp_path):
    """A plugin root with one case under it, on disk. Nothing here starts a container."""
    root = tmp_path / "smoke"
    (root / ".claude-plugin").mkdir(parents=True)
    (root / ".claude-plugin" / "plugin.json").write_text("{}")
    (root / "evals" / "plugin" / "python-version").mkdir(parents=True)
    return root


def run_options(**overrides) -> RunOptions:
    fixed = {
        "model": "sonnet",
        "judge_model": "haiku",
        "ablation": "none",
        "max_cost_usd": "5",
        "allow_tools": ("Bash",),
    }
    return RunOptions(**{**fixed, **overrides})


def test_run_argv_mounts_the_plugin_read_only_and_the_logs_read_write(plugin, tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    argv = backend().run_argv(plugin, logs, run_options())
    mounts = [argv[i + 1] for i, value in enumerate(argv) if value == "-v"]
    assert mounts[-2:] == [
        f"{plugin.resolve()}:/work/plugin:ro",
        f"{logs.resolve()}:/work/logs:rw",
    ]


def test_run_argv_carries_the_uid_the_home_and_the_sandbox_options(plugin, tmp_path):
    argv = backend().run_argv(plugin, tmp_path, run_options())
    assert argv[:3] == ["docker", "run", "--rm"]
    assert build_arg(argv, "--platform") == "linux/arm64"
    assert build_arg(argv, "--user") == f"{os.getuid()}:{os.getgid()}"
    assert f"HOME={CONTAINER_HOME}" in argv
    options = [argv[i + 1] for i, value in enumerate(argv) if value == "--security-opt"]
    assert options == ["seccomp=unconfined", "systempaths=unconfined"]
    assert "CLAUDE_CODE_WALNUT_SPIRE=1" in argv


def test_the_container_side_target_is_relative_to_the_plugin_root(plugin, tmp_path):
    case = plugin / "evals" / "plugin" / "python-version"
    argv = backend().run_argv(case, tmp_path, run_options())
    assert "/work/plugin/evals/plugin/python-version" in argv


def test_the_plugin_root_itself_is_the_mount_point(plugin, tmp_path):
    argv = backend().run_argv(plugin, tmp_path, run_options())
    assert "/work/plugin" in argv


def test_the_output_dir_is_the_log_mount(plugin, tmp_path):
    argv = backend().run_argv(plugin, tmp_path, run_options())
    assert build_arg(argv, "--output-dir") == "/work/logs"
    assert build_arg(argv, "--debug-file") == "/work/logs/debug.txt"


def test_the_two_login_paths_are_mounted_read_write(plugin, tmp_path):
    """The one credential route. docs/docker.md."""
    logs = tmp_path / "logs"
    logs.mkdir()
    docker = backend()
    argv = docker.run_argv(plugin, logs, run_options())
    mounts = [argv[i + 1] for i, value in enumerate(argv) if value == "-v"]
    assert mounts == [
        f"{docker.claude_dir}:{CONTAINER_HOME}/.claude:rw",
        f"{docker.state_file}:{CONTAINER_HOME}/.claude.json:rw",
        f"{plugin.resolve()}:/work/plugin:ro",
        f"{logs.resolve()}:/work/logs:rw",
    ]


def test_run_argv_ends_with_the_tag_and_the_harness_command(plugin, tmp_path):
    docker = backend()
    argv = docker.run_argv(plugin, tmp_path, run_options())
    image = argv.index(docker.tag)
    assert argv[image + 1 : image + 4] == ["claude", "--debug-file", "/work/logs/debug.txt"]
    assert "--no-publish" in argv[image:]


def test_run_argv_mounts_nothing_else_from_the_host(plugin, tmp_path):
    """The two login paths, the plugin and the logs. Nothing else."""
    argv = backend().run_argv(plugin, tmp_path, run_options())
    assert argv.count("-v") == 4


def test_a_run_keeping_its_traces_puts_the_harness_tmpdir_in_the_log_mount(plugin, tmp_path):
    """The log mount is the only writable host path, so a kept sandbox has to land there."""
    argv = backend().run_argv(plugin, tmp_path, run_options(keep_traces=True))
    assert f"TMPDIR={CONTAINER_TMPDIR}" in argv
    assert CONTAINER_TMPDIR.startswith(f"{CONTAINER_LOGS}/")
    assert "--keep-temp" in argv


def test_a_run_that_keeps_no_trace_moves_no_tmpdir_and_keeps_no_sandbox(plugin, tmp_path):
    argv = backend().run_argv(plugin, tmp_path, run_options(keep_traces=False))
    assert not [value for value in argv if value.startswith("TMPDIR=")]
    assert "--keep-temp" not in argv


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


def test_an_empty_env_passthrough_produces_the_list_it_produces_today():
    """Byte for byte, so a repository that names none is unaffected by the setting."""
    assert backend().run_preamble() == [
        "docker",
        "run",
        "--rm",
        "--platform",
        "linux/arm64",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "--env",
        f"HOME={CONTAINER_HOME}",
        "--env",
        "CLAUDE_CODE_WALNUT_SPIRE=1",
        "--security-opt",
        "seccomp=unconfined",
        "--security-opt",
        "systempaths=unconfined",
        *backend().credential_argv(),
    ]


def test_a_name_the_host_does_not_set_is_never_forwarded_as_an_empty_string(monkeypatch):
    """The preflight refuses it first. This is the rule held where it would be broken."""
    monkeypatch.delenv(PROBE, raising=False)
    with pytest.raises(DockerError) as raised:
        backend(env_passthrough=[PROBE]).run_preamble()
    assert PROBE in str(raised.value)


def test_the_redacted_list_replaces_the_value_and_reads_none(monkeypatch):
    monkeypatch.setenv(PROBE, VALUE)
    argv = backend(env_passthrough=[PROBE]).run_preamble(redact=True)
    assert f"{PROBE}={REDACTED}" in forwarded(argv)
    assert VALUE not in " ".join(argv)


def test_the_redacted_list_carries_a_name_the_host_has_not_set(monkeypatch):
    """A dry run skips the preflight, so it names what is configured and not what is there."""
    monkeypatch.delenv(PROBE, raising=False)
    argv = backend(env_passthrough=[PROBE]).run_preamble(redact=True)
    assert f"{PROBE}={REDACTED}" in forwarded(argv)


def test_a_value_is_read_once_and_not_again_at_container_start(monkeypatch):
    """`check` reads the host, and the argument list uses what it read."""
    monkeypatch.setenv(PROBE, VALUE)
    docker = backend(env_passthrough=[PROBE])
    assert docker.check_environment() == []
    monkeypatch.setenv(PROBE, "a-different-value")
    assert f"{PROBE}={VALUE}" in forwarded(docker.run_preamble())


def test_an_absent_name_is_one_unmet_condition_naming_it(monkeypatch):
    monkeypatch.delenv(PROBE, raising=False)
    unmet = backend(env_passthrough=[PROBE]).check_environment()
    assert [condition for condition, _ in unmet] == [Condition.ENVIRONMENT]
    assert PROBE in unmet[0][1]


def test_an_empty_name_is_the_same_condition(monkeypatch):
    """An empty string is not a value."""
    monkeypatch.setenv(PROBE, "")
    assert [condition for condition, _ in backend(env_passthrough=[PROBE]).check_environment()] == [
        Condition.ENVIRONMENT
    ]


def test_a_credential_name_is_refused_whatever_it_holds(monkeypatch):
    for name in sorted(CREDENTIAL_NAMES):
        monkeypatch.setenv(name, VALUE)
        unmet = backend(env_passthrough=[name]).check_environment()
        assert [condition for condition, _ in unmet] == [Condition.ENV_CREDENTIAL], name
        assert name in unmet[0][1]
        assert "cowork_evals login --docker" in unmet[0][1]


def test_a_credential_name_is_refused_when_the_host_does_not_set_it_either(monkeypatch):
    for name in sorted(CREDENTIAL_NAMES):
        monkeypatch.delenv(name, raising=False)
        unmet = backend(env_passthrough=[name]).check_environment()
        assert [condition for condition, _ in unmet] == [Condition.ENV_CREDENTIAL], name


def test_no_message_about_a_forwarded_variable_carries_its_value(monkeypatch):
    monkeypatch.setenv(PROBE, VALUE)
    monkeypatch.setenv("ANTHROPIC_API_KEY", VALUE)
    unmet = backend(env_passthrough=[PROBE, "ANTHROPIC_API_KEY"]).check_environment()
    assert VALUE not in " ".join(message for _, message in unmet)


def test_the_conditions_reach_the_whole_check(monkeypatch):
    """`check --docker` reports them, so a developer sees them without starting a run."""
    monkeypatch.delenv(PROBE, raising=False)
    unmet = backend(env_passthrough=[PROBE]).check()
    assert Condition.ENVIRONMENT in [condition for condition, _ in unmet]


# The two credential routes. docs/docker.md.
#
# `login` is the default and is what every test above ran under. These pin the other one,
# and pin that exactly one route is read.

BEDROCK_VALUE = "bedrock-probe-value-not-a-secret"


def bedrock_host(monkeypatch, **overrides) -> None:
    """Every Bedrock name set on this process, which is the host the backend reads."""
    for name in BEDROCK_NAMES:
        value = overrides.get(name, BEDROCK_VALUE)
        if value is None:
            monkeypatch.delenv(name, raising=False)
            continue
        monkeypatch.setenv(name, value)


def test_the_default_route_is_the_login():
    assert backend().credential == "login"
    assert backend().uses_login is True
    assert backend(credential="bedrock").uses_login is False


def test_the_bedrock_route_forwards_every_name_with_its_value(monkeypatch):
    bedrock_host(monkeypatch)
    forwards = forwarded(backend(credential="bedrock").run_preamble())
    for name in BEDROCK_NAMES:
        assert f"{name}={BEDROCK_VALUE}" in forwards


def test_the_login_route_forwards_no_bedrock_name(monkeypatch):
    """The host may have all four and still be on the login route. The route decides."""
    bedrock_host(monkeypatch)
    forwards = forwarded(backend().run_preamble())
    assert [name for name in BEDROCK_NAMES if any(name in value for value in forwards)] == []


def test_the_redacted_bedrock_list_carries_the_names_and_reads_no_value(monkeypatch):
    bedrock_host(monkeypatch)
    argv = backend(credential="bedrock").run_preamble(redact=True)
    for name in BEDROCK_NAMES:
        assert f"{name}={REDACTED}" in forwarded(argv)
    assert BEDROCK_VALUE not in " ".join(argv)


def test_a_bedrock_name_the_host_does_not_set_stops_the_preamble(monkeypatch):
    """The preflight refuses it first. This is the rule held where it would be broken."""
    bedrock_host(monkeypatch, AWS_REGION=None)
    with pytest.raises(DockerError) as raised:
        backend(credential="bedrock").run_preamble()
    assert "AWS_REGION" in str(raised.value)


def test_an_empty_bedrock_name_stops_it_too(monkeypatch):
    """An empty string is not a value, as for a forwarded name."""
    bedrock_host(monkeypatch, AWS_BEARER_TOKEN_BEDROCK="")
    with pytest.raises(DockerError) as raised:
        backend(credential="bedrock").run_preamble()
    assert "AWS_BEARER_TOKEN_BEDROCK" in str(raised.value)


def test_the_login_is_mounted_on_one_route_and_on_neither_path_of_the_other(tmp_path):
    assert backend(login_dir=tmp_path / "login").credential_argv() != []
    assert backend(login_dir=tmp_path / "login", credential="bedrock").credential_argv() == []


def test_the_preflight_reads_the_configured_route_and_never_both(monkeypatch, tmp_path):
    bedrock_host(monkeypatch)
    absent = tmp_path / "login"

    on_login = backend(login_dir=absent).check_credential()
    assert [condition for condition, _ in on_login] == [Condition.CREDENTIAL]

    assert backend(login_dir=absent, credential="bedrock").check_credential() == []


def test_each_unset_bedrock_name_is_one_condition_naming_it(monkeypatch, tmp_path):
    bedrock_host(monkeypatch, AWS_REGION=None, ANTHROPIC_BEDROCK_BASE_URL=None)
    unmet = backend(login_dir=tmp_path / "login", credential="bedrock").check_credential()
    assert [condition for condition, _ in unmet] == [Condition.BEDROCK, Condition.BEDROCK]
    assert "ANTHROPIC_BEDROCK_BASE_URL" in unmet[0][1]
    assert "AWS_REGION" in unmet[1][1]


def test_no_message_about_the_bedrock_route_carries_a_value(monkeypatch, tmp_path):
    bedrock_host(monkeypatch, AWS_REGION="")
    unmet = backend(login_dir=tmp_path / "login", credential="bedrock").check_credential()
    assert BEDROCK_VALUE not in " ".join(message for _, message in unmet)


def test_a_login_under_the_bedrock_route_raises_rather_than_opening_a_browser(tmp_path):
    """`setup --docker` stops before this, and this is the rule held where it would break."""
    with pytest.raises(DockerError) as raised:
        backend(login_dir=tmp_path / "login", credential="bedrock").login()
    assert "no login to make" in str(raised.value)


def test_every_bedrock_name_is_refused_to_the_forwarding_list():
    """One route for Claude's own credential, so the other list cannot carry its names."""
    assert set(BEDROCK_NAMES) <= CREDENTIAL_NAMES


def test_the_remedy_for_an_unset_bedrock_name_names_both_ways_out():
    """`scripts/image.sh` drops this condition beside `CREDENTIAL`, so both exist."""
    assert Condition.BEDROCK in Condition
    assert "docker.credential: login" in remedy(Condition.BEDROCK)
    assert "cowork_evals login --docker" in remedy(Condition.BEDROCK)


def credential(docker, **oauth) -> None:
    """Write one `.credentials.json`, the shape the CLI writes."""
    docker.claude_dir.mkdir(parents=True, exist_ok=True)
    docker.credentials_file.write_text(json.dumps({"claudeAiOauth": oauth}), encoding="utf-8")


def test_an_absent_credential_file_is_not_a_login(tmp_path):
    assert backend(login_dir=tmp_path / "login").has_credential() is False


def test_a_credential_file_with_an_access_token_is_a_login(tmp_path):
    docker = backend(login_dir=tmp_path / "login")
    credential(docker, accessToken="tok", refreshToken="ref", expiresAt=1)
    assert docker.has_credential() is True


def test_an_expired_access_token_with_a_refresh_token_is_still_a_login(tmp_path):
    """The CLI refreshes it, so an expiry in the past is not an absent login."""
    docker = backend(login_dir=tmp_path / "login")
    credential(docker, accessToken="", refreshToken="ref", expiresAt=0)
    assert docker.has_credential() is True


def test_a_credential_file_with_empty_tokens_is_not_a_login(tmp_path):
    """An abandoned OAuth flow leaves the file behind carrying no token.

    The file is there, so presence alone reported a login that the CLI then refused
    inside the container with `Not logged in`.
    """
    docker = backend(login_dir=tmp_path / "login")
    credential(
        docker,
        accessToken="",
        refreshToken="",
        expiresAt=0,
        scopes=["user:inference"],
        subscriptionType="max",
    )
    assert docker.has_credential() is False


def test_an_unparseable_credential_file_is_not_a_login(tmp_path):
    docker = backend(login_dir=tmp_path / "login")
    docker.claude_dir.mkdir(parents=True)
    docker.credentials_file.write_text("", encoding="utf-8")
    assert docker.has_credential() is False


def test_a_credential_file_carrying_no_oauth_section_is_not_a_login(tmp_path):
    docker = backend(login_dir=tmp_path / "login")
    docker.claude_dir.mkdir(parents=True)
    docker.credentials_file.write_text('{"other": {}}', encoding="utf-8")
    assert docker.has_credential() is False


def test_seed_login_dir_writes_a_state_file_the_cli_will_accept(tmp_path):
    """An empty `.claude.json` is not an absent one: the CLI exits 1 on it."""
    docker = backend(login_dir=tmp_path / "login")
    docker.seed_login_dir()
    assert docker.claude_dir.is_dir()
    assert docker.state_file.read_text() == "{}"


def test_seed_login_dir_replaces_an_empty_state_file(tmp_path):
    docker = backend(login_dir=tmp_path / "login")
    docker.claude_dir.mkdir(parents=True)
    docker.state_file.write_text("")
    docker.seed_login_dir()
    assert docker.state_file.read_text() == "{}"


def test_seed_login_dir_keeps_a_state_file_the_cli_already_wrote(tmp_path):
    docker = backend(login_dir=tmp_path / "login")
    docker.claude_dir.mkdir(parents=True)
    docker.state_file.write_text('{"kept": true}')
    docker.seed_login_dir()
    assert docker.state_file.read_text() == '{"kept": true}'


# The remedy. Every caller reads it here, and it names what a consumer runs.


def test_the_remedy_for_a_missing_image_is_the_setup_verb():
    assert remedy(Condition.IMAGE) == "run cowork_evals setup --docker"


def test_the_remedy_for_a_missing_login_is_the_login_verb_and_not_the_setup_verb():
    """An image is a build product and a credential is not, so one command does not fix both.

    A machine whose login was revoked holds two current images, and `setup --docker` there
    prints `current` twice and returns 0 without making the one thing that is missing.
    """
    assert remedy(Condition.CREDENTIAL) == "run cowork_evals login --docker"
    assert remedy(Condition.CREDENTIAL) != remedy(Condition.IMAGE)


def test_the_remedy_for_an_unreachable_daemon_names_no_command_of_this_package():
    assert remedy(Condition.DAEMON) == "start Docker Desktop or Rancher Desktop"


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
        ("cowork-evals-test:0eafee9a4184", datetime(2026, 9, 9, 5, 15, 58, tzinfo=EDT)),
        ("cowork-evals:57f48ba2adac", datetime(2026, 9, 9, 4, 8, 37, tzinfo=EDT)),
        ("cowork-evals:9e9d75cdfb6e", datetime(2026, 9, 8, 16, 47, 25, tzinfo=EDT)),
    ]


def test_a_row_in_no_format_this_reads_is_dropped():
    """It is not an image to delete, and a guessed age would delete the wrong one."""
    assert parse_images("cowork-evals:abc\tyesterday\nnot a row at all\n") == []


def test_the_listing_is_sorted_by_tag():
    listing = (
        "cowork-evals:ff78131ca4c5\t2026-09-08 18:38:34 -0400 EDT\n"
        "cowork-evals:0b8b9652310f\t2026-09-08 17:56:46 -0400 EDT\n"
    )
    assert [tag for tag, _ in parse_images(listing)] == [
        "cowork-evals:0b8b9652310f",
        "cowork-evals:ff78131ca4c5",
    ]
