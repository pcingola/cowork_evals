"""An advisory check that fails. It leaves a mark in the scratch directory, so the plain
check after it can tell that it ran."""

from cowork_evals.checks import Result, Run, check


@check(advisory=True)
def advised(run: Run) -> Result:
    (run.scratch / "seen.txt").write_text("seen", encoding="utf-8")
    return Result(passed=False, explanation="the advice was not followed")
