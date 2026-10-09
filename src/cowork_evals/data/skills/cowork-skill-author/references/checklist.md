# Review checklist

Run every applicable item. Items marked _(code)_ apply only to a skill that carries scripts.

Report failures and warnings separately. A failure is a defect. A warning is a question, and is
never reported as a defect.

Sections A to F are answered by reading the skill's files. Sections G and H are answered by
reading the code and its fenced examples, which a file listing does not show.

`claude plugin validate --strict` checks the manifests and that each `SKILL.md` frontmatter
parses. It reads no field and nothing outside the manifests. A2b is the only item it catches.

______________________________________________________________________

## A. Frontmatter

The rules are in `frontmatter.md`.

- **A1.** `name` matches `^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$` and the parent directory name.
- **A2.** `description` is one line.
- **A2b.** `description` is quoted. Unquoted, the skill loads with every field dropped.
- **A2c.** _(warning)_ `description` is longer than around 250 characters. Measure with
  `echo -n '<desc>' | wc -c`, and ask what the extra characters buy.
- **A3.** The description starts with a third-person verb: "Extracts...", not "Use this...".
- **A4.** It contains `TRIGGER when:` with concrete user phrases or file extensions.
- **A4b.** `TRIGGER when:` comes early, not after a long capability sentence.
- **A5.** It declares `NOT for ...` where the boundary with an adjacent skill is unclear.
- **A6.** No `allowed-tools` key.
- **A7.** System binaries the skill runs (LibreOffice, Poppler, Tesseract) are declared in
  `compatibility` with install hints. Python packages are not.
- **A8.** `version`, if set, is a top-level string, not inside `metadata`.

## B. Directory structure

The tree is in `structure.md`.

- **B1.** `SKILL.md` exists at the skill root.
- **B2.** The skill sits at `<plugin>/skills/<name>/`, under a directory carrying
  `.claude-plugin/plugin.json`.
- **B3.** No stray files at the skill root.
- **B4.** No committed secrets, API keys, `.env` files, internal hostnames, absolute local paths
  or personal data. `.env_example` is allowed.
- **B5.** Every file the `SKILL.md` body references exists.
- **B6.** No link leaves the skill directory: no `../`, no path into a sibling project, in
  `SKILL.md` or any reference. A wrapper's own path arithmetic is not a link, see D2.
- **B7.** Nothing is left from the repository it was ported from: no other runtime's sandbox, no
  `Dockerfile` or `.dockerignore`, no notebook workflow, no container paths. Grep for the source
  repository's name.
- **B8.** _(code)_ `scripts/` holds `<name>.sh` and the `<name>_tool/` package.

## C. SKILL.md body

The rules are in `body.md`.

- **C1.** 500 lines or fewer, around 5000 tokens.
- **C2.** Agent-facing only, no implementation or architecture.
- **C3.** Step-by-step instructions for the primary workflow.
- **C4.** Command syntax, if the skill has scripts.
- **C5.** Outputs: where files are written, and in what format.
- **C6.** Non-obvious behaviour is stated.
- **C7.** References are one level deep.

## D. Shell wrapper _(code)_

- **D1.** `scripts/<name>.sh` exists and is executable.
- **D2.** It has the form in `wrapper.md`: `#!/bin/bash -eu`, `set -o pipefail`, `SCRIPT_DIR` from
  `$0`, then `exec env PYTHONPATH="$SCRIPT_DIR" python3 -m <name>_tool "$@"`.
- **D3.** `<wrapper> --help` exits 0.

## E. Python package _(code)_

- **E1.** The package is `scripts/<name>_tool/` with `__init__.py`, `__main__.py` and argparse
  dispatch.
- **E2.** Its intra-package imports are absolute.

## F. Tests and evals

Both live in the plugin, outside the skill directory. Check the paths.

- **F1.** Unit tests live in the plugin's `tests/`, named after the skill and the module they
  cover. `cowork_evals test --docker <plugin>/tests` passes.
- **F2.** `<plugin>/evals/<skill>/` holds at least a case where the skill fires and a case where
  it must not. Where the description declares `NOT for` (A5), the second case records it.
- **F3.** A case is a directory: `prompt.md` with frontmatter, and one file per grader under
  `graders/`, each with `---` delimiters.
- **F4.** The case rests on structural graders wherever one can express the assertion. A judged
  grader also decides the exit code, but it is a model's vote.

The `cowork-evals` skill holds the case format.

## G. Does it run in a session?

Read the code against `runtime.md`. Then run `cowork_evals test --docker <plugin>/tests`, which
catches an import the tests reach, and `cowork_evals run --docker <plugin>/evals`, which catches
a command or a variable in a `Bash` call the evals reach.

- **G1.** Nothing installs at run time, and no wrapper runs a project manager: no
  `uv run --project`, `pip install`, `npm install` or `apt-get install`.
- **G2.** No `pyproject.toml`, `uv.lock`, `.venv`, `node_modules` or `Dockerfile` anywhere in the
  plugin.
- **G3.** No Python 3.11+ syntax or API. `runtime.md` lists the common ones.
- **G4.** Every Python import is the standard library, a package in `pip_freeze.txt`, or a module
  the plugin ships.
- **G5.** Every command the skill runs is installed: in scripts, hook commands, `subprocess`
  calls, and every fenced shell block the model is told to run.
- **G6.** Every JS module is a Node built-in, a global package loaded with `require()`, or a file
  the skill ships.
- **G7.** Every environment variable read is in `runtime.md`'s table.
- **G8.** Nothing is written outside `$TMPDIR` and the user's `outputs` folder.
- **G9.** The skill's output references no asset the skill does not ship: no CDN URL, no bare JS
  module specifier. Read the fenced HTML and the templates, because tests do not catch it.
- **G10.** Nothing depends on the laptop: no x86_64 binary, no macOS command (`open`, `pbcopy`,
  `sed -i ''`), no Microsoft font.

## H. Wiring a file listing does not show

| Item | Fault                                                                                      | Check                                                                            |
| ---- | ------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------- |
| H1   | A script invoked through `${CLAUDE_PLUGIN_ROOT}` or `${CLAUDE_SKILL_DIR}`                   | Neither is set in a session. Use a path relative to the skill directory          |
| H2   | An `mcp__plugin_<plugin>_<server>__` tool prefix matching no server in the plugin's config | Grep the prefix, and confirm the server name is in that plugin's `.mcp.json`     |
| H3   | A `SKILL.md` that says the plugin's `bin/` is on `PATH`                                    | It is not. The skill calls the script by its path in the plugin                  |
