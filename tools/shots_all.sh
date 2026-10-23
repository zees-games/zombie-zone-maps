#!/bin/bash
# One spawn frame and one overview frame of every world under <regen dir>, then a contact sheet.
#   tools/shots_all.sh <regen dir, as written by regen_all.sh> <out dir>
# GPU_OFFLOAD=0: the world prefix lives outside the repository, which the GPU boxes do not have.
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$1"; OUT="$2"; mkdir -p "$OUT"
for d in "$SRC"/zz_world_*/; do
    id="$(basename "$d")"; id="${id#zz_world_}"
    for v in spawn overview; do
        GPU_OFFLOAD=0 "$HERE/../../dot-map/tools/screenshot.sh" "$d/$id" "$OUT/${id}_$v.png" --view=$v > "$OUT/${id}_$v.log" 2>&1
    done
done
for v in spawn overview; do
    montage "$OUT"/*_$v.png -tile 6x -geometry 426x240+2+2 -label '%t' "$OUT/sheet_$v.png"
done
