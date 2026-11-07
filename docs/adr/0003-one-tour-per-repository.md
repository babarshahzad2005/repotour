# One tour per repository in v1

A tour always covers the whole repository. If `PATH` points at a subdirectory, Repotour finds the repo root and tours the whole repo. In a monorepo, the packages are listed in the overview rather than getting tours of their own. Scoping a tour to a package changes what history, ownership, the dependency graph, and the reading order mean, and that would double the design and test surface for v1. Tours per package or per subdirectory are left for a later version.
