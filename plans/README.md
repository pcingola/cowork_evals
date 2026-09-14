# plans

Work in progress. Each plan is executed on its own branch off `main` and merged back when
its checklist is complete. A plan that is done moves to [`done/`](done), and everything in
that directory is frozen.

**A plan is never deleted by Claude.** The developer decides when a plan goes, and says so.
A completed plan stays until then, because it is the record of which decisions were asked
for and which were proposed, and that record is what anyone needs when a design decision is
questioned later. Git history does not answer that: every commit here is authored by the
developer with Claude as co-author, so it cannot tell the two apart.

A plan is still not a place to record anything durable. It links to `docs/`, and `docs/`
never links back. Whatever a plan establishes that outlives the work is written into `docs/`
while the work happens.

## Plans

Nineteen plans. Seventeen build something and are numbered in build order, and one of those
seventeen is skipped. `plan_fix` builds nothing, so it carries no number: it corrects what the
others wrote, and it ran before `plan_cowork_backend.md` because it changes what that plan and
`plan_cli.md` both read. `plan_believable_results` carries no number for the same reason:
it holds measurements and decisions, and its product is the four plans numbered 10 to 13. The order is the
order they are built in, not a precondition: a plan is
written whenever the developer decides to write it, and a plan whose inputs already exist is
executable whether or not the plan before it is finished. `status` is the plan's own state,
not the system's: what is built and usable is
[`../docs/running_evals.md`](../docs/running_evals.md).

| # | Plan                     | Builds                                                                            | Status      | Branch                |
| - | ------------------------ | ----------------------------------------------------------------------------------- | ----------- | --------------------- |
| 1 | [`done/plan_cowork_tools.20260908.md`](done/plan_cowork_tools.20260908.md) | The CoWork driver: submit one prompt, wait, return what the session produced      | implemented | `feat/cowork-tools`   |
| 2 | [`done/plan_docker.20260908.md`](done/plan_docker.20260908.md) | The image, its digest, `scripts/parity.sh`, and the harness run inside a container | implemented | `feat/docker`         |
| 3 | `plan_venv.md`           | The staged relocatable 3.10 runtime, and the harness run under it                 | skipped     |                       |
| 4 | [`done/plan_cowork_backend.20260909.md`](done/plan_cowork_backend.20260909.md) | The case reader, the CoWork grader and the v1 result document over the driver     | implemented | `feat/cowork-backend` |
| 5 | [`done/plan_test.20260909.md`](done/plan_test.20260909.md) | The test image, and a consumer's pytest suite run on the CoWork runtime            | implemented | `feat/test`           |
| 6 | [`done/plan_cli.20260909.md`](done/plan_cli.20260909.md) | Scope resolution, the run directory, the verdict, and the command                    | implemented | `feat/cli`            |
| - | [`done/plan_fix.20260909.md`](done/plan_fix.20260909.md) | Nothing. One configuration file, one name per artifact, and the false statements  | implemented | `feat/fix-consistency` |
| 7 | [`done/plan_consumer.20260909.md`](done/plan_consumer.20260909.md) | The shipped documentation, the `docs` and `init` verbs, and the eval-authoring skill | implemented | `feat/consumer`       |
| 8 | [`done/plan_ask.20260912.md`](done/plan_ask.20260912.md) | The `ask` verb over the driver, and the skill that asks a live session what it does | implemented | `feat/ask`            |
| 9 | [`done/plan_focus.20260912.md`](done/plan_focus.20260912.md) | The consent modal, the frontmost guard and the composer clear, in the driver | implemented | `feat/focus`          |
| - | [`done/plan_believable_results.20260912.md`](done/plan_believable_results.20260912.md) | Nothing. The measurements, the decisions, and the four plans that follow them | implemented |                       |
| 10 | [`done/plan_run_validity.20260912.md`](done/plan_run_validity.20260912.md) | A run that never got its tool fails instead of scoring, and honest counts | implemented | `feat/run-validity`   |
| 11 | [`done/plan_runnability.20260912.md`](done/plan_runnability.20260912.md) | The `no-cowork` tag on a case, enforced both ways, counted rather than failed | implemented | `feat/runnability`    |
| 12 | [`done/plan_env_passthrough.20260912.md`](done/plan_env_passthrough.20260912.md) | Named host variables forwarded into the run container, values never logged | implemented | `feat/env-passthrough` |
| 13 | [`done/plan_ablation.20260912.md`](done/plan_ablation.20260912.md) | The baseline arm, and a verdict that decides on the per-case delta | implemented | `feat/ablation`       |
| 14 | [`done/plan_panel.20260913.md`](done/plan_panel.20260913.md) | The per-case run history, the `panel` verb, and `prune --history` | implemented | `feat/panel` |
| 15 | [`done/plan_consent.20260913.md`](done/plan_consent.20260913.md) | The keyboard consent dialog, shown by the driver rather than by a caller | implemented | `fix/consent` |
| 16 | [`plan_artifact_checks.md`](plan_artifact_checks.md) | An assertion an author writes as code, deciding the run beside the harness's graders | written | `feat/artifact-checks` |
| 17 | [`plan_eval_design.md`](plan_eval_design.md) | The document that owns which cases to write, the interview the skill runs, and a second credential route | written | `feat/eval-enhancement` |

