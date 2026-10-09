# Eval design

## Summary

Which cases to write for a skill, which assertion answers which question, and what to do with a
failure. The case format is [eval_format.md](eval_format.md). Checks are
[checks.md](checks.md). How pass and fail are decided is [running_evals.md](running_evals.md).

The steps below follow the order the work is done in.

## Step 1. Read the skill and write a plan

Read the skill's description and instructions. They say what it does and what it must do. Look
in the repository for real inputs, and at any existing suite for what it already covers.

Write the plan as a file with a checklist of cases, one line per case. Each line says what the
case does and what the output must contain to pass. Tick a line when its case is written.

## Step 2. Choose what to check

Each row below is something a case can check, and the assertion that checks it. Add to each
case in the plan the rows it uses. One case can carry several rows. A row that does not apply
to the skill adds a run and checks nothing.

The "Use" column names graders. When the output is not text, such as a spreadsheet or an image,
write a check instead.

| To check that                                              | Use                                                                                                                       |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| The skill fires on a request it handles                    | `tool_used` on `Skill`, with `input_match` on the skill's name                                                            |
| The skill does not fire on a nearby request                | the same grader with `min: 0, max: 0`, on a prompt on the same topic in other words                                       |
| A specific tool is called within the skill                 | `tool_used` with `input_match` on that call                                                                               |
| A tool is never called, such as one that deletes or sends  | `tool_used` with `min: 0, max: 0`                                                                                         |
| Two steps happen in a given order                          | `tool_order` with `before` and `after`                                                                                    |
| A file is created                                          | `file_exists` with `path` as a glob                                                                                       |
| A value is in the answer or in a produced file             | `regex` on `last_message`, or on `{source: file, path}` for the file's contents                                           |
| The answer has a required format                           | `regex` on `last_message`. Add `m` to `flags` if `^` or `$` must match each line                                          |
| The answer invents nothing the input lacks                 | a prompt that asks about something the input does not contain, and `regex` with `not_contains` for each value the skill might invent |
| A private value in the input does not leak                 | a made-up value in the input, and `regex` with `not_contains` for it on `last_message`, `trace` and each produced file    |
| The content is good by a criterion no pattern expresses    | `llm`, or `baseline` against a reference answer                                                                           |

For a private value, use a made-up one. The run log keeps everything the container prints.

## Step 3. Review the plan

Review the plan before writing the cases. A change to the plan costs a line. A change to a
written case costs its files.

A known problem with the skill becomes the assertion that catches it. "The summaries are too
long" becomes a `regex` over the final message.

## Step 4. Write the cases

Write the files for each case in the plan, in the format [eval_format.md](eval_format.md)
describes, and tick the case in the plan when it is written.

### Show what the skill adds

A passing case does not show the skill helped. A model asked for a spreadsheet usually builds
one with or without a spreadsheet skill, so the case passes either way. A good case is one the
model fails without the skill and passes with it.

`--ablation with-without` runs every case twice, with the plugin and without it, and reports
the delta between the two scores. It runs on `--docker` only, because a CoWork session always
loads the skills of its profile. See [running_evals.md](running_evals.md).

Both arms get the same prompt:

- Ask for the result, not the steps. A prompt that names the skill or lists its steps lets the
  model follow along without the skill.
- Pick a task the model does badly on its own. If it does it well, both arms score the same.
- Do not paste the input file's content into the prompt, or the model never opens the file.

Write assertions that can fail in both arms. One that can only pass with the plugin loaded
makes the two scores impossible to compare.

Make the input look real: large enough that the model cannot answer from memory, messy the way
real inputs are, and with the edge cases the skill handles. It can go in the prompt or in a
file.

### The assertions to write

Check on every case that the output is right. Check on every case that needs the plugin that
the plugin loaded. Check that the run used the skill the way the skill says to when that way is
itself the requirement.

#### The plugin loaded

Add a `tool_used: Skill` grader to every case that needs the plugin. Without it a case passes
when the model did all the work alone. Under `--ablation with-without` this grader is reported
and not scored. In a normal run it can fail the case.

The skill loads only when the prompt matches what its description says it handles. A case that
tests a capability uses wording from the description. A case that tests that the skill does not
load too easily stays on the topic and avoids that wording. If the skill does something its
description never names, add it to the description: a user who asks for it does not get the
skill either.

#### The output is right

Graders read only text, so they cannot look inside a spreadsheet, a deck, a PDF or an image.
Use a grader where it can read the thing, and a check where it cannot. A check is Python that
opens the file. A case needs at least one grader, or the harness does not load it.

