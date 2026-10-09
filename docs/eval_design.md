# Eval design

## Summary

This file suggests how to design an eval suite for a Claude CoWork skill: what a case can check, how
to show what the skill adds over the model alone, and what to do with the results.

It does not repeat the case format. [eval_format.md](eval_format.md) is how a case file is written,
[checks.md](checks.md) is how to write a check, and [running_evals.md](running_evals.md) is how pass
and fail are decided.

The sections below follow the order the work is usually done in.

## Step 1. Read the skill and write a plan

Read the skill's description and instructions: they say what it does and what it must do. Look at the
repository for real inputs, and at any existing suite for what is already covered.

Write the plan as a file with a checklist of cases, one line per case. Each line says what the case
does and what the output must contain to pass. Tick a line when its case is written.

## Step 2. Choose what to check

Each row below is something a case can check, and the assertion that checks it. Add to each case in
the plan the rows it uses. One case can carry several rows. A row that does not apply to the skill
adds a run and checks nothing.

The "Use" column names graders. When the output is not text, such as a spreadsheet or an image,
write a check instead.

| To check that                                            | Use                                                                                                       |
| -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| The skill fires on a request it handles                  | `tool_used` on `Skill`, with `input_match` on the skill's name                                            |
| The skill does not fire on a nearby request              | the same grader with `min: 0, max: 0`, on a prompt on the same topic in other words                       |
| A specific tool is called within the skill               | `tool_used` with `input_match` on that call                                                               |
| A tool is never called, such as one that deletes or sends | `tool_used` with `min: 0, max: 0`                                                                        |
| Two steps happen in a given order                        | `tool_order` with `before` and `after`                                                                    |
| A file is created                                        | `file_exists` with `path` as a glob                                                                       |
| A value is in the answer or in a produced file           | `regex` on `last_message`, or on `{source: file, path}` for the file's contents                           |
| The answer has a required format                         | `regex` on `last_message`. Add `m` to `flags` if `^` or `$` should match each line                        |
| The answer invents nothing the input lacks               | a prompt that asks about something the input does not contain, and `regex` with `not_contains` for each value the skill might invent |
| A private value in the input does not leak               | a made-up value in the input, and `regex` with `not_contains` for it on `last_message`, `trace`, `mock_calls` and each produced file |
| The content is good by a criterion no pattern expresses  | `llm`, or `baseline` against a reference answer                                                          |

For a private value, use a made-up one. The run log keeps everything the container prints.

## Step 3. Review the plan

Review the plan before writing the cases. Changing a case now is cheap; once the case files exist it
means rewriting them.

A known problem with the skill becomes the assertion that catches it. "The summaries are too long",
for example, becomes a `regex` over the final message.

## Step 4. Write the cases

Write the eval files for each case in the plan, in the format [eval_format.md](eval_format.md)
describes, and tick the case in the plan when it is written. The four parts below are what to watch
while writing it.

### Show what the skill adds

A passing case does not prove the skill helped. Ask a model to build a spreadsheet and it will usually
manage with or without your spreadsheet skill, so the case passes either way. A good case is one the
model fails without the skill and passes with it.

`--ablation with-without` tests exactly this. It runs every case twice, with the plugin and without
it, and reports the difference between the two scores. It only works on `--docker`, because a CoWork
session always loads the skills of its profile.

Both runs get the same prompt, so write it with the run without the skill in mind:

- Ask for the result, not the steps. A prompt that names the skill or lists the steps lets the model
  follow along without the skill.
- Pick a task the model does badly on its own. If it does it well, both runs score the same.
- Do not paste the input file's content into the prompt, or the model never needs to open the file.

Write assertions that can fail in both runs. One that can only pass when the plugin is loaded makes
the two scores impossible to compare.

Make the input look real: large enough that the model cannot work it out from memory, messy the way
real inputs are, and including the edge cases the skill handles. It can go in the prompt or in a file.

### The assertions to write

Check on every case that the output is right, and on every case that needs the plugin that the
plugin loaded. Check that the run used the skill the way the skill says to when that way is itself
the requirement.

#### The plugin loaded

Add a `tool_used: Skill` grader to every case that needs the plugin. Without it, a case can pass while
the model did all the work alone. With `--ablation with-without` this grader is reported but not
scored; in a normal run it can fail the case.

The skill only loads when the prompt matches what its description says it handles. A case testing a
capability uses wording from the description. A case testing that the skill does not load too easily
stays on the same topic but avoids that wording. If the skill does something its description never
mentions, add it to the description: users asking for it will not get the skill either.

#### The output is right

Graders only read text, so they cannot look inside a spreadsheet, a slide deck, a PDF or an image. For
each thing you need to check, use a grader if it can read it, and a check if not. A check is Python
that opens the file. A case must have at least one grader, or the harness does not load it.

When both would work, use the grader, since a check is code to maintain. Prefer `regex`, `tool_used`,
`tool_order` and `file_exists` over `llm` and `baseline`, which ask a model and give results that vary
from run to run.

