"""The unmet conditions of each backend.

Nothing here starts a daemon, a container or a CoWork session. The configuration files are
written to `tmp_path`, the case tree and the run log are hand-written, and the ceiling
arithmetic is read back from what `cowork_backend.plan` reported. The conditions are the
preflight table in docs/cli.md. See ../README.md.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from cowork_evals import preflight
from cowork_evals.config import Config

TREE = Path(__file__).resolve().parent.parent / "data" / "cases" / "tree"


def configured(tmp_path: Path, text: str) -> Config:
    """One `cowork_evals.yaml` written to disk and loaded, as an invocation loads it."""
    path = tmp_path / "cowork_evals.yaml"
    path.write_text(text, encoding="utf-8")
    return Config.load(path)


# The CoWork lines.


def test_no_configured_profile_is_one_line_carrying_its_message(tmp_path: Path) -> None:
    config = configured(tmp_path, "cowork:\n  surface: cowork\n")
    lines = preflight.checks(preflight.COWORK, config)
    assert [line for line in lines if "cowork.profile" in line] == [
        "no CoWork profile configured: set cowork.profile in cowork_evals.yaml"
    ]


@pytest.mark.parametrize("readable", [False, True])
def test_an_unreadable_sessions_root_is_one_line_naming_it(tmp_path: Path, readable: bool) -> None:
    profile = tmp_path / "Profile"
    sessions = profile / "local-agent-mode-sessions"
    (sessions if readable else profile).mkdir(parents=True)
    config = configured(tmp_path, f"cowork:\n  profile: {profile}\n")
    lines = preflight.checks(preflight.COWORK, config)
    assert [line for line in lines if "cowork.profile" in line] == (
        []
        if readable
        else [
            f"{sessions}: no readable sessions root: check cowork.profile in the "
            "configuration file, and open CoWork once on this profile"
        ]
    )


# The rate ceiling.


@pytest.mark.parametrize(
    ("recent", "max_runs", "expected"),
    [
        (2, 50, []),
        # `tests/data/cases/tree/evals` holds four cases, two of which this backend honours.
        (
            3,
            3,
            [
                "the rate ceiling would be exceeded: 2 submissions planned, "
                "3 already made in the last 24 hours, max_runs is 3"
            ],
        ),
    ],
)
def test_a_suite_above_the_ceiling_is_one_line_carrying_the_arithmetic(
    tmp_path: Path, run_log: Callable[..., None], recent: int, max_runs: int, expected: list[str]
) -> None:
    log = tmp_path / "runs.jsonl"
    run_log(log, recent)
    config = configured(tmp_path, f"cowork:\n  max_runs: {max_runs}\n  run_log: {log}\n")
    assert preflight.cowork_ceiling(TREE / "evals", config=config) == expected


def test_the_ceiling_reads_the_filters_it_is_given(
    tmp_path: Path, run_log: Callable[..., None]
) -> None:
    log = tmp_path / "runs.jsonl"
    run_log(log, 3)
    config = configured(tmp_path, f"cowork:\n  max_runs: 3\n  run_log: {log}\n")
    assert preflight.cowork_ceiling(TREE / "evals", config=config, tags=("absent",)) == []


# The forwarded variables. docs/docker.md.
#
# `monkeypatch.delenv` removes a real variable from this process, which is the environment
# the backend reads. Nothing here stands in for the read.

PROBE = "COWORK_EVALS_TEST_PROBE"
FORWARDS = f"docker:\n  env_passthrough: [{PROBE}]\n"


def test_the_forwarded_names_are_the_container_backends_alone(tmp_path: Path, monkeypatch) -> None:
    """A session decides its own environment, so that backend has nothing to report."""
    monkeypatch.delenv(PROBE, raising=False)
    config = configured(tmp_path, FORWARDS + "cowork:\n  profile: /nowhere-at-all\n")
    assert not [line for line in preflight.checks(preflight.COWORK, config) if PROBE in line]
