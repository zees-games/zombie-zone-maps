#!/bin/bash
# Refresh only the `lights` of the committed documents from the source maps (import_bsp's --lights-only): no box, nav or world change.
#   tools/relight.sh [--water] [--check] [id ...]    (--check writes nothing and fails when a document would change; all of ship.tsv without ids)
#   --water refreshes only `water` instead (import_bsp's --water-only).
HERE="$(cd "$(dirname "$0")" && pwd)"
STORE="${DOTBSP_STORE:-$HOME/mapsrc/store}"
DOCS="${ZZ_DOCS:-$HERE/../maps}"
what=lights; rm -f "${TMPDIR:-/tmp}/relight.rc"
[ "$1" = "--water" ] && { what=water; shift; }
mode=--$what-only
[ "$1" = "--check" ] && { mode=--$what-only-check; shift; }
grep -v '^#' "$HERE/convert/ship.tsv" | while IFS=$'\t' read -r id key; do
    [ $# -gt 0 ] && [[ " $* " != *" $id "* ]] && continue
    grep -q "^$key " "$HERE/convert/excluded.txt" && continue
    h="$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$STORE/index.json" "$key")"
    python3 -I "$HERE/import_bsp.py" $mode "$HERE/bsp/$id.json" "$STORE/$h/source.bsp" "$DOCS/$id.json" 2>&1 | tail -n 1
    [ "${PIPESTATUS[0]}" -ne 0 ] && echo 1 > "${TMPDIR:-/tmp}/relight.rc"
done
[ -f "${TMPDIR:-/tmp}/relight.rc" ] && { rm -f "${TMPDIR:-/tmp}/relight.rc"; exit 1; }
exit 0
