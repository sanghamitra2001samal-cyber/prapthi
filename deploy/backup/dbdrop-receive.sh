#!/bin/bash
# Forced command for the dbdrop user: store one encrypted database backup
# from stdin. The sender can do nothing else: no shell, no reading, no delete.
# Copies are encrypted on the web server with a public key whose private half
# exists only on the owner's Mac, so this box cannot read them either.
set -euo pipefail
umask 077
DIR=/srv/dbdrop/incoming
MAX=$((500 * 1024 * 1024))
KEEP_DAYS=60
case "${SSH_ORIGINAL_COMMAND:-}" in
  store) ;;
  *) echo "only 'store' is allowed" >&2; exit 2 ;;
esac
out="$DIR/ayaanvoice-$(date -u +%Y%m%d-%H%M%S).bundle"
head -c "$MAX" > "$out.part"
[ -s "$out.part" ] || { rm -f "$out.part"; echo "empty upload" >&2; exit 3; }
mv "$out.part" "$out"
find "$DIR" -name 'ayaanvoice-*.bundle' -mtime +"$KEEP_DAYS" -delete
echo "stored $(basename "$out") $(stat -c %s "$out") bytes"
