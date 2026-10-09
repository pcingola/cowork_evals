---
name: cowork-skill-author
description: 'Authors and reviews CoWork skills and plugins, and checks code against the CoWork runtime. TRIGGER when: "create a skill", "new skill", "review skill", "check skill", "validate skill", "skill audit", or does plugin code run in CoWork. NOT for eval cases.'
---

# CoWork skill author

Authors and reviews skills against the Agent Skills spec and against the CoWork session they
run in. A CoWork session is an Ubuntu 22.04 aarch64 VM with Python 3.10.12 and a fixed set of
packages, commands and environment variables. Code in a skill uses what is there, and nothing
else.

Eval cases are the `cowork-evals` skill. Asking a live session a question is the `cowork-ask`
skill.

| Reference                   | Holds                                                                |
| --------------------------- | -------------------------------------------------------------------- |
| `references/structure.md`   | The plugin and skill tree, and what each directory is for            |
| `references/frontmatter.md` | Every frontmatter field, and what the description has to do         |
| `references/body.md`        | The `SKILL.md` body and its progressive-disclosure budget            |
| `references/wrapper.md`     | The shell wrapper and the Python package, for a skill with code      |
| `references/runtime.md`     | Python, commands, Node and environment variables in a CoWork session |
| `references/pip_freeze.txt` | `pip freeze` in a session: every Python package and its version      |
| `references/checklist.md`   | The review checklist, sections A to H                                |

## Does it run in a session

Read `references/runtime.md` before writing an import, a command or a variable read. Then
settle it on the Docker image, which reproduces the CoWork image:

```bash
cowork_evals test --docker <plugin>/tests     # the plugin's tests, on the session's Python and packages
cowork_evals run --docker <plugin>/evals      # the skills end to end, in the session environment
```

`test` checks the Python the tests reach. `run` checks the commands and variables each `Bash`
call reaches. Code that neither reaches is not checked.

## Author a new skill

1. Gather requirements: what the skill does, whether it needs scripts, what triggers it, and
   what must not trigger it.
2. Scaffold the plugin shell if the plugin does not exist, per `references/structure.md`:
   `.claude-plugin/plugin.json`, `skills/`, and `agents/`, `commands/` or `hooks/` only when
   used, `tests/` for the plugin's pytest suite, and `evals/<skill>/` for its eval cases.
3. Scaffold the skill directory, `<plugin>/skills/<skill>/`, per `references/structure.md`.
4. Write `SKILL.md`: frontmatter per `references/frontmatter.md`, body per
   `references/body.md`.
5. If the skill has scripts, write the wrapper and the package per `references/wrapper.md`. Keep
   every import, command and variable within `references/runtime.md`.
6. If the skill carries code, write its tests in `<plugin>/tests/` and run them with
   `cowork_evals test --docker <plugin>/tests`.
7. Write the eval cases in `<plugin>/evals/<skill>/`: at least a case where the skill fires
   and a case where it must not. The `cowork-evals` skill holds the format.
8. Run `references/checklist.md`. Fix every failure before reporting done.

## Review an existing skill

1. Identify the target: a skill name, or every skill in the plugin.
2. Locate the plugin shell: the `.claude-plugin/plugin.json` above the skill, the plugin's
   `tests/`, and `evals/<skill>/`. A skill under no plugin cannot be installed.
3. Run every applicable item of `references/checklist.md`, A to H. Read the files, including
   the manifest, the tests and the evals, which sit outside the skill directory.
4. Run `cowork_evals test --docker <plugin>/tests`.
5. Report a pass and fail table by section, with the defect and the fix for each failure.
   Report warnings apart from failures.
6. Apply the fixes the user asks for, then run the checklist and the tests again.

## Rules

- The Agent Skills spec is https://agentskills.io/specification.
- `claude plugin validate <plugin> --strict` checks the manifests and that each `SKILL.md`
  frontmatter parses. It reads no frontmatter field, so a clean validate proves nothing else.
- When a question about the session is still open, `cowork_evals ask --cowork` settles it:
  ask the session to run the import or the command, and read what it did.
