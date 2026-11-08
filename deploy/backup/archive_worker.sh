#!/usr/bin/env bash
# Packs a read-only disk into encrypted parts on Google Drive. Runs on the
# temporary AWS machine that aws_archive.sh creates, never on a live server.
#
#   archive_worker.sh pack NAME SOURCE_DIR   tar + zstd into 20 GB parts, then
#                                            prove the parts hold every path
#   archive_worker.sh upload                 rclone copy to the crypt remote
#   archive_worker.sh verify                 compare Drive with the local parts
#
# Why parts and not plain files: Drive takes only a few new files a second, so
# 533,000 files would take days, and a dropped upload resumes per part.
set -euo pipefail

OUT="${ARCHIVE_OUT:-/archive/out}"
REMOTE="${ARCHIVE_REMOTE:-archive:aws}"
CONF="${ARCHIVE_CONF:-/root/rclone.conf}"
PART_SIZE="${ARCHIVE_PART_SIZE:-20G}"
# GNU tools under their Homebrew names when testing on a Mac.
TAR="${TAR:-tar}"; SPLIT="${SPLIT:-split}"; FIND="${FIND:-find}"; SHA256="${SHA256:-sha256sum}"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

pack() {
    local name="$1" src="$2"
    local dir="$OUT/$name"
    [ -f "$dir/DONE" ] && { log "$name already packed"; return; }
    rm -rf "$dir"
    mkdir -p "$dir"

    log "$name: listing $src"
    # Sockets are skipped: tar cannot store them, and they mean nothing on disk.
    "$FIND" "$src" -xdev -not -type s -printf '%y %s %T@ %m %U:%G %P\n' | zstd -q -T0 > "$dir/$name.manifest.zst"
    "$FIND" "$src" -xdev -not -type s -printf '%P\n' | LC_ALL=C sort > "$dir/.want"

    log "$name: packing"
    "$TAR" --create --one-file-system --numeric-owner --sparse --xattrs --xattrs-include='*' --acls \
        -C "$src" . | zstd -q -T0 -3 | "$SPLIT" -b "$PART_SIZE" -d -a 4 - "$dir/$name.tar.zst.part-"

    log "$name: proving the parts hold every path"
    cat "$dir/$name.tar.zst.part-"* | zstd -dc \
        | "$TAR" --list --quoting-style=literal --file=- \
        | sed -e 's|^\./||' -e 's|/$||' -e 's|^\.$||' | LC_ALL=C sort > "$dir/.got"
    if ! cmp -s "$dir/.want" "$dir/.got"; then
        LC_ALL=C comm -3 "$dir/.want" "$dir/.got" | head -20
        log "$name: FAILED, archive does not match the disk"
        exit 1
    fi
    local paths; paths=$(wc -l < "$dir/.want" | tr -d ' ')
    rm -f "$dir/.want" "$dir/.got"

    (cd "$dir" && "$SHA256" "$name".* > "$name.SHA256SUMS")
    echo "$paths" > "$dir/DONE"
    log "$name: packed $paths paths, $(du -sh "$dir" | cut -f1)"
}

upload() {
    log "uploading $OUT"
    # Stop rather than hammer Drive if its 750 GB/day limit is reached; running
    # this again carries on from the parts already there.
    rclone copy "$OUT" "$REMOTE" --config "$CONF" \
        --transfers 2 --checkers 4 --drive-chunk-size 128M \
        --retries 10 --low-level-retries 20 --drive-stop-on-upload-limit \
        --stats 60s --stats-one-line --stats-log-level NOTICE
    log "upload finished"
}

verify() {
    log "checking every part on Drive against the local copy"
    # cryptcheck compares the checksum of the encrypted data, so it proves what
    # Drive really stores without downloading it.
    rclone cryptcheck "$OUT" "$REMOTE" --config "$CONF" --one-way --checkers 4
    log "VERIFIED: everything on Drive matches"
}

cmd="${1:-}"
case "$cmd" in
    pack)   pack "$2" "$3" ;;
    upload) upload ;;
    verify) verify ;;
    *) echo "usage: $0 pack NAME DIR | upload | verify" >&2; exit 2 ;;
esac
