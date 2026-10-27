#!/bin/bash
# Publish this repository's own hand-built maps (author "zombie-zone-maps", MIT) to the CDN and pin them in content.lock.json.
#   tools/publish_maps.sh [--id NAME] [--version V | --bump patch|minor|major] [--dry-run] [other publish_pack.sh options]
# Converted community maps (CC BY-NC-ND or no stated licence) are never staged: the site refuses NC/ND and the family ships only
# CC0/MIT/PD/CC-BY. The stage holds maps/<id>.json, hulls and a world pack of the allowed maps, LICENSE, a filtered provides.json
# and a licence.json; the publisher is dot-cloud's tools/publish_pack.sh (token: $DOT_CLI_TOKEN or ~/.config/dot/cli-token).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUB="${DOT_CLOUD:-$HERE/../dot-cloud}/tools/publish_pack.sh"
[ -x "$PUB" ] || { echo "publish_maps: dot-cloud is not beside this checkout (set DOT_CLOUD)" >&2; exit 2; }
ID=zz-maps; ARGS=(); while [ $# -gt 0 ]; do
    case $1 in --id) ID="${2:?}"; shift 2 ;; *) ARGS+=("$1"); shift ;; esac
done
STAGE="$(mktemp -d)"; trap 'rm -rf "$STAGE"' EXIT
python3 -I - "$HERE" "$STAGE" <<'PY'
import json, os, shutil, sys
root, stage = sys.argv[1:3]
own = []
for f in sorted(os.listdir(os.path.join(root, "maps"))):
    if f.endswith(".json") and not f.endswith(".nav.json"):
        d = json.load(open(os.path.join(root, "maps", f)))
        if d.get("author") == "zombie-zone-maps": own.append((f[:-5], d))
if not own: sys.exit("publish_maps: no map of our own to publish")
os.makedirs(os.path.join(stage, "maps"))
for mid, d in own:
    shutil.copy(os.path.join(root, "maps", mid + ".json"), os.path.join(stage, "maps"))
    for sub in ("hulls", ):
        for ext in (".json", ".bin", ".nav.json"):
            p = os.path.join(root, "maps", sub, mid + ext)
            if os.path.isfile(p):
                os.makedirs(os.path.join(stage, "maps", sub), exist_ok=True); shutil.copy(p, os.path.join(stage, "maps", sub))
    if d.get("world"):
        w = os.path.join(root, "world", "zz_world_" + mid)
        if os.path.isdir(w): shutil.copytree(w, os.path.join(stage, "world", "zz_world_" + mid))
ids = {m for m, _ in own}
prov = json.load(open(os.path.join(root, "provides.json")))
prov["entries"] = [e for e in prov["entries"] if e.get("id") in ids]
json.dump(prov, open(os.path.join(stage, "provides.json"), "w"), indent=4)
shutil.copy(os.path.join(root, "LICENSE"), stage)
json.dump([{"paths": [""], "licence": "MIT", "author": "zombie-zone-maps contributors",
            "url": "https://github.com/zees-games/zombie-zone-maps"}], open(os.path.join(stage, "licence.json"), "w"), indent=2)
print("publish_maps: staging %d maps: %s" % (len(own), ", ".join(sorted(ids))))
PY
cd "$HERE"
"$PUB" --source "$STAGE" --id "$ID" --lock "$HERE/content.lock.json" --kind pack --lock-optional --name "Zombie Zone maps" "${ARGS[@]}"
