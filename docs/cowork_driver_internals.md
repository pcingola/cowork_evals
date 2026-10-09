# CoWork driver internals

## Summary

How the driver is built: its Python API, the design of each step of the sequence, how it
reads a session, and where the rate ceiling and the logs are implemented. What the driver
does, from the side of someone who runs it, is [cowork_driver.md](cowork_driver.md): the
sequence, the refusals, the `cowork:` keys, the session document and the failure taxonomy.
This file cites that one and never restates it. The measured application internals the
driver couples to are [cowork_desktop.md](cowork_desktop.md).

The split from the layer above is one question: does the statement need to know what a case
is? Yes, and it is in [cowork_backend.md](cowork_backend.md). No, and it is in
[cowork_driver.md](cowork_driver.md) or here. Between those two, a fact a caller acts on is
in [cowork_driver.md](cowork_driver.md), and how the code produces it is here.

What of this is built is the status table in [status.md](status.md).

## The API

The driver is a library and nothing else. It has no entry point, no console script and no
`__main__`. It runs on the host and never under the CoWork mirror: it drives a desktop
application and reads host paths, and nothing it does belongs to a session. It is therefore
not bound to 3.10; see [library.md](library.md).

Two modules, PyYAML and pydantic.

| Module                | Holds                                                                       |
| --------------------- | --------------------------------------------------------------------------- |
| `cowork_evals.config` | `cowork_evals.yaml`, the frozen `Config` and its sections, and `CoWorkError` |
| `cowork_evals.cowork` | `CoWork`, the driver, and the records it reads and returns                  |

`Config`, its four sections, `CoWork` and `CoWorkError` are the names re-exported from
`cowork_evals`, and they are what a consumer imports rather than reaching through the
command. The backend's modules are imported by their own names, and every module this
package ships is the table in [library.md](library.md). A `CoWork` takes the `cowork:`
section, `CoWorkSection`, and never the whole file. A caller passes a configuration once and
calls methods on the object that holds it.

Three module functions stand beside the class. Each is a function because what it reads is
not one driver's configuration.

| Function                 | Reads                  | Is there because                                                                                                        |
| ------------------------ | ---------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `final_text(transcript)` | one session transcript | `traces.py` writes that text beside the transcript it copies, and this format is parsed here and must not be parsed twice |
| `frontmost()`            | the desktop            | the guard compares its result, and it takes no configuration                                                             |
| `consent(section)`       | the developer, once    | the answer is one operator's for one process, and a frozen section cannot carry it                                       |

```python
from cowork_evals import Config, CoWork, CoWorkError

cw = CoWork()  # reads cowork_evals.yaml
cw = CoWork(profile="...", max_runs=10)  # the same, with overrides
cw = CoWork(Config.load().cowork)  # from a configuration already loaded
cw = CoWork.from_file("other.yaml")

doc = cw.run("Reply with exactly: PONG")  # submit, wait, collect
```

| Method                              | Does                                                   | Returns                                  | Fires |
| ----------------------------------- | ------------------------------------------------------ | ---------------------------------------- | ----- |
| `from_file(path, **overrides)`      | Builds from a named configuration file                 | A `CoWork`                               | no    |
| `run(prompt)`                       | `submit`, then `wait`, then `collect`                  | A `SessionDocument`                      | yes   |
| `submit(prompt)`                    | Steps 1 to 7 of the sequence                           | The attributed session directory         | yes   |
| `wait(session_dir)`                 | Step 8, the completion signal                          | The same directory                       | no    |
| `collect(session_dir, prompt=None)` | Step 9, reading one session already on disk            | A `SessionDocument`                      | no    |
| `sessions(root=None)`               | Every session directory under a root                   | Paths, sorted                            | no    |
| `history(run_log=None)`             | The run log                                            | One `RunLogEntry` per line, oldest first | no    |
| `deep_link(prompt)`                 | Builds the URL, percent-encoding the prompt            | The URL                                  | no    |
| `recent()`                          | Submissions in the trailing 24 hours, from the run log | A count                                  | no    |

Rules that hold for all of them:

- Construction resolves the configuration and validates nothing else. It reads no session,
  starts no process and raises only on a malformed configuration file. A missing `profile`
  is refused by the first method that needs one, so `CoWork().collect(archived_dir)` works
  on a machine that has no CoWork.
- A failure raises `CoWorkError`, which carries the taxonomy code as `.code` and the session
  directory as `.session_dir` when one is known. No method returns an error code, calls
  `sys.exit`, or prints. The codes are not exit codes: the library exits nothing, and a
  command line over it maps them onto its own.
- `config` is a frozen dataclass and is not reassigned. A different configuration is a
  different `CoWork`.
- `sessions` and `history` default to the configured paths and take an argument to read
  somewhere else, which is what the tests use.
- `recent()` owns the trailing 24-hour window and the timestamp parsing. Step 1 calls it,
  and so does the backend's suite arithmetic, so the window is implemented once.
- There is no test seam. `open` and `osascript` are run directly, no mock, fake, stub or
  patch is used anywhere in this repository, and no parameter exists to inject one. What a
  test cannot reach without the application, the live test reaches by firing one. See
  `tests/README.md`.
