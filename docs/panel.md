# The panel

## Summary

`cowork_evals panel <path>` prints one row per case under the path: its latest outcome on each
backend, its age, and whether the case files changed since. `run` appends one record per case
to a history tree that outlives the run directory, and the panel joins that history to the case
tree. The panel reaches no backend, spends nothing, and writes nothing under the history root.
Use it to find a case that never ran on a backend.

```bash
cowork_evals panel <plugin>                  # every case, and its latest result
cowork_evals panel <plugin> --markdown p.md  # the same rows, as a Markdown table
cowork_evals panel <plugin> --json p.json    # the same rows, as JSON
cowork_evals panel <plugin> --removed        # add rows for history whose case is gone
```

The path resolves as it does for `run`. There is no `--tag`, no `--case` and no backend flag.
The options are [cli.md](cli.md).

| Condition                                 | Exit                            |
| ----------------------------------------- | ------------------------------- |
| rows printed                              | 0                               |
| a history line that does not parse        | 0, and the line named on stderr |
| a path selecting no case                  | 2                               |
| a path with no plugin root at or above it | 2                               |

No exit code means a red panel. `run` decides pass and fail.

## The columns

The definitions come from the case tree at render time, never from a record.

| Column        | Is                                                                     |
| ------------- | ---------------------------------------------------------------------- |
| `plugin`      | the manifest name                                                      |
| `skill`       | the skill directory, empty for a case outside one                      |
| `case`        | the case name                                                          |
| `description` | the case's own, empty when it writes none. Cut to 40 characters in the terminal table only |
| `docker`      | that backend's latest outcome, and its age in days                     |
| `cowork`      | the same for CoWork                                                    |
| `score`       | the latest record's score                                              |
| `duration`    | how long that run took                                                 |
| `flake`       | how often that backend's records of this case passed, and how many there are. A declared record is not counted |
| `stale`       | whether the case files changed since the record                        |
| `artefacts`   | where that result's run directory is, relative to the working directory when it is under it, or `gone` when it was pruned |

`score`, `duration`, `flake`, `stale` and `artefacts` come from the latest record of either
backend.

A backend with no record reads `never run`. The `cowork` column of a case tagged `no-cowork`
reads `declared`, whether or not it was ever submitted. The tag is
[eval_format.md](eval_format.md).

`stale` compares a digest over `prompt.md`, `case.yaml` when present, each `graders/*.md` and
each `checks/*.py`. It hashes each file's name and bytes, so a whitespace edit or a renamed
grader makes the row stale. Other files in the case directory do not. Both digests are of the
tree on this host, on both backends. A case directory that holds none of those files has no
digest, and its row is never stale.

## The renders

| Render            | Is                                                                  |
| ----------------- | ------------------------------------------------------------------- |
| default           | the text table. The only render that cuts a description             |
| `--markdown FILE` | the same columns as a Markdown table, every description whole       |
| `--json FILE`     | the same rows as JSON, one entry each. A number is a number, and an absent value is absent |

`--markdown` and `--json` may be given together.

`--removed` adds a row for every history file of a selected plugin whose case is no longer in
the tree. The row carries `removed` in place of a description and is built from the record. A
case still in the tree but not selected by the path is not removed.

## The records

`run` appends one record per case, once, after the verdict. A dry run and a refused run append
nothing. A failed append prints `panel: <reason>` on stderr and does not change the exit code.

```
logs/evals/history/<plugin>/<skill>/<case>.jsonl
```

| The case sits                   | Its file                              |
| ------------------------------- | ------------------------------------- |
| under one skill directory       | `<plugin>/<skill>/<case>.jsonl`       |
| directly under `evals/`         | `<plugin>/<case>.jsonl`               |
| deeper than one skill directory | `<plugin>/<skill>/<...>/<case>.jsonl` |

Each path component is slugged as a run directory's name is. `panel.root` sets the root,
default `logs/evals/history` under the working directory. `--out` does not move it. Pruning run
directories does not touch it. Two plugins whose manifests carry the same `name` share one
history directory.

One JSON object per line. An optional field is absent, never null. A line of another
`schemaVersion` is reported and not read. A line that does not parse is reported and skipped.
The newest record for a backend is the last one for it in the file.

| Field                           | Is                                                          |
| ------------------------------- | ----------------------------------------------------------- |
| `schemaVersion`                 | `1`                                                         |
| `invocation`                    | the run directory's name                                    |
| `startedAt`                     | the result document's stamp                                 |
| `claudeVersion`                 | the `claude` that produced it                               |
| `backend`                       | `docker` or `cowork`                                        |
| `image`                         | the image tag, on `--docker`                                |
| `coworkEvals`                   | the package version that recorded it                        |
| `plugin`, `pluginVersion`       | the manifest name and version, not the run directory's name |
| `skill`                         | the first directory under `evals/`, absent outside a skill  |
| `case`, `dir`                   | the case name, and its directory relative to the plugin root |
| `caseDigest`                    | the digest `stale` compares, absent when the case has none  |
| `outcome`                       | `pass`, `fail` or `declared`, as [running_evals.md](running_evals.md) defines them |
| `score`, `passRate`             | the case's aggregates                                       |
| `delta`                         | the case's delta, on a two-arm run                          |
| `runs`                          | how many times the case ran                                 |
| `durationSeconds`               | summed over the runs                                        |
| `costUsd`                       | judge spend over the runs, the only spend the host can see  |
| `failedGraders`                 | each scored grader that did not pass, named once            |
| `error`                         | the first run error                                         |
| `deniedTools`, `unofferedTools` | the union over the runs, when traces were kept              |
| `tracePath`                     | the first failing run's trace, else the first run's         |

A record repeats the plugin, skill and case its path says, so one line reads alone.
`invocation` and `tracePath` lead back to the run directory while it exists.

## Removing history

`prune --history --older-than DAYS` drops records older than `DAYS`, then deletes files left
with no record and directories left empty. It reads `panel.root` and ignores `--out`. `DAYS` is
an exact moment `DAYS` before now, as for run directories. The age is the record's own stamp,
never the file's modification time. A record with no stamp, and a line that does not parse, are
kept.

Nothing is deleted automatically. `prune` takes no path and does not remove the history of a
case that left the tree. To retire one case's history, delete its one file. `panel --removed`
lists the files whose case has left the tree.
