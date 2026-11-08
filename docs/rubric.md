# Reading-order rubric

The "Start here" list is Repotour's main promise, so it is checked against a written standard on real repositories before each release.

## The rule

A file in the reading order **passes** when both hold:

1. **It belongs near the start.** It is at least one of:
   - an **entry point** (where execution starts, or the package's public surface),
   - a **core module** (listed under "Core modules" in the same tour), or
   - **directly imported by an entry point**.
2. **Its reason is true.** Every part of the stated reason can be checked against the code and history at the toured commit (the import exists, the importer and change counts are right, the entry point does what it says).

A sample **passes** when at least **4 of its 5** files pass.

## How a review is done

1. Generate the tours with the Sample tours workflow (`benchmarks/samples.py`), which pins each repository to a release commit.
2. For each file in "Start here", check rule 1 against the same tour's Entry points, Core modules, and Dependency graph sections, and spot-check rule 2 in the repository.
3. Record the result per file in `docs/samples/REVIEW.md`, next to the tours.
4. A failing sample blocks the release until the ranking is fixed or the failure is recorded with a reason.
