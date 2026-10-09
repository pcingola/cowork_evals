# Review Checklist

Run every applicable item. Items marked _(code)_ apply only to skills that carry scripts.
Everything else applies to every skill.

Report failures and warnings separately. A **failure** is a defect. A **warning** is a question
worth answering, and must never be reported as a defect.

Sections A to F are answered by reading the skill's own files. Sections G and H are answered by
reading the code and the fenced examples inside it, which is why a file listing passes a skill that
cannot run.

______________________________________________________________________

## A. Frontmatter

Every item here except A2b is a manual check. `claude plugin validate --strict` parses the
frontmatter but reads none of its fields.

- **A1.** `name` is present, matches `^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$`, and matches the
  parent directory name
- **A2.** `description` is present and on a **single line**. Multi-line YAML breaks the parser,
  hard fail.
- **A2b.** `description` is **quoted**. Every description contains `TRIGGER when:`, and a
  colon-plus-space inside a plain YAML scalar is a parse error. Quote it: single quotes if the text
  contains `"..."` phrases, double quotes otherwise. This one _is_ caught by
  `claude plugin validate --strict`, and it is the only frontmatter item that is: an unquoted
  description fails with `YAML frontmatter failed to parse`, and the skill loads with **every field
  silently dropped**.
- **A2c.** _(warning, never a failure)_ `description` is longer than around 250 chars. Measure with
  `echo -n '<desc>' | wc -c`, then ask what the extra characters buy, because every one is paid in
  every session by every user. There is no truncation limit to enforce: shipped skills at 349 and
  542 chars match fine.
- **A3.** Description starts with a third-person verb ("Extracts...", not "Use this...")
- **A4.** Description contains `TRIGGER when:` with concrete user phrases or file extensions
- **A4b.** `TRIGGER when:` is front-loaded, not buried behind a long capability sentence. The
  trigger list is the part that has to match user phrasing, so it comes early.
- **A5.** Description declares the negative case (`NOT for ...`) where the boundary with a
  neighbouring skill is fuzzy
- **A6.** **No `allowed-tools` key.** It takes paths relative to the authoring tree, which do not
  resolve once the skill is installed under `<plugin>/skills/<name>/`, so it silently points at
  nothing. Skills ported from a source repo carry it and it must be dropped. A skill that calls
  another skill's CLI invokes the wrapper by path instead.
- **A7.** If the skill shells out to system binaries or external tools (LibreOffice, Poppler,
  Tesseract), they are declared in `compatibility` with install hints. Pip dependencies do not
  belong there.
- **A8.** `version`, if set, is a top-level string, not inside `metadata`. It is unrelated to the
  plugin's `version`.

**What `claude plugin validate --strict` does and does not do.** It checks the manifests, and it
checks that each `SKILL.md`'s YAML frontmatter **parses**. It reads none of the fields. Measured: a
`SKILL.md` carrying `version`, `compatibility`, an `allowed-tools` pointing at a script that does
not exist, **and** an invented `bogus-key` validated clean; an unquoted `description` failed. Two
consequences: every item in section A except A2b is manual, and nothing outside the manifests is
checked at all, so sections B to H are invisible to it. "Validate passed" is no evidence that any
of the rest hold.

## B. Directory structure

- **B1.** `SKILL.md` exists at the skill root
- **B2.** The skill sits at `<plugin>/skills/<name>/`, under a directory carrying
  `.claude-plugin/plugin.json`. A skill under no plugin cannot be installed.
- **B3.** No stray files at the skill root that do not belong, see `structure.md`
- **B4.** No committed secrets, API keys, `.env` files, internal hostnames, absolute local paths,
  or PII. `.env_example` is fine.
- **B5.** All files referenced in the `SKILL.md` body exist on disk
- **B6.** No documentation link that walks outside the skill directory: no `../`, no path into a
  sibling project directory, in `SKILL.md` or any reference file. The skill ships alone, so such a
  link resolves in the authoring tree and nowhere else. If a rule lives elsewhere, inline the rule.
  A wrapper's own path arithmetic is not a link, see D2.
- **B7.** No leftovers from the source it was ported from: no mention of another runtime's sandbox,
  no `Dockerfile` or `.dockerignore`, no notebook workflow, no container paths. If the skill was
  copied, grep for the source repo's name.
- **B8.** _(code)_ `scripts/` holds `<name>.sh` and the `<name>_tool/` package, and **no
  `pyproject.toml`, no `uv.lock`, no `.venv`**. There is no environment to declare, see section G.

## C. SKILL.md body

- **C1.** 500 lines or fewer, around 5000 tokens
- **C2.** Agent-facing only, no implementation details or architecture. Those belong in the
  project's documentation.
