#!/bin/bash
# Puts each drawn world's solid prop boxes into its game document (`solid_props`), so a deployed server, whose
# maps pack ships no world/, collides where a client does. Run after ship_docs.sh (which drops them); idempotent.
# Run it under `heavy --` (it starts Godot).
#   GAME=../game-zombie-zone tools/solid_props.sh [id ...]     (every document naming a "world" by default)
HERE="$(cd "$(dirname "$0")" && pwd)"
GAME="${GAME:-$HERE/../../game-zombie-zone}"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT
if [ $# -eq 0 ]; then
    set -- $(python3 -I - "$HERE/../maps" <<'PY'
import glob, json, os, sys
for f in sorted(glob.glob(os.path.join(sys.argv[1], "*.json"))):
    if json.load(open(f)).get("world"): print(os.path.basename(f)[:-5])
PY
)
fi
godot --headless --path "$GAME" --script tools/solid_props.gd -- "$TMP" "$@" || exit $?
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
