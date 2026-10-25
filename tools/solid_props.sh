#!/bin/bash
# Puts each drawn world's solid prop boxes into its game document (`solid_props`), so a deployed server, whose
# maps pack ships no world/, collides where a client does. Run after ship_docs.sh (which drops them); idempotent.
# Run it under `heavy --` (it starts Godot).
#   GAME=../game-zombie-zone tools/solid_props.sh [id ...]     (every document naming a "world" by default)
HERE="$(cd "$(dirname "$0")" && pwd)"
GAME="${GAME:-$HERE/../../game-zombie-zone}"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
# Every document naming a world, or those of the ids given that do (a map with no drawn world has no props to box).
set -- $(python3 -I - "$HERE/../maps" "$@" <<'PY'
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
godot --headless --path "$GAME" --script tools/solid_props.gd -- "$TMP" "$@" || exit $?
[ -s "$TMP" ] || { echo "solid_props: the script wrote nothing (a parse error?)" >&2; exit 1; }    # a script that fails to load still exits 0
python3 -I - "$HERE/../maps" "$TMP" <<'PY'
import json, sys
boxes = json.load(open(sys.argv[2]))
for id, bs in boxes.items():
    path = "%s/%s.json" % (sys.argv[1], id)
    doc = json.load(open(path))
    doc.pop("solid_props", None)
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
