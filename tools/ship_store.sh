#!/bin/bash
# Publish the PBR sets and library models the worlds draw as dot-cloud slices (one per map, VRAM-compressed) and stamp each
# world's manifest with licence.store_pack. Run after tools/regen_all.sh; publish the world packs with --depends id@version
# for that stamp (dot-cloud's `publish --depends`), and a client downloads each slice once.
#   [SHIP_IDS="a b"] [DIST=dist] [STORE_SITE=url STORE_TOKEN_FILE=f [STORE_ORIGIN=url]] tools/ship_store.sh
# With STORE_SITE the slices the stamps name (and their dependencies) are then uploaded through that site's pack API
# (tools/upload_store.py; slice versions are h-hashes, which publish_pack.sh refuses), skipping what STORE_ORIGIN
# (default https://dotgames.org) already serves. Prod: STORE_SITE=https://moddingcommunity.com with gamemann's creator token
# (~/.config/dot/creator-token-prod); dev: https://tmcdev.net. The site signs each manifest.
HERE="$(cd "$(dirname "$0")" && pwd)"
BSP="${DOTBSP_PATH:-$HERE/../../dot-map-convert}"
OUT="${STORE_PROJECT:-$HERE/../.stores/project}"
DIST="${DIST:-$HERE/../dist}"
packs=()
while IFS=$'\t' read -r id key; do
    [ -n "$SHIP_IDS" ] && [[ " $SHIP_IDS " != *" $id "* ]] && continue
    m="$HERE/../world/zz_world_$id/$id.json"
    [ -f "$m" ] && packs+=("$m")
done < <(grep -v '^#' "$HERE/convert/ship.tsv")
python3 -P "$BSP/bsp.py" storepack "${packs[@]}" --out "$OUT" --dist "$DIST" ${STORE_KEY:+--key "$STORE_KEY"} || exit
[ -n "${STORE_SITE:-}" ] || exit 0
[ -s "${STORE_TOKEN_FILE:-}" ] || { echo "ship_store: STORE_SITE needs STORE_TOKEN_FILE (a creator token of the slice owner)" >&2; exit 2; }
exec python3 -P "$HERE/upload_store.py" "${packs[@]}" --site "$STORE_SITE" --token-file "$STORE_TOKEN_FILE" --project "$OUT" \
    --dist "$DIST" --bsp "$BSP" ${STORE_ORIGIN:+--origin "$STORE_ORIGIN"} ${DOT_CLOUD:+--cloud "$DOT_CLOUD"}
