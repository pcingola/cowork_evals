# Assets

The images the repository's `README.md` shows. This directory does not ship.

| File                     | Shows                                                                      | Used in `README.md`              |
| ------------------------ | -------------------------------------------------------------------------- | -------------------------------- |
| `images/logo.webp`       | The name, and an agent under test in a glass booth                         | The top                          |
| `images/case_flow.webp`  | A case from `prompt.md` through a backend, graders and checks to the exit code | Summary                       |
| `images/backends.webp`   | The CoWork backend taking the keyboard, the container, and the verdict     | What you need                    |
| `images/ablation.webp`   | The same case with and without the plugin, and the delta between them      | Quickstart, after "Then widen it" |
| `images/runtime.webp`    | Tests that pass on a laptop, and an `ImportError` in the 3.10 session      | Quickstart, Tests                |

## Rules

- An image lives here, and only `README.md` shows it. No file under `docs/` carries an image:
  `docs/` ships, an agent reads it in a terminal, and a link from it to this directory dangles
  in an install.
- An image is WebP, at most 1600 pixels wide.
- Text in an image states what is true of this repository: real frontmatter keys, real grader
  types, real commands. An image that contradicts `docs/` is a defect, the same as a sentence.
- An image carries no product logo, no person's name and no identifier. The public repository
  rule in `README.md` applies to pixels.
