# Eval design

## Summary

This file explains how to design an eval suite for a Claude CoWork skill: which cases to write, how to
make each case show what the skill adds over the model working alone, and what to do with the results.

It does not repeat the case format. [eval_format.md](eval_format.md) is how a case file is written,
[checks.md](checks.md) is how to write a check, and [running_evals.md](running_evals.md) is how pass
and fail are decided.

The work has five steps, in the order of the sections below. Finish each step before starting the
next, and write no file before the developer agrees to the draft.

## Step 1. Read the skill and draft the suite

Read the skill's description and instructions: they say what it does and what it must do. Look at the
repository for real inputs, and at any existing suite for what is already covered. This is usually
enough to draft the whole suite without asking the developer anything.

Write the draft as a list, one line per case. Each line says what the case checks and what the output
must contain to pass. Do not create any files yet.

## Step 2. Check the draft against the dimensions

Each row below is a common way a skill fails. Go through the table and add a case for every row that
applies to this skill and is not in the draft yet.

A row applies only when the skill matches the "Add it when" column, and most rows will not apply. One case can cover several rows. There is no target number of cases. A case added only to fill
a row costs a run every time and tells you nothing.

The "How to check it" column names graders. When the output is not text, such as a spreadsheet or an
image, write a check instead.

| Dimension | What the case does | How to check it | Add it when |
| --------- | ------------------ | --------------- | ----------- |
| Expected behaviour, end to end | asks for the skill's whole job in one prompt | `file_exists` for the file it should create, `tool_order` if the steps must happen in order, `llm` to judge the content | always |
| The right tools are used | sends a request the skill should handle, and one on a nearby topic it should ignore | `tool_used` on `Skill` to confirm it loaded, and `tool_used` with `min: 0, max: 0` for a tool it must not call or a request it must ignore | always |
| The goal is achieved | asks for the result without saying how to get it | `file_exists` for the output file, and `regex` for a value that must be in it | always |
| Each capability on its own | one case per thing the skill can do, each asking for only that thing | `tool_used` with `input_match` on the call that capability makes, and `regex` on its output | the skill can do more than one thing |
| The instructions are followed | asks for an answer the skill's instructions shape: a format, a length, an order, a required section | `regex` on the final message. Add `m` to `flags` if `^` or `$` should match each line | the instructions say how the output must look |
| Edge cases | gives input that is empty, missing, malformed, too large, or contradictory | `regex` for the expected refusal or result, and `tool_used` with `min: 0, max: 0` for a harmful action it must not take | the instructions mention such inputs, or the skill's real input can be like that |
| Hallucination | asks for a fact that only the case's input contains, or about something that is not there | `regex` with `not_contains` for each value the skill might invent, or `baseline` against a correct answer | the skill reports facts it read |
| Context relevancy | gives more input than needed, with the answer in one part of it | `tool_used` with `input_match` naming the file it had to open | the skill must choose which inputs to read |
| Answer relevancy | asks one question whose answer has an expected shape | `regex` with `count:N` to catch padding, `llm` to judge the answer, or `baseline` against a reference | the skill's output is a message, not a file |
| PII and confidential information leakage | gives an input that contains private data the task does not need, such as a customer's phone number, and checks it is not repeated | `regex` with `not_contains` for that private value in the final message, every output file, the transcript and MCP calls | the skill reads data that can hold private information, such as customer records, emails or documents |

For the leakage row, make up the private value for the test. Never use a real credential, because the
run log keeps everything the container prints.

## Step 3. Propose the draft to the developer

Show the developer the checked draft as a list. Changing a case now is cheap; once the files exist it
means rewriting them. Describe each case in the skill's own words, not with the dimension names above.

Only ask the developer about access you cannot see in the repository, such as a credential, an
external service or an MCP server. If they do not know, design that part yourself and do not ask
again.

If the developer describes a problem, turn it into the assertion that catches it. "The summaries are
too long", for example, becomes a `regex` over the final message.

Go to step 4 once the developer agrees.

## Step 4. Write the cases

Write each case in the draft, following the four parts below.

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

### Give every case three assertions

Each case checks three things: the plugin loaded, the output is right, and the run used the skill the
way the skill says to.

#### The plugin loaded

Add a `tool_used: Skill` grader to every case that needs the plugin. Without it, a case can pass while
the model did all the work alone. With `--ablation with-without` this grader is reported but not
scored; in a normal run it can fail the case.

