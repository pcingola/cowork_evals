---
name: cowork-evals
description: "Writes and runs CoWork plugin evals, and runs a plugin's pytest suite on the CoWork runtime. TRIGGER when: writing or fixing an eval case, grader, check or plugin test, configuring cowork_evals.yaml, or running cowork_evals. NOT for skill authoring."
---

# cowork_evals

`cowork_evals` runs evals of CoWork skills and plugins, and runs a plugin's own pytest suite on
the CoWork runtime. It is an installed Python package. Evals live in this repository, not in
the package.

Read the reference that answers the question before acting on it. Each holds the whole
answer, and nothing here repeats it.

| Question                                                     | Read                           |
| ------------------------------------------------------------ | ------------------------------ |
| Which cases to write, and which assertion answers what       | `references/eval_design.md`    |
| How to write a case, field by field, and the authoring traps | `references/eval_format.md`    |
| Every grader type and field, and the harness under Docker    | `references/plugin_eval.md`    |
| An assertion no grader type can express                      | `references/checks.md`         |
| Every verb, option and exit code                             | `references/cli.md`            |
| Which backend proves what, and its cost                      | `references/approaches.md`     |
| Pass and fail, ablation, the kept run, what a run costs      | `references/running_evals.md`  |
| What plugin code may import, run and read in a session       | `references/runtime.md`        |
| Every Python package a session has, and its version          | `references/pip_freeze.txt`    |
| `test`, and the runtime a suite gets                         | `references/cowork_test.md`    |
| What `panel` shows, and the records behind it                | `references/panel.md`          |
| A `--cowork` failure: the driver code, and what to do        | `references/cowork_driver.md`  |
| What the CoWork application writes, and the grants it needs  | `references/cowork_desktop.md` |
| `ask`, one prompt to a live session                          | `references/ask.md`            |

## Workflow

1. `cowork_evals check --all`, then `setup --docker` and `login --docker` for what it reports
   missing.
2. Read the authoring traps in `references/eval_format.md`. Each one fails silently.
3. Write the case: the tree below, `prompt.md`, and one file per grader. Add `checks/` for an
   assertion no grader type can express.
4. `cowork_evals run --docker <case> --dry-run`. It validates the tree and spends nothing.
5. `cowork_evals run --docker <case>`. On a failure, read the kept run, per
   `references/running_evals.md`.
6. Run the skill's directory, then the plugin's `evals/`.
7. `--ablation with-without` to show the plugin makes a difference.
8. `cowork_evals run --cowork <path>` against the real application.
9. `cowork_evals panel <path>` to find a case that never ran on a backend.

Before adding an import, a command or a variable read to plugin code, read
`references/runtime.md`, then run `cowork_evals test --docker <plugin>/tests`.

## The command

```bash
cowork_evals check --all                       # what each backend still needs
cowork_evals setup --docker                    # build the images
cowork_evals login --docker                    # log in once, in a container
cowork_evals run  --docker <path>              # an eval: a model, graders, a verdict
cowork_evals test --docker <path>/tests        # pytest on the CoWork runtime, no model
cowork_evals ask  --cowork "<prompt>"          # one prompt to a live session, and its answer
cowork_evals panel <path>                      # every case, and what each backend last said
cowork_evals init                              # write the config, the skills, and a CLAUDE.md block
cowork_evals prune --docker                    # delete what setup built
```

`--docker` runs Claude Code in a container that reproduces the CoWork image. Use it to iterate.
`--cowork` drives the real desktop application. It needs macOS and a configured profile, and it
takes the keyboard for the length of the run. A modal asks for the keyboard once per
invocation, before the first plugin. `--dry-run` prints what would run, spends nothing, and
shows no modal.

The path sets the scope. A case directory runs that case, `evals/<skill>/` runs that skill,
`evals/` runs the plugin, and a directory holding several plugins runs each in turn.

`ask` is not an eval. The `cowork-ask` skill covers it.

## The tree

```
<plugin>/.claude-plugin/plugin.json       # what makes <plugin> a plugin root
<plugin>/skills/<skill>/SKILL.md
<plugin>/evals/<skill>/<case>/prompt.md
<plugin>/evals/<skill>/<case>/graders/<name>.md
<plugin>/evals/<skill>/<case>/checks/<name>.py  # optional, assertions as Python
<plugin>/evals/<skill>/<case>/case.yaml   # optional, context.* only
<plugin>/evals/plugin/<case>/             # a case that crosses skills
<plugin>/evals/mocks/<server>/<tool>.md   # MCP tool mocks shared by every case
```

A directory directly under `evals/` is a skill name, `plugin` or `mocks`, and nothing else. The
validator enforces this in both directions. Fixtures live inside the case that uses them.
