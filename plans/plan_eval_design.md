# Eval design: which cases a skill needs, and the interview that decides

## The problem

Pointed at a consumer repository, a Claude Code session with the `cowork-evals` skill invented
eval cases and graders from nothing. Nothing it read told it which cases a skill needs, because
no file said. [`../docs/eval_format.md`](../docs/eval_format.md) is the file contract and says
nothing about coverage, and every other first-party file is a mechanism or a cost. The only
design guidance in the tree is vendored and is Anthropic's.

A suite written with no reference under-evaluates the skill, and it does so silently: it passes.
The validator has nothing to say about it, and `--require-coverage` counts directories.

## What this plan does

One document owns eval design, and the shipped skill carries the short form, so a session in a
consumer repository asks the developer what the skill has to get right before it writes a case
and checks the suite against a stated list of coverage dimensions.

It adds no command, no option, no configuration key and no validator rule. Coverage stays
unenforced by the tool, which is why it is written down.

A second, unrelated product is in phase 4: a second credential route for the container backend,
so a host that authenticates Claude Code through Bedrock can run an eval at all.

Branch: `feat/eval-enhancement`.

## Decisions

| Decision                          | Chosen                                                    | By            |
| --------------------------------- | ---------------------------------------------------------- | ------------- |
| Where the guidance lives          | a new document, `docs/eval_design.md`                     | the developer |
| The skill shape                   | a new section in `cowork-evals`, not a third skill        | the developer |
| The Bedrock route                 | a phase here, and a second credential route               | the developer |
| The interview is the default      | asking is default, designing alone is the exception       | the developer |
| The ten coverage dimensions       | the developer named all ten, and none was added           | the developer |

The developer named the ten dimensions. The mapping from each one onto a case shape and a grader
is this plan's, and it invents no grader type: every grader named is one of the six the format
already defines.

## The split rule

Two files now cover an eval, so a rule decides which side a statement goes on.
[`../CLAUDE.md`](../CLAUDE.md) requires it, and it is written in
[`../docs/README.md`](../docs/README.md) beside the other splits.

**Does the statement depend on what the skill under test does?** No, and it is the format. Yes,
and it is the design.

It was checked against every statement already in either file. Two moved out of the format,
both about which grader class to prefer, because that depends on what the skill produces.
Nothing else moved.

## What this plan does not do

| Not in scope                                  | Where it is instead                                            |
| --------------------------------------------- | -------------------------------------------------------------- |
| Enforcing dimension coverage                  | Nowhere. `--require-coverage` counts directories, and the document says so |
| A new grader type                              | Nowhere. The six in [`../docs/eval_format.md`](../docs/eval_format.md) answer all ten dimensions |
| A third shipped skill                         | Nowhere. Designing and authoring fire on one request, so a split would need a rule and has none |
| An eval for any of this                       | Nowhere. This is a library, and the rule is [`../CLAUDE.md`](../CLAUDE.md) |
| A guard on the model name under Bedrock       | Nowhere. No measurement here says an alias fails, and the value is the developer's |

## Orientation

| Fact                                                    | Where                                                       |
| ------------------------------------------------------- | ----------------------------------------------------------- |
| A skill states no fact of its own                       | [`../docs/library.md`](../docs/library.md)                   |
| The six grader types and their two classes              | [`../docs/eval_format.md`](../docs/eval_format.md)           |
| Which case feature the CoWork backend cannot honour     | [`../docs/approaches.md`](../docs/approaches.md)             |
| Which grader class decides the exit code                | [`../docs/running_evals.md`](../docs/running_evals.md)       |
| What a forwarded variable does, and what the log carries | [`../docs/docker.md`](../docs/docker.md)                    |
| The credential preflight, and the login it looks for    | `src/cowork_evals/docker/__init__.py`, `Condition`, `has_credential` |
| The skill against the documents it condenses            | `tests/unit/test_resources.py`                              |
| The trap count both files have to agree on              | `tests/unit/test_resources.py`, `_traps`                    |

The trap count is positional: it reads from one heading to another. A section added between
those two headings changes it, so the new section goes above them.

## Phases

### Phase 1: the document

- [x] `docs/eval_design.md`: the split rule, the interview and what each opener is read for, the
      exception when the developer does not know, the ten dimensions with the case shape, the
      grader and when each applies, what the table does not decide, the access table, and the
      proposal step
- [x] [`../docs/README.md`](../docs/README.md): the row, the count in the divide prose, and the
      split question beside the other splits
