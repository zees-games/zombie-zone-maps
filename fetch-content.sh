#!/bin/bash
# Fetch what this repository's content.lock.json names from the CDN (hash-checked, once; present files skipped).
# Thin wrapper: the one fetcher is dot-bootstrap/tools/fetch_lock.sh, whose header lists every option (--only/--except ITEM,
# --cdn URL, --list). The CDN URL comes from --cdn, $DOT_CDN_URL, or DOT_CDN_URL in dot-bootstrap/.env (one edit for every repo).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for tool in "${DOT_BOOTSTRAP:-$HERE/../dot-bootstrap}/tools/fetch_lock.sh" "$HERE/tools/fetch_lock.sh"; do
    [ -x "$tool" ] && exec "$tool" "$HERE/content.lock.json" --root "$HERE" "$@"
done
echo "fetch-content: dot-bootstrap is not beside this checkout; clone it or set DOT_BOOTSTRAP" >&2; exit 2
