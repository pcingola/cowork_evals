# CLAUDE.md

`cowork_evals`: a system for running evals against Claude CoWork skills and plugins, and for
running a plugin's own Python tests on the CoWork runtime. `README.md` says what it is, and
`docs/` says how it works.

## Where things are written

Each directory has a `README.md` that indexes it and owns the rules for it. Read the index
before changing anything under it. Never restate one of these in another file; link to it.

| Index               | Owns                                                     |
| ------------------- | -------------------------------------------------------- |
| `README.md`         | What the repo is, and the public repository rule         |
| `assets/README.md`  | The images `README.md` shows, and the rules for an image |
| `docs/README.md`    | Reference material: boundary, command, runtime, harness  |
| `plans/README.md`   | How a plan is structured and executed                    |
| `plugins/README.md` | The fixture plugins, and what they are not               |
| `scripts/README.md` | Every development task, and the shell conventions        |
| `tests/README.md`   | What is a test here, and what is not                     |

## Working rules

- **This is a library, not a consumer.** No eval for a shipped plugin is written here. The
  repository that owns the plugins installs this package and points it at its own tree.
  `plugins/` holds fixtures for this repository's own tests, nothing more. See
  `docs/library.md`.
- **One command.** Everything a consumer does goes through `cowork_evals`, and a consumer
  never invokes `claude plugin eval` or `docker` directly. Never add a second entry point or a
  per-backend executable. The surface is `docs/cli.md`.
- **One config file.** `cowork_evals.yaml` holds every setting this repository defines: the
  driver's, each backend's, the models, the tool grants, the ceilings. There is no second
  route. Nothing is read from the process environment except the variables `docker.env_passthrough`
  names, whose values are forwarded into the run container and read as configuration nowhere.
  There is no `.env`. A command-line option beats the file. The file beats the built-in
  default. See `docs/library.md`.
- **A split needs a rule.** Wherever one thing is divided across two files, two modules or
  two mechanisms, write down the rule that decides which side a new item goes on. It holds
  for every item already there. A split with no such rule is a defect. Build order is not a
  rule. Derive a fact in one place. Give a default one home.
- **Three kinds of code, three sets of rules.** This package runs on a laptop and controls
  CoWork. The code under test runs inside the CoWork VM. A consumer's own tests run in the
  test image. What binds one does not bind another, and no two are ever conflated.

  | Code                                     | Runs on               | Python | May depend on                          |
  | ---------------------------------------- | --------------------- | ------ | -------------------------------------- |
  | This package, `src/cowork_evals/`        | a developer's laptop  | 3.10   | anything                               |
  | The code under test, under the eval path | the CoWork session VM | 3.10   | the image wheel set, and nothing else  |
  | A consumer's `tests/`                    | the test image        | 3.10   | the image wheel set, and pytest        |

  Every row is 3.10, so the interpreter never separates them. The dependency column does.
  The second row is the hard one: each skill, command, agent and hook under the path passed
  to `cowork_evals run` imports only what the image carries. See `docs/runtime.md`. The one
  other thing under that path is a case's `checks/*.py`, which is the first row and not the
  second: it runs on the host after the run is graded, and its imports are the consumer's
  own. See `docs/checks.md`. The first row is constrained by nothing about CoWork, and its
  3.10 is a floor a consumer must clear, not a runtime fact; the rules that apply to it are
  in `docs/library.md`. The third row is never loaded in a session, so the wheel set does not
  bind it; see `docs/cowork_test.md`.
- **Never mock, and never skip.** No mock, fake, stub, patch or injected seam appears in a
  test, and no library that supplies one is a dependency. No test is skipped, and no `if`
  bypasses the assertions inside one. A test runs against the real thing or it is not
  written. Either rule is lifted only when the developer approves that exception.
