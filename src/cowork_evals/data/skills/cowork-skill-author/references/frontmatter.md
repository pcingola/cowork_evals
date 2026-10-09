# Frontmatter

## `name` (required)

1 to 64 chars, lowercase alphanumeric plus hyphens, no leading, trailing or consecutive hyphens.
Must match the parent directory name.

Regex: `^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$`

## `description` (required)

The description is the only text matched against a request, so it decides whether the skill
fires.

Structure:

1. Capability sentence in third person, "Extracts text from PDFs", not "Use this skill to...".
2. `TRIGGER when:`, concrete user phrases, file extensions, task patterns.
3. `NOT for ...` where the boundary with a neighbouring skill is fuzzy.

**One literal line.** Multi-line YAML breaks the parser.

**Quoted.** `TRIGGER when:` puts a colon and a space in the value, which is a parse error in a
plain YAML scalar. Use single quotes if the text contains `"..."` phrases, double quotes
otherwise. An unquoted description fails `claude plugin validate --strict` with
`YAML frontmatter failed to parse`, and the skill loads with every field dropped.

**Around 250 characters.** Every character is loaded in every session. It is a target, not a
limit: descriptions past 1000 characters render in full in the loaded skill list, and shipped
skills at 349 and 542 characters match. Past the target, ask what the extra characters buy.

**Triggers early.** The trigger list is the part that matches user phrasing. A long capability
sentence in front of it hides it.

**The negative case.** A greedy description takes over unrelated conversations. Where two skills
are adjacent (`pptx` and `pptx-author`, `pdf` and `pdf-redact`), state the boundary in the
description and record an eval case that must not fire.

Always measure: `echo -n '<description>' | wc -c`

### Good

```
Analyzes datasets in CSV, TSV, and Excel formats. Generates summary statistics, filters rows, and produces charts. TRIGGER when: user asks to explore, summarize, or visualize tabular data.
```

### Bad

```
Use this skill to analyze data
# first person, no TRIGGER when
```

```
A very powerful and flexible tool that can do many things including reading, writing, converting, transforming, analyzing, summarizing, filtering, grouping, aggregating, pivoting, and producing charts from ... TRIGGER when: user mentions spreadsheet.
# the capability sentence buries the triggers, and says nothing concrete
```

```
Helps with documents
# vague, no TRIGGER, no specifics
```

### Anti-patterns

- No `TRIGGER when:`. A capability alone gives nothing to match.
- Vague triggers, such as "when needed" or "when relevant". Use concrete phrases.
- First or second person, such as "I can help you" or "Use this skill to".
- The skill name repeated. Use the characters for trigger phrases.

## `version` (optional)

A free-form string at the top level, not inside `metadata`. Nothing compares versions on
reload. It is unrelated to the plugin's `version` in `plugin.json`.

## `allowed-tools`, do not use it

The key takes paths relative to the authoring tree, such as
`Bash(skills/<name>/scripts/<name>.sh:*)`. Once the skill is installed under
`<plugin>/skills/<name>/` they point at nothing, silently. Skills ported from another repository
carry it. Drop it. A skill that calls another skill's wrapper calls it by path, with no
`allowed-tools`.

## `metadata` (optional)

A string-to-string map for free-form keys such as `author` or `date`.

## Other optional fields

- `license`, license name or reference to a bundled file.
- `compatibility`, 500 chars or fewer. Declare runtime and system requirements here: external
  tools or system binaries the skill shells out to, not pip dependencies, with install hints.
  Example: `Requires LibreOffice and Poppler (pdftoppm) for visual-preview and export-pdf.`

Nothing reads the optional keys at run time, and `claude plugin validate --strict` checks only
that the frontmatter parses, so it accepts an unknown key. They are for the human reader.
