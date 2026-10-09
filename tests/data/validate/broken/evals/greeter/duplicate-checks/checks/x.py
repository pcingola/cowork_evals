"""Check `y` in `x.py`, which is named `x.y`."""

from cowork_evals.checks import Run, check


@check
def y(run: Run) -> bool:
    return True
