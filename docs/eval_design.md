# Eval design

## Summary

Which cases a skill needs, and which grader answers which question. This is the design contract
over [eval_format.md](eval_format.md), which is the file contract.

- **Claude Code does not invent a suite.** It asks the developer what the skill has to get
  right, and reads the cases and the graders out of the reply.
- **It never asks which eval and which grader the developer wants.** That question hands the
  design back.
- **A developer who says they do not know gets a suite Claude Code designed.** The signal is
  the reply, not a flag.
- **Ten dimensions.** Each one that applies to the skill has at least one case, whichever route
  produced the suite.
- **A missing access changes the design.** A case that needs access it does not have measures
  the access and not the skill.
- **The split against the format is one question**: does the statement depend on what the skill
  under test does?

Pass and fail over what these cases produce is [running_evals.md](running_evals.md). Which
backend honours which case feature is [approaches.md](approaches.md). No case field and no
validator rule is here. Both are [eval_format.md](eval_format.md).

## The split against the format

One question decides the side, and it holds for every statement in either file.

**Does the statement depend on what the skill under test does?** No, and it is the format. Yes,
and it is the design.

| Statement                                                       | Depends on the skill | Side   |
| --------------------------------------------------------------- | -------------------- | ------ |
| The `prompt.md` key table, the caps, the `EVAL_` prefix         | no                   | format |
| The two addressability keys, and what `plugins` counts to       | no                   | format |
| The reserved tag, enforced in both directions                   | no                   | format |
| The grader type table, and its class column                     | no                   | format |
| The regex anchoring snapshot                                    | no                   | format |
| The validator rules, and the authoring traps                    | no                   | format |
| Which grader class a case should prefer                         | yes                  | design |
| Which cases the suite needs, and which it is missing            | yes                  | design |
| What a missing access changes                                   | yes                  | design |

A statement about a case file that any reader can check without opening the skill is the
format's. Everything that needs the skill's own instructions, or the developer's answer about
what the skill is for, is here.

## The interview

Claude Code does not invent a suite. Before it writes a case it asks the developer what the
skill has to get right, what a bad answer looks like, and what a release must not ship. It reads
the cases and the grader kinds out of the reply, and asks a follow-up question when the reply
does not decide one.

It never asks which eval and which grader the developer wants. That question hands the design
back to the developer, and a developer who could answer it would have written the case already.

| Ask                                                    | Read out of the reply                                     |
| ------------------------------------------------------ | --------------------------------------------------------- |
| What does this skill have to get right?                | the end to end case, and the goal the grader asserts      |
| What does a bad answer look like?                      | the edge cases, and every `not_contains` pattern          |
| What must a release never ship?                        | which dimension carries a structural grader               |
| What does it read, and what does it write?             | the fixtures, the access, and which target a grader reads |
| Which part of it breaks most often?                    | which capability gets a case of its own                   |

A reply names a symptom, not a case. The work is to turn it into one. `The summaries are too
long` is a `regex` over `last_message`. `It makes things up about our schema` is a fixture and a
`not_contains` pattern per invented value. `It ignores the config file` is a `tool_used` with an
`input_match` naming that file.

Ask again when the reply does not decide the grader. One follow-up question that settles a
target is worth more than a case that grades the wrong thing.

### When the developer does not know

A reply that says the developer does not know, or that asks Claude Code to decide, is the
authorization. The signal is the reply. Nothing in `cowork_evals.yaml` selects it and no option
does.

Claude Code then designs the suite itself, and says which dimensions it covered, which it left
out, and why each left-out one does not apply.

## The coverage dimensions

Ten dimensions. Each one that applies to the skill has at least one case. One case may answer
more than one row, so the check is that no applying row has none.

Every grader named below is one of the six types [eval_format.md](eval_format.md) defines. This
file adds none.

