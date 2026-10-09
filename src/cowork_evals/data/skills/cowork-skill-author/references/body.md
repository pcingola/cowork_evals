# SKILL.md body

Budget: 500 lines or fewer, around 5000 tokens. Move long content to `references/`.

Start with an H1 matching the skill's display name, for example `# Data Analysis`.

## Structure

1. Introduction: one paragraph on what the skill does and when to use it.
2. Instructions: numbered steps for the primary workflow, one subsection per mode.
3. CLI reference, if the skill has scripts: commands by category, with syntax and main flags.
4. Rules: the constraints the agent follows, as a list.

## Progressive disclosure

Skills load in three tiers:

| Tier         | Size                | Loaded                                                        |
| ------------ | ------------------- | ------------------------------------------------------------- |
| Metadata     | around 100 tokens   | `name` and `description`, at startup, for every skill         |
| Body         | under 5000 tokens   | when the skill activates                                      |
| Resources    | any                 | `references/`, `scripts/`, `assets/`, `resources/`, when read |

Anything long, rarely needed, or needed only in one sub-task goes in a reference file the body
links to. References are one level deep: `SKILL.md` links to `references/<topic>.md`, and a
reference links to no other reference.

## Principles

- Agent-facing only. Implementation and architecture belong in the project's documentation.
- State the outputs: where files are written, and in what format.
- State non-obvious behaviour, for example "batch correction is off by default".
- Every path is relative to the skill root, such as `references/<topic>.md`, and the file exists.
- No link leaves the skill directory. The skill ships alone, so such a link resolves only in the
  authoring tree. Inline a rule that lives in a project document.
- An asset the skill's output references ships with the skill. A generated HTML file that points
  at a CDN, or a generated script with a bare JS module specifier, resolves to nothing in a
  session. Bundle the asset and reference it by relative path.
