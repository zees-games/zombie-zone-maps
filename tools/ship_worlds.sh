#!/bin/bash
# Rebuild the worlds the game draws (tools/convert/ship.tsv) from the lossless store, replacing world/zz_world_<id>/.
#   tools/ship_worlds.sh [outdir]   (default world/); SHIP_IDS="id id" limits it to those rows
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$HERE/../world}"
BSP="${DOTBSP_PATH:-$HERE/../../dot-map/tools/bsp}"
grep -v '^#' "$HERE/convert/ship.tsv" | while IFS=$'\t' read -r id key; do
    [ -n "$SHIP_IDS" ] && [[ " $SHIP_IDS " != *" $id "* ]] && continue
    grep -q "^$key " "$HERE/convert/excluded.txt" && { echo "$id excluded"; continue; }
    d="$OUT/zz_world_$id"; rm -rf "$d"; mkdir -p "$d"
    args=(--game-rules "$HERE/convert")
    y0=$(python3 -I -c 'import json,sys; print(json.load(open(sys.argv[1])).get("y0",""))' "$HERE/bsp/$id.json" 2>/dev/null)
    [ -n "$y0" ] && args+=(--y0 "$y0")
    if grep -q '"world_crop"' "$HERE/bsp/$id.json" 2>/dev/null; then    # drawn faces cropped to the street: regen cannot
        h="$(python3 -I -c "import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]])" "${DOTBSP_STORE:-$HOME/mapsrc/store}/index.json" "$key")"
        python3 -I "$HERE/build_worlds.py" "$HERE/bsp/$id.json" "${DOTBSP_STORE:-$HOME/mapsrc/store}/$h/source.bsp" "$OUT" > "$d/regen.log" 2>&1
    else
    python3 -I "$BSP/bsp.py" regen "$key" --out "$d/$id" "${args[@]}" > "$d/regen.log" 2>&1
    fi
    rc=$?; mv "$d/regen.log" "${TMPDIR:-/tmp}/regen-$id.log"; echo "$id exit $rc"
done
# A regenerated world can change its props: refresh the documents' solid_props from it (only when it went to world/).
[ "$OUT" = "$HERE/../world" ] && "$HERE/solid_props.sh" $SHIP_IDS || true
