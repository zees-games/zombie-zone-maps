#!/bin/bash
# Puts each drawn world's solid prop boxes into its game document (`solid_props`), so a deployed server, whose
# maps pack ships no world/, collides where a client does. Run after ship_docs.sh (which drops them); idempotent.
# Run it under `heavy --` (it starts Godot).
#   GAME=../game-zombie-zone tools/solid_props.sh [id ...]     (every document naming a "world" by default)
#   FROM_DOC=1 re-filters each document's boxes instead of rebuilding them (after a change to how the horde's graph cuts props).
HERE="$(cd "$(dirname "$0")" && pwd)"
GAME="${GAME:-$HERE/../../game-zombie-zone}"
TMP="$(mktemp)"
# solid_props.gd reads every library model from the game's .stores/model-library by absolute path (GLTFDocument), never
# through res:// and never through a world's licence model_store (a path relative to wherever the world was converted).
# Through res:// a model with a .import (the shared store holds some) loads only in a checkout whose .godot imported it:
# elsewhere ResourceLoader.exists() is true, load() fails and the prop was dropped silently, so the counts followed the
# checkout (08404a0: gm_balkans 763 -> 2434). The script fails when a solid model does not load. An empty .stores
# directory (a bootstrap or hv preflight leaves one) is replaced by the link for the run, or every model is "missing"; the
# empty directory comes back on exit, because a link left there makes hv/gpu.sh upload the whole 5.8G store (--copy-links).
LINKED=
STORES="$(cd "$HERE/.." && pwd)/.stores"
[ -d "$GAME/.stores" ] && [ ! -L "$GAME/.stores" ] && rmdir "$GAME/.stores" 2>/dev/null
if [ ! -e "$GAME/.stores" ]; then ln -s "$STORES" "$GAME/.stores" && LINKED=1; fi
[ -d "$GAME/.stores/model-library" ] || { echo "solid_props: $GAME/.stores/model-library is missing (link $STORES there)" >&2; exit 1; }
trap 'rm -f "$TMP"; [ -n "$LINKED" ] && rm -f "$GAME/.stores" && mkdir "$GAME/.stores"' EXIT
# Every document naming a world, or those of the ids given that do (a map with no drawn world has no props to box).
set -- $(python3 -P - "$HERE/../maps" "$@" <<'PY'
import glob, json, os, sys
want = sys.argv[2:]
for f in sorted(glob.glob(os.path.join(sys.argv[1], "*.json"))):
    id = os.path.basename(f)[:-5]
    if (not want or id in want) and json.load(open(f)).get("world"): print(id)
PY
)
[ $# -gt 0 ] || { echo "solid_props: no document with a world"; exit 0; }
[ -f "$GAME/.godot/global_script_class_cache.cfg" ] || godot --headless --path "$GAME" --import > /dev/null 2>&1    # a fresh worktree has no class cache
: > "$TMP"
godot --headless --path "$GAME" --script tools/solid_props.gd -- "$TMP" ${FROM_DOC:+--from-doc} "$@" || exit $?
[ -s "$TMP" ] || { echo "solid_props: the script wrote nothing (a parse error?)" >&2; exit 1; }    # a script that fails to load still exits 0
python3 -P - "$HERE/../maps" "$TMP" "$HERE" "${DOTBSP_PATH:-$HERE/../../dot-map-convert}" <<'PY'
import json, os, sys
sys.path.insert(0, sys.argv[3])
sys.path.insert(0, sys.argv[4])
import build_maps
boxes = json.load(open(sys.argv[2]))
boxes.pop("_loose", None)
for id, bs in boxes.items():
    path = "%s/%s.json" % (sys.argv[1], id)
    doc = json.load(open(path))
    doc.pop("solid_props", None)
    doc.pop("loose_toys", None)    # maps carry no loose props or supports any more (owner 2026-11-08)
    doc.pop("supports", None)
    doc.pop("toys", None)
    if bs:
        new = {}
        for k, v in doc.items():    # right after "props", where a reader looks for it
            new[k] = v
            if k == "props":
                new["solid_props"] = bs
        doc = new
    with open(path, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
PY
