#!/bin/bash
# Publish the PBR sets and library models the worlds draw as dot-cloud slices (one per map, VRAM-compressed) and stamp each
# world's manifest with licence.store_pack. Run after tools/regen_all.sh; publish the world packs with --depends id@version
# for that stamp (dot-cloud's `publish --depends`), and a client downloads each slice once.
#   [SHIP_IDS="a b"] [DIST=dist] tools/ship_store.sh
HERE="$(cd "$(dirname "$0")" && pwd)"
BSP="${DOTBSP_PATH:-$HERE/../../dot-map/tools/bsp}"
OUT="${STORE_PROJECT:-$HERE/../.stores/project}"
packs=()
while IFS=$'\t' read -r id key; do
    [ -n "$SHIP_IDS" ] && [[ " $SHIP_IDS " != *" $id "* ]] && continue
    m="$HERE/../world/zz_world_$id/$id.json"
    [ -f "$m" ] && packs+=("$m")
done < <(grep -v '^#' "$HERE/convert/ship.tsv")
exec python3 -I "$BSP/bsp.py" storepack "${packs[@]}" --out "$OUT" --dist "${DIST:-$HERE/../dist}" ${STORE_KEY:+--key "$STORE_KEY"}