| Dimension | The case | The grader | Applies when |
| --------- | -------- | ---------- | ------------ |
| Expected behaviour, end to end | one prompt carrying the whole job the skill exists for | `file_exists` on the artefact, `tool_order` on the steps that have an order, one `llm` over `{source: file, path}` on the contents | always. Every skill has one job |
| The right tools are used | the request the skill's own description triggers on, and a second request near its subject that it must not fire on | the skill-fired `tool_used` idiom, `tool_order` for a required sequence, `tool_used` with `min: 0, max: 0` for a tool it must not call and for the request it must not fire on | always |
| The goal is achieved | a prompt naming the outcome and no steps | `file_exists` on the artefact, `regex` over `{source: file, path}` for a value that has to be in it, `llm` over the same when the outcome is prose | always. It differs from the first row in which grader carries the assertion |
| Each capability on its own | one case per capability the skill's own instructions name, each prompt asking for that capability alone | `tool_used` with the `input_match` for the call that capability makes, `regex` over `{source: file, path}` or `last_message` for its output | the skill names more than one capability |
| The instructions are followed | a prompt whose answer the instructions constrain: a format, a length, an ordering, a required section | `regex` over `last_message` with `match: contains`, `not_contains` or `count:N`, and `m` in `flags` when the anchor is per line. `llm` over `last_message` when the constraint is not a pattern | the instructions constrain the output |
| Edge cases | the input at a boundary: empty, absent, malformed, oversized, or two instructions that conflict | `regex` over `last_message` for the stated refusal or the handled result, `tool_used` with `min: 0, max: 0` for the destructive action it must not take | the developer named a boundary, or the input is a file or a value that has one |
| Hallucination | a prompt asking for a fact only the case's own fixture carries, or naming a thing that is not there | `regex` over `last_message` with `match: not_contains` for each value the fixture does not carry, `baseline` against a `baseline_file` holding the correct answer | the skill reports what it read rather than transforming what it was given |
| Context relevancy | more context than the answer needs, with the answer in one named part of it | `tool_used` with `input_match` naming the file it had to open, `regex` over `trace` for that path, `regex` over `last_message` with `not_contains` for a value only the irrelevant part carries | the skill chooses what to read |
| Answer relevancy | one question, asked once, whose answer has a shape | `regex` over `last_message` with `count:N` or `not_contains` for the padding shape, `llm` over `last_message` for the criteria, `baseline` when a reference answer exists | the product is the message and not a file |
| PII and confidential information leakage | a fixture carrying a marked value the answer does not need, and a prompt that does not ask for it | `regex` with `match: not_contains` over `last_message`, over `{source: file, path}` for each artefact, over `trace` for the value reaching a tool call, and over `mock_calls` for it reaching an MCP call | the skill reads anything the prompt did not carry: a staged fixture, a forwarded credential, a service |

The applies-when column is read against the skill's own `SKILL.md` and against the developer's
answers. A row that does not apply gets no case, and the reason it does not apply is what Claude
Code says back to the developer.

### What the table does not decide

- **A row whose only grader is `llm` or `baseline` leaves the exit code silent about it.** Those
  two are judged, are printed, and carry no verdict. Give every dimension a release must not
  ship a structural grader as well. See [running_evals.md](running_evals.md).
- **Prefer a structural grader.** A judged grader over a non-deterministic agent is a flaky
  verdict, and a judge is noisy on a long input. Where a structural grader can decide a
  dimension, it decides it.
- **A `regex` anchor covers the whole target** unless `flags` carries `m`. The snapshot is
  [eval_format.md](eval_format.md).
- **Three dimensions need a staged fixture**: context relevancy, leakage, and the malformed
  input form of edge cases. A fixture is a `context.*` key, so each of those cases carries
  `no-cowork`. See [eval_format.md](eval_format.md).
- **The leakage row's marked value is a fixture the case owns.** It is never the credential
  `docker.env_passthrough` forwards. `run.log` is captured at the file descriptor level, so a
  case that makes the agent print a forwarded value puts that value in the log. See
  [docker.md](docker.md).
- **Directory coverage is not dimension coverage.** One `evals/<skill>/` per skill is what `run`
  reports and `--require-coverage` enforces. See [cli.md](cli.md). Nothing enforces the table
  above, which is why it is written here.

## Access

A case that needs access it does not have measures the access and not the skill.

| The case needs                | Absent, the case measures                                       | The route                                                                   |
| ----------------------------- | ---------------------------------------------------------------- | --------------------------------------------------------------------------- |
| A credential the skill reads  | the credential, and every case fails for a reason that is not the skill | `docker.env_passthrough` names the variable, and a name unset or empty exits 3. See [docker.md](docker.md) |
| A third-party service         | that service's uptime as well as the skill                       | a fixture the case stages, or a `mocks/` stand-in                           |
| An MCP server                 | nothing. The tool is not there                                   | `evals/mocks/<server>/<tool>.md`, which makes the case `no-cowork` and makes `mock_calls` a readable target |
| A tool                        | the grant. A run that never had a granted tool fails rather than scores | `eval.allow_tools`, or the case's own `allowed_tools`, which makes the case `no-cowork`. See [running_evals.md](running_evals.md) |
| A file staged before the run  | a prompt with nothing to read                                    | `context.add_dirs` or `context.scaffold_script` in `case.yaml`, which makes the case `no-cowork` |
| A wheel the skill imports     | an import error inside the session, in every case at once        | `cowork_evals test` catches it before an eval is written over it. See [runtime.md](runtime.md) |
| The deployed stack            | the container, and not CoWork                                    | the honoured subset in [approaches.md](approaches.md)                       |

Two rules follow, and the route above decides neither.

- When Claude Code designs the suite, it designs around the access that exists.
- When the developer proposes a case that needs access that is not there, Claude Code says so
  before it writes the case, and names the route that would supply it.

## The proposal

Either route proposes the suite before a file is written: one line per case, naming the
dimension it covers and the grader that decides it. A developer reads that list and strikes a
case in one sentence. The same list read after the cases exist costs a rewrite.

The proposal also names, per case, the access it needs and whether it carries `no-cowork`. Those
two are what a developer objects to, and they are invisible in a case name.
