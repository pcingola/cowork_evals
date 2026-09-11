"""The `claude plugin eval` command line, built once for both Claude Code backends.

Every flag emitted here is pinned in docs/running_evals.md, and the harness behind them is
docs/plugin_eval.md. The venv backend reuses this unchanged; only the host differs.

Both paths arrive already resolved for the host the harness runs on, so the container backend
passes container paths and nothing here resolves one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .config import Config

# The debug log's name inside the run's output directory. The log layout fixes it.
# docs/running_evals.md.
DEBUG_FILE_NAME = "debug.txt"

# The result document's name in the same directory, from the same layout. Every backend
# writes one, not only the two that run this command line, so it is here and not under one
# of them. docs/running_evals.md.
RESULT_NAME = "aggregate-result.json"

# The early-access enablement variable, as `--env` takes it. The package exports it into
# the child, and no developer chooses it, so it is a constant and not a setting.
# docs/plugin_eval.md.
ENABLEMENT_ENV = "CLAUDE_CODE_WALNUT_SPIRE=1"

# Two pinned flags have no option and no setting. `--threshold 0` hands pass and fail to
# the gate; `--ablation none` keeps a `tool_used: Skill` grader scored.
THRESHOLD = "0"
ABLATION = "none"


@dataclass(frozen=True)
class RunOptions:
    """One run's resolved options. Every field is already the value that will be emitted."""

    model: str
    judge_model: str
    max_cost_usd: str
    allow_tools: tuple[str, ...]
    keep_traces: bool = True
    runs: int | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    case: str | None = None

    @classmethod
    def resolve(
        cls,
        config: Config | None = None,
        *,
        model: str | None = None,
        judge_model: str | None = None,
        max_cost_usd: str | None = None,
        allow_tools: tuple[str, ...] | None = None,
        keep_traces: bool | None = None,
        runs: int | None = None,
        tags: tuple[str, ...] = (),
        case: str | None = None,
    ) -> RunOptions:
        """An explicit argument beats the file, which beats the built-in default.

        `config` defaults to `cowork_evals.yaml` in the working directory. `allow_tools`
        replaces the configured value rather than adding to it, so a widened value names
        `Bash` again. `keep_traces` is a three-state argument: `None` is the option not
        typed, and both `True` and `False` beat the file.
        """
        settings = (config if config is not None else Config.load()).eval
        return cls(
            model=model if model is not None else settings.model,
            judge_model=judge_model if judge_model is not None else settings.judge_model,
            max_cost_usd=(max_cost_usd if max_cost_usd is not None else str(settings.max_cost_usd)),
            allow_tools=allow_tools if allow_tools is not None else settings.allow_tools,
            keep_traces=keep_traces if keep_traces is not None else settings.keep_traces,
            runs=runs,
            tags=tags,
            case=case,
        )


def eval_argv(target: Path | str, output_dir: Path | str, options: RunOptions) -> list[str]:
    """The whole command line. Nothing that is neither pinned nor optioned is emitted.

    `--debug-file` goes before `plugin`, and never a bare `--debug`, which swallows the
    subcommand name as its filter. `--json` is never emitted, for the reason in
    docs/plugin_eval.md.
    """
    output_dir = Path(output_dir)
    argv = [
        "claude",
        "--debug-file",
        str(output_dir / DEBUG_FILE_NAME),
        "plugin",
        "eval",
        # The target goes ahead of every variadic flag below, which would swallow it.
        str(target),
        "--model",
        options.model,
        "--judge-model",
        options.judge_model,
        "--ablation",
        ABLATION,
        "--threshold",
        THRESHOLD,
        "--max-cost-usd",
        options.max_cost_usd,
        "--output-dir",
        str(output_dir),
        "--no-publish",
        "--no-scaffold",
        "--verbose",
    ]
    if options.keep_traces:
        # Every run's sandbox is kept, not only an errored run's. Where it is kept is the
        # backend's `TMPDIR`, and what is kept out of it is traces.py.
        argv.append("--keep-temp")
    if options.runs is not None:
        argv += ["--runs", str(options.runs)]
    if options.case is not None:
        argv += ["--case", options.case]
    # Variadic, and last.
    if options.allow_tools:
        argv += ["--allow-tools", *options.allow_tools]
    if options.tags:
        argv += ["--tag", *options.tags]
    return argv
