#!/bin/bash
# Rebuild every Zombie Zone world pack from the lossless store through dot-map's regen, keeping the pack in place.
#   tools/regen_all.sh [outdir]   (default world/); one prefix per ship.tsv row: <outdir>/zz_world_<id>/<id>
# The id is the document id from ship.tsv, never the store key's name (zm_4way_tunnel is store key zm_4way_tunnel_v2):
# the spec tools/bsp/<id>.json is found by the id, and its y0 must reach regen or the bin lands y0 metres off its movers.
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$HERE/../world}"
BSP="${DOTBSP_PATH:-$HERE/../../dot-map/tools/bsp}"
rc=0
while IFS=$'\t' read -r id key; do
    grep -q "^$key " "$HERE/convert/excluded.txt" && { echo "$id excluded"; continue; }
    [ -n "$REGEN_IDS" ] && [[ " $REGEN_IDS " != *" $id "* ]] && continue
    d="$OUT/zz_world_$id"; mkdir -p "$d"
    args=(--game-rules "$HERE/convert")
    [ -f "$HERE/convert/maps/$id.json" ] && args+=(--map-rules "$HERE/convert/maps/$id.json")
    y0=$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1])).get("y0",""))' "$HERE/bsp/$id.json" 2>/dev/null)
    [ -n "$y0" ] && args+=(--y0 "$y0")
    python3 -I "$BSP/bsp.py" regen "$key" --out "$d/$id" "${args[@]}" > "${TMPDIR:-/tmp}/regen-$id.log" 2>&1 < /dev/null
    r=$?; [ $r -ne 0 ] && rc=1
    echo "$id exit $r${y0:+ y0 $y0}"
done < <(grep -v '^#' "$HERE/convert/ship.tsv")
exit $rc
