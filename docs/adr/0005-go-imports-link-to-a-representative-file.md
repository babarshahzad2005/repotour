# Go imports link to one representative file of the package

A Go import names a package, which is a directory of files, while every other language in the graph imports a single file and the graph's nodes are files. Linking an import to every file of the imported package multiplies edges (on golang/go, around a million), which makes PageRank too slow for the large-repository target; switching Go to package-level nodes would mix directory nodes into a file graph and leave the reading order without files to recommend. So each Go import links to one representative file of the imported package, chosen deterministically: the file named after the directory (`http/http.go`), else `doc.go`, else the file with the most lines (ties by path). The edge's evidence states that the import is of the package, so the tour never claims a file-level import that does not exist.

## Consequences

- PageRank concentrates a package's importance on its representative file, which is also the file a newcomer would open first.
- Other files in a package have no incoming Go edges of their own, so leaf detection asks the adapter which files are imported together with a target (the whole package for Go) and never calls a file in an imported package a leaf.
