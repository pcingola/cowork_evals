# Case history

## Summary

`run` appends one record per case to a history tree, and `panel` renders it. What a consumer
reads, the columns, the record fields, the tree layout and pruning, is [panel.md](panel.md).
This file holds how the store is written and the decisions behind its shape.
`src/cowork_evals/panel.py` is the only code that writes or deletes a path under the history
root, as `logs.py` is over the run tree. What one invocation produced lives in that
invocation's run directory and is deleted with it. What outlives that deletion lives here.

- **`run` writes one record per case, once, after the verdict.** No backend changes, and nothing
  writes a record during a run.
- **`outcome` is the word the verdict reached**, carried across unchanged. The panel records
  what was decided and does not decide again.
- **A case with no record reads `never run`.** It is a value in the column, never an empty cell.

The setting is `panel.root`, in [library.md](library.md)'s ladder.

## The tree

The case is the panel's row, so the path is the lookup key and reading one row is one file
open. Two invocations contend only when both ran the same case. Retiring one case is `rm` of
one file.

The three path shapes in [panel.md](panel.md) stay unique. A case directly under `evals/` cannot
collide with a skill directory: one is a file and the other a directory of the same stem. A case
deeper than one skill directory carries every component, so two cases that share a directory
name under two skills stay apart.

Two plugins whose manifests carry the same `name` share one history directory. A run directory
suffixes the second `-2`. A history path cannot, because it is stable across invocations.

`--out DIR` does not move the root. That option relocates what one invocation produced, and a
record is read after that invocation's directory is gone. `logs.prune` deletes only children of
the log root whose names match the run stamp, so the history directory under that root
survives it.

## The record

The contract is additive-only: a reader ignores a field it does not know, and a line of another
`schemaVersion` is reported and not read. The schema is this module's own, not the result
document's.

A record is self-contained. It repeats the plugin, the skill and the case its path says, so a
row for a case that has left the tree is built from the record alone.

`invocation` and `tracePath` are the two join keys back into the run tree. The panel reports the
artefacts as `gone` when the directory is not there, which is what a pruned run directory
leaves.

## The digest

`caseDigest` covers `prompt.md`, `case.yaml` when present, each `graders/*.md` in path order and
then each `checks/*.py`: every file that decides what the case asks and how it is graded. A
check file counts because an edited assertion would otherwise leave the row green over a result
that asserted something else. It hashes each file's name before its content, so a renamed
grader moves it.

It is computed when the record is written and recomputed when the row is rendered. Both
readings are of the tree on this host. The container backend's result document names
`/work/plugin` as `suite.root`, which is the mount point inside the container, so `run` hands
the record the plugin root it was pointed at and not the one the document carries.

A case directory with no file that defines a case has no digest, and the record carries none.
`sha256` over no bytes is a valid-looking digest that matches no real one, and recording it
would make every later row read `stale` over files nobody edited.

The plugin's git revision is not recorded. It needs a subprocess against a tool that may be
absent, in a tree that may not be a repository, and it moves on every unrelated commit. The
digest answers the same question.

## Appending

`run` appends after the verdict, once, from the result documents the invocation wrote. A
`--dry-run` and every refusal return before the sweep, so neither appends.

Each file is opened for append under an exclusive `flock`, and every line it takes is written in
one call, so a concurrent reader sees whole lines.

An append that fails prints `panel: <reason>` on stderr and leaves the exit code alone.
Recording a result is not deciding one, so an unwritable history root does not turn a passing
run red.

A line that does not parse is reported and skipped. A truncated last line loses one
measurement. Refusing the file would lose every other measurement of that case.

## The render

The definitions come from the case tree at render time, never from a record: a second copy of
what a case is would drift from the case.

The five columns after the backends come from the row's latest record, whichever backend
produced it, because that is the most recent measurement of the case. Of each backend's newest
record, the latest is the one with the newest `startedAt`, and a record with no `startedAt` is
older than any record with one. Each backend's newest
record is the last one for it in the file: appending is the only write, so file order is the
order the records were made in.

The CoWork column of a `no-cowork` case reads `declared` whether or not it was ever submitted,
because the tag is in the tree and is the reason no record will appear there.

`--removed` is decided by the tree and not by the path argument: a case still there and not
selected is not a case that was removed.

## Pruning

The age is the record's own stamp, never the file's modification time. Reading a file moves
that time, and a case nobody looked at is not younger than one somebody did. A record that
cannot be dated is kept, because dropping it would be a deletion on the age of nothing.

`DAYS` is read as `logs.prune` reads it, at one exact moment `DAYS` before now, because it is
one flag over both trees. A floor on whole days would keep a record a day longer than the run
directory it names.

There is no automatic retention. A keep-N or keep-days rule would delete the newest record of a
case that runs twice a year, which is the row the panel most needs. Deleting a record is the
operator's act. `prune` takes no path and cannot know what the tree holds, so it never removes
the history of a case that left the tree.
