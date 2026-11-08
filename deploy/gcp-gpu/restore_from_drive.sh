#!/usr/bin/env bash
# Runs ON the new GCP GPU machine, as root. Streams the AWS GPU disk back out of
# the encrypted Drive copy (deploy/backup) into /restore, taking only what the
# model services need. Nothing is staged: Drive -> zstd -> tar in one pipe.
# The crypt remote authenticates every block, so a damaged part stops the pipe.
#
#   restore_from_drive.sh /root/rclone.conf
set -euo pipefail
CONF="${1:?usage: $0 RCLONE_CONF}"
OUT=/restore
log() { echo "[$(date -u +%H:%M:%S)] $*"; }

export DEBIAN_FRONTEND=noninteractive
cloud-init status --wait >/dev/null || true
apt-get -o DPkg::Lock::Timeout=300 update -q
apt-get -o DPkg::Lock::Timeout=300 install -y -q zstd acl curl

if ! command -v rclone >/dev/null; then
    rv=v1.75.2; deb="rclone-$rv-linux-amd64.deb"
    (cd /tmp && curl -fsSLO "https://downloads.rclone.org/$rv/$deb" \
        && curl -fsSL "https://downloads.rclone.org/$rv/SHA256SUMS" | grep " $deb\$" | sha256sum -c --quiet \
        && dpkg -i "$deb" >/dev/null && rm -f "$deb")
fi

# What the services run from. The swapfile, kernel, snaps and AWS agents stay behind.
MEMBERS=(
    ./home/ubuntu
    ./usr/local/cuda ./usr/local/cuda-12.8 ./usr/local/cuda-12.9 ./usr/local/cuda-13.2
    ./usr/local/bin ./usr/local/lib
    ./var/lib/docker ./var/lib/containerd ./etc/docker
    ./etc/systemd/system ./etc/ld.so.conf.d ./etc/sysctl.d ./etc/environment ./etc/fstab
    ./etc/apt/sources.list.d ./etc/apt/keyrings ./usr/share/keyrings
    ./etc/os-release ./var/lib/dpkg/status
)

mkdir -p "$OUT"
log "streaming live-p1 from Drive into $OUT"
rclone lsf archive:aws/live-p1 --config "$CONF" --include 'live-p1.tar.zst.part-*' | sort \
    | while read -r part; do
        # A failed part must end the stream, not be skipped.
        rclone cat "archive:aws/live-p1/$part" --config "$CONF" --drive-chunk-size 128M || exit 1
    done \
    | zstd -dc \
    | tar --extract --numeric-owner --sparse --xattrs --xattrs-include='*' --acls \
        -C "$OUT" "${MEMBERS[@]}"
log "restored: $(du -sh "$OUT" | cut -f1)"
touch "$OUT/.RESTORE_DONE"
