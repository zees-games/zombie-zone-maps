#!/bin/bash
# Every world's art resolves from published slices: the stamp, each slice (and its dependencies) and every PBR set and model the
# manifest draws. Reads the signed slice manifests of dist/ (after ship_store.sh) or, with ORIGIN=https://dotgames.org, the
# published ones, which is what a player's client reads.
#   [ORIGIN=url] [DIST=dist] tools/check_store.sh [id ...]
HERE="$(cd "$(dirname "$0")" && pwd)"
BSP="${DOTBSP_PATH:-$HERE/../../dot-map/tools/bsp}"
ids=("$@")
[ ${#ids[@]} -gt 0 ] || mapfile -t ids < <(grep -v '^#' "$HERE/convert/ship.tsv" | cut -f1)
packs=()
for id in "${ids[@]}"; do packs+=("$HERE/../world/zz_world_$id/$id.json"); done
exec python3 -I "$BSP/bsp.py" storecheck "${packs[@]}" ${ORIGIN:+--origin "$ORIGIN"} ${ORIGIN:---dist "${DIST:-$HERE/../dist}"}
