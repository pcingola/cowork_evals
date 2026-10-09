"""One check that reads a sibling module."""

from helpers import shout

from cowork_evals.checks import Run, check


@check
def the_sibling_is_importable(run: Run) -> bool:
    return shout("WRITTEN") == "written"
