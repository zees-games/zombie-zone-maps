"""Upload the art slices the given world manifests name (licence.store_pack, and every dependency below it) to the site,
skipping each one the content origin already serves. Called by tools/ship_store.sh after `bsp.py storepack` when
STORE_SITE is set; usable alone after a ship_store run in the same checkout.

Slice versions are content hashes (h1234abcd), which tools/publish_pack.sh refuses (it checks semver); the site's pack API
takes any path-safe version, so this runs dot-cloud's CLI (`dot_cloud_cli.gd publish --upload --resume`) directly on each
slice's source folder under the storepack project. The site signs the manifest. Dependencies go first.

  python3 -P tools/upload_store.py --site URL --token-file F --project DIR --dist DIR [--origin URL] [--cloud DIR] world.json...
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifests", nargs="+")
    ap.add_argument("--site", required=True, help="the site whose API takes the pack (https://moddingcommunity.com, https://tmcdev.net)")
    ap.add_argument("--token-file", required=True, help="a creator token of the slice owner (gamemann)")
    ap.add_argument("--project", required=True, help="the storepack project (its slices/<name> are the sources)")
    ap.add_argument("--dist", required=True, help="the storepack --dist (the locally signed manifests name each slice's dependencies)")
    ap.add_argument("--origin", default="https://dotgames.org", help="the content origin to check first")
    ap.add_argument("--cloud", default=os.path.expanduser("~/godot/dot-cloud"))
    ap.add_argument("--bsp", default=os.path.expanduser("~/godot/dot-map-convert"), help="dot-map-convert (for dotbsp.storecheck)")
    ap.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    ap.add_argument("--prefix", default="store-")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, a.bsp)
    from dotbsp import storecheck

    order, seen = [], set()

    def visit(sid, version):
        if (sid, version) in seen:
            return
        seen.add((sid, version))
        local = storecheck.fetch(sid, version, dist=a.dist)
        if local is None:
            sys.exit("upload_store: %s@%s is not in %s (run tools/ship_store.sh first)" % (sid, version, a.dist))
        deps = [(d["id"], d["version"]) for d in local.get("dependencies", [])]
        for d in deps:
            visit(*d)
        order.append((sid, version, deps))

    for p in a.manifests:
        with open(p) as f:
            pack = json.load(f)["licence"].get("store_pack")
        if not pack:
            print("upload_store: %s has no licence.store_pack, skipped" % p, file=sys.stderr)
            continue
        for s in pack.get("shared", []):
            visit(s["id"], s["version"])
        visit(pack["id"], pack["version"])

    cli = os.path.join(a.cloud, "addons/dot_cloud/publish/dot_cloud_cli.gd")
    sent = there = failed = 0
    for sid, version, deps in order:
        if storecheck.fetch(sid, version, origin=a.origin) is not None:
            there += 1
            continue
        repo = sid.split("/", 1)[1]
        src = os.path.join(os.path.abspath(a.project), "slices", repo[len(a.prefix):] if repo.startswith(a.prefix) else repo)
        if not os.path.isdir(src):
            print("upload_store: %s@%s: no source folder %s" % (sid, version, src), file=sys.stderr)
            failed += 1
            continue
        print("upload_store: %s@%s (%d dependencies) from %s" % (sid, version, len(deps), src), flush=True)
        if a.dry_run:
            continue
        with tempfile.TemporaryDirectory() as out:
            cmd = [a.godot, "--headless", "--path", a.cloud, "--script", cli, "--", "publish", "--upload", "--resume",
                   "--token-file", os.path.abspath(a.token_file), "--site", a.site, "--source", src, "--out", out,
                   "--id", repo, "--version", version]
            for d in deps:
                cmd += ["--depends", "%s@%s" % d]
            for attempt in range(8):
                r = subprocess.run(cmd, timeout=7200, capture_output=True, text=True)
                wait = re.search(r"rate_limited.*?in (\d+)s", r.stdout + r.stderr)
                if r.returncode == 0 or not wait:
                    break
                time.sleep(int(wait.group(1)) + 2)  # the site caps claims per minute
        tail = [l for l in (r.stdout + r.stderr).splitlines() if l.strip() and not l.lstrip().startswith("[")][-6:]
        if r.returncode != 0:
            print("upload_store: %s@%s FAILED rc=%d:\n  %s" % (sid, version, r.returncode, "\n  ".join(tail)), file=sys.stderr)
            failed += 1
            continue
        if storecheck.fetch(sid, version, origin=a.origin) is None:
            print("upload_store: %s@%s uploaded but %s does not serve it yet:\n  %s" % (sid, version, a.origin, "\n  ".join(tail)),
                  file=sys.stderr)
            failed += 1
            continue
        sent += 1
    print("upload_store: %d slices: %d uploaded, %d already served, %d failed" % (len(order), sent, there, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