- **Two tiers of test.** A test is unit and runs by default, or it is marked `integration`
  and is selected with `-m integration`. Integration is for what needs a real CoWork
  profile or a real run, and it is run at the end of a plan and after a merge into `main`.
  A missing precondition fails an integration test. It never skips it. See
  `tests/README.md`. This rule is about this repository's own tests. A consumer's tests are
  the consumer's, and `cowork_evals test` runs them without interpreting them.
- **Never invent a restriction.** No guard, gate, filter, ceiling, deny-list or refusal
  goes into this package unless the developer asked for it. A limit that comes from a
  measured fact about the application is not a restriction, and it cites the measurement.
  Everything else is the developer's call, including in a plan: a plan proposes, it does
  not authorize.
- **Development tasks are shell scripts** under `scripts/`, are never shipped, and have no
  build system and no Makefile.
- **One case format, two backends.** Every eval is written in the `claude plugin eval` case
  format, and the same case tree runs in Docker and on CoWork. Never add a second format or a
  per-backend variant of a case. The format is `docs/eval_format.md`. Which backend honours
  which field is `docs/approaches.md`. A third backend, Claude Code against a 3.10 mirror on
  the host, is designed and deliberately not built: `docs/staged_runtime.md`.
- **Two environments, never mixed.** `.venv` is repository tooling and is what `init.sh`
  builds. The CoWork mirror, `.venv_cowork`, is optional, costs 604 MB, is built on demand by
  `scripts/cowork_venv.sh`, and nothing in the package reads it. Both are Python 3.10, so the
  wheel set is what separates them, not the interpreter. Code that must behave like a session
  runs under the mirror through `scripts/cowork_run.sh`, and `cowork_evals test --docker`
  answers the same question against the real image. Never run `uv run` under the mirror. See
  `docs/environments.md`.
- **A plan is the state while it exists.** Tick a box only when it is verified, then
  commit. Do not batch ticks. A cleared context resumes from the plan file.
- **Never delete a plan.** The developer decides when a plan goes, and says so. A plan is
  also the record of who decided what, which is the first thing anyone needs when a design
  decision is questioned later.
- **`plans/done/` is history. Never read it, never update it.** A plan moves there when it
  is finished, and from then on it states what was true and what was decided at that time,
  not what is true now. Never read one to learn how the system works, and never cite one as
  a source. Never correct one, however wrong it has become: it is meant to go stale, and
  editing it destroys the record. A sweep that fixes statements across the repository skips
  `plans/done/` entirely. What is true now is in `docs/`. `plans/README.md` holds when a
  plan moves and what it is named.
- **Nothing durable lives only in a plan.** A plan links to `docs/`. Documentation never
  links to a plan. Anything a plan establishes that outlives the work is written into
  `docs/` while the work happens, not as a step before removing the file.
- NEVER sign commits or PRs as Claude.

## Writing rules

These apply to every file in the repository: documentation, plans, comments, commit
messages.

Audience is expert engineers and Claude Code. Readers build Claude Code plugins for a
living. They know what a skill, plugin, command, agent, hook, MCP server, context window,
LLM, test and CI are, and they have read the official Claude Code documentation. Assume all
of it.

- Never define a term.
- Never motivate a practice. State it.
- A file is a file. Never call one a page, here or in conversation. `page` means a page of
  a book or a web page, and neither is in this repository.
- Simplified Technical English. No filler, no corporate register.
- One idea per sentence. Tables for anything with more than two attributes.
- State what is true of this repository, and verify before writing.
- **Never date a fact, and never tell the story of how it was found.** State the behaviour.
  Documentation is not a log, and a reader who has never met the developer gets nothing from
  a date or an incident. A version, a platform or an image tag is a condition the statement
  depends on and stays in it. The one exception is a fact whose date changes what a reader
  must do, and it says why. This binds `docs/`, `README.md`, code comments and docstrings.
  A plan is the exception: it records when a decision was made, which is what it is for.
- Sentence case headings. No emojis, no em dashes.