| Status        | Means                                                                     |
| ------------- | --------------------------------------------------------------------------- |
| `not written` | The plan file does not exist yet                                           |
| `not started` | The plan file exists and no box in it is ticked                            |
| `written`     | The plan file exists, and its checklist is not finished                    |
| `implemented` | Every box is ticked and the branch is merged. The file is in `done/`       |
| `skipped`     | The developer decided not to write it. What it would build stays designed in `docs/` and unbuilt |

Plan 3 is skipped, so the venv backend is not built. Its design stays in
[`../docs/staged_runtime.md`](../docs/staged_runtime.md), which is titled and opens as not
implemented, and the status table in
[`../docs/running_evals.md`](../docs/running_evals.md) carries the one row that says so.
Nothing is removed from `docs/` for a skipped plan, but the command surface names none of it:
there is no `--venv` on any verb.

Every section below describes each plan as it is written, plan 3 included. What plan 3
describes is designed and not built.

Plan 5 is the one plan that builds no part of an eval. It runs a consumer's Python tests
inside the container, with no model, no case tree and no result document, so that code
destined for a skill is exercised on the CoWork runtime before an eval is written over it.
The rule that separates it from the other five is in
[`../tests/README.md`](../tests/README.md): if a failure can be caught by pytest, it is not
an eval. Its mechanism is [`../docs/cowork_test.md`](../docs/cowork_test.md), and plan 6
builds the verb that reaches it.

Plan 7 builds no part of a run either. It changes what the distribution carries and what the
installed package can tell a reader about itself: `docs/` ships, the references that break on
the way out are corrected, and two verbs and one skill put the shipped tree in front of a
Claude Code session in the consumer repository. The boundary it moves is
[`../docs/library.md`](../docs/library.md).

Plan 8 builds no part of an eval either. It puts a verb on the driver plan 1 built and a
skill on that verb, so a question about what a live CoWork session does is answered by
asking one rather than by argument. Several decisions in later plans rest on facts only a
session can settle, and the command surface it adds is
[`../docs/cli.md`](../docs/cli.md). The first four facts it settled are section 5 of
[`../docs/cowork_desktop.md`](../docs/cowork_desktop.md).

Plan 9 corrected a defect in plan 1. The driver took the keyboard without asking and typed
into a composer it never cleared, so a developer working in another window contaminated the
prompt. It was the driver's and not any one verb's: every `run --cowork` case goes through
the same call. What it changed is [`../docs/cowork_driver.md`](../docs/cowork_driver.md). The
one line it names in `cli._ask` ships with plan 8, which owns that verb.

The four plans numbered 10 to 13 were one piece of work in four merges, and all four are
implemented. Each states the decisions it rests on in its own file, so one is implemented by
reading one file;
[`done/plan_believable_results.20260912.md`](done/plan_believable_results.20260912.md) is the
record of what was measured on the day they were written. Together they made a result
believable: a run that never got the tool it needed stops scoring, a case a backend cannot run
says so instead of failing every suite forever, a skill that needs a credential became
evaluable at all, and a suite can be asked whether the plugin changed anything rather than only
whether the cases passed. They were implemented in that order. `plan_ablation` was last
because it rewrites the pass and fail rules that `plan_run_validity` and `plan_runnability`
both change, and `plan_env_passthrough` is independent of all three. What those rules are now
is [`../docs/running_evals.md`](../docs/running_evals.md).

