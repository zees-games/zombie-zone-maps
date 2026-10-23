#!/bin/bash
# Rebuild the game document (maps/<id>.json) of every row of tools/convert/ship.tsv from its store entry and spec
# (tools/bsp/<id>.json, written by tools/auto_spec.py when nobody tuned one). Run tools/ship_worlds.sh first so the document names its world.
#   tools/ship_docs.sh [id ...]
HERE="$(cd "$(dirname "$0")" && pwd)"
STORE="${DOTBSP_STORE:-$HOME/mapsrc/store}"
grep -v '^#' "$HERE/convert/ship.tsv" | while IFS=$'\t' read -r id key; do
    [ $# -gt 0 ] && [[ " $* " != *" $id "* ]] && continue
    grep -q "^$key " "$HERE/convert/excluded.txt" && continue
    h="$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]])" "$STORE/index.json" "$key")"
    log="${TMPDIR:-/tmp}/doc-$id.log"
    python3 -I "$HERE/import_bsp.py" "$HERE/bsp/$id.json" "$STORE/$h/source.bsp" > "$log" 2>&1
    if grep -q "no ground within 3 m" "$log" && grep -q '"generated"' "$HERE/bsp/$id.json"; then
        # The floor is sculpted ground, not brushes: a generated spec takes the displacement terrain and runs again.
        python3 -I - "$HERE/bsp/$id.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1])); s["terrain"] = True; s["terrain_mat"] = "grass"
open(sys.argv[1], "w").write(json.dumps(s, indent=1) + "\n")
PY
        python3 -I "$HERE/import_bsp.py" "$HERE/bsp/$id.json" "$STORE/$h/source.bsp" > "$log" 2>&1
    fi
    echo "$id exit $? $(tail -n 2 "${TMPDIR:-/tmp}/doc-$id.log" | head -n 1 | cut -c1-160)"
done
