"""Run evals for Claude CoWork skills and plugins, and run a plugin's own tests on the runtime.

The command is `cowork_evals`, and docs/cli.md is the whole of its surface. It does two things.
`run` executes a case tree on one of two backends, Claude Code inside a container that
reproduces the CoWork image or the real desktop application driven directly, grades what came
back and decides pass or fail on it. `test` runs a consumer's pytest suite inside the CoWork
runtime with no model in the loop.

Evals are not written here. This is a library, installed by the repository that owns the
plugins under test. The boundary is docs/library.md, the case format is docs/eval_format.md,
and `cowork_evals docs` prints where those files landed in the install.

The names exported below are the driver and the configuration, which are the only parts a
consumer imports rather than reaching through the command. The driver's behaviour is
docs/cowork_driver.md, its API is docs/cowork_driver_internals.md, and the application
internals it couples to are docs/cowork_desktop.md.
"""

from .config import (
    Config,
    CoWorkError,
    CoWorkSection,
    DockerSection,
    EvalSection,
    PanelSection,
)
from .cowork import CoWork

__all__ = [
    "CoWork",
    "CoWorkError",
    "CoWorkSection",
    "Config",
    "DockerSection",
    "EvalSection",
    "PanelSection",
]
