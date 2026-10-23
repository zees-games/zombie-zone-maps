#!/bin/bash
# Rebuild every Zombie Zone world pack from the lossless store through dot-map's regen.
#   tools/regen_all.sh [outdir]   (default world/); one prefix per store entry: <outdir>/zz_world_<id>/<id>
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$HERE/../world}"
BSP="${DOTBSP_PATH:-$HERE/../../dot-map/tools/bsp}"
STORE="${DOTBSP_STORE:-$HOME/mapsrc/store}"
python3 -I - "$STORE/index.json" <<'PY' | while read -r key id; do
import json, sys
for k in sorted(json.load(open(sys.argv[1]))):
    if k.startswith("zz/"):
        print(k, k[3:].split("~")[0])
PY
    grep -q "^$key " "$HERE/convert/excluded.txt" && { echo "$id excluded"; continue; }
    d="$OUT/zz_world_$id"; mkdir -p "$d"
    args=(--game-rules "$HERE/convert")
    [ -f "$HERE/convert/maps/$id.json" ] && args+=(--map-rules "$HERE/convert/maps/$id.json")
    python3 -I "$BSP/bsp.py" regen "$key" --out "$d/$id" "${args[@]}" > "$d/regen.log" 2>&1
    echo "$id exit $?"
done
