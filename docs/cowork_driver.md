# CoWork driver

## Summary

The driver makes the CoWork desktop application run one prompt and hands back what the
session produced. CoWork has no scriptable entry point. The driver opens a `claude://` deep
link, presses Return with a synthetic keystroke, waits for the session to finish, and reads
the files the session wrote on the host. One prompt in, one session document out.
`cowork_evals ask` is one call of it, and `run --cowork` calls it once per submission. See
[ask.md](ask.md).

This file holds what a caller acts on: the sequence, what the driver refuses, the `cowork:`
keys, the rate ceiling and its two logs, the session document and the failure codes. The
measured application facts it depends on are [cowork_desktop.md](cowork_desktop.md).

Attachments and plugin staging are out of scope. The driver sends no `file` or `folder`
parameter, and nothing on the host writes into the VM.

## The sequence

Each step names the code it raises on failure.

| #  | Step                | Does                                                                       | Fails as |
| -- | ------------------- | ---------------------------------------------------------------------------- | -------- |
| 1  | Refuse              | Check the configuration, the rate ceiling and the prompt cap               | 2        |
| 2  | Record the baseline | List the session directories that already exist                            |          |
| 2a | Consent             | Ask for the keyboard, unless this process already did                      | 2        |
| 2b | Activate and guard  | Activate CoWork, then check it is frontmost                                 | 3, 9     |
| 2c | Clear               | Select all and delete, in the composer                                     | 3        |
| 3  | Fire the deep link  | `open claude://claude.ai/new?q=<prompt>&surface=<surface>`                  | 3        |
| 4  | Settle              | Sleep `settle_seconds` while the window navigates and focuses the composer |          |
| 4a | Guard               | Check CoWork is still frontmost                                            | 9        |
| 5  | Submit              | Send the synthetic Return through `osascript`                              | 3        |
| 6  | Discover            | Poll for one session directory that is not in the baseline                 | 4, 5     |
| 7  | Attribute           | Compare the prompt the application recorded with the submitted one         | 6        |
| 8  | Wait                | Block until the session completes                                          | 7        |
| 9  | Collect             | Build the session document from the session directory                      | 8        |

The session is complete when `audit.jsonl` records the `completed` state. If that never
appears, the session is complete when no file under the session directory has changed for
`idle_seconds` after the run started. A run has started at a `started` lifecycle state or a
first assistant turn. The fallback logs a warning when it fires, and it can fire during a
long pause in a run. Raise `idle_seconds` if it does. It applies only to a run in which no box
was answered or the last one was denied: a denied box can end the turn with no `completed`,
while after an allow or an answered question Claude can think longer than the window before it
writes, so such a run ends at `completed` or at `run_timeout`.

## Questions and approval boxes

A question (`AskUserQuestion`) or an approval box writes a `permission_request` record to
`audit.jsonl`, and its answer a `permission_response` ([cowork_desktop.md](cowork_desktop.md)).
While one stands, quiescence does not count.

| Request      | What the driver does                                                                   |
| ------------ | -------------------------------------------------------------------------------------- |
| Question     | Leaves it `waiting_seconds` for a person to answer, then presses its first option      |
| Approval box | Presses the first answer from `interactions.yaml` that matches it and is not a spent allow, after 2 seconds. With none, leaves it `waiting_seconds` for a person, then stops the run as waiting |

