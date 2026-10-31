#!/usr/bin/env bash
# Prints the add-in's version, worked out from git tags (the only place versions are decided):
#   a commit tagged v1.2.3 (or v1.2.3-beta.1)  ->  1.2.3
#   any other commit                           ->  <last tag>+dev.<commits since it>.<short hash>
#                                                  (0.0.0+dev.<n>.<hash> before the first tag)
# The manifest in the repository only holds a placeholder; the build writes this version into it.
set -euo pipefail
if tag=$(git describe --tags --exact-match --match 'v[0-9]*' 2>/dev/null); then
  version="${tag#v}"
else
  if last=$(git describe --tags --abbrev=0 --match 'v[0-9]*' 2>/dev/null); then
    count=$(git rev-list --count "$last..HEAD")
  else
    last=v0.0.0
    count=$(git rev-list --count HEAD)
  fi
  version="${last#v}+dev.${count}.$(git rev-parse --short=7 HEAD)"
fi
if ! [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$ ]]; then
  echo "Not a valid version: $version (tags must look like v1.2.3 or v1.2.3-beta.1)" >&2
  exit 1
fi
echo "$version"