The skill only loads when the prompt matches what its description says it handles. A case testing a
capability uses wording from the description. A case testing that the skill does not load too easily
stays on the same topic but avoids that wording. If the skill does something its description never
mentions, tell the developer: users asking for it will not get the skill either.

#### The output is right

Graders only read text, so they cannot look inside a spreadsheet, a slide deck, a PDF or an image. For
each thing you need to check, use a grader if it can read it, and a check if not. A check is Python
that opens the file. A case must have at least one grader, or the harness does not load it.

When both would work, use the grader, since a check is code to maintain. Prefer `regex`, `tool_used`,
`tool_order` and `file_exists` over `llm` and `baseline`: those two ask a model, their results vary,
and they never decide pass or fail. A check always decides pass or fail, even when it asks a model.

#### The run used the skill

The first two assertions only look at the result, not at how it was made. A case can score 1.00 when
the agent ran the skill's command and then replaced the result with output from its own script.

To catch this, write a check that calls `run.judge` with three files: the run's transcript
(`run.trace`), the skill's `SKILL.md`, and the case's `prompt.md` without its frontmatter. The prompt
is needed because the transcript does not include the task. The judge answers three questions: did
the run use the method the skill documents, did it follow the skill's instructions, and did it state
anything no tool returned.

Mark it `@check(advisory=True)`. Its verdict is recorded and failures are shown as notes, but it does
not change the score, because a judge asked how a run worked still gets some answers wrong.

When writing the judge's instructions:

- Point it at the skill file instead of summarising the skill's rules, so it stays correct when the
  skill changes.
- Do not ask for a method the skill has no command for, or every run fails.
- Ask how the run worked, not whether the result is right. The other assertions already check that.
- Skip it for the run without the plugin, which has no skill to follow.
- If the judge's votes disagree, reword the instructions before blaming the judge.

It is the most expensive assertion, so use one per case.

### Make sure each assertion works

An assertion that can never fail, or never pass, looks fine and tells you nothing. Before running the
suite, try each one on an output that should pass and one that should fail. Test a `regex` with the
same engine the harness uses, and remember that `^` and `$` match the whole text unless `flags` has
`m`. Test a check on the skill's real output: if it fails a correct output, the check is wrong.

Then ask three questions about outputs you have not seen:

- Would it fail a wrong answer?
- Would it pass a correct answer written differently?
- Would it fail an empty answer?

The second one catches the most mistakes. `not_contains` is the usual cause: a wrong answer often uses
the same words as a right one, so banning a word fails good answers and passes vague ones. Check what
the answer concluded instead. The third one matters when all of a case's assertions are negative,
since then an empty answer passes. Add at least one thing the output must contain.

Check what the answer says, not how it is formatted. A correct conclusion can be a table row, a
bullet, a symbol or a sentence, so imagine two or three correct answers in different styles and make
sure the assertion passes all of them. Prefer what must be present over what must be absent, a
minimum count over every expected item, and the effect of a tool over its name. When an assertion
fails, it should say what it found, so you can tell a real failure from a mistake in the assertion.

### Give the case the access it needs

A case that needs something the run does not have fails for that reason and tells you nothing about
the skill. Plan around what is available, and tell the developer before writing a case that needs
something missing.

- A credential the skill reads goes in `docker.env_passthrough`.
- An external service or MCP server can be replaced by a stand-in under `mocks/`.
- Extra tools are granted with `eval.allow_tools`.
- A Python library a check imports is a dependency of your own project.
- A package the skill imports must exist in the CoWork image, which `cowork_evals test` verifies.

The details are in [eval_format.md](eval_format.md) and [docker.md](docker.md).

## Step 5. Run the suite and read the results

Run the suite.

When a case fails, find out whether the skill is wrong or the assertion is wrong before reporting
anything. The score cannot tell you; the files can. The run folder keeps the final message, the
workspace, the transcript and every judge exchange. Look at what the skill produced and ask: would a
correct answer have passed this assertion?

- **No:** the assertion is broken. Fix it and recompute the score from the files the run already
  produced. Graders and checks give the same result on the same files, so the case does not need to
  run again, unless the run used `--no-keep-traces` and the files are gone.
- **Yes:** the failure is real. Report it and leave the assertion as it is.

Never change an assertion only to raise the score. Do not re-judge `llm`, `baseline` or advisory
results yourself; report what the judge said.

Finish with one message to the developer: each case's score, each failure and its cause, the
assertions you fixed and how, the corrected scores, and what the remaining failures say about the
skill.
