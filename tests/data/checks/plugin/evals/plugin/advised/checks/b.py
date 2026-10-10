"""A plain check that passes when the advisory check before it ran."""

from cowork_evals.checks import Run, check


@check
def plain(run: Run) -> bool:
    return (run.scratch / "seen.txt").exists()
