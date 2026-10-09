# Directory structure

A skill is a directory holding a `SKILL.md`, inside a plugin. The plugin is what a user
installs, so a skill under no plugin cannot be installed. There is one shape, the tree below.

## The plugin

```
<plugin>/
├── .claude-plugin/
│   └── plugin.json            # name, description, version, author
├── skills/<skill>/
│   ├── SKILL.md               # required
│   ├── scripts/               # optional: only when the skill carries code
│   │   ├── <skill>.sh         # shell wrapper (executable)
│   │   └── <skill>_tool/      # Python package (underscores + _tool suffix)
│   ├── references/            # optional: agent-facing docs, loaded on demand
│   ├── resources/             # optional: supplemental reference docs
│   └── assets/                # optional: templates, images, data files
├── agents/<name>.md           # optional: flat .md files
├── commands/<name>.md         # optional: flat .md files
├── hooks/hooks.json           # optional: event handlers
├── .mcp.json                  # optional: MCP server config
├── scripts/                   # optional: helpers shared by several skills
├── tests/                     # the plugin's pytest suite, one per plugin
└── evals/<skill>/<case>/      # one eval directory per skill
```

Four properties of this tree:

- **No `pyproject.toml`, no `uv.lock`, no `.venv`, no `Dockerfile`.** Nothing is installed when a
  skill runs, so there is no project to declare and no environment to build. A dependency is
  either already on the image or bundled in the plugin as source. See `runtime.md`.
- **`tests/` and `evals/` belong to the plugin, not to the skill.** A module is shared across a
  plugin's skills, and one eval directory per skill makes a per-skill selection match the tree.
  A listing of the skill directory shows neither, so a skill can look complete and have neither.
- **The wrapper resolves its own directory.** A skill's `scripts/<skill>.sh` derives its paths
  from `$0` and never from an environment variable that may be unset. See `cli.md`.
- **A skill never links outside its own directory.** The skill is read where it is installed. A
  path that walks up out of the skill resolves in the authoring tree and nowhere else.

## Orchestration skills

A skill that carries no code of its own and drives another skill's wrapper invokes it **by path**,
`<plugin>/skills/<other>/scripts/<other>.sh`. No frontmatter key is involved, and the plugin's
`bin/` is not on `PATH`.

An orchestration skill is only installable when the skill it drives is in the same plugin, or when
the plugin declares the other one as a dependency. A wrapper reached across plugins breaks the
moment one of the two is installed alone.

## On-demand directories

`references/`, `resources/` and `assets/` load only when read. `references/` holds markdown the
`SKILL.md` body links to. `resources/` holds supplemental reference material. `assets/` holds
binary templates, images, fonts and sample data. Anything brand- or organisation-specific goes in
`assets/`, so a fork swaps assets and nothing else.

## Naming

| Thing           | Path                                             |
| --------------- | ------------------------------------------------ |
| Skill directory | `<plugin>/skills/my-skill/`                      |
| `name` field    | matches the skill directory name                 |
| Shell wrapper   | `<plugin>/skills/my-skill/scripts/my-skill.sh`   |
| Python package  | `<plugin>/skills/my-skill/scripts/my_skill_tool/` |
| Tests           | `<plugin>/tests/test_my_skill_<module>.py`       |
| Eval cases      | `<plugin>/evals/my-skill/<case>/`                |

Plugin names and skill names are kebab-case. Python packages cannot contain hyphens, so a
hyphenated skill name becomes underscores in the package and in the test file name:
`pptx-author` becomes `pptx_author_tool/` and `test_pptx_author_<module>.py`.