On macOS a question is answered through the Accessibility API, one step per call, repeated every
second while the question stands (up to two steps per question plus two). A step chooses the
first option of the card's current question if none is chosen, and otherwise presses Submit or
Next question. Choosing the option is enough for a single question and moves a card with several
on to the next; a multi-choice question needs its Submit. The digit shortcut stopped working in
the Cowork update of 10 Nov 2026 and now types into the card's "Something else" text field.
On macOS an approval box, the folder box included, is answered by pressing its own button
through the Accessibility API, by label
(`Allow once` or `Allow`, `Deny`), so the keyboard focus and the frontmost application do not
matter. The press is repeated every 3 seconds while the box stands, four times at most: an
AXPress that succeeds has been measured to leave the box open. On Windows a question takes `1`
(not measured since the update, and the card's text field may take it now) and a multi-choice
question is sent with Ctrl+Enter; a tool box is allowed once with Ctrl+Enter
and denied with Escape; the folder box, which takes no key, is denied with Escape and allowed by
invoking its Allow button through UI Automation (Windows PowerShell). That search takes only a
button whose parent or grandparent also holds a Deny button, so a chat or a banner called
"Allow" is never pressed. On Windows a press that was sent is not repeated, since a second one
could land on the next box; only "no button yet" is, as above. Every press is logged: what, for
which request, and whether it was sent. A run that stopped as waiting names the tool in the session
document's `waiting`, and is not code 8 when it has no assistant text. Nor is a run whose turn
ended right after a deny: a denied folder box ends the turn with no reply. That means the
last answer was a deny and Claude then did no more than retry the denied call: a new box, text,
or a call to another tool after it is a run that went on.

## What it refuses

| Refusal                                                          | Code |
| ---------------------------------------------------------------- | ---- |
| `cowork.profile` unset, or its sessions root unreadable          | 2    |
| The rate ceiling already reached                                 | 2    |
| A prompt longer than the 14336 character deep link cap           | 2    |
| Cancel on the keyboard modal                                     | 2    |
| CoWork not frontmost when a keystroke is due. It does not retry  | 9    |
| More than one new session directory. It does not guess           | 5    |
| A session whose recorded prompt differs from the submitted one   | 6    |

A refusal with code 2 has fired nothing, leaves no run log line, and does not count against
the ceiling.

The driver never writes or deletes anything under the profile. Every submission leaves a
permanent session in the signed-in account's CoWork history. Remove one by hand, in the
application. The run log is the list to read when doing so.

## Live account exposure

The driver drives a real signed-in account through the organization inference gateway, with
every MCP server that account has. A prompt can send mail or change data for real.

## Configuration

The `cowork:` section of `cowork_evals.yaml`, in the working directory. The driver reads no
environment variable.

```yaml
cowork:
  profile: <the Application Support profile directory name>   # required
  surface: cowork
  settle_seconds: 3
  session_timeout: 120
  idle_seconds: 20
  waiting_seconds: 60
  run_timeout: 1800
  max_runs: 50
  consent: dialog
  consent_timeout: 10
  run_log: ~/.cowork-runs.jsonl
  log_dir: logs
```

| Key               | Default                | Is                                                                    |
| ----------------- | ---------------------- | ----------------------------------------------------------------------- |
| `profile`         | none, required         | The profile directory. A bare name resolves under `~/Library/Application Support/`. An absolute path is taken as it stands |
| `surface`         | `cowork`               | Deep link `surface` parameter. `""` omits it                          |
| `settle_seconds`  | 3                      | Wait after the deep link, before the Return                           |
| `session_timeout` | 120                    | Wait for a session directory to appear, and for its audit record      |
| `idle_seconds`    | 20                     | Quiescence window of the fallback completion signal                   |
| `waiting_seconds` | 60                     | How long a question or an unanswered approval box is left for a person |
| `run_timeout`     | 1800                   | Wait for the run to finish. `ask --timeout-seconds` replaces it       |
| `max_runs`        | 50                     | Submissions allowed in the trailing 24 hours                          |
| `consent`         | `dialog`               | `dialog` shows the modal once per process. `none` fires without asking |
| `consent_timeout` | 10                     | Seconds before the modal gives up and proceeds                        |
| `run_log`         | `~/.cowork-runs.jsonl` | The run log, outside the profile                                      |
| `log_dir`         | `logs`                 | Diagnostic logs. `null` turns them off                                |

An unset or unreadable `profile` is refused at step 1, as code 2, before anything is fired.
Find the active profile with `lsof` on the running application. See
[cowork_desktop.md](cowork_desktop.md).

## Taking the keyboard

The driver types into whatever is frontmost. macOS gives an unprivileged process no lock on
the keyboard or the mouse.

The developer approves once per invocation, however many submissions it makes. The modal
forces itself in front of every window and has no default button, so a Return typed into
another window does not dismiss it. Cancel is code 2 and fires nothing. With no answer, the
modal proceeds after `consent_timeout` seconds, and its message states that timeout.
`consent: none` fires without asking. It is the route for an unattended run, and the only
route that fires without a warning. A step that fires nothing never asks, so `ask --session`
and a dry run never show the modal. The modal itself needs no Accessibility grant.

Before each keystroke the driver checks that CoWork is the frontmost application, by the
process name in [cowork_desktop.md](cowork_desktop.md). Any other name is code 9, and nothing
is typed. An `osascript` failure during the check is code 3.

Before the deep link the driver selects all and deletes in the composer. It does not read or
report what it cleared.

A person who types after the deep link changes the prompt the application records. The
driver compares that record with the submitted prompt and refuses a mismatch as code 6, so an
altered prompt is never collected. Keep hands off the keyboard while a submission runs.

## The rate ceiling, and the two logs

The ceiling counts submissions in the trailing 24 hours, read from the run log. Every
submission is counted, successful or not, so a failing loop is throttled like a working one.
The window is fixed at 24 hours. Only `max_runs` changes the count, and nothing skips it.
Raise `max_runs` deliberately when a sweep needs more. `ask --dry-run` prints the count
without spending.

| File                                           | Holds                                                                                       | Lifetime             |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------- | -------------------- |
| `<log_dir>/<yyyymmdd-hhmmss>-cowork_evals.log` | What one call did: the link fired, the session found, the signal seen, the failure raised   | One per firing call  |
| `run_log`, `~/.cowork-runs.jsonl`              | One JSON line per submission: timestamp, prompt hash, session directory, and the outcome, `submitted` or `failed:<code>` | Append only, forever |

The prompt hash joins a run log line to the session document's `prompt_sha256`. A killed
process can leave a fired submission with no run log line.

## The session document

One JSON object, and it holds exactly these keys.

| Key                    | Is                                                                     |
| ---------------------- | ------------------------------------------------------------------------ |
| `prompt`               | The submitted prompt                                                   |
| `prompt_sha256`        | Its digest, the join key to the run log                                |
| `session_dir`          | Absolute path of the attributed session                                |
| `submitted_at`         | Timestamp of the `user` audit record, when the prompt reached the application |
| `collected_at`         | Timestamp of the collection                                            |
| `transcript`           | Path of the main transcript, or `null` when there is none              |
| `other_transcripts`    | Paths of the remaining top level transcripts                           |
| `subagent_transcripts` | Paths under `subagents/`                                               |
| `audit_prompt`         | The prompt as recorded in the first `user` record of `audit.jsonl`     |
| `lifecycle`            | Every `command_lifecycle` state name, in order. `completed` is the terminal one |
| `turns`                | `role` and `text` per turn, from `user` and `assistant` records. A thinking block is not turn text |
| `tool_calls`           | One object per call, below                                             |
| `tool_names`           | Tool names in call order, for a grader that only asks what fired       |
| `final_text`           | The last assistant text turn                                           |
| `outputs`              | Files under `outputs/`, relative to the session directory              |
| `log_file`             | The diagnostic log of the call that produced it, or `null`             |
| `waiting`              | The tool of the request the run stopped on unanswered, or `null`       |

Each entry of `tool_calls`:

| Key          | Is                                                          |
| ------------ | ----------------------------------------------------------- |
| `id`         | The tool use id                                             |
| `name`       | The tool name, for example `mcp__workspace__bash`           |
| `input`      | The call's input, as the model sent it                      |
| `mcp_server` | The MCP server the call is attributed to, or `null`         |
| `mcp_tool`   | The MCP tool the call is attributed to, or `null`           |
| `timestamp`  | When the call was recorded                                  |
| `result`     | The paired tool result content, or `null` when none arrived |

A result is paired to its call by id. Calls made inside a subagent are not in `tool_calls`;
their transcripts are in `subagent_transcripts`. The cost the application records is not in the
document. Read it from the `result` record in `audit.jsonl`, which
[cowork_desktop.md](cowork_desktop.md) describes.

## Failure taxonomy

Every failure carries one of these codes, and no two are collapsed. They are not exit codes.
[ask.md](ask.md) and the `--cowork` backend map them onto the command's exit codes.

| Code | Meaning                                                                    | Do                                                                                   |
| ---- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| 2    | Refused before submission: configuration, rate ceiling, or prompt too long | Read the message. Set `cowork.profile`, shorten the prompt, raise `max_runs` on purpose, or answer the modal |
| 3    | Submission failed: `open` or `osascript` returned non-zero                 | `osascript` error 1002 on standard error is a missing Accessibility grant. See [cowork_desktop.md](cowork_desktop.md) |
| 4    | No session directory appeared within the timeout                           | Check CoWork is signed in and the deep link permission rule is granted. A tenant that sets `disableDeepLinkRegistration` fails here, closed. A cold VM boot takes about 45 seconds, so raise `session_timeout` on a slow machine |
| 5    | More than one session directory appeared, cannot attribute                 | Another session started during the run. Submit again with nothing else using CoWork  |
| 6    | A session appeared but its audit prompt does not match                     | Something typed into the composer during the submission. Keep off the keyboard and submit again |
| 7    | The run did not complete within the timeout                                | The session keeps running in the VM, and the error carries its directory. Collect what it produced so far with `ask --session <dir>`, or raise the timeout |
| 8    | The run completed with no assistant output                                 | Read the transcript in the session directory. The prompt produced no answer          |
| 9    | CoWork was not frontmost when a keystroke was due                          | Nothing was typed. Leave CoWork in front and submit again                            |

A run that completed and was collected raises nothing.
