# CoWork runtime

## Summary

A CoWork session is an Ubuntu 22.04.5 aarch64 VM. Each skill, command, agent and hook in a
plugin runs inside it, and uses what the image carries, or what the plugin ships as source, and
nothing else. Every value in this file was read from a real session. It is what one session
held, not a contract the product offers.

- A session cannot count on an earlier one. Each session is a new user with a new home
  directory, so anything installed during a session is paid for again in the next.
- Plugin code is bound to Python 3.10 and the installed package set. No install at run time,
  no virtualenv, no package that is not already there.
- The host gives a skill less than a laptop does. No plugin `bin/` on `PATH`, no working
  directory at the skill, no shell state between `Bash` calls.

The Docker image `cowork_evals setup --docker` builds reproduces this image. The tables below
are a selection. Whether an import resolves or a command exists is settled on that image:

```bash
cowork_evals test --docker <plugin>/tests     # the plugin's tests, on the session's Python and packages
cowork_evals run --docker <plugin>/evals      # its evals, with the session's environment variables
```

## Rules for code that runs in a session

These bind every file under the path passed to `cowork_evals run`: each skill, command, agent
and hook in the plugin. They do not bind `cowork_evals` itself, which runs on a laptop. They do
not bind a case's `checks/*.py`, which runs on the host after the run is graded and imports
what the consumer's own repository declares.