#### The run used the skill

The assertions above check that the skill loaded and that the output is right. They do not check how
the output was made. For example, the agent can load the skill, run its command, ignore the result,
and write the output with its own script, and every assertion above still passes.

To catch this, write a check that calls `run.judge` with three paths: the run's transcript,
`run.trace`; the skill's `SKILL.md`; and a copy of the case's `prompt.md` with its frontmatter
removed, written to `run.scratch`. The judge needs the prompt because the transcript does not include
the task. The judge answers three questions: did the run use the method the skill documents, did 
it follow the skill's instructions, and did it state anything no tool returned.

When writing the judge's instructions:

- Point it at the skill file instead of summarising the skill's rules, so it stays correct when the
  skill changes.
- Do not ask for a method the skill has no command for, or every run fails.
- Ask how the run worked, not whether the result is right. The other assertions already check that.
- If the judge's votes disagree, reword the instructions before blaming the judge.

It is the most expensive assertion, so use one per case.

### Make sure each assertion works

Before running the suite, try each assertion on an output that should pass and on one that should
fail. Test a `regex` as a JavaScript `RegExp`, which is what the harness uses. `^` and `$` match only
at the start and end of the whole text unless `flags` has `m`. Test a check on the skill's real
output. If it fails a correct output, the check is wrong.

Then ask three questions about outputs you have not seen:

- Would it fail a wrong answer?
- Would it pass a correct answer written differently?
- Would it fail an empty answer?

`not_contains` often fails the second question. A wrong answer and a right one often use the same
words, so banning a word fails good answers and passes vague ones. Assert on what the answer
concluded instead. When every assertion of a case is negative, the case fails the third question,
because an empty answer contains nothing banned. Add at least one thing the output must contain.

Check what the answer says, not how it is formatted. A correct conclusion can be a table row, a
bullet, a symbol or a sentence, so imagine two or three correct answers in different styles and make
sure the assertion passes all of them. Prefer what must be present over what must be absent, and a
minimum count over every expected item. Prefer an assertion on what a tool call produced over one on
the tool's name. Have a check return a `Result` whose `explanation` says what it found, so a failure
shows whether the skill or the assertion is wrong.

### Run the case close to real use

Run each case in conditions close to real use, so that a pass means the skill works for a user and a
fail means it does not.

For example, a weather skill runs a script that fetches the forecast from a weather service. If the
script has a bug, the call fails, the skill fails, and the case fails. That is what the case is for.
The case catches that bug only when the run can reach the service the way a real session does. Give
the run each thing the skill uses in real use:

- A credential the skill reads from an environment variable. A `--docker` run starts a container
  that receives none of your host's environment variables. To forward one, list its name under
  `env_passthrough` in the `docker:` section of `cowork_evals.yaml`:

  ```yaml
  docker:
    env_passthrough: [WEATHER_TOKEN]
  ```

  On `--cowork`, the session sets its own environment and this setting does nothing. See
  [docker.md](docker.md#environment-passthrough).
- An MCP server. A server your plugin declares in its own `.mcp.json` starts in both backends.
  Under `--docker` its tools are callable once you add them to `eval.allow_tools` in
  `cowork_evals.yaml`, as `mcp__plugin_<plugin>_<server>__*`. The list replaces the default rather
  than adding to it, so keep the default tools in it. Connectors on your CoWork account are not
  available under `--docker`. This is a temporary limitation of `cowork_evals`, not of Claude Code.
  Until it is removed, run cases that call a connector with `cowork_evals run --cowork`. See
  [approaches.md](approaches.md).
- A Python package. There is nothing to configure. The `--docker` image carries the same
  interpreter and wheels as a CoWork session, and nothing else, so a skill that imports a missing
  package fails in the run the same way it fails for a user. Check the skill's imports against
  [runtime.md](runtime.md#rules-for-code-that-runs-in-a-session) before writing cases. To test the
  skill's code on that image, run your own pytest suite with `cowork_evals test`. See
  [cowork_test.md](cowork_test.md).

## Step 5. Run the suite and read the results

Run the suite with `cowork_evals run --docker <plugin>/evals`. Run the cases that call a connector on
your CoWork account with `cowork_evals run --cowork`. See [cli.md](cli.md).

When a case fails, find out whether the skill or the assertion is wrong. The score doesn't tell you,
but the run's files do. Each failure line ends with the run's directory, `traces/<case>/run-N`, which
holds the final message, the workspace, the transcript, and the `checks.jsonl` a check leaves,
including each `run.judge` call. Look at what the skill produced and ask whether a correct answer
would have passed the assertion.

- **No:** the assertion is wrong. Fix it, and confirm on the failed run's files that a correct output
  now passes. `cowork_evals` has no command that re-grades a stored run, so run the case again to get
  its score.
- **Yes:** the failure is real. Fix the skill and leave the assertion as it is.

Never change an assertion only to raise the score.
