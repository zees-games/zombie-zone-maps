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
hc = s.get("hull_collision") or {}    # the world's hulls collide where the boxes were cut or cropped
if s.get("crop") and not hc.get("uncropped"):
    print("--within=%s" % ",".join(map(str, s["crop"])))
if s.get("walk_limit"):    # a per-map exception to the global 0.002; walk_limit_reason says why (printed below)
    print("--max-loss=%s" % s["walk_limit"])
# One --band, never two (the last would silently win): walk_band, which drop_lids/drop_decor set because
# they removed what stands above the street on purpose, overrides clip_y, which only cuts the boxes.
band = s.get("walk_band") or (s.get("clip_y") if not hc.get("uncropped") else None)
if band:
    print("--band=%s" % ",".join(map(str, band)))
# breakables the game cannot break stay passable unless the spec makes them solid (import_bsp.BREAKABLE)
for cls in ("func_breakable", "func_breakable_surf", "func_physbox", "func_physbox_multiplayer"):
    if cls not in s.get("solid_classes", []) or cls == s.get("barricade_class"):
        print("--passable=%s" % cls)
for i, c in enumerate(s.get("cut", [])):
    if len(c) < 7 and i not in hc.get("cuts", []):
        print("--skip=%s" % ",".join(map(str, c[:6])))
PY
)
    log="${TMPDIR:-/tmp}/walk-$id.log"
    # a document with `world_collision` also collides with its world pack's hulls
    pack="$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1])).get('world',''))" "$DOCS/$id.json")"
    [ -n "$pack" ] && [ -f "$HERE/../world/$pack/$id.json" ] && args+=("--world=$HERE/../world/$pack/$id")
    python3 -I "$BSPPY" audit "$STORE/$h/source.bsp" --doc "$DOCS/$id.json" "${args[@]}" > "$log" 2>&1
    rc=$?
    reason="$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1])).get('walk_limit_reason',''))" "$HERE/bsp/$id.json")"
    [ -n "$reason" ] && echo "$id: walk limit exception: $reason"
    echo "$id $(grep -h 'lost:' "$log" | sed 's/^ *//')$([ $rc -ne 0 ] && echo "  FAIL (see $log)")"
    [ $rc -ne 0 ] && fail=1
done < <(grep -v '^#' "$HERE/convert/ship.tsv")
exit $fail