- **C3.** Has step-by-step instructions for the primary workflow
- **C4.** Documents command syntax if the skill has scripts
- **C5.** Documents outputs, where files are written and in what format
- **C6.** Calls out non-obvious behaviour
- **C7.** References are one level deep, `SKILL.md` to `references/topic.md`, no nested chains

## D. Shell wrapper _(code)_

- **D1.** Exists at `scripts/<name>.sh` and is executable
- **D2.** Follows the form in `cli.md`: `#!/bin/bash -eu`, `set -o pipefail`,
  `SCRIPT_DIR` resolved from `$0`, then
  `exec env PYTHONPATH="$SCRIPT_DIR" python3 -m <name>_tool "$@"`. The path arithmetic comes from
  `$0` because `$0` is always defined.
- **D3.** Runs without import errors: `<wrapper> --help` exits 0

## E. Python package _(code)_

- **E1.** The package declares no project file of its own. Every import is on the image or bundled
  in the plugin as source, see section G and `runtime.md`.
- **E2.** The package is `scripts/<name>_tool/` with `__init__.py`, `__main__.py`, and argparse
  dispatch, and its intra-package imports are absolute

## F. Tests and evals

Both live in the plugin, outside the skill directory. Listing the skill shows neither, so a skill
can look complete and have no test and no eval at all. Check the paths, do not infer from the tree.

- **F1.** Unit tests live in the plugin's `tests/`, named after the skill and the module they
  cover. They never run in a session, which has no pytest. `cowork_evals test --docker
  <plugin>/tests` runs them on the session's Python and wheel set, and passes.
- **F2.** Every skill has an eval directory, `<plugin>/evals/<skill>/`, holding at least a case
  where the skill fires and a case where it must not.
- **F3.** A case is a directory: `prompt.md` with frontmatter, and one file per grader under
  `graders/`. A grader file missing its `---` delimiters is read as a note and silently ignored.
- **F4.** Every grader decides the exit code, a judged one included. A judged grader is a
  model's vote, so the case rests on structural graders wherever one can say it.

`cowork_evals run --docker <plugin>/evals/<skill>` runs the cases, and the `cowork-evals` skill
holds the case format. Where the description declares a negative trigger (A5), F2's non-firing
case is the one that records it.

## G. Does it run in a session?

Nothing installs when a skill runs. Read the code against `runtime.md`. Then run
`cowork_evals test --docker <plugin>/tests`, which catches an import the tests reach, and
`cowork_evals run --docker <plugin>/evals`, which catches a command or a variable in a `Bash`
call the evals reach.

- **G1.** No wrapper installs anything and none runs a project manager: no `uv run --project`,
  no `pip install`, no `npm install`, no `apt-get install`. The wrapper execs `python3` directly.
- **G2.** No `pyproject.toml`, `uv.lock`, `.venv`, `node_modules` or `Dockerfile` in the plugin.
  A skill ported from a source repository usually ships several.
- **G3.** No 3.11+ syntax or API. The session is Python 3.10.12, and `runtime.md` lists the
  names that fail.
- **G4.** Every Python import is the standard library, a package in `pip_freeze.txt`, or a
  module the plugin ships.
- **G5.** Every command the skill runs is installed: in scripts, in hook commands, in
  `subprocess` calls, and in every fenced shell block the model is told to run. `runtime.md`
  names the common ones that are not.
- **G6.** Every JS module is a Node built-in, a global package loaded with `require()`, or a
  file the skill ships.
- **G7.** Every environment variable read is in `runtime.md`'s table. No `CLAUDE_PLUGIN_ROOT`,
  `CLAUDE_SKILL_DIR` or credential variable.
- **G8.** Nothing is written outside `$TMPDIR` and the user's `outputs` folder.
- **G9.** Nothing the skill's output references is an asset the skill does not ship: no CDN
  URL, no bare JS module specifier in a generated file.
- **G10.** Nothing depends on the laptop: no x86_64 binary, no macOS command (`open`, `pbcopy`,
  `sed -i ''`), no Microsoft font.

G9 is a property of what the skill writes, not of what it ships. Read the fenced HTML and the
templates. A skill that writes a deck pointing at an unbundled JS framework passes its tests
and fails in a session.

## H. Wiring a file listing does not show

| Item | Fault                                                                                      | How to check                                                                     |
| ---- | ------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------- |
| H1   | A script invoked through `${CLAUDE_PLUGIN_ROOT}` or `${CLAUDE_SKILL_DIR}`                   | Neither is set in a session. A relative path from the skill directory, or a wrapper that resolves its own directory |
| H2   | An `mcp__plugin_<plugin>_<server>__` tool prefix matching no server in the plugin's config | Grep the prefix, then confirm the server name is in that plugin's `.mcp.json`    |
| H3   | A `SKILL.md` claiming the plugin's `bin/` is on `PATH`                                     | It is not. The skill calls the script by its path in the plugin                 |