- Python 3.10 syntax only. See [Python](#python).
- Import the standard library, a package in [pip_freeze.txt](pip_freeze.txt), or a module the
  plugin ships. Nothing else resolves.
- Run a command the image carries, or one the plugin ships, by a path relative to the skill.
  The plugin's `bin/` is not on `PATH`.
- Read only a variable in [the variable table](#what-the-host-provides). Any other name
  expands to the empty string, and the command then fails on a path that starts with `/`.
  Never hard-code `/sessions/<session>`.
- No install at run time: no `pip install`, `uv pip install`, `npm install`,
  `apt-get install`, `brew`, `conda`, no `npx` of a package that is not global, and no script
  that shells out to one.
- No virtualenv: no `.venv`, `node_modules`, conda environment or other per-session
  environment directory. No `pyproject.toml`, `uv.lock` or `package.json` dependencies in the
  plugin. Nothing builds them.
- Use what is already there. Check the inventory below before assuming a package is missing:
  `pandas`, `python-docx`, `pypdf`, LibreOffice, ffmpeg and ImageMagick are present.
- Bundle instead of installing. A small pure-Python or pure-JS file shipped inside the plugin
  costs one download at plugin install, not one per session.
- When work needs a library the image lacks, use an MCP server or a remote API. Do not pull
  the library into the session.
- A credential comes from an MCP server, never from the environment or a `.env` file.
- Write temporary files under `$TMPDIR`, and what the user gets under the mounted `outputs`
  folder. Leave nothing in the user home or the project.
- Output the skill writes references only what the skill ships: no CDN URL, and no bare module
  specifier in a generated file.

## Python

Python 3.10.12, at `/usr/bin/python3`, `/usr/bin/python3.10` and `/usr/bin/python`. The
installed packages and their exact versions are [pip_freeze.txt](pip_freeze.txt), the verbatim
`pip freeze` of a session.

Code written for 3.11 or later often parses on 3.10 and fails at the first call.

| Not in 3.10                             | Use                                           |
| --------------------------------------- | --------------------------------------------- |
| `datetime.UTC`                          | `datetime.timezone.utc`                       |
| `enum.StrEnum`                          | `class X(str, enum.Enum)`                     |
| `tomllib`                               | JSON or YAML: no TOML parser is installed     |
| `typing.Self`, `Never`, `LiteralString` | a `TypeVar`, `NoReturn`, `str`                |
| `typing.Required`, `NotRequired`        | two `TypedDict` classes, `total=False` on one |
| `typing.override`                       | drop it                                       |
| `ExceptionGroup`, `except*`             | a list of exceptions                          |
| `asyncio.TaskGroup`, `asyncio.timeout`  | `asyncio.gather`, `asyncio.wait_for`          |
| `contextlib.chdir`                      | `os.chdir` in `try`/`finally`                 |
| `itertools.batched`                     | a loop                                        |
| PEP 695 `type X = ...`, `def f[T]()`    | `TypeAlias`, `TypeVar`                        |

`match` is available. `X | Y` in an annotation needs `from __future__ import annotations`.

Import names differ from the names in `pip_freeze.txt`:

| Package                                   | Import                     |
| ----------------------------------------- | -------------------------- |
| `beautifulsoup4`                          | `bs4`                      |
| `PyYAML`                                  | `yaml`                     |
| `Pillow`                                  | `PIL`                      |
| `python-docx`, `python-pptx`              | `docx`, `pptx`             |
| `opencv-python`, `opencv-python-headless` | `cv2`                      |
| `python-dateutil`, `python-dotenv`        | `dateutil`, `dotenv`       |
| `pdfminer.six`                            | `pdfminer`                 |
| `camelot-py`, `tabula-py`                 | `camelot`, `tabula`        |
| `odfpy`, `Wand`, `fonttools`              | `odf`, `wand`, `fontTools` |

`uno` and `unohelper`, LibreOffice's bindings, import from the system interpreter.

| Area          | Notable installed packages                                                                                                                                                                                                             |
| ------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Document, PDF | `python-docx`, `python-pptx`, `openpyxl`, `xlsxwriter`, `xlrd`, `pypdf`, `pypdfium2`, `pdfplumber`, `pdfminer.six`, `pikepdf`, `pdf2image`, `camelot-py`, `tabula-py`, `img2pdf`, `pdfkit`, `reportlab`, `markitdown`, `odfpy`, `pyoo` |
| Data          | `pandas`, `numpy`, `matplotlib`, `seaborn`, `opencv-python`, `opencv-python-headless`, `Pillow`, `sympy`                                                                                                                               |
| Web, parsing  | `requests`, `beautifulsoup4`, `lxml`, `markdown`, `markdownify`, `mistune`, `marko`, `Jinja2`                                                                                                                                          |
| OCR, ML       | `pytesseract`, `onnxruntime`, `magika`                                                                                                                                                                                                 |
| Other         | `Wand` (ImageMagick binding), `graphviz`, `psutil`, `python-dotenv`                                                                                                                                                                    |

Not installed, and often carried by a ported skill: `httpx`, `typer`, `rich`, `structlog`,
`pydantic`, `pymupdf`, `anthropic`, `openai`, `google-genai`, `tenacity`, `mammoth`,
`pypandoc`, `weasyprint`, `pytest`.

## What the host provides

| Mechanism                                   | Present in a skill Bash call | Evidence                                                                                 |
| ------------------------------------------- | ---------------------------- | ---------------------------------------------------------------------------------------- |
| Plugin `bin/` on `PATH`                     | no                           | `PATH` is the OS default with the global npm `bin/` in front. See the table below        |
| `cwd` set to the skill directory            | no                           | `pwd` is the session root. A bare `python scripts/x.py` fails with ENOENT                |
| Shell state across Bash calls               | no                           | Each call is a fresh shell. No `cwd` and no exported variable survives                   |
| `Base directory for this skill: <abs path>` | yes                          | Injected above the `SKILL.md` body at invocation time, not in the file                   |
| `TMPDIR`                                    | yes                          | `/sessions/<session>/tmp`, honoured by `tempfile.mkdtemp()`. `/tmp` is also writable     |
| The same environment as a plain Bash call   | yes                          | `env` in a skill's Bash call and in a Bash call with no skill print the same variables   |

A Bash call runs GNU bash 5.1.16, whatever `SHELL` says. The shell is PID 2 in its own PID
namespace, and PID 1 is `bwrap`.

The complete environment of a session shell is below. `<session>` is the generated session
name, three words joined by hyphens. It is also the Unix user name, and it changes every
session. bash itself sets `_` and its own shell variables. No other variable is set.
`INVOCATION_ID`, `JOURNAL_STREAM` and `SYSTEMD_EXEC_PID` are inherited from the systemd unit
that starts `bwrap`.

| Variable             | Value                                                                                                 |
| -------------------- | ----------------------------------------------------------------------------------------------------- |
| `HOME`               | `/sessions/<session>`                                                                                 |
| `PWD`                | `/sessions/<session>`, the same directory as `HOME`                                                   |
| `USER`               | `<session>`                                                                                           |
| `LOGNAME`            | `<session>`                                                                                           |
| `TMPDIR`             | `/sessions/<session>/tmp`                                                                             |
| `CLAUDE_TMPDIR`      | `/sessions/<session>/tmp`                                                                             |
| `CLAUDE_CODE_TMPDIR` | `/sessions/<session>/tmp`                                                                             |
| `TZ`                 | The host machine's IANA zone, for example `America/New_York`. The image zone is `Etc/UTC`             |
| `LANG`               | `C.UTF-8`                                                                                             |
| `PATH`               | `/usr/local/lib/node_modules_global/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin` |
| `NODE_PATH`          | `/usr/local/lib/node_modules_global/lib/node_modules`                                                 |
| `SHELL`              | `/bin/sh`. A `Bash` call runs bash all the same                                                       |
| `SHLVL`              | `0`                                                                                                   |
| `INVOCATION_ID`      | 32 hex digits, the systemd unit invocation id                                                         |
| `JOURNAL_STREAM`     | `<device>:<inode>` of the systemd journal stream                                                      |
| `SYSTEMD_EXEC_PID`   | The PID systemd started the unit with                                                                 |

Any other variable is empty, including `CLAUDE_PLUGIN_ROOT`, `CLAUDE_SKILL_DIR`,
`CLAUDE_PROJECT_DIR`, `CLAUDE_SESSION_ID`, every `ANTHROPIC_*`, every API key, `HTTP_PROXY`,
`SSL_CERT_FILE`, `PYTHONPATH` and `DISPLAY`. No variable names the plugin directory, the skill
directory or the user's mounted folders. No credential reaches the shell.
`"$CLAUDE_PLUGIN_ROOT/scripts/x.sh"` becomes `/scripts/x.sh` and fails.

A Docker run gives every `Bash` call this set of names and no other. `docker.session_env` in
`cowork_evals.yaml` holds the set, and its default is this table.

A skill that needs the session root, the user or the user's time zone reads `HOME`, `USER` or
`TZ`. `/etc/localtime` and `/etc/timezone` give `Etc/UTC`, not the user's zone.

A skill names a script it ships by a path relative to the skill directory. The model prefixes
the announced base directory. The shell never resolves it.

```sh
python3 scripts/build_pipeline.py --out deck.pptx
```

An agent is not a skill and gets no base directory. An agent that runs a bundled script takes
the path as an argument from its caller.

## Session lifetime

The VM stops on application quit, not per session, and its session data image persists.
Session directories from earlier sessions therefore remain present inside a running VM, and
`ls /sessions` lists every one of them. Sessions are separate users and separate directories
on a reused VM.

An eval case cannot assume a clean guest filesystem outside its own session directory.

## What is on the image

### Core runtime

| Component    | Version                                                                               |
| ------------ | ------------------------------------------------------------------------------------- |
| OS           | Ubuntu 22.04.5 LTS (jammy)                                                            |
| Architecture | aarch64 (ARM64). On an x86_64 development machine package builds and behaviour differ |
| Python       | 3.10.12 (`/usr/bin/python3`, also `/usr/bin/python3.10` and `/usr/bin/python`)        |
| pip          | 25.3                                                                                  |
| uv           | 0.12.3                                                                                |
| Node.js      | v22.23.2 (`node`, `npm`, `npx`)                                                       |
| npm          | 10.9.8                                                                                |
| npm globals  | corepack 0.34.6 and npm 10.9.8 under `/usr/lib/node_modules`, and the tree below      |
| Java         | OpenJDK 11.0.32 (Ubuntu build)                                                        |
| Git          | 2.34.1                                                                                |
| Build        | `gcc`, `make`, and the rest of the build-essential toolchain                          |

### Node

A second global npm tree is at `/usr/local/lib/node_modules_global`. Its `bin/` is first on
`PATH` and its `lib/node_modules` is `NODE_PATH`, so `require()` resolves these packages from
any directory. An ES module `import` of one fails, because ES module resolution does not read
`NODE_PATH`. Load it with `require()`, or with `createRequire(import.meta.url)` from
`node:module`. `tsx` runs a `.ts` file with no build step.

| Package                         | Version | Command on `PATH`                                                                                |
| ------------------------------- | ------- | ------------------------------------------------------------------------------------------------ |
| `@anthropic-ai/sandbox-runtime` | 0.0.76  | `srt`                                                                                            |
| `docx`                          | 9.7.1   | none                                                                                             |
| `graphviz`                      | 0.0.9   | none                                                                                             |
| `markdown-toc`                  | 1.2.0   | `markdown-toc`                                                                                   |
| `marked`                        | 18.0.12 | `marked`                                                                                         |
| `pdf-lib`                       | 1.17.1  | none                                                                                             |
| `pdfjs-dist`                    | 6.3.289 | none                                                                                             |
| `pptxgenjs`                     | 4.0.1   | none                                                                                             |
| `sharp`                         | 0.35.4  | none                                                                                             |
| `ts-node`                       | 10.9.2  | `ts-node`, `ts-node-cwd`, `ts-node-esm`, `ts-node-script`, `ts-node-transpile-only`, `ts-script` |
| `tsx`                           | 4.23.13 | `tsx`                                                                                            |
| `typescript`                    | 7.0.2   | `tsc`                                                                                            |

No other npm package is installed. A skill that needs one bundles it as a file.

### Document and office tooling

| Component                        | Version                                                                                           |
| -------------------------------- | ------------------------------------------------------------------------------------------------- |
| LibreOffice (`soffice`)          | 26.2.5.2                                                                                          |
| unoserver (`unoserver`, `unoconvert`) | 3.7, pairs with the LibreOffice UNO API for headless conversion                              |
| pandoc                           | 2.9.2.1                                                                                           |
| poppler-utils (`pdftoppm`, `pdftotext`, `pdfinfo`) | 22.02.0                                                                         |
| ghostscript (`gs`)               | 9.55.0                                                                                            |
| qpdf                             | 10.6.3                                                                                            |
| tesseract-ocr (`tesseract`)      | 4.1.1 (leptonica 1.82.0), English                                                                 |
| TeX Live (`pdflatex`, `xelatex`) | 2021, pdfTeX 3.141592653: latex-base, latex-recommended, fonts-recommended, xetex. `latexmk` 4.76 |
| Graphviz (`dot`)                 | package 2.42.2, and `dot -V` reports 2.43.0                                                       |
| Xvfb (`xvfb-run`)                | 21.1.4                                                                                            |

Not present: `wkhtmltopdf`, `weasyprint`, `exiftool`, `docker`, the `sqlite3` CLI, `magick`,
`mutool`, `inkscape`, `rsvg-convert`, `chromium`, `google-chrome` or any other browser, `gh`,
`yq`, `aws`, `gcloud`, `az`. The Python `sqlite3` module is available.

### Image and media tooling

| Component                            | Version              |
| ------------------------------------ | -------------------- |
| ImageMagick (`convert`, `identify`)  | 6.9.11-60 Q16        |
| ffmpeg (`ffmpeg`, `ffprobe`)         | 4.4.2 (Ubuntu build) |

ImageMagick is 6, not 7. The command is `convert`, there is no `magick`, and argument
semantics differ between the two.

### Fonts

394 font faces, 118 families, the standard Ubuntu font stack: DejaVu, Liberation, Carlito,
Caladea, Latin Modern, Bitstream Charter, C059, Century Schoolbook L, Courier, D050000L,
Dingbats, Droid Sans Fallback, FontAwesome, Noto fallbacks, URW base 35 clones, TeX Gyre.
Full list: `fc-list : family | sort -u`.

No Microsoft font is installed. LibreOffice substitutes Liberation, Carlito and Caladea, so a
skill that needs pixel-exact Office rendering does not get it.

### Other commands

`git`, `curl` 7.81.0, `wget` 1.21.2, `jq` 1.6, `ssh`, `rg` 13.0.0, `zip` 3.0, `unzip` 6.00,
`rsync` 3.2.7, `bc` 1.07.1, `file` 5.41, `xmllint`, `nc`, `lsof`, `bwrap` (bubblewrap 0.6.1),
`socat` 1.7.4.1, `sudo`, and the standard coreutils.
