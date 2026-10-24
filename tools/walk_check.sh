#!/bin/bash
# The walk test: every shipped document (or the ids given) against its source map, by dot-map's `bsp.py audit --doc`.
# Fails when a player-solid brush the global world draws, or ground under a standable top, is missing from the boxes.
#   tools/walk_check.sh [id ...]        (logs in ${TMPDIR:-/tmp}/walk-<id>.log)
HERE="$(cd "$(dirname "$0")" && pwd)"
STORE="${DOTBSP_STORE:-$HOME/mapsrc/store}"
DOCS="${ZZ_DOCS:-$HERE/../maps}"     # another folder of documents, e.g. a re-conversion not yet copied in
BSPPY="${DOTBSP_PATH:-$HERE/../../dot-map/tools/bsp}/bsp.py"
[ -f "$BSPPY" ] || { echo "walk_check: dot-map's tools/bsp was not found; set DOTBSP_PATH" >&2; exit 2; }
fail=0
while IFS=$'\t' read -r id key; do
    [ $# -gt 0 ] && [[ " $* " != *" $id "* ]] && continue
    grep -q "^$key " "$HERE/convert/excluded.txt" && continue
    h="$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1])).get(sys.argv[2],''))" "$STORE/index.json" "$key")"
    [ -n "$h" ] || { echo "$id: no store entry for $key"; fail=1; continue; }
    # y0, and the spec's own crop, clip_y and cut regions, which leave ground out on purpose
    mapfile -t args < <(python3 -I - "$HERE/bsp/$id.json" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
print("--y0=%s" % s.get("y0", 0.0))
if s.get("crop"):
    print("--within=%s" % ",".join(map(str, s["crop"])))
if s.get("clip_y"):
    print("--band=%s" % ",".join(map(str, s["clip_y"])))
# breakables the game cannot break stay passable unless the spec makes them solid (import_bsp.BREAKABLE)
for cls in ("func_breakable", "func_breakable_surf", "func_physbox", "func_physbox_multiplayer"):
    if cls not in s.get("solid_classes", []) or cls == s.get("barricade_class"):
        print("--passable=%s" % cls)
for c in s.get("cut", []):
    if len(c) < 7:
        print("--skip=%s" % ",".join(map(str, c[:6])))
PY
)
    log="${TMPDIR:-/tmp}/walk-$id.log"
    # a document with `world_collision` also collides with its world pack's hulls
    pack="$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1])).get('world',''))" "$DOCS/$id.json")"
    [ -n "$pack" ] && [ -f "$HERE/../world/$pack/$id.json" ] && args+=("--world=$HERE/../world/$pack/$id")
    python3 -I "$BSPPY" audit "$STORE/$h/source.bsp" --doc "$DOCS/$id.json" "${args[@]}" > "$log" 2>&1
    rc=$?
    echo "$id $(grep -h 'lost:' "$log" | sed 's/^ *//')$([ $rc -ne 0 ] && echo "  FAIL (see $log)")"
    [ $rc -ne 0 ] && fail=1
done < <(grep -v '^#' "$HERE/convert/ship.tsv")
exit $fail