- `collect` takes `prompt` when the caller knows what was submitted, which fills `prompt`
  and `prompt_sha256`. Without it those two come from the audit record.
- Every public callable is fully type hinted. `run` and `collect` return a `SessionDocument`,
  a pydantic model serialised with `model_dump_json()`. It carries exactly the keys
  [cowork_driver.md](cowork_driver.md) lists, every path is a string, and a field with no
  value is written as null. `history` returns one `RunLogEntry` per run log line, oldest
  first.

Five methods fire nothing and need no authorization beyond read access to the profile:
`collect`, `sessions`, `history`, `recent` and `deep_link`. `collect` runs over a recorded
session directory, so it is what the tests exercise and what is called again when a stored
run has to be re-parsed.

A calling script pairs `submit` with a later `collect` when it must not hold a process open
for the length of an agentic run. Everything else uses `run`.

## The sequence, step by step

The step table and the code each step raises are in [cowork_driver.md](cowork_driver.md).

Every keystroke goes to the frontmost application, so a step that types runs behind a check
that CoWork is the frontmost application. The check is 2b for the clear and 4a for the
Return. 4a is after the settle, so the gap between the last check and the keystroke is as
small as the sequence allows. Step 5 carries no activation of its own: activating again
after 4a would reopen the gap the check just closed.

The clear is 2c and not a step after the deep link. The deep link is what puts the prompt in
the composer, so clearing after it deletes the prompt.

Step 2a refuses on Cancel, and a refusal has fired nothing, so it leaves no run log line and
does not count against the ceiling. That is the rule step 1 already follows, and code 2 is
the one taxonomy code that carries it.

Step 6 identifies a session by structure and not by name, over the layout in
[cowork_desktop.md](cowork_desktop.md). New sessions are the set difference against the
baseline. More than one means another session was created while this one ran, and the run
cannot be attributed: code 5, not a guess.

Step 7 tolerates a session directory that exists before its `user` audit record is written.
It keeps polling until the record appears or the discovery timeout expires.

## The completion signal

The `completed` `command_lifecycle` audit state is the signal. It is the only terminal state
[cowork_desktop.md](cowork_desktop.md) records, so a failed or cancelled command has an
unknown state name and a fallback is needed.

Quiescence counts only after the run has demonstrably started, which is a `started`
lifecycle state or a first assistant turn in the transcript. Without that condition the
idle window accrues during VM boot and an empty session is reported as a finished run.

The fallback is a heuristic, is labelled as one in the code, and logs a warning when it
fires.

## Loading the configuration

The loading rules are [library.md](library.md), which owns the file. Two are the driver's
own: a file named to `Config.load` or `CoWork.from_file` must exist, so a mistyped path is
never a silent set of defaults, and an override passed to the `CoWork` constructor beats
the file.

`profile` has no default on purpose. A wrong guess drives the wrong account. An absolute path
is how a test and a developer point the driver at a profile elsewhere.

`session_timeout` is the VM boot in [cowork_desktop.md](cowork_desktop.md) with margin.
`settle_seconds` is not measured and is conservative.

## Taking the keyboard

Three mechanisms stand between the driver and a keystroke in a source file, and none of them
replaces the other two.

| Mechanism   | Buys                                     | Cannot                                            |
| ----------- | ---------------------------------------- | ------------------------------------------------- |
| Consent     | The developer's intent, once per process | Stop them typing anyway                           |
| The guard   | That CoWork is frontmost at the check    | Close the gap between the check and the keystroke |
| Attribution | That an altered prompt is never collected | Prevent the alteration                           |

macOS offers no lock on the keyboard or the mouse to an unprivileged process, so there is
none here. The guard narrows a race it cannot close, and attribution stays the backstop: a
keystroke that lands elsewhere is caught as code 6 rather than returned.

### Consent

The answer is module state in `cowork.py`, set by `cowork.consent`, which step 2a calls: a
caller may build many drivers in one invocation, and `CoWorkSection` is frozen besides.

| Caller                          | Calls                                              |
| ------------------------------- | -------------------------------------------------- |
| `run` and `submit`, at step 2a  | `cowork.consent(self._config)` on every submission |
| `ask`, before the driver        | `cowork.consent(config.cowork)` once               |
| `run --cowork`, before the first case   | the same, once for the whole invocation    |
| A library caller                | the same, or sets `consent: none` in the file      |

The driver asks rather than reading what a caller left, so a caller that forgot cannot take
the keyboard with no warning. The command still asks up front, because asking before a suite
starts beats asking at its first submission, and the ask is once per process, so the second
call shows nothing.

`collect`, `sessions`, `history`, `recent` and `deep_link` never ask, because they fire
nothing.

The modal is `osascript` `display dialog`, which needs no Accessibility grant. Only the
keystrokes need one, and the preflight in [cli.md](cli.md) covers that.