- [x] [`../docs/eval_format.md`](../docs/eval_format.md): the two preference statements leave,
      the class fact stays, and the coverage sentence names what coverage then is. Nothing is
      added below its last heading
- [x] `README.md`: the row in the documentation table, and one sentence where the quickstart
      stops after two graders
- [x] `scripts/build.sh`: the new document is a wheel member, and the comment counts three

### Phase 2: the skill

- [x] `## What to evaluate` in `src/cowork_evals/data/skills/cowork-evals/SKILL.md`, above the
      command section: the interview, the exception, the dimensions condensed to dimension,
      grader and applies-when, the class preference, the access routes and the proposal
- [x] The routing table gains the row that names the new document
- [x] The grader section drops the preference and keeps the class fact
- [x] `description` fires when a skill has no evals yet, not only when a case is being fixed
- [x] [`../docs/library.md`](../docs/library.md): the skill still fires on one question, and its
      row and the documents it condenses both name the new one
- [x] `src/cowork_evals/resources.py`: the `CLAUDE.md` block names the new document and the
      interview. The marker is unchanged, so a consumer who already ran `init` keeps the old
      block, which [`../docs/cli.md`](../docs/cli.md) already states
- [x] [`../docs/cli.md`](../docs/cli.md) and `README.md`, wherever they say what that skill holds

### Phase 3: the tests

Unit tier, over the real files, in the pattern already there.

- [x] `eval_design` is an expected document, and the skill sends a reader to it by name
- [x] Every dimension the document defines appears in the skill, read out of the document's own
      table so no dimension is spelled in the test
- [x] Every grader type the format defines appears in the document, so a seventh type has to
      land in a dimension
- [x] The interview default and its exception are in both files
- [x] The format carries no preference statement and the document carries one, which pins the
      split
- [x] `scripts/lint.sh` and `scripts/test.sh` pass

### Phase 4: the Bedrock credential route

`run --docker` accepts one credential: a claude.ai login this package owns. A host that
authenticates Claude Code through Bedrock fails the preflight and can run nothing.

The forwarding half is already built. Only the preflight blocks it, and it is unconditional.
This is a second credential route and not a use of `docker.env_passthrough`, which stays what
[`../docs/docker.md`](../docs/docker.md) says it is: the route for a credential the skill under
test reads.

- [x] `docker.credential`, `login` or `bedrock`, defaulting to `login`, refusing a third value
      wherever it arrived from
- [x] The four variable names the `bedrock` route owns, spelled once, and refused to
      `env_passthrough` so the two routes cannot be confused
- [x] Under `bedrock` the preflight drops the login condition and requires each of the four set
      and non-empty, with its own condition and its own remedy. Under `login` nothing changes
- [x] The run container gets the four, redacted in a dry run like every other forwarded value,
      and neither credential mount
- [x] `setup --docker` skips the login under `bedrock` and reports why, and `Docker.login` raises
      rather than opening a browser for a credential the route never reads
- [x] `env.txt` records the route and no name it forwards, so two runs of one image on one host
      are told apart. The names each route owns are fixed and are in
      [`../docs/docker.md`](../docs/docker.md)
- [x] [`../docs/docker.md`](../docs/docker.md): two routes, the rule that decides which one a
      host uses, and what the model name has to be under this one
- [x] The example configuration, [`../docs/cli.md`](../docs/cli.md)'s `setup` and `check`
      sections, `README.md`'s backend table, and the two files that called the login the one
      route for Claude's own credential
- [x] Unit tests: the key and its refusal, the preflight under each route, an absent name, a
      forwarded name that is refused, the preamble under each route, and the `env.txt` line

### Phase 5: verification

- [x] `scripts/lint.sh`, `scripts/test.sh`, `scripts/build.sh`. 725 unit tests pass, the
      formatter and the linter are clean, and both artefacts carry the new document
- [ ] `cowork_evals docs eval_design` resolves in an install and in a checkout
- [ ] A `--docker` run under `credential: bedrock`, which is the only thing that says whether the
      four forwarded values authenticate the CLI inside the container, and whether `eval.model`
      has to be an inference profile id
- [ ] In a consumer repository, a session asked for evals for a skill that has none asks what the
      skill has to get right before it writes a file, does not ask which grader is wanted, and
      proposes the suite first
- [ ] The same session, told the developer does not know, designs the suite and reports which
      dimensions it left out
- [ ] The integration tier, at the end and after the merge, as
      [`../tests/README.md`](../tests/README.md) requires
