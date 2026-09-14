"""The unmet conditions of each backend.

Nothing here starts a daemon, a container or a CoWork session. The configuration files are
written to `tmp_path`, the case tree and the run log are hand-written, and the ceiling
arithmetic is read back from what `cowork_backend.plan` reported. The conditions are the
preflight table in docs/cli.md. See ../README.md.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cowork_evals import preflight
from cowork_evals.config import Config

DATA = Path(__file__).resolve().parent.parent / "data"
TREE = DATA / "cases" / "tree"


def configured(tmp_path: Path, text: str) -> Config:
    """One `cowork_evals.yaml` written to disk and loaded, as an invocation loads it."""
    path = tmp_path / "cowork_evals.yaml"
    path.write_text(text, encoding="utf-8")
    return Config.load(path)


# The shape of each returned list.


def test_every_backend_returns_a_list_of_lines() -> None:
    config = Config()
    for backend in (preflight.DOCKER, preflight.COWORK, preflight.TEST):
        lines = preflight.checks(backend, config)
        assert isinstance(lines, list)
        assert all(isinstance(line, str) for line in lines)


def test_checks_all_covers_both_backends_in_order() -> None:
    config = Config()
    assert preflight.checks_all(config) == preflight.checks(
        preflight.DOCKER, config
    ) + preflight.checks(preflight.COWORK, config)


def test_report_all_keeps_the_backend_each_line_belongs_to() -> None:
    """`checks_all` flattens and loses the pairing. `report_all` is what `check --all` prints."""
    config = Config()
    report = preflight.report_all(config)
    assert [backend for backend, _ in report] == list(preflight.BACKENDS)
    for backend, unmet in report:
        assert unmet == preflight.checks(backend, config)


def test_report_all_and_checks_all_never_disagree_about_pass() -> None:
    """The exit code comes from one and the report from the other, so they must agree."""
    config = Config()
    report = preflight.report_all(config)
    assert any(unmet for _, unmet in report) == bool(preflight.checks_all(config))


def test_the_test_verb_preflight_never_names_the_container_login() -> None:
    """There is no model call in that path, so there is nothing to authenticate."""
    lines = preflight.checks(preflight.TEST, Config())
    assert not [line for line in lines if "credential" in line]


def test_an_unknown_backend_is_refused() -> None:
    with pytest.raises(ValueError, match="no preflight for venv"):
        preflight.checks("venv", Config())


def test_every_docker_line_names_the_command_that_fixes_it() -> None:
    for line in preflight.checks(preflight.DOCKER, Config()):
        assert (
            "cowork_evals setup --docker" in line
            or "cowork_evals login --docker" in line
            or "Docker Desktop" in line
        )


# The CoWork lines.


def test_no_configured_profile_is_one_line_carrying_its_message(tmp_path: Path) -> None:
    config = configured(tmp_path, "cowork:\n  surface: cowork\n")
    lines = preflight.checks(preflight.COWORK, config)
    assert [line for line in lines if "cowork.profile" in line] == [
        "no CoWork profile configured: set cowork.profile in cowork_evals.yaml"
    ]


def test_an_unreadable_sessions_root_is_one_line_naming_it(tmp_path: Path) -> None:
    profile = tmp_path / "Profile"
    profile.mkdir()
    config = configured(tmp_path, f"cowork:\n  profile: {profile}\n")
    sessions = profile / "local-agent-mode-sessions"
    lines = preflight.checks(preflight.COWORK, config)
    assert [line for line in lines if str(sessions) in line] == [
        f"{sessions}: no readable sessions root: check cowork.profile in the "
        "configuration file, and open CoWork once on this profile"
    ]


def test_a_readable_sessions_root_reports_nothing(tmp_path: Path) -> None:
    profile = tmp_path / "Profile"
    (profile / "local-agent-mode-sessions").mkdir(parents=True)
    config = configured(tmp_path, f"cowork:\n  profile: {profile}\n")
    lines = preflight.checks(preflight.COWORK, config)
    assert not [line for line in lines if "sessions root" in line]
    assert not [line for line in lines if "cowork.profile" in line]


def test_the_platform_is_reported_only_off_macos(tmp_path: Path) -> None:
    config = configured(tmp_path, "cowork:\n  profile: Nowhere\n")
    named = [line for line in preflight.checks(preflight.COWORK, config) if "platform" in line]
    assert named == ([] if sys.platform == preflight.DARWIN else [named[0]])


# The rate ceiling.


def run_log(path: Path, entries: int) -> None:
    """A CoWork run log carrying `entries` submissions inside the trailing 24 hours."""
    stamp = datetime.now(timezone.utc).isoformat()
    path.write_text(
        "".join(
            json.dumps({"timestamp": stamp, "outcome": "collected", "session_dir": None}) + "\n"
            for _ in range(entries)
        ),
        encoding="utf-8",
    )


def test_a_suite_inside_the_ceiling_reports_nothing(tmp_path: Path) -> None:
    log = tmp_path / "runs.jsonl"
    run_log(log, 2)
    config = configured(tmp_path, f"cowork:\n  max_runs: 50\n  run_log: {log}\n")
    assert preflight.cowork_ceiling(TREE / "evals", config=config) == []


def test_a_suite_above_the_ceiling_is_one_line_carrying_the_arithmetic(tmp_path: Path) -> None:
    """`tests/data/cases/tree/evals` holds four cases, two of which this backend can honour."""
    log = tmp_path / "runs.jsonl"
    run_log(log, 3)
    config = configured(tmp_path, f"cowork:\n  max_runs: 3\n  run_log: {log}\n")
    assert preflight.cowork_ceiling(TREE / "evals", config=config) == [
        "the rate ceiling would be exceeded: 2 submissions planned, "
        "3 already made in the last 24 hours, max_runs is 3"
    ]


def test_the_ceiling_reads_the_filters_it_is_given(tmp_path: Path) -> None:
    log = tmp_path / "runs.jsonl"
    run_log(log, 3)
    config = configured(tmp_path, f"cowork:\n  max_runs: 3\n  run_log: {log}\n")
    assert preflight.cowork_ceiling(TREE / "evals", config=config, tags=("absent",)) == []


# The forwarded variables, through the dispatch `check --docker` and `run` both use.
# docs/docker.md.
#
# `monkeypatch.setenv` sets a real variable in this process, which is the environment the
# backend reads. Nothing here stands in for the read.

PROBE = "COWORK_EVALS_TEST_PROBE"
FORWARDS = f"docker:\n  env_passthrough: [{PROBE}]\n"


def test_an_absent_name_is_an_unmet_docker_condition(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv(PROBE, raising=False)
    lines = preflight.checks(preflight.DOCKER, configured(tmp_path, FORWARDS))
    assert [line for line in lines if PROBE in line and "unset or empty" in line]


def test_an_empty_name_is_the_same_unmet_condition(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(PROBE, "")
    lines = preflight.checks(preflight.DOCKER, configured(tmp_path, FORWARDS))
    assert [line for line in lines if PROBE in line and "unset or empty" in line]


def test_a_set_name_adds_no_line(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(PROBE, "probe-value-not-a-secret")
    lines = preflight.checks(preflight.DOCKER, configured(tmp_path, FORWARDS))
    assert not [line for line in lines if PROBE in line]


def test_a_credential_name_is_refused_and_names_the_one_route(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "probe-value-not-a-secret")
    config = configured(tmp_path, "docker:\n  env_passthrough: [ANTHROPIC_API_KEY]\n")
    named = [
        line
        for line in preflight.checks(preflight.DOCKER, config)
        if "ANTHROPIC_API_KEY" in line and "cowork_evals login --docker" in line
    ]
    assert named
    assert "probe-value-not-a-secret" not in " ".join(named)


def test_the_forwarded_names_are_the_container_backends_alone(tmp_path: Path, monkeypatch) -> None:
    """A session decides its own environment, so that backend has nothing to report."""
    monkeypatch.delenv(PROBE, raising=False)
    config = configured(tmp_path, FORWARDS + "cowork:\n  profile: /nowhere-at-all\n")
    assert not [line for line in preflight.checks(preflight.COWORK, config) if PROBE in line]


# The credential route, through the same dispatch. docs/docker.md.

BEDROCK = "docker:\n  credential: bedrock\n"


def test_an_unset_bedrock_name_is_an_unmet_docker_condition(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    lines = preflight.checks(preflight.DOCKER, configured(tmp_path, BEDROCK))
    assert [
        line for line in lines if "AWS_BEARER_TOKEN_BEDROCK" in line and "unset or empty" in line
    ]


def test_the_bedrock_route_asks_for_no_login(tmp_path: Path, monkeypatch) -> None:
    """The login condition is the other route's, and exactly one route is checked."""
    for name in ("CLAUDE_CODE_USE_BEDROCK", "AWS_BEARER_TOKEN_BEDROCK", "AWS_REGION"):
        monkeypatch.setenv(name, "probe-value-not-a-secret")
    monkeypatch.setenv("ANTHROPIC_BEDROCK_BASE_URL", "https://example.invalid")
    lines = preflight.checks(preflight.DOCKER, configured(tmp_path, BEDROCK))
    assert not [line for line in lines if "no credential" in line]
