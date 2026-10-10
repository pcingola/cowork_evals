"""A check file that raises while it is being imported. It is named `x.y`, as check `y` in
`x.py` is."""

raise RuntimeError("this file does not import")
