#!/bin/bash
# The link-validity check: no nav link of a document may run through what the game's physics world blocks (boxes, solid props, the world's hulls).
# Python, no engine: --cut-links-check over every document in maps/; tools/link_check.gd in game-zombie-zone asks the real physics space.
#   tools/link_check.sh [id ...]    exits 1 and names the documents that still have blocked links
HERE="$(cd "$(dirname "$0")" && pwd)"
ids=("$@"); [ $# -gt 0 ] || mapfile -t ids < <(cd "$HERE/../maps" && ls *.json | sed 's/\.json$//')
fail=0
for id in "${ids[@]}"; do
    out="$(python3 -I "$HERE/import_bsp.py" --cut-links-check "$HERE/bsp/$id.json" "$HERE/../maps/$id.json" 2>&1)" || { fail=1; echo "$out" | tail -1; }
done
[ $fail = 0 ] && echo "link_check: no blocked links in ${#ids[@]} documents"
exit $fail
