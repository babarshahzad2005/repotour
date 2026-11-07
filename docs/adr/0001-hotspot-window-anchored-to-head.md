# Hotspot window is measured from the HEAD commit's date, not from today

A tour must be byte-identical for the same commit and config. That rule is what makes the GitHub Action's "has the tour changed?" check work and what lets users trust the output. If "last 6 months" were measured from today, the same commit would give a different tour every day. So the hotspot window ends at the HEAD commit's committer date. The consequence: for a repo with no recent commits, "last 6 months" means the six months before its last commit, and the tour says so.