When both work, use the grader. Prefer `regex`, `tool_used`, `tool_order` and `file_exists`
over `llm` and `baseline`, which ask a model and vary from run to run.

#### The run used the skill

The assertions above check that the skill loaded and that the output is right. They do not
check how the output was made. The agent can load the skill, run its command, ignore the
result, write the output with its own script, and pass every one.

To catch this, write a check that calls `run.judge` with three paths: the run's transcript,
`run.trace`; the skill's `SKILL.md`; and a copy of the case's `prompt.md` without its
frontmatter, written to `run.scratch`. The judge needs the prompt because the transcript does
not carry the task. It answers three questions: did the run use the method the skill
documents, did it follow the skill's instructions, and did it state anything no tool returned.

- Point the judge at the skill file. Do not summarise the skill's rules in the prompt, so the
  judge stays correct when the skill changes.
- Do not ask for a method the skill has no command for, or every run fails.
- Ask how the run worked, not whether the result is right. The other assertions check that.
- If the votes disagree, reword the instructions before blaming the judge.

This is the most expensive assertion. Use one per case.

### Make sure each assertion works

Before running the suite, try each assertion on an output that must pass and on one that must
fail. Test a `regex` as a JavaScript `RegExp`, which is what the harness uses. `^` and `$`
match only at the start and end of the whole text unless `flags` has `m`. Test a check on the
skill's real output. If it fails a correct output, the check is wrong.

Ask three questions about outputs you have not seen:

- Does it fail a wrong answer?
- Does it pass a correct answer written differently?
- Does it fail an empty answer?

`not_contains` often fails the second question. A wrong answer and a right one often use the
same words, so banning a word fails good answers and passes vague ones. Assert on what the
answer concluded. A case whose every assertion is negative fails the third question, because
an empty answer contains nothing banned. Add at least one thing the output must contain.

Assert on what the answer says, not on its format. A correct conclusion can be a table row, a
bullet, a symbol or a sentence. Imagine two or three correct answers in different styles, and
make sure the assertion passes all of them. Prefer what must be present over what must be
absent, a minimum count over every expected item, and what a tool call produced over the tool's
name. Have a check return a `Result` whose `explanation` says what it found, so a failure shows
whether the skill or the assertion is wrong.

### Run the case close to real use

Run each case in conditions close to real use, so that a pass means the skill works for a user
and a fail means it does not. A weather skill that runs a script to fetch a forecast catches a
bug in that script only when the run can reach the service the way a real session does. Give
the run each thing the skill uses in real use:

- A credential the skill reads from an environment variable. A `--docker` container receives
  none of the host's variables. List the name under `docker.env_passthrough` in
  `cowork_evals.yaml`. The value is forwarded into the run container and is read as
  configuration nowhere. On `--cowork` the session sets its own environment and the setting
  does nothing.

  ```yaml
  docker:
    env_passthrough: [WEATHER_TOKEN]
  ```

- An MCP server the plugin declares in its own `.mcp.json`. It starts on both backends. Under
  `--docker` its tools are callable once `eval.allow_tools` lists them, as
  `mcp__plugin_<plugin>_<server>__*`. The list replaces the default, so keep the default tools
  in it. Connectors on the CoWork account are not available under `--docker`. That is a limit
  of `cowork_evals`, not of Claude Code. Run a case that calls a connector with `--cowork`. See
  [approaches.md](approaches.md).
- A Python package. There is nothing to configure. The `--docker` image carries the session's
  interpreter and wheels and nothing else, so a missing import fails there as it fails for a
  user. Check the skill's imports against
  [runtime.md](runtime.md#rules-for-code-that-runs-in-a-session) before writing cases, and run
  the plugin's own tests on that image with `cowork_evals test`. See
  [cowork_test.md](cowork_test.md).

## Step 5. Run the suite and read the results

Run `cowork_evals run --docker <plugin>/evals`. Run the cases that call a connector on the
CoWork account with `cowork_evals run --cowork`. See [cli.md](cli.md).

When a case fails, decide whether the skill or the assertion is wrong. The score does not say,
and the run's files do. Each failure line ends with the run directory, `traces/<case>/run-N`,
which holds the final message, the workspace, the transcript, and the `checks.jsonl` a check
leaves, with each `run.judge` call. Look at what the skill produced, and ask whether a correct
answer would have passed the assertion.

- No: the assertion is wrong. Fix it, and confirm on the failed run's files that a correct
  output now passes. Nothing re-grades a stored run, so run the case again for its score.
- Yes: the failure is real. Fix the skill and leave the assertion as it is.

Never change an assertion only to raise the score.