| Property              | Is                                                                                             |
| --------------------- | ------------------------------------------------------------------------------------------------ |
| `tell me to activate` | What forces the modal in front of the editor the developer is working in                       |
| No `default button`   | A Return typed into that editor mid-sentence must not dismiss it, so the developer has to click |
| Cancel                | A non-zero exit from `osascript`, which becomes code 2. Nothing has fired                      |
| `giving up after`     | Proceeds. An unattended run is the case the key exists for                                     |
| The message           | States the timeout, because `display dialog` renders no countdown                              |

`consent: none` is a configuration value and not a test seam: a test sets it in a
configuration file exactly as a consumer would, and no parameter exists to inject an answer.

### The guard

`System Events` reports the frontmost process by name, and the name CoWork carries is in
[cowork_desktop.md](cowork_desktop.md). There is no retry after a failed check. Retrying
blind is how a keystroke reaches an editor.

Code 9 is not code 3. A grading layer has to tell "the driver refused to type into something
that was not CoWork" apart from "osascript is broken", and code 3 already carries the second.

### The clear

It runs behind the guard, so the worst field it can reach is a CoWork field that is not the
composer, and the contents of a CoWork composer are a draft. It does not read what it cleared
and does not report it. Reading the composer means reading the screen, which
[cowork_desktop.md](cowork_desktop.md) rules out.

The clear is cheap insurance rather than a fix for a measured loss. What the application
does with a deep link fired into a composer that already holds text, and what a human typing
during a submission does to the recorded prompt, are both in
[cowork_desktop.md](cowork_desktop.md).

## Reading a session

Rules the reader follows. The record shapes they act on are in
[cowork_desktop.md](cowork_desktop.md).

- The run is the newest top level transcript by modification time under
  `.claude/projects/session/`. Files under `subagents/` are recorded by path and are never
  merged into it.
- An unparsable line, or one that does not validate as its record, is skipped. Both
  `audit.jsonl` and the transcript are appended while the run is live, so the last line can
  be partial. The run log is read by the same rule.
- Both forms `message.content` takes are read for turn text.
- A `tool_result` is paired to its `tool_use` by id, never by position: results arrive in
  later records, and parallel calls interleave.
- A `tool_result` whose call is absent from this transcript belongs to a subagent and is
  dropped.
- Turns are read from `user` and `assistant` records only. Every other record type is
  ignored, because [cowork_desktop.md](cowork_desktop.md) measures that set as open. A
  thinking block is not read as turn text.
- The prompt, the submission timestamp and the lifecycle states come from the first `user`
  audit record of the directory, because one session directory can hold more than one
  command.
- `final_text` is the last assistant text turn. A run with none raises code 8.
- A session directory with no transcript directory yet is tolerated, and raises code 8 for
  the same reason.

## The rate ceiling and the logs

The driver never deletes anything: deleting from the profile directory is writing into
application-managed state and can corrupt a profile. The mitigation for a filling account
history is a rate ceiling and a record, not deferral. The ceiling counts submissions, because
a runaway loop is what fills an account history.

Before submitting, `run` and `submit` count the run log entries whose timestamp falls in the
trailing 24 hours. `collect` never checks it.

The run log line is written after the sequence returns or raises, so a process killed between
the deep link and that write leaves a fired submission the ceiling never counts. Nothing
inside the library closes that window, because the line cannot be written before the thing it
records.

The default of 50 is a working day of development, and it is a ceiling, not a budget. What a
whole suite costs the ceiling before it starts is [cowork_backend.md](cowork_backend.md).

The run log cannot be per-run, because the ceiling counts the submissions in the trailing 24
hours. It stays in the home directory, because the ceiling protects one CoWork account and an
account is not per-project.

The diagnostic log is written by `run` and `submit` only, through a handler on the
`cowork_evals` logger. Every `CoWorkError` that leaves one of them is logged once, where the
handler is opened, rather than at the step that raised it. The library never configures the
root logger and never adds a handler twice. With `log_dir: null` the logger carries whatever
handler the caller attached. Two calls in the same second would share one name, so the second
gets a counter suffix.

## Coupling list

Re-probe every item after an application update. This is a checklist, not an investigation.
Each item is measured in [cowork_desktop.md](cowork_desktop.md).

The `claude://claude.ai/new` route, the `q`, `surface`, `file` and `folder` parameter names,
the 14336 cap, the `Claude` process name `System Events` reports, the sessions root path, the
three level session directory depth, the `audit.jsonl` filename, the `user` and
`command_lifecycle` record types, the `state` values,
the transcript path under `.claude/projects/session`, the `subagents/*.jsonl` layout, the
`tool_use` `id` and `tool_result` `tool_use_id` fields, the `outputs/` directory, and the
`Write`, `mcp__workspace__bash` and `mcp__workspace__web_fetch` tool names.

Every field a reader of a collected session acts on, by file:

| File            | Fields                                                                        |
| --------------- | ------------------------------------------------------------------------------- |
| `audit.jsonl`   | `type`, `state`, `timestamp`, `message.content`                                |
| The transcript  | `type`, `attributionMcpServer`, `attributionMcpTool`, `timestamp`, `message.role`, `message.content`, and per block `type`, `text`, `id`, `name`, `input`, `tool_use_id`, `content` |
| The directory   | `.claude/projects/session/<uuid>.jsonl`, `<uuid>/subagents/*.jsonl`, `outputs/` |
