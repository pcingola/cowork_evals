# Skills with code

A skill with code carries `scripts/`: a shell wrapper, and the Python package it runs. Every
import is on the image or bundled in the plugin as source. See `runtime.md`.

## Shell wrapper

Create `scripts/<skillname>.sh`, one wrapper per tool package:

```bash
#!/bin/bash -eu
set -o pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd -P)"
exec env PYTHONPATH="$SCRIPT_DIR" python3 -m <skillname>_tool "$@"
```

Then: `chmod +x scripts/<skillname>.sh`

Each of the four properties is required:

- **`SCRIPT_DIR` comes from `$0`.** `$0` is always defined. `${CLAUDE_PLUGIN_ROOT}` and
  `${CLAUDE_SKILL_DIR}` are not, so a wrapper that reads one with no `:-` fallback fails the
  moment it is invoked from a test, from another skill, or from a shell.
- **`-m` is what makes the package's own imports resolve.** `python3 <skillname>_tool/cli.py` puts
  the package directory on `sys.path` rather than its parent, so the package cannot import itself,
  and it runs nothing unless that module carries an `if __name__ == "__main__"` guard.
- **`PYTHONPATH` gets only the skill's own `scripts/` directory.** Skills in one plugin share an
  interpreter, not a namespace.
- **`python3` is executed directly.** No project manager and no install. See the list below.

Drop `-m` and `PYTHONPATH` only for a tool that is a single file importing nothing of its own.

## Python package

Create `scripts/<skillname>_tool/`:

**`__init__.py`**, empty or a one-line docstring.

**`__main__.py`**:

```python
from <skillname>_tool.<skillname> import main

main()
```

**`<skillname>.py`**, the main module, with argparse subcommand dispatch:

```python
import argparse
import sys


def cmd_example(args):
    pass


def main():
    parser = argparse.ArgumentParser(prog="<skillname>")
    sub = parser.add_subparsers(dest="command")
    p = sub.add_parser("example", help="Do something")
    p.add_argument("input", help="Input file")
    p.set_defaults(func=cmd_example)
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    args.func(args)
```

For many subcommands, split into `cmd_*.py` modules with shared code in `common.py`.

**Intra-package imports are absolute**, `from <skillname>_tool import common`, never
`from .common import ...`. Both resolve under `-m`, and the absolute form is the one that still
resolves when a module is run or imported directly.

## What a script must not carry

- No `# /// script` inline metadata block, and no `uv run --script` shebang. The shebang is
  `#!/usr/bin/env python3`.
- No `pyproject.toml` and no `uv.lock`, anywhere in the plugin. Nothing builds the environment
  they declare.
- No install call, direct or shelled out: `pip install`, `uv pip install`, `npm install`,
  `apt-get install`, `conda`, `brew`.
- No proxy handling, no `ssl_verify` toggle, no `.env` loading. A session shell has no
  credential and no proxy or CA variable. A service that needs a credential is reached through an
  MCP server.

A script that runs a sibling Python script uses `sys.executable`, never a bare `python` or
`python3`.

## After writing the wrapper

```bash
chmod +x scripts/<skillname>.sh
scripts/<skillname>.sh --help        # must exit 0
```

An import error appears only when the wrapper runs, and usually means an import the image does
not carry. Check it against `runtime.md` and `pip_freeze.txt`. `--help` on a laptop proves the
imports resolve on the laptop's Python only. `cowork_evals test --docker <plugin>/tests` runs
the plugin's tests on the session's Python and wheel set.
