#!/bin/bash
# Rebuild the worlds the game draws (tools/convert/ship.tsv) from the lossless store, replacing world/zz_world_<id>/.
#   tools/ship_worlds.sh [outdir]   (default world/)
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$HERE/../world}"
BSP="${DOTBSP_PATH:-$HERE/../../dot-map/tools/bsp}"
grep -v '^#' "$HERE/convert/ship.tsv" | while IFS=$'\t' read -r id key; do
    grep -q "^$key " "$HERE/convert/excluded.txt" && { echo "$id excluded"; continue; }
    d="$OUT/zz_world_$id"; rm -rf "$d"; mkdir -p "$d"
    python3 -I "$BSP/bsp.py" regen "$key" --out "$d/$id" --game-rules "$HERE/convert" > "$d/regen.log" 2>&1
    rc=$?; mv "$d/regen.log" "${TMPDIR:-/tmp}/regen-$id.log"; echo "$id exit $rc"
done
