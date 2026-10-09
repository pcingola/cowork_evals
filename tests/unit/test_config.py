"""`cowork_evals.yaml` loads as docs/library.md says it does.

One file, three sections, and no other route. Every test writes a real file and reads it
back through the real loader.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cowork_evals.config import (
    CONFIG_FILENAME,
    CONSENT_NONE,
    CREDENTIAL_BEDROCK,
    Config,
    CoWorkError,
    CoWorkSection,
    DockerSection,
    EvalSection,
    PanelSection,
)

# The variable table in docs/runtime.md, "What the host provides": the complete environment
# of a CoWork session shell, and the one record `docker.session_env` defaults to.
RUNTIME = Path(__file__).resolve().parents[2] / "docs" / "runtime.md"
RUNTIME_VARIABLES = tuple(
    re.findall(
        r"^\| `([A-Z_]+)` +\|",
        RUNTIME.read_text(encoding="utf-8").split("| Variable ", 1)[1].split("\n\n", 1)[0],
        re.MULTILINE,
    )
)


def write(directory: Path, body: str, name: str = CONFIG_FILENAME) -> Path:
    file = directory / name
    file.write_text(body, encoding="utf-8")
    return file


# The defaults, section by section.


def test_missing_file_yields_the_cowork_defaults(working_directory, tmp_path: Path) -> None:
    with working_directory(tmp_path):
        section = Config.load().cowork
    assert section.profile is None
    assert section.surface == "cowork"
    assert section.settle_seconds == 3.0
    assert section.session_timeout == 120.0
    assert section.idle_seconds == 20.0
    assert section.run_timeout == 1800.0
    assert section.max_runs == 50
    assert section.consent == "dialog"
    assert section.consent_timeout == 10.0
    assert section.run_log == Path.home() / ".cowork-runs.jsonl"
    assert section.log_dir == tmp_path / "logs"


def test_missing_file_yields_the_eval_defaults(working_directory, tmp_path: Path) -> None:
    with working_directory(tmp_path):
        section = Config.load().eval
    assert section.model == "sonnet"
    assert section.judge_model == "haiku"
    # The session mirror, in the container's tool names. docs/running_evals.md.
    assert section.allow_tools == (
        "Bash",
        "Read",
        "Glob",
        "Grep",
        "Write",
        "Edit",
        "WebFetch",
        "Skill",
    )
    assert section.ablation == "none"
    assert section.delta_threshold == 0
    assert section.max_cost_usd == 5
    assert section.max_cost_total_usd == 25
    assert section.keep_traces is True


def test_missing_file_yields_the_docker_defaults(working_directory, tmp_path: Path) -> None:
    with working_directory(tmp_path):
        section = Config.load().docker
    assert section.platform == "linux/arm64"
    assert section.claude_code_version == "2.1.265"
    assert section.login_dir == Path.home() / ".cache" / "cowork_evals" / "claude"
    assert section.extra_ca_file is None
    assert section.env_passthrough == ()
    assert section.session_env == RUNTIME_VARIABLES
    assert section.keep_env == (
        "NODE_EXTRA_CA_CERTS",
        "CLAUDE_PLUGIN_ROOT",
        "CLAUDE_PLUGIN_DATA",
        "CLAUDE_PROJECT_DIR",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    )


# The file over the defaults.


def test_every_section_is_read_from_one_file(tmp_path: Path) -> None:
    file = write(
        tmp_path,
        "cowork:\n"
        "  profile: Fixture\n"
        "eval:\n"
        "  model: opus\n"
        "  allow_tools: [Bash, Write]\n"
        "docker:\n"
        "  platform: linux/amd64\n"
        "panel:\n"
        "  root: /elsewhere/history\n",
    )
    config = Config.load(file)
    assert config.cowork.profile == "Fixture"
    assert config.eval.model == "opus"
    assert config.eval.allow_tools == ("Bash", "Write")
    assert config.docker.platform == "linux/amd64"
    assert config.panel.root == Path("/elsewhere/history")


@pytest.mark.parametrize(
    "config",
    [
        Config(),
        Config(cowork=CoWorkSection(profile="Fixture", consent=CONSENT_NONE, log_dir=None)),
        Config(eval=EvalSection(model="opus", allow_tools=("Bash", "Write"))),
        Config(eval=EvalSection(keep_traces=False, max_cost_usd=2.5, ablation="with-without")),
        Config(
            docker=DockerSection(
                credential=CREDENTIAL_BEDROCK,
                extra_ca_file=Path("/etc/ca.pem"),
                env_passthrough=("ACME_API_KEY",),
            )
        ),
        Config(panel=PanelSection(root=Path("/elsewhere/history"))),
    ],
)
def test_a_dumped_configuration_loads_back_equal(tmp_path: Path, config: Config) -> None:
    file = tmp_path / CONFIG_FILENAME
    config.dump(file)
    assert Config.load(file) == config


def test_a_section_the_file_omits_is_the_default(tmp_path: Path) -> None:
    file = write(tmp_path, "cowork:\n  profile: Fixture\n")
    assert Config.load(file).eval == EvalSection()
    assert Config.load(file).docker == DockerSection()
    assert Config.load(file).panel == PanelSection()


def test_missing_file_yields_the_panel_default(working_directory, tmp_path: Path) -> None:
    """The history sits under the log root, and is resolved from the working directory the
    way every other path is. It is not under `--out`. docs/panel.md."""
    with working_directory(tmp_path):
        section = Config.load().panel
    assert section.root == tmp_path / "logs" / "evals" / "history"


def test_the_panel_root_resolves_against_the_working_directory(
    working_directory, tmp_path: Path
) -> None:
    file = write(tmp_path, "panel:\n  root: build/history\n")
    with working_directory(tmp_path):
        assert Config.load(file).panel.root == tmp_path / "build" / "history"


def test_the_forwarded_names_are_read_as_written(tmp_path: Path) -> None:
    file = write(tmp_path, "docker:\n  env_passthrough: [ACME_API_KEY, ACME_REGION]\n")
    assert Config.load(file).docker.env_passthrough == ("ACME_API_KEY", "ACME_REGION")


@pytest.mark.parametrize("name", ["1ACME", "acme-key", "acme key", "ACME=1", ""])
def test_a_name_no_shell_would_accept_is_refused_at_load(tmp_path: Path, name: str) -> None:
    """The message names the line, so a reader knows which one to change."""
    file = write(tmp_path, f"docker:\n  env_passthrough: ['{name}']\n")
    with pytest.raises(CoWorkError) as raised:
        Config.load(file)
    assert raised.value.code == 2
    assert "docker.env_passthrough" in str(raised.value)


def test_the_runtime_table_holds_sixteen_names() -> None:
    assert len(RUNTIME_VARIABLES) == 16


def test_the_kept_lists_are_read_as_written(tmp_path: Path) -> None:
    file = write(tmp_path, "docker:\n  session_env: [HOME, PATH]\n  keep_env: [ACME]\n")
    section = Config.load(file).docker
    assert section.session_env == ("HOME", "PATH")
    assert section.keep_env == ("ACME",)
    assert section.kept == ("HOME", "PATH", "ACME")


@pytest.mark.parametrize("key", ["session_env", "keep_env"])
def test_a_kept_name_no_shell_would_accept_is_refused_at_load(tmp_path: Path, key: str) -> None:
    file = write(tmp_path, f"docker:\n  {key}: ['acme-key']\n")
    with pytest.raises(CoWorkError) as raised:
        Config.load(file)
    assert raised.value.code == 2
    assert f"docker.{key}" in str(raised.value)


@pytest.mark.parametrize(
    ("body", "first", "second"),
    [
        ("  keep_env: [HOME]\n", "session_env", "keep_env"),
        ("  env_passthrough: [PATH]\n", "session_env", "env_passthrough"),
        ("  env_passthrough: [ACME]\n  keep_env: [ACME]\n", "env_passthrough", "keep_env"),
    ],
)
def test_a_name_in_two_lists_is_refused_naming_both(
    tmp_path: Path, body: str, first: str, second: str
) -> None:
    file = write(tmp_path, "docker:\n" + body)
    with pytest.raises(CoWorkError) as raised:
        Config.load(file)
    assert raised.value.code == 2
    assert f"docker.{first}" in str(raised.value)
    assert f"docker.{second}" in str(raised.value)


def test_a_widened_allow_tools_replaces_the_default(tmp_path: Path) -> None:
    file = write(tmp_path, "eval:\n  allow_tools: [Write]\n")
    assert Config.load(file).eval.allow_tools == ("Write",)


def test_unknown_top_level_section_is_ignored(tmp_path: Path) -> None:
    file = write(tmp_path, "venv:\n  anything: 1\ncowork:\n  profile: Fixture\n")
    assert Config.load(file).cowork.profile == "Fixture"


def test_empty_file_yields_defaults(tmp_path: Path) -> None:
    file = write(tmp_path, "")
    assert Config.load(file) == Config.load(write(tmp_path, "cowork:\n", "other.yaml"))


def test_a_named_file_that_is_absent_raises(tmp_path: Path) -> None:
    with pytest.raises(CoWorkError) as raised:
        Config.load(tmp_path / "absent.yaml")
    assert raised.value.code == 2


# An unknown key, in each section.


@pytest.mark.parametrize(
    ("body", "typo"),
    [
        ("cowork:\n  profil: Fixture\n", "profil"),
        ("eval:\n  modle: opus\n", "modle"),
        ("docker:\n  platfrom: linux/amd64\n", "platfrom"),
    ],
)
def test_an_unknown_key_inside_a_known_section_raises(tmp_path: Path, body: str, typo: str) -> None:
    file = write(tmp_path, body)
    with pytest.raises(CoWorkError) as raised:
        Config.load(file)
    assert raised.value.code == 2
    assert typo in str(raised.value)


# A wrongly typed value, in each section.


@pytest.mark.parametrize(
    ("body", "key"),
    [
        ("cowork:\n  max_runs: many\n", "cowork.max_runs"),
        ("cowork:\n  consent: 3\n", "cowork.consent"),
        ("cowork:\n  consent_timeout: soon\n", "cowork.consent_timeout"),
        ("eval:\n  max_cost_usd: five\n", "eval.max_cost_usd"),
        ("eval:\n  allow_tools: Bash Write\n", "eval.allow_tools"),
        ("docker:\n  platform: 3\n", "docker.platform"),
        ("docker:\n  env_passthrough: ACME_KEY\n", "docker.env_passthrough"),
        ("docker:\n  env_passthrough: [3]\n", "docker.env_passthrough"),
    ],
)
def test_a_wrongly_typed_value_raises(tmp_path: Path, body: str, key: str) -> None:
    file = write(tmp_path, body)
    with pytest.raises(CoWorkError) as raised:
        Config.load(file)
    assert raised.value.code == 2
    assert key in str(raised.value)


def test_a_section_that_is_not_a_mapping_raises(tmp_path: Path) -> None:
    file = write(tmp_path, "eval:\n  - model\n")
    with pytest.raises(CoWorkError) as raised:
        Config.load(file)
    assert raised.value.code == 2


def test_a_wrongly_typed_field_raises_however_the_section_was_built() -> None:
    """Conversion is `__post_init__`, so a direct build is checked like a loaded one."""
    with pytest.raises(CoWorkError) as raised:
        CoWorkSection(max_runs="many")  # type: ignore[arg-type]
    assert raised.value.code == 2


# The path convention, which every path key follows.


def test_tilde_is_expanded(tmp_path: Path) -> None:
    file = write(tmp_path, "cowork:\n  run_log: ~/somewhere/runs.jsonl\n")
    config = Config.load(file)
    assert config.cowork.run_log == Path.home() / "somewhere" / "runs.jsonl"
    assert "~" not in str(config.cowork.run_log)


def test_a_relative_path_resolves_against_the_working_directory(
    working_directory, tmp_path: Path
) -> None:
    file = write(tmp_path, "cowork:\n  log_dir: build/logs\ndocker:\n  login_dir: build/login\n")
    with working_directory(tmp_path):
        config = Config.load(file)
    assert config.cowork.log_dir == tmp_path / "build" / "logs"
    assert config.docker.login_dir == tmp_path / "build" / "login"


def test_log_dir_null_turns_the_file_off(tmp_path: Path) -> None:
    file = write(tmp_path, "cowork:\n  log_dir: null\n")
    assert Config.load(file).cowork.log_dir is None


# The profile, which has no default.


def test_sessions_root_is_derived_from_the_profile() -> None:
    root = CoWorkSection(profile="Fixture").sessions_root
    assert root == (
        Path.home() / "Library" / "Application Support" / "Fixture" / "local-agent-mode-sessions"
    )


def test_sessions_root_without_a_profile_raises() -> None:
    with pytest.raises(CoWorkError) as raised:
        _ = CoWorkSection().sessions_root
    assert raised.value.code == 2


def test_every_section_is_frozen() -> None:
    config = Config()
    for section, key in ((config.cowork, "profile"), (config.eval, "model")):
        with pytest.raises((AttributeError, TypeError)):
            setattr(section, key, "Other")


def test_the_consent_key_reads_one_of_two_words_and_refuses_anything_else(
    tmp_path: Path,
) -> None:
    """`consent` is the one `cowork:` key with a fixed set of values.

    A third word is not a wider setting. It is a typo that would fire without asking, so it
    is refused where every other wrongly typed value is.
    """
    file = write(tmp_path, "cowork:\n  consent: none\n  consent_timeout: 5\n")
    section = Config.load(file).cowork
    assert section.consent == "none"
    assert section.consent_timeout == 5.0

    with pytest.raises(CoWorkError) as raised:
        Config.load(write(tmp_path, "cowork:\n  consent: yes-please\n"))
    assert "cowork.consent: expected one of dialog, none" in str(raised.value)


def test_the_ablation_key_reads_one_of_two_words_and_refuses_anything_else(
    tmp_path: Path,
) -> None:
    """A third word would reach `claude plugin eval` as a flag value it refuses, after the
    container has started and the suite has been read."""
    file = write(tmp_path, "eval:\n  ablation: with-without\n")
    assert Config.load(file).eval.ablation == "with-without"

    with pytest.raises(CoWorkError) as raised:
        Config.load(write(tmp_path, "eval:\n  ablation: with-only\n"))
    assert "eval.ablation: expected one of none, with-without" in str(raised.value)


def test_the_delta_threshold_reads_a_number_from_zero_to_one(tmp_path: Path) -> None:
    """A case score is a mean of grader results and is in that range, so a delta is in -1 to
    1 and a threshold above 1 is one no case can meet."""
    assert Config.load(write(tmp_path, "eval:\n  delta_threshold: 0.25\n")).eval.delta_threshold

    with pytest.raises(CoWorkError) as raised:
        Config.load(write(tmp_path, "eval:\n  delta_threshold: 2\n"))
    assert "eval.delta_threshold: expected a number from 0 to 1, got 2" in str(raised.value)

    with pytest.raises(CoWorkError) as negative:
        Config.load(write(tmp_path, "eval:\n  delta_threshold: -1\n"))
    assert "eval.delta_threshold: expected a number at or above zero" in str(negative.value)


def test_the_traces_key_reads_a_boolean_and_refuses_anything_else(tmp_path: Path) -> None:
    """It is the one `eval:` key that is a flag, and `keep_traces: "no"` is not false."""
    written = tmp_path / "cowork_evals.yaml"
    written.write_text("eval:\n  keep_traces: false\n", encoding="utf-8")
    assert Config.load(written).eval.keep_traces is False

    written.write_text("eval:\n  keep_traces: 'no'\n", encoding="utf-8")
    with pytest.raises(CoWorkError) as raised:
        Config.load(written)
    assert "eval.keep_traces: expected true or false, got str" in str(raised.value)


def test_no_votes_at_all_is_refused_at_load(tmp_path: Path) -> None:
    """Zero turns every judged assertion into a lost vote, so it is refused."""
    written = write(tmp_path, "eval:\n  judge_votes: 0\n")
    with pytest.raises(CoWorkError) as raised:
        Config.load(written)
    assert "at or above one" in str(raised.value)
