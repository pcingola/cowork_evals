---
name: cowork-ask
description: "Answers what a live CoWork session does by submitting one prompt with cowork_evals ask. TRIGGER when: a claim about CoWork must be confirmed in the product, not argued, or cowork_evals ask fails. NOT for evals."
---

# cowork_evals ask

`cowork_evals ask --cowork "<prompt>"` submits one prompt to a real CoWork session, waits,
and prints the answer. It runs no eval: no case tree, no grader, no result document, no verdict
and no run directory.

Use it when the answer is a fact about the deployed product. Do not use it to check anything
a file already states, and do not use it in place of `cowork_evals run`.

Read the reference that answers the question before acting on it.

| Question                                                   | Read                           |
| ---------------------------------------------------------- | ------------------------------ |
| The verb, its options, its output, its cost, exit codes    | `references/ask.md`            |
| The session document, the ceilings, every driver code      | `references/cowork_driver.md`  |
| What the application writes, how a skill loads, the grants | `references/cowork_desktop.md` |
| What the CoWork backend can and cannot honour              | `references/approaches.md`     |
| What a session may import, run and read                    | `references/runtime.md`        |
| Every Python package a session has                         | `references/pip_freeze.txt`    |

## Steps

1. Confirm no reference states the answer: read the one the table above names.
2. Write a prompt that makes the session do the thing, per the table below.
3. `cowork_evals ask --cowork --dry-run "<prompt>"` when the prompt is long or built by hand.
4. `cowork_evals ask --cowork "<prompt>"`, once.
5. Read what the session did: `outputs`, `tools`, or `tool_calls` under `--json`.
6. Re-read with `--session <dir>`, never by asking again.

## Ask it to act, and read what it did

Ask the session to do the thing, and read what it did. What a session says about its own
configuration is not evidence: a model reports its tools, its permissions and its environment
from its prompt and from habit, and both go stale.

| Question                      | Ask                                                       | Read                    |
| ----------------------------- | --------------------------------------------------------- | ----------------------- |
| Can it write a file?          | write one, at a named path, with named contents           | `outputs` in the footer |
| Can it run a shell command?   | run one whose output cannot be guessed                    | `tools`, then the text  |
| Which tools does it have?     | use the tool                                              | `tools` in the footer   |
| Does a skill fire?            | give it the request the skill's own description triggers on | `tool_calls` under `--json`. There is no `Skill` tool in a session: it reads `SKILL.md` over the mount, which `references/cowork_desktop.md` records |

`--json` prints the whole session document, and `tool_calls` in it carries each call's input
and its result. That is what a claim about a tool is checked against.

A refusal is a result. Record what the session refused and how, and do not re-ask a different
way to get a different answer.

## When it fails

Read the exit code and the driver code in `references/ask.md` and `references/cowork_driver.md`.