Plan 14 builds no part of a run either. A result document lives in a run directory, and a
run directory is deleted once it is old enough, so a suite that passed last month leaves
nothing behind. It adds the one record that outlives that directory, one file per case, and
the verb that renders it. What it changes in the verdict is a return value and no condition:
pass and fail stay in [`../docs/running_evals.md`](../docs/running_evals.md), and the store
and the render are `../docs/panel.md`, which it writes.

Plan 15 corrects a defect in plan 9, the way plan 9 corrected one in plan 1. The consent
dialog plan 9 built is shown by two callers in `cli.py` and by nothing else, so every other
path that takes the keyboard either refuses or fires in silence, and this repository's own
integration tier was configured to fire in silence. On 2026-09-13 a `-m integration` run
therefore took the keyboard with no warning while the developer was typing elsewhere. It moves
the asking into the driver, so the dialog is shown by every path that takes the keyboard and
`cowork.consent: none` is the one way to switch it off. What it changes is
[`../docs/cowork_driver.md`](../docs/cowork_driver.md).

Plan 16 is the first that adds a grader this package evaluates itself. The harness's five
grader types are a closed vocabulary owned by a tool this repository does not control, so an
assertion that does not fit one of them cannot be made and the case runs green having checked
nothing. It adds a layer on top of `claude plugin eval`: the harness grades a run as it does
now, and this layer then runs an author's own code over what the run produced and adds its
assertions to the same result.

Plan 17 builds no part of a run. A session pointed at a consumer repository invented its eval
cases and graders, because no file said which cases a skill needs: the format contract covers
the file and nothing covers the suite. It adds one shipped document, one section to one shipped
skill, and the rule that separates the two documents. The boundary it moves is
[`../docs/library.md`](../docs/library.md), and what it now says about coverage is
[`../docs/eval_design.md`](../docs/eval_design.md). Its last phase is unrelated to the rest and
is there because the same developer could run nothing without it: the container backend accepted
one credential, and a host that authenticates Claude Code through Bedrock failed the preflight.

Plans 2 and 3 each build one backend whole. Running an eval on those two backends is
`claude plugin eval`, which discovers the cases, runs them, grades them and writes
`aggregate-result.json` itself, so there is nothing above the backend to put in a plan of its
own. Only the host changes between them. See
[`../docs/approaches.md`](../docs/approaches.md).

### What a backend plan builds, and what it does not

Plans 1, 2, 3 and 5 build mechanisms. The first three build the way to reach a running
agent: the desktop driver, the container, and the staged 3.10 runtime. Plan 5 builds the way
to reach no agent at all, which is why it fires nothing in the table below. None of them writes an eval, runs a
suite, or introduces a cadence. Those belong to the consumer repository, and the rule is in
[`../CLAUDE.md`](../CLAUDE.md).

A mechanism still has to be shown to work, and some facts about one cannot be reached by
reading a file. Each of plans 2, 3 and 4 therefore ends by firing `plugins/smoke/` once,
from the integration tier, and recording what that settled. Plan 8 fires no case tree: it
fires four prompts, because what it has to establish is what a session does and not what a
grader scores. Plan 5 fires nothing: every fact it needs is a container with a fixed command
and a fixed expected output.

| Plan | Fires once to establish                                                              |
| ---- | -------------------------------------------------------------------------------------- |
| 2    | Whether the harness runs end to end inside the container, and whether a case there reaches a running command |
| 3    | Whether a staged interpreter is reachable from inside the OS sandbox, and whether a case that shells out gets 3.10 |
| 4    | Whether a case tree reaches a real CoWork session, and whether the grader scores what that session produced |
| 8    | What a live session does when it is asked to write a file, shell out, fetch a URL and fire a skill |
| 9    | Whether clearing the composer before the deep link removes the contamination, and what `System Events` calls the CoWork process |

