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

`cowork_evals docs` prints the shipped documentation. Every rule below is in one of those
files, and the right column names the file that owns it.

| Question                                       | Read                   |
| ---------------------------------------------- | ---------------------- |
| The verb, its options and its exit codes       | `docs cli`             |
| What the driver does, and what it refuses      | `docs cowork_driver`   |
| What the application writes, and where         | `docs cowork_desktop`  |
| What the CoWork backend can and cannot honour  | `docs approaches`      |
| What a session may import                      | `docs runtime`         |

## Steps

1. Confirm no file states the answer: `cowork_evals docs`, then the document that owns it.
2. Write a prompt that makes the session do the thing, per the table below.
3. `cowork_evals ask --cowork --dry-run "<prompt>"` when the prompt is long or built by hand.
4. `cowork_evals ask --cowork "<prompt>"`, once.
5. Read what the session did: `outputs`, `tools`, or `tool_calls` under `--json`.
6. Re-read with `--session <dir>`, never by asking again.

## The command

```bash
cowork_evals ask --cowork "Reply with the single word: ready"
cowork_evals ask --cowork --dry-run "..."      # the deep link and the ceiling. Spends nothing
cowork_evals ask --cowork --json "..."         # the session document instead of the text
cowork_evals ask --cowork --session <dir>      # a session already on disk. Submits nothing
```

The answer is stdout. The session directory, the assistant turn count, the tool names, the
outputs and the driver log are stderr, so a redirect captures the answer alone.

## What it costs

One ask costs a VM boot, one submission against `cowork.max_runs`, and the keyboard for the
length of the run, because the submission is a synthetic Return to the frontmost window.

Ask once. Use `--dry-run` first when the prompt is long or built by hand. Use `--session` to
re-read a session already on disk instead of submitting again.

## Ask it to act, and read what it did

Ask the session to do the thing, and read what it did. What a session says about its own
configuration is not evidence: a model reports its tools, its permissions and its environment
from its prompt and from habit, and both go stale.

| Question                      | Ask                                                       | Read                    |
| ----------------------------- | --------------------------------------------------------- | ----------------------- |
| Can it write a file?          | write one, at a named path, with named contents           | `outputs` in the footer |
| Can it run a shell command?   | run one whose output cannot be guessed                    | `tools`, then the text  |
| Which tools does it have?     | use the tool                                              | `tools` in the footer   |
| Does a skill fire?            | give it the request the skill's own description triggers on | `tool_calls` under `--json`. There is no `Skill` tool in a session: it reads `SKILL.md` over the mount, which `docs cowork_desktop` records |

`--json` prints the whole session document, and `tool_calls` in it carries each call's input
and its result. That is what a claim about a tool is checked against.

A refusal is a result. Record what the session refused and how, and do not re-ask a different
way to get a different answer.

## When it fails

`cowork_evals ask` exits 3 when the preflight is unmet or the driver refused before
submitting, and the message names what to fix. Exit 1 is everything else the driver raised,
and the driver's codes are in `cowork_evals docs cowork_driver`.

`cowork_evals check --cowork` reports what the backend is missing. The authorizations it
cannot report, including the macOS Accessibility grant, are in
`cowork_evals docs cowork_desktop`.
