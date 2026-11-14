#!/bin/bash
# Publish each converted map's drawn world (world/zz_world_<id>/) as a pack of its own, <owner>/zz_world_<id>@<version>, listed
# on the maps' collection page instead of a Workshop page each.
#   tools/publish_worlds.sh --version V --member-of ASSET [--dry-run] [id ...] [other publish_pack.sh options]
# V is the version just published for zombie-zone-maps: a client fetches zz_world_<id>@<the maps pack's version> (game-zombie-zone's
# ZzModule._world_key), so a world missing at that version is drawn as boxes. ASSET is the zombie-zone-maps collection's asset id
# (99 on moddingcommunity.com). The release's `worlds` job did this through the site's release sync; a CLI-published maps
# version has no GitHub release, so its worlds go out from here. No id publishes every world named in licence.json.
# Each world's licence.json is cut from the repository's (the entries naming world/zz_world_<id>/, re-rooted) and removed
# afterwards; a world licence.json does not name is skipped and listed. The project is imported once, before the first world.
# Each world also gets a provides.json for the publish (removed afterwards too): kinds [map] and no entries. The site takes a
# credited-community-map licence only in a pack whose provides.kinds includes "map"; with no entries nothing is listed as a
# map of its own (the maps pack's provides.json lists them, and --member-of keeps the world on the collection page). That file
# is ours, so its licence entry is the repository's own (MIT), not the map's.
# The worlds are not pinned anywhere (the game asks for them by key): the lock lines go to a scratch file.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PUB="${DOT_CLOUD:-$HERE/../dot-cloud}/tools/publish_pack.sh"
[ -x "$PUB" ] || { echo "publish_worlds: dot-cloud is not beside this checkout (set DOT_CLOUD)" >&2; exit 2; }
IDS=(); ARGS=(); VERSION=""
while [ $# -gt 0 ]; do
    case $1 in
        --version) VERSION="${2:?}"; shift 2 ;;
        --dry-run|--resume|--no-import) ARGS+=("$1"); shift ;;
        --*) ARGS+=("$1" "${2:?publish_worlds: $1 needs a value}"); shift 2 ;;
        *) IDS+=("${1#zz_world_}"); shift ;;
    esac
done
[ -n "$VERSION" ] || { echo "publish_worlds: --version is required (the maps pack's)" >&2; exit 2; }
[[ " ${ARGS[*]} " == *" --member-of "* ]] || { echo "publish_worlds: --member-of ASSET is required (the maps' collection)" >&2; exit 2; }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"; rm -f "$HERE"/world/zz_world_*/licence.json "$HERE"/world/zz_world_*/provides.json' EXIT
# A licence.json per world into $TMP/<id>.json; prints the ids it wrote one for.
python3 -P - "$HERE" "$TMP" "${IDS[@]}" > "$TMP/ids" <<'PY' || exit 1
import json, os, sys
root, tmp, want = sys.argv[1], sys.argv[2], sys.argv[3:]
per, own = {}, None
META = ("licence.json", "provides.json")  # written for the publish, not the map's
for e in json.load(open(os.path.join(root, "licence.json"))):
    if "exception" not in e and e["paths"] == [""]:
        own = e
    for p in e["paths"]:
        if p.startswith("world/zz_world_"):
            wid = p.split("/")[1][len("zz_world_"):]
            rest, d = p.split("/", 2)[2], os.path.join(root, "world", "zz_world_" + wid)
            # The site refuses "" (the whole pack) for a credited map: name each top-level entry instead.
            paths = [rest] if rest else sorted(n + ("/" if os.path.isdir(os.path.join(d, n)) else "")
                                               for n in os.listdir(d) if n not in META) if os.path.isdir(d) else []
            per.setdefault(wid, []).append(dict(e, paths=paths))
for wid in want or sorted(per):
    if wid not in per or not os.path.isdir(os.path.join(root, "world", "zz_world_" + wid)):
        print("publish_worlds: skip %s: licence.json names no world/zz_world_%s/" % (wid, wid), file=sys.stderr); continue
    if own is None:
        sys.exit("publish_worlds: licence.json has no own-content entry (paths [\"\"], no exception) to license provides.json")
    json.dump(per[wid] + [dict(own, paths=["licence.json", "provides.json"])], open(os.path.join(tmp, wid + ".json"), "w"), indent=2)
    json.dump({"schema": 1, "title": "Zombie Zone world: " + wid, "kinds": ["map"], "games": ["gamemann/game-zombie-zone"],
               "entries": []}, open(os.path.join(tmp, wid + ".provides.json"), "w"), indent=2)
    print(wid)
PY
fails=(); once=()
while read -r id; do
    d="$HERE/world/zz_world_$id"; cp "$TMP/$id.json" "$d/licence.json"; cp "$TMP/$id.provides.json" "$d/provides.json"
    echo "publish_worlds: zz_world_$id@$VERSION" >&2
    "$PUB" publish --source "$d" --id "zz_world_$id" --version "$VERSION" --kind pack --lock "$TMP/lock.json" \
        "${once[@]}" "${ARGS[@]}" < /dev/null || fails+=("$id")
    rm -f "$d/licence.json" "$d/provides.json"; once=(--no-import)
done < "$TMP/ids"
echo "publish_worlds: $(wc -l < "$TMP/ids") worlds, ${#fails[@]} failed${fails[*]:+: ${fails[*]}}"
[ ${#fails[@]} -eq 0 ]