Everything else those plans measure is a `docker run` or a subprocess with a fixed command
and a fixed expected output, and is asserted without a model. A fact that can be established
deterministically never costs an agentic run.

Three fixture cases, in the integration tier, are not a suite. None runs in the default
selection, and nothing here runs any of them on a cadence. See
[`../tests/README.md`](../tests/README.md) and [`../plugins/README.md`](../plugins/README.md).

Plan 4 is separate because CoWork is not symmetric with the other two. The driver returns one
session document for one prompt. Reading the case tree, deciding which case the backend can
honour, grading it and writing the v1 result document are all built there, and are what the
harness provides for free elsewhere. See
[`../docs/cowork_backend.md`](../docs/cowork_backend.md).

Docker comes before the venv, although the venv is cheaper to build.
[`../docs/staged_runtime.md`](../docs/staged_runtime.md) records that a `Bash`-granting run is
refused on this host, and every case that shells out needs that grant. The container installs
bubblewrap and runs with `seccomp=unconfined` and `systempaths=unconfined`, so it may be the
only backend on this machine that can grant `Bash`. Measuring that early is worth more than
the cheaper build.

Plan 4 waits on neither. It reads `plugins/smoke/`, `src/cowork_evals/config.py` and the
driver, all of which exist, and it needs nothing the venv backend would have built.

### The contract that keeps the command plan last

A backend is a function. It takes a case path and an output directory, and it returns the
path to the `aggregate-result.json` it produced.

A backend never names the run directory, never writes `env.txt` or the `latest` symlink,
never prunes, never parses an option and never decides pass or fail. Plan 6 owns all of it.

Plans 2 and 4 hold to that, so plan 6 assembles what exists and rebuilds none of it. Plan 5
holds to the same shape without being a backend: it returns an exit code rather than a
result document, and plan 6 adds the verb over it. A
backend that writes a log layout of its own breaks the one verdict that covers all three. The
layout and the verdict are [`../docs/running_evals.md`](../docs/running_evals.md), and the
command is [`../docs/cli.md`](../docs/cli.md).

## How a plan is written

Writing rules are in [`../CLAUDE.md`](../CLAUDE.md). These are the rules specific to a
plan.

- It points at `docs/`. It never restates a document, and nothing in `docs/` points back.
- Its design lives in `docs/`. The plan holds scope, phases and checklists only.
- It is self-contained and executable with a cleared context.
- It is complete. No open question, no TBD, no decision left to the reader. Where a fact
  was unknown at writing time, the plan says which phase measures it and what ships if the
  measurement fails.
- Phases are worked in order. Finish one before starting the next.
- Testing and documentation are phases, not afterthoughts.

## How a plan is executed

Work one box, verify it, tick it in the plan file, commit. Do not batch ticks. The plan
file is the state, so a cleared context can resume from it, and at every instant the ticks
say exactly what is done. Where a box cannot leave the suite green on its own, because the
refactor around it is mid-flight, the tick still goes in immediately and the next green
commit carries it and names in its message which boxes it carries.

A measurement is written into the file under `docs/` that owns it, not into the plan. The plan
file stays, but nothing durable may live only in it. A row in `docs/` still reading
`not yet measured` means the box that fills it is not ticked.

## How a plan is retired

A plan is done when every box is ticked and its branch is merged. Neither half alone is
enough: a full checklist on an unmerged branch is still work in progress.

A plan that builds nothing has no branch, and is done when its last box is ticked. Before it
moves, every file outside `done/` that depends on it stops doing so, because nothing outside
`done/` may depend on a file inside it. For a plan whose product is other plans, that means
each of those carries the decisions it rests on rather than pointing back.

On the merge, move the file to `done/` and rename it `plan_<name>.<YYYYMMDD>.md`. The date
is the date it was merged, so `plan_docker.md` merged on 2026-09-08 becomes
`done/plan_docker.20260908.md`. Update its row in the table above to the new path. The date
is in the name because two plans over the same subject are told apart by when they ran, and
because the name then says how old the account is without opening it.

What a file in `done/` then is, and why it is neither read nor updated, is in
[`../CLAUDE.md`](../CLAUDE.md).

Nothing outside `done/` may depend on a file inside it. `docs/` never links to a plan at
all, and the table above is the only route in.
